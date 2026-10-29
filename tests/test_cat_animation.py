"""Opt-in real-browser cat animation regression with held API responses."""

import os
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(os.getenv("MEDIA_UI_URL"), "Set MEDIA_UI_URL for browser QA")
class CatAnimationTests(unittest.TestCase):
    def test_chewing_success_error_cancellation_and_reduced_motion(self):
        from playwright.sync_api import sync_playwright, expect
        from PIL import Image

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chrome")
            page = browser.new_page(
                viewport={"width": 1280, "height": 950}, reduced_motion="no-preference"
            )
            errors, pending = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route("**/info", lambda route: pending.append(route))
            page.goto(os.environ["MEDIA_UI_URL"])
            page.evaluate(
                'window.catStates=[];new MutationObserver(()=>catStates.push(document.querySelector("#cat-scene").dataset.state)).observe(document.querySelector("#cat-scene"),{attributes:true,attributeFilter:["data-state"]})'
            )
            scene = page.locator("#cat-scene")

            def begin():
                page.locator("#url").fill("https://youtube.com/watch?v=fixture")
                page.locator("#inspect").click()
                expect(scene).to_have_attribute("data-state", "chewing")
                expect(page.locator("#empty-state")).to_be_visible()
                expect(page.locator("#inspect")).to_be_disabled()

            result = {
                "type": "image",
                "title": "fixture",
                "thumbnail": None,
                "items": [{"id": "image-0", "type": "image", "thumbnail": None, "qualities": []}],
            }
            begin()
            expect(scene).to_have_attribute("data-ready", "true")
            output = Path(tempfile.gettempdir())
            frames = []
            for position in (100, 300):
                page.locator(".cat-chew").evaluate_all(
                    "(es,time)=>es.forEach(e=>e.getAnimations().forEach(a=>{a.pause();a.currentTime=time}))",
                    position,
                )
                path = output / f"cat-chewing-{position}.png"
                scene.screenshot(path=str(path))
                pixels = Image.open(path).convert("RGB")
                white_pixels = sum(
                    1 for r, g, b in pixels.get_flattened_data() if min(r, g, b) > 160
                )
                self.assertGreater(
                    white_pixels, 1000, "The cat must never disappear between frames"
                )
                frames.append(pixels.tobytes())
            self.assertNotEqual(
                frames[0], frames[1], "The mouth must actually change between frames"
            )
            page.locator(".cat-chew").evaluate_all(
                "es=>es.forEach(e=>e.getAnimations().forEach(a=>a.play()))"
            )
            pending.pop(0).fulfill(json=result)
            expect(scene).to_have_attribute("data-state", "spitting")
            page.screenshot(path=str(output / "cat-animation-success.png"))
            expect(page.locator("#media-picker")).to_be_visible()
            expect(scene).to_have_attribute("data-state", "idle")
            page.keyboard.press("Escape")

            page.evaluate("catStates.length=0")
            begin()
            pending.pop(0).fulfill(
                status=400,
                json={
                    "error": {"code": "no_media", "message": "ไม่พบวิดีโอหรือรูปในลิงก์นี้ หรือเนื้อหาถูกลบแล้ว"}
                },
            )
            expect(scene).to_have_attribute("data-state", "idle")
            expect(page.locator("#error-message")).not_to_be_empty()
            self.assertNotIn("spitting", page.evaluate("catStates"))

            page.evaluate("catStates.length=0")
            begin()
            page.locator("#url").fill("https://youtube.com/watch?v=changed")
            expect(scene).to_have_attribute("data-state", "idle")
            pending.pop(0).fulfill(json=result)
            page.wait_for_timeout(800)
            expect(page.locator("#media-picker")).not_to_be_visible()
            self.assertNotIn("spitting", page.evaluate("catStates"))

            begin()
            pending.pop(0).fulfill(json=result)
            expect(scene).to_have_attribute("data-state", "spitting")
            page.locator("#url").fill("https://youtube.com/watch?v=changed-during-success")
            expect(scene).to_have_attribute("data-state", "idle")
            page.wait_for_timeout(750)
            expect(page.locator("#media-picker")).not_to_be_visible()

            page.emulate_media(reduced_motion="reduce")
            page.evaluate("catStates.length=0")
            begin()
            expect(page.locator(".cat-scene .empty-cat")).to_have_css("opacity", "1")
            expect(page.locator(".cat-chew-open")).to_have_css("display", "none")
            pending.pop(0).fulfill(json=result)
            expect(page.locator("#media-picker")).to_be_visible()
            self.assertNotIn("spitting", page.evaluate("catStates"))
            self.assertEqual(errors, [])
            browser.close()
