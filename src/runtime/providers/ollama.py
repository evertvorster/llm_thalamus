from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional, Sequence, Union

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


def _as_dict(obj: Any) -> Dict[str, Any]:
    """Best-effort conversion for pydantic-ish objects, dataclasses, or plain dicts."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    # pydantic v2
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()  # type: ignore[attr-defined]
        except Exception:
            pass
    # pydantic v1
    if hasattr(obj, "dict"):
        try:
            return obj.dict()  # type: ignore[attr-defined]
        except Exception:
            pass
    # fallback: try vars()
    try:
        return dict(vars(obj))
    except Exception:
        return {}


def _tooldef_to_ollama_tool(td: ToolDef) -> Dict[str, Any]:
    """
    Ollama /api/chat tool schema is OpenAI-ish:
      {"type":"function","function":{"name":..., "description":..., "parameters":{...}}}
    """
    return {
        "type": "function",
        "function": {
            "name": td.name,
            "description": td.description,
            "parameters": td.parameters or {"type": "object", "properties": {}},
        },
    }


def _extract_tool_calls_from_message(msg_obj: Any) -> List[ToolCall]:
    """
    python-ollama returns tool calls on Message.tool_calls, typically as a list of dict-like
    objects with a nested function payload. We normalize to runtime.providers.types.ToolCall.
    """
    msg = _as_dict(msg_obj)
    raw_calls = msg.get("tool_calls") or []
    out: List[ToolCall] = []

    for i, rc in enumerate(raw_calls):
        d = _as_dict(rc)

        # Common shapes we handle:
        # 1) {"id": "...", "type": "function", "function": {"name":"x","arguments":{...}}}
        # 2) {"function": {"name":"x","arguments":{...}}}  (no id)
        # 3) {"name":"x","arguments":{...}} (flattened)
        call_id = str(d.get("id") or f"toolcall_{i}")
        fn = d.get("function")
        if fn is None and ("name" in d or "arguments" in d):
            fn = d

        fn_d = _as_dict(fn)
        name = str(fn_d.get("name") or d.get("name") or "")
        args = fn_d.get("arguments", d.get("arguments", {}))

        if isinstance(args, str):
            # sometimes already JSON
            args_json = args
        else:
            try:
                args_json = json.dumps(args if args is not None else {}, ensure_ascii=False)
            except Exception:
                args_json = "{}"

        if name:
            out.append(ToolCall(id=call_id, name=name, arguments_json=args_json))

    return out


def _chatparams_to_options(params: Any) -> Dict[str, Any]:
    """
    Map runtime ChatParams onto Ollama options (best-effort).
    Ollama supports many more keys; we pass through params.extra verbatim.
    """
    if params is None:
        return {}

    # runtime.types.ChatParams is a dataclass (frozen) but might arrive as dict in some tests/tools.
    d = _as_dict(params)

    opts: Dict[str, Any] = {}
    # These names match Ollama's common option keys.
    if d.get("temperature") is not None:
        opts["temperature"] = d["temperature"]
    if d.get("top_p") is not None:
        opts["top_p"] = d["top_p"]
    if d.get("top_k") is not None:
        opts["top_k"] = d["top_k"]
    if d.get("seed") is not None:
        opts["seed"] = d["seed"]
    if d.get("num_ctx") is not None:
        opts["num_ctx"] = d["num_ctx"]
    if d.get("stop") is not None:
        opts["stop"] = d["stop"]

    extra = d.get("extra")
    if isinstance(extra, dict):
        # explicit escape hatch
        opts.update(extra)

    return opts


def _response_format_to_ollama_format(fmt: Any) -> Any:
    """
    runtime ChatRequest.response_format:
      - None
      - "json"
      - dict JSON schema
    python-ollama Client.chat format:
      - '' | 'json' | dict | None
    """
    if fmt is None:
        return None
    if fmt == "json":
        return "json"
    if isinstance(fmt, dict):
        return fmt
    # unknown: ignore
    return None


class OllamaProvider(LLMProvider):
    """
    Provider backed by the official python-ollama client.

    This preserves llm_thalamus' internal provider contract (base.py + types.py) while
    delegating transport, streaming, and tool-call wire formats to python-ollama.
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        try:
            import ollama as ollama_pkg  # python-ollama
        except GeneratorExit:
            sent_done = True
            return
        except Exception as e:
            raise ProviderError(f"python-ollama is not available: {e}") from e

        self._ollama = ollama_pkg

        # Create a client. Different versions have used different kwarg names.
        # We probe supported init kwargs at runtime to avoid hard dependency on one signature.
        try:
            import inspect

            sig = inspect.signature(self._ollama.Client)
            kwargs: Dict[str, Any] = {}
            if base_url:
                # Common parameter names across versions:
                for k in ("host", "base_url", "url"):
                    if k in sig.parameters:
                        kwargs[k] = base_url
                        break
            self._client = self._ollama.Client(**kwargs)
        except Exception:
            # Fallback: try no-arg client; caller can still rely on OLLAMA_HOST env var.
            try:
                self._client = self._ollama.Client()
            except Exception as e:
                raise ProviderError(f"Failed to construct ollama.Client(): {e}") from e

        self._base_url = base_url

    def provider_name(self) -> str:
        return "ollama"

    def diagnostics(self) -> Dict[str, str]:
        return {
            "provider": "ollama",
            "transport": "python-ollama",
            "base_url": str(self._base_url or ""),
            "client_module": str(getattr(self._ollama, "__file__", "")),
        }

    def ping(self) -> None:
        # Best-effort: list() is cheap and exercises connectivity.
        try:
            _ = self._client.list()
        except Exception as e:
            raise ProviderError(f"Ollama ping failed: {e}") from e

    def capabilities(self) -> Sequence[str]:
        # Provider-level capabilities: chat + embeddings + tools + json_mode + streaming.
        return ["chat", "embeddings", "tools", "json_mode", "streaming"]

    def list_models(self) -> List[ModelInfo]:
        try:
            resp = self._client.list()
        except Exception as e:
            raise ProviderError(f"Ollama list() failed: {e}") from e

        d = _as_dict(resp)
        models = d.get("models") or []
        out: List[ModelInfo] = []
        for m in models:
            md = _as_dict(m)
            name = str(md.get("name") or md.get("model") or "").strip()
            if not name:
                continue
            # Ollama list response often includes: name, modified_at, size, digest, details, etc.
            # We conservatively fill what we can.
            out.append(
                ModelInfo(
                    name=name,
                    family=str(_as_dict(md.get("details")).get("family") or "") or None,
                    parameter_size=str(_as_dict(md.get("details")).get("parameter_size") or "") or None,
                    quantization=str(_as_dict(md.get("details")).get("quantization_level") or "") or None,
                    context_length=None,
                    capabilities=["chat", "embeddings", "tools", "json_mode", "streaming"],
                )
            )
        return out

    def chat_stream(self, req: ChatRequest) -> Iterator[StreamEvent]:
        """
        Streaming chat. Contract: MUST end with StreamEvent(type="done") or StreamEvent(type="error").
        """
        # Convert runtime messages to python-ollama message dicts.
        messages: List[Dict[str, Any]] = []
        for m in req.messages:
            md: Dict[str, Any] = {"role": m.role, "content": m.content}
            # For tool messages: python-ollama supports tool_name; role 'tool' content is fine.
            if m.role == "tool":
                if m.name:
                    md["tool_name"] = m.name
            messages.append(md)

        tools = None
        if req.tools:
            tools = [_tooldef_to_ollama_tool(td) for td in req.tools]

        options = _chatparams_to_options(req.params)
        fmt = _response_format_to_ollama_format(req.response_format)

        # For delta computation (some clients return accumulated text, some return deltas).
        prev_content = ""
        prev_thinking = ""
        sent_done = False
        saw_tool_calls = False
        last_nontrivial_thinking = ""

        try:
            it = self._client.chat(
                model=req.model,
                messages=messages,
                tools=tools,
                stream=True,
                format=fmt,
                options=options or None,
            )

            for chunk in it:
                cd = _as_dict(chunk)
                done = bool(cd.get("done"))

                msg_obj = getattr(chunk, "message", None)
                msg = _as_dict(msg_obj)
                content = str(msg.get("content") or "")
                thinking = str(msg.get("thinking") or "")
                if thinking and thinking != "Thinking":
                    last_nontrivial_thinking = thinking

                # Emit delta_text (compute delta if chunk is cumulative)
                if content:
                    if content.startswith(prev_content):
                        delta = content[len(prev_content) :]
                    else:
                        delta = content
                    prev_content = content
                    if delta:
                        yield StreamEvent(type="delta_text", text=delta)

                # Emit delta_thinking with a small filter to avoid placeholder spam
                if thinking and thinking != "Thinking":
                    if thinking.startswith(prev_thinking):
                        tdelta = thinking[len(prev_thinking) :]
                    else:
                        tdelta = thinking
                    prev_thinking = thinking
                    if tdelta:
                        yield StreamEvent(type="delta_thinking", text=tdelta)

                # Emit tool calls if present
                tool_calls = _extract_tool_calls_from_message(msg_obj)
                if tool_calls:
                    saw_tool_calls = True
                for tc in tool_calls:
                    yield StreamEvent(type="tool_call", tool_call=tc)

                # Emit usage opportunistically (usually most meaningful at done)
                if done:
                    # If we never received any assistant content AND no tool calls,
                    # downstream structured parsers will crash on json.loads("").
                    if not prev_content and not saw_tool_calls:
                        reason = str(cd.get("done_reason") or "")
                        # Include the last known thinking text to help diagnose "thinking-only" streams.
                        last_thinking = last_nontrivial_thinking
                        yield StreamEvent(
                            type="error",
                            error=(
                                "Ollama returned an empty assistant message. "
                                f"model={req.model!r} done_reason={reason!r} "
                                f"thinking_tail={last_thinking[-120:]!r} "
                                "This often indicates an incompatible option (e.g. num_predict too low) "
                                "or a format/json-mode mismatch."
                            ),
                        )
                        sent_done = True
                        break

                    usage = Usage(
                        input_tokens=cd.get("prompt_eval_count"),
                        output_tokens=cd.get("eval_count"),
                        total_tokens=None,
                    )
                    if usage.input_tokens is not None or usage.output_tokens is not None:
                        yield StreamEvent(type="usage", usage=usage)

                    yield StreamEvent(type="done")
                    sent_done = True
                    break

        except GeneratorExit:
            # Stream consumer cancelled/closed the generator.
            # MUST stop immediately; do not yield from finally.
            sent_done = True
            return
        except (getattr(self._ollama, "RequestError", Exception), getattr(self._ollama, "ResponseError", Exception)) as e:
            yield StreamEvent(type="error", error=str(e))
            sent_done = True
        except Exception as e:
            yield StreamEvent(type="error", error=str(e))
            sent_done = True
        finally:
            # Hard contract guard: ensure we always terminate.
            if not sent_done:
                yield StreamEvent(type="done")

    def chat(self, req: ChatRequest) -> ChatResponse:
        """
        Non-stream convenience wrapper around Client.chat(stream=False).
        """
        messages: List[Dict[str, Any]] = []
        for m in req.messages:
            md: Dict[str, Any] = {"role": m.role, "content": m.content}
            if m.role == "tool" and m.name:
                md["tool_name"] = m.name
            messages.append(md)

        tools = None
        if req.tools:
            tools = [_tooldef_to_ollama_tool(td) for td in req.tools]

        options = _chatparams_to_options(req.params)
        fmt = _response_format_to_ollama_format(req.response_format)

        try:
            resp = self._client.chat(
                model=req.model,
                messages=messages,
                tools=tools,
                stream=False,
                format=fmt,
                options=options or None,
            )
        except Exception as e:
            raise ProviderError(f"Ollama chat() failed: {e}") from e

        rd = _as_dict(resp)
        msg_obj = getattr(resp, "message", None)
        msgd = _as_dict(msg_obj)

        tool_calls = _extract_tool_calls_from_message(msg_obj)
        usage = Usage(
            input_tokens=rd.get("prompt_eval_count"),
            output_tokens=rd.get("eval_count"),
            total_tokens=None,
        )
        if usage.input_tokens is None and usage.output_tokens is None:
            usage = None  # type: ignore[assignment]

        return ChatResponse(
            message=Message(role="assistant", content=str(msgd.get("content") or "")),
            tool_calls=tool_calls or None,
            usage=usage,
        )

    def embed(self, req: EmbeddingRequest) -> EmbeddingResponse:
        """
        Ollama embeddings endpoint is per-text. We preserve runtime contract: vectors in same order.
        """
        vectors: List[List[float]] = []
        for text in req.texts:
            try:
                eresp = self._client.embeddings(model=req.model, prompt=text)
            except Exception as e:
                raise ProviderError(f"Ollama embeddings() failed: {e}") from e

            ed = _as_dict(eresp)
            # python-ollama has historically returned either:
            #  - {"embedding":[...]}
            #  - {"embeddings":[...]} (less common)
            vec = ed.get("embedding")
            if vec is None:
                vecs = ed.get("embeddings")
                if isinstance(vecs, list) and vecs:
                    vec = vecs[0]
            if not isinstance(vec, list):
                raise ProviderError("Ollama embeddings response missing 'embedding' list")
            vectors.append([float(x) for x in vec])

        return EmbeddingResponse(vectors=vectors)
