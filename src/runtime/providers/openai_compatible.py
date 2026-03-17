from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Sequence
from urllib import error as urllib_error
from urllib import request as urllib_request

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


def _join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _read_json_response(resp) -> Dict[str, Any]:
    raw = resp.read()
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise ProviderError(f"Invalid JSON response: {e}") from e


def _message_role_for_wire(role: str) -> str:
    if role == "developer":
        return "system"
    return role


def _message_to_wire(msg: Message) -> Dict[str, Any]:
    wire: Dict[str, Any] = {
        "role": _message_role_for_wire(msg.role),
        "content": msg.content,
    }
    if msg.name:
        wire["name"] = msg.name
    if msg.role == "assistant" and msg.tool_calls:
        wire["tool_calls"] = [_tool_call_to_wire(tc) for tc in msg.tool_calls]
    if msg.role == "tool" and msg.tool_call_id:
        wire["tool_call_id"] = msg.tool_call_id
    return wire


def _tool_def_to_wire(td: ToolDef) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": td.name,
            "description": td.description,
            "parameters": td.parameters or {"type": "object", "properties": {}},
        },
    }


def _tool_call_to_wire(tc: ToolCall) -> Dict[str, Any]:
    return {
        "id": tc.id,
        "type": "function",
        "function": {
            "name": tc.name,
            "arguments": tc.arguments_json or "{}",
        },
    }


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "")
            if item_type in {"text", "output_text"}:
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _extract_tool_calls(raw_tool_calls: Any) -> List[ToolCall]:
    out: List[ToolCall] = []
    if not isinstance(raw_tool_calls, list):
        return out
    for i, item in enumerate(raw_tool_calls):
        if not isinstance(item, dict):
            continue
        fn = item.get("function")
        if not isinstance(fn, dict):
            continue
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        arguments = fn.get("arguments")
        if isinstance(arguments, str):
            arguments_json = arguments
        else:
            try:
                arguments_json = json.dumps(arguments if arguments is not None else {}, ensure_ascii=False)
            except Exception:
                arguments_json = "{}"
        out.append(
            ToolCall(
                id=str(item.get("id") or f"toolcall_{i}"),
                name=name,
                arguments_json=arguments_json,
            )
        )
    return out


def _extract_usage(raw: Dict[str, Any]) -> Usage | None:
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        return None
    out = Usage(
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
    )
    if out.input_tokens is None and out.output_tokens is None and out.total_tokens is None:
        return None
    return out


def _thinking_delta_from_delta(delta: Dict[str, Any]) -> str:
    for key in ("reasoning", "reasoning_content", "thinking", "reasoning_text"):
        value = delta.get(key)
        if isinstance(value, str):
            return value
    content = delta.get("content")
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "") in {"reasoning", "thinking"}:
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "".join(parts)
    return ""


def _payload_from_request(req: ChatRequest) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": req.model,
        "messages": [_message_to_wire(msg) for msg in req.messages],
        "stream": bool(req.stream),
    }
    if req.tools:
        payload["tools"] = [_tool_def_to_wire(td) for td in req.tools]
    if req.response_format == "json":
        payload["response_format"] = {"type": "json_object"}
    elif isinstance(req.response_format, dict):
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "schema": req.response_format,
            },
        }

    options = getattr(req.params, "options", None)
    if isinstance(options, dict):
        for key, value in options.items():
            if key in payload:
                continue
            payload[key] = value

    return payload


