# Speech-to-Text — Design

**Date:** 2026-04-29
**Status:** Approved (pre-implementation)
**Owner:** vvitorafonso@gmail.com

A macOS background daemon that transcribes speech to text on demand and pastes
the result into the focused application. Triggered by a hold-to-talk hotkey or
a tap-to-toggle hotkey. Transcription runs locally via `whisper.cpp` — no
network calls, no API key, no per-minute cost.

---

## 1. Goals & non-goals

### Goals

- Press a hotkey, speak, get text into whatever app is focused — Slack,
  iMessage, browser, IDE, Notes, anywhere.
- Local-only transcription. Audio never leaves the machine.
- Zero-friction daily use: install once, forget about it. Auto-start on login,
  auto-restart on crash.
- Configurable hotkeys, model, and audio cues without touching code.

### Non-goals

- No GUI / menu bar app (audio cues are sufficient feedback).
- No streaming transcription (record-then-paste is the workflow; words do not
  appear live as the user speaks).
- No multi-platform support. macOS only. Linux / Windows are out of scope.
- No cloud transcription backend in v1. Architecture leaves room to add one
  later via the pluggable `Transcriber` interface, but the only shipped
  implementation is `whisper.cpp`.
- No automatic punctuation / formatting beyond what the model produces.
- No translation, summarization, or any post-processing of transcribed text.

---

## 2. User experience

### Daily flow

1. User installs once: `uv tool install speech-to-text` → `stt install` →
   `stt enable`. macOS prompts for Microphone and Accessibility permissions.
2. From then on, the daemon runs automatically at login.
3. User focuses any app where they want to type.
4. User holds Right Command, speaks, releases. Or taps Control+Shift+Space,
   speaks, taps again to stop.
5. A short "tink" plays when recording starts. A soft "ding" plays when the
   transcribed text appears at the cursor (pasted via simulated `⌘V`).
6. The clipboard contents from before dictation are restored.

### Defaults

- **Push-to-talk:** hold Right Command (`⌘ Right`).
- **Toggle:** Control+Shift+Space (`⌃⇧ Space`).
- **Model:** `ggml-small.bin` (~488 MB, multilingual). Whisper auto-detects
  language per utterance — no explicit language config required.
  English-only `ggml-small.en.bin` is also supported via config swap for
  users who only dictate English and want a slightly snappier model.
- **Audio cues:** on for record-start, paste-success, and errors.
- **Notifications:** off for normal flow. Shown only for errors the user needs
  to know about: permission issues, paste failures, and transcription
  crashes. See §6 for the full list.

All of the above are settable in `~/.config/speech-to-text/config.toml`.

---

## 3. High-level architecture

A single Python process running as a macOS LaunchAgent. It registers two
global hotkeys, captures mic audio while a hotkey is active, runs the audio
through a local `whisper.cpp` model held in memory, and pastes the result
into whatever app has focus.

```
┌────────────────────────────────────────────────────────────┐
│              launchd LaunchAgent (auto-start)              │
│                                                            │
│  ┌──────────┐    ┌──────────┐    ┌─────────────────────┐   │
│  │ hotkeys  ├───►│  daemon  │◄───┤  whisper.cpp model  │   │
│  │ (pynput) │    │ (state   │    │  (loaded once into  │   │
│  └──────────┘    │  machine)│    │   memory at start)  │   │
│                  └─────┬────┘    └─────────────────────┘   │
│                        │                                   │
│             ┌──────────┼──────────┐                        │
│             ▼          ▼          ▼                        │
│        ┌────────┐ ┌────────┐ ┌────────┐                    │
│        │ audio  │ │ paste  │ │ sounds │                    │
│        │capture │ │(clip + │ │ (cues) │                    │
│        │        │ │ Cmd+V) │ │        │                    │
│        └────────┘ └────────┘ └────────┘                    │
└────────────────────────────────────────────────────────────┘
```

The model is loaded once at daemon start (~1–2 s) and held in RAM, so each
utterance pays only inference time, not model-load time. Each side-effect
module is small and independently testable.

---

## 4. Components & boundaries

