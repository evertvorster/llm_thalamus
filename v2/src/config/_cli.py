from __future__ import annotations

import argparse
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BootstrapArgs:
    dev_mode: bool


def _env_truthy(name: str) -> bool:
    v = os.environ.get(name, "")
    return v.lower() in {"1", "true", "yes", "y", "on"}


def parse_bootstrap_args(argv: list[str]) -> BootstrapArgs:
    p = argparse.ArgumentParser(add_help=True)
    p.add_argument(
        "--dev",
        action="store_true",
        help="Run in development mode (repo-local runtime roots under ./var).",
    )

    ns = p.parse_args(argv)

    dev_mode = bool(ns.dev) or _env_truthy("LLM_THALAMUS_DEV")
    return BootstrapArgs(dev_mode=dev_mode)
