"""Project / subject dashboard: pick task + subject, see per-step status, run steps."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from rpcoding.gui.config import load_subject_list, save_config, save_subject_list
from rpcoding.gui.error_dialog import format_exception, show_error
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
        self._scan_token = 0
        # Subject summaries are computed one-per-event-loop-tick so a big (cloud-synced) scan never
        # blocks the UI; a child QTimer is auto-cancelled on teardown.
        self._summary_queue: list[str] = []
        self._summary_total = 0
        self._summary_done = 0
        self._summary_timer = QTimer(self)
        self._summary_timer.setSingleShot(True)
        self._summary_timer.setInterval(0)
        self._summary_timer.timeout.connect(self._process_next_summary)

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

        # A small bottom-centre toast for transient feedback (e.g. "Subject list saved").
        self._toast_label = QLabel("", self)
        self._toast_label.setObjectName("Toast")
        self._toast_label.setVisible(False)
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(lambda: self._toast_label.setVisible(False))

        # Auto-rescan when the task changes (connected after the combo is populated).
        self._task_combo.currentIndexChanged.connect(self._on_task_changed)

    # ---- UI construction ----
    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(54)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(12)
        task_label = QLabel("Task")
        task_label.setObjectName("Secondary")
        lay.addWidget(task_label)
        self._task_combo = QComboBox()
        self._task_combo.setMinimumWidth(240)
        for t in Task:
            self._task_combo.addItem(t.value, t)
        lay.addWidget(self._task_combo)
        scan = QPushButton("Scan subjects")
        scan.clicked.connect(self._scan)
        lay.addWidget(scan)
        save_list = QPushButton("Save list")
        save_list.clicked.connect(self._save_list)
        lay.addWidget(save_list)
        lay.addStretch(1)
        self._run_all = QPushButton("▶ Run automated · selected")
        self._run_all.setObjectName("Primary")
        self._run_all.clicked.connect(self._open_batch)
        lay.addWidget(self._run_all)
        settings_btn = QPushButton("⚙ Settings")
        settings_btn.clicked.connect(self._open_settings)
        lay.addWidget(settings_btn)
        self._theme_btn = QPushButton("◑ Light")
        self._theme_btn.setObjectName("ThemeToggle")
        self._theme_btn.setText("◑ Light" if self._theme.name == "dark" else "◑ Dark")
        self._theme_btn.clicked.connect(self.theme_toggle_requested.emit)
        lay.addWidget(self._theme_btn)
        return bar

    def _build_side_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("SidePanel")
        panel.setFixedWidth(300)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QFrame()
        header.setObjectName("SidePanelHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 13, 16, 13)
        hl.setSpacing(9)
        self._select_all = QCheckBox()
        self._select_all.setTristate(True)
        self._select_all.setToolTip("Select all / none")
        self._select_all.clicked.connect(self._toggle_all)
        hl.addWidget(self._select_all)
        title = QLabel("Subjects")
        title.setObjectName("SectionTitle")
        hl.addWidget(title)
        hl.addStretch(1)
        self._subj_count = QLabel("")
        self._subj_count.setObjectName("SubjCount")
        hl.addWidget(self._subj_count)
        lay.addWidget(header)

        filter_row = QFrame()
        filter_row.setObjectName("FilterRow")
        fl = QHBoxLayout(filter_row)
        fl.setContentsMargins(12, 9, 12, 9)
        fl.setSpacing(8)
        self._filter = QLineEdit()
        self._filter.setObjectName("FilterInput")
        self._filter.setPlaceholderText("filter…")
        self._filter.textChanged.connect(self._on_filter)
        fl.addWidget(self._filter, 1)
        add_btn = QPushButton("＋")
        add_btn.setObjectName("IconSmall")
        add_btn.setToolTip("Add a subject by ID (from the filter box)")
        add_btn.clicked.connect(self._add_subject)
        fl.addWidget(add_btn)
        rm_btn = QPushButton("－")
        rm_btn.setObjectName("IconSmall")
        rm_btn.setToolTip("Remove the selected subject from the list")
        rm_btn.clicked.connect(self._remove_subject)
        fl.addWidget(rm_btn)
        lay.addWidget(filter_row)

        self._subjects = SubjectList(self._theme)
        self._subjects.subject_selected.connect(self._on_subject)
        self._subjects.selection_changed.connect(self._update_count)
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
        self._sub_path.setObjectName("SubPath")
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
        rows_lay.setContentsMargins(24, 6, 24, 6)
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
        self._scan_token += 1
        subs = scan_subjects(paths.d_data_dir(self._config.droot, self.current_task))
        self._subjects.set_subjects(subs)
        saved = load_subject_list(self.current_task.value)
        if saved is not None:
            self._subjects.set_checked(saved)  # restore a previously-saved selection
        self._update_count()
        self._summary_queue = list(subs)
        self._summary_total = len(subs)
        self._summary_done = 0
        if subs:
            self._summary_timer.start()

    def _toggle_all(self) -> None:
        # All-or-nothing from the current row state (ignore the checkbox's own tri-state cycle).
        self._subjects.set_all_checked(self._subjects.selected_count() < self._subjects.count())

    def _update_count(self) -> None:
        found = self._subjects.count()
        sel = self._subjects.selected_count()
        self._subj_count.setText(f"{found} found · {sel} selected")
        self._select_all.blockSignals(True)
        if found and sel == found:
            self._select_all.setCheckState(Qt.CheckState.Checked)
        elif sel == 0:
            self._select_all.setCheckState(Qt.CheckState.Unchecked)
        else:
            self._select_all.setCheckState(Qt.CheckState.PartiallyChecked)
        self._select_all.blockSignals(False)

    def _process_next_summary(self) -> None:
        if not self._summary_queue:
            return
        sid = self._summary_queue.pop(0)
        try:
            done, total, state = SubjectSession(self._config, self.current_task, sid).summary()
            self._subjects.set_summary(sid, done, total, state)
        except OSError:
            pass  # a cloud-sync placeholder we can't read yet; skip it this pass
        self._summary_done += 1
        n, k = self._summary_total, self._summary_done
        if k >= n:
            self._update_count()
        else:
            self._subj_count.setText(f"{n} found · {k}/{n}…")  # transient compute progress
        if self._summary_queue:
            self._summary_timer.start()  # next subject on the next event-loop tick

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
        self._theme_btn.setText("◑ Light" if theme.name == "dark" else "◑ Dark")
        self._subjects.set_theme(theme)
        for row in self._rows.values():
            row.set_theme(theme)
        self._refresh_states()

    # ---- subject-list curation (filter / add / remove / save) ----
    def _on_filter(self, text: str) -> None:
        self._subjects.set_filter(text)

    def _add_subject(self) -> None:
        sid = self._filter.text().strip()
        if sid:
            self._subjects.add_subject(sid)
            self._filter.clear()

    def _remove_subject(self) -> None:
        sid = self._subjects.current_subject()
        if sid:
            self._subjects.remove_subject(sid)

    def _save_list(self) -> None:
        subs = self._subjects.checked_subjects()
        save_subject_list(self.current_task.value, subs)
        self._toast(f"Saved {len(subs)} subject(s) to the list")

    def _toast(self, message: str) -> None:
        self._toast_label.setText(message)
        self._toast_label.adjustSize()
        self._position_toast()
        self._toast_label.setVisible(True)
        self._toast_label.raise_()
        self._toast_timer.start(2200)

    def _position_toast(self) -> None:
        lbl = self._toast_label
        lbl.move((self.width() - lbl.width()) // 2, self.height() - lbl.height() - 22)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        if self._toast_label.isVisible():
            self._position_toast()

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
            try:
                self._refresh_states()
                if self._session is not None:
                    d, t, st = self._session.summary()
                    self._subjects.set_summary(self._session.subject, d, t, st)
            except Exception as exc:  # noqa: BLE001 - never let a refresh crash the app
                show_error(
                    "Could not refresh status after the step.", format_exception(exc), parent=self
                )

        def failed(message: str) -> None:
            # The worker already recorded the error (red chip); also pop a dialog so it's visible.
            show_error(f"Step failed: {_SPECS[step].title}", message, parent=self)

        self._active = run_in_thread(
            self, run_step, self._session, step, on_finished=done, on_error=failed
        )

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
        dialog = SettingsDialog(self._config, self._theme, self)
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
