"""Agent main loop: collect -> buffer -> flush, with backoff and graceful shutdown."""
from __future__ import annotations

import json
import logging
import os
import random
import signal
import threading
import time
from pathlib import Path

from . import __version__
from .buffer import SampleBuffer
from .checks import run_check
from .client import AuthError, RejectedBatch, ServerClient, TransientError
from .collector import SystemCollector, now_utc, system_info
from .config import AgentConfig

log = logging.getLogger("infrawatch.agent")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        d = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname,
             "logger": record.name, "msg": record.getMessage()}
        d.update(getattr(record, "ctx", {}))
        if record.exc_info:
            d["exc"] = self.formatException(record.exc_info)
        return json.dumps(d)


def setup_logging(level: str) -> None:
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    logging.basicConfig(level=level.upper(), handlers=[h], force=True)


def load_api_key(cfg: AgentConfig) -> str | None:
    if cfg.api_key:
        return cfg.api_key
    if cfg.key_file.is_file():
        return cfg.key_file.read_text().strip() or None
    return None


def save_api_key(cfg: AgentConfig, key: str) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(cfg.key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key)


def register(cfg: AgentConfig, client: ServerClient) -> str:
    if not cfg.enrollment_token:
        raise RuntimeError("no API key and no enrollment token: cannot register")
    d = client.register(cfg.enrollment_token, system_info())
    save_api_key(cfg, d["api_key"])
    log.info("registered with server", extra={"ctx": {"host_id": d["host_id"], "environment": d["environment"]}})
    return d["api_key"]


class Agent:
    def __init__(self, cfg: AgentConfig, client: ServerClient | None = None, sleep=None):
        self.cfg = cfg
        self.client = client or ServerClient(cfg)
        self.buffer = SampleBuffer(cfg.state_dir / "buffer.db", cfg.buffer_max_samples)
        self.collector = SystemCollector(cfg.disk_path)
        self.stop_event = threading.Event()
        self._wait = sleep or self.stop_event.wait
        self.info = system_info()
        self.api_key: str | None = None
        self.consecutive_failures = 0
        self.last_success: float | None = None
        self.sent_total = 0

    # -- health -------------------------------------------------------------
    def health(self) -> dict:
        return {
            "agent_version": __version__, "pid": os.getpid(), "buffered_samples": len(self.buffer),
            "dropped_samples": self.buffer.dropped, "consecutive_failures": self.consecutive_failures,
            "last_success_unix": self.last_success, "sent_total": self.sent_total, "registered": bool(self.api_key),
            "updated_unix": time.time(),
        }

    def write_health(self) -> None:
        p = self.cfg.state_dir / "health.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.health()))
        os.replace(tmp, p)

    # -- steps --------------------------------------------------------------
    def collect_once(self) -> dict:
        sample = {"ts": now_utc().isoformat(), "system": self.collector.collect(),
                  "checks": [run_check(c) for c in self.cfg.checks]}
        self.buffer.add(sample)
        return sample

    def flush(self) -> bool:
        """Send buffered samples in batches. Returns True if the buffer was fully drained."""
        while len(self.buffer) and not self.stop_event.is_set():
            batch = self.buffer.peek(self.cfg.batch_size)
            ids = [i for i, _ in batch]
            try:
                resp = self.client.send(self.api_key, self.info, [s for _, s in batch], self.cfg.interval)
            except TransientError as exc:
                self.consecutive_failures += 1
                log.warning("send failed, will retry", extra={"ctx": {"error": str(exc), "buffered": len(self.buffer),
                                                                      "failures": self.consecutive_failures}})
                return False
            except RejectedBatch as exc:
                # A permanently invalid batch must not block the queue forever.
                log.error("server rejected batch; dropping it", extra={"ctx": {"error": str(exc), "size": len(ids)}})
                self.buffer.delete(ids)
                continue
            self.buffer.delete(ids)
            self.sent_total += resp.get("accepted", 0)
            self.consecutive_failures = 0
            self.last_success = time.time()
            if resp.get("upgrade_available"):
                log.info("newer agent version available", extra={"ctx": {"latest": resp.get("latest_agent_version")}})
        return True

    def backoff_delay(self) -> float:
        n = min(self.consecutive_failures, 10)
        base = min(self.cfg.backoff_max, self.cfg.interval * (2 ** n))
        return base * random.uniform(0.5, 1.0)  # jitter avoids thundering herds after an outage

    # -- main loop ----------------------------------------------------------
    def run(self, max_iterations: int | None = None) -> None:
        log.info("agent starting", extra={"ctx": {"version": __version__, "interval": self.cfg.interval,
                                                  "server": self.cfg.server_url, "checks": len(self.cfg.checks)}})
        self.api_key = load_api_key(self.cfg)
        i = 0
        while not self.stop_event.is_set() and (max_iterations is None or i < max_iterations):
            i += 1
            started = time.monotonic()
            if not self.api_key:
                try:
                    self.api_key = register(self.cfg, self.client)
                except (TransientError, AuthError, RejectedBatch) as exc:
                    self.consecutive_failures += 1
                    log.error("registration failed", extra={"ctx": {"error": str(exc)}})
            self.collect_once()  # always collect: data is buffered even while offline
            if self.api_key:
                try:
                    self.flush()
                except AuthError as exc:
                    self.consecutive_failures += 1
                    log.error("server rejected credentials (key revoked?)", extra={"ctx": {"error": str(exc)}})
            try:
                self.write_health()
            except OSError:
                log.exception("could not write health file")
            elapsed = time.monotonic() - started
            delay = max(0.0, self.cfg.interval - elapsed)
            if self.consecutive_failures:
                delay = max(delay, self.backoff_delay())
            if self._wait(delay):
                break
        self.shutdown()

    def shutdown(self) -> None:
        log.info("agent shutting down", extra={"ctx": {"buffered": len(self.buffer)}})
        # Best-effort final flush, bounded so shutdown cannot hang.
        self.stop_event.clear()
        if self.api_key and len(self.buffer):
            try:
                self.flush()
            except Exception:
                pass
        try:
            self.write_health()
        except OSError:
            pass
        self.buffer.close()
        self.client.close()

    def install_signal_handlers(self) -> None:
        def handler(signum, _frame):
            log.info("signal received", extra={"ctx": {"signal": signum}})
            self.stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, handler)
