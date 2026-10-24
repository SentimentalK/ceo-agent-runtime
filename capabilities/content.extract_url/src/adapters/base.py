"""
Base abstract platform adapter.
"""

from abc import ABC, abstractmethod
from typing import Optional

try:
    from ..models import ContentMetadata, ResolvedContent, TranscriptResult
except (ImportError, ValueError):
    try:
        from .models import ContentMetadata, ResolvedContent, TranscriptResult
    except (ImportError, ValueError):
        from models import ContentMetadata, ResolvedContent, TranscriptResult


class BaseAdapter(ABC):
    """Abstract base class for platform adapters."""

    @classmethod
    @abstractmethod
    def can_handle(cls, url: str) -> bool:
        """Return True if this adapter can process the given URL."""
        pass

    @abstractmethod
    def resolve_metadata(self, url: str) -> ContentMetadata:
        """
        Extract lightweight, read-only metadata from URL.
        Must never download media/subtitles, read browser cookies, or initialize ASR.
        Must raise ResolveError if resolution fails.
        """
        pass

    @abstractmethod
    def try_get_native_transcript(
        self,
        url: str,
        metadata: ContentMetadata,
        tmp_dir: str,
    ) -> Optional[TranscriptResult]:
        """
        Attempt to retrieve native subtitles/transcripts for this platform.
        Returns TranscriptResult if native subtitles exist, or None.
        """
        pass

    def resolve(self, url: str, tmp_dir: Optional[str] = None) -> ResolvedContent:
        """
        Internal backward-compatibility wrapper combining resolve_metadata
        and try_get_native_transcript.
        """
        metadata = self.resolve_metadata(url)
        native = self.try_get_native_transcript(url, metadata, tmp_dir or "")
        if native:
            return ResolvedContent(
                metadata=metadata,
                transcript=native.text,
                transcript_status="available",
                transcript_method=native.method,
            )
        return ResolvedContent(
            metadata=metadata,
            transcript=None,
            transcript_status="unavailable",
            transcript_method=None,
        )
