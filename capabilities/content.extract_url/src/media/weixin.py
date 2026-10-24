"""
WeChat Channels media acquisition provider using local browser Yuanbao session.
"""

import os
import random
import re
import time
from typing import Dict, List, Optional
from urllib.parse import parse_qs, quote, urlparse

import httpx

try:
    from yt_dlp.cookies import extract_cookies_from_browser
except ImportError:
    extract_cookies_from_browser = None

try:
    from .base import (
        BaseMediaProvider,
        MediaAuthError,
        MediaDownloadError,
        MediaProviderError,
        MediaResolveError,
    )
except (ImportError, ValueError):
    from base import (
        BaseMediaProvider,
        MediaAuthError,
        MediaDownloadError,
        MediaProviderError,
        MediaResolveError,
    )


ALLOWED_COOKIE_DOMAINS = (".tencent.com", "yuanbao.tencent.com")
ALLOWED_COOKIE_NAMES = {
    "hy_token",
    "hy_user",
    "hy_source",
    "_qimei_fingerprint",
    "_qimei_i_3",
    "_qimei_uuid42",
    "_TDID_CK",
}


def redact_sensitive_url(url: str) -> str:
    """Strip token and credentials from URL for safe logging/errors."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        q = parse_qs(parsed.query)
        redacted_pairs = []
        for k, vals in q.items():
            if k.lower() in ("token", "generaltoken", "key", "pass_ticket", "encfilekey"):
                redacted_pairs.append(f"{k}=[REDACTED]")
            else:
                redacted_pairs.append(f"{k}={vals[0]}")
        redacted_query = "&".join(redacted_pairs)
        return parsed._replace(query=redacted_query).geturl()
    except Exception:
        return "[URL_REDACTED]"


class WeixinMediaProvider(BaseMediaProvider):
    """Acquires WeChat Channels MP4 stream by leveraging local Chrome Yuanbao session."""

    PARSE_ENDPOINT = "https://yuanbao.tencent.com/api/weixin/get_parse_result"
    FEED_ENDPOINT = "https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info"

    def __init__(
        self,
        browser_name: str = "chrome",
        profile_name: str = "Default",
        timeout: float = 30.0,
    ):
        self.browser_name = browser_name
        self.profile_name = profile_name
        self.timeout = timeout

    def extract_filtered_cookies(self) -> Dict[str, str]:
        """
        Extract only strictly allowed Tencent/Yuanbao cookies from local browser profile.
        Never flattens or forwards the entire browser cookie jar.
        """
        if extract_cookies_from_browser is None:
            raise MediaAuthError("yt-dlp is required for browser cookie extraction.")

        try:
            jar = extract_cookies_from_browser(self.browser_name, profile=self.profile_name)
        except Exception as e:
            raise MediaAuthError(f"Failed to access local {self.browser_name} cookies: {e}") from e

        filtered_cookies: Dict[str, str] = {}
        for cookie in jar:
            domain = getattr(cookie, "domain", "") or ""
            name = getattr(cookie, "name", "") or ""
            value = getattr(cookie, "value", "") or ""

            # Strict domain filter: only Tencent / Yuanbao domains
            if any(domain == d or domain.endswith(d) for d in ALLOWED_COOKIE_DOMAINS):
                # Filter to allowed Yuanbao auth & device tracking cookie names
                if name in ALLOWED_COOKIE_NAMES or domain == "yuanbao.tencent.com":
                    filtered_cookies[name] = value

        if not filtered_cookies.get("hy_token"):
            raise MediaAuthError(
                f"No active Tencent Yuanbao session found in {self.browser_name} ({self.profile_name}). "
                "Please log in to https://yuanbao.tencent.com/ in your browser first."
            )

        return filtered_cookies

    def _call_yuanbao_parse(self, share_url: str, cookies: Dict[str, str]) -> Dict[str, str]:
        """Request Yuanbao to parse SPH share link and return (token, export_id)."""
        headers = {
            "Content-Type": "application/json",
            "Origin": "https://yuanbao.tencent.com",
            "Referer": "https://yuanbao.tencent.com/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        payload = {
            "type": "video_channel_url",
            "url": share_url,
            "scene": 1,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self.PARSE_ENDPOINT, headers=headers, cookies=cookies, json=payload)
                if resp.status_code in (401, 403):
                    raise MediaAuthError(f"Yuanbao authentication rejected (HTTP {resp.status_code}).")
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise MediaResolveError(f"Yuanbao parse HTTP request failed: {e}") from e

        code = data.get("code")
        if code != 0:
            msg = data.get("msg") or f"code={code}"
            if any(w in str(msg).lower() for w in ("login", "auth", "登录", "鉴权")):
                raise MediaAuthError(f"Yuanbao session expired or invalid: {msg}")
            raise MediaResolveError(f"Yuanbao failed to parse video: {msg}")

        data_block = data.get("data") or {}
        playable_url = data_block.get("playable_url") or ""
        if not playable_url:
            raise MediaResolveError("Yuanbao response did not contain playable_url.")

        try:
            q = parse_qs(urlparse(playable_url).query)
            token = (q.get("token") or [""])[0]
            export_id = (q.get("eid") or [""])[0] or str(data_block.get("wx_export_id") or "")
        except Exception as e:
            raise MediaResolveError(f"Failed to parse playable_url query params: {e}") from e

        if not token or not export_id:
            raise MediaResolveError("Extracted token or exportId is missing from Yuanbao playable_url.")

        return {"token": token, "export_id": export_id}

    def _resolve_stream_url(self, token: str, export_id: str) -> str:
        """Call finder-preview get_feed_info with token and exportId to obtain direct MP4 stream URL."""
        rid = f"{int(time.time()):x}-{random.randrange(16**8):08x}"
        page_url = "https://channels.weixin.qq.com/finder-preview/pages/feed"
        q_page = quote(page_url, safe="")
        q_token = quote(token, safe="")
        q_eid = quote(export_id, safe="")
        
        endpoint = f"{self.FEED_ENDPOINT}?_rid={rid}&_pageUrl={q_page}"
        referer = f"{page_url}?entry_card_type=48&comment_scene=39&appid=0&token={q_token}&entry_scene=0&eid={q_eid}"

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://channels.weixin.qq.com",
            "Referer": referer,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        payload = {
            "baseReq": {"generalToken": token},
            "exportId": export_id,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(endpoint, headers=headers, json=payload)
                resp.raise_for_status()
                feed_data = resp.json()
        except Exception as e:
            raise MediaResolveError(f"WeChat feed request failed: {e}") from e

        err_code = feed_data.get("errCode")
        if err_code not in (0, None):
            err_msg = feed_data.get("errMsg") or f"errCode={err_code}"
            raise MediaResolveError(f"WeChat feed returned error: {err_msg}")

        feed_info = feed_data.get("data", {}).get("feedInfo") or {}
        candidates: List[str] = []
        
        # Priority order: h264VideoInfo > videoUrl > h265VideoInfo > originVideoUrl
        h264_info = feed_info.get("h264VideoInfo") or {}
        if h264_info.get("videoUrl"):
            candidates.append(h264_info["videoUrl"])
        if feed_info.get("videoUrl"):
            candidates.append(feed_info["videoUrl"])
        if feed_info.get("originVideoUrl"):
            candidates.append(feed_info["originVideoUrl"])
        h265_info = feed_info.get("h265VideoInfo") or {}
        if h265_info.get("videoUrl"):
            candidates.append(h265_info["videoUrl"])

        for cand in candidates:
            if cand and isinstance(cand, str) and cand.startswith("http"):
                return cand

        raise MediaResolveError("No valid video stream URL found in WeChat feed response.")

    def acquire(self, url: str, output_dir: str, prefix: str) -> str:
        """
        Orchestrate complete media acquisition:
        1. Extract domain-filtered browser cookies
        2. Parse share link via Yuanbao API
        3. Query WeChat feed API with token and export ID
        4. Stream MP4 file to target output path
        """
        os.makedirs(output_dir, exist_ok=True)
        target_path = os.path.join(output_dir, f"{prefix}.mp4")

        # 1. Cookies
        cookies = self.extract_filtered_cookies()

        # 2. Yuanbao parse
        auth_bundle = self._call_yuanbao_parse(url, cookies)

        # 3. Stream URL
        stream_url = self._resolve_stream_url(auth_bundle["token"], auth_bundle["export_id"])

        # 4. Download media stream
        download_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://channels.weixin.qq.com/",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("GET", stream_url, headers=download_headers) as resp:
                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "").lower()
                    if "text" in content_type or "html" in content_type:
                        raise MediaDownloadError(f"Unexpected non-video content-type from CDN: {content_type}")

                    with open(target_path, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
        except Exception as e:
            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except Exception:
                    pass
            redacted_stream_url = redact_sensitive_url(stream_url)
            raise MediaDownloadError(f"Failed to download video stream from {redacted_stream_url}: {e}") from e

        if not os.path.exists(target_path) or os.path.getsize(target_path) == 0:
            if os.path.exists(target_path):
                os.remove(target_path)
            raise MediaDownloadError("Downloaded media file is empty.")

        return target_path
