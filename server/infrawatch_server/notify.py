"""Notification delivery. Webhooks only (JSON POST); easy to extend."""
from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx

from . import models
from .config import Settings

log = logging.getLogger("infrawatch.notify")
SEV_RANK = {"info": 0, "warning": 1, "critical": 2}


def validate_webhook_url(url: str, allow_private: bool) -> None:
    """Reject non-http(s) URLs and (unless allowed) internal targets, to limit SSRF."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("webhook URL must be http(s)")
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError(f"cannot resolve webhook host: {exc}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("webhook target resolves to a non-public address")


class Notifier:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, channel: models.NotificationChannel, event: str, alert: models.Alert) -> bool:
        if not channel.enabled or SEV_RANK[alert.severity] < SEV_RANK.get(channel.min_severity, 0):
            return False
        payload = {
            "event": event,
            "alert": {
                "id": alert.id, "title": alert.title, "message": alert.message, "severity": alert.severity,
                "status": alert.status, "host": alert.host.hostname, "environment": alert.host.environment,
                "value": alert.value, "opened_at": alert.opened_at.isoformat(),
            },
        }
        try:
            validate_webhook_url(channel.url, self.settings.allow_private_webhooks)
            r = httpx.post(channel.url, json=payload, timeout=self.settings.webhook_timeout_seconds,
                           follow_redirects=False)
            r.raise_for_status()
            return True
        except Exception as exc:
            log.warning("notification to channel %s failed: %s", channel.name, exc)
            return False
