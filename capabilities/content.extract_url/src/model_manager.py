"""
Model Manager for FireRedASR2-AED and Silero VAD offline models.
Handles checksum verification, safe tar extraction, staging verification,
and atomic activation under the capability-local .models/.
"""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import uuid
from typing import Dict, List, Optional

# Pinned releases and constants
FIRERED_MODEL_DIR_NAME = "firered-asr2-aed-int8-2026-02-26"
FIRERED_TAR_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-fire-red-asr2-zh_en-int8-2026-02-26.tar.bz2"
)
FIRERED_TAR_SHA256 = (
    "43015b3f1643a5688b4821e8ed323473d38b798c4ec291471fe00df1bcfc4f1c"
)
FIRERED_EXPECTED_FILES = [
    "encoder.int8.onnx",
    "decoder.int8.onnx",
    "tokens.txt",
]

SILERO_VAD_FILENAME = "silero_vad.onnx"
SILERO_VAD_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
)
SILERO_VAD_SHA256 = (
    "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6"
)


def get_project_root() -> Path:
    """Return the absolute Path of subtitle-extractor project root."""
    return Path(__file__).resolve().parent.parent


def get_models_dir() -> Path:
    """Return the Path to project-local .models/ directory."""
    d = get_project_root() / ".models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_tmp_dir() -> Path:
    """Return the Path to project-local .tmp/ directory."""
    d = get_project_root() / ".tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_firered_dir() -> Path:
    """Return the Path to the active FireRedASR2 model directory."""
    return get_models_dir() / FIRERED_MODEL_DIR_NAME


def get_vad_path() -> Path:
    """Return the Path to silero_vad.onnx."""
    return get_models_dir() / SILERO_VAD_FILENAME


def compute_sha256(filepath: Path) -> str:
    """Compute SHA256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def is_firered_ready() -> bool:
    """Check if all expected FireRedASR2 model files are present and non-empty."""
    model_dir = get_firered_dir()
    if not model_dir.is_dir():
        return False
    for filename in FIRERED_EXPECTED_FILES:
        target = model_dir / filename
        if not target.is_file() or target.stat().st_size == 0:
            return False
    return True


def is_vad_ready() -> bool:
    """Check if Silero VAD model is present and non-empty."""
    vad_file = get_vad_path()
    return vad_file.is_file() and vad_file.stat().st_size > 0


def _download_file(url: str, dest_path: Path, expected_sha256: Optional[str] = None) -> None:
    """Download file with progress display and optional checksum verification."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_download = dest_path.with_suffix(dest_path.suffix + f".download_{uuid.uuid4().hex[:8]}")

    print(f"▶ 正在下载: {url}")
    print(f"  目标路径: {dest_path}")

    req = urllib.request.Request(url, headers={"User-Agent": "subtitle-extractor/1.0"})
    with urllib.request.urlopen(req) as response, open(temp_download, "wb") as out_file:
        total_size = int(response.headers.get("Content-Length", 0))
        downloaded = 0
        last_percent = -1

        while True:
            buffer = response.read(1024 * 1024)
            if not buffer:
                break
            downloaded += len(buffer)
            out_file.write(buffer)

            if total_size > 0:
                percent = int(downloaded * 100 / total_size)
                if percent != last_percent and percent % 10 == 0:
                    last_percent = percent
                    mb_downloaded = downloaded / (1024 * 1024)
                    mb_total = total_size / (1024 * 1024)
                    print(f"  进度: {percent}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)")

    if expected_sha256:
        print("▶ 正在校验 SHA256 校验和...")
        actual_sha256 = compute_sha256(temp_download)
        if actual_sha256.lower() != expected_sha256.lower():
            temp_download.unlink(missing_ok=True)
            raise ValueError(
                f"Checksum mismatch for {dest_path.name}!\n"
                f"Expected: {expected_sha256}\n"
                f"Actual:   {actual_sha256}"
            )
        print("✔ SHA256 校验通过！")

    temp_download.replace(dest_path)


