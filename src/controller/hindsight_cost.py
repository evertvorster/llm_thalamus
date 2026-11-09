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

Prices are pi's own table for deepseek-v4-flash, in dollars per million
tokens: uncached input, cached input, output.  Reasoning is billed as output,
which is why thoughts are added to it.
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

BASE_URL = "http://127.0.0.1:8889"
# The plugin's default bank template (src/core/bank.ts: "coding-agent::{gitProject}").
BANK_TEMPLATE = "coding-agent::{}"
TIMEOUT = 1.5
PAGE = 500
MAX_PAGES = 8

RATES = (0.30, 0.006, 1.20)

__all__ = [
    "BASE_URL",
    "RATES",
    "Spend",
    "bank_for",
    "banks",
    "session_id_of",
    "spend_for",
]


@dataclass(frozen=True)
class Spend:
    """Token counts for a set of Hindsight LLM calls."""

    calls: int = 0
    input: int = 0
    cached: int = 0
    output: int = 0
    thoughts: int = 0

    def __add__(self, other: Spend) -> Spend:
        return Spend(
            self.calls + other.calls,
            self.input + other.input,
            self.cached + other.cached,
            self.output + other.output,
            self.thoughts + other.thoughts,
        )

    @property
    def cost(self) -> float:
        """Dollars, at pi's deepseek-v4-flash rates."""
        uncached = max(0, self.input - self.cached)
        return (
            uncached * RATES[0]
            + self.cached * RATES[1]
            + (self.output + self.thoughts) * RATES[2]
        ) / 1e6

    @property
    def cache_rate(self) -> float | None:
        """Share of input tokens served from cache, 0..1, or None if no input."""
        return self.cached / self.input if self.input else None


def _get(path: str) -> dict | None:
    """GET a JSON object from the local Hindsight API, or None on any failure."""
    try:
        with urllib.request.urlopen(
            BASE_URL + path, timeout=TIMEOUT
        ) as resp:
            data = json.loads(resp.read().decode())
    except (OSError, ValueError, urllib.error.URLError):
        return None
    return data if isinstance(data, dict) else None


def _rows(path: str) -> list[dict]:
    """All rows of a paged llm-requests query, bounded by MAX_PAGES."""
    out: list[dict] = []
    offset = 0
    for _ in range(MAX_PAGES):
        sep = "&" if "?" in path else "?"
        page = _get(f"{path}{sep}limit={PAGE}&offset={offset}")
        if not page:
            break
        items = page.get("items") or []
        out.extend(x for x in items if isinstance(x, dict))
        total = page.get("total")
        offset += len(items)
        if not items or not isinstance(total, int) or offset >= total:
            break
    return out


def _spend(rows: list[dict]) -> Spend:
    """Sum the token-bearing rows; embedding calls carry nulls and contribute 0."""
    total = Spend()
    for row in rows:
        if not row.get("model"):
            continue
        total += Spend(
            calls=1,
            input=int(row.get("input_tokens") or 0),
            cached=int(row.get("cached_tokens") or 0),
            output=int(row.get("output_tokens") or 0),
            thoughts=int(row.get("thoughts_tokens") or 0),
        )
    return total


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
    stem = Path(session_file).stem
    _, _, uid = stem.partition("_")
    return uid or None


def spend_for(bank: str, *, document_id: str | None = None,
              since: datetime | None = None) -> Spend | None:
    """Token spend for one bank, optionally for a document or a start time.

    ``document_id`` is the exact session link (``conversation:<session id>``);
    ``since`` narrows to calls started at or after that instant.
    """
    path = f"/v1/default/banks/{bank}/llm-requests?"
    if document_id:
        path += f"document_id={urllib.parse.quote(document_id, safe='')}&"
    if since:
        path += f"start_date={urllib.parse.quote(since.isoformat(), safe='')}&"
    rows = _rows(path.rstrip("?&"))
    return _spend(rows)


def banks() -> list[str]:
    """Every bank the server knows, or an empty list when it is unreachable."""
    data = _get("/v1/default/banks")
    if not data:
        return []
    out = []
    for entry in data.get("banks") or []:
        bank_id = entry.get("bank_id")
        if isinstance(bank_id, str) and bank_id:
            out.append(bank_id)
    return out
