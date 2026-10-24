"""
Platform adapter registry and exports.
"""

try:
    from .base import BaseAdapter
    from .bilibili import BilibiliAdapter
    from .weixin import WeixinAdapter
    from .weixin_article import WeixinArticleAdapter
    from .web import WebAdapter
    from .youtube import YouTubeAdapter
    from ..models import UnsupportedURLError
except (ImportError, ValueError):
    try:
        from adapters.base import BaseAdapter
        from adapters.bilibili import BilibiliAdapter
        from adapters.weixin import WeixinAdapter
        from adapters.weixin_article import WeixinArticleAdapter
        from adapters.web import WebAdapter
        from adapters.youtube import YouTubeAdapter
        from models import UnsupportedURLError
    except (ImportError, ValueError):
        from base import BaseAdapter
        from bilibili import BilibiliAdapter
        from weixin import WeixinAdapter
        from weixin_article import WeixinArticleAdapter
        from web import WebAdapter
        from youtube import YouTubeAdapter
        from models import UnsupportedURLError

ADAPTERS = [
    YouTubeAdapter,
    BilibiliAdapter,
    WeixinAdapter,
    WeixinArticleAdapter,
    WebAdapter,  # fallback for any http(s) URL; keep last
]


def get_adapter_for_url(url: str, browser_name: str = "chrome", profile_name: str = "Default") -> BaseAdapter:
    """Find and instantiate the matching adapter for a URL."""
    for adapter_cls in ADAPTERS:
        if adapter_cls.can_handle(url):
            try:
                return adapter_cls(browser_name=browser_name, profile_name=profile_name)
            except TypeError:
                return adapter_cls()
    raise UnsupportedURLError(f"No adapter registered for URL: {url}")
