from __future__ import annotations

from llm_thalamus.config.access import get_config
from llm_thalamus.config.paths import resources_root
from llm_thalamus.core.prompting.prompts import load_prompt_template


def main() -> int:
    cfg = get_config()

    calls = getattr(cfg, "calls", None)
    if not calls:
        print("probe_prompt_templates: SKIP (no cfg.calls on typed config)")
        return 0

    preferred = ["answer", "reflection", "memory_query", "plan"]
    call_name = next((n for n in preferred if n in calls), next(iter(calls.keys()), None))
    if not call_name:
        print("probe_prompt_templates: SKIP (calls empty)")
        return 0

    call_cfg = calls[call_name]

    text = load_prompt_template(call_name, call_cfg, base_dir=resources_root())
    if text is None:
        print(f"probe_prompt_templates: OK (no template configured for {call_name})")
        return 0

    print("probe_prompt_templates: OK")
    print(f"  call={call_name}")
    print(f"  chars={len(text)}")
    print(f"  head={text[:60].replace(chr(10), ' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
