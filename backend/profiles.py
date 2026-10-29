"""Bounded Instagram profile pagination and downloads in disposable workers."""

import json
import re
import shutil
from urllib.parse import urlsplit
import zipfile
import base64

from .settings import settings


def encode_cursor(after, username, document, providers):
    payload = json.dumps(
        [after, username.lower(), document, providers], separators=(",", ":")
    ).encode()
    encoded = "ig1." + base64.urlsafe_b64encode(payload).decode().rstrip("=")
    if len(encoded) > 4096:
        from .downloader import MediaError

        raise MediaError("cursor", "ข้อมูลหน้าถัดไปมีขนาดใหญ่เกินกำหนด กรุณาแบ่งอ่านโพสต์ใหม่")
    return encoded


def decode_cursor(cursor, username):
    from .downloader import MediaError

    try:
        if not cursor.startswith("ig1.") or len(cursor) > 4096:
            raise ValueError()
        after, owner, document, providers = json.loads(
            base64.urlsafe_b64decode(cursor[4:] + "=" * (-len(cursor[4:]) % 4))
        )
        if (
            owner != username.lower()
            or not isinstance(after, str)
            or not after
            or len(after) > 2048
            or not isinstance(document, str)
            or not re.fullmatch(r"[0-9]{1,30}", document)
            or not isinstance(providers, list)
            or len(providers) > 32
            or any(
                not isinstance(p, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,100}", p)
                for p in providers
            )
        ):
            raise ValueError()
        return after, document, providers
    except (ValueError, TypeError, UnicodeError):
        raise MediaError("cursor", "ข้อมูลหน้าถัดไปไม่ถูกต้อง กรุณาตรวจสอบโปรไฟล์ใหม่") from None


def script_urls(page):
    from html import unescape

    candidates = re.findall(
        r'https://[^"\s<>\\]+', page.replace("\\/", "/").replace("\\u0026", "&")
    )
    urls = []
    for candidate in candidates:
        candidate = unescape(candidate)
        parts = urlsplit(candidate)
        host = parts.hostname or ""
        if (
            (host == "static.cdninstagram.com" or host.endswith(".fbcdn.net"))
            and parts.path.startswith("/rsrc.php/")
            and parts.path.endswith(".js")
            and not parts.username
            and not parts.password
            and parts.port in (None, 443)
            and candidate not in urls
        ):
            urls.append(candidate)
    return urls[:1000]


def query_info(ext, opname, path):
    from .downloader import MediaError

    page = ext.cache(ext.api._webpage, path)
    document = None
    providers = []
    total = 0
    name = re.escape(opname)
    for url in script_urls(page):
        script = ext.request(url, interval=False).text
        if len(script) > 8 * 1024 * 1024:
            raise MediaError("metadata_limit", "ข้อมูลโปรไฟล์มีขนาดใหญ่เกินกำหนด")
        total += len(script)
        if total > 64 * 1024 * 1024:
            raise MediaError("metadata_limit", "ข้อมูล query โปรไฟล์มีขนาดใหญ่เกินกำหนด")
        match = re.search(
            rf'__d\("{name}_instagramRelayOperation",\[\],.{{0,2000}}?\bexports="([^"]+)',
            script,
        )
        if match:
            document = match[1]
        match = re.search(rf'__d\("{name}(?:\.graphql|\$Parameters)",\[([^\]]+)\]', script)
        if match:
            providers = re.findall(r'"([^" ]+)\.relayprovider"', match[1])
        if document and providers:
            return document, list(dict.fromkeys(providers))
    raise MediaError("platform_blocked", "Instagram ไม่ส่ง query ของรายการโพสต์ กรุณาลองใหม่ภายหลัง")


def graphql_connection(content, field):
    """Instagram can stream several JSON documents for one GraphQL response."""
    source = re.sub(r"^\s*for\s*\(\s*;\s*;\s*\)\s*;\s*", "", content.decode("utf-8"))
    decoder = json.JSONDecoder()
    data = {}
    while source.strip():
        document, end = decoder.raw_decode(source.lstrip())
        source = source.lstrip()[end:].lstrip()
        if not isinstance(document, dict) or not isinstance(document.get("data") or {}, dict):
            raise ValueError("invalid GraphQL data")
        data.update(document.get("data") or {})
        for patch in document.get("incremental") or []:
            path = patch.get("path") or []
            if not path or path[0] != field or len(path) > 32:
                continue
            target = data
            for key in path[:-1]:
                target = target[key]
            key = path[-1]
            if isinstance(target[key], dict) and isinstance(patch.get("data"), dict):
                target[key].update(patch["data"])
            else:
                target[key] = patch.get("data")
    connection = data[field]
    if "edges" not in connection:
        connection = next(v for v in connection.values() if isinstance(v, dict) and "edges" in v)
    return connection


