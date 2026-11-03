#!/usr/bin/env bash
# Runs the smoke flow headless against a local page. Checks the result and secret redaction.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT
"$DIR/../run" run "$DIR/smoke.yaml" --var page_url="file://$DIR/page.html" --out "$OUT" >"$OUT/stdout.json" 2>"$OUT/stderr.txt"
python3 - "$OUT" <<'PY'
import json, sys, pathlib
out = pathlib.Path(sys.argv[1])
r = json.loads((out / "stdout.json").read_text())
assert r["ok"], r
assert r["extracted"]["accounts"] == ["Chequing 123.45", "Savings 678.90"], r["extracted"]
assert r["extracted"]["chequing"] == "123.45"
assert (out / "downloads/statement.txt").read_text() == "statement-content"
for f in ("log.txt", "stdout.json", "end.snapshot.yaml"):
    assert "s3cret" not in (out / f).read_text(), f"secret leaked in {f}"
assert "optional step failed" in (out / "log.txt").read_text()
assert "if_visible not met" in (out / "log.txt").read_text()
print("run: ok")
PY

# include + download each (+ skip_existing on second run)
"$DIR/../run" run "$DIR/each.yaml" --var page_url="file://$DIR/page.html" --var dir="$OUT/each" --out "$OUT/each-run" >"$OUT/each.json" 2>>"$OUT/stderr.txt"
"$DIR/../run" run "$DIR/each.yaml" --var page_url="file://$DIR/page.html" --var dir="$OUT/each" --out "$OUT/each-run2" >"$OUT/each2.json" 2>"$OUT/each2.log"
python3 - "$OUT" <<'PY'
import json, sys, pathlib
out = pathlib.Path(sys.argv[1])
r = json.loads((out / "each.json").read_text())
assert r["ok"] and r["steps_total"] == 15, r
names = sorted(p.name for p in (out / "each").iterdir())
assert names == ["Card A - eStatement 2026-09-09.txt", "Card A - eStatement 2026-10-09.txt"], names
assert (out / "each/Card A - eStatement 2026-10-09.txt").read_text() == "September 10 to October 9, 2026"
assert "2 matched, 0 downloaded, 2 already present" in (out / "each2.log").read_text()
print("include/each: ok")
PY

# attach: open a browser on a test profile, drive it from a second process
"$DIR/../run" open "file://$DIR/page.html" --profile test --cdp-port 9333 >"$OUT/open.log" 2>&1 &
OPEN_PID=$!
for _ in $(seq 1 30); do curl -sf http://127.0.0.1:9333/json/version >/dev/null && break; sleep 0.5; done
"$DIR/../run" attach --cdp 9333 --out "$OUT/attach" \
  --step 'fill: {target: label=Username, value: bob}' \
  --step 'click: role=button[name="Sign on"]' \
  --step 'extract: {name: out, target: "#out"}' >"$OUT/attach.json" 2>>"$OUT/stderr.txt"
"$DIR/../run" attach --cdp 9333 --out "$OUT/attach" --snapshot >"$OUT/attach.snap" 2>/dev/null
kill "$OPEN_PID" 2>/dev/null; wait "$OPEN_PID" 2>/dev/null || true
python3 - "$OUT" <<'PY'
import json, sys, pathlib
out = pathlib.Path(sys.argv[1])
r = json.loads((out / "attach.json").read_text())
assert r["ok"] and r["extracted"]["out"] == "hello bob", r
assert 'textbox "Username": bob' in (out / "attach.snap").read_text()
print("attach: ok")
print("all tests passed")
PY
