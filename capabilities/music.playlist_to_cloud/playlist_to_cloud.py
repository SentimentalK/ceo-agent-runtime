#!/usr/bin/env python3
"""Download Spotify playlists with Downtify, then upload the tracks to a cloud folder.

Downtify runs in Docker on this machine and serves its API on ``DOWNTIFY_URL``
(default ``http://localhost:8000``).  Uploads use rclone and a remote folder
such as ``onedrive:40_音乐``.

Only the Python standard library is needed.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DOWNLOADS = os.path.expanduser("~/downtify/downloads")
DEFAULT_DEST = "onedrive:40_音乐"
UPLOAD_GLOBS = ("*.mp3", "*.lrc")


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def load_dotenv(path: str) -> None:
    """Add KEY=VALUE pairs from ``.env`` to the environment when missing."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


class DowntifyError(RuntimeError):
    pass


class Downtify:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )
        self.username = username
        self.password = password

    def request(self, path: str, method: str = "GET", params=None, body=None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            url, data=data, method=method, headers={"Content-Type": "application/json"}
        )
        try:
            with self.opener.open(request, timeout=120) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read()[:400].decode("utf-8", "replace")
            raise DowntifyError(f"{method} {path} failed: HTTP {error.code} {detail}") from None
        except urllib.error.URLError as error:
            raise DowntifyError(
                f"Cannot reach Downtify at {self.base_url}: {error.reason}"
            ) from None
        return json.loads(raw) if raw else None

    def login(self) -> None:
        result = self.request(
            "/api/auth/login",
            method="POST",
            body={"username": self.username, "password": self.password},
        )
        if not result or not result.get("signed_in"):
            raise DowntifyError("Sign-in failed. Check DOWNTIFY_USERNAME and DOWNTIFY_PASSWORD.")

    def resolve(self, url: str):
        songs = self.request("/api/url", params={"url": url})
        if not isinstance(songs, list):
            raise DowntifyError(f"Downtify did not return a track list for {url}.")
        return songs

    def batch(self, url: str, songs) -> dict:
        payload = [
            {**song, "downtify_playlist_url": url, "downtify_track_order": order}
            for order, song in enumerate(songs)
        ]
        return self.request(
            "/api/download/batch",
            method="POST",
            body={
                "songs": payload,
                "playlist_url": url,
                "generate_m3u": True,
            },
        )

    def max_batch_id(self, url: str) -> int:
        batches = self.request("/api/playlists/batches").get("playlists", [])
        ids = [b["batch_id"] for b in batches if b.get("playlist_url") == url]
        return max(ids) if ids else 0

    def batch_status(self, url: str, after_id: int):
        batches = self.request("/api/playlists/batches").get("playlists", [])
        mine = [
            b
            for b in batches
            if b.get("playlist_url") == url and b.get("batch_id", 0) > after_id
        ]
        return max(mine, key=lambda b: b["batch_id"]) if mine else None

    def queue_active(self) -> int:
        return int(self.request("/api/queue/state").get("active") or 0)

    def pending_for(self, url: str) -> int:
        pending = 0
        for item in self.request("/api/queue") or []:
            song = item.get("song") or {}
            if song.get("downtify_playlist_url") == url and item.get("status") in {
                "queued",
                "downloading",
            }:
                pending += 1
        return pending

    def queue_pending(self) -> int:
        return sum(
            1
            for item in self.request("/api/queue") or []
            if item.get("status") in {"queued", "downloading"}
        )

    def playlist_folder(self, playlist_name: str):
        details = self.request(
            "/api/library/playlists/details", params={"name": playlist_name}
        )
        folders = set()
        for filename in (details or {}).get("providers", {}):
            folder = filename.split("/", 1)[0]
            if folder and folder != filename:
                folders.add(folder)
        return sorted(folders)


