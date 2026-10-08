# pihole-automation

![CI](https://github.com/Nav546/pihole-automation/actions/workflows/ci.yml/badge.svg)

Python scripts that automate a Pi-hole DNS server through its REST API: daily stats,
blocklist management, and local DNS records managed from a config file.
Built on top of my [pihole-docker](https://github.com/Nav546/pihole-docker) project.

Targets **Pi-hole v6** (Core 6.x / FTL 6.x). v5 uses a different API and is not supported.

## What it does

| Script | Purpose |
|---|---|
| `stats.py` | Queries, % blocked, top blocked/permitted domains, top clients (`--json` supported) |
| `blocklists.py` | `list`, `add`, `remove`, and `sync` blocklists from `config.yaml` |
| `dns_records.py` | Sync local DNS records from `config.yaml` (add / update / optional prune) |
| `pihole_client.py` | Small API client: login, logout, error handling, session cleanup |

## Design choices

- **Config as source of truth, idempotent sync.** Running `dns_records.py` twice changes nothing the second time.
- **`--dry-run` everywhere that changes state**, so you see the plan before applying it.
- **Nothing is deleted unless you pass `--prune`.**
- **Password comes from the `PIHOLE_PASSWORD` environment variable**, never from a file in Git.
- **Always logs out** (context manager), so API sessions do not pile up.
- **Plan logic is pure functions**, unit tested without a live Pi-hole. CI runs ruff and pytest on every push.

## Setup

```bash
# 1. start Pi-hole (see the pihole-docker repo)
docker compose up -d

# 2. install
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. credentials (same password as your Pi-hole web UI)
export PIHOLE_PASSWORD='your-password'                 # PowerShell: $env:PIHOLE_PASSWORD='your-password'
```

Edit `config.yaml` if your Pi-hole is not at `http://localhost:8080`.

## Usage

```bash
python stats.py
python stats.py --json

python blocklists.py list
python blocklists.py sync --dry-run
python blocklists.py sync

python dns_records.py --dry-run
python dns_records.py
python dns_records.py --prune
```

Example output (illustrative):

```
$ python dns_records.py
Added:     nas.home.lab -> 192.168.1.50
Added:     printer.home.lab -> 192.168.1.60
Unchanged: 0   Added: 2   Updated: 0   Removed: 0
```

## Tests

```bash
ruff check .
python -m pytest -q
```

## Notes

- Updating gravity after list changes can take a while on large lists.
- Keep Pi-hole bound to localhost or your LAN. Never expose its API to the internet.
