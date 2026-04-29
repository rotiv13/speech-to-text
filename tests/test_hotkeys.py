from unittest.mock import MagicMock

import pytest

from speech_to_text.hotkeys import Hotkeys, parse_single_key


def test_parse_single_key_special():
    from pynput.keyboard import Key
    assert parse_single_key("<cmd_r>") is Key.cmd_r
    assert parse_single_key("<f19>") is Key.f19
    assert parse_single_key("<right>") is Key.right


def test_parse_single_key_invalid_raises():
    with pytest.raises(ValueError):
        parse_single_key("not-a-key")


def test_ptt_press_and_release_invoke_callbacks(mocker):
    from pynput.keyboard import Key

    listener_cls = mocker.patch("speech_to_text.hotkeys.keyboard.Listener")
    on_press_cb = MagicMock()
    on_release_cb = MagicMock()
    on_toggle_cb = MagicMock()

    hk = Hotkeys(
        ptt_key="<cmd_r>",
        toggle_combo="<ctrl>+<shift>+<space>",
        on_ptt_press=on_press_cb,
        on_ptt_release=on_release_cb,
        on_toggle=on_toggle_cb,
    )
    hk.start()

    listener_cls.assert_called_once()
    kwargs = listener_cls.call_args.kwargs
    press_handler = kwargs["on_press"]
    release_handler = kwargs["on_release"]

    press_handler(Key.cmd_r)
    on_press_cb.assert_called_once()

    release_handler(Key.cmd_r)
    on_release_cb.assert_called_once()


def test_other_keys_do_not_trigger_ptt(mocker):
    from pynput.keyboard import Key, KeyCode

    mocker.patch("speech_to_text.hotkeys.keyboard.Listener")
    on_press_cb = MagicMock()
    on_release_cb = MagicMock()

    hk = Hotkeys(
        ptt_key="<cmd_r>",
        toggle_combo="<ctrl>+<shift>+<space>",
        on_ptt_press=on_press_cb,
        on_ptt_release=on_release_cb,
        on_toggle=MagicMock(),
    )
    hk.start()

    press_handler = hk._press_handler
    press_handler(Key.shift)
    press_handler(KeyCode.from_char("a"))
    on_press_cb.assert_not_called()


def test_stop_calls_listener_stop(mocker):
    listener = MagicMock()
    mocker.patch("speech_to_text.hotkeys.keyboard.Listener", return_value=listener)
    hk = Hotkeys(
        ptt_key="<cmd_r>",
        toggle_combo="<ctrl>+<shift>+<space>",
        on_ptt_press=MagicMock(),
        on_ptt_release=MagicMock(),
        on_toggle=MagicMock(),
    )
    hk.start()
    hk.stop()
    listener.stop.assert_called_once()
