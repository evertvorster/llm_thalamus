#!/usr/bin/env python3
from __future__ import annotations

import sys
from dataclasses import replace

from config import bootstrap_config
from controller.mcp.config import discover_and_reconcile_mcp, save_mcp_config
from runtime.providers.configured import active_provider_model_status, missing_required_roles


def _startup_llm_config_is_valid(cfg) -> tuple[bool, str]:
    status = active_provider_model_status(getattr(cfg, "raw", {}) or {})
    if status.error:
        return False, status.error

    missing_roles = missing_required_roles(getattr(cfg, "raw", {}) or {}, status.available_models)
    if missing_roles:
        return (
            False,
            "The selected backend does not provide the configured required role models: "
            + ", ".join(missing_roles),
        )
    return True, ""


def main(argv: list[str]) -> int:
    cfg = bootstrap_config(argv)
    runtime_mcp = discover_and_reconcile_mcp(dict(cfg.mcp_servers))
    save_mcp_config(cfg.mcp_servers_file, runtime_mcp)
    cfg = replace(cfg, mcp_servers=runtime_mcp)

    # --- Launch UI ---
    from PySide6.QtWidgets import QApplication

    from controller.worker import ControllerWorker
    from ui.main_window import MainWindow
    from ui.config_dialog import ConfigDialog

    app = QApplication(sys.argv)

    while True:
        is_valid, error_text = _startup_llm_config_is_valid(cfg)
        if is_valid:
            break

        dlg = ConfigDialog(
            dict(cfg.raw),
            dict(cfg.mcp_servers),
            mcp_runtime_config=dict(cfg.mcp_servers),
        )
        if error_text:
            dlg.set_banner_message(
                "The active backend/model configuration is invalid.\n\n"
                f"{error_text}\n\n"
                "Select valid models for the selected backend before continuing."
            )
        if dlg.exec() != dlg.Accepted:
            return 1
        cfg = bootstrap_config(argv)
        runtime_mcp = discover_and_reconcile_mcp(dict(cfg.mcp_servers))
        save_mcp_config(cfg.mcp_servers_file, runtime_mcp)
        cfg = replace(cfg, mcp_servers=runtime_mcp)

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

    controller = ControllerWorker(cfg)
    window = MainWindow(cfg, controller)

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
