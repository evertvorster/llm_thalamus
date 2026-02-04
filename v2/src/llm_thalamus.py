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
    print(f"  model:         {cfg.llm_model}")
    print(f"  kind:          {cfg.llm_kind}")
    print(f"  url:           {cfg.llm_url}")
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
    print("")
    print("prompt_files:")
    for name, p in sorted(cfg.prompt_files.items()):
        print(f"  {name:14} {p}")

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

#    # --- TEMP: interactive OpenMemory test ---
#    # NOTE: Keep this block during bring-up. Comment it out when moving on to the controller/UI work.
#    user_id = None
#    try:
#        user_id = str((cfg.raw.get("thalamus") or {}).get("default_user_id") or "").strip() or None
#    except Exception:
#        user_id = None
#
#    from tests.openmemory_interactive import run_openmemory_interactive_test
#
#    return run_openmemory_interactive_test(result.client, user_id=user_id, k=5)
#
#    # --- TEMP: Ollama interactive test (no history) ---
#    # NOTE: Keep this block during bring-up. Comment it out when moving on.
#
#    if cfg.llm_kind != "ollama":
#        print(f"LLM interactive test only supports ollama (llm.kind={cfg.llm_kind})")
#        return 1
#
#    from tests.ollama_chat_interactive import run_ollama_interactive_chat
#
#    return run_ollama_interactive_chat(
#        llm_url=cfg.llm_url,
#        model=cfg.llm_model,
#        timeout_s=120.0,
#    )

    # --- TEMP: chat history smoke test ---
    print("\n== chat history smoketest ==")
    from tests.chat_history_smoketest import run_chat_history_smoketest

    run_chat_history_smoketest(
        history_file=cfg.message_file,
        max_turns=cfg.message_history_max,
    )



if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
