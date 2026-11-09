# music.playlist_to_cloud

Downloads Spotify playlists with the Downtify service on this machine. Then uploads the tracks to OneDrive with rclone.

## Run

```bash
capabilities/music.playlist_to_cloud/run "<PLAYLIST_URL>" [<PLAYLIST_URL> ...] [options]
capabilities/music.playlist_to_cloud/run --file list.txt [options]
capabilities/music.playlist_to_cloud/run --upload-only "<PLAYLIST_NAME>" [options]
```

## Options

- `--file FILE`: Read playlist URLs from a file. Put one URL on each line.
- `--upload-only`: Upload the local folder of each named playlist. Do not download.
- `--dest REMOTE`: rclone destination folder. Default: `onedrive:40_音乐`.
- `--downloads DIR`: Downtify download folder. Default: `~/downtify/downloads`.
- `--no-upload`: Download only. Do not run rclone.
- `--poll SECONDS`: Seconds between status checks. Default: `15`.
- `--timeout SECONDS`: Seconds to wait for one playlist. Default: `10800`.
- `--dry-run`: Resolve the lists and print the planned work. Change nothing.

## Steps

1. Sign in to Downtify.
2. Resolve each playlist URL to its track list.
3. Queue the batch download. If a batch for this playlist is already running, wait for it instead.
4. Wait until the queue is empty. The command also waits while other playlists download.
5. Find the download folder of the playlist.
6. Copy the MP3 and LRC files to `<dest>/<folder>`.
7. Print a JSON report.

Existing tracks are skipped. A second run does not download the same track again. rclone skips files that are already in the cloud.

## Output

JSON on stdout:

```json
{"ok": true, "dest": "onedrive:40_音乐", "playlists": [
  {"url": "...", "tracks": 86, "playlist": "...", "folder": "...",
   "batch_id": 7, "batch_status": "complete", "expected": 86,
   "downloaded": 86, "missing": 0,
   "upload": {"local_files": 172, "remote_files": 172, "remote": "onedrive:40_音乐/..."}}
]}
```

Progress lines go to stderr.

## Rules

1. Run the command in the foreground. Wait until it stops. A large list can take hours.
2. Read the JSON report. Give the user the playlist names, the track counts, and the missing counts.
3. If `missing` is not `0`, tell the user which tracks failed. Do not retry without a request.
4. If the command says that a playlist URL is not supported, tell the user. Give a playlist URL, not an album or a track URL.
5. If `local_files` is not equal to `remote_files`, run the command again. rclone continues the upload.
6. Do not delete local files after the upload. Ask the user first.

## Requirements

- Downtify must run and serve `DOWNTIFY_URL` (default `http://localhost:8000`).
- `rclone` must be in `PATH`. The remote (`onedrive:`) must be configured.
- Credentials: set `DOWNTIFY_USERNAME` and `DOWNTIFY_PASSWORD` in `.env` at the repository root.

## Limits

- Each playlist folder must have a unique name. Downtify names the folder after the playlist.
- Downloads use the Downtify settings: MP3 320 kbps, lyrics on, one download at a time, 3 seconds between tracks.
