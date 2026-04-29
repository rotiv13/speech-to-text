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
