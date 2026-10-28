import socket
import unittest
from unittest.mock import patch
from backend.downloader import MediaError, friendly_error, quality_options, allowed_format


class DownloaderTests(unittest.TestCase):
    def test_quality_options_exclude_drm_and_external_protocols(self):
        def fmt(height, **extra):
            return {"protocol": "https", "url": "https://cdn.example/a", "height": height, "vcodec": "avc", "acodec": "aac", **extra}
        options = quality_options([fmt(360), fmt(720), fmt(720), fmt(1080, has_drm=True), fmt(2160, protocol="m3u8")])
        self.assertEqual([q["id"] for q in options], ["360p", "720p", "mp3"])

    def test_errors_are_thai_and_hide_raw_secrets(self):
        for text, code in (("please login", "login_required"), ("private post", "private"), ("HTTP 429", "platform_blocked"), ("404 not found", "no_media"), ("connection timeout", "network"), ("secret-token", "extract_failed")):
            result = friendly_error(Exception(text))
            self.assertEqual(result["code"], code)
            self.assertNotIn(text, result["message"])
        self.assertEqual(friendly_error(MediaError("limit", "เกินขนาด"))["code"], "limit")

    def test_socket_guard_in_disposable_process(self):
        import subprocess, sys
        code = '''from backend.network import install_network_guard
import socket
install_network_guard()
for host in ("127.0.0.1", "169.254.169.254", "::1", "10.0.0.1"):
    try: socket.create_connection((host, 80), timeout=.1)
    except ValueError: pass
    else: raise AssertionError(host)
try: socket.socket().connect(("youtube.com", 443))
except ValueError: pass
else: raise AssertionError("implicit DNS allowed")
print("ok")'''
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__": unittest.main()
