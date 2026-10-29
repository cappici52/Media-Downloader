"""FastAPI endpoints for the private, single-process localhost application."""

from contextlib import asynccontextmanager
import asyncio
import copy
from pathlib import Path
import shutil
import time
from uuid import uuid4
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException

from .downloader import MediaError
from .jobs import JobManager, run_worker
from .settings import settings
from .validators import URLValidationError, validate_url
from .streaming import PreviewStream, PreviewResponse
from .browser_session import browser_session


manager = JobManager()
previews = {}
thumbnail_pending = 0
ROOT = Path(__file__).resolve().parent.parent


class ClosingFileResponse(FileResponse):
    """Release file leases even if the browser disconnects while receiving."""

    def __init__(self, *args, on_close, **kwargs):
        super().__init__(*args, **kwargs)
        self.on_close = on_close

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.on_close()


@asynccontextmanager
async def lifespan(app):
    await manager.start()
    await browser_session.refresh()
    try:
        yield
    finally:
        await manager.close()
        previews.clear()
        browser_session.clear()


app = FastAPI(title="Personal Media Downloader", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])


def error_response(code, message, status=400):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


@app.middleware("http")
async def private_request_policy(request: Request, call_next):
    origin = request.headers.get("origin")
    site = request.headers.get("sec-fetch-site")
    expected = f"{request.url.scheme}://{request.url.netloc}"
    if (origin and origin != expected) or site == "cross-site":
        return error_response("origin", "ไม่อนุญาตคำขอจากเว็บไซต์อื่น", 403)
    if request.method in ("POST", "PUT", "PATCH"):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 65536:
                return error_response("body_limit", "ข้อมูลคำขอมีขนาดใหญ่เกินไป", 413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    return response


@app.exception_handler(URLValidationError)
async def invalid_url(request, error):
    return error_response(error.code, str(error))


@app.exception_handler(MediaError)
async def media_error(request, error):
    status = 429 if error.code in ("busy", "queue_full", "history_full") else 400
    if error.code == "storage_limit":
        status = 507
    return error_response(error.code, str(error), status)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, error):
    return error_response("invalid_request", "ข้อมูลไม่ถูกต้อง กรุณาตรวจสอบลิงก์และรายการที่เลือก", 422)


@app.exception_handler(HTTPException)
async def http_error(request, error):
    message = (
        "ไม่พบหน้าหรือไฟล์นี้" if error.status_code == 404 else "ไม่สามารถทำรายการนี้ได้ กรุณาตรวจสอบคำขอ"
    )
    return error_response("http_error", message, error.status_code)


class InfoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    url: str = Field(min_length=1, max_length=8192)


class InfoQuery(InfoRequest):
    cursor: str | None = Field(default=None, min_length=1, max_length=4096)


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^(?:(video|image)-[0-9]{1,3}|post-[A-Za-z0-9_-]{1,28})$")
    quality: str | None = Field(default=None, pattern=r"^(best|mp3|[0-9]{2,5}p)$")


class DownloadRequest(InfoRequest):
    video_format: Literal["mkv", "mp4", "mov"] = "mkv"
    selections: list[Selection] = Field(min_length=1, max_length=settings.max_items)


def prune_previews():
    now = time.time()
    for identifier, entry in list(previews.items()):
        if entry["expires"] <= now:
            previews.pop(identifier, None)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/session")
async def session_status():
    return browser_session.status()


@app.post("/session/refresh")
async def refresh_session(request: Request):
    if (await request.body()).strip():
        return error_response("invalid_request", "ไม่รับข้อมูล cookies จากผู้ใช้", 422)
    return await browser_session.refresh()


@app.post("/info")
async def info(payload: InfoQuery):
    url = (await asyncio.to_thread(validate_url, payload.url)).url
    result = copy.deepcopy(
        await manager.inspect(url, payload.cursor)
        if payload.cursor is not None
        else await manager.inspect(url)
    )
    prune_previews()
    # Bound cached preview tickets; raw URLs never appear in the browser DOM.
    while len(previews) >= 20:
        previews.pop(next(iter(previews)))
    identifier = uuid4().hex
    urls = []
    streams = []

    def proxy_thumbnail(item):
        thumbnail = item.get("thumbnail")
        if isinstance(thumbnail, str) and thumbnail.startswith(("https://", "http://")):
            urls.append(thumbnail)
            item["thumbnail"] = f"/thumbnails/{identifier}/{len(urls) - 1}"
        else:
            item["thumbnail"] = None

    proxy_thumbnail(result)
    for item in result.get("items", []):
        proxy_thumbnail(item)
        descriptor = item.pop("_preview", None)
        if item["type"] == "video" and isinstance(descriptor, dict):
            streams.append(descriptor)
            item["preview_url"] = f"/streams/{identifier}/{len(streams) - 1}"
            item["preview_muted"] = bool(descriptor.get("muted"))
        else:
            item["preview_url"] = None
    result["images"] = [item for item in result.get("items", []) if item["type"] == "image"]
    previews[identifier] = {"urls": urls, "streams": streams, "expires": time.time() + settings.ttl}
    result["limits"] = {
        "max_file_mb": settings.max_bytes // (1024 * 1024),
        "max_duration_seconds": settings.max_duration,
        "max_items": settings.max_items,
        "ttl_seconds": settings.ttl,
    }
    return result


