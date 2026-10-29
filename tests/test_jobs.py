import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from backend.downloader import MediaError
from backend.jobs import JobManager, run_worker
from backend.settings import settings


class JobTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.limits = replace(settings, root=Path(self.temp.name), workers=1, queue_size=1, ttl=1)

    async def test_completion_failure_and_ttl(self):
        async def fake(request, **kwargs):
            if request["url"] == "fail":
                raise MediaError("private", "โพสต์เป็นส่วนตัว")
            self.assertEqual(request["video_format"], "mov")
            kwargs["progress"]({"progress": 55, "phase": "downloading"})
            (Path(request["directory"]) / "media.jpg").write_bytes(b"image")
            return {"filename": "media.jpg"}

        manager = JobManager(self.limits, fake)
        await manager.start()
        try:
            job = await manager.submit("ok", [{"id": "image-0"}], video_format="mov")
            await asyncio.wait_for(manager.queue.join(), 2)
            self.assertEqual(job.status, "completed")
            self.assertEqual(job.progress, 100)
            job.finished_at = time.time() - 2
            job.readers = 1
            await manager.cleanup()
            self.assertIn(job.id, manager.jobs)
            job.readers = 0
            await manager.cleanup()
            self.assertNotIn(job.id, manager.jobs)
            self.assertFalse(job.directory.exists())
            job = await manager.submit("fail", [])
            await asyncio.wait_for(manager.queue.join(), 2)
            self.assertEqual(job.error["code"], "private")
            self.assertFalse(job.directory.exists())
        finally:
            await manager.close()

    async def test_unlimited_jobs_admit_large_current_storage_and_low_disk_still_rejects(self):
        limits = replace(self.limits, max_bytes=0, max_storage=0)
        manager = JobManager(limits)
        with patch("backend.jobs.directory_size", return_value=10 * 1024 * 1024 * 1024):
            job = await manager.submit("https://youtube.com", [{"id": "video-0"}])
        self.assertEqual(job.status, "queued")
        other = JobManager(limits)
        with (
            patch(
                "backend.jobs.shutil.disk_usage",
                return_value=SimpleNamespace(free=limits.min_free_bytes - 1),
            ),
            self.assertRaises(MediaError) as error,
        ):
            await other.submit("https://youtube.com", [{"id": "video-0"}])
        self.assertEqual(error.exception.code, "storage_limit")
        self.assertEqual(len(other.jobs), 0)

    async def test_queue_rejects_without_creating_directory(self):
        manager = JobManager(self.limits)
        await manager.submit("one", [])
        with self.assertRaises(MediaError) as error:
            await manager.submit("two", [])
        self.assertEqual(error.exception.code, "queue_full")
        self.assertEqual(len(list(self.limits.root.iterdir())), 1)

    async def test_worker_rejects_invalid_url_in_real_subprocess(self):
        with self.assertRaises(MediaError) as error:
            await run_worker(
                {"action": "info", "url": "file:///etc/passwd"}, timeout=20, limits=self.limits
            )
        self.assertEqual(error.exception.code, "invalid_scheme")

    async def test_timeout_kills_real_worker(self):
        with self.assertRaises(MediaError) as error:
            await run_worker(
                {"action": "info", "url": "https://youtube.com"}, timeout=0.001, limits=self.limits
            )
        self.assertEqual(error.exception.code, "timeout")

    async def test_restart_only_removes_owned_directories(self):
        (self.limits.root / ("a" * 32)).mkdir()
        (self.limits.root / "personal").mkdir()
        manager = JobManager(self.limits)
        await manager.start()
        await manager.close()
        self.assertFalse((self.limits.root / ("a" * 32)).exists())
        self.assertTrue((self.limits.root / "personal").exists())
