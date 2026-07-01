"""Settings dialog: data root, word/nonword lists, per-task MFA config map, and MFA setup.

Builds a new :class:`AppConfig` from the form on accept (``result_config``); the caller persists it
and refreshes any open sessions. The MFA section probes the install (engine / model / dictionaries /
denoise dep) and offers a one-click download+install that runs off the UI thread.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rpcoding.core.config import AppConfig
from rpcoding.core.mfa.models import ensure_mfa_setup, mfa_status
from rpcoding.core.steps import EffectiveState
from rpcoding.core.tasks import Task
from rpcoding.gui.theme import DARK_THEME, Theme
from rpcoding.gui.workers.worker import run_in_thread


class _PathField(QWidget):
    """A line edit + Browse button for a file or directory path."""

    def __init__(
        self, value: str = "", *, directory: bool, caption: str, placeholder: str = "", parent=None
    ):
        super().__init__(parent)
        self._directory = directory
        self._caption = caption
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._edit = QLineEdit(value)
        self._edit.setPlaceholderText(placeholder)
        lay.addWidget(self._edit, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        lay.addWidget(browse)

    def _browse(self) -> None:
        if self._directory:
            chosen = QFileDialog.getExistingDirectory(self, self._caption, self._edit.text())
        else:
            chosen, _ = QFileDialog.getOpenFileName(
                self, self._caption, self._edit.text(), "MATLAB files (*.mat);;All files (*)"
            )
        if chosen:
            self._edit.setText(chosen)

    def text(self) -> str:
        return self._edit.text().strip()


class SettingsDialog(QDialog):
    # exec() result codes for the anomaly-handling gadgets (vs Accepted=1 / Rejected=0).
    FIX_CLOCK = 2
    MERGE_MULTIPART = 3
    FIX_TRIGGER = 4

    def __init__(self, config: AppConfig, theme: Theme | None = None, parent=None):
        super().__init__(parent)
        self._theme = theme or DARK_THEME
        self._install_err: str | None = None
        self.setWindowTitle("Settings")
        self.resize(560, 520)

        outer = QVBoxLayout(self)
        form = QFormLayout()
        outer.addLayout(form)

        self._droot = _PathField(
            str(config.droot), directory=True, caption="CoganLab data root ($BOX/CoganLab)"
        )
        form.addRow("Data root", self._droot)

        self._word = _PathField(
            str(config.word_list) if config.word_list else "",
            directory=False,
            caption="Word list (.mat)",
            placeholder="blank → bundled lab word_lst.mat",
        )
        form.addRow("Word list", self._word)
        self._nonword = _PathField(
            str(config.nonword_list) if config.nonword_list else "",
            directory=False,
            caption="Nonword list (.mat)",
            placeholder="blank → bundled lab nonword_lst.mat",
        )
        form.addRow("Nonword list", self._nonword)

        outer.addWidget(QLabel("MFA task config (blank = unmapped)"))
        mfa_form = QFormLayout()
        outer.addLayout(mfa_form)
        self._mfa: dict[str, QLineEdit] = {}
        for task in Task:
            edit = QLineEdit(config.mfa_task(task) or "")
            self._mfa[task.value] = edit
            mfa_form.addRow(task.value, edit)

        outer.addWidget(self._build_mfa_group())
        self._use_processed.setChecked(config.editor_use_processed_audio)

        outer.addWidget(self._build_anomaly_group())

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

        self._render_mfa_status()

    # ---- MFA setup section ----
    def _build_mfa_group(self) -> QGroupBox:
        group = QGroupBox("Montreal Forced Aligner")
        gl = QVBoxLayout(group)
        self._mfa_status_box = QWidget()
        self._mfa_status_lay = QVBoxLayout(self._mfa_status_box)
        self._mfa_status_lay.setContentsMargins(0, 0, 0, 0)
        self._mfa_status_lay.setSpacing(3)
        gl.addWidget(self._mfa_status_box)

        row = QHBoxLayout()
        self._mfa_install_btn = QPushButton("Download & install models")
        self._mfa_install_btn.clicked.connect(self._install_mfa)
        self._mfa_recheck_btn = QPushButton("Re-check")
        self._mfa_recheck_btn.clicked.connect(self._render_mfa_status)
        row.addWidget(self._mfa_install_btn)
        row.addWidget(self._mfa_recheck_btn)
        row.addStretch(1)
        gl.addLayout(row)

        self._mfa_status_line = QLabel("")
        self._mfa_status_line.setObjectName("Secondary")
        self._mfa_status_line.setWordWrap(True)
        gl.addWidget(self._mfa_status_line)

        self._use_processed = QCheckBox("Load the MFA-denoised audio in the editor")
        self._use_processed.setToolTip(
            "MFA denoises allblocks.wav and keeps the original as allblocks_original.wav.\n"
            "Off (default): the editor loads the original; on: it loads the denoised audio."
        )
        gl.addWidget(self._use_processed)
        return group

    # ---- anomaly handling section ----
    def _build_anomaly_group(self) -> QGroupBox:
        group = QGroupBox("异常处理 · Anomaly handling")
        gl = QVBoxLayout(group)
        gl.addWidget(QLabel("Tools for subjects whose upstream data needs manual correction."))
        row = QHBoxLayout()
        btn = QPushButton("修复时钟差异 · Fix clock drift…")
        btn.setToolTip(
            "Mark each block's true first/last stimulus position on the audio; the tool fits the\n"
            "EDF-trigger vs allblocks.wav clock drift and corrects the cue/condition events."
        )
        btn.clicked.connect(lambda: self.done(self.FIX_CLOCK))
        row.addWidget(btn)
        merge_btn = QPushButton("合并分段录制 · Merge multi-part files…")
        merge_btn.setToolTip(
            "For subjects recorded in >1 part, combine the numbered Trials1/2, trialInfo1/2 and\n"
            "experiment1/2 into single Trials.mat / trialInfo.mat / experiment.mat in D_Data."
        )
        merge_btn.clicked.connect(lambda: self.done(self.MERGE_MULTIPART))
        row.addWidget(merge_btn)
        trig_btn = QPushButton("修复触发错位 · Fix trigger misalignment…")
        trig_btn.setToolTip(
            "For subjects whose Trials.Auditory is off by a mis-counted trigger: re-detect the\n"
            "raw trigger.mat pulses and align them to trialInfo, then write a corrected\n"
            "Trials.mat and regenerate the cue/condition events."
        )
        trig_btn.clicked.connect(lambda: self.done(self.FIX_TRIGGER))
        row.addWidget(trig_btn)
        row.addStretch(1)
        gl.addLayout(row)
        return group

    def _render_mfa_status(self):
        while self._mfa_status_lay.count():
            item = self._mfa_status_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        status = mfa_status()
        ok_c = self._theme.state_color(EffectiveState.DONE)
        bad_c = self._theme.state_color(EffectiveState.ERROR)
        ter = self._theme.color("text-ter")
        for c in status.checks:
            glyph, col = ("✓", ok_c) if c.ok else ("✗", bad_c)
            lbl = QLabel(
                f'<span style="color:{col};">{glyph}</span> {c.label} '
                f'<span style="color:{ter};">— {c.detail}</span>'
            )
            self._mfa_status_lay.addWidget(lbl)
        self._mfa_install_btn.setText(
            "Re-install / repair" if status.complete else "Download & install models"
        )
        return status

    def _install_mfa(self) -> None:
        # Disable everything while the (multi-minute, network) install runs off the UI thread, so
        # the dialog can't be closed out from under the worker's completion callback.
        for w in (self._mfa_install_btn, self._mfa_recheck_btn, self._buttons):
            w.setEnabled(False)
        self._install_err = None
        self._mfa_status_line.setText(
            "Installing… downloading the acoustic model + dictionaries (~100 MB). "
            "This can take a few minutes."
        )
        run_in_thread(
            self,
            ensure_mfa_setup,
            on_error=self._on_install_error,
            on_finished=self._on_install_done,
        )

    def _on_install_error(self, message: str) -> None:
        self._install_err = message

    def _on_install_done(self) -> None:
        for w in (self._mfa_install_btn, self._mfa_recheck_btn, self._buttons):
            w.setEnabled(True)
        status = self._render_mfa_status()
        if self._install_err:
            self._mfa_status_line.setText(f"Install failed: {self._install_err}")
        elif status.complete:
            self._mfa_status_line.setText("✓ MFA is ready.")
        else:
            self._mfa_status_line.setText("Some items are still missing — see the list above.")

    def result_config(self) -> AppConfig:
        """Build an :class:`AppConfig` from the current field values."""
        task_map = {name: (edit.text().strip() or None) for name, edit in self._mfa.items()}
        return AppConfig(
            droot=Path(self._droot.text()),
            mfa_task_map=task_map,
            word_list=Path(self._word.text()) if self._word.text() else None,
            nonword_list=Path(self._nonword.text()) if self._nonword.text() else None,
            editor_use_processed_audio=self._use_processed.isChecked(),
        )
