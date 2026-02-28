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
    print("llm roles:")
    if cfg.llm_roles:
        for name in sorted(cfg.llm_roles):
            model = cfg.llm_roles[name].get("model")
            fmt = cfg.llm_roles[name].get("response_format")
            fmt_s = fmt if fmt is not None else "text"
            print(f"  {name:12} {model} ({fmt_s})")
    else:
        print("  (none)")
    print("")
    print(f"log_file:        {cfg.log_file}")
    print(f"message_file:    {cfg.message_file}")
    print(f"graphics_dir:    {cfg.graphics_dir}")
    print("")

    # --- Launch UI ---
    from PySide6.QtWidgets import QApplication

    from controller.worker import ControllerWorker
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)

    controller = ControllerWorker(cfg)
    window = MainWindow(cfg, controller)

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
