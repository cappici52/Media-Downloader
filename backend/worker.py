"""One request per disposable process; stdout is a JSON-lines protocol."""

import json
import sys
from pathlib import Path

from .network import install_network_guard
from .browser_session import install_worker_session
from .downloader import (
    download_media,
    download_preview,
    inspect_media,
    friendly_error,
    disable_external_downloaders,
)


def emit(data):
    print(json.dumps(data, ensure_ascii=True), flush=True)


def main():
    request = json.loads(sys.stdin.readline())
    if "_browser_session" in request:
        install_worker_session(request["_browser_session"])
    install_network_guard()
    disable_external_downloaders()
    try:
        if request["action"] == "info":
            result = inspect_media(request["url"], request.get("cursor"))[0]
        elif request["action"] == "download":
            result = {
                "filename": download_media(
                    request["url"],
                    request["selections"],
                    Path(request["directory"]),
                    emit,
                    video_format=request.get("video_format", "mkv"),
                ).name
            }
        elif request["action"] == "preview":
            result = download_preview(request["url"], Path(request["directory"]))
        else:
            raise ValueError("Unknown worker action")
        emit({"event": "result", "data": result})
    except Exception as error:
        emit({"event": "error", **friendly_error(error)})
        sys.exit(1)


if __name__ == "__main__":
    main()
