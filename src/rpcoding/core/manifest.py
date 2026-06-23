"""Per-subject manifest: step records + atomic JSON persistence."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from rpcoding.core.steps import Step


def fingerprint(path: Path | str) -> str | None:
    """Cheap content fingerprint (``size:mtime_ns``) without reading the file; None if absent.

    Returns None on any ``OSError`` (missing file, or a cloud-sync placeholder that can't be
    stat-ed — e.g. Box returns WinError 1006), so status checks never crash on synced data.
    """
    try:
        st = Path(path).stat()
    except OSError:
        return None
    return f"{st.st_size}:{st.st_mtime_ns}"


@dataclass
class StepRecord:
    state: str = "not_started"  # not_started | done | error
    outputs: dict[str, str | None] = field(default_factory=dict)
    dep_inputs: dict[str, str | None] = field(default_factory=dict)
    ran_at: str | None = None
    error: str | None = None


@dataclass
class Manifest:
    task: str
    subject: str
    steps: dict[str, StepRecord] = field(default_factory=dict)

    def record(self, step: Step) -> StepRecord:
        return self.steps.setdefault(str(step), StepRecord())

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "subject": self.subject,
            "steps": {k: asdict(v) for k, v in self.steps.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> Manifest:
        m = cls(task=d["task"], subject=d["subject"])
        for k, v in d.get("steps", {}).items():
            m.steps[k] = StepRecord(**v)
        return m

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8", newline="\n")
        os.replace(tmp, path)  # atomic on the same filesystem

    @classmethod
    def load(cls, path: Path | str) -> Manifest:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
