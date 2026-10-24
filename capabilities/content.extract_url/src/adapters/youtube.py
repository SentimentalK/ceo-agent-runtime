"""
YouTube platform adapter wrapping yt-dlp.
"""

import os
import re
from typing import Optional

try:
    from .base import BaseAdapter
    from ..models import ContentMetadata, ResolveError, TranscriptResult
    from ..ytdlp import download_subtitles, fetch_metadata, parse_srt_to_paragraphs
except (ImportError, ValueError):
    try:
        from adapters.base import BaseAdapter
        from models import ContentMetadata, ResolveError, TranscriptResult
        from ytdlp import download_subtitles, fetch_metadata, parse_srt_to_paragraphs
    except (ImportError, ValueError):
        from base import BaseAdapter
        from models import ContentMetadata, ResolveError, TranscriptResult
        from ytdlp import download_subtitles, fetch_metadata, parse_srt_to_paragraphs


class YouTubeAdapter(BaseAdapter):
    """Adapter for YouTube URLs."""

    YT_ARGS = [
        "--extractor-args", "youtube:player_client=android,web,default",
        "--remote-components", "ejs:github",
    ]

    @classmethod
    def can_handle(cls, url: str) -> bool:
        lower = url.lower()
        return "youtube.com" in lower or "youtu.be" in lower

    def resolve_metadata(self, url: str) -> ContentMetadata:
        """
        Lightweight metadata resolution for YouTube.
        Fetches metadata JSON via yt-dlp without downloading media or subtitles.
        """
        try:
            data = fetch_metadata(url, extra_args=self.YT_ARGS)
        except Exception as e:
            raise ResolveError(f"YouTube metadata resolution failed for {url}: {e}") from e

        if not data or not isinstance(data, dict):
            raise ResolveError(f"YouTube returned empty metadata for {url}")

        source_id = data.get("id")
        if not source_id:
            m = re.search(r"[?&]v=([^&#]+)", url)
            if m:
                source_id = m.group(1)
            elif "youtu.be/" in url:
                source_id = url.split("youtu.be/")[-1].split("?")[0]
            else:
                source_id = ""

        title = data.get("title") or None
        creator = data.get("uploader") or data.get("channel") or data.get("uploader_id")

        pub_date = data.get("upload_date")
        if pub_date and len(pub_date) == 8:
            published_at = f"{pub_date[:4]}-{pub_date[4:6]}-{pub_date[6:8]}"
        else:
            published_at = None

        return ContentMetadata(
            source_type="youtube",
            source_url=url,
            canonical_url=data.get("webpage_url") or url,
            source_id=source_id,
            title=title,
            description=data.get("description"),
            creator=creator,
            published_at=published_at,
            duration_seconds=data.get("duration"),
            thumbnail_url=data.get("thumbnail"),
            view_count=data.get("view_count"),
            like_count=data.get("like_count"),
            comment_count=data.get("comment_count"),
        )

    def try_get_native_transcript(
        self,
        url: str,
        metadata: ContentMetadata,
        tmp_dir: str,
    ) -> Optional[TranscriptResult]:
        """
        Attempt to download and parse native subtitles (manual or auto-captions).
        Returns TranscriptResult if available, otherwise None.
        """
        prefix = f"sub_{metadata.source_id or 'yt'}"
        sub_file, method = download_subtitles(url, tmp_dir, prefix, extra_args=self.YT_ARGS)

        if sub_file and os.path.exists(sub_file):
            try:
                paragraphs = parse_srt_to_paragraphs(sub_file)
                if paragraphs:
                    return TranscriptResult(text=paragraphs, method=method or "subtitles")
            finally:
                if os.path.exists(sub_file):
                    try:
                        os.remove(sub_file)
                    except Exception:
                        pass

        return None
