#!/usr/bin/env python3
"""
Explicit ASR Model Preparation Script.
Downloads and verifies FireRedASR2-AED INT8 and Silero VAD models ahead of time.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.model_manager import ensure_all_asr_models, is_firered_ready, is_vad_ready


def main():
    print("=== FireRedASR2-AED & Silero VAD Model Pre-downloader ===")
    firered_ready = is_firered_ready()
    vad_ready = is_vad_ready()

    if firered_ready and vad_ready:
        print("✔ All models are already downloaded, verified, and ready.")
        models = ensure_all_asr_models()
        print(f"FireRedASR2 encoder: {models['encoder']}")
        print(f"FireRedASR2 decoder: {models['decoder']}")
        print(f"FireRedASR2 tokens:  {models['tokens']}")
        print(f"Silero VAD model:    {models['vad_model']}")
        return

    print("▶ Models missing or incomplete. Starting download and verification...")
    models = ensure_all_asr_models()
    print("✔ Model preparation completed successfully!")
    print(f"FireRedASR2 encoder: {models['encoder']}")
    print(f"FireRedASR2 decoder: {models['decoder']}")
    print(f"FireRedASR2 tokens:  {models['tokens']}")
    print(f"Silero VAD model:    {models['vad_model']}")


if __name__ == "__main__":
    main()
