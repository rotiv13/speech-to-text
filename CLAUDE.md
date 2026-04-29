# CLAUDE.md

Operational notes for Claude instances working in this repo. The README is for end users; this file is for engineering.

## What this is

A macOS-only Python daemon that runs as a `launchd` LaunchAgent. Hotkeys (`pynput`) trigger mic capture (`sounddevice`), audio is transcribed locally via `whisper.cpp` bindings (`pywhispercpp`), and the result is pasted into the focused app via `NSPasteboard` + a synthesized `⌘V` (`pyobjc`). Single process, single state machine, no IPC.

The authoritative design and per-task plan live here:

- [`docs/superpowers/specs/2026-04-29-speech-to-text-design.md`](docs/superpowers/specs/2026-04-29-speech-to-text-design.md)
- [`docs/superpowers/plans/2026-04-29-speech-to-text.md`](docs/superpowers/plans/2026-04-29-speech-to-text.md)

Read the spec before making non-trivial changes. The §5 state diagram and §6 error table are the parts that matter most.

## Common commands

```bash
# Run the fast suite (54 unit tests; runs in <1 s)
uv run pytest -m "not integration"

# Run the integration test (downloads tiny.en if absent, hits real whisper.cpp)
uv run pytest -m integration

# Run everything
uv run pytest

# Coverage
uv run pytest --cov=src --cov-report=term-missing

# Reinstall the daemon after code changes (the LaunchAgent runs the
# uv-tool-installed copy, NOT the working tree)
uv tool install --reinstall --force .

# Daemon control
stt install            # one-time: writes config, downloads model, writes plist
stt enable             # launchctl load
stt disable            # launchctl unload
stt status             # is the daemon running?
stt start              # foreground for debugging — bypasses launchd
stt logs               # tail ~/Library/Logs/speech-to-text/daemon.log

# Useful diagnostic
launchctl list | grep speechtotext
ps -p $(launchctl list | awk '/speechtotext/{print $1}') -o pid,stat,command
```

## Repo layout

```
src/speech_to_text/
  __main__.py     # python -m speech_to_text → cli.main
  cli.py          # argparse subcommands; _run_daemon_foreground wires everything
  config.py       # frozen dataclasses, TOML loader, defaults
  daemon.py       # state machine: IDLE → RECORDING → TRANSCRIBING → PASTING → IDLE
  hotkeys.py      # pynput Listener wrapping PTT key + HotKey for the toggle combo
  audio.py        # sounddevice mic capture; 16 kHz mono float32; queue-based
  transcribe.py   # pywhispercpp Model wrapper; lazy load + whitespace normalization
  paste.py        # NSPasteboard snapshot/restore + CGEvent ⌘V
  sounds.py       # afplay subprocess.Popen; non-blocking
  notifications.py# osascript with argv-passed title/body (escape-safe)
  launchd.py      # plist render/install/load/unload
  assets/sounds/  # tink.wav, ding.wav, error.wav (from /System/Library/Sounds)

tests/
  test_*.py       # one file per module; mocks for all side-effect modules
  fixtures/
    expected.plist            # golden launchd plist
    quick-brown-fox.wav       # 16 kHz mono — generate.sh recreates it via `say`
    silence.wav               # for empty-transcription path
```

## Module boundaries (don't blur these)

- The daemon never imports `pynput`, `sounddevice`, `AppKit`, or `Quartz` directly. It only sees its own internal types — `Recorder`, `Hotkeys`, `Paster`, `Transcriber`, `Sounds`, plus a `notifier` callable. Keep it that way; that's why daemon tests are pure-mock and run in milliseconds.
- Side-effect modules (`paste`, `audio`, `sounds`, `notifications`, `hotkeys`, `launchd`) are the only places that talk to the OS. Each one has the OS-specific imports at the top of its file. If you find yourself importing `Quartz` in `daemon.py`, stop and rethink.
- `transcribe.py` is the only place that imports `pywhispercpp`. The `Transcriber` class hides the model lifecycle.

## Gotchas (real bugs we hit)

1. **`pywhispercpp` defaults `language="en"` via whisper.cpp's C side.** Multilingual models will silently force-transcribe Portuguese as English unless you pass `language=""` (whisper.cpp's "no language pin, auto-detect" sentinel). The string `"auto"` is rejected with `unknown language 'auto'`. There's a regression test (`test_model_constructed_with_empty_language_for_auto_detect`) — leave it in place.

2. **macOS Accessibility permission is granted to the resolved binary, not the symlink.** `~/.local/bin/stt` resolves through several symlinks down to `/opt/homebrew/Cellar/python@3.14/.../Python.app`. That `Python.app` bundle is what System Settings → Privacy & Security → Accessibility lists, and what permission must be granted to. After `uv tool install --reinstall --force .`, the resolved binary path is stable, so the grant survives.

