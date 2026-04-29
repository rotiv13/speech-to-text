from pathlib import Path

import numpy as np
import pytest

from speech_to_text.transcribe import Transcriber


def test_loads_model_lazily_then_transcribes(mocker):
    fake_model_cls = mocker.patch("speech_to_text.transcribe.Model")
    fake_model = fake_model_cls.return_value
    fake_seg = mocker.MagicMock()
    fake_seg.text = " hello world "
    fake_model.transcribe.return_value = [fake_seg]

    t = Transcriber("/fake/model.bin")
    fake_model_cls.assert_not_called()  # lazy

    samples = np.zeros(16000, dtype=np.float32)
    text = t.transcribe(samples)

    fake_model_cls.assert_called_once_with(
        "/fake/model.bin",
        n_threads=mocker.ANY,
        language="auto",
    )
    fake_model.transcribe.assert_called_once()
    np.testing.assert_array_equal(fake_model.transcribe.call_args[0][0], samples)
    assert text == "hello world"


def test_model_constructed_with_auto_language(mocker):
    """Regression: whisper.cpp defaults language to 'en'. Without explicit
    'auto', a multilingual model force-transcribes Portuguese as English."""
    fake_model_cls = mocker.patch("speech_to_text.transcribe.Model")
    t = Transcriber("/fake/model.bin")
    t.load()
    kwargs = fake_model_cls.call_args.kwargs
    assert kwargs.get("language") == "auto", (
        "Transcriber must pass language='auto' so multilingual models "
        "auto-detect per utterance instead of defaulting to English."
    )


def test_concatenates_multiple_segments(mocker):
    fake_model_cls = mocker.patch("speech_to_text.transcribe.Model")
    fake_model = fake_model_cls.return_value

    def make_seg(s):
        m = mocker.MagicMock()
        m.text = s
        return m

    fake_model.transcribe.return_value = [make_seg(" the quick "), make_seg(" brown fox.")]

    t = Transcriber("/fake/model.bin")
    text = t.transcribe(np.zeros(16000, dtype=np.float32))
    assert text == "the quick brown fox."


def test_empty_audio_returns_empty_string(mocker):
    mocker.patch("speech_to_text.transcribe.Model")
    t = Transcriber("/fake/model.bin")
    text = t.transcribe(np.array([], dtype=np.float32))
    assert text == ""


def test_model_load_failure_raises_on_first_use(mocker):
    mocker.patch(
        "speech_to_text.transcribe.Model",
        side_effect=RuntimeError("model file corrupt"),
    )
    t = Transcriber("/fake/model.bin")
    with pytest.raises(RuntimeError):
        t.transcribe(np.zeros(16000, dtype=np.float32))


@pytest.mark.integration
def test_real_model_transcribes_quick_brown_fox():
    """Slow integration test using actual whisper.cpp + tiny.en. Requires internet on first run."""
    fixture = Path(__file__).parent / "fixtures" / "quick-brown-fox.wav"
    if not fixture.exists():
        pytest.skip("fixture not generated; run tests/fixtures/generate.sh")

    import wave
    with wave.open(str(fixture), "rb") as wf:
        assert wf.getframerate() == 16000
        frames = wf.readframes(wf.getnframes())
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

    t = Transcriber("tiny.en")
    text = t.transcribe(samples).lower()
    assert "quick" in text
    assert "brown" in text
    assert "fox" in text
