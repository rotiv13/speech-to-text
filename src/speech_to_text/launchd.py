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
