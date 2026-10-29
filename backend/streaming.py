"""Async lifetime management for streaming workers, including disconnects."""

import asyncio
import json
from hashlib import sha256
import os
from pathlib import Path
import sys
from fastapi.responses import StreamingResponse

from .downloader import MediaError
from .jobs import stop_process
from .video_cache import VideoStartupCache, MemoryPreview, complete_small_mp4

startup_cache = VideoStartupCache()
STARTUP_BUFFER_SECONDS = 0.75


class PreviewStream:
    def __init__(self, process, semaphore):
        self.process, self.semaphore = process, semaphore
        self.closed = False
        self.timer = None
        self.cleanup_task = None
        self.prefix = b""

    @classmethod
    async def open(cls, descriptor, range_header, semaphore):
        key = sha256(json.dumps(descriptor, sort_keys=True).encode()).digest()
        cached = startup_cache.get(key)
        if cached is not None:
            return MemoryPreview(cached, range_header, descriptor["media_type"])
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=20)
        except TimeoutError:
            raise MediaError("busy", "ระบบกำลังทำงานเต็มจำนวน กรุณาลองเล่นอีกครั้ง") from None
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "backend.stream_worker",
                cwd=str(Path(__file__).resolve().parent.parent),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                **({"start_new_session": True} if os.name != "nt" else {}),
            )
        except BaseException:
            semaphore.release()
            raise
        lease = cls(process, semaphore)
        try:
            process.stdin.write(
                (json.dumps({"descriptor": descriptor, "range": range_header}) + "\n").encode()
            )
            await process.stdin.drain()
            process.stdin.close()
            header = json.loads(await asyncio.wait_for(process.stdout.readline(), timeout=25))
            if "error" in header:
                raise MediaError(header["error"]["code"], header["error"]["message"])
            lease.header = header
            lease.timer = asyncio.create_task(lease.expire())
            if complete_small_mp4(header, range_header):
                length = int(header["headers"]["Content-Length"])
                buffered = bytearray()
                try:
                    # Chrome may probe the tail even for faststart MP4s. Give a
                    # small original file a brief chance to finish, then serve
                    # all subsequent ranges from RAM without extra CDN trips.
                    async with asyncio.timeout(STARTUP_BUFFER_SECONDS):
                        while len(buffered) < length:
                            chunk = await process.stdout.read(min(65536, length - len(buffered)))
                            if not chunk:
                                raise MediaError(
                                    "preview_unavailable", "เปิดตัวอย่างคลิปไม่ได้ กรุณาลองใหม่"
                                )
                            buffered.extend(chunk)
                except TimeoutError:
                    lease.prefix = bytes(buffered)  # Slow source: replay bytes and stream normally.
                else:
                    data = bytes(buffered)
                    await lease.close()
                    startup_cache.put(key, data)
                    return MemoryPreview(data, range_header, descriptor["media_type"])
            return lease
        except (ValueError, TimeoutError, ConnectionError, asyncio.IncompleteReadError):
            await lease.close()
            raise MediaError("preview_unavailable", "เปิดตัวอย่างคลิปไม่ได้ กรุณาลองใหม่") from None
        except BaseException:
            await lease.close()
            raise

    async def expire(self):
        await asyncio.sleep(60)
        await self.close()

    async def close(self):
        if not self.closed:
            self.closed = True
            if self.timer and self.timer is not asyncio.current_task():
                self.timer.cancel()
            self.cleanup_task = asyncio.create_task(self.cleanup())
        await asyncio.shield(self.cleanup_task)

    async def cleanup(self):
        try:
            await stop_process(self.process)
        finally:
            self.semaphore.release()

    async def chunks(self):
        try:
            remaining = int(self.header["headers"]["Content-Length"])
            if self.prefix:
                remaining -= len(self.prefix)
                yield self.prefix
                self.prefix = b""
            while remaining > 0:
                chunk = await asyncio.wait_for(
                    self.process.stdout.read(min(65536, remaining)), timeout=25
                )
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
        finally:
            await self.close()


class PreviewResponse(StreamingResponse):
    def __init__(self, lease):
        self.lease = lease
        super().__init__(
            lease.chunks(), status_code=lease.header["status"], headers=lease.header["headers"]
        )

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.lease.close()
