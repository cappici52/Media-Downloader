"""Bounded, guarded HTTP byte-range proxy. No video file is written to disk.

stdout contains one JSON header line followed by raw video bytes. Only the web
server sends this worker descriptors from inspected media, never a client URL.
"""

import json
import re
import sys

from .downloader import MediaError, friendly_error
from .network import install_network_guard
from .settings import settings
from .validators import validate_network_url

CHUNK_LIMIT = min(8 * 1024 * 1024, settings.max_bytes)


def bounded_range(value):
    if not value:
        return f"bytes=0-{CHUNK_LIMIT - 1}"
    match = re.fullmatch(r"bytes=([0-9]{0,15})-([0-9]{0,15})", value)
    if not match or not any(match.groups()):
        raise MediaError("invalid_range", "ช่วงข้อมูลวิดีโอไม่ถูกต้อง")
    left, right = match.groups()
    if not left:
        if int(right) <= 0:
            raise MediaError("invalid_range", "ช่วงข้อมูลวิดีโอไม่ถูกต้อง")
        return f"bytes=-{min(int(right), CHUNK_LIMIT)}"
    start = int(left)
    end = min(int(right), start + CHUNK_LIMIT - 1) if right else start + CHUNK_LIMIT - 1
    if end < start or start >= settings.max_preview_bytes:
        raise MediaError("invalid_range", "ช่วงข้อมูลวิดีโอไม่ถูกต้อง")
    return f"bytes={start}-{end}"


def stream(request, output, on_headers=None):
    import requests

    descriptor = request["descriptor"]
    validate_network_url(descriptor["url"])
    headers = {
        key: value
        for key, value in descriptor.get("headers", {}).items()
        if key.lower() in ("user-agent", "referer", "origin")
    }
    headers.update({"Range": bounded_range(request.get("range")), "Accept-Encoding": "identity"})
    with requests.Session() as session:
        session.trust_env = False
        # This descriptor comes from inspected media in server RAM, never the
        # client. Preserve CookieJar domain/path/expiry rules across redirects.
        from .tiktok import is_tiktok
        from http.cookiejar import Cookie

        if is_tiktok(descriptor["url"]):
            for row in descriptor.get("cookie_rows", []):
                if is_tiktok("https://" + row["domain"].lstrip(".")):
                    cookie = Cookie(**row)
                    if not cookie.is_expired():
                        session.cookies.set_cookie(cookie)
        with session.get(descriptor["url"], headers=headers, stream=True, timeout=20) as response:
            if response.status_code == 416:
                raise MediaError("invalid_range", "ช่วงข้อมูลวิดีโอไม่ถูกต้อง")
            response.raise_for_status()
            length = int(response.headers.get("Content-Length", -1))
            if not 0 < length <= CHUNK_LIMIT:
                raise MediaError("preview_range", "คลิปนี้ไม่รองรับการสตรีมตัวอย่าง กรุณาดาวน์โหลดเพื่อเปิดดู")
            forwarded = {
                "Content-Length": str(length),
                "Accept-Ranges": "bytes",
                "Content-Type": descriptor["media_type"],
            }
            if response.status_code == 206:
                content_range = response.headers.get("Content-Range", "")
                match = re.fullmatch(r"bytes ([0-9]+)-([0-9]+)/([0-9]+)", content_range)
                if (
                    not match
                    or int(match[2]) - int(match[1]) + 1 != length
                    or not int(match[1]) <= int(match[2]) < int(match[3])
                ):
                    raise MediaError("preview_range", "ข้อมูลช่วงวิดีโอจากต้นทางไม่ถูกต้อง")
                if int(match[3]) > settings.max_preview_bytes:
                    raise MediaError("preview_size_limit", "ไฟล์ต้นทางใหญ่เกินขีดจำกัดพรีวิว")
                forwarded["Content-Range"] = content_range
            elif response.status_code != 200 or headers["Range"].split("=")[1].split("-")[0] != "0":
                raise MediaError("preview_range", "คลิปนี้ไม่รองรับการเลื่อนตำแหน่งตัวอย่าง")
            output.write(
                (json.dumps({"status": response.status_code, "headers": forwarded}) + "\n").encode()
            )
            output.flush()
            if on_headers:
                on_headers()
            sent = 0
            try:
                for chunk in response.iter_content(65536):
                    sent += len(chunk)
                    if sent > length:
                        break
                    output.write(chunk)
                    output.flush()
            except Exception:
                return  # Terminate on upstream failure after headers, never append JSON.


def main():
    request = json.loads(sys.stdin.readline())
    install_network_guard()
    headers_sent = False

    def mark_headers():
        nonlocal headers_sent
        headers_sent = True

    try:
        stream(request, sys.stdout.buffer, mark_headers)
    except (BrokenPipeError, ConnectionResetError):
        pass
    except Exception as error:
        # Errors after headers terminate the stream; never append JSON to video data.
        if not headers_sent and not getattr(sys.stdout, "closed", False):
            print(json.dumps({"error": friendly_error(error)}), flush=True)


if __name__ == "__main__":
    main()
