"""OCR Engine wrapper using RapidOCR (lightweight, highly accurate ONNX-based PaddleOCR fork)."""

import io
import logging
from typing import List, Dict, Any, Optional
from PIL import Image

logger = logging.getLogger(__name__)

class OCREngine:
    def __init__(self, confidence_threshold: float = 0.55):
        self.confidence_threshold = confidence_threshold
        self._ocr = None

    def _get_ocr(self):
        if self._ocr is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                self._ocr = RapidOCR()
            except Exception as e:
                logger.error(f"Failed to initialize RapidOCR: {e}")
                raise
        return self._ocr

    def extract_text_from_image_bytes(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Extract text from raw image bytes.
        Returns a list of items: [{'text': str, 'confidence': float, 'bbox': list, 'y': float, 'x': float}]
        Sorted by vertical (top-to-bottom), then horizontal (left-to-right).
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))
            # Convert RGBA/P to RGB if needed
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            
            ocr = self._get_ocr()
            results, _ = ocr(image)
            
            if not results:
                return []

            extracted = []
            for item in results:
                # item format: [box, text, score]
                # box is 4 points: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
                box, text, score = item[0], item[1], float(item[2])
                
                if score < self.confidence_threshold:
                    continue

                text = text.strip()
                if not text:
                    continue
                
                # Simple noise filter for lonely punctuation
                if len(text) == 1 and text in "|-._~`^:;,/\\":
                    continue

                # Calculate approximate top-left (y, x) for reading order
                top_y = min(pt[1] for pt in box)
                left_x = min(pt[0] for pt in box)

                extracted.append({
                    "text": text,
                    "confidence": score,
                    "bbox": box,
                    "y": top_y,
                    "x": left_x
                })

            # Sort by top-to-bottom, then left-to-right
            extracted.sort(key=lambda item: (item["y"], item["x"]))
            return extracted

        except Exception as e:
            logger.warning(f"OCR processing failed for image: {e}")
            return []
