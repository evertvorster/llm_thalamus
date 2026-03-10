from __future__ import annotations

from copy import deepcopy
from typing import Any

from runtime.tools.resources import ToolResources
from runtime.tools.types import ToolArgs, ToolHandler, ToolResult


def bind(resources: ToolResources) -> ToolHandler:
    _ = resources

    def handler(args: ToolArgs) -> ToolResult:
        if not isinstance(args, dict):
            raise ValueError("context_apply_ops: args must be an object")

        context = args.get("context")
        if not isinstance(context, dict):
            raise ValueError("context_apply_ops: 'context' must be an object")

        ops = args.get("ops")
        if not isinstance(ops, list):
            raise ValueError("context_apply_ops: 'ops' must be an array")

        out = deepcopy(context)
        for raw_op in ops:
            if not isinstance(raw_op, dict):
                raise ValueError("context_apply_ops: each op must be an object")
            _apply_op(out, raw_op)

        return {
            "ok": True,
            "context": out,
        }

    return handler


def _source_identity(source: dict[str, Any]) -> tuple[str, str | None]:
    kind = str(source.get("kind") or "").strip()
    slot_value = source.get("slot")
    slot = str(slot_value).strip() if isinstance(slot_value, str) and slot_value.strip() else None
    return kind, slot


def _match_source(*, existing: dict[str, Any], target: dict[str, Any]) -> bool:
    existing_kind, _existing_slot = _source_identity(existing)
    target_kind, _target_slot = _source_identity(target)
    return bool(existing_kind) and existing_kind == target_kind


def _coerce_sources(context: dict[str, Any]) -> list[dict[str, Any]]:
    raw = context.get("sources")
    if isinstance(raw, list):
        sources = [s for s in raw if isinstance(s, dict)]
    else:
        sources = []
    context["sources"] = sources
    return sources


def _apply_op(context: dict[str, Any], op: dict[str, Any]) -> None:
    operation = str(op.get("op") or "").strip()
    if not operation:
        raise ValueError("context_apply_ops: op is required")

    if operation == "upsert_source":
        source = op.get("source")
        if not isinstance(source, dict):
            raise ValueError("context_apply_ops: upsert_source requires object field 'source'")

        kind, _slot = _source_identity(source)
        if not kind:
            raise ValueError("context_apply_ops: upsert_source source.kind must be non-empty")

        sources = _coerce_sources(context)
        for idx, existing in enumerate(sources):
            if _match_source(existing=existing, target=source):
                sources[idx] = dict(source)
                break
        else:
            sources.append(dict(source))
        return

    if operation == "clear_sources_by_kind":
        kind = str(op.get("kind") or "").strip()
        if not kind:
            raise ValueError("context_apply_ops: clear_sources_by_kind requires non-empty 'kind'")

        sources = _coerce_sources(context)
        context["sources"] = [
            src for src in sources
            if str(src.get("kind") or "").strip() != kind
        ]
        return

    if operation == "set_complete":
        value = op.get("value")
        if not isinstance(value, bool):
            raise ValueError("context_apply_ops: set_complete value must be boolean")
        context["complete"] = value
        return

    if operation == "set_next":
        value = op.get("value")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("context_apply_ops: set_next value must be non-empty string")
        context["next"] = value.strip()
        return

    raise ValueError(f"context_apply_ops: unsupported op '{operation}'")
