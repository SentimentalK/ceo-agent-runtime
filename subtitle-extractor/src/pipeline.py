"""
Internal content ingestion orchestration pipeline.
Coordinates platform adapters, media providers, ASR engine, and exporters.
"""

import os
import sys
import tempfile
from typing import Optional, Tuple

try:
    from .adapters import get_adapter_for_url
    from .content_grade import is_content_grade_text, is_no_speech_transcript
    from .markdown import export_markdown, sanitize_filename
    from .models import ContentMetadata, ResolvedContent
    from .resolver import resolve_url as _standalone_resolve_url
except (ImportError, ValueError):
    from adapters import get_adapter_for_url
    from content_grade import is_content_grade_text, is_no_speech_transcript
    from markdown import export_markdown, sanitize_filename
    from models import ContentMetadata, ResolvedContent
    from resolver import resolve_url as _standalone_resolve_url


class Pipeline:
    """Internal orchestration pipeline for resolving metadata and extracting full content."""

    def __init__(
        self,
        output_dir: str = "./output",
        browser_name: str = "chrome",
        profile_name: str = "Default",
        enable_asr_fallback: bool = True,  # Kept for backward compatibility
    ):
        self.output_dir = output_dir
        self.browser_name = browser_name
        self.profile_name = profile_name
        self.enable_asr_fallback = enable_asr_fallback

    def resolve_url(self, url: str) -> ContentMetadata:
        """
        Capability A: Lightweight, read-only metadata resolution.
        Never accesses cookies, downloads media/subtitles, or touches ASR.
        """
        return _standalone_resolve_url(url)

    def extract_url(self, url: str) -> ResolvedContent:
        """
        Capability B: Full content extraction.
        Independently resolves URL -> checks native transcript -> acquires media/ASR if needed.
        Never requires a prior resolve_url call.
        """
        adapter = get_adapter_for_url(
            url,
            browser_name=self.browser_name,
            profile_name=self.profile_name,
        )
        print(f"▶ 识别平台: {adapter.__class__.__name__} ({url})", file=sys.stderr)

        # Step 1: Resolve metadata (anonymous for WeChat; no cookies / media / ASR)
        metadata = adapter.resolve_metadata(url)

        # Step 1b: WeChat description is already on the metadata response.
        # If it is content-grade, publish it and skip media / ASR / OCR.
        if metadata.source_type == "weixin" and is_content_grade_text(metadata.description):
            print("✔ 微信 description 已达 content-grade，跳过媒体下载与 ASR", file=sys.stderr)
            return ResolvedContent(
                metadata=metadata,
                transcript=metadata.description.strip(),
                transcript_status="available",
                transcript_method="description",
            )

        # Lazy import heavy model manager, media providers, and ASR modules
        try:
            from .asr import download_media_for_asr, transcribe_media_file
            from .media import (
                MediaAuthError,
                MediaDownloadError,
                MediaProviderError,
                MediaResolveError,
                get_media_provider,
            )
            from .model_manager import get_tmp_dir
        except (ImportError, ValueError):
            from asr import download_media_for_asr, transcribe_media_file
            from media import (
                MediaAuthError,
                MediaDownloadError,
                MediaProviderError,
                MediaResolveError,
                get_media_provider,
            )
            from model_manager import get_tmp_dir

        with tempfile.TemporaryDirectory(prefix="ingest_", dir=str(get_tmp_dir())) as tmp_dir:

            # Step 2: Try native subtitles (WeChat has none; YouTube/Bilibili may)
            native = adapter.try_get_native_transcript(url, metadata, tmp_dir)
            if native and not is_no_speech_transcript(native.text):
                return ResolvedContent(
                    metadata=metadata,
                    transcript=native.text,
                    transcript_status="available",
                    transcript_method=native.method,
                )
            if native and is_no_speech_transcript(native.text):
                print("⚠ 原生字幕仅为静音标记，忽略", file=sys.stderr)

            # Step 3: Native transcript unavailable -> Attempt media acquisition & ASR fallback
            media_file = None
            prefix = f"asr_{metadata.source_id or 'media'}"

            if self.enable_asr_fallback:
                if metadata.source_type == "weixin":
                    print("▶ 微信视频号未包含外挂字幕，尝试通过本地浏览器会话获取媒体流...", file=sys.stderr)
                    try:
                        provider = get_media_provider(
                            "weixin",
                            browser_name=self.browser_name,
                            profile_name=self.profile_name,
                        )
                        if provider:
                            media_file = provider.acquire(url, tmp_dir, prefix)
                    except MediaAuthError as e:
                        print(f"⚠ 微信媒体认证失败 (跳过 ASR): {e}", file=sys.stderr)
                    except MediaResolveError as e:
                        print(f"⚠ 微信媒体解析失败 (跳过 ASR): {e}", file=sys.stderr)
                    except MediaDownloadError as e:
                        print(f"⚠ 微信媒体下载失败 (跳过 ASR): {e}", file=sys.stderr)
                    except MediaProviderError as e:
                        print(f"⚠ 微信媒体获取失败 (跳过 ASR): {e}", file=sys.stderr)
                    except Exception as e:
                        print(f"⚠ 媒体获取发生异常 (跳过 ASR): {e}", file=sys.stderr)

                elif metadata.source_type in ("youtube", "bilibili"):
                    print("▶ 未检测到原生字幕，尝试启动 yt-dlp 音频下载...", file=sys.stderr)
                    try:
                        media_file = download_media_for_asr(url, tmp_dir, prefix)
                    except Exception as e:
                        print(f"⚠ 媒体下载失败 (跳过 ASR): {e}", file=sys.stderr)

                # Step 4: If media was acquired, run FireRedASR2 speech recognition
                if media_file and os.path.exists(media_file):
                    try:
                        print("▶ 运行 FireRedASR2-AED 语音识别...", file=sys.stderr)
                        transcript = transcribe_media_file(media_file)
                        if is_no_speech_transcript(transcript):
                            print("⚠ ASR 无有效人声 (no_speech)，不写入 content", file=sys.stderr)
                        else:
                            print("✔ ASR 语音识别成功！", file=sys.stderr)
                            return ResolvedContent(
                                metadata=metadata,
                                transcript=transcript,
                                transcript_status="available",
                                transcript_method="firered-asr2-aed",
                            )
                    except Exception as e:
                        print(f"⚠ ASR 转录失败: {e}", file=sys.stderr)
                    finally:
                        if os.path.exists(media_file):
                            try:
                                os.remove(media_file)
                            except Exception:
                                pass

            return ResolvedContent(
                metadata=metadata,
                transcript=None,
                transcript_status="unavailable",
                transcript_method=None,
            )

    def process_url(self, url: str) -> Tuple[str, ResolvedContent]:
        """
        Internal backward-compatibility wrapper: extracts URL and writes Markdown artifact.
        """
        resolved = self.extract_url(url)
        clean_title = sanitize_filename(resolved.metadata.title or "Untitled")
        out_filename = f"{clean_title}.md"
        out_path = os.path.join(self.output_dir, out_filename)

        os.makedirs(self.output_dir, exist_ok=True)
        md_text = export_markdown(resolved)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_text)

        print(f"✨ 导出 Markdown 成功: {out_path}", file=sys.stderr)
        return out_path, resolved
