"""Defense for Python extractor sockets, installed only in isolated workers.

DNS answers are checked in full, and the numeric address passed to connect is
checked again. Redirects therefore cannot reach private networks, even after DNS
rebinding. No process-wide monkeypatch is ever installed in the web server.
External downloader processes are forbidden; ffmpeg gets local files only.
"""

import os
import socket
import urllib.request
from .validators import MAX_REDIRECTS, URLValidationError, _public_address, validate_network_url


def install_network_guard():
    original_dns = socket.getaddrinfo
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_open = urllib.request.OpenerDirector.open

    def open_url(opener, fullurl, *args, **kwargs):
        target = fullurl.full_url if isinstance(fullurl, urllib.request.Request) else fullurl
        validate_network_url(target)
        return original_open(opener, fullurl, *args, **kwargs)

    def dns(host, port, *args, **kwargs):
        records = original_dns(host, port, *args, **kwargs)
        for record in records:
            _public_address(record[4][0])
        return records

    def check(sock, address):
        if sock.family not in (socket.AF_INET, socket.AF_INET6):
            raise URLValidationError("unsafe_address", "ไม่อนุญาตการเชื่อมต่อเครือข่ายภายใน")
        # Require numeric addresses here, so connect cannot perform a second DNS lookup.
        _public_address(address[0])
        if address[1] not in (80, 443):
            raise URLValidationError("invalid_port", "ไม่อนุญาตพอร์ตปลายทางนี้")

    def connect(sock, address):
        check(sock, address)
        return original_connect(sock, address)

    def connect_ex(sock, address):
        check(sock, address)
        return original_connect_ex(sock, address)

    def deny_datagram(*args, **kwargs):
        raise URLValidationError("unsafe_address", "ไม่อนุญาตการเชื่อมต่อชนิดนี้")

    socket.getaddrinfo = dns
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.socket.sendto = deny_datagram
    urllib.request.OpenerDirector.open = open_url
    urllib.request.HTTPRedirectHandler.max_redirections = MAX_REDIRECTS
    import requests.sessions

    requests.sessions.DEFAULT_REDIRECT_LIMIT = MAX_REDIRECTS
    socket.setdefaulttimeout(20)
    for name in list(os.environ):
        if name.lower().endswith("_proxy"):
            os.environ.pop(name, None)
