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
print("all tests passed")
PY
