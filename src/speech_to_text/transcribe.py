from __future__ import annotations

import logging
import os
import re

import numpy as np
from pywhispercpp.model import Model

log = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s+")


class Transcriber:
    def __init__(self, model_path: str, n_threads: int | None = None) -> None:
        self._model_path = model_path
        self._n_threads = n_threads or max(1, (os.cpu_count() or 4) // 2)
        self._model: Model | None = None

    def load(self) -> None:
        """Eagerly load the model so subsequent transcriptions don't pay the
        cost. Lets the daemon fail fast at startup if the model is missing or
        corrupt instead of degrading silently on the first dictation."""
        if self._model is None:
            log.info("Loading whisper model: %s", self._model_path)
            # whisper.cpp's C-side `whisper_full_default_params` defaults
            # `language` to "en", which forces English output regardless of
            # what was actually spoken. For a multilingual model that means
            # Portuguese audio comes back as English-text "translation". We
            # explicitly request auto-detect so each utterance is transcribed
            # in its source language.
            self._model = Model(
                self._model_path,
                n_threads=self._n_threads,
                language="auto",
            )

    def transcribe(self, samples: np.ndarray) -> str:
        if samples.size == 0:
            return ""
        self.load()
        assert self._model is not None
        segments = self._model.transcribe(samples)
        joined = "".join(seg.text for seg in segments)
        return _WHITESPACE.sub(" ", joined).strip()
