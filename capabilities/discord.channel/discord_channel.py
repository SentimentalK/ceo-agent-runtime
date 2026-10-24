#!/usr/bin/env python3
"""
Read, react to, and delete messages in a Discord channel via the REST API.

Config (environment variables override <repo>/.env):
  DISCORD_BOT_TOKEN           bot token
  DISCORD_DEFAULT_CHANNEL_ID  channel used when --channel is omitted
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_BASE = "https://discord.com/api/v10"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
USER_AGENT = "DiscordBot (https://github.com/SentimentalK/ceo-agent-runtime, 1.0)"


def load_config() -> dict:
    config = {}
    env_file = REPO_ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip().strip("'\"")
    for key in ("DISCORD_BOT_TOKEN", "DISCORD_DEFAULT_CHANNEL_ID"):
        if os.environ.get(key):
            config[key] = os.environ[key]
    return config


def fail(message: str, code: int = 1) -> None:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    sys.exit(code)


def api(token: str, method: str, path: str, query: dict = None):
    url = API_BASE + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    headers = {"Authorization": f"Bot {token}", "User-Agent": USER_AGENT}
    data = b"" if method == "PUT" else None

    for _ in range(3):
        req = urllib.request.Request(url, method=method, headers=headers, data=data)
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                body = res.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            if exc.code == 429:
                retry_after = json.loads(body).get("retry_after", 1)
                time.sleep(float(retry_after))
                continue
            fail(f"Discord API {method} {path} returned {exc.code}: {body}")
        except urllib.error.URLError as exc:
            fail(f"Discord API {method} {path} failed: {exc.reason}")
    fail(f"Discord API {method} {path} still rate limited after retries")


def format_message(msg: dict) -> dict:
    return {
        "id": msg["id"],
        "timestamp": msg["timestamp"],
        "author": msg["author"].get("global_name") or msg["author"]["username"],
        "author_id": msg["author"]["id"],
        "content": msg.get("content", ""),
        "attachments": [a["url"] for a in msg.get("attachments", [])],
        "embeds": [e.get("url") or e.get("title") for e in msg.get("embeds", [])],
        "reactions": [
            {"emoji": r["emoji"].get("name"), "count": r["count"], "me": r.get("me", False)}
            for r in msg.get("reactions", [])
        ],
    }


def cmd_read(token: str, channel: str, args) -> dict:
    messages = api(token, "GET", f"/channels/{channel}/messages",
                   {"limit": args.limit, "after": args.after})
    messages = sorted(messages, key=lambda m: int(m["id"]))
    if args.unhandled:
        messages = [m for m in messages
                    if not any(r.get("me") for r in m.get("reactions", []))]
    return {"ok": True, "channel_id": channel, "messages": [format_message(m) for m in messages]}


def cmd_react(token: str, channel: str, args) -> dict:
    emoji = urllib.parse.quote(args.emoji)
    api(token, "PUT", f"/channels/{channel}/messages/{args.message_id}/reactions/{emoji}/@me")
    return {"ok": True, "channel_id": channel, "message_id": args.message_id, "emoji": args.emoji}


def cmd_delete(token: str, channel: str, args) -> dict:
    api(token, "DELETE", f"/channels/{channel}/messages/{args.message_id}")
    return {"ok": True, "channel_id": channel, "message_id": args.message_id, "deleted": True}


def main() -> None:
    parser = argparse.ArgumentParser(description="Discord channel access for agents")
    parser.add_argument("--channel", help="Channel ID (default: DISCORD_DEFAULT_CHANNEL_ID)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_read = sub.add_parser("read", help="Read recent messages, oldest first")
    p_read.add_argument("--limit", type=int, default=50, help="1-100 (default 50)")
    p_read.add_argument("--after", help="Only messages after this message ID")
    p_read.add_argument("--unhandled", action="store_true",
                        help="Skip messages the bot has already reacted to")

    p_react = sub.add_parser("react", help="Add a reaction to a message")
    p_react.add_argument("message_id")
    p_react.add_argument("--emoji", default="✅")

    p_delete = sub.add_parser("delete", help="Delete a message")
    p_delete.add_argument("message_id")

    args = parser.parse_args()
    if args.command == "read" and not 1 <= args.limit <= 100:
        fail("--limit must be between 1 and 100")

    config = load_config()
    token = config.get("DISCORD_BOT_TOKEN")
    channel = args.channel or config.get("DISCORD_DEFAULT_CHANNEL_ID")
    if not token:
        fail(f"DISCORD_BOT_TOKEN is not set (env or {REPO_ROOT / '.env'})", 2)
    if not channel:
        fail("No channel: pass --channel or set DISCORD_DEFAULT_CHANNEL_ID", 2)

    handlers = {"read": cmd_read, "react": cmd_react, "delete": cmd_delete}
    result = handlers[args.command](token, channel, args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
