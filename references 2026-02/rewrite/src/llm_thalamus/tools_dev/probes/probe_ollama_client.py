from __future__ import annotations

from llm_thalamus.adapters.llm.ollama import OllamaClient
from llm_thalamus.config.access import get_config


def main() -> int:
    cfg = get_config()

    # In the current schema, these are top-level on ThalamusConfig
    base_url = getattr(cfg, "ollama_url", None)
    model = getattr(cfg, "llm_model", None)

    if not base_url or not model:
        print("probe_ollama_client: SKIP (missing ollama_url/llm_model in typed config)")
        return 0

    client = OllamaClient(base_url=str(base_url), model=str(model))
    print("probe_ollama_client: OK")
    print(f"  base_url={client.base_url}")
    print(f"  model={client.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
