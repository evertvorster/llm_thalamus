"""SettingsDialog — unified settings dialog (Display + pi Backend + STT)."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from controller.stt import available_backends, get_backend, SttBackend
from ui.chat_renderer import ChatRenderer
from ui.theme import THEMES

# ── STT language codes (Whisper-supported subset) ─────────────────

_STT_LANGUAGES: list[tuple[str, str]] = [
    ("auto", "Auto-detect"),
    ("af", "Afrikaans"),
    ("ar", "Arabic"),
    ("de", "German"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("it", "Italian"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("nl", "Dutch"),
    ("pl", "Polish"),
    ("pt", "Portuguese"),
    ("ru", "Russian"),
    ("sw", "Swahili"),
    ("tl", "Tagalog"),
    ("xh", "Xhosa"),
    ("zh", "Chinese"),
    ("zu", "Zulu"),
]

# ── Model capability descriptions ─────────────────────────────────

_STT_MODEL_INFO: dict[str, tuple[str, str]] = {
    "tiny":         ("~150 MB", "English only, low accuracy"),
    "tiny.en":      ("~150 MB", "English only"),
    "base":         ("~300 MB", "Good English, poor multi-language"),
    "base.en":      ("~300 MB", "English only, faster"),
    "small":        ("~1.5 GB", "Good multi-language"),
    "small.en":     ("~1.5 GB", "English only, good accuracy"),
    "medium":       ("~3 GB", "Very good multi-language"),
    "medium.en":    ("~3 GB", "English only, high accuracy"),
    "large":        ("~6 GB", "Best multi-language"),
    "large-v1":     ("~6 GB", "Best multi-language"),
    "large-v2":     ("~6 GB", "Best multi-language"),
    "large-v3":     ("~6 GB", "Best multi-language (recommended)"),
    "large-v3-turbo": ("~3 GB", "Best multi-language, faster"),
    "turbo":        ("~3 GB", "Best multi-language, faster"),
    "distil-large-v2":  ("~3 GB", "Good multi-language, fast"),
    "distil-large-v3":  ("~3 GB", "Good multi-language, fast"),
    "distil-large-v3.5":("~3 GB", "Good multi-language, fast"),
}


# ── Spin-row builder ──────────────────────────────────────────────


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


# ═══════════════════════════════════════════════════════════════════
#  SettingsDialog
# ═══════════════════════════════════════════════════════════════════


class SettingsDialog(QDialog):
    """Unified settings dialog with Display, pi Backend, and STT tabs.

    Signals:
        restart_requested:  Emitted when pi needs to restart (config dir
                            changed or Backend tab was active).
    """

    restart_requested = Signal()

    def __init__(
        self,
        chat: ChatRenderer,
        available_models: list[dict],
        bridge_config_dir: str,
        stt_backend: SttBackend | None,
        default_tab: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(540, 420)
        self.setModal(True)

        self._chat = chat
        self._available_models = available_models
        self._stt_backend = stt_backend
        self._settings = QSettings("llm-thalamus", "llm-thalamus")
        self._pi_settings_path = Path.home() / ".pi" / "agent" / "settings.json"
        self._initial_cfg_dir = bridge_config_dir or ""

        self._build_ui(default_tab)

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self, default_tab: int) -> None:
        layout = QVBoxLayout(self)
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        self._build_display_tab()
        self._build_backend_tab()
        self._build_stt_tab()
        self._tabs.setCurrentIndex(default_tab)

        # ── Buttons ─────────────────────────────────────────────
        br = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        apply_btn = QPushButton("Close && Apply")
        apply_btn.clicked.connect(self._on_close)
        br.addStretch()
        br.addWidget(cancel_btn)
        br.addWidget(apply_btn)
        layout.addLayout(br)

    # ── Tab 1: Display ──────────────────────────────────────────

    def _build_display_tab(self) -> None:
        pi_settings = self._read_pi_settings()

        disp = QWidget()
        dl = QVBoxLayout(disp)
        dl.setSpacing(8)

        # Theme
        self._theme_cb = QComboBox()
        self._theme_cb.addItems(["dark", "light", "system"])
        t = str(pi_settings.get("theme", "dark"))
        i = self._theme_cb.findText(t)
        if i >= 0:
            self._theme_cb.setCurrentIndex(i)
        r = QHBoxLayout()
        r.addWidget(QLabel("Theme:"))
        r.addWidget(self._theme_cb)
        r.addStretch()
        dl.addLayout(r)

        aw_l, self._aw_spin = _sr(
            "Auto-collapse agent work (keep N):",
            self._chat._auto_collapse_agent_work, -1, 20,
        )
        dl.addLayout(aw_l)
        tk_l, self._tk_spin = _sr(
            "Auto-collapse thinking (keep N):",
            self._chat._auto_collapse_thinking, -1, 20,
        )
        dl.addLayout(tk_l)
        tl_l, self._tl_spin = _sr(
            "Auto-collapse tools (keep N):",
            self._chat._auto_collapse_tools, -1, 20,
        )
        dl.addLayout(tl_l)
        dl.addSpacing(8)
        pg_l, self._pg_spin = _sr(
            "Messages per page:", self._chat._page_size, 1, 100,
        )
        dl.addLayout(pg_l)
        pd_l, self._pd_spin = _sr(
            "Pages displayed:", self._chat._pages_displayed, 1, 10,
        )
        dl.addLayout(pd_l)

        dl.addStretch()
        self._tabs.addTab(disp, "Display")

    # ── Tab 2: pi Backend ───────────────────────────────────────

    def _build_backend_tab(self) -> None:
        pi_settings = self._read_pi_settings()

        bk = QWidget()
        bl = QVBoxLayout(bk)
        bl.setSpacing(8)

        # Provider
        self._prov_cb = QComboBox()
        self._prov_cb.setEditable(True)
        self._prov_cb.addItems(
            sorted(set(m.get("provider", "") for m in self._available_models))
        )
        v = str(pi_settings.get("defaultProvider", ""))
        if v:
            i = self._prov_cb.findText(v)
            self._prov_cb.setCurrentIndex(max(0, i))
        r = QHBoxLayout()
        r.addWidget(QLabel("Default provider:"))
        r.addWidget(self._prov_cb, 1)
        bl.addLayout(r)

        # Model
        self._mod_cb = QComboBox()
        self._mod_cb.setEditable(True)
        self._mod_cb.addItems(
            sorted(set(m.get("id", "") for m in self._available_models))
        )
        v = str(pi_settings.get("defaultModel", ""))
        if v:
            i = self._mod_cb.findText(v)
            self._mod_cb.setCurrentIndex(max(0, i))
        r = QHBoxLayout()
        r.addWidget(QLabel("Default model:"))
        r.addWidget(self._mod_cb, 1)
        bl.addLayout(r)

        # Thinking level
        self._tl_cb = QComboBox()
        self._tl_cb.addItems(["off", "minimal", "low", "medium", "high", "xhigh"])
        v = str(pi_settings.get("defaultThinkingLevel", "low"))
        i = self._tl_cb.findText(v)
        if i >= 0:
            self._tl_cb.setCurrentIndex(i)
        r = QHBoxLayout()
        r.addWidget(QLabel("Default thinking level:"))
        r.addWidget(self._tl_cb)
        r.addStretch()
        bl.addLayout(r)

        # Checkboxes
        self._hide_cb = QCheckBox("Hide thinking blocks")
        cur = int(self._settings.value("display/show_thinking", 1) or 1)
        self._hide_cb.setChecked(cur != 1)
        bl.addWidget(self._hide_cb)

        self._quiet_cb = QCheckBox("Quiet startup (skip wake-up header)")
        self._quiet_cb.setChecked(bool(pi_settings.get("quietStartup", False)))
        bl.addWidget(self._quiet_cb)

        # Project trust
        self._trust_cb = QComboBox()
        self._trust_cb.addItems(["ask", "always", "never"])
        v = str(pi_settings.get("defaultProjectTrust", "ask"))
        i = self._trust_cb.findText(v)
        if i >= 0:
            self._trust_cb.setCurrentIndex(i)
        r = QHBoxLayout()
        r.addWidget(QLabel("Default project trust:"))
        r.addWidget(self._trust_cb)
        r.addStretch()
        bl.addLayout(r)

        bl.addSpacing(12)

        # Compaction group
        cg = QGroupBox("Compaction")
        cl = QVBoxLayout(cg)
        comp = pi_settings.get("compaction", {})
        self._comp_en = QCheckBox("Enable auto-compaction")
        self._comp_en.setChecked(bool(comp.get("enabled", True)))
        cl.addWidget(self._comp_en)
        cr_l, self._cr_spin = _sr(
            "Reserve tokens:", int(comp.get("reserveTokens", 16384)), 1024, 131072,
        )
        cl.addLayout(cr_l)
        ck_l, self._ck_spin = _sr(
            "Keep recent tokens:", int(comp.get("keepRecentTokens", 20000)), 1024, 262144,
        )
        cl.addLayout(ck_l)
        bl.addWidget(cg)

        # Retry group
        rg = QGroupBox("Retry")
        rl = QVBoxLayout(rg)
        ret = pi_settings.get("retry", {})
        self._ret_en = QCheckBox("Enable auto-retry")
        self._ret_en.setChecked(bool(ret.get("enabled", True)))
        rl.addWidget(self._ret_en)
        rm_l, self._rm_spin = _sr(
            "Max retries:", int(ret.get("maxRetries", 3)), 0, 10,
        )
        rl.addLayout(rm_l)
        bl.addWidget(rg)

        # ── pi Config directory ────────────────────────────────
        cfg_group = QGroupBox("pi Config")
        cfg_layout = QVBoxLayout(cfg_group)

        local_cfg = str(
            Path(__file__).resolve().parent.parent.parent
            / "resources" / "pi-config"
        )

        self._cfg_default = QRadioButton("Default (~/.pi/agent/)")
        self._cfg_local = QRadioButton("Local (shipped pi-config)")
        self._cfg_custom = QRadioButton("Custom:")
        self._cfg_custom_path = QLineEdit()
        self._cfg_custom_path.setPlaceholderText("/path/to/pi-config")
        cfg_browse = QPushButton("Browse...")

        if not self._initial_cfg_dir or self._initial_cfg_dir == local_cfg:
            self._cfg_default.setChecked(not self._initial_cfg_dir)
            self._cfg_local.setChecked(self._initial_cfg_dir == local_cfg)
        else:
            self._cfg_custom.setChecked(True)
            self._cfg_custom_path.setText(self._initial_cfg_dir)

        cfg_layout.addWidget(self._cfg_default)
        cfg_layout.addWidget(self._cfg_local)
        custom_row = QHBoxLayout()
        custom_row.addWidget(self._cfg_custom)
        custom_row.addWidget(self._cfg_custom_path, 1)
        custom_row.addWidget(cfg_browse)
        cfg_layout.addLayout(custom_row)

        cfg_browse.clicked.connect(
            lambda: self._cfg_custom_path.setText(
                QFileDialog.getExistingDirectory(self, "Select pi config directory")
                or self._cfg_custom_path.text()
            )
        )

        self._cfg_default.toggled.connect(self._on_cfg_changed)
        self._cfg_local.toggled.connect(self._on_cfg_changed)
        self._cfg_custom_path.textChanged.connect(self._on_cfg_changed)

        bl.addWidget(cfg_group)
        bl.addStretch()
        self._tabs.addTab(bk, "pi Backend")

    # ── Tab 3: Speech-to-Text ───────────────────────────────────

    def _build_stt_tab(self) -> None:
        stt_w = QWidget()
        stt_layout = QVBoxLayout(stt_w)
        stt_layout.setSpacing(8)

        backend = self._stt_backend
        available = backend is not None

        status_label = QLabel()
        if available:
            status_label.setText(
                f"Backend: {backend.name} (\u2713 available)"
            )
            status_label.setStyleSheet("color: #4caf50;")
        else:
            status_label.setText(
                "STT backend: not installed. "
                "Install python-faster-whisper to enable speech-to-text."
            )
            status_label.setStyleSheet("color: #f44336;")
            status_label.setWordWrap(True)
        stt_layout.addWidget(status_label)

        if not available:
            stt_layout.addStretch()
            self._tabs.addTab(stt_w, "Speech-to-Text")
            return

        # ── Model row ──────────────────────────────────────────
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))

        self._stt_model_cb = QComboBox()
        self._stt_model_cb.addItems(backend.available_models())
        saved_model = self._settings.value("stt/model", "base")
        idx = self._stt_model_cb.findText(str(saved_model))
        if idx >= 0:
            self._stt_model_cb.setCurrentIndex(idx)
        model_row.addWidget(self._stt_model_cb, 1)

        stt_download_btn = QPushButton("Download")
        stt_delete_btn = QPushButton("Delete")
        stt_delete_btn.setEnabled(False)
        model_row.addWidget(stt_download_btn)
        model_row.addWidget(stt_delete_btn)
        stt_layout.addLayout(model_row)

        # ── Cache info ─────────────────────────────────────────
        cache_group = QGroupBox("Model Cache")
        cache_layout = QVBoxLayout(cache_group)

        self._stt_cache_loc = QLabel()
        self._stt_cache_size = QLabel()
        self._stt_models_table = QLabel()
        self._stt_models_table.setWordWrap(True)
        self._stt_models_table.setTextFormat(Qt.PlainText)

        cache_layout.addWidget(self._stt_cache_loc)
        cache_layout.addWidget(self._stt_cache_size)
        cache_layout.addWidget(self._stt_models_table)
        stt_layout.addWidget(cache_group)

        # ── Recording mode ─────────────────────────────────────
        rec_row = QHBoxLayout()
        rec_row.addWidget(QLabel("Recording mode:"))
        self._stt_rec_cb = QComboBox()
        self._stt_rec_cb.addItems(["Push-to-talk", "Dialog"])
        saved_mode = self._settings.value("stt/recording_mode", "Push-to-talk")
        idx2 = self._stt_rec_cb.findText(str(saved_mode))
        if idx2 >= 0:
            self._stt_rec_cb.setCurrentIndex(idx2)
        rec_row.addWidget(self._stt_rec_cb)
        rec_row.addStretch()
        stt_layout.addLayout(rec_row)

        # ── Voice mode ─────────────────────────────────────
        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("Voice mode:"))
        self._stt_voice_cb = QComboBox()
        self._stt_voice_cb.addItems(["STT", "Direct"])
        saved_voice = self._settings.value("stt/voice_mode", "stt")
        iv = self._stt_voice_cb.findText(str(saved_voice).capitalize())
        if iv >= 0:
            self._stt_voice_cb.setCurrentIndex(iv)
        voice_row.addWidget(self._stt_voice_cb)
        voice_row.addStretch()
        stt_layout.addLayout(voice_row)

        # ── Task ───────────────────────────────────────────────
        task_row = QHBoxLayout()
        task_row.addWidget(QLabel("Task:"))
        self._stt_task_cb = QComboBox()
        self._stt_task_cb.addItems(["Transcribe", "Translate to English"])
        saved_task = self._settings.value("stt/task", "Transcribe")
        i3 = self._stt_task_cb.findText(str(saved_task))
        if i3 >= 0:
            self._stt_task_cb.setCurrentIndex(i3)
        task_row.addWidget(self._stt_task_cb)
        task_row.addStretch()
        stt_layout.addLayout(task_row)

        # ── Language ───────────────────────────────────────────
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Language:"))
        self._stt_lang_cb = QComboBox()
        for code, label in _STT_LANGUAGES:
            self._stt_lang_cb.addItem(
                f"{label} ({code})" if code != "auto" else label, code
            )
        saved_lang = self._settings.value("stt/language", "auto")
        li = self._stt_lang_cb.findData(str(saved_lang))
        if li >= 0:
            self._stt_lang_cb.setCurrentIndex(li)
        self._stt_lang_cb.setToolTip(
            "Set the spoken language for better accuracy.\n"
            "'Auto-detect' lets Whisper guess the language.\n"
            "Picking the right language improves results, \n"
            "especially with smaller models."
        )
        lang_row.addWidget(self._stt_lang_cb)
        lang_row.addStretch()
        stt_layout.addLayout(lang_row)

        # ── Model info label ───────────────────────────────────
        self._stt_info_label = QLabel("")
        self._stt_info_label.setWordWrap(True)
        self._stt_info_label.setStyleSheet(
            "color: var(--meta-text, #888); font-size: 10px; padding: 4px 0;"
        )
        stt_layout.addWidget(self._stt_info_label)

        self._stt_model_cb.currentTextChanged.connect(self._update_stt_model_info)
        self._update_stt_model_info()

        # ── Wire buttons ───────────────────────────────────────
        self._stt_model_cb.currentTextChanged.connect(self._on_stt_model_changed)
        stt_download_btn.clicked.connect(self._on_stt_download)
        stt_delete_btn.clicked.connect(self._on_stt_delete)

        self._stt_download_btn = stt_download_btn
        self._stt_delete_btn = stt_delete_btn

        # ── Populate cache info ────────────────────────────────
        self._refresh_stt_cache()

        stt_layout.addStretch()
        self._tabs.addTab(stt_w, "Speech-to-Text")

    # ── STT helpers ─────────────────────────────────────────────

    def _update_stt_model_info(self) -> None:
        name = self._stt_model_cb.currentText()
        info = _STT_MODEL_INFO.get(name)
        if info:
            self._stt_info_label.setText(
                f"{name}: {info[0]} \u2014 {info[1]}"
            )
        else:
            self._stt_info_label.setText("")

    def _refresh_stt_cache(self) -> None:
        backend = self._stt_backend
        if backend is None:
            return
        info = backend.cache_info()
        self._stt_cache_loc.setText(f"Location: {info['location']}")
        self._stt_cache_size.setText(f"Total: {info['size_human']}")
        lines: list[str] = []
        for m in info["models"]:
            status = (
                f"{m['size_human']} cached"
                if m["downloaded"]
                else "not cached"
            )
            lines.append(f"  {m['name']:24s} \u2014 {status}")
        self._stt_models_table.setText("\n".join(lines))

        cur = self._stt_model_cb.currentText()
        downloaded = backend.is_model_downloaded(cur)
        self._stt_download_btn.setEnabled(not downloaded)
        self._stt_delete_btn.setEnabled(downloaded)

    def _on_stt_model_changed(self) -> None:
        if self._stt_backend is None:
            return
        cur = self._stt_model_cb.currentText()
        downloaded = self._stt_backend.is_model_downloaded(cur)
        self._stt_download_btn.setEnabled(not downloaded)
        self._stt_delete_btn.setEnabled(downloaded)

    def _on_stt_download(self) -> None:
        if self._stt_backend is None:
            return
        cur = self._stt_model_cb.currentText()
        self._stt_download_btn.setEnabled(False)
        self._stt_download_btn.setText("Downloading\u2026")
        QApplication.processEvents()
        try:
            self._stt_backend.download_model(cur)
        except Exception as exc:
            QMessageBox.warning(
                self, "Download Error",
                f"Failed to download model '{cur}':\n{exc}",
            )
        finally:
            self._stt_download_btn.setText("Download")
            self._refresh_stt_cache()

    def _on_stt_delete(self) -> None:
        if self._stt_backend is None:
            return
        cur = self._stt_model_cb.currentText()
        reply = QMessageBox.question(
            self, "Delete Model",
            f"Delete cached model '{cur}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._stt_backend.delete_model(cur)
        except Exception as exc:
            QMessageBox.warning(
                self, "Delete Error",
                f"Failed to delete model '{cur}':\n{exc}",
            )
        self._refresh_stt_cache()

    # ── Apply / Close ───────────────────────────────────────────

    def _cfg_value(self) -> str:
        """Return the selected pi config directory."""
        if self._cfg_default.isChecked():
            return ""
        if self._cfg_local.isChecked():
            return str(
                Path(__file__).resolve().parent.parent.parent
                / "resources" / "pi-config"
            )
        return self._cfg_custom_path.text().strip()

    def _on_cfg_changed(self) -> None:
        """Handle pi config directory changes (used by _apply for restart check)."""
        pass

    def _apply(self) -> None:
        """Apply all settings and emit restart_requested if needed."""

        # Display tab
        self._chat.configure(
            page_size=self._pg_spin.value(),
            pages_displayed=self._pd_spin.value(),
            auto_collapse_agent_work=self._aw_spin.value(),
            auto_collapse_thinking=self._tk_spin.value(),
            auto_collapse_tools=self._tl_spin.value(),
        )
        tn = self._theme_cb.currentText()
        if tn == "system":
            scheme = QApplication.instance().styleHints().colorScheme()
            tn = "dark" if scheme == Qt.ColorScheme.Dark else "light"
        tc = THEMES.get(tn)
        if tc:
            self._chat.set_theme(tc)

        # Build new pi settings
        pi_settings = self._read_pi_settings()
        new_pi = dict(pi_settings)
        new_pi.update({
            "theme": tn,
            "defaultProvider": self._prov_cb.currentText(),
            "defaultModel": self._mod_cb.currentText(),
            "defaultThinkingLevel": self._tl_cb.currentText(),
            "hideThinkingBlock": self._hide_cb.isChecked(),
            "quietStartup": self._quiet_cb.isChecked(),
            "defaultProjectTrust": self._trust_cb.currentText(),
            "compaction": {
                "enabled": self._comp_en.isChecked(),
                "reserveTokens": self._cr_spin.value(),
                "keepRecentTokens": self._ck_spin.value(),
            },
            "retry": {
                "enabled": self._ret_en.isChecked(),
                "maxRetries": self._rm_spin.value(),
            },
        })
        self._settings.setValue(
            "display/show_thinking", 0 if self._hide_cb.isChecked() else 1
        )
        # STT settings
        if self._stt_backend is not None:
            self._settings.setValue("stt/model", self._stt_model_cb.currentText())
            self._settings.setValue(
                "stt/recording_mode", self._stt_rec_cb.currentText()
            )
            self._settings.setValue(
                "stt/voice_mode", self._stt_voice_cb.currentText().lower()
            )
            self._settings.setValue("stt/task", self._stt_task_cb.currentText())
            self._settings.setValue("stt/language", self._stt_lang_cb.currentData())
        self._settings.sync()
        try:
            self._pi_settings_path.write_text(json.dumps(new_pi, indent=2))
        except OSError:
            pass

        # Check if pi needs restart
        cfg_val = self._cfg_value()
        needs_restart = self._tabs.currentIndex() == 1 or cfg_val != self._initial_cfg_dir
        if needs_restart:
            self.restart_requested.emit()

    def _on_close(self) -> None:
        """Apply all pending changes and close."""
        self._apply()
        self.accept()

    # ── helpers ─────────────────────────────────────────────────

    def _read_pi_settings(self) -> dict:
        try:
            return json.loads(self._pi_settings_path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
