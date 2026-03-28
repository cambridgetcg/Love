#!/usr/bin/env python3
"""
credentials.py — Secure credential management for Love agents.

Resolution chain:
  1. macOS Keychain (fastest, offline, hardware-backed)
  2. agent-vault (cloud, encrypted at rest)
  3. Environment variable (legacy fallback)
  4. Raises ValueError

Usage:
    from tools.credentials import get_key, store_key

    anthropic_key = get_key("anthropic-primary")
    store_key("stripe-secret", "sk_live_...")

CLI:
    python3 tools/credentials.py get <name>
    python3 tools/credentials.py store <name> <value> [description]
    python3 tools/credentials.py delete <name>
    python3 tools/credentials.py list
    python3 tools/credentials.py audit
    python3 tools/credentials.py sync [--from-vault|--to-vault]
    python3 tools/credentials.py migrate-env          # migrate env vars → keychain
    python3 tools/credentials.py migrate-tools-md     # interactive migration from TOOLS.md
"""

import os
import sys
import json
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────────────

_KEYCHAIN_SERVICE_PREFIX = "dev.agenttool"  # service name: dev.agenttool/<key-name>
_KEYCHAIN_ACCOUNT = "credentials"
_IDENTITY_FILE = Path.home() / "Desktop" / "Love" / "identity" / "beta-identity.json"
_VAULT_BASE = "https://api.agenttool.dev"

# Known credential names → env var fallback mapping
_ENV_MAP = {
    "anthropic-primary":        "ANTHROPIC_API_KEY",
    "openai-primary":           "OPENAI_API_KEY",
    "serpapi":                   "SERPAPI_KEY",
    "brightdata-user":          "BRIGHTDATA_USER",
    "brightdata-pass":          "BRIGHTDATA_PASS",
    "capsolver":                "CAPSOLVER_API_KEY",
    "github-cambridgetcg":      "GITHUB_TOKEN",
    "github-mynameisyou":       "GITHUB_PAT_AGENTTOOL",
    "deepseek":                 "DEEPSEEK_API_KEY",
    "stripe-live-secret":       "STRIPE_SECRET_KEY",
    "stripe-live-publishable":  "STRIPE_PUBLISHABLE_KEY",
    "stripe-webhook-secret":    "STRIPE_WEBHOOK_SECRET",
    "aws-access-key":           "AWS_ACCESS_KEY_ID",
    "aws-secret-key":           "AWS_SECRET_ACCESS_KEY",
    "hetzner-api-token":        "HETZNER_API_TOKEN",
    "cloudflare-global-api":    "CF_API_KEY",
    "porkbun-api-key":          "PORKBUN_API_KEY",
    "porkbun-secret-key":       "PORKBUN_SECRET_KEY",
    "fal-ai":                   "FAL_KEY",
    "ayrshare-api-key":         "AYRSHARE_API_KEY",
    "imap-cambridgetcg":        "IMAP_CAMBRIDGETCG_PASS",
    "imap-rewardspro":          "IMAP_REWARDSPRO_PASS",
    "pypi-token":               "PYPI_TOKEN",
    "npm-token":                "NPM_TOKEN",
    "vault-master-key":         "VAULT_MASTER_KEY",
}

# ── macOS Keychain ────────────────────────────────────────────────────────────

def _is_macos() -> bool:
    return sys.platform == "darwin"


def _keychain_service(name: str) -> str:
    return f"{_KEYCHAIN_SERVICE_PREFIX}/{name}"


