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


def _validate_required_models_or_die(
    *,
    provider: LLMProvider,
    provider_name: str,
    base_url: str,
    required: Mapping[str, str],
) -> None:
    """
    Startup validation: verify required models exist for the chosen provider.
    For now we fail fast (terminate program) by raising RuntimeError.
    """
    try:
        models = provider.list_models()
    except Exception as e:
        raise RuntimeError(
            "LLM startup validation failed:\n"
            f"- provider: {provider_name}\n"
            f"- base_url: {base_url}\n"
            f"- error: {type(e).__name__}: {e}\n\n"
            "Fix:\n"
            "- Ensure the provider is running and reachable.\n"
            "- For Ollama, verify `ollama serve` is running and `ollama list` works.\n"
        ) from e

    installed = {m.name for m in (models or []) if getattr(m, "name", None)}

    missing = []
    for role, model in required.items():
        if model not in installed:
            missing.append(f"- {role}: {model}")

    if missing:
        missing_txt = "\n".join(missing)
        raise RuntimeError(
            "LLM startup validation failed: required models are not installed.\n"
            f"- provider: {provider_name}\n"
            f"- base_url: {base_url}\n"
            f"- installed_models: {len(installed)}\n\n"
            "Missing:\n"
            f"{missing_txt}\n\n"
            "Fix:\n"
            "- Pull/install the missing models for this provider.\n"
            "- For Ollama: `ollama pull <model>` then re-run.\n"
        )



@dataclass(frozen=True)
class RoleSpec:
    model: str
    params: Mapping[str, Any]
    response_format: Any


def _normalize_response_format(v: Any) -> Any:
    # Config may use "text" to mean "no special response format".
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip().lower()
        if not s or s == "text":
            return None
        return s
    return v


@dataclass(frozen=True)
class Deps:
    prompt_root: Path

    provider: LLMProvider
    roles: Dict[str, RoleSpec]
    llms_by_role: Dict[str, RoleLLM]

    tool_step_limit: int

    def get_role(self, role: str) -> RoleSpec:
        if role not in self.roles:
            raise KeyError(f"Unknown role: {role}")
        return self.roles[role]

    def get_llm(self, role: str) -> RoleLLM:
        if role not in self.llms_by_role:
            raise KeyError(f"Unknown role: {role}")
        return self.llms_by_role[role]

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

    roles_cfg = _get_cfg_value(cfg, "llm_roles", None)
    if roles_cfg is None:
        raise RuntimeError("config missing llm.roles")

    if not isinstance(roles_cfg, dict):
        raise RuntimeError("config llm.roles must be an object")

    provider = make_provider(llm_provider, base_url=llm_url)

    # ---- Startup validation (fail-fast) ----
    required: Dict[str, str] = {}
    for role_name, role_obj in roles_cfg.items():
        if not isinstance(role_name, str):
            continue
        if not isinstance(role_obj, dict):
            continue
        model = str(role_obj.get("model") or "").strip()
        if not model:
            raise RuntimeError(f"config missing llm.roles.{role_name}.model")
        required[role_name] = model

    _validate_required_models_or_die(
        provider=provider,
        provider_name=llm_provider,
        base_url=llm_url,
        required=required,
    )

    roles: Dict[str, RoleSpec] = {}
    llms_by_role: Dict[str, RoleLLM] = {}

    for role_name, role_obj in roles_cfg.items():
        if not isinstance(role_name, str):
            continue
        if not isinstance(role_obj, dict):
            raise RuntimeError(f"config llm.roles.{role_name} must be an object")

        model = str(role_obj.get("model") or "").strip()
        if not model:
            raise RuntimeError(f"config missing llm.roles.{role_name}.model")

        params = role_obj.get("params", {})
        if not isinstance(params, dict):
            raise RuntimeError(f"config llm.roles.{role_name}.params must be an object")

        response_format = _normalize_response_format(role_obj.get("response_format", None))

        roles[role_name] = RoleSpec(model=model, params=params, response_format=response_format)
        llms_by_role[role_name] = RoleLLM(
            provider=provider,
            model=model,
            params=params,
            response_format=response_format,
        )

    tool_step_limit = int(_get_cfg_value(cfg, "orchestrator_tool_step_limit", 16))

    return Deps(
        prompt_root=prompt_root,
        provider=provider,
        roles=roles,
        llms_by_role=llms_by_role,
        tool_step_limit=tool_step_limit,
    )
