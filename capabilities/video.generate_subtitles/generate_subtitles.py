#!/usr/bin/env python3
"""
Generate subtitles (.srt, .vtt) for a video using local FireRedASR2-AED + Silero VAD,
and embed soft subtitles into the MP4 container.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple

import numpy as np

# Reuse ASR implementation from content.extract_url
EXTRACTOR_SRC = Path(__file__).resolve().parent.parent / "content.extract_url" / "src"
sys.path.insert(0, str(EXTRACTOR_SRC))

from asr import create_fire_red_recognizer, get_ffmpeg_bin, normalize_audio_for_asr, read_wave_pcm
from model_manager import ensure_all_asr_models, get_tmp_dir


def format_srt_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours = millis // 3600000
    millis %= 3600000
    minutes = millis // 60000
    millis %= 60000
    secs = millis // 1000
    millis %= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_vtt_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours = millis // 3600000
    millis %= 3600000
    minutes = millis // 60000
    millis %= 60000
    secs = millis // 1000
    millis %= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def wrap_text_for_subtitle(text: str, max_line_len: int = 30) -> str:
    """Wraps text onto two lines if it's longer than max_line_len."""
    text = text.strip()
    if len(text) <= max_line_len:
        return text

    # Try finding punctuation or space near the middle
    mid = len(text) // 2
    best_split = -1
    best_dist = 999

    for i, char in enumerate(text):
        if char in " ，。！？；,!? ":
            dist = abs(i - mid)
            if dist < best_dist:
                best_dist = dist
                best_split = i

    if best_split > 0 and best_dist < max_line_len // 2:
        part1 = text[:best_split].strip()
        part2 = text[best_split:].strip(" ，。！？；,!? ")
        return f"{part1}\n{part2}"
    else:
        # Split in the middle
        return f"{text[:mid]}\n{text[mid:]}"


def extract_and_transcribe(
    media_path: str,
    min_silence_duration: float = 0.3,
    max_speech_duration: float = 6.0,
) -> List[Tuple[float, float, str]]:
    """
    Extracts audio, runs Silero VAD segmentation and FireRedASR2-AED recognition.
    Returns list of (start_sec, end_sec, text).
    """
    import sherpa_onnx

    model_paths = ensure_all_asr_models()

    tmp_dir = get_tmp_dir() / "subtitles_run"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    temp_wav = tmp_dir / f"audio_{os.getpid()}_{int(time.time())}.wav"

    try:
        print(f"▶ 正在从视频中提取 16kHz 单声道音频: {media_path}...", flush=True)
        normalize_audio_for_asr(str(media_path), str(temp_wav))
        samples, sample_rate = read_wave_pcm(str(temp_wav))
        total_audio_sec = len(samples) / sample_rate
        print(f"▶ 音频提取完成，时长: {total_audio_sec:.1f} 秒 ({total_audio_sec / 60:.1f} 分钟)", flush=True)

        if len(samples) == 0:
            return []

        # Configure Silero VAD
        vad_config = sherpa_onnx.VadModelConfig()
        vad_config.silero_vad.model = str(model_paths["vad_model"])
        vad_config.sample_rate = sample_rate
        vad_config.silero_vad.threshold = 0.5
        vad_config.silero_vad.min_speech_duration = 0.25
        vad_config.silero_vad.min_silence_duration = min_silence_duration
        vad_config.silero_vad.max_speech_duration = max_speech_duration
        vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=60)

        window_size = 512
        raw_segments: List[Tuple[int, np.ndarray]] = []

        print("▶ 正在进行语音活动检测 (Silero VAD 分段)...", flush=True)
        for i in range(0, len(samples), window_size):
            chunk = samples[i : i + window_size]
            vad.accept_waveform(chunk)
            while not vad.empty():
                seg = vad.front
                seg_samples = np.array(seg.samples, dtype=np.float32)
                if len(seg_samples) > 0:
                    raw_segments.append((seg.start, seg_samples))
                vad.pop()

        vad.flush()
        while not vad.empty():
            seg = vad.front
            seg_samples = np.array(seg.samples, dtype=np.float32)
            if len(seg_samples) > 0:
                raw_segments.append((seg.start, seg_samples))
            vad.pop()

        if not raw_segments and len(samples) > 0:
            raw_segments.append((0, samples))

        total_speech_sec = sum(len(s) for _, s in raw_segments) / sample_rate
        print(
            f"▶ VAD 检测出 {len(raw_segments)} 个语音片段 (总语音时长: {total_speech_sec:.1f} 秒)",
            flush=True,
        )

        # Initialize recognizer
        num_threads = min(8, os.cpu_count() or 4)
        recognizer = create_fire_red_recognizer(model_paths, num_threads)

        subtitles: List[Tuple[float, float, str]] = []
        t_start = time.time()

        print(f"▶ 开始识别转录 (FireRedASR2-AED)...", flush=True)
        for idx, (start_sample, seg_samples) in enumerate(raw_segments, 1):
            stream = recognizer.create_stream()
            stream.accept_waveform(sample_rate, seg_samples)
            recognizer.decode_stream(stream)
            text = stream.result.text.strip()

            if text:
                start_sec = start_sample / sample_rate
                end_sec = (start_sample + len(seg_samples)) / sample_rate
                subtitles.append((start_sec, end_sec, text))

            if idx % 20 == 0 or idx == len(raw_segments):
                elapsed = time.time() - t_start
                percent = (idx / len(raw_segments)) * 100
                print(
                    f"▶ 转录进度: {idx}/{len(raw_segments)} ({percent:.1f}%) | 已耗时 {elapsed:.1f}s",
                    flush=True,
                )

        print(f"▶ 语音识别完成，共生成 {len(subtitles)} 条有效字幕！", flush=True)
        return subtitles

    finally:
        if temp_wav.exists():
            try:
                temp_wav.unlink()
            except Exception:
                pass


