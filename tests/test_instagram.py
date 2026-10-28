import copy
from dataclasses import replace
import json
import unittest
from unittest.mock import Mock, patch

import requests
from backend import downloader
from backend.downloader import MediaError
from backend.validators import ValidatedURL


def product_fixture(count=16):
    return {
        "pk": "1000",
        "code": "Fixture123",
        "taken_at": 1700000000,
        "caption": {"text": "fixture"},
        "user": {"pk": "123", "username": "fixture", "full_name": "Fixture", "is_private": False},
        "carousel_media": [
            {
                "pk": str(2000 + i),
                "media_type": 1,
                "image_versions2": {
                    "candidates": [
                        {"url": f"https://cdn.example/{i}.jpg", "width": 1080, "height": 1080}
                    ]
                },
            }
            for i in range(count)
        ],
    }


class InstagramTests(unittest.TestCase):
    def test_private_public_fallback_retries_authorized_browser_session(self):
        adapter = Mock(side_effect=[MediaError("login_required", "login"), ["fixture"]])
        with (
            patch.object(downloader, "settings", replace(downloader.settings, browser="chrome")),
            patch.object(
                downloader, "instagram_public_product", side_effect=MediaError("private", "private")
            ),
        ):
            result = downloader.extract_public_first(adapter, "https://instagram.com/p/Fixture123/")
        self.assertEqual(result, ["fixture"])
        self.assertEqual(
            [call.kwargs["use_cookies"] for call in adapter.call_args_list], [False, True]
        )

    def setUp(self):
        downloader.instagram_public_product.cache_clear()
        self.addCleanup(downloader.instagram_public_product.cache_clear)

    def mock_session(self, product):
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.headers = {}
        session.cookies = requests.cookies.RequestsCookieJar()
        session.cookies.set("csrftoken", "anonymous-test-token", domain=".instagram.com")
        root = Mock()
        root.__enter__ = Mock(return_value=root)
        root.__exit__ = Mock(return_value=False)
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        body = json.dumps(
            {"data": {"xdt_api__v1__media__shortcode__web_info": {"items": [product]}}}
        ).encode()
        response.iter_content.return_value = [body]
        session.get.return_value = root
        session.post.return_value = response
        return session, response

    def test_tracking_links_and_reels_are_canonicalized(self):
        for url in (
            "https://www.instagram.com/p/Fixture123/?utm_source=test",
            "https://instagram.com/reel/Fixture123/?srtk=tracking",
            "https://m.instagram.com/owner/p/Fixture123/",
        ):
            self.assertEqual(
                downloader.normalize_post_url(url), "https://www.instagram.com/p/Fixture123/"
            )
        self.assertIsNone(
            downloader.instagram_shortcode("https://instagram.com.evil.test/p/Fixture123/")
        )

    def test_public_query_is_anonymous_bounded_and_cached_per_worker(self):
        session, _ = self.mock_session(product_fixture())
        with patch("requests.Session", return_value=session):
            self.assertEqual(
                len(downloader.instagram_public_product("Fixture123")["carousel_media"]), 16
            )
            downloader.instagram_public_product("Fixture123")
        self.assertFalse(session.trust_env)
        self.assertNotIn("Cookie", session.headers)
        self.assertEqual(session.post.call_count, 1)
        self.assertEqual(session.headers["X-CSRFToken"], "anonymous-test-token")

    def test_private_and_oversized_carousels_are_rejected(self):
        for private, count, expected in ((True, 1, "private"), (False, 101, "item_limit")):
            product = product_fixture(count)
            product["user"]["is_private"] = private
            session, _ = self.mock_session(product)
            with (
                patch("requests.Session", return_value=session),
                self.assertRaises(MediaError) as error,
            ):
                downloader.instagram_public_product("Fixture123")
            self.assertEqual(error.exception.code, expected)

    def test_response_size_limit(self):
        session, response = self.mock_session(product_fixture(1))
        response.iter_content.return_value = [b"x" * (8 * 1024 * 1024 + 1)]
        with (
            patch("requests.Session", return_value=session),
            self.assertRaises(MediaError) as error,
        ):
            downloader.instagram_public_product("Fixture123")
        self.assertEqual(error.exception.code, "metadata_limit")

    def test_public_fallback_precedes_browser_cookies(self):
        adapter = Mock(side_effect=[MediaError("login_required", "ต้องล็อกอิน"), ["image"]])
        product = product_fixture()
        with (
            patch.object(downloader, "instagram_public_product", return_value=product),
            patch.object(downloader, "settings", replace(downloader.settings, browser="chrome")),
        ):
            self.assertEqual(
                downloader.extract_public_first(adapter, "https://instagram.com/p/Fixture123/"),
                ["image"],
            )
        self.assertEqual(adapter.call_count, 2)
        self.assertEqual(
            [call.kwargs["use_cookies"] for call in adapter.call_args_list], [False, False]
        )
        self.assertIs(adapter.call_args.kwargs["instagram_product"], product)

    def test_gallery_parses_all_public_carousel_images(self):
        with patch.object(downloader, "validate_network_url"):
            images = downloader.image_info(
                "https://www.instagram.com/p/Fixture123/",
                use_cookies=False,
                instagram_product=product_fixture(),
            )
        self.assertEqual(len(images), 16)
        self.assertTrue(all(image["extension"] == "jpg" for image in images))

    def test_ytdlp_parses_video_from_mixed_public_carousel(self):
        product = product_fixture(2)
        video = product["carousel_media"][0]
        video.update(
            {
                "media_type": 2,
                "has_audio": True,
                "video_duration": 10,
                "video_versions": [
                    {
                        "id": "1",
                        "url": "https://cdn.example/video.mp4",
                        "width": 1280,
                        "height": 720,
                    }
                ],
            }
        )
        _, videos = downloader.video_info(
            "https://www.instagram.com/p/Fixture123/",
            use_cookies=False,
            instagram_product=copy.deepcopy(product),
        )
        self.assertEqual(len(videos), 1)
        self.assertFalse(videos[0]["use_cookies"])
        self.assertEqual([quality["id"] for quality in videos[0]["qualities"]], ["720p", "mp3"])

    def test_actionable_cookie_error_wins_over_generic_login_error(self):
        checked = ValidatedURL(
            "https://instagram.com/p/Fixture123/", "instagram.com", 443, ("8.8.8.8",)
        )
        with (
            patch.object(downloader, "validate_url", return_value=checked),
            patch.object(
                downloader,
                "extract_public_first",
                side_effect=[
                    MediaError("login_required", "ต้องล็อกอิน"),
                    MediaError("cookies_locked", "ปิด Chrome ก่อน"),
                ],
            ),
            self.assertRaises(MediaError) as error,
        ):
            downloader.inspect_media(checked.url)
        self.assertEqual(error.exception.code, "cookies_locked")
