from unittest.mock import MagicMock

import numpy as np
import pytest

from speech_to_text.daemon import Daemon, State


@pytest.fixture
def deps():
    audio = MagicMock()
    transcriber = MagicMock()
    paster = MagicMock()
    sounds = MagicMock()
    notifier = MagicMock()
    hotkeys = MagicMock()

    audio.duration_seconds = 1.0
    audio.stop.return_value = np.ones(16000, dtype=np.float32)
    transcriber.transcribe.return_value = "hello world"
    paster.paste.return_value = True

    return {
        "audio": audio,
        "transcriber": transcriber,
        "paster": paster,
        "sounds": sounds,
        "notifier": notifier,
        "hotkeys": hotkeys,
    }


def _make_daemon(deps, min_ms=400, max_ms=300_000):
    return Daemon(
        hotkeys=deps["hotkeys"],
        audio=deps["audio"],
        transcriber=deps["transcriber"],
        paster=deps["paster"],
        sounds=deps["sounds"],
        notifier=deps["notifier"],
        min_duration_ms=min_ms,
        max_duration_ms=max_ms,
    )


def test_idle_to_recording_on_ptt_press(deps):
    d = _make_daemon(deps)
    d.on_ptt_press()
    assert d.state == State.RECORDING
    deps["audio"].start.assert_called_once()
    deps["sounds"].play.assert_called_with("tink.wav")


def test_full_happy_path(deps):
    d = _make_daemon(deps)
    d.on_ptt_press()
    d.on_ptt_release()
    deps["audio"].stop.assert_called_once()
    deps["transcriber"].transcribe.assert_called_once()
    deps["paster"].paste.assert_called_once_with("hello world")
    deps["sounds"].play.assert_any_call("ding.wav")
    assert d.state == State.IDLE


def test_too_short_recording_silently_returns_to_idle(deps):
    deps["audio"].duration_seconds = 0.1  # 100 ms — below 400 ms threshold
    deps["audio"].stop.return_value = np.zeros(1600, dtype=np.float32)
    d = _make_daemon(deps, min_ms=400)
    d.on_ptt_press()
    d.on_ptt_release()
    deps["transcriber"].transcribe.assert_not_called()
    deps["paster"].paste.assert_not_called()
    deps["notifier"].assert_not_called()
    sound_calls = [c.args[0] for c in deps["sounds"].play.call_args_list]
    assert "error.wav" not in sound_calls
    assert d.state == State.IDLE


def test_empty_transcription_returns_to_idle_silently(deps):
    deps["transcriber"].transcribe.return_value = ""
    d = _make_daemon(deps)
    d.on_ptt_press()
    d.on_ptt_release()
    deps["paster"].paste.assert_not_called()
    sound_calls = [c.args[0] for c in deps["sounds"].play.call_args_list]
    assert "error.wav" not in sound_calls
    assert d.state == State.IDLE


def test_paste_failure_plays_error_and_notifies(deps):
    deps["paster"].paste.return_value = False
    d = _make_daemon(deps)
    d.on_ptt_press()
    d.on_ptt_release()
    deps["sounds"].play.assert_any_call("error.wav")
    deps["notifier"].assert_called()
    assert d.state == State.IDLE


def test_transcription_exception_returns_to_idle_with_error(deps):
    deps["transcriber"].transcribe.side_effect = RuntimeError("whisper boom")
    d = _make_daemon(deps)
    d.on_ptt_press()
    d.on_ptt_release()
    deps["sounds"].play.assert_any_call("error.wav")
    deps["notifier"].assert_called()
    deps["paster"].paste.assert_not_called()
    assert d.state == State.IDLE


def test_toggle_starts_recording_when_idle(deps):
    d = _make_daemon(deps)
    d.on_toggle()
    assert d.state == State.RECORDING
    deps["audio"].start.assert_called_once()


def test_toggle_stops_recording_when_recording(deps):
    d = _make_daemon(deps)
    d.on_toggle()
    d.on_toggle()
    deps["paster"].paste.assert_called_once()
    assert d.state == State.IDLE


def test_max_duration_hard_stops(deps):
    deps["audio"].duration_seconds = 400.0  # 400 s, above 300 s max
    d = _make_daemon(deps, max_ms=300_000)
    d.on_ptt_press()
    d.on_max_duration_check()
    deps["audio"].stop.assert_called_once()


def test_audio_start_failure_returns_to_idle_with_error(deps):
    """Mic permission denied or device unavailable: notify + error sound, state IDLE."""
    deps["audio"].start.side_effect = OSError("mic permission denied")
    d = _make_daemon(deps)
    d.on_ptt_press()
    deps["sounds"].play.assert_any_call("error.wav")
    deps["notifier"].assert_called()
    assert d.state == State.IDLE
