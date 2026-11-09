#!/usr/bin/env python3
"""Check or start the WeChat Official Accounts backend session."""
import argparse
import json
import os
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_lib"))
import wechat_backend as wb  # noqa: E402


def cmd_status(args):
    try:
        p, b, ctx = wb.connect(args.cdp)
        try:
            page, token, account = wb.open_home(ctx)
            page.close()
            print(json.dumps({"ok": True, "logged_in": True, "account": account,
                              "token": token, "cdp": args.cdp}, ensure_ascii=False))
        finally:
            wb.close_session(p, b)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "logged_in": False, "cdp": args.cdp,
                          "error": str(e)}, ensure_ascii=False))
        return 1
    return 0


def cmd_open(args):
    run = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                       "browser.run_flow", "run")
    cmd = [run, "open", wb.HOME, "--profile", args.profile, "--cdp-port", str(args.cdp_port)]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    end = time.time() + 45
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", args.cdp_port), timeout=1).close()
            print(json.dumps({"ok": True, "cdp": args.cdp_port, "profile": args.profile,
                              "hint": "scan the QR in the browser if it shows the login page"},
                             ensure_ascii=False))
            return 0
        except OSError:
            time.sleep(1)
    print(json.dumps({"ok": False, "error": "CDP port did not open"}, ensure_ascii=False))
    return 1


def main():
    ap = argparse.ArgumentParser(prog="wechat.login")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status", help="report whether the controlled browser is signed in")
    s.add_argument("--cdp", type=int, default=9223, help="CDP port of the controlled browser")
    s.set_defaults(fn=cmd_status)
    o = sub.add_parser("open", help="open a persistent Chrome profile for the backend")
    o.add_argument("--profile", required=True, help="browser.run_flow profile name")
    o.add_argument("--cdp-port", type=int, default=9223)
    o.set_defaults(fn=cmd_open)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