def instagram_profile(url):
    parts = urlsplit(url)
    host = parts.hostname or ""
    if host != "instagram.com" and not host.endswith(".instagram.com"):
        return None
    match = re.fullmatch(r"/([A-Za-z0-9._]{1,30})/?", parts.path)
    if not match or match[1].lower() in {
        "p",
        "tv",
        "reel",
        "reels",
        "stories",
        "explore",
        "accounts",
        "direct",
        "about",
        "developer",
        "developers",
        "legal",
        "privacy",
        "challenge",
    }:
        return None
    return match[1]


def profile_page(url, cursor=None, *, use_cookies=False):
    from .downloader import MediaError, gallery_extractor, assert_media_access, has_login_session

    username = instagram_profile(url)
    if not username:
        raise MediaError("profile", "กรุณาใช้ลิงก์โปรไฟล์ Instagram")
    if cursor is not None and (not isinstance(cursor, str) or not 1 <= len(cursor) <= 4096):
        raise MediaError("cursor", "ข้อมูลหน้าถัดไปไม่ถูกต้อง กรุณาตรวจสอบโปรไฟล์ใหม่")
    after, cached_document, cached_providers = (
        decode_cursor(cursor, username) if cursor else (None, None, None)
    )
    ext = gallery_extractor(f"https://www.instagram.com/{username}/posts/", use_cookies=use_cookies)
    try:
        ext.login()
        user = ext.api.user_by_web(username)
        user["username"] = username
        ext._assign_user(user)
        variables = {
            "after": after,
            "before": None,
            "last": None,
            "first": 12,
            "username": username,
            "include_multi_captions": True,
            "data": {
                "count": 12,
                "include_relationship_info": True,
                "include_reel_media_seen_timestamp": True,
                "latest_besties_reel_media": True,
                "latest_reel_media": True,
            },
            "__relay_internal__pv__PolarisSEOIsCrawlerrelayprovider": False,
        }
        field = "xdt_api__v1__feed__user_timeline_graphql_connection"
        ext.api._extract_opname_info = (
            lambda name, path: (cached_document, cached_providers)
            if cached_document
            else query_info(ext, name, path)
        )
        headers, body = ext.api._prepare_graphql(
            "PolarisProfilePostsTabContentQuery_connection", variables, field
        )
        body = {
            key: body[key]
            for key in ("doc_id", "variables", "fb_dtsg", "lsd", "__a", "__d", "__user")
            if key in body
        }
        headers["Accept-Encoding"] = "gzip, deflate"
        response = ext.request(
            ext.root + "/graphql/query", method="POST", headers=headers, data=body
        )
        if len(response.content) > 8 * 1024 * 1024:
            raise MediaError("metadata_limit", "ข้อมูลโปรไฟล์มีขนาดใหญ่เกินกำหนด")
        try:
            connection = graphql_connection(response.content, field)
        except (ValueError, KeyError, TypeError, StopIteration, IndexError, RecursionError):
            raise MediaError(
                "platform_blocked", "Instagram ไม่ส่งรายการโพสต์ กรุณาตรวจสอบ session หรือลองใหม่ภายหลัง"
            ) from None
        posts = []
        seen = set()
        edges = connection.get("edges", [])
        if len(edges) > 50:
            raise MediaError("item_limit", "Instagram ส่งโพสต์ต่อหน้ามากเกินกำหนด")
        for edge in edges:
            post = edge.get("node") or {}
            assert_media_access(
                post,
                use_cookies=use_cookies,
                authenticated=has_login_session(ext.session.cookies, url),
            )
            code = post.get("code")
            if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", code):
                continue
            # Private-feed codes carry a suffix; gallery-dl resolves the same
            # post by the base shortcode when downloading with this session.
            identifier = code[:-28] if len(code) > 28 else code
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,28}", identifier):
                raise MediaError("profile", "Instagram ส่งรหัสโพสต์ที่ไม่รองรับ")
            if identifier in seen:
                continue
            seen.add(identifier)
            children = post.get("carousel_media") or [post]
            image = (children[0].get("image_versions2") or {}).get("candidates") or []
            caption = (post.get("caption") or {}).get("text") or f"โพสต์โดย @{username}"
            posts.append(
                {
                    "id": "post-" + identifier,
                    "type": "post",
                    "title": str(caption)[:200],
                    "url": f"https://www.instagram.com/p/{code}/",
                    "thumbnail": image[0].get("url") if image else None,
                    "media_count": len(children),
                    "has_video": any(item.get("media_type") == 2 for item in children),
                    "qualities": [],
                }
            )
        page_info = connection.get("page_info") or {}
        next_cursor = page_info.get("end_cursor") if page_info.get("has_next_page") else None
        if page_info.get("has_next_page") and (
            not isinstance(next_cursor, str)
            or not next_cursor
            or len(next_cursor) > 4096
            or next_cursor == after
        ):
            raise MediaError("cursor", "Instagram ส่งหน้าซ้ำ กรุณาลองใหม่ภายหลัง")
        if next_cursor:
            next_cursor = encode_cursor(
                next_cursor,
                username,
                body["doc_id"],
                [
                    key[len("__relay_internal__pv__") : -len("relayprovider")]
                    for key in json.loads(body["variables"])
                    if key.startswith("__relay_internal__pv__")
                ],
            )
        return {
            "type": "profile",
            "url": f"https://www.instagram.com/{username}/",
            "title": f"@{username}",
            "thumbnail": posts[0]["thumbnail"] if posts else None,
            "duration": None,
            "qualities": [],
            "items": posts,
            "images": [],
            "next_cursor": next_cursor,
            "page_size": 12,
        }
    finally:
        ext.session.close()


