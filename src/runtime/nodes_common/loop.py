from __future__ import annotations

import json
from typing import Any, Callable, Iterable, Optional, Sequence

from runtime.providers.types import Message, StreamEvent, ToolCall
from runtime.tool_loop import ToolSet, chat_stream

from .context import TokenBuilder, append_tool_transcript_messages, build_reflect_messages
from .execution_state import (
    build_invalid_output_feedback_payload,
    ensure_controller_execution_state,
    reset_controller_execution_state,
)
from .primitives import (
    append_node_trace,
    get_emitter,
    normalize_completion_sentinel,
    parse_first_json_object,
)
from .tools import ensure_tool_transcript, execute_recovered_tool_call, reset_tool_transcript


def _compact_text(text: str, *, limit: int = 2000) -> str:
    if text is None:
        return ""
    s = str(text)
    if len(s) <= limit:
        return s
    return s[:limit] + "…"


def _compact_tool_args(tc: ToolCall, *, limit: int = 800) -> str:
    try:
        s = tc.arguments_json or ""
    except Exception:
        s = ""
    return _compact_text(s, limit=limit)


def collect_text(
    events: Iterable[StreamEvent],
    *,
    span=None,
    on_tool_result: Optional[Callable[[str, str], None]] = None,
    on_delta_text: Optional[Callable[[str], None]] = None,
    log_fields: Optional[dict] = None,
) -> str:
    """Collect final assistant text from a streamed chat."""
    parts: list[str] = []
    pending_tool_names: list[str] = []

    for ev in events:
        if ev.type == "delta_text" and ev.text:
            parts.append(ev.text)
            if on_delta_text is not None:
                try:
                    on_delta_text(ev.text)
                except Exception:
                    pass
        elif ev.type == "delta_thinking" and ev.text and span is not None:
            try:
                span.thinking(ev.text)
            except Exception:
                pass
        elif ev.type == "tool_call" and ev.tool_call is not None:
            pending_tool_names.append(ev.tool_call.name)
            if span is not None:
                try:
                    span.log(
                        level="info",
                        logger="llm",
                        message=f"[llm] tool_call {ev.tool_call.name} args={_compact_tool_args(ev.tool_call)}",
                        fields={
                            "tool": ev.tool_call.name,
                            "tool_call_id": ev.tool_call.id,
                            "args_json": ev.tool_call.arguments_json,
                        },
                    )
                except Exception:
                    pass
        elif ev.type == "tool_result" and ev.text is not None:
            tool_name = pending_tool_names.pop(0) if pending_tool_names else "unknown_tool"
            if on_tool_result is not None:
                try:
                    on_tool_result(tool_name, ev.text)
                except Exception:
                    pass
            if span is not None:
                try:
                    span.log(
                        level="info",
                        logger="tool_loop",
                        message=f"[tool] result {tool_name} = {_compact_text(ev.text, limit=2000)}",
                        fields={"tool": tool_name, "result": ev.text},
                    )
                except Exception:
                    pass
        elif ev.type == "error":
            raise RuntimeError(ev.error or "LLM provider error")
        elif ev.type == "done":
            break

    out = "".join(parts)
    if span is not None:
        try:
            span.log(
                level="info",
                logger="llm",
                message=f"[llm] final_output = {_compact_text(out, limit=4000)}",
                fields={**({} if log_fields is None else dict(log_fields)), "final_output": out},
            )
        except Exception:
            pass
    return out


