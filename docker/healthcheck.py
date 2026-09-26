#!/usr/bin/env python3
"""Docker HEALTHCHECK for the BigTree bot container.

Healthy when either:
  1. the API server answers /api/health, or
  2. the bot.main process is alive (covers API_ENABLED=false).
"""
import os
import sys
import urllib.request

port = os.getenv("API_PORT", "8090")

try:
    urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5)
    sys.exit(0)
except Exception:
    pass

for pid in os.listdir("/proc"):
    if pid.isdigit():
        try:
            cmd = (
                open(f"/proc/{pid}/cmdline", "rb")
                .read()
                .replace(b"\0", b" ")
                .decode()
            )
            if "bot.main" in cmd:
                sys.exit(0)
        except Exception:
            pass

sys.exit(1)
