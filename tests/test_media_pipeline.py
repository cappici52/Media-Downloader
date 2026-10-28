from dataclasses import replace
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from backend import downloader


class FakeResponse:
    headers = {"Content-Type": "image/jpeg"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield b"fixture-image"


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get(self, *args, **kwargs):
        return FakeResponse()


class ImagePipelineTests(unittest.TestCase):
    def test_multiple_images_are_zipped_with_safe_names(self):
        images = [
            {"url": "https://cdn.example/a.jpg", "extension": "jpg", "headers": {}, "cookies": None}
        ] * 2
        public = {"items": [{"id": "image-0", "type": "image"}, {"id": "image-1", "type": "image"}]}
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(downloader, "inspect_media", return_value=(public, [], images)),
            patch("requests.Session", FakeSession),
        ):
            output = downloader.download_media(
                "unused", [{"id": "image-0"}, {"id": "image-1"}], Path(temp), lambda e: None
            )
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist(), ["media-001.jpg", "media-002.jpg"])
                self.assertEqual(archive.read("media-001.jpg"), b"fixture-image")
            self.assertEqual([p.name for p in Path(temp).iterdir()], ["media.zip"])

    def test_size_limit_for_unknown_length_stream(self):
        public = {"items": [{"id": "image-0", "type": "image"}]}
        images = [
            {"url": "https://cdn.example/a.jpg", "extension": "jpg", "headers": {}, "cookies": None}
        ]
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(downloader, "inspect_media", return_value=(public, [], images)),
            patch("requests.Session", FakeSession),
            patch.object(downloader, "settings", replace(downloader.settings, max_bytes=3)),
        ):
            with self.assertRaises(downloader.MediaError) as error:
                downloader.download_media("unused", [{"id": "image-0"}], Path(temp), lambda e: None)
            self.assertEqual(error.exception.code, "size_limit")


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg and ffprobe required"
)
class VideoPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.mp4"
        subprocess.run(
            [
                shutil.which("ffmpeg"),
                "-nostdin",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=64x64:r=10",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=44100",
                "-t",
                "2",
                "-c:v",
                "mpeg4",
                "-c:a",
                "aac",
                str(self.source),
            ],
            check=True,
            timeout=20,
        )

    def test_local_conversion_to_mp3_and_mkv(self):
        for extension, audio in (("mp3", True), ("mkv", False)):
            output = self.root / ("result." + extension)
            downloader.transcode([self.source], output, audio=audio)
            self.assertGreater(output.stat().st_size, 100)

    def test_duration_limit_rejects_local_file(self):
        with patch.object(downloader, "settings", replace(downloader.settings, max_duration=1)):
            with self.assertRaises(downloader.MediaError) as error:
                downloader.transcode([self.source], self.root / "result.mkv")
            self.assertEqual(error.exception.code, "duration_limit")

    def test_mixed_video_and_image_pipeline(self):
        fmt = {
            "format_id": "18",
            "url": "https://cdn.example/video.mp4",
            "protocol": "https",
            "height": 360,
            "vcodec": "mpeg4",
            "acodec": "aac",
            "ext": "mp4",
        }
        public = {
            "items": [
                {"id": "video-0", "type": "video", "qualities": [{"id": "360p"}]},
                {"id": "image-0", "type": "image"},
            ]
        }
        videos = [{"raw": {"id": "test", "title": "fixture", "formats": [fmt]}}]
        images = [
            {"url": "https://cdn.example/a.jpg", "extension": "jpg", "headers": {}, "cookies": None}
        ]
        from yt_dlp.networking import Response

        source = self.source.read_bytes()

        def send(handler, request):
            return Response(
                io.BytesIO(source),
                request.url,
                {"Content-Length": str(len(source)), "Content-Type": "video/mp4"},
            )

        directory = self.root / "job"
        directory.mkdir()
        with (
            patch.object(downloader, "inspect_media", return_value=(public, videos, images)),
            patch("yt_dlp.networking._urllib.UrllibRH._send", send),
            patch("requests.Session", FakeSession),
        ):
            output = downloader.download_media(
                "unused",
                [{"id": "video-0", "quality": "360p"}, {"id": "image-0"}],
                directory,
                lambda e: None,
            )
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.namelist(), ["media-001.mkv", "media-002.jpg"])