def _safe_extract_tar(tar_path: Path, extract_dir: Path) -> None:
    """Safely extract tar archive preventing directory traversal."""
    extract_dir.mkdir(parents=True, exist_ok=True)
    extract_root = extract_dir.resolve()

    tar_bin = shutil.which("tar")
    if tar_bin:
        res = subprocess.run(
            [tar_bin, "-xjf", str(tar_path), "-C", str(extract_dir)],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            return

    with tarfile.open(tar_path, "r:*") as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(extract_dir, filter="data")
        else:
            for member in tar.getmembers():
                target_path = (extract_dir / member.name).resolve()
                if not target_path.is_relative_to(extract_root):
                    raise SecurityError(f"Attempted Path Traversal in tar file: {member.name}")
            tar.extractall(extract_dir)


def ensure_vad_model() -> Path:
    """Ensure Silero VAD model is downloaded and verified."""
    vad_file = get_vad_path()
    if is_vad_ready():
        return vad_file

    print("▶ 未检测到 Silero VAD 模型，正在准备...")
    download_dir = get_tmp_dir() / "downloads"
    tmp_vad = download_dir / SILERO_VAD_FILENAME
    if not tmp_vad.exists() or compute_sha256(tmp_vad).lower() != SILERO_VAD_SHA256.lower():
        _download_file(SILERO_VAD_URL, tmp_vad, expected_sha256=SILERO_VAD_SHA256)

    # Atomic move to .models/
    shutil.move(str(tmp_vad), str(vad_file))
    print(f"✔ Silero VAD 模型已就绪: {vad_file}")
    return vad_file


def ensure_firered_model() -> Dict[str, str]:
    """
    Ensure FireRedASR2-AED INT8 model is downloaded, verified, and ready.
    Uses safe tar extraction, staging verification, and atomic directory rename.
    """
    if is_firered_ready():
        model_dir = get_firered_dir()
        return {
            "encoder": str(model_dir / "encoder.int8.onnx"),
            "decoder": str(model_dir / "decoder.int8.onnx"),
            "tokens": str(model_dir / "tokens.txt"),
        }

    print("▶ 未检测到 FireRedASR2-AED 离线模型，准备下载并解压 (~838.6 MB 压缩包，解压后约 1.2 GB)...")
    download_dir = get_tmp_dir() / "downloads"
    tar_path = download_dir / "firered2.tar.bz2"

    if not tar_path.exists() or compute_sha256(tar_path).lower() != FIRERED_TAR_SHA256.lower():
        _download_file(FIRERED_TAR_URL, tar_path, expected_sha256=FIRERED_TAR_SHA256)

    staging_dir = get_models_dir() / f".staging_{uuid.uuid4().hex[:8]}"
    try:
        print(f"▶ 正在安全解压模型到暂存区: {staging_dir.name}...")
        _safe_extract_tar(tar_path, staging_dir)

        # Locate the directory containing encoder.int8.onnx, decoder.int8.onnx, tokens.txt
        found_dir: Optional[Path] = None
        for root, _, files in os.walk(staging_dir):
            if all(f in files for f in FIRERED_EXPECTED_FILES):
                found_dir = Path(root)
                break

        if not found_dir:
            raise RuntimeError(
                f"Extracted archive does not contain all expected files: {FIRERED_EXPECTED_FILES}"
            )

        # Verify non-empty files
        for f in FIRERED_EXPECTED_FILES:
            target_f = found_dir / f
            if not target_f.is_file() or target_f.stat().st_size == 0:
                raise RuntimeError(f"Extracted file {f} is missing or empty.")

        # Atomic rename to final destination
        final_dir = get_firered_dir()
        if final_dir.exists():
            shutil.rmtree(final_dir)

        if found_dir == staging_dir:
            staging_dir.rename(final_dir)
        else:
            # Move found inner directory to final destination
            shutil.move(str(found_dir), str(final_dir))
            shutil.rmtree(staging_dir, ignore_errors=True)

        print(f"✔ FireRedASR2-AED 模型解压并校验完成: {final_dir}")
    finally:
        # Clean up downloaded tar archive and staging if failed
        if tar_path.exists():
            tar_path.unlink(missing_ok=True)
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

    return {
        "encoder": str(get_firered_dir() / "encoder.int8.onnx"),
        "decoder": str(get_firered_dir() / "decoder.int8.onnx"),
        "tokens": str(get_firered_dir() / "tokens.txt"),
    }


def ensure_all_asr_models() -> Dict[str, str]:
    """Ensure both FireRedASR2 and Silero VAD models are ready."""
    vad_path = ensure_vad_model()
    models = ensure_firered_model()
    models["vad_model"] = str(vad_path)
    return models
