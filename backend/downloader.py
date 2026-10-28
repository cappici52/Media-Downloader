"""Library adapters, used exclusively inside backend.worker."""

import shutil
import subprocess
import zipfile
import re
from urllib.parse import urlsplit, urlunsplit
from functools import lru_cache
import json

from .settings import settings
from .validators import URLValidationError, validate_url, validate_network_url
from .browser_session import has_worker_session, worker_cookie_jar
from .tiktok import is_tiktok


class MediaError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def friendly_error(error):
    if isinstance(error, (MediaError, URLValidationError)):
        return {"code": error.code, "message": str(error)}
    text = (type(error).__name__ + " " + str(error)).lower()
    cause = error.__cause__ or error.__context__
    if cause:
        text += " " + str(cause).lower()
    if "cookie" in text and any(
        word in text for word in ("could not copy", "locked", "permission denied")
    ):
        return {
            "code": "cookies_locked",
            "message": "อ่าน cookies ของเบราว์เซอร์ไม่ได้ เพราะไฟล์ถูกล็อก กรุณาปิดเบราว์เซอร์ทุกหน้าต่างแล้วลองใหม่",
        }
    if any(
        word in text for word in ("dpapi", "decrypt", "app-bound", "unsupported cookie version")
    ):
        return {
            "code": "cookies_decryption",
            "message": "ถอดรหัส cookies ของ Chrome ไม่ได้ แม้ล็อกอินแล้ว อาจต้องใช้ Firefox ในเครื่องแทน",
        }
    if any(word in text for word in ("paywall", "premium_only", "subscriber_only")):
        return {"code": "paywall", "message": "ยังไม่รองรับเนื้อหาหลัง paywall หรือสมาชิกแบบเสียเงิน"}
    if "drm" in text:
        return {"code": "drm", "message": "ไม่รองรับสื่อที่มี DRM"}
    if any(
        word in text for word in ("private", "protected", "not available to you", "followers only")
    ):
        return {"code": "private", "message": "บัญชีที่ล็อกอินยังไม่มีสิทธิ์เข้าถึงโพสต์นี้ หรือ session หมดอายุ"}
    if any(
        word in text
        for word in (
            "login",
            "log in",
            "sign in",
            "authentication",
            "authorization",
            "age-restricted",
        )
    ):
        return {"code": "login_required", "message": "ต้องล็อกอิน เว็บไซต์อาจไม่อนุญาตให้ดึงโพสต์นี้"}
    if "cookie" in text:
        return {
            "code": "cookies_unavailable",
            "message": "อ่าน cookies จากเบราว์เซอร์ไม่ได้ กรุณาตรวจสอบเบราว์เซอร์ที่ตั้งค่าไว้",
        }
    if any(word in text for word in ("403", "429", "blocked", "captcha", "bot", "challenge")):
        return {"code": "platform_blocked", "message": "แพลตฟอร์มบล็อกการดึงข้อมูล กรุณาลองใหม่ภายหลัง"}
    if any(
        word in text
        for word in (
            "unsupported",
            "not found",
            "notfound",
            "404",
            "no video",
            "unavailable",
            "no suitable",
        )
    ):
        return {"code": "no_media", "message": "ไม่พบวิดีโอหรือรูปในลิงก์นี้ หรือเนื้อหาถูกลบแล้ว"}
    if any(word in text for word in ("timeout", "timed out", "network", "connection", "resolve")):
        return {"code": "network", "message": "เชื่อมต่อเว็บไซต์ไม่ได้ กรุณาลองใหม่อีกครั้ง"}
    return {
        "code": "extract_failed",
        "message": "ดึงข้อมูลไม่สำเร็จ ลองอัปเดต yt-dlp และ gallery-dl แล้วตรวจสอบลิงก์อีกครั้ง",
    }


class QuietLogger:
    def debug(self, message, *args, **kwargs):
        pass

    def info(self, message, *args, **kwargs):
        pass

    def warning(self, message, *args, **kwargs):
        pass

    def error(self, message, *args, **kwargs):
        pass

    def traceback(self, error):
        pass


def ydl_options(*, use_cookies=True):
    options = {
        "quiet": True,
        "no_warnings": True,
        "logger": QuietLogger(),
        "noplaylist": True,
        "playlistend": settings.max_items,
        "socket_timeout": 20,
        "retries": 1,
        "fragment_retries": 1,
        "proxy": "",
        "cachedir": False,
        "ignoreconfig": True,
        "hls_prefer_native": True,
        "external_downloader": {"default": "native"},
        "fixup": "never",
        "postprocessors": [],
        "skip_unavailable_fragments": False,
        "max_filesize": settings.max_bytes,
        "overwrites": False,
        "js_runtimes": {"node": {}},
    }
    if settings.browser and use_cookies:
        if settings.browser not in (
            "chrome",
            "chromium",
            "edge",
            "firefox",
            "brave",
            "opera",
            "vivaldi",
            "safari",
        ):
            raise MediaError("browser", "การตั้งค่าเบราว์เซอร์สำหรับ cookies ไม่ถูกต้อง")
        if has_worker_session():
            options["_cached_browser_session"] = True
        else:
            options["cookiesfrombrowser"] = (settings.browser,)
    return options


def twitter_public_scope(result):
    """Preserve explicit X visibility evidence without treating missing fields as public."""
    if result.get("__typename") != "Tweet":
        return None
    legacy = result.get("legacy") or {}
    if paid_media(result) or paid_media(legacy):
        return "subscriber_only"
    user = ((result.get("core") or {}).get("user_results") or {}).get("result") or {}
    protected = (user.get("privacy") or {}).get(
        "protected", (user.get("legacy") or {}).get("protected")
    )
    scope = "private" if protected is True else "public" if protected is False else None
    for source in (result, legacy):
        for key, value in source.items():
            if value and any(
                marker in key.lower()
                for marker in (
                    "exclusive",
                    "subscription",
                    "subscriber",
                    "super_followers",
                    "trusted_friends",
                    "limited_action",
                    "community",
                )
            ):
                scope = None
    for child in (result.get("quoted_status_result"), legacy.get("retweeted_status_result")):
        if child:
            child_scope = twitter_public_scope(child.get("result") or {})
            if child_scope == "subscriber_only":
                return child_scope
            if child_scope != "public":
                scope = child_scope if child_scope == "private" else None
    return scope


