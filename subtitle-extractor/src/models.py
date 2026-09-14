"""
Common data models and typed errors for content metadata and resolved content.
"""

from dataclasses import asdict, dataclass, field
import datetime
from typing import Any, Dict, Optional


class ResolveError(Exception):
    """Raised when lightweight metadata resolution fails."""
    pass


class UnsupportedURLError(ResolveError, ValueError):
    """Raised when no platform adapter can handle the URL."""
    pass


@dataclass
class TranscriptResult:
    """Internal representation of a retrieved native subtitle transcript."""
    text: str
    method: str  # e.g. "subtitles", "auto-subtitles"


@dataclass
class ContentMetadata:
    source_type: str
    source_url: str
    canonical_url: Optional[str] = None
    source_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    creator: Optional[str] = None
    published_at: Optional[str] = None
    duration_seconds: Optional[int | float] = None
    language: Optional[str] = None
    thumbnail_url: Optional[str] = None
    media_url: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int | str] = None
    comment_count: Optional[int | str] = None
    captured_at: Optional[str] = None
    platform_metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.captured_at is None:
            self.captured_at = datetime.datetime.now().astimezone().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to JSON-serializable dictionary."""
        return asdict(self)


@dataclass
class ResolvedContent:
    metadata: ContentMetadata
    transcript: Optional[str] = None
    transcript_status: str = "unavailable"  # "available", "unavailable", "failed"
    transcript_method: Optional[str] = None  # "description", "subtitles", "auto-subtitles", "firered-asr2-aed", None

    def to_dict(self) -> Dict[str, Any]:
        """Convert resolved content to JSON-serializable dictionary."""
        return asdict(self)
