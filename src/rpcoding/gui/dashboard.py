"""Project / subject dashboard: pick task + subject, see per-step status, run steps."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from rpcoding.core import paths
from rpcoding.core.config import AppConfig
from rpcoding.core.scanner import scan_subjects
from rpcoding.core.session import SubjectSession
from rpcoding.core.steps import STEP_ORDER, STEP_SHORT, EffectiveState, Step, StepKind, StepSpec
from rpcoding.core.steps import STEP_SPECS as _SPECS
from rpcoding.core.tasks import Task
from rpcoding.gui.config import load_subject_list, save_config, save_subject_list
from rpcoding.gui.error_dialog import format_exception, show_error
from rpcoding.gui.log_dialog import LogDialog
from rpcoding.gui.settings_dialog import SettingsDialog
from rpcoding.gui.theme import Theme
from rpcoding.gui.widgets.step_row import StepRow
from rpcoding.gui.widgets.subject_list import SubjectList
from rpcoding.gui.workers.worker import run_in_thread


class Dashboard(QWidget):
    open_editor = Signal(object, object)  # (SubjectSession, Step)
    theme_toggle_requested = Signal()
    # Step progress relayed from the worker thread; a Dashboard signal -> Dashboard slot is a queued
    # (cross-thread) connection, so the row update runs safely on the GUI thread.
    _step_tick = Signal(object, object, str)  # (Step, fraction|None, message)

    def __init__(self, config: AppConfig, theme: Theme, parent=None):
        super().__init__(parent)
        self._config = config
        self._theme = theme
        self._session: SubjectSession | None = None
        self._active: tuple | None = None  # (thread, worker) kept alive
        self._scan_token = 0
        # Path to the most recent run log (MFA writes mfa_run.log); the status bar reveals it.
        self._last_log_path: Path | None = None
        # Resolving the raw-blocks dir walks the Box folder tree (slow), so the Folders menu does it
        # off the UI thread and caches the result per subject (key = "task/subject").
        self._blocks_cache: dict[str, Path | None] = {}
        self._blocks_pending: set[str] = set()
        # Subject summaries are computed one-per-event-loop-tick so a big (cloud-synced) scan never
        # blocks the UI; a child QTimer is auto-cancelled on teardown.
        self._summary_queue: list[str] = []
        self._summary_total = 0
        self._summary_done = 0
        self._summary_timer = QTimer(self)
        self._summary_timer.setSingleShot(True)
        self._summary_timer.setInterval(0)
        self._summary_timer.timeout.connect(self._process_next_summary)
        self._step_tick.connect(self._on_step_progress)

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
        outer.addWidget(self._build_status_bar())

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
        self._flag_btn = QPushButton("⚑ Flag")
        self._flag_btn.setObjectName("Icon")
        self._flag_btn.setCheckable(True)
        self._flag_btn.setEnabled(False)
        self._flag_btn.setToolTip("Manually mark this subject as having a problem")
        self._flag_btn.toggled.connect(self._on_flag_toggled)
        hl.addWidget(self._flag_btn)
        self._banner = QLabel("")
        self._banner.setObjectName("Banner")
        hl.addWidget(self._banner)
        lay.addWidget(head)

        # Free-text notes for the selected subject (behavioural coding is messy — let the user jot
        # state per subject). Saved (debounced) into the subject's manifest.
        notes_bar = QFrame()
        notes_bar.setObjectName("PanelHeader")
        nl = QHBoxLayout(notes_bar)
        nl.setContentsMargins(24, 8, 24, 10)
        nl.setSpacing(10)
        notes_cap = QLabel("Notes")
        notes_cap.setObjectName("Caption")
        nl.addWidget(notes_cap, 0, Qt.AlignmentFlag.AlignTop)
        self._notes = QPlainTextEdit()
        self._notes.setObjectName("NotesField")
        self._notes.setPlaceholderText("Manual notes about this subject…")
        self._notes.setFixedHeight(48)
        self._notes.setEnabled(False)
        self._notes.textChanged.connect(lambda: self._notes_timer.start(600))
        nl.addWidget(self._notes, 1)
        lay.addWidget(notes_bar)
        # Debounced notes save (avoid writing JSON on every keystroke).
        self._notes_timer = QTimer(self)
        self._notes_timer.setSingleShot(True)
        self._notes_timer.timeout.connect(self._save_notes)

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

    def _build_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("StatusBar")
        bar.setFixedHeight(32)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 12, 0)
        lay.setSpacing(10)
        # Clickable status text → opens the last run log (the MFA pipeline's output, etc.).
        self._status_btn = QPushButton("Ready")
        self._status_btn.setObjectName("StatusLink")
        self._status_btn.setFlat(True)
        self._status_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._status_btn.setToolTip("Click to view the last run log")
        self._status_btn.clicked.connect(self._show_last_log)
        lay.addWidget(self._status_btn)
        lay.addStretch(1)
        self._open_folder_btn = QPushButton("📂 Folders")
        self._open_folder_btn.setObjectName("Icon")
        self._open_folder_btn.setToolTip("Open a key folder for this subject")
        self._open_folder_btn.setEnabled(False)
        folder_menu = QMenu(self._open_folder_btn)
        folder_menu.aboutToShow.connect(self._populate_folder_menu)
        self._open_folder_btn.setMenu(folder_menu)
        lay.addWidget(self._open_folder_btn)
        return bar

    def _set_status(self, text: str) -> None:
        self._status_btn.setText(text)

    def _current_log_path(self) -> Path | None:
        """The log to show when the status bar is clicked: the last one we ran, else this subject's
        mfa_run.log if present."""
        if self._last_log_path is not None and self._last_log_path.exists():
            return self._last_log_path
        if self._session is not None:
            cand = self._session.results_dir / "mfa_run.log"
            if cand.exists():
                return cand
        return None

    def _recorded_errors_text(self) -> str:
        """A synthesized 'log' from this subject's recorded step errors, for steps that don't
        write a log file of their own."""
        if self._session is None:
            return ""
        chunks = []
        for step in STEP_ORDER:
            err = self._session.step_error(step)
            if err:
                chunks.append(f"[{_SPECS[step].title}]\n{err}")
        return "\n\n".join(chunks)

    def _show_last_log(self) -> None:
        path = self._current_log_path()
        if path is not None:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                text = f"Could not read log file:\n{exc}"
            LogDialog(
                f"Run log — {path.parent.name}/{path.name}",
                text,
                folder=path.parent,
                parent=self,
            ).exec()
            return
        # No log file on disk — fall back to any recorded step errors for this subject.
        errors = self._recorded_errors_text()
        if errors:
            folder = self._session.results_dir if self._session is not None else None
            LogDialog("Last run — recorded errors", errors, folder=folder, parent=self).exec()
            return
        QMessageBox.information(
            self,
            "Run log",
            "No run log found yet.\n\nThe MFA step writes mfa_run.log into the subject's "
            "results folder when it runs.",
        )

    def _remember_log_for(self, step: Step) -> None:
        """Point the status-bar log link at the freshest log produced by ``step`` (currently only
        MFA writes one); other steps fall back to recorded errors."""
        if self._session is None:
            return
        log = self._session.results_dir / "mfa_run.log"
        self._last_log_path = log if log.exists() else None

    # ---- folder shortcuts ----
    @staticmethod
    def _dir_exists(path) -> bool:
        try:
            return Path(path).is_dir()
        except OSError:  # un-stat-able cloud placeholder
            return False

    def _add_folder_action(self, menu, label: str, path) -> None:
        act = menu.addAction(label)
        if path is not None and self._dir_exists(path):
            act.triggered.connect(lambda _checked=False, p=path: self._open_folder(p))
        else:
            act.setEnabled(False)  # not present yet (e.g. results before any step ran)

    def _add_blocks_action(self, menu, session) -> None:
        """The raw-blocks dir is found by walking the Box folder tree — slow on cloud storage — so
        resolve it off the UI thread and cache it; the menu shows '(finding…)' until it's ready."""
        key = f"{session.task}/{session.subject}"
        if key in self._blocks_cache:
            self._add_folder_action(menu, "Raw audio blocks", self._blocks_cache[key])
            return
        act = menu.addAction("Raw audio blocks (finding…)")
        act.setEnabled(False)
        if key not in self._blocks_pending:
            self._blocks_pending.add(key)
            run_in_thread(
                self,
                lambda s=session: s.all_blocks_dir,  # the slow Box-tree walk (memoised on success)
                on_result=lambda d, k=key: self._store_blocks(k, d),
                on_error=lambda _msg, k=key: self._store_blocks(k, None),
            )

    def _store_blocks(self, key: str, path) -> None:
        self._blocks_cache[key] = path
        self._blocks_pending.discard(key)

    def _populate_folder_menu(self) -> None:
        menu = self._open_folder_btn.menu()
        menu.clear()
        if self._session is None:
            return
        s = self._session
        self._add_folder_action(menu, "Results folder", s.results_dir)
        self._add_folder_action(menu, "D_Data folder (Trials.mat)", s.d_data_subject_dir)
        self._add_blocks_action(menu, s)  # resolved off-thread (slow on Box)
        self._add_folder_action(menu, "Data root (CoganLab)", Path(self._config.droot))

    def _open_folder(self, path) -> None:
        if self._dir_exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self._toast("That folder doesn't exist yet")

    # ---- per-subject notes + problem flag ----
    def _save_notes(self) -> None:
        if self._session is not None:
            self._session.set_notes(self._notes.toPlainText())

    def _flush_notes(self) -> None:
        """Persist any pending (debounced) notes edit before switching away from this subject."""
        if self._session is not None and self._notes_timer.isActive():
            self._notes_timer.stop()
            self._session.set_notes(self._notes.toPlainText())

    def _on_flag_toggled(self, checked: bool) -> None:
        if self._session is None:
            return
        self._session.set_flagged(checked)
        self._update_flag_button(checked)
        done, total, state, current = self._session.status()
        self._subjects.set_summary(
            self._session.subject, done, total, state, self._step_label(current)
        )
        self._refresh_states()

    def _update_flag_button(self, flagged: bool) -> None:
        self._flag_btn.setText("⚑ Flagged" if flagged else "⚑ Flag")
        if flagged:
            color = self._theme.state_color(EffectiveState.FLAGGED)
            self._flag_btn.setStyleSheet(
                f"color: {color}; border: 1px solid {color}; font-weight: 600;"
            )
        else:
            self._flag_btn.setStyleSheet("")

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

    @staticmethod
    def _step_label(current: Step | None) -> str:
        """Short label of the subject's current step (or a done marker) for the subject list."""
        return "✓ done" if current is None else STEP_SHORT.get(current, current.value)

    def _process_next_summary(self) -> None:
        if not self._summary_queue:
            return
        sid = self._summary_queue.pop(0)
        try:
            done, total, state, current = SubjectSession(
                self._config, self.current_task, sid
            ).status()
            self._subjects.set_summary(sid, done, total, state, self._step_label(current))
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
        self._flush_notes()
        self._session = None
        self._last_log_path = None
        self._open_folder_btn.setEnabled(False)
        self._set_status("Ready")
        self._header.setText("Select a subject")
        self._sub_path.setText("")
        self._banner.setText("")
        self._notes.blockSignals(True)
        self._notes.clear()
        self._notes.blockSignals(False)
        self._notes.setEnabled(False)
        self._flag_btn.blockSignals(True)
        self._flag_btn.setChecked(False)
        self._flag_btn.blockSignals(False)
        self._flag_btn.setEnabled(False)
        self._update_flag_button(False)
        for row in self._rows.values():
            row.set_state(EffectiveState.NOT_STARTED)
        self._scan()

    def _on_subject(self, subject: str) -> None:
        self._flush_notes()  # save any pending notes for the previously selected subject
        self._session = SubjectSession(self._config, self.current_task, subject)
        self._last_log_path = None  # fall back to this subject's own run log
        self._open_folder_btn.setEnabled(True)
        # Load this subject's notes + flag without re-triggering their change handlers.
        self._notes.blockSignals(True)
        self._notes.setPlainText(self._session.notes)
        self._notes.blockSignals(False)
        self._notes.setEnabled(True)
        self._flag_btn.blockSignals(True)
        self._flag_btn.setChecked(self._session.flagged)
        self._flag_btn.blockSignals(False)
        self._flag_btn.setEnabled(True)
        self._update_flag_button(self._session.flagged)
        self._set_status(f"{subject} selected")
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
            done, total, state, current = self._session.status()
            self._subjects.set_summary(
                self._session.subject, done, total, state, self._step_label(current)
            )

    def _refresh_states(self) -> None:
        if self._session is None:
            return
        self._header.setText(self._session.subject)
        states = self._session.effective_states()
        # Optional steps (Denoise) don't count toward completion — mirror SubjectSession.summary().
        required = {st: s for st, s in states.items() if _SPECS[st].kind != StepKind.OPTIONAL}
        done = sum(1 for s in required.values() if s == EffectiveState.DONE)
        stale = sum(1 for s in required.values() if s == EffectiveState.STALE)
        self._sub_path.setText(f"{self.current_task.value} · results/{self._session.subject}/")
        if self._session.flagged:
            self._banner.setText("⚑ Flagged — manual problem")
            self._banner.setStyleSheet(f"color: {self._theme.state_color(EffectiveState.FLAGGED)};")
        elif stale:
            self._banner.setText(f"⚠ {stale} step(s) stale — upstream edited")
            self._banner.setStyleSheet(f"color: {self._theme.state_color(EffectiveState.STALE)};")
        else:
            self._banner.setText(f"{done} / {len(required)} complete")
            self._banner.setStyleSheet(f"color: {self._theme.color('text-ter')};")
        for step, row in self._rows.items():
            error = self._session.step_error(step)
            log_available = error is not None or self._step_log_path(step) is not None
            row.set_state(states[step], self._meta_for(step), error, log_available=log_available)

    def _step_log_path(self, step: Step) -> Path | None:
        """The on-disk run log for a step, if it writes one (only MFA does), else None."""
        if self._session is None or step != Step.RUN_MFA:
            return None
        log = self._session.results_dir / "mfa_run.log"
        return log if log.exists() else None

    def _meta_for(self, step: Step) -> str:
        rec = self._session.manifest.steps.get(str(step)) if self._session else None
        if rec is not None and rec.state == "error":
            return "error — click the chip for details"
        if self._step_log_path(step) is not None:
            return (f"ran {rec.ran_at[:16].replace('T', ' ')} · " if rec and rec.ran_at else "") + (
                "click the chip for the run log"
            )
        if rec is not None and rec.ran_at:
            return f"ran {rec.ran_at[:16].replace('T', ' ')}"
        return ""

    def _on_step_action(self, step: Step) -> None:
        if self._session is None:
            return
        spec: StepSpec = _SPECS[step]
        # Manual steps and Denoise are done in the editor (Denoise needs the waveform to pick a
        # noise profile), so open it instead of running a headless action.
        if spec.kind == StepKind.MANUAL or step == Step.DENOISE:
            self.open_editor.emit(self._session, step)
            return
        # Single automated step: run inline (no popup) — just flip the row to "running".
        # Lazy import: the pipeline chain is only pulled when a step actually runs (faster startup).
        from rpcoding.core.runner import run_step

        self._rows[step].set_running()
        self._remember_log_for(step)
        self._set_status(f"Running {_SPECS[step].title}…")

        def done() -> None:
            self._remember_log_for(step)
            self._set_status(f"✓ {_SPECS[step].title} — done")
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
            self._remember_log_for(step)
            self._set_status(f"✗ {_SPECS[step].title} failed — click to view log")
            self._refresh_states()
            show_error(f"Step failed: {_SPECS[step].title}", message, parent=self)

        def report(fraction: float | None, message: str) -> None:
            # Called on the worker thread -> emit a signal so the row updates on the GUI thread.
            self._step_tick.emit(step, fraction, message)

        self._active = run_in_thread(
            self, run_step, self._session, step, report=report, on_finished=done, on_error=failed
        )

    def _on_step_progress(self, step: Step, fraction: float | None, message: str) -> None:
        row = self._rows.get(step)
        if row is not None:
            row.set_progress(fraction, message)

    def _show_error(self, step: Step) -> None:
        """Chip clicked: show this step's run log (MFA) and/or its recorded error."""
        if self._session is None:
            return
        parts: list[str] = []
        error = self._session.step_error(step)
        if error:
            parts.append(f"--- recorded error ---\n{error}")
        log = self._step_log_path(step)
        if log is not None:
            try:
                body = log.read_text(encoding="utf-8", errors="replace")
                parts.append(f"--- {log.name} ---\n{body}")
            except OSError as exc:
                parts.append(f"(could not read {log.name}: {exc})")
        text = (
            "\n\n".join(parts) if parts else "No error details or run log recorded for this step."
        )
        LogDialog(
            f"{_SPECS[step].title} — log",
            text,
            folder=self._session.results_dir,
            parent=self,
        ).exec()

    def _open_batch(self) -> None:
        from rpcoding.gui.batch_dialog import BatchDialog  # lazy: pulls the pipeline chain

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
