"""One bounded TikTok profile page using gallery-dl's guarded transport."""

import base64
import hashlib
import json
import re
from urllib.parse import urlsplit

from .tiktok import is_tiktok


def tiktok_profile(url):
    if not is_tiktok(url):
        return None
    match = re.fullmatch(r"/@([A-Za-z0-9._]{1,24})/?", urlsplit(url).path)
    return match[1] if match else None


def encode_cursor(username, mode, position, fingerprint):
    return "tt1." + base64.urlsafe_b64encode(
        json.dumps([username.lower(), mode, position, fingerprint]).encode()
    ).decode().rstrip("=")


def decode_cursor(cursor, username):
    from .downloader import MediaError

    try:
        if not isinstance(cursor, str) or not cursor.startswith("tt1.") or len(cursor) > 512:
            raise ValueError()
        owner, mode, position, fingerprint = json.loads(
            base64.urlsafe_b64decode(cursor[4:] + "=" * (-len(cursor[4:]) % 4))
        )
        if (
            owner != username.lower()
            or mode not in ("posts", "creator")
            or type(position) is not int
            or not 0 < position < 10**16
            or not isinstance(fingerprint, str)
            or not re.fullmatch("[a-f0-9]{64}", fingerprint)
        ):
            raise ValueError()
        return mode, position, fingerprint
    except (ValueError, TypeError, UnicodeError):
        raise MediaError("cursor", "ข้อมูลหน้าถัดไปไม่ถูกต้อง กรุณาตรวจสอบโปรไฟล์ใหม่") from None


