"""HTTPS client for the InfraWatch server."""
from __future__ import annotations

import ssl

import httpx

from . import __version__
from .config import AgentConfig


class AuthError(Exception):
    """Server rejected our credentials (revoked/invalid key)."""


class RejectedBatch(Exception):
    """Server permanently rejected the payload (4xx other than auth/rate-limit)."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"{status}: {detail}")
        self.status = status


class TransientError(Exception):
    """Network failure, timeout, 5xx or 429: safe to retry later."""


class ServerClient:
    def __init__(self, cfg: AgentConfig, transport: httpx.BaseTransport | None = None):
        self.cfg = cfg
        verify = ssl.create_default_context(cafile=cfg.ca_bundle) if cfg.ca_bundle else True  # never disabled
        self._http = httpx.Client(base_url=cfg.server_url.rstrip("/"), timeout=cfg.http_timeout, verify=verify,
                                  headers={"User-Agent": f"infrawatch-agent/{__version__}"}, transport=transport)

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, token: str, json=None) -> httpx.Response:
        try:
            r = self._http.request(method, path, json=json, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as exc:
            raise TransientError(type(exc).__name__) from exc
        if r.status_code in (401, 403):
            raise AuthError(r.text[:200])
        if r.status_code == 429 or r.status_code >= 500:
            raise TransientError(f"HTTP {r.status_code}")
        if r.status_code >= 400:
            raise RejectedBatch(r.status_code, r.text[:200])
        return r

    def register(self, enrollment_token: str, info: dict) -> dict:
        return self._request("POST", "/api/v1/agents/register", enrollment_token,
                             json=info | {"agent_version": __version__}).json()

    def whoami(self, api_key: str) -> dict:
        return self._request("GET", "/api/v1/agents/whoami", api_key).json()

    def send(self, api_key: str, info: dict, samples: list[dict], interval: int) -> dict:
        body = {"agent": info | {"agent_version": __version__, "collection_interval": interval}, "samples": samples}
        return self._request("POST", "/api/v1/agents/metrics", api_key, json=body).json()