def make_ydl(options=None):
    from yt_dlp import YoutubeDL
    from yt_dlp.networking._urllib import UrllibRH
    from yt_dlp.extractor.twitter import TwitterIE
    from yt_dlp.extractor.facebook import FacebookIE

    class FacebookStoryIE(FacebookIE):
        _VALID_URL = r"https?://(?:[\w-]+\.)?facebook\.com/stories/[0-9]+/(?P<id>[A-Za-z0-9_=-]+)/?"

        def _real_extract(self, url):
            from .facebook_story import video_page

            card, _ = facebook_story_data(
                url, use_cookies=bool(self._downloader.params.get("_story_cookies"))
            )
            reject_unsupported_media(card)
            self._story_url = url
            self._story_page = video_page(card)
            if not self._story_page:
                raise MediaError("no_media", "Story นี้ไม่มีวิดีโอ")
            return self._extract_from_url(url, self._match_id(url))

        def _download_webpage(self, url, *args, **kwargs):
            if url == getattr(self, "_story_url", None):
                return self._story_page
            return super()._download_webpage(url, *args, **kwargs)

    class ScopedTwitterIE(TwitterIE):
        @classmethod
        def ie_key(cls):
            return "Twitter"

        def _graphql_to_legacy(self, data, twid):
            self._media_scope = twitter_public_scope(
                (data.get("tweetResult") or {}).get("result") or {}
            )
            return super()._graphql_to_legacy(data, twid)

        def _real_extract(self, url):
            result = super()._real_extract(url)
            scope = getattr(self, "_media_scope", None)
            if scope and not result.get("availability"):
                result["availability"] = scope
            return result

    class GuardedYoutubeDL(YoutubeDL):
        def build_request_director(self, handlers, preferences=None):
            # Native curl/impersonation transports bypass Python's socket guard.
            return super().build_request_director([UrllibRH], preferences=[])

    params = dict(options or ydl_options())
    cached = params.pop("_cached_browser_session", False)
    ydl = GuardedYoutubeDL(params)
    if cached:
        for cookie in worker_cookie_jar():
            ydl.cookiejar.set_cookie(cookie)
    ydl.add_info_extractor(ScopedTwitterIE(ydl))
    ydl.add_info_extractor(FacebookStoryIE(ydl))
    return ydl


def disable_external_downloaders():
    from yt_dlp.downloader.external import FFmpegFD

    def denied(*args, **kwargs):
        raise MediaError("unsupported_protocol", "รูปแบบสื่อนี้ต้องใช้การเชื่อมต่อที่ไม่รองรับ")

    # Native HLS can fall back to ffmpeg even with hls_prefer_native enabled.
    FFmpegFD.real_download = denied


def allowed_format(fmt):
    return (
        fmt.get("protocol") in ("http", "https", "http_dash_segments", "m3u8_native")
        and not fmt.get("has_drm")
        and fmt.get("url", "").startswith(("https://", "http://"))
    )


def paid_media(metadata):
    if metadata.get("availability") in ("premium_only", "subscriber_only"):
        return True
    if any(
        metadata.get(key)
        for key in (
            "is_paid_content",
            "is_subscription_only",
            "super_followers_only",
            "exclusive_tweet_info",
        )
    ):
        return True
    for key in ("subscription", "subscription_media_visibility"):
        value = metadata.get(key)
        if value and str(value).lower() not in ("public", "all", "everyone"):
            return True
    return False


def reject_unsupported_media(metadata):
    if metadata.get("has_drm") or metadata.get("is_drm_protected"):
        raise MediaError("drm", "ไม่รองรับสื่อที่มี DRM")
    if paid_media(metadata):
        raise MediaError("paywall", "ยังไม่รองรับเนื้อหาหลัง paywall หรือสมาชิกแบบเสียเงิน")


def has_login_session(jar, url):
    host = (urlsplit(url).hostname or "").lower()
    for domains, credentials in (
        (("x.com", "twitter.com"), ({"auth_token"},)),
        (("instagram.com",), ({"sessionid"},)),
        (("tiktok.com",), ({"sessionid"}, {"sessionid_ss"})),
        (("facebook.com", "fb.watch"), ({"c_user", "xs"},)),
        (("youtube.com", "youtu.be"), ({"SAPISID"}, {"__Secure-3PAPISID"}, {"SID"})),
    ):
        if any(host == domain or host.endswith("." + domain) for domain in domains):
            names = {
                cookie.name
                for cookie in jar
                if cookie.value
                and not cookie.is_expired()
                and any(
                    cookie.domain.lstrip(".").lower() == domain
                    or cookie.domain.lstrip(".").lower().endswith("." + domain)
                    for domain in domains
                )
            }
            return any(required <= names for required in credentials)
    return False


def assert_media_access(metadata, *, use_cookies, authenticated):
    reject_unsupported_media(metadata)
    # Successful extractor metadata is still required: provider access denials are
    # never caught or overridden here. A configured browser alone is not a login.
    if use_cookies and authenticated:
        return
    try:
        assert_public(metadata, use_cookies=False)
    except MediaError as error:
        if error.code == "private":
            raise MediaError(
                "login_required", "โพสต์ส่วนตัวต้องใช้ session ของบัญชีที่มีสิทธิ์ดู กรุณาเชื่อมต่อเบราว์เซอร์ที่ล็อกอินไว้"
            ) from None
        raise


