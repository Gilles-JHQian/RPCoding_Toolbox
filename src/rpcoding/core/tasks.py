"""Task identifiers and the mapping from app task -> MFA pipeline task config."""

from __future__ import annotations

from enum import StrEnum


class Task(StrEnum):
    """Supported response-coding tasks (value = on-disk folder name under D_Data)."""

    LEXICAL_NODELAY = "LexicalDecRepNoDelay"
    LEXICAL_DELAY = "LexicalDecRepDelay"
    UNIQUENESS_POINT = "Uniqueness_Point"

    @classmethod
    def from_str(cls, value: str) -> Task:
        """Look up a task by its on-disk name; raises ValueError if unknown."""
        return cls(value)


# Default app-task -> MFA pipeline task-config name (conf/task/<name>.yaml).
# Configurable/extensible: Uniqueness_Point's config is supplied by the user later, so it maps
# to None until then.
DEFAULT_MFA_TASK_MAP: dict[Task, str | None] = {
    Task.LEXICAL_NODELAY: "lexical_repeat_no_delay",
    Task.LEXICAL_DELAY: "lexical_repeat",
    Task.UNIQUENESS_POINT: None,
}

# The raw-acquisition tree (Cogan_Task_Data) uses human-readable folder names with spaces,
# distinct from the task id used under D_Data / results.
COGAN_TASK_FOLDER: dict[Task, str] = {
    Task.LEXICAL_NODELAY: "Lexical No Delay",
    Task.LEXICAL_DELAY: "Lexical Delay",
    Task.UNIQUENESS_POINT: "Uniqueness Point",
}
