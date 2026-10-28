"""Browser-only credentials kept in RAM and passed to workers over stdin.

No cookie upload, cookie file, environment credential or browser-facing value.
Only cookies belonging to supported platform domains are retained.
"""

import asyncio
import copy
from http.cookiejar import Cookie, CookieJar
import time
from urllib.parse import urlsplit

from .settings import settings

GROUPS = (
    ("youtube.com", "youtu.be"),
    ("facebook.com", "fb.watch"),
    ("instagram.com",),
    ("x.com", "twitter.com"),
    ("tiktok.com",),
)
_worker_rows = None


def matches(host, domain):
    return host == domain or host.endswith("." + domain)


def install_worker_session(rows):
    global _worker_rows
    _worker_rows = rows


def has_worker_session():
    return _worker_rows is not None


def worker_cookie_jar():
    jar = CookieJar()
    for row in _worker_rows or []:
        if row["expires"] is None or row["expires"] > time.time():
            jar.set_cookie(Cookie(**row))
    return jar


class BrowserSession:
    def __init__(self, browser, ttl=21600, loader=None):
        self.browser, self.ttl, self.loader = browser, ttl, loader or self.load_browser
        self._rows = None
        self.loaded_at = None
        self.error = None
        self._expired = False
        self.lock = asyncio.Lock()

    @staticmethod
    def load_browser(browser):
        from yt_dlp.cookies import extract_cookies_from_browser
        from .downloader import QuietLogger

        return extract_cookies_from_browser(browser, logger=QuietLogger())

    def clear(self):
        self._rows = None
        self.loaded_at = None
        self._expired = False
        self.error = None

    def status(self):
        expired = self.loaded_at is not None and time.time() >= self.loaded_at + self.ttl
        if expired:
            self.clear()
            self._expired = True
        return {
            "browser": self.browser or None,
            "status": "disabled"
            if not self.browser
            else "ready"
            if self._rows is not None
            else "expired"
            if self._expired
            else "not_loaded",
            "loaded_at": self.loaded_at,
            "expires_at": self.loaded_at + self.ttl if self.loaded_at is not None else None,
            "error": self.error,
        }

    async def refresh(self):
        if not self.browser:
            return self.status()
        from .downloader import friendly_error

        async with self.lock:
            try:
                jar = await asyncio.to_thread(self.loader, self.browser)
                rows = []
                for cookie in jar:
                    host = cookie.domain.lstrip(".").lower()
                    if cookie.is_expired() or not any(
                        matches(host, domain) for group in GROUPS for domain in group
                    ):
                        continue
                    rows.append(
                        {
                            key: getattr(cookie, key)
                            for key in (
                                "version",
                                "name",
                                "value",
                                "port",
                                "port_specified",
                                "domain",
                                "domain_specified",
                                "domain_initial_dot",
                                "path",
                                "path_specified",
                                "secure",
                                "expires",
                                "discard",
                                "comment",
                                "comment_url",
                            )
                        }
                        | {"rest": dict(cookie._rest), "rfc2109": cookie.rfc2109}
                    )
                self._rows = rows
                self.loaded_at = time.time()
                self.error = None
                self._expired = False
            except Exception as error:
                self.error = friendly_error(error)
            return self.status()

    def for_url(self, url):
        if self.status()["status"] != "ready":
            return None
        host = (urlsplit(url).hostname or "").lower()
        domains = next(
            (group for group in GROUPS if any(matches(host, domain) for domain in group)), ()
        )
        return copy.deepcopy(
            [
                row
                for row in self._rows
                if any(matches(row["domain"].lstrip(".").lower(), domain) for domain in domains)
                and (row["expires"] is None or row["expires"] > time.time())
            ]
        )


browser_session = BrowserSession(settings.browser, settings.browser_session_ttl)
