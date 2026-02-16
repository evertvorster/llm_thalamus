from __future__ import annotations

from typing import Callable, Optional

from runtime.build import run_graph
from runtime.deps import Deps, LLMClient
from runtime.events import Event
from runtime.state import State


class DummyLLM(LLMClient):
    """
    Replace this with your real local LLM adapter.
    This dummy is just to prove the graph runs.
    """
    def complete_text(self, prompt: str, *, emit_thought: Optional[Callable[[str], None]] = None) -> str:
        if emit_thought:
            emit_thought("dummy thought: generating answer")
        return "OK (dummy). Replace DummyLLM with your real adapter."

    def complete_json(self, prompt: str, *, emit_thought: Optional[Callable[[str], None]] = None) -> str:
        if emit_thought:
            emit_thought("dummy thought: routing to answer")
        return '{"route":"answer","confidence":"high"}'


def emit(e: Event) -> None:
    # Minimal console printer. Your UI can consume Event objects directly.
    if e.channel == "ops":
        print(f"[{e.channel}:{e.phase}] {e.node_id} {e.msg} {e.data}")
    else:
        # thought
        print(f"[{e.channel}] {e.node_id}: {e.data.get('text','')}")


if __name__ == "__main__":
    deps = Deps(llm=DummyLLM(), prompt_root="runtime/prompts")
    s = State(user_text="Hello from the new runtime graph.")
    out = run_graph(s, deps, emit)
    print("\nassistant_text:\n", out.assistant_text)