def sanitize(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", name)
    return name.strip().rstrip(".")


def resolve_folder(client: Downtify, playlist_name: str, downloads: str) -> str:
    folders = client.playlist_folder(playlist_name)
    if len(folders) == 1:
        return folders[0]
    wanted = {sanitize(playlist_name)}
    local = [
        entry
        for entry in os.listdir(downloads)
        if os.path.isdir(os.path.join(downloads, entry)) and sanitize(entry) in wanted
    ]
    if len(local) == 1:
        return local[0]
    raise DowntifyError(
        f"Cannot find one download folder for playlist {playlist_name!r} "
        f"(candidates: {folders or local or 'none'})."
    )


def wait_for_batch(client: Downtify, url: str, after_id: int, poll: float, timeout: float) -> dict:
    """Wait until the queue is empty and the playlist batch reports a final state.

    Downtify keeps a batch at ``incomplete`` while its tracks are still queued,
    so the queue is the reliable signal.  Two idle polls in a row end the wait.
    """
    deadline = time.monotonic() + timeout
    seen = None
    idle = 0
    while time.monotonic() < deadline:
        status = client.batch_status(url, after_id)
        if status:
            seen = status
            pending = client.queue_pending()
            active = client.queue_active()
            if pending == 0 and active == 0 and not status.get("active_in_queue"):
                idle += 1
                if status.get("status") == "complete" or idle >= 2:
                    return status
            else:
                idle = 0
                log(
                    f"waiting: {status.get('downloaded_count')}/{status.get('expected_count')} "
                    f"done, {pending} queued, {active} downloading"
                )
        time.sleep(poll)
    detail = json.dumps(seen, ensure_ascii=False) if seen else "no batch status"
    raise DowntifyError(f"Timed out after {timeout:.0f}s waiting for {url}: {detail}")


def count_files(folder: str) -> int:
    total = 0
    for _, _, files in os.walk(folder):
        total += sum(1 for name in files if name.lower().endswith((".mp3", ".lrc")))
    return total


def remote_count(remote: str) -> int:
    result = subprocess.run(
        ["rclone", "lsf", remote, "-R", "--files-only"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"rclone lsf {remote} failed: {result.stderr.strip()}")
    return sum(
        1 for line in result.stdout.splitlines() if line.lower().endswith((".mp3", ".lrc"))
    )


def upload(local: str, remote: str, dry_run: bool) -> dict:
    command = ["rclone", "copy", local, remote, "--stats-one-line", "--stats=10s"]
    for pattern in UPLOAD_GLOBS:
        command += ["--include", pattern]
    if dry_run:
        log("DRY-RUN " + " ".join(command))
    else:
        log(f"Uploading {local} -> {remote}")
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"rclone copy failed: {result.stderr.strip()[-800:]}")
    local_files = count_files(local)
    remote_files = 0 if dry_run else remote_count(remote)
    return {"local_files": local_files, "remote_files": remote_files, "remote": remote}


def run_playlist(client: Downtify, url: str, args) -> dict:
    songs = client.resolve(url)
    log(f"Resolved {len(songs)} tracks: {url}")
    entry = {"url": url, "tracks": len(songs)}
    if args.dry_run:
        entry["action"] = "dry-run"
        return entry

    running = client.batch_status(url, 0)
    still_queued = bool(running) and client.pending_for(url) > 0
    if running and (
        running.get("status") not in {"complete", "failed", "error"} or still_queued
    ):
        log(f"A batch is already running. Waiting up to {args.timeout:.0f}s ...")
        before = 0
    else:
        before = client.max_batch_id(url)
        client.batch(url, songs)
        log(f"Queued the download. Waiting up to {args.timeout:.0f}s ...")
    status = wait_for_batch(client, url, before, args.poll, args.timeout)

    name = status.get("playlist_name") or ""
    if not name:
        raise DowntifyError(f"Downtify did not report a playlist name for {url}.")
    folder = resolve_folder(client, name, args.downloads)
    entry.update(
        playlist=name,
        folder=folder,
        batch_id=status.get("batch_id"),
        batch_status=status.get("status"),
        expected=status.get("expected_count"),
        downloaded=status.get("downloaded_count"),
        missing=status.get("missing_count"),
    )

    local = os.path.join(args.downloads, folder)
    if not os.path.isdir(local):
        raise DowntifyError(f"Download folder does not exist: {local}")
    if args.no_upload:
        entry["upload"] = "skipped"
    else:
        entry["upload"] = upload(local, f"{args.dest}/{folder}", args.dry_run)
    return entry


def run_upload_only(client: Downtify, names, args) -> list:
    results = []
    for name in names:
        folder = resolve_folder(client, name, args.downloads)
        local = os.path.join(args.downloads, folder)
        if not os.path.isdir(local):
            raise DowntifyError(f"Download folder does not exist: {local}")
        log(f"Uploading existing playlist {name!r} from {local}")
        results.append(
            {
                "playlist": name,
                "folder": folder,
                "upload": upload(local, f"{args.dest}/{folder}", args.dry_run),
            }
        )
    return results


def main() -> int:
    load_dotenv(os.path.join(REPO_ROOT, ".env"))

    parser = argparse.ArgumentParser(
        description="Download Spotify playlists with Downtify, then upload them with rclone."
    )
    parser.add_argument("playlists", nargs="*", help="Spotify playlist URLs, or playlist names with --upload-only.")
    parser.add_argument("--file", help="Read playlist URLs from a file (one per line).")
    parser.add_argument("--upload-only", action="store_true", help="Upload the local folders of the named playlists. Do not download.")
    parser.add_argument("--dest", default=os.environ.get("DOWNTIFY_CLOUD_DEST", DEFAULT_DEST), help=f"rclone destination folder. Default: {DEFAULT_DEST}")
    parser.add_argument("--downloads", default=os.environ.get("DOWNTIFY_DOWNLOADS", DEFAULT_DOWNLOADS), help="Downtify download folder on this machine.")
    parser.add_argument("--no-upload", action="store_true", help="Download only. Do not run rclone.")
    parser.add_argument("--poll", type=float, default=15.0, help="Seconds between status checks. Default: 15.")
    parser.add_argument("--timeout", type=float, default=10800.0, help="Seconds to wait for one playlist. Default: 10800.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve the lists and print the planned work. Change nothing.")
    args = parser.parse_args()

    urls = list(args.playlists)
    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            urls += [line.strip() for line in handle if line.strip() and not line.startswith("#")]
    if not urls:
        parser.error("Give at least one playlist URL, or use --file.")

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
        if args.upload_only:
            results = run_upload_only(client, urls, args)
        else:
            results = []
            for url in urls:
                if "open.spotify.com/playlist/" not in url and not url.startswith("spotify:playlist:"):
                    raise DowntifyError(f"Not a Spotify playlist URL: {url}")
                results.append(run_playlist(client, url, args))
    except (DowntifyError, RuntimeError) as error:
        log(f"Error: {error}")
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1

    print(json.dumps({"ok": True, "dest": args.dest, "playlists": results}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
