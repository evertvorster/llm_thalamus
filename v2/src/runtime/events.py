from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional


Channel = Literal["ops", "thought"]
Phase = Literal["start", "progress", "end", "error"]


@dataclass(frozen=True)
class Event:
    """
    Single event schema for UI + logs.
    Keep ops/thought separate using channel.
    """
    channel: Channel
    phase: Phase
    run_id: str
    span_id: str
    node_id: str
    msg: str
    data: Dict[str, Any] = field(default_factory=dict)


def emit_ops(emit, *, run_id: str, span_id: str, node_id: str, phase: Phase, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
    emit(Event(channel="ops", phase=phase, run_id=run_id, span_id=span_id, node_id=node_id, msg=msg, data=data or {}))


def emit_thought(emit, *, run_id: str, span_id: str, node_id: str, text: str) -> None:
    # Treat as "progress" so UI can stream it in a separate panel.
    emit(Event(channel="thought", phase="progress", run_id=run_id, span_id=span_id, node_id=node_id, msg="thought", data={"text": text}))
