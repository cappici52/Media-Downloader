import unittest
from dataclasses import replace
from unittest.mock import patch
from backend import downloader
from backend.downloader import MediaError, assert_public, friendly_error, quality_options
from unittest.mock import Mock


class DownloaderTests(unittest.TestCase):
    def test_registered_x_extractor_preserves_verified_scope_without_overriding_restrictions(self):
        from yt_dlp.extractor.twitter import TwitterIE

        with downloader.make_ydl(downloader.ydl_options(use_cookies=False)) as ydl:
            extractor = ydl.get_info_extractor("Twitter")
            data = {
                "tweetResult": {
                    "result": {
                        "__typename": "Tweet",
                        "core": {"user_results": {"result": {"privacy": {"protected": False}}}},
                        "legacy": {},
                    }
                }
            }
            extractor._graphql_to_legacy(data, "123")
            with patch.object(TwitterIE, "_real_extract", return_value={"id": "123"}):
                self.assertEqual(extractor._real_extract("unused")["availability"], "public")
            with patch.object(
                TwitterIE,
                "_real_extract",
                return_value={"id": "123", "availability": "subscriber_only"},
            ):
                self.assertEqual(
                    extractor._real_extract("unused")["availability"], "subscriber_only"
                )

    def test_x_public_visibility_is_taken_from_explicit_author_privacy(self):
        for source in ({"privacy": {"protected": False}}, {"legacy": {"protected": False}}):
            result = {
                "__typename": "Tweet",
                "core": {"user_results": {"result": source}},
                "legacy": {},
            }
            self.assertEqual(downloader.twitter_public_scope(result), "public")

    def test_x_visibility_rejects_private_missing_and_gated_metadata(self):
        result = {
            "__typename": "Tweet",
            "core": {"user_results": {"result": {"privacy": {"protected": True}}}},
            "legacy": {},
        }
        self.assertEqual(downloader.twitter_public_scope(result), "private")
        result["core"]["user_results"]["result"]["privacy"] = {}
        self.assertIsNone(downloader.twitter_public_scope(result))
        result["core"]["user_results"]["result"]["privacy"]["protected"] = False
        result["exclusive_tweet_info"] = {"is_exclusive": True}
        self.assertIsNone(downloader.twitter_public_scope(result))
        self.assertIsNone(downloader.twitter_public_scope({"__typename": "TweetTombstone"}))

    def test_x_quoted_private_media_is_not_marked_public(self):
        result = {
            "__typename": "Tweet",
            "core": {"user_results": {"result": {"privacy": {"protected": False}}}},
            "quoted_status_result": {
                "result": {
                    "__typename": "Tweet",
                    "core": {"user_results": {"result": {"privacy": {"protected": True}}}},
                }
            },
        }
        self.assertEqual(downloader.twitter_public_scope(result), "private")

    def test_gallery_initializes_session_before_configuring_it(self):
        import requests
        from gallery_dl.extractor.common import Message

        class LazyExtractor:
            session = None

            def initialize(self):
                if self.session is None:
                    self.session = requests.Session()

            def __iter__(self):
                self.initialize()
                yield (
                    Message.Url,
                    "https://pbs.twimg.com/media/fixture.jpg",
                    {"extension": "jpg", "title": "fixture"},
                )

        extractor = LazyExtractor()
        with (
            patch("gallery_dl.extractor.find", return_value=extractor),
            patch.object(downloader, "validate_network_url"),
            patch.object(downloader, "settings", replace(downloader.settings, browser="chrome")),
        ):
            images = downloader.image_info(
                "https://x.com/fixture/status/123/photo/1", use_cookies=False
            )
        self.assertEqual(len(images), 1)
        self.assertFalse(extractor.session.trust_env)
        extractor.session.close()

    def test_public_posts_do_not_read_browser_cookies(self):
        adapter = Mock(return_value=["image"])
        with patch.object(downloader, "settings", replace(downloader.settings, browser="chrome")):
            self.assertEqual(downloader.extract_public_first(adapter, "url"), ["image"])
            self.assertNotIn("cookiesfrombrowser", downloader.ydl_options(use_cookies=False))
            assert_public({}, use_cookies=False)
            with self.assertRaises(MediaError):
                assert_public({"is_private": True}, use_cookies=False)
        adapter.assert_called_once_with("url", use_cookies=False)

    def test_authentication_retry_only_when_needed(self):
        adapter = Mock(side_effect=[MediaError("login_required", "ต้องล็อกอิน"), ["image"]])
        with patch.object(downloader, "settings", replace(downloader.settings, browser="chrome")):
            self.assertEqual(downloader.extract_public_first(adapter, "url"), ["image"])
        self.assertEqual(
            [call.kwargs["use_cookies"] for call in adapter.call_args_list], [False, True]
        )
        adapter = Mock(side_effect=MediaError("private", "โพสต์เป็นส่วนตัว"))
        with (
            patch.object(downloader, "settings", replace(downloader.settings, browser="chrome")),
            self.assertRaises(MediaError),
        ):
            downloader.extract_public_first(adapter, "url")
        self.assertEqual(adapter.call_count, 1)

    def test_x_missing_media_retries_configured_browser_session(self):
        adapter = Mock(side_effect=[MediaError("no_media", "No video could be found"), ["video"]])
        with patch.object(downloader, "settings", replace(downloader.settings, browser="chrome")):
            result = downloader.extract_public_first(adapter, "https://x.com/owner/status/123")
        self.assertEqual(result, ["video"])
        self.assertEqual(
            [call.kwargs["use_cookies"] for call in adapter.call_args_list], [False, True]
        )

    def test_x_unavailable_does_not_claim_the_post_was_deleted(self):
        adapter = Mock(side_effect=MediaError("no_media", "Unavailable"))
        with (
            patch.object(downloader, "settings", replace(downloader.settings, browser="")),
            self.assertRaises(MediaError) as error,
        ):
            downloader.extract_public_first(adapter, "https://twitter.com/owner/status/123")
        self.assertEqual(error.exception.code, "x_unavailable")
        self.assertIn("ยังยืนยันไม่ได้", str(error.exception))
        self.assertEqual(adapter.call_count, 1)

    def test_x_missing_media_reports_browser_cookie_failure(self):
        adapter = Mock(
            side_effect=[
                MediaError("no_media", "No video"),
                Exception("Could not copy Chrome cookie database"),
            ]
        )
        with (
            patch.object(downloader, "settings", replace(downloader.settings, browser="chrome")),
            self.assertRaises(Exception) as error,
        ):
            downloader.extract_public_first(adapter, "https://x.com/owner/status/123")
        self.assertEqual(friendly_error(error.exception)["code"], "cookies_locked")

    def test_x_media_links_normalize_to_the_entire_post(self):
        for host in ("x.com", "twitter.com", "www.x.com", "m.twitter.com"):
            url = f"https://{host}/owner/status/123"
            for suffix in ("/photo/1", "/video/2", "/photo/1/"):
                self.assertEqual(
                    downloader.normalize_post_url(url + suffix + "?s=20"), url + "?s=20"
                )
        unrelated = "https://instagram.com/owner/status/123/photo/1"
        self.assertEqual(downloader.normalize_post_url(unrelated), unrelated)

    def test_cookie_and_login_errors_are_actionable(self):
        for message, code in (
            ("Could not copy Chrome cookie database", "cookies_locked"),
            ("Failed to decrypt with DPAPI", "cookies_decryption"),
            ("Failed to load cookies", "cookies_unavailable"),
            ("AuthorizationError: Login required", "login_required"),
        ):
            result = friendly_error(Exception(message))
            self.assertEqual(result["code"], code)
            self.assertNotIn(message, result["message"])

    def test_private_content_is_rejected_even_with_browser_cookies(self):
        with patch.object(downloader, "settings", replace(downloader.settings, browser="firefox")):
            for metadata in ({"availability": "private"}, {"owner": {"is_private": True}}, {}):
                with self.subTest(metadata=metadata), self.assertRaises(MediaError):
                    assert_public(metadata)
            assert_public({"availability": "public"})
            assert_public({"user": {"protected": False}})

    def test_quality_options_exclude_drm_and_external_protocols(self):
        def fmt(height, **extra):
            return {
                "protocol": "https",
                "url": "https://cdn.example/a",
                "height": height,
                "vcodec": "avc",
                "acodec": "aac",
                **extra,
            }

        options = quality_options(
            [fmt(360), fmt(720), fmt(720), fmt(1080, has_drm=True), fmt(2160, protocol="m3u8")]
        )
        self.assertEqual([q["id"] for q in options], ["360p", "720p", "mp3"])

    def test_errors_are_thai_and_hide_raw_secrets(self):
        for text, code in (
            ("please login", "login_required"),
            ("private post", "private"),
            ("HTTP 429", "platform_blocked"),
            ("404 not found", "no_media"),
            ("connection timeout", "network"),
            ("secret-token", "extract_failed"),
        ):
            result = friendly_error(Exception(text))
            self.assertEqual(result["code"], code)
            self.assertNotIn(text, result["message"])
        self.assertEqual(friendly_error(MediaError("limit", "เกินขนาด"))["code"], "limit")

    def test_socket_guard_in_disposable_process(self):
        import subprocess
        import sys

        code = """from backend.network import install_network_guard
import socket
install_network_guard()
for host in ("127.0.0.1", "169.254.169.254", "::1", "10.0.0.1"):
    try: socket.create_connection((host, 80), timeout=.1)
    except ValueError: pass
    else: raise AssertionError(host)
try: socket.socket().connect(("youtube.com", 443))
except ValueError: pass
else: raise AssertionError("implicit DNS allowed")
import urllib.request
for url in ("file:///etc/passwd", "ftp://example.com/file", "data:text/plain,secret"):
    try: urllib.request.urlopen(url)
    except ValueError: pass
    else: raise AssertionError("non-HTTP URL allowed")
print("ok")"""
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=10
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
