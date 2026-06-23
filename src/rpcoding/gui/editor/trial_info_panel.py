"""Trial Info side panel: the trial owning the current selection + a one-click error palette."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QVBoxLayout

from rpcoding.core.trial_index import TrialInfo

# Authoritative error taxonomy from the lab wiki.
ERROR_CODES = [
    "ERR_TASK_YN_REP",
    "ERR_TASK_REP_YN",
    "ERR_RESP_YN_YN",
    "ERR_RESP_YN_NY",
    "ERR_RESP_REP_WRO",
    "ERR_RESP_REP_MIS",
    "NOISY",
    "LATR_RESP",
]
_FIELDS = ["Trial", "Block", "Task", "Stim", "Word/Nonword", "Response", "Error"]


class TrialInfoPanel(QFrame):
    error_code_picked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.setFixedWidth(272)
        lay = QVBoxLayout(self)

        title = QLabel("Trial Info")
        title.setObjectName("SubjectId")
        lay.addWidget(title)

        grid = QGridLayout()
        self._values: dict[str, QLabel] = {}
        for row, key in enumerate(_FIELDS):
            grid.addWidget(QLabel(key), row, 0)
            val = QLabel("—")
            val.setObjectName("Secondary")
            self._values[key] = val
            grid.addWidget(val, row, 1)
        lay.addLayout(grid)

        lay.addWidget(QLabel("Error palette"))
        palette = QGridLayout()
        for i, code in enumerate(ERROR_CODES):
            btn = QPushButton(code)
            btn.clicked.connect(lambda _checked=False, c=code: self.error_code_picked.emit(c))
            palette.addWidget(btn, i // 2, i % 2)
        lay.addLayout(palette)
        lay.addStretch(1)

    def set_trial(
        self,
        info: TrialInfo | None,
        *,
        block=None,
        word_nonword=None,
        response=None,
        error=None,
    ) -> None:
        if info is None:
            for val in self._values.values():
                val.setText("—")
            return
        self._values["Trial"].setText(str(info.trial))
        self._values["Block"].setText("—" if block is None else str(block))
        self._values["Task"].setText(info.task or "—")
        self._values["Stim"].setText(info.stim or "—")
        self._values["Word/Nonword"].setText(word_nonword or "—")
        self._values["Response"].setText(response or "—")
        self._values["Error"].setText(error or "—")
