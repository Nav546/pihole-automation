"""Sync Pi-hole local DNS records from config.yaml (config is the source of truth).

Usage:
    python dns_records.py --dry-run      # show the plan, change nothing
    python dns_records.py                # add/update records from config.yaml
    python dns_records.py --prune        # also remove records not in config.yaml

Safe to run repeatedly: unchanged records are left alone (idempotent).
"""

from __future__ import annotations

import argparse
import sys

from pihole_client import PiholeClient, PiholeError, load_config


def plan_changes(desired: dict[str, str], current: dict[str, str], prune: bool = False):
    """Pure function (easy to unit test).

    Returns (to_add, to_update, to_remove, unchanged) where
      to_add:    {hostname: ip} not in Pi-hole yet
      to_update: {hostname: (old_ip, new_ip)} present with a different IP
      to_remove: {hostname: ip} in Pi-hole but not in config (only with prune)
      unchanged: list of hostnames already correct
    """
    to_add = {h: ip for h, ip in desired.items() if h not in current}
    to_update = {
        h: (current[h], ip) for h, ip in desired.items() if h in current and current[h] != ip
    }
    to_remove = {h: ip for h, ip in current.items() if h not in desired} if prune else {}
    unchanged = [h for h, ip in desired.items() if current.get(h) == ip]
    return to_add, to_update, to_remove, unchanged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", help="path to config.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prune", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    desired = cfg.get("dns_records", {}) or {}
    dry = args.dry_run
    try:
        with PiholeClient(cfg["pihole"]["base_url"]) as client:
            current = client.get_hosts()
            to_add, to_update, to_remove, unchanged = plan_changes(
                desired, current, prune=args.prune
            )
            for host, ip in to_add.items():
                print(f"{'Would add' if dry else 'Added'}:     {host} -> {ip}")
                if not dry:
                    client.add_host(host, ip)
            for host, (old, new) in to_update.items():
                print(f"{'Would update' if dry else 'Updated'}:  {host} {old} -> {new}")
                if not dry:
                    client.remove_host(host, old)
                    client.add_host(host, new)
            for host, ip in to_remove.items():
                print(f"{'Would remove' if dry else 'Removed'}:  {host} -> {ip}")
                if not dry:
                    client.remove_host(host, ip)
            print(
                f"Unchanged: {len(unchanged)}   Added: {len(to_add)}   "
                f"Updated: {len(to_update)}   Removed: {len(to_remove)}"
                + ("   (dry run)" if dry else "")
            )
    except PiholeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