def inspect_profile(url, cursor=None):
    from .downloader import extract_public_first, has_login_session
    from .browser_session import worker_cookie_jar

    if settings.browser and has_login_session(worker_cookie_jar(), url):
        return profile_page(url, cursor, use_cookies=True)

    return extract_public_first(
        lambda link, use_cookies: profile_page(link, cursor, use_cookies=use_cookies), url
    )


def download_profile(url, selections, directory, emit, *, video_format="mkv"):
    from .downloader import MediaError, inspect_media, download_media, check_size

    if (
        not selections
        or len(selections) > settings.max_items
        or len({s["id"] for s in selections}) != len(selections)
    ):
        raise MediaError("selection", "กรุณาเลือกโพสต์โดยไม่เลือกซ้ำ และไม่เกินจำนวนที่กำหนด")
    for selection in selections:
        if not re.fullmatch(r"post-[A-Za-z0-9_-]{1,28}", selection["id"]):
            raise MediaError("selection", "รายการโพสต์ไม่ถูกต้อง กรุณาตรวจสอบโปรไฟล์ใหม่")
    from .tiktok_profiles import tiktok_profile

    tiktok_user = tiktok_profile(url)
    output = directory / "profile.zip"
    file_count = 0
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for index, selection in enumerate(selections):
            emit(
                {
                    "event": "progress",
                    "phase": "inspecting",
                    "progress": round(index / len(selections) * 95, 1),
                }
            )
            post_url = f"https://www.instagram.com/p/{selection['id'][5:]}/"
            if tiktok_user:
                if not selection["id"][5:].isdigit():
                    raise MediaError("selection", "รหัสโพสต์ TikTok ไม่ถูกต้อง")
                post_url = f"https://www.tiktok.com/@{tiktok_user}/video/{selection['id'][5:]}"
            inspected = inspect_media(post_url, use_session_first=True)
            items = inspected[0]["items"]
            file_count += len(items)
            if file_count > settings.max_items:
                raise MediaError(
                    "item_limit", "สื่อรวมในโพสต์ที่เลือกเกินขีดจำกัด กรุณาแบ่งดาวน์โหลดเป็นชุดเล็กลง"
                )
            choices = []
            for item in items:
                choice = {"id": item["id"]}
                if item["type"] == "video":
                    qualities = [q["id"] for q in item["qualities"] if q["id"] != "mp3"]
                    if not qualities:
                        raise MediaError(
                            "no_media", "โพสต์มีคลิปที่ยังไม่รองรับ กรุณาดาวน์โหลดโพสต์นี้แยกต่างหาก"
                        )
                    choice["quality"] = "best"
                choices.append(choice)
            folder = directory / f"post-{index + 1:03}"
            folder.mkdir()

            def progress(event):
                emit(
                    dict(
                        event,
                        progress=round(
                            (index + event.get("progress", 0) / 100) / len(selections) * 95, 1
                        ),
                    )
                )
                check_size(directory)

            path = download_media(
                post_url, choices, folder, progress, inspected=inspected, video_format=video_format
            )
            prefix = selection["id"] + "/"
            if path.suffix == ".zip":
                with zipfile.ZipFile(path) as source:
                    for member in source.infolist():
                        with (
                            source.open(member) as incoming,
                            archive.open(prefix + member.filename, "w") as outgoing,
                        ):
                            shutil.copyfileobj(incoming, outgoing, 65536)
                        check_size(directory)
            else:
                archive.write(path, prefix + path.name)
                check_size(directory)
            shutil.rmtree(folder)
    check_size(directory)
    return output
