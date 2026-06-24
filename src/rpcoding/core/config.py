"""Application configuration (data root + MFA task map), persisted as JSON.

JSON (stdlib) is used for the on-disk format for robust, dependency-free round-tripping.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from rpcoding.core.tasks import DEFAULT_MFA_TASK_MAP, Task


@dataclass
class AppConfig:
    """User/site configuration. ``droot`` is the CoganLab data root (``$BOX/CoganLab``)."""

    droot: Path
    # app-task name -> MFA task-config name (or None). Overrides merged over the defaults.
    mfa_task_map: dict[str, str | None] = field(default_factory=dict)
    # word / nonword stimulus lists (``*.mat``); required for the write-Trials step.
    word_list: Path | None = None
    nonword_list: Path | None = None
    # After MFA, load the MFA-denoised allblocks.wav in the editor? Default: the preserved original.
    editor_use_processed_audio: bool = False

    def __post_init__(self) -> None:
        self.droot = Path(self.droot)
        if self.word_list is not None:
            self.word_list = Path(self.word_list)
        if self.nonword_list is not None:
            self.nonword_list = Path(self.nonword_list)
        merged: dict[str, str | None] = {t.value: name for t, name in DEFAULT_MFA_TASK_MAP.items()}
        merged.update(self.mfa_task_map)
        self.mfa_task_map = merged

    def mfa_task(self, task: Task | str) -> str | None:
        """MFA task-config name for an app task, or None if not configured."""
        key = task.value if isinstance(task, Task) else str(task)
        return self.mfa_task_map.get(key)

    # ---- persistence ----
    def to_dict(self) -> dict:
        return {
            "droot": str(self.droot),
            "mfa_task_map": self.mfa_task_map,
            "word_list": str(self.word_list) if self.word_list is not None else None,
            "nonword_list": str(self.nonword_list) if self.nonword_list is not None else None,
            "editor_use_processed_audio": self.editor_use_processed_audio,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AppConfig:
        word_list = data.get("word_list")
        nonword_list = data.get("nonword_list")
        return cls(
            droot=Path(data["droot"]),
            mfa_task_map=dict(data.get("mfa_task_map", {})),
            word_list=Path(word_list) if word_list else None,
            nonword_list=Path(nonword_list) if nonword_list else None,
            editor_use_processed_audio=bool(data.get("editor_use_processed_audio", False)),
        )

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8", newline="\n")

    @classmethod
    def load(cls, path: Path | str) -> AppConfig:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)
