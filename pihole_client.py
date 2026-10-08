"""Small client for the Pi-hole v6 REST API.

Pi-hole v6 (Core 6.x / FTL 6.x) replaced the old api.php with a REST API:
  POST   /api/auth                      log in, returns a session id (sid)
  DELETE /api/auth                      log out
  GET    /api/stats/summary             query counts, % blocked, clients
  GET    /api/stats/top_domains         top permitted / blocked domains
  GET    /api/stats/top_clients         top clients
  GET    /api/lists                     list blocklists/allowlists
  POST   /api/lists?type=block          add a list
  DELETE /api/lists/{address}?type=block remove a list
  POST   /api/action/gravity            rebuild gravity (apply list changes)
  GET    /api/config/dns/hosts          local DNS records ("IP hostname")
  PUT    /api/config/dns/hosts/{entry}  add a record
  DELETE /api/config/dns/hosts/{entry}  remove a record

This does NOT work against Pi-hole v5 (different API).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Self
from urllib.parse import quote

import requests
import yaml

DEFAULT_CONFIG = Path(__file__).with_name("config.yaml")


class PiholeError(RuntimeError):
    """Raised for any failed Pi-hole API call, with a readable message."""


def load_config(path: str | os.PathLike | None = None) -> dict[str, Any]:
    """Load config.yaml. The password is never stored there: use PIHOLE_PASSWORD."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    if not cfg_path.exists():
        raise PiholeError(f"Config file not found: {cfg_path}")
    with cfg_path.open() as fh:
        return yaml.safe_load(fh) or {}


class PiholeClient:
    def __init__(
        self,
        base_url: str,
        password: str | None = None,
        timeout: float = 10.0,
        verify_tls: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.password = password if password is not None else os.environ.get("PIHOLE_PASSWORD")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.verify = verify_tls
        self._sid: str | None = None

    # -- context manager: always log out so we don't leak API sessions ---------
    def __enter__(self) -> Self:
        self.login()
        return self

    def __exit__(self, *exc: object) -> None:
        self.logout()

    # -- low level -------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float | None = None,
        parse_json: bool = True,
        **kwargs: Any,
    ) -> Any:
        url = f"{self.base_url}/api{path}"
        headers = kwargs.pop("headers", {})
        if self._sid:
            headers["sid"] = self._sid
        try:
            resp = self.session.request(
                method, url, headers=headers, timeout=timeout or self.timeout, **kwargs
            )
        except requests.ConnectionError as exc:
            raise PiholeError(
                f"Cannot reach Pi-hole at {self.base_url}. Is the container running "
                f"and is base_url correct?"
            ) from exc
        except requests.Timeout as exc:
            raise PiholeError(f"Timed out talking to {url}") from exc

        if resp.status_code == 401:
            raise PiholeError("Unauthorised: check PIHOLE_PASSWORD (or session expired).")
        if resp.status_code >= 400:
            detail = ""
            try:
                detail = resp.json().get("error", {}).get("message", "")
            except ValueError:
                detail = resp.text[:200]
            raise PiholeError(f"{method} {path} failed ({resp.status_code}): {detail}")
        if resp.status_code == 204 or not resp.content:
            return {}
        if not parse_json:
            return resp.text
        try:
            return resp.json()
        except ValueError as exc:
            raise PiholeError(f"{method} {path} returned a non-JSON response") from exc

    # -- auth ------------------------------------------------------------------
    def login(self) -> None:
        if not self.password:
            raise PiholeError("No password. Set the PIHOLE_PASSWORD environment variable.")
        data = self._request("POST", "/auth", json={"password": self.password})
        sess = data.get("session", {})
        if not sess.get("valid"):
            raise PiholeError(f"Login rejected: {sess.get('message', 'invalid password')}")
        self._sid = sess["sid"]

    def logout(self) -> None:
        if self._sid:
            try:
                self._request("DELETE", "/auth")
            except PiholeError:
                pass  # best effort
            self._sid = None

    # -- stats -----------------------------------------------------------------
    def summary(self) -> dict[str, Any]:
        return self._request("GET", "/stats/summary")

    def top_domains(self, blocked: bool = False, count: int = 5) -> list[dict[str, Any]]:
        data = self._request(
            "GET", "/stats/top_domains", params={"blocked": str(blocked).lower(), "count": count}
        )
        return data.get("domains", [])

    def top_clients(self, count: int = 5) -> list[dict[str, Any]]:
        data = self._request("GET", "/stats/top_clients", params={"count": count})
        return data.get("clients", [])

    # -- blocklists ------------------------------------------------------------
    def get_lists(self, list_type: str = "block") -> list[dict[str, Any]]:
        data = self._request("GET", "/lists", params={"type": list_type})
        return data.get("lists", [])

    def add_list(self, address: str, comment: str = "", list_type: str = "block") -> None:
        self._request(
            "POST",
            "/lists",
            params={"type": list_type},
            json={"address": address, "comment": comment, "enabled": True},
        )

    def remove_list(self, address: str, list_type: str = "block") -> None:
        self._request("DELETE", f"/lists/{quote(address, safe='')}", params={"type": list_type})

    def update_gravity(self) -> None:
        """Rebuild gravity so list changes take effect.

        Pi-hole v6 streams the gravity log back as plain text (not JSON) and the
        download can take a minute or more, so use a long timeout and skip JSON parsing.
        """
        self._request("POST", "/action/gravity", timeout=300, parse_json=False)

    # -- local DNS records -----------------------------------------------------
    def get_hosts(self) -> dict[str, str]:
        """Return current local DNS records as {hostname: ip}."""
        data = self._request("GET", "/config/dns/hosts")
        entries = data.get("config", {}).get("dns", {}).get("hosts", [])
        records: dict[str, str] = {}
        for entry in entries:
            parts = entry.split()
            if len(parts) >= 2:
                records[parts[1]] = parts[0]
        return records

    def add_host(self, hostname: str, ip: str) -> None:
        self._request("PUT", f"/config/dns/hosts/{quote(f'{ip} {hostname}', safe='')}")

    def remove_host(self, hostname: str, ip: str) -> None:
        self._request("DELETE", f"/config/dns/hosts/{quote(f'{ip} {hostname}', safe='')}")
