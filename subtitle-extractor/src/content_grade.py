"""
Content-grade sufficiency and speech-signal contracts.

v1 is intentionally conservative:
- Description is content only when it looks like real prose, not a caption + hashtags.
- FireRed silence / special tokens are no_speech, never publishable content.
"""

from __future__ import annotations

import re
from typing import Optional

# FireRed / sherpa special tokens that must never become ManagedResource content.
_SPECIAL_TOKEN_RE = re.compile(
    r"</?(?:sil|unk|blank|s|noise|music|nsn|spk)>",
    re.IGNORECASE,
)

_HASHTAG_RE = re.compile(r"(?:(?<=^)|(?<=\s))#[^\s#]+")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
_WHITESPACE_RE = re.compile(r"\s+")

_MIN_NONE_HASHTAG_CHARS = 80
_MIN_SENTENCE_LIKE = 2
_MIN_SENTENCE_CHARS = 6
_MIN_CLEAN_RATIO = 0.5

# Short engagement bait that should not count as body text.
_BOILERPLATE_RE = re.compile(
    r"(赶紧收藏|一键三连|记得点赞|点赞关注|点击关注|关注我|转发给朋友|"
    r"评论区见|链接在评论|扫码观看|点击主页|"
    r"like and subscribe|follow for more)",
    re.IGNORECASE,
)


def _collapse_ws(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def strip_non_prose(text: str) -> str:
    """Remove hashtags, URLs, and common boilerplate; keep remaining prose."""
    cleaned = _HASHTAG_RE.sub(" ", text)
    cleaned = _URL_RE.sub(" ", cleaned)
    cleaned = _BOILERPLATE_RE.sub(" ", cleaned)
    return _collapse_ws(cleaned)


def sentence_like_segments(text: str) -> list[str]:
    parts = [_collapse_ws(p) for p in _SENTENCE_SPLIT_RE.split(text)]
    return [p for p in parts if len(p) >= _MIN_SENTENCE_CHARS]


def is_content_grade_text(text: Optional[str]) -> bool:
    """
    True when text is usable as extracted content.

    v1 gate (tune later from data):
    - non-hashtag/URL/boilerplate text >= 80 chars
    - remaining prose is not a minority leftover of tags/URLs
    - at least 2 sentence-like segments
    """
    if not text or not isinstance(text, str):
        return False

    raw = text.strip()
    if not raw:
        return False

    cleaned = strip_non_prose(raw)
    if len(cleaned) < _MIN_NONE_HASHTAG_CHARS:
        return False

    raw_compact_len = len(re.sub(r"\s+", "", raw))
    clean_compact_len = len(re.sub(r"\s+", "", cleaned))
    if raw_compact_len == 0 or clean_compact_len / raw_compact_len < _MIN_CLEAN_RATIO:
        return False

    if len(sentence_like_segments(cleaned)) < _MIN_SENTENCE_LIKE:
        return False

    return True


def is_no_speech_transcript(text: Optional[str]) -> bool:
    """
    True when ASR/native text is empty or only recognizer special tokens.

    `<sil>` belongs here. It must never enter the content domain.
    """
    if text is None or not isinstance(text, str):
        return True

    stripped = text.strip()
    if not stripped:
        return True

    without_tokens = _SPECIAL_TOKEN_RE.sub(" ", stripped)
    leftover = _collapse_ws(without_tokens)
    leftover = re.sub(r"[\\/|.·•\-_=+~`'\",:]+", "", leftover)
    return leftover == ""