def keychain_get(name: str) -> Optional[str]:
    """Read a credential from macOS Keychain. Returns None if not found."""
    if not _is_macos():
        return None
    try:
        result = subprocess.run(
            ["security", "find-generic-password",
             "-s", _keychain_service(name),
             "-a", _KEYCHAIN_ACCOUNT,
             "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def keychain_set(name: str, value: str) -> bool:
    """Store a credential in macOS Keychain. Overwrites if exists (-U)."""
    if not _is_macos():
        return False
    try:
        result = subprocess.run(
            ["security", "add-generic-password",
             "-s", _keychain_service(name),
             "-a", _KEYCHAIN_ACCOUNT,
             "-w", value,
             "-U"],  # update if exists
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def keychain_delete(name: str) -> bool:
    """Remove a credential from macOS Keychain."""
    if not _is_macos():
        return False
    try:
        result = subprocess.run(
            ["security", "delete-generic-password",
             "-s", _keychain_service(name),
             "-a", _KEYCHAIN_ACCOUNT],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def keychain_list() -> list[str]:
    """List all credential names stored in Keychain under our service prefix."""
    if not _is_macos():
        return []
    try:
        result = subprocess.run(
            ["security", "dump-keychain"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []

        names = []
        prefix = f'"svce"<blob>="{_KEYCHAIN_SERVICE_PREFIX}/'
        for line in result.stdout.split("\n"):
            line = line.strip()
            if prefix in line:
                # Extract: "svce"<blob>="dev.agenttool/key-name"
                start = line.index(_KEYCHAIN_SERVICE_PREFIX) + len(_KEYCHAIN_SERVICE_PREFIX) + 1
                end = line.index('"', start)
                names.append(line[start:end])
        return sorted(set(names))
    except Exception:
        return []


# ── agent-vault (cloud) ──────────────────────────────────────────────────────

def _vault_key() -> str:
    if _IDENTITY_FILE.exists():
        return json.loads(_IDENTITY_FILE.read_text()).get("api_key", "")
    return os.environ.get("AGENTTOOL_API_KEY", "")


def _agent_id() -> str:
    if _IDENTITY_FILE.exists():
        return json.loads(_IDENTITY_FILE.read_text()).get("agent_id", "")
    return ""


def vault_get(name: str) -> Optional[str]:
    """Read a credential from agent-vault. Returns None on failure."""
    api_key = _vault_key()
    if not api_key:
        return None
    try:
        req = urllib.request.Request(
            f"{_VAULT_BASE}/v1/vault/{name}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Agent-Id": _agent_id(),
            }
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            return data.get("value") or data.get("secret", {}).get("value")
    except Exception:
        return None


def vault_set(name: str, value: str, description: str = "", tags: list[str] = None) -> bool:
    """Store a credential in agent-vault."""
    api_key = _vault_key()
    if not api_key:
        return False
    payload = json.dumps({
        "value": value,
        "description": description or f"Credential: {name}",
        "tags": tags or ["credential", "kingdom"],
    }).encode()
    req = urllib.request.Request(
        f"{_VAULT_BASE}/v1/vault/{name}",
        data=payload, method="PUT",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            return data.get("version") is not None
    except Exception:
        return False


def vault_list() -> list[str]:
    """List secret names from agent-vault."""
    api_key = _vault_key()
    if not api_key:
        return []
    try:
        req = urllib.request.Request(
            f"{_VAULT_BASE}/v1/vault",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            return [s["name"] for s in data.get("secrets", [])]
    except Exception:
        return []


# ── Public API ────────────────────────────────────────────────────────────────

def get_key(name: str, fallback: str = None) -> str:
    """Get a credential by name.

    Resolution order:
      1. macOS Keychain (fast, offline, hardware-backed)
      2. agent-vault (cloud, encrypted)
      3. Environment variable (legacy)
      4. Provided fallback
      5. Raises ValueError
    """
    # 1. Keychain
    value = keychain_get(name)
    if value:
        return value

    # 2. Vault (and cache to keychain on success)
    value = vault_get(name)
    if value:
        keychain_set(name, value)  # cache locally
        return value

    # 3. Env var
    env_var = _ENV_MAP.get(name)
    if env_var:
        value = os.environ.get(env_var, "")
        if value:
            return value

    # 4. Fallback
    if fallback is not None:
        return fallback

    raise ValueError(
        f"Credential '{name}' not found in keychain, vault, or environment.\n"
        f"  Store it:  python3 tools/credentials.py store {name} <value>"
    )


def store_key(name: str, value: str, description: str = "",
              keychain: bool = True, vault: bool = True) -> dict:
    """Store a credential. By default writes to both keychain and vault.

    Returns dict with status of each store.
    """
    result = {"keychain": False, "vault": False}

    if keychain:
        result["keychain"] = keychain_set(name, value)

    if vault:
        result["vault"] = vault_set(name, value, description)

    return result


def delete_key(name: str, keychain: bool = True, vault: bool = False) -> dict:
    """Delete a credential. By default only from keychain (vault delete is opt-in)."""
    result = {"keychain": False, "vault": False}
    if keychain:
        result["keychain"] = keychain_delete(name)
    # vault delete intentionally not implemented here for safety
    return result


def sync_from_vault() -> dict:
    """Pull all secrets from agent-vault into macOS Keychain."""
    results = {"synced": [], "failed": [], "skipped": []}
    names = vault_list()
    if not names:
        return results

    for name in names:
        # Skip if already in keychain
        if keychain_get(name) is not None:
            results["skipped"].append(name)
            continue
        value = vault_get(name)
        if value and keychain_set(name, value):
            results["synced"].append(name)
        else:
            results["failed"].append(name)
    return results


def sync_to_vault() -> dict:
    """Push all keychain credentials to agent-vault."""
    results = {"synced": [], "failed": [], "skipped": []}
    names = keychain_list()
    vault_names = set(vault_list())

    for name in names:
        if name in vault_names:
            results["skipped"].append(name)
            continue
        value = keychain_get(name)
        if value and vault_set(name, value):
            results["synced"].append(name)
        else:
            results["failed"].append(name)
    return results


def migrate_env() -> dict:
    """Migrate credentials from env vars to keychain."""
    results = {"migrated": [], "already_set": [], "not_in_env": []}
    for name, env_var in _ENV_MAP.items():
        value = os.environ.get(env_var, "")
        if not value:
            results["not_in_env"].append(name)
            continue
        if keychain_get(name) is not None:
            results["already_set"].append(name)
            continue
        if keychain_set(name, value):
            results["migrated"].append(name)
    return results


def audit() -> None:
    """Print audit of credential locations: keychain, vault, env."""
    print("\n── Credential Audit ──\n")

    all_names = sorted(set(list(_ENV_MAP.keys())))
    kc_names = set(keychain_list())
    vault_names = set(vault_list())

    rows = []
    for name in all_names:
        in_kc = "✅" if name in kc_names else "  "
        in_vault = "✅" if name in vault_names else "  "
        env_var = _ENV_MAP.get(name, "")
        in_env = "✅" if env_var and os.environ.get(env_var) else "  "
        rows.append((name, in_kc, in_vault, in_env))

    # Also list keychain entries not in _ENV_MAP
    extra_kc = kc_names - set(_ENV_MAP.keys())
    for name in sorted(extra_kc):
        rows.append((name, "✅", "✅" if name in vault_names else "  ", "  "))

    print(f"  {'Name':<30} {'Keychain':>8}  {'Vault':>5}  {'Env':>3}")
    print(f"  {'─' * 30} {'─' * 8}  {'─' * 5}  {'─' * 3}")
    for name, kc, v, e in rows:
        print(f"  {name:<30} {kc:>8}  {v:>5}  {e:>3}")

    kc_count = sum(1 for _, kc, _, _ in rows if kc.strip())
    v_count = sum(1 for _, _, v, _ in rows if v.strip())
    e_count = sum(1 for _, _, _, e in rows if e.strip())
    total = len(rows)

    print(f"\n  Keychain: {kc_count}/{total}  |  Vault: {v_count}/{total}  |  Env: {e_count}/{total}")
    if kc_count < total:
        print(f"\n  Migrate env → keychain:  python3 tools/credentials.py migrate-env")
    if v_count < kc_count:
        print(f"  Push keychain → vault:   python3 tools/credentials.py sync --to-vault")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "audit"

    if cmd == "audit":
        audit()

    elif cmd == "get" and len(args) >= 2:
        try:
            value = get_key(args[1])
            print(value)
        except ValueError as e:
            print(f"❌ {e}", file=sys.stderr)
            sys.exit(1)

    elif cmd == "store" and len(args) >= 3:
        name, value = args[1], args[2]
        desc = " ".join(args[3:]) if len(args) > 3 else ""
        vault_flag = "--no-vault" not in args
        result = store_key(name, value, desc, keychain=True, vault=vault_flag)
        kc = "✅" if result["keychain"] else "❌"
        vt = "✅" if result["vault"] else ("⏭️ " if not vault_flag else "❌")
        print(f"  Keychain: {kc}  Vault: {vt}  →  {name}")

    elif cmd == "delete" and len(args) >= 2:
        result = delete_key(args[1])
        print(f"  Keychain: {'✅ deleted' if result['keychain'] else '❌ not found'}  →  {args[1]}")

    elif cmd == "list":
        names = keychain_list()
        if names:
            print(f"\n  {len(names)} credentials in Keychain:\n")
            for n in names:
                print(f"    • {n}")
        else:
            print("\n  No credentials in Keychain yet.")
        print()

    elif cmd == "sync":
        direction = args[1] if len(args) > 1 else "--from-vault"
        if direction == "--from-vault":
            print("\n  Syncing vault → keychain...")
            r = sync_from_vault()
            print(f"  Synced: {len(r['synced'])}  Skipped: {len(r['skipped'])}  Failed: {len(r['failed'])}")
            if r["synced"]:
                print(f"  New: {', '.join(r['synced'])}")
        elif direction == "--to-vault":
            print("\n  Syncing keychain → vault...")
            r = sync_to_vault()
            print(f"  Synced: {len(r['synced'])}  Skipped: {len(r['skipped'])}  Failed: {len(r['failed'])}")
            if r["synced"]:
                print(f"  Pushed: {', '.join(r['synced'])}")
        else:
            print("Usage: credentials.py sync [--from-vault|--to-vault]")

    elif cmd == "migrate-env":
        print("\n  Migrating env vars → keychain...")
        r = migrate_env()
        print(f"  Migrated: {len(r['migrated'])}  Already set: {len(r['already_set'])}  Not in env: {len(r['not_in_env'])}")
        if r["migrated"]:
            print(f"  New: {', '.join(r['migrated'])}")
        print()

    else:
        print("""credentials.py — Love credential management

Usage:
  get <name>              Read a credential (keychain → vault → env)
  store <name> <value>    Store to keychain + vault
  store <name> <val> --no-vault   Keychain only
  delete <name>           Remove from keychain
  list                    List all keychain entries
  audit                   Full audit: keychain vs vault vs env
  sync --from-vault       Pull vault → keychain
  sync --to-vault         Push keychain → vault
  migrate-env             Move env vars → keychain
""")


if __name__ == "__main__":
    main()