def run_controller_node(
    *,
    state: dict,
    deps,
    services,
    node_id: str,
    label: str,
    role_key: str,
    prompt_name: str,
    node_key_for_tools: str,
    apply_tool_result: Callable[[dict, str, str], None],
    apply_handoff: Callable[[dict, dict], bool],
    stop_when: Optional[Callable[[dict], bool]] = None,
    invalid_output_retry_limit: int = 0,
    build_invalid_output_feedback: Optional[Callable[[dict, Optional[str], str], dict[str, Any] | None]] = None,
    max_rounds: int = 5,
    prepare_execution_state: Optional[Callable[[dict], None]] = None,
    on_tool_executed: Optional[Callable[[dict, dict[str, Any], dict[str, Any]], None]] = None,
    build_initial_messages: Optional[Callable[[dict, Any], list[Message]]] = None,
    replace_initial_system_message: bool = True,
    insert_tool_transcript_before_final_user: bool = True,
    toolset_for_round: Optional[Callable[[dict, ToolSet], ToolSet]] = None,
    completion_sentinels: Optional[Sequence[str]] = None,
    on_completion_sentinel: Optional[Callable[[dict, str], bool]] = None,
    build_post_tool_result_messages: Optional[Callable[[dict, str, str], Sequence[Message] | None]] = None,
    allow_final_text: bool = False,
    require_completion_ready_for_final_text: bool = True,
    disable_tools_when_final_text_allowed: bool = True,
    final_text_message_id: Optional[str] = None,
    on_final_text: Optional[Callable[[dict, str], None]] = None,
    recover_tool_call_from_text: Optional[Callable[[str, ToolSet | None], ToolCall | None]] = None,
) -> dict:
    append_node_trace(state, node_id)
    emitter = get_emitter(state)
    span = emitter.span(node_id=node_id, label=label)

    try:
        llm = deps.get_llm(role_key)
        toolset = services.tools.toolset_for_node(node_key_for_tools)
        builder = TokenBuilder(state, deps, node_id, role_key, toolset)
        invalid_retry_count = 0
        pending_feedback: dict[str, Any] | None = None
        sentinel_set = {normalize_completion_sentinel(item) for item in (completion_sentinels or []) if str(item).strip()}
        reset_tool_transcript(state, node_id)
        reset_controller_execution_state(state, node_id)
        if prepare_execution_state is not None:
            prepare_execution_state(state)

        for round_idx in range(1, max_rounds + 1):
            if stop_when is not None and stop_when(state):
                span.end_ok()
                return state

            execution_state = ensure_controller_execution_state(state, node_id)
            execution_state["current_round"] = round_idx
            if prepare_execution_state is not None:
                prepare_execution_state(state)

            prompt = builder.render_prompt(prompt_name)
            if build_initial_messages is not None:
                messages = list(build_initial_messages(state, builder))
                if replace_initial_system_message and messages:
                    messages[0] = Message(role="system", content=prompt)
                messages = append_tool_transcript_messages(
                    messages,
                    state,
                    node_id,
                    insert_before_final_user=insert_tool_transcript_before_final_user,
                )
            else:
                messages = [Message(role="user", content=prompt)]
            if pending_feedback is not None:
                messages.append(Message(role="system", content=json.dumps(pending_feedback, ensure_ascii=False)))
                pending_feedback = None

            last_tool_name: str | None = None
            tool_executed = False
            terminal_tool_triggered = False
            final_text_stream_started = False

            def _on_tool_result(tool_name: str, result_text: str) -> bool:
                nonlocal last_tool_name, tool_executed, terminal_tool_triggered
                last_tool_name = tool_name
                tool_executed = True
                apply_tool_result(state, tool_name, result_text)
                should_stop = bool(stop_when(state)) if stop_when is not None else False
                if should_stop:
                    terminal_tool_triggered = True
                return should_stop

            def _on_tool_executed(entry: dict[str, Any]) -> None:
                ensure_tool_transcript(state, node_id).append(dict(entry))
                execution_state = ensure_controller_execution_state(state, node_id)
                execution_state["last_action_name"] = str(entry.get("tool_name") or "none")
                execution_state["last_action_kind"] = str(entry.get("tool_kind") or "none")
                execution_state["last_action_status"] = "ok" if bool(entry.get("ok")) else "error"
                if on_tool_executed is not None:
                    on_tool_executed(state, execution_state, dict(entry))

            completion_ready_now = bool(execution_state.get("completion_ready", False))
            round_toolset = toolset_for_round(state, toolset) if toolset_for_round is not None else toolset
            final_text_allowed_now = allow_final_text and (
                completion_ready_now or not require_completion_ready_for_final_text
            )
            active_tools = None if (final_text_allowed_now and disable_tools_when_final_text_allowed) else round_toolset
            stop_after_round = False if active_tools is None else True

            events = chat_stream(
                provider=deps.provider,
                model=llm.model,
                messages=messages,
                params=llm.params,
                response_format=None,
                tools=active_tools,
                max_steps=1,
                emitter=emitter,
                node_id=node_id,
                span_id=getattr(span, "span_id", None),
                on_tool_result=_on_tool_result,
                build_post_tool_result_messages=(
                    None
                    if build_post_tool_result_messages is None
                    else lambda tool_name, result_text, descriptor: build_post_tool_result_messages(state, tool_name, result_text)
                ),
                on_tool_executed=_on_tool_executed,
                stop_after_tool_round=stop_after_round,
            )

            def _on_final_delta(text: str) -> None:
                nonlocal final_text_stream_started
                if not final_text_allowed_now or emitter is None or not text:
                    return
                message_id = final_text_message_id or node_id
                if not final_text_stream_started:
                    emitter.emit(emitter.factory.assistant_start(message_id=message_id))
                    final_text_stream_started = True
                emitter.emit(emitter.factory.assistant_delta(message_id=message_id, text=text))

            raw = collect_text(
                events,
                span=span,
                on_delta_text=_on_final_delta if final_text_allowed_now else None,
                log_fields={"round": round_idx},
            )

            if terminal_tool_triggered:
                span.end_ok()
                return state

            if stop_when is not None and stop_when(state):
                break

            if tool_executed:
                continue

            invalid_output_error: str | None = None
            obj: dict[str, Any] | None = None

            if not raw or not raw.strip():
                invalid_output_error = f"{node_id}: model produced no final output"
            elif final_text_allowed_now:
                final_text = raw.strip()
                if emitter is not None and final_text_stream_started:
                    message_id = final_text_message_id or node_id
                    emitter.emit(emitter.factory.assistant_end(message_id=message_id))
                if on_final_text is not None:
                    on_final_text(state, final_text)
                span.end_ok()
                return state
            elif allow_final_text:
                invalid_output_error = (
                    f"{node_id}: final text is not allowed before completion_ready is true; "
                    "call a real tool instead"
                )
            else:
                raw_stripped = raw.strip()
                if recover_tool_call_from_text is not None and active_tools is not None:
                    recovered_tool_call = recover_tool_call_from_text(raw_stripped, active_tools)
                    if recovered_tool_call is not None:
                        stop = execute_recovered_tool_call(
                            recovered_tool_call=recovered_tool_call,
                            tools=active_tools,
                            emitter=emitter,
                            node_id=node_id,
                            span_id=getattr(span, "span_id", None),
                            step=round_idx,
                            on_tool_result=_on_tool_result,
                            on_tool_executed=_on_tool_executed,
                        )
                        if stop:
                            span.end_ok()
                            return state
                        continue
                sentinel = normalize_completion_sentinel(raw_stripped)
                if sentinel_set and sentinel in sentinel_set:
                    if on_completion_sentinel is None:
                        invalid_output_error = f"{node_id}: completion sentinel is not supported for this node"
                    else:
                        try:
                            stop = on_completion_sentinel(state, sentinel)
                        except Exception as e:
                            invalid_output_error = f"{node_id}: {e}"
                        else:
                            if stop:
                                span.end_ok()
                                return state
                            invalid_output_error = f"{node_id}: completion sentinel did not complete the node"
                else:
                    try:
                        obj = parse_first_json_object(raw)
                    except Exception as e:
                        invalid_output_error = f"{node_id}: {e}"

            if invalid_output_error is None and obj is not None:
                try:
                    stop = apply_handoff(state, obj)
                except Exception as e:
                    invalid_output_error = f"{node_id}: {e}"
                else:
                    if stop:
                        break

            if invalid_output_error is None:
                continue

            if emitter is not None:
                emitter.emit(
                    emitter.factory.log_line(
                        level="error",
                        logger="controller_node",
                        message=f"[controller] invalid output {node_id}: {invalid_output_error}",
                        node_id=node_id,
                        span_id=getattr(span, "span_id", None),
                        fields={
                            "node": node_id,
                            "round": round_idx,
                            "last_tool": last_tool_name,
                            "retry_count": invalid_retry_count,
                            "error": invalid_output_error,
                            "invalid_node_output": True,
                        },
                    )
                )

            if (
                build_invalid_output_feedback is not None
                and invalid_retry_count < max(0, int(invalid_output_retry_limit))
            ):
                feedback = build_invalid_output_feedback(state, last_tool_name, invalid_output_error)
                if isinstance(feedback, dict):
                    pending_feedback = feedback
                invalid_retry_count += 1
                continue

            raise RuntimeError(invalid_output_error)

        span.end_ok()
        return state
    except Exception as e:
        span.end_error(code="NODE_ERROR", message=str(e))
        raise


