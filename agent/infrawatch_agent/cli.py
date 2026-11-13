from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .agent import Agent, load_api_key, register, setup_logging
from .client import AuthError, RejectedBatch, ServerClient, TransientError
from .config import ConfigError, load_config


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="infrawatch-agent")
    ap.add_argument("-c", "--config", default=None, help="path to agent.yaml")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="run the agent (registers on first start)")
    sub.add_parser("register", help="register with the server and store the API key")
    sub.add_parser("check", help="validate config and verify server connectivity + credentials")
    sub.add_parser("status", help="print local health information")
    sub.add_parser("validate", help="validate the configuration file only")
    args = ap.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    setup_logging(cfg.log_level)

    if args.cmd == "validate":
        print("configuration OK")
        return 0
    if args.cmd == "status":
        p = cfg.state_dir / "health.json"
        if not p.is_file():
            print("no health file (agent has not run yet)", file=sys.stderr)
            return 1
        print(json.dumps(json.loads(p.read_text()), indent=2))
        return 0

    client = ServerClient(cfg)
    try:
        if args.cmd == "register":
            register(cfg, client)
            print("registered; key stored in", cfg.key_file)
            return 0
        if args.cmd == "check":
            key = load_api_key(cfg)
            if not key:
                print("not registered yet (run `register`)", file=sys.stderr)
                return 1
            print(json.dumps(client.whoami(key), indent=2))
            return 0
        agent = Agent(cfg, client)
        agent.install_signal_handlers()
        agent.run()
        return 0
    except (AuthError, RejectedBatch) as exc:
        print(f"server rejected the request: {exc}", file=sys.stderr)
        return 1
    except TransientError as exc:
        print(f"cannot reach server: {exc}", file=sys.stderr)
        return 1
