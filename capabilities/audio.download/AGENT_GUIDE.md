# audio.download

Downloads the audio of a URL as an MP3 file. Does not download video.

Supported sites: Bilibili, YouTube, and other sites that yt-dlp supports.

## Run

```bash
capabilities/audio.download/run "<URL>" [-o <OUTPUT_DIR>] [--quality <N>]
```

## Options

- `-o <OUTPUT_DIR>`: Output folder. Default: current folder.
- `--quality N`: MP3 quality from `0` (best) to `9` (smallest). Default: `0`.
- `--dry-run`: Print the yt-dlp command. Do not download.

## Output

- One MP3 file in `<OUTPUT_DIR>`.
- File name: `<title> [<id>].mp3`.

## Rules

1. Run the command in the foreground. Wait until it stops.
2. If the output says that a format is missing, tell the user. Do not change the format yourself.
3. If the output says that the format needs a premium account, tell the user.
4. If the command says that yt-dlp or ffmpeg is missing, tell the user. Do not install them yourself.
5. If the command fails, read the command output. Report the error.

## Requirements

- `yt-dlp` must be in `PATH`, or set `YT_DLP_PATH` to its path.
- `ffmpeg` must be in `PATH`. It converts the audio stream to MP3.

## Limits

- Some sites need a login. This capability does not pass cookies.
- Bilibili Dolby and Hi-Res audio need a premium account. The command uses the best free audio stream.
