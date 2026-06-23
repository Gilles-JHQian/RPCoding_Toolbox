"""The optional denoise step is a registered no-op (external Audacity), runnable + records done."""

from __future__ import annotations

from rpcoding.core.config import AppConfig
from rpcoding.core.runner import DEFAULT_ACTIONS, run_step
from rpcoding.core.session import SubjectSession
from rpcoding.core.steps import Step
from rpcoding.core.tasks import Task


def test_denoise_registered_and_noop(tmp_path):
    assert Step.DENOISE in DEFAULT_ACTIONS
    cfg = AppConfig(droot=tmp_path)
    session = SubjectSession(cfg, Task.LEXICAL_NODELAY, "D1")
    assert DEFAULT_ACTIONS[Step.DENOISE](session) is None


def test_denoise_run_step_records_done(tmp_path):
    cfg = AppConfig(droot=tmp_path)
    session = SubjectSession(cfg, Task.LEXICAL_NODELAY, "D1")
    run_step(session, Step.DENOISE)  # no-op action, must not raise
    assert session.manifest.steps[str(Step.DENOISE)].state == "done"
