# Speech-to-Text Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a macOS background daemon that transcribes speech to text via local `whisper.cpp`, triggered by global hotkeys, pasting the result into the focused app.

**Architecture:** Single Python process running as a `launchd` LaunchAgent. State machine driven by hotkey events from `pynput`. Audio captured via `sounddevice`, transcribed via `pywhispercpp`, pasted via `NSPasteboard` + simulated `⌘V`. All side-effect modules behind narrow interfaces so the daemon's state machine is fully unit-testable.

**Tech Stack:**
- Python 3.11+ (for stdlib `tomllib`)
- `pywhispercpp` — whisper.cpp Python bindings
- `sounddevice` — PortAudio mic capture
- `pynput` — global hotkeys
- `pyobjc-framework-Cocoa` + `pyobjc-framework-Quartz` — clipboard + keystroke simulation
- `numpy` — audio buffers
- `pytest` + `pytest-mock` — testing
- `uv` — packaging / install
- `launchd` — process supervision

**Spec:** [`docs/superpowers/specs/2026-04-29-speech-to-text-design.md`](../specs/2026-04-29-speech-to-text-design.md)

---

## File Structure

Files created or modified by this plan:

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, deps, console-script entry |
| `.gitignore` | Ignore caches, venvs, model files |
| `src/speech_to_text/__init__.py` | Package marker, version |
| `src/speech_to_text/__main__.py` | `python -m speech_to_text` → daemon foreground |
| `src/speech_to_text/config.py` | Load & validate `config.toml`; defaults |
| `src/speech_to_text/sounds.py` | Play short audio cues via `afplay` |
| `src/speech_to_text/notifications.py` | macOS notifications via `osascript` |
| `src/speech_to_text/paste.py` | Snapshot clipboard, paste text, restore |
| `src/speech_to_text/audio.py` | Mic capture (16 kHz mono float32) |
| `src/speech_to_text/transcribe.py` | `pywhispercpp` wrapper |
| `src/speech_to_text/hotkeys.py` | Global hotkey listener |
| `src/speech_to_text/daemon.py` | State machine wiring all components |
| `src/speech_to_text/launchd.py` | Generate / install / control LaunchAgent plist |
| `src/speech_to_text/cli.py` | `argparse` subcommands |
| `src/speech_to_text/assets/sounds/{tink,ding,error}.wav` | Audio cue files |
| `tests/conftest.py` | Shared fixtures |
| `tests/fixtures/quick-brown-fox.wav` | Integration-test audio |
| `tests/fixtures/silence.wav` | Empty-transcription test |
| `tests/fixtures/generate.sh` | Regenerate fixtures with macOS `say` |
| `tests/test_*.py` | Unit + integration tests |
| `docs/manual-test-plan.md` | Manual smoke checklist |
| `README.md` | User-facing install + usage |

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/speech_to_text/__init__.py`
- Create: `src/speech_to_text/__main__.py`
- Create: `src/speech_to_text/cli.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing smoke test**

Create `tests/test_smoke.py`:

```python
def test_package_imports():
    import speech_to_text
    assert speech_to_text.__version__


def test_cli_main_callable():
    from speech_to_text.cli import main
    assert callable(main)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'speech_to_text'`.

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "speech-to-text"
version = "0.1.0"
description = "Local-first macOS speech-to-text dictation daemon"
requires-python = ">=3.11"
readme = "README.md"
dependencies = [
  "numpy>=1.26",
  "sounddevice>=0.4.6",
  "pynput>=1.7.7",
  "pywhispercpp>=1.2.0",
  "pyobjc-framework-Cocoa>=10.0",
  "pyobjc-framework-Quartz>=10.0",
]

[project.scripts]
stt = "speech_to_text.cli:main"

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-mock>=3.12"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/speech_to_text"]

