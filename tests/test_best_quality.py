from dataclasses import replace
from unittest.mock import Mock, patch
import unittest

from backend import downloader
from backend.downloader import MediaError, select_video_formats


def fmt(height, **extra):
    return {
        "format_id": str(height),
        "url": "https://cdn.example/video.mp4",
        "height": height,
        "width": height * 16 // 9,
        "vcodec": "h264",
        "acodec": "none",
        "protocol": "https",
        "tbr": height,
        **extra,
    }


class BestQualityTests(unittest.TestCase):
    def test_best_selects_highest_original_video_and_best_separate_audio(self):
        audio = fmt(0, format_id="audio", vcodec="none", acodec="aac", abr=192)
        source = [
            fmt(360),
            fmt(720),
            fmt(2160),
            audio,
            fmt(4320, has_drm=True),
            fmt(8000, protocol="rtmp"),
        ]
        chosen = select_video_formats(source)
        self.assertEqual([f["format_id"] for f in chosen], ["2160", "audio"])
        self.assertIs(chosen[0], source[2])

    def test_muxed_original_does_not_duplicate_audio_and_legacy_api_still_works(self):
        formats = [fmt(360, acodec="aac"), fmt(1920, acodec="aac")]
        self.assertEqual(select_video_formats(formats)[0]["height"], 1920)
        self.assertEqual(len(select_video_formats(formats)), 1)
        self.assertEqual(select_video_formats(formats, "360p")[0]["height"], 360)

    def test_video_with_known_resolution_and_unspecified_codec_remains_supported(self):
        source = fmt(1080)
        source.pop("vcodec")
        self.assertEqual(select_video_formats([source]), [source])

    def test_audio_only_and_missing_video(self):
        audio = fmt(0, vcodec="none", acodec="aac", abr=192)
        self.assertEqual(select_video_formats([audio], "mp3"), [audio])
        with self.assertRaises(MediaError):
            select_video_formats([audio])

    def test_two_hour_video_is_allowed_when_duration_limit_is_disabled(self):
        raw = {
            "id": "fixture",
            "title": "fixture",
            "availability": "public",
            "duration": 7200,
            "formats": [fmt(2160, acodec="aac")],
        }
        ydl = Mock()
        ydl.cookiejar = []
        ydl.__enter__ = Mock(return_value=ydl)
        ydl.__exit__ = Mock(return_value=False)
        ydl.extract_info.return_value = raw
        with (
            patch.object(downloader, "make_ydl", return_value=ydl),
            patch.object(downloader, "settings", replace(downloader.settings, max_duration=0)),
        ):
            _, videos = downloader.video_info(
                "https://youtube.com/watch?v=fixture", use_cookies=False
            )
            self.assertEqual(len(videos), 1)
        with (
            patch.object(downloader, "make_ydl", return_value=ydl),
            patch.object(downloader, "settings", replace(downloader.settings, max_duration=1800)),
            self.assertRaises(MediaError) as error,
        ):
            downloader.video_info("https://youtube.com/watch?v=fixture", use_cookies=False)
        self.assertEqual(error.exception.code, "duration_limit")
