#!/usr/bin/env python3
"""Shared backend helpers for the wechat.* capabilities.

Requires a logged-in Chrome that browser.run_flow started with a persistent
profile and an exposed CDP port, e.g.:

    capabilities/browser.run_flow/run open https://mp.weixin.qq.com/cgi-bin/home \\
        --profile wechat-b --cdp-port 9223
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import sys
import time

import httpx
import lxml.html
from PIL import Image
from playwright.sync_api import sync_playwright

BASE = "https://mp.weixin.qq.com"
HOME = f"{BASE}/cgi-bin/home?t=home/index&lang=zh_CN"
DRAFT_LIST = f"{BASE}/cgi-bin/appmsg?begin={{begin}}&count=10&type=77&action=list_card&lang=zh_CN&token={{token}}"
PUBLISHED = f"{BASE}/cgi-bin/appmsgpublish?sub=list&begin={{begin}}&count=10&lang=zh_CN&token={{token}}"
NEW_EDITOR = f"{BASE}/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&lang=zh_CN&token={{token}}"
EDITOR = f"{BASE}/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=77&appmsgid={{aid}}&lang=zh_CN&token={{token}}"
WECHAT_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.50(0x1800323c) "
             "NetType/WIFI Language/zh_CN")
RATIOS = {
    "cdn_url0": (940, 400),
    "cdn_235_1_url0": (940, 400),
    "cdn_16_9_url0": (1280, 720),
    "cdn_3_4_url0": (720, 960),
    "cdn_1_1_url0": (960, 960),
}
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


class WechatError(RuntimeError):
    pass


# ---------------------------------------------------------------- dialogs

DISMISS_JS = """() => {
  document.querySelectorAll('.weui-desktop-dialog').forEach(d => {
    const t = d.innerText || '';
    if (t.includes('未授权使用切换账号能力') || t.includes('尚未实名') || t.includes('未设置头像')) {
      const b = Array.from(d.querySelectorAll('button')).find(
        x => ['取消', '我知道了'].includes(x.innerText.trim()));
      if (b) b.click();
      d.style.display = 'none';
      const w = d.closest('.weui-desktop-dialog__wrp');
      if (w) w.style.display = 'none';
    }
  });
}"""


def dismiss_dialogs(page):
    page.evaluate(DISMISS_JS)


def visible_dialogs(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll('.weui-desktop-dialog'))
        .filter(e => { const r = e.getBoundingClientRect(); return r.width > 150 && r.height > 60; })
        .map(e => ({t: (e.innerText || '').trim(),
                    btns: Array.from(e.querySelectorAll('button')).map(b => b.innerText.trim())}))""")


def click_dialog_button(page, text):
    return page.evaluate("""(text) => {
      const ds = Array.from(document.querySelectorAll('.weui-desktop-dialog'))
        .filter(e => { const r = e.getBoundingClientRect(); return r.width > 150 && r.height > 60; });
      for (const d of ds) {
        const b = Array.from(d.querySelectorAll('button')).find(x => x.innerText.trim() === text);
        if (b) { b.click(); return true; }
      }
      return false;
    }""", text)


def scan_waiting(page):
    try:
        return page.evaluate("""() => Array.from(document.querySelectorAll('*')).some(e => {
          const t = (e.innerText || '').trim(); const r = e.getBoundingClientRect();
          return r.width > 0 && r.height > 0 && t.length < 40 && t.includes('扫码验证');
        })""")
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------- session

def connect(cdp=9223):
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp}")
    ctx = browser.contexts[0]
    return p, browser, ctx


def close_session(p, browser):
    try:
        browser.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        p.stop()
    except Exception:  # noqa: BLE001
        pass


def discover_token(ctx):
    for pg in ctx.pages:
        m = re.search(r"[?&]token=(\d+)", pg.url)
        if m:
            return m.group(1)
    return None


