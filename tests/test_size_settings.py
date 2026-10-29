import os
import tempfile
from pathlib import Path
import unittest
from dataclasses import replace
from unittest.mock import patch
from backend import downloader
from backend.settings import nonnegative
from backend.stream_worker import bounded_range


class SizeSettingTests(unittest.TestCase):
    def test_zero_disables_caps_and_negative_values_are_rejected(self):
        for name in ("MAX_FILE_MB", "MAX_STORAGE_MB"):
            with patch.dict(os.environ, {name: "0"}):
                self.assertEqual(nonnegative(name), 0)
            with patch.dict(os.environ, {name: "123"}):
                self.assertEqual(nonnegative(name), 123)
            with patch.dict(os.environ, {name: "-1"}), self.assertRaises(ValueError):
                nonnegative(name)

    def test_unlimited_files_do_not_get_a_zero_byte_ytdlp_cap_or_break_streaming(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(downloader, "settings", replace(downloader.settings, max_bytes=0)),
        ):
            (Path(temp) / "file").write_bytes(b"not empty")
            downloader.check_size(Path(temp))
            self.assertIsNone(downloader.ydl_options(use_cookies=False)["max_filesize"])
            self.assertEqual(bounded_range("bytes=0-1023"), "bytes=0-1023")
