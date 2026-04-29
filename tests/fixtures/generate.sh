#!/usr/bin/env bash
# Regenerate test audio fixtures using macOS `say` and afconvert.
# Run from repo root: bash tests/fixtures/generate.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

# 1. quick-brown-fox.wav — speech sample for integration test
say -o "$DIR/_tmp.aiff" "the quick brown fox jumps over the lazy dog"
afconvert -f WAVE -d LEI16@16000 -c 1 "$DIR/_tmp.aiff" "$DIR/quick-brown-fox.wav"
rm "$DIR/_tmp.aiff"

# 2. silence.wav — 1 second of silence
python3 -c "
import wave, struct
with wave.open('$DIR/silence.wav', 'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b'\\x00\\x00' * 16000)
"

echo "Generated fixtures in $DIR"
ls -la "$DIR"/*.wav
