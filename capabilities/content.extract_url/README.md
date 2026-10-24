# content.extract_url — 实现说明

Agent 用法见 `AGENT_GUIDE.md`。本文件面向开发者。

## 两个能力

| 能力 | 语义 | 入口 |
|---|---|---|
| `resolve` | 这个 URL 是什么：只读元数据，不读 Cookie、不下载、不加载 ASR，<300ms | `src/cli.py resolve <URL>`，或 HTTP 服务 `src/service.py` |
| `extract` | 这个 URL 的完整内容：元数据 → 原生字幕 → 下载音频 + FireRedASR2-AED 转录 | `./run`，或 `src/cli.py extract <URL> [--json] [-o DIR]` |

## 平台

| 平台 | 元数据 | 字幕 | ASR 兜底 |
|---|---|---|---|
| YouTube | yt-dlp `-J` | 官方字幕 → 自动字幕 | yt-dlp 下载音频 |
| Bilibili | yt-dlp `-J` | 官方 / AI 字幕 | yt-dlp 下载音频 |
| 微信视频号 | 腾讯预览接口（匿名 `shortUri`） | 无 | 复用本机 Chrome 的元宝登录 Cookie 下载媒体流 |
| 公众号文章 | 页面 JS 变量（标题/公众号/发布时间） | `#js_content` 正文 → trafilatura → Markdown | 无 |
| 其他网页（兜底） | trafilatura 元数据 | trafilatura 正文 → Markdown | 无 |

网页抓取（`src/adapters/web.py`）每一跳重定向都会检查目标地址，拒绝内网 / 回环 / 保留地址，防止 resolve 服务被用作 SSRF。

## 目录

```text
run / doctor / setup     capability 入口（setup 创建 .venv 并安装依赖）
capability.json          capability 合约（输入/输出 schema）
src/api.py               公开 API：resolve_url, extract_url
src/cli.py               CLI：resolve / extract
src/pipeline.py          extract 流程编排
src/adapters/            平台元数据适配器（匿名）
src/media/               媒体获取（隔离认证）
src/asr.py               FireRedASR2-AED + Silero VAD；优先 GPU，不可用时回退 CPU
src/model_manager.py     模型下载、SHA-256 校验、原子部署
src/service.py           resolve 的 FastAPI 服务（Dockerfile 打包）
.venv/ .models/ .tmp/    本地运行时，git 忽略
```

## 开发

```bash
./setup                                                  # 创建 .venv
.venv/bin/python scripts/prepare_asr_model.py            # 可选：预下载 ASR 模型（否则首次 ASR 时下载）
.venv/bin/python -m unittest discover -s tests -p "test_*.py"
```

ASR 设备：环境变量 `FIRERED_ASR_PROVIDER=auto|cuda|cpu`（默认 `auto`）。

## Resolve HTTP 服务

```bash
export TOOLS_INTERNAL_TOKEN=<token>
.venv/bin/uvicorn src.service:app --host 0.0.0.0 --port 8000
```

| 端点 | 鉴权 | 说明 |
|---|---|---|
| `GET /healthz` | 无 | 存活检查 |
| `GET /readyz` | 无 | 未设置 `TOOLS_INTERNAL_TOKEN` 时返回 503 |
| `POST /v1/resolve` | `Bearer <token>` | 请求体 `{"schema_version": 1, "url": "..."}`；400 非法/不支持，401 鉴权失败，502 上游失败 |

错误格式：`{"error": {"code": "...", "message": "..."}}`。未知字段一律返回 `null`，不编造。
