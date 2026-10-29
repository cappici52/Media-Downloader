import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch, AsyncMock
import zipfile
from dataclasses import replace

import requests
from fastapi.testclient import TestClient

from backend import downloader, main, profiles
from backend.downloader import MediaError
from backend.validators import ValidatedURL


URL = "https://www.instagram.com/fixture/"
FIELD = "xdt_api__v1__feed__user_timeline_graphql_connection"


def post(code="Fixture1", private=False):
    return {
        "code": code,
        "user": {"is_private": private},
        "media_type": 1,
        "caption": {"text": "โพสต์ทดสอบ"},
        "image_versions2": {"candidates": [{"url": "https://cdn.example/a.jpg"}]},
    }


class ProfileTests(unittest.TestCase):
    def test_private_mixed_post_is_complete_and_partial_extraction_is_an_error(self):
        product = {
            "pk": "123456789",
            "code": "Fixture1",
            "caption": None,
            "taken_at": 1700000000,
            "user": {"pk": "123", "username": "fixture", "is_private": True},
            "carousel_media": [
                {
                    "pk": "123456790",
                    "media_type": 1,
                    "image_versions2": {
                        "candidates": [
                            {"url": "https://cdn.example/a.jpg", "width": 1080, "height": 1080}
                        ]
                    },
                },
                {
                    "pk": "123456791",
                    "media_type": 2,
                    "has_audio": True,
                    "video_duration": 10,
                    "image_versions2": {
                        "candidates": [
                            {"url": "https://cdn.example/b.jpg", "width": 720, "height": 1280}
                        ]
                    },
                    "video_versions": [
                        {
                            "id": "1",
                            "url": "https://cdn.example/b.mp4",
                            "width": 720,
                            "height": 1280,
                        }
                    ],
                },
            ],
        }
        jar = requests.cookies.RequestsCookieJar()
        jar.set("sessionid", "fixture", domain=".instagram.com")
        post_url = "https://www.instagram.com/p/Fixture1/"
        with (
            patch.object(downloader, "settings", replace(downloader.settings, browser="chrome")),
            patch.object(downloader, "has_worker_session", return_value=True),
            patch.object(downloader, "worker_cookie_jar", return_value=jar),
            patch.object(
                downloader,
                "validate_url",
                return_value=ValidatedURL(post_url, "www.instagram.com", 443, ("8.8.8.8",)),
            ),
            patch.object(downloader, "validate_network_url"),
            patch.object(downloader, "instagram_authenticated_product", return_value=product),
        ):
            result, _, _ = downloader.inspect_media(post_url, use_session_first=True)
            self.assertEqual(sorted(item["type"] for item in result["items"]), ["image", "video"])
            with (
                patch.object(
                    downloader, "video_info", side_effect=MediaError("login_required", "fixture")
                ),
                self.assertRaises(MediaError) as error,
            ):
                downloader.inspect_media(post_url, use_session_first=True)
            self.assertEqual(error.exception.code, "incomplete_media")

    def test_graphql_stream_applies_deferred_post_metadata(self):
        first = {
            "data": {
                FIELD: {
                    "edges": [{"node": {"caption": None}}],
                    "page_info": {"has_next_page": False},
                }
            }
        }
        later = {
            "incremental": [
                {"path": [FIELD, "edges", 0, "node"], "data": {"caption": {"text": "fixture"}}}
            ]
        }
        content = (json.dumps(first) + "\n" + json.dumps(later)).encode()
        result = profiles.graphql_connection(content, FIELD)
        self.assertEqual(result["edges"][0]["node"]["caption"]["text"], "fixture")

    def test_private_suffix_is_kept_in_open_link_but_id_uses_base_shortcode(self):
        private = post("Fixture1" + "A" * 28, private=True)
        ext = self.extractor([private, post("Fixture1")], authenticated=True)
        with patch.object(downloader, "gallery_extractor", return_value=ext):
            result = profiles.profile_page(URL, use_cookies=True)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["id"], "post-Fixture1")
        self.assertIn("Fixture1" + "A" * 28, result["items"][0]["url"])

    def test_cursor_roundtrip_and_rejection_of_other_profile_or_arbitrary_query_fields(self):
        cursor = profiles.encode_cursor("next", "Fixture", "123", ["PolarisSEOIsCrawler"])
        self.assertEqual(
            profiles.decode_cursor(cursor, "fixture"), ("next", "123", ["PolarisSEOIsCrawler"])
        )
        for invalid, owner in (
            (cursor, "other"),
            ("not-base64", "fixture"),
            (profiles.encode_cursor("next", "fixture", "https://127.0.0.1/", []), "fixture"),
        ):
            with self.assertRaises(MediaError) as error:
                profiles.decode_cursor(invalid, owner)
            self.assertEqual(error.exception.code, "cursor")

    def extractor(self, posts=None, more=False, cursor=None, authenticated=False):
        ext = Mock()
        ext.root = "https://www.instagram.com"
        ext.session = requests.Session()
        self.addCleanup(ext.session.close)
        if authenticated:
            ext.session.cookies.set("sessionid", "fixture", domain=".instagram.com")
        ext.api.user_by_web.return_value = {"id": "123", "username": ""}
        ext.api._prepare_graphql.side_effect = lambda name, variables, field: (
            {},
            {"doc_id": "123", "variables": json.dumps(variables)},
        )
        data = {
            "data": {
                FIELD: {
                    "edges": [{"node": item} for item in (posts or [])],
                    "page_info": {"has_next_page": more, "end_cursor": cursor},
                }
            }
        }
        ext.request.return_value.content = json.dumps(data).encode()
        return ext

    def test_only_profile_paths_are_accepted(self):
        self.assertEqual(profiles.instagram_profile(URL), "fixture")
        self.assertIsNone(
            profiles.instagram_profile(URL.replace("instagram.com", "instagram.com.evil.test"))
        )
        for path in ("p", "stories", "reel", "accounts", "explore", "direct", "p/Fixture1"):
            self.assertIsNone(profiles.instagram_profile("https://instagram.com/" + path + "/"))

    def test_profile_pagination_is_one_request_and_keeps_canonical_post_links(self):
        ext = self.extractor([post(), post(), post("Fixture2")], True, "next-page")
        with patch.object(downloader, "gallery_extractor", return_value=ext):
            result = profiles.profile_page(
                URL, profiles.encode_cursor("previous", "fixture", "123", []), use_cookies=False
            )
        self.assertEqual(
            [item["id"] for item in result["items"]], ["post-Fixture1", "post-Fixture2"]
        )
        self.assertEqual(profiles.decode_cursor(result["next_cursor"], "fixture")[0], "next-page")
        self.assertEqual(result["items"][0]["url"], "https://www.instagram.com/p/Fixture1/")
        variables = ext.api._prepare_graphql.call_args.args[1]
        self.assertEqual(variables["after"], "previous")
        self.assertEqual(variables["first"], 12)
        self.assertFalse(variables["__relay_internal__pv__PolarisSEOIsCrawlerrelayprovider"])
        ext.request.assert_called_once()
        self.assertEqual(ext.api.user_by_web.return_value["username"], "fixture")

    def test_private_posts_need_real_platform_login_and_paid_posts_are_denied(self):
        for authenticated in (False, True):
            ext = self.extractor([post(private=True)], authenticated=authenticated)
            with patch.object(downloader, "gallery_extractor", return_value=ext):
                if authenticated:
                    self.assertEqual(len(profiles.profile_page(URL, use_cookies=True)["items"]), 1)
                else:
                    with self.assertRaises(MediaError) as error:
                        profiles.profile_page(URL, use_cookies=True)
                    self.assertEqual(error.exception.code, "login_required")
        paid = dict(post(), availability="subscriber_only")
        with (
            patch.object(
                downloader,
                "gallery_extractor",
                return_value=self.extractor([paid], authenticated=True),
            ),
            self.assertRaises(MediaError) as error,
        ):
            profiles.profile_page(URL, use_cookies=True)
        self.assertEqual(error.exception.code, "paywall")

    def test_repeated_and_missing_next_cursors_are_errors_not_fake_completion(self):
        for cursor in ("previous", None, ""):
            with (
                patch.object(
                    downloader,
                    "gallery_extractor",
                    return_value=self.extractor([post()], True, cursor),
                ),
                self.assertRaises(MediaError) as error,
            ):
                profiles.profile_page(URL, profiles.encode_cursor("previous", "fixture", "123", []))
            self.assertEqual(error.exception.code, "cursor")

    def test_bad_response_and_empty_profile_are_distinct(self):
        ext = self.extractor()
        with patch.object(downloader, "gallery_extractor", return_value=ext):
            self.assertEqual(profiles.profile_page(URL)["items"], [])
        ext.request.return_value.content = b'{"errors":[{"message":"fixture"}]}'
        with (
            patch.object(downloader, "gallery_extractor", return_value=ext),
            self.assertRaises(MediaError) as error,
        ):
            profiles.profile_page(URL)
        self.assertEqual(error.exception.code, "platform_blocked")

    def test_script_sources_are_limited_to_platform_cdns_and_query_module_is_parsed(self):
        page = '"src":"https:\\/\\/static.cdninstagram.com\\/rsrc.php\\/fixture.js" https://127.0.0.1/evil.js https://evil.test/steal.js'
        self.assertEqual(
            profiles.script_urls(page), ["https://static.cdninstagram.com/rsrc.php/fixture.js"]
        )
        ext = Mock()
        ext.cache.return_value = page
        ext.request.return_value.text = '__d("Test_instagramRelayOperation",[],(function(a){a.exports="123";}));__d("Test$Parameters",["PolarisSEOIsCrawler.relayprovider"],function(){});'
        self.assertEqual(
            profiles.query_info(ext, "Test", "/fixture"), ("123", ["PolarisSEOIsCrawler"])
        )

    def test_bulk_zip_flattens_carousels_and_preserves_each_post_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            inspection = ({"items": [{"id": "image-0", "type": "image"}]}, [], [])

            def download(url, choices, folder, emit, **kwargs):
                if "Fixture1" in url:
                    path = folder / "media.zip"
                    with zipfile.ZipFile(path, "w") as archive:
                        archive.writestr("media-001.jpg", b"fixture1")
                else:
                    path = folder / "media-001.jpg"
                    path.write_bytes(b"fixture2")
                emit({"event": "progress", "progress": 90, "phase": "downloading"})
                return path

            progress = Mock()
            with (
                patch.object(downloader, "inspect_media", return_value=inspection),
                patch.object(downloader, "download_media", side_effect=download),
            ):
                output = profiles.download_profile(
                    URL, [{"id": "post-Fixture1"}, {"id": "post-Fixture2"}], directory, progress
                )
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(
                    archive.namelist(),
                    ["post-Fixture1/media-001.jpg", "post-Fixture2/media-001.jpg"],
                )
                self.assertIsNone(archive.testzip())
            self.assertEqual(list(directory.iterdir()), [output])

    def test_bulk_rejects_path_injection_duplicates_and_aggregate_media_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            for selections in ([{"id": "post-../evil"}], [{"id": "post-A"}, {"id": "post-A"}]):
                with self.assertRaises(MediaError):
                    profiles.download_profile(URL, selections, Path(temp), Mock())
            inspection = ({"items": [{"id": "image-0", "type": "image"}] * 101}, [], [])
            with (
                patch.object(downloader, "inspect_media", return_value=inspection),
                self.assertRaises(MediaError) as error,
            ):
                profiles.download_profile(URL, [{"id": "post-A"}], Path(temp), Mock())
            self.assertEqual(error.exception.code, "item_limit")

    def test_api_proxies_profile_thumbnails_and_passes_opaque_cursor(self):
        client = TestClient(main.app, base_url="http://localhost")
        result = {
            "type": "profile",
            "title": "@fixture",
            "items": [
                {"id": "post-Fixture1", "type": "post", "thumbnail": "https://cdn.example/a.jpg"}
            ],
            "thumbnail": None,
            "next_cursor": "next",
        }
        with (
            patch.object(
                main,
                "validate_url",
                return_value=ValidatedURL(URL, "www.instagram.com", 443, ("8.8.8.8",)),
            ),
            patch.object(main.manager, "inspect", new=AsyncMock(return_value=result)) as inspect,
        ):
            response = client.post("/info", json={"url": URL, "cursor": "previous"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["items"][0]["thumbnail"].startswith("/thumbnails/"))
        inspect.assert_awaited_once_with(URL, "previous")
        self.assertEqual(
            client.post("/info", json={"url": URL, "cursor": "x" * 4097}).status_code, 422
        )

    def test_bulk_video_uses_highest_source_quality(self):
        with tempfile.TemporaryDirectory() as temp:
            inspection = (
                {
                    "items": [
                        {
                            "id": "video-0",
                            "type": "video",
                            "qualities": [{"id": q} for q in ("360p", "720p", "1080p", "mp3")],
                        }
                    ]
                },
                [],
                [],
            )

            def download(url, choices, folder, emit, **kwargs):
                self.assertEqual(choices, [{"id": "video-0", "quality": "best"}])
                self.assertEqual(kwargs["video_format"], "mov")
                path = folder / "media.mkv"
                path.write_bytes(b"fixture")
                return path

            with (
                patch.object(downloader, "inspect_media", return_value=inspection),
                patch.object(downloader, "download_media", side_effect=download),
            ):
                profiles.download_profile(
                    URL, [{"id": "post-Fixture1"}], Path(temp), Mock(), video_format="mov"
                )
