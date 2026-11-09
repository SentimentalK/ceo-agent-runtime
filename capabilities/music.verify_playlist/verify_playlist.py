#!/usr/bin/env python3
"""Check every track of a playlist against the Spotify preview of that track.

Downtify can pick a different edit or a cover when its search is wrong.  This
tool compares the audio fingerprint (Chromaprint) of each file with the 30
second Spotify preview.  The same recording gives a mean bit agreement of about
29-32 out of 32.  A different master stays near 26.  A different recording
stays below 22.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.request

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "music.playlist_to_cloud"),
)
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "music.fill_from_youtube"),
)
from playlist_to_cloud import (  # noqa: E402
    DEFAULT_DEST,
    DEFAULT_DOWNLOADS,
    REPO_ROOT,
    Downtify,
    DowntifyError,
    load_dotenv,
    log,
    sanitize,
)
from fill_from_youtube import chromaprint, find_folder, similarity  # noqa: E402

MATCH_MEAN = 29.0
SAME_PERFORMANCE_MEAN = 24.0


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def local_files(downloads: str, folder: str) -> dict:
    base = os.path.join(downloads, folder)
    files = {}
    if not os.path.isdir(base):
        return files
    for name in os.listdir(base):
        if name.lower().endswith(".mp3"):
            files.setdefault(normalize(os.path.splitext(name)[0]), os.path.join(base, name))
    return files


def remote_files(remote: str) -> dict:
    result = subprocess.run(
        ["rclone", "lsf", remote, "-R", "--files-only"], capture_output=True, text=True
    )
    if result.returncode != 0:
        return {}
    files = {}
    for line in result.stdout.splitlines():
        if line.lower().endswith(".mp3"):
            files.setdefault(normalize(os.path.splitext(os.path.basename(line))[0]), line)
    return files


def fetch_remote(remote: str, relative: str, target: str) -> bool:
    result = subprocess.run(
        ["rclone", "copyto", f"{remote}/{relative}", target], capture_output=True, text=True
    )
    return result.returncode == 0 and os.path.exists(target)


def preview(song: dict, staging: str):
    url = song.get("preview_url") or ""
    if not url:
        return None
    path = os.path.join(staging, f"preview-{song.get('song_id') or 'unknown'}.mp3")
    if not os.path.exists(path):
        try:
            urllib.request.urlretrieve(url, path)
        except Exception:
            return None
    return path


def verdict(mean: float) -> str:
    if mean >= MATCH_MEAN:
        return "MATCH"
    if mean >= SAME_PERFORMANCE_MEAN:
        return "SAME-PERFORMANCE"
    return "MISMATCH"


def main() -> int:
    load_dotenv(os.path.join(REPO_ROOT, ".env"))
    parser = argparse.ArgumentParser(description="Verify playlist audio against the Spotify previews.")
    parser.add_argument("playlist", help="Spotify playlist URL.")
    parser.add_argument("--downloads", default=os.environ.get("DOWNTIFY_DOWNLOADS", DEFAULT_DOWNLOADS))
    parser.add_argument("--dest", default=os.environ.get("DOWNTIFY_CLOUD_DEST", DEFAULT_DEST))
    parser.add_argument("--staging", default=os.path.join(REPO_ROOT, "temp"), help="Folder for temporary files.")
    parser.add_argument("--folder", help="Playlist folder name. Default: found from the files.")
    args = parser.parse_args()

    missing = [key for key in ("DOWNTIFY_USERNAME", "DOWNTIFY_PASSWORD") if not os.environ.get(key)]
    if missing:
        log(f"Error: set {', '.join(missing)} in .env or the environment.")
        return 3

    client = Downtify(
        os.environ.get("DOWNTIFY_URL", "http://localhost:8000"),
        os.environ["DOWNTIFY_USERNAME"],
        os.environ["DOWNTIFY_PASSWORD"],
    )
    client.login()

    try:
        songs = client.resolve(args.playlist)
        if not args.folder:
            try:
                args.folder = find_folder(args.downloads, songs)
            except DowntifyError:
                batches = client.request("/api/playlists/batches").get("playlists", [])
                mine = [b for b in batches if b.get("playlist_url") == args.playlist]
                if not mine:
                    raise DowntifyError("No batch for this playlist. Run music.playlist_to_cloud first.")
                name = max(mine, key=lambda b: b["batch_id"])["playlist_name"]
                args.folder = sanitize(name)
    except DowntifyError as error:
        log(f"Error: {error}")
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1

    staging = tempfile.mkdtemp(prefix="verify-", dir=args.staging)
    remote = f"{args.dest}/{args.folder}"
    local = local_files(args.downloads, args.folder)
    cloud = remote_files(remote)
    rows = []
    try:
        for song in songs:
            stem = f"{song['artist']} - {song['name']}"
            key = normalize(stem)
            entry = {"track": stem, "expected_duration": song["duration"]}
            path = local.get(key)
            source = "local"
            if not path and key in cloud:
                target = os.path.join(staging, f"{song['song_id']}.mp3")
                if fetch_remote(remote, cloud[key], target):
                    path, source = target, "cloud"
            if not path:
                entry["verdict"] = "MISSING"
                rows.append(entry)
                log(f"MISSING  {stem}")
                continue
            preview_path = preview(song, staging)
            if not preview_path:
                entry["verdict"] = "NO-PREVIEW"
                rows.append(entry)
                log(f"NO-PREV  {stem}")
                continue
            mean, good = similarity(chromaprint(preview_path), chromaprint(path))
            entry.update(verdict=verdict(mean), mean=mean, good=good, source=source)
            rows.append(entry)
            log(f"{entry['verdict']:16} mean={mean} good={good} {stem}")
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    summary = {}
    for row in rows:
        summary[row["verdict"]] = summary.get(row["verdict"], 0) + 1
    print(json.dumps({"ok": True, "folder": args.folder, "summary": summary, "tracks": rows}, ensure_ascii=False, indent=1))
    bad = summary.get("MISMATCH", 0) + summary.get("MISSING", 0)
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