def assert_public(metadata, *, use_cookies=True):
    reject_unsupported_media(metadata)
    visibility = metadata.get("availability") or metadata.get("visibility")
    if visibility in ("private", "premium_only", "subscriber_only", "needs_auth", "followers"):
        raise MediaError("private", "รองรับเฉพาะเนื้อหาสาธารณะเท่านั้น")
    public = visibility in ("public", "unlisted")
    for source in (metadata, metadata.get("user"), metadata.get("owner"), metadata.get("author")):
        if not isinstance(source, dict):
            continue
        for key in ("is_private", "private", "protected"):
            if source.get(key) is True:
                raise MediaError("private", "โพสต์เป็นส่วนตัว รองรับเฉพาะเนื้อหาสาธารณะเท่านั้น")
            if source.get(key) is False:
                public = True
    if settings.browser and use_cookies and not public:
        raise MediaError(
            "public_unverified", "ยืนยันไม่ได้ว่าโพสต์นี้เป็นสาธารณะ จึงไม่ใช้ cookies เพื่อดาวน์โหลดโพสต์นี้"
        )


def quality_options(formats):
    heights = sorted(
        {
            int(f["height"])
            for f in formats
            if allowed_format(f) and f.get("height") and f.get("vcodec") != "none"
        }
    )
    options = [{"id": f"{height}p", "label": f"{height}p"} for height in heights]
    if any(allowed_format(f) and f.get("acodec") not in (None, "none") for f in formats):
        options.append({"id": "mp3", "label": "เสียงอย่างเดียว MP3"})
    return options


def video_info(url, *, use_cookies=True, instagram_product=None):
    if instagram_story(url) and use_cookies and instagram_product is None:
        instagram_product = instagram_story_product(url)
    elif settings.browser and use_cookies and instagram_post_url(url) and instagram_product is None:
        instagram_product = instagram_authenticated_product(url)
    options = ydl_options(use_cookies=use_cookies)
    if facebook_story(url):
        options["_story_cookies"] = use_cookies
    with make_ydl(options) as ydl:
        if is_tiktok(url):
            from .tiktok import post_data
            from yt_dlp.extractor.tiktok import TikTokIE

            post = post_data(url, use_cookies=use_cookies)
            if "imagePost" in post:
                return {"title": str(post.get("desc") or "TikTok")}, []
            from http.cookiejar import Cookie

            for row in post.get("_cookie_rows", []):
                ydl.cookiejar.set_cookie(Cookie(**row))
            raw = TikTokIE(ydl)._parse_aweme_video_web(post, url, str(post["id"]))
            raw.update({"extractor": "TikTok", "extractor_key": "TikTok", "webpage_url": url})
            raw["http_headers"] = dict(post.get("_media_headers") or {"Referer": url})
            for fmt in raw.get("formats") or []:
                fmt.setdefault("protocol", urlsplit(fmt.get("url", "")).scheme)
                fmt.setdefault("ext", "mp4")
            if raw.get("thumbnails"):
                raw["thumbnail"] = raw["thumbnails"][-1]["url"]
            # Use the normal yt-dlp result processing (including its rendition
            # checks), through GuardedYoutubeDL/UrllibRH inside the socket guard.
            raw = ydl.process_ie_result(raw, download=False)
            raw["formats"] = [
                f for f in reversed(raw.get("formats") or []) if f.get("__working") is not False
            ]
            raw["_preview_cookie_rows"] = post.get("_cookie_rows", [])
        elif instagram_product is None:
            raw = ydl.extract_info(
                url, download=False, **({"ie_key": "FacebookStory"} if facebook_story(url) else {})
            )
        else:
            from yt_dlp.extractor.instagram import InstagramIE

            raw = InstagramIE(ydl)._extract_product(instagram_product, get_comments=False)
            for entry in raw.get("entries") or [raw]:
                for fmt in entry.get("formats", []):
                    fmt.setdefault("protocol", urlsplit(fmt["url"]).scheme)
                    fmt.setdefault("ext", "mp4")
                    fmt["vcodec"] = fmt.get("vcodec") or "unknown"
                    fmt["acodec"] = fmt.get("acodec") or "unknown"
                if entry.get("thumbnails"):
                    entry["thumbnail"] = entry["thumbnails"][-1]["url"]
        reject_unsupported_media(raw)
        entries = list(raw.get("entries") or [raw])
        videos = []
        for entry in entries:
            if not entry:
                continue
            if not entry.get("availability") and raw.get("availability"):
                entry = dict(entry, availability=raw["availability"])
            if entry.get("is_live") or entry.get("live_status") in ("is_live", "is_upcoming"):
                raise MediaError("live_not_supported", "ยังไม่รองรับวิดีโอถ่ายทอดสด กรุณาใช้วิดีโอที่จบแล้ว")
            assert_media_access(
                entry, use_cookies=use_cookies, authenticated=has_login_session(ydl.cookiejar, url)
            )
            if len(videos) >= settings.max_items:
                raise MediaError("item_limit", "โพสต์มีสื่อเกินจำนวนที่กำหนด")
            if (entry.get("duration") or 0) > settings.max_duration:
                raise MediaError("duration_limit", "วิดีโอยาวเกินเวลาที่กำหนด")
            qualities = quality_options(entry.get("formats") or [entry])
            if is_tiktok(url) and not any(
                f.get("height") or f.get("vcodec") not in (None, "none")
                for f in entry.get("formats", [])
            ):
                continue  # A photo slideshow soundtrack is not a video item.
            if qualities:
                videos.append({"raw": entry, "qualities": qualities, "use_cookies": use_cookies})
        return raw, videos


