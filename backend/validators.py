"""URL policy shared by metadata, download and redirect handling.

validate_url is for user input and platform redirects. validate_network_url is
for extractor-produced CDN URLs, never for accepting arbitrary user input.
Neither function fetches URLs. A transport MUST connect to one of the returned
addresses (preserving Host and TLS hostname checks), revalidate every redirect,
and disable implicit redirects/proxies. Resolving then letting a client resolve
again is vulnerable to DNS rebinding. These helpers alone are not a network
sandbox; every downloader and ffmpeg request needs the same transport policy.
"""

from dataclasses import dataclass
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit


ALLOWED_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "facebook.com",
    "fb.watch",
    "instagram.com",
    "x.com",
    "twitter.com",
)
MAX_URL_LENGTH = 8192
MAX_REDIRECTS = 5
_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


class URLValidationError(ValueError):
    """Safe Thai error text and stable machine-readable code."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ValidatedURL:
    url: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


def _public_address(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise URLValidationError("invalid_dns", "ข้อมูลที่อยู่ปลายทางไม่ถูกต้อง") from None
    mapped = getattr(address, "ipv4_mapped", None)
    checked = mapped or address
    if (
        not checked.is_global
        or checked.is_multicast
        or checked.is_reserved
        or getattr(checked, "is_site_local", False)
        or getattr(address, "scope_id", None)
        or getattr(address, "sixtofour", None)
        or getattr(address, "teredo", None)
        or (
            address.version == 6
            and any(
                address in network
                for network in (
                    ipaddress.ip_network("64:ff9b::/96"),
                    ipaddress.ip_network("64:ff9b:1::/48"),
                )
            )
        )
    ):
        raise URLValidationError("unsafe_address", "ไม่อนุญาตลิงก์ที่ชี้ไปยังเครือข่ายภายในหรือที่อยู่พิเศษ")
    return str(address)


def _validate(url: str, *, platform_only: bool) -> ValidatedURL:
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        raise URLValidationError("invalid_url", "กรุณาระบุลิงก์ที่ถูกต้องและไม่ยาวเกินไป")
    # Reject ambiguous input before urllib silently strips control characters.
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url) or "\\" in url:
        raise URLValidationError("invalid_url", "ลิงก์มีช่องว่างหรืออักขระที่ไม่อนุญาต")
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        port = parts.port
    except ValueError:
        raise URLValidationError("invalid_url", "รูปแบบลิงก์หรือพอร์ตไม่ถูกต้อง") from None
    if parts.scheme.lower() not in ("http", "https"):
        raise URLValidationError("invalid_scheme", "รองรับเฉพาะลิงก์ http และ https เท่านั้น")
    if not hostname or not parts.netloc:
        raise URLValidationError("invalid_url", "ลิงก์ต้องมีชื่อเว็บไซต์ที่ถูกต้อง")
    if parts.username is not None or parts.password is not None:
        raise URLValidationError("credentials_not_allowed", "ไม่อนุญาตลิงก์ที่ฝังชื่อผู้ใช้หรือรหัสผ่าน")
    hostname = hostname.lower()
    # ASCII DNS names only; percent-encoded hosts and trailing dots are rejected.
    if len(hostname) > 253 or any(
        not _HOST_LABEL.fullmatch(label) for label in hostname.split(".")
    ):
        raise URLValidationError("invalid_host", "ชื่อเว็บไซต์ในลิงก์ไม่ถูกต้อง")
    expected_port = 443 if parts.scheme.lower() == "https" else 80
    if port is not None and port != expected_port:
        raise URLValidationError("invalid_port", "รองรับเฉพาะพอร์ตมาตรฐานของ http และ https")
    if parts.netloc.endswith(":"):
        raise URLValidationError("invalid_port", "รูปแบบพอร์ตไม่ถูกต้อง")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise URLValidationError("ip_not_allowed", "กรุณาใช้ลิงก์ชื่อเว็บไซต์แทนหมายเลข IP")
    if platform_only and not any(
        hostname == domain or hostname.endswith("." + domain) for domain in ALLOWED_DOMAINS
    ):
        raise URLValidationError(
            "unsupported_domain", "รองรับเฉพาะลิงก์ YouTube, Facebook, Instagram และ X เท่านั้น"
        )
    try:
        records = socket.getaddrinfo(hostname, port or expected_port, type=socket.SOCK_STREAM)
    except OSError:
        raise URLValidationError("dns_failed", "ติดต่อเว็บไซต์ไม่ได้ กรุณาตรวจสอบลิงก์หรือลองใหม่") from None
    if not records:
        raise URLValidationError("dns_failed", "ไม่พบที่อยู่ของเว็บไซต์นี้")
    # Reject the entire answer if even one record is unsafe, including mixed A/AAAA.
    addresses = tuple(dict.fromkeys(_public_address(record[4][0]) for record in records))
    normalized = urlunsplit((parts.scheme.lower(), hostname, parts.path or "/", parts.query, ""))
    return ValidatedURL(normalized, hostname, expected_port, addresses)


def validate_url(url: str) -> ValidatedURL:
    """Validate user input against the platform allowlist and all DNS answers."""
    return _validate(url, platform_only=True)


def validate_network_url(url: str) -> ValidatedURL:
    """Validate an extractor-generated URL, allowing public CDN hostnames."""
    return _validate(url, platform_only=False)


def validate_redirect(
    current: ValidatedURL, location: str, *, hop: int, media: bool = False
) -> ValidatedURL:
    """Validate a Location before following it; hop is one-based.

    Use media=True only for extractor/CDN requests, never user platform navigation.
    The caller must enforce the hop counter across the complete redirect chain.
    """
    if not isinstance(hop, int) or isinstance(hop, bool) or not 1 <= hop <= MAX_REDIRECTS:
        raise URLValidationError("too_many_redirects", "เว็บไซต์เปลี่ยนเส้นทางหลายครั้งเกินไป")
    if not isinstance(location, str) or not location or len(location) > MAX_URL_LENGTH:
        raise URLValidationError("invalid_redirect", "เว็บไซต์ส่งเส้นทางใหม่ที่ไม่ถูกต้อง")
    if (
        any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in location)
        or "\\" in location
    ):
        raise URLValidationError("invalid_redirect", "เว็บไซต์ส่งเส้นทางใหม่ที่ไม่ถูกต้อง")
    target = urljoin(current.url, location)
    return validate_network_url(target) if media else validate_url(target)
