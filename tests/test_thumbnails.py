import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backend.downloader import MediaError
from backend.settings import settings
from backend.thumbnails import ThumbnailCache


class ThumbnailCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.limits = replace(settings, root=Path(self.temp.name), ttl=300, max_items=2)
        self.calls = []

        async def worker(request, **kwargs):
            self.calls.append(request["url"])
            path = Path(request["directory"]) / "thumbnail.jpg"
            path.write_bytes(request["url"][-1:].encode() * 4)
            return {"filename": path.name, "media_type": "image/jpeg"}

        self.cache = ThumbnailCache(self.limits, worker, max_bytes=8, max_entries=2)

    async def asyncTearDown(self):
        await self.cache.close()
        self.temp.cleanup()

    async def test_identical_requests_share_one_fetch_and_files_are_removed(self):
        results = await asyncio.gather(*(self.cache.get("https://cdn.example/a") for _ in range(3)))
        self.assertEqual(results, [(b"aaaa", "image/jpeg")] * 3)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(list(self.limits.root.iterdir()), [])
        self.assertEqual(await self.cache.get("https://cdn.example/a"), results[0])
        self.assertEqual(len(self.calls), 1)

    async def test_lru_and_ttl_keep_memory_bounded(self):
        for key in ("a", "b", "a", "c", "b"):
            await self.cache.get("https://cdn.example/" + key)
        self.assertEqual(self.calls, ["https://cdn.example/" + key for key in ("a", "b", "c", "b")])
        self.assertLessEqual(self.cache.size, 8)
        with patch("backend.thumbnails.time.monotonic", return_value=10**12):
            await self.cache.get("https://cdn.example/b")
        self.assertEqual(len(self.calls), 5)

    async def test_entry_limit_and_pending_queue_are_bounded(self):
        self.cache.max_entries = 1
        for key in ("a", "b", "a"):
            await self.cache.get("https://cdn.example/" + key)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(len(self.cache.entries), 1)
        entered, release = asyncio.Event(), asyncio.Event()
        count = 0
        worker = self.cache.worker

        async def blocked(request, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                entered.set()
            await release.wait()
            return await worker(request, **kwargs)

        self.cache.worker = blocked
        tasks = [
            asyncio.create_task(self.cache.get("https://cdn.example/" + key)) for key in ("c", "d")
        ]
        await entered.wait()
        try:
            with self.assertRaises(MediaError) as error:
                await self.cache.get("https://cdn.example/e")
            self.assertEqual(error.exception.code, "busy")
        finally:
            release.set()
            await asyncio.gather(*tasks)

    async def test_cancelled_waiter_does_not_cancel_shared_work(self):
        entered, release = asyncio.Event(), asyncio.Event()
        worker = self.cache.worker

        async def blocked(request, **kwargs):
            entered.set()
            await release.wait()
            return await worker(request, **kwargs)

        self.cache.worker = blocked
        first = asyncio.create_task(self.cache.get("https://cdn.example/a"))
        await entered.wait()
        second = asyncio.create_task(self.cache.get("https://cdn.example/a"))
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        release.set()
        self.assertEqual(await second, (b"aaaa", "image/jpeg"))
        self.assertEqual(len(self.calls), 1)

    async def test_failure_can_be_retried_and_shutdown_cleans_pending_tasks(self):
        async def fail(request, **kwargs):
            raise MediaError("preview", "failed")

        self.cache.worker = fail
        for _ in range(2):
            with self.assertRaises(MediaError):
                await self.cache.get("https://cdn.example/a")
        self.assertEqual(self.cache.size, 0)
        entered = asyncio.Event()

        async def blocked(request, **kwargs):
            entered.set()
            await asyncio.Event().wait()

        self.cache.worker = blocked
        task = asyncio.create_task(self.cache.get("https://cdn.example/b"))
        await entered.wait()
        await self.cache.close()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.cache.pending)
        self.assertEqual(list(self.limits.root.iterdir()), [])
