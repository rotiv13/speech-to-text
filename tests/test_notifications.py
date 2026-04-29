from speech_to_text.notifications import notify


def test_notify_calls_osascript_with_argv(mocker):
    fake = mocker.patch("speech_to_text.notifications.subprocess.run")
    notify("Title", "Body text")
    fake.assert_called_once()
    args = fake.call_args[0][0]
    assert args[0] == "osascript"
    assert args[1] == "-e"
    # Title and body are passed as argv to the script — not interpolated.
    assert "--" in args
    assert args[-2] == "Title"
    assert args[-1] == "Body text"


def test_notify_safely_passes_quotes_and_backslashes(mocker):
    """Tricky chars in title/body must reach osascript verbatim, not escaped."""
    fake = mocker.patch("speech_to_text.notifications.subprocess.run")
    notify('A "tricky" title', 'Path: C:\\foo and "quotes"')
    args = fake.call_args[0][0]
    assert args[-2] == 'A "tricky" title'
    assert args[-1] == 'Path: C:\\foo and "quotes"'


def test_notify_swallows_errors(mocker):
    """Notification failure must never crash the caller."""
    mocker.patch(
        "speech_to_text.notifications.subprocess.run",
        side_effect=FileNotFoundError("osascript missing"),
    )
    notify("t", "b")