[tool.hatch.build]
include = ["src/speech_to_text/assets/**"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --strict-markers"
```

- [ ] **Step 4: Create `.gitignore`**

```gitignore
__pycache__/
*.pyc
.pytest_cache/
.venv/
.venvs/
dist/
build/
*.egg-info/
.coverage
.DS_Store
# Local model files (downloaded on install, not committed)
*.bin
!tests/fixtures/*.bin
```

- [ ] **Step 5: Create package skeleton**

`src/speech_to_text/__init__.py`:

```python
__version__ = "0.1.0"
```

`src/speech_to_text/cli.py`:

```python
def main() -> int:
    print("stt: not yet wired up")
    return 0
```

`src/speech_to_text/__main__.py`:

```python
from speech_to_text.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

`tests/__init__.py`: empty file.

- [ ] **Step 6: Install deps and re-run test**

Run:
```bash
uv venv
uv pip install -e ".[dev]"
uv run pytest tests/test_smoke.py -v
```
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore src tests
git commit -m "chore: scaffold speech-to-text Python package"
```

---

## Task 2: Config loader

**Files:**
- Create: `src/speech_to_text/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_config.py`:

```python
from pathlib import Path
import textwrap

from speech_to_text.config import Config, load


def test_defaults_when_file_missing(tmp_path):
    cfg = load(tmp_path / "nope.toml")
    assert cfg.hotkeys.push_to_talk == "<cmd_r>"
    assert cfg.hotkeys.toggle == "<ctrl>+<shift>+<space>"
    assert cfg.model.name == "small.en"
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
    # Untouched keys keep defaults
    assert cfg.audio.sample_rate == 16000


def test_model_path_expansion(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[model]\npath = "~/models/foo.bin"\n')
    cfg = load(p)
    assert cfg.model.path == str(Path("~/models/foo.bin").expanduser())


def test_returns_config_dataclass(tmp_path):
    cfg = load(tmp_path / "nope.toml")
    assert isinstance(cfg, Config)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'speech_to_text.config'`.

- [ ] **Step 3: Implement `config.py`**

Create `src/speech_to_text/config.py`:

```python
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL_PATH = "~/.local/share/speech-to-text/models/ggml-small.en.bin"


@dataclass(frozen=True)
class HotkeysConfig:
    push_to_talk: str = "<cmd_r>"
    toggle: str = "<ctrl>+<shift>+<space>"


@dataclass(frozen=True)
class ModelConfig:
    name: str = "small.en"
    path: str = DEFAULT_MODEL_PATH


@dataclass(frozen=True)
class AudioConfig:
    sample_rate: int = 16000
    input_device: str = "default"
    min_duration_ms: int = 400
    max_duration_ms: int = 300_000


@dataclass(frozen=True)
class PasteConfig:
    restore_clipboard_delay_ms: int = 200


@dataclass(frozen=True)
class SoundsConfig:
    enabled: bool = True
    record_start: str = "tink.wav"
    paste_done: str = "ding.wav"
    error: str = "error.wav"


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 3


@dataclass(frozen=True)
class Config:
    hotkeys: HotkeysConfig = field(default_factory=HotkeysConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    paste: PasteConfig = field(default_factory=PasteConfig)
    sounds: SoundsConfig = field(default_factory=SoundsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load(path: Path) -> Config:
    if not path.exists():
        return Config()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    return _build(raw)


def _build(raw: dict) -> Config:
    model_section = raw.get("model", {})
    if "path" in model_section:
        model_section = {**model_section, "path": str(Path(model_section["path"]).expanduser())}
    return Config(
        hotkeys=HotkeysConfig(**raw.get("hotkeys", {})),
        model=ModelConfig(**model_section),
        audio=AudioConfig(**raw.get("audio", {})),
        paste=PasteConfig(**raw.get("paste", {})),
        sounds=SoundsConfig(**raw.get("sounds", {})),
        logging=LoggingConfig(**raw.get("logging", {})),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/speech_to_text/config.py tests/test_config.py
git commit -m "feat(config): TOML loader with dataclass defaults"
```

---

## Task 3: Sounds module

**Files:**
- Create: `src/speech_to_text/sounds.py`
- Create: `tests/test_sounds.py`
- Create (placeholder): `src/speech_to_text/assets/sounds/.gitkeep`

- [ ] **Step 1: Write failing tests**

Create `tests/test_sounds.py`:

```python
from pathlib import Path

import pytest

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
    # Popen was called (non-blocking); .wait() / .communicate() must NOT be called
    fake_popen.return_value.wait.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sounds.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `sounds.py`**

Create `src/speech_to_text/sounds.py`:

```python
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


class Sounds:
    def __init__(self, asset_dir: Path, enabled: bool = True) -> None:
        self._asset_dir = Path(asset_dir)
        self._enabled = enabled

    def play(self, filename: str) -> None:
        if not self._enabled:
            return
        path = self._asset_dir / filename
        if not path.exists():
            log.warning("Sound file not found: %s", path)
            return
        try:
            subprocess.Popen(
                ["afplay", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            log.warning("afplay not available; skipping sound")
```

- [ ] **Step 4: Create asset placeholder**

Create `src/speech_to_text/assets/sounds/.gitkeep` (empty file). The actual `.wav` files are added in Task 12.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_sounds.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/speech_to_text/sounds.py src/speech_to_text/assets tests/test_sounds.py
git commit -m "feat(sounds): non-blocking afplay wrapper for audio cues"
```

---

## Task 4: Notifications module

**Files:**
- Create: `src/speech_to_text/notifications.py`
- Create: `tests/test_notifications.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_notifications.py`:

```python
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
    # Embedded quotes are escaped via backslash so AppleScript parses correctly.
    assert '\\"tricky\\"' in script
    assert '\\"quotes\\"' in script


def test_notify_swallows_errors(mocker):
    """Notification failure must never crash the caller."""
    mocker.patch(
        "speech_to_text.notifications.subprocess.run",
        side_effect=FileNotFoundError("osascript missing"),
    )
    # Must not raise.
    notify("t", "b")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_notifications.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `notifications.py`**

Create `src/speech_to_text/notifications.py`:

```python
from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)


def notify(title: str, body: str) -> None:
    safe_title = title.replace('"', '\\"')
    safe_body = body.replace('"', '\\"')
    script = f'display notification "{safe_body}" with title "{safe_title}"'
    try:
        subprocess.run(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        log.warning("Notification failed: %s", e)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_notifications.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/speech_to_text/notifications.py tests/test_notifications.py
git commit -m "feat(notifications): osascript wrapper for macOS user-facing errors"
```

---

## Task 5: Paste module

**Files:**
- Create: `src/speech_to_text/paste.py`
- Create: `tests/test_paste.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_paste.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_paste.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `paste.py`**

Create `src/speech_to_text/paste.py`:

```python
from __future__ import annotations

import logging
import time
from typing import Any

import AppKit  # type: ignore[import-not-found]
import Quartz  # type: ignore[import-not-found]

log = logging.getLogger(__name__)

_KEY_CODE_V = 9  # macOS virtual key code for "v" on US layout


class Paster:
    def __init__(self, restore_delay_ms: int = 200) -> None:
        self._restore_delay_s = restore_delay_ms / 1000.0

    def paste(self, text: str) -> bool:
        pb = _general_pasteboard()
        snapshot = _snapshot_pasteboard(pb)
        pb.clearContents()
        pb.setString_forType_(text, AppKit.NSPasteboardTypeString)

        if not _post_cmd_v():
            log.warning("Cmd+V simulation failed; leaving text on clipboard")
            return False

        time.sleep(self._restore_delay_s)
        _restore_pasteboard(pb, snapshot)
        return True


def _general_pasteboard() -> Any:
    return AppKit.NSPasteboard.generalPasteboard()


def _snapshot_pasteboard(pb: Any) -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    for item in pb.pasteboardItems() or []:
        item_data: dict[str, Any] = {}
        for type_ in item.types():
            data = item.dataForType_(type_)
            if data is not None:
                item_data[str(type_)] = data
        if item_data:
            snapshot.append(item_data)
    return snapshot


def _restore_pasteboard(pb: Any, snapshot: list[dict[str, Any]]) -> None:
    pb.clearContents()
    items = []
    for item_data in snapshot:
        item = AppKit.NSPasteboardItem.alloc().init()
        for type_, data in item_data.items():
            item.setData_forType_(data, type_)
        items.append(item)
    if items:
        pb.writeObjects_(items)


def _post_cmd_v() -> bool:
    try:
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        down = Quartz.CGEventCreateKeyboardEvent(src, _KEY_CODE_V, True)
        Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskCommand)
        up = Quartz.CGEventCreateKeyboardEvent(src, _KEY_CODE_V, False)
        Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        return True
    except Exception as e:
        log.exception("Cmd+V failed: %s", e)
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_paste.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/speech_to_text/paste.py tests/test_paste.py
git commit -m "feat(paste): clipboard snapshot/restore with simulated Cmd+V"
```

---

## Task 6: Audio capture

**Files:**
- Create: `src/speech_to_text/audio.py`
- Create: `tests/test_audio.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_audio.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_audio.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `audio.py`**

Create `src/speech_to_text/audio.py`:

```python
from __future__ import annotations

import logging
import queue
from typing import Any

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)


class Recorder:
    def __init__(self, sample_rate: int = 16000, input_device: str | None = None) -> None:
        self._sample_rate = sample_rate
        self._input_device = input_device if input_device and input_device != "default" else None
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: Any | None = None
        self._frames_captured = 0

    def start(self) -> None:
        if self._stream is not None:
            return
        self._queue = queue.Queue()
        self._frames_captured = 0
        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            blocksize=1024,
            device=self._input_device,
            callback=self._on_audio,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is None:
            return np.array([], dtype=np.float32)
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None

        chunks: list[np.ndarray] = []
        while True:
            try:
                chunks.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if not chunks:
            return np.array([], dtype=np.float32)
        return np.concatenate(chunks).flatten().astype(np.float32, copy=False)

    @property
    def duration_seconds(self) -> float:
        return self._frames_captured / self._sample_rate

    def _on_audio(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            log.debug("sounddevice status: %s", status)
        self._queue.put(indata.copy())
        self._frames_captured += frames
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_audio.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/speech_to_text/audio.py tests/test_audio.py
git commit -m "feat(audio): mic capture via sounddevice with frame queue"
```

---

## Task 7: Transcribe wrapper

**Files:**
- Create: `src/speech_to_text/transcribe.py`
- Create: `tests/test_transcribe.py`
- Create: `tests/fixtures/generate.sh`

- [ ] **Step 1: Write failing tests**

Create `tests/test_transcribe.py`:

```python
from pathlib import Path

import numpy as np
import pytest

from speech_to_text.transcribe import Transcriber


def test_loads_model_lazily_then_transcribes(mocker):
    fake_model_cls = mocker.patch("speech_to_text.transcribe.Model")
    fake_model = fake_model_cls.return_value
    fake_seg = mocker.MagicMock()
    fake_seg.text = " hello world "
    fake_model.transcribe.return_value = [fake_seg]

    t = Transcriber("/fake/model.bin")
    fake_model_cls.assert_not_called()  # lazy

    samples = np.zeros(16000, dtype=np.float32)
    text = t.transcribe(samples)

    fake_model_cls.assert_called_once_with("/fake/model.bin", n_threads=mocker.ANY)
    fake_model.transcribe.assert_called_once()
    np.testing.assert_array_equal(fake_model.transcribe.call_args[0][0], samples)
    assert text == "hello world"


def test_concatenates_multiple_segments(mocker):
    fake_model_cls = mocker.patch("speech_to_text.transcribe.Model")
    fake_model = fake_model_cls.return_value

    def make_seg(s):
        m = mocker.MagicMock()
        m.text = s
        return m

    fake_model.transcribe.return_value = [make_seg(" the quick "), make_seg(" brown fox.")]

    t = Transcriber("/fake/model.bin")
    text = t.transcribe(np.zeros(16000, dtype=np.float32))
    assert text == "the quick brown fox."


def test_empty_audio_returns_empty_string(mocker):
    mocker.patch("speech_to_text.transcribe.Model")
    t = Transcriber("/fake/model.bin")
    text = t.transcribe(np.array([], dtype=np.float32))
    assert text == ""


def test_model_load_failure_raises_on_first_use(mocker):
    fake_model_cls = mocker.patch(
        "speech_to_text.transcribe.Model",
        side_effect=RuntimeError("model file corrupt"),
    )
    t = Transcriber("/fake/model.bin")
    with pytest.raises(RuntimeError):
        t.transcribe(np.zeros(16000, dtype=np.float32))


@pytest.mark.integration
def test_real_model_transcribes_quick_brown_fox():
    """Slow integration test using actual whisper.cpp + tiny.en. Requires internet on first run."""
    fixture = Path(__file__).parent / "fixtures" / "quick-brown-fox.wav"
    if not fixture.exists():
        pytest.skip("fixture not generated; run tests/fixtures/generate.sh")

    import wave
    with wave.open(str(fixture), "rb") as wf:
        assert wf.getframerate() == 16000
        frames = wf.readframes(wf.getnframes())
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

    t = Transcriber("tiny.en")  # pywhispercpp will download if not present
    text = t.transcribe(samples).lower()
    assert "quick" in text
    assert "brown" in text
    assert "fox" in text
```

- [ ] **Step 2: Add a marker config**

Add to `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
markers = ["integration: slow tests that hit real whisper.cpp"]
```

(Edit existing `[tool.pytest.ini_options]` section to add this line; keep `testpaths` and `addopts`.)

- [ ] **Step 3: Run unit tests to verify failure**

Run: `uv run pytest tests/test_transcribe.py -v -m "not integration"`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement `transcribe.py`**

Create `src/speech_to_text/transcribe.py`:

```python
from __future__ import annotations

import logging
import os

import numpy as np
from pywhispercpp.model import Model

log = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, model_path: str, n_threads: int | None = None) -> None:
        self._model_path = model_path
        self._n_threads = n_threads or max(1, (os.cpu_count() or 4) // 2)
        self._model: Model | None = None

    def transcribe(self, samples: np.ndarray) -> str:
        if samples.size == 0:
            return ""
        if self._model is None:
            log.info("Loading whisper model: %s", self._model_path)
            self._model = Model(self._model_path, n_threads=self._n_threads)
        segments = self._model.transcribe(samples)
        return "".join(seg.text for seg in segments).strip()
```

- [ ] **Step 5: Run unit tests to verify pass**

Run: `uv run pytest tests/test_transcribe.py -v -m "not integration"`
Expected: 4 passed.

- [ ] **Step 6: Create fixture generator**

Create `tests/fixtures/generate.sh` (and `chmod +x`):

```bash
#!/usr/bin/env bash
# Regenerate test audio fixtures using macOS `say` and afconvert.
# Run from repo root: bash tests/fixtures/generate.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

# 1. quick-brown-fox.wav — speech sample for integration test
say -o "$DIR/_tmp.aiff" "the quick brown fox jumps over the lazy dog"
afconvert -f WAVE -d LEI16@16000 -c 1 "$DIR/_tmp.aiff" "$DIR/quick-brown-fox.wav"
rm "$DIR/_tmp.aiff"

# 2. silence.wav — 1 second of silence
afconvert -f WAVE -d LEI16@16000 -c 1 -o "$DIR/silence.wav" /dev/null 2>/dev/null || \
  python3 -c "
import wave, struct
with wave.open('$DIR/silence.wav', 'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b'\\x00\\x00' * 16000)
"

echo "Generated fixtures in $DIR"
ls -la "$DIR"/*.wav
```

- [ ] **Step 7: Generate fixtures and run integration test**

Run:
```bash
bash tests/fixtures/generate.sh
uv run pytest tests/test_transcribe.py::test_real_model_transcribes_quick_brown_fox -v -m integration
```
Expected: 1 passed (after pywhispercpp downloads tiny.en on first run, ~75 MB).

- [ ] **Step 8: Commit**

```bash
git add src/speech_to_text/transcribe.py tests/test_transcribe.py tests/fixtures pyproject.toml
git commit -m "feat(transcribe): pywhispercpp wrapper with lazy model load"
```

---

## Task 8: Hotkeys

**Files:**
- Create: `src/speech_to_text/hotkeys.py`
- Create: `tests/test_hotkeys.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_hotkeys.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hotkeys.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `hotkeys.py`**

Create `src/speech_to_text/hotkeys.py`:

```python
from __future__ import annotations

import logging
from typing import Callable

from pynput import keyboard

log = logging.getLogger(__name__)


def parse_single_key(spec: str) -> keyboard.Key:
    """Parse a `<keyname>` spec into a single `Key` enum value."""
    s = spec.strip()
    if not (s.startswith("<") and s.endswith(">")):
        raise ValueError(f"single-key spec must look like '<cmd_r>', got: {spec!r}")
    name = s[1:-1]
    try:
        return getattr(keyboard.Key, name)
    except AttributeError as e:
        raise ValueError(f"unknown key name: {name!r}") from e


class Hotkeys:
    def __init__(
        self,
        ptt_key: str,
        toggle_combo: str,
        on_ptt_press: Callable[[], None],
        on_ptt_release: Callable[[], None],
        on_toggle: Callable[[], None],
    ) -> None:
        self._ptt_key = parse_single_key(ptt_key)
        self._toggle_hotkey = keyboard.HotKey(
            keyboard.HotKey.parse(toggle_combo),
            on_toggle,
        )
        self._on_ptt_press = on_ptt_press
        self._on_ptt_release = on_ptt_release
        self._listener: keyboard.Listener | None = None

    def start(self) -> None:
        self._listener = keyboard.Listener(
            on_press=self._press_handler,
            on_release=self._release_handler,
        )
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _press_handler(self, key) -> None:
        try:
            if key == self._ptt_key:
                self._on_ptt_press()
            canonical = self._listener.canonical(key) if self._listener else key
            self._toggle_hotkey.press(canonical)
        except Exception:
            log.exception("error in press handler")

    def _release_handler(self, key) -> None:
        try:
            if key == self._ptt_key:
                self._on_ptt_release()
            canonical = self._listener.canonical(key) if self._listener else key
            self._toggle_hotkey.release(canonical)
        except Exception:
            log.exception("error in release handler")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hotkeys.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/speech_to_text/hotkeys.py tests/test_hotkeys.py
git commit -m "feat(hotkeys): pynput-backed PTT + toggle hotkey listener"
```

---

## Task 9: Daemon state machine

**Files:**
- Create: `src/speech_to_text/daemon.py`
- Create: `tests/test_daemon.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_daemon.py`:

```python
from unittest.mock import MagicMock

import numpy as np
import pytest

from speech_to_text.daemon import Daemon, State


@pytest.fixture
def deps():
    audio = MagicMock()
    transcriber = MagicMock()
    paster = MagicMock()
    sounds = MagicMock()
    notifier = MagicMock()
    hotkeys = MagicMock()

    audio.duration_seconds = 1.0
    audio.stop.return_value = np.ones(16000, dtype=np.float32)
    transcriber.transcribe.return_value = "hello world"
    paster.paste.return_value = True

    return {
        "audio": audio,
        "transcriber": transcriber,
        "paster": paster,
        "sounds": sounds,
        "notifier": notifier,
        "hotkeys": hotkeys,
    }


def _make_daemon(deps, min_ms=400, max_ms=300_000):
    return Daemon(
        hotkeys=deps["hotkeys"],
        audio=deps["audio"],
        transcriber=deps["transcriber"],
        paster=deps["paster"],
        sounds=deps["sounds"],
        notifier=deps["notifier"],
        min_duration_ms=min_ms,
        max_duration_ms=max_ms,
    )


def test_idle_to_recording_on_ptt_press(deps):
    d = _make_daemon(deps)
    d.on_ptt_press()
    assert d.state == State.RECORDING
    deps["audio"].start.assert_called_once()
    deps["sounds"].play.assert_called_with("tink.wav")


def test_full_happy_path(deps):
    d = _make_daemon(deps)
    d.on_ptt_press()
    d.on_ptt_release()
    deps["audio"].stop.assert_called_once()
    deps["transcriber"].transcribe.assert_called_once()
    deps["paster"].paste.assert_called_once_with("hello world")
    deps["sounds"].play.assert_any_call("ding.wav")
    assert d.state == State.IDLE


def test_too_short_recording_silently_returns_to_idle(deps):
    deps["audio"].duration_seconds = 0.1  # 100 ms — below 400 ms threshold
    deps["audio"].stop.return_value = np.zeros(1600, dtype=np.float32)
    d = _make_daemon(deps, min_ms=400)
    d.on_ptt_press()
    d.on_ptt_release()
    deps["transcriber"].transcribe.assert_not_called()
    deps["paster"].paste.assert_not_called()
    deps["notifier"].assert_not_called()
    # No error sound should play
    sound_calls = [c.args[0] for c in deps["sounds"].play.call_args_list]
    assert "error.wav" not in sound_calls
    assert d.state == State.IDLE


def test_empty_transcription_returns_to_idle_silently(deps):
    deps["transcriber"].transcribe.return_value = ""
    d = _make_daemon(deps)
    d.on_ptt_press()
    d.on_ptt_release()
    deps["paster"].paste.assert_not_called()
    sound_calls = [c.args[0] for c in deps["sounds"].play.call_args_list]
    assert "error.wav" not in sound_calls
    assert d.state == State.IDLE


def test_paste_failure_plays_error_and_notifies(deps):
    deps["paster"].paste.return_value = False
    d = _make_daemon(deps)
    d.on_ptt_press()
    d.on_ptt_release()
    deps["sounds"].play.assert_any_call("error.wav")
    deps["notifier"].assert_called()
    assert d.state == State.IDLE


def test_transcription_exception_returns_to_idle_with_error(deps):
    deps["transcriber"].transcribe.side_effect = RuntimeError("whisper boom")
    d = _make_daemon(deps)
    d.on_ptt_press()
    d.on_ptt_release()
    deps["sounds"].play.assert_any_call("error.wav")
    deps["notifier"].assert_called()
    deps["paster"].paste.assert_not_called()
    assert d.state == State.IDLE


def test_toggle_starts_recording_when_idle(deps):
    d = _make_daemon(deps)
    d.on_toggle()
    assert d.state == State.RECORDING
    deps["audio"].start.assert_called_once()


def test_toggle_stops_recording_when_recording(deps):
    d = _make_daemon(deps)
    d.on_toggle()
    d.on_toggle()
    deps["paster"].paste.assert_called_once()
    assert d.state == State.IDLE


def test_max_duration_hard_stops(deps):
    deps["audio"].duration_seconds = 400.0  # 400 s, above 300 s max
    d = _make_daemon(deps, max_ms=300_000)
    d.on_ptt_press()
    d.on_max_duration_check()
    deps["audio"].stop.assert_called_once()


def test_audio_start_failure_returns_to_idle_with_error(deps):
    """Mic permission denied or device unavailable: notify + error sound, state IDLE."""
    deps["audio"].start.side_effect = OSError("mic permission denied")
    d = _make_daemon(deps)
    d.on_ptt_press()
    deps["sounds"].play.assert_any_call("error.wav")
    deps["notifier"].assert_called()
    assert d.state == State.IDLE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_daemon.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `daemon.py`**

Create `src/speech_to_text/daemon.py`:

```python
from __future__ import annotations

import enum
import logging
import threading
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)


class State(enum.Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    PASTING = "pasting"


class Daemon:
    def __init__(
        self,
        hotkeys,
        audio,
        transcriber,
        paster,
        sounds,
        notifier: Callable[[str, str], None],
        min_duration_ms: int = 400,
        max_duration_ms: int = 300_000,
    ) -> None:
        self._hotkeys = hotkeys
        self._audio = audio
        self._transcriber = transcriber
        self._paster = paster
        self._sounds = sounds
        self._notifier = notifier
        self._min_duration_s = min_duration_ms / 1000.0
        self._max_duration_s = max_duration_ms / 1000.0
        self._state = State.IDLE
        self._lock = threading.Lock()

    @property
    def state(self) -> State:
        return self._state

    def on_ptt_press(self) -> None:
        with self._lock:
            if self._state == State.IDLE:
                self._start_recording()

    def on_ptt_release(self) -> None:
        with self._lock:
            if self._state == State.RECORDING:
                self._stop_and_process()

    def on_toggle(self) -> None:
        with self._lock:
            if self._state == State.IDLE:
                self._start_recording()
            elif self._state == State.RECORDING:
                self._stop_and_process()
            # If TRANSCRIBING or PASTING, ignore — too late to cancel cleanly

    def on_max_duration_check(self) -> None:
        """Periodic call from a watchdog timer; force-stops over-long recordings."""
        with self._lock:
            if (
                self._state == State.RECORDING
                and self._audio.duration_seconds >= self._max_duration_s
            ):
                log.warning(
                    "Recording exceeded max duration (%ss); hard-stopping",
                    self._max_duration_s,
                )
                self._stop_and_process()

    def _start_recording(self) -> None:
        try:
            self._audio.start()
        except Exception as e:
            log.exception("Failed to start audio capture: %s", e)
            self._sounds.play("error.wav")
            self._notifier(
                "Speech-to-Text",
                f"Couldn't start microphone: {e}. "
                "Check System Settings → Privacy & Security → Microphone.",
            )
            self._state = State.IDLE
            return
        self._state = State.RECORDING
        self._sounds.play("tink.wav")

    def _stop_and_process(self) -> None:
        duration = self._audio.duration_seconds
        samples = self._audio.stop()
        self._state = State.TRANSCRIBING

        if duration < self._min_duration_s or samples.size == 0:
            log.debug("Recording too short (%.3fs); discarding", duration)
            self._state = State.IDLE
            return

        try:
            text = self._transcriber.transcribe(samples)
        except Exception as e:
            log.exception("Transcription failed: %s", e)
            self._sounds.play("error.wav")
            self._notifier("Speech-to-Text", f"Transcription failed: {e}")
            self._state = State.IDLE
            return

        if not text:
            log.debug("Empty transcription; ignoring")
            self._state = State.IDLE
            return

        self._state = State.PASTING
        try:
            ok = self._paster.paste(text)
        except Exception as e:
            log.exception("Paste failed: %s", e)
            self._sounds.play("error.wav")
            self._notifier(
                "Speech-to-Text",
                f"Transcribed but couldn't paste: {e}. Text is on your clipboard.",
            )
            self._state = State.IDLE
            return

        if not ok:
            self._sounds.play("error.wav")
            self._notifier(
                "Speech-to-Text",
                "Transcribed but couldn't paste. Text is on your clipboard.",
            )
        else:
            self._sounds.play("ding.wav")
        self._state = State.IDLE
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_daemon.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/speech_to_text/daemon.py tests/test_daemon.py
git commit -m "feat(daemon): state machine wiring hotkeys → audio → transcribe → paste"
```

---

## Task 10: launchd plist generation

**Files:**
- Create: `src/speech_to_text/launchd.py`
- Create: `tests/test_launchd.py`
- Create: `tests/fixtures/expected.plist`

- [ ] **Step 1: Write failing tests**

Create `tests/test_launchd.py`:

```python
from pathlib import Path

import pytest

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
    assert "<string>start</string>" in out  # passes the `start` subcommand
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
```

- [ ] **Step 2: Create golden fixture**

Create `tests/fixtures/expected.plist` (exact contents — note no trailing newlines added by shell):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.user.speechtotext</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/stt</string>
    <string>start</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/var/log/stt.log</string>
  <key>StandardErrorPath</key>
  <string>/var/log/stt.log</string>
  <key>ProcessType</key>
  <string>Interactive</string>
</dict>
</plist>
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_launchd.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement `launchd.py`**

Create `src/speech_to_text/launchd.py`:

```python
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

LABEL = "com.user.speechtotext"

_PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{program_path}</string>
    <string>start</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{log_path}</string>
  <key>StandardErrorPath</key>
  <string>{log_path}</string>
  <key>ProcessType</key>
  <string>Interactive</string>
</dict>
</plist>
"""


def render_plist(program_path: str, log_path: str) -> str:
    return _PLIST_TEMPLATE.format(
        label=LABEL, program_path=program_path, log_path=log_path
    )


def plist_path() -> Path:
    return Path(os.path.expanduser("~/Library/LaunchAgents")) / f"{LABEL}.plist"


def write_plist(program_path: str, log_path: str) -> Path:
    p = plist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_plist(program_path, log_path))
    return p


def enable() -> None:
    p = plist_path()
    if not p.exists():
        raise FileNotFoundError(
            f"plist not found at {p}; run `stt install` first"
        )
    subprocess.run(["launchctl", "load", "-w", str(p)], check=True)


def disable() -> None:
    p = plist_path()
    if not p.exists():
        return
    subprocess.run(["launchctl", "unload", "-w", str(p)], check=False)


def is_loaded() -> bool:
    completed = subprocess.run(
        ["launchctl", "list"],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in completed.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2] == LABEL:
            return True
    return False
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_launchd.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add src/speech_to_text/launchd.py tests/test_launchd.py tests/fixtures/expected.plist
git commit -m "feat(launchd): plist generation and load/unload commands"
```

---

## Task 11: CLI subcommands

**Files:**
- Modify: `src/speech_to_text/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cli.py`:

```python
import pytest

from speech_to_text.cli import main


def test_no_args_shows_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])
    captured = capsys.readouterr()
    assert "usage:" in captured.out.lower() or "usage:" in captured.err.lower()
    assert exc.value.code != 0


def test_install_creates_config_and_plist(mocker, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    mocker.patch("speech_to_text.cli._download_model")  # don't actually download

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
    daemon_run = mocker.patch("speech_to_text.cli._run_daemon_foreground")
    rc = main(["start"])
    assert rc == 0
    daemon_run.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — current `cli.main()` only prints a placeholder.

- [ ] **Step 3: Implement `cli.py`**

Replace `src/speech_to_text/cli.py`:

```python
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

DEFAULT_MODEL = "ggml-small.en.bin"
MODEL_URL = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/" + DEFAULT_MODEL
)

DEFAULT_CONFIG_BODY = textwrap.dedent("""\
    [hotkeys]
    push_to_talk = "<cmd_r>"
    toggle = "<ctrl>+<shift>+<space>"

    [model]
    name = "small.en"
    path = "~/.local/share/speech-to-text/models/ggml-small.en.bin"

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
    p = argparse.ArgumentParser(prog="stt", description="Local-first speech-to-text dictation daemon")
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
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(dest)
    print("Model downloaded.")


def _run_daemon_foreground() -> int:
    """Wire all components and run the daemon until interrupted. Defined here
    rather than in `daemon.py` so unit tests for the state machine remain
    free of real I/O imports."""
    from speech_to_text import audio as audio_mod
    from speech_to_text import config as config_mod
    from speech_to_text import notifications, sounds as sounds_mod
    from speech_to_text.daemon import Daemon
    from speech_to_text.hotkeys import Hotkeys
    from speech_to_text.paste import Paster
    from speech_to_text.transcribe import Transcriber

    cfg = config_mod.load(CONFIG_FILE)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, cfg.logging.level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE)],
    )

    asset_dir = Path(__file__).parent / "assets" / "sounds"
    sounds = sounds_mod.Sounds(asset_dir=asset_dir, enabled=cfg.sounds.enabled)
    paster = Paster(restore_delay_ms=cfg.paste.restore_clipboard_delay_ms)
    transcriber = Transcriber(cfg.model.path)
    audio = audio_mod.Recorder(
        sample_rate=cfg.audio.sample_rate,
        input_device=cfg.audio.input_device,
    )

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
    log.info("Daemon ready. Push-to-talk: %s | Toggle: %s",
             cfg.hotkeys.push_to_talk, cfg.hotkeys.toggle)

    try:
        import threading
        threading.Event().wait()  # block forever
    except KeyboardInterrupt:
        log.info("Shutting down")
        hotkeys.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: 7 passed.

- [ ] **Step 5: Verify smoke test still passes**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/speech_to_text/cli.py tests/test_cli.py
git commit -m "feat(cli): install/enable/disable/status/start/logs/config/uninstall subcommands"
```

---

## Task 12: Bundle audio cue assets

**Files:**
- Create: `src/speech_to_text/assets/sounds/tink.wav`
- Create: `src/speech_to_text/assets/sounds/ding.wav`
- Create: `src/speech_to_text/assets/sounds/error.wav`
- Create: `scripts/generate_sounds.sh`

- [ ] **Step 1: Write the generator script**

Create `scripts/generate_sounds.sh` (and `chmod +x`):

```bash
#!/usr/bin/env bash
# Generate the three audio cue files using macOS built-in sound effects.
# Run from repo root: bash scripts/generate_sounds.sh
set -euo pipefail

OUT_DIR="src/speech_to_text/assets/sounds"
mkdir -p "$OUT_DIR"

# macOS ships .aiff system sounds at /System/Library/Sounds.
# Convert to WAV (afplay handles either, but WAV is portable).
SRC="/System/Library/Sounds"
afconvert -f WAVE -d LEI16 "$SRC/Tink.aiff"   "$OUT_DIR/tink.wav"
afconvert -f WAVE -d LEI16 "$SRC/Glass.aiff"  "$OUT_DIR/ding.wav"
afconvert -f WAVE -d LEI16 "$SRC/Sosumi.aiff" "$OUT_DIR/error.wav"

echo "Generated:"
ls -la "$OUT_DIR"/*.wav
```

- [ ] **Step 2: Run it**

Run:
```bash
bash scripts/generate_sounds.sh
```
Expected: three `.wav` files in `src/speech_to_text/assets/sounds/`.

- [ ] **Step 3: Manually play each and confirm they sound right**

Run:
```bash
afplay src/speech_to_text/assets/sounds/tink.wav
afplay src/speech_to_text/assets/sounds/ding.wav
afplay src/speech_to_text/assets/sounds/error.wav
```

- [ ] **Step 4: Update `.gitignore` to include assets but exclude model files**

The current `.gitignore` excludes `*.bin`. Confirm it does **not** exclude `*.wav`. The file from Task 1 already gets this right; just verify with:

```bash
git check-ignore -v src/speech_to_text/assets/sounds/tink.wav || echo "(not ignored — good)"
```
Expected: `(not ignored — good)`.

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_sounds.sh src/speech_to_text/assets/sounds/*.wav
git commit -m "feat(sounds): bundle tink/ding/error audio cues from macOS system sounds"
```

---

## Task 13: README and manual test plan

**Files:**
- Create: `README.md`
- Create: `docs/manual-test-plan.md`

- [ ] **Step 1: Write `README.md`**

Create `README.md`:

````markdown
# speech-to-text

Local-first macOS speech-to-text dictation. Press a hotkey, speak, get text into whatever app is focused. Audio never leaves your machine — transcription runs locally via [whisper.cpp](https://github.com/ggerganov/whisper.cpp).

## Install

```bash
uv tool install speech-to-text   # or: pipx install speech-to-text
stt install                       # downloads model, writes config + LaunchAgent
stt enable                        # start daemon, enable auto-start at login
```

On first run, macOS prompts for **Microphone** and **Accessibility** permissions. Grant both in System Settings → Privacy & Security.

## Usage

| Action | Default |
|---|---|
| Push-to-talk: hold key, speak, release | Right Command (`⌘ Right`) |
| Toggle: tap to start, tap again to stop | `⌃⇧ Space` |

A "tink" plays when recording starts. A soft "ding" plays when the transcribed text is pasted. An "uh-oh" plays on error (with a notification explaining what happened).

## Commands

| Command | What it does |
|---|---|
| `stt install` | One-time setup: write config, download model, install LaunchAgent |
| `stt enable` | Start daemon and auto-start at login |
| `stt disable` | Stop daemon and disable auto-start |
| `stt status` | Is the daemon running? |
| `stt start` | Foreground run for debugging (bypasses launchd) |
| `stt logs` | Tail the daemon log |
| `stt config` | Open `~/.config/speech-to-text/config.toml` in `$EDITOR` |
| `stt uninstall [--purge]` | Remove LaunchAgent (and config/models with `--purge`) |

## Configuration

Edit `~/.config/speech-to-text/config.toml`:

```toml
[hotkeys]
push_to_talk = "<cmd_r>"               # hold to record
toggle = "<ctrl>+<shift>+<space>"      # tap to start/stop

[model]
name = "small.en"                      # tiny.en | base.en | small.en | medium.en
path = "~/.local/share/speech-to-text/models/ggml-small.en.bin"

[audio]
min_duration_ms = 400                  # ignore taps under this length
max_duration_ms = 300000               # hard-stop after 5 min

[sounds]
enabled = true
```

After editing, restart: `stt disable && stt enable`.

## Privacy

- Audio is captured to memory only — never written to disk.
- Transcription happens 100% locally. No internet calls.
- The clipboard is snapshotted before paste and restored after, so dictation does not stomp on your existing copy/paste content.
````

- [ ] **Step 2: Write `docs/manual-test-plan.md`**

Create `docs/manual-test-plan.md`:

```markdown
# Manual Test Plan

These tests cover behaviour that depends on real macOS permissions and hardware events, so they are not automated. Run before each release.

## Pre-flight

- [ ] Fresh install: `stt uninstall --purge` then `stt install` — config, model, and plist appear in expected locations
- [ ] `stt enable` — daemon shows as running in `stt status`
- [ ] First run prompts for Microphone permission — grant
- [ ] First run prompts for Accessibility permission — grant
- [ ] Restart: `stt disable && stt enable`

## Push-to-talk

- [ ] Focus a TextEdit window
- [ ] Hold Right Command, say "the quick brown fox", release
- [ ] "Tink" plays on press, "ding" plays on paste, text appears in TextEdit
- [ ] Repeat in: Slack, iMessage, Notes, Safari address bar, VS Code, Terminal
- [ ] Tap Right Command for <400 ms — silently does nothing (no error sound)
- [ ] Hold Right Command, say nothing for 1 second, release — silently does nothing

## Toggle

- [ ] Tap `⌃⇧ Space` (no app focus change), speak, tap again — text is pasted
- [ ] During recording, switch focus to a different app, then tap `⌃⇧ Space` — text pastes into the new app

## Clipboard preservation

- [ ] Copy "before" to clipboard. Use dictation to type "during". Verify clipboard contains "before" again after the paste

## Error paths

- [ ] Disable Microphone permission in System Settings → use a hotkey → notification appears, error sound plays
- [ ] Re-enable, restart daemon, dictation works
- [ ] Edit config to point `model.path` at a nonexistent file → restart daemon → notification + log entry → daemon exits
- [ ] Restore valid path, restart, dictation works

## Auto-start

- [ ] `stt enable`, then log out and back in → daemon is running automatically

## Crash recovery

- [ ] `pkill -f "speech_to_text"` while daemon is enabled → launchd restarts it within a second (verify with `stt status` and timestamps in `stt logs`)
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/manual-test-plan.md
git commit -m "docs: README and manual test plan"
```

---

## Task 14: Final integration smoke

**Files:** none new — full end-to-end exercise.

- [ ] **Step 1: Run the full unit test suite**

Run: `uv run pytest -v -m "not integration"`
Expected: all tests pass (config 4 + sounds 4 + notifications 3 + paste 3 + audio 5 + transcribe 4 + hotkeys 5 + daemon 10 + launchd 7 + cli 7 + smoke 2 = 54 tests).

- [ ] **Step 2: Run the integration test**

Run: `uv run pytest -v -m integration`
Expected: 1 passed (`test_real_model_transcribes_quick_brown_fox`).

- [ ] **Step 3: Install and exercise on real Mac**

Run:
```bash
uv pip install -e .
stt install
stt enable
```

- [ ] **Step 4: Walk through manual test plan**

Open `docs/manual-test-plan.md` and tick each item. If anything fails, file a bug, fix it (with a regression test if possible), and commit the fix before continuing.

- [ ] **Step 5: Final commit**

If everything passed without code changes, no commit needed — the project is ready.

If you made fixes during manual testing, commit them with descriptive messages, e.g.:

```bash
git commit -m "fix(paste): wait additional 50 ms in Slack to avoid premature clipboard restore"
```

---

## Self-review checklist (run before handing off implementation)

After working through every task, verify:

- [ ] Every section of the spec maps to at least one task (Tasks 1–14 cover §1–§9 of the design doc)
- [ ] Every code block is real, runnable code — no `# TODO` or `# fill in here`
- [ ] Function and method names are consistent across tasks (e.g., `Recorder.start()` / `Recorder.stop()`, `Paster.paste()`, `Daemon.on_ptt_press()`, `launchd.enable()`)
- [ ] All test files import only modules created in earlier tasks
- [ ] All file paths in tests match the paths the implementation creates
- [ ] No dependency is introduced without being in `pyproject.toml`
