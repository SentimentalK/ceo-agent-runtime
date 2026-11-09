#!/usr/bin/env python3
"""List, set covers on, and publish WeChat Official Account drafts."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_lib"))
import wechat_backend as wb  # noqa: E402


def resolve_appmsgid(ctx, token, args):
    if args.appmsgid:
        return args.appmsgid
    if not args.title:
        raise wb.WechatError("need --title or --appmsgid")
    for d in wb.list_drafts(ctx, token):
        if d["title"] == args.title:
            return d["appmsgid"]
    raise wb.WechatError(f"draft not found: {args.title}")


def cmd_list(args):
    p, b, ctx = wb.connect(args.cdp)
    try:
        page, token, account = wb.open_home(ctx)
        page.close()
        items = wb.list_published(ctx, token) if args.published else wb.list_drafts(ctx, token)
        print(json.dumps({"ok": True, "account": account,
                          "kind": "published" if args.published else "drafts",
                          "items": items}, ensure_ascii=False, indent=1))
        return 0
    finally:
        wb.close_session(p, b)


def cmd_set_cover(args):
    p, b, ctx = wb.connect(args.cdp)
    try:
        page, token, _ = wb.open_home(ctx)
        page.close()
        aid = resolve_appmsgid(ctx, token, args)
        result = wb.set_cover(ctx, token, aid, args.image, force=args.force)
        print(json.dumps({"ok": True, "appmsgid": aid, "result": result}, ensure_ascii=False))
        return 0
    finally:
        wb.close_session(p, b)


def cmd_delete(args):
    p, b, ctx = wb.connect(args.cdp)
    try:
        page, token, _ = wb.open_home(ctx)
        page.close()
        aid = resolve_appmsgid(ctx, token, args)
        wb.delete_draft(ctx, token, appmsgid=aid)
        print(json.dumps({"ok": True, "appmsgid": aid, "deleted": True}, ensure_ascii=False))
        return 0
    finally:
        wb.close_session(p, b)


def cmd_publish(args):
    p, b, ctx = wb.connect(args.cdp)
    try:
        page, token, _ = wb.open_home(ctx)
        page.close()
        aid = resolve_appmsgid(ctx, token, args)
        status = wb.publish_draft(ctx, token, appmsgid=aid, wait_scan=args.wait_scan,
                                  dry_run=args.dry_run)
        ok = status in ("published", "dry-run")
        print(json.dumps({"ok": ok, "appmsgid": aid, "status": status}, ensure_ascii=False))
        return 0 if ok else 1
    finally:
        wb.close_session(p, b)


def main():
    ap = argparse.ArgumentParser(prog="wechat.draft")
    sub = ap.add_subparsers(dest="cmd", required=True)

    l = sub.add_parser("list", help="list drafts or published articles")
    l.add_argument("--published", action="store_true")
    l.add_argument("--cdp", type=int, default=9223)
    l.set_defaults(fn=cmd_list)

    c = sub.add_parser("set-cover", help="set or replace a draft's cover image")
    c.add_argument("--title")
    c.add_argument("--appmsgid")
    c.add_argument("--image", help="cover file or URL (default: first body image)")
    c.add_argument("--force", action="store_true")
    c.add_argument("--cdp", type=int, default=9223)
    c.set_defaults(fn=cmd_set_cover)

    p_ = sub.add_parser("publish", help="publish a draft with 群发通知 off")
    p_.add_argument("--title")
    p_.add_argument("--appmsgid")
    p_.add_argument("--wait-scan", type=int, default=300,
                    help="seconds to wait if WeChat asks for a QR scan")
    p_.add_argument("--dry-run", action="store_true",
                    help="open the publish dialog, turn 群发通知 off, then cancel")
    p_.add_argument("--cdp", type=int, default=9223)
    p_.set_defaults(fn=cmd_publish)

    d = sub.add_parser("delete", help="delete a draft")
    d.add_argument("--title")
    d.add_argument("--appmsgid")
    d.add_argument("--cdp", type=int, default=9223)
    d.set_defaults(fn=cmd_delete)

    args = ap.parse_args()
    try:
        return args.fn(args)
    except wb.WechatError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
