"""MainWindow — the central Qt window connecting PiRPCBridge signals to the UI."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from controller.pi_bridge import PiRPCBridge
from ui.chat_renderer import ChatRenderer
from ui.command_palette import CommandPalette
from ui.model_dialog import ModelPickerDialog
from ui.session_dialog import SessionDialog
from ui.widgets import BrainWidget, ChatInput


class MainWindow(QWidget):
    """A minimal Qt window connecting PiRPCBridge signals to ChatRenderer."""

    def __init__(self, bridge: PiRPCBridge, graphics_dir: Path):
        super().__init__()
        self.setWindowTitle("llm_thalamus")
        self.resize(1100, 700)

        self._settings = QSettings("llm-thalamus", "llm-thalamus")
        geom = self._settings.value("window/geometry")
        if geom is not None:
            self.restoreGeometry(geom)

        self._bridge = bridge
        self._streaming: bool = False
        self._busy: bool = False
        self._provider: str = ""
        self._thinking_level: str = ""

        # --- chat (full width) ---
        self.chat = ChatRenderer()

        self.chat_input = ChatInput()
        self.chat_input.sendRequested.connect(self._on_send)
        self.chat_input.textChanged.connect(self._on_input_text_changed)

        # ── slash command palette ─────────────────────────────────
        self._command_palette = CommandPalette()
        self._command_palette.attach(bridge, self.chat_input)
        self._command_palette.command_requested.connect(self._on_command_requested)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._on_send)

        self.follow_up_button = QPushButton("Follow up")
        self.follow_up_button.setEnabled(False)
        self.follow_up_button.clicked.connect(self._on_follow_up)

        self.session_button = QPushButton("Session")
        self.session_button.clicked.connect(self._on_open_session_dialog)

        self.quit_button = QPushButton("Quit")
        self.quit_button.clicked.connect(self.close)

        # --- brain (positioned between input and buttons) ---
        self.brain = BrainWidget(graphics_dir)
        self.brain.set_state("thalamus")
        self.brain.setMinimumSize(220, 220)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.addWidget(self.chat_input, 1)
        input_row.addWidget(self.brain, 0, Qt.AlignCenter)

        buttons_col = QVBoxLayout()
        buttons_col.setContentsMargins(0, 0, 0, 0)
        buttons_col.setSpacing(4)
        buttons_col.addWidget(self.send_button)
        buttons_col.addWidget(self.follow_up_button)
        buttons_col.addWidget(self.session_button)

        self.configure_button = QPushButton("Settings")
        self.configure_button.clicked.connect(lambda: self._on_settings_dialog(0))
        buttons_col.addWidget(self.configure_button)

        buttons_col.addWidget(self.quit_button)
        input_row.addLayout(buttons_col)

        # --- status bar ---
        self._status_entries: dict[str, str] = {}

        self._status_frame = QFrame()
        self._status_frame.setObjectName("statusFrame")
        self._status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self._status_frame.setStyleSheet(
            "#statusFrame {"
            "  border-top: 1px solid #ccc; padding: 2px 6px; background: #f5f5f7;"
            "  font-size: 9pt;"
            "}"
            "#statusFrame QLabel { color: #444; }"
        )
        status_vlayout = QVBoxLayout(self._status_frame)
        status_vlayout.setContentsMargins(0, 0, 0, 0)
        status_vlayout.setSpacing(0)

        # ── row 1: path | tokens | context | model ─────────
        row1 = QHBoxLayout()
        row1.setContentsMargins(6, 2, 6, 2)
        row1.setSpacing(16)

        self._path_label = QLabel("\u00a0")
        self._path_label.setToolTip("Working directory and git branch")
        row1.addWidget(self._path_label)
        row1.addStretch(1)

        self._tokens_label = QLabel("\u00a0")
        self._tokens_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._tokens_label.setToolTip("Input ↑ / Output ↓ tokens (k=thousands, M=millions) — R = cache reads")
        row1.addWidget(self._tokens_label)

        self._context_label = QLabel("\u00a0")
        self._context_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._context_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._context_label.setToolTip("Context window usage — current tokens / total window size")
        row1.addWidget(self._context_label)

        self._model_label = QLabel("-")
        self._model_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._model_label.setToolTip("Provider and model.  Click to change model, Ctrl+P to cycle.")
        self._model_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._model_label.mousePressEvent = lambda e: self._on_open_model_picker()
        row1.addWidget(self._model_label)

        # ── thinking level (clickable) ──────────────────────
        self._thinking_label = QLabel("-")
        self._thinking_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._thinking_label.setToolTip("Thinking level.  Click to change, Shift+Tab to cycle.")
        self._thinking_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thinking_label.mousePressEvent = lambda e: self._on_thinking_level_menu()
        row1.addWidget(self._thinking_label)

        status_vlayout.addLayout(row1)

        # ── row 2: toggle buttons + extension status ──────────
        row2 = QHBoxLayout()
        row2.setContentsMargins(6, 0, 6, 2)
        row2.setSpacing(6)

        self._show_thinking_btn = QPushButton("Thinking ON")
        self._show_thinking_btn.setCheckable(True)
        self._show_thinking_btn.setChecked(True)
        self._show_thinking_btn.setFixedHeight(20)
        self._show_thinking_btn.setStyleSheet(
            "QPushButton { font-size: 10px; padding: 0 8px; border-radius: 3px; }"
            "QPushButton:checked { background: #4caf50; color: white; }"
            "QPushButton:!checked { background: #ccc; }"
        )
        self._show_thinking_btn.clicked.connect(self._on_toggle_thinking)
        row2.addWidget(self._show_thinking_btn)

        self._show_tools_btn = QPushButton("Tools ON")
        self._show_tools_btn.setCheckable(True)
        self._show_tools_btn.setChecked(True)
        self._show_tools_btn.setFixedHeight(20)
        self._show_tools_btn.setStyleSheet(
            "QPushButton { font-size: 10px; padding: 0 8px; border-radius: 3px; }"
            "QPushButton:checked { background: #4caf50; color: white; }"
            "QPushButton:!checked { background: #ccc; }"
        )
        self._show_tools_btn.clicked.connect(self._on_toggle_tools)
        row2.addWidget(self._show_tools_btn)

        # Sync button state with renderer defaults from QSettings.
        self._show_thinking_btn.setChecked(self.chat._show_thinking)
        self._show_thinking_btn.setText("Thinking ON" if self.chat._show_thinking else "Thinking OFF")
        self._show_tools_btn.setChecked(self.chat._show_tools)
        self._show_tools_btn.setText("Tools ON" if self.chat._show_tools else "Tools OFF")

        self._status_extras_label = QLabel("")
        self._status_extras_label.setToolTip("Extension status indicators (MemPalace, Memory capture)")
        self._status_extras_label.setVisible(False)
        row2.addWidget(self._status_extras_label, 1)
        status_vlayout.addLayout(row2)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(self.chat, 1)
        root.addLayout(input_row)
        root.addWidget(self._status_frame)

        # --- wire signals ---
        bridge.assistant_stream_start.connect(self._on_stream_start)
        bridge.assistant_stream_delta.connect(self._on_stream_delta)
        bridge.assistant_stream_end.connect(self._on_stream_end)
        bridge.thinking_started.connect(self._on_thinking_started)
        bridge.thinking_delta.connect(self._on_thinking_delta)
        bridge.thinking_finished.connect(self._on_thinking_finished)
        bridge.tool_execution_start.connect(self._on_tool_start)
        bridge.tool_execution_update.connect(self._on_tool_update)
        bridge.tool_execution_end.connect(self._on_tool_end)
        bridge.busy_changed.connect(self._on_busy)
        bridge.error.connect(self._on_error)
        bridge.history_turn.connect(self._on_history_turn)
        bridge.history_thinking.connect(self._on_history_thinking)
        bridge.extension_ui_dialog.connect(self._on_extension_ui_dialog)
        bridge.extension_ui_notify.connect(self._on_extension_ui_notify)
        bridge.extension_ui_status.connect(self._on_extension_ui_status)

        bridge.response_received.connect(self._on_response_received)

        # brain click opens the RPC event log (placeholder for now)
        self.brain.clicked.connect(lambda: print("[brain] clicked"))

        # Track system theme changes for "system" theme mode.
        QApplication.instance().styleHints().colorSchemeChanged.connect(
            self._on_system_theme_changed
        )

        # Request initial status after startup.
        QTimer.singleShot(1200, self._refresh_status_bar)

        # Batch history renders until all startup messages arrive.
        self._history_batch_pending: bool = False

        # ── keyboard shortcuts (single source of truth) ──────────
        _shortcuts: dict[str, tuple[str, object, Qt.ShortcutContext | None]] = {
            "Escape": ("Abort / close palette", self._on_escape, None),
            "Ctrl+L": ("Open model picker", self._on_open_model_picker, None),
            "Ctrl+P": ("Cycle model forward", lambda: self._bridge.send_command({"type": "cycle_model"}), None),
            "Alt+Enter": ("Queue follow-up message", self._on_follow_up, None),
            "Shift+Tab": ("Cycle thinking level", self._on_cycle_thinking_level, Qt.ApplicationShortcut),
        }
        # Also used by /hotkeys and _on_show_hotkeys.
        self._shortcut_descriptions: dict[str, str] = {}
        for keyseq, (desc, handler, ctx) in _shortcuts.items():
            self._shortcut_descriptions[keyseq] = desc
            sc = QShortcut(QKeySequence(keyseq), self)
            sc.activated.connect(handler)
            if ctx is not None:
                sc.setContext(ctx)

        # Track current session path for the session list.
        self._current_session_path: str | None = None
        self._pending_rename: str | None = None
        self._available_models: list[dict] = []
        self._session_dialog: SessionDialog | None = None
        self._session_dir_path: Path | None = None

    def closeEvent(self, event) -> None:
        """Save window layout before closing."""
        self._settings.setValue("window/geometry", self.saveGeometry())
        self.chat.persist_zoom()
        self._bridge.shutdown()
        super().closeEvent(event)

    # ── slot: send / abort / steer / follow-up ─────────────────

    def _on_send(self) -> None:
        """Handle the Send/Stop button and ChatInput Enter key.

        When idle: Send button → ``prompt`` via ``submit_message``.
        When busy + typed text → ``steer`` via ``send_command``.
        When busy + no text (Stop button click) → ``abort``.
        """
        text = self.chat_input.toPlainText().strip()

        if self._busy:
            if not text:
                # Stop button clicked — abort the current operation.
                self._bridge.send_command({"type": "abort"})
                return
            # Steering message while agent is running — use a lightweight
            # insertion so the active assistant stream is not killed.
            self.chat.add_steer_message(text)
            self.chat_input.clear()
            self._bridge.send_command({"type": "steer", "message": text})
            return

        # Idle — normal prompt.
        if not text:
            return
        self.chat.add_turn("human", text)
        self.chat_input.clear()
        self._bridge.submit_message(text)

    def _on_follow_up(self) -> None:
        """Queue a follow-up message for after the agent finishes."""
        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        self.chat.add_steer_message(f"[follow-up] {text}")
        self.chat_input.clear()
        self._bridge.send_command(
            {"type": "follow_up", "message": text}
        )

    # ── theme definitions ───────────────────────────────────────

    _THEMES: dict[str, dict[str, str]] = {
        "dark": {
            "bg": "#1a1a2e",
            "text": "#e0e0e0",
            "bubble_user": "#2d2d44",
            "bubble_assistant": "#252535",
            "meta_text": "#888888",
            "border": "#444444",
        },
        "light": {
            "bg": "#f5f5f7",
            "text": "#000000",
            "bubble_user": "#e3f2fd",
            "bubble_assistant": "#ffffff",
            "meta_text": "#666666",
            "border": "#cccccc",
        },
    }

    # ── slots: display toggles ─────────────────────────────────

    def _on_toggle_thinking(self) -> None:
        val = self._show_thinking_btn.isChecked()
        self._show_thinking_btn.setText("Thinking ON" if val else "Thinking OFF")
        self.chat.set_show_thinking(val)

    def _on_toggle_tools(self) -> None:
        val = self._show_tools_btn.isChecked()
        self._show_tools_btn.setText("Tools ON" if val else "Tools OFF")
        self.chat.set_show_tools(val)

    # ── slots: system theme tracking ────────────────────────────

    def _on_system_theme_changed(self) -> None:
        """Re-apply the system theme when the OS switches dark/light mode."""
        pi_path = Path.home() / ".pi" / "agent" / "settings.json"
        try:
            pi = json.loads(pi_path.read_text())
            if pi.get("theme") != "system":
                return
        except (OSError, json.JSONDecodeError):
            return
        scheme = QApplication.instance().styleHints().colorScheme()
        tn = "dark" if scheme == Qt.ColorScheme.Dark else "light"
        tc = self._THEMES.get(tn)
        if tc:
            self.chat.set_theme(tc)

    # ── slots: settings dialog ──────────────────────────────────

    def _on_settings_dialog(self, default_tab: int = 0) -> None:
        """Show a unified settings dialog (Display + pi Backend).

        *default_tab* — which tab is shown first (0=Display, 1=pi Backend).
        """
        pi_path = Path.home() / ".pi" / "agent" / "settings.json"
        pi_settings: dict = {}
        try:
            pi_settings = json.loads(pi_path.read_text())
        except (OSError, json.JSONDecodeError):
            pass

        def _sr(label: str, cur: int, mn: int, mx: int) -> tuple[QHBoxLayout, QSpinBox]:
            """Build a labeled spin-row."""
            r = QHBoxLayout()
            r.addWidget(QLabel(label))
            sp = QSpinBox()
            sp.setRange(mn, mx)
            sp.setValue(cur)
            r.addWidget(sp)
            r.addStretch()
            return r, sp

        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.resize(540, 420)
        dlg.setModal(True)

        layout = QVBoxLayout(dlg)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # ── Tab 1: Display ────────────────────────────────────────
        disp = QWidget()
        dl = QVBoxLayout(disp)
        dl.setSpacing(8)

        theme_cb = QComboBox()
        theme_cb.addItems(["dark", "light", "system"])
        t = str(pi_settings.get("theme", "dark"))
        i = theme_cb.findText(t)
        if i >= 0: theme_cb.setCurrentIndex(i)
        r = QHBoxLayout(); r.addWidget(QLabel("Theme:")); r.addWidget(theme_cb); r.addStretch()
        dl.addLayout(r)

        _, aw_spin = _sr("Auto-collapse agent work (keep N):",
                         self.chat._auto_collapse_agent_work, -1, 20)
        dl.addLayout(_sr("Auto-collapse agent work (keep N):",
                         self.chat._auto_collapse_agent_work, -1, 20)[0])
        _, tk_spin = _sr("Auto-collapse thinking (keep N):",
                         self.chat._auto_collapse_thinking, -1, 20)
        dl.addLayout(_sr("Auto-collapse thinking (keep N):",
                         self.chat._auto_collapse_thinking, -1, 20)[0])
        _, tl_spin = _sr("Auto-collapse tools (keep N):",
                         self.chat._auto_collapse_tools, -1, 20)
        dl.addLayout(_sr("Auto-collapse tools (keep N):",
                         self.chat._auto_collapse_tools, -1, 20)[0])
        dl.addSpacing(8)
        _, pg_spin = _sr("Messages per page:", self.chat._page_size, 1, 100)
        dl.addLayout(_sr("Messages per page:", self.chat._page_size, 1, 100)[0])
        _, pd_spin = _sr("Pages displayed:", self.chat._pages_displayed, 1, 10)
        dl.addLayout(_sr("Pages displayed:", self.chat._pages_displayed, 1, 10)[0])
        dl.addStretch()
        tabs.addTab(disp, "Display")

        # ── Tab 2: pi Backend ─────────────────────────────────────
        bk = QWidget()
        bl = QVBoxLayout(bk)
        bl.setSpacing(8)

        # Provider
        prov_cb = QComboBox(); prov_cb.setEditable(True)
        prov_cb.addItems(sorted(set(m.get("provider","") for m in self._available_models)))
        v = str(pi_settings.get("defaultProvider",""))
        if v: i=prov_cb.findText(v); prov_cb.setCurrentIndex(max(0,i))
        r = QHBoxLayout(); r.addWidget(QLabel("Default provider:")); r.addWidget(prov_cb,1); bl.addLayout(r)

        # Model
        mod_cb = QComboBox(); mod_cb.setEditable(True)
        mod_cb.addItems(sorted(set(m.get("id","") for m in self._available_models)))
        v = str(pi_settings.get("defaultModel",""))
        if v: i=mod_cb.findText(v); mod_cb.setCurrentIndex(max(0,i))
        r = QHBoxLayout(); r.addWidget(QLabel("Default model:")); r.addWidget(mod_cb,1); bl.addLayout(r)

        # Thinking level
        tl_cb = QComboBox()
        tl_cb.addItems(["off","minimal","low","medium","high","xhigh"])
        v = str(pi_settings.get("defaultThinkingLevel","low"))
        i = tl_cb.findText(v)
        if i >= 0: tl_cb.setCurrentIndex(i)
        r = QHBoxLayout(); r.addWidget(QLabel("Default thinking level:")); r.addWidget(tl_cb); r.addStretch(); bl.addLayout(r)

        # Checkboxes
        hide_cb = QCheckBox("Hide thinking blocks")
        hide_cb.setChecked(bool(pi_settings.get("hideThinkingBlock",False)))
        bl.addWidget(hide_cb)
        quiet_cb = QCheckBox("Quiet startup (skip wake-up header)")
        quiet_cb.setChecked(bool(pi_settings.get("quietStartup",False)))
        bl.addWidget(quiet_cb)

        # Project trust
        trust_cb = QComboBox()
        trust_cb.addItems(["ask","always","never"])
        v = str(pi_settings.get("defaultProjectTrust","ask"))
        i = trust_cb.findText(v)
        if i >= 0: trust_cb.setCurrentIndex(i)
        r = QHBoxLayout(); r.addWidget(QLabel("Default project trust:")); r.addWidget(trust_cb); r.addStretch(); bl.addLayout(r)

        bl.addSpacing(12)

        # Compaction group
        cg = QGroupBox("Compaction")
        cl = QVBoxLayout(cg)
        comp = pi_settings.get("compaction",{})
        comp_en = QCheckBox("Enable auto-compaction")
        comp_en.setChecked(bool(comp.get("enabled",True)))
        cl.addWidget(comp_en)
        _, cr_spin = _sr("Reserve tokens:", int(comp.get("reserveTokens",16384)), 1024, 131072)
        cl.addLayout(_sr("Reserve tokens:", int(comp.get("reserveTokens",16384)), 1024, 131072)[0])
        _, ck_spin = _sr("Keep recent tokens:", int(comp.get("keepRecentTokens",20000)), 1024, 262144)
        cl.addLayout(_sr("Keep recent tokens:", int(comp.get("keepRecentTokens",20000)), 1024, 262144)[0])
        bl.addWidget(cg)

        # Retry group
        rg = QGroupBox("Retry")
        rl = QVBoxLayout(rg)
        ret = pi_settings.get("retry",{})
        ret_en = QCheckBox("Enable auto-retry")
        ret_en.setChecked(bool(ret.get("enabled",True)))
        rl.addWidget(ret_en)
        _, rm_spin = _sr("Max retries:", int(ret.get("maxRetries",3)), 0, 10)
        rl.addLayout(_sr("Max retries:", int(ret.get("maxRetries",3)), 0, 10)[0])
        bl.addWidget(rg)

        # ── pi Config directory ──────────────────────────────────
        cfg_group = QGroupBox("pi Config")
        cfg_layout = QVBoxLayout(cfg_group)

        _local_cfg = str(
            Path(__file__).resolve().parent.parent.parent
            / "resources" / "pi-config"
        )
        _current_cfg = self._bridge._pi_config_dir or ""
        _initial_cfg = _current_cfg

        cfg_default = QRadioButton("Default (~/.pi/agent/)")
        cfg_local = QRadioButton("Local (shipped pi-config)")
        cfg_custom = QRadioButton("Custom:")
        cfg_custom_path = QLineEdit()
        cfg_custom_path.setPlaceholderText("/path/to/pi-config")
        cfg_browse = QPushButton("Browse...")

        if not _current_cfg or _current_cfg == _local_cfg:
            cfg_default.setChecked(not _current_cfg)
            cfg_local.setChecked(_current_cfg == _local_cfg)
        else:
            cfg_custom.setChecked(True)
            cfg_custom_path.setText(_current_cfg)

        cfg_layout.addWidget(cfg_default)
        cfg_layout.addWidget(cfg_local)
        custom_row = QHBoxLayout()
        custom_row.addWidget(cfg_custom)
        custom_row.addWidget(cfg_custom_path, 1)
        custom_row.addWidget(cfg_browse)
        cfg_layout.addLayout(custom_row)

        cfg_browse.clicked.connect(
            lambda: cfg_custom_path.setText(
                QFileDialog.getExistingDirectory(self, "Select pi config directory")
                or cfg_custom_path.text()
            )
        )

        def _cfg_value() -> str:
            if cfg_default.isChecked():
                return ""
            if cfg_local.isChecked():
                return _local_cfg
            return cfg_custom_path.text().strip()

        bl.addWidget(cfg_group)

        bl.addStretch()
        tabs.addTab(bk, "pi Backend")
        tabs.setCurrentIndex(default_tab)

        # ── Buttons ───────────────────────────────────────────────
        br = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        close_btn = QPushButton("Close")
        br.addStretch(); br.addWidget(apply_btn); br.addWidget(close_btn)
        layout.addLayout(br)

        _config_changed = False
        _applied = False

        def _on_cfg_changed() -> None:
            nonlocal _config_changed
            _config_changed = (_cfg_value() != _initial_cfg)

        cfg_default.toggled.connect(_on_cfg_changed)
        cfg_local.toggled.connect(_on_cfg_changed)
        cfg_custom_path.textChanged.connect(_on_cfg_changed)

        def _apply() -> None:
            nonlocal _applied
            _applied = True

            self.chat.configure(
                page_size=pg_spin.value(),
                pages_displayed=pd_spin.value(),
                auto_collapse_agent_work=aw_spin.value(),
                auto_collapse_thinking=tk_spin.value(),
                auto_collapse_tools=tl_spin.value(),
            )
            tn = theme_cb.currentText()
            if tn == "system":
                scheme = QApplication.instance().styleHints().colorScheme()
                tn = "dark" if scheme == Qt.ColorScheme.Dark else "light"
            tc = self._THEMES.get(tn)
            if tc:
                self.chat.set_theme(tc)
            new_pi = dict(pi_settings)
            new_pi.update({
                "theme": tn,
                "defaultProvider": prov_cb.currentText(),
                "defaultModel": mod_cb.currentText(),
                "defaultThinkingLevel": tl_cb.currentText(),
                "hideThinkingBlock": hide_cb.isChecked(),
                "quietStartup": quiet_cb.isChecked(),
                "defaultProjectTrust": trust_cb.currentText(),
                "compaction": {
                    "enabled": comp_en.isChecked(),
                    "reserveTokens": cr_spin.value(),
                    "keepRecentTokens": ck_spin.value(),
                },
                "retry": {
                    "enabled": ret_en.isChecked(),
                    "maxRetries": rm_spin.value(),
                },
            })
            try:
                pi_path.write_text(json.dumps(new_pi, indent=2))
            except OSError:
                pass

            # Save config choice and restart if changed or on Backend tab
            cfg_val = _cfg_value()
            if cfg_val != _initial_cfg:
                self._bridge._pi_config_dir = cfg_val
                _s = QSettings("llm-thalamus", "llm-thalamus")
                _s.setValue("pi/config_dir", cfg_val)
                _s.sync()
            restart = tabs.currentIndex() == 1 or cfg_val != _initial_cfg
            if restart:
                self._on_reload()

        def _on_close() -> None:
            if _config_changed and not _applied:
                reply = QMessageBox.question(
                    dlg, "Apply changes?",
                    "The pi config directory has changed. Apply changes?\n"
                    "This will restart pi.",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    _apply()
            dlg.accept()

        apply_btn.clicked.connect(_apply)
        close_btn.clicked.connect(_on_close)
        dlg.exec()

    # ── slots: streaming ─────────────────────────────────────────

    def _on_stream_start(self) -> None:
        """A turn has started. Don't create the assistant bubble yet — it would
        appear empty during the thinking phase. The first ``text_delta`` in
        ``_on_stream_delta`` creates the bubble lazily."""
        pass

    def _on_stream_delta(self, text: str) -> None:
        if not self._streaming:
            self._streaming = True
            self.chat.begin_assistant_stream()
        self.chat.append_assistant_delta(text)

    def _on_stream_end(self) -> None:
        self._streaming = False
        self.chat.end_assistant_stream()

    # ── slots: thinking ──────────────────────────────────────────

    def _on_thinking_started(self) -> None:
        self.brain.set_saturation(0.7)
        self.chat.add_thinking()

    def _on_thinking_delta(self, text: str) -> None:
        self.chat.append_thinking_delta(text)

    def _on_thinking_finished(self) -> None:
        self.brain.set_saturation(1.0)
        self.chat.end_thinking()  # finalize, collapse

    # ── slots: tools ─────────────────────────────────────────────

    def _on_tool_start(self, call_id: str, name: str, args: dict) -> None:
        self.chat.upsert_tool_event(call_id, {
            "event_type": "tool_call",
            "tool_call_id": call_id,
            "tool_name": name,
            "args": args,
        })

    def _on_tool_update(self, call_id: str, partial_text: str) -> None:
        """Streaming progress from a running tool (e.g. subagent output)."""
        # Clean escaped JSON sequences so the text is readable.
        cleaned = partial_text.replace("\\n", "\n").replace("\\t", "\t").replace("\\\"", '"')
        self.chat.upsert_tool_event(call_id, {
            "event_type": "tool_update",
            "tool_call_id": call_id,
            "partial_result": cleaned,
        })

    def _on_tool_end(self, call_id: str, name: str, result_text: str, is_error: bool, details: dict = None) -> None:
        self.chat.upsert_tool_event(call_id, {
            "event_type": "tool_result",
            "tool_call_id": call_id,
            "tool_name": name,
            "result": result_text,
            "ok": not is_error,
            "details": details,
        })

    # ── slots: lifecycle ─────────────────────────────────────────

    def _on_busy(self, busy: bool) -> None:
        self._busy = busy
        self.send_button.setText("Stop" if busy else "Send")
        self.send_button.setEnabled(True)
        self.brain.set_state("llm" if busy else "thalamus")
        if not busy:
            self.follow_up_button.setEnabled(False)
            # Agent finished — refresh token / context stats.
            self._refresh_status_bar()

    def _on_input_text_changed(self) -> None:
        """Update the button label to reflect whether typing steers or aborts."""
        if self._busy:
            has_text = bool(self.chat_input.toPlainText().strip())
            self.send_button.setText("Steer" if has_text else "Stop")
            self.follow_up_button.setEnabled(has_text)

    def _on_escape(self) -> None:
        """Escape key: dismiss palette or abort the current agent operation."""
        if self._command_palette.is_visible:
            return
        if self._busy:
            self._bridge.send_command({"type": "abort"})

    def _on_error(self, text: str) -> None:
        self.chat.add_turn("system", text)
        self.brain.set_state("inactive")

    # ── slots: thinking level ─────────────────────────────────

    def _update_thinking_border(self) -> None:
        """Update the chat input border color based on current thinking level."""
        self.chat_input.set_thinking_border_color(self._thinking_level)

    def _on_cycle_thinking_level(self) -> None:
        """Cycle thinking level and refresh the UI."""
        self._bridge.send_command({"type": "cycle_thinking_level"})
        self._bridge.send_command({"type": "get_state"})

    def _on_thinking_level_menu(self) -> None:
        """Show a QMenu with available thinking levels."""
        levels = ["off", "minimal", "low", "medium", "high", "xhigh"]
        menu = QMenu(self)
        for level in levels:
            action = menu.addAction(level)
            action.setCheckable(True)
            if level == self._thinking_level:
                action.setChecked(True)
        chosen = menu.exec(self._thinking_label.mapToGlobal(
            self._thinking_label.rect().bottomLeft()))
        if chosen is not None:
            self._thinking_level = chosen.text()
            self._update_thinking_border()
            self._bridge.send_command({
                "type": "set_thinking_level",
                "level": chosen.text(),
            })

    # ── slots: session management ──────────────────────────────

    def _on_open_session_dialog(self) -> None:
        """Create (or show) the non‑modal session manager dialog."""
        if self._session_dialog is None:
            dlg = SessionDialog(self)
            dlg.new_requested.connect(self._on_new_session)
            dlg.reload_requested.connect(self._on_reload)
            dlg.compact_requested.connect(self._on_compact)
            dlg.import_requested.connect(self._on_import_session)
            dlg.session_info_requested.connect(self._on_session_info)
            dlg.switch_requested.connect(self._on_switch_session)
            dlg.rename_requested.connect(self._on_rename_session)
            dlg.delete_requested.connect(self._on_delete_session)
            dlg.inspect_requested.connect(self._on_inspect_session)
            self._session_dialog = dlg

        dlg = self._session_dialog
        # Refresh the tree with latest data.
        dlg.refresh_sessions(
            str(self._session_dir()) if self._session_dir() else None,
            self._current_session_path,
        )
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_import_session(self) -> None:
        """Open a file dialog and switch to the selected .jsonl session."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Session",
            str(Path.home() / ".pi" / "agent" / "sessions"),
            "Session files (*.jsonl)",
        )
        if not path:
            return
        self._bridge.send_command({
            "type": "switch_session",
            "sessionPath": path,
        })

    def _on_session_info(self) -> None:
        """Show current session info in a message box."""
        # Request latest state + stats and show once both arrive.
        self._bridge.send_command({"type": "get_state"})
        self._bridge.send_command({"type": "get_session_stats"})

        # We'll accumulate the results and show them via a helper.
        self._pending_session_info: dict[str, object] = {}

        def _on_info_get_state(data: dict) -> None:
            self._pending_session_info["sessionFile"] = data.get("sessionFile", "?")
            self._pending_session_info["sessionId"] = data.get("sessionId", "?")
            self._pending_session_info["sessionName"] = data.get("sessionName") or "(unnamed)"
            self._pending_session_info["messageCount"] = data.get("messageCount", "?")
            model = data.get("model")
            if isinstance(model, dict):
                self._pending_session_info["model"] = f"{model.get('provider','?')}/{model.get('name',model.get('id','?'))}"
            self._pending_session_info["thinkingLevel"] = data.get("thinkingLevel", "-")
            self._pending_session_info["cwd"] = str(Path.cwd())
            self._maybe_show_session_info()

        def _on_info_stats(data: dict) -> None:
            tokens = data.get("tokens", {})
            if isinstance(tokens, dict):
                parts: list[str] = []
                for label, key in [("Input", "input"), ("Output", "output"),
                                    ("Cache Read", "cacheRead"), ("Cache Write", "cacheWrite")]:
                    v = int(tokens.get(key, 0) or 0)
                    if v:
                        parts.append(f"{label}: {_fmt_tokens(v)}")
                self._pending_session_info["tokens"] = ", ".join(parts) if parts else "none"
            cost = data.get("cost", 0)
            if cost:
                self._pending_session_info["cost"] = f"${float(cost):.4f}"
            ctx = data.get("contextUsage", {})
            if isinstance(ctx, dict):
                pct = ctx.get("percent")
                if pct is not None:
                    self._pending_session_info["context"] = f"{float(pct):.0f}% ({ctx.get('tokens','?')}/{ctx.get('contextWindow','?')})"
            self._pending_session_info["userMessages"] = data.get("userMessages", "?")
            self._maybe_show_session_info()

        # Store the callbacks on the instance so the response handler can find them.
        self._on_info_get_state = _on_info_get_state
        self._on_info_stats = _on_info_stats

    def _maybe_show_session_info(self) -> None:
        """Show the session info dialog if both state and stats have arrived."""
        info = self._pending_session_info
        # Both get_state and get_session_stats provide at least some fragment.
        if "sessionFile" in info and "tokens" in info:
            msg_parts: list[str] = []
            for label, key in [
                ("Session file", "sessionFile"),
                ("Session ID", "sessionId"),
                ("Session name", "sessionName"),
                ("Working directory", "cwd"),
                ("Messages", "messageCount"),
                ("Model", "model"),
                ("Thinking level", "thinkingLevel"),
                ("Token usage", "tokens"),
            ]:
                v = info.get(key)
                if v is not None:
                    msg_parts.append(f"{label}: {v}")
            if "cost" in info:
                msg_parts.append(f"Cost: {info['cost']}")
            if "context" in info:
                msg_parts.append(f"Context: {info['context']}")

            QMessageBox.information(
                self,
                f"Session: {info.get('sessionName', '?')}",
                "\n".join(msg_parts),
            )
            # Clean up.
            self._pending_session_info = {}

    def _on_new_session(self) -> None:
        """Ask the user where to start a fresh session.

        Pops up a native directory picker.  If a directory different from
        the current CWD is chosen, pi is restarted from that location because
        pi's CWD is fixed at process launch.
        """
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select working directory for new session",
            str(Path.cwd()),
        )
        if not dir_path:
            return  # user cancelled

        target = Path(dir_path).resolve()
        if target == Path.cwd().resolve():
            # Same directory — just start a new session via RPC.
            self._bridge.send_command({"type": "new_session"})
        else:
            # Different directory — restart pi from the new CWD.
            self._bridge.restart(cwd=str(target))
            self.chat.clear()
            self._current_session_path = None
            self._refresh_session_list()
            QTimer.singleShot(1200, self._refresh_status_bar)
            # Give pi a moment to start, then request a fresh session.
            QTimer.singleShot(1800, lambda: self._bridge.send_command({"type": "new_session"}))

    # More shortcuts handled natively by widgets (added to help below).
    _HELP_SHORTCUTS: dict[str, str] = {
        "Enter":         "Send message",
        "Shift+Enter":   "New line in input",
        "Alt+Enter":     "Queue follow-up message",
        "Ctrl+Scroll":   "Zoom chat",
        "Up/Down":       "Navigate command palette",
        "Tab":           "Execute selected command",
    }

    def _on_show_hotkeys(self) -> None:
        """Show a dialog listing all keyboard shortcuts."""
        all_keys = {
            **self._shortcut_descriptions,
            **self._HELP_SHORTCUTS,
        }
        lines = ["Keyboard shortcuts:", ""]
        width = max(len(k) for k in all_keys)
        for key, desc in all_keys.items():
            lines.append(f"{key:<{width}}  {desc}")
        QMessageBox.information(self, "Keyboard Shortcuts", "\n".join(lines))

    def _on_copy_last(self) -> None:
        """Copy the last assistant message to clipboard."""
        for msg in reversed(self.chat._messages):
            if msg.get("kind") == "turn" and msg.get("role") == "you":
                text = msg.get("content", "")
                if text:
                    QApplication.clipboard().setText(text)
                break

    def _on_compact(self) -> None:
        """Send the compact RPC to compress context."""
        self._bridge.send_command({"type": "compact"})

    def _on_reload(self) -> None:
        """Restart the pi subprocess to pick up new extensions, skills,
        and configuration, then resume the current session."""
        self._bridge.restart(
            cwd=str(Path.cwd()),
            session_path=self._current_session_path,
        )
        self.chat.clear()
        self._refresh_session_list()
        # Give pi time to start up and load the session, then fetch
        # history + state.
        QTimer.singleShot(1500, self._bridge.load_history)
        QTimer.singleShot(2000, self._refresh_status_bar)

    def _on_switch_session(self, session_path: str) -> None:
        """Switch to a different session and reload conversation."""
        self._bridge.send_command({
            "type": "switch_session",
            "sessionPath": session_path,
        })

    def _on_inspect_session(self, session_path: str) -> None:
        """Open a read-only dialog showing the session's messages."""
        from ui.chat_renderer import ChatRenderer

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Inspect: {Path(session_path).stem[:40]}")
        dlg.resize(650, 500)
        layout = QVBoxLayout(dlg)

        viewer = ChatRenderer()

        # Stacked widget: index 0 = native placeholder (instant), index 1 = viewer.
        # Switch to the viewer once the WebEngine-heavy render completes.
        from PySide6.QtWidgets import QStackedWidget
        stack = QStackedWidget()

        placeholder = QLabel("Rendering session…")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet(
            "color: #888; font-size: 14pt;"
            "background: transparent;"
        )
        stack.addWidget(placeholder)  # index 0
        stack.addWidget(viewer)        # index 1
        stack.setCurrentIndex(0)
        layout.addWidget(stack, 1)

        btn_row = QHBoxLayout()
        switch_btn = QPushButton("Switch to this session")
        switch_btn.clicked.connect(lambda: (
            self._on_switch_session(session_path),
            dlg.accept(),
        ))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addStretch()
        btn_row.addWidget(switch_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        # Show the dialog immediately (placeholder QLabel is native Qt, renders
        # instantly), then populate asynchronously so the WebEngine-heavy
        # rendering doesn't block the UI.
        dlg.show()
        QTimer.singleShot(
            0, lambda: self._populate_inspect(viewer, session_path, dlg, stack)
        )
        dlg.exec()

    def _populate_inspect(
        self,
        viewer: "ChatRenderer",
        session_path: str,
        dlg: QDialog,
        stack: "QStackedWidget | None" = None,
    ) -> None:
        """Parse and render a session file into an already-visible dialog."""
        try:
            viewer.begin_batch()
            with open(session_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = entry.get("message", {}) if isinstance(entry, dict) else None
                    if not isinstance(msg, dict):
                        continue
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        parts = []
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "text":
                                parts.append(b.get("text", ""))
                        text = " ".join(parts)
                    else:
                        text = str(content) if content else ""
                    if not text:
                        continue
                    display_role = "human" if role == "user" else "you"
                    viewer.add_turn(display_role, text)
            viewer.end_batch()
            if stack is not None:
                stack.setCurrentIndex(1)
        except (OSError, UnicodeDecodeError) as e:
            QMessageBox.warning(dlg, "Error", f"Failed to read session:\n{e}")

    def _on_command_requested(self, name: str, remaining: str) -> None:
        """Handle a slash command that needs UI interaction.

        Currently supports:
          - /name  → opens the rename dialog
          - /compact → compact context RPC
          - /new   → opens directory picker (same as Session → New)
          - /export → calls export_html RPC directly
        """
        if name == "name":
            session_path = self._current_session_path
            if session_path:
                current_name = remaining if remaining else ""
                new_name, ok = QInputDialog.getText(
                    self, "Set Session Name", "New name:",
                    text=current_name,
                )
                if ok and new_name:
                    self._bridge.send_command({
                        "type": "set_session_name",
                        "name": new_name,
                    })
        elif name in ("model", "scoped-models"):
            self._on_open_model_picker()
        elif name == "session":
            self._on_session_info()
        elif name in ("resume", "tree", "import"):
            self._on_open_session_dialog()
        elif name == "settings":
            self._on_settings_dialog(1)
        elif name == "quit":
            self.close()
        elif name == "hotkeys":
            self._on_show_hotkeys()
        elif name == "copy":
            self._on_copy_last()
        elif name == "reload":
            self._on_reload()
        elif name == "compact":
            self._on_compact()
        elif name == "new":
            self._on_new_session()
        elif name == "export":
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Session",
                str(Path.home() / "session.html"),
                "HTML files (*.html);;All files (*)",
            )
            if path:
                self._bridge.send_command({
                    "type": "export_html",
                    "outputPath": path,
                })
            else:
                # No path — pi uses a default location.
                self._bridge.send_command({"type": "export_html"})

    def _on_rename_session(self, session_path: str, new_name: str) -> None:
        """Set the display name for a session."""
        if session_path == self._current_session_path:
            self._bridge.send_command({
                "type": "set_session_name",
                "name": new_name,
            })
        else:
            # Switch first, then rename on the response handler.
            self._pending_rename = new_name
            self._bridge.send_command({
                "type": "switch_session",
                "sessionPath": session_path,
            })

    def _on_delete_session(self, paths: list[str]) -> None:
        """Delete one or more session files from disk."""
        failed: list[str] = []
        for session_path in paths:
            try:
                p = Path(session_path)
                if p.exists():
                    p.unlink()
            except OSError as e:
                failed.append(f"{Path(session_path).name}: {e}")
        self._refresh_session_list()
        if failed:
            QMessageBox.warning(
                self, "Error",
                f"Failed to delete {len(failed)} session(s):\n"
                + "\n".join(failed[:5])
            )

    def _on_session_switched(self) -> None:
        """Called after new_session or switch_session succeeds.

        Clears the chat, reloads history, and refreshes the
        session list.
        """
        self.chat.clear()
        self._bridge.load_history()
        self._refresh_session_list()
        self._refresh_status_bar()

        # If a rename was queued before the switch, send it now.
        if self._pending_rename:
            self._bridge.send_command({
                "type": "set_session_name",
                "name": self._pending_rename,
            })
            self._pending_rename = None

    def _session_dir(self) -> Path | None:
        """Resolve the pi session storage directory.

        Returns None if we can't determine the location.
        """
        if self._session_dir_path is not None:
            return self._session_dir_path
        cfg = self._bridge._pi_config_dir
        if cfg:
            self._session_dir_path = Path(cfg) / "sessions"
        else:
            self._session_dir_path = Path.home() / ".pi" / "agent" / "sessions"
        if not self._session_dir_path.is_dir():
            self._session_dir_path = None
        return self._session_dir_path

    def _refresh_session_list(self) -> None:
        """Re-scan the session directory and update the session dialog tree.

        Only refreshes if the dialog is currently visible.
        """
        dlg = self._session_dialog
        if dlg is not None and dlg.isVisible():
            dlg.refresh_sessions(
                str(self._session_dir()) if self._session_dir() else None,
                self._current_session_path,
            )

    # ── slots: model picker ──────────────────────────────────

    def _on_open_model_picker(self) -> None:
        """Open the model picker dialog and send ``set_model`` on accept."""
        if not self._available_models:
            # Models not loaded yet — request and defer.
            self._bridge.send_command({"type": "get_available_models"})
            QMessageBox.information(
                self,
                "Model Picker",
                "Model list is being loaded.  Please try again in a moment.",
            )
            return

        scoped_raw = self._settings.value("model/scoped_ids")
        scoped_ids: set[str] = (
            set(json.loads(scoped_raw))
            if isinstance(scoped_raw, str)
            else set()
        )

        dlg = ModelPickerDialog(self._available_models, scoped_ids, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.selected_model_id and dlg.selected_provider:
                self._bridge.send_command({
                    "type": "set_model",
                    "provider": dlg.selected_provider,
                    "modelId": dlg.selected_model_id,
                })
            self._settings.setValue(
                "model/scoped_ids",
                json.dumps(sorted(dlg.scoped_ids)),
            )
            self._settings.sync()

    # ── slots: session management ──────────────────────────────

    def _on_get_state(self, data: dict) -> None:
        """Handle ``get_state`` response — update model and session info."""
        # Update current session path.
        session_file = data.get("sessionFile")
        if session_file:
            self._current_session_path = str(session_file)
            dlg = self._session_dialog
            if dlg is not None and dlg.isVisible():
                dlg.set_current_session(self._current_session_path)

        # Update model label.
        model = data.get("model")
        if isinstance(model, dict):
            self._provider = str(model.get("provider", ""))
            thinking_level = str(data.get("thinkingLevel", ""))
            self._thinking_level = thinking_level
            self._update_thinking_border()
            model_name = model.get("name") or model.get("id") or "?"
            parts: list[str] = []
            if self._provider:
                parts.append(f"({self._provider})")
            parts.append(model_name)
            self._model_label.setText(" ".join(parts))
            self._thinking_label.setText(thinking_level if thinking_level else "-")

    def _on_history_turn(self, role: str, content: str, _ts: str) -> None:
        # Map pi roles to chat renderer roles.
        # pi roles: "user", "assistant", "toolResult", "bashExecution"
        display_role = "human" if role == "user" else "you"
        self.chat.begin_batch()
        self.chat.add_turn(display_role, content)
        if not self._history_batch_pending:
            self._history_batch_pending = True
            QTimer.singleShot(0, self._flush_history_batch)

    def _on_history_thinking(self, text: str, _ts: str) -> None:
        # History thinking bubbles start collapsed.
        self.chat.begin_batch()
        self.chat.add_thinking(text)
        if not self._history_batch_pending:
            self._history_batch_pending = True
            QTimer.singleShot(0, self._flush_history_batch)

    def _flush_history_batch(self) -> None:
        """Render all accumulated history messages in one shot."""
        self._history_batch_pending = False
        self.chat.end_batch()

    # ── slots: extension UI ───────────────────────────────────────

    def _on_extension_ui_dialog(
        self, request_id: str, method: str, title: str, data: dict
    ) -> None:
        """Show a Qt dialog for a pi ``extension_ui_request`` and send the
        response back through the bridge."""
        response: dict

        if method == "confirm":
            message = str(data.get("message", ""))
            reply = QMessageBox.question(
                self, title, message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            response = {"confirmed": reply == QMessageBox.StandardButton.Yes}

        elif method == "select":
            options_raw = data.get("options", [])
            options = (
                [str(o) for o in options_raw]
                if isinstance(options_raw, list) else []
            )
            item, ok = QInputDialog.getItem(
                self, title, "Choose:", options, 0, False,
            )
            if ok:
                response = {"value": item}
            else:
                response = {"cancelled": True}

        elif method == "input":
            placeholder = str(data.get("placeholder", ""))
            text, ok = QInputDialog.getText(self, title, placeholder)
            if ok:
                response = {"value": text}
            else:
                response = {"cancelled": True}

        elif method == "editor":
            prefill = str(data.get("prefill", ""))
            dlg = QDialog(self)
            dlg.setWindowTitle(title)
            dlg.resize(500, 400)
            layout = QVBoxLayout(dlg)
            editor = QTextEdit()
            editor.setPlainText(prefill)
            layout.addWidget(editor)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok
                | QDialogButtonBox.StandardButton.Cancel,
            )
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            layout.addWidget(buttons)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                response = {"value": editor.toPlainText()}
            else:
                response = {"cancelled": True}

        else:
            return  # unknown method, don't respond

        self._bridge.send_extension_ui_response(request_id, response)

    def _on_extension_ui_notify(self, message: str, notify_type: str) -> None:
        # Log to stderr for now; future: status bar or toast.
        print(
            f"[notify] [{notify_type}] {message}",
            flush=True,
        )

    def _on_extension_ui_status(self, key: str, text: str) -> None:
        """Handle a setStatus extension_ui_request.

        When *text* is non-empty, store/update the entry for *key*.
        When *text* is empty, remove the entry (status was cleared).
        """
        if text:
            self._status_entries[key] = text
        else:
            self._status_entries.pop(key, None)
        self._update_status_extras()

    def _update_status_extras(self) -> None:
        """Rebuild the status extras label from current entries.

        Shows all non-empty status lines joined with spaces on a second
        row of the status bar.  Hidden when there are no entries.
        """
        parts = [v for v in self._status_entries.values() if v]
        if not parts:
            self._status_extras_label.setVisible(False)
            return
        self._status_extras_label.setText("    ".join(parts))
        self._status_extras_label.setVisible(True)

    # ── slots: status bar ────────────────────────────────────────

    def _on_response_received(self, command: str, response: object) -> None:
        """Route RPC responses to the appropriate handler."""
        if not isinstance(response, dict):
            return
        if not response.get("success"):
            return
        data = response.get("data")
        if not isinstance(data, dict):
            return

        if command == "get_state":
            if hasattr(self, "_on_info_get_state"):
                self._on_info_get_state(data)
                del self._on_info_get_state
                return  # Don't double-handle
            self._on_get_state(data)
        elif command == "get_available_models":
            models = data.get("models", [])
            if isinstance(models, list):
                self._available_models = models
        elif command == "set_model":
            self._refresh_status_bar()
        elif command == "cycle_model":
            self._refresh_status_bar()
        elif command == "get_commands":
            cmds = data.get("commands", [])
            if isinstance(cmds, list):
                self._command_palette.set_dynamic_commands(cmds)
        elif command == "new_session":
            cancelled = data.get("cancelled", False)
            if not cancelled:
                self._on_session_switched()
        elif command == "switch_session":
            cancelled = data.get("cancelled", False)
            if not cancelled:
                self._on_session_switched()
        elif command == "set_session_name":
            self._refresh_session_list()
        elif command == "clone":
            cancelled = data.get("cancelled", False)
            if not cancelled:
                self._on_session_switched()
        elif command == "get_session_stats":
            if hasattr(self, "_on_info_stats"):
                self._on_info_stats(data)
                del self._on_info_stats
                return
            tokens = data.get("tokens")
            if isinstance(tokens, dict):
                inp = int(tokens.get("input", 0) or 0)
                out = int(tokens.get("output", 0) or 0)
                cache = int(tokens.get("cacheRead", 0) or 0)
                parts: list[str] = []
                if inp:
                    parts.append(f"↑{_fmt_tokens(inp)}")
                if out:
                    parts.append(f"↓{_fmt_tokens(out)}")
                if cache:
                    parts.append(f"R{_fmt_tokens(cache)}")
                if parts:
                    self._tokens_label.setText(" ".join(parts))
                else:
                    self._tokens_label.setText("\u00a0")
            ctx = data.get("contextUsage")
            if isinstance(ctx, dict) and ctx.get("contextWindow"):
                pct = ctx.get("percent")
                if pct is not None:
                    self._context_label.setText(f"{float(pct):.0f}%")
                else:
                    self._context_label.setText("\u00a0")
            else:
                self._context_label.setText("\u00a0")

    def _refresh_status_bar(self) -> None:
        """Request fresh state and stats from pi; update local info."""
        self._update_path_label()
        self._refresh_session_list()
        self._bridge.send_command({"type": "get_state"})
        self._bridge.send_command({"type": "get_session_stats"})
        self._bridge.send_command({"type": "get_commands"})
        self._bridge.send_command({"type": "get_available_models"})

    def _update_path_label(self) -> None:
        """Update the path label with shortened cwd and optional git branch."""
        cwd = Path.cwd()
        home = Path.home()
        try:
            short = f"~/{cwd.relative_to(home)}" if cwd.is_relative_to(home) else str(cwd)
        except ValueError:
            short = str(cwd)
        branch = _git_branch(cwd)
        if branch:
            self._path_label.setText(f"{short} ({branch})")
        else:
            self._path_label.setText(short)


# ── helpers ──────────────────────────────────────────────────────────


def _git_branch(cwd: Path) -> str:
    """Return the current git branch name, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=2,
        )
        branch = result.stdout.strip()
        if result.returncode == 0 and branch and branch != "HEAD":
            return branch
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return ""


def _fmt_tokens(count: int) -> str:
    """Format a token count with k / M suffix."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count // 1_000}k"
    return str(count)
