import numpy as np
import pytest

from speech_to_text.audio import Recorder


def test_start_then_stop_returns_concatenated_array(mocker):
    """Simulate sounddevice pushing two callbacks then stop."""
    fake_stream = mocker.MagicMock()
    fake_input_stream = mocker.patch(
        "speech_to_text.audio.sd.InputStream",
        return_value=fake_stream,
    )
    rec = Recorder(sample_rate=16000)

    rec.start()
    callback = fake_input_stream.call_args.kwargs["callback"]
    chunk_a = np.ones((1024, 1), dtype=np.float32) * 0.1
    chunk_b = np.ones((1024, 1), dtype=np.float32) * 0.2
    callback(chunk_a, 1024, None, None)
    callback(chunk_b, 1024, None, None)
    samples = rec.stop()

    assert samples.dtype == np.float32
    assert samples.ndim == 1
    assert samples.shape[0] == 2048
    assert np.isclose(samples[0], 0.1)
    assert np.isclose(samples[-1], 0.2)
    fake_stream.start.assert_called_once()
    fake_stream.stop.assert_called_once()
    fake_stream.close.assert_called_once()


def test_stop_without_start_returns_empty_array():
    rec = Recorder(sample_rate=16000)
    samples = rec.stop()
    assert samples.dtype == np.float32
    assert samples.shape == (0,)


def test_stop_with_no_callbacks_returns_empty(mocker):
    fake_stream = mocker.MagicMock()
    mocker.patch("speech_to_text.audio.sd.InputStream", return_value=fake_stream)
    rec = Recorder(sample_rate=16000)
    rec.start()
    samples = rec.stop()
    assert samples.shape == (0,)


def test_double_start_is_safe(mocker):
    """Calling start twice should not open two streams."""
    fake_stream = mocker.MagicMock()
    fake_input_stream = mocker.patch(
        "speech_to_text.audio.sd.InputStream",
        return_value=fake_stream,
    )
    rec = Recorder(sample_rate=16000)
    rec.start()
    rec.start()
    assert fake_input_stream.call_count == 1


def test_duration_seconds_property(mocker):
    fake_stream = mocker.MagicMock()
    mocker.patch("speech_to_text.audio.sd.InputStream", return_value=fake_stream)
    rec = Recorder(sample_rate=16000)
    rec.start()
    # 16000 frames = 1 second at 16 kHz
    rec._on_audio(np.zeros((16000, 1), dtype=np.float32), 16000, None, None)
    assert rec.duration_seconds == pytest.approx(1.0, rel=1e-3)
