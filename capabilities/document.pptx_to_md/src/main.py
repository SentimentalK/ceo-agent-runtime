"""CLI entry point for pptx-to-md converter."""

import argparse
import sys
import os
import glob
import logging
from typing import Optional, List
from .converter import PPTXToMarkdownConverter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("pptx-to-md")

def process_file(converter: PPTXToMarkdownConverter, input_path: str, output_path: Optional[str] = None):
    if not os.path.exists(input_path):
        logger.error(f"File not found: {input_path}")
        return False

    if output_path is None:
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        parent_dir = os.path.dirname(input_path) or "."
        if parent_dir.endswith("input"):
            output_dir = os.path.join(parent_dir, "..", "output")
        else:
            output_dir = os.path.join(parent_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{base_name}.md")
    elif os.path.isdir(output_path):
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(output_path, f"{base_name}.md")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    logger.info(f"Processing: {input_path} -> {output_path}")
    try:
        md_content = converter.convert_file(input_path)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        logger.info(f"Successfully converted: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to convert {input_path}: {e}", exc_info=True)
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Convert .pptx presentation to pure clean Markdown with OCR and deduplication."
    )
    parser.add_argument("inputs", nargs="+", help="Path to .pptx file(s) or directory")
    parser.add_argument("-o", "--output", help="Output file path or directory", default=None)
    parser.add_argument("--no-ocr", action="store_true", help="Disable image OCR")
    parser.add_argument("--confidence", type=float, default=0.55, help="OCR confidence threshold (default: 0.55)")
    parser.add_argument("--no-dedup", action="store_true", help="Disable slide-level text deduplication")
    parser.add_argument("--keep-footers", action="store_true", help="Keep repeated headers/footers")

    args = parser.parse_args()

    converter = PPTXToMarkdownConverter(
        enable_ocr=not args.no_ocr,
        confidence_threshold=args.confidence,
        enable_dedup=not args.no_dedup,
        clean_footers=not args.keep_footers
    )

    all_files: List[str] = []
    for item in args.inputs:
        if os.path.isdir(item):
            found = glob.glob(os.path.join(item, "**/*.pptx"), recursive=True)
            all_files.extend(found)
        elif os.path.isfile(item) and item.lower().endswith(".pptx"):
            all_files.append(item)
        else:
            logger.warning(f"Skipping non-pptx or missing path: {item}")

    if not all_files:
        logger.warning("No valid .pptx files found to process.")
        sys.exit(1)

    logger.info(f"Total files to process: {len(all_files)}")
    failed = [f for f in all_files if not process_file(converter, f, args.output)]
    if failed:
        logger.error(f"{len(failed)} of {len(all_files)} files failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
