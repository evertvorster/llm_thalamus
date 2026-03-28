from __future__ import annotations

from runtime.providers.configured import (
    active_provider_key,
    list_models_for_provider,
    missing_required_roles,
    provider_options_from_config,
)


def test_provider_options_use_explicit_labels_when_present() -> None:
    raw = {
        "llm": {
            "provider": "ollama",
            "providers": {
                "lmstudio": {"kind": "openai_compatible", "label": "LM Studio", "url": "http://localhost:1234/v1"},
                "ollama": {"kind": "openai_compatible", "label": "Ollama", "url": "http://localhost:11434/v1"},
            },
        }
    }

    options = provider_options_from_config(raw)

    assert [option.key for option in options] == ["lmstudio", "ollama"]
    assert [option.label for option in options] == ["LM Studio", "Ollama"]
    assert active_provider_key(raw) == "ollama"


def test_list_models_for_provider_reports_unsupported_backend() -> None:
    raw = {
        "llm": {
            "provider": "huggingface",
            "providers": {
                "huggingface": {"kind": "huggingface_inference", "label": "Hugging Face", "url": "https://example.invalid"}
            },
        }
    }

    status = list_models_for_provider(raw, "huggingface")

    assert status.provider_label == "Hugging Face"
    assert status.models == ()
    assert status.error is not None
    assert "Unknown provider kind" in status.error


def test_missing_required_roles_checks_selected_backend_models() -> None:
    raw = {
        "llm": {
            "roles": {
                "planner": {"model": "model-a"},
                "reflect": {"model": "model-b"},
            }
        }
    }

    assert missing_required_roles(raw, {"model-a", "model-b"}) == []
    assert missing_required_roles(raw, {"model-a"}) == ["reflect"]
