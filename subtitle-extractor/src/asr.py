"""
FireRedASR2-AED Automatic Speech Recognition Module.
Uses official sherpa-onnx runtime with Silero VAD for long-form speech segmentation.
Fully host-native, CPU-capable, zero Whisper dependencies.
"""

import glob
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple
import uuid
import wave

import numpy as np

try:
    from .model_manager import ensure_all_asr_models, get_tmp_dir
    from .ytdlp import build_base_ytdlp_cmd
except (ImportError, ValueError):
    from model_manager import ensure_all_asr_models, get_tmp_dir
    from ytdlp import build_base_ytdlp_cmd


def get_ffmpeg_bin() -> str:
    """Resolve ffmpeg binary from PATH or ~/.local/bin."""
    cmd = shutil.which("ffmpeg")
    if cmd:
        return cmd
    local_ffmpeg = Path.home() / ".local" / "bin" / "ffmpeg"
    if local_ffmpeg.is_file() and os.access(local_ffmpeg, os.X_OK):
        return str(local_ffmpeg)
    return "ffmpeg"


def download_media_for_asr(url: str, output_dir: str, prefix: str) -> Optional[str]:
    """Download best audio for ASR fallback using yt-dlp."""
    os.makedirs(output_dir, exist_ok=True)
    template = os.path.join(output_dir, f"{prefix}_media.%(ext)s")
    cmd = build_base_ytdlp_cmd(url, extra_args=["-f", "bestaudio/best", "-o", template])
    subprocess.run(cmd, capture_output=True, text=True)

    for f in glob.glob(os.path.join(output_dir, f"{prefix}_media.*")):
        return f
    return None


def normalize_audio_for_asr(input_media: str, output_wav: str) -> None:
    """
    Extract and normalize audio stream to 16kHz mono 16-bit PCM WAV using ffmpeg.
    """
    ffmpeg_bin = get_ffmpeg_bin()
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        input_media,
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        output_wav,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed (exit {res.returncode}): {res.stderr}")


def read_wave_pcm(wav_path: str) -> Tuple[np.ndarray, int]:
    """
    Read 16-bit mono PCM wave file using Python stdlib wave + numpy.
    Returns normalized float32 samples in range [-1.0, 1.0] and sample rate.
    """
    with wave.open(wav_path, "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        if channels != 1:
            raise ValueError(f"Expected mono WAV, got {channels} channels")
        if sampwidth != 2:
            raise ValueError(f"Expected 16-bit PCM (sampwidth=2), got {sampwidth}")

        n_frames = wf.getnframes()
        raw_bytes = wf.readframes(n_frames)
        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        return samples, sample_rate


def segment_audio_with_vad(
    samples: np.ndarray,
    sample_rate: int,
    vad_model_path: str,
) -> List[np.ndarray]:
    """
    Segment long audio into speech segments using sherpa_onnx.VoiceActivityDetector.
    Falls back to whole audio if no segments detected.
    """
    import sherpa_onnx

    vad_config = sherpa_onnx.VadModelConfig()
    vad_config.silero_vad.model = vad_model_path
    vad_config.sample_rate = sample_rate
    vad_config.silero_vad.threshold = 0.5
    vad_config.silero_vad.min_speech_duration = 0.25
    vad_config.silero_vad.min_silence_duration = 0.4

    vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=60)
    window_size = 512
    speech_segments: List[np.ndarray] = []

    for i in range(0, len(samples), window_size):
        chunk = samples[i : i + window_size]
        vad.accept_waveform(chunk)
        while not vad.empty():
            seg = vad.front
            seg_samples = np.array(seg.samples, dtype=np.float32)
            if len(seg_samples) > 0:
                speech_segments.append(seg_samples)
            vad.pop()

    vad.flush()
    while not vad.empty():
        seg = vad.front
        seg_samples = np.array(seg.samples, dtype=np.float32)
        if len(seg_samples) > 0:
            speech_segments.append(seg_samples)
        vad.pop()

    if not speech_segments and len(samples) > 0:
        # Fallback: treat whole audio as single segment if VAD detected nothing
        speech_segments.append(samples)

    return speech_segments


def transcribe_media_file(media_file: str) -> str:
    """
    Transcribe an audio or video file using local FireRedASR2-AED INT8 model
    and Silero VAD speech segmentation.
    Returns structured paragraphs of transcribed text.
    """
    try:
        import sherpa_onnx
    except ImportError:
        raise RuntimeError(
            "sherpa-onnx is not installed. Run `./setup.sh` or `pip install sherpa-onnx==1.13.7`."
        )

    # 1. Ensure models are ready
    model_paths = ensure_all_asr_models()

    # 2. Extract and normalize audio to 16kHz mono WAV in project .tmp/
    tmp_audio_dir = get_tmp_dir() / "audio_processing"
    tmp_audio_dir.mkdir(parents=True, exist_ok=True)
    temp_wav = tmp_audio_dir / f"norm_{uuid.uuid4().hex[:8]}.wav"

    try:
        normalize_audio_for_asr(media_file, str(temp_wav))
        samples, sample_rate = read_wave_pcm(str(temp_wav))

        if len(samples) == 0:
            return ""

        # 3. Speech segmentation using Silero VAD
        segments = segment_audio_with_vad(samples, sample_rate, model_paths["vad_model"])

        # 4. Initialize FireRedASR2-AED offline recognizer
        num_threads = min(8, os.cpu_count() or 4)
        recognizer = sherpa_onnx.OfflineRecognizer.from_fire_red_asr(
            encoder=model_paths["encoder"],
            decoder=model_paths["decoder"],
            tokens=model_paths["tokens"],
            num_threads=num_threads,
            provider="cpu",
        )

        recognized_sentences: List[str] = []
        for seg_samples in segments:
            stream = recognizer.create_stream()
            stream.accept_waveform(sample_rate, seg_samples)
            recognizer.decode_stream(stream)
            text = stream.result.text.strip()
            if text:
                recognized_sentences.append(text)

        # 5. Format sentences into clean paragraphs
        if not recognized_sentences:
            return ""

        paragraphs: List[str] = []
        chunk_size = 4  # 4 sentences per paragraph
        for i in range(0, len(recognized_sentences), chunk_size):
            paragraph = "".join(recognized_sentences[i : i + chunk_size])
            paragraphs.append(paragraph)

        return "\n\n".join(paragraphs)

    finally:
        if temp_wav.exists():
            try:
                temp_wav.unlink()
            except Exception:
                pass
