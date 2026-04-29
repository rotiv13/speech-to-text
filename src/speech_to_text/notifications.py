from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)

# AppleScript that pulls title/body from positional argv. Passing the strings
# as arguments rather than interpolating them into the script avoids quote-
# and backslash-escape pitfalls that would otherwise let user-influenced text
# (e.g. exception messages, file paths) break out of the AppleScript literal.
_NOTIFY_SCRIPT = (
    "on run argv\n"
    "  display notification (item 2 of argv) with title (item 1 of argv)\n"
    "end run"
)


def notify(title: str, body: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e", _NOTIFY_SCRIPT, "--", title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        log.warning("Notification failed: %s", e)
