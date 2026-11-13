"""Service health checks: HTTP endpoint, TCP port, process presence."""
from __future__ import annotations

import socket
import time

import httpx
import psutil

from .config import CheckConfig


def run_check(c: CheckConfig) -> dict:
    base = {"name": c.name, "kind": c.kind, "target": c.target[:512]}
    start = time.perf_counter()
    try:
        if c.kind == "http":
            with httpx.Client(timeout=c.timeout, verify=c.verify_tls, follow_redirects=False) as client:
                r = client.get(c.target)
            ms = (time.perf_counter() - start) * 1000
            ok = r.status_code == c.expected_status if c.expected_status else r.status_code < 400
            return base | {"ok": ok, "response_ms": round(ms, 1), "status_code": r.status_code,
                           "error": "" if ok else f"HTTP {r.status_code}"}
        if c.kind == "tcp":
            host, _, port = c.target.rpartition(":")
            with socket.create_connection((host, int(port)), timeout=c.timeout):
                pass
            return base | {"ok": True, "response_ms": round((time.perf_counter() - start) * 1000, 1)}
        if c.kind == "process":
            # Only process *names* are compared; command lines/users are never read.
            found = any((p.info["name"] or "").lower() == c.target.lower()
                        for p in psutil.process_iter(["name"]))
            return base | {"ok": found, "error": "" if found else "process not running"}
    except httpx.TimeoutException:
        return base | {"ok": False, "error": "timeout"}
    except (httpx.HTTPError, OSError) as exc:
        return base | {"ok": False, "error": f"{type(exc).__name__}"[:255]}
    return base | {"ok": False, "error": "unsupported check kind"}
