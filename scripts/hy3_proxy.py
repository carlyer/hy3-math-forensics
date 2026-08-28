#!/usr/bin/env python3
"""Hy3 本地代理：解决浏览器直连 Hy3 端点时的 CORS 限制。
用法：
    HY3_UPSTREAM=https://你的hy3端点/v1 python3 scripts/hy3_proxy.py [端口，默认8787]
然后在工作台「接口配置」里把 Base URL 填为 http://localhost:8787/v1
API Key 仍由浏览器端发送，代理只做转发并附加 CORS 头，不记录任何内容。
"""
import os
import sys
import json
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

UPSTREAM = os.environ.get("HY3_UPSTREAM", "").rstrip("/")
# 兼容用户写 http://.../v1 的情况：代理暴露的 path 已包含 /v1，避免重复
if UPSTREAM.endswith("/v1"):
    UPSTREAM = UPSTREAM[:-3]
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8787


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if not UPSTREAM:
            self.send_response(500)
            self._cors()
            self.end_headers()
            self.wfile.write(b'{"error": "HY3_UPSTREAM not set"}')
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        req = urllib.request.Request(
            UPSTREAM + self.path,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": self.headers.get("Authorization", ""),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                payload = resp.read()
                self.send_response(resp.status)
        except urllib.error.HTTPError as e:
            payload = e.read()
            self.send_response(e.code)
        except Exception as e:  # noqa: BLE001
            payload = json.dumps({"error": str(e)}).encode()
            self.send_response(502)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # 静音默认日志
        pass


if __name__ == "__main__":
    print(f"Hy3 proxy listening on http://localhost:{PORT} -> {UPSTREAM or '(未设置 HY3_UPSTREAM!)'}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
