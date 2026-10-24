"""
Stable V1 wire contract definitions for the content resolver service.
Strictly versioned request, response, and error payloads.
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

try:
    from .models import ContentMetadata
except (ImportError, ValueError):
    from models import ContentMetadata


@dataclass
class ResolveUrlInputV1:
    """Input payload for resolving URL metadata."""
    url: str
    schema_version: int = 1

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResolveUrlInputV1":
        schema_version = data.get("schema_version", 1)
        url = data.get("url")
        if not url or not isinstance(url, str):
            raise ValueError("Field 'url' is required and must be a non-empty string.")
        return cls(url=url, schema_version=schema_version)


@dataclass
class ContentMetadataV1:
    """
    Versioned canonical source metadata response contract.
    All unknown/unavailable fields are explicitly None (serialized to JSON null).
    Never contains fabricated or synthetic fallback titles/metadata.
    """
    source_type: str
    source_url: str
    schema_version: int = 1
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

    @classmethod
    def from_content_metadata(cls, meta: ContentMetadata, schema_version: int = 1) -> "ContentMetadataV1":
        return cls(
            schema_version=schema_version,
            source_type=meta.source_type,
            source_url=meta.source_url,
            canonical_url=meta.canonical_url,
            source_id=meta.source_id,
            title=meta.title,
            description=meta.description,
            creator=meta.creator,
            published_at=meta.published_at,
            duration_seconds=meta.duration_seconds,
            language=meta.language,
            thumbnail_url=meta.thumbnail_url,
            media_url=meta.media_url,
            view_count=meta.view_count,
            like_count=meta.like_count,
            comment_count=meta.comment_count,
            captured_at=meta.captured_at,
            platform_metadata=meta.platform_metadata,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary with explicit nulls for missing values."""
        return asdict(self)


@dataclass
class ErrorDetail:
    code: str
    message: str


@dataclass
class ErrorResponse:
    error: ErrorDetail

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
