"""
Unit tests for the generic web adapter and the WeChat article adapter (offline).
"""

import os
import sys
import unittest
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.adapters import WebAdapter, WeixinAdapter, WeixinArticleAdapter, get_adapter_for_url
from src.adapters.web import ensure_public_host
from src.models import ResolveError

PARAGRAPH = "这是一段用于测试的正文内容，长度足够让正文提取器把它识别为文章主体。" * 3

WEIXIN_HTML = f"""<html><head>
<meta property="og:title" content="OG 标题" />
<meta property="og:url" content="https://mp.weixin.qq.com/s/AbC123?nwr_flag=1" />
</head><body>
<div id="page-ui">在小说阅读器读本章 微信扫一扫</div>
<div id="js_content"><p>{PARAGRAPH}</p><p>{PARAGRAPH}</p></div>
<script>
var nickname = htmlDecode("测试公众号");
var msg_title = '测试文章标题'.html(false);
var msg_desc = htmlDecode("文章摘要");
var author = "张三";
var ct = "1784263917";
var msg_cdn_url = "https://mmbiz.qpic.cn/cover.jpg";
</script></body></html>"""

WEB_HTML = f"""<html lang="en"><head><title>Example Article</title>
<meta name="author" content="Jane Doe" /></head>
<body><nav>Home | About</nav><article><h1>Example Article</h1>
<p>{PARAGRAPH}</p><p>{PARAGRAPH}</p></article><footer>Copyright</footer></body></html>"""


class TestRouting(unittest.TestCase):
    def test_weixin_article_routing(self):
        for url in (
            "https://mp.weixin.qq.com/s/NRLy2VIXluqpqM5efpS2aw",
            "https://mp.weixin.qq.com/s?__biz=MzIz&mid=1&idx=1&sn=abc",
        ):
            self.assertIsInstance(get_adapter_for_url(url), WeixinArticleAdapter)

    def test_channels_still_routes_to_weixin_adapter(self):
        self.assertIsInstance(get_adapter_for_url("https://weixin.qq.com/sph/AF17JEGHVd"), WeixinAdapter)

    def test_generic_url_falls_back_to_web(self):
        self.assertIsInstance(get_adapter_for_url("https://example.com/post/1"), WebAdapter)

    def test_source_id(self):
        self.assertEqual(WeixinArticleAdapter.extract_source_id("https://mp.weixin.qq.com/s/AbC_1-2"), "AbC_1-2")
        self.assertEqual(
            WeixinArticleAdapter.extract_source_id("https://mp.weixin.qq.com/s?__biz=x&sn=deadbeef"), "deadbeef"
        )


class TestPublicHostGuard(unittest.TestCase):
    def test_rejects_non_public_addresses(self):
        for url in ("http://localhost/", "http://127.0.0.1:8000/", "http://169.254.169.254/", "http://10.0.0.1/"):
            with self.assertRaises(ResolveError, msg=url):
                ensure_public_host(url)

    def test_rejects_non_http_scheme(self):
        with self.assertRaises(ResolveError):
            ensure_public_host("file:///etc/passwd")


class TestWeixinArticleAdapter(unittest.TestCase):
    @patch("src.adapters.weixin_article.fetch_html")
    def test_metadata_and_body(self, mock_fetch):
        mock_fetch.return_value = ("https://mp.weixin.qq.com/s/AbC123", WEIXIN_HTML)
        adapter = WeixinArticleAdapter()
        url = "https://mp.weixin.qq.com/s/AbC123"

        meta = adapter.resolve_metadata(url)
        self.assertEqual(meta.source_type, "weixin_article")
        self.assertEqual(meta.title, "测试文章标题")
        self.assertEqual(meta.creator, "测试公众号")
        self.assertEqual(meta.description, "文章摘要")
        self.assertEqual(meta.canonical_url, "https://mp.weixin.qq.com/s/AbC123")
        self.assertEqual(meta.platform_metadata, {"account": "测试公众号", "author": "张三"})
        self.assertTrue(meta.published_at.startswith("2026-"))

        result = adapter.try_get_native_transcript(url, meta, "")
        self.assertEqual(result.method, "article")
        self.assertIn("测试的正文内容", result.text)
        self.assertNotIn("微信扫一扫", result.text)
        self.assertEqual(mock_fetch.call_count, 1)

    @patch("src.adapters.weixin_article.fetch_html")
    def test_verification_page_raises(self, mock_fetch):
        mock_fetch.return_value = ("https://mp.weixin.qq.com/s/x", "<html>环境异常 去验证</html>")
        with self.assertRaises(ResolveError):
            WeixinArticleAdapter().resolve_metadata("https://mp.weixin.qq.com/s/x")


class TestWebAdapter(unittest.TestCase):
    @patch("src.adapters.web.fetch_html")
    def test_metadata_and_article(self, mock_fetch):
        mock_fetch.return_value = ("https://example.com/post/1", WEB_HTML)
        adapter = WebAdapter()
        meta = adapter.resolve_metadata("https://example.com/post/1")
        self.assertEqual(meta.source_type, "web")
        self.assertEqual(meta.title, "Example Article")
        self.assertEqual(meta.creator, "Jane Doe")

        result = adapter.try_get_native_transcript("https://example.com/post/1", meta, "")
        self.assertEqual(result.method, "article")
        self.assertIn("测试的正文内容", result.text)
        self.assertNotIn("Home | About", result.text)

    @patch("src.adapters.web.fetch_html")
    def test_page_without_text_returns_none(self, mock_fetch):
        mock_fetch.return_value = ("https://example.com/", "<html><body><p>hi</p></body></html>")
        adapter = WebAdapter()
        meta = adapter.resolve_metadata("https://example.com/")
        self.assertIsNone(adapter.try_get_native_transcript("https://example.com/", meta, ""))


if __name__ == "__main__":
    unittest.main()
