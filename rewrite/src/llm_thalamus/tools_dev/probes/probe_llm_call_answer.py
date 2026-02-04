from __future__ import annotations

import traceback

from llm_thalamus.config.access import get_config
from llm_thalamus.core.prompting.answer_pipeline import answer_via_ollama


def main() -> int:
    try:
        print("probe_llm_call_answer: start")
        cfg = get_config()

        user_message = "Reply with a single sentence confirming you received the prompt."
        response = answer_via_ollama(user_message, cfg=cfg, timeout=120)

        head = response.strip().replace("\n", "\\n")
        if len(head) > 300:
            head = head[:299] + "…"

        model = getattr(cfg, "llm_model", None) or "unknown"
        print("probe_llm_call_answer: OK")
        print(f"  model={model}")
        print(f"  response_len_chars={len(response)}")
        print(f"  response_head={head}")
        return 0
    except Exception:
        print("probe_llm_call_answer: FAIL")
        traceback.print_exc()
        return 1
