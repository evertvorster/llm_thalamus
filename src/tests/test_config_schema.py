from __future__ import annotations

from pathlib import Path

from config._schema import extract_effective_values


def test_prefill_socket_counts_parse_from_orchestrator_retrieval_config() -> None:
    eff = extract_effective_values(
        raw={
            "llm": {
                "provider": "ollama",
                "roles": {
                    "planner": {"model": "planner", "params": {}, "response_format": None},
                    "reflect": {"model": "reflect", "params": {}, "response_format": None},
                },
            },
            "thalamus": {
                "orchestrator": {
                    "retrieval": {
                        "default_k": 17,
                        "prefill": {
                            "shared_k": 3,
                            "user_k": 4,
                            "agent_k": 5,
                        },
                    }
                },
            },
        },
        llm_backends={"backends": {"ollama": {"kind": "ollama", "url": "http://localhost:11434"}}},
        resources_root=Path("/tmp/resources"),
        data_root=Path("/tmp/data"),
        state_root=Path("/tmp/state"),
        project_root=Path("/tmp/project"),
        dev_mode=True,
    )

    assert eff.orchestrator_retrieval_default_k == 17
    assert eff.orchestrator_prefill_shared_k == 3
    assert eff.orchestrator_prefill_user_k == 4
    assert eff.orchestrator_prefill_agent_k == 5
    assert not hasattr(eff, "llm_model")


def test_prefill_socket_counts_clamp_negative_values_to_zero() -> None:
    eff = extract_effective_values(
        raw={
            "llm": {
                "provider": "ollama",
                "roles": {
                    "planner": {"model": "planner", "params": {}, "response_format": None},
                    "reflect": {"model": "reflect", "params": {}, "response_format": None},
                },
            },
            "thalamus": {
                "orchestrator": {
                    "retrieval": {
                        "prefill": {
                            "shared_k": -1,
                            "user_k": -2,
                            "agent_k": -3,
                        },
                    }
                },
            },
        },
        llm_backends={"backends": {"ollama": {"kind": "ollama", "url": "http://localhost:11434"}}},
        resources_root=Path("/tmp/resources"),
        data_root=Path("/tmp/data"),
        state_root=Path("/tmp/state"),
        project_root=Path("/tmp/project"),
        dev_mode=True,
    )

    assert eff.orchestrator_prefill_shared_k == 0
    assert eff.orchestrator_prefill_user_k == 0
    assert eff.orchestrator_prefill_agent_k == 0


def test_extract_effective_values_does_not_require_top_level_llm_model() -> None:
    eff = extract_effective_values(
        raw={
            "llm": {
                "provider": "ollama",
                "roles": {
                    "planner": {"model": "planner", "params": {}, "response_format": None},
                    "reflect": {"model": "reflect", "params": {}, "response_format": None},
                },
            },
        },
        llm_backends={"backends": {"ollama": {"kind": "openai_compatible", "url": "http://localhost:11434/v1"}}},
        resources_root=Path("/tmp/resources"),
        data_root=Path("/tmp/data"),
        state_root=Path("/tmp/state"),
        project_root=Path("/tmp/project"),
        dev_mode=True,
    )

    assert eff.llm_provider == "ollama"
    assert eff.llm_url == "http://localhost:11434/v1"
