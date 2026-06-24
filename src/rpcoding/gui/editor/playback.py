"""Streaming audio playback for the editor (sounddevice / PortAudio).

Plays an arbitrary ``[start, end)`` window of a wav by streaming blocks from the file in the audio
callback — so playing from the cursor to the end (or the whole 50-min file) never loads it into RAM.
``finished`` is emitted on the UI thread when playback ends or is stopped; ``position`` reports the
current play time so the editor can animate a playhead. All sounddevice use is lazy/guarded, so the
module imports (and the editor runs) even without a working audio backend.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal


class AudioPlayer(QObject):
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stream = None
        self._file = None
        self._fs = 1
        self._start_frame = 0
        self._frames_done = 0
        self._remaining = 0

    def is_playing(self) -> bool:
        return self._stream is not None

    def position(self) -> float:
        """Current playback time in seconds."""
        return (self._start_frame + self._frames_done) / self._fs

    def play(self, wav_path: Path | str, start_sec: float, end_sec: float | None) -> None:
        """Play ``[start_sec, end_sec)`` (None = to the end). A no-op if it can't start."""
        self.stop()
        try:
            import sounddevice as sd
            import soundfile as sf

            f = sf.SoundFile(str(wav_path))
            self._fs = f.samplerate
            start = max(int(start_sec * self._fs), 0)
            end = len(f) if end_sec is None else min(int(end_sec * self._fs), len(f))
            if end <= start:
                f.close()
                return
            f.seek(start)
            self._file = f
            self._start_frame = start
            self._frames_done = 0
            self._remaining = end - start
            self._stream = sd.OutputStream(
                samplerate=self._fs,
                channels=1,
                dtype="float32",
                callback=self._make_callback(sd),
                finished_callback=self._on_finished,
            )
            self._stream.start()
        except Exception:  # noqa: BLE001 - no device / unreadable file: stay silent, reset state
            self.stop()
            self.finished.emit()

    def _make_callback(self, sd):
        def callback(outdata, frames, _time, _status):
            f = self._file
            if f is None or self._remaining <= 0:
                raise sd.CallbackStop
            n = min(frames, self._remaining)
            data = f.read(n, dtype="float32", always_2d=True)
            got = len(data)
            outdata[:got, 0] = data[:, 0]
            if got < frames:
                outdata[got:, 0] = 0.0
            self._remaining -= got
            self._frames_done += got
            if got == 0 or self._remaining <= 0:
                raise sd.CallbackStop

        return callback

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # noqa: BLE001
                pass
        if self._file is not None:
            try:
                self._file.close()
            except Exception:  # noqa: BLE001
                pass
            self._file = None

    def _on_finished(self) -> None:
        # Called from the PortAudio thread; the queued connection runs the slot on the UI thread.
        if self._file is not None:
            try:
                self._file.close()
            except Exception:  # noqa: BLE001
                pass
            self._file = None
        self._stream = None
        self.finished.emit()
