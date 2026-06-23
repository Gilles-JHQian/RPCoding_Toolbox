"""Project / subject dashboard: pick task + subject, see per-step status, run steps."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from rpcoding.core import paths
from rpcoding.core.config import AppConfig
from rpcoding.core.runner import run_step
from rpcoding.core.scanner import scan_subjects
from rpcoding.core.session import SubjectSession
from rpcoding.core.steps import STEP_ORDER, EffectiveState, Step, StepKind, StepSpec
from rpcoding.core.steps import STEP_SPECS as _SPECS
from rpcoding.core.tasks import Task
from rpcoding.gui.batch_dialog import BatchDialog
from rpcoding.gui.config import save_config
from rpcoding.gui.settings_dialog import SettingsDialog
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
        outer.setSpacing(0)
        outer.addWidget(self._build_top_bar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_side_panel())
        body.addWidget(self._build_status_panel(), 1)
        outer.addLayout(body, 1)

        # Auto-rescan when the task changes (connected after the combo is populated).
        self._task_combo.currentIndexChanged.connect(self._on_task_changed)

    # ---- UI construction ----
    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(54)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(12)
        lay.addWidget(QLabel("Task"))
        self._task_combo = QComboBox()
        self._task_combo.setMinimumWidth(240)
        for t in Task:
            self._task_combo.addItem(t.value, t)
        lay.addWidget(self._task_combo)
        scan = QPushButton("Scan subjects")
        scan.clicked.connect(self._scan)
        lay.addWidget(scan)
        lay.addStretch(1)
        self._run_all = QPushButton("▶ Run automated · selected")
        self._run_all.setObjectName("Primary")
        self._run_all.clicked.connect(self._open_batch)
        lay.addWidget(self._run_all)
        settings_btn = QPushButton("⚙ Settings")
        settings_btn.clicked.connect(self._open_settings)
        lay.addWidget(settings_btn)
        theme_btn = QPushButton("◐")
        theme_btn.setObjectName("Icon")
        theme_btn.clicked.connect(self.theme_toggle_requested.emit)
        lay.addWidget(theme_btn)
        return bar

    def _build_side_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("SidePanel")
        panel.setFixedWidth(300)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QFrame()
        header.setObjectName("PanelHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 13, 16, 13)
        title = QLabel("Subjects")
        title.setObjectName("SectionTitle")
        hl.addWidget(title)
        hl.addStretch(1)
        self._subj_count = QLabel("")
        self._subj_count.setObjectName("Meta")
        hl.addWidget(self._subj_count)
        lay.addWidget(header)

        self._subjects = SubjectList(self._theme)
        self._subjects.subject_selected.connect(self._on_subject)
        lay.addWidget(self._subjects, 1)
        return panel

    def _build_status_panel(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QFrame()
        head.setObjectName("PanelHeader")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(24, 15, 24, 15)
        hl.setSpacing(13)
        self._header = QLabel("Select a subject")
        self._header.setObjectName("SubjectId")
        hl.addWidget(self._header)
        self._sub_path = QLabel("")
        self._sub_path.setObjectName("Secondary")
        hl.addWidget(self._sub_path)
        hl.addStretch(1)
        self._banner = QLabel("")
        self._banner.setObjectName("Banner")
        hl.addWidget(self._banner)
        lay.addWidget(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        rows_host = QWidget()
        rows_lay = QVBoxLayout(rows_host)
        rows_lay.setContentsMargins(24, 0, 24, 0)
        rows_lay.setSpacing(0)
        self._rows: dict[Step, StepRow] = {}
        for i, step in enumerate(STEP_ORDER, start=1):
            row = StepRow(self._theme, step, i)
            row.action.connect(self._on_step_action)
            row.error_details.connect(self._show_error)
            self._rows[step] = row
            rows_lay.addWidget(row)
            line = QFrame()
            line.setObjectName("HLine")
            rows_lay.addWidget(line)
        rows_lay.addStretch(1)
        scroll.setWidget(rows_host)
        lay.addWidget(scroll, 1)
        return panel

    # ---- backend wiring ----
    @property
    def current_task(self) -> Task:
        # currentData() round-trips a StrEnum to a plain str via QVariant; coerce back to Task.
        return Task.from_str(self._task_combo.currentText())

    def _scan(self) -> None:
        subs = scan_subjects(paths.d_data_dir(self._config.droot, self.current_task))
        self._subjects.set_subjects(subs)
        for sid in subs:
            done, total, state = SubjectSession(self._config, self.current_task, sid).summary()
            self._subjects.set_summary(sid, done, total, state)
        self._subj_count.setText(f"{len(subs)} found")

    def _on_task_changed(self) -> None:
        self._session = None
        self._header.setText("Select a subject")
        self._sub_path.setText("")
        self._banner.setText("")
        for row in self._rows.values():
            row.set_state(EffectiveState.NOT_STARTED)
        self._scan()

    def _on_subject(self, subject: str) -> None:
        self._session = SubjectSession(self._config, self.current_task, subject)
        self._refresh_states()

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._subjects.set_theme(theme)
        for row in self._rows.values():
            row.set_theme(theme)
        self._refresh_states()

    def refresh(self) -> None:
        """Recompute and repaint step states (e.g. after the editor saves an output)."""
        self._refresh_states()
        if self._session is not None:
            done, total, state = self._session.summary()
            self._subjects.set_summary(self._session.subject, done, total, state)

    def _refresh_states(self) -> None:
        if self._session is None:
            return
        self._header.setText(self._session.subject)
        states = self._session.effective_states()
        done = sum(1 for s in states.values() if s == EffectiveState.DONE)
        stale = sum(1 for s in states.values() if s == EffectiveState.STALE)
        self._sub_path.setText(f"{self.current_task.value} · results/{self._session.subject}/")
        if stale:
            self._banner.setText(f"⚠ {stale} step(s) stale — upstream edited")
            self._banner.setStyleSheet(f"color: {self._theme.state_color(EffectiveState.STALE)};")
        else:
            self._banner.setText(f"{done} / {len(states)} complete")
            self._banner.setStyleSheet(f"color: {self._theme.color('text-ter')};")
        for step, row in self._rows.items():
            row.set_state(states[step], self._meta_for(step), self._session.step_error(step))

    def _meta_for(self, step: Step) -> str:
        rec = self._session.manifest.steps.get(str(step)) if self._session else None
        if rec is None:
            return ""
        if rec.state == "error":
            return "error — click the chip for details"
        if rec.ran_at:
            return f"ran {rec.ran_at[:16].replace('T', ' ')}"
        return ""

    def _on_step_action(self, step: Step) -> None:
        if self._session is None:
            return
        spec: StepSpec = _SPECS[step]
        if spec.kind == StepKind.MANUAL:
            self.open_editor.emit(self._session, step)
            return
        # Single automated step: run inline (no popup) — just flip the row to "running".
        self._rows[step].set_running()

        def done() -> None:
            self._refresh_states()
            if self._session is not None:
                d, t, st = self._session.summary()
                self._subjects.set_summary(self._session.subject, d, t, st)

        self._active = run_in_thread(self, run_step, self._session, step, on_finished=done)

    def _show_error(self, step: Step) -> None:
        if self._session is None:
            return
        message = self._session.step_error(step) or "No error details recorded."
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(f"{_SPECS[step].title} — error")
        box.setText(_SPECS[step].title)
        box.setInformativeText(message)
        box.exec()

    def _open_batch(self) -> None:
        subjects = self._subjects.checked_subjects()
        if not subjects:
            return
        BatchDialog(self._config, self.current_task, subjects, self).exec()
        self._scan()
        if self._session is not None:
            self._refresh_states()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._config, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return
        self.set_config(dialog.result_config())

    def set_config(self, config: AppConfig) -> None:
        """Apply and persist a new config; rebuild the current session against it."""
        self._config = config
        save_config(config)
        if self._session is not None:
            self._session = SubjectSession(config, self.current_task, self._session.subject)
        self._refresh_states()
