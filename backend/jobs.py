"""Bounded in-memory queue with disposable workers and TTL-managed artifacts.

Run one ASGI process: queue state is deliberately local. Restart discards jobs
and removes orphaned files; this app is not a persistent/public download service.
"""

import asyncio
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import time
from uuid import uuid4

from .downloader import MediaError
from .settings import settings
from .browser_session import browser_session


def directory_size(directory):
    size = 0
    for path in directory.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                size += path.stat().st_size
        except FileNotFoundError:
            pass
    return size


async def stop_process(process):
    if process.returncode is not None:
        return
    if os.name == "nt":
        killer = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await killer.wait()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    await process.wait()


async def run_worker(request, *, timeout, progress=None, limits=settings):
    request = dict(request)
    if request.get("action") in ("info", "download"):
        snapshot = browser_session.for_url(request.get("url", ""))
        if snapshot is not None:
            request["_browser_session"] = snapshot
    kwargs = {"start_new_session": True} if os.name != "nt" else {}
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "backend.worker",
        cwd=str(Path(__file__).resolve().parent.parent),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        limit=8 * 1024 * 1024,
        **kwargs,
    )

    async def communicate():
        process.stdin.write((json.dumps(request) + "\n").encode())
        await process.stdin.drain()
        process.stdin.close()
        result = None
        while line := await process.stdout.readline():
            try:
                event = json.loads(line)
            except (ValueError, UnicodeError):
                continue  # Third-party libraries occasionally print non-protocol lines.
            if not isinstance(event, dict):
                continue
            if event.get("event") == "error":
                raise MediaError(
                    event.get("code", "worker"), event.get("message", "ดาวน์โหลดไม่สำเร็จ")
                )
            if event.get("event") == "result":
                result = event["data"]
            elif event.get("event") == "progress" and progress:
                progress(event)
        await process.wait()
        if process.returncode or result is None:
            raise MediaError("worker", "งานหยุดทำงาน กรุณาลองใหม่อีกครั้ง")
        return result

    async def monitor():
        while True:
            await asyncio.sleep(0.25)
            if (
                request.get("directory")
                and await asyncio.to_thread(directory_size, Path(request["directory"]))
                > limits.max_bytes
            ):
                raise MediaError("size_limit", "ไฟล์รวมมีขนาดเกินที่กำหนด")
            if await asyncio.to_thread(directory_size, limits.root) > limits.max_storage:
                raise MediaError("storage_limit", "พื้นที่เก็บไฟล์เต็ม กรุณารอระบบล้างไฟล์เก่า")

    communication = asyncio.create_task(communicate())
    monitoring = asyncio.create_task(monitor())
    try:
        done, _ = await asyncio.wait(
            (communication, monitoring), timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        if not done:
            raise MediaError("timeout", "งานใช้เวลานานเกินกำหนด กรุณาลองใหม่")
        for task in done:
            if task.exception():
                raise task.exception()
        return communication.result()
    finally:
        for task in (communication, monitoring):
            if not task.done():
                task.cancel()
        await asyncio.gather(communication, monitoring, return_exceptions=True)
        await stop_process(process)


@dataclass
class Job:
    id: str
    url: str
    selections: list
    directory: Path
    video_format: str = "mkv"
    status: str = "queued"
    progress: float = 0
    phase: str = "queued"
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    filename: str | None = None
    error: dict | None = None
    readers: int = 0

    def public(self):
        return {
            "id": self.id,
            "status": self.status,
            "progress": self.progress,
            "phase": self.phase,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "file_url": f"/files/{self.id}" if self.status == "completed" else None,
            "filename": self.filename,
        }


class JobManager:
    def __init__(self, limits=settings, worker=run_worker):
        self.limits = limits
        self.worker = worker
        self.jobs = {}
        self.queue = asyncio.Queue(maxsize=limits.queue_size)
        self.slots = asyncio.Semaphore(limits.workers)
        self.tasks = []

    async def start(self):
        self.limits.root.mkdir(parents=True, exist_ok=True)
        # Only remove UUID-owned directories, never arbitrary contents of DOWNLOAD_DIR.
        for path in self.limits.root.iterdir():
            if (
                path.is_dir()
                and not path.is_symlink()
                and len(path.name) == 32
                and all(c in "0123456789abcdef" for c in path.name)
            ):
                await asyncio.to_thread(shutil.rmtree, path)
        self.tasks = [asyncio.create_task(self._consumer()) for _ in range(self.limits.workers)]
        self.tasks.append(asyncio.create_task(self._janitor()))

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def submit(self, url, selections, *, video_format="mkv"):
        await self.cleanup()
        if self.queue.full():
            raise MediaError("queue_full", "คิวงานเต็ม กรุณารอสักครู่แล้วลองใหม่")
        if len(self.jobs) >= self.limits.max_history:
            raise MediaError("history_full", "มีงานในระบบครบจำนวนแล้ว กรุณารอระบบล้างงานเก่า")
        if (
            await asyncio.to_thread(directory_size, self.limits.root) + self.limits.max_bytes
            > self.limits.max_storage
        ):
            raise MediaError("storage_limit", "พื้นที่เก็บไฟล์ไม่เพียงพอ กรุณารอระบบล้างไฟล์เก่า")
        identifier = uuid4().hex
        directory = self.limits.root / identifier
        directory.mkdir()
        job = Job(identifier, url, selections, directory, video_format=video_format)
        self.jobs[identifier] = job
        try:
            self.queue.put_nowait(job)
        except asyncio.QueueFull:
            self.jobs.pop(identifier)
            directory.rmdir()
            raise MediaError("queue_full", "คิวงานเต็ม กรุณารอสักครู่แล้วลองใหม่") from None
        return job

    async def inspect(self, url, cursor=None):
        if self.slots.locked():
            raise MediaError("busy", "ระบบกำลังทำงานเต็มจำนวน กรุณารอสักครู่")
        async with self.slots:
            request = {"action": "info", "url": url}
            if cursor is not None:
                request["cursor"] = cursor
            return await self.worker(request, timeout=self.limits.info_timeout, limits=self.limits)

    async def _consumer(self):
        while True:
            job = await self.queue.get()
            try:
                async with self.slots:
                    job.status = "running"
                    job.phase = "inspecting"

                    def update(event):
                        job.progress = max(job.progress, min(99, float(event.get("progress", 0))))
                        job.phase = event.get("phase", "downloading")

                    result = await self.worker(
                        {
                            "action": "download",
                            "url": job.url,
                            "selections": job.selections,
                            "video_format": job.video_format,
                            "directory": str(job.directory),
                        },
                        timeout=self.limits.timeout,
                        progress=update,
                        limits=self.limits,
                    )
                    filename = result["filename"]
                    if Path(filename).name != filename or not (job.directory / filename).is_file():
                        raise MediaError("worker", "ไม่พบไฟล์ที่ดาวน์โหลดเสร็จแล้ว")
                    job.filename = filename
                    job.status = "completed"
                    job.progress = 100
                    job.phase = "completed"
            except asyncio.CancelledError:
                await asyncio.to_thread(shutil.rmtree, job.directory, True)
                raise
            except Exception as error:
                job.status = "failed"
                job.phase = "failed"
                job.error = {
                    "code": getattr(error, "code", "job_failed"),
                    "message": str(error)
                    if isinstance(error, MediaError)
                    else "ดาวน์โหลดไม่สำเร็จ กรุณาลองใหม่",
                }
                await asyncio.to_thread(shutil.rmtree, job.directory, True)
            finally:
                job.finished_at = time.time()
                self.queue.task_done()

    async def cleanup(self):
        now = time.time()
        for identifier, job in list(self.jobs.items()):
            if (
                job.finished_at is not None
                and now - job.finished_at >= self.limits.ttl
                and not job.readers
            ):
                self.jobs.pop(identifier, None)
                await asyncio.to_thread(shutil.rmtree, job.directory, True)

    async def _janitor(self):
        while True:
            await asyncio.sleep(min(60, self.limits.ttl))
            await self.cleanup()