| Module | Job | Public interface | Dependencies |
|---|---|---|---|
| `daemon.py` | State machine: `IDLE → RECORDING → TRANSCRIBING → PASTING → IDLE`. Wires components together. | `run()` — blocks forever | hotkeys, audio, transcribe, paste, sounds |
| `hotkeys.py` | Listen for global hotkeys, emit events | `Hotkeys(on_ptt_press, on_ptt_release, on_toggle).start()` | `pynput` |
| `audio.py` | Record from default mic at 16 kHz mono | `Recorder.start()` / `Recorder.stop() -> np.ndarray[float32]` | `sounddevice` |
| `transcribe.py` | Run audio through `whisper.cpp` | `Transcriber(model_path).transcribe(samples) -> str` | `pywhispercpp` |
| `paste.py` | Save clipboard, paste text, restore clipboard | `paste(text)` | `pyobjc` (NSPasteboard, CGEventPost) |
| `sounds.py` | Play short audio cues from disk | `play("tink"\|"ding"\|"error")` | `afplay` via subprocess |
| `config.py` | Load TOML, apply defaults | `load() -> Config` | stdlib `tomllib` |
| `launchd.py` | Generate, install, load, unload the LaunchAgent plist | `install()`, `enable()`, `disable()`, `status()` | stdlib + `launchctl` shell-out |
| `notifications.py` | Display macOS notifications for errors | `notify(title, body)` | `osascript` via subprocess |
| `cli.py` | Subcommands | `main()` | `argparse`, launchd |

The daemon never imports `pynput`, `sounddevice`, or `NSPasteboard` directly
— it only sees its own internal interfaces. Each external dependency can be
mocked for unit tests, and any one of them can be swapped later (e.g.,
replace `pynput` with a Swift hotkey helper) without touching daemon logic.

### File layout

```
speech-to-text/
├── pyproject.toml
├── README.md
├── docs/
│   ├── manual-test-plan.md
│   └── superpowers/specs/2026-04-29-speech-to-text-design.md
├── src/speech_to_text/
│   ├── __init__.py
│   ├── __main__.py        # python -m speech_to_text → daemon
│   ├── cli.py
│   ├── daemon.py
│   ├── hotkeys.py
│   ├── audio.py
│   ├── transcribe.py
│   ├── paste.py
│   ├── sounds.py
│   ├── config.py
│   ├── launchd.py
│   ├── notifications.py
│   └── assets/sounds/{tink,ding,error}.wav
└── tests/
    ├── fixtures/{quick-brown-fox.wav,silence.wav,expected.plist}
    └── test_*.py
```

---

## 5. Data flow & state machine

```
                    ┌──────────────────────────┐
                    │           IDLE           │
                    └─┬────────────────────┬───┘
            ptt_press │                    │ toggle
            (Right ⌘) │                    │ (⌃⇧ Space)
                      ▼                    ▼
                    ┌──────────────────────────┐
                    │        RECORDING         │◄──┐
                    │  (audio frames → queue)  │   │
                    └─┬────────────────────┬───┘   │
        ptt_release   │                    │ toggle│
                      ▼                    │       │
                    ┌──────────────────────┴────┐  │
                    │       TRANSCRIBING        │  │
                    │  (whisper.cpp on samples) │  │
                    └─┬────────────────────┬────┘  │
            text != ""│                    │ ""    │
                      ▼                    │       │
                    ┌──────────────────────┴────┐  │
                    │         PASTING           │  │
                    │  (clip save → ⌘V → restore)│ │
                    └─┬─────────────────────────┘  │
                      │                            │
                      └──────► back to IDLE ───────┘
```

### Sequence for one dictation

1. **Hotkey fires** → daemon transitions `IDLE → RECORDING`, plays `tink`,
   calls `audio.start()`. `sounddevice` opens 16 kHz mono stream and pushes
   raw float32 frames into an internal queue.
2. **Hotkey released (or toggle tapped again)** → daemon transitions
   `RECORDING → TRANSCRIBING`, calls `audio.stop()` which drains the queue
   and concatenates into a single numpy array.
3. **Guards:**
   - If recording duration < 400 ms, abort silently and return to IDLE
     (accidental key tap).
   - If recording duration > 5 min, hard-stop the stream and continue with
     what we captured.
4. **Transcribe:** `transcribe.transcribe(samples)` runs `whisper.cpp` on
   the array (already in 16 kHz mono float32, the format `whisper.cpp`
   wants — no resampling). Returns plain text. Typical latency: ~1 s for
   `small` on a 30 s clip on Apple Silicon.
5. **Paste:** daemon transitions `TRANSCRIBING → PASTING`. Snapshot current
   clipboard for all types (string, RTF, image), put text on clipboard,
   simulate `⌘V` via `CGEventPost`, sleep 200 ms (so the target app has
   time to read the clipboard), restore the snapshot. Play `ding`.
