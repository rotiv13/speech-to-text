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