def run_default_node(
    *,
    state: dict,
    deps,
    services,
    node_id: str,
    label: str,
    role_key: str,
    prompt_name: str,
    node_key_for_tools: str,
    max_rounds: int,
    prepare_execution_state: Callable[[dict], None],
    build_initial_messages: Callable[[dict, Any], list[Message]],
    apply_tool_result: Callable[[dict, str, str], None],
    build_invalid_output_feedback: Callable[[dict, str | None, str], dict[str, Any] | None],
    stop_when: Callable[[dict], bool] | None = None,
    on_tool_executed: Callable[[dict, dict[str, Any], dict[str, Any]], None] | None = None,
    toolset_for_round: Callable[[dict, ToolSet], ToolSet] | None = None,
    insert_tool_transcript_before_final_user: bool = True,
    replace_initial_system_message: bool = False,
    completion_sentinel: str | None = None,
    complete_on_sentinel: Callable[[dict], None] | None = None,
    post_tool_guidance: str | None = None,
    allow_final_text: bool = False,
    require_completion_ready_for_final_text: bool = True,
    disable_tools_when_final_text_allowed: bool = True,
    final_text_message_id: str | None = None,
    on_final_text: Callable[[dict, str], None] | None = None,
    invalid_output_retry_limit: int = 2,
) -> dict:
    build_post_tool_result_messages = None
    if isinstance(post_tool_guidance, str) and post_tool_guidance.strip():
        def _build_post_tool_result_messages(state: dict, tool_name: str, result_text: str) -> list[Message]:
            _ = state
            _ = tool_name
            _ = result_text
            return [Message(role="system", content=post_tool_guidance)]
        build_post_tool_result_messages = _build_post_tool_result_messages

    on_completion_sentinel = None
    if completion_sentinel is not None and complete_on_sentinel is not None:
        def _on_completion_sentinel(state: dict, sentinel: str) -> bool:
            if normalize_completion_sentinel(sentinel) != normalize_completion_sentinel(completion_sentinel):
                return False
            complete_on_sentinel(state)
            return True
        on_completion_sentinel = _on_completion_sentinel

    def _apply_handoff(state: dict, obj: dict) -> bool:
        _ = state
        _ = obj
        if completion_sentinel is not None:
            raise RuntimeError(f"{node_id} completes only by replying {completion_sentinel}")
        if allow_final_text:
            raise RuntimeError(f"{node_id} must either call a tool or emit final user-facing prose")
        raise RuntimeError(f"{node_id} emitted an unsupported handoff payload")

    return run_controller_node(
        state=state,
        deps=deps,
        services=services,
        node_id=node_id,
        label=label,
        role_key=role_key,
        prompt_name=prompt_name,
        node_key_for_tools=node_key_for_tools,
        apply_tool_result=apply_tool_result,
        apply_handoff=_apply_handoff,
        stop_when=stop_when,
        invalid_output_retry_limit=invalid_output_retry_limit,
        build_invalid_output_feedback=build_invalid_output_feedback,
        max_rounds=max_rounds,
        prepare_execution_state=prepare_execution_state,
        on_tool_executed=on_tool_executed,
        build_initial_messages=build_initial_messages,
        replace_initial_system_message=replace_initial_system_message,
        insert_tool_transcript_before_final_user=insert_tool_transcript_before_final_user,
        toolset_for_round=toolset_for_round,
        completion_sentinels=None if completion_sentinel is None else [completion_sentinel],
        on_completion_sentinel=on_completion_sentinel,
        build_post_tool_result_messages=build_post_tool_result_messages,
        allow_final_text=allow_final_text,
        require_completion_ready_for_final_text=require_completion_ready_for_final_text,
        disable_tools_when_final_text_allowed=disable_tools_when_final_text_allowed,
        final_text_message_id=final_text_message_id,
        on_final_text=on_final_text,
    )


