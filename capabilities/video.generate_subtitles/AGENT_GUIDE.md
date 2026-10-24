# video.generate_subtitles

Makes subtitles for a local video file with local speech recognition (FireRedASR2-AED). Puts the subtitles into an MP4 as a soft subtitle track.

## Run

```bash
capabilities/video.generate_subtitles/run "<VIDEO>" [-s <SRT>] [-v <VTT>] [-o <OUTPUT_MP4>] [--no-embed]
```

## Output

If you do not give paths, the files go next to the video:

- `<name>.srt`
- `<name>.vtt`
- `<name>_subtitled.mp4` (not made with `--no-embed`)

## Rules

1. Run the command in the foreground. Wait until it stops. A long video can take many minutes.
2. If the output says that no speech was found, tell the user. Do not write subtitles yourself.
3. If the command says that the Python environment is missing, run `capabilities/content.extract_url/setup`.

## Requirements

- This capability uses the Python environment and ASR model of `content.extract_url`.
- `ffmpeg` must be in `PATH`.
- The subtitle track is labeled Chinese. The model also recognizes English.
