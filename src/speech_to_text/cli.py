from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import textwrap
import urllib.request
from pathlib import Path
from typing import Sequence

from speech_to_text import launchd

log = logging.getLogger(__name__)

CONFIG_DIR = Path("~/.config/speech-to-text").expanduser()
CONFIG_FILE = CONFIG_DIR / "config.toml"
DATA_DIR = Path("~/.local/share/speech-to-text").expanduser()
MODELS_DIR = DATA_DIR / "models"
LOG_DIR = Path("~/Library/Logs/speech-to-text").expanduser()
LOG_FILE = LOG_DIR / "daemon.log"

DEFAULT_MODEL = "ggml-small.bin"
MODEL_URL = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/" + DEFAULT_MODEL
)

DEFAULT_CONFIG_BODY = textwrap.dedent("""\
    [hotkeys]
    push_to_talk = "<cmd_r>"
    toggle = "<ctrl>+<shift>+<space>"

    [model]
    # Multilingual default; auto-detects language per utterance.
    # Swap to "small.en" + ggml-small.en.bin for English-only / lower latency.
    name = "small"
    path = "~/.local/share/speech-to-text/models/ggml-small.bin"

    [audio]
    sample_rate = 16000
    input_device = "default"
    min_duration_ms = 400
    max_duration_ms = 300000

    [paste]
    restore_clipboard_delay_ms = 200

    [sounds]
    enabled = true

    [logging]
    level = "INFO"
""")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    handler = COMMANDS[args.command]
    return handler(args)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stt",
        description="Local-first speech-to-text dictation daemon",
    )
    sub = p.add_subparsers(dest="command")
    for name, help_ in (
        ("install", "first-time setup: config, model, plist"),
        ("enable", "load LaunchAgent (auto-start)"),
        ("disable", "unload LaunchAgent"),
        ("status", "is the daemon running?"),
        ("start", "run daemon in the foreground (debug)"),
        ("logs", "tail the daemon log"),
        ("config", "open the config file in $EDITOR"),
        ("uninstall", "remove plist (use --purge to also remove config and models)"),
    ):
        sp = sub.add_parser(name, help=help_)
        if name == "uninstall":
            sp.add_argument("--purge", action="store_true")
    return p


def cmd_install(args) -> int:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(DEFAULT_CONFIG_BODY)
        print(f"Wrote default config to {CONFIG_FILE}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / DEFAULT_MODEL
    if not model_path.exists():
        _download_model(MODEL_URL, model_path)
    else:
        print(f"Model already present at {model_path}")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    program = shutil.which("stt") or sys.argv[0]
    plist = launchd.write_plist(program_path=program, log_path=str(LOG_FILE))
    print(f"Wrote LaunchAgent plist to {plist}")
    print(
        "\nNext: run `stt enable` to start the daemon.\n"
        "macOS will prompt for Microphone and Accessibility permissions on first run."
    )
    return 0


def cmd_enable(args) -> int:
    launchd.enable()
    print("Daemon enabled. Logs:", LOG_FILE)
    return 0


def cmd_disable(args) -> int:
    launchd.disable()
    print("Daemon disabled.")
    return 0


def cmd_status(args) -> int:
    if launchd.is_loaded():
        print("Daemon: running (loaded by launchd)")
    else:
        print("Daemon: not running")
    return 0


def cmd_start(args) -> int:
    return _run_daemon_foreground()


def cmd_logs(args) -> int:
    if not LOG_FILE.exists():
        print(f"No log file at {LOG_FILE}")
        return 0
    subprocess.run(["tail", "-f", str(LOG_FILE)], check=False)
    return 0


def cmd_config(args) -> int:
    editor = os.environ.get("EDITOR", "open")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(DEFAULT_CONFIG_BODY)
    subprocess.run([editor, str(CONFIG_FILE)], check=False)
    return 0


def cmd_uninstall(args) -> int:
    launchd.disable()
    p = launchd.plist_path()
    if p.exists():
        p.unlink()
        print(f"Removed {p}")
    if getattr(args, "purge", False):
        for d in (CONFIG_DIR, DATA_DIR):
            if d.exists():
                shutil.rmtree(d)
                print(f"Removed {d}")
    return 0


COMMANDS = {
    "install": cmd_install,
    "enable": cmd_enable,
    "disable": cmd_disable,
    "status": cmd_status,
    "start": cmd_start,
    "logs": cmd_logs,
    "config": cmd_config,
    "uninstall": cmd_uninstall,
}


def _download_model(url: str, dest: Path) -> None:
    print(f"Downloading {url} → {dest} (this may take a while)…")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)  # noqa: S310 — model URL is config'd, https
    tmp.rename(dest)
    print("Model downloaded.")


