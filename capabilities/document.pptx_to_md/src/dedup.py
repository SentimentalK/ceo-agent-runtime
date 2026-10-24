"""Deduplication and text normalization utilities."""

import re
from typing import List, Set

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

def normalize_text(text: str) -> str:
    """Normalize text for deduplication comparison."""
    # Lowercase, replace multiple whitespaces with single space, strip
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

class SlideDeduplicator:
    def __init__(self, fuzzy_threshold: float = 90.0, enabled: bool = True):
        self.fuzzy_threshold = fuzzy_threshold
        self.enabled = enabled
        self.seen_normalized: Set[str] = set()

    def is_duplicate(self, text: str) -> bool:
        if not self.enabled:
            return False

        norm = normalize_text(text)
        if not norm:
            return True  # Empty text is treated as duplicate / ignore

        # Exact normalized match
        if norm in self.seen_normalized:
            return True

        # Fuzzy matching against already seen strings (if length is substantial enough)
        if HAS_RAPIDFUZZ and len(norm) > 5:
            for seen in self.seen_normalized:
                if len(seen) > 5 and abs(len(seen) - len(norm)) / max(len(seen), len(norm)) < 0.3:
                    ratio = fuzz.ratio(norm, seen)
                    if ratio >= self.fuzzy_threshold:
                        return True

        self.seen_normalized.add(norm)
        return False

    def add(self, text: str):
        norm = normalize_text(text)
        if norm:
            self.seen_normalized.add(norm)

    def filter_unique(self, text_list: List[str]) -> List[str]:
        """Filter out duplicates in a sequence of texts."""
        unique_texts = []
        for t in text_list:
            if not self.is_duplicate(t):
                unique_texts.append(t)
        return unique_texts
