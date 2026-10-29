from dataclasses import replace
import json
import time
import unittest
from unittest.mock import Mock, patch, AsyncMock

import requests
from backend.browser_session import BrowserSession, install_worker_session, worker_cookie_jar
from backend import downloader, main
from fastapi.testclient import TestClient


def sample_jar():
    jar = requests.cookies.RequestsCookieJar()
    jar.set("auth_token", "secret-x-token", domain=".x.com", path="/", secure=True)
    jar.set("sessionid", "secret-instagram-token", domain=".instagram.com", path="/", secure=True)
    jar.set("unrelated", "private-unrelated-token", domain=".bank.example", path="/")
    jar.set("lookalike", "private-lookalike-token", domain=".evilx.com", path="/")
    return jar


class BrowserSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_filters_domains_and_exposes_no_values(self):
        loader = Mock(return_value=sample_jar())
        cache = BrowserSession("chrome", loader=loader)
        status = await cache.refresh()
        self.assertEqual(status["status"], "ready")
        self.assertNotIn("secret", json.dumps(status))
        self.assertNotIn("token", json.dumps(status))
        rows = cache.for_url("https://x.com/owner/status/123")
        self.assertEqual([row["name"] for row in rows], ["auth_token"])
        self.assertEqual(cache.for_url("https://facebook.com/post"), [])
        rows[0]["value"] = "modified"
        self.assertEqual(cache.for_url("https://x.com/post")[0]["value"], "secret-x-token")
        self.assertEqual(loader.call_count, 1)

    async def test_expiry_and_clear_erase_session(self):
        cache = BrowserSession("chrome", ttl=1, loader=Mock(return_value=sample_jar()))
        await cache.refresh()
        cache.loaded_at = time.time() - 2
        self.assertEqual(cache.status()["status"], "expired")
        self.assertIsNone(cache.for_url("https://x.com/post"))
        self.assertIsNone(cache._rows)
        await cache.refresh()
        cache.clear()
        self.assertEqual(cache.status()["status"], "not_loaded")

    async def test_failed_refresh_preserves_valid_cached_session_without_echoing_error(self):
        loader = Mock(
            side_effect=[sample_jar(), Exception("Could not copy Chrome cookie database")]
        )
        cache = BrowserSession("chrome", loader=loader)
        await cache.refresh()
        status = await cache.refresh()
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["error"]["code"], "cookies_locked")
        self.assertIsNotNone(cache.for_url("https://x.com/post"))

    async def test_worker_cache_avoids_browser_reads_and_preserves_cookie_domains(self):
        cache = BrowserSession("chrome", loader=Mock(return_value=sample_jar()))
        await cache.refresh()
        install_worker_session(cache.for_url("https://x.com/post"))
        try:
            with patch.object(
                downloader, "settings", replace(downloader.settings, browser="chrome")
            ):
                options = downloader.ydl_options(use_cookies=True)
                self.assertNotIn("cookiesfrombrowser", options)
                with downloader.make_ydl(options) as ydl:
                    self.assertTrue(
                        any(
                            cookie.name == "auth_token" and cookie.domain == ".x.com"
                            for cookie in ydl.cookiejar
                        )
                    )
                self.assertNotIn(
                    "_cached_browser_session", downloader.ydl_options(use_cookies=False)
                )
            self.assertEqual([cookie.domain for cookie in worker_cookie_jar()], [".x.com"])
        finally:
            install_worker_session(None)

    async def test_gallery_uses_cached_cookies_during_lazy_initialization(self):
        from gallery_dl.extractor.common import Message

        class Extractor:
            session = None

            def initialize(self):
                if self.session is None:
                    self.session = requests.Session()
                    self.cookies = self.session.cookies
                    self.cookies_load(["chrome"])

            def cookies_load(self, source):
                raise AssertionError("Browser database must not be read")

            def __iter__(self):
                yield (
                    Message.Url,
                    "https://cdn.example/photo.jpg",
                    {"extension": "jpg", "user": {"protected": False}},
                )

        cache = BrowserSession("chrome", loader=Mock(return_value=sample_jar()))
        await cache.refresh()
        install_worker_session(cache.for_url("https://x.com/post"))
        extractor = Extractor()
        try:
            with (
                patch.object(
                    downloader, "settings", replace(downloader.settings, browser="chrome")
                ),
                patch("gallery_dl.extractor.find", return_value=extractor),
                patch.object(downloader, "validate_network_url"),
            ):
                images = downloader.image_info("https://x.com/post", use_cookies=True)
            self.assertEqual(len(images), 1)
            self.assertEqual(extractor.cookies.get("auth_token", domain=".x.com"), "secret-x-token")
        finally:
            install_worker_session(None)
            if extractor.session:
                extractor.session.close()


class SessionAPITests(unittest.TestCase):
    def test_status_contains_no_cookie_values_and_refresh_rejects_uploads(self):
        cache = BrowserSession("chrome", loader=Mock(return_value=sample_jar()))
        manager = Mock(start=AsyncMock(), close=AsyncMock(), limits=main.settings)
        with (
            patch.object(main, "browser_session", cache),
            patch.object(main, "manager", manager),
            TestClient(main.app, base_url="http://localhost") as client,
        ):
            response = client.get("/session")
            self.assertEqual(response.json()["status"], "ready")
            self.assertNotIn("secret", response.text)
            self.assertNotIn("auth_token", response.text)
            self.assertEqual(
                client.post("/session/refresh", json={"cookies": "not-allowed"}).status_code, 422
            )
            self.assertEqual(
                client.post(
                    "/session/refresh", headers={"Origin": "https://evil.example"}
                ).status_code,
                403,
            )
