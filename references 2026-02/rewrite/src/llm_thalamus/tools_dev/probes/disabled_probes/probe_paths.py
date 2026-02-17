# src/llm_thalamus/tools_dev/probes/probe_paths.py
from __future__ import annotations

from llm_thalamus.config import paths


def main() -> int:
    print("dev_mode:", paths.is_dev_mode())
    print("app_id:", paths.app_id())
    print("repo_root:", paths.repo_root())
    print("resources_root:", paths.resources_root())
    print("config_path:", paths.config_path())
    print("data_root:", paths.data_root())
    print("state_root:", paths.state_root())
    print("logs_dir:", paths.logs_dir())
    print("chat_history_dir:", paths.chat_history_dir())
    print("images_dir:", paths.get_images_dir())

    # Deterministic resolution smoke checks
    print("resolve data ./data/memory.sqlite ->",
          paths.resolve_app_path("./data/memory.sqlite", kind="data"))
    print("resolve log  ./log/thalamus.log  ->",
          paths.resolve_app_path("./log/thalamus.log", kind="log"))
    print("resolve abs  /tmp/x             ->",
          paths.resolve_app_path("/tmp/x", kind="data"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