def _run_daemon_foreground() -> int:
    """Wire all components and run the daemon until interrupted."""
    from speech_to_text import audio as audio_mod
    from speech_to_text import config as config_mod
    from speech_to_text import notifications, sounds as sounds_mod
    from speech_to_text.daemon import Daemon
    from speech_to_text.hotkeys import Hotkeys
    from speech_to_text.paste import Paster
    from speech_to_text.transcribe import Transcriber

    cfg = config_mod.load(CONFIG_FILE)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # launchd already redirects stdout+stderr to LOG_FILE via the plist, so a
    # bare StreamHandler is enough; adding a FileHandler too produces every
    # line twice in the log.
    logging.basicConfig(
        level=getattr(logging, cfg.logging.level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler()],
    )

    # pynput's macOS backend logs "This process is not trusted!" at WARNING
    # level when Accessibility permission is missing, then silently delivers
    # no key events. Catch that warning and surface it via notification + log
    # so the daemon doesn't pretend to be working.
    accessibility_denied = _install_accessibility_watcher()

    model_path = Path(cfg.model.path).expanduser()
    if not model_path.exists():
        msg = (
            f"Model file not found: {model_path}. "
            "Run `stt install` to download it."
        )
        log.error(msg)
        notifications.notify("Speech-to-Text", msg)
        return 1

    asset_dir = Path(__file__).parent / "assets" / "sounds"
    sounds = sounds_mod.Sounds(asset_dir=asset_dir, enabled=cfg.sounds.enabled)
    paster = Paster(restore_delay_ms=cfg.paste.restore_clipboard_delay_ms)
    transcriber = Transcriber(str(model_path))
    audio = audio_mod.Recorder(
        sample_rate=cfg.audio.sample_rate,
        input_device=cfg.audio.input_device,
    )

    try:
        transcriber.load()
    except Exception as e:
        log.exception("Failed to load whisper model")
        notifications.notify("Speech-to-Text", f"Failed to load model: {e}")
        return 1

    daemon = Daemon(
        hotkeys=None,
        audio=audio,
        transcriber=transcriber,
        paster=paster,
        sounds=sounds,
        notifier=notifications.notify,
        min_duration_ms=cfg.audio.min_duration_ms,
        max_duration_ms=cfg.audio.max_duration_ms,
    )

    hotkeys = Hotkeys(
        ptt_key=cfg.hotkeys.push_to_talk,
        toggle_combo=cfg.hotkeys.toggle,
        on_ptt_press=daemon.on_ptt_press,
        on_ptt_release=daemon.on_ptt_release,
        on_toggle=daemon.on_toggle,
    )
    hotkeys.start()

    # pynput's trust check happens shortly after listener.start(), give it a
    # moment then check whether the warning fired.
    import time as _time
    _time.sleep(0.5)
    if accessibility_denied.is_set():
        msg = (
            "Accessibility permission denied. "
            "Open System Settings → Privacy & Security → Accessibility "
            "and enable Python, then run `stt disable && stt enable`."
        )
        log.error(msg)
        notifications.notify("Speech-to-Text", msg)
        hotkeys.stop()
        return 1

    log.info(
        "Daemon ready. Push-to-talk: %s | Toggle: %s",
        cfg.hotkeys.push_to_talk,
        cfg.hotkeys.toggle,
    )

    try:
        import threading
        threading.Event().wait()
    except KeyboardInterrupt:
        log.info("Shutting down")
        hotkeys.stop()
    return 0


def _install_accessibility_watcher() -> "object":
    """Watch pynput's logger for the 'not trusted' warning and signal an
    event when seen. Returns a `threading.Event` that gets set if pynput
    reports its process is missing Accessibility permission."""
    import threading
    denied = threading.Event()

    class _Watcher(logging.Handler):
        def emit(self, record):
            if "not trusted" in record.getMessage().lower():
                denied.set()

    logging.getLogger("pynput").addHandler(_Watcher())
    return denied


if __name__ == "__main__":
    raise SystemExit(main())