@dataclass
class _BufferedToolCall:
    id: str = ""
    name: str = ""
    arguments_parts: List[str] | None = None

    def __post_init__(self) -> None:
        if self.arguments_parts is None:
            self.arguments_parts = []

    def to_tool_call(self, index: int) -> ToolCall | None:
        if not self.name:
            return None
        return ToolCall(
            id=self.id or f"toolcall_{index}",
            name=self.name,
            arguments_json="".join(self.arguments_parts or []) or "{}",
        )


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key: str | None = None,
    ) -> None:
        if not base_url:
            raise ProviderError("OpenAI-compatible provider requires a base URL")
        self._provider_name = provider_name.strip() or "openai_compatible"
        self._base_url = base_url.strip().rstrip("/")
        self._api_key = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None

    def provider_name(self) -> str:
        return self._provider_name

    def diagnostics(self) -> Dict[str, str]:
        return {
            "provider": self._provider_name,
            "transport": "openai_compatible_http",
            "base_url": self._base_url,
            "auth": "bearer" if self._api_key else "none",
        }

    def capabilities(self) -> Sequence[str]:
        return ["chat", "embeddings", "tools", "json_mode", "streaming"]

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        payload: Dict[str, Any] | None = None,
        accept: str = "application/json",
    ):
        headers = self._headers()
        headers["Accept"] = accept
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib_request.Request(
            _join_url(self._base_url, path),
            data=data,
            headers=headers,
            method=method,
        )
        try:
            return urllib_request.urlopen(req, timeout=300)
        except urllib_error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            detail = body.strip() or str(e)
            raise ProviderError(f"{self._provider_name} {method} {path} failed: {detail}") from e
        except urllib_error.URLError as e:
            raise ProviderError(f"{self._provider_name} {method} {path} failed: {e.reason}") from e
        except Exception as e:
            raise ProviderError(f"{self._provider_name} {method} {path} failed: {e}") from e

    def build_chat_payload(self, req: ChatRequest) -> Dict[str, Any] | None:
        return _payload_from_request(req)

    def build_chat_curl(self, payload: Dict[str, Any]) -> str | None:
        url = _join_url(self._base_url, "/chat/completions")
        auth = " -H 'Authorization: Bearer $API_KEY'" if self._api_key else ""
        return f"curl -sS {url} -H 'Content-Type: application/json'{auth} -d @payload.json"

    def ping(self) -> None:
        with self._request_json(method="GET", path="/models") as resp:
            _ = _read_json_response(resp)

    def list_models(self) -> List[ModelInfo]:
        with self._request_json(method="GET", path="/models") as resp:
            raw = _read_json_response(resp)
        data = raw.get("data")
        out: List[ModelInfo] = []
        if not isinstance(data, list):
            return out
        for item in data:
            if not isinstance(item, dict):
                continue
            name = str(item.get("id") or item.get("name") or "").strip()
            if not name:
                continue
            out.append(
                ModelInfo(
                    name=name,
                    family=str(item.get("owned_by") or "") or None,
                    capabilities=["chat", "embeddings", "tools", "json_mode", "streaming"],
                )
            )
        return out

    def chat_stream(self, req: ChatRequest) -> Iterator[StreamEvent]:
        payload = _payload_from_request(req)
        payload["stream"] = True
        buffered_tool_calls: Dict[int, _BufferedToolCall] = {}
        usage_sent = False
        sent_done = False

        try:
            with self._request_json(
                method="POST",
                path="/chat/completions",
                payload=payload,
                accept="text/event-stream",
            ) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except Exception:
                        continue

                    usage = _extract_usage(chunk)
                    if usage is not None:
                        yield StreamEvent(type="usage", usage=usage)
                        usage_sent = True

                    choices = chunk.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = choices[0]
                    if not isinstance(choice, dict):
                        continue
                    delta = choice.get("delta")
                    if not isinstance(delta, dict):
                        delta = {}

                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        yield StreamEvent(type="delta_text", text=content)
                    elif isinstance(content, list):
                        text = _extract_message_text(content)
                        if text:
                            yield StreamEvent(type="delta_text", text=text)

                    thinking = _thinking_delta_from_delta(delta)
                    if thinking:
                        yield StreamEvent(type="delta_thinking", text=thinking)

                    raw_tool_calls = delta.get("tool_calls")
                    if isinstance(raw_tool_calls, list):
                        for pos, item in enumerate(raw_tool_calls):
                            if not isinstance(item, dict):
                                continue
                            idx = item.get("index")
                            if not isinstance(idx, int):
                                idx = pos
                            buf = buffered_tool_calls.setdefault(idx, _BufferedToolCall())
                            call_id = item.get("id")
                            if isinstance(call_id, str) and call_id:
                                buf.id = call_id
                            fn = item.get("function")
                            if isinstance(fn, dict):
                                name = fn.get("name")
                                if isinstance(name, str) and name:
                                    buf.name = name
                                arguments = fn.get("arguments")
                                if isinstance(arguments, str) and arguments:
                                    buf.arguments_parts.append(arguments)

                for idx in sorted(buffered_tool_calls):
                    tc = buffered_tool_calls[idx].to_tool_call(idx)
                    if tc is not None:
                        yield StreamEvent(type="tool_call", tool_call=tc)

                if not usage_sent:
                    pass

                yield StreamEvent(type="done")
                sent_done = True
        except GeneratorExit:
            sent_done = True
            return
        except Exception as e:
            yield StreamEvent(type="error", error=str(e))
            sent_done = True
        finally:
            if not sent_done:
                yield StreamEvent(type="done")

    def chat(self, req: ChatRequest) -> ChatResponse:
        payload = _payload_from_request(req)
        payload["stream"] = False
        with self._request_json(method="POST", path="/chat/completions", payload=payload) as resp:
            raw = _read_json_response(resp)

        choices = raw.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError(f"{self._provider_name} chat returned no choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise ProviderError(f"{self._provider_name} chat returned invalid choice payload")
        message = first.get("message")
        if not isinstance(message, dict):
            raise ProviderError(f"{self._provider_name} chat returned no message")

        return ChatResponse(
            message=Message(
                role="assistant",
                content=_extract_message_text(message.get("content")),
            ),
            tool_calls=_extract_tool_calls(message.get("tool_calls")) or None,
            usage=_extract_usage(raw),
        )

    def embed(self, req: EmbeddingRequest) -> EmbeddingResponse:
        payload = {
            "model": req.model,
            "input": list(req.texts),
        }
        with self._request_json(method="POST", path="/embeddings", payload=payload) as resp:
            raw = _read_json_response(resp)
        data = raw.get("data")
        if not isinstance(data, list):
            raise ProviderError(f"{self._provider_name} embeddings returned no data")
        vectors: List[List[float]] = []
        for item in data:
            if not isinstance(item, dict):
                raise ProviderError(f"{self._provider_name} embeddings returned invalid item")
            embedding = item.get("embedding")
            if not isinstance(embedding, list):
                raise ProviderError(f"{self._provider_name} embeddings item missing vector")
            vectors.append([float(x) for x in embedding])
        return EmbeddingResponse(vectors=vectors)


def api_key_from_env(env_name: str | None) -> str | None:
    if not env_name:
        return None
    value = os.environ.get(env_name)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None
