# video.download

Downloads the video file from a URL. Does not download audio only. Does not convert audio.

Supported sites: Bilibili, YouTube, and other sites that yt-dlp supports.

## Run

```bash
capabilities/video.download/run "<URL>" [--height <N>] [-o <OUTPUT_DIR>]
```

## Options

- `--height N`: Highest video height. Default: `1080`. For 720p, use `--height 720`.
- `-o <OUTPUT_DIR>`: Output folder. Default: current folder.
- `--dry-run`: Print the yt-dlp command. Do not download.

## Output

- One MP4 file in `<OUTPUT_DIR>`.
- File name: `<title> [<id>] <height>p.mp4`.
- Video and audio are copied into the MP4. Audio is not re-encoded.

## Rules

1. Run the command in the foreground. Wait until it stops. A 1080p video can take several minutes.
2. If the output says that a format is missing, tell the user. Do not change the format yourself.
3. If the output says that the format needs a premium account, tell the user. Give the user the `--height 720` option.
4. If the command says that yt-dlp or ffmpeg is missing, tell the user. Do not install them yourself.
5. If the command fails, read the command output. Report the error.

## Requirements

- `yt-dlp` must be in `PATH`, or set `YT_DLP_PATH` to its path.
- `ffmpeg` must be in `PATH`. It merges the video and audio streams.

## Limits

- Bilibili shows the "1080P 高码率" format only to premium members. The standard 1080p format works without a login.
- Some sites need a login. This capability does not pass cookies.
