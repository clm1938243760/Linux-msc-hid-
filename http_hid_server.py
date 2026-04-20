#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import subprocess

PORT = 8000
JSON_PATH = "/tmp/hid_cmd.json"
RUNNER = "/root/hid_runner_abs.py"
BUSY_FLAG = "/tmp/ums_busy"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            obj = {
                "kbd": os.path.exists("/dev/hidg0"),
                "mouse": os.path.exists("/dev/hidg1"),
                "ums_busy": os.path.exists(BUSY_FLAG),
            }
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(obj).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        try:
            if os.path.exists(BUSY_FLAG):
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"USB image is being processed, try again later")
                return

            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"empty body")
                return

            data = self.rfile.read(length)
            obj = json.loads(data.decode("utf-8"))

            with open(JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False)

            result = subprocess.run(
                ["python3", RUNNER, JSON_PATH],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            else:
                self.send_response(500)
                self.end_headers()
                msg = result.stderr if result.stderr else "runner failed"
                self.wfile.write(msg.encode("utf-8", errors="ignore"))

        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8", errors="ignore"))

    def log_message(self, fmt, *args):
        print("%s - - [%s] %s" % (
            self.client_address[0],
            self.log_date_time_string(),
            fmt % args
        ))


if __name__ == "__main__":
    print(f"HTTP HID server running on port {PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()