"""Log-frequency spectrogram: chunked STFT -> dB -> fixed log-freq grid, memmapped; pool + slice.

Storage is the **pre-resampled** log-frequency grid ``(n_rows, n_frames)`` float32 (not the
linear FFT), so display is a trivial linear ImageItem and the 80-200 Hz rows are filled. For
~135M samples at the default params this is ~263,668 frames, ~270 MB on disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b
from pathlib import Path

import numpy as np
from numpy.lib.format import open_memmap

# Imported at module load (main thread): a *first* scipy import on the spectrogram worker thread
# (where build_log_spectrogram runs) is an access violation with scipy's C extensions.
from scipy.signal import stft

SPECTRO_VERSION = 1


@dataclass(frozen=True)
class StftParams:
    n_fft: int = 2048
    hop: int = 512
    f_lo: float = 80.0
    f_hi: float = 8000.0
    n_rows: int = 256

    def key(self) -> str:
        raw = f"v{SPECTRO_VERSION}_{self.n_fft}_{self.hop}_{self.f_lo}_{self.f_hi}_{self.n_rows}"
        return blake2b(raw.encode(), digest_size=6).hexdigest()


def n_frames(n_samples: int, n_fft: int, hop: int) -> int:
    """Number of STFT frames (boundary=None, padded=False)."""
    return 0 if n_samples < n_fft else 1 + (n_samples - n_fft) // hop


def frame_time_offset(n_fft: int, hop: int, fs: float) -> float:
    """Seconds to shift the spectrogram so each column's cell is centred on its window centre.

    ``scipy.signal.stft(boundary=None)`` centres frame ``c`` on sample ``c*hop + n_fft/2``, so a
    column drawn naively at ``c*dt`` (its window's *start*) lands ``(n_fft - hop) / (2*fs)`` s too
    early against the sample-accurate waveform. Adding this offset aligns the two.
    """
    return (n_fft - hop) / (2.0 * fs)


def db_magnitude(mag: np.ndarray, floor: float = 1e-10) -> np.ndarray:
    """20*log10(|mag| + floor) as float32 (|mag|=1 -> 0 dB, |mag|=0 -> ~-200 dB, finite)."""
    return (20.0 * np.log10(np.abs(mag) + floor)).astype(np.float32)


def _log_interp_weights(lin_f: np.ndarray, log_f: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    idx = np.clip(np.searchsorted(lin_f, log_f) - 1, 0, len(lin_f) - 2)
    f0 = lin_f[idx]
    f1 = lin_f[idx + 1]
    frac = np.clip((log_f - f0) / (f1 - f0), 0.0, 1.0).astype(np.float32)
    return idx.astype(np.int64), frac


def _interp_to_log(db: np.ndarray, idx: np.ndarray, frac: np.ndarray) -> np.ndarray:
    return db[idx] * (1.0 - frac[:, None]) + db[idx + 1] * frac[:, None]


def pool_columns_max(block: np.ndarray, w_px: int) -> np.ndarray:
    """Max-pool time columns to <= ``w_px`` (preserves peaks). Identity when narrow enough."""
    ncols = block.shape[1]
    if w_px <= 0 or ncols <= w_px:
        return block
    starts = np.linspace(0, ncols, w_px + 1).astype(np.int64)[:-1]
    return np.maximum.reduceat(block, starts, axis=1).astype(block.dtype)


def slice_spectro(mmap, t0: float, t1: float, dt: float, w_px: int, t_offset: float = 0.0):
    """Slice the memmap to the visible time window and max-pool to viewport width.

    ``t_offset`` (see :func:`frame_time_offset`) shifts column time so frames sit under the matching
    waveform; columns are chosen for ``[t0, t1]`` in shifted time and the returned x bounds carry
    the same shift. Returns ``(image, x0_seconds, x1_seconds, n_rows)``.
    """
    nf = mmap.shape[1]
    c0 = max(int(np.floor((t0 - t_offset) / dt)), 0)
    c1 = min(int(np.ceil((t1 - t_offset) / dt)) + 1, nf)
    if c1 <= c0:
        c1 = min(c0 + 1, nf)
    block = np.ascontiguousarray(mmap[:, c0:c1])
    return pool_columns_max(block, w_px), c0 * dt + t_offset, c1 * dt + t_offset, mmap.shape[0]


def build_log_spectrogram(
    wav_path, out_path, params: StftParams | None = None, progress=None
) -> dict:
    """Build the memmapped log-spectrogram; returns a meta dict (shape, dt, p2/p98, ...)."""
    import soundfile as sf

    params = params or StftParams()
    info = sf.info(str(wav_path))
    fs = info.samplerate
    total = info.frames
    nf = n_frames(total, params.n_fft, params.hop)

    lin_f = np.fft.rfftfreq(params.n_fft, 1.0 / fs)
    log_f = np.geomspace(params.f_lo, params.f_hi, params.n_rows)
    idx, frac = _log_interp_weights(lin_f, log_f)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mm = open_memmap(out_path, mode="w+", dtype=np.float32, shape=(params.n_rows, max(nf, 1)))

    noverlap = params.n_fft - params.hop
    chunk = 20000  # frames per chunk -> ~10M samples read at a time
    subs: list[np.ndarray] = []
    f0 = 0
    while f0 < nf:
        f1 = min(f0 + chunk, nf)
        s0 = f0 * params.hop
        s1 = (f1 - 1) * params.hop + params.n_fft
        block, _ = sf.read(
            str(wav_path), start=s0, frames=s1 - s0, dtype="float32", always_2d=False
        )
        if block.ndim == 2:
            block = block[:, 0]
        _, _, z = stft(
            block, fs=fs, nperseg=params.n_fft, noverlap=noverlap, boundary=None, padded=False
        )
        logd = _interp_to_log(db_magnitude(z), idx, frac).astype(np.float32)
        m = min(logd.shape[1], f1 - f0)
        mm[:, f0 : f0 + m] = logd[:, :m]
        if logd.size:
            subs.append(logd[:, ::97].ravel())
        f0 = f1
        if progress is not None and nf:
            progress(int(100 * f1 / nf), "Building spectrogram")
    mm.flush()

    allvals = np.concatenate(subs) if subs else np.array([0.0, 1.0], np.float32)
    return {
        "version": SPECTRO_VERSION,
        "shape": [params.n_rows, nf],
        "dtype": "float32",
        "fs": int(fs),
        "n_fft": params.n_fft,
        "hop": params.hop,
        "dt": params.hop / fs,
        "t_offset": frame_time_offset(params.n_fft, params.hop, fs),
        "f_lo": params.f_lo,
        "f_hi": params.f_hi,
        "n_rows": params.n_rows,
        "p2": float(np.percentile(allvals, 2)),
        "p98": float(np.percentile(allvals, 98)),
    }
