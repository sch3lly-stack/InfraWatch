"""Agent configuration: YAML file + environment overrides, strictly validated."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml


class ConfigError(ValueError):
    pass


@dataclass
class CheckConfig:
    name: str
    kind: str  # http | tcp | process
    target: str  # url | host:port | process name
    timeout: float = 5.0
    expected_status: int | None = None  # http: exact status; default any 2xx/3xx
    verify_tls: bool = True


@dataclass
class AgentConfig:
    server_url: str
    interval: int = 15
    http_timeout: float = 10.0
    state_dir: Path = Path("./infrawatch-agent-state")
    disk_path: str = "/"
    ca_bundle: str | None = None  # custom CA (self-signed servers); never disable verification
    allow_insecure_http: bool = False  # lab use only; refuses non-localhost plain HTTP otherwise
    enrollment_token: str | None = None
    api_key: str | None = None
    buffer_max_samples: int = 20000
    batch_size: int = 100
    backoff_max: float = 300.0
    log_level: str = "INFO"
    checks: list[CheckConfig] = field(default_factory=list)

    @property
    def key_file(self) -> Path:
        return self.state_dir / "agent.key"


def _is_local(host: str | None) -> bool:
    return host in ("localhost", "127.0.0.1", "::1")


def validate(cfg: AgentConfig) -> AgentConfig:
    u = urlparse(cfg.server_url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ConfigError("server_url must be a http(s) URL")
    if u.scheme == "http" and not (cfg.allow_insecure_http or _is_local(u.hostname)):
        raise ConfigError("server_url must use https (set allow_insecure_http only for lab testing)")
    if not 1 <= cfg.interval <= 3600:
        raise ConfigError("interval must be between 1 and 3600 seconds")
    if not 1 <= cfg.http_timeout <= 120:
        raise ConfigError("http_timeout must be between 1 and 120 seconds")
    if not 1 <= cfg.batch_size <= 500:
        raise ConfigError("batch_size must be between 1 and 500")
    if cfg.buffer_max_samples < 10:
        raise ConfigError("buffer_max_samples must be >= 10")
    if cfg.ca_bundle and not Path(cfg.ca_bundle).is_file():
        raise ConfigError(f"ca_bundle not found: {cfg.ca_bundle}")
    names = set()
    for c in cfg.checks:
        if not c.name or len(c.name) > 128:
            raise ConfigError("check name must be 1-128 characters")
        if c.name in names:
            raise ConfigError(f"duplicate check name: {c.name}")
        names.add(c.name)
        if c.kind not in ("http", "tcp", "process"):
            raise ConfigError(f"check {c.name}: kind must be http, tcp or process")
        if not 0.1 <= c.timeout <= 60:
            raise ConfigError(f"check {c.name}: timeout must be between 0.1 and 60")
        if c.kind == "http" and urlparse(c.target).scheme not in ("http", "https"):
            raise ConfigError(f"check {c.name}: target must be an http(s) URL")
        if c.kind == "tcp":
            host, _, port = c.target.rpartition(":")
            if not host or not port.isdigit() or not 0 < int(port) < 65536:
                raise ConfigError(f"check {c.name}: tcp target must be host:port")
        if c.kind == "process" and not c.target:
            raise ConfigError(f"check {c.name}: process name required")
    return cfg


def load_config(path: str | os.PathLike | None) -> AgentConfig:
    raw: dict = {}
    if path:
        p = Path(path)
        if not p.is_file():
            raise ConfigError(f"config file not found: {p}")
        try:
            raw = yaml.safe_load(p.read_text()) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("config root must be a mapping")
    env = os.environ
    raw.setdefault("server_url", env.get("INFRAWATCH_SERVER_URL"))
    raw["enrollment_token"] = env.get("INFRAWATCH_ENROLLMENT_TOKEN", raw.get("enrollment_token"))
    raw["api_key"] = env.get("INFRAWATCH_AGENT_KEY", raw.get("api_key"))
    if not raw.get("server_url"):
        raise ConfigError("server_url is required")
    checks_raw = raw.pop("checks", []) or []
    known = set(AgentConfig.__dataclass_fields__) - {"checks"}
    unknown = set(raw) - known
    if unknown:
        raise ConfigError(f"unknown config keys: {sorted(unknown)}")
    try:
        cfg = AgentConfig(**raw)
        cfg.state_dir = Path(cfg.state_dir)
        cfg.checks = [CheckConfig(**c) for c in checks_raw]
    except TypeError as exc:
        raise ConfigError(str(exc)) from exc
    return validate(cfg)
