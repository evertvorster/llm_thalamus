"""Hindsight's DeepSeek spend, read from its local HTTP API.

Hindsight records every LLM call in `llm_requests`, and serves them at
``/v1/default/banks/<bank>/llm-requests``.  Two things about that record shape
what this module can honestly report:

* **Retain calls carry the session.**  The coding-agent plugin writes each
  transcript as ``conversation:<pi session id>`` and Hindsight stores it as
  ``metadata.document_id``, so a session's write-back spend is an exact join,
  not a time window.
* **Consolidation and reflect carry no session id.**  They work across
  memories left by many sessions, so they are reported as a running total for
  the bank instead of being apportioned to whichever session was open.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

BASE_URL = "http://127.0.0.1:8889"
# The plugin's default bank template (src/core/bank.ts: "coding-agent::{gitProject}").
BANK_TEMPLATE = "coding-agent::{}"
TIMEOUT = 1.5
PAGE = 500  # the endpoint's own limit
MAX_PAGES = 8


class Rates(NamedTuple):
    """Dollars per million tokens."""

    input: float
    cached: float
    output: float


# Priced by the model that produced the row, not by the deployment: Hindsight
# can be pointed at a local llama.cpp server between one row and the next, and
# those rows cost nothing.  pi's own deepseek figures, so the two sides of a
# session's cost stay comparable.  A model absent from here is free, not an
# error — its tokens are still counted and shown.
RATES = {"deepseek-v4-flash": Rates(0.30, 0.006, 1.20)}


@dataclass(frozen=True)
class Spend:
    """Token counts, and the money they cost, for a set of Hindsight calls."""

    calls: int = 0
    input: int = 0
    cached: int = 0
    output: int = 0
    thoughts: int = 0
    cost: float = 0.0

    def __add__(self, other: Spend) -> Spend:
        return Spend(
            self.calls + other.calls,
            self.input + other.input,
            self.cached + other.cached,
            self.output + other.output,
            self.thoughts + other.thoughts,
            self.cost + other.cost,
        )

    @property
    def cache_rate(self) -> float | None:
        """Share of input tokens served from cache, 0..1, or None if no input."""
        return self.cached / self.input if self.input else None


def _get(path: str) -> dict | None:
    """GET a JSON object from the local Hindsight API, or None on any failure."""
    try:
        with urllib.request.urlopen(BASE_URL + path, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except (OSError, ValueError, urllib.error.URLError):
        return None
    return data if isinstance(data, dict) else None


def _query(bank: str, *, document_id: str | None = None,
           since: datetime | None = None) -> list[dict]:
    """Every llm-request row for one bank, paged to the end or to MAX_PAGES."""
    path = f"/v1/default/banks/{bank}/llm-requests?"
    if document_id:
        path += f"document_id={urllib.parse.quote(document_id, safe='')}&"
    if since:
        path += f"start_date={urllib.parse.quote(since.isoformat(), safe='')}&"
    rows: list[dict] = []
    offset = 0
    for _ in range(MAX_PAGES):
        page = _get(f"{path}limit={PAGE}&offset={offset}")
        if not page:
            break
        items = page.get("items") or []
        rows.extend(x for x in items if isinstance(x, dict))
        offset += len(items)
        total = page.get("total")
        if not items or not isinstance(total, int) or offset >= total:
            break
    return rows


def _cost(model: str, input: int, cached: int, output: int,
          thoughts: int) -> float:
    """Dollars for one call, or 0.0 for a model with no published price."""
    rates = RATES.get(model)
    if not rates:
        return 0.0
    return (
        max(0, input - cached) * rates.input
        + cached * rates.cached
        + (output + thoughts) * rates.output
    ) / 1e6


def _to_spend(row: dict) -> Spend | None:
    """One row as a Spend, or None for an embedding call (no model, no tokens)."""
    model = row.get("model")
    if not model:
        return None
    tokens = (
        int(row.get("input_tokens") or 0),
        int(row.get("cached_tokens") or 0),
        int(row.get("output_tokens") or 0),
        int(row.get("thoughts_tokens") or 0),
    )
    return Spend(calls=1, input=tokens[0], cached=tokens[1], output=tokens[2],
                 thoughts=tokens[3], cost=_cost(model, *tokens))


def spend_by_operation(bank: str, *, document_id: str | None = None,
                       since: datetime | None = None) -> dict[str, Spend]:
    """Token spend for one bank, split by operation.

    ``document_id`` is the exact session link (``conversation:<session id>``);
    ``since`` narrows to calls started at or after that instant.  The split is
    what is worth showing: consolidation is the bulk of Hindsight's spend and
    the part that runs on its own schedule.
    """
    out: dict[str, Spend] = {}
    for row in _query(bank, document_id=document_id, since=since):
        spend = _to_spend(row)
        if spend:
            operation = str(row.get("operation") or "unknown")
            out[operation] = out.get(operation, Spend()) + spend
    return out


def spend_for(bank: str, **kwargs) -> Spend:
    """Total token spend for one bank; see :func:`spend_by_operation`."""
    return sum(spend_by_operation(bank, **kwargs).values(), Spend())


def bank_for(cwd: str | Path | None) -> str:
    """The bank the coding-agent plugin would use for *cwd*.

    Mirrors ``gitProjectName``: the main repository's name, which is what makes
    worktrees share one bank.  Not a repository at all means the directory's
    own name, which is how ``~`` becomes ``coding-agent::<user>``.
    """
    path = Path(cwd) if cwd else Path.cwd()
    name = path.name
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--path-format=absolute",
             "--git-common-dir"],
            check=False, capture_output=True, text=True, timeout=1.0,
        )
        if out.returncode == 0 and out.stdout.strip():
            common = Path(out.stdout.strip())
            name = common.parent.name if common.name == ".git" else common.name
    except (OSError, subprocess.SubprocessError):
        pass
    return BANK_TEMPLATE.format(name)


def session_id_of(session_file: str | Path | None) -> str | None:
    """The pi session id from a session file name (``<timestamp>_<uuid>.jsonl``)."""
    if not session_file:
        return None
    _, _, uid = Path(session_file).stem.partition("_")
    return uid or None


def banks() -> list[str]:
    """Every bank the server knows, or an empty list when it is unreachable."""
    data = _get("/v1/default/banks")
    if not data:
        return []
    return [
        entry["bank_id"]
        for entry in data.get("banks") or []
        if isinstance(entry.get("bank_id"), str) and entry["bank_id"]
    ]
