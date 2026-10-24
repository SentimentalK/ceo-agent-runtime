"""
Lightweight, side-effect-free resolver capability.
Directly invokes platform adapters for metadata resolution.
Strictly decoupled from heavy Pipeline, media acquisition, and ASR execution.
"""

from typing import Optional

try:
    from .adapters import get_adapter_for_url
    from .models import ContentMetadata, ResolveError, UnsupportedURLError
except (ImportError, ValueError):
    from adapters import get_adapter_for_url
    from models import ContentMetadata, ResolveError, UnsupportedURLError


def resolve_url(url: str) -> ContentMetadata:
    """
    Lightweight, read-only metadata resolution for any supported URL.

    - Performs platform detection and public metadata lookup.
    - Fast and read-only (<300ms typical).
    - Strictly never touches browser cookies or local profiles.
    - Strictly never downloads media or subtitle files.
    - Strictly never initializes, downloads, or loads FireRedASR2 or Silero VAD models.
    - Strictly never creates temporary working directories.

    Raises:
        UnsupportedURLError: If the URL platform is not supported.
        ResolveError: If metadata resolution fails.
    """
    adapter = get_adapter_for_url(url)
    return adapter.resolve_metadata(url)
