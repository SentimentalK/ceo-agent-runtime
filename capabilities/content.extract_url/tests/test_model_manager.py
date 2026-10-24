"""
Unit tests for ModelManager (path resolution, checksum verification, safe tar extraction, readiness).
"""

import hashlib
import io
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.model_manager import (
    FIRERED_EXPECTED_FILES,
    FIRERED_TAR_SHA256,
    SILERO_VAD_SHA256,
    _safe_extract_tar,
    compute_sha256,
    ensure_all_asr_models,
    get_firered_dir,
    get_models_dir,
    get_project_root,
    get_tmp_dir,
    get_vad_path,
    is_firered_ready,
    is_vad_ready,
)


class TestModelManager(unittest.TestCase):
    def test_paths_are_project_local(self):
        root = get_project_root()
        self.assertTrue(root.is_dir())
        self.assertEqual(get_models_dir(), root / ".models")
        self.assertEqual(get_tmp_dir(), root / ".tmp")
        self.assertTrue(str(get_firered_dir()).startswith(str(root / ".models")))
        self.assertEqual(get_vad_path(), root / ".models" / "silero_vad.onnx")

    def test_sha256_computation(self):
        with tempfile.TemporaryDirectory() as td:
            sample_file = Path(td) / "test.bin"
            content = b"hello sherpa-onnx firered-asr2"
            sample_file.write_bytes(content)
            expected = hashlib.sha256(content).hexdigest()
            self.assertEqual(compute_sha256(sample_file), expected)

    def test_firered_readiness_checks(self):
        with tempfile.TemporaryDirectory() as td:
            mock_model_dir = Path(td) / "firered"
            mock_model_dir.mkdir()

            with patch("src.model_manager.get_firered_dir", return_value=mock_model_dir):
                self.assertFalse(is_firered_ready())

                # Create partial files
                (mock_model_dir / "encoder.int8.onnx").write_bytes(b"data")
                self.assertFalse(is_firered_ready())

                # Create all expected files
                for fname in FIRERED_EXPECTED_FILES:
                    (mock_model_dir / fname).write_bytes(b"data")

                self.assertTrue(is_firered_ready())

    def test_vad_readiness_checks(self):
        with tempfile.TemporaryDirectory() as td:
            mock_vad_path = Path(td) / "silero_vad.onnx"
            with patch("src.model_manager.get_vad_path", return_value=mock_vad_path):
                self.assertFalse(is_vad_ready())
                mock_vad_path.write_bytes(b"vad_weights")
                self.assertTrue(is_vad_ready())

    def test_safe_tar_extraction_prevents_path_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            tar_path = Path(td) / "malicious.tar"
            extract_dir = Path(td) / "extract"

            # Create an in-memory tar archive with a path traversal attempt
            tar_buffer = io.BytesIO()
            with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
                ti = tarfile.TarInfo(name="../evil.txt")
                data = b"malicious payload"
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))

            tar_path.write_bytes(tar_buffer.getvalue())

            with self.assertRaises(Exception):
                _safe_extract_tar(tar_path, extract_dir)

    def test_ensure_all_asr_models_returns_paths_when_ready(self):
        with patch("src.model_manager.is_firered_ready", return_value=True), \
             patch("src.model_manager.is_vad_ready", return_value=True):
            models = ensure_all_asr_models()
            self.assertIn("encoder", models)
            self.assertIn("decoder", models)
            self.assertIn("tokens", models)
            self.assertIn("vad_model", models)


if __name__ == "__main__":
    unittest.main()
