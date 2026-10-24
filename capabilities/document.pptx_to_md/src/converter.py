"""Core converter pipeline combining parser, OCR, dedup, and formatter."""

import logging
from typing import Optional
from .pptx_reader import parse_pptx
from .ocr_engine import OCREngine
from .dedup import SlideDeduplicator
from .md_formatter import clean_repeated_footers, generate_markdown

logger = logging.getLogger(__name__)

class PPTXToMarkdownConverter:
    def __init__(
        self,
        enable_ocr: bool = True,
        confidence_threshold: float = 0.55,
        enable_dedup: bool = True,
        clean_footers: bool = True
    ):
        self.enable_ocr = enable_ocr
        self.enable_dedup = enable_dedup
        self.clean_footers = clean_footers
        self.ocr_engine = OCREngine(confidence_threshold=confidence_threshold) if enable_ocr else None

    def convert_file(self, pptx_path: str) -> str:
        """Convert a single PPTX file to Markdown string."""
        slides_data, total_slides = parse_pptx(pptx_path)
        all_slides_blocks = []
        all_slides_notes = []

        for slide in slides_data:
            slide_blocks = []
            deduplicator = SlideDeduplicator(enabled=self.enable_dedup)

            for elem in slide.elements:
                if elem.element_type in ("text", "table", "chart"):
                    if elem.content and not deduplicator.is_duplicate(elem.content):
                        slide_blocks.append(elem.content)

                elif elem.element_type == "image" and self.enable_ocr and self.ocr_engine:
                    if elem.image_bytes:
                        ocr_results = self.ocr_engine.extract_text_from_image_bytes(elem.image_bytes)
                        for item in ocr_results:
                            text = item["text"]
                            if not deduplicator.is_duplicate(text):
                                slide_blocks.append(text)

            all_slides_blocks.append(slide_blocks)
            all_slides_notes.append(slide.speaker_notes or "")

        if self.clean_footers:
            all_slides_blocks = clean_repeated_footers(all_slides_blocks)

        return generate_markdown(
            filename=pptx_path,
            total_slides=total_slides,
            slides_blocks=all_slides_blocks,
            slides_notes=all_slides_notes
        )
