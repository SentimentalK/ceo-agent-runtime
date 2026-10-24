"""
Unit tests for Markdown exporter and YAML Front Matter formatting.
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.models import ContentMetadata, ResolvedContent
from src.markdown import export_markdown, format_yaml_val, sanitize_filename


class TestMarkdownExporter(unittest.TestCase):
    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("Hello World!"), "Hello_World!")
        self.assertEqual(sanitize_filename("a/b\\c:d*e?f\"g<h>i|j"), "a_b_c_d_e_f_g_h_i_j")
        self.assertEqual(sanitize_filename("   "), "untitled")
        self.assertEqual(sanitize_filename(""), "untitled")

    def test_format_yaml_val(self):
        self.assertEqual(format_yaml_val(None), "null")
        self.assertEqual(format_yaml_val(123), "123")
        self.assertEqual(format_yaml_val(12.34), "12.34")
        self.assertEqual(format_yaml_val(True), "true")
        self.assertEqual(format_yaml_val(False), "false")
        self.assertEqual(format_yaml_val('hello "world"'), '"hello \\"world\\""')

    def test_export_markdown_with_transcript(self):
        meta = ContentMetadata(
            source_type="youtube",
            source_url="https://www.youtube.com/watch?v=123",
            source_id="123",
            title="Sample Video",
            creator="Tester",
            published_at="2026-01-01",
            duration_seconds=120,
            description="A sample test description.",
        )
        resolved = ResolvedContent(
            metadata=meta,
            transcript="This is paragraph one.\n\nThis is paragraph two.",
            transcript_status="available",
            transcript_method="subtitles",
        )

        md = export_markdown(resolved)
        self.assertTrue(md.startswith("---\n"))
        self.assertIn("source_type: \"youtube\"", md)
        self.assertIn("source_id: \"123\"", md)
        self.assertIn("transcript_status: \"available\"", md)
        self.assertIn("transcript_method: \"subtitles\"", md)
        self.assertIn("# Sample Video", md)
        self.assertIn("## Description", md)
        self.assertIn("A sample test description.", md)
        self.assertIn("## Transcript", md)
        self.assertIn("This is paragraph one.", md)

    def test_export_markdown_without_transcript(self):
        meta = ContentMetadata(
            source_type="weixin",
            source_url="https://weixin.qq.com/sph/AF17JEGHVd",
            source_id="AF17JEGHVd",
            title="WeChat Short Video",
            creator="AuthorName",
            published_at="2026-09-05",
            description="WeChat video description.",
        )
        resolved = ResolvedContent(
            metadata=meta,
            transcript=None,
            transcript_status="unavailable",
            transcript_method=None,
        )

        md = export_markdown(resolved)
        self.assertIn("source_type: \"weixin\"", md)
        self.assertIn("transcript_status: \"unavailable\"", md)
        self.assertIn("transcript_method: null", md)
        self.assertIn("## Transcript", md)
        self.assertIn("Transcript unavailable.", md)
        self.assertIn("WeChat video description.", md)


if __name__ == "__main__":
    unittest.main()
