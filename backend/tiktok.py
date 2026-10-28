"""Single-post TikTok URLs and bounded, validated short-link resolution."""

import re
import copy
from functools import lru_cache
from urllib.parse import urlsplit

from .validators import MAX_REDIRECTS, validate_url, validate_redirect


@lru_cache(maxsize=2)
def post_data(url, *, use_cookies):
    from .downloader import MediaError, gallery_extractor, assert_media_access, has_login_session
    from .settings import settings

    ext = gallery_extractor(url, use_cookies=use_cookies)
    try:
        scope = ext._extract_rehydration_data(url)
        detail = scope.get("webapp.video-detail") or {}
        status = detail.get("statusCode") or 0
        if status in (10216, 10222):
            raise MediaError("login_required", "TikTok ไม่อนุญาตให้บัญชีนี้ดูโพสต์ หรือจำเป็นต้องล็อกอิน")
        if status == 10231:
            raise MediaError("region_restricted", "TikTok จำกัดการเข้าถึงโพสต์นี้ในภูมิภาคของคุณ")
        if status == 10204:
            raise MediaError("no_media", "ไม่พบโพสต์ TikTok นี้ หรือเนื้อหาไม่พร้อมให้ดู")
        if status:
            raise MediaError("platform_blocked", "TikTok ไม่ส่งข้อมูลโพสต์ กรุณาลองใหม่ภายหลัง")
        post = (detail.get("itemInfo") or {}).get("itemStruct")
        if not isinstance(post, dict):
            raise MediaError("extract_failed", "อ่านโพสต์ TikTok ไม่สำเร็จ กรุณาลองใหม่ภายหลัง")
        if str(post.get("id")) != urlsplit(url).path.rstrip("/").split("/")[-1]:
            raise MediaError("no_media", "TikTok ส่งข้อมูลไม่ตรงกับโพสต์ในลิงก์ กรุณาตรวจสอบลิงก์ใหม่")
        owner = urlsplit(url).path.split("/")[1].removeprefix("@")
        if owner and str((post.get("author") or {}).get("uniqueId", "")).lower() != owner.lower():
            raise MediaError("no_media", "TikTok ส่งโพสต์ไม่ตรงกับบัญชีในลิงก์ กรุณาตรวจสอบลิงก์ใหม่")
        if any(post.get(key) for key in ("isPaidContent", "isPaidVideo", "isPaidCollection")):
            raise MediaError("paywall", "ไม่รองรับเนื้อหา TikTok แบบเสียเงิน")
        if (post.get("video") or {}).get("isDRM"):
            raise MediaError("drm", "ไม่รองรับสื่อที่มี DRM")
        metadata = dict(post)
        if post.get("privateItem") or (post.get("author") or {}).get("privateAccount"):
            metadata["availability"] = "private"
        assert_media_access(
            metadata,
            use_cookies=use_cookies,
            authenticated=has_login_session(ext.session.cookies, url),
        )
        if len((post.get("imagePost") or {}).get("images") or []) > settings.max_items:
            raise MediaError("item_limit", "โพสต์ TikTok มีรูปเกินจำนวนที่กำหนด")
        post["_media_headers"] = {"Referer": url}
        if ext.session.headers.get("User-Agent"):
            post["_media_headers"]["User-Agent"] = ext.session.headers["User-Agent"]
        # Keep response cookies in worker RAM and preserve their original domains.
        # They never become browser-facing metadata or Cookie headers on other hosts.
        post["_cookie_rows"] = []
        for cookie in ext.session.cookies:
            if cookie.is_expired() or not is_tiktok("https://" + cookie.domain.lstrip(".")):
                continue
            row = dict(cookie.__dict__)
            row["rest"] = row.pop("_rest", {})
            post["_cookie_rows"].append(row)
        return copy.deepcopy(post)
    finally:
        ext.session.close()


def is_tiktok(url):
    host = (urlsplit(url).hostname or "").lower()
    return host == "tiktok.com" or host.endswith(".tiktok.com")


def short_link(url):
    if not is_tiktok(url):
        return False
    parts = urlsplit(url)
    return parts.hostname in ("vm.tiktok.com", "vt.tiktok.com") or bool(
        re.fullmatch(r"/t/[A-Za-z0-9]+/?", parts.path)
    )


def normalize_url(url):
    from .downloader import MediaError

    parts = urlsplit(url)
    if not is_tiktok(url):
        raise MediaError("tiktok_url", "กรุณาใช้ลิงก์ TikTok")
    match = re.fullmatch(r"/(?:@([A-Za-z0-9._-]*)|share)/(video|photo)/([0-9]+)/?", parts.path)
    if match:
        # Both libraries read photo posts from the canonical video-detail page.
        return f"https://www.tiktok.com/@{match[1] or ''}/video/{match[3]}"
    if re.fullmatch(r"/embed/(?:v2/)?([0-9]+)/?", parts.path):
        identifier = parts.path.rstrip("/").split("/")[-1]
        return f"https://www.tiktok.com/@/video/{identifier}"
    if short_link(url) and re.fullmatch(r"/(?:t/)?[A-Za-z0-9]+/?", parts.path):
        host = (
            parts.hostname
            if parts.hostname in ("vm.tiktok.com", "vt.tiktok.com")
            else "www.tiktok.com"
        )
        return f"https://{host}{parts.path}"
    if "live" in parts.path.split("/"):
        raise MediaError("live_not_supported", "ยังไม่รองรับ TikTok LIVE กรุณาใช้ลิงก์คลิปที่โพสต์แล้ว")
    raise MediaError("tiktok_post_required", "กรุณาใช้ลิงก์คลิปหรือโพสต์รูปภาพ TikTok ยังไม่รองรับลิงก์โปรไฟล์")


def resolve_url(url):
    from .downloader import MediaError
    import requests

    checked = validate_url(url)
    normalized = normalize_url(checked.url)
    if not short_link(normalized):
        return normalized
    with requests.Session() as session:
        session.trust_env = False
        session.headers["User-Agent"] = "facebookexternalhit/1.1"
        for hop in range(MAX_REDIRECTS + 1):
            with session.get(
                checked.url, allow_redirects=False, stream=True, timeout=20
            ) as response:
                response.raise_for_status()
                if response.status_code not in (301, 302, 303, 307, 308):
                    raise MediaError(
                        "no_media", "TikTok ไม่ส่งปลายทางของลิงก์สั้น กรุณาคัดลอกลิงก์เต็มของโพสต์"
                    )
                location = response.headers.get("Location")
                if not location:
                    raise MediaError("no_media", "ลิงก์สั้น TikTok ไม่มีปลายทาง กรุณาใช้ลิงก์เต็ม")
                checked = validate_redirect(checked, location, hop=hop + 1)
            if not is_tiktok(checked.url):
                raise MediaError("tiktok_url", "ลิงก์สั้นเปลี่ยนไปเว็บไซต์อื่น กรุณาใช้ลิงก์โพสต์ TikTok โดยตรง")
            normalized = normalize_url(checked.url)
            if not short_link(normalized):
                return normalized
    raise MediaError("redirect_limit", "ลิงก์ TikTok เปลี่ยนเส้นทางหลายครั้งเกินไป")