def profile_page(url, cursor=None, *, use_cookies=False):
    from gallery_dl.extractor.tiktok import TiktokPostItemListRequest, TiktokCreatorItemListRequest
    from .downloader import MediaError, gallery_extractor, has_login_session, assert_media_access

    username = tiktok_profile(url)
    if not username:
        raise MediaError("profile", "กรุณาใช้ลิงก์โปรไฟล์ TikTok")
    canonical = f"https://www.tiktok.com/@{username}"
    mode, position, previous = decode_cursor(cursor, username) if cursor else ("posts", 0, None)
    ext = gallery_extractor(canonical + "/posts", use_cookies=use_cookies)
    try:
        original_request = ext.request

        def bounded_request(*args, **kwargs):
            response = original_request(*args, **kwargs)
            if len(response.content) > 8 * 1024 * 1024:
                raise MediaError("metadata_limit", "ข้อมูลโปรไฟล์มีขนาดใหญ่เกินกำหนด")
            return response

        ext.request = bounded_request
        detail = ext._extract_rehydration_data(canonical).get("webapp.user-detail") or {}
        user_info = detail.get("userInfo") or {}
        user = user_info.get("user") or {}
        status = detail.get("statusCode") or 0
        if status == 10231:
            raise MediaError("region_restricted", "TikTok จำกัดการเข้าถึงโปรไฟล์นี้ในภูมิภาคของคุณ")
        if status in (10204, 10221):
            raise MediaError("no_media", "ไม่พบโปรไฟล์ TikTok นี้")
        authenticated = use_cookies and has_login_session(ext.session.cookies, url)
        private = bool(user.get("privateAccount") or status == 10222)
        if private:
            assert_media_access(
                {"availability": "private"}, use_cookies=use_cookies, authenticated=authenticated
            )
        elif status:
            raise MediaError("platform_blocked", "TikTok ไม่ส่งข้อมูลโปรไฟล์ กรุณาลองใหม่ภายหลัง")
        if str(user.get("uniqueId", "")).lower() != username.lower():
            raise MediaError("profile", "TikTok ส่งข้อมูลไม่ตรงกับโปรไฟล์ที่ขอ")
        sec_uid = user.get("secUid")
        if not isinstance(sec_uid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", sec_uid):
            raise MediaError("platform_blocked", "TikTok ไม่ส่งรหัสโปรไฟล์ กรุณาลองใหม่ภายหลัง")
        count = (user_info.get("stats") or user_info.get("statsV2") or {}).get("videoCount")
        if not private and not cursor and count is not None and str(count) == "0":
            return page_result(canonical, username, [], None)
        # Only the first page may change endpoint. Later cursors keep their original semantics.
        modes = [mode, "creator"] if not cursor and mode == "posts" else [mode]
        data = None
        for mode in modes:
            request = (
                TiktokPostItemListRequest if mode == "posts" else TiktokCreatorItemListRequest
            )(None)
            page_cursor = request.cursor_type({"post_item_list_request_type": "0"})()
            if position:
                page_cursor.cursor = position
            query = {"secUid": sec_uid, "count": "15"}
            query.update(
                {"post_item_list_request_type": "0", "needPinnedItemIds": "false"}
                if mode == "posts"
                else {"type": "1"}
            )
            try:
                data, parameters = request._request_data(ext, page_cursor, query)
                if not isinstance(data, dict) or data.get("statusCode", 0) != 0:
                    raise ValueError()
                if not isinstance(data.get("itemList"), list):
                    raise ValueError()
                flag = "hasMore" if mode == "posts" else "hasMorePrevious"
                if (
                    flag not in data
                    or type(data[flag]) not in (int, bool)
                    or data[flag] not in (0, 1)
                ):
                    raise ValueError()
                break
            except (ValueError, KeyError, TypeError):
                data = None
        if data is None:
            if private:
                raise MediaError(
                    "private",
                    "TikTok ไม่ส่งรายการของบัญชีส่วนตัวนี้ กรุณาตรวจสอบว่า session ตรงกับบัญชี Chrome ที่ดูโพสต์ได้",
                )
            raise MediaError("platform_blocked", "TikTok ไม่ส่งรายการโพสต์ กรุณาลองใหม่ภายหลัง")
        rows = data["itemList"]
        if len(rows) > 50:
            raise MediaError("item_limit", "TikTok ส่งโพสต์ต่อหน้ามากเกินกำหนด")
        posts, seen = [], set()
        for post in rows:
            identifier = str(post.get("id", ""))
            author = post.get("author") or {}
            if not re.fullmatch("[0-9]{1,28}", identifier):
                raise MediaError("profile", "TikTok ส่งรหัสโพสต์ที่ไม่รองรับ")
            if str(author.get("uniqueId", "")).lower() != username.lower():
                raise MediaError("profile", "TikTok ส่งโพสต์ของบัญชีอื่น กรุณาลองใหม่ภายหลัง")
            if identifier in seen:
                continue
            seen.add(identifier)
            if post.get("privateItem"):
                assert_media_access(
                    {"availability": "private"},
                    use_cookies=use_cookies,
                    authenticated=authenticated,
                )
            if any(post.get(k) for k in ("isPaidContent", "isPaidVideo", "isPaidCollection")) or (
                post.get("video") or {}
            ).get("isDRM"):
                continue
            images = (post.get("imagePost") or {}).get("images") or []
            video = post.get("video") or {}
            cover = video.get("cover") or video.get("originCover")
            if images:
                cover = ((images[0].get("imageURL") or {}).get("urlList") or [None])[0]
            posts.append(
                {
                    "id": "post-" + identifier,
                    "type": "post",
                    "title": str(post.get("desc") or f"โพสต์โดย @{username}")[:200],
                    "url": f"{canonical}/video/{identifier}",
                    "thumbnail": cover,
                    "media_count": len(images) if images else 1,
                    "has_video": not bool(images),
                    "qualities": [],
                }
            )
        fingerprint = hashlib.sha256(",".join(sorted(seen)).encode()).hexdigest()
        if rows and fingerprint == previous:
            raise MediaError("cursor", "TikTok ส่งหน้าซ้ำ กรุณาลองใหม่ภายหลัง")
        more = data["hasMore" if mode == "posts" else "hasMorePrevious"]
        if not rows and not more and private:
            raise MediaError(
                "private",
                "TikTok ไม่ส่งโพสต์ของบัญชีส่วนตัวนี้ กรุณาตรวจสอบ session และสิทธิ์ใน Chrome หรือใช้ลิงก์โพสต์แต่ละอัน",
            )
        if not rows and not more and not cursor and str(count) != "0":
            raise MediaError(
                "platform_blocked", "TikTok ไม่ส่งโพสต์ แม้โปรไฟล์อาจยังมีโพสต์ กรุณาลองใหม่ภายหลัง"
            )
        next_cursor = None
        if more:
            try:
                page_cursor.next_page(data, parameters)
                next_position = page_cursor.current_page()
                if (
                    type(next_position) is not int
                    or next_position == position
                    or next_position <= 0
                ):
                    raise ValueError()
                next_cursor = encode_cursor(username, mode, next_position, fingerprint)
            except (ValueError, KeyError, TypeError, IndexError):
                raise MediaError("cursor", "TikTok ไม่ส่งหน้าถัดไปที่ถูกต้อง กรุณาลองใหม่ภายหลัง") from None
        return page_result(canonical, username, posts, next_cursor)
    finally:
        ext.session.close()


def page_result(url, username, posts, cursor):
    return {
        "type": "profile",
        "platform": "TikTok",
        "url": url,
        "title": f"@{username}",
        "thumbnail": posts[0]["thumbnail"] if posts else None,
        "duration": None,
        "qualities": [],
        "items": posts,
        "images": [],
        "next_cursor": cursor,
        "page_size": 15,
    }


def inspect_profile(url, cursor=None):
    from .browser_session import worker_cookie_jar, has_worker_session
    from .downloader import extract_public_first
    from .settings import settings

    if settings.browser and has_worker_session() and any(worker_cookie_jar()):
        return profile_page(url, cursor, use_cookies=True)
    return extract_public_first(
        lambda link, use_cookies: profile_page(link, cursor, use_cookies=use_cookies), url
    )
