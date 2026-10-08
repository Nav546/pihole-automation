"""Print a daily summary from Pi-hole: queries, % blocked, top domains and clients.

Usage:
    export PIHOLE_PASSWORD='your-password'
    python stats.py
    python stats.py --json        # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import sys

from pihole_client import PiholeClient, PiholeError, load_config


def build_report(client: PiholeClient, top_n: int) -> dict:
    summary = client.summary()
    queries = summary.get("queries", {})
    clients = summary.get("clients", {})
    return {
        "queries_total": queries.get("total", 0),
        "queries_blocked": queries.get("blocked", 0),
        "percent_blocked": round(queries.get("percent_blocked", 0.0), 1),
        "unique_domains": queries.get("unique_domains", 0),
        "active_clients": clients.get("active", 0),
        "top_blocked": [(d["domain"], d["count"]) for d in client.top_domains(True, top_n)],
        "top_permitted": [(d["domain"], d["count"]) for d in client.top_domains(False, top_n)],
        "top_clients": [
            (c.get("name") or c.get("ip"), c["count"]) for c in client.top_clients(top_n)
        ],
    }


def format_report(r: dict) -> str:
    def fmt(pairs: list) -> str:
        return ", ".join(f"{name} ({count:,})" for name, count in pairs) or "none"

    return "\n".join(
        [
            "Pi-hole summary",
            f"Queries:        {r['queries_total']:,}",
            f"Blocked:        {r['queries_blocked']:,}  ({r['percent_blocked']}%)",
            f"Unique domains: {r['unique_domains']:,}",
            f"Active clients: {r['active_clients']}",
            f"Top blocked:    {fmt(r['top_blocked'])}",
            f"Top permitted:  {fmt(r['top_permitted'])}",
            f"Top clients:    {fmt(r['top_clients'])}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", help="path to config.yaml")
    parser.add_argument("--top", type=int, default=3, help="how many top entries to show")
    parser.add_argument("--json", action="store_true", help="output JSON")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    try:
        with PiholeClient(cfg["pihole"]["base_url"]) as client:
            report = build_report(client, args.top)
    except PiholeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2) if args.json else format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