def save_srt(subtitles: List[Tuple[float, float, str]], output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        for idx, (start, end, text) in enumerate(subtitles, 1):
            cue_text = wrap_text_for_subtitle(text)
            f.write(f"{idx}\n")
            f.write(f"{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}\n")
            f.write(f"{cue_text}\n\n")


def save_vtt(subtitles: List[Tuple[float, float, str]], output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for idx, (start, end, text) in enumerate(subtitles, 1):
            cue_text = wrap_text_for_subtitle(text)
            f.write(f"{idx}\n")
            f.write(f"{format_vtt_timestamp(start)} --> {format_vtt_timestamp(end)}\n")
            f.write(f"{cue_text}\n\n")


def embed_subtitles_in_video(video_path: str, srt_path: str, output_path: str) -> None:
    ffmpeg_bin = get_ffmpeg_bin()
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(srt_path),
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "-c:s",
        "mov_text",
        "-metadata:s:s:0",
        "language=chi",
        "-metadata:s:s:0",
        "title=中文",
        "-disposition:s:0",
        "default",
        str(output_path),
    ]
    print(f"▶ 正在封装字幕轨道至视频: {output_path}...", flush=True)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg 封装字幕失败: {res.stderr}")
    print(f"✔ 封装完成: {output_path}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="为本地视频提取音频并生成/添加字幕")
    parser.add_argument("video", help="输入视频路径")
    parser.add_argument("-s", "--srt", help="输出 SRT 文件路径")
    parser.add_argument("-v", "--vtt", help="输出 VTT 文件路径")
    parser.add_argument("-o", "--output-video", help="输出封装字幕后的 MP4 视频路径")
    parser.add_argument("--no-embed", action="store_true", help="不生成封装字幕的视频，仅导出字幕文件")

    args = parser.parse_args()

    video_path = Path(args.video).resolve()
    if not video_path.is_file():
        print(f"错误: 视频文件不存在: {video_path}", file=sys.stderr)
        sys.exit(1)

    stem = video_path.stem
    parent = video_path.parent

    srt_path = Path(args.srt) if args.srt else parent / f"{stem}.srt"
    vtt_path = Path(args.vtt) if args.vtt else parent / f"{stem}.vtt"
    out_video_path = Path(args.output_video) if args.output_video else parent / f"{stem}_subtitled.mp4"

    subtitles = extract_and_transcribe(str(video_path))

    if not subtitles:
        print("未检测到有效语音，未生成字幕。")
        sys.exit(0)

    save_srt(subtitles, str(srt_path))
    print(f"✔ SRT 字幕已生成: {srt_path}")

    save_vtt(subtitles, str(vtt_path))
    print(f"✔ VTT 字幕已生成: {vtt_path}")

    if not args.no_embed:
        embed_subtitles_in_video(str(video_path), str(srt_path), str(out_video_path))

    print("\n🎉 全部处理完成！")
    print(f"  • SRT 字幕: {srt_path}")
    print(f"  • VTT 字幕: {vtt_path}")
    if not args.no_embed:
        print(f"  • 带字幕视频: {out_video_path}")


if __name__ == "__main__":
    main()
