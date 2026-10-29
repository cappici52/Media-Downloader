"""Bounded in-memory image cache with its own guarded worker pool."""

import asyncio
from collections import OrderedDict
from hashlib import sha256
from pathlib import Path
import shutil
import time
from uuid import uuid4

from .downloader import MediaError


class ThumbnailCache:
    def __init__(self, limits, worker, *, max_bytes=32 * 1024 * 1024, max_entries=256):
        self.limits, self.worker = limits, worker
        self.max_bytes, self.max_entries = max_bytes, max_entries
        self.ttl = min(300, limits.ttl)
        self.slots = asyncio.Semaphore(2)
        self.entries = OrderedDict()
        self.pending = {}
        self.size = 0

    def _remove(self, key):
        entry = self.entries.pop(key)
        self.size -= len(entry[1])

    def _prune(self):
        now = time.monotonic()
        for key, (expires, _, _) in list(self.entries.items()):
            if expires <= now:
                self._remove(key)

    def _finished(self, key, task):
        if self.pending.get(key) is task:
            self.pending.pop(key)
        if not task.cancelled():
            task.exception()  # Also consume failures when every browser waiter disconnected.

    async def get(self, url):
        self._prune()
        key = sha256(url.encode()).digest()
        if key in self.entries:
            self.entries.move_to_end(key)
            _, data, media_type = self.entries[key]
            return data, media_type
        task = self.pending.get(key)
        if task is None:
            if len(self.pending) >= self.limits.max_items:
                raise MediaError("busy", "ระบบกำลังทำงานเต็มจำนวน กรุณารอสักครู่")
            task = asyncio.create_task(self._load(key, url))
            self.pending[key] = task
            task.add_done_callback(lambda done: self._finished(key, done))
        return await asyncio.shield(task)

    async def _load(self, key, url):
        directory = self.limits.root / uuid4().hex
        try:
            async with asyncio.timeout(60):
                async with self.slots:
                    directory.mkdir()
                    result = await self.worker(
                        {"action": "preview", "url": url, "directory": str(directory)},
                        timeout=30,
                        limits=self.limits,
                    )
                    filename = result["filename"]
                    path = directory / filename
                    if (
                        Path(filename).name != filename
                        or path.is_symlink()
                        or not path.is_file()
                        or path.stat().st_size > 12 * 1024 * 1024
                    ):
                        raise MediaError("preview", "ไม่สามารถแสดงตัวอย่างรูปนี้ได้")
                    data = await asyncio.to_thread(path.read_bytes)
                    media_type = result["media_type"]
                    if media_type != "image/jpeg":
                        raise MediaError("preview", "ไม่สามารถแสดงตัวอย่างรูปนี้ได้")
                    self._prune()
                    if len(data) <= self.max_bytes:
                        while self.entries and (
                            len(self.entries) >= self.max_entries
                            or self.size + len(data) > self.max_bytes
                        ):
                            self._remove(next(iter(self.entries)))
                        self.entries[key] = (time.monotonic() + self.ttl, data, media_type)
                        self.size += len(data)
                    return data, media_type
        except TimeoutError:
            raise MediaError("busy", "ระบบกำลังทำงานเต็มจำนวน กรุณาเปิดตัวอย่างอีกครั้ง") from None
        finally:
            await asyncio.to_thread(shutil.rmtree, directory, True)

    async def close(self):
        tasks = list(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.pending.clear()
        self.entries.clear()
        self.size = 0
