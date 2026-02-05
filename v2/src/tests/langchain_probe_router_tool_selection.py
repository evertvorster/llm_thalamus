# src/tests/langchain_probe_router_tool_selection.py
from __future__ import annotations

from typing import Literal, Optional, Dict, Any
import requests

from langchain_core.output_parsers import PydanticOutputParser
try:
    from langchain_core.pydantic_v1 import BaseModel, Field  # type: ignore
except Exception:
    from pydantic import BaseModel, Field  # type: ignore


# -------- config --------
OLLAMA_URL = "http://localhost:11434"
ROUTER_MODEL = "qwen2.5:7b"   # fast + deterministic
TIMEOUT_S = 300


# -------- schema --------

class RouteAction(BaseModel):
    action: Literal["ANSWER", "PLAN", "MEMORY", "TOOL"] = Field(
        description="High-level routing decision"
    )
    tool: Optional[str] = Field(
        default=None,
        description="Tool name if action == TOOL"
    )
    args: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Tool arguments if action == TOOL"
    )


parser = PydanticOutputParser(pydantic_object=RouteAction)


# -------- transport --------

def call_ollama(prompt: str, model: str) -> str:
    url = OLLAMA_URL.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    r = requests.post(url, json=payload, timeout=TIMEOUT_S)
    r.raise_for_status()
    return (r.json().get("response") or "").strip()


# -------- node logic (router) --------

def router_llm(user_text: str) -> RouteAction:
    header = (
        "You are a routing controller for a local assistant.\n"
        "Decide what should happen next.\n\n"
        "Rules:\n"
        "- ANSWER: simple conversational reply\n"
        "- PLAN: multi-step reasoning or design\n"
        "- MEMORY: needs recalling past context or stored knowledge\n"
        "- TOOL: requires calling a specific tool\n\n"
        "If TOOL is chosen, provide:\n"
        "- tool: short tool identifier\n"
        "- args: JSON object with arguments\n\n"
        "IMPORTANT:\n"
        "- Output MUST be valid JSON\n"
        "- Output MUST conform exactly to the schema\n"
        "- Do NOT include explanations\n"
    )

    prompt = (
        header
        + "\n"
        + parser.get_format_instructions()
        + "\n\n"
        + f"User message:\n{user_text}\n"
        + "\nOutput:"
    )

    raw = call_ollama(prompt, ROUTER_MODEL)
    print("\n--- RAW MODEL OUTPUT ---")
    print(raw)

    parsed = parser.parse(raw)
    return parsed


# -------- test harness --------

def main() -> int:
    tests = [
        "Hello, how are you?",
        "Design a config layout for multiple LLM roles in Thalamus",
        "Do you remember what we discussed earlier about Arch Linux?",
        "Extract text from this image: screenshot.png",
    ]

    for t in tests:
        print("\n==============================")
        print("USER:", t)
        try:
            decision = router_llm(t)
            print("PARSED:", decision)
            print("ACTION:", decision.action)
            if decision.action == "TOOL":
                print("TOOL :", decision.tool)
                print("ARGS :", decision.args)
        except Exception as e:
            print("❌ PARSE FAILED:", type(e).__name__, e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
