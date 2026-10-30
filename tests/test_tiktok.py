import copy
from dataclasses import replace
import socket
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch, AsyncMock

import requests

from backend import downloader, tiktok
from backend.browser_session import BrowserSession
from backend.downloader import MediaError
from backend.validators import URLValidationError, validate_url
from backend.validators import ValidatedURL
from backend import main
from backend.stream_worker import stream
from fastapi.testclient import TestClient


URL = "https://www.tiktok.com/@fixture/video/123456789"


def fixture(photo=False):
    post = {
        "id": "123456789",
        "desc": "fixture",
        "createTime": 1700000000,
        "author": {"id": "123", "uniqueId": "fixture", "nickname": "fixture"},
        "stats": {},
        "music": {"playUrl": "https://cdn.example/music.mp3", "duration": 10},
    }
    if photo:
        post["imagePost"] = {
            "images": [
                {
                    "imageURL": {"urlList": [f"https://cdn.example/{i}.jpg"]},
                    "imageWidth": 1080,
                    "imageHeight": 1920,
                }
                for i in range(3)
            ]
        }
    else:
        post["video"] = {
            "width": 720,
            "height": 1280,
            "duration": 10,
            "format": "mp4",
            "playAddr": "https://cdn.example/video.mp4",
            "cover": "https://cdn.example/cover.jpg",
        }
    return post


def dns(host, port, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]


