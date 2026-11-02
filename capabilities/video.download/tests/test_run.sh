#!/usr/bin/env bash
# Offline tests for video.download/run. They do not download anything.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$SCRIPT_DIR/../run"
URL="https://www.bilibili.com/video/BV1cv2yYDE4U"
FAILED=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAILED=1; }

# 1. Default height is 1080.
out="$("$RUN" "$URL" --dry-run)"
if [[ "$out" == *'height\<=1080'* && "$out" == *'merge-output-format mp4'* ]]; then
    pass "default height is 1080 and merges to mp4"
else
    fail "default height is 1080 (got: $out)"
fi

# 2. --height 720 sets the cap.
out="$("$RUN" "$URL" --height 720 --dry-run)"
if [[ "$out" == *'height\<=720'* && "$out" != *'height\<=1080'* ]]; then
    pass "--height 720 sets the cap"
else
    fail "--height 720 sets the cap (got: $out)"
fi

# 3. The format never selects audio-only or re-encodes audio.
out="$("$RUN" "$URL" --dry-run)"
if [[ "$out" != *"audio-only"* && "$out" != *"--extract-audio"* && "$out" != *"--audio"* ]]; then
    pass "no audio extraction flags"
else
    fail "no audio extraction flags (got: $out)"
fi

# 4. Output folder is passed through.
out="$("$RUN" "$URL" -o /tmp/vd-test --dry-run)"
if [[ "$out" == */tmp/vd-test/* ]]; then
    pass "-o sets the output folder"
else
    fail "-o sets the output folder (got: $out)"
fi

# 5. Non-numeric height is refused.
if "$RUN" "$URL" --height abc >/dev/null 2>&1; then
    fail "non-numeric --height is refused"
else
    pass "non-numeric --height is refused"
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
