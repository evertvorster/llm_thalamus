from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .factory import make_provider
from .openai_compatible import api_key_from_env
from .types import ModelInfo


@dataclass(frozen=True)
class ProviderOption:
    key: str
    display_name: str
    label: str
    kind: str
    url: str
    tooltip: str


@dataclass(frozen=True)
class ProviderModelStatus:
    provider_key: str
    provider_label: str
    kind: str
    url: str
    models: tuple[str, ...]
    error: str | None = None

    @property
    def available_models(self) -> set[str]:
        return set(self.models)


def _llm_cfg(raw_cfg: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(raw_cfg, Mapping):
        return {}
    llm_cfg = raw_cfg.get("llm")
    return llm_cfg if isinstance(llm_cfg, Mapping) else {}


def _backends_cfg(backends_cfg: Mapping[str, Any] | None) -> Mapping[str, Any]:
    backends = backends_cfg.get("backends") if isinstance(backends_cfg, Mapping) else None
    return backends if isinstance(backends, Mapping) else {}


def provider_kind_label(kind: str) -> str:
    kind = str(kind or "").strip().lower()
    if kind == "openai_compatible":
        return "OpenAI-compatible"
    if kind == "ollama":
        return "Ollama"
    text = kind.replace("_", " ").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in text.split()) or kind


def provider_label(provider_key: str, provider_cfg: Mapping[str, Any] | None = None) -> str:
    kind = str(provider_cfg.get("kind") or provider_key).strip() if isinstance(provider_cfg, Mapping) else provider_key
    kind_label = provider_kind_label(kind)
    if isinstance(provider_cfg, Mapping):
        label = provider_cfg.get("label")
        if isinstance(label, str) and label.strip():
            label_text = label.strip()
            if label_text.lower() != kind_label.lower():
                return label_text

    key_text = provider_key.replace("_", " ").replace("-", " ").strip()
    key_label = " ".join(part.capitalize() for part in key_text.split()) or provider_key
    return key_label


def provider_display_name(provider_key: str, provider_cfg: Mapping[str, Any] | None = None) -> str:
    label = provider_label(provider_key, provider_cfg)
    norm_label = label.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    norm_key = provider_key.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    if norm_label == norm_key:
        return provider_key
    return f"{label} [{provider_key}]"


def provider_options_from_config(backends_cfg: Mapping[str, Any] | None) -> list[ProviderOption]:
    options: list[ProviderOption] = []
    providers_cfg = _backends_cfg(backends_cfg)
    for key in sorted(providers_cfg.keys()):
        if not isinstance(key, str):
            continue
        provider_cfg = providers_cfg.get(key)
        if not isinstance(provider_cfg, Mapping):
            provider_cfg = {}
        options.append(
            ProviderOption(
                key=key,
                display_name=provider_display_name(key, provider_cfg),
                label=provider_label(key, provider_cfg),
                kind=str(provider_cfg.get("kind") or key).strip(),
                url=str(provider_cfg.get("url") or "").strip(),
                tooltip=f"{key} • {provider_kind_label(str(provider_cfg.get('kind') or key).strip())} • {str(provider_cfg.get('url') or '').strip() or '-'}",
            )
        )
    return options


def active_provider_key(raw_cfg: Mapping[str, Any] | None) -> str:
    return str(_llm_cfg(raw_cfg).get("provider") or "").strip()


def provider_config(backends_cfg: Mapping[str, Any] | None, provider_key: str) -> Mapping[str, Any]:
    providers_cfg = _backends_cfg(backends_cfg)
    provider_cfg = providers_cfg.get(provider_key)
    return provider_cfg if isinstance(provider_cfg, Mapping) else {}


def required_role_models(raw_cfg: Mapping[str, Any] | None) -> dict[str, str]:
    roles_cfg = _llm_cfg(raw_cfg).get("roles")
    if not isinstance(roles_cfg, Mapping):
        return {}

    required: dict[str, str] = {}
    for role_name, role_obj in roles_cfg.items():
        if not isinstance(role_name, str) or not isinstance(role_obj, Mapping):
            continue
        model = str(role_obj.get("model") or "").strip()
        if model:
            required[role_name] = model
    return required


def list_models_for_provider(backends_cfg: Mapping[str, Any] | None, provider_key: str) -> ProviderModelStatus:
    provider_key = str(provider_key or "").strip()
    provider_cfg = provider_config(backends_cfg, provider_key)
    label = provider_label(provider_key, provider_cfg)
    kind = str(provider_cfg.get("kind") or provider_key).strip()
    url = str(provider_cfg.get("url") or "").strip()

    if not provider_key:
        return ProviderModelStatus(
            provider_key="",
            provider_label="",
            kind=kind,
            url=url,
            models=(),
            error="No active backend selected.",
        )

    try:
        api_key = api_key_from_env(str(provider_cfg.get("api_key_env") or provider_cfg.get("api_token_env") or "").strip())
        provider = make_provider(
            provider_key,
            kind=kind,
            base_url=url,
            api_key=api_key,
        )
        models = provider.list_models()
    except Exception as exc:
        return ProviderModelStatus(
            provider_key=provider_key,
            provider_label=label,
            kind=kind,
            url=url,
            models=(),
            error=f"{type(exc).__name__}: {exc}",
        )

    names = sorted(
        {
            m.name.strip()
            for m in models
            if isinstance(m, ModelInfo) and isinstance(m.name, str) and m.name.strip()
        }
    )
    return ProviderModelStatus(
        provider_key=provider_key,
        provider_label=label,
        kind=kind,
        url=url,
        models=tuple(names),
        error=None,
    )


def missing_required_roles(
    raw_cfg: Mapping[str, Any] | None,
    available_models: set[str] | None,
    *,
    required_roles: tuple[str, ...] = ("planner", "reflect"),
) -> list[str]:
    roles_cfg = _llm_cfg(raw_cfg).get("roles")
    if not isinstance(roles_cfg, Mapping):
        return list(required_roles)

    missing: list[str] = []
    for role_name in required_roles:
        role_obj = roles_cfg.get(role_name)
        if not isinstance(role_obj, Mapping):
            missing.append(role_name)
            continue
        model = str(role_obj.get("model") or "").strip()
        if not model:
            missing.append(role_name)
            continue
        if available_models is not None and model not in available_models:
            missing.append(role_name)
    return missing


def active_provider_model_status(raw_cfg: Mapping[str, Any] | None, backends_cfg: Mapping[str, Any] | None) -> ProviderModelStatus:
    return list_models_for_provider(backends_cfg, active_provider_key(raw_cfg))
