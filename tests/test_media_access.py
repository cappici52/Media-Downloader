import time
import unittest
from unittest.mock import Mock, patch

import requests

from backend import downloader
from backend.downloader import MediaError
from backend.validators import ValidatedURL


class MediaAccessTests(unittest.TestCase):
    def test_private_metadata_requires_authenticated_extraction(self):
        for metadata in ({"availability": "private"}, {"owner": {"is_private": True}}):
            downloader.assert_media_access(metadata, use_cookies=True, authenticated=True)
            for use_cookies, authenticated in ((False, False), (True, False), (False, True)):
                with self.subTest(metadata=metadata, cookies=use_cookies, login=authenticated):
                    with self.assertRaises(MediaError) as error:
                        downloader.assert_media_access(
                            metadata, use_cookies=use_cookies, authenticated=authenticated
                        )
                    self.assertEqual(error.exception.code, "login_required")

    def test_login_cookie_must_match_platform_and_be_unexpired(self):
        jar = requests.cookies.RequestsCookieJar()
        url = "https://instagram.com/p/Fixture123/"
        jar.set("sessionid", "fixture", domain=".instagram.com.evil.test")
        self.assertFalse(downloader.has_login_session(jar, url))
        jar.set("sessionid", "fixture", domain=".instagram.com", expires=int(time.time()) - 1)
        self.assertFalse(downloader.has_login_session(jar, url))
        jar.set("sessionid", "fixture", domain=".instagram.com", expires=int(time.time()) + 3600)
        self.assertTrue(downloader.has_login_session(jar, url))
        self.assertFalse(downloader.has_login_session(jar, "https://x.com/owner/status/123"))

    def test_facebook_requires_both_login_cookies(self):
        jar = requests.cookies.RequestsCookieJar()
        jar.set("c_user", "fixture", domain=".facebook.com")
        self.assertFalse(downloader.has_login_session(jar, "https://fb.watch/fixture/"))
        jar.set("xs", "fixture", domain=".facebook.com")
        self.assertTrue(downloader.has_login_session(jar, "https://fb.watch/fixture/"))

    def test_login_does_not_allow_paid_or_drm_media(self):
        for metadata, code in (
            ({"availability": "premium_only"}, "paywall"),
            ({"availability": "subscriber_only"}, "paywall"),
            ({"is_paid_content": True}, "paywall"),
            ({"exclusive_tweet_info": {"is_exclusive": True}}, "paywall"),
            ({"has_drm": True}, "drm"),
        ):
            with self.subTest(metadata=metadata), self.assertRaises(MediaError) as error:
                downloader.assert_media_access(metadata, use_cookies=True, authenticated=True)
            self.assertEqual(error.exception.code, code)

    def test_paid_or_drm_failure_cannot_be_hidden_by_other_adapter(self):
        url = "https://instagram.com/p/Fixture123/"
        for code in ("paywall", "drm"):
            with (
                patch.object(
                    downloader,
                    "validate_url",
                    return_value=ValidatedURL(url, "instagram.com", 443, ("8.8.8.8",)),
                ),
                patch.object(downloader, "image_info", return_value=[{"url": "fixture"}]),
                patch.object(downloader, "video_info", side_effect=MediaError(code, "blocked")),
                self.assertRaises(MediaError) as error,
            ):
                downloader.inspect_media(url)
            self.assertEqual(error.exception.code, code)

    def test_gallery_accepts_private_metadata_only_with_login_session(self):
        from gallery_dl.extractor.common import Message

        ext = Mock()
        ext.session = requests.Session()
        self.addCleanup(ext.session.close)
        ext.session.cookies.set("sessionid", "fixture", domain=".instagram.com")
        ext.__iter__ = Mock(
            return_value=iter(
                [
                    (
                        Message.Url,
                        "https://cdn.example/fixture.jpg",
                        {"extension": "jpg", "user": {"is_private": True}},
                    )
                ]
            )
        )
        with (
            patch("gallery_dl.extractor.find", return_value=ext),
            patch.object(downloader, "validate_network_url"),
        ):
            result = downloader.image_info("https://instagram.com/p/Fixture123/", use_cookies=True)
        self.assertEqual(len(result), 1)

    def test_private_instagram_long_link_is_preserved_for_native_extractor(self):
        url = "https://www.instagram.com/p/Fixture1234_" + "A" * 28 + "/?img_index=1"
        self.assertEqual(downloader.normalize_post_url(url), url)
        self.assertIsNone(downloader.instagram_shortcode(url))

    def test_video_accepts_private_metadata_with_authenticated_session(self):
        jar = requests.cookies.RequestsCookieJar()
        jar.set("sessionid", "fixture", domain=".instagram.com")
        raw = {
            "availability": "private",
            "formats": [
                {
                    "protocol": "https",
                    "url": "https://cdn.example/fixture.mp4",
                    "height": 720,
                    "vcodec": "avc",
                    "acodec": "aac",
                }
            ],
        }
        ydl = Mock(cookiejar=jar)
        ydl.extract_info.return_value = raw
        context = Mock()
        context.__enter__ = Mock(return_value=ydl)
        context.__exit__ = Mock(return_value=False)
        with patch.object(downloader, "make_ydl", return_value=context):
            _, videos = downloader.video_info(
                "https://instagram.com/p/Fixture123/", use_cookies=True
            )
        self.assertEqual(len(videos), 1)
        self.assertEqual(videos[0]["qualities"][0]["id"], "720p")

    def test_paid_playlist_parent_rejected_even_when_entries_appear_public(self):
        ydl = Mock()
        ydl.extract_info.return_value = {
            "is_paid_content": True,
            "entries": [{"availability": "public"}],
        }
        context = Mock()
        context.__enter__ = Mock(return_value=ydl)
        context.__exit__ = Mock(return_value=False)
        with (
            patch.object(downloader, "make_ydl", return_value=context),
            self.assertRaises(MediaError) as error,
        ):
            downloader.video_info("https://instagram.com/p/Fixture123/", use_cookies=True)
        self.assertEqual(error.exception.code, "paywall")
