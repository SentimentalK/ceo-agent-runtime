# content.extract_url

Gets the content of a URL.

| URL | Method |
|---|---|
| YouTube, Bilibili, WeChat Channels (`weixin.qq.com/sph/...`) | Native subtitles. If there are no subtitles, local speech recognition (ASR). |
| WeChat articles (`mp.weixin.qq.com/s...`) | Article body. |
| Other web pages | Main article text. |

## Run

```bash
capabilities/content.extract_url/run --url "<URL>" --output-dir "<OUTPUT_DIR>"
```

## Output

- `<OUTPUT_DIR>/result.json`: `metadata`, `transcript`, `transcript_status`, `transcript_method`.
  - For articles and web pages, `transcript` contains the article text in Markdown and `transcript_method` is `article`.
- `<OUTPUT_DIR>/completion.json`: exit code, `business_status`, `error`.

## Rules

1. Run the command in the foreground. Wait until it stops. ASR can take several minutes.
2. If the command succeeds, read `result.json`.
3. If `transcript_status` is not `available`, tell the user. Do not write a transcript yourself.
4. If the command fails, read `completion.json` and the command output. Report the error.
5. If the command says that setup is necessary, run `capabilities/content.extract_url/setup`.
6. To examine the environment, run `capabilities/content.extract_url/doctor`.

## Limits

- Web pages that need a login or JavaScript to show text give `transcript_status: unavailable`.
- PDF and other non-HTML URLs fail with "Unsupported content type".
- WeChat can show a verification page ("环境异常"). Then the command fails. Try again later.
- Private and local network addresses are refused.

## Requirements

- WeChat Channels: the user must be logged in to `yuanbao.tencent.com` in local Chrome.
- ASR: `ffmpeg` must be in `PATH`. The ASR model downloads on first use (about 1.2 GB).
