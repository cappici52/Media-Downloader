"""Library adapters, used exclusively inside backend.worker."""

import shutil
import subprocess
import zipfile

from .settings import settings
from .validators import URLValidationError, validate_url, validate_network_url


class MediaError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def friendly_error(error):
    if isinstance(error, (MediaError, URLValidationError)):
        return {"code": error.code, "message": str(error)}
    text = (type(error).__name__ + " " + str(error)).lower()
    if any(
        word in text
        for word in ("private", "authorization", "not available to you", "followers only")
    ):
        return {"code": "private", "message": "โพสต์เป็นส่วนตัวหรือคุณไม่มีสิทธิ์เข้าถึง"}
    if any(
        word in text
        for word in ("login", "log in", "sign in", "cookies", "authentication", "age-restricted")
    ):
        return {"code": "login_required", "message": "ต้องล็อกอิน เว็บไซต์อาจไม่อนุญาตให้ดึงโพสต์นี้"}
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
    def debug(self, message):
        pass

    def info(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


def ydl_options():
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
    if settings.browser:
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
        options["cookiesfrombrowser"] = (settings.browser,)
    return options


def make_ydl(options=None):
    from yt_dlp import YoutubeDL
    from yt_dlp.networking._urllib import UrllibRH

    class GuardedYoutubeDL(YoutubeDL):
        def build_request_director(self, handlers, preferences=None):
            # Native curl/impersonation transports bypass Python's socket guard.
            return super().build_request_director([UrllibRH], preferences=[])

    return GuardedYoutubeDL(options or ydl_options())


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


def assert_public(metadata):
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
    if settings.browser and not public:
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


def video_info(url):
    with make_ydl() as ydl:
        raw = ydl.extract_info(url, download=False)
        entries = list(raw.get("entries") or [raw])
        videos = []
        for entry in entries:
            if not entry:
                continue
            if entry.get("is_live") or entry.get("live_status") in ("is_live", "is_upcoming"):
                raise MediaError("live_not_supported", "ยังไม่รองรับวิดีโอถ่ายทอดสด กรุณาใช้วิดีโอที่จบแล้ว")
            assert_public(entry)
            if len(videos) >= settings.max_items:
                raise MediaError("item_limit", "โพสต์มีสื่อเกินจำนวนที่กำหนด")
            if (entry.get("duration") or 0) > settings.max_duration:
                raise MediaError("duration_limit", "วิดีโอยาวเกินเวลาที่กำหนด")
            qualities = quality_options(entry.get("formats") or [entry])
            if qualities:
                videos.append({"raw": entry, "qualities": qualities})
        return raw, videos


def image_info(url):
    from gallery_dl import config, extractor
    from gallery_dl.extractor.common import Message

    config.clear()
    config.set(("cache",), "file", ":memory:")
    config.set(("extractor",), "retries", 1)
    config.set(("extractor",), "timeout", 20)
    config.set(("extractor",), "proxy", "")
    if settings.browser:
        # gallery-dl uses its own local browser-cookie loader.
        config.set(("extractor",), "cookies", [settings.browser])
    ext = extractor.find(url)
    if ext is None:
        raise MediaError("no_media", "ไม่พบรูปในลิงก์นี้")
    ext.session.trust_env = False
    images = []
    for message in ext:
        if message[0] != Message.Url:
            continue  # Never recurse profile queues or delegate to another downloader.
        media_url, metadata = message[1:3]
        assert_public(metadata)
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


def inspect_media(url):
    checked = validate_url(url)
    url = checked.url
    videos, images, failures = [], [], []
    raw = {}
    if not any(
        checked.hostname == domain or checked.hostname.endswith("." + domain)
        for domain in ("youtube.com", "youtu.be")
    ):
        try:
            images = image_info(url)
        except Exception as error:
            failures.append(error)
    try:
        raw, videos = video_info(url)
    except Exception as error:
        failures.append(error)
    if not videos and not images:
        preferred = next(
            (
                error
                for error in failures
                if friendly_error(error)["code"]
                in ("private", "login_required", "platform_blocked", "public_unverified")
            ),
            None,
        )
        raise preferred or (
            failures[-1] if failures else MediaError("no_media", "ไม่พบวิดีโอหรือรูปในลิงก์นี้")
        )
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
                    if size > 2 * 1024 * 1024:
                        raise MediaError("preview", "รูปตัวอย่างมีขนาดใหญ่เกินไป")
                    stream.write(chunk)
    return {"filename": target.name, "media_type": kind}


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


def download_media(url, selections, directory, emit):
    import requests

    public, videos, images = inspect_media(url)
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

                options = ydl_options() | {"outtmpl": str(path), "progress_hooks": [hook]}
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
