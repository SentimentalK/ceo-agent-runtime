# wechat.article

Extract a WeChat article. Create a draft from HTML or Markdown and images. Reprint another account's original article.

## Setup

```bash
capabilities/wechat.article/setup
```

## Extract an article

```bash
capabilities/wechat.article/run extract --url "<article URL>" --out temp/<task>/article
```

The command writes `article.json`, `content.html`, and `images/`.

## Create a draft

```bash
capabilities/wechat.article/run create-draft \
  --title "<title>" \
  --content temp/<task>/article/content.html \
  --footer "转载自 <账号>（原公众号），原文发布于 YYYY-MM-DD。" \
  --cdp 9223
```

The input is HTML or Markdown.

The command does these steps:

1. Downloads the images.
2. Builds a DOCX.
3. Imports the DOCX into a new draft.
4. Sets the title.
5. Sets the cover. Use `--cover` to choose the image. Without `--cover`, it uses the first body image.
6. Saves the draft.

Use `--no-cover` to skip the cover step.

Output is JSON with `appmsgid`.

## Reprint an original article

```bash
capabilities/wechat.article/run reprint --url "<article URL>" [--account "<source account>"] --cdp 9223
```

The source account must authorize the target account. Or the article must allow quick reprint.

Only original (原创) articles can be reprinted.

## Rules

1. Run `wechat.login` first.
2. Extract the article first. Use its `content.html` for a full rebuild.
3. Add a footer when you rebuild another account's article.
4. Do not reprint a non-original article. Rebuild it with `create-draft`.