def run_reflect_node(
    *,
    state: dict,
    deps,
    services,
    node_id: str,
    label: str,
    role_key: str,
    prompt_name: str,
    node_key_for_tools: str,
    max_rounds: int,
    completion_sentinel: str,
    stop_when: Callable[[dict], bool],
    prepare_evidence: Callable[[dict], None],
    prepare_execution_state: Callable[[dict], None],
    build_task_message: Callable[[dict, Any], Message],
    toolset_for_round: Callable[[dict, ToolSet], ToolSet],
    apply_tool_result: Callable[[dict, str, str], None],
    complete_on_sentinel: Callable[[dict], None],
    build_invalid_output_hint: Callable[[str], str],
    post_tool_guidance: str,
    include_bootstrap_system_messages: bool = False,
    include_recent_turns: bool = True,
    recent_turn_limit: int = 10,
) -> dict:
    prepare_evidence(state)

    def _build_messages(state: dict, builder) -> list[Message]:
        task_message = build_task_message(state, builder)
        return build_reflect_messages(
            state=state,
            builder=builder,
            node_id=node_id,
            role_key=role_key,
            system_prompt_name=prompt_name,
            task_message=task_message,
            include_bootstrap_system_messages=include_bootstrap_system_messages,
            include_recent_turns=include_recent_turns,
            recent_turn_limit=recent_turn_limit,
            include_final_answer=True,
        )

    def _build_invalid_output_feedback(
        state: dict,
        last_tool: str | None,
        error_message: str,
    ) -> dict[str, Any]:
        _ = state
        return build_invalid_output_feedback_payload(
            allowed_actions=["tool_call", completion_sentinel],
            last_tool=last_tool,
            node_hint=build_invalid_output_hint(str(error_message or "")),
        )

    return run_default_node(
        state=state,
        deps=deps,
        services=services,
        node_id=node_id,
        label=label,
        role_key=role_key,
        prompt_name=prompt_name,
        node_key_for_tools=node_key_for_tools,
        max_rounds=max_rounds,
        prepare_execution_state=prepare_execution_state,
        build_initial_messages=_build_messages,
        apply_tool_result=apply_tool_result,
        build_invalid_output_feedback=_build_invalid_output_feedback,
        stop_when=stop_when,
        toolset_for_round=toolset_for_round,
        replace_initial_system_message=False,
        completion_sentinel=completion_sentinel,
        complete_on_sentinel=complete_on_sentinel,
        post_tool_guidance=post_tool_guidance,
    )
