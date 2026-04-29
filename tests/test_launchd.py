from pathlib import Path

from speech_to_text.launchd import (
    LABEL,
    enable,
    disable,
    is_loaded,
    plist_path,
    render_plist,
)


def test_render_plist_contains_required_keys():
    out = render_plist(
        program_path="/Users/x/.local/bin/stt",
        log_path="/Users/x/Library/Logs/speech-to-text/daemon.log",
    )
    assert LABEL in out
    assert "<key>RunAtLoad</key>" in out
    assert "<true/>" in out
    assert "<key>KeepAlive</key>" in out
    assert "/Users/x/.local/bin/stt" in out
    assert "<string>start</string>" in out
    assert "/Users/x/Library/Logs/speech-to-text/daemon.log" in out


def test_render_plist_matches_golden_fixture():
    fixture = Path(__file__).parent / "fixtures" / "expected.plist"
    expected = fixture.read_text()
    out = render_plist(
        program_path="/usr/local/bin/stt",
        log_path="/var/log/stt.log",
    )
    assert out.strip() == expected.strip()


def test_plist_path_under_launch_agents(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = plist_path()
    assert p == tmp_path / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def test_enable_calls_launchctl_load(mocker, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = plist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("<plist/>")
    fake = mocker.patch("speech_to_text.launchd.subprocess.run")
    enable()
    fake.assert_called_once()
    args = fake.call_args[0][0]
    assert args[0] == "launchctl"
    assert args[1] == "load"
    assert args[-1] == str(p)


def test_disable_calls_launchctl_unload(mocker, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = plist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("<plist/>")
    fake = mocker.patch("speech_to_text.launchd.subprocess.run")
    disable()
    fake.assert_called_once()
    args = fake.call_args[0][0]
    assert args[1] == "unload"


def test_is_loaded_parses_launchctl_list(mocker):
    completed = mocker.MagicMock()
    completed.stdout = (
        "PID\tStatus\tLabel\n"
        f"12345\t0\t{LABEL}\n"
        "-\t0\tcom.example.other\n"
    )
    mocker.patch("speech_to_text.launchd.subprocess.run", return_value=completed)
    assert is_loaded() is True


def test_is_loaded_returns_false_when_absent(mocker):
    completed = mocker.MagicMock()
    completed.stdout = "PID\tStatus\tLabel\n-\t0\tcom.example.other\n"
    mocker.patch("speech_to_text.launchd.subprocess.run", return_value=completed)
    assert is_loaded() is False