def gallery_extractor(url, *, use_cookies=True, instagram_product=None, tiktok_product=None):
    from gallery_dl import config, extractor

    config.clear()
    config.set(("cache",), "file", ":memory:")
    config.set(("extractor",), "retries", 1)
    config.set(("extractor",), "timeout", 20)
    config.set(("extractor",), "proxy", "")
    if is_tiktok(url):
        config.set(("extractor", "tiktok"), "audio", False)
        config.set(("extractor", "tiktok"), "covers", False)
    if settings.browser and use_cookies:
        # gallery-dl uses its own local browser-cookie loader.
        config.set(("extractor",), "cookies", [settings.browser])
    if tiktok_product is not None:
        from gallery_dl.extractor.tiktok import TiktokPostExtractor
        import copy

        class PreparedTiktokPostExtractor(TiktokPostExtractor):
            def _extract_rehydration_data(self, *args, **kwargs):
                return {
                    "webapp.video-detail": {
                        "statusCode": 0,
                        "itemInfo": {"itemStruct": copy.deepcopy(tiktok_product)},
                    }
                }

        ext = PreparedTiktokPostExtractor.from_url(url)
    elif instagram_product is None:
        ext = extractor.find(url)
    else:
        from gallery_dl.extractor.instagram import InstagramPostExtractor

        class ProductInstagramPostExtractor(InstagramPostExtractor):
            def posts(self):
                return iter((instagram_product,))

        product_url = "https://www.instagram.com/p/Story/" if instagram_story(url) else url
        ext = ProductInstagramPostExtractor.from_url(product_url)
    if ext is None:
        raise MediaError("no_media", "ไม่พบรูปในลิงก์นี้")
    ext.log = QuietLogger()
    if use_cookies and settings.browser and has_worker_session():

        def load_cached_cookies(source):
            for cookie in worker_cookie_jar():
                ext.cookies.set_cookie(cookie)

        ext.cookies_load = load_cached_cookies
    # gallery-dl creates its Session lazily, not in extractor.find().
    ext.initialize()
    ext.session.trust_env = False
    return ext


def instagram_story(url):
    parts = urlsplit(url)
    host = parts.hostname or ""
    return (host == "instagram.com" or host.endswith(".instagram.com")) and bool(
        re.fullmatch(
            r"/stories/(?:highlights/[0-9]+|(?!(?:highlights|me)(?:/|$))[A-Za-z0-9._]+(?:/[0-9]+)?)/?",
            parts.path,
        )
    )


def instagram_story_product(url):
    """Read authorized Stories through gallery-dl's authenticated media API."""
    ext = gallery_extractor(url, use_cookies=True)
    try:
        if not has_login_session(ext.session.cookies, url):
            raise MediaError("login_required", "Story ต้องใช้ session Instagram ของบัญชีที่มีสิทธิ์ดู")
        ext.login()
        parts = urlsplit(url).path.strip("/").split("/")
        highlight = parts[1] == "highlights"
        single = len(parts) == 3 and not highlight
        if single:
            data = ext.api._call(f"/v1/media/{parts[2]}/info/")
        else:
            from gallery_dl.extractor.instagram import InstagramAPI

            story_path = "/" + "/".join(parts)

            class StoryAPI(InstagramAPI):
                # Read Story query IDs and tokens from the Story page itself;
                # the profile page need not include these operations.
                def _extract_fb_tokens(self, path):
                    return super()._extract_fb_tokens(story_path)

                def _extract_opname_info(self, opname, path):
                    return super()._extract_opname_info(opname, story_path)

            ext.api = StoryAPI(ext)
            if highlight:
                user_id = parts[2]
                reel_id = f"highlight:{user_id}"
            else:
                user = ext.api.user_by_web(parts[1])
                ext._assign_user(user)
                user_id = reel_id = user["id"]
            data = next(iter(ext.api.reels_media((reel_id,))), {})
        items = data.get("items") or []
        if not items:
            raise MediaError("story_unavailable", "ไม่พบ Story นี้ อาจหมดอายุ ถูกลบ หรือบัญชีไม่มีสิทธิ์ดู")
        if single:
            product = items[0]
        else:
            reject_unsupported_media(data)
            if len(items) > settings.max_items:
                raise MediaError("item_limit", "Story มีสื่อเกินจำนวนที่กำหนด")
            for item in items:
                reject_unsupported_media(item)
            product = {
                "pk": str(user_id),
                "code": "Story",
                "caption": None,
                "title": data.get("title") if highlight else None,
                "user": data.get("user") or items[0].get("user") or {},
                "taken_at": items[0].get("taken_at"),
                "carousel_media": items,
            }
        reject_unsupported_media(product)
        if len(product.get("carousel_media") or [product]) > settings.max_items:
            raise MediaError("item_limit", "Story มีสื่อเกินจำนวนที่กำหนด")
        return product
    finally:
        ext.session.close()


def image_info(url, *, use_cookies=True, instagram_product=None):
    from gallery_dl.extractor.common import Message

    if instagram_story(url) and use_cookies and instagram_product is None:
        instagram_product = instagram_story_product(url)

    if facebook_story(url):
        return facebook_story_images(url, use_cookies=use_cookies)

    tiktok_product = None
    if is_tiktok(url):
        from .tiktok import post_data

        tiktok_product = post_data(url, use_cookies=use_cookies)
    ext = gallery_extractor(
        url,
        use_cookies=use_cookies,
        instagram_product=instagram_product,
        tiktok_product=tiktok_product,
    )
    images = []
    for message in ext:
        if message[0] != Message.Url:
            continue  # Never recurse profile queues or delegate to another downloader.
        media_url, metadata = message[1:3]
        assert_media_access(
            metadata,
            use_cookies=use_cookies,
            authenticated=has_login_session(ext.session.cookies, url),
        )
        suffix = str(metadata.get("extension", "")).lower()
        if suffix not in ("jpg", "jpeg", "png", "webp", "gif", "avif"):
            continue
        validate_network_url(media_url)
        if len(images) >= settings.max_items:
            raise MediaError("item_limit", "โพสต์มีรูปเกินจำนวนที่กำหนด")
        images.append(
            {
                "url": media_url,
                "extension": suffix,
                "title": str(metadata.get("description") or metadata.get("title") or "รูปภาพ")[:300],
                "headers": {
                    key: value
                    for key, value in ext.session.headers.items()
                    if key.lower() not in ("cookie", "host")
                },
                "cookies": ext.session.cookies.copy(),
            }
        )
    return images


