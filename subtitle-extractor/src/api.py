"""
Public Python API for Subtitle Extractor & Content Ingestion Scaffold.

Exposes exactly two capabilities:
1. resolve_url(url: str) -> ContentMetadata
   Lightweight, read-only metadata lookup. Never accesses cookies, downloads media,
   or initializes ASR.
2. extract_url(url: str, ...) -> ResolvedContent
   Autonomous full content extraction (metadata -> native subtitles -> media/ASR fallback).
"""

from typing import Optional

try:
    from .models import ContentMetadata, ResolveError, ResolvedContent, UnsupportedURLError
    from .resolver import resolve_url
except (ImportError, ValueError):
    from models import ContentMetadata, ResolveError, ResolvedContent, UnsupportedURLError
    from resolver import resolve_url

__all__ = [
    "resolve_url",
    "extract_url",
    "ContentMetadata",
    "ResolvedContent",
    "ResolveError",
    "UnsupportedURLError",
]


def extract_url(
    url: str,
    browser_name: str = "chrome",
    profile_name: str = "Default",
) -> ResolvedContent:
    """
    Extract full content for any supported URL.

    - Completely self-contained: independently resolves the URL without requiring
      a prior resolve_url() call.
    - WeChat: if feed description is content-grade, use it and skip media/ASR.
    - Otherwise checks for platform native subtitles.
    - If native subtitles are unavailable, acquires media (reusing local browser
      auth state if necessary) and runs local FireRedASR2-AED offline speech recognition.
    - ASR silence tokens such as `<sil>` are no_speech, never published as content.
    - Returns ResolvedContent containing ContentMetadata and full transcript.

    Raises:
        UnsupportedURLError: If the URL platform is not supported.
        ResolveError: If metadata resolution fails.
    """
    try:
        from .pipeline import Pipeline
    except (ImportError, ValueError):
        from pipeline import Pipeline

    pipeline = Pipeline(browser_name=browser_name, profile_name=profile_name)
    return pipeline.extract_url(url)
