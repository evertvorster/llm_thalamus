# src/tests/langchain_probe_output_parser.py
from __future__ import annotations

from typing import Literal

from langchain_core.output_parsers import PydanticOutputParser

# LangChain ships a pydantic v1 compatibility shim in many builds,
# but not all. This makes the probe robust.
try:
    from langchain_core.pydantic_v1 import BaseModel, Field  # type: ignore
except Exception:
    from pydantic import BaseModel, Field  # type: ignore


class RouteDecision(BaseModel):
    route: Literal["DIRECT", "PLAN"] = Field(
        description="Routing decision: DIRECT or PLAN"
    )


def main() -> int:
    parser = PydanticOutputParser(pydantic_object=RouteDecision)

    print("Format instructions:")
    print(parser.get_format_instructions())

    samples = [
        'route: DIRECT',
        '{"route":"DIRECT"}',
        '{"route":"PLAN"}',
        '{"route":"Plan"}',
        "DIRECT",
    ]

    for s in samples:
        print("\n---")
        print("input:", repr(s))
        try:
            parsed = parser.parse(s)
            print("parsed:", parsed)
            print("route:", parsed.route)
        except Exception as e:
            print("PARSE FAIL:", type(e).__name__, e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
