"""
Markdown exporter and YAML front matter generator.
"""

import re
from typing import Any
try:
    from .models import ResolvedContent
except (ImportError, ValueError):
    from models import ResolvedContent


def sanitize_filename(name: str) -> str:
    """Sanitize title for safe filesystem filenames."""
    if not name:
        return "untitled"
    name = re.sub(r'[\\/*?:"<>|]', '_', name)
    name = re.sub(r'\s+', '_', name)
    name = re.sub(r'_+', '_', name)
    return name.strip('_') or "untitled"


def format_yaml_val(val: Any) -> str:
    """Format python value into valid YAML scalar."""
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    val_str = str(val).replace('"', '\\"')
    return f'"{val_str}"'


def export_markdown(content: ResolvedContent) -> str:
    """Generate Markdown text with YAML front matter."""
    meta = content.metadata
    
    yaml_lines = [
        "---",
        f"source_type: {format_yaml_val(meta.source_type)}",
        f"source_url: {format_yaml_val(meta.source_url)}",
        f"canonical_url: {format_yaml_val(meta.canonical_url or meta.source_url)}",
        f"source_id: {format_yaml_val(meta.source_id)}",
        f"title: {format_yaml_val(meta.title)}",
        f"creator: {format_yaml_val(meta.creator)}",
        f"published_at: {format_yaml_val(meta.published_at)}",
        f"duration_seconds: {format_yaml_val(meta.duration_seconds)}",
        f"thumbnail_url: {format_yaml_val(meta.thumbnail_url)}",
        f"media_url: {format_yaml_val(meta.media_url)}",
        f"view_count: {format_yaml_val(meta.view_count)}",
        f"like_count: {format_yaml_val(meta.like_count)}",
        f"comment_count: {format_yaml_val(meta.comment_count)}",
        f"transcript_status: {format_yaml_val(content.transcript_status)}",
        f"transcript_method: {format_yaml_val(content.transcript_method)}",
        f"captured_at: {format_yaml_val(meta.captured_at)}"
    ]

    if meta.platform_metadata:
        yaml_lines.append("platform_metadata:")
        for k, v in meta.platform_metadata.items():
            yaml_lines.append(f"  {k}: {format_yaml_val(v)}")

    yaml_lines.append("---")
    yaml_header = "\n".join(yaml_lines)

    title = meta.title or "Untitled"
    source_url = meta.canonical_url or meta.source_url
    
    sections = [
        yaml_header,
        f"\n# {title}",
        f"\n> 视频链接: {source_url}"
    ]

    if meta.description and meta.description.strip():
        sections.append(f"\n## Description\n\n{meta.description.strip()}")

    sections.append("\n## Transcript\n")
    if content.transcript and content.transcript.strip():
        sections.append(content.transcript.strip())
    else:
        sections.append("Transcript unavailable.")

    return "\n".join(sections) + "\n"
