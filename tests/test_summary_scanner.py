"""SubjectSummaryScanner: parallel, off-UI-thread subject status with generation cancellation."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from rpcoding.core.config import AppConfig
from rpcoding.core.tasks import Task
from rpcoding.gui.workers.summary_scanner import SubjectSummaryScanner


def test_scanner_streams_each_subject_then_finishes(qtbot, tmp_path):
    scanner = SubjectSummaryScanner(AppConfig(droot=tmp_path))
    got: list[str] = []
    finished: list[int] = []
    scanner.subject_ready.connect(lambda gen, sid, *rest: got.append(sid))
    scanner.scan_finished.connect(finished.append)

    gen = scanner.start(Task.LEXICAL_NODELAY, ["D1", "D2", "D3"])
    qtbot.waitUntil(lambda: len(finished) == 1, timeout=3000)

    assert set(got) == {"D1", "D2", "D3"}  # every subject reported (results run on pool threads)
    assert finished == [gen]  # finished fires once, for this generation
    scanner.shutdown()


def test_scanner_empty_list_finishes_immediately(qtbot, tmp_path):
    scanner = SubjectSummaryScanner(AppConfig(droot=tmp_path))
    finished: list[int] = []
    scanner.scan_finished.connect(finished.append)
    gen = scanner.start(Task.LEXICAL_NODELAY, [])
    assert finished == [gen]
    scanner.shutdown()


def test_scanner_rescan_drops_stale_generation(qtbot, tmp_path):
    scanner = SubjectSummaryScanner(AppConfig(droot=tmp_path))
    seen_gens: list[int] = []
    scanner.subject_ready.connect(lambda gen, *rest: seen_gens.append(gen))

    gen_a = scanner.start(Task.LEXICAL_NODELAY, [f"A{i}" for i in range(8)])
    gen_b = scanner.start(Task.LEXICAL_DELAY, [f"B{i}" for i in range(8)])  # supersede immediately
    assert gen_b != gen_a

    qtbot.waitUntil(lambda: gen_b in seen_gens, timeout=3000)
    qtbot.wait(50)  # let any stale gen_a results arrive and be dropped
    assert all(g == gen_b for g in seen_gens)  # no result from the superseded scan is re-emitted
    scanner.shutdown()


def test_scanner_shutdown_is_clean_and_silences_late_results(qtbot, tmp_path):
    scanner = SubjectSummaryScanner(AppConfig(droot=tmp_path))
    scanner.start(Task.LEXICAL_NODELAY, [f"D{i}" for i in range(20)])
    scanner.shutdown()  # cancels + waits; must return without hanging

    fired: list[tuple] = []
    scanner.subject_ready.connect(lambda *a: fired.append(a))
    qtbot.wait(50)
    assert fired == []  # nothing emits after shutdown
