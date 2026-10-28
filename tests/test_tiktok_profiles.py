import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from gallery_dl.extractor.tiktok import TiktokPaginationRequest

from backend import downloader, profiles, tiktok, tiktok_profiles as tp
from backend.downloader import MediaError
from backend.validators import ValidatedURL

URL = "https://www.tiktok.com/@fixture?lang=en"


def post(identifier="123", photo=False):
    item = {
        "id": identifier,
        "desc": "fixture",
        "createTime": 1700000000,
        "author": {"uniqueId": "fixture"},
        "video": {"cover": "https://cdn.example/cover.jpg"},
    }
    if photo:
        item["imagePost"] = {
            "images": [{"imageURL": {"urlList": ["https://cdn.example/a.jpg"]}}] * 3
        }
    return item


class TikTokProfileTests(unittest.TestCase):
    def extractor(self, private=False, status=0, count=30, login=False):
        ext = Mock()
        ext.session = requests.Session()
        self.addCleanup(ext.session.close)
        if login:
            ext.session.cookies.set("sessionid", "fixture", domain=".tiktok.com")
        ext._extract_rehydration_data.return_value = {
            "webapp.user-detail": {
                "statusCode": status,
                "userInfo": {
                    "user": {
                        "uniqueId": "fixture",
                        "secUid": "MS4wLjABAAAA" + "a" * 40,
                        "privateAccount": private,
                    },
                    "stats": {"videoCount": count},
                },
            }
        }
        return ext

    def page(self, rows=None, more=False, cursor=1600000000000):
        return {
            "itemList": rows if rows is not None else [post(), post("124", True)],
            "hasMore": more,
            "cursor": cursor,
        }, {}

    def test_profile_urls_do_not_accept_posts_live_or_other_domains(self):
        self.assertEqual(tp.tiktok_profile(URL), "fixture")
        for url in (
            "https://tiktok.com/@fixture/video/123",
            "https://tiktok.com/@fixture/live",
            "https://tiktok.com.evil.test/@fixture",
            "https://x.com/@fixture",
            "https://tiktok.com/@",
            "https://tiktok.com/@bad%2Fname",
        ):
            self.assertIsNone(tp.tiktok_profile(url))

    def test_cursor_is_scoped_to_owner_and_all_fields_are_validated(self):
        cursor = tp.encode_cursor("fixture", "posts", 1234, "a" * 64)
        self.assertEqual(tp.decode_cursor(cursor, "Fixture"), ("posts", 1234, "a" * 64))
        for invalid, owner in (
            (cursor, "other"),
            ("tt1.!!!", "fixture"),
            (tp.encode_cursor("fixture", "https://127.0.0.1", 1, "a" * 64), "fixture"),
            (tp.encode_cursor("fixture", "posts", True, "a" * 64), "fixture"),
            ("tt1." + "a" * 4096, "fixture"),
        ):
            with self.assertRaises(MediaError):
                tp.decode_cursor(invalid, owner)

    def test_one_page_retains_photos_videos_and_returns_cursor(self):
        ext = self.extractor()
        with (
            patch.object(downloader, "gallery_extractor", return_value=ext),
            patch.object(
                TiktokPaginationRequest, "_request_data", return_value=self.page(more=True)
            ) as request,
        ):
            result = tp.profile_page(URL)
        self.assertEqual(request.call_count, 1)
        self.assertEqual([i["media_count"] for i in result["items"]], [1, 3])
        self.assertEqual([i["has_video"] for i in result["items"]], [True, False])
        self.assertEqual(result["platform"], "TikTok")
        self.assertEqual(result["url"], "https://www.tiktok.com/@fixture")
        self.assertEqual(tp.decode_cursor(result["next_cursor"], "fixture")[1], 1600000000000)
        self.assertTrue(
            all(i["url"].startswith(result["url"] + "/video/") for i in result["items"])
        )

    def test_next_page_preserves_endpoint_cursor_and_rejects_repeated_rows(self):
        ext = self.extractor()
        fingerprint = hashlib.sha256(b"123,124").hexdigest()
        cursor = tp.encode_cursor("fixture", "posts", 1700000000000, fingerprint)
        with (
            patch.object(downloader, "gallery_extractor", return_value=ext),
            patch.object(
                TiktokPaginationRequest, "_request_data", return_value=self.page(more=True)
            ) as request,
        ):
            with self.assertRaises(MediaError) as error:
                tp.profile_page(URL, cursor)
        self.assertEqual(error.exception.code, "cursor")
        self.assertEqual(request.call_args.args[1].current_page(), 1700000000000)
        self.assertEqual(request.call_count, 1)

    def test_failed_modern_page_falls_back_once_to_legacy(self):
        ext = self.extractor()
        legacy = {"itemList": [post()], "hasMorePrevious": True}
        with (
            patch.object(downloader, "gallery_extractor", return_value=ext),
            patch.object(
                TiktokPaginationRequest, "_request_data", side_effect=[ValueError(), (legacy, {})]
            ) as request,
        ):
            result = tp.profile_page(URL)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(tp.decode_cursor(result["next_cursor"], "fixture")[0], "creator")

    def test_blocked_page_and_empty_account_are_distinct(self):
        for data in ({}, {"itemList": [], "hasMore": False}, {"itemList": [], "hasMore": "false"}):
            with (
                patch.object(downloader, "gallery_extractor", return_value=self.extractor()),
                patch.object(TiktokPaginationRequest, "_request_data", return_value=(data, {})),
            ):
                with self.assertRaises(MediaError) as error:
                    tp.profile_page(URL)
                self.assertEqual(error.exception.code, "platform_blocked")
        with (
            patch.object(downloader, "gallery_extractor", return_value=self.extractor(count=0)),
            patch.object(TiktokPaginationRequest, "_request_data") as request,
        ):
            self.assertEqual(tp.profile_page(URL)["items"], [])
            request.assert_not_called()

    def test_private_account_requires_own_authorized_session(self):
        with patch.object(
            downloader, "gallery_extractor", return_value=self.extractor(private=True)
        ):
            with self.assertRaises(MediaError) as error:
                tp.profile_page(URL)
            self.assertEqual(error.exception.code, "login_required")
        with (
            patch.object(
                downloader,
                "gallery_extractor",
                return_value=self.extractor(private=True, login=True),
            ),
            patch.object(TiktokPaginationRequest, "_request_data", return_value=self.page()),
        ):
            self.assertEqual(len(tp.profile_page(URL, use_cookies=True)["items"]), 2)

    def test_private_zero_count_still_requests_posts_with_authorized_session(self):
        ext = self.extractor(private=True, status=10222, count=0, login=True)
        with (
            patch.object(downloader, "gallery_extractor", return_value=ext),
            patch.object(
                TiktokPaginationRequest, "_request_data", return_value=self.page()
            ) as request,
        ):
            result = tp.profile_page(URL, use_cookies=True)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(request.call_count, 1)

    def test_private_empty_or_blocked_list_is_an_access_error_not_empty_success(self):
        for data in ({"itemList": [], "hasMore": False}, {}):
            ext = self.extractor(private=True, status=10222, count=0, login=True)
            with (
                patch.object(downloader, "gallery_extractor", return_value=ext),
                patch.object(TiktokPaginationRequest, "_request_data", return_value=(data, {})),
                self.assertRaises(MediaError) as error,
            ):
                tp.profile_page(URL, use_cookies=True)
            self.assertEqual(error.exception.code, "private")

    def test_other_author_or_bad_ids_are_never_exposed_and_paid_posts_are_skipped(self):
        for item in (dict(post(), author={"uniqueId": "other"}), dict(post(), id="../bad")):
            with (
                patch.object(downloader, "gallery_extractor", return_value=self.extractor()),
                patch.object(
                    TiktokPaginationRequest, "_request_data", return_value=self.page([item])
                ),
            ):
                with self.assertRaises(MediaError):
                    tp.profile_page(URL)
        with (
            patch.object(downloader, "gallery_extractor", return_value=self.extractor()),
            patch.object(
                TiktokPaginationRequest,
                "_request_data",
                return_value=self.page([dict(post(), isPaidContent=True)]),
            ),
        ):
            self.assertEqual(tp.profile_page(URL)["items"], [])

    def test_profile_routes_to_new_adapter_without_single_post_normalization(self):
        with (
            patch.object(
                downloader,
                "validate_url",
                return_value=ValidatedURL(URL, "www.tiktok.com", 443, ("8.8.8.8",)),
            ),
            patch.object(tp, "inspect_profile", return_value={"type": "profile"}) as inspect,
        ):
            self.assertEqual(downloader.inspect_media(URL, "cursor")[0]["type"], "profile")
        inspect.assert_called_once_with(URL, "cursor")

    def test_bulk_download_reuses_zip_and_never_sends_tiktok_ids_to_instagram(self):
        with tempfile.TemporaryDirectory() as temp:
            inspection = ({"items": [{"id": "image-0", "type": "image"}]}, [], [])

            def save(url, selections, folder, emit, **kwargs):
                self.assertTrue(url.startswith("https://www.tiktok.com/@fixture/video/"))
                output = folder / "media.jpg"
                output.write_bytes(b"fixture")
                return output

            with (
                patch.object(downloader, "inspect_media", return_value=inspection) as inspect,
                patch.object(downloader, "download_media", side_effect=save),
            ):
                output = profiles.download_profile(
                    URL, [{"id": "post-123"}, {"id": "post-124"}], Path(temp), Mock()
                )
            self.assertEqual(inspect.call_count, 2)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist(), ["post-123/media.jpg", "post-124/media.jpg"])
                self.assertIsNone(archive.testzip())

    def test_single_post_rejects_wrong_profile_owner(self):
        ext = self.extractor()
        ext._extract_rehydration_data.return_value = {
            "webapp.video-detail": {
                "itemInfo": {"itemStruct": dict(post(), author={"uniqueId": "other"})}
            }
        }
        tiktok.post_data.cache_clear()
        with (
            patch.object(downloader, "gallery_extractor", return_value=ext),
            self.assertRaises(MediaError),
        ):
            tiktok.post_data("https://www.tiktok.com/@fixture/video/123", use_cookies=False)
        tiktok.post_data.cache_clear()
