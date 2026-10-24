"""
WeChat Official Account article (微信公众号文章) adapter.
Fetches mp.weixin.qq.com pages anonymously and extracts the #js_content body.
"""

import datetime
import html as html_lib
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

try:
    from .base import BaseAdapter
    from .web import extract_article_markdown, fetch_html
    from ..models import ContentMetadata, ResolveError, TranscriptResult
except (ImportError, ValueError):
    try:
        from adapters.base import BaseAdapter
        from adapters.web import extract_article_markdown, fetch_html
        from models import ContentMetadata, ResolveError, TranscriptResult
    except (ImportError, ValueError):
        from base import BaseAdapter
        from web import extract_article_markdown, fetch_html
        from models import ContentMetadata, ResolveError, TranscriptResult


# The WeChat in-app browser UA avoids the "环境异常" verification page more reliably.
WECHAT_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.50(0x1800323c) "
    "NetType/WIFI Language/zh_CN"
)


def _js_var(page: str, name: str) -> Optional[str]:
    """Read a string JS variable such as: var nickname = htmlDecode("...")."""
    m = re.search(
        rf"var\s+{name}\s*=\s*(?:htmlDecode\()?\s*(['\"])(.*?)\1",
        page,
        re.DOTALL,
    )
    if not m:
        return None
    value = html_lib.unescape(m.group(2)).strip()
    return value or None


def _meta_property(page: str, prop: str) -> Optional[str]:
    m = re.search(rf'<meta\s+property="{re.escape(prop)}"\s+content="([^"]*)"', page)
    return html_lib.unescape(m.group(1)).strip() or None if m else None


class WeixinArticleAdapter(BaseAdapter):
    """Adapter for mp.weixin.qq.com article links."""

    def __init__(self, browser_name: str = "chrome", profile_name: str = "Default"):
        self._html: Optional[str] = None

    @classmethod
    def can_handle(cls, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.hostname == "mp.weixin.qq.com" and parsed.path.startswith("/s")

    @classmethod
    def extract_source_id(cls, url: str) -> Optional[str]:
        parsed = urlparse(url)
        m = re.match(r"^/s/([A-Za-z0-9_-]+)", parsed.path)
        if m:
            return m.group(1)
        sn = parse_qs(parsed.query).get("sn")
        return sn[0] if sn else None

    def _fetch(self, url: str) -> str:
        _, page = fetch_html(url, user_agent=WECHAT_UA)
        if "环境异常" in page and 'id="js_content"' not in page:
            raise ResolveError(f"WeChat returned a verification page for {url}")
        if 'id="js_content"' not in page:
            raise ResolveError(f"WeChat article body not found (deleted or restricted?): {url}")
        return page

    def resolve_metadata(self, url: str) -> ContentMetadata:
        self._html = self._fetch(url)
        page = self._html

        published_at = None
        m = re.search(r'var\s+(?:ct|create_time)\s*=\s*"(\d{9,11})"', page)
        if m:
            published_at = (
                datetime.datetime.fromtimestamp(int(m.group(1)), tz=datetime.timezone.utc)
                .astimezone()
                .isoformat()
            )

        canonical = _meta_property(page, "og:url")
        if canonical:
            canonical = re.sub(r"[?&]nwr_flag=\d+", "", canonical)

        account = _js_var(page, "nickname")
        author = _js_var(page, "author")

        return ContentMetadata(
            source_type="weixin_article",
            source_url=url,
            canonical_url=canonical or url,
            source_id=self.extract_source_id(url),
            title=_js_var(page, "msg_title") or _meta_property(page, "og:title"),
            description=_js_var(page, "msg_desc") or _meta_property(page, "og:description"),
            creator=account or author,
            published_at=published_at,
            language="zh",
            thumbnail_url=_js_var(page, "msg_cdn_url") or _meta_property(page, "og:image"),
            platform_metadata={"account": account, "author": author} if author else None,
        )

    def try_get_native_transcript(
        self,
        url: str,
        metadata: ContentMetadata,
        tmp_dir: str,
    ) -> Optional[TranscriptResult]:
        import lxml.html

        if self._html is None:
            self._html = self._fetch(url)
        body = lxml.html.fromstring(self._html).get_element_by_id("js_content", None)
        if body is None:
            return None
        fragment = lxml.html.tostring(body, encoding="unicode")
        text = extract_article_markdown(f"<html><body><article>{fragment}</article></body></html>")
        return TranscriptResult(text=text, method="article") if text else None
