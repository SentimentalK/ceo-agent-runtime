"""Content-grade sufficiency and no_speech contracts."""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.content_grade import is_content_grade_text, is_no_speech_transcript


CONTENT_GRADE_WECHAT = (
    "前端的下一个变化，可能不是新的 UI 框架，而是一份 AI 能读懂的设计说明。"
    "VoltAgent/awesome-design-md 把 Stripe、Linear、Figma、Ferrari 等品牌风格整理成 DESIGN.md，"
    "放进项目根目录后，AI 就能按配色、字体、间距和组件规则生成更一致的界面。"
    "GitHub 页面显示它已经冲到 7.7 万+ Star、9.4K Fork，"
    "说明「让 AI 按设计系统做 UI」正在成为新的 Vibe Coding 工作流。\n"
    "#AI编程 #VibeCoding #前端开发 #DESIGNmd #GitHub开源"
)

MARKETING_CAPTION = "AI 太强了！赶紧收藏\n#AI #程序员 #效率工具"


class TestContentGrade(unittest.TestCase):
    def test_wechat_article_description_is_content_grade(self):
        self.assertTrue(is_content_grade_text(CONTENT_GRADE_WECHAT))

    def test_marketing_caption_is_not_content_grade(self):
        self.assertFalse(is_content_grade_text(MARKETING_CAPTION))

    def test_hashtag_only_is_not_content_grade(self):
        self.assertFalse(is_content_grade_text("#AI #程序员 #效率工具 #收藏"))

    def test_single_sentence_under_threshold_is_not_content_grade(self):
        self.assertFalse(is_content_grade_text("这是一句还算完整但不够长的说明文字。"))

    def test_url_heavy_text_is_not_content_grade(self):
        blob = (
            "看这里 https://example.com/a https://example.com/b "
            "https://example.com/c https://example.com/d 收藏一下。"
        )
        self.assertFalse(is_content_grade_text(blob))

    def test_empty_and_none_are_not_content_grade(self):
        self.assertFalse(is_content_grade_text(None))
        self.assertFalse(is_content_grade_text(""))
        self.assertFalse(is_content_grade_text("   "))


class TestNoSpeechTranscript(unittest.TestCase):
    def test_sil_token_is_no_speech(self):
        self.assertTrue(is_no_speech_transcript("<sil>"))
        self.assertTrue(is_no_speech_transcript("  <sil>  "))
        self.assertTrue(is_no_speech_transcript("<sil><sil>"))
        self.assertTrue(is_no_speech_transcript("<SIL>"))

    def test_empty_is_no_speech(self):
        self.assertTrue(is_no_speech_transcript(None))
        self.assertTrue(is_no_speech_transcript(""))
        self.assertTrue(is_no_speech_transcript("   "))

    def test_real_speech_is_not_no_speech(self):
        self.assertFalse(is_no_speech_transcript("语音识别转录文本"))
        self.assertFalse(is_no_speech_transcript("这里可以看到增长非常明显"))

    def test_speech_with_embedded_sil_is_still_speech(self):
        self.assertFalse(is_no_speech_transcript("开头 <sil> 后面还有人声"))


if __name__ == "__main__":
    unittest.main()
