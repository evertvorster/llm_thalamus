from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple, Union

from .base import LLMProvider, ProviderError
from .types import (
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    Message,
    ModelInfo,
    StreamEvent,
    ToolCall,
    ToolDef,
    Usage,
)


def _http_json(
    url: str,
    payload: Dict[str, Any],
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except Exception as e:
        raise ProviderError(f"Ollama HTTP error: {e}") from e


def _http_jsonl_stream(
    url: str,
    payload: Dict[str, Any],
    timeout_s: float = 120.0,
) -> Iterator[Dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            # Ollama streams JSON lines
            for line in resp:
                if not line:
                    continue
                s = line.decode("utf-8").strip()
                if not s:
                    continue
                yield json.loads(s)
    except Exception as e:
        raise ProviderError(f"Ollama stream error: {e}") from e


def _to_ollama_messages(msgs: Sequence[Message]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in msgs:
        d: Dict[str, Any] = {"role": m.role, "content": m.content}
        # Ollama tool-result messages use "tool_name" (not "name").
        # Keep "name" for non-tool messages where a backend may accept it.
        if m.name:
            if m.role == "tool":
                d["tool_name"] = m.name
            else:
                d["name"] = m.name
        # tool_call_id is not universally supported by Ollama; we carry it internally.
        out.append(d)
    return out


def _to_ollama_tools(tools: Sequence[ToolDef]) -> List[Dict[str, Any]]:
    """
    Ollama uses a JSON structure similar to OpenAI tools:
    { "type": "function", "function": { "name": ..., "description": ..., "parameters": {...} } }
    """
    out: List[Dict[str, Any]] = []
    for t in tools:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
        )
    return out


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: Optional[str] = None) -> None:
        self._base_url = base_url or os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")

    def provider_name(self) -> str:
        return "ollama"

    def diagnostics(self) -> Dict[str, str]:
        return {"base_url": self._base_url}

    def ping(self) -> None:
        # Ollama has /api/tags (POST not required), but simplest is just list_models.
        self.list_models()

    # NEW: provider-level capability declaration (used by startup validation)
    def capabilities(self) -> Sequence[str]:
        # Ollama supports:
        # - /api/chat (chat)
        # - streaming JSONL (streaming)
        # - tools / tool_calls (tools)
        # - "format": "json" (json_mode)
        # - /api/embeddings (embeddings)
        return ("chat", "streaming", "tools", "json_mode", "embeddings")

    def list_models(self) -> List[ModelInfo]:
        url = f"{self._base_url}/api/tags"
        # /api/tags is GET in many clients, but Ollama supports it; use urllib GET.
        try:
            with urllib.request.urlopen(url, timeout=30.0) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
        except Exception as e:
            raise ProviderError(f"Ollama tags error: {e}") from e

        models: List[ModelInfo] = []
        for m in data.get("models", []) or []:
            # Ollama tag fields vary; keep robust
            name = m.get("name") or ""
            details = m.get("details") or {}
            models.append(
                ModelInfo(
                    name=name,
                    family=details.get("family"),
                    parameter_size=details.get("parameter_size"),
                    quantization=details.get("quantization_level"),
                    # context length is not always provided
                    context_length=None,
                    capabilities=None,  # fill via explicit capability probes if you want
                )
            )
        return models

    def chat_stream(self, req: ChatRequest) -> Iterator[StreamEvent]:
        url = f"{self._base_url}/api/chat"

        payload: Dict[str, Any] = {
            "model": req.model,
            "messages": _to_ollama_messages(req.messages),
            "stream": True,
        }

        if req.tools:
            payload["tools"] = _to_ollama_tools(req.tools)

        if req.response_format is not None:
            # Ollama uses "format": "json" or JSON schema dict
            if req.response_format == "json":
                payload["format"] = "json"
            elif isinstance(req.response_format, dict):
                payload["format"] = req.response_format
            else:
                raise ProviderError(f"Unsupported response_format: {req.response_format!r}")

        if req.params:
            opts: Dict[str, Any] = {}
            if req.params.temperature is not None:
                opts["temperature"] = req.params.temperature
            if req.params.top_p is not None:
                opts["top_p"] = req.params.top_p
            if req.params.top_k is not None:
                opts["top_k"] = req.params.top_k
            if req.params.seed is not None:
                opts["seed"] = req.params.seed
            if req.params.num_ctx is not None:
                opts["num_ctx"] = req.params.num_ctx
            if req.params.stop is not None:
                opts["stop"] = req.params.stop
            if req.params.extra:
                # explicit escape hatch
                opts.update(req.params.extra)
            if opts:
                payload["options"] = opts

        # Accumulate tool calls if provider emits them across deltas
        # Ollama typically emits a final tool_calls in message, but keep flexible.
        for obj in _http_jsonl_stream(url, payload):
            if obj.get("error"):
                yield StreamEvent(type="error", error=str(obj.get("error")))
                return

            # Common Ollama stream shape:
            # { "message": { "role": "assistant", "content": "..." }, "done": false, ... }
            msg = obj.get("message") or {}
            content = msg.get("content")
            if content:
                yield StreamEvent(type="delta_text", text=content)

            # Some models/providers may provide "thinking" separately (not standard in Ollama),
            # but keep a hook if you later add a convention.
            thinking = msg.get("thinking")
            if thinking:
                yield StreamEvent(type="delta_thinking", text=thinking)

            # Tool calls (Ollama supports tools; shape can vary by model)
            # Expected-ish shape:
            # msg["tool_calls"] = [{ "id": "...", "function": { "name": "...", "arguments": "..." } }, ...]
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function") or {}

                    args = fn.get("arguments")
                    if args is None:
                        arguments_json = ""
                    elif isinstance(args, str):
                        arguments_json = args
                    else:
                        # Ollama typically provides arguments as a JSON object.
                        # Preserve valid JSON instead of Python repr (single quotes).
                        arguments_json = json.dumps(args, ensure_ascii=False)

                    yield StreamEvent(
                        type="tool_call",
                        tool_call=ToolCall(
                            id=str(tc.get("id") or ""),
                            name=str(fn.get("name") or ""),
                            arguments_json=arguments_json,
                        ),
                    )

            # Usage: Ollama may include prompt_eval_count / eval_count
            if "prompt_eval_count" in obj or "eval_count" in obj:
                usage = Usage(
                    input_tokens=obj.get("prompt_eval_count"),
                    output_tokens=obj.get("eval_count"),
                    total_tokens=None,
                )
                yield StreamEvent(type="usage", usage=usage)

            if obj.get("done") is True:
                yield StreamEvent(type="done")
                return

        # If stream ends without done, emit done defensively
        yield StreamEvent(type="done")

    def chat(self, req: ChatRequest) -> ChatResponse:
        # Non-stream convenience: call stream, stitch, capture last tool_calls if any.
        text_parts: List[str] = []
        tool_calls: List[ToolCall] = []
        usage: Optional[Usage] = None
        for ev in self.chat_stream(req):
            if ev.type == "delta_text" and ev.text:
                text_parts.append(ev.text)
            elif ev.type == "tool_call" and ev.tool_call:
                tool_calls.append(ev.tool_call)
            elif ev.type == "usage" and ev.usage:
                usage = ev.usage
            elif ev.type == "error":
                raise ProviderError(ev.error or "Unknown provider error")
            elif ev.type == "done":
                break

        msg = Message(role="assistant", content="".join(text_parts))
        return ChatResponse(
            message=msg,
            tool_calls=tool_calls or None,
            usage=usage,
        )

    def embed(self, req: EmbeddingRequest) -> EmbeddingResponse:
        url = f"{self._base_url}/api/embeddings"

        vectors: List[List[float]] = []
        for text in req.texts:
            payload = {"model": req.model, "prompt": text}
            obj = _http_json(url, payload, timeout_s=120.0)
            emb = obj.get("embedding")
            if not isinstance(emb, list):
                raise ProviderError("Ollama embeddings: missing embedding vector")
            vectors.append([float(x) for x in emb])

        return EmbeddingResponse(vectors=vectors)
