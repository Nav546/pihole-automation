"""Manage Pi-hole blocklists, either one-off or from config.yaml.

Usage:
    python blocklists.py list
    python blocklists.py add https://example.com/list.txt
    python blocklists.py remove https://example.com/list.txt
    python blocklists.py sync --dry-run     # show what config.yaml would change
    python blocklists.py sync               # add missing lists, then update gravity

`sync` only ADDS lists that are in config.yaml but missing from Pi-hole. It never
removes lists unless you pass --prune.
"""

from __future__ import annotations

import argparse
import sys

from pihole_client import PiholeClient, PiholeError, load_config


def plan_changes(desired: list[str], current: list[str], prune: bool = False):
    """Pure function (easy to unit test): returns (to_add, to_remove)."""
    desired_set, current_set = set(desired), set(current)
    to_add = [u for u in desired if u not in current_set]
    to_remove = sorted(current_set - desired_set) if prune else []
    return to_add, to_remove


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", help="path to config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    add_p = sub.add_parser("add")
    add_p.add_argument("url")
    add_p.add_argument("--comment", default="added by pihole-automation")
    rm_p = sub.add_parser("remove")
    rm_p.add_argument("url")
    sync_p = sub.add_parser("sync")
    sync_p.add_argument("--dry-run", action="store_true")
    sync_p.add_argument("--prune", action="store_true", help="also remove lists not in config")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    try:
        with PiholeClient(cfg["pihole"]["base_url"]) as client:
            if args.command == "list":
                for item in client.get_lists():
                    state = "on " if item.get("enabled") else "off"
                    print(f"[{state}] {item['address']}")
            elif args.command == "add":
                client.add_list(args.url, args.comment)
                print(f"Added: {args.url}\nRun 'python blocklists.py sync' or update gravity to apply.")
                client.update_gravity()
                print("Gravity update finished.")
            elif args.command == "remove":
                client.remove_list(args.url)
                print(f"Removed: {args.url}")
                client.update_gravity()
            elif args.command == "sync":
                current = [i["address"] for i in client.get_lists()]
                to_add, to_remove = plan_changes(
                    cfg.get("blocklists", []), current, prune=args.prune
                )
                for url in to_add:
                    print(f"{'Would add' if args.dry_run else 'Adding'}:   {url}")
                for url in to_remove:
                    print(f"{'Would remove' if args.dry_run else 'Removing'}: {url}")
                if not to_add and not to_remove:
                    print("Already in sync. Nothing to do.")
                elif not args.dry_run:
                    for url in to_add:
                        client.add_list(url, "managed by pihole-automation")
                    for url in to_remove:
                        client.remove_list(url)
                    client.update_gravity()
                    print("Gravity update finished.")
    except PiholeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
