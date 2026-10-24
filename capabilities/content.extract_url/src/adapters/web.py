"""
Generic web page adapter (fallback for any http/https URL).
Fetches the page anonymously and extracts the main article text with trafilatura.
"""

import ipaddress
import socket
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx

try:
    from .base import BaseAdapter
    from ..models import ContentMetadata, ResolveError, TranscriptResult
except (ImportError, ValueError):
    try:
        from adapters.base import BaseAdapter
        from models import ContentMetadata, ResolveError, TranscriptResult
    except (ImportError, ValueError):
        from base import BaseAdapter
        from models import ContentMetadata, ResolveError, TranscriptResult


DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
MAX_PAGE_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 5
MIN_ARTICLE_CHARS = 50


def ensure_public_host(url: str) -> None:
    """Reject URLs whose host resolves to a private, loopback, or reserved address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ResolveError(f"Not an http(s) URL: {url}")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or None)
    except socket.gaierror as e:
        raise ResolveError(f"Cannot resolve host {parsed.hostname}: {e}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ResolveError(f"Refusing to fetch non-public address {ip} for {parsed.hostname}")


def fetch_html(url: str, user_agent: str = DESKTOP_UA, timeout: float = 20.0) -> Tuple[str, str]:
    """
    Fetch an HTML page. Every redirect hop is checked with ensure_public_host.
    Returns (final_url, html).
    """
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    current = url
    with httpx.Client(headers=headers, timeout=timeout, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            ensure_public_host(current)
            try:
                with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        current = urljoin(current, resp.headers.get("location", ""))
                        continue
                    if resp.status_code >= 400:
                        raise ResolveError(f"HTTP {resp.status_code} fetching {current}")
                    content_type = resp.headers.get("content-type", "")
                    if "html" not in content_type and "xml" not in content_type:
                        raise ResolveError(f"Unsupported content type '{content_type}' at {current}")
                    body = b""
                    for chunk in resp.iter_bytes():
                        body += chunk
                        if len(body) > MAX_PAGE_BYTES:
                            raise ResolveError(f"Page exceeds {MAX_PAGE_BYTES} bytes: {current}")
                    encoding = resp.encoding or "utf-8"
                    return current, body.decode(encoding, errors="replace")
            except httpx.HTTPError as e:
                raise ResolveError(f"Request failed for {current}: {e}") from e
    raise ResolveError(f"Too many redirects for {url}")


def extract_article_markdown(html: str) -> Optional[str]:
    """Extract main text as Markdown. Returns None when no usable text is found."""
    import trafilatura

    text = trafilatura.extract(
        html,
        output_format="markdown",
        include_tables=True,
        include_comments=False,
        favor_recall=True,
    )
    if not text or len(text.strip()) < MIN_ARTICLE_CHARS:
        return None
    return text.strip()


class WebAdapter(BaseAdapter):
    """Fallback adapter for any http/https web page."""

    def __init__(self, browser_name: str = "chrome", profile_name: str = "Default"):
        self._html: Optional[str] = None

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return urlparse(url).scheme in ("http", "https") and bool(urlparse(url).hostname)

    def resolve_metadata(self, url: str) -> ContentMetadata:
        import trafilatura

        final_url, self._html = fetch_html(url)
        meta = trafilatura.extract_metadata(self._html, default_url=final_url)

        return ContentMetadata(
            source_type="web",
            source_url=url,
            canonical_url=(meta.url if meta and meta.url else final_url),
            title=meta.title if meta else None,
            description=meta.description if meta else None,
            creator=meta.author if meta else None,
            published_at=meta.date if meta else None,
            language=meta.language if meta else None,
            thumbnail_url=meta.image if meta else None,
            platform_metadata={"site_name": meta.sitename} if meta and meta.sitename else None,
        )

    def try_get_native_transcript(
        self,
        url: str,
        metadata: ContentMetadata,
        tmp_dir: str,
    ) -> Optional[TranscriptResult]:
        if self._html is None:
            _, self._html = fetch_html(url)
        text = extract_article_markdown(self._html)
        return TranscriptResult(text=text, method="article") if text else None