def open_home(ctx):
    token = discover_token(ctx)
    pg = ctx.new_page()
    if token:
        pg.goto(f"{BASE}/cgi-bin/home?t=home/index&lang=zh_CN&token={token}",
                wait_until="domcontentloaded")
    else:
        pg.goto(HOME, wait_until="domcontentloaded")
    pg.wait_for_timeout(4500)
    body = pg.inner_text("body")
    if "请重新登录" in body:
        m = re.search(r"[?&]token=(\d+)", pg.url)
        if not m:
            pg.goto(HOME, wait_until="domcontentloaded")
            pg.wait_for_timeout(4000)
            body = pg.inner_text("body")
    m = re.search(r"[?&]token=(\d+)", pg.url)
    if not m or "请重新登录" in body:
        pg.close()
        raise WechatError("not logged in: open the controlled browser and sign in to mp.weixin.qq.com")
    account = pg.evaluate("""() => {
      const e = document.querySelector('.weui-desktop-account__info, .mp_account_box, .weui-desktop-account__nickname');
      return e ? e.innerText.trim().split('\\n')[0] : '';
    }""")
    return pg, m.group(1), account


def token_of(page):
    m = re.search(r"[?&]token=(\d+)", page.url)
    if not m:
        raise WechatError("page has no token; open the official-account backend first")
    return m.group(1)


# ---------------------------------------------------------------- extract

def _js_var(text, name):
    m = re.search(rf"var\s+{name}\s*=\s*(?:htmlDecode\()?\s*(['\"])(.*?)\1", text, re.DOTALL)
    return lxml.html.fragment_fromstring(f"<span>{m.group(2)}</span>").text_content().strip() if m else None


def article_meta(url):
    """Fetch an article's metadata without downloading images."""
    r = httpx.get(url, headers={"User-Agent": WECHAT_UA, "Referer": BASE + "/"},
                  follow_redirects=True, timeout=40)
    page = r.text
    if "环境异常" in page and 'id="js_content"' not in page:
        raise WechatError("WeChat verification page; retry later")
    if 'id="js_content"' not in page:
        raise WechatError("article body not found (deleted or restricted)")
    return {
        "source_url": url,
        "title": _js_var(page, "msg_title") or (doc_xpath_title(page)),
        "account": _js_var(page, "nickname"),
        "author": _js_var(page, "author"),
        "digest": _js_var(page, "msg_desc"),
        "cover_url": _js_var(page, "msg_cdn_url"),
    }


def doc_xpath_title(page):
    try:
        doc = lxml.html.fromstring(page)
        t = doc.get_element_by_id("activity-name")
        return t.text_content().strip() if t is not None else None
    except Exception:  # noqa: BLE001
        return None


def fetch_article(url, outdir):
    os.makedirs(outdir, exist_ok=True)
    r = httpx.get(url, headers={"User-Agent": WECHAT_UA, "Referer": BASE + "/"}, follow_redirects=True, timeout=40)
    page = r.text
    if "环境异常" in page and 'id="js_content"' not in page:
        raise WechatError("WeChat verification page; retry later")
    if 'id="js_content"' not in page:
        raise WechatError("article body not found (deleted, restricted, or an image-only post)")
    doc = lxml.html.fromstring(page)
    body = doc.get_element_by_id("js_content")
    for tag in ("script", "style", "iframe"):
        for e in body.xpath(f".//{tag}"):
            e.drop_tree()
    meta = {
        "source_url": url,
        "canonical_url": (doc.xpath('//meta[@property="og:url"]/@content') or [url])[0],
        "title": _js_var(page, "msg_title") or (doc.xpath('//meta[@property="og:title"]/@content') or [None])[0],
        "account": _js_var(page, "nickname"),
        "author": _js_var(page, "author"),
        "digest": _js_var(page, "msg_desc"),
        "cover_url": _js_var(page, "msg_cdn_url"),
        "published_at": None,
    }
    m = re.search(r'var\s+(?:ct|create_time)\s*=\s*"(\d{9,11})"', page)
    if m:
        import datetime
        meta["published_at"] = datetime.datetime.fromtimestamp(
            int(m.group(1)), tz=datetime.timezone.utc).astimezone().isoformat()
    imgs = []
    for i, img in enumerate(body.xpath(".//img"), 1):
        src = img.get("data-src") or img.get("src")
        if not src:
            continue
        ext = "gif" if "gif" in src else ("png" if "png" in src else "jpg")
        path = os.path.join(outdir, "images", f"{i:03d}.{ext}")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            data = httpx.get(src, headers={"User-Agent": WECHAT_UA, "Referer": url}, timeout=40).content
            open(path, "wb").write(data)
            imgs.append({"index": i, "src": src, "path": path})
        except Exception:  # noqa: BLE001
            imgs.append({"index": i, "src": src, "path": None})
    frag = lxml.html.tostring(body, encoding="unicode")
    open(os.path.join(outdir, "content.html"), "w", encoding="utf-8").write(frag)
    meta["images"] = imgs
    json.dump(meta, open(os.path.join(outdir, "article.json"), "w"), ensure_ascii=False, indent=1)
    return meta


