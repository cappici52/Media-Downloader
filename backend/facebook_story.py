"""Select a Facebook Story by its exact ID before passing video data to yt-dlp."""

import json
import re


def find_card(page, identifier):
    if len(page.encode("utf-8")) > 8 * 1024 * 1024:
        raise ValueError("metadata_limit")
    best, score = None, -1
    for raw in re.findall(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', page, re.S):
        try:
            stack = [json.loads(raw)]
        except (ValueError, RecursionError):
            continue
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("id") == identifier and isinstance(node.get("attachments"), list):
                    media = media_items(node)
                    detail = len(json.dumps(media)) if media else -1
                    if detail > score:
                        best, score = node, detail
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(reversed(node))
    return best


def media_items(card):
    return [
        attachment["media"]
        for attachment in card.get("attachments", [])
        if isinstance(attachment, dict) and isinstance(attachment.get("media"), dict)
    ]


def protected_media(media):
    if media.get("has_drm") or media.get("is_drm_protected"):
        return True
    info = media.get("drm_info")
    if isinstance(info, str):
        try:
            info = json.loads(info) if info else None
        except ValueError:
            return True
    if not isinstance(info, dict):
        return bool(info)
    # Facebook includes a generic Widevine certificate on unencrypted videos.
    # An actual license or explicit protection flag is evidence of DRM.
    return any(
        value for key, value in info.items() if key not in ("widevine_cert", "fairplay_cert")
    )


def video_page(card):
    videos = [media for media in media_items(card) if media.get("__typename") == "Video"]
    if not videos:
        return None
    # Use yt-dlp's existing Facebook parser for DASH/HLS/progressive formats.
    data = {
        "nodes": [
            {
                "comet_sections": {
                    "content": {
                        "story": {
                            "attachments": [
                                {"styles": {"attachment": {"media": video}}} for video in videos
                            ]
                        }
                    }
                }
            }
        ]
    }
    relay = {
        "require": [
            ["RelayPrefetchedStreamCache", [], [], [{"__bbox": {"result": {"data": data}}}]]
        ]
    }
    return (
        '<script type="application/json" data-sjs>'
        + json.dumps(relay).replace("<", "\\u003c")
        + "</script>"
    )