def instagram_shortcode(url):
    parts = urlsplit(url)
    host = parts.hostname or ""
    if host != "instagram.com" and not host.endswith(".instagram.com"):
        return None
    match = re.fullmatch(r"/(?:[^/]+/)?(?:p|tv|reels?)/([A-Za-z0-9_-]{1,28})/?", parts.path)
    return match[1] if match else None


def instagram_post_url(url):
    parts = urlsplit(url)
    host = parts.hostname or ""
    return (host == "instagram.com" or host.endswith(".instagram.com")) and bool(
        re.fullmatch(r"/(?:p|tv|reels?)/[A-Za-z0-9_-]{1,64}/?", parts.path)
    )


def instagram_authenticated_product(url):
    ext = gallery_extractor(url, use_cookies=True)
    try:
        if not has_login_session(ext.session.cookies, url):
            raise MediaError("login_required", "ต้องใช้ session Instagram ของบัญชีที่มีสิทธิ์ดูโพสต์นี้")
        ext.login()
        product = next(iter(ext.posts()), None)
        if not isinstance(product, dict):
            raise MediaError("no_media", "ไม่พบสื่อในโพสต์นี้ หรือบัญชีไม่มีสิทธิ์ดู")
        children = product.get("carousel_media") or [product]
        if len(children) > settings.max_items:
            raise MediaError("item_limit", "โพสต์มีสื่อเกินจำนวนที่กำหนด")
        for item in [product, *children]:
            reject_unsupported_media(item)
        return product
    finally:
        ext.session.close()


@lru_cache(maxsize=1)
def instagram_public_product(shortcode):
    """Read public media only, with a fresh anonymous session (no browser cookies).

    Public web query documented in gallery-dl issue #9564; Instagram may rotate
    this query ID. Keep the response bounded and never follow private-content hints.
    """
    import requests

    with requests.Session() as session:
        session.trust_env = False
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0",
                "X-IG-App-ID": "936619743392459",
                "Referer": "https://www.instagram.com/",
            }
        )
        with session.get("https://www.instagram.com/", timeout=20, stream=True) as response:
            response.raise_for_status()
        csrf = next((cookie.value for cookie in session.cookies if cookie.name == "csrftoken"), "")
        session.headers["X-CSRFToken"] = csrf
        with session.post(
            "https://www.instagram.com/graphql/query",
            data={
                "doc_id": "27128499623469141",
                "variables": json.dumps(
                    {
                        "shortcode": shortcode,
                        "__relay_internal__pv__PolarisAIGMMediaWebLabelEnabledrelayprovider": False,
                    }
                ),
            },
            timeout=20,
            stream=True,
        ) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body) > 8 * 1024 * 1024:
                    raise MediaError("metadata_limit", "ข้อมูลโพสต์มีขนาดใหญ่เกินกำหนด")
            try:
                data = json.loads(body)
                items = (
                    (data.get("data") or {})
                    .get("xdt_api__v1__media__shortcode__web_info", {})
                    .get("items", [])
                )
            except (ValueError, AttributeError):
                raise MediaError(
                    "platform_blocked", "Instagram ไม่ส่งข้อมูลโพสต์สาธารณะ กรุณาลองใหม่ภายหลัง"
                ) from None
    if not items or not isinstance(items[0], dict):
        raise MediaError("login_required", "Instagram ไม่เปิดข้อมูลโพสต์นี้แบบสาธารณะ อาจต้องล็อกอิน")
    product = items[0]
    assert_public(product, use_cookies=False)
    if len(product.get("carousel_media") or [product]) > settings.max_items:
        raise MediaError("item_limit", "โพสต์มีสื่อเกินจำนวนที่กำหนด")
    return product


def normalize_post_url(url):
    parts = urlsplit(url)
    if is_tiktok(url):
        from .tiktok import normalize_url

        return normalize_url(url)
    if facebook_story(url):
        return "https://www.facebook.com" + parts.path
    shortcode = instagram_shortcode(url)
    if shortcode:
        return f"https://www.instagram.com/p/{shortcode}/"
    host = parts.hostname or ""
    if any(host == domain or host.endswith("." + domain) for domain in ("x.com", "twitter.com")):
        path = re.sub(r"(/status/[0-9]+)/(?:photo|video)/[0-9]+/?$", r"\1", parts.path)
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))
    return url


def facebook_story(url):
    parts = urlsplit(url)
    host = parts.hostname or ""
    return (host == "facebook.com" or host.endswith(".facebook.com")) and bool(
        re.fullmatch(r"/stories/[0-9]+/[A-Za-z0-9_=-]+/?", parts.path)
    )


@lru_cache(maxsize=2)
def facebook_story_data(url, *, use_cookies):
    from .facebook_story import find_card, media_items, protected_media

    identifier = urlsplit(url).path.strip("/").split("/")[-1]
    with make_ydl(ydl_options(use_cookies=use_cookies)) as ydl:
        authenticated = has_login_session(ydl.cookiejar, url)
        page = ydl.get_info_extractor("Facebook")._download_webpage(url, identifier)
        try:
            card = find_card(page, identifier)
        except ValueError:
            raise MediaError("metadata_limit", "ข้อมูล Story มีขนาดใหญ่เกินกำหนด") from None
        if not card:
            if not authenticated:
                raise MediaError("login_required", "Facebook Story ต้องใช้ session ของบัญชีที่มีสิทธิ์ดู")
            raise MediaError(
                "story_unavailable", "ไม่พบ Facebook Story นี้ อาจหมดอายุ ถูกลบ หรือบัญชีไม่มีสิทธิ์ดู"
            )
        assert_media_access(card, use_cookies=use_cookies, authenticated=authenticated)
        media = media_items(card)
        if len(media) > settings.max_items:
            raise MediaError("item_limit", "Story มีสื่อเกินจำนวนที่กำหนด")
        for item in media:
            reject_unsupported_media(item)
            if protected_media(item):
                raise MediaError("drm", "ไม่รองรับสื่อที่มี DRM")
        return card, ydl.cookiejar


