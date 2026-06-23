"""Cheap, stable content hash for large audio files (for cache keys)."""

from __future__ import annotations

import hashlib
from pathlib import Path


def content_hash(path: Path | str, probe_bytes: int = 1 << 20, n_probes: int = 8) -> str:
    """blake2b(16-hex) over file size, mtime, and ``n_probes`` strided ``probe_bytes`` chunks.

    Milliseconds even on a 270 MB file. Not adversarial — it guards against the wav being
    regenerated, not against deliberate collisions.
    """
    p = Path(path)
    st = p.stat()
    h = hashlib.blake2b(digest_size=8)
    h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
    with open(p, "rb") as f:
        if st.st_size <= probe_bytes * n_probes:
            h.update(f.read())
        else:
            step = st.st_size // n_probes
            for i in range(n_probes):
                f.seek(i * step)
                h.update(f.read(probe_bytes))
    return h.hexdigest()
