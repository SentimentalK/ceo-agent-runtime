"""
Media acquisition providers registry and exports.
"""

from typing import Optional

try:
    from .base import (
        BaseMediaProvider,
        MediaAuthError,
        MediaDownloadError,
        MediaProviderError,
        MediaResolveError,
    )
    from .weixin import WeixinMediaProvider, redact_sensitive_url
except (ImportError, ValueError):
    from base import (
        BaseMediaProvider,
        MediaAuthError,
        MediaDownloadError,
        MediaProviderError,
        MediaResolveError,
    )
    from weixin import WeixinMediaProvider, redact_sensitive_url


def get_media_provider(source_type: str, **kwargs) -> Optional[BaseMediaProvider]:
    """Factory to get the appropriate media provider for a platform."""
    if source_type == "weixin":
        return WeixinMediaProvider(**kwargs)
    return None