def facebook_story_images(url, *, use_cookies):
    from .facebook_story import media_items

    card, cookies = facebook_story_data(url, use_cookies=use_cookies)
    images = []
    for item in media_items(card):
        if item.get("__typename") != "Photo":
            continue
        image = item.get("image") or item.get("viewer_image") or {}
        media_url = image.get("uri")
        if not isinstance(media_url, str):
            continue
        validate_network_url(media_url)
        suffix = urlsplit(media_url).path.rsplit(".", 1)[-1].lower()
        if suffix not in ("jpg", "jpeg", "png", "webp"):
            suffix = "jpg"
        images.append(
            {
                "url": media_url,
                "extension": suffix,
                "title": "Facebook Story",
                "headers": {"Referer": "https://www.facebook.com/"},
                "cookies": cookies,
            }
        )
    return images


def extract_public_first(adapter, url):
    try:
        return adapter(url, use_cookies=False)
    except Exception as error:
        failure = error
        code = friendly_error(error)["code"]
        shortcode = instagram_shortcode(url)
        host = urlsplit(url).hostname or ""
        is_x = any(
            host == domain or host.endswith("." + domain) for domain in ("x.com", "twitter.com")
        )
        retry_codes = ("login_required", "private", "platform_blocked", "extract_failed")
        if shortcode or is_x or instagram_story(url) or facebook_story(url) or is_tiktok(url):
            retry_codes += ("no_media",)
        if shortcode and code in retry_codes:
            try:
                product = instagram_public_product(shortcode)
                return adapter(url, use_cookies=False, instagram_product=product)
            except Exception as fallback_error:
                if friendly_error(fallback_error)["code"] in (
                    "item_limit",
                    "metadata_limit",
                    "paywall",
                    "drm",
                ):
                    raise
                failure = fallback_error
        if not settings.browser or code not in retry_codes:
            if is_x and code == "no_media":
                raise MediaError(
                    "x_unavailable",
                    "X ไม่ส่งข้อมูลรูปหรือวิดีโอของโพสต์นี้ อาจไม่มีสื่อหรือถูกจำกัดการเข้าถึง ยังยืนยันไม่ได้ว่าโพสต์ถูกลบ",
                ) from None
            raise failure
    try:
        return adapter(url, use_cookies=True)
    except Exception as error:
        if is_x and friendly_error(error)["code"] == "no_media":
            raise MediaError(
                "x_unavailable",
                "X ไม่ส่งข้อมูลรูปหรือวิดีโอให้ session นี้ อาจไม่มีสื่อหรือถูกจำกัดการเข้าถึง ยังยืนยันไม่ได้ว่าโพสต์ถูกลบ",
            ) from None
        raise


def inspect_media(url, cursor=None, *, use_session_first=False):
    checked = validate_url(url)
    from .profiles import instagram_profile, inspect_profile
    from .tiktok_profiles import tiktok_profile, inspect_profile as inspect_tiktok_profile

    if tiktok_profile(checked.url):
        return inspect_tiktok_profile(checked.url, cursor), [], []
    if instagram_profile(checked.url):
        return inspect_profile(checked.url, cursor), [], []
    if cursor is not None:
        raise MediaError("cursor", "โหลดหน้าถัดไปได้เฉพาะลิงก์โปรไฟล์ Instagram หรือ TikTok")
    url = normalize_post_url(checked.url)
    if is_tiktok(url):
        from .tiktok import resolve_url

        url = resolve_url(url)
    tiktok_session = (
        is_tiktok(url) and settings.browser and has_worker_session() and any(worker_cookie_jar())
    )
    product = None
    authenticated = (
        use_session_first and settings.browser and has_login_session(worker_cookie_jar(), url)
    )
    if authenticated and instagram_post_url(url):
        product = instagram_authenticated_product(url)

    def inspect_adapter(adapter):
        if tiktok_session:
            return adapter(url, use_cookies=True)
        if authenticated:
            return adapter(
                url, use_cookies=True, **({"instagram_product": product} if product else {})
            )
        return extract_public_first(adapter, url)

    videos, images, failures = [], [], []
    raw = {}
    if not any(
        checked.hostname == domain or checked.hostname.endswith("." + domain)
        for domain in ("youtube.com", "youtu.be")
    ):
        try:
            images = inspect_adapter(image_info)
        except Exception as error:
            if friendly_error(error)["code"] in ("paywall", "drm"):
                raise
            failures.append(error)
    try:
        raw, videos = inspect_adapter(video_info)
    except Exception as error:
        if friendly_error(error)["code"] in ("paywall", "drm"):
            raise
        failures.append(error)
    if not videos and not images:
        priority = (
            "private",
            "cookies_locked",
            "cookies_decryption",
            "cookies_unavailable",
            "story_unavailable",
            "login_required",
            "platform_blocked",
            "public_unverified",
        )
        preferred = (
            min(
                failures,
                key=lambda error: priority.index(friendly_error(error)["code"])
                if friendly_error(error)["code"] in priority
                else len(priority),
            )
            if failures
            else None
        )
        raise preferred or (
            failures[-1] if failures else MediaError("no_media", "ไม่พบวิดีโอหรือรูปในลิงก์นี้")
        )
    if product:
        children = product.get("carousel_media") or [product]
        if len(images) + len(videos) != len(children) or len(videos) != sum(
            item.get("media_type") == 2 for item in children
        ):
            raise MediaError("incomplete_media", "อ่านสื่อในโพสต์นี้ได้ไม่ครบ กรุณาตรวจสอบโพสต์แยกแล้วลองใหม่")
    if len(videos) + len(images) > settings.max_items:
        raise MediaError("item_limit", "โพสต์มีสื่อเกินจำนวนที่กำหนด")
    items = []
    for index, video in enumerate(videos):
        entry = video["raw"]
        items.append(
            {
                "id": f"video-{index}",
                "type": "video",
                "title": str(entry.get("title") or "วิดีโอ")[:300],
                "thumbnail": entry.get("thumbnail"),
                "duration": entry.get("duration"),
                "qualities": video["qualities"],
                "_preview": video_preview(entry),
            }
        )
    for index, image in enumerate(images):
        items.append(
            {
                "id": f"image-{index}",
                "type": "image",
                "title": image["title"],
                "thumbnail": image["url"],
                "qualities": [],
            }
        )
    kind = "carousel" if len(items) > 1 else items[0]["type"]
    public = {
        "url": url,
        "type": kind,
        "title": str(raw.get("title") or items[0]["title"])[:300],
        "thumbnail": items[0]["thumbnail"],
        "duration": items[0].get("duration"),
        "qualities": items[0]["qualities"],
        "images": [i for i in items if i["type"] == "image"],
        "items": items,
    }
    return public, videos, images


