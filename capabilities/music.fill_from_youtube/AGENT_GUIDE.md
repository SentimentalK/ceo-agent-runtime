# music.fill_from_youtube

Finds the tracks that Downtify missed. Uses YouTube. Checks the audio, not only the duration. Then uploads the tracks to the cloud folder of the playlist.

Use it after `music.playlist_to_cloud` reports `missing` greater than `0`.

## Run

```bash
capabilities/music.fill_from_youtube/run "<PLAYLIST_URL>" [options]
capabilities/music.fill_from_youtube/run "<PLAYLIST_URL>" --dry-run
```

## Options

- `--dest REMOTE`: rclone destination folder. Default: `onedrive:40_音乐`.
- `--downloads DIR`: Downtify download folder. Default: `~/downtify/downloads`.
- `--staging DIR`: Folder for temporary downloads. Default: `temp/`.
- `--tolerance SECONDS`: Maximum duration difference. Default: `1`.
- `--candidates N`: Search results to inspect for each query. Default: `10`.
- `--attempts N`: Candidates to download and check for each track. Default: `4`.
- `--no-verify`: Skip the audio check. Use the duration only. Do not use it unless the command says `NO-PREVIEW`.
- `--dry-run`: Search and print the best candidate. Download nothing.
- `--no-upload`: Write local files only. Do not run rclone.

## Steps

1. Read the track list of the playlist from Downtify.
2. Collect the tracks that are in the download folder or in the cloud folder. Find the missing tracks. The command is safe to run again.
3. Search YouTube with three query forms: `<artist> <title>`, `<title> <artist>`, `<title>`.
4. Rank the candidates: duration first, then an official channel, then the smallest duration difference.
5. Download the first `--attempts` candidates.
6. Check each candidate against the Spotify preview of the track. Use the Chromaprint audio fingerprint. Keep a candidate when at least `24/32` bits agree and at least half of the frames match.
7. Stop at the first candidate that passes the check.
8. Write the Spotify metadata: title, artists, album, album artist, cover.
9. Name the file `<artist> - <title>.mp3`. Remove the characters that OneDrive rejects.
10. Put the file in the download folder. If the folder is not writable, upload it from the staging folder.
11. Upload the file to `<dest>/<folder>/`.
12. Print a JSON report.

The Spotify preview is 30 seconds of the real track. The fingerprint finds the same audio at any offset. This rejects covers, karaoke, live versions, and drum covers that have the same duration.

## Output

```json
{"ok": true, "folder": "...", "missing": 1, "filled": 1,
 "results": [
  {"track": "...", "expected_duration": 255, "status": "filled",
   "video": "WrB2jUHrvhE", "video_duration": 256.0, "file_duration": 255.24,
   "delta": 1.0, "channel": "FLOW Official YouTube Channel",
   "verified": true, "match_score": 28.33,
   "scores": [{"video": "WrB2jUHrvhE", "mean": 28.33, "good": 0.922, "delta": 1.0}],
   "local": null, "uploaded": true}
]}
```

Status values: `filled`, `no-match`, `duration-mismatch`, `candidate` (dry run).

Exit code `0`: all missing tracks filled. Exit code `2`: one or more tracks failed.

Score guide: `29` to `32` is the same master. `24` to `29` is the same performance with a different master. Below `22` is a different recording.

## Rules

1. The fingerprint is the decision. A duration match alone is not enough. A drum cover can have the same duration.
2. Show the user the `no-match` entries with their `scores`. Ask before you choose a candidate with a score below `24`.
3. Do not edit the Downtify library database or the playlist M3U files.
4. If the report says `local: null`, tell the user that the track is in the cloud only. The download folder is owned by root.
5. Do not delete the Spotify preview files during a run. They are in the staging folder.
6. `--dry-run` for a long playlist sends three searches per missing track. It can take minutes.

## Requirements

- `yt-dlp`, `ffmpeg` in `PATH`. ffmpeg must have the `chromaprint` muxer.
- Python module `mutagen`.
- `rclone` in `PATH`. The remote (`onedrive:`) must be configured.
- `DOWNTIFY_USERNAME` and `DOWNTIFY_PASSWORD` in `.env` at the repository root.
- Run `music.playlist_to_cloud` first. The download folder must exist.
- A Spotify preview is not available for every track. Such tracks have no audio check.

## Limits

- The Spotify preview can use a different master than the playlist track. The score then stays near `26` although the performance is the same.
- The audio check needs one download per candidate. Four candidates take about 30 seconds per track.
- If two tracks in one playlist have the same artist and title, the second one can be reported as present when only the first is on disk.
