# wechat.login

Start or check the WeChat Official Accounts backend session. The session lives in a controlled Chrome profile.

## Setup

```bash
capabilities/wechat.login/setup
```

## Start the browser

```bash
capabilities/wechat.login/run open --profile wechat-b --cdp-port 9223
```

Scan the QR code if the browser shows the login page.

The session persists in `~/.local/share/browser.run_flow/profiles/wechat-b`. A later `open` reuses it.

Use a different profile for each official account.

## Check the session

```bash
capabilities/wechat.login/run status --cdp 9223
```

Output is JSON: `ok`, `logged_in`, `account`, `token`, `cdp`.

## Rules

1. Start the browser before you run any other `wechat.*` capability.
2. Keep the browser open while the other capabilities run.
3. Do not print or share the `token` value.
4. Use one profile for each account. Do not reuse a profile across accounts.
