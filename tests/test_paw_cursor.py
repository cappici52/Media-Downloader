"""Opt-in browser regression for decorative pixel paw pointer behavior."""

import os
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(os.getenv("MEDIA_UI_URL"), "Set MEDIA_UI_URL for browser QA")
class PawCursorTests(unittest.TestCase):
    def test_states_loading_dialog_layer_motion_and_touch(self):
        from playwright.sync_api import sync_playwright, expect

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="chrome")
            page = browser.new_page(viewport={"width": 1280, "height": 950})
            errors, pending = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route("**/info", lambda route: pending.append(route))
            page.goto(os.environ["MEDIA_UI_URL"])
            page.bring_to_front()
            cursor = page.locator("#paw-cursor")
            page.mouse.move(30, 250)
            expect(page.locator("html")).to_have_attribute("data-paw-cursor", "on")
            expect(cursor).to_have_attribute("data-kind", "default")
            self.assertTrue(cursor.evaluate('e=>e.matches(":popover-open")'))
            expect(cursor).to_have_css("pointer-events", "none")
            page.mouse.down()
            expect(cursor).to_have_attribute("data-pressed", "true")
            page.mouse.up()
            expect(cursor).to_have_attribute("data-pressed", "false")
            cursor.evaluate("e=>e.hidePopover()")
            expect(page.locator("html")).not_to_have_attribute("data-paw-cursor", "on")
            page.mouse.move(40, 260)
            expect(page.locator("html")).to_have_attribute("data-paw-cursor", "on")
            page.locator("#url").hover()
            expect(cursor).to_have_attribute("data-kind", "text")
            expect(page.locator(".paw-caret")).to_have_css("display", "block")
            page.locator("#inspect").hover()
            expect(cursor).to_have_attribute("data-kind", "pointer")
            page.locator("#download").hover()
            expect(cursor).to_have_attribute("data-kind", "disabled")
            page.locator("#url").fill("https://youtube.com/watch?v=fixture")
            page.locator("#inspect").click()
            expect(cursor).to_have_attribute("data-kind", "busy")
            expect(page.locator(".paw-rotor")).to_have_css("animation-name", "paw-spin")
            page.screenshot(path=str(Path(tempfile.gettempdir()) / "pixel-paw-loading.png"))
            page.locator("#cat-motion-toggle").click()
            expect(page.locator(".paw-rotor")).to_have_css("animation-name", "none")
            pending.pop(0).fulfill(
                json={
                    "type": "image",
                    "title": "fixture",
                    "thumbnail": None,
                    "items": [
                        {"id": "image-0", "type": "image", "thumbnail": None, "qualities": []}
                    ],
                }
            )
            expect(page.locator("#media-picker")).to_be_visible()
            self.assertTrue(cursor.evaluate('e=>e.matches(":popover-open")'))
            page.locator(".tile-preview").hover()
            expect(cursor).to_have_attribute("data-kind", "pointer")
            self.assertTrue(
                page.locator(".tile-preview").evaluate(
                    'e=>{const r=e.getBoundingClientRect();return !!document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest(".tile-preview")}'
                )
            )
            page.locator(".tile-preview").click()
            expect(page.locator("#media-viewer")).to_be_visible()
            page.locator("#close-viewer").click()
            page.keyboard.press("Escape")
            expect(page.locator("#media-picker")).not_to_be_visible()
            page.locator("#url").focus()
            page.keyboard.press("Tab")
            self.assertTrue(page.locator("#inspect").evaluate("e=>e===document.activeElement"))
            page.locator("#cat-motion-toggle").click()
            page.emulate_media(forced_colors="active")
            page.mouse.move(30, 250)
            self.assertIsNone(page.locator("html").get_attribute("data-paw-cursor"))
            expect(cursor).to_have_css("display", "none")
            expect(page.locator("body")).to_have_css("cursor", "auto")
            self.assertEqual(errors, [])
            page.close()

            mobile = browser.new_context(
                viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
            )
            touch = mobile.new_page()
            touch.goto(os.environ["MEDIA_UI_URL"])
            touch.locator("#url").tap()
            self.assertIsNone(touch.locator("html").get_attribute("data-paw-cursor"))
            self.assertTrue(touch.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            mobile.close()
            browser.close()
