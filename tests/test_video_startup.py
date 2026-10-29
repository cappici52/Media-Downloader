import asyncio
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch
from backend.downloader import MediaError
from backend.streaming import PreviewStream, startup_cache
from backend.video_cache import VideoStartupCache, MemoryPreview, complete_small_mp4


def atom(kind, body=b""):
    return (len(body) + 8).to_bytes(4, "big") + kind + body


class StartupDataTests(unittest.TestCase):
    def test_only_complete_small_open_ended_mp4s_are_eligible(self):
        header = {
            "headers": {
                "Content-Type": "video/mp4",
                "Content-Length": "100",
                "Content-Range": "bytes 0-99/100",
            }
        }
        self.assertTrue(complete_small_mp4(header, "bytes=0-"))
        self.assertFalse(complete_small_mp4(header, "bytes=0-99"))
        header["headers"]["Content-Range"] = "bytes 0-99/10000000"
        self.assertFalse(complete_small_mp4(header, "bytes=0-"))

    def test_cache_is_lru_bounded_and_expires(self):
        cache = VideoStartupCache(max_bytes=8, ttl=10)
        cache.put("a", b"aaaa")
        cache.put("b", b"bbbb")
        cache.get("a")
        cache.put("c", b"cccc")
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.size, 8)
        cache.put("a", b"a")
        self.assertEqual(cache.size, 5)
        with patch("backend.video_cache.time.monotonic", return_value=10**12):
            self.assertIsNone(cache.get("a"))
        self.assertEqual(cache.size, 0)


class StartupStreamTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        startup_cache.clear()

    async def asyncTearDown(self):
        startup_cache.clear()

    def process(self, data, claimed=None, slow=False):
        length = claimed or len(data)
        header = {
            "status": 206,
            "headers": {
                "Content-Type": "video/mp4",
                "Content-Length": str(length),
                "Content-Range": f"bytes 0-{length - 1}/{length}",
                "Accept-Ranges": "bytes",
            },
        }
        reader = asyncio.StreamReader()
        reader.feed_data(json.dumps(header).encode() + b"\n" + (data[:4] if slow else data))
        if slow:

            def finish():
                reader.feed_data(data[4:])
                reader.feed_eof()

            asyncio.get_running_loop().call_later(0.05, finish)
        else:
            reader.feed_eof()
        return Mock(stdout=reader, stdin=Mock(drain=AsyncMock()), returncode=0)

    async def test_cold_tail_mp4_and_warm_seek_preserve_exact_source_bytes(self):
        data = atom(b"ftyp") + atom(b"mdat", b"original-video" * 100) + atom(b"moov", b"metadata")
        semaphore = asyncio.Semaphore(1)
        descriptor = {"url": "https://cdn.example/video.mp4", "media_type": "video/mp4"}
        spawn = AsyncMock(return_value=self.process(data))
        with patch("backend.streaming.asyncio.create_subprocess_exec", spawn):
            cold = await PreviewStream.open(descriptor, "bytes=0-", semaphore)
            self.assertEqual(b"".join([chunk async for chunk in cold.chunks()]), data)
            warm = await PreviewStream.open(descriptor, "bytes=-10", semaphore)
            self.assertEqual(b"".join([chunk async for chunk in warm.chunks()]), data[-10:])
        self.assertEqual(spawn.await_count, 1)
        self.assertEqual(semaphore._value, 1)
        with self.assertRaises(MediaError):
            MemoryPreview(data, f"bytes={len(data)}-", "video/mp4")

    async def test_slow_source_passes_through_and_truncated_prefix_releases_slot(self):
        data = atom(b"ftyp") + atom(b"moov") + atom(b"mdat", b"original")
        semaphore = asyncio.Semaphore(1)
        descriptor = {"url": "https://cdn.example/video.mp4", "media_type": "video/mp4"}
        process = self.process(data, slow=True)
        # Force the bounded buffering window to fall back before consuming bytes.
        with (
            patch(
                "backend.streaming.asyncio.create_subprocess_exec",
                AsyncMock(return_value=process),
            ),
            patch("backend.streaming.STARTUP_BUFFER_SECONDS", 0.01),
        ):
            stream = await PreviewStream.open(descriptor, "bytes=0-", semaphore)
            self.assertIsInstance(stream, PreviewStream)
            self.assertEqual(b"".join([chunk async for chunk in stream.chunks()]), data)
        with (
            patch(
                "backend.streaming.asyncio.create_subprocess_exec",
                AsyncMock(return_value=self.process(data, 1000)),
            ),
            self.assertRaises(MediaError),
        ):
            await PreviewStream.open(descriptor, "bytes=0-", semaphore)
        self.assertEqual(semaphore._value, 1)