3. **Pre-push hook calls bare `pytest`.** The user's global hook (`~/.codex/git-hooks/pre-push`) runs `pytest -q` from `$PATH`, not `uv run pytest`. If you push from a fresh shell you'll see import errors for every test file. Workarounds: `source .venv/bin/activate` before `git push`, OR run `uv sync` first to ensure deps are resolvable from a system pytest. Don't bypass the hook with `--no-verify`.

4. **launchd captures stdout AND stderr to the same log file.** Don't add a `logging.FileHandler` on top of the `StreamHandler` — every line will appear twice. `cli._run_daemon_foreground` deliberately uses `StreamHandler` only.

5. **Daemon worker thread.** `Daemon.on_ptt_release` returns immediately and dispatches transcribe+paste to a worker thread. This matters for tests: call `daemon.wait_idle()` before assertions, or the worker won't have run yet. It also means a second hotkey press while transcribing/pasting is silently dropped (not queued — see `Daemon.on_toggle` for the conditional).

6. **`sounds.Sounds.play` uses `Popen`, not `run`.** Audio cues must not block the state-machine thread. There's a test that asserts `.wait()` is never called on the returned process.

## Testing conventions

- TDD strictly: failing test → minimum impl → green → commit. Plan tasks 2-13 follow this pattern.
- Mock at the module-import boundary: `mocker.patch("speech_to_text.sounds.subprocess.Popen")`, not at `subprocess.Popen` globally.
- Integration tests are marked `@pytest.mark.integration` and excluded from the default run via `-m "not integration"`.
- 80% coverage target (rule from `~/.claude/rules/common/testing.md`). The exemptions are `hotkeys.py` and the OS-shell-out parts of `launchd.py`, which are covered by manual smoke testing in [`docs/manual-test-plan.md`](docs/manual-test-plan.md).
- When adding a side-effect module, add the corresponding `tests/test_*.py` with the side-effect mocked at import boundary. Don't add tests that require real microphone, real keyboard hooks, or real notifications — those go in the manual test plan.

## Style & rules

User-global rules apply (see `~/.claude/rules/python/`):

- Frozen `@dataclass` for any value type
- PEP 8, type hints on every public signature
- Files <800 lines; functions <50 lines; nesting <4 levels
- No `print()` in library code — use `logging`. The CLI subcommand handlers in `cli.py` use `print()` deliberately for user-facing output and that's fine.

Project additions:

- Each new module gets its own file with one responsibility. Don't grow `daemon.py` or `cli.py` past their current scope.
- Conventional Commits in commit messages (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- One module per commit when possible (see git log on commits up to `54333ab`).

## Common workflows

### Adding a new module

1. Add the failing test first (`tests/test_<name>.py`).
2. Run it; confirm it fails for the right reason (`ModuleNotFoundError`, not a typo).
3. Implement `src/speech_to_text/<name>.py` with the narrowest interface that makes the test pass.
4. Wire it into `cli._run_daemon_foreground` if it's a runtime dep.
5. Run the full unit suite. Commit with `feat(<name>): ...`.

### Changing the model

`config.py` (`ModelConfig.name`, `DEFAULT_MODEL_PATH`), `cli.py` (`DEFAULT_MODEL`, `DEFAULT_CONFIG_BODY`), `tests/test_config.py` (default assertion), `README.md`, and the spec doc all mention the model name. Update all six. The user's own `~/.config/speech-to-text/config.toml` is independent — they may need a migration step.

### Changing daemon behavior

Read the spec §5 (state diagram) and §6 (error table) first. The state machine is the contract; deviations should be reflected in the spec, not just the code. Add a daemon test for each new transition or error path before changing `daemon.py`.

### Pushing changes

1. `uv run pytest -m "not integration"` — must pass.
2. `source .venv/bin/activate && git push` — needed for the global pre-push hook to find pytest.
3. Open a PR via `gh pr create` rather than merging directly to `main`. The user's preference is PR-based review even on solo work.

## Environment

- Python 3.11+ (stdlib `tomllib`). Verified on 3.14.
- macOS 13+ for the modern `launchctl` semantics. The hook uses `launchctl load -w` which still works on Sequoia but will need migration to `launchctl bootstrap` eventually.
- `uv` for tool installation (`uv tool install`). Project deps locked in `uv.lock`.

## When in doubt

- Read the spec.
- Run the tests.
- Look at `git log --oneline` — commits up to `54333ab` are organized one-module-per-commit and document the build order.
