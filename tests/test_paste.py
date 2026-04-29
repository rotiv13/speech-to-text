from unittest.mock import MagicMock

from speech_to_text.paste import Paster


def _fake_pasteboard():
    pb = MagicMock()
    pb.pasteboardItems.return_value = []
    return pb


def test_paste_sets_text_then_simulates_cmd_v(mocker):
    pb = _fake_pasteboard()
    mocker.patch("speech_to_text.paste._general_pasteboard", return_value=pb)
    fake_post = mocker.patch("speech_to_text.paste._post_cmd_v", return_value=True)
    sleep_mock = mocker.patch("speech_to_text.paste.time.sleep")
    paster = Paster(restore_delay_ms=50)

    ok = paster.paste("hello world")

    assert ok is True
    pb.clearContents.assert_called()
    pb.setString_forType_.assert_called_with("hello world", mocker.ANY)
    fake_post.assert_called_once()
    sleep_mock.assert_called_with(0.05)


def test_paste_failure_keeps_text_on_clipboard(mocker):
    """If Cmd+V simulation fails, do NOT restore clipboard — leave the transcribed text."""
    pb = _fake_pasteboard()
    mocker.patch("speech_to_text.paste._general_pasteboard", return_value=pb)
    mocker.patch("speech_to_text.paste._post_cmd_v", return_value=False)
    restore_mock = mocker.patch("speech_to_text.paste._restore_pasteboard")
    paster = Paster(restore_delay_ms=50)

    ok = paster.paste("kept on clipboard")

    assert ok is False
    restore_mock.assert_not_called()


def test_paste_restores_clipboard_after_success(mocker):
    pb = _fake_pasteboard()
    fake_snapshot = [{"public.text": b"original"}]
    mocker.patch("speech_to_text.paste._general_pasteboard", return_value=pb)
    mocker.patch("speech_to_text.paste._snapshot_pasteboard", return_value=fake_snapshot)
    mocker.patch("speech_to_text.paste._post_cmd_v", return_value=True)
    mocker.patch("speech_to_text.paste.time.sleep")
    restore_mock = mocker.patch("speech_to_text.paste._restore_pasteboard")
    paster = Paster(restore_delay_ms=50)

    paster.paste("transient")

    restore_mock.assert_called_once_with(pb, fake_snapshot)
