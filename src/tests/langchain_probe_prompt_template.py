# src/tests/langchain_probe_prompt_template.py
from langchain_core.prompts import PromptTemplate

def main() -> int:
    tpl = PromptTemplate.from_template(
        "Header:\n{header}\n\nWorld:\n{world}\n\nUser:\n{user}\n"
    )
    out = tpl.format(
        header="You are a router. Output DIRECT or PLAN.",
        world="(none)",
        user="Please plan this for me",
    )
    print(out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
