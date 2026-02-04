from __future__ import annotations

import json

from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton


class ConfigDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Config")

        self._cfg = cfg

        self.editor = QTextEdit()
        self.editor.setText(json.dumps(cfg.raw, indent=2))

        save = QPushButton("Save")
        save.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)
        layout.addWidget(save)

    def accept(self):
        new_cfg = json.loads(self.editor.toPlainText())
        self._cfg.config_file.write_text(
            json.dumps(new_cfg, indent=2),
            encoding="utf-8",
        )
        super().accept()
