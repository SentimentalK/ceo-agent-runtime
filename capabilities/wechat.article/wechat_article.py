#!/usr/bin/env python3
"""Extract, create drafts from, and reprint WeChat Official Account articles."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_lib"))
import wechat_backend as wb  # noqa: E402


def cmd_extract(args):
    meta = wb.fetch_article(args.url, args.out)
    print(json.dumps({"ok": True, "article": meta}, ensure_ascii=False, indent=1))
    return 0


def cmd_create_draft(args):
    raw = open(args.content, encoding="utf-8").read()
    if args.content.endswith((".md", ".markdown")):
        html = wb.markdown_to_html(raw)
    else:
        html = raw
    outdir = args.out or os.path.join(os.path.dirname(os.path.abspath(args.content)),
                                      "wechat_draft_build")
    os.makedirs(outdir, exist_ok=True)
    docx_path = os.path.join(outdir, "article.docx")
    wb.build_docx(html, args.title, docx_path, os.path.join(outdir, "img"),
                  footer=args.footer)
    p, b, ctx = wb.connect(args.cdp)
    try:
        page, token, account = wb.open_home(ctx)
        page.close()
        aid = wb.import_docx(ctx, token, docx_path, args.title)
        cover = None
        if args.cover:
            cover = args.cover
        if not args.no_cover:
            try:
                wb.set_cover(ctx, token, aid, cover)
            except Exception as e:  # noqa: BLE001
                print(f"warning: cover not set: {e}", file=sys.stderr)
        print(json.dumps({"ok": True, "appmsgid": aid, "title": args.title,
                          "account": account, "cdp": args.cdp}, ensure_ascii=False))
        return 0
    finally:
        wb.close_session(p, b)


def cmd_reprint(args):
    title, account = args.title, args.account
    if args.url:
        meta = wb.article_meta(args.url)
        title = title or meta.get("title")
        account = account or meta.get("account")
    if not title:
        raise wb.WechatError("need --title or --url")
    p, b, ctx = wb.connect(args.cdp)
    try:
        page, token, _ = wb.open_home(ctx)
        page.close()
        aid = wb.reprint(ctx, token, title, account)
        print(json.dumps({"ok": True, "appmsgid": aid, "title": title,
                          "account": account, "cdp": args.cdp}, ensure_ascii=False))
        return 0
    finally:
        wb.close_session(p, b)


def main():
    ap = argparse.ArgumentParser(prog="wechat.article")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="fetch a WeChat article's HTML, images and metadata")
    e.add_argument("--url", required=True)
    e.add_argument("--out", required=True)
    e.set_defaults(fn=cmd_extract)

    c = sub.add_parser("create-draft", help="build a draft from HTML/Markdown and images")
    c.add_argument("--title", required=True)
    c.add_argument("--content", required=True, help="HTML or Markdown file")
    c.add_argument("--out", help="build directory (default: next to --content)")
    c.add_argument("--cover", help="cover image file or URL (default: first body image)")
    c.add_argument("--footer", help="text appended at the end, e.g. a source note")
    c.add_argument("--no-cover", action="store_true")
    c.add_argument("--cdp", type=int, default=9223)
    c.set_defaults(fn=cmd_create_draft)

    r = sub.add_parser("reprint", help="reprint another account's original article")
    r.add_argument("--title")
    r.add_argument("--url")
    r.add_argument("--account", help="source account nickname")
    r.add_argument("--cdp", type=int, default=9223)
    r.set_defaults(fn=cmd_reprint)

    args = ap.parse_args()
    try:
        return args.fn(args)
    except wb.WechatError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
