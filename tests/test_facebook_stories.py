from dataclasses import replace
import json
import unittest
from unittest.mock import Mock, patch

import requests

from backend import downloader
from backend.downloader import MediaError
from backend.facebook_story import find_card, find_cards, media_items, protected_media, video_page


URL = "https://www.facebook.com/stories/123/FixtureStory=/"


def card_fixture(identifier="FixtureStory=", photo=False):
    media = {"__typename": "Photo" if photo else "Video", "id": "456"}
    if photo:
        media["image"] = {"uri": "https://cdn.example/fixture.jpg"}
    else:
        media.update(
            {
                "playable_url": "https://cdn.example/fixture.mp4",
                "drm_info": "",
                "name": "Fixture video",
                "length_in_second": 10,
            }
        )
    return {"id": identifier, "attachments": [{"media": media}]}


def page_fixture(*cards):
    return (
        '<script type="application/json" data-sjs>'
        + json.dumps({"data": list(cards)})
        + "</script>"
    )


class FacebookStoryTests(unittest.TestCase):
    def setUp(self):
        downloader.facebook_story_data.cache_clear()
        self.addCleanup(downloader.facebook_story_data.cache_clear)

    def test_url_detection_and_mobile_normalization(self):
        self.assertTrue(downloader.facebook_story(URL))
        self.assertFalse(
            downloader.facebook_story(URL.replace("facebook.com", "facebook.com.evil.test"))
        )
        self.assertTrue(downloader.facebook_story("https://facebook.com/stories/123/"))
        self.assertEqual(
            downloader.normalize_post_url(
                "https://m.facebook.com/stories/123/?source=profile_highlight&tracking=ignored"
            ),
            "https://www.facebook.com/stories/123/?source=profile_highlight",
        )
        self.assertFalse(downloader.facebook_story("https://facebook.com/stories/not-a-bucket/"))
        self.assertEqual(
            downloader.normalize_post_url(URL.replace("www.", "m.") + "?source=fixture"), URL
        )

    def test_selects_only_exact_story_and_prefers_complete_duplicate(self):
        target = card_fixture()
        stub = {"id": "FixtureStory=", "attachments": []}
        other = card_fixture("OtherStory=")
        page = page_fixture(other, stub, target, stub)
        self.assertEqual(find_card(page, "FixtureStory="), target)
        self.assertIsNone(find_card(page, "MissingStory="))
        self.assertEqual(len(media_items(target)), 1)

    def test_bucket_resolves_only_its_cards_in_order_and_prefers_full_duplicates(self):
        target = {
            "id": "123",
            "unified_stories": {"edges": [{"node": {"id": key}} for key in ("Second", "First")]},
        }
        page = page_fixture(
            target,
            {
                "id": "999",
                "unified_stories_with_notes": {"edges": [{"node": card_fixture("Unrelated")}]},
            },
            {"id": "First", "attachments": []},
            card_fixture("First", photo=True),
            card_fixture("Second"),
        )
        cards = find_cards(page, "123", bucket=True)
        self.assertEqual([card["id"] for card in cards], ["Second", "First"])
        self.assertEqual(len(media_items(cards[1])), 1)
        self.assertEqual(find_cards(page, "Missing", bucket=True), [])

    def test_bucket_download_adapter_merges_photos_and_videos_without_other_buckets(self):
        url = "https://www.facebook.com/stories/123/?source=profile_highlight"
        bucket = {
            "id": "123",
            "unified_stories_with_notes": {
                "edges": [{"node": card_fixture("V")}, {"node": card_fixture("P", photo=True)}]
            },
        }
        with patch.object(
            downloader,
            "make_ydl",
            return_value=self.mock_ydl(page_fixture(bucket, card_fixture("Other")), True),
        ):
            card, _ = downloader.facebook_story_data(url, use_cookies=True)
        self.assertEqual([media["__typename"] for media in media_items(card)], ["Video", "Photo"])
        with (
            patch.object(
                downloader,
                "facebook_story_data",
                return_value=(card, requests.cookies.RequestsCookieJar()),
            ),
            downloader.make_ydl(downloader.ydl_options(use_cookies=False)) as ydl,
        ):
            result = ydl.get_info_extractor("FacebookStory")._real_extract(url)
        self.assertEqual(result["id"], "456")
        fmt = result["formats"][0]
        self.assertEqual(downloader.quality_options([fmt])[0]["id"], "best")
        self.assertEqual(
            downloader.select_video_formats([dict(fmt, quality=-3), dict(fmt, quality=-2)])[0][
                "quality"
            ],
            -2,
        )

    def test_bucket_still_checks_access_and_drm_on_each_card(self):
        url = "https://www.facebook.com/stories/123/"
        for protected in (
            dict(card_fixture("V"), availability="private"),
            {"id": "V", "attachments": [{"media": {"__typename": "Video", "has_drm": True}}]},
        ):
            downloader.facebook_story_data.cache_clear()
            bucket = {"id": "123", "unified_stories_with_notes": {"edges": [{"node": protected}]}}
            with (
                patch.object(
                    downloader, "make_ydl", return_value=self.mock_ydl(page_fixture(bucket))
                ),
                self.assertRaises(MediaError),
            ):
                downloader.facebook_story_data(url, use_cookies=False)

    def test_oversized_or_invalid_metadata_is_not_used(self):
        with self.assertRaises(ValueError):
            find_card("x" * (8 * 1024 * 1024 + 1), "fixture")
        self.assertIsNone(find_card('<script type="application/json">invalid</script>', "fixture"))

    def test_video_adapter_uses_existing_ytdlp_parser_without_fetching_other_media(self):
        card = card_fixture()
        with (
            patch.object(
                downloader,
                "facebook_story_data",
                return_value=(card, requests.cookies.RequestsCookieJar()),
            ),
            downloader.make_ydl(downloader.ydl_options(use_cookies=False)) as ydl,
        ):
            result = ydl.get_info_extractor("FacebookStory")._real_extract(URL)
        self.assertEqual(result["formats"][0]["url"], "https://cdn.example/fixture.mp4")
        self.assertEqual(result["id"], "456")

    def test_photo_adapter_uses_only_attached_photo_and_validates_url(self):
        card = card_fixture(photo=True)
        with (
            patch.object(
                downloader,
                "facebook_story_data",
                return_value=(card, requests.cookies.RequestsCookieJar()),
            ),
            patch.object(downloader, "validate_network_url") as validator,
        ):
            images = downloader.image_info(URL, use_cookies=True)
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["extension"], "jpg")
        validator.assert_called_once_with("https://cdn.example/fixture.jpg")
        self.assertIsNone(video_page(card))

    def test_generic_certificate_is_not_drm_but_licenses_and_protection_flags_are(self):
        info = {
            "video_license_uri_map": {},
            "graph_api_video_license_uri": None,
            "widevine_cert": "fixture-certificate",
            "fairplay_cert": None,
        }
        self.assertFalse(protected_media({"drm_info": json.dumps(info)}))
        for media in (
            {"has_drm": True},
            {"drm_info": json.dumps(dict(info, video_license_uri_map={"widevine": "fixture"}))},
            {"drm_info": {"graph_api_video_license_uri": "fixture"}},
            {"drm_info": {"is_drm_protected": True}},
            {"drm_info": {"drm_type": "widevine"}},
            {"drm_info": "unknown protection"},
        ):
            self.assertTrue(protected_media(media))

    def test_missing_media_retries_browser(self):
        adapter = Mock(side_effect=[MediaError("no_media", "missing"), ["fixture"]])
        with patch.object(downloader, "settings", replace(downloader.settings, browser="chrome")):
            self.assertEqual(downloader.extract_public_first(adapter, URL), ["fixture"])
        self.assertEqual([c.kwargs["use_cookies"] for c in adapter.call_args_list], [False, True])

    def mock_ydl(self, page, authenticated=False):
        ydl = Mock()
        ydl.cookiejar = requests.cookies.RequestsCookieJar()
        if authenticated:
            ydl.cookiejar.set("c_user", "fixture", domain=".facebook.com")
            ydl.cookiejar.set("xs", "fixture", domain=".facebook.com")
        ydl.get_info_extractor.return_value._download_webpage.return_value = page
        context = Mock()
        context.__enter__ = Mock(return_value=ydl)
        context.__exit__ = Mock(return_value=False)
        return context

    def test_unavailable_story_does_not_return_other_stories(self):
        for authenticated, expected in ((False, "login_required"), (True, "story_unavailable")):
            downloader.facebook_story_data.cache_clear()
            with (
                patch.object(
                    downloader,
                    "make_ydl",
                    return_value=self.mock_ydl(
                        page_fixture(card_fixture("OtherStory=")), authenticated
                    ),
                ),
                self.assertRaises(MediaError) as error,
            ):
                downloader.facebook_story_data(URL, use_cookies=authenticated)
            self.assertEqual(error.exception.code, expected)

    def test_private_story_requires_actual_login_and_drm_is_rejected_before_parsing(self):
        private = dict(card_fixture(), availability="private")
        with (
            patch.object(downloader, "make_ydl", return_value=self.mock_ydl(page_fixture(private))),
            self.assertRaises(MediaError) as error,
        ):
            downloader.facebook_story_data(URL, use_cookies=False)
        self.assertEqual(error.exception.code, "login_required")
        drm = card_fixture()
        drm["attachments"][0]["media"]["has_drm"] = True
        with (
            patch.object(
                downloader, "make_ydl", return_value=self.mock_ydl(page_fixture(drm), True)
            ),
            self.assertRaises(MediaError) as error,
        ):
            downloader.facebook_story_data(URL, use_cookies=True)
        self.assertEqual(error.exception.code, "drm")
