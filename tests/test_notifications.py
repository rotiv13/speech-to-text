from speech_to_text.notifications import notify


def test_notify_calls_osascript(mocker):
    fake = mocker.patch("speech_to_text.notifications.subprocess.run")
    notify("Title", "Body text")
    fake.assert_called_once()
    args = fake.call_args[0][0]
    assert args[0] == "osascript"
    assert args[1] == "-e"
    script = args[2]
    assert 'display notification "Body text"' in script
    assert 'with title "Title"' in script


def test_notify_escapes_quotes(mocker):
    fake = mocker.patch("speech_to_text.notifications.subprocess.run")
    notify('A "tricky" title', 'Body with "quotes"')
    script = fake.call_args[0][0][2]
    assert '\\"tricky\\"' in script
    assert '\\"quotes\\"' in script


def test_notify_swallows_errors(mocker):
    """Notification failure must never crash the caller."""
    mocker.patch(
        "speech_to_text.notifications.subprocess.run",
        side_effect=FileNotFoundError("osascript missing"),
    )
    notify("t", "b")
