from __future__ import annotations

from config import _migrate_legacy_llm_providers


def test_migrate_legacy_llm_providers_merges_missing_entries() -> None:
    raw = {
        "llm": {
            "providers": {
                "huggingface": {"kind": "openai_compatible", "url": "https://example.invalid/v1"},
                "ollama_alt": {"kind": "openai_compatible", "url": "http://localhost:11434/v1"},
            }
        }
    }
    llm_backends = {
        "backends": {
            "ollama": {"kind": "ollama", "url": "http://localhost:11434"},
        }
    }

    out = _migrate_legacy_llm_providers(raw=raw, llm_backends=llm_backends)

    assert sorted(out["backends"].keys()) == ["huggingface", "ollama", "ollama_alt"]
