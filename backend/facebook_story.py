"""Select exact Facebook Story cards or one requested bucket for yt-dlp."""

import json
import re


def find_cards(page, identifier, *, bucket=False):
    """Resolve exact card IDs, or only cards belonging to the requested bucket."""
    if len(page.encode("utf-8")) > 8 * 1024 * 1024:
        raise ValueError("metadata_limit")
    nodes = []
    for raw in re.findall(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', page, re.S):
        try:
            stack = [json.loads(raw)]
        except (ValueError, RecursionError):
            continue
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                nodes.append(node)
                stack.extend(reversed(list(node.values())))
            elif isinstance(node, list):
                stack.extend(reversed(node))
    wanted = dict.fromkeys([identifier] if not bucket else [])
    if bucket:
        for node in nodes:
            if node.get("id") != identifier:
                continue
            for key in ("unified_stories", "unified_stories_with_notes"):
                connection = node.get(key)
                if not isinstance(connection, dict):
                    continue
                for edge in connection.get("edges", []):
                    card = edge.get("node") if isinstance(edge, dict) else None
                    if isinstance(card, dict) and isinstance(card.get("id"), str):
                        wanted.setdefault(card["id"], None)
    best = {}
    for node in nodes:
        card_id = node.get("id")
        if (
            not isinstance(card_id, str)
            or card_id not in wanted
            or not isinstance(node.get("attachments"), list)
        ):
            continue
        media = media_items(node)
        score = len(json.dumps(media)) if media else -1
        if card_id not in best or score > best[card_id][0]:
            best[card_id] = (score, node)
    return [best[key][1] for key in wanted if key in best and best[key][0] >= 0]


def find_card(page, identifier):
    cards = find_cards(page, identifier)
    return cards[0] if cards else None


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