6. **Idle.**

### Concurrency

- Hotkey events arrive on a `pynput` thread.
- The daemon serializes everything through a single internal event queue —
  `pynput` callbacks push events; the main thread drains the queue and runs
  the state machine. The state machine is never touched from two threads.
- A second hotkey press while `TRANSCRIBING` or `PASTING` is queued. We do
  not preempt the in-flight transcription, but we also do not drop the new
  event. The next transition is processed once the current one finishes.

### Audio capture details

- Sample rate: 16 kHz (whisper's native input — no resampling required).
- Channels: 1 (mono).
- Format: `float32`.
- Chunk size: 1024 frames (~64 ms at 16 kHz). Small enough that stop-latency
  is imperceptible.
- Buffer: a `queue.Queue` of numpy arrays. `audio.stop()` drains the queue
  with a 50 ms timeout and concatenates with `np.concatenate`.

---

## 6. Error handling

Every failure mode produces an audible cue and a logged line — never silent.
Errors that block dictation also surface a one-shot macOS notification (the
only non-audio feedback used).

| Failure | Detection | Behavior |
|---|---|---|
| Microphone permission denied | `sounddevice.PortAudioError` on stream open | Notification with "Open System Settings → Privacy → Microphone and enable Python", error sound, daemon stays running so user can grant and retry |
| Accessibility permission denied | `pynput` listener fails to start, or `CGEventPost` returns failure | Notification with the exact System Settings path, error sound, daemon stays running but hotkeys / paste are no-ops until the user grants permission and restarts the daemon |
| Hotkey collision (another app owns it) | `pynput` swallows the event | Logged at startup with a hint to change config; the other hotkey still works |
| Recording too short (<400 ms) | Sample count check after stop | Discard, no error sound, return to IDLE silently — this is "I tapped by accident", not a failure |
| Recording too long (>5 min) | Frame counter during capture | Hard-stop the stream, transcribe what we have, log a warning |
| Whisper crash / OOM / corrupt model | Exception from `pywhispercpp` | Error sound, notification, log the exception with traceback, return to IDLE — daemon stays up |
| Empty transcription (silent audio) | `text.strip() == ""` | No error sound (not really an error), return to IDLE silently |
| Paste failed (clipboard busy, target app closed) | `CGEventPost` non-zero return, or focused app unreachable | Error sound + notification "transcribed but couldn't paste — text is on your clipboard", **skip the clipboard restore** so the user can paste manually |
| Daemon crashes | launchd plist `KeepAlive=true` | macOS handles restart; in-flight transcription is lost |
| Model file missing on first run | File-exists check at startup | `stt install` downloads it; if daemon starts without it, log + notification + exit non-zero so launchd retries with backoff |

### Principles

- **The daemon never exits on a per-utterance failure.** Every recoverable
  error returns to `IDLE` with cues. Only un-fixable startup conditions
  (missing model, fatal init) cause exit, and launchd retries on backoff.
- **On paste failure, transcribed text stays on the clipboard.** The user
  can `⌘V` it manually. This is the one place where we trade clipboard
  preservation for not losing the transcription — losing several seconds of
  dictation is worse than overwriting the clipboard.

---

## 7. Permissions, install, and CLI

### Required macOS permissions

| Permission | Why | When prompted |
|---|---|---|
| Microphone | `sounddevice` capture | First time the daemon opens an input stream |
| Accessibility | `pynput` global hotkeys + `CGEventPost` for `⌘V` | First time the daemon registers a global listener |
| Input Monitoring | Some macOS versions require this for `pynput` global key hooks | Same trigger as Accessibility |

These are granted to *the binary that runs Python*, which is why `pipx` /
`uv tool install` is the recommended distribution: the project gets its own
isolated venv with a stable interpreter path that does not move when the
user upgrades Homebrew Python.

### Install flow

```text
$ uv tool install speech-to-text
$ stt install
   ✓ Wrote default config to ~/.config/speech-to-text/config.toml
   ✓ Downloaded ggml-small.bin (488 MB) to ~/.local/share/speech-to-text/models/
   ✓ Wrote LaunchAgent to ~/Library/LaunchAgents/com.user.speechtotext.plist
   ⚠ macOS will prompt for Microphone and Accessibility permissions on first run.
     Open System Settings → Privacy & Security to grant them if you miss the prompt.
$ stt enable
   ✓ Daemon started. Logs at ~/Library/Logs/speech-to-text/daemon.log
```

### CLI subcommands

| Command | Behavior |
|---|---|
| `stt install` | One-time setup: write default config, download model, write LaunchAgent plist |
| `stt enable` | `launchctl load` the plist (start daemon, enable auto-start) |
| `stt disable` | `launchctl unload` the plist (stop daemon, disable auto-start) |
| `stt status` | Is the daemon running? Last activity? Recent log lines? |
| `stt start` | Run daemon in foreground (for debugging — bypasses launchd) |
| `stt logs` | Tail the daemon log |
| `stt config` | Open `config.toml` in `$EDITOR` |
| `stt uninstall` | Remove LaunchAgent plist; optionally remove config and models with `--purge` |

### Installed file layout

```
~/.config/speech-to-text/config.toml              # user-editable settings
~/.local/share/speech-to-text/models/             # whisper model files
~/Library/LaunchAgents/com.user.speechtotext.plist
~/Library/Logs/speech-to-text/daemon.log          # auto-rotated at 10 MB
```

### Config file shape

```toml
[hotkeys]
push_to_talk = "<cmd_r>"        # hold to record
toggle       = "<ctrl>+<shift>+<space>"  # tap to start/stop

[model]
name = "small"                  # multilingual; use small.en/medium.en for English-only
path = "~/.local/share/speech-to-text/models/ggml-small.bin"

[audio]
sample_rate = 16000
input_device = "default"        # or a substring of the device name
min_duration_ms = 400
max_duration_ms = 300000

[paste]
restore_clipboard_delay_ms = 200

[sounds]
enabled = true                  # master switch
record_start = "tink.wav"
paste_done   = "ding.wav"
error        = "error.wav"

[logging]
level = "INFO"                  # DEBUG | INFO | WARNING | ERROR
max_bytes = 10485760            # 10 MB
backup_count = 3
```

---

## 8. Testing strategy

| Layer | Tool | What it covers |
|---|---|---|
| **Unit** | `pytest` | Config parsing & defaults; state machine transitions driven by fake events; paste logic with mocked clipboard + mocked `CGEventPost`; recording-too-short / too-long guards; launchd plist generation (string compare against fixture) |
| **Integration** | `pytest` with real `whisper.cpp` | End-to-end transcription of a checked-in fixture WAV. Asserts the returned text contains expected words. Uses `tiny.en` to keep CI fast. Validates that `pywhispercpp` and our wrapper are wired correctly. |
| **Manual smoke** | `docs/manual-test-plan.md` | Hotkey behavior, real mic, real paste into a real app — depend on macOS permissions and hardware events that cannot be simulated reliably. Run before each release. |

### Coverage target

80%+ on everything except `hotkeys.py` and the OS-shell-out parts of
`launchd.py` (thin wrappers around `pynput` / `launchctl`, covered by
manual smoke tests).

### Test fixtures committed to the repo

- `tests/fixtures/quick-brown-fox.wav` — ~5 s, 16 kHz mono, public-domain
  phrase
- `tests/fixtures/silence.wav` — 1 s of silence, for the empty-transcription
  path
- `tests/fixtures/expected.plist` — golden launchd plist for compare

### Explicitly not auto-tested

- Real global hotkey registration (requires Accessibility permission)
- Real `CGEventPost` keystroke simulation
- Real microphone capture
- Real notification display

These go in the manual checklist because mocking them costs more in test
maintenance than they catch. Internal interfaces (`hotkeys.Hotkeys`,
`audio.Recorder`, `paste.paste`) are mockable, so daemon logic is fully
covered.

---

## 9. Open questions / future work

Not in scope for v1, but flagged for later:

- **Pluggable transcription backend.** The `Transcriber` interface is
  designed to allow a second implementation (OpenAI's API, an alternative
  local model). Not implemented in v1; only `whisper.cpp` ships.
- **Custom vocabulary / prompt biasing.** `whisper.cpp` accepts an initial
  prompt to bias toward specific terms (names, jargon). Could be exposed
  via config later.
- **Per-app configuration.** Different hotkeys, models, or post-processing
  rules depending on the focused app's bundle identifier.
- **Streaming transcription.** Replace batch with the Realtime / streaming
  API if a low-latency path is needed.
- **Cross-platform support.** Linux / Windows would need different
  hotkey, paste, and daemon-management implementations. macOS only in v1.
