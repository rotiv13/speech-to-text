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
