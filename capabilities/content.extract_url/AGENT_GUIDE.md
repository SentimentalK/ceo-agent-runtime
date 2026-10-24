# content.extract_url

Gets the text of a URL. It uses native subtitles first. If there are no subtitles, it downloads the audio and uses local speech recognition (ASR).

Supported sites: YouTube, Bilibili, WeChat Channels (`weixin.qq.com/sph/...`).

## Run

```bash
capabilities/content.extract_url/run --url "<URL>" --output-dir "<OUTPUT_DIR>"
```

## Output

- `<OUTPUT_DIR>/result.json`: `metadata`, `transcript`, `transcript_status`, `transcript_method`.
- `<OUTPUT_DIR>/completion.json`: exit code, `business_status`, `error`.

## Rules

1. Run the command in the foreground. Wait until it stops. ASR can take several minutes.
2. If the command succeeds, read `result.json`.
3. If `transcript_status` is not `available`, tell the user. Do not write a transcript yourself.
4. If the command fails, read `completion.json` and the command output. Report the error.
5. If the command says that setup is necessary, run `capabilities/content.extract_url/setup`.
6. To examine the environment, run `capabilities/content.extract_url/doctor`.

## Requirements

- WeChat Channels: the user must be logged in to `yuanbao.tencent.com` in local Chrome.
- ASR: `ffmpeg` must be in `PATH`. The ASR model downloads on first use (about 1.2 GB).
