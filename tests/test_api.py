from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from backend import main
from backend.jobs import JobManager
from backend.settings import settings
from backend.validators import ValidatedURL


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        async def fake(request, **kwargs):
            if request["action"] == "info":
                return {
                    "title": "ตัวอย่าง",
                    "type": "image",
                    "thumbnail": "https://cdn.example/a.jpg",
                    "items": [
                        {
                            "id": "image-0",
                            "type": "image",
                            "thumbnail": "https://cdn.example/a.jpg",
                            "title": "รูป",
                            "qualities": [],
                        }
                    ],
                    "images": [],
                }
            (Path(request["directory"]) / "media.jpg").write_bytes(b"test-image")
            return {"filename": "media.jpg"}

        limits = replace(settings, root=Path(self.temp.name), workers=1)
        self.manager = JobManager(limits, fake)
        self.patcher = patch.object(main, "manager", self.manager)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client = TestClient(main.app, base_url="http://localhost")
        self.client.__enter__()
        self.addCleanup(lambda: self.client.__exit__(None, None, None))

    def valid_dns(self):
        return patch.object(
            main,
            "validate_url",
            return_value=ValidatedURL("https://youtube.com/", "youtube.com", 443, ("8.8.8.8",)),
        )

    def test_rejects_invalid_platform_and_malformed_requests(self):
        response = self.client.post("/info", json={"url": "http://127.0.0.1"})
        self.assertEqual(response.status_code, 400)
        for body in ({}, {"url": "https://youtube.com", "cookies": "secret"}, {"url": 42}):
            self.assertEqual(self.client.post("/info", json=body).status_code, 422)

    def test_private_origin_host_and_body_policy(self):
        self.assertEqual(
            self.client.post(
                "/info", headers={"Origin": "https://evil.example"}, json={"url": "x"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/health", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403
        )
        self.assertEqual(
            self.client.get("/health", headers={"Host": "evil.example"}).status_code, 400
        )
        self.assertEqual(self.client.post("/info", content="x" * 65537).status_code, 413)

    def test_info_rewrites_thumbnails(self):
        with self.valid_dns():
            response = self.client.post("/info", json={"url": "https://youtube.com"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["thumbnail"].startswith("/thumbnails/"))
        self.assertNotIn("cdn.example", response.text)

    def test_video_preview_uses_private_ticket_and_streams_a_range(self):
        from types import SimpleNamespace

        descriptor = {
            "url": "https://cdn.example/private-signed.mp4",
            "headers": {},
            "media_type": "video/mp4",
            "muted": False,
        }
        data = {
            "type": "video",
            "title": "คลิป",
            "thumbnail": None,
            "items": [
                {
                    "id": "video-0",
                    "type": "video",
                    "thumbnail": None,
                    "qualities": [],
                    "_preview": descriptor,
                }
            ],
        }
        with self.valid_dns(), patch.object(self.manager, "inspect", AsyncMock(return_value=data)):
            response = self.client.post("/info", json={"url": "https://youtube.com"})
        self.assertNotIn("private-signed", response.text)
        self.assertNotIn("_preview", response.text)
        path = response.json()["items"][0]["preview_url"]

        async def chunks():
            yield b"clip"

        lease = SimpleNamespace(
            header={
                "status": 206,
                "headers": {
                    "Content-Length": "4",
                    "Content-Range": "bytes 10-13/100",
                    "Content-Type": "video/mp4",
                },
            },
            chunks=chunks,
            close=AsyncMock(),
        )
        with patch.object(main.PreviewStream, "open", AsyncMock(return_value=lease)) as opener:
            streamed = self.client.get(path, headers={"Range": "bytes=10-13"})
        self.assertEqual(streamed.status_code, 206)
        self.assertEqual(streamed.content, b"clip")
        self.assertEqual(streamed.headers["content-range"], "bytes 10-13/100")
        self.assertEqual(opener.call_args.args[1], "bytes=10-13")
        lease.close.assert_awaited()
        self.assertEqual(self.client.get("/streams/expired/0").status_code, 404)

    def test_job_to_file_round_trip(self):
        with self.valid_dns():
            response = self.client.post(
                "/download", json={"url": "https://youtube.com", "selections": [{"id": "image-0"}]}
            )
        self.assertEqual(response.status_code, 202)
        identifier = response.json()["job_id"]
        self.client.portal.call(self.manager.queue.join)
        status = self.client.get(f"/jobs/{identifier}").json()
        self.assertEqual(status["status"], "completed")
        response = self.client.get(status["file_url"])
        self.assertEqual(response.content, b"test-image")
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertEqual(self.manager.jobs[identifier].readers, 0)

    def test_missing_jobs_files_and_duplicate_selection(self):
        self.assertEqual(self.client.get("/jobs/missing").status_code, 404)
        self.assertEqual(self.client.get("/files/../../etc/passwd").status_code, 404)
        self.assertEqual(self.client.get("/files/missing").status_code, 404)
        with self.valid_dns():
            response = self.client.post(
                "/download",
                json={
                    "url": "https://youtube.com",
                    "selections": [{"id": "image-0"}, {"id": "image-0"}],
                },
            )
        self.assertEqual(response.status_code, 400)


class StaticPixelAssetTests(unittest.TestCase):
    def test_pixel_assets_are_self_hosted_and_other_files_stay_blocked(self):
        client = TestClient(main.app, base_url="http://localhost")
        for filename in ("cat.svg", "pixel-font.ttf", "pixel-font-license.txt", "i18n.js"):
            response = client.get("/assets/" + filename)
            self.assertEqual(response.status_code, 200)
            self.assertIn("script-src 'self'", response.headers["content-security-policy"])
        for filename in (".env", "main.py", "unknown.js"):
            self.assertEqual(client.get("/assets/" + filename).status_code, 404)
