from speech_to_text.sounds import Sounds


def test_play_invokes_afplay(mocker, tmp_path):
    fake_run = mocker.patch("speech_to_text.sounds.subprocess.Popen")
    asset_dir = tmp_path
    (asset_dir / "tink.wav").write_bytes(b"")
    sounds = Sounds(asset_dir=asset_dir, enabled=True)

    sounds.play("tink.wav")

    fake_run.assert_called_once()
    args = fake_run.call_args[0][0]
    assert args[0] == "afplay"
    assert args[1] == str(asset_dir / "tink.wav")


def test_play_no_op_when_disabled(mocker, tmp_path):
    fake_run = mocker.patch("speech_to_text.sounds.subprocess.Popen")
    sounds = Sounds(asset_dir=tmp_path, enabled=False)

    sounds.play("tink.wav")

    fake_run.assert_not_called()


def test_play_no_op_when_file_missing(mocker, tmp_path):
    fake_run = mocker.patch("speech_to_text.sounds.subprocess.Popen")
    sounds = Sounds(asset_dir=tmp_path, enabled=True)

    sounds.play("missing.wav")

    fake_run.assert_not_called()


def test_play_does_not_block(mocker, tmp_path):
    """afplay must run in background — Popen, not run."""
    fake_popen = mocker.patch("speech_to_text.sounds.subprocess.Popen")
    (tmp_path / "ding.wav").write_bytes(b"")
    sounds = Sounds(asset_dir=tmp_path, enabled=True)
    sounds.play("ding.wav")
    fake_popen.return_value.wait.assert_not_called()
