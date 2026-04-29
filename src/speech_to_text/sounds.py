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
