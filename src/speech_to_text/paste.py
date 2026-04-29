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
