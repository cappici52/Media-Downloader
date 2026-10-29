"""Bounded original-byte cache for small progressive video startup."""

from collections import OrderedDict
import re
import time

from .downloader import MediaError
from .stream_worker import bounded_range


class VideoStartupCache:
    def __init__(self, max_bytes=32 * 1024 * 1024, ttl=300):
        self.max_bytes, self.ttl = max_bytes, ttl
        self.entries = OrderedDict()
        self.size = 0

    def _remove(self, key):
        self.size -= len(self.entries.pop(key)[1])

    def get(self, key):
        now = time.monotonic()
        for expired, (deadline, _) in list(self.entries.items()):
            if deadline <= now:
                self._remove(expired)
        if key not in self.entries:
            return None
        self.entries.move_to_end(key)
        return self.entries[key][1]

    def put(self, key, data):
        if len(data) > self.max_bytes:
            return
        self.get(key)  # Prune expired entries before admitting new data.
        if key in self.entries:
            self._remove(key)
        while self.entries and self.size + len(data) > self.max_bytes:
            self._remove(next(iter(self.entries)))
        self.entries[key] = (time.monotonic() + self.ttl, data)
        self.size += len(data)

    def clear(self):
        self.entries.clear()
        self.size = 0


class MemoryPreview:
    def __init__(self, data, range_header, media_type):
        left, right = bounded_range(range_header).removeprefix("bytes=").split("-")
        total = len(data)
        start = int(left) if left else max(0, total - int(right))
        end = min(int(right), total - 1) if left else total - 1
        if start >= total:
            raise MediaError("invalid_range", "ช่วงข้อมูลวิดีโอไม่ถูกต้อง")
        self.data = data[start : end + 1]
        self.header = {
            "status": 206,
            "headers": {
                "Content-Type": media_type,
                "Content-Length": str(len(self.data)),
                "Content-Range": f"bytes {start}-{end}/{total}",
                "Accept-Ranges": "bytes",
            },
        }

    async def chunks(self):
        yield self.data

    async def close(self):
        pass


def complete_small_mp4(header, range_header):
    fields = header["headers"]
    match = re.fullmatch(r"bytes 0-([0-9]+)/([0-9]+)", fields.get("Content-Range", ""))
    return (
        range_header == "bytes=0-"
        and fields.get("Content-Type") == "video/mp4"
        and match is not None
        and int(match[1]) + 1 == int(match[2]) == int(fields["Content-Length"])
        and 0 < int(match[2]) <= 8 * 1024 * 1024
    )
