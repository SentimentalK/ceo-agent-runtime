#!/usr/bin/env python3
"""Recover playlist tracks that Downtify could not match, using YouTube.

Downtify searches YouTube Music for each Spotify track.  When a track is not
found, this tool searches YouTube for the artist and title, keeps only the
candidates whose duration matches the Spotify duration, downloads the best
candidate as MP3, writes the Spotify metadata, and uploads it to the cloud
folder of the playlist.

Only the Python standard library is needed besides ``yt-dlp``, ``ffmpeg`` and
``mutagen`` (all three are already used by other capabilities).
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

MEDIA_SUFFIXES = (".mp3", ".lrc")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def track_stem(song: dict) -> str:
    return f"{song['artist']} - {song['name']}"


def downloaded_stems(folder: str) -> list:
    stems = []
    for name in os.listdir(folder):
        if name.lower().endswith(".mp3"):
            stems.append(normalize(os.path.splitext(name)[0]))
    return stems


def find_folder(base: str, songs) -> str:
    wanted = {normalize(track_stem(song)) for song in songs}
    best, best_hits = None, 0
    for entry in os.listdir(base):
        path = os.path.join(base, entry)
        if not os.path.isdir(path):
            continue
        hits = len(wanted & set(downloaded_stems(path)))
        if hits > best_hits:
            best, best_hits = entry, hits
    if not best:
        raise DowntifyError(
            f"No download folder under {base} matches this playlist. Run music.playlist_to_cloud first."
        )
    return best


def remote_stems(remote: str) -> set:
    result = subprocess.run(
        ["rclone", "lsf", remote, "--files-only"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        if "not found" in result.stderr.lower() or "doesn't exist" in result.stderr.lower():
            return set()
        raise RuntimeError(f"rclone lsf {remote} failed: {result.stderr.strip()[-400:]}")
    return {
        normalize(os.path.splitext(os.path.basename(line))[0])
        for line in result.stdout.splitlines()
        if line.lower().endswith(".mp3")
    }


def missing_songs(songs, have: set):
    missing = []
    remaining = set(have)
    for song in songs:
        key = normalize(track_stem(song))
        if key in remaining:
            remaining.remove(key)
        else:
            missing.append(song)
    return missing


def search(query: str, limit: int):
    command = [
        "yt-dlp",
        "--flat-playlist",
        "--no-warnings",
        "--print",
        "%(duration)s\t%(id)s\t%(channel)s\t%(title)s",
        f"ytsearch{limit}:{query}",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp search failed: {result.stderr.strip()[-400:]}")
    candidates = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 4 or not parts[0] or parts[0] in {"NA", "None"}:
            continue
        try:
            duration = float(parts[0])
        except ValueError:
            continue
        candidates.append(
            {"duration": duration, "id": parts[1], "channel": parts[2], "title": parts[3]}
        )
    return candidates


def ranked_candidates(song: dict, args) -> list:
    """Collect candidates from every query variant and rank them.

    Order: duration inside the tolerance first, then official channels, then
    the smallest duration difference.  The audio fingerprint decides last.
    """
    seen = set()
    items = []
    for query in queries_for(song):
        for candidate in search(query, args.candidates):
            if candidate["id"] in seen:
                continue
            seen.add(candidate["id"])
            candidate["delta"] = round(abs(candidate["duration"] - song["duration"]), 2)
            items.append(candidate)

    def rank(candidate):
        channel = candidate["channel"].lower()
        official = candidate["channel"].endswith("- Topic") or "official" in channel
        return (candidate["delta"] > args.tolerance, 0 if official else 1, candidate["delta"])

    items.sort(key=rank)
    return items


def download(video_id: str, staging: str) -> str:
    command = [
        "yt-dlp",
        "-f",
        "bestaudio/best",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--no-warnings",
        "-o",
        os.path.join(staging, "%(id)s.%(ext)s"),
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    path = os.path.join(staging, f"{video_id}.mp3")
    if result.returncode != 0 or not os.path.exists(path):
        raise RuntimeError(f"yt-dlp download failed for {video_id}: {result.stderr.strip()[-400:]}")
    return path


def tag(path: str, song: dict) -> None:
    from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TPE2, PictureType

    tags = ID3()
    tags.add(TIT2(encoding=3, text=song["name"]))
    tags.add(TPE1(encoding=3, text="; ".join(song.get("artists") or [song["artist"]])))
    if song.get("album_artist"):
        tags.add(TPE2(encoding=3, text=song["album_artist"]))
    if song.get("album_name"):
        tags.add(TALB(encoding=3, text=song["album_name"]))
    cover_url = song.get("cover_url") or ""
    if cover_url:
        try:
            cover = urllib.request.urlopen(cover_url, timeout=30).read()
            tags.add(
                APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=PictureType.COVER_FRONT,
                    desc="Cover",
                    data=cover,
                )
            )
        except Exception:
            pass
    tags.save(path)


def duration_of(path: str) -> float:
    from mutagen.mp3 import MP3

    return float(MP3(path).info.length)


VERIFY_MEAN = 24.0
VERIFY_GOOD = 0.5


def chromaprint(path: str):
    import array

    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "chromaprint", "-fp_format", "raw", "-"],
        capture_output=True,
    ).stdout
    data = array.array("i")
    data.frombytes(raw[: len(raw) // 4 * 4])
    return data


def similarity(preview, candidate) -> tuple:
    """Best bit agreement between the Spotify preview and a window of the candidate."""
    n = len(preview)
    if n == 0 or len(candidate) < n:
        return 0.0, 0.0
    best_mean, best_shift = 0.0, 0
    for shift in range(len(candidate) - n + 1):
        total = 0
        for index in range(n):
            total += 32 - bin(preview[index] ^ candidate[shift + index]).count("1")
        mean = total / n
        if mean > best_mean:
            best_mean, best_shift = mean, shift
    good = (
        sum(
            1
            for index in range(n)
            if 32 - bin(preview[index] ^ candidate[best_shift + index]).count("1") >= 26
        )
        / n
    )
    return round(best_mean, 2), round(good, 3)


def preview_file(song: dict, staging: str):
    url = song.get("preview_url") or ""
    if not url:
        return None
    path = os.path.join(staging, f"preview-{song.get('song_id') or 'unknown'}.mp3")
    try:
        urllib.request.urlretrieve(url, path)
    except Exception:
        return None
    return path


def upload_file(local: str, remote_dir: str, remote_name: str) -> None:
    result = subprocess.run(
        ["rclone", "copyto", local, f"{remote_dir}/{remote_name}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"rclone copyto failed: {result.stderr.strip()[-400:]}")


def queries_for(song: dict) -> list:
    artist = song.get("artist") or ""
    name = song.get("name") or ""
    queries = []
    for candidate in (
        f"{artist} {name}",
        f"{name} {artist}",
        name,
    ):
        candidate = candidate.strip()
        if candidate and candidate not in queries:
            queries.append(candidate)
    for alt in song.get("artists") or []:
        candidate = f"{alt} {name}".strip()
        if candidate and candidate not in queries:
            queries.append(candidate)
    return queries


def process(songs, folder: str, args) -> list:
    local_dir = os.path.join(args.downloads, folder)
    remote_dir = f"{args.dest}/{folder}"
    staging = tempfile.mkdtemp(prefix="fill-youtube-", dir=args.staging)
    results = []
    try:
        for song in songs:
            label = track_stem(song)
            entry = {"track": label, "expected_duration": song["duration"]}
            candidates = ranked_candidates(song, args)
            if args.dry_run:
                entry["candidate"] = candidates[0] if candidates else None
                entry["status"] = "candidate" if candidates else "no-match"
                results.append(entry)
                log(f"{entry['status']:9} {label} ({len(candidates)} candidates)")
                continue

            preview = preview_file(song, staging) if args.verify else None
            scores = []
            chosen = None
            for candidate in candidates[: args.attempts]:
                try:
                    path = download(candidate["id"], staging)
                except RuntimeError as error:
                    log(f"skip {candidate['id']}: {error}")
                    continue
                if preview:
                    mean, good = similarity(chromaprint(preview), chromaprint(path))
                    scores.append(
                        {"video": candidate["id"], "mean": mean, "good": good, "delta": candidate["delta"]}
                    )
                    if mean >= VERIFY_MEAN and good >= VERIFY_GOOD:
                        chosen = (candidate, path, mean)
                        break
                    os.remove(path)
                elif candidate["delta"] <= args.tolerance:
                    chosen = (candidate, path, None)
                    break
                else:
                    os.remove(path)

            if not chosen:
                entry["status"] = "no-match"
                entry["scores"] = scores
                entry["candidates"] = [
                    {"id": c["id"], "duration": c["duration"], "channel": c["channel"]}
                    for c in candidates[:5]
                ]
                results.append(entry)
                log(f"no-match {label}")
                continue

            candidate, path, mean = chosen
            actual = duration_of(path)
            if mean is None and abs(actual - song["duration"]) > args.tolerance + 1:
                entry["status"] = "duration-mismatch"
                entry["got_duration"] = round(actual, 2)
                results.append(entry)
                log(f"mismatch {label}: got {actual:.1f}s")
                continue

            tag(path, song)
            name = f"{sanitize(track_stem(song))}.mp3"
            placed = None
            try:
                os.replace(path, os.path.join(local_dir, name))
                placed = os.path.join(local_dir, name)
            except PermissionError:
                log(f"cannot write {local_dir} (root-owned); upload from staging")
            if not args.no_upload:
                upload_file(placed or path, remote_dir, name)
            entry.update(
                status="filled",
                video=candidate["id"],
                video_duration=candidate["duration"],
                file_duration=round(actual, 2),
                delta=candidate["delta"],
                channel=candidate["channel"],
                verified=mean is not None,
                match_score=mean,
                scores=scores,
                local=placed,
                uploaded=not args.no_upload,
            )
            results.append(entry)
            log(f"filled    {label} <- {candidate['id']} ({candidate['channel']}) score={mean}")
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return results


def main() -> int:
    load_dotenv(os.path.join(REPO_ROOT, ".env"))
    parser = argparse.ArgumentParser(
        description="Fill tracks that Downtify missed, from YouTube, using a duration match."
    )
    parser.add_argument("playlist", help="Spotify playlist URL.")
    parser.add_argument("--dest", default=os.environ.get("DOWNTIFY_CLOUD_DEST", DEFAULT_DEST))
    parser.add_argument("--downloads", default=os.environ.get("DOWNTIFY_DOWNLOADS", DEFAULT_DOWNLOADS))
    parser.add_argument("--staging", default=os.path.join(REPO_ROOT, "temp"), help="Folder for the temporary downloads.")
    parser.add_argument("--tolerance", type=float, default=1.0, help="Allowed duration difference in seconds. Default: 1.")
    parser.add_argument("--candidates", type=int, default=10, help="Search results to inspect. Default: 10.")
    parser.add_argument("--attempts", type=int, default=4, help="Candidates to download and check per track. Default: 4.")
    parser.add_argument("--no-verify", dest="verify", action="store_false", help="Skip the audio fingerprint check. Use the duration only.")
    parser.set_defaults(verify=True)
    parser.add_argument("--dry-run", action="store_true", help="Search and print the best candidate. Download nothing.")
    parser.add_argument("--no-upload", action="store_true", help="Write local files only. Do not run rclone.")
    args = parser.parse_args()

    missing = [key for key in ("DOWNTIFY_USERNAME", "DOWNTIFY_PASSWORD") if not os.environ.get(key)]
    if missing:
        log(f"Error: set {', '.join(missing)} in .env or the environment.")
        return 3
    os.makedirs(args.staging, exist_ok=True)

    client = Downtify(
        os.environ.get("DOWNTIFY_URL", "http://localhost:8000"),
        os.environ["DOWNTIFY_USERNAME"],
        os.environ["DOWNTIFY_PASSWORD"],
    )
    client.login()

    try:
        songs = client.resolve(args.playlist)
        folder = find_folder(args.downloads, songs)
        have = set(downloaded_stems(os.path.join(args.downloads, folder)))
        have |= remote_stems(f"{args.dest}/{folder}")
        wanted = missing_songs(songs, have)
        log(f"{len(songs)} tracks, {len(wanted)} missing in {folder}")
        results = process(wanted, folder, args)
    except (DowntifyError, RuntimeError) as error:
        log(f"Error: {error}")
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1

    filled = sum(1 for r in results if r.get("status") == "filled")
    matched = sum(1 for r in results if r.get("status") in {"filled", "candidate"})
    print(
        json.dumps(
            {
                "ok": True,
                "playlist": args.playlist,
                "folder": folder,
                "missing": len(results),
                "filled": filled,
                "results": results,
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0 if matched == len(results) else 2


if __name__ == "__main__":
    sys.exit(main())
