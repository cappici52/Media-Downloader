import copy
from dataclasses import replace
import unittest
from unittest.mock import Mock, patch

import requests

from backend import downloader
from backend.downloader import MediaError
from backend.browser_session import install_worker_session


URL = "https://www.instagram.com/stories/fixture/123456789/"


def product_fixture(video=False):
    product = {
        "pk": "123456789",
        "code": "Fixture123",
        "taken_at": 1700000000,
        "caption": None,
        "user": {"pk": "123", "username": "fixture", "is_private": True},
        "media_type": 2 if video else 1,
        "image_versions2": {
            "candidates": [{"url": "https://cdn.example/image.jpg", "width": 1080, "height": 1920}]
        },
    }
    if video:
        product.update(
            {
                "has_audio": True,
                "video_duration": 10,
                "video_versions": [
                    {
                        "id": "1",
                        "url": "https://cdn.example/video.mp4",
                        "width": 720,
                        "height": 1280,
                    }
                ],
            }
        )
    return product


class StoryTests(unittest.TestCase):
    def test_story_links_remain_intact_and_do_not_use_public_post_query(self):
        self.assertTrue(downloader.instagram_story(URL))
        self.assertTrue(downloader.instagram_story(URL + "?source=fixture"))
        self.assertTrue(downloader.instagram_story("https://instagram.com/stories/fixture/"))
        self.assertFalse(
            downloader.instagram_story("https://instagram.com.evil.test/stories/f/123/")
        )
        self.assertFalse(
            downloader.instagram_story("https://instagram.com/stories/highlights/123/")
        )
        self.assertEqual(downloader.normalize_post_url(URL), URL)
        self.assertIsNone(downloader.instagram_shortcode(URL))

    def test_story_missing_media_retries_browser_session(self):
        adapter = Mock(side_effect=[MediaError("no_media", "missing"), ["fixture"]])
        with (
            patch.object(downloader, "settings", replace(downloader.settings, browser="chrome")),
            patch.object(downloader, "instagram_public_product") as public_query,
        ):
            self.assertEqual(downloader.extract_public_first(adapter, URL), ["fixture"])
        self.assertEqual(
            [call.kwargs["use_cookies"] for call in adapter.call_args_list], [False, True]
        )
        public_query.assert_not_called()

    def extractor(self, authenticated=True):
        ext = Mock()
        ext.session = requests.Session()
        if authenticated:
            ext.session.cookies.set("sessionid", "fixture", domain=".instagram.com")
        ext.api._call.return_value = {"items": [product_fixture()]}
        ext.config.return_value = "memory"
        return ext

    def test_story_collection_preserves_all_authorized_close_friends_media(self):
        from gallery_dl.extractor.instagram import InstagramAPI

        ext = self.extractor()
        items = [product_fixture(), product_fixture(True)]
        items[1]["pk"] = "987654321"
        for item in items:
            item["is_besties"] = True
        reel = {"user": items[0]["user"], "items": items}
        with (
            patch.object(downloader, "gallery_extractor", return_value=ext),
            patch.object(
                InstagramAPI, "user_by_web", return_value={"id": "123", "username": "fixture"}
            ),
            patch.object(InstagramAPI, "reels_media", return_value=iter([reel])) as reels,
        ):
            product = downloader.instagram_story_product("https://instagram.com/stories/fixture/")
        self.assertEqual(
            [item["pk"] for item in product["carousel_media"]], ["123456789", "987654321"]
        )
        self.assertTrue(all(item["is_besties"] for item in product["carousel_media"]))
        reels.assert_called_once_with(("123",))

    def test_collection_query_and_tokens_are_loaded_from_story_page(self):
        from gallery_dl.extractor.instagram import InstagramAPI

        ext = self.extractor()

        def read_reels(api, reel_ids):
            api._extract_fb_tokens("/fixture")
            api._extract_opname_info("StoryQuery", "/fixture")
            return iter([{"items": [product_fixture()]}])

        with (
            patch.object(downloader, "gallery_extractor", return_value=ext),
            patch.object(
                InstagramAPI, "user_by_web", return_value={"id": "123", "username": "fixture"}
            ),
            patch.object(InstagramAPI, "reels_media", read_reels),
            patch.object(
                InstagramAPI, "_extract_fb_tokens", return_value=("fixture", "fixture")
            ) as tokens,
            patch.object(InstagramAPI, "_extract_opname_info", return_value=("123", [])) as query,
        ):
            downloader.instagram_story_product("https://instagram.com/stories/fixture/")
        tokens.assert_called_once_with("/stories/fixture")
        query.assert_called_once_with("StoryQuery", "/stories/fixture")

    def test_collection_without_login_does_not_request_user_or_media(self):
        ext = self.extractor(authenticated=False)
        with (
            patch.object(downloader, "gallery_extractor", return_value=ext),
            self.assertRaises(MediaError) as error,
        ):
            downloader.instagram_story_product("https://instagram.com/stories/fixture/")
        self.assertEqual(error.exception.code, "login_required")
        ext.api.user_by_web.assert_not_called()

    def test_collection_limits_and_paid_restrictions_are_preserved(self):
        from gallery_dl.extractor.instagram import InstagramAPI

        for items, expected in (
            ([product_fixture()] * (downloader.settings.max_items + 1), "item_limit"),
            ([dict(product_fixture(), is_paid_content=True)], "paywall"),
            ([], "story_unavailable"),
        ):
            ext = self.extractor()
            with (
                patch.object(downloader, "gallery_extractor", return_value=ext),
                patch.object(
                    InstagramAPI, "user_by_web", return_value={"id": "123", "username": "fixture"}
                ),
                patch.object(InstagramAPI, "reels_media", return_value=iter([{"items": items}])),
                self.assertRaises(MediaError) as error,
            ):
                downloader.instagram_story_product("https://instagram.com/stories/fixture/")
            self.assertEqual(error.exception.code, expected)

    def test_exact_story_media_is_read_without_profile_or_reels_queries(self):
        ext = self.extractor()
        with patch.object(downloader, "gallery_extractor", return_value=ext):
            product = downloader.instagram_story_product(URL)
        self.assertEqual(product["pk"], "123456789")
        ext.api._call.assert_called_once_with("/v1/media/123456789/info/")
        ext.api.user.assert_not_called()
        ext.posts.assert_not_called()

    def test_story_requires_login_before_requesting_media(self):
        ext = self.extractor(authenticated=False)
        with (
            patch.object(downloader, "gallery_extractor", return_value=ext),
            self.assertRaises(MediaError) as error,
        ):
            downloader.instagram_story_product(URL)
        self.assertEqual(error.exception.code, "login_required")
        ext.api._call.assert_not_called()

    def test_expired_deleted_or_inaccessible_story_has_specific_error(self):
        ext = self.extractor()
        ext.api._call.return_value = {"items": []}
        with (
            patch.object(downloader, "gallery_extractor", return_value=ext),
            self.assertRaises(MediaError) as error,
        ):
            downloader.instagram_story_product(URL)
        self.assertEqual(error.exception.code, "story_unavailable")

    def test_provider_denial_is_not_replaced_with_media(self):
        ext = self.extractor()
        ext.api._call.side_effect = MediaError("private", "denied")
        with (
            patch.object(downloader, "gallery_extractor", return_value=ext),
            self.assertRaises(MediaError) as error,
        ):
            downloader.instagram_story_product(URL)
        self.assertEqual(error.exception.code, "private")

    def test_authenticated_story_images_and_videos_use_existing_media_parsers(self):
        install_worker_session(
            [
                {
                    "name": "sessionid",
                    "version": 0,
                    "port": None,
                    "port_specified": False,
                    "value": "fixture",
                    "domain": ".instagram.com",
                    "domain_specified": True,
                    "domain_initial_dot": True,
                    "path": "/",
                    "path_specified": True,
                    "secure": True,
                    "expires": None,
                    "discard": True,
                    "comment": None,
                    "comment_url": None,
                    "rest": {},
                }
            ]
        )
        self.addCleanup(install_worker_session, None)
        with patch.object(downloader, "settings", replace(downloader.settings, browser="chrome")):
            with (
                patch.object(downloader, "instagram_story_product", return_value=product_fixture()),
                patch.object(downloader, "validate_network_url"),
            ):
                images = downloader.image_info(URL, use_cookies=True)
            self.assertEqual(len(images), 1)
            with patch.object(
                downloader,
                "instagram_story_product",
                return_value=copy.deepcopy(product_fixture(True)),
            ):
                _, videos = downloader.video_info(URL, use_cookies=True)
            self.assertEqual(len(videos), 1)
            self.assertEqual(videos[0]["qualities"][0]["id"], "1280p")
