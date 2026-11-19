#!/usr/bin/env python3
"""Linux integration: real Xray -> local authenticated proxy -> verified HTTPS.

No service installation or production configuration is changed. Every listening
socket is loopback and every upstream tunnel is restricted to the trace target.
"""
import argparse
import base64
import json
from pathlib import Path
import select
import socket
import socketserver
import sys
import threading
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import egress

USER, PASSWORD = "canary-user", "fixture-canary-password"
TARGET = "www.cloudflare.com"


def exact(sock, size):
    result = b""
    while len(result) < size:
        part = sock.recv(size - len(result))
        if not part:
            raise OSError("short frame")
        result += part
    return result


def relay(client, remote):
    try:
        for _ in range(300):
            ready, _, _ = select.select([client, remote], [], [], 10)
            if not ready:
                return
            for source in ready:
                body = source.recv(32768)
                if not body:
                    return
                (remote if source is client else client).sendall(body)
    finally:
        remote.close()


class Proxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, protocol):
        self.protocol, self.tunnels, self.denied = protocol, [], 0
        super().__init__(("127.0.0.1", 0), Handler)


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        sock = self.request
        sock.settimeout(15)
        try:
            if self.server.protocol == "socks5":
                version, count = exact(sock, 2)
                methods = exact(sock, count)
                if version != 5 or 2 not in methods:
                    sock.sendall(b"\x05\xff")
                    return
                sock.sendall(b"\x05\x02")
                version, length = exact(sock, 2)
                user = exact(sock, length)
                password = exact(sock, exact(sock, 1)[0])
                if version != 1 or user != USER.encode() or password != PASSWORD.encode():
                    self.server.denied += 1
                    sock.sendall(b"\x01\x01")
                    return
                sock.sendall(b"\x01\x00")
                version, command, reserved, atyp = exact(sock, 4)
                if version != 5 or command != 1 or atyp != 3:
                    raise OSError("unsupported proxy request")
                host = exact(sock, exact(sock, 1)[0]).decode("ascii")
                port = int.from_bytes(exact(sock, 2), "big")
                if host != TARGET or port != 443:
                    raise OSError("target refused")
                remote = socket.create_connection((host, port), timeout=10)
                sock.sendall(b"\x05\x00\x00\x01" + b"\0" * 6)
            else:
                raw = b""
                while b"\r\n\r\n" not in raw and len(raw) < 16384:
                    raw += exact(sock, 1)
                lines = raw.decode("ascii").split("\r\n")
                expected = "Basic " + base64.b64encode((USER + ":" + PASSWORD).encode()).decode()
                headers = dict(line.split(": ", 1) for line in lines[1:] if ": " in line)
                if headers.get("Proxy-Authorization") != expected:
                    self.server.denied += 1
                    sock.sendall(b"HTTP/1.1 407 Proxy Authentication Required\r\nContent-Length: 0\r\n\r\n")
                    return
                if lines[0] != "CONNECT " + TARGET + ":443 HTTP/1.1":
                    raise OSError("target refused")
                host, port = TARGET, 443
                remote = socket.create_connection((host, port), timeout=10)
                sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            self.server.tunnels.append({"host": host, "port": port})
            relay(sock, remote)
        except (OSError, ValueError, UnicodeError):
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xray", required=True, type=Path)
    args = parser.parse_args()
    if not args.xray.is_file():
        raise SystemExit("xray binary unavailable")
    real_popen = egress.subprocess.Popen
    def substitute(argv, *positional, **options):
        if argv[0] == "/usr/local/bin/xray":
            argv = [str(args.xray), *argv[1:]]
        return real_popen(argv, *positional, **options)
    report = {"suite": "real_xray_authenticated_exit_https", "results": []}
    with patch.object(egress.subprocess, "Popen", substitute):
        for protocol in ("socks5", "http-connect"):
            server = Proxy(protocol)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                profile = {"protocol": protocol, "host": "127.0.0.1", "port": server.server_address[1],
                           "username": USER, "password": PASSWORD}
                actual = egress.run_probe(egress.outbound(profile))
                if actual.get("ok") is not True or not server.tunnels:
                    raise AssertionError("verified tunnel absent")
                before = len(server.tunnels)
                try:
                    egress.run_probe(egress.outbound({**profile, "password": "wrong-fixture-password"}))
                except egress.EgressError as error:
                    if str(error) != "exit_connectivity_failed":
                        raise
                else:
                    raise AssertionError("invalid proxy password fell back to direct")
                if server.denied < 1 or len(server.tunnels) != before:
                    raise AssertionError("invalid credentials reached an upstream tunnel")
                report["results"].append({"protocol": protocol, "https_verified": True, "trace": actual,
                                          "authenticated_tunnels": len(server.tunnels),
                                          "bad_credentials_failed_closed": True})
            finally:
                server.shutdown()
                server.server_close()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
