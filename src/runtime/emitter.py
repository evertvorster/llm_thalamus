from __future__ import annotations

"""runtime.emitter

Node-facing emission helpers.

Design goals:
- Make correct streaming the default when authoring nodes.
- Centralize span + timing rules (node_start/node_end, thinking_start/thinking_end).
- Keep nodes free of UI/Qt concerns.
"""

from dataclasses import dataclass
import time
from typing import Any, Dict, Optional

from runtime.events import TurnEventFactory, TurnEvent, LogLevel


@dataclass
class NodeSpan:
    node_id: str
    span_id: str
    label: str
    _factory: TurnEventFactory
    _emit: callable
    _t0_ms: int

    def thinking(self, text: str) -> None:
        if not text:
            return
        self._emit(self._factory.thinking_delta(node_id=self.node_id, span_id=self.span_id, text=text))

    def log(
        self,
        *,
        level: LogLevel,
        message: str,
        logger: str,
        fields: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._emit(
            self._factory.log_line(
                level=level,
                message=message,
                logger=logger,
                node_id=self.node_id,
                span_id=self.span_id,
                fields=fields,
            )
        )

    def end_ok(self) -> None:
        dt = max(0, int(time.time() * 1000) - self._t0_ms)
        self._emit(self._factory.thinking_end(node_id=self.node_id, span_id=self.span_id))
        self._emit(self._factory.node_end_ok(node_id=self.node_id, span_id=self.span_id, duration_ms=dt))

    def end_error(self, *, code: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        dt = max(0, int(time.time() * 1000) - self._t0_ms)
        self._emit(self._factory.thinking_end(node_id=self.node_id, span_id=self.span_id))
        self._emit(
            self._factory.node_end_error(
                node_id=self.node_id,
                span_id=self.span_id,
                code=code,
                message=message,
                details=details,
                duration_ms=dt,
            )
        )


class TurnEmitter:
    """High-level event emission for a single turn."""

    def __init__(self, factory: TurnEventFactory, emit_fn) -> None:
        self._factory = factory
        self._emit = emit_fn

    @property
    def factory(self) -> TurnEventFactory:
        return self._factory

    def emit(self, ev: TurnEvent) -> None:
        self._emit(ev)

    def start_turn(
        self,
        *,
        user_text: str,
        chat_turn_index: Optional[int] = None,
        provider: Optional[str] = None,
        models: Optional[Dict[str, str]] = None,
    ) -> None:
        self._emit(
            self._factory.turn_start(
                user_text=user_text,
                chat_turn_index=chat_turn_index,
                provider=provider,
                models=models,
            )
        )

    def end_turn_ok(self, *, duration_ms: Optional[int] = None) -> None:
        self._emit(self._factory.turn_end_ok(duration_ms=duration_ms))

    def end_turn_error(self, *, code: str, message: str, details: Optional[Dict[str, Any]] = None, duration_ms: Optional[int] = None) -> None:
        self._emit(self._factory.turn_end_error(code=code, message=message, details=details, duration_ms=duration_ms))

    def span(self, *, node_id: str, label: str, attempt: int = 1) -> NodeSpan:
        span_id = self._factory.new_span_id(node_id=node_id)
        t0 = int(time.time() * 1000)
        self._emit(self._factory.node_start(node_id=node_id, span_id=span_id, label=label, attempt=attempt))
        self._emit(self._factory.thinking_start(node_id=node_id, span_id=span_id))
        return NodeSpan(
            node_id=node_id,
            span_id=span_id,
            label=label,
            _factory=self._factory,
            _emit=self._emit,
            _t0_ms=t0,
        )

    # assistant helpers (optional streaming)
    def assistant_full(self, *, message_id: str, text: str) -> None:
        self._emit(self._factory.assistant_start(message_id=message_id))
        if text:
            self._emit(self._factory.assistant_delta(message_id=message_id, text=text))
        self._emit(self._factory.assistant_end(message_id=message_id))