@app.post("/download", status_code=202)
async def download(payload: DownloadRequest):
    url = (await asyncio.to_thread(validate_url, payload.url)).url
    selections = [selection.model_dump(exclude_none=True) for selection in payload.selections]
    if len({selection["id"] for selection in selections}) != len(selections):
        raise MediaError("selection", "กรุณาเลือกรายการสื่อโดยไม่เลือกซ้ำ")
    job = await manager.submit(url, selections, video_format=payload.video_format)
    return {"job_id": job.id, "status_url": f"/jobs/{job.id}"}


@app.get("/jobs/{identifier}")
async def job_status(identifier: str):
    await manager.cleanup()
    job = manager.jobs.get(identifier)
    if job is None:
        return error_response("job_not_found", "ไม่พบงานนี้ งานอาจหมดอายุหรือระบบถูกเริ่มใหม่", 404)
    return job.public()


@app.get("/files/{identifier}")
async def file_download(identifier: str):
    await manager.cleanup()
    job = manager.jobs.get(identifier)
    if job is None:
        return error_response("file_expired", "ไม่พบไฟล์หรือไฟล์หมดอายุแล้ว กรุณาดาวน์โหลดใหม่", 404)
    if job.status != "completed":
        return error_response("file_not_ready", "ไฟล์ยังไม่พร้อมดาวน์โหลด", 409)
    path = job.directory / job.filename
    if not path.is_file() or path.is_symlink():
        return error_response("file_missing", "ไม่พบไฟล์ กรุณาดาวน์โหลดใหม่", 404)
    job.readers += 1

    def release():
        job.readers -= 1

    return ClosingFileResponse(path, filename=job.filename, on_close=release)


@app.get("/thumbnails/{identifier}/{index}")
async def thumbnail(identifier: str, index: int):
    global thumbnail_pending
    prune_previews()
    entry = previews.get(identifier)
    if entry is None or not 0 <= index < len(entry["urls"]):
        return error_response("preview_expired", "ตัวอย่างรูปหมดอายุแล้ว", 404)
    if thumbnail_pending >= settings.max_items:
        return error_response("busy", "ระบบกำลังทำงานเต็มจำนวน", 429)
    directory = settings.root / uuid4().hex
    thumbnail_pending += 1
    try:
        async with asyncio.timeout(60):
            async with manager.slots:
                directory.mkdir()
                result = await run_worker(
                    {"action": "preview", "url": entry["urls"][index], "directory": str(directory)},
                    timeout=30,
                )
        return ClosingFileResponse(
            directory / result["filename"],
            media_type=result["media_type"],
            on_close=lambda: shutil.rmtree(directory, True),
        )
    except TimeoutError:
        await asyncio.to_thread(shutil.rmtree, directory, True)
        raise MediaError("busy", "ระบบกำลังทำงานเต็มจำนวน กรุณาเปิดตัวอย่างอีกครั้ง") from None
    except BaseException:
        await asyncio.to_thread(shutil.rmtree, directory, True)
        raise
    finally:
        thumbnail_pending -= 1


@app.api_route("/streams/{identifier}/{index}", methods=["GET", "HEAD"])
async def stream_preview(identifier: str, index: int, request: Request):
    prune_previews()
    entry = previews.get(identifier)
    if entry is None or not 0 <= index < len(entry.get("streams", [])):
        return error_response("preview_expired", "ตัวอย่างคลิปหมดอายุแล้ว กรุณาตรวจสอบลิงก์ใหม่", 404)
    try:
        lease = await PreviewStream.open(
            entry["streams"][index], request.headers.get("range"), manager.slots
        )
    except MediaError as error:
        status = 416 if error.code == "invalid_range" else 429 if error.code == "busy" else 502
        return error_response(error.code, str(error), status)
    if request.method == "HEAD":
        await lease.close()
        return Response(status_code=lease.header["status"], headers=lease.header["headers"])
    return PreviewResponse(lease)


@app.get("/")
async def home():
    path = ROOT / "frontend" / "index.html"
    if not path.is_file():
        return error_response("frontend_pending", "กำลังเตรียมหน้าเว็บ", 503)
    return FileResponse(path)


@app.get("/assets/{filename}")
async def asset(filename: str):
    if filename not in (
        "app.js",
        "styles.css",
        "i18n.js",
        "cat.svg",
        "pixel-font.ttf",
        "pixel-font-license.txt",
    ):
        return error_response("not_found", "ไม่พบไฟล์นี้", 404)
    return FileResponse(ROOT / "frontend" / filename)
