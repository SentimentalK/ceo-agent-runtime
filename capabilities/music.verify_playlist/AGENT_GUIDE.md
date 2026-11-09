# music.verify_playlist

Checks every track of a playlist against the Spotify preview of that track. Finds wrong versions: covers, live versions, and different edits.

## Run

```bash
capabilities/music.verify_playlist/run "<PLAYLIST_URL>" [options]
```

## Options

- `--downloads DIR`: Downtify download folder. Default: `~/downtify/downloads`.
- `--dest REMOTE`: rclone destination folder. Default: `onedrive:40_音乐`.
- `--folder NAME`: Playlist folder name. Default: found from the files.
- `--staging DIR`: Folder for temporary files. Default: `temp/`.

## Steps

1. Read the track list of the playlist from Downtify.
2. Find the playlist folder. Use the local MP3 files first, then the cloud files.
3. Download the 30 second Spotify preview of every track.
4. Compare the audio fingerprints (Chromaprint) of the preview and the file.
5. Print a JSON report.

## Output

```json
{"ok": true, "folder": "liked song",
 "summary": {"MATCH": 62, "SAME-PERFORMANCE": 7},
 "tracks": [
  {"track": "...", "expected_duration": 255, "verdict": "SAME-PERFORMANCE",
   "mean": 28.33, "good": 0.922, "source": "cloud"}
]}
```

Verdicts:

| Verdict | Mean bits | Meaning |
|---|---|---|
| `MATCH` | 29 to 32 | The same master. |
| `SAME-PERFORMANCE` | 24 to 29 | The same performance. A different master or edit. |
| `MISMATCH` | below 24 | A different recording. A cover or a live version. |
| `MISSING` | none | The track is in no folder. |
| `NO-PREVIEW` | none | Spotify has no preview for this track. |

Exit code `0`: no `MISMATCH` and no `MISSING`. Exit code `2`: one or more problems.

## Rules

1. A `MISMATCH` is a wrong track. Replace it with `music.fill_from_youtube`.
2. Tell the user about every `SAME-PERFORMANCE` track. The duration can differ from Spotify.
3. The check reads the local file when it exists. It reads the cloud file only when the local file is missing. Say which one the report used (`source`).
4. A full playlist takes about 3 seconds per track. Cloud files add the download time.

## Requirements

- `ffmpeg` in `PATH`. ffmpeg must have the `chromaprint` muxer.
- `rclone` in `PATH`.
- `DOWNTIFY_USERNAME` and `DOWNTIFY_PASSWORD` in `.env` at the repository root.
- The playlist must have a batch in Downtify, or a local folder.

## Limits

- Spotify previews are 30 second excerpts. A track with only silence in the excerpt is not distinguishable.
- Some tracks have no preview. The command reports `NO-PREVIEW`.
- The comparison uses 8-bit frame hashes. Two different recordings of the same song seldom go above `22`.
