from __future__ import annotations

import logging
import queue
from typing import Any

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)


class Recorder:
    def __init__(self, sample_rate: int = 16000, input_device: str | None = None) -> None:
        self._sample_rate = sample_rate
        self._input_device = input_device if input_device and input_device != "default" else None
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: Any | None = None
        self._frames_captured = 0

    def start(self) -> None:
        if self._stream is not None:
            return
        self._queue = queue.Queue()
        self._frames_captured = 0
        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            blocksize=1024,
            device=self._input_device,
            callback=self._on_audio,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is None:
            return np.array([], dtype=np.float32)
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None

        chunks: list[np.ndarray] = []
        while True:
            try:
                chunks.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if not chunks:
            return np.array([], dtype=np.float32)
        return np.concatenate(chunks).flatten().astype(np.float32, copy=False)

    @property
    def duration_seconds(self) -> float:
        return self._frames_captured / self._sample_rate

    def _on_audio(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            log.debug("sounddevice status: %s", status)
        self._queue.put(indata.copy())
        self._frames_captured += frames
