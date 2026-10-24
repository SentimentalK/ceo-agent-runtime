#!/usr/bin/env python3
"""
CLI entrypoint for subtitle-extractor & URL content ingestion scaffold.
Supports two primary capabilities:
  1. resolve <URL>  -> machine-friendly JSON ContentMetadata to stdout
  2. extract <URL>  -> full autonomous extraction (Markdown artifact or JSON)
"""

import argparse
import json
import os
import sys

# Support running directly as a script
if __package__ is None or __package__ == "":
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    SRC_DIR = os.path.dirname(os.path.abspath(__file__))
    if SRC_DIR not in sys.path:
        sys.path.insert(0, SRC_DIR)
    try:
        from src.api import extract_url, resolve_url
        from src.markdown import export_markdown, sanitize_filename
        from src.models import ResolveError, UnsupportedURLError
    except (ImportError, ValueError):
        from api import extract_url, resolve_url
        from markdown import export_markdown, sanitize_filename
        from models import ResolveError, UnsupportedURLError
else:
    from .api import extract_url, resolve_url
    from .markdown import export_markdown, sanitize_filename
    from .models import ResolveError, UnsupportedURLError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract metadata and transcripts from YouTube, Bilibili, and WeChat Channels (视频号)."
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run: 'resolve' or 'extract'")

    # Subcommand: resolve (lightweight metadata lookup -> machine-friendly JSON)
    p_resolve = subparsers.add_parser(
        "resolve",
        help="Resolve lightweight, read-only metadata (emits JSON to stdout)",
    )
    p_resolve.add_argument("urls", nargs="+", help="One or more URLs to resolve")
    p_resolve.add_argument("--compact", action="store_true", help="Emit compact JSON instead of formatted JSON")

    # Subcommand: extract (full autonomous extraction -> Markdown artifact or JSON)
    p_extract = subparsers.add_parser(
        "extract",
        help="Full autonomous content extraction (metadata, native subtitles, or local FireRedASR2)",
    )
    p_extract.add_argument("urls", nargs="+", help="One or more URLs to extract")
    p_extract.add_argument("-o", "--output-dir", default=".", help="Directory to save Markdown output files (default: .)")
    p_extract.add_argument("--json", action="store_true", help="Emit JSON output to stdout instead of writing Markdown file")
    p_extract.add_argument("--browser", default="chrome", help="Browser for session cookies (default: chrome)")
    p_extract.add_argument("--profile", default="Default", help="Browser profile directory (default: Default)")
    p_extract.add_argument("--enable-asr", action="store_true", help="Deprecated/no-op flag (extract always enables ASR fallback)")

    return parser


def handle_resolve(args) -> int:
    results = []
    has_error = False

    for url in args.urls:
        try:
            meta = resolve_url(url)
            results.append(meta.to_dict())
        except (UnsupportedURLError, ResolveError) as e:
            print(f"Error resolving {url}: {e}", file=sys.stderr)
            has_error = True
        except Exception as e:
            print(f"Unexpected error resolving {url}: {e}", file=sys.stderr)
            has_error = True

    indent = None if args.compact else 2
    if len(results) == 1:
        print(json.dumps(results[0], ensure_ascii=False, indent=indent))
    else:
        print(json.dumps(results, ensure_ascii=False, indent=indent))

    return 1 if has_error else 0


def handle_extract(args) -> int:
    has_error = False
    success_count = 0

    for url in args.urls:
        if not args.json:
            print(f"\n==========================================")
            print(f"=== 开始处理: {url} ===")
            print(f"==========================================")

        try:
            resolved = extract_url(
                url,
                browser_name=args.browser,
                profile_name=args.profile,
            )

            if args.json:
                print(json.dumps(resolved.to_dict(), ensure_ascii=False, indent=2))
            else:
                clean_title = sanitize_filename(resolved.metadata.title or "Untitled")
                out_filename = f"{clean_title}.md"
                os.makedirs(args.output_dir, exist_ok=True)
                out_path = os.path.join(args.output_dir, out_filename)

                md_text = export_markdown(resolved)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(md_text)

                print(f"✨ 导出 Markdown 成功: {out_path}")
                print(f"✔ 完成: {resolved.metadata.title} (状态: {resolved.transcript_status})")

            success_count += 1
        except Exception as e:
            print(f"❌ 处理失败 {url}: {e}", file=sys.stderr)
            has_error = True

    if not args.json:
        print(f"\n全部处理完毕！成功处理 {success_count}/{len(args.urls)} 个链接。")

    return 1 if has_error else 0


def main():
    parser = build_parser()
    raw_args = sys.argv[1:]

    # Backward compatibility: if no subcommand specified, default to extract
    if raw_args and raw_args[0] not in ("resolve", "extract", "-h", "--help"):
        raw_args.insert(0, "extract")

    args = parser.parse_args(raw_args)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "resolve":
        sys.exit(handle_resolve(args))
    elif args.command == "extract":
        sys.exit(handle_extract(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
