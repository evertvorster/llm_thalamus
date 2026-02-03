from __future__ import annotations

import inspect
import os
import traceback
from datetime import datetime
from typing import Any, Dict, List

from llm_thalamus.config.access import get_config
from llm_thalamus.core.prompting.assemble_answer import AnswerPromptInputs, assemble_answer_prompt
from llm_thalamus.core.state.message_history import MessageHistoryStore


def _cfg_int(cfg: object, names: tuple[str, ...], default: int) -> int:
    for name in names:
        if hasattr(cfg, name):
            try:
                return int(getattr(cfg, name))
            except Exception:
                pass
    return default


def _recent_history_block(history: object, limit: int) -> str:
    fmt = getattr(history, "format_for_prompt", None)
    if callable(fmt):
        try:
            return fmt(limit=limit)
        except TypeError:
            return fmt(limit)
    raise RuntimeError(
        "MessageHistoryStore missing required formatter method format_for_prompt. "
        f"Available attrs: {sorted(a for a in dir(history) if not a.startswith('_'))}"
    )


def _format_memories_block(results: List[Dict[str, Any]], max_items: int) -> str:
    if not results:
        return "(no relevant memories found.)"

    lines: List[str] = []
    for i, r in enumerate(results[:max_items], start=1):
        content = str(r.get("content", "") or "").strip()
        if not content:
            continue
        sector = str(r.get("primary_sector", "") or "").strip()
        score = r.get("score", None)

        header = f"{i}."
        if sector:
            header += f" [{sector}]"
        if score is not None:
            header += f" score={score}"

        if len(content) > 800:
            content = content[:799] + "…"

        lines.append(f"{header}\n{content}")

    return "\n\n".join(lines).strip() if lines else "(no relevant memories found.)"


def _debug_adapter_introspection(om_client: object) -> None:
    print("[debug] adapters.openmemory.client loaded from:", inspect.getsourcefile(om_client))

    # Environment variables that commonly affect OpenMemory behavior
    keys = [
        "OM_DB_URL",
        "OM_TIER",
        "OM_EMBEDDINGS_PROVIDER",
        "OM_OLLAMA_URL",
        "OM_OLLAMA_EMBEDDING_MODEL",
        "OM_OLLAMA_EMBEDDINGS_MODEL",
        "OM_OLLAMA_EMBED_MODEL",
        "OPENMEMORY_DB_URL",
        "OPENMEMORY_TIER",
        "OPENMEMORY_EMBEDDINGS_PROVIDER",
        "OPENMEMORY_EMBEDDINGS_MODEL",
        "OPENMEMORY_OLLAMA_URL",
        "OLLAMA_URL",
    ]
    present = [k for k in keys if k in os.environ]
    if present:
        print("[debug] relevant env:")
        for k in present:
            print(f"  {k}={os.environ.get(k)}")


def _install_numpy_dot_tracer() -> Any:
    """
    Monkeypatch numpy.dot to print shapes + caller stack when we hit the mismatch.
    Returns the original np.dot so we can restore it.
    """
    import numpy as np  # type: ignore

    original_dot = np.dot

    def traced_dot(a, b, *args, **kwargs):
        try:
            # best-effort shape detection
            a_shape = getattr(a, "shape", None)
            b_shape = getattr(b, "shape", None)

            # Only print for the common failing case: 1D vectors with mismatched lengths
            if (
                a_shape is not None
                and b_shape is not None
                and len(a_shape) == 1
                and len(b_shape) == 1
                and a_shape[0] != b_shape[0]
            ):
                print("[dot-trace] numpy.dot called with mismatched 1D vectors:")
                print(f"[dot-trace]   a.shape={a_shape}  b.shape={b_shape}")

                # Short stack so we see which OpenMemory codepath invoked it
                import traceback as tb

                stack = tb.format_stack(limit=14)
                print("[dot-trace] caller stack (most recent last):")
                for line in stack[:-2]:
                    print(line.rstrip())

            return original_dot(a, b, *args, **kwargs)
        except Exception:
            # If our tracer itself errors, fall back to original behavior
            return original_dot(a, b, *args, **kwargs)

    np.dot = traced_dot  # type: ignore[assignment]
    return original_dot


def _restore_numpy_dot(original_dot: Any) -> None:
    import numpy as np  # type: ignore
    np.dot = original_dot  # type: ignore[assignment]


def _read_memories_block_via_client(user_message: str, k: int) -> str:
    """
    HARD RULE: Only adapters/openmemory/client.py may access OpenMemory.
    """
    from llm_thalamus.adapters.openmemory import client as om_client

    _debug_adapter_introspection(om_client)

    uid = om_client.get_default_user_id()
    print(f"[debug] default_user_id={uid}")

    # Install tracer just around the call we know explodes
    original_dot = _install_numpy_dot_tracer()
    try:
        print(f"[4/7] calling om_client.search(query=..., k={k})")
        results = om_client.search(query=user_message, k=k, user_id=uid)
    finally:
        _restore_numpy_dot(original_dot)

    print(f"[5/7] om_client.search returned {len(results) if hasattr(results, '__len__') else 'unknown'} results")

    normalized: List[Dict[str, Any]] = []
    for r in results:
        if isinstance(r, dict):
            normalized.append(r)
        else:
            normalized.append({"content": str(r)})

    return _format_memories_block(normalized, max_items=min(8, k))


def main() -> int:
    try:
        print("[1/7] load config")
        cfg = get_config()
        print("[debug] config type:", type(cfg).__name__)

        short_term_max = _cfg_int(cfg, ("short_term_max_messages", "short_term_max"), default=10)
        memory_limit = _cfg_int(cfg, ("memory_limit", "max_memories"), default=8)
        print(f"[debug] short_term_max={short_term_max} memory_limit={memory_limit}")

        print("[2/7] load MessageHistoryStore")
        history = MessageHistoryStore.from_config()
        print("[debug] MessageHistoryStore loaded from:", inspect.getsourcefile(MessageHistoryStore))

        print("[3/7] format recent history for prompt")
        recent_block = _recent_history_block(history, limit=short_term_max)
        print(f"[debug] recent_block_len={len(recent_block)}")

        user_message = "Probe: assemble answer prompt from real history + real memory store."

        print("[4/7] retrieve memories block via adapters/openmemory/client.py")
        memories_block = _read_memories_block_via_client(user_message=user_message, k=memory_limit)
        print(f"[debug] memories_block_len={len(memories_block)}")

        print("[6/7] assemble answer prompt (pure)")
        inputs = AnswerPromptInputs(
            now_iso=datetime.now().isoformat(timespec="seconds"),
            user_message=user_message,
            recent_conversation_block=recent_block,
            memories_block=memories_block,
            history_message_limit=short_term_max,
            memory_limit=memory_limit,
        )
        prompt = assemble_answer_prompt(inputs)

        print("[7/7] success")
        print("probe_prompt_assemble_answer: OK")
        print(f"  prompt_len_chars={len(prompt)}")
        print(f"  approx_tokens={len(prompt)//4}")
        print(f"  head={prompt[:400].replace(chr(10), '\\\\n')}")
        return 0

    except Exception:
        print("probe_prompt_assemble_answer: FAIL")
        traceback.print_exc()
        return 1
