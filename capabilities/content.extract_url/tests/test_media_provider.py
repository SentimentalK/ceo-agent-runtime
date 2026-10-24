"""
Unit tests for WeixinMediaProvider, cookie domain filtering, credential redaction, and typed errors.
"""

from dataclasses import dataclass
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.media.base import (
    MediaAuthError,
    MediaDownloadError,
    MediaProviderError,
    MediaResolveError,
)
from src.media.weixin import WeixinMediaProvider, redact_sensitive_url
from src.pipeline import Pipeline


@dataclass
class MockCookie:
    domain: str
    name: str
    value: str


class TestWeixinMediaProvider(unittest.TestCase):
    def test_typed_error_hierarchy(self):
        self.assertTrue(issubclass(MediaAuthError, MediaProviderError))
        self.assertTrue(issubclass(MediaResolveError, MediaProviderError))
        self.assertTrue(issubclass(MediaDownloadError, MediaProviderError))

    def test_redact_sensitive_url(self):
        raw_url = (
            "https://channels.weixin.qq.com/feed?token=SECRET_TOKEN_12345"
            "&eid=export_123&encfilekey=SECRET_FILE_KEY&comment_scene=39"
        )
        redacted = redact_sensitive_url(raw_url)
        self.assertNotIn("SECRET_TOKEN_12345", redacted)
        self.assertNotIn("SECRET_FILE_KEY", redacted)
        self.assertIn("token=[REDACTED]", redacted)
        self.assertIn("encfilekey=[REDACTED]", redacted)
        self.assertIn("eid=export_123", redacted)
        self.assertIn("comment_scene=39", redacted)

    def test_strict_cookie_domain_filtering(self):
        mock_jar = [
            MockCookie(domain=".google.com", name="SID", value="google_secret"),
            MockCookie(domain="github.com", name="user_session", value="gh_secret"),
            MockCookie(domain="evil.com", name="token", value="evil_secret"),
            MockCookie(domain=".tencent.com", name="hy_token", value="valid_hy_token"),
            MockCookie(domain=".tencent.com", name="hy_user", value="valid_hy_user"),
            MockCookie(domain="yuanbao.tencent.com", name="561553b295037d16", value="yb_token"),
            MockCookie(domain=".tencent.com", name="unrelated_junk", value="junk"),
        ]

        provider = WeixinMediaProvider()
        with patch("src.media.weixin.extract_cookies_from_browser", return_value=mock_jar):
            filtered = provider.extract_filtered_cookies()

        # Must contain allowed Tencent/Yuanbao cookies
        self.assertEqual(filtered.get("hy_token"), "valid_hy_token")
        self.assertEqual(filtered.get("hy_user"), "valid_hy_user")
        self.assertEqual(filtered.get("561553b295037d16"), "yb_token")

        # Must NEVER contain external cookies
        self.assertNotIn("SID", filtered)
        self.assertNotIn("user_session", filtered)
        self.assertNotIn("evil_secret", str(filtered))
        self.assertNotIn("google_secret", str(filtered))

    def test_missing_auth_cookie_raises_media_auth_error(self):
        # Cookie jar with no hy_token
        mock_jar = [
            MockCookie(domain=".tencent.com", name="other", value="123")
        ]
        provider = WeixinMediaProvider()
        with patch("src.media.weixin.extract_cookies_from_browser", return_value=mock_jar):
            with self.assertRaises(MediaAuthError):
                provider.extract_filtered_cookies()

    def test_yuanbao_expired_session_raises_media_auth_error(self):
        provider = WeixinMediaProvider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 20001, "msg": "Login session expired, please login"}

        with patch("httpx.Client.post", return_value=mock_resp):
            with self.assertRaises(MediaAuthError):
                provider._call_yuanbao_parse("https://weixin.qq.com/sph/123", {"hy_token": "expired"})

    def test_yuanbao_general_parse_error_raises_media_resolve_error(self):
        provider = WeixinMediaProvider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 500, "msg": "Video not found"}

        with patch("httpx.Client.post", return_value=mock_resp):
            with self.assertRaises(MediaResolveError):
                provider._call_yuanbao_parse("https://weixin.qq.com/sph/123", {"hy_token": "valid"})

    def test_metadata_only_path_never_invokes_media_provider(self):
        """Verify that default metadata ingestion never accesses cookies or media provider."""
        with tempfile.TemporaryDirectory() as td:
            pipeline = Pipeline(output_dir=td, enable_asr_fallback=False)
            with patch("src.media.weixin.WeixinMediaProvider.acquire") as mock_acquire, \
                 patch("src.media.weixin.extract_cookies_from_browser") as mock_extract:
                
                with patch("src.adapters.weixin.WeixinAdapter.resolve") as mock_resolve:
                    from src.models import ContentMetadata, ResolvedContent
                    mock_resolve.return_value = ResolvedContent(
                        metadata=ContentMetadata(
                            source_type="weixin",
                            source_url="https://weixin.qq.com/sph/test",
                            title="Mock Video",
                        ),
                        transcript=None,
                        transcript_status="unavailable",
                    )
                    pipeline.process_url("https://weixin.qq.com/sph/test")

                mock_acquire.assert_not_called()
                mock_extract.assert_not_called()


if __name__ == "__main__":
    unittest.main()
