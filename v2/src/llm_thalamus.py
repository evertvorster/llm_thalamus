#!/usr/bin/env python3
from __future__ import annotations

import sys

from config import bootstrap_config


def main(argv: list[str]) -> int:
    cfg = bootstrap_config(argv)

    # Print config summary
    print("== llm-thalamus config ==")
    print(f"mode:            {'dev' if cfg.dev_mode else 'installed'}")
    print(f"project_root:    {cfg.project_root}")
    print(f"resources_root:  {cfg.resources_root}")
    print(f"config_template: {cfg.config_template}")
    print(f"config_file:     {cfg.config_file}")
    print(f"runtime_root:    {cfg.runtime_root}")
    print(f"data_root:       {cfg.data_root}")
    print(f"state_root:      {cfg.state_root}")
    print("")
    print("llm:")
    print(f"  provider:      {cfg.llm_provider}")
    print(f"  kind:          {cfg.llm_kind}")
    print(f"  url:           {cfg.llm_url}")
    print("")
    print("langgraph_nodes:")
    if cfg.llm_langgraph_nodes:
        for name in sorted(cfg.llm_langgraph_nodes):
            print(f"  {name:12} {cfg.llm_langgraph_nodes[name]}")
    else:
        print("  (none)")
    print("")
    print("openmemory:")
    print(f"  mode:          {cfg.openmemory_mode}")
    print(f"  tier:          {cfg.openmemory_tier}")
    print(f"  endpoint.kind: {cfg.openmemory_endpoint_kind}")
    print(f"  endpoint.url:  {cfg.openmemory_endpoint_url}")
    print(f"  db_path:       {cfg.openmemory_db_path}")
    print("")
    print("openmemory.embeddings:")
    print(f"  provider:      {cfg.embeddings_provider}")
    print(f"  model:         {cfg.embeddings_model}")
    print(f"  ollama_url:    {cfg.embeddings_ollama_url}")
    print("")
    print(f"log_file:        {cfg.log_file}")
    print(f"message_file:    {cfg.message_file}")
    print(f"graphics_dir:    {cfg.graphics_dir}")
    print("")

    # --- OpenMemory bootstrap ---
    print("\n== openmemory bootstrap ==")
    from thalamus_openmemory.bootstrap.factory import init_openmemory

    result = init_openmemory(cfg)
    if not result.ok or result.client is None:
        print("FAILURE")
        if result.health and result.health.details:
            print(result.health.details)
        elif result.error:
            print(result.error)
        return 1

    print("SUCCESS")
    if result.health and result.health.details:
        print(result.health.details)

    # --- Launch UI ---
    from PySide6.QtWidgets import QApplication

    from controller.worker import ControllerWorker
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)

    controller = ControllerWorker(cfg, openmemory_client=result.client)
    window = MainWindow(cfg, controller)

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
