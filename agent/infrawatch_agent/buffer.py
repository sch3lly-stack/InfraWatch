"""Durable local buffer (SQLite). Survives agent restarts and server outages.
Bounded: when full, the oldest samples are dropped first."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path


class SampleBuffer:
    def __init__(self, path: Path, max_samples: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.max_samples = max_samples
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        self._db.execute("CREATE TABLE IF NOT EXISTS samples (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL)")
        self._db.commit()
        self.dropped = 0

    def add(self, sample: dict) -> None:
        with self._lock:
            self._db.execute("INSERT INTO samples(body) VALUES (?)", (json.dumps(sample),))
            n = self._db.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
            if n > self.max_samples:
                excess = n - self.max_samples
                self._db.execute("DELETE FROM samples WHERE id IN (SELECT id FROM samples ORDER BY id LIMIT ?)", (excess,))
                self.dropped += excess
            self._db.commit()

    def peek(self, limit: int) -> list[tuple[int, dict]]:
        with self._lock:
            rows = self._db.execute("SELECT id, body FROM samples ORDER BY id LIMIT ?", (limit,)).fetchall()
        return [(i, json.loads(b)) for i, b in rows]

    def delete(self, ids: list[int]) -> None:
        if not ids:
            return
        with self._lock:
            self._db.executemany("DELETE FROM samples WHERE id = ?", [(i,) for i in ids])
            self._db.commit()

    def __len__(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM samples").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._db.close()
