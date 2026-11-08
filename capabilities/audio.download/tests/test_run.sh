#!/usr/bin/env bash
# Offline tests for audio.download/run. They do not download anything.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$SCRIPT_DIR/../run"
URL="https://www.bilibili.com/video/BV1cv2yYDE4U"
FAILED=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILED=1; }

# 1. Default: best audio, extract, convert to MP3, quality 0.
out="$("$RUN" "$URL" --dry-run)"
if [[ "$out" == *'bestaudio'* && "$out" == *'--audio-format mp3'* && "$out" == *'--audio-quality 0'* ]]; then
    pass "default is best audio to VBR V0 mp3"
else
    fail "default is best audio to VBR V0 mp3 (got: $out)"
fi

# 2. --quality sets the MP3 quality.
out="$("$RUN" "$URL" --quality 4 --dry-run)"
if [[ "$out" == *'--audio-quality 4'* ]]; then
    pass "--quality sets the mp3 quality"
else
    fail "--quality sets the mp3 quality (got: $out)"
fi

# 3. The format has no video stream selector.
out="$("$RUN" "$URL" --dry-run)"
if [[ "$out" != *'bestvideo'* && "$out" != *'mp4'* ]]; then
    pass "no video stream is selected"
else
    fail "no video stream is selected (got: $out)"
fi

# 4. Output folder is passed through.
out="$("$RUN" "$URL" -o /tmp/ad-test --dry-run)"
if [[ "$out" == */tmp/ad-test/* ]]; then
    pass "-o sets the output folder"
else
    fail "-o sets the output folder (got: $out)"
fi

# 5. Bad quality is refused.
if "$RUN" "$URL" --quality 12 >/dev/null 2>&1; then
    fail "out-of-range --quality is refused"
else
    pass "out-of-range --quality is refused"
fi

# 6. Missing URL is refused.
if "$RUN" >/dev/null 2>&1; then
    fail "missing URL is refused"
else
    pass "missing URL is refused"
fi

# 7. Two URLs are refused.
if "$RUN" "$URL" "$URL" >/dev/null 2>&1; then
    fail "two URLs are refused"
else
    pass "two URLs are refused"
fi

if [[ "$FAILED" -ne 0 ]]; then
    echo "Some tests failed." >&2
    exit 1
fi
echo "All tests passed."
