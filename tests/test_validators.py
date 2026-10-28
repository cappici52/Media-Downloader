import socket
import unittest
from unittest.mock import patch

from backend.validators import (
    ALLOWED_DOMAINS,
    MAX_URL_LENGTH,
    URLValidationError,
    validate_network_url,
    validate_redirect,
    validate_url,
)


def dns_records(*addresses):
    return [
        (
            socket.AF_INET6 if ":" in address else socket.AF_INET,
            socket.SOCK_STREAM,
            6,
            "",
            (address, 443),
        )
        for address in addresses
    ]


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.resolver = patch(
            "backend.validators.socket.getaddrinfo",
            return_value=dns_records("8.8.8.8", "2606:4700:4700::1111"),
        ).start()
        self.addCleanup(patch.stopall)

    def assert_rejected(self, url, code=None, validator=validate_url):
        with self.assertRaises(URLValidationError) as context:
            validator(url)
        if code:
            self.assertEqual(context.exception.code, code)
        self.assertTrue(any("\u0e00" <= c <= "\u0e7f" for c in str(context.exception)))

    def test_all_platforms_and_subdomains(self):
        for domain in ALLOWED_DOMAINS:
            for prefix in ("", "www.", "m.", "a.b."):
                with self.subTest(domain=prefix + domain):
                    result = validate_url(f"https://{prefix}{domain}/post?id=1")
                    self.assertEqual(result.hostname, prefix + domain)
                    self.assertEqual(result.port, 443)

    def test_normalization_preserves_query_and_removes_fragment(self):
        result = validate_url("HTTPS://WWW.YOUTUBE.COM:443/watch?v=abc%20def#section")
        self.assertEqual(result.url, "https://www.youtube.com/watch?v=abc%20def")
        self.assertEqual(result.addresses, ("8.8.8.8", "2606:4700:4700::1111"))

    def test_http_and_default_path(self):
        result = validate_url("http://youtu.be:80")
        self.assertEqual(result.url, "http://youtu.be/")
        self.resolver.assert_called_once_with("youtu.be", 80, type=socket.SOCK_STREAM)

    def test_lookalikes_rejected_before_dns(self):
        for host in (
            "evilyoutube.com",
            "youtube.com.evil.test",
            "notx.com",
            "eviltiktok.com",
            "tiktok.com.evil.test",
            "example.com",
            "localhost",
        ):
            with self.subTest(host=host):
                self.assert_rejected("https://" + host, "unsupported_domain")
        self.resolver.assert_not_called()

    def test_malformed_and_ambiguous_inputs(self):
        for url in (
            None,
            12,
            "",
            " ",
            "x" * (MAX_URL_LENGTH + 1),
            "https://",
            "https:///youtube.com",
            "//youtube.com",
            "youtube.com",
            "https://youtube.com:abc",
            "https://youtube.com:65536",
            "https://youtube.com:",
            "https://[broken",
            "https://youtube.com./",
            "https://%79outube.com/",
            "https://you\u0442ube.com/",
            "https://-a.youtube.com",
            "https://a..youtube.com",
            "https://youtube.com\\@evil.test",
            "https://youtube.com/\nfoo",
            " https://youtube.com",
            "https://youtube.com/a b",
            "https://youtube.com/\x7f",
            "https://youtube.com/\tfoo",
            "https://youtube.com/\u00a0",
        ):
            with self.subTest(url=str(url)[:100]):
                self.assert_rejected(url)
        self.resolver.assert_not_called()

    def test_non_http_schemes(self):
        for scheme in ("file", "ftp", "data", "javascript", "gopher"):
            with self.subTest(scheme=scheme):
                self.assert_rejected(f"{scheme}://youtube.com/test", "invalid_scheme")

    def test_credentials_and_ports(self):
        for url in (
            "https://user:pass@youtube.com",
            "https://@youtube.com",
            "https://youtube.com@127.0.0.1",
            "https://youtube.com:80",
            "http://youtube.com:443",
            "https://youtube.com:8080",
            "https://youtube.com:0",
        ):
            with self.subTest(url=url):
                self.assert_rejected(url)

    def test_ip_literals_rejected_even_for_media(self):
        for host in (
            "127.0.0.1",
            "10.0.0.1",
            "192.168.1.1",
            "8.8.8.8",
            "[::1]",
            "[2606:4700::1111]",
        ):
            with self.subTest(host=host):
                self.assert_rejected("https://" + host, validator=validate_network_url)

    def test_unsafe_dns_including_ipv6_and_mapped_addresses(self):
        for address in (
            "127.0.0.1",
            "10.0.0.1",
            "172.16.0.1",
            "192.168.1.1",
            "169.254.169.254",
            "0.0.0.0",
            "100.64.0.1",
            "192.0.2.1",
            "198.18.0.1",
            "224.0.0.1",
            "255.255.255.255",
            "::",
            "::1",
            "fc00::1",
            "fe80::1",
            "fec0::1",
            "ff02::1",
            "2001:db8::1",
            "::ffff:127.0.0.1",
            "::ffff:10.0.0.1",
            "fe80::1%eth0",
            "2002:7f00:0001::1",
            "not-an-ip",
            "64:ff9b::7f00:1",
            "64:ff9b:1::a00:1",
        ):
            with self.subTest(address=address):
                self.resolver.return_value = dns_records(address)
                self.assert_rejected("https://youtube.com")

    def test_mixed_dns_answers_fail_closed(self):
        self.resolver.return_value = dns_records("8.8.8.8", "::1")
        self.assert_rejected("https://youtube.com", "unsafe_address")

    def test_duplicate_dns_answers(self):
        self.resolver.return_value = dns_records("8.8.8.8", "8.8.8.8")
        self.assertEqual(validate_url("https://youtube.com").addresses, ("8.8.8.8",))

    def test_dns_failure_and_empty_answer(self):
        for error in (socket.gaierror(), TimeoutError()):
            self.resolver.side_effect = error
            self.assert_rejected("https://youtube.com", "dns_failed")
        self.resolver.side_effect = None
        self.resolver.return_value = []
        self.assert_rejected("https://youtube.com", "dns_failed")

    def test_media_cdn_is_separate_from_platform_allowlist(self):
        url = "https://video.cdn.example/video.mp4?signature=abc"
        self.assert_rejected(url, "unsupported_domain")
        self.assertEqual(validate_network_url(url).hostname, "video.cdn.example")
        self.resolver.return_value = dns_records("192.168.0.1")
        self.assert_rejected(url, "unsafe_address", validate_network_url)

    def test_relative_and_cross_platform_redirects(self):
        current = validate_url("https://youtu.be/abc")
        self.assertEqual(validate_redirect(current, "/def", hop=1).url, "https://youtu.be/def")
        self.assertEqual(
            validate_redirect(current, "https://www.youtube.com/watch?v=abc", hop=5).hostname,
            "www.youtube.com",
        )

    def test_redirect_to_unapproved_domain(self):
        current = validate_url("https://youtube.com")
        with self.assertRaises(URLValidationError):
            validate_redirect(current, "https://evil.test", hop=1)

    def test_redirect_rechecks_dns_even_on_same_host(self):
        current = validate_url("https://youtube.com")
        self.resolver.return_value = dns_records("127.0.0.1")
        with self.assertRaises(URLValidationError) as error:
            validate_redirect(current, "/next", hop=1)
        self.assertEqual(error.exception.code, "unsafe_address")

    def test_media_redirect_checks_target(self):
        current = validate_url("https://youtube.com")
        self.assertEqual(
            validate_redirect(current, "//cdn.example/file", hop=1, media=True).hostname,
            "cdn.example",
        )
        self.resolver.return_value = dns_records("169.254.169.254")
        with self.assertRaises(URLValidationError):
            validate_redirect(current, "https://cdn.example/file", hop=2, media=True)

    def test_invalid_redirect_locations_and_hops(self):
        current = validate_url("https://youtube.com")
        for location in (
            None,
            "",
            "\nhttps://youtube.com",
            "\\evil.test",
            "x" * (MAX_URL_LENGTH + 1),
            "file:///etc/passwd",
        ):
            with self.subTest(location=str(location)[:80]), self.assertRaises(URLValidationError):
                validate_redirect(current, location, hop=1)
        for hop in (0, -1, 6, True, 1.5, "1"):
            with self.subTest(hop=hop), self.assertRaises(URLValidationError):
                validate_redirect(current, "/next", hop=hop)


if __name__ == "__main__":
    unittest.main()
