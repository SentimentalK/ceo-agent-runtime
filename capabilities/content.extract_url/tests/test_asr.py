"""
Unit tests for FireRedASR2-AED ASR module (audio extraction, PCM loading, transcription workflow).
"""

import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import wave

import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.asr import (
    get_ffmpeg_bin,
    normalize_audio_for_asr,
    read_wave_pcm,
    segment_audio_with_vad,
    transcribe_media_file,
)


class TestASR(unittest.TestCase):
    def test_get_ffmpeg_bin(self):
        bin_path = get_ffmpeg_bin()
        self.assertTrue(isinstance(bin_path, str))
        self.assertTrue(len(bin_path) > 0)

    def test_normalize_audio_for_asr_command(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            normalize_audio_for_asr("/path/to/in.mp4", "/path/to/out.wav")

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            self.assertIn("-i", args)
            self.assertIn("/path/to/in.mp4", args)
            self.assertIn("-ar", args)
            self.assertIn("16000", args)
            self.assertIn("-ac", args)
            self.assertIn("1", args)
            self.assertIn("pcm_s16le", args)
            self.assertIn("/path/to/out.wav", args)

    def test_read_wave_pcm(self):
        with tempfile.TemporaryDirectory() as td:
            wav_path = os.path.join(td, "test_16k_mono.wav")
            sample_rate = 16000
            # Generate 1 second of test samples (e.g. 0.5 amplitude sine or int16)
            int16_samples = [int(16384 * np.sin(2 * np.pi * 440 * t / sample_rate)) for t in range(sample_rate)]

            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                raw_bytes = struct.pack(f"<{len(int16_samples)}h", *int16_samples)
                wf.writeframes(raw_bytes)

            samples, sr = read_wave_pcm(wav_path)
            self.assertEqual(sr, 16000)
            self.assertEqual(len(samples), 16000)
            self.assertAlmostEqual(samples[0], 0.0, places=3)
            # Max amplitude should be ~0.5
            self.assertAlmostEqual(float(np.max(samples)), 0.5, places=2)

    def test_transcribe_media_file_workflow(self):
        dummy_models = {
            "encoder": "/mock/encoder.int8.onnx",
            "decoder": "/mock/decoder.int8.onnx",
            "tokens": "/mock/tokens.txt",
            "vad_model": "/mock/silero_vad.onnx",
        }

        mock_stream = MagicMock()
        mock_stream.result.text = "今天天气真好"

        mock_recognizer = MagicMock()
        mock_recognizer.create_stream.return_value = mock_stream

        with patch("src.asr.ensure_all_asr_models", return_value=dummy_models), \
             patch("src.asr.normalize_audio_for_asr") as mock_norm, \
             patch("src.asr.read_wave_pcm", return_value=(np.zeros(16000, dtype=np.float32), 16000)), \
             patch("src.asr.segment_audio_with_vad", return_value=[np.zeros(16000, dtype=np.float32)]), \
             patch("sherpa_onnx.OfflineRecognizer.from_fire_red_asr", return_value=mock_recognizer):

            text = transcribe_media_file("/dummy/path/input.mp4")
            self.assertEqual(text, "今天天气真好")
            mock_norm.assert_called_once()
            mock_recognizer.decode_stream.assert_called_once()


if __name__ == "__main__":
    unittest.main()
