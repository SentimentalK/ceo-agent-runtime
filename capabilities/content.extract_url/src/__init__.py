"""
Subtitle Extractor & Content Ingestion Scaffold.

Public API:
- resolve_url(url: str) -> ContentMetadata
- extract_url(url: str, ...) -> ResolvedContent
"""

from .api import extract_url, resolve_url
from .contracts import ContentMetadataV1, ResolveUrlInputV1
from .models import ContentMetadata, ResolveError, ResolvedContent, UnsupportedURLError

__all__ = [
    "resolve_url",
    "extract_url",
    "ContentMetadata",
    "ResolvedContent",
    "ResolveError",
    "UnsupportedURLError",
    "ResolveUrlInputV1",
    "ContentMetadataV1",
]
