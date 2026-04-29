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
