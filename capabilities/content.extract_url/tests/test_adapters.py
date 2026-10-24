"""
Unit tests for platform adapters and fixture parsing.
"""

import json
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.adapters.weixin import WeixinAdapter
from src.adapters.youtube import YouTubeAdapter
from src.adapters.bilibili import BilibiliAdapter


class TestAdapters(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = os.path.join(PROJECT_ROOT, "fixtures")

    def test_weixin_fixture_parsing(self):
        fixture_path = os.path.join(self.fixtures_dir, "weixin", "sample_feed_info.json")
        with open(fixture_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        url = "https://weixin.qq.com/sph/AF17JEGHVd"
        short_uri = "AF17JEGHVd"
        resolved = WeixinAdapter.parse_api_response(url, short_uri, raw_data)

        meta = resolved.metadata
        self.assertEqual(meta.source_type, "weixin")
        self.assertEqual(meta.source_id, "AF17JEGHVd")
        self.assertEqual(meta.creator, "玩娱少女")
        self.assertIn("鹦鹉:我也要这样婶儿的", meta.description)
        self.assertEqual(meta.published_at, "2026-09-05")
        self.assertEqual(meta.like_count, "8968")
        self.assertEqual(meta.comment_count, "730")
        self.assertIsNotNone(meta.thumbnail_url)
        self.assertEqual(meta.platform_metadata.get("fav_count"), "1.4万")
        self.assertEqual(meta.platform_metadata.get("forward_count"), "1.9万")
        self.assertEqual(meta.platform_metadata.get("dynamic_export_id"), "export/sample_export_id_12345")

        # Crucial semantic guarantee: transcript unavailable is success
        self.assertEqual(resolved.transcript_status, "unavailable")
        self.assertIsNone(resolved.transcript)
        self.assertIsNone(resolved.transcript_method)

    def test_weixin_missing_fields_resilience(self):
        # Even with totally empty data, adapter must not crash
        resolved = WeixinAdapter.parse_api_response("https://weixin.qq.com/sph/test", "test", {})
        meta = resolved.metadata
        self.assertEqual(meta.source_type, "weixin")
        self.assertEqual(meta.source_id, "test")
        self.assertIsNone(meta.creator)
        self.assertIsNone(meta.description)
        self.assertIsNone(meta.title)
        self.assertEqual(resolved.transcript_status, "unavailable")

    def test_weixin_short_uri_extraction(self):
        self.assertEqual(
            WeixinAdapter.extract_short_uri("https://weixin.qq.com/sph/AF17JEGHVd"),
            "AF17JEGHVd"
        )
        self.assertEqual(
            WeixinAdapter.extract_short_uri("https://weixin.qq.com/sph/AF17JEGHVd/"),
            "AF17JEGHVd"
        )
        self.assertEqual(
            WeixinAdapter.extract_short_uri("https://channels.weixin.qq.com/finder-preview/pages/sph?id=AF17JEGHVd&foo=bar"),
            "AF17JEGHVd"
        )


if __name__ == "__main__":
    unittest.main()
