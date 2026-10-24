"""Markdown formatter for PPTX content."""

from typing import List, Dict
import os
from collections import Counter
import re

def clean_repeated_footers(slides_content_blocks: List[List[str]], threshold_ratio: float = 0.65) -> List[List[str]]:
    """
    Remove headers/footers/page numbers that repeat identically across > threshold_ratio of slides.
    """
    total_slides = len(slides_content_blocks)
    if total_slides < 3:
        return slides_content_blocks

    block_counts = Counter()
    for blocks in slides_content_blocks:
        unique_in_slide = set(b.strip() for b in blocks if b.strip())
        for b in unique_in_slide:
            # Don't count very long blocks (likely not footers)
            if len(b) < 120:
                block_counts[b] += 1

    common_footers = set()
    for block, count in block_counts.items():
        if count / total_slides >= threshold_ratio:
            common_footers.add(block)

    cleaned_slides = []
    slide_num_pattern = re.compile(r'^\d+$|^\d+\s*/\s*\d+$')
    for blocks in slides_content_blocks:
        filtered = []
        for b in blocks:
            text = b.strip()
            # Filter common footers and bare slide number counters
            if text in common_footers or slide_num_pattern.match(text):
                continue
            filtered.append(b)
        cleaned_slides.append(filtered)

    return cleaned_slides

def generate_markdown(
    filename: str,
    total_slides: int,
    slides_blocks: List[List[str]],
    slides_notes: List[str]
) -> str:
    """Generate final formatted Markdown output with frontmatter and slide blocks."""
    lines = []
    
    # Frontmatter
    lines.append("---")
    lines.append(f"source: {os.path.basename(filename)}")
    lines.append(f"slides: {total_slides}")
    lines.append("---\n")

    for idx, (blocks, notes) in enumerate(zip(slides_blocks, slides_notes), start=1):
        lines.append(f"# Slide {idx}\n")
        
        if blocks:
            for b in blocks:
                lines.append(b)
                lines.append("")  # Empty line between blocks
        else:
            lines.append("*(Empty slide / No text)*\n")

        if notes and notes.strip():
            lines.append("### Notes\n")
            lines.append(notes.strip())
            lines.append("")

        if idx < total_slides:
            lines.append("---\n")

    return "\n".join(lines).strip() + "\n"
