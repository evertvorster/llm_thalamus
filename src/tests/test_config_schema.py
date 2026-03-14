from __future__ import annotations

from pathlib import Path

from config._schema import extract_effective_values


def test_retrieval_k_falls_through_to_orchestrator_default_k() -> None:
    eff = extract_effective_values(
        raw={
            "llm": {
                "provider": "ollama",
                "model": "unused",
                "providers": {"ollama": {"kind": "ollama", "url": "http://localhost:11434"}},
                "roles": {
                    "planner": {"model": "planner", "params": {}, "response_format": None},
                    "answer": {"model": "answer", "params": {}, "response_format": None},
                    "reflect": {"model": "reflect", "params": {}, "response_format": None},
                },
            },
            "thalamus": {
                "retrieval_k": 17,
            },
        },
        resources_root=Path("/tmp/resources"),
        data_root=Path("/tmp/data"),
        state_root=Path("/tmp/state"),
        project_root=Path("/tmp/project"),
        dev_mode=True,
    )

    assert eff.orchestrator_retrieval_default_k == 17
