from __future__ import annotations

import json
import time
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QPushButton,
    QSizePolicy,
)
from PySide6.QtCore import Slot, Qt, QTimer, QSequentialAnimationGroup, QPropertyAnimation, QEasingCurve, QAbstractAnimation

from controller.mcp.config import load_mcp_config, save_mcp_config
from ui.chat_renderer import ChatRenderer
from ui.config_dialog import ConfigDialog
from ui.widgets import (
    BrainWidget,
    ChatInput,
    MCPServersPanel,
    WorldSummaryWidget,
    CombinedLogsWindow,
)


class MainWindow(QWidget):
    def __init__(self, cfg, controller):
        super().__init__()
        self.setWindowTitle("llm_thalamus")
        self.resize(1100, 700)

        self._cfg = cfg
        self._controller = controller

        # --- brain/log state ---
        self._thalamus_active = True
        self._llm_active = False
        self._logs_window: CombinedLogsWindow | None = None
        self._session_id = str(int(time.time()))

        # --- thinking channel state (ephemeral, per-request) ---
        self._thinking_buffer: list[str] = []

        # --- prompt capture buffer (ephemeral, per-request) ---
        self._prompts_buffer: list[str] = []

        # --- assistant streaming state (chat bubble streaming) ---
        self._assistant_stream_active: bool = False
        self._tool_stack_seq: int = 0
        self._tool_stack_ids_by_span: dict[str, str] = {}

        # --- latest debug snapshots ---
        self._latest_world: dict | None = None
        self._latest_state: dict | None = None
        self._mcp_runtime_config: dict = json.loads(json.dumps(getattr(cfg, "mcp_servers", {}) or {}))
        self._mcp_config_file = Path(getattr(cfg, "mcp_servers_file"))

        # --- thalamus log buffer (persistent for session; always captured) ---
        self._thalamus_buffer: list[str] = []

        # --- left: chat renderer + input area ---
        self.chat = ChatRenderer()
        self.chat.toolApprovalActionRequested.connect(self._on_tool_approval_action_requested)

        self.chat_input = ChatInput()
        self.chat_input.sendRequested.connect(self._on_send_clicked)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._on_send_clicked)

        self.config_button = QPushButton("Config")
        self.config_button.clicked.connect(self._on_config_clicked)

        self.quit_button = QPushButton("Quit")
        self.quit_button.clicked.connect(self._on_quit_clicked)

        buttons_col = QVBoxLayout()
        buttons_col.setContentsMargins(4, 0, 0, 0)
        buttons_col.setSpacing(4)
        buttons_col.addWidget(self.send_button)
        buttons_col.addWidget(self.config_button)
        buttons_col.addWidget(self.quit_button)
        buttons_col.addStretch(1)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.addWidget(self.chat_input, 1)
        input_row.addLayout(buttons_col, 0)

        input_container = QWidget()
        input_container.setLayout(input_row)
        input_container.setMinimumHeight(0)

        min_h = (
            self.send_button.sizeHint().height() * 3
            + buttons_col.spacing() * 2
        )
        self.chat_input.setMinimumHeight(min_h)
        self.chat_input.setSizePolicy(
            self.chat_input.sizePolicy().horizontalPolicy(),
            QSizePolicy.Expanding,
        )

        # Splitter between chat history (top) and input area (bottom)
        self._chat_splitter = QSplitter(Qt.Vertical, self)
        self._chat_splitter.addWidget(self.chat)
        self._chat_splitter.addWidget(input_container)
        self._chat_splitter.setStretchFactor(0, 4)
        self._chat_splitter.setStretchFactor(1, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(self._chat_splitter, 1)

        # --- right: brain at top + world view panel below ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self.brain_widget = BrainWidget(cfg.graphics_dir)
        self.brain_widget.clicked.connect(self._on_brain_clicked)
        self.brain_widget.setMinimumSize(220, 220)

        # Smooth thinking animation: saturate 1.0 <-> 0.7 in a loop
        self._thinking_anim = QSequentialAnimationGroup(self)

        a1 = QPropertyAnimation(self.brain_widget, b"saturation", self)
        a1.setStartValue(1.00)
        a1.setEndValue(0.70)
        a1.setDuration(900)
        a1.setEasingCurve(QEasingCurve.InOutSine)

        a2 = QPropertyAnimation(self.brain_widget, b"saturation", self)
        a2.setStartValue(0.70)
        a2.setEndValue(1.00)
        a2.setDuration(900)
        a2.setEasingCurve(QEasingCurve.InOutSine)

        self._thinking_anim.addAnimation(a1)
        self._thinking_anim.addAnimation(a2)
        self._thinking_anim.setLoopCount(-1)

        # World view widget
        self.mcp_panel = MCPServersPanel()
        self.mcp_panel.serverClicked.connect(self._on_mcp_server_clicked)
        self.mcp_panel.setMinimumWidth(260)

        self.spaces_panel = WorldSummaryWidget()
        self.spaces_panel.setMinimumWidth(260)

        right_layout.addWidget(self.brain_widget, 0, Qt.AlignHCenter)
        right_layout.addWidget(self.mcp_panel, 0)
        right_layout.addWidget(self.spaces_panel, 1)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(splitter, 1)

        # wiring from controller (snapshot signal names)
        controller.assistant_message.connect(self._on_reply)
        # Streaming assistant output (optional). If present, prefer it.
        if hasattr(controller, "assistant_stream_start"):
            controller.assistant_stream_start.connect(self._on_assistant_stream_start)
        if hasattr(controller, "assistant_stream_delta"):
            controller.assistant_stream_delta.connect(self._on_assistant_stream_delta)
        if hasattr(controller, "assistant_stream_end"):
            controller.assistant_stream_end.connect(self._on_assistant_stream_end)

        controller.busy_changed.connect(self._on_busy)
        controller.error.connect(self._on_error)
        controller.log_line.connect(self._on_log_line)
        controller.history_turn.connect(self._on_history_turn)
        if hasattr(controller, "activity_event"):
            controller.activity_event.connect(self._on_activity_event)

        controller.thinking_started.connect(self._on_thinking_started)
        controller.thinking_delta.connect(self._on_thinking_delta)
        controller.thinking_finished.connect(self._on_thinking_finished)

        if hasattr(controller, "prompt_started"):
            controller.prompt_started.connect(self._on_prompt_started)
        if hasattr(controller, "prompt_delta"):
            controller.prompt_delta.connect(self._on_prompt_delta)
        if hasattr(controller, "prompt_finished"):
            controller.prompt_finished.connect(self._on_prompt_finished)

        if hasattr(controller, "world_committed"):
            controller.world_committed.connect(self._on_world_committed)
        if hasattr(controller, "world_updated"):
            controller.world_updated.connect(self._on_world_updated)
        if hasattr(controller, "state_updated"):
            controller.state_updated.connect(self._on_state_updated)
        if hasattr(controller, "tool_approval_requested"):
            controller.tool_approval_requested.connect(self._on_tool_approval_requested)

        # initial brain state
        self._update_brain_graphic()
        self.brain_widget.set_saturation(1.0)

        # load history once on startup
        controller.emit_history()

        # initial world summary paint (best-effort)
        self._refresh_mcp_panel()
        self._refresh_world_summary()
        self._load_initial_world_snapshot()

        # Seed the vertical splitter after first layout so geometry is correct
        QTimer.singleShot(0, self._seed_chat_splitter)

    # --- splitter seeding ---

    def _seed_chat_splitter(self) -> None:
        h = max(self.height(), 700)
        input_h = int(h * 0.20)
        chat_h = max(h - input_h, 200)
        self._chat_splitter.setSizes([chat_h, input_h])

    def closeEvent(self, event) -> None:
        try:
            if hasattr(self._controller, "shutdown"):
                self._controller.shutdown()
        finally:
            event.accept()

    # --- world summary (Spaces panel) --- 
    def _load_initial_world_snapshot(self) -> None:
        """Load world_state.json once at startup so debug panes have initial data."""
        try:
            world_path = self._controller.world_state_path
            obj = json.loads(Path(world_path).read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                self._latest_world = obj
                # Update mini world widget without waiting for a mutation event.
                try:
                    self.spaces_panel.refresh_from_world(obj)
                except Exception:
                    pass
        except Exception:
            pass

    def _refresh_world_summary(self) -> None:
        """
        Refresh the Spaces panel by reading world_state.json.

        NOTE: do not resolve paths/config here. Delegate to controller.
        """
        try:
            world_path = self._controller.world_state_path
        except Exception:
            return

        try:
            self.spaces_panel.refresh_from_path(Path(world_path))
        except Exception:
            return

    def _refresh_mcp_panel(self) -> None:
        self.mcp_panel.set_servers(self._mcp_runtime_config)

    @Slot()
    def _on_world_committed(self) -> None:
        self._refresh_world_summary()

        # Also populate latest world snapshot for debug panes (best-effort).
        try:
            world_path = self._controller.world_state_path
            obj = json.loads(Path(world_path).read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                self._latest_world = obj
                if self._logs_window is not None and self._logs_window.isVisible():
                    self._logs_window.set_world_json(obj)
        except Exception:
            pass




    @Slot(object)
    def _on_world_updated(self, world: object) -> None:
        if isinstance(world, dict):
            self._latest_world = world
            try:
                self.spaces_panel.refresh_from_world(world)
            except Exception:
                pass
            if self._logs_window is not None and self._logs_window.isVisible():
                try:
                    self._logs_window.set_world_json(world)
                except Exception:
                    pass

    @Slot(object)
    def _on_state_updated(self, state_view: object) -> None:
        if isinstance(state_view, dict):
            self._latest_state = state_view
            if self._logs_window is not None and self._logs_window.isVisible():
                try:
                    self._logs_window.set_state_json(state_view)
                except Exception:
                    pass

    # --- brain & combined logs window ---

    def _update_brain_graphic(self) -> None:
        if not self._thalamus_active:
            state = "inactive"
        elif not self._llm_active:
            state = "thalamus"
        else:
            state = "llm"
        self.brain_widget.set_state(state)

    @Slot()
    def _on_brain_clicked(self) -> None:
        if self._logs_window is None:
            self._logs_window = CombinedLogsWindow(self, session_id=self._session_id)

        if self._logs_window.isVisible():
            self._logs_window.hide()
            return

        # Seed both panes from buffers every time we open (truth = buffers).
        self._logs_window.set_thalamus_text("".join(self._thalamus_buffer))
        self._logs_window.set_thinking_text("".join(self._thinking_buffer))
        self._logs_window.set_prompts_text("".join(self._prompts_buffer))


        # Seed world/state debug panes.
        if self._latest_world is not None:
            self._logs_window.set_world_json(self._latest_world)
        else:
            self._logs_window.set_world_json({})

        if self._latest_state is not None:
            self._logs_window.set_state_json(self._latest_state)
        else:
            # Before the first turn runs, there is no runtime State to snapshot.
            self._logs_window.set_state_json({"note": "No active turn yet."})

        self._logs_window.show()
        self._logs_window.raise_()
        self._logs_window.activateWindow()

    @Slot(str)
    def _on_log_line(self, text: str) -> None:
        # Always buffer, even if the logs window is not visible.
        self._append_thalamus_buffer_line(text)

        # Live update if visible.
        if self._logs_window is not None and self._logs_window.isVisible():
            self._logs_window.append_thalamus_line(text)

    def _append_thalamus_buffer_line(self, text: str) -> None:
        line = text if text.endswith("\n") else (text + "\n")
        self._thalamus_buffer.append(line)

    def _append_thinking_buffer_text(self, text: str) -> None:
        if not text:
            return
        self._thinking_buffer.append(text)
        if self._logs_window is not None and self._logs_window.isVisible():
            self._logs_window.append_thinking_text(text)

    # --- thinking channel (signals) ---

    @Slot()
    def _on_thinking_started(self) -> None:
        self._thinking_buffer = []
        # Start smooth animation
        if self._thinking_anim.state() != QAbstractAnimation.Running:
            self._thinking_anim.start()

        if self._logs_window is not None and self._logs_window.isVisible():
            self._logs_window.set_thinking_text("")
            self._logs_window.set_prompts_text("")

    @Slot(str)
    def _on_thinking_delta(self, text: str) -> None:
        if not text:
            return

        self._append_thinking_buffer_text(text)

    @Slot()
    def _on_thinking_finished(self) -> None:
        # Stop animation and restore full saturation
        if self._thinking_anim.state() == QAbstractAnimation.Running:
            self._thinking_anim.stop()
        self.brain_widget.set_saturation(1.0)

        if self._logs_window is not None and self._logs_window.isVisible():
            self._logs_window.set_thinking_text("".join(self._thinking_buffer))

    
    # --- prompt capture channel (signals) ---

    @Slot()
    def _on_prompt_started(self) -> None:
        self._prompts_buffer = []
        if self._logs_window is not None and self._logs_window.isVisible():
            self._logs_window.set_prompts_text("")

    @Slot(str)
    def _on_prompt_delta(self, text: str) -> None:
        if not text:
            return
        self._prompts_buffer.append(text)
        if self._logs_window is not None and self._logs_window.isVisible():
            self._logs_window.append_prompts_text(text)

    @Slot()
    def _on_prompt_finished(self) -> None:
        if self._logs_window is not None and self._logs_window.isVisible():
            self._logs_window.set_prompts_text("".join(self._prompts_buffer))

# --- send / input ---

    @Slot()
    def _on_send_clicked(self) -> None:
        if not self.send_button.isEnabled():
            return

        text = self.chat_input.toPlainText().strip()
        if not text:
            return

        # reset per-request thinking/prompts
        self._thinking_buffer = []
        self._prompts_buffer = []
        if self._thinking_anim.state() == QAbstractAnimation.Running:
            self._thinking_anim.stop()
        self.brain_widget.set_saturation(1.0)

        if self._logs_window is not None and self._logs_window.isVisible():
            self._logs_window.set_thinking_text("")
            self._logs_window.set_prompts_text("")

        self.chat.add_turn("human", text)
        self.chat_input.clear()
        self._controller.submit_message(text)

    @Slot(bool)
    def _on_busy(self, busy: bool) -> None:
        self.send_button.setDisabled(busy)
        self._llm_active = bool(busy)
        if busy:
            self._thalamus_active = True
        self._update_brain_graphic()

    # --- assistant streaming (chat bubble) ---

    @Slot()
    def _on_assistant_stream_start(self) -> None:
        self._assistant_stream_active = True
        self._thalamus_active = True
        self._update_brain_graphic()
        self.chat.begin_assistant_stream()

    @Slot(str)
    def _on_assistant_stream_delta(self, text: str) -> None:
        if not self._assistant_stream_active:
            return
        self.chat.append_assistant_delta(text)

    @Slot()
    def _on_assistant_stream_end(self) -> None:
        if not self._assistant_stream_active:
            return
        self.chat.end_assistant_stream()
        self._assistant_stream_active = False


    @Slot(str)
    def _on_reply(self, text: str) -> None:
        # If we are streaming an assistant message into the chat bubble, ignore the
        # legacy one-shot signal to avoid duplicates.
        if self._assistant_stream_active:
            return

        self._thalamus_active = True
        self._update_brain_graphic()
        self.chat.add_turn("you", text)

    @Slot(str)
    def _on_error(self, text: str) -> None:
        self._thalamus_active = False
        self._update_brain_graphic()
        self.chat.add_turn("system", text)

    @Slot(str, str, str)
    def _on_history_turn(self, role: str, content: str, ts: str) -> None:
        self.chat.add_turn(role, content, meta=f"history • {ts}")

    @Slot(object)
    def _on_activity_event(self, event: object) -> None:
        if not isinstance(event, dict):
            return

        et = str(event.get("type") or "")
        node_id = str(event.get("node_id") or "")
        span_id = str(event.get("span_id") or "")
        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}

        if et == "node_start":
            label = str(payload.get("label") or node_id or "node")
            self._append_thalamus_buffer_line(f"[node] start {node_id or label}")
            self._append_thinking_buffer_text(f"\n\n===== {node_id or label} START =====\n")
        elif et == "node_end":
            status = "ok" if payload.get("ok", True) else "error"
            self._append_thalamus_buffer_line(f"[node] end {node_id or 'node'} status={status}")
            self._append_thinking_buffer_text(f"\n===== {node_id or 'node'} END ({status}) =====\n")

        if et in {"tool_call", "tool_result"}:
            stack_id = self._ensure_tool_stack_id_for_span(
                span_id,
                fallback_key=f"node:{node_id or 'unknown'}",
            )
            tool_event = dict(payload)
            tool_event["event_type"] = et
            tool_event["node_id"] = node_id
            tool_event["span_id"] = span_id
            self.chat.upsert_tool_event(stack_id, tool_event)
            return

        if et == "node_start":
            stack_id = self._ensure_tool_stack_id_for_span(
                span_id,
                fallback_key=f"node:{node_id or 'unknown'}",
            )
            node_event = dict(payload)
            node_event["event_type"] = et
            node_event["node_id"] = node_id
            node_event["span_id"] = span_id
            self.chat.upsert_tool_event(stack_id, node_event)
            return
        elif et == "node_end":
            stack_id = self._ensure_tool_stack_id_for_span(
                span_id,
                fallback_key=f"node:{node_id or 'unknown'}",
            )
            node_event = dict(payload)
            node_event["event_type"] = et
            node_event["node_id"] = node_id
            node_event["span_id"] = span_id
            self.chat.upsert_tool_event(stack_id, node_event)
            return

    def _ensure_tool_stack_id_for_span(self, span_id: str, *, fallback_key: str) -> str:
        key = span_id.strip() or fallback_key.strip() or "unknown"
        existing = self._tool_stack_ids_by_span.get(key)
        if existing:
            return existing
        self._tool_stack_seq += 1
        stack_id = f"tool-stack-{self._tool_stack_seq}"
        self._tool_stack_ids_by_span[key] = stack_id
        return stack_id

    # --- config / quit ---

    def _write_config_file(self, new_cfg: dict) -> None:
        path = Path(self._cfg.config_file)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(new_cfg, f, ensure_ascii=False, indent=2)
            f.write("\n")

    def _write_mcp_config_file(self, mcp_cfg: dict) -> None:
        save_mcp_config(self._mcp_config_file, mcp_cfg)

    def _set_mcp_tool_policy(self, server_id: str, tool_name: str, approval: str) -> bool:
        if not server_id or not tool_name or approval not in {"ask", "auto", "deny"}:
            return False
        try:
            persisted_cfg = load_mcp_config(self._mcp_config_file)
            servers = persisted_cfg.get("servers", {})
            if not isinstance(servers, dict):
                return False
            server_cfg = servers.get(server_id)
            if not isinstance(server_cfg, dict):
                return False

            tools = server_cfg.get("tools", {})
            if not isinstance(tools, dict):
                tools = {}
                server_cfg["tools"] = tools

            tool_cfg = tools.get(tool_name)
            if not isinstance(tool_cfg, dict):
                tool_cfg = {}
                tools[tool_name] = tool_cfg
            tool_cfg["approval"] = approval

            self._write_mcp_config_file(persisted_cfg)

            runtime_servers = self._mcp_runtime_config.get("servers", {})
            if not isinstance(runtime_servers, dict):
                runtime_servers = {}
                self._mcp_runtime_config["servers"] = runtime_servers
            runtime_server = runtime_servers.get(server_id)
            if not isinstance(runtime_server, dict):
                runtime_server = {}
                runtime_servers[server_id] = runtime_server
            runtime_tools = runtime_server.get("tools", {})
            if not isinstance(runtime_tools, dict):
                runtime_tools = {}
                runtime_server["tools"] = runtime_tools
            runtime_tool = runtime_tools.get(tool_name)
            if not isinstance(runtime_tool, dict):
                runtime_tool = {}
                runtime_tools[tool_name] = runtime_tool
            runtime_tool["approval"] = approval

            self._refresh_mcp_panel()

            if hasattr(self._controller, "update_mcp_tool_approval_policy"):
                self._controller.update_mcp_tool_approval_policy(server_id, tool_name, approval)
            return True
        except Exception:
            return False

    @Slot(dict, bool)
    def _on_config_applied(self, new_cfg: dict, _should_restart: bool) -> None:
        self._write_config_file(new_cfg)
        self._controller.reload_config()

    @Slot(dict)
    def _on_mcp_config_applied(self, new_mcp_cfg: dict) -> None:
        self._write_mcp_config_file(new_mcp_cfg)
        self._merge_runtime_mcp_view(new_mcp_cfg)
        self._refresh_mcp_panel()

    def _merge_runtime_mcp_view(self, new_mcp_cfg: dict) -> None:
        runtime_cfg = json.loads(json.dumps(self._mcp_runtime_config))
        runtime_servers = runtime_cfg.get("servers", {}) if isinstance(runtime_cfg, dict) else {}
        if not isinstance(runtime_servers, dict):
            runtime_servers = {}
            runtime_cfg = {"servers": runtime_servers}

        new_servers = new_mcp_cfg.get("servers", {}) if isinstance(new_mcp_cfg, dict) else {}
        if not isinstance(new_servers, dict):
            new_servers = {}

        for server_id in list(runtime_servers.keys()):
            if server_id not in new_servers:
                runtime_servers.pop(server_id, None)

        for server_id, server_cfg in new_servers.items():
            if not isinstance(server_id, str) or not isinstance(server_cfg, dict):
                continue
            runtime_server = runtime_servers.get(server_id)
            if not isinstance(runtime_server, dict):
                runtime_server = {}
                runtime_servers[server_id] = runtime_server

            for key in ("label", "enabled", "transport", "status"):
                if key in server_cfg:
                    runtime_server[key] = json.loads(json.dumps(server_cfg[key]))

            new_tools = server_cfg.get("tools", {}) or {}
            if not isinstance(new_tools, dict):
                new_tools = {}
            runtime_tools = runtime_server.get("tools", {}) or {}
            if not isinstance(runtime_tools, dict):
                runtime_tools = {}
                runtime_server["tools"] = runtime_tools

            for tool_name in list(runtime_tools.keys()):
                if tool_name not in new_tools:
                    runtime_tools.pop(tool_name, None)

            for tool_name, tool_cfg in new_tools.items():
                if not isinstance(tool_name, str) or not isinstance(tool_cfg, dict):
                    continue
                runtime_tool = runtime_tools.get(tool_name)
                if not isinstance(runtime_tool, dict):
                    runtime_tool = {}
                    runtime_tools[tool_name] = runtime_tool
                for key in ("approval", "available"):
                    if key in tool_cfg:
                        runtime_tool[key] = json.loads(json.dumps(tool_cfg[key]))

        self._mcp_runtime_config = runtime_cfg

    def _open_config_dialog(self, *, focused_server_id: str | None = None) -> None:
        with open(self._cfg.config_file, "r", encoding="utf-8") as f:
            file_cfg = json.load(f)

        file_mcp_cfg = load_mcp_config(self._mcp_config_file)
        dlg = ConfigDialog(
            file_cfg,
            file_mcp_cfg,
            mcp_runtime_config=self._mcp_runtime_config,
            focused_server_id=focused_server_id,
            parent=self,
        )
        dlg.configApplied.connect(self._on_config_applied)
        dlg.mcpConfigApplied.connect(self._on_mcp_config_applied)
        dlg.exec()

    @Slot()
    def _on_config_clicked(self) -> None:
        self._open_config_dialog()

    @Slot(str)
    def _on_mcp_server_clicked(self, server_id: str) -> None:
        self._open_config_dialog(focused_server_id=server_id)

    @Slot(object)
    def _on_tool_approval_requested(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return

        request_id = str(payload.get("request_id") or "")
        if not request_id:
            return

        span_id = str(payload.get("span_id") or "")
        node_id = str(payload.get("node_id") or "")
        tool_call_id = str(payload.get("tool_call_id") or "")
        stack_id = self._ensure_tool_stack_id_for_span(
            span_id,
            fallback_key=f"approval:{node_id or 'unknown'}:{tool_call_id or request_id}",
        )
        self.chat.set_tool_approval_pending(stack_id, payload)

    @Slot(str, str, str)
    def _on_tool_approval_action_requested(self, stack_id: str, request_id: str, action: str) -> None:
        if not stack_id or not request_id:
            return
        pending_payload = self.chat.get_pending_tool_approval(stack_id, request_id)
        approved = action in {"approve-once", "always-allow"}

        if action in {"always-allow", "always-deny"}:
            if not isinstance(pending_payload, dict):
                return
            server_id = str(pending_payload.get("mcp_server_id") or "")
            tool_name = str(pending_payload.get("tool_name") or "")
            approval = "auto" if action == "always-allow" else "deny"
            if not self._set_mcp_tool_policy(server_id, tool_name, approval):
                return

        self.chat.resolve_tool_approval_pending(stack_id, request_id, approved)
        self._controller.resolve_tool_approval(request_id, approved)

    @Slot()
    def _on_quit_clicked(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.quit()
