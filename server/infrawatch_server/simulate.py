"""Generate SIMULATED hosts and metrics for demos/tests.

Everything created here is flagged Host.is_simulated=True and is hidden from the API
unless ?include_simulated=true is passed. Simulated hosts have an unguessable API key
hash that nobody holds, so no agent can ever report as one.

    python -m infrawatch_server.simulate --hosts 8 --hours 24
    python -m infrawatch_server.simulate --purge
"""
from __future__ import annotations

import argparse
import math
import random
import secrets
from datetime import timedelta

from sqlalchemy import delete, select

from . import models
from .alerts import evaluate
from .config import get_settings
from .db import Database
from .models import utcnow
from .notify import Notifier
from .security import sha256_hex

ENVS = ["production", "staging", "development"]
GROUPS = ["web", "db", "cache", "worker"]
OSES = [("Linux", "Ubuntu 24.04"), ("Linux", "Debian 12"), ("Darwin", "14.5"), ("Windows", "11 23H2")]


def purge(db: Database) -> int:
    with db.session() as s:
        n = s.query(models.Host).filter_by(is_simulated=True).count()
        s.execute(delete(models.Host).where(models.Host.is_simulated.is_(True)))
        s.commit()
    return n


def seed(db: Database, hosts: int = 8, hours: int = 24, interval: int = 60, seed_value: int | None = 42) -> list[int]:
    rng = random.Random(seed_value)
    now = utcnow()
    ids: list[int] = []
    with db.session() as s:
        for i in range(hosts):
            os_, ver = OSES[i % len(OSES)]
            offline = i == hosts - 1 and hosts > 2  # last host stopped reporting 30 min ago
            h = models.Host(
                hostname=f"sim-{GROUPS[i % 4]}-{i + 1:02d}", os=os_, os_version=ver, arch="x86_64",
                agent_version="0.1.0", environment=ENVS[i % 3], group=GROUPS[i % 4],
                api_key_hash=sha256_hex(secrets.token_hex(32)), is_simulated=True,
                registered_at=now - timedelta(hours=hours), collection_interval=interval,
            )
            s.add(h)
            s.flush()
            ids.append(h.id)
            base_cpu, base_mem = rng.uniform(10, 50), rng.uniform(30, 70)
            disk0 = rng.uniform(30, 88 if i == 1 else 70)
            end = now - timedelta(minutes=30) if offline else now
            n = int(hours * 3600 / interval)
            net_phase = rng.uniform(0, 6)
            for k in range(n):
                ts = now - timedelta(seconds=interval * (n - k))
                if ts > end:
                    break
                t = k / n
                diurnal = math.sin(2 * math.pi * (t * hours / 24)) * 12
                spike = 45 if (i == 0 and k > n - 12) else 0  # host 1: recent CPU spike -> alert
                cpu = min(100, max(1, base_cpu + diurnal + rng.gauss(0, 4) + spike))
                mem = min(99, max(5, base_mem + diurnal / 3 + rng.gauss(0, 1.5)))
                disk = min(99, disk0 + t * 2)
                mt = 16 * 2**30
                s.add(models.Metric(
                    host_id=h.id, ts=ts, cpu_percent=round(cpu, 2), mem_percent=round(mem, 2),
                    mem_total_bytes=mt, mem_available_bytes=int(mt * (1 - mem / 100)),
                    disk_percent=round(disk, 2), disk_total_bytes=500 * 10**9, disk_free_bytes=int(500e9 * (1 - disk / 100)),
                    net_sent_bps=max(0, 2e5 + 1.5e5 * math.sin(t * 20 + net_phase) + rng.gauss(0, 3e4)),
                    net_recv_bps=max(0, 5e5 + 3e5 * math.sin(t * 17 + net_phase) + rng.gauss(0, 6e4)),
                    uptime_seconds=int(3 * 86400 + k * interval), load1=round(cpu / 25 + rng.random() * .3, 2),
                    load5=round(cpu / 28, 2), load15=round(cpu / 30, 2)))
                if k % max(1, 60 // interval) == 0:
                    for name, kind, target, p_fail, base_ms in (("web", "http", "http://localhost/health", .01, 40),
                                                                 ("ssh", "tcp", "localhost:22", 0.0, 3)):
                        failing = (name == "web" and i == 2 and k > n - 6)  # host 3: web down recently
                        ok = not failing and rng.random() > p_fail
                        s.add(models.ServiceCheck(host_id=h.id, name=name, ts=ts, kind=kind, target=target, ok=ok,
                                                  response_ms=round(base_ms * rng.uniform(.7, 1.8), 1) if ok else None,
                                                  status_code=200 if ok and kind == "http" else (None if ok else 503),
                                                  error="" if ok else "HTTP 503"))
            h.last_seen = end
        s.commit()
    return ids


def seed_rules_and_alerts(db: Database) -> None:
    with db.session() as s:
        if not s.query(models.AlertRule).count():
            s.add_all([
                models.AlertRule(name="CPU high", type="cpu_high", threshold=85, for_seconds=300, severity="warning"),
                models.AlertRule(name="Memory high", type="mem_high", threshold=90, for_seconds=300, severity="warning"),
                models.AlertRule(name="Disk almost full", type="disk_low", threshold=15, severity="critical"),
                models.AlertRule(name="Host down", type="host_down", severity="critical"),
                models.AlertRule(name="Service down", type="service_down", severity="critical"),
                models.AlertRule(name="Slow response", type="response_slow", threshold=500, severity="info"),
            ])
            s.commit()
        settings = get_settings()
        evaluate(s, settings, Notifier(settings), utcnow())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hosts", type=int, default=8)
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--purge", action="store_true", help="delete all simulated hosts and their data")
    args = ap.parse_args()
    db = Database(get_settings().database_url)
    db.create_all()
    if args.purge:
        print(f"removed {purge(db)} simulated hosts")
        return
    purge(db)
    ids = seed(db, args.hosts, args.hours, args.interval)
    seed_rules_and_alerts(db)
    print(f"created {len(ids)} SIMULATED hosts (view with 'Show simulated data' in the dashboard)")


if __name__ == "__main__":
    main()
