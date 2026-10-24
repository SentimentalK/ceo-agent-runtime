"""
Unit tests for lightweight resolver boundary isolation and V1 contracts.
Verifies that the resolver path does not import heavy ASR/NumPy modules,
does not touch cookies/media/subtitles, and produces canonical V1 contracts.
"""

import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.contracts import ContentMetadataV1, ResolveUrlInputV1
from src.models import ContentMetadata, ResolveError, UnsupportedURLError
from src.resolver import resolve_url


class TestResolverBoundary(unittest.TestCase):
    def test_clean_process_resolver_import_isolation(self):
        """
        Verify in a fresh Python process that importing src.resolver does NOT
        import heavy modules: sherpa_onnx, numpy, src.asr, src.media, or src.model_manager.
        """
        check_code = (
            "import sys; "
            "from src.resolver import resolve_url; "
            "heavy_mods = ['sherpa_onnx', 'numpy', 'src.asr', 'src.media', 'src.model_manager']; "
            "loaded = [m for m in heavy_mods if m in sys.modules]; "
            "assert not loaded, f'Heavy modules unexpectedly loaded: {loaded}'; "
            "print('ISOLATION_OK')"
        )
        proc = subprocess.run(
            [sys.executable, "-c", check_code],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, f"Import isolation check failed: {proc.stderr}")
        self.assertIn("ISOLATION_OK", proc.stdout)

    def test_resolve_youtube_metadata_lightweight(self):
        """Verify YouTube metadata resolution through lightweight boundary without synthetic fallbacks."""
        mock_ytdlp_data = {
            "id": "dQw4w9WgXcQ",
            "title": "Rick Astley - Never Gonna Give You Up",
            "description": "The official video...",
            "uploader": "RickAstleyVEVO",
            "upload_date": "20091025",
            "duration": 213,
            "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
            "view_count": 1500000000,
            "like_count": 16000000,
            "comment_count": 2000000,
        }
        with patch("src.adapters.youtube.fetch_metadata", return_value=mock_ytdlp_data):
            meta = resolve_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            self.assertEqual(meta.source_type, "youtube")
            self.assertEqual(meta.source_id, "dQw4w9WgXcQ")
            self.assertEqual(meta.title, "Rick Astley - Never Gonna Give You Up")
            self.assertEqual(meta.creator, "RickAstleyVEVO")
            self.assertEqual(meta.published_at, "2009-10-25")
            self.assertEqual(meta.duration_seconds, 213)

            # Contract conversion
            v1 = ContentMetadataV1.from_content_metadata(meta)
            self.assertEqual(v1.schema_version, 1)
            self.assertEqual(v1.title, "Rick Astley - Never Gonna Give You Up")

    def test_resolve_bilibili_metadata_lightweight(self):
        """Verify Bilibili metadata resolution through lightweight boundary."""
        mock_ytdlp_data = {
            "id": "BV1xx411c7mD",
            "title": "B站高质量视频",
            "description": "视频简介内容",
            "uploader": "UP主昵称",
            "upload_date": "20230501",
            "duration": 180,
            "thumbnail": "https://i0.hdslb.com/bfs/archive/pic.jpg",
            "view_count": 50000,
        }
        with patch("src.adapters.bilibili.fetch_metadata", return_value=mock_ytdlp_data):
            meta = resolve_url("https://www.bilibili.com/video/BV1xx411c7mD")
            self.assertEqual(meta.source_type, "bilibili")
            self.assertEqual(meta.source_id, "BV1xx411c7mD")
            self.assertEqual(meta.title, "B站高质量视频")
            self.assertEqual(meta.creator, "UP主昵称")

            v1 = ContentMetadataV1.from_content_metadata(meta)
            self.assertEqual(v1.schema_version, 1)
            self.assertIsNone(v1.like_count)  # Unknown is real null

    def test_resolve_weixin_metadata_lightweight(self):
        """Verify WeChat Channels metadata resolution through lightweight boundary."""
        mock_api_resp = {
            "errCode": 0,
            "data": {
                "authorInfo": {"nickname": "玩娱少女", "headImgUrl": "https://wx.qlogo.cn/avatar.jpg"},
                "feedInfo": {
                    "description": "鹦鹉文案第一行\n第二行介绍",
                    "createtime": 1725567000,
                    "coverUrl": "https://finder.video.qq.com/cover.jpg",
                    "likeCountFmt": "9071",
                    "commentCountFmt": "732",
                    "favCountFmt": "1.4万",
                    "forwardCountFmt": "1.9万",
                },
                "sceneInfo": {"dynamicExportId": "export/12345"},
            },
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_api_resp
        mock_resp.raise_for_status.return_value = None

        with patch("httpx.Client.post", return_value=mock_resp):
            meta = resolve_url("https://weixin.qq.com/sph/AF17JEGHVd")
            self.assertEqual(meta.source_type, "weixin")
            self.assertEqual(meta.source_id, "AF17JEGHVd")
            self.assertEqual(meta.title, "鹦鹉文案第一行")
            self.assertEqual(meta.creator, "玩娱少女")
            self.assertEqual(meta.like_count, "9071")

            v1 = ContentMetadataV1.from_content_metadata(meta)
            self.assertEqual(v1.schema_version, 1)
            self.assertIsNone(v1.duration_seconds)

    def test_no_synthetic_fallback_titles(self):
        """Verify unavailable metadata fields strictly resolve to None (JSON null)."""
        # YouTube with no title
        with patch("src.adapters.youtube.fetch_metadata", return_value={"id": "xyz"}):
            meta_yt = resolve_url("https://www.youtube.com/watch?v=xyz")
            self.assertIsNone(meta_yt.title)
            v1 = ContentMetadataV1.from_content_metadata(meta_yt)
            self.assertIsNone(v1.title)
            self.assertIsNone(v1.to_dict()["title"])

        # Bilibili with no title
        with patch("src.adapters.bilibili.fetch_metadata", return_value={"id": "BV123"}):
            meta_bili = resolve_url("https://www.bilibili.com/video/BV123")
            self.assertIsNone(meta_bili.title)

        # Weixin with empty description
        mock_api_empty_desc = {
            "errCode": 0,
            "data": {
                "authorInfo": {"nickname": "测试作者"},
                "feedInfo": {"description": ""},
            },
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_api_empty_desc
        with patch("httpx.Client.post", return_value=mock_resp):
            meta_wx = resolve_url("https://weixin.qq.com/sph/no_title")
            self.assertIsNone(meta_wx.title)

    def test_unsupported_url_raises_typed_error(self):
        """Verify unsupported URL raises UnsupportedURLError (both ResolveError and ValueError)."""
        with self.assertRaises(UnsupportedURLError) as ctx:
            resolve_url("https://tiktok.com/@user/video/123")
        self.assertIsInstance(ctx.exception, ResolveError)
        self.assertIsInstance(ctx.exception, ValueError)

    def test_deterministic_resolve_failure_raises_typed_resolve_error(self):
        """Verify deterministic API errors raise ResolveError and do not fabricate data."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"errCode": -1001, "errMsg": "Feed does not exist"}
        with patch("httpx.Client.post", return_value=mock_resp):
            with self.assertRaises(ResolveError) as ctx:
                resolve_url("https://weixin.qq.com/sph/non_existent")
            self.assertIn("Feed does not exist", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
