# wechat.draft

List drafts. Set a cover. Publish a draft. Delete a draft.

## Setup

```bash
capabilities/wechat.draft/setup
```

## List drafts

```bash
capabilities/wechat.draft/run list --cdp 9223
capabilities/wechat.draft/run list --published --cdp 9223
```

Output is JSON with `appmsgid`, `title`, and `updated` for drafts. Published items have `date` and `status`.

## Set a cover

```bash
capabilities/wechat.draft/run set-cover --title "<title>" [--image <file or URL>] --cdp 9223
```

Without `--image`, the command uses the first body image.

Use `--force` to replace an existing cover.

## Publish a draft

```bash
capabilities/wechat.draft/run publish --title "<title>" --cdp 9223
```

The command does these steps:

1. Finds the draft.
2. Clicks `发表` on the draft card.
3. Turns `群发通知` off.
4. Confirms `继续发表` and `继续发布`.

If WeChat asks for a QR scan, the command waits. Set `--wait-scan` to change the wait time.

Use `--dry-run` to open the publish dialog and cancel.

## Delete a draft

```bash
capabilities/wechat.draft/run delete --title "<title>" --cdp 9223
```

## Rules

1. Run `wechat.login` first.
2. Publish with `群发通知` off for archives. This does not use the daily notification quota.
3. Read `--dry-run` output before you publish many drafts.
4. Do not publish the same draft twice.
