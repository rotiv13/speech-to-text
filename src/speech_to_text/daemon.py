from __future__ import annotations

import enum
import logging
import threading
from typing import Callable

log = logging.getLogger(__name__)


class State(enum.Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    PASTING = "pasting"


class Daemon:
    def __init__(
        self,
        hotkeys,
        audio,
        transcriber,
        paster,
        sounds,
        notifier: Callable[[str, str], None],
        min_duration_ms: int = 400,
        max_duration_ms: int = 300_000,
    ) -> None:
        self._hotkeys = hotkeys
        self._audio = audio
        self._transcriber = transcriber
        self._paster = paster
        self._sounds = sounds
        self._notifier = notifier
        self._min_duration_s = min_duration_ms / 1000.0
        self._max_duration_s = max_duration_ms / 1000.0
        self._state = State.IDLE
        self._lock = threading.Lock()

    @property
    def state(self) -> State:
        return self._state

    def on_ptt_press(self) -> None:
        with self._lock:
            if self._state == State.IDLE:
                self._start_recording()

    def on_ptt_release(self) -> None:
        with self._lock:
            if self._state == State.RECORDING:
                self._stop_and_process()

    def on_toggle(self) -> None:
        with self._lock:
            if self._state == State.IDLE:
                self._start_recording()
            elif self._state == State.RECORDING:
                self._stop_and_process()
            # If TRANSCRIBING or PASTING, ignore — too late to cancel cleanly

    def on_max_duration_check(self) -> None:
        """Periodic call from a watchdog timer; force-stops over-long recordings."""
        with self._lock:
            if (
                self._state == State.RECORDING
                and self._audio.duration_seconds >= self._max_duration_s
            ):
                log.warning(
                    "Recording exceeded max duration (%ss); hard-stopping",
                    self._max_duration_s,
                )
                self._stop_and_process()

    def _start_recording(self) -> None:
        try:
            self._audio.start()
        except Exception as e:
            log.exception("Failed to start audio capture: %s", e)
            self._sounds.play("error.wav")
            self._notifier(
                "Speech-to-Text",
                f"Couldn't start microphone: {e}. "
                "Check System Settings → Privacy & Security → Microphone.",
            )
            self._state = State.IDLE
            return
        self._state = State.RECORDING
        self._sounds.play("tink.wav")

    def _stop_and_process(self) -> None:
        duration = self._audio.duration_seconds
        samples = self._audio.stop()
        self._state = State.TRANSCRIBING

        if duration < self._min_duration_s or samples.size == 0:
            log.debug("Recording too short (%.3fs); discarding", duration)
            self._state = State.IDLE
            return

        try:
            text = self._transcriber.transcribe(samples)
        except Exception as e:
            log.exception("Transcription failed: %s", e)
            self._sounds.play("error.wav")
            self._notifier("Speech-to-Text", f"Transcription failed: {e}")
            self._state = State.IDLE
            return

        if not text:
            log.debug("Empty transcription; ignoring")
            self._state = State.IDLE
            return

        self._state = State.PASTING
        try:
            ok = self._paster.paste(text)
        except Exception as e:
            log.exception("Paste failed: %s", e)
            self._sounds.play("error.wav")
            self._notifier(
                "Speech-to-Text",
                f"Transcribed but couldn't paste: {e}. Text is on your clipboard.",
            )
            self._state = State.IDLE
            return

        if not ok:
            self._sounds.play("error.wav")
            self._notifier(
                "Speech-to-Text",
                "Transcribed but couldn't paste. Text is on your clipboard.",
            )
        else:
            self._sounds.play("ding.wav")
        self._state = State.IDLE
