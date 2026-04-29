from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL_PATH = "~/.local/share/speech-to-text/models/ggml-medium.bin"


@dataclass(frozen=True)
class HotkeysConfig:
    push_to_talk: str = "<cmd_r>"
    toggle: str = "<ctrl>+<shift>+<space>"


@dataclass(frozen=True)
class ModelConfig:
    # `medium` is the multilingual variant with reliable accuracy on
    # under-represented language variants (e.g. European Portuguese).
    # Swap to `small`/`small.en` for ~3x faster inference if accuracy is fine.
    name: str = "medium"
    path: str = DEFAULT_MODEL_PATH


@dataclass(frozen=True)
class AudioConfig:
    sample_rate: int = 16000
    input_device: str = "default"
    min_duration_ms: int = 400
    max_duration_ms: int = 300_000


@dataclass(frozen=True)
class PasteConfig:
    restore_clipboard_delay_ms: int = 200


@dataclass(frozen=True)
class SoundsConfig:
    enabled: bool = True
    record_start: str = "tink.wav"
    paste_done: str = "ding.wav"
    error: str = "error.wav"


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 3


@dataclass(frozen=True)
class Config:
    hotkeys: HotkeysConfig = field(default_factory=HotkeysConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    paste: PasteConfig = field(default_factory=PasteConfig)
    sounds: SoundsConfig = field(default_factory=SoundsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load(path: Path) -> Config:
    if not path.exists():
        return Config()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    return _build(raw)


def _build(raw: dict) -> Config:
    model_section = raw.get("model", {})
    if "path" in model_section:
        model_section = {**model_section, "path": str(Path(model_section["path"]).expanduser())}
    return Config(
        hotkeys=HotkeysConfig(**raw.get("hotkeys", {})),
        model=ModelConfig(**model_section),
        audio=AudioConfig(**raw.get("audio", {})),
        paste=PasteConfig(**raw.get("paste", {})),
        sounds=SoundsConfig(**raw.get("sounds", {})),
        logging=LoggingConfig(**raw.get("logging", {})),
    )
