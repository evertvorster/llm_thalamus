from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional, Tuple

from runtime.providers.base import LLMProvider
from runtime.providers.factory import make_provider
from runtime.providers.types import ChatParams, ChatRequest, Message


Chunk = Tuple[str, str]  # (kind, text); kind is "response" (bootstrap keeps it simple)


def _get_cfg_value(cfg, name: str, default=None):
    return getattr(cfg, name, default)


@dataclass(frozen=True)
class RoleLLM:
    """Small compatibility wrapper around LLMProvider for prompt-based nodes."""

    provider: LLMProvider
    model: str
    params: Mapping[str, Any]
    response_format: Any

    def generate_stream(self, prompt: str) -> Iterator[Chunk]:
        # Convert prompt-based call into a chat call with a single user message.
        req = ChatRequest(
            model=self.model,
            messages=[Message(role="user", content=prompt)],
            response_format=self.response_format,
            params=_chat_params_from_mapping(self.params),
            stream=True,
        )

        for ev in self.provider.chat_stream(req):
            if ev.type == "delta_text" and ev.text:
                yield ("response", ev.text)
            elif ev.type == "error":
                raise RuntimeError(ev.error or "LLM provider error")
            elif ev.type == "done":
                break


def _chat_params_from_mapping(d: Mapping[str, Any]) -> Optional[ChatParams]:
    if not d:
        return None

    # Keep it explicit: only map known keys.
    extra: Dict[str, Any] = {}
    known = {"temperature", "top_p", "top_k", "seed", "num_ctx", "stop"}
    for k, v in d.items():
        if k not in known:
            extra[k] = v

    return ChatParams(
        temperature=_maybe_float(d.get("temperature")),
        top_p=_maybe_float(d.get("top_p")),
        top_k=_maybe_int(d.get("top_k")),
        seed=_maybe_int(d.get("seed")),
        num_ctx=_maybe_int(d.get("num_ctx")),
        stop=_maybe_str_list(d.get("stop")),
        extra=(extra or None),
    )


def _maybe_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        return None


def _maybe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _maybe_str_list(v: Any) -> Optional[list[str]]:
    if v is None:
        return None
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return list(v)
    return None


@dataclass(frozen=True)
class Deps:
    prompt_root: Path
    models: Dict[str, str]  # e.g. {"router": "...", "final": "..."}

    provider: LLMProvider
    llm_router: RoleLLM
    llm_final: RoleLLM

    def load_prompt(self, name: str) -> str:
        p = self.prompt_root / f"{name}.txt"
        if not p.exists():
            raise FileNotFoundError(f"missing prompt file: {p}")
        return p.read_text(encoding="utf-8")


def build_runtime_deps(cfg) -> Deps:
    resources_root = Path(_get_cfg_value(cfg, "resources_root"))
    prompt_root = resources_root / "prompts"

    llm_provider = str(_get_cfg_value(cfg, "llm_provider") or "").strip()
    if not llm_provider:
        raise RuntimeError("config missing llm.provider")

    llm_url = str(_get_cfg_value(cfg, "llm_url") or "").strip()
    if not llm_url:
        raise RuntimeError("config missing llm.providers.<active>.url")

    nodes = _get_cfg_value(cfg, "llm_langgraph_nodes", None)
    if nodes is None:
        raise RuntimeError("config missing llm.langgraph_nodes")

    role_params = _get_cfg_value(cfg, "llm_role_params", None)
    if role_params is None:
        raise RuntimeError("config missing llm.role_params")

    role_fmt = _get_cfg_value(cfg, "llm_role_response_format", None)
    if role_fmt is None:
        raise RuntimeError("config missing llm.role_response_format")

    router_model = str(nodes.get("router") or "").strip()
    final_model = str(nodes.get("final") or "").strip()

    if not router_model:
        raise RuntimeError("config missing llm.langgraph_nodes.router")
    if not final_model:
        raise RuntimeError("config missing llm.langgraph_nodes.final")

    models = {"router": router_model, "final": final_model}

    provider = make_provider(llm_provider, base_url=llm_url)

    # No fallbacks: roles must exist in config.
    router_params = role_params.get("router")
    if not isinstance(router_params, dict):
        raise RuntimeError("config missing llm.role_params.router")

    final_params = role_params.get("final")
    if not isinstance(final_params, dict):
        raise RuntimeError("config missing llm.role_params.final")

    router_fmt = role_fmt.get("router")
    final_fmt = role_fmt.get("final")

    return Deps(
        prompt_root=prompt_root,
        models=models,
        provider=provider,
        llm_router=RoleLLM(
            provider=provider,
            model=router_model,
            params=router_params,
            response_format=router_fmt,
        ),
        llm_final=RoleLLM(
            provider=provider,
            model=final_model,
            params=final_params,
            response_format=final_fmt,
        ),
    )
