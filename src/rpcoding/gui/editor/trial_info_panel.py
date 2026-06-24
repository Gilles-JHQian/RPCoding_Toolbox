"""Trial Info side panel: the trial owning the current selection + a one-click error palette."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rpcoding.core.rpcode.errors import response_tags
from rpcoding.core.tasks import Task
from rpcoding.core.trial_index import TrialInfo

_FIELDS = ["Trial", "Block", "Task", "Stim", "Word/Nonword", "Response", "Error"]
_CONVENTIONS = (
    'Conventions (hints): Just-Listen → no label · Repeat → number · Yes/No → "yes"/"no" · '
    'uncertain → "noisy" · missed → blank · evens ascending.'
)


class TrialInfoPanel(QFrame):
    error_code_picked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TrialPanel")
        self.setFixedWidth(272)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        title = QLabel("Trial Info")
        title.setObjectName("SectionTitle")
        title.setContentsMargins(16, 13, 16, 13)
        lay.addWidget(title)
        lay.addWidget(self._hline())

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        self._values: dict[str, QLabel] = {}
        for row, key in enumerate(_FIELDS):
            k = QLabel(key)
            k.setObjectName("Secondary")
            grid.addWidget(k, row, 0)
            val = QLabel("—")
            val.setObjectName("ErrorVal" if key == "Error" else "FieldVal")
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val.setWordWrap(key == "Error")
            self._values[key] = val
            grid.addWidget(val, row, 1)
        lay.addWidget(grid_host)
        lay.addWidget(self._hline())

        pal_host = QWidget()
        pv = QVBoxLayout(pal_host)
        pv.setContentsMargins(16, 12, 16, 12)
        pv.setSpacing(10)
        cap = QLabel("ERROR TAGS · CLICK TO SET LABEL")
        cap.setObjectName("Caption")
        pv.addWidget(cap)
        self._palette = QGridLayout()
        self._palette.setSpacing(6)
        pv.addLayout(self._palette)
        hint = QLabel(_CONVENTIONS)
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        pv.addWidget(hint)
        lay.addWidget(pal_host)
        lay.addStretch(1)
        self.set_tags(response_tags(Task.LEXICAL_DELAY))  # default until the task is known

    def set_tags(self, tags: list[tuple[str, str]]) -> None:
        """Rebuild the quick-tag palette from ``(code, description)`` pairs (per task)."""
        while self._palette.count():
            item = self._palette.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)  # detach now so it isn't found before deleteLater runs
                w.deleteLater()
        for i, (code, desc) in enumerate(tags):
            btn = QPushButton(code)
            btn.setObjectName("Chip")
            btn.setToolTip(desc)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # mouse-only; keep Tab on the editor
            btn.clicked.connect(lambda _checked=False, c=code: self.error_code_picked.emit(c))
            self._palette.addWidget(btn, i // 2, i % 2)

    def _hline(self) -> QFrame:
        line = QFrame()
        line.setObjectName("HLine")
        line.setFrameShape(QFrame.Shape.HLine)
        return line

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
