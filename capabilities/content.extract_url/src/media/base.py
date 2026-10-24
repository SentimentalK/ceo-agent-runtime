"""
Base interface and error types for media acquisition providers.
"""

from abc import ABC, abstractmethod


class MediaProviderError(Exception):
    """Base exception for media acquisition failures."""
    pass


class MediaAuthError(MediaProviderError):
    """Raised when authentication / session credentials are missing or expired."""
    pass


class MediaResolveError(MediaProviderError):
    """Raised when the media URL or stream cannot be resolved."""
    pass


class MediaDownloadError(MediaProviderError):
    """Raised when media streaming or file saving fails."""
    pass


class BaseMediaProvider(ABC):
    """Abstract base class for platform-specific media acquisition providers."""

    @abstractmethod
    def acquire(self, url: str, output_dir: str, prefix: str) -> str:
        """
        Acquire and download media file for the given URL into output_dir.
        Returns the absolute path to the downloaded media file.
        Raises MediaProviderError subclasses on failure.
        """
        pass
