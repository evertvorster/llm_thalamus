from __future__ import annotations

import runtime.providers.factory as provider_factory
from runtime.providers.factory import make_provider
from runtime.providers.openai_compatible import OpenAICompatibleProvider
from runtime.providers.types import ChatParams, ChatRequest, Message, ToolCall, ToolDef


def test_make_provider_uses_openai_compatible_kind() -> None:
    provider = make_provider(
        "lmstudio",
        kind="openai_compatible",
        base_url="http://localhost:1234/v1",
    )

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.provider_name() == "lmstudio"


def test_make_provider_keeps_native_ollama_kind(monkeypatch) -> None:
    class _SentinelProvider:
        def __init__(self, *, base_url: str | None = None) -> None:
            self.base_url = base_url

    monkeypatch.setattr(provider_factory, "OllamaProvider", _SentinelProvider)
    provider = make_provider(
        "ollama",
        kind="ollama",
        base_url="http://localhost:11434",
    )

    assert isinstance(provider, _SentinelProvider)
    assert provider.base_url == "http://localhost:11434"


def test_openai_compatible_payload_uses_openai_wire_shape() -> None:
    provider = OpenAICompatibleProvider(
        provider_name="lmstudio",
        base_url="http://localhost:1234/v1",
    )
    req = ChatRequest(
        model="qwen",
        messages=[
            Message(role="system", content="system prompt"),
            Message(role="developer", content="developer prompt"),
            Message(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id="call_1", name="echo", arguments_json='{"value":"x"}')],
            ),
            Message(role="tool", content='{"ok":true}', tool_call_id="call_1", name="echo"),
            Message(role="user", content="hello"),
        ],
        tools=[
            ToolDef(
                name="echo",
                description="Echoes text",
                parameters={"type": "object", "properties": {"value": {"type": "string"}}},
            )
        ],
        response_format="json",
        params=ChatParams(options={"temperature": 0.2}),
        stream=True,
    )

    payload = provider.build_chat_payload(req)

    assert payload is not None
    assert payload["model"] == "qwen"
    assert payload["stream"] is True
    assert payload["messages"][1]["role"] == "system"
    assert payload["messages"][2]["tool_calls"][0]["function"]["arguments"] == '{"value":"x"}'
    assert payload["messages"][3]["tool_call_id"] == "call_1"
    assert payload["tools"][0]["function"]["name"] == "echo"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["temperature"] == 0.2
