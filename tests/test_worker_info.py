import io
import json
import unittest
from unittest.mock import patch
from backend import worker


class InfoWorkerTests(unittest.TestCase):
    def test_only_instagram_posts_prefer_an_existing_authenticated_session(self):
        for url, preferred in (
            ("https://www.instagram.com/p/Fixture/", True),
            ("https://www.instagram.com/reel/Fixture/", True),
            ("https://www.instagram.com/fixture/", False),
            ("https://x.com/fixture/status/123", False),
        ):
            with (
                patch.object(
                    worker.sys, "stdin", io.StringIO(json.dumps({"action": "info", "url": url}))
                ),
                patch.object(worker, "install_network_guard"),
                patch.object(worker, "disable_external_downloaders"),
                patch.object(worker, "emit"),
                patch.object(worker, "inspect_media", return_value=({}, [], [])) as inspect,
            ):
                worker.main()
            inspect.assert_called_once_with(url, None, use_session_first=preferred)
