# WeChat Channels (微信视频号) SPH Acquisition Experiment Report

## 1. Executive Summary

This report documents real-world experiments conducted on WeChat Channels (`微信视频号`) share links (`https://weixin.qq.com/sph/<id>`), using sample URL `https://weixin.qq.com/sph/AF17JEGHVd`.

The goal was to identify the most minimal, reliable, and cost-effective content acquisition path for Phase 1 without premature dependencies on heavy browser automation (Playwright/Scrapling) or unauthenticated video reverse-engineering.

---

## 2. Experiment Matrix & Observations

### Experiment A — Plain HTTP & Redirect Handling
- **Request**: HTTP GET `https://weixin.qq.com/sph/AF17JEGHVd`
- **Redirect Chain**:
  - `301 Moved Permanently` -> `https://channels.weixin.qq.com/finder-preview/pages/sph?id=AF17JEGHVd`
- **Resulting Page**:
  - A client-side Single Page Application (SPA) with `<div id="app"></div>` and bundled scripts (`feed.*.js`, `merlin.*.js`, `mmfinderopenwebapisvr.*.js`).
  - No static HTML metadata, OpenGraph tags, or JSON-LD are pre-rendered in the initial HTML body.

### Discovery: Internal Preview API Endpoint
- Analysis of the frontend JavaScript bundles revealed that the SPA triggers an internal preview RPC upon initialization:
  - **Method**: `POST`
  - **URL**: `https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info`
  - **Payload**: `{"baseReq": {"generalToken": ""}, "shortUri": "<id>"}`
- **Experimental Finding**:
  In tested SPH samples, anonymous `shortUri` requests returned sufficient public metadata without login or browser rendering:
  - **Author / Creator**: `authorInfo.nickname` (e.g. `玩娱少女`)
  - **Avatar**: `authorInfo.headImgUrl`
  - **Description**: `feedInfo.description` (e.g. `鹦鹉:我也要这样婶儿的#看一遍笑一遍#萌宠#搞笑#抽象#万万没想到`)
  - **Cover Image**: `feedInfo.coverUrl`
  - **Creation Time**: `feedInfo.createtime` (Unix timestamp)
  - **Engagement Metrics**: `favCountFmt`, `likeCountFmt`, `forwardCountFmt`, `commentCountFmt`
  - **Export Identifier**: `sceneInfo.dynamicExportId`

> [!NOTE]
> This endpoint is an internal WeChat web preview API rather than a public guaranteed SLA contract. In the event Tencent alters this endpoint in the future, it should be treated as an adapter-level update rather than an architecture failure.

### Experiment B & C — Headless Browser (Chrome / Scrapling / Playwright)
- **Observations**:
  - Rendering the page in a headless browser runs the client-side JavaScript, which executes the exact same `get_feed_info` API call.
  - Because no user session or `token` exists in the unauthenticated browser context, the UI renders an overlay prompting users to scan a QR code in the WeChat mobile app:
    - `"可扫码前往微信观看此内容"` or `"此内容暂时无法播放"`.
  - The browser DOM does not yield any additional metadata beyond what the JSON API already returned.
- **Evaluation**:
  - Spawning a full browser instance adds significant CPU, memory, and startup latency overhead with zero informational benefit for metadata extraction.
  - Scrapling / Playwright are unnecessary for Phase 1 metadata ingestion.

### Experiment D — Open Source Resolvers Ecosystem
We investigated existing active projects including `ltaoo/wx_channels_download` and `joeseesun/qiaomu-wx-video`.
- **Media Stream Acquisition**:
  1. **Tencent Yuanbao Route**: Sends the share URL to `https://yuanbao.tencent.com/api/weixin/get_parse_result` to exchange for a `playable_url` containing a temporary `token` and `exportId`, which is then passed back to `get_feed_info`.
     - *Limitation*: Requires a valid logged-in Tencent Yuanbao cookie (`.tencent.com`). Without cookies, it responds with `401 Authorization Required`.
  2. **Local MITM Proxy Route**: Runs a local HTTPS proxy (e.g., SunnyNet) and intercepts decrypted video URLs when playback is initiated inside the WeChat Desktop client.
     - *Limitation*: Requires desktop client execution, root CA certificate installation, and system proxy manipulation.
  3. **Third-Party Workers Proxies**: Often rate-limited, unstable, or protected by basic authentication.

---

## 3. Native Subtitle Availability

- **Finding**: WeChat Channels does **not** distribute separate native timed subtitle tracks (WebVTT / SRT).
- Any captions visible on WeChat videos are either burned into the video video stream as hardcoded pixels (open captions) or rendered natively within the WeChat mobile client.
- **Semantic Rule**:
  `no native transcript != extraction failure`.
  When a WeChat video is ingested, metadata is preserved, `transcript_status` is set to `unavailable`, and a clean Markdown document is generated. Whisper ASR is not run automatically.

---

## 4. Production Acquisition Path (Phase 1)

```text
SPH URL (https://weixin.qq.com/sph/<id>)
   ↓
Extract shortUri id
   ↓
POST https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info
   ↓
Map author, title/description, coverUrl, publish date, metrics to ContentMetadata
   ↓
Native Subtitle = unavailable
   ↓
Output Markdown with complete YAML front matter
```

### Risk Boundaries & Platform Constraints
- WeChat Channels is inherently a closed mobile-first ecosystem.
- Changes to Tencent's web preview route or increased anti-bot restrictions are platform risks isolated entirely within `src/adapters/weixin.py`.

---

## 5. Phase 2 Roadmap (Design Only)

In Phase 2, if raw media extraction and speech/visual enrichment are required:

1. **Media Acquisition Provider**:
   - Pluggable provider interface (e.g. Yuanbao cookie session or local desktop proxy bridge) to supply `playable_url`.
2. **ASR Enricher (`ASREnricher`)**:
   - Download audio stream only when media URL is available.
   - Run Faster-Whisper with speech detection gating.
3. **Visual Text Enricher (`VisualTextEnricher`)**:
   - Sample keyframes from short videos.
   - Run OCR to recover code blocks, repo names, and hardcoded captions.
4. **Transcript Quality Gating (`quality.py`)**:
   - Evaluate whether transcript is mostly music, repetitive, or sufficient before finalizing the record.