class TikTokTests(unittest.TestCase):
    def test_preview_cookies_keep_domain_path_secure_and_expiry_rules(self):
        session = requests.Session()
        jar = requests.cookies.RequestsCookieJar()
        jar.set("sessionid", "fixture-secret", domain=".tiktok.com", path="/media", secure=True)
        jar.set("other", "never-send", domain=".instagram.com", path="/")
        jar.set("expired", "never-send", domain=".tiktok.com", path="/", expires=1)
        rows = []
        for cookie in jar:
            row = dict(cookie.__dict__)
            row["rest"] = row.pop("_rest", {})
            rows.append(row)
        response = Mock(
            status_code=206, headers={"Content-Length": "4", "Content-Range": "bytes 0-3/10"}
        )
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_content.return_value = [b"clip"]
        session.get = Mock(return_value=response)
        descriptor = {
            "url": "https://v16.tiktok.com/media/video.mp4",
            "media_type": "video/mp4",
            "cookie_rows": rows,
        }
        with (
            patch("requests.Session", return_value=session),
            patch("backend.stream_worker.validate_network_url"),
        ):
            stream({"descriptor": descriptor, "range": "bytes=0-3"}, io.BytesIO())
        header = session.prepare_request(requests.Request("GET", descriptor["url"])).headers.get(
            "Cookie", ""
        )
        self.assertIn("fixture-secret", header)
        self.assertNotIn("never-send", header)
        for url in (
            "https://other.example/media/video.mp4",
            "https://v16.tiktok.com/elsewhere",
            "http://v16.tiktok.com/media/video.mp4",
        ):
            self.assertNotIn(
                "Cookie", session.prepare_request(requests.Request("GET", url)).headers
            )

    def test_info_never_returns_preview_cookie_values_to_browser(self):
        result = {
            "title": "fixture",
            "type": "video",
            "thumbnail": None,
            "items": [
                {
                    "id": "video-0",
                    "type": "video",
                    "thumbnail": None,
                    "_preview": {
                        "url": "https://v16.tiktok.com/video.mp4",
                        "headers": {},
                        "media_type": "video/mp4",
                        "cookie_rows": [{"value": "fixture-secret"}],
                    },
                }
            ],
        }
        client = TestClient(main.app, base_url="http://localhost")
        with (
            patch.object(main.manager, "inspect", new=AsyncMock(return_value=result)),
            patch.object(
                main,
                "validate_url",
                return_value=ValidatedURL(URL, "www.tiktok.com", 443, ("8.8.8.8",)),
            ),
        ):
            response = client.post("/info", json={"url": URL})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("fixture-secret", response.text)
        self.assertNotIn("cookie_rows", response.text)
        ticket = response.json()["items"][0]["preview_url"].split("/")[2]
        self.assertEqual(
            main.previews[ticket]["streams"][0]["cookie_rows"][0]["value"], "fixture-secret"
        )
        main.previews.pop(ticket)

    def setUp(self):
        tiktok.post_data.cache_clear()
        self.addCleanup(tiktok.post_data.cache_clear)

    def test_allowlist_accepts_tiktok_and_short_subdomains_only(self):
        with patch("backend.validators.socket.getaddrinfo", side_effect=dns):
            for host in (
                "tiktok.com",
                "www.tiktok.com",
                "m.tiktok.com",
                "vt.tiktok.com",
                "vm.tiktok.com",
            ):
                self.assertEqual(validate_url("https://" + host + "/fixture").hostname, host)
            for host in ("eviltiktok.com", "tiktok.com.evil.test", "tiktokv.com", "douyin.com"):
                with self.assertRaises(URLValidationError):
                    validate_url("https://" + host + "/fixture")

    def test_video_photo_and_embed_urls_normalize_to_same_post(self):
        for url in (
            URL,
            URL.replace("www.", "m."),
            URL.replace("www.", "").replace("/video/", "/photo/") + "?tracking=fixture",
        ):
            self.assertEqual(tiktok.normalize_url(url), URL)
        self.assertEqual(
            tiktok.normalize_url("https://www.tiktok.com/embed/v2/123456789"),
            "https://www.tiktok.com/@/video/123456789",
        )
        self.assertEqual(
            tiktok.normalize_url("https://www.tiktok.com/@/video/123456789"),
            "https://www.tiktok.com/@/video/123456789",
        )

    def test_profiles_live_and_other_domains_are_rejected(self):
        for url, code in (
            ("https://tiktok.com/@fixture", "tiktok_post_required"),
            ("https://tiktok.com/@fixture/live", "live_not_supported"),
            ("https://tiktok.com.evil.test/@fixture/video/123", "tiktok_url"),
        ):
            with self.assertRaises(MediaError) as error:
                tiktok.normalize_url(url)
            self.assertEqual(error.exception.code, code)
        self.assertFalse(tiktok.short_link("https://evil.test/t/abc"))

    def session(self, location):
        session = Mock()
        session.headers = {}
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        response = Mock(status_code=302, headers={"Location": location})
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        session.get.return_value = response
        return session

    def test_short_link_resolves_with_explicit_redirects(self):
        session = self.session(URL.replace("/video/", "/photo/"))
        with (
            patch("requests.Session", return_value=session),
            patch("backend.validators.socket.getaddrinfo", side_effect=dns),
        ):
            self.assertEqual(tiktok.resolve_url("https://vt.tiktok.com/Fixture/"), URL)
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])
        self.assertTrue(session.get.call_args.kwargs["stream"])
        self.assertFalse(session.trust_env)

    def test_redirect_to_private_ip_or_other_platform_is_never_followed(self):
        for location in ("http://127.0.0.1/secret", "https://youtube.com/watch?v=fixture"):
            session = self.session(location)
            with (
                patch("requests.Session", return_value=session),
                patch("backend.validators.socket.getaddrinfo", side_effect=dns),
            ):
                with self.assertRaises((MediaError, URLValidationError)):
                    tiktok.resolve_url("https://vt.tiktok.com/Fixture/")
            self.assertEqual(session.get.call_count, 1)

    def test_redirect_dns_private_address_and_loops_are_blocked(self):
        session = self.session(URL)

        def resolver(host, port, **kwargs):
            ip = "10.0.0.1" if host == "www.tiktok.com" else "8.8.8.8"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

        with (
            patch("requests.Session", return_value=session),
            patch("backend.validators.socket.getaddrinfo", side_effect=resolver),
        ):
            with self.assertRaises(URLValidationError) as error:
                tiktok.resolve_url("https://vt.tiktok.com/Fixture/")
        self.assertEqual(error.exception.code, "unsafe_address")
        self.assertEqual(session.get.call_count, 1)
        session = self.session("/Loop/")
        with (
            patch("requests.Session", return_value=session),
            patch("backend.validators.socket.getaddrinfo", side_effect=dns),
        ):
            with self.assertRaises(URLValidationError) as error:
                tiktok.resolve_url("https://vt.tiktok.com/Fixture/")
        self.assertEqual(error.exception.code, "too_many_redirects")
        self.assertLessEqual(session.get.call_count, 6)

    def extractor(self, post, status=0, authenticated=False):
        ext = Mock()
        ext.session = requests.Session()
        self.addCleanup(ext.session.close)
        if authenticated:
            ext.session.cookies.set("sessionid", "fixture", domain=".tiktok.com")
        ext._extract_rehydration_data.return_value = {
            "webapp.video-detail": {"statusCode": status, "itemInfo": {"itemStruct": post}}
        }
        return ext

    def test_statuses_are_actionable_and_private_paid_drm_remain_restricted(self):
        for status, code in (
            (10222, "login_required"),
            (10204, "no_media"),
            (10231, "region_restricted"),
            (999, "platform_blocked"),
        ):
            with (
                patch.object(
                    downloader, "gallery_extractor", return_value=self.extractor(fixture(), status)
                ),
                self.assertRaises(MediaError) as error,
            ):
                tiktok.post_data(URL, use_cookies=False)
            self.assertEqual(error.exception.code, code)
        for post, code in (
            (dict(fixture(), privateItem=True), "login_required"),
            (dict(fixture(), isPaidContent=True), "paywall"),
            (dict(fixture(), video={"isDRM": True}), "drm"),
            (dict(fixture(), id="987654321"), "no_media"),
        ):
            with (
                patch.object(downloader, "gallery_extractor", return_value=self.extractor(post)),
                self.assertRaises(MediaError) as error,
            ):
                tiktok.post_data(URL, use_cookies=False)
            self.assertEqual(error.exception.code, code)

    def test_gallery_parses_all_photos_without_soundtrack_video(self):
        with (
            patch.object(tiktok, "post_data", return_value=fixture(True)),
            patch.object(downloader, "validate_network_url"),
        ):
            images = downloader.image_info(URL, use_cookies=False)
            _, videos = downloader.video_info(URL, use_cookies=False)
        self.assertEqual(len(images), 3)
        self.assertEqual(videos, [])
        self.assertTrue(all(image["extension"] == "jpg" for image in images))

    def test_ytdlp_processes_video_formats_using_existing_transport(self):
        with patch.object(tiktok, "post_data", return_value=copy.deepcopy(fixture())):
            _, videos = downloader.video_info(URL, use_cookies=False)
        self.assertEqual(len(videos), 1)
        self.assertEqual([q["id"] for q in videos[0]["qualities"]], ["1280p", "mp3"])
        self.assertTrue(
            downloader.video_preview(videos[0]["raw"])["url"].startswith("https://cdn.example/")
        )

    def test_video_without_caption_still_has_a_title(self):
        post = fixture()
        post["desc"] = ""
        with patch.object(tiktok, "post_data", return_value=post):
            raw, videos = downloader.video_info(URL, use_cookies=False)
        self.assertEqual(len(videos), 1)
        self.assertTrue(raw["title"])

    def test_inspection_tries_public_post_before_saved_chrome_session(self):
        # A saved session can receive 403 even when this public post is readable.
        with (
            patch.object(downloader, "settings", replace(downloader.settings, browser="chrome")),
            patch.object(downloader, "has_worker_session", return_value=True),
            patch.object(downloader, "worker_cookie_jar", return_value=[object()]),
            patch.object(
                downloader,
                "validate_url",
                return_value=ValidatedURL(URL, "www.tiktok.com", 443, ("8.8.8.8",)),
            ),
            patch.object(tiktok, "resolve_url", return_value=URL),
            patch.object(tiktok, "post_data", return_value=fixture()),
            patch.object(downloader, "image_info", return_value=[]) as images,
        ):
            result, videos, _ = downloader.inspect_media(URL)
        self.assertEqual(result["type"], "video")
        self.assertFalse(videos[0]["use_cookies"])
        images.assert_called_once_with(URL, use_cookies=False)

    def test_private_post_still_retries_with_authorized_session(self):
        ext_public = self.extractor(fixture(), status=10222)
        ext_private = self.extractor(fixture(), authenticated=True)
        with (
            patch.object(downloader, "settings", replace(downloader.settings, browser="chrome")),
            patch.object(
                downloader, "gallery_extractor", side_effect=[ext_public, ext_private]
            ) as extract,
        ):
            post = downloader.extract_public_first(tiktok.post_data, URL)
        self.assertEqual(post["id"], "123456789")
        self.assertEqual(
            [call.kwargs["use_cookies"] for call in extract.call_args_list], [False, True]
        )

    def test_download_preserves_anonymous_cdn_session_cookie_scope(self):
        jar = requests.cookies.RequestsCookieJar()
        jar.set("tt_chain_token", "fixture", domain=".tiktok.com", path="/media", secure=True)
        row = dict(next(iter(jar)).__dict__)
        row["rest"] = row.pop("_rest", {})
        entry = {
            "id": "123456789",
            "extractor_key": "TikTok",
            "_preview_cookie_rows": [row],
            "formats": [
                {
                    "url": "https://v16.tiktok.com/media/video.mp4",
                    "protocol": "https",
                    "ext": "mp4",
                    "vcodec": "h264",
                    "acodec": "aac",
                    "height": 1280,
                }
            ],
        }
        ydl = Mock()
        ydl.cookiejar = requests.cookies.RequestsCookieJar()
        ydl.__enter__ = Mock(return_value=ydl)
        ydl.__exit__ = Mock(return_value=False)
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            ydl.process_info.side_effect = lambda info: Path(info["filepath"]).write_bytes(b"video")
            inspected = (
                {"items": [{"id": "video-0", "type": "video", "qualities": []}]},
                [{"raw": entry, "use_cookies": False}],
                [],
            )
            with (
                patch.object(downloader, "make_ydl", return_value=ydl),
                patch.object(
                    downloader,
                    "transcode",
                    side_effect=lambda paths, target, **kw: target.write_bytes(b"output"),
                ),
            ):
                result = downloader.download_media(
                    URL, [{"id": "video-0"}], directory, lambda event: None, inspected=inspected
                )
            self.assertEqual(result.read_bytes(), b"output")
        session = requests.Session()
        session.cookies = ydl.cookiejar
        self.addCleanup(session.close)
        for url, expected in (
            (entry["formats"][0]["url"], True),
            ("https://other.example/media/video.mp4", False),
            ("https://v16.tiktok.com/elsewhere", False),
            ("http://v16.tiktok.com/media/video.mp4", False),
        ):
            header = session.prepare_request(requests.Request("GET", url)).headers.get("Cookie", "")
            self.assertEqual("fixture" in header, expected)


class TikTokSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_keeps_only_tiktok_credentials_for_tiktok(self):
        jar = requests.cookies.RequestsCookieJar()
        jar.set("sessionid", "fixture", domain=".tiktok.com")
        jar.set("sessionid", "other", domain=".instagram.com")
        jar.set("bad", "fixture", domain=".eviltiktok.com")
        cache = BrowserSession("chrome", loader=Mock(return_value=jar))
        await cache.refresh()
        rows = cache.for_url(URL)
        self.assertEqual([row["domain"] for row in rows], [".tiktok.com"])
        self.assertEqual(cache.for_url("https://youtube.com/watch?v=fixture"), [])
