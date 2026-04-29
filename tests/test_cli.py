import pytest

from speech_to_text.cli import main


def test_no_args_shows_help(capsys):
    rc = main([])
    captured = capsys.readouterr()
    assert "usage:" in captured.out.lower() or "usage:" in captured.err.lower()
    assert rc != 0


def test_install_creates_config_and_plist(mocker, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    # Patch in cli module's resolved paths AFTER setting HOME
    import speech_to_text.cli as cli_mod
    monkeypatch.setattr(cli_mod, "CONFIG_DIR", tmp_path / ".config" / "speech-to-text")
    monkeypatch.setattr(cli_mod, "CONFIG_FILE", tmp_path / ".config" / "speech-to-text" / "config.toml")
    monkeypatch.setattr(cli_mod, "DATA_DIR", tmp_path / ".local" / "share" / "speech-to-text")
    monkeypatch.setattr(cli_mod, "MODELS_DIR", tmp_path / ".local" / "share" / "speech-to-text" / "models")
    monkeypatch.setattr(cli_mod, "LOG_DIR", tmp_path / "Library" / "Logs" / "speech-to-text")
    monkeypatch.setattr(cli_mod, "LOG_FILE", tmp_path / "Library" / "Logs" / "speech-to-text" / "daemon.log")
    mocker.patch("speech_to_text.cli._download_model")

    rc = main(["install"])
    assert rc == 0

    cfg = tmp_path / ".config" / "speech-to-text" / "config.toml"
    assert cfg.exists()
    plist = tmp_path / "Library" / "LaunchAgents" / "com.user.speechtotext.plist"
    assert plist.exists()


def test_enable_calls_launchd_enable(mocker):
    enable_mock = mocker.patch("speech_to_text.cli.launchd.enable")
    rc = main(["enable"])
    assert rc == 0
    enable_mock.assert_called_once()


def test_disable_calls_launchd_disable(mocker):
    disable_mock = mocker.patch("speech_to_text.cli.launchd.disable")
    rc = main(["disable"])
    assert rc == 0
    disable_mock.assert_called_once()


def test_status_running(mocker, capsys):
    mocker.patch("speech_to_text.cli.launchd.is_loaded", return_value=True)
    rc = main(["status"])
    assert rc == 0
    out = capsys.readouterr().out.lower()
    assert "running" in out or "loaded" in out


def test_status_not_running(mocker, capsys):
    mocker.patch("speech_to_text.cli.launchd.is_loaded", return_value=False)
    rc = main(["status"])
    assert rc == 0
    out = capsys.readouterr().out.lower()
    assert "not" in out


def test_start_runs_daemon(mocker):
    daemon_run = mocker.patch("speech_to_text.cli._run_daemon_foreground", return_value=0)
    rc = main(["start"])
    assert rc == 0
    daemon_run.assert_called_once()
