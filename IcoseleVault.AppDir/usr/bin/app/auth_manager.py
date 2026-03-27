"""Tasks 2-3 — LDAP auth + local RBAC. Stdlib only (socket, ssl, hashlib)."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import ssl
import stat
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_DATA = Path(__file__).resolve().parent.parent / "data"
_LDAP_CFG = _DATA / "ldap_config.json"
_LDAP_GROUPS = _DATA / "ldap_groups.json"
_LOCAL_USERS = _DATA / "local_users.json"

ROLES = {
    "admin": {"label": "Admin", "can_modify": True, "can_action": True, "can_view": True, "can_delete": True},
    "operator": {"label": "Operator", "can_modify": False, "can_action": True, "can_view": True, "can_delete": False},
    "viewer": {"label": "Viewer", "can_modify": False, "can_action": False, "can_view": True, "can_delete": False},
}


def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ── Local users ────────────────────────────────────────────────────────

def load_local_users() -> list[dict]:
    if _LOCAL_USERS.exists():
        try:
            return json.loads(_LOCAL_USERS.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_local_users(users: list[dict]) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    _LOCAL_USERS.write_text(json.dumps(users, indent=2))
    try:
        os.chmod(_LOCAL_USERS, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def create_local_user(username: str, password: str, role: str = "viewer") -> bool:
    users = load_local_users()
    if any(u["username"] == username for u in users):
        return False
    users.append({
        "username": username,
        "password_hash": _hash_pw(password),
        "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_login": "",
    })
    save_local_users(users)
    return True


def verify_local_user(username: str, password: str) -> dict | None:
    for u in load_local_users():
        if u["username"] == username and u["password_hash"] == _hash_pw(password):
            u["last_login"] = datetime.now(timezone.utc).isoformat()
            save_local_users(load_local_users())  # update last_login
            return u
    return None


def delete_local_user(username: str) -> None:
    users = [u for u in load_local_users() if u["username"] != username]
    save_local_users(users)


# ── LDAP config ────────────────────────────────────────────────────────

_LDAP_DEFAULTS = {
    "enabled": False, "host": "", "port": 389, "use_ssl": False,
    "base_dn": "", "bind_dn": "", "bind_password": "",
    "user_filter": "(uid={username})", "group_attr": "memberOf",
}


def load_ldap_config() -> dict:
    if _LDAP_CFG.exists():
        try:
            d = json.loads(_LDAP_CFG.read_text())
            m = dict(_LDAP_DEFAULTS)
            m.update(d)
            return m
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_LDAP_DEFAULTS)


def save_ldap_config(cfg: dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    _LDAP_CFG.write_text(json.dumps(cfg, indent=2))
    try:
        os.chmod(_LDAP_CFG, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def load_ldap_groups() -> dict:
    if _LDAP_GROUPS.exists():
        try:
            return json.loads(_LDAP_GROUPS.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"admin_groups": [], "operator_groups": [], "viewer_groups": []}


def save_ldap_groups(groups: dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    _LDAP_GROUPS.write_text(json.dumps(groups, indent=2))


def test_ldap_connection(cfg: dict) -> tuple[bool, str]:
    """Minimal LDAP bind test using raw sockets."""
    host = cfg.get("host", "")
    port = cfg.get("port", 389)
    if not host:
        return False, "No host configured"
    try:
        sock = socket.create_connection((host, port), timeout=5)
        if cfg.get("use_ssl"):
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=host)
        sock.close()
        return True, f"TCP connection to {host}:{port} succeeded"
    except Exception as exc:
        return False, str(exc)
