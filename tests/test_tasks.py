"""Tests for the Task enum and MFA task map."""

from __future__ import annotations

import pytest

from rpcoding.core.tasks import DEFAULT_MFA_TASK_MAP, Task


def test_from_str():
    assert Task.from_str("LexicalDecRepDelay") is Task.LEXICAL_DELAY
    with pytest.raises(ValueError):
        Task.from_str("NotATask")


def test_map_covers_all_tasks():
    assert set(DEFAULT_MFA_TASK_MAP) == set(Task)
    assert DEFAULT_MFA_TASK_MAP[Task.LEXICAL_NODELAY] == "lexical_repeat_no_delay"
    assert DEFAULT_MFA_TASK_MAP[Task.LEXICAL_DELAY] == "lexical_repeat"
    assert DEFAULT_MFA_TASK_MAP[Task.UNIQUENESS_POINT] == "uniqueness_point"
