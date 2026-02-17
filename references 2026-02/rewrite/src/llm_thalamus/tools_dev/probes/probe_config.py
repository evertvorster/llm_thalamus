from __future__ import annotations

from llm_thalamus.config import loader, paths
from llm_thalamus.config.access import get_config


def main() -> int:
    print("dev_mode:", paths.is_dev_mode())
    print("config_path:", paths.config_path())

    raw = loader.load_raw_config()
    print("raw keys:", sorted(list(raw.keys())))

    cfg = get_config()
    print("llm_model:", cfg.llm_model)
    print("ollama_url:", cfg.ollama_url)
    print("openmemory_db_path:", cfg.openmemory_db_path())
    print("openmemory_db_url:", cfg.openmemory_db_url())
    print("log_file:", cfg.log_file)

    # Calls present?
    print("calls:", sorted(cfg.calls.keys()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
