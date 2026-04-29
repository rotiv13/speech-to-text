#!/usr/bin/env bash
# Generate the three audio cue files using macOS built-in sound effects.
# Run from repo root: bash scripts/generate_sounds.sh
set -euo pipefail

OUT_DIR="src/speech_to_text/assets/sounds"
mkdir -p "$OUT_DIR"

SRC="/System/Library/Sounds"
afconvert -f WAVE -d LEI16 "$SRC/Tink.aiff"   "$OUT_DIR/tink.wav"
afconvert -f WAVE -d LEI16 "$SRC/Glass.aiff"  "$OUT_DIR/ding.wav"
afconvert -f WAVE -d LEI16 "$SRC/Sosumi.aiff" "$OUT_DIR/error.wav"

echo "Generated:"
ls -la "$OUT_DIR"/*.wav
