"""
Unit tests for platform detection and routing.
"""

import unittest
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.adapters import (
    ADAPTERS,
    BilibiliAdapter,
    WeixinAdapter,
    YouTubeAdapter,
    get_adapter_for_url,
)


class TestPlatformDetection(unittest.TestCase):
    def test_youtube_detection(self):
        urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "http://youtube.com/embed/dQw4w9WgXcQ",
        ]
        for u in urls:
            self.assertTrue(YouTubeAdapter.can_handle(u), f"Failed for {u}")
            adapter = get_adapter_for_url(u)
            self.assertIsInstance(adapter, YouTubeAdapter)

    def test_bilibili_detection(self):
        urls = [
            "https://www.bilibili.com/video/BV1PT4y1n7JA",
            "http://b23.tv/BV1PT4y1n7JA",
            "https://www.bilibili.com/video/av123456",
        ]
        for u in urls:
            self.assertTrue(BilibiliAdapter.can_handle(u), f"Failed for {u}")
            adapter = get_adapter_for_url(u)
            self.assertIsInstance(adapter, BilibiliAdapter)

    def test_weixin_detection(self):
        urls = [
            "https://weixin.qq.com/sph/AF17JEGHVd",
            "https://weixin.qq.com/sph/AF17JEGHVd/",
            "https://channels.weixin.qq.com/finder-preview/pages/sph?id=AF17JEGHVd",
        ]
        for u in urls:
            self.assertTrue(WeixinAdapter.can_handle(u), f"Failed for {u}")
            adapter = get_adapter_for_url(u)
            self.assertIsInstance(adapter, WeixinAdapter)

    def test_unknown_detection(self):
        unknown_urls = [
            "https://example.com/video/123",
            "https://vimeo.com/76979871",
        ]
        for u in unknown_urls:
            with self.assertRaises(ValueError):
                get_adapter_for_url(u)


if __name__ == "__main__":
    unittest.main()
