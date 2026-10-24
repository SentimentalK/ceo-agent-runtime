"""
yt-dlp wrapper utility with dynamic binary discovery and subtitle extraction.
"""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, Optional, Tuple


def find_binary(name: str, env_var: Optional[str] = None, fallback_paths: Optional[list] = None) -> str:
    """Dynamically resolve binary executable path."""
    if env_var and os.environ.get(env_var):
        cand = os.environ[env_var]
        if os.path.exists(cand) and os.access(cand, os.X_OK):
            return cand

    # Prioritize binary within the current python environment (e.g. .venv/bin/)
    venv_cand = os.path.join(sys.prefix, "bin", name)
    if os.path.exists(venv_cand) and os.access(venv_cand, os.X_OK):
        return venv_cand

    which_path = shutil.which(name)
    if which_path:
        return which_path

    fallbacks = fallback_paths or []
    for p in fallbacks:
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p

    # Default to binary name in PATH
    return name


def get_ytdlp_path() -> str:
    return find_binary(
        "yt-dlp",
        env_var="YT_DLP_PATH",
        fallback_paths=[
            "/Library/Frameworks/Python.framework/Versions/3.12/bin/yt-dlp",
            "/home/sentimentalk/.local/bin/yt-dlp",
            "/usr/local/bin/yt-dlp",
            "/usr/bin/yt-dlp",
        ],
    )


def build_base_ytdlp_cmd(url: str, extra_args: Optional[list] = None) -> list:
    """Build base yt-dlp command with node js runtime if available."""
    cmd = [get_ytdlp_path()]
    
    # Check if node is available for JS runtimes
    node_bin = shutil.which("node")
    if node_bin:
        cmd.extend(["--js-runtimes", "node"])

    if extra_args:
        cmd.extend(extra_args)

    cmd.append(url)
    return cmd


def fetch_metadata(url: str, extra_args: Optional[list] = None) -> Dict[str, Any]:
    """Fetch video metadata via yt-dlp -J."""
    args = ["-J"]
    if extra_args:
        args.extend(extra_args)
    cmd = build_base_ytdlp_cmd(url, extra_args=args)
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
    except Exception:
        pass
    return {}


def download_subtitles(
    url: str,
    output_dir: str,
    prefix: str,
    extra_args: Optional[list] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Download subtitles via yt-dlp and return (filepath, method)."""
    os.makedirs(output_dir, exist_ok=True)
    template = os.path.join(output_dir, f"{prefix}.%(ext)s")

    # Step 1: Try official author-provided subtitles first (avoids 429 rate limits on auto-translation)
    official_args = [
        "--skip-download",
        "--write-subs",
        "--sub-langs", "ai-zh,zh-Hans,zh-CN,zh,en",
        "-o", template,
    ]
    if extra_args:
        official_args.extend(extra_args)

    cmd = build_base_ytdlp_cmd(url, extra_args=official_args)
    subprocess.run(cmd, capture_output=True, text=True)

    found_file = _find_subtitle_file(output_dir, prefix)
    if found_file:
        return found_file, "subtitles"

    # Step 2: Fallback to auto-generated subtitles if no official subtitles were found
    auto_args = [
        "--skip-download",
        "--write-auto-subs",
        "--sub-langs", "ai-zh,zh-Hans,zh-CN,zh,en",
        "-o", template,
    ]
    if extra_args:
        auto_args.extend(extra_args)

    cmd = build_base_ytdlp_cmd(url, extra_args=auto_args)
    subprocess.run(cmd, capture_output=True, text=True)

    found_file = _find_subtitle_file(output_dir, prefix)
    if found_file:
        return found_file, "auto-subtitles"

    return None, None


def _find_subtitle_file(output_dir: str, prefix: str) -> Optional[str]:
    """Find downloaded subtitle file matching standard extensions."""
    for ext in [
        ".zh-Hans.srt", ".zh-CN.srt", ".zh.srt", ".ai-zh.srt", ".en.srt", ".srt",
        ".zh-Hans.vtt", ".zh-CN.vtt", ".zh.vtt", ".ai-zh.vtt", ".en.vtt", ".vtt",
    ]:
        found = glob.glob(os.path.join(output_dir, f"{prefix}*{ext}"))
        if found:
            return found[0]

    all_subs = glob.glob(os.path.join(output_dir, f"{prefix}*.srt")) + glob.glob(os.path.join(output_dir, f"{prefix}*.vtt"))
    if all_subs:
        return all_subs[0]
    return None


def parse_srt_to_paragraphs(srt_path: str, chunk_size: int = 10) -> str:
    """Parse SRT or WebVTT file content into coherent paragraphs."""
    if not os.path.exists(srt_path):
        return ""

    with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    blocks = content.strip().split("\n\n")
    text_lines = []
    prev_line = ""

    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        
        # Determine whether block starts with timestamp (WebVTT) or sequence number (SRT)
        sub_text_parts = []
        if "-->" in lines[0]:
            # WebVTT: line 0 is timestamp, line 1+ is text
            sub_text_parts = lines[1:]
        elif len(lines) >= 2 and "-->" in lines[1]:
            # SRT: line 0 is index, line 1 is timestamp, line 2+ is text
            sub_text_parts = lines[2:]
        else:
            # Header or comment block (e.g. WEBVTT, Kind: captions)
            continue

        sub_text = " ".join(sub_text_parts).strip()
        # Filter out webvtt timing/style artifacts
        sub_text = re.sub(r"<[^>]+>", "", sub_text)
        if sub_text and sub_text != prev_line:
            text_lines.append(sub_text)
            prev_line = sub_text

    paragraphs = []
    for i in range(0, len(text_lines), chunk_size):
        paragraph = "".join(text_lines[i : i + chunk_size])
        paragraphs.append(paragraph)

    return "\n\n".join(paragraphs)
