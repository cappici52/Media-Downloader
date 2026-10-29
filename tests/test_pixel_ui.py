"""Opt-in browser regression: MEDIA_UI_URL=http://127.0.0.1:8002 pytest tests/test_pixel_ui.py.

Browser plugin unavailable; use an isolated Playwright Chrome profile with fixture media.
No user browser credentials or external media requests are used.
"""

import json
import os
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(os.getenv("MEDIA_UI_URL"), "Set MEDIA_UI_URL for opt-in browser QA")
class PixelUITests(unittest.TestCase):
    def test_language_state_and_pixel_workflows(self):
        from playwright.sync_api import sync_playwright, expect

        base = os.environ["MEDIA_UI_URL"]
        output = Path(tempfile.gettempdir())
        # A locally generated WebM can exercise real playback without fetching private content.
        clip = output / "pixel-ui-preview.webm"
        thumbnail = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160"><path fill="#254d61" d="M0 0h160v160H0z"/><path fill="#f2cf7c" d="M110 20h20v20h-20z"/><path fill="#517f83" d="M0 120 55 50 100 120z"/><path fill="#8dc4c6" d="m40 70 15-20 14 20z"/><path fill="#315349" d="m55 160 65-95 40 60v35z"/><path fill="#80a9ab" d="M0 140h160v20H0z"/></svg>'
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chrome")
            page = browser.new_page(
                viewport={"width": 1440, "height": 1050}, reduced_motion="reduce"
            )
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            submitted = []
            polls = []
            job_id = "a" * 32
            limits = {
                "max_file_mb": 500,
                "max_duration_seconds": 1800,
                "max_items": 100,
                "ttl_seconds": 3600,
            }
            title = "ชื่อคลิปภาษาไทย must stay unchanged <not HTML>"

            def media():
                items = [
                    {
                        "id": "image-0",
                        "type": "image",
                        "thumbnail": "/thumbnails/fixture/0",
                        "qualities": [],
                    }
                ]
                items += [
                    {
                        "id": "video-0",
                        "type": "video",
                        "thumbnail": "/thumbnails/fixture/1",
                        "preview_url": "/streams/fixture/0",
                        "qualities": [
                            {"id": "360p", "label": "360p"},
                            {"id": "720p", "label": "720p"},
                            {"id": "mp3", "label": "MP3"},
                        ],
                    }
                ]
                items += [
                    {
                        "id": f"image-{n}",
                        "type": "image",
                        "thumbnail": "/thumbnails/fixture/0",
                        "qualities": [],
                    }
                    for n in range(1, 7)
                ]
                return {
                    "type": "carousel",
                    "title": title,
                    "duration": 12,
                    "thumbnail": "/thumbnails/fixture/0",
                    "items": items,
                    "limits": limits,
                }

            def profile(cursor):
                identifiers = ["3"] if cursor else ["1", "2"]
                return {
                    "type": "profile",
                    "platform": "TikTok",
                    "title": "@fixture",
                    "url": "https://www.tiktok.com/@fixture",
                    "thumbnail": None,
                    "next_cursor": None if cursor else "fixture-cursor",
                    "limits": limits,
                    "items": [
                        {
                            "id": "post-" + identifier,
                            "type": "post",
                            "title": title,
                            "url": "https://www.tiktok.com/@fixture/video/" + identifier,
                            "thumbnail": "/thumbnails/fixture/0",
                            "media_count": 1,
                            "has_video": True,
                            "qualities": [],
                        }
                        for identifier in identifiers
                    ],
                }

            def route_info(route):
                payload = route.request.post_data_json
                url = payload["url"]
                if "private" in url:
                    route.fulfill(
                        status=400,
                        json={
                            "error": {
                                "code": "login_required",
                                "message": "ต้องล็อกอิน เว็บไซต์อาจไม่อนุญาตให้ดึงโพสต์นี้",
                            }
                        },
                    )
                elif "offline" in url:
                    route.abort("failed")
                elif "/@fixture" in url and "/video/" not in url:
                    route.fulfill(json=profile(payload.get("cursor")))
                else:
                    route.fulfill(json=media())

            page.route("**/info", route_info)
            page.route(
                "**/thumbnails/**",
                lambda route: route.fulfill(content_type="image/svg+xml", body=thumbnail),
            )
            if clip.exists():
                page.route(
                    "**/streams/**",
                    lambda route: route.fulfill(content_type="video/webm", body=clip.read_bytes()),
                )
            page.route(
                "**/download",
                lambda route: (
                    submitted.append(route.request.post_data_json),
                    route.fulfill(status=202, json={"job_id": job_id}),
                ),
            )

            def job(route):
                polls.append(True)
                complete = len(polls) > 2
                route.fulfill(
                    json={
                        "status": "completed" if complete else "running",
                        "phase": "downloading",
                        "progress": 100 if complete else 45,
                        "file_url": "/files/fixture",
                        "filename": "media.zip",
                    }
                )

            page.route("**/jobs/*", job)
            page.goto(base)
            expect(page.locator("#inspect")).to_have_text("ตรวจสอบ")
            self.assertEqual(page.request.get(base + "/assets/cat.svg").status, 200)
            self.assertEqual(page.request.get(base + "/assets/pixel-font.ttf").status, 200)
            page.evaluate("document.fonts.ready")
            self.assertEqual(page.evaluate("getComputedStyle(document.body).colorScheme"), "dark")
            page.screenshot(path=str(output / "pixel-ui-desktop-th.png"), full_page=True)
            page.locator(".brand [data-language-toggle]").click()
            expect(page.locator("#inspect")).to_have_text("Check link")
            expect(page.locator("html")).to_have_attribute("lang", "en")
            self.assertNotIn(
                "The request could not be completed", page.locator("body").inner_text()
            )
            self.assertIn("Files kept for 60 min", page.locator("#limits").inner_text())
            page.reload()
            expect(page.locator("#inspect")).to_have_text("Check link")
            page.locator("#url").fill("https://youtube.com/watch?v=fixture")
            page.locator("#inspect").click()
            expect(page.locator("#media-picker")).to_be_visible()
            expect(page.locator(".media-tile")).to_have_count(8)
            page.locator(".picker-header [data-language-toggle]").focus()
            page.keyboard.press("Shift+Tab")
            self.assertTrue(
                page.locator(".picker-footer button").evaluate("e=>e===document.activeElement")
            )
            page.keyboard.press("Tab")
            self.assertTrue(
                page.locator(".picker-header [data-language-toggle]").evaluate(
                    "e=>e===document.activeElement"
                )
            )
            expect(page.locator("#media-title")).to_have_text(title)
            page.locator("#select-all").uncheck()
            page.locator("[data-item]").nth(0).check()
            page.locator("[data-item]").nth(1).check()
            page.locator("[data-quality]").select_option("360p")
            expect(page.locator("#picker-count")).to_have_text("Selected 2 / 8 items")
            page.screenshot(path=str(output / "pixel-ui-picker-en.png"))
            page.locator(".tile-preview").nth(1).click()
            if clip.exists():
                for _ in range(40):
                    if page.locator("#viewer-video").evaluate("v=>v.readyState>=2"):
                        break
                    page.wait_for_timeout(100)
                self.assertTrue(page.locator("#viewer-video").evaluate("v=>v.readyState>=2"))
            source = page.locator("#viewer-video").get_attribute("src")
            page.locator(".picker-header [data-language-toggle]").click()
            expect(page.locator("#picker-title")).to_have_text("เลือกสื่อที่จะบันทึก")
            self.assertEqual(page.locator("#viewer-video").get_attribute("src"), source)
            self.assertEqual(page.locator("[data-quality]").input_value(), "360p")
            expect(page.locator("[data-item]:checked")).to_have_count(2)
            page.locator("#close-viewer").click()
            page.locator(".picker-header [data-language-toggle]").click()
            page.locator("[data-quality]").focus()
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Enter")
            page.locator("[data-quality]").select_option("360p")
            page.locator("#close-picker").click()
            page.locator("#download").click()
            page.locator(".brand [data-language-toggle]").click()
            expect(page.locator("#file-link")).to_be_visible(timeout=15000)
            self.assertEqual(
                submitted[0]["selections"],
                [{"id": "image-0"}, {"id": "video-0", "quality": "360p"}],
            )
            page.locator("#url").fill("https://www.tiktok.com/@fixture")
            page.locator("#inspect").click()
            expect(page.locator(".media-tile")).to_have_count(2)
            page.locator("#select-all").uncheck()
            page.locator("[data-item]").first.check()
            page.locator("#load-more").click()
            expect(page.locator(".media-tile")).to_have_count(3)
            self.assertFalse(page.locator("[data-item]").nth(1).is_checked())
            page.locator(".tile-preview").first.click()
            expect(page.locator("#return-profile-picker")).to_be_visible()
            page.locator("#return-profile-picker").click()
            expect(page.locator(".media-tile")).to_have_count(3)
            self.assertFalse(page.locator("[data-item]").nth(1).is_checked())
            page.locator(".picker-header [data-language-toggle]").click()
            expect(page.locator("#profile-status")).to_have_text(
                "3 posts loaded · All posts returned by the platform loaded"
            )
            page.set_viewport_size({"width": 390, "height": 844})
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            self.assertTrue(
                page.locator("#media-picker").evaluate("e=>e.scrollWidth<=e.clientWidth")
            )
            page.screenshot(path=str(output / "pixel-ui-mobile-en.png"))
            page.keyboard.press("Escape")
            page.locator("#url").fill("https://youtube.com/private")
            page.locator("#inspect").click()
            expect(page.locator("#error-message")).to_have_text(
                "Sign-in is required, or the platform is restricting this post."
            )
            page.locator(".brand [data-language-toggle]").click()
            expect(page.locator("#error-message")).to_have_text(
                "ต้องล็อกอิน เว็บไซต์อาจไม่อนุญาตให้ดึงโพสต์นี้"
            )
            page.locator("#url").fill("https://youtube.com/offline")
            page.locator("#inspect").click()
            expect(page.locator("#error-message")).to_contain_text("เชื่อมต่อแอปไม่ได้")
            page.set_viewport_size({"width": 320, "height": 750})
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            self.assertEqual(errors, [])
            self.assertEqual(page.evaluate("localStorage.getItem('media-language')"), "th")
            browser.close()
            print(
                json.dumps(
                    {
                        "desktop_mobile": True,
                        "language_persistence": True,
                        "selection_quality_preserved": True,
                        "preview_preserved": True,
                        "profile_navigation": True,
                        "error_offline": True,
                        "console_errors": errors,
                    }
                )
            )
