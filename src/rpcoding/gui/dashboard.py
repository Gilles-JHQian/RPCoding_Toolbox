"""Project / subject dashboard: pick task + subject, see per-step status, run steps."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from rpcoding.core import paths
from rpcoding.core.config import AppConfig
from rpcoding.core.runner import run_pipeline, run_step
from rpcoding.core.scanner import scan_subjects
from rpcoding.core.session import SubjectSession
from rpcoding.core.steps import STEP_ORDER, EffectiveState, Step, StepKind, StepSpec
from rpcoding.core.steps import STEP_SPECS as _SPECS
from rpcoding.core.tasks import Task
from rpcoding.gui.progress_dialog import ProgressDialog
from rpcoding.gui.theme import Theme
from rpcoding.gui.widgets.step_row import StepRow
from rpcoding.gui.widgets.subject_list import SubjectList
from rpcoding.gui.workers.worker import run_in_thread


class Dashboard(QWidget):
    open_editor = Signal(object, object)  # (SubjectSession, Step)
    theme_toggle_requested = Signal()

    def __init__(self, config: AppConfig, theme: Theme, parent=None):
        super().__init__(parent)
        self._config = config
        self._theme = theme
        self._session: SubjectSession | None = None
        self._active: tuple | None = None  # (thread, worker) kept alive

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._build_top_bar())

        body = QHBoxLayout()
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(12)
        self._subjects = SubjectList()
        self._subjects.setFixedWidth(300)
        self._subjects.subject_selected.connect(self._on_subject)
        body.addWidget(self._subjects)
        body.addWidget(self._build_status_panel(), 1)
        outer.addLayout(body, 1)

    # ---- UI construction ----
    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.addWidget(QLabel("Task"))
        self._task_combo = QComboBox()
        for t in Task:
            self._task_combo.addItem(t.value, t)
        lay.addWidget(self._task_combo)
        scan = QPushButton("Scan subjects")
        scan.clicked.connect(self._scan)
        lay.addWidget(scan)
        lay.addStretch(1)
        self._run_all = QPushButton("▶ Run automated")
        self._run_all.setObjectName("Primary")
        self._run_all.clicked.connect(self._run_automated)
        lay.addWidget(self._run_all)
        theme_btn = QPushButton("◐")
        theme_btn.setFixedWidth(36)
        theme_btn.clicked.connect(self.theme_toggle_requested.emit)
        lay.addWidget(theme_btn)
        return bar

    def _build_status_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        lay = QVBoxLayout(panel)
        self._header = QLabel("Select a subject")
        self._header.setObjectName("SubjectId")
        lay.addWidget(self._header)
        self._summary = QLabel("")
        self._summary.setObjectName("Secondary")
        lay.addWidget(self._summary)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        rows_host = QWidget()
        rows_lay = QVBoxLayout(rows_host)
        rows_lay.setSpacing(4)
        self._rows: dict[Step, StepRow] = {}
        for i, step in enumerate(STEP_ORDER, start=1):
            row = StepRow(self._theme, step, i)
            row.action.connect(self._on_step_action)
            self._rows[step] = row
            rows_lay.addWidget(row)
        rows_lay.addStretch(1)
        scroll.setWidget(rows_host)
        lay.addWidget(scroll, 1)
        return panel

    # ---- backend wiring ----
    @property
    def current_task(self) -> Task:
        return self._task_combo.currentData()

    def _scan(self) -> None:
        subs = scan_subjects(paths.d_data_dir(self._config.droot, self.current_task))
        self._subjects.set_subjects(subs)

    def _on_subject(self, subject: str) -> None:
        self._session = SubjectSession(self._config, self.current_task, subject)
        self._refresh_states()

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        for row in self._rows.values():
            row.set_theme(theme)
        self._refresh_states()

    def _refresh_states(self) -> None:
        if self._session is None:
            return
        self._header.setText(self._session.subject)
        states = self._session.effective_states()
        done = sum(1 for s in states.values() if s == EffectiveState.DONE)
        self._summary.setText(f"{done} / {len(states)} complete   ·   {self._session.results_dir}")
        for step, row in self._rows.items():
            row.set_state(states[step])

    def _on_step_action(self, step: Step) -> None:
        if self._session is None:
            return
        spec: StepSpec = _SPECS[step]
        if spec.kind == StepKind.MANUAL:
            self.open_editor.emit(self._session, step)
            return
        self._run(spec.title, run_step, self._session, step)

    def _run_automated(self) -> None:
        if self._session is None:
            return
        self._run("Run automated pipeline", run_pipeline, self._session)

    def _run(self, title: str, fn, *args) -> None:
        dialog = ProgressDialog(f"{title} — {self._session.subject}", self)
        dialog.append("Running…")

        def on_error(msg: str) -> None:
            dialog.append(f"ERROR: {msg}")

        def on_finished() -> None:
            dialog.finish(ok=True, message="Finished.")
            self._refresh_states()

        self._active = run_in_thread(self, fn, *args, on_error=on_error, on_finished=on_finished)
        dialog.exec()