# ---------------------------------------------------------------- docx

def normalize_text(s):
    return re.sub(r"[ \t\r\f\v\u00a0]+", " ", (s or "")).strip()


def crop_center(img, w, h):
    iw, ih = img.size
    tr = w / h
    if iw / ih > tr:
        nw = int(ih * tr)
        box = ((iw - nw) // 2, 0, (iw - nw) // 2 + nw, ih)
    else:
        nh = int(iw / tr)
        box = (0, (ih - nh) // 2, iw, (ih - nh) // 2 + nh)
    return img.crop(box).resize((w, h))


def build_docx(content_html, title, out_path, imgdir=None, footer=None):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches

    root = lxml.html.fromstring(content_html)
    body = root.get_element_by_id("js_content", root)
    imgdir = imgdir or (os.path.splitext(out_path)[0] + "_img")
    os.makedirs(imgdir, exist_ok=True)
    doc = Document()
    seen = set()
    idx = 0

    def add_image(src):
        nonlocal idx
        idx += 1
        path = None
        if os.path.isfile(src):
            path = src
        elif src.startswith("http"):
            path = os.path.join(imgdir, f"{idx:03d}.jpg")
            if not (os.path.exists(path) and os.path.getsize(path) > 0):
                try:
                    open(path, "wb").write(
                        httpx.get(src, headers={"User-Agent": WECHAT_UA, "Referer": BASE + "/"},
                                  timeout=40).content)
                except Exception:  # noqa: BLE001
                    return
        if not path or not os.path.exists(path):
            return
        try:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(path, width=Inches(5.5))
        except Exception:  # noqa: BLE001
            pass

    for el in body.iter():
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag == "img":
            add_image(el.get("data-src") or el.get("src") or "")
        elif tag in ("p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "li"):
            if any(isinstance(c.tag, str) and c.tag in ("p", "blockquote", "li") for c in el):
                continue
            text = normalize_text("".join(el.itertext()))
            if not text or (tag, text) in seen:
                continue
            seen.add((tag, text))
            para = doc.add_paragraph()
            if tag in ("h1", "h2", "h3"):
                para.add_run(text).bold = True
            else:
                para.add_run(text)
    if footer:
        doc.add_paragraph()
        doc.add_paragraph(footer)
    doc.save(out_path)
    return out_path


def markdown_to_html(md):
    """Minimal Markdown to the subset build_docx understands."""
    out = []
    for line in (md or "").splitlines():
        s = line.rstrip()
        if not s.strip():
            continue
        m = re.match(r"!\[[^\]]*\]\(([^)]+)\)", s.strip())
        if m:
            out.append(f'<p><img data-src="{m.group(1)}"></p>')
        elif s.startswith("#"):
            out.append(f"<h2>{s.lstrip('#').strip()}</h2>")
        else:
            out.append(f"<p>{s}</p>")
    return f'<div id="js_content">{"".join(out)}</div>'


# ---------------------------------------------------------------- editor

def set_title(page, title):
    page.evaluate("""(t) => {
      const el = document.querySelector('#title');
      if (!el) return;
      el.value = t;
      ['input', 'change', 'keyup'].forEach(k => el.dispatchEvent(new Event(k, {bubbles: true})));
    }""", title)
    page.wait_for_timeout(600)


def content_len(page):
    try:
        lens = page.evaluate("() => Array.from(document.querySelectorAll('.ProseMirror'))"
                             ".map(e => (e.innerText || '').length)")
        return max(lens) if lens else 0
    except Exception:  # noqa: BLE001
        return 0


def save_draft(page):
    dismiss_dialogs(page)
    page.evaluate("""() => { const b = Array.from(document.querySelectorAll('*')).find(
        e => (e.innerText || '').trim() === '保存为草稿' && e.children.length === 0); if (b) b.click(); }""")
    end = time.time() + 40
    while time.time() < end:
        page.wait_for_timeout(1000)
        try:
            if "手动保存" in page.inner_text("body"):
                return appmsgid_of(page)
        except Exception:  # noqa: BLE001
            pass
    return appmsgid_of(page)


def appmsgid_of(page):
    m = re.search(r"[?&]appmsgid=(\d+)", page.url)
    return m.group(1) if m else None


def import_docx(ctx, token, docx_path, title):
    pg = ctx.new_page()
    try:
        pg.goto(NEW_EDITOR.format(token=token), wait_until="domcontentloaded")
        pg.wait_for_timeout(7000)
        dismiss_dialogs(pg)
        pg.locator("#js_import_file").evaluate("e => e.click()")
        pg.wait_for_timeout(2500)
        pg.locator('input[accept*="word"]').first.set_input_files(docx_path)
        end = time.time() + 70
        while time.time() < end:
            pg.wait_for_timeout(1500)
            if content_len(pg) > 30:
                break
        else:
            raise WechatError("DOCX import produced no content")
        dismiss_dialogs(pg)
        set_title(pg, title)
        aid = save_draft(pg)
        if not aid:
            raise WechatError("draft was not saved")
        return aid
    finally:
        try:
            pg.close()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------- cover

def capture_save(ctx, token, appmsgid, force=False):
    """Open the draft, save once, return the form fields + fresh data_seq."""
    pg = ctx.new_page()
    cap = {}
    pg.on("request", lambda r: cap.update(body=r.post_data, url=r.url)
          if ("operate_appmsg" in r.url and "sub=update" in r.url) else None)

    def on_resp(r):
        if "operate_appmsg" in r.url and "sub=update" in r.url:
            try:
                cap["json"] = r.json()
            except Exception:  # noqa: BLE001
                pass

    pg.on("response", on_resp)
    try:
        pg.goto(EDITOR.format(aid=appmsgid, token=token), wait_until="domcontentloaded")
        pg.wait_for_timeout(7000)
        dismiss_dialogs(pg)
        covered = pg.evaluate("""() => { const a = document.querySelector('#js_cover_area');
            if (!a) return false; const p = a.querySelector('.js_cover_preview_new');
            return p ? getComputedStyle(p).display !== 'none' : false; }""")
        if covered and not force:
            return None
        pg.evaluate("""() => { const b = Array.from(document.querySelectorAll('*')).find(
            e => (e.innerText || '').trim() === '保存为草稿' && e.children.length === 0); if (b) b.click(); }""")
        pg.wait_for_timeout(6000)
    finally:
        try:
            pg.close()
        except Exception:  # noqa: BLE001
            pass
    body = cap.get("body") or ""
    fields = {}
    for part in re.split(r"------WebKitFormBoundary[^\r\n]*\r\n", body):
        m = re.search(r'name="([^"]+)"', part)
        if m:
            fields[m.group(1)] = (part.split("\r\n\r\n", 1)[1].rsplit("\r\n", 1)[0]
                                  if "\r\n\r\n" in part else "")
    seq = (cap.get("json") or {}).get("data_seq") or fields.get("data_seq")
    return {"fields": fields, "seq": seq, "url": cap.get("url"),
            "image": first_image(fields)}


def first_image(fields):
    try:
        ci = json.loads(fields.get("copyright_img_list0") or "{}")
        imgs = [x.get("url") for x in ci.get("img_list", []) if x.get("url")]
        if imgs:
            return imgs[0].replace("\\/", "/")
    except Exception:  # noqa: BLE001
        pass
    return None


def get_upload_url(ctx, token):
    """Capture the account's image-upload endpoint (ticket) from a throwaway editor."""
    pg = ctx.new_page()
    cap = {}
    pg.on("request", lambda r: cap.update(url=r.url) if "filetransfer" in r.url else None)
    try:
        pg.goto(NEW_EDITOR.format(token=token), wait_until="domcontentloaded")
        pg.wait_for_timeout(7000)
        dismiss_dialogs(pg)
        probe = io.BytesIO()
        Image.new("RGB", (320, 240), (200, 200, 200)).save(probe, format="JPEG", quality=80)
        pg.locator('input[type=file][accept*="image"]').first.set_input_files(
            {"name": "probe.jpg", "mimeType": "image/jpeg", "buffer": probe.getvalue()})
        end = time.time() + 15
        while time.time() < end and not cap.get("url"):
            pg.wait_for_timeout(500)
    finally:
        try:
            pg.close()
        except Exception:  # noqa: BLE001
            pass
    if not cap.get("url"):
        raise WechatError("could not capture the image upload endpoint")
    return cap["url"]


def upload_image(ctx, upload_url, data, referer):
    r = ctx.request.post(upload_url,
                         multipart={"file": {"name": "image.jpg", "mimeType": "image/jpeg",
                                             "buffer": data}},
                         headers={"Referer": referer})
    j = r.json()
    ret = j.get("base_resp", {}).get("ret")
    if ret != 0:
        raise WechatError(f"image upload failed: {j.get('base_resp')}")
    return j.get("cdn_url", "").replace("\\/", "/"), j.get("content")


def load_image(src):
    if os.path.isfile(src):
        data = open(src, "rb").read()
    else:
        data = httpx.get(src, headers={"User-Agent": "Mozilla/5.0"}, timeout=40).content
    return Image.open(io.BytesIO(data)).convert("RGB")


def set_cover(ctx, token, appmsgid, image, force=False, upload_url=None):
    cap = capture_save(ctx, token, appmsgid, force=force)
    if cap is None:
        return "already-covered"
    if not image:
        image = cap.get("image")
    if not image:
        raise WechatError("no cover image: pass --image or use an article with a body image")
    if not upload_url:
        upload_url = get_upload_url(ctx, token)
    referer = EDITOR.format(aid=appmsgid, token=token)
    img = load_image(image)
    fields = cap["fields"]
    urls, fids = {}, {}
    for key, (w, h) in RATIOS.items():
        buf = io.BytesIO()
        crop_center(img, w, h).save(buf, format="JPEG", quality=92)
        urls[key], fids[key] = upload_image(ctx, upload_url, buf.getvalue(), referer)
    for k, v in urls.items():
        fields[k] = v
    fields["cdn_url_back0"] = urls["cdn_235_1_url0"]
    fields["fileid0"] = fids["cdn_235_1_url0"]
    fields["data_seq"] = cap["seq"]
    fields.update({"show_cover_pic0": "1", "app_cover_auto0": "0",
                   "last_choose_cover_from0": "1"})
    r = ctx.request.post(cap["url"], multipart=fields,
                         headers={"Referer": referer, "Origin": BASE})
    j = r.json()
    info = j.get("cover_check_info") or {}
    ok = j.get("base_resp", {}).get("ret") == 0 and not info.get("err_format")
    if not ok:
        raise WechatError(f"cover save rejected: {info or j.get('base_resp')}")
    return "ok"


# ---------------------------------------------------------------- lists

def list_drafts(ctx, token):
    pg = ctx.new_page()
    out = []
    try:
        for begin in range(0, 90, 10):
            pg.goto(DRAFT_LIST.format(begin=begin, token=token), wait_until="domcontentloaded")
            pg.wait_for_timeout(1800)
            out.extend(pg.evaluate("""() => Array.from(document.querySelectorAll('.weui-desktop-publish')).map(c => {
                const lines = c.innerText.split('\\n').map(x => x.replace(/\\u00a0/g, ' ').trim());
                const title = lines[0].startsWith('更新于') ? '' : lines[0];
                const updated = (lines.find(x => x.startsWith('更新于')) || '').replace('更新于 ', '');
                return {appmsgid: c.getAttribute('data-appid'), title, updated};
            })"""))
    finally:
        pg.close()
    seen, uniq = set(), []
    for d in out:
        if d["appmsgid"] in seen:
            continue
        seen.add(d["appmsgid"])
        uniq.append(d)
    return uniq


def list_published(ctx, token):
    pg = ctx.new_page()
    out = []
    try:
        for begin in range(0, 90, 10):
            pg.goto(PUBLISHED.format(begin=begin, token=token), wait_until="domcontentloaded")
            pg.wait_for_timeout(2000)
            out.extend(pg.evaluate("""() => Array.from(document.querySelectorAll('.weui-desktop-mass-media')).map(m => {
                const a = m.querySelector('a.weui-desktop-mass-appmsg__title');
                const p = m.parentElement;
                const lines = p ? p.innerText.split('\\n').map(x => x.trim()) : [];
                return {title: a ? a.innerText.replace(/\\u00a0/g, ' ').trim() : '',
                        date: lines[0] || '', status: lines[1] || ''};
            })"""))
    finally:
        pg.close()
    return out


# ---------------------------------------------------------------- publish

def find_draft_card(page, token, appmsgid=None, title=None):
    for begin in range(0, 90, 10):
        page.goto(DRAFT_LIST.format(begin=begin, token=token), wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        cards = page.locator(".weui-desktop-publish")
        for i in range(cards.count()):
            txt = cards.nth(i).inner_text().replace("\u00a0", " ")
            aid = cards.nth(i).get_attribute("data-appid")
            if (appmsgid and aid == appmsgid) or (title and title in txt):
                return cards.nth(i)
    raise WechatError("draft not found")


def publish_draft(ctx, token, appmsgid=None, title=None, wait_scan=300, dry_run=False):
    # close stale editors so the new one is unambiguous
    for p_ in list(ctx.pages):
        if "appmsg_edit" in p_.url:
            try:
                p_.close()
            except Exception:  # noqa: BLE001
                pass
    list_page = ctx.new_page()
    editor = None
    try:
        card = find_draft_card(list_page, token, appmsgid=appmsgid, title=title)
        card.hover()
        list_page.wait_for_timeout(500)
        card.locator("a").filter(has_text="发表").first.click()
        end = time.time() + 45
        while time.time() < end:
            list_page.wait_for_timeout(800)
            for p_ in ctx.pages:
                if "appmsg_edit" not in p_.url:
                    continue
                try:
                    dismiss_dialogs(p_)
                    if any("群发通知" in d["t"] for d in visible_dialogs(p_)):
                        editor = p_
                        break
                except Exception:  # noqa: BLE001
                    continue
            if editor:
                break
        if editor is None:
            raise WechatError("publish dialog not found")
        checks = editor.evaluate("""() => { const d = Array.from(document.querySelectorAll('.weui-desktop-dialog'))
            .find(e => e.getBoundingClientRect().width > 150 && (e.innerText || '').includes('群发通知'));
            return d ? Array.from(d.querySelectorAll('input.weui-desktop-switch__input')).map(i => i.checked) : []; }""")
        if checks and checks[0]:
            editor.evaluate("""() => { const d = Array.from(document.querySelectorAll('.weui-desktop-dialog'))
                .find(e => e.getBoundingClientRect().width > 150 && (e.innerText || '').includes('群发通知'));
                const i = d && d.querySelector('input.weui-desktop-switch__input');
                if (i && i.checked) i.click(); }""")
            editor.wait_for_timeout(800)
        if dry_run:
            click_dialog_button(editor, "取消")
            return "dry-run"
        if not click_dialog_button(editor, "发表"):
            raise WechatError("cannot click 发表")
        editor.wait_for_timeout(2500)
        click_dialog_button(editor, "继续发表")
        editor.wait_for_timeout(2000)
        click_dialog_button(editor, "继续发布")
        end = time.time() + wait_scan
        while time.time() < end:
            editor.wait_for_timeout(2000)
            try:
                if editor.is_closed():
                    return "published"
            except Exception:  # noqa: BLE001
                return "published"
            if scan_waiting(editor):
                continue
            if not visible_dialogs(editor):
                body = editor.inner_text("body")
                if "审核中" in body or "已发表" in body:
                    return "published"
        return "timeout"
    finally:
        try:
            list_page.close()
        except Exception:  # noqa: BLE001
            pass
        if editor is not None:
            try:
                editor.close()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------- reprint

def reprint(ctx, token, title, account, publish=False, wait_scan=300):
    list_page = ctx.new_page()
    try:
        list_page.goto(f"{BASE}/cgi-bin/home?t=home/index&lang=zh_CN&token={token}",
                       wait_until="domcontentloaded")
        list_page.wait_for_timeout(3500)
        dismiss_dialogs(list_page)
        list_page.locator(".new-creation__menu-item", has_text="转载").first.click()
        list_page.wait_for_timeout(4000)
        editor = [p_ for p_ in ctx.pages if "edit_v2" in p_.url][-1]
        dlg = editor.locator(".dialog_wrp.share_article_dialog")
        if not dlg.count() or not dlg.is_visible():
            editor.get_by_text("转载文章", exact=True).first.click()
            editor.wait_for_timeout(2500)
        dlg.locator('li[data-type="fast_reprint"]').evaluate("e => e.click()")
        editor.wait_for_timeout(800)
        inp = editor.locator(".js_search_input")
        inp.fill(title)
        inp.press("Enter")
        editor.wait_for_timeout(5000)
        row = editor.locator(".js_search_content table tbody tr").filter(has_text=account).filter(has_text=title)
        if not row.count():
            dlg.locator('li[data-type="whitelist_reprint"]').evaluate("e => e.click()")
            editor.wait_for_timeout(3000)
            row = editor.locator(".js_article_content tr, .js_biz_article_content tr").filter(
                has_text=account).filter(has_text=title)
        if not row.count():
            raise WechatError("article not found in reprint search")
        row.first.locator("input.js_selected_radio").evaluate("e => e.click()")
        editor.wait_for_timeout(500)
        dlg.locator('button.js_btn[data-index="0"]').evaluate("e => e.click()")
        end = time.time() + 40
        while time.time() < end:
            editor.wait_for_timeout(1500)
            if content_len(editor) > 50 or title in editor.inner_text("body"):
                break
        else:
            raise WechatError("reprint content did not load")
        aid = save_draft(editor)
        return aid or "ok"
    finally:
        try:
            list_page.close()
        except Exception:  # noqa: BLE001
            pass


def delete_draft(ctx, token, appmsgid=None, title=None):
    list_page = ctx.new_page()
    try:
        card = find_draft_card(list_page, token, appmsgid=appmsgid, title=title)
        card.hover()
        list_page.wait_for_timeout(600)
        aid = appmsgid or card.get_attribute("data-appid")
        trigger = list_page.evaluate("""(aid) => {
          const card = Array.from(document.querySelectorAll('.weui-desktop-publish'))
            .find(c => c.getAttribute('data-appid') === aid);
          if (!card) return 'no card';
          const wraps = Array.from(card.querySelectorAll('.weui-desktop-popover__wrp'));
          for (const w of wraps) {
            if ((w.innerText || '').includes('删除该素材')) {
              const a = w.querySelector('a.weui-desktop-icon-btn');
              if (a) { a.click(); return 'ok'; }
            }
          }
          return 'no trigger';
        }""", aid)
        if trigger != "ok":
            raise WechatError(f"delete trigger not found: {trigger}")
        list_page.wait_for_timeout(1200)
        done = list_page.evaluate("""(aid) => {
          const card = Array.from(document.querySelectorAll('.weui-desktop-publish'))
            .find(c => c.getAttribute('data-appid') === aid);
          const scope = card || document;
          const pops = Array.from(scope.querySelectorAll('.weui-desktop-popover'))
            .filter(e => getComputedStyle(e).display !== 'none' && (e.innerText || '').includes('删除该素材'));
          for (const p of pops) {
            const b = Array.from(p.querySelectorAll('button')).find(x => x.innerText.trim() === '删除');
            if (b) { b.click(); return 'deleted'; }
          }
          return 'no confirm';
        }""", aid)
        if done != "deleted":
            raise WechatError(f"delete confirmation not found: {done}")
        list_page.wait_for_timeout(2000)
        return True
    finally:
        list_page.close()