def video_preview(entry):
    formats = [
        fmt
        for fmt in entry.get("formats", [entry])
        if allowed_format(fmt)
        and fmt.get("protocol") in ("http", "https")
        and fmt.get("ext") in ("mp4", "webm")
        and fmt.get("vcodec") != "none"
        and (fmt.get("filesize") or 0) <= settings.max_bytes
    ]
    if not formats:
        return None

    # Progressive MP4 with sound is the most widely playable browser preview.
    def score(fmt):
        height = fmt.get("height") or 0
        return (
            fmt.get("acodec") not in (None, "none"),
            fmt.get("ext") == "mp4",
            height <= 720,
            height if height <= 720 else -height,
        )

    fmt = max(formats, key=score)
    headers = dict(entry.get("http_headers") or {}) | dict(fmt.get("http_headers") or {})
    return {
        "url": fmt["url"],
        "headers": {
            key: value
            for key, value in headers.items()
            if key.lower() in ("user-agent", "referer", "origin")
        },
        "media_type": "video/mp4" if fmt["ext"] == "mp4" else "video/webm",
        "muted": fmt.get("acodec") == "none",
        "cookie_rows": entry.get("_preview_cookie_rows", [])
        if entry.get("extractor_key") == "TikTok"
        else [],
    }


def download_preview(url, directory):
    import requests

    validate_network_url(url)
    target = directory / "preview"
    with requests.Session() as session:
        session.trust_env = False
        with session.get(url, stream=True, timeout=15) as response:
            response.raise_for_status()
            kind = response.headers.get("Content-Type", "").split(";")[0].lower()
            if kind not in ("image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"):
                raise MediaError("preview", "ไม่สามารถแสดงตัวอย่างรูปนี้ได้")
            size = 0
            with target.open("wb") as stream:
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 12 * 1024 * 1024:
                        raise MediaError("preview", "รูปตัวอย่างมีขนาดใหญ่เกินไป")
                    stream.write(chunk)
    from PIL import Image, ImageOps
    import warnings

    Image.MAX_IMAGE_PIXELS = 20_000_000
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(target) as source:
                if source.format not in ("JPEG", "PNG", "WEBP", "GIF", "AVIF"):
                    raise MediaError("preview", "ชนิดไฟล์รูปตัวอย่างไม่รองรับ")
                image = ImageOps.exif_transpose(source)
                image.thumbnail((1280, 1280))
                image.convert("RGB").save(directory / "thumbnail.jpg", quality=85, optimize=True)
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise MediaError("preview", "ไม่สามารถแสดงตัวอย่างรูปนี้ได้") from None
    target.unlink()
    return {"filename": "thumbnail.jpg", "media_type": "image/jpeg"}


def check_size(directory):
    if sum(p.stat().st_size for p in directory.rglob("*") if p.is_file()) > settings.max_bytes:
        raise MediaError("size_limit", "ไฟล์รวมมีขนาดเกินที่กำหนด")


