"""System metric collection (psutil). Collects resource counters only: no files,
process arguments, user names or environment are read or transmitted."""
from __future__ import annotations

import os
import platform
import socket
import time
from datetime import datetime, timezone

import psutil


class SystemCollector:
    def __init__(self, disk_path: str = "/"):
        self.disk_path = disk_path
        self._last_net: tuple[float, int, int] | None = None
        psutil.cpu_percent(None)  # prime the counter so the first reading is meaningful

    def _net_rates(self) -> tuple[float | None, float | None]:
        c = psutil.net_io_counters()
        now = time.monotonic()
        prev, self._last_net = self._last_net, (now, c.bytes_sent, c.bytes_recv)
        if prev is None or now <= prev[0]:
            return None, None
        dt = now - prev[0]
        # counters can reset (interface restart) -> clamp to 0 rather than report negatives
        return max(0.0, (c.bytes_sent - prev[1]) / dt), max(0.0, (c.bytes_recv - prev[2]) / dt)

    def collect(self) -> dict:
        vm = psutil.virtual_memory()
        try:
            du = psutil.disk_usage(self.disk_path)
            disk = {"disk_percent": round(du.percent, 2), "disk_free_bytes": du.free, "disk_total_bytes": du.total}
        except OSError:
            disk = {"disk_percent": None, "disk_free_bytes": None, "disk_total_bytes": None}
        sent, recv = self._net_rates()
        load = (None, None, None)
        if hasattr(os, "getloadavg"):  # unavailable on Windows
            try:
                load = os.getloadavg()
            except OSError:
                pass
        return {
            "cpu_percent": round(psutil.cpu_percent(None), 2),
            "mem_percent": round(vm.percent, 2),
            "mem_available_bytes": vm.available,
            "mem_total_bytes": vm.total,
            **disk,
            "net_sent_bps": round(sent, 1) if sent is not None else None,
            "net_recv_bps": round(recv, 1) if recv is not None else None,
            "uptime_seconds": int(time.time() - psutil.boot_time()),
            "load1": round(load[0], 2) if load[0] is not None else None,
            "load5": round(load[1], 2) if load[1] is not None else None,
            "load15": round(load[2], 2) if load[2] is not None else None,
        }


def system_info() -> dict:
    return {
        "hostname": socket.gethostname()[:255],
        "os": platform.system() or "unknown",
        "os_version": (platform.mac_ver()[0] if platform.system() == "Darwin" else platform.release())[:255],
        "arch": platform.machine()[:32],
    }


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
