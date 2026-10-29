# Media Downloader

A personal localhost app for saving videos and images from **YouTube, Facebook, Instagram, X and TikTok**.

- Preview media, select individual items, and save multiple files as ZIP.
- Download the highest available video quality as MKV, MP4 or MOV; optionally save MP3 audio.
- Browse Instagram/TikTok profiles and supported Stories/Highlights.
- Dark pixel-art UI with Thai/English switching.

Use media you own or have permission to save. Platform restrictions still apply; the app does not bypass access controls, paywalls or DRM. Keep it on localhost: it has no user authentication.

## Run with Docker

```sh
cp .env.example .env
docker compose up --build -d
```

Open [localhost:8000](http://localhost:8000). The image includes Python, FFmpeg and Node.js.

```sh
docker compose logs -f app
docker compose down
```

Use the native setup below when you need your own browser session. Docker cannot read the host's Chrome profile.

## Run on Windows

Install Python 3.12+, FFmpeg/ffprobe and Node.js 22+ on PATH, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1 --env-file .env
```

Run one ASGI worker: jobs and sessions live in process memory. On Linux/macOS, use `.venv/bin/python` instead.

### Use your Chrome session

Log in to the platform in Chrome, save your work, close all Chrome windows, then run:

```powershell
.\scripts\start_chrome.ps1
```

If a server is already running without Chrome enabled, stop it first. The launcher prepares a RAM-only session and reopens Chrome. Browser cookie access depends on your OS/browser; it only grants the permissions your account already has. There is no cookie upload feature.

## Usage

1. Paste a supported post, video or profile URL and check it.
2. Open the media picker to preview and select items.
3. Choose MKV, MP4 or MOV, then download and save the finished file.

MKV preserves original codecs. MP4/MOV may require codec conversion, which takes longer and can introduce loss. Preview quality follows source selection; split audio/video may need a temporary MP4 before playback. Browser codec support still matters.

Returning to a profile reuses loaded images and selections. Recently opened posts stay in memory for up to five minutes. Thumbnail requests have a separate two-worker pool and a shared RAM cache (32 MB, 256 entries, up to five minutes); identical requests share one fetch. Small MP4s can use a separate 32 MB RAM cache to avoid repeated startup range trips. Buffering gets at most 750 ms before falling back to streaming; original bytes and quality are preserved.

Files expire after one hour by default. Restarting clears job history and managed temporary folders. Save finished files before they expire, and keep personal files outside `DOWNLOAD_DIR`.

## Configuration

Edit `.env` and restart. See [.env.example](.env.example) for all options.

| Setting | Default | Meaning |
| --- | --- | --- |
| `MAX_FILE_MB` / `MAX_STORAGE_MB` | `0` | No fixed download/storage cap; positive values enable caps. |
| `MAX_DURATION_SECONDS` | `0` | No fixed video duration limit. |
| `MIN_FREE_DISK_MB` | `512` | Stop jobs when free disk space falls below this reserve. |
| `MAX_CONCURRENT_JOBS` | `2` | Concurrent inspection/download workers; thumbnails use a separate pool. |
| `MAX_PREVIEW_FILE_MB` | `8192` | Direct-stream source limit; responses are capped at 8 MB each. |
| `FILE_TTL_SECONDS` | `3600` | Finished-file retention. |

## Updates and tests

Update the extractors in the active Python environment:

```powershell
.\.venv\Scripts\python scripts/update_extractors.py
```

For Docker: `docker compose build --build-arg UPGRADE_EXTRACTORS=1`, then `docker compose up -d`.

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m unittest discover -s tests
node --test tests/test_frontend_api.cjs
```

## API

`POST /info` inspects a URL; `POST /download` queues selections; `GET /jobs/{id}` reports progress; `GET /files/{id}` serves the result. The full schema is at [/openapi.json](http://localhost:8000/openapi.json).

Downloads run in guarded subprocesses with URL/redirect checks against internal networks. Platform changes, expired sessions and rate limits can still cause failures; update the extractors and recheck the link when needed.
