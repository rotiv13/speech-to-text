from pathlib import Path
import textwrap

from speech_to_text.config import Config, load


def test_defaults_when_file_missing(tmp_path):
    cfg = load(tmp_path / "nope.toml")
    assert cfg.hotkeys.push_to_talk == "<cmd_r>"
    assert cfg.hotkeys.toggle == "<ctrl>+<shift>+<space>"
    assert cfg.model.name == "medium"
    assert cfg.audio.sample_rate == 16000
    assert cfg.audio.min_duration_ms == 400
    assert cfg.audio.max_duration_ms == 300_000
    assert cfg.paste.restore_clipboard_delay_ms == 200
    assert cfg.sounds.enabled is True


def test_overrides(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent("""
        [hotkeys]
        push_to_talk = "<f19>"
        toggle = "<cmd>+<shift>+d"

        [model]
        name = "medium.en"

        [audio]
        min_duration_ms = 600

        [sounds]
        enabled = false
    """))
    cfg = load(p)
    assert cfg.hotkeys.push_to_talk == "<f19>"
    assert cfg.hotkeys.toggle == "<cmd>+<shift>+d"
    assert cfg.model.name == "medium.en"
    assert cfg.audio.min_duration_ms == 600
    assert cfg.sounds.enabled is False
    assert cfg.audio.sample_rate == 16000


def test_model_path_expansion(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[model]\npath = "~/models/foo.bin"\n')
    cfg = load(p)
    assert cfg.model.path == str(Path("~/models/foo.bin").expanduser())


def test_returns_config_dataclass(tmp_path):
    cfg = load(tmp_path / "nope.toml")
    assert isinstance(cfg, Config)