def transcode(inputs, output, audio=False):
    executable = shutil.which("ffmpeg")
    if not executable:
        raise MediaError("ffmpeg_missing", "ไม่พบ ffmpeg กรุณาติดตั้งก่อนดาวน์โหลดวิดีโอ")
    probe = shutil.which("ffprobe")
    if not probe:
        raise MediaError("ffmpeg_missing", "ไม่พบ ffprobe กรุณาติดตั้งชุด ffmpeg ให้ครบ")
    for path in inputs:
        result = subprocess.run(
            [
                probe,
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path.resolve()),
            ],
            capture_output=True,
            timeout=30,
            shell=False,
        )
        try:
            duration = float(result.stdout.strip())
        except ValueError:
            raise MediaError(
                "duration_unknown", "ตรวจสอบความยาววิดีโอไม่ได้ จึงไม่สามารถดาวน์โหลดได้"
            ) from None
        if result.returncode or not 0 < duration <= settings.max_duration:
            raise MediaError("duration_limit", "วิดีโอยาวเกินเวลาที่กำหนดหรือไม่มีข้อมูลความยาว")
    args = [executable, "-nostdin", "-v", "error", "-y"]
    for path in inputs:
        args += ["-protocol_whitelist", "file,pipe", "-i", str(path.resolve())]
    args += (
        ["-vn", "-codec:a", "libmp3lame", "-b:a", "192k"]
        if audio
        else ["-map", "0:v:0", "-map", "1:a:0" if len(inputs) > 1 else "0:a:0?", "-c", "copy"]
    )
    args += ["-fs", str(max(1, settings.max_bytes // 2)), str(output.resolve())]
    # Output cap is conservative; intermediates and final output share the quota.
    result = subprocess.run(args, capture_output=True, timeout=settings.timeout, shell=False)
    if result.returncode:
        raise MediaError("conversion_failed", "แปลงไฟล์ไม่สำเร็จ รูปแบบสื่ออาจไม่รองรับ")
    if output.stat().st_size >= settings.max_bytes // 2:
        output.unlink(missing_ok=True)
        raise MediaError("size_limit", "ไฟล์ที่แปลงมีขนาดเกินที่กำหนด")


def download_media(url, selections, directory, emit, *, inspected=None):
    import requests
    from .profiles import instagram_profile, download_profile
    from .tiktok_profiles import tiktok_profile

    if instagram_profile(url) or tiktok_profile(url):
        checked = validate_url(url)
        return download_profile(checked.url, selections, directory, emit)
    public, videos, images = inspected if inspected is not None else inspect_media(url)
    available = {item["id"]: item for item in public["items"]}
    if (
        not selections
        or len(selections) > settings.max_items
        or len({s["id"] for s in selections}) != len(selections)
    ):
        raise MediaError("selection", "กรุณาเลือกสื่ออย่างน้อยหนึ่งรายการและไม่เลือกซ้ำ")
    results = []
    for number, selection in enumerate(selections):
        item = available.get(selection["id"])
        if not item:
            raise MediaError("selection", "รายการสื่อเปลี่ยนไป กรุณาตรวจสอบลิงก์อีกครั้ง")
        base = directory / f"media-{number + 1:03}"
        if item["type"] == "image":
            image = images[int(item["id"].split("-")[1])]
            target = base.with_suffix("." + image["extension"])
            with requests.Session() as session:
                session.trust_env = False
                with session.get(
                    image["url"],
                    headers=image["headers"],
                    cookies=image["cookies"],
                    stream=True,
                    timeout=20,
                ) as response:
                    response.raise_for_status()
                    if not response.headers.get("Content-Type", "").lower().startswith("image/"):
                        raise MediaError("no_media", "ปลายทางไม่ได้ส่งไฟล์รูปภาพ")
                    with target.open("wb") as stream:
                        for chunk in response.iter_content(65536):
                            stream.write(chunk)
                            stream.flush()
                            check_size(directory)
        else:
            quality = selection.get("quality")
            if quality not in {q["id"] for q in item["qualities"]}:
                raise MediaError("selection", "คุณภาพที่เลือกไม่อยู่ในรายการที่รองรับ")
            entry = videos[int(item["id"].split("-")[1])]["raw"]
            formats = [f for f in entry.get("formats", [entry]) if allowed_format(f)]
            audio_only = quality == "mp3"
            audios = [
                f
                for f in formats
                if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")
            ]
            if audio_only:
                candidates = audios or [f for f in formats if f.get("acodec") not in (None, "none")]
                chosen = [max(candidates, key=lambda f: f.get("abr") or f.get("tbr") or 0)]
            else:
                candidates = [
                    f
                    for f in formats
                    if f.get("height")
                    and f["height"] <= int(quality[:-1])
                    and f.get("vcodec") != "none"
                ]
                chosen = [max(candidates, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))]
                if chosen[0].get("acodec") == "none" and audios:
                    chosen.append(max(audios, key=lambda f: f.get("abr") or f.get("tbr") or 0))
            paths = []
            for index, fmt in enumerate(chosen):
                path = base.with_suffix(
                    f".part{index}.{fmt.get('ext') if fmt.get('ext') in ('mp4', 'webm', 'm4a', 'mp3', 'ogg') else 'bin'}"
                )

                def hook(data):
                    check_size(directory)
                    total = data.get("total_bytes") or data.get("total_bytes_estimate")
                    fraction = min(0.95, data.get("downloaded_bytes", 0) / total) if total else 0
                    emit(
                        {
                            "event": "progress",
                            "progress": round(
                                (number + (index + fraction) / len(chosen)) / len(selections) * 90,
                                1,
                            ),
                            "phase": "downloading",
                        }
                    )

                options = ydl_options(
                    use_cookies=videos[int(item["id"].split("-")[1])].get("use_cookies", False)
                ) | {"outtmpl": str(path), "progress_hooks": [hook]}
                with make_ydl(options) as ydl:
                    # Download only the already-inspected format; no external protocols/processors.
                    info = dict(entry)
                    info.pop("requested_formats", None)
                    info.pop("requested_downloads", None)
                    info.update(fmt)
                    info["filepath"] = str(path)
                    ydl.process_info(info)
                if not path.is_file():
                    raise MediaError("download_failed", "ดาวน์โหลดไฟล์ไม่สำเร็จหรือไฟล์ใหญ่เกินกำหนด")
                paths.append(path)
                check_size(directory)
            target = base.with_suffix(".mp3" if audio_only else ".mkv")
            emit(
                {
                    "event": "progress",
                    "progress": round((number + 0.95) / len(selections) * 90, 1),
                    "phase": "converting",
                }
            )
            transcode(paths, target, audio=audio_only)
            check_size(directory)
            for path in paths:
                path.unlink()
        results.append(target)
        emit(
            {
                "event": "progress",
                "progress": round((number + 1) / len(selections) * 90, 1),
                "phase": "downloading",
            }
        )
    if len(results) == 1:
        check_size(directory)
        return results[0]
    archive = directory / "media.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        for path in results:
            if archive.stat().st_size + path.stat().st_size > settings.max_bytes:
                raise MediaError("size_limit", "ไฟล์ ZIP มีขนาดเกินที่กำหนด")
            bundle.write(path, path.name)
            path.unlink()
    check_size(directory)
    return archive
