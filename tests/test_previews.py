import asyncio
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from backend.downloader import MediaError, download_preview, video_preview
from backend.stream_worker import CHUNK_LIMIT, bounded_range, stream
from backend.streaming import PreviewStream


class PreviewTests(unittest.TestCase):
    def test_ranges_are_bounded_and_invalid_ranges_rejected(self):
        self.assertEqual(bounded_range(None), f"bytes=0-{CHUNK_LIMIT - 1}")
        self.assertEqual(bounded_range("bytes=100-200"), "bytes=100-200")
        self.assertEqual(bounded_range("bytes=-500"), "bytes=-500")
        self.assertEqual(bounded_range("bytes=10-"), f"bytes=10-{10 + CHUNK_LIMIT - 1}")
        for value in (
            "bytes=",
            "bytes=-0",
            "bytes=20-10",
            "bytes=0-1,3-4",
            "other=0-1",
            "bytes=" + "9" * 100 + "-",
        ):
            with self.subTest(value=value), self.assertRaises(MediaError):
                bounded_range(value)

    def test_preview_prefers_progressive_mp4_with_audio_and_does_not_expose_cookies(self):
        base = {
            "protocol": "https",
            "ext": "mp4",
            "vcodec": "avc",
            "acodec": "aac",
            "height": 720,
            "url": "https://cdn.example/720.mp4",
        }
        entry = {
            "formats": [dict(base, height=1080), base, dict(base, acodec="none", height=2160)],
            "http_headers": {
                "Cookie": "secret",
                "Authorization": "secret",
                "Referer": "https://x.com/",
            },
        }
        result = video_preview(entry)
        self.assertEqual(result["url"], base["url"])
        self.assertEqual(result["headers"], {"Referer": "https://x.com/"})
        self.assertFalse(result["muted"])
        self.assertIsNone(video_preview({"formats": [dict(base, protocol="m3u8_native")]}))

    def mock_session(self, content, headers, status=206):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.headers, response.status_code = headers, status
        response.iter_content.return_value = [content]
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.get.return_value = response
        return session, response

    def test_stream_returns_range_headers_and_bytes_without_creating_a_file(self):
        session, _ = self.mock_session(
            b"clip", {"Content-Length": "4", "Content-Range": "bytes 10-13/100"}
        )
        output = io.BytesIO()
        descriptor = {
            "url": "https://cdn.example/video.mp4",
            "media_type": "video/mp4",
            "headers": {"Cookie": "secret"},
        }
        with (
            patch("requests.Session", return_value=session),
            patch("backend.stream_worker.validate_network_url"),
        ):
            stream({"descriptor": descriptor, "range": "bytes=10-13"}, output)
        header, body = output.getvalue().split(b"\n", 1)
        self.assertEqual(json.loads(header)["status"], 206)
        self.assertEqual(body, b"clip")
        self.assertNotIn("Cookie", session.get.call_args.kwargs["headers"])

    def test_stream_rejects_ignored_ranges_and_oversized_responses(self):
        descriptor = {"url": "https://cdn.example/video.mp4", "media_type": "video/mp4"}
        for length in (CHUNK_LIMIT + 1, -1):
            session, _ = self.mock_session(b"clip", {"Content-Length": str(length)}, status=200)
            with (
                patch("requests.Session", return_value=session),
                patch("backend.stream_worker.validate_network_url"),
                self.assertRaises(MediaError),
            ):
                stream({"descriptor": descriptor}, io.BytesIO())

    def test_thumbnail_is_resized_and_verified(self):
        source = io.BytesIO()
        Image.new("RGB", (2400, 1600), "blue").save(source, format="JPEG")
        session, _ = self.mock_session(
            source.getvalue(), {"Content-Type": "image/jpeg"}, status=200
        )
        with (
            tempfile.TemporaryDirectory() as temp,
            patch("requests.Session", return_value=session),
            patch("backend.downloader.validate_network_url"),
        ):
            result = download_preview("https://cdn.example/image.jpg", Path(temp))
            with Image.open(Path(temp) / result["filename"]) as image:
                self.assertLessEqual(max(image.size), 1280)
            self.assertEqual(result["media_type"], "image/jpeg")
            self.assertFalse((Path(temp) / "preview").exists())


class StreamProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stream_worker_rejects_internal_addresses_and_releases_slot(self):
        semaphore = asyncio.Semaphore(1)
        with self.assertRaises(MediaError):
            await PreviewStream.open(
                {"url": "http://127.0.0.1/secret", "media_type": "video/mp4"}, None, semaphore
            )
        self.assertEqual(semaphore._value, 1)
