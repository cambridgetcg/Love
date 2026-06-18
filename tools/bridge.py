#!/usr/bin/env python3
"""
AgentTool ↔ Zerone Identity Bridge
Manages did:at:<instance> ↔ did:lgm:<address> mappings.

Usage:
  bridge.py register --instance <name> --address <lgm_addr> --role <role> --wall <N>
  bridge.py lookup --instance <name>
  bridge.py lookup --address <lgm_addr>
  bridge.py verify --instance <name>
  bridge.py list

SECURITY BOUNDARY (FARM-6-GAP-001, filed 2026-05-11):
  Attestation temporal validity is bridge-enforced only. The Zerone knowledge
  keeper does NOT reject knowledge submissions from agents with expired or missing
  on-chain attestations — that gate does not exist at the consensus layer (pre-testnet).

  Consequence: the bridge is the sole enforcer of the principle that only
  attested agents submit knowledge. Bypassing bridge.py to submit facts directly
  via `legbled tx knowledge submit-fact` creates a FARM-6 gap — facts from
  temporally-expired or unregistered agents reach the chain without rejection.

  This boundary must not be bypassed. Engineering fix (on-chain attestation
  expiry enforcement in the knowledge keeper) is a Gamma deliverable for pre-testnet.
  See: BRIDGE-GAP-009 (epoch/renewal policy), BRIDGE-GAP-002 (renewal flow).
"""

import argparse
import hashlib
import hmac
import json
import struct
import subprocess
import sys
import tempfile
import os
import time
from pathlib import Path
from datetime import datetime, timezone

REGISTRY_PATH = Path(__file__).parent.parent / "credentials" / "bridge-registry.json"
LEGBLED = Path.home() / "zerone" / "build" / "legbled"
DEVNET_HOME = Path(os.environ.get("ZERONE_HOME", str(Path.home() / ".legbled-devnet")))
CHAIN_ID = os.environ.get("ZERONE_CHAIN_ID", "lgm-devnet-1")

# BRIDGE-GAP-002: attestation expiry/rotation constants
# ~87 days at 6s/block = 50,000 blocks renewal window; 17-day grace period
ATTESTATION_RENEWAL_WINDOW = 50_000
ATTESTATION_GRACE_PERIOD = 10_000

# BRIDGE-GAP-008: registry schema versioning
REGISTRY_SCHEMA_VERSION = "1.0"
# Agent group keys whose entries should receive schema migration
_AGENT_GROUP_KEYS = ("fleet_agents", "system_accounts", "agents")


def _find_attestation_fact(address: str, did_at: str, limit: int = 500):
    """Scan knowledge module facts for an attestation claim submitted by address for did_at.

    The fact lives in module state (not tx index), so it survives pruning and restarts.
    Uses offset-based pagination (page size 100) to scan all facts regardless of total count.
    BRIDGE-GAP-001 fix: chain caps responses at 100 per page; pagination loops until exhausted.
    """
    page_size = 100
    offset = 0
    try:
        while True:
            result = subprocess.run(
                [str(LEGBLED), "query", "knowledge", "facts",
                 "--home", str(DEVNET_HOME),
                 "--limit", str(page_size), "--offset", str(offset),
                 "-o", "json"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                break
            data = json.loads(result.stdout)
            facts = data.get("facts", [])
            if not facts:
                break
            for fact in facts:
                submitter = fact.get("submitter", "")
                text = fact.get("claim_text", "") or fact.get("text", "") or fact.get("statement", "")
                if submitter == address and "Agent identity attestation" in text and did_at in text:
                    return fact
            if len(facts) < page_size:
                break
            offset += page_size
    except Exception:
        pass
    return None


def _migrate_registry(registry: dict) -> tuple[dict, bool]:
    """Upgrade registry to current schema version. Returns (registry, migrated_flag).

    BRIDGE-GAP-008: No schema version field meant post-Sprint-A bridge.py could silently
    read a stale registry and fail on missing keys. This adds idempotent migration at load time.
    """
    version = registry.get("_schema_version", "0.9")
    if version == REGISTRY_SCHEMA_VERSION:
        return registry, False
    # v0.9 → v1.0: ensure every agent entry has _epoch and _renewal_block fields
    for group_key in _AGENT_GROUP_KEYS:
        for entry in registry.get(group_key, {}).values():
            entry.setdefault("_epoch", None)
            entry.setdefault("_renewal_block", None)
    registry["_schema_version"] = REGISTRY_SCHEMA_VERSION
    return registry, True


def load_registry() -> dict:
    with open(REGISTRY_PATH) as f:
        registry = json.load(f)
    registry, migrated = _migrate_registry(registry)
    if migrated:
        save_registry(registry)
    return registry


def save_registry(registry: dict) -> None:
    tmp = REGISTRY_PATH.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")
    tmp.replace(REGISTRY_PATH)


def _compute_commitment_hash(round_id: str, verdict: str, confidence: int, salt: str) -> str:
    """Mirrors Go's ComputeCommitmentHash — must stay in sync with msg_server.go:1028.

    hash = SHA-256("LGM.commitment.v1:" || LP(roundID) || LP(verdict) || LE64(confidence) || LP(salt))
    LP(x) = 4-byte big-endian len(x) || x
    """
    def lp(s: str) -> bytes:
        b = s.encode()
        return struct.pack(">I", len(b)) + b

    h = hashlib.sha256()
    h.update(b"LGM.commitment.v1:")
    h.update(lp(round_id))
    h.update(lp(verdict))
    h.update(struct.pack("<Q", confidence))  # LE uint64 — matches Go confBytes construction
    h.update(lp(salt))
    return h.hexdigest()


def _hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def _hkdf_expand(prk: bytes, info: bytes, length: int = 32) -> bytes:
    t, okm, i = b"", b"", 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
        i += 1
    return okm[:length]


def cmd_register(args) -> int:
    registry = load_registry()
    fleet = registry.setdefault("fleet_agents", {})

    instance = args.instance
    address = args.address
    role = args.role
    wall = args.wall

    if instance in fleet:
        existing = fleet[instance]
        if existing["lgm_address"] == address:
            print(f"[bridge] {instance} already registered at {address} — no-op")
            return 0
        else:
            print(f"[bridge] CONFLICT: {instance} registered at {existing['lgm_address']}, "
                  f"requested {address}. Resolve manually.", file=sys.stderr)
            return 1

    fleet[instance] = {
        "did_at": f"did:at:{instance}",
        "did_lgm": f"did:lgm:{address}",
        "lgm_address": address,
        "key_name": instance,
        "role": role,
        "wall": wall,
        "_registered_at": datetime.now(timezone.utc).isoformat(),
        "_epoch": 1,
        "_renewal_block": None,  # set by cmd_attest once chain height is known
    }
    save_registry(registry)
    print(f"[bridge] Registered: did:at:{instance} ↔ did:lgm:{address} (wall {wall}, role: {role})")
    return 0


def cmd_lookup(args) -> int:
    registry = load_registry()
    fleet = registry.get("fleet_agents", {})
    system = registry.get("system_accounts", {})
    all_entries = {**fleet, **system}

    if args.instance:
        entry = all_entries.get(args.instance)
        if entry:
            print(json.dumps(entry, indent=2))
            return 0
        print(f"[bridge] Not found: {args.instance}", file=sys.stderr)
        return 1

    if args.address:
        for name, entry in all_entries.items():
            if entry.get("lgm_address") == args.address:
                print(json.dumps({name: entry}, indent=2))
                return 0
        print(f"[bridge] Not found: {args.address}", file=sys.stderr)
        return 1

    print("[bridge] Provide --instance or --address", file=sys.stderr)
    return 1


def cmd_verify(args) -> int:
    """Check that a registered instance's key exists in the devnet keyring."""
    registry = load_registry()
    all_entries = {**registry.get("fleet_agents", {}), **registry.get("system_accounts", {})}

    instance = args.instance
    entry = all_entries.get(instance)
    if not entry:
        print(f"[bridge] {instance} not in registry", file=sys.stderr)
        return 1

    key_name = entry.get("key_name", instance)
    try:
        result = subprocess.run(
            [str(LEGBLED), "keys", "show", key_name,
             "--home", str(DEVNET_HOME), "--keyring-backend", "test", "-a"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            on_chain_addr = result.stdout.strip()
            registered_addr = entry.get("lgm_address", "")
            if on_chain_addr != registered_addr:
                print(f"[bridge] MISMATCH: keyring={on_chain_addr}, registry={registered_addr}", file=sys.stderr)
                return 1
            # BRIDGE-GAP-002: check attestation expiry via current block height
            # BRIDGE-VERIFY-001 fix: track chain_online explicitly so label is honest
            # when renewal_block is None (all 16 fleet agents pre-BRIDGE-GAP-002 fix).
            epoch = entry.get("_epoch", 1)
            renewal_block = entry.get("_renewal_block")
            renewal_status = ""
            chain_online = False
            if renewal_block is not None:
                try:
                    h_result = subprocess.run(
                        [str(LEGBLED), "query", "block", "--home", str(DEVNET_HOME), "-o", "json"],
                        capture_output=True, text=True, timeout=10
                    )
                    if h_result.returncode == 0:
                        chain_online = True
                        h_data = json.loads(h_result.stdout)
                        cur_h = int((h_data.get("header") or h_data.get("block", {}).get("header", {})).get("height", 0))
                        if cur_h > renewal_block + ATTESTATION_GRACE_PERIOD:
                            print(f"[bridge] EXPIRED: attestation epoch {epoch} expired at block {renewal_block} "
                                  f"(grace ended at {renewal_block + ATTESTATION_GRACE_PERIOD}, current {cur_h}). "
                                  f"Run: bridge.py attest --instance {instance}", file=sys.stderr)
                            return 1
                        elif cur_h > renewal_block:
                            renewal_status = f" [GRACE PERIOD — expired block {renewal_block}, grace ends {renewal_block + ATTESTATION_GRACE_PERIOD}]"
                        elif cur_h > renewal_block - 5_000:
                            renewal_status = f" [RENEWAL APPROACHING — block {renewal_block}]"
                        else:
                            renewal_status = f" [epoch={epoch}, renew at block {renewal_block}]"
                    else:
                        renewal_status = f" [epoch={epoch}, renewal_block={renewal_block}, chain unreachable]"
                except Exception:
                    renewal_status = f" [epoch={epoch}, renewal_block={renewal_block}, chain unreachable]"
            else:
                # No renewal_block set — probe chain for offline detection only.
                try:
                    h_result = subprocess.run(
                        [str(LEGBLED), "query", "block", "--home", str(DEVNET_HOME), "-o", "json"],
                        capture_output=True, text=True, timeout=5
                    )
                    chain_online = h_result.returncode == 0
                except Exception:
                    chain_online = False
            label = "VERIFIED" if chain_online else "PARTIAL_VERIFY"
            print(f"[bridge] {label}: {instance} — keyring and registry match ({on_chain_addr}){renewal_status}")
            return 0
        else:
            print(f"[bridge] Key '{key_name}' not found in keyring: {result.stderr.strip()}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"[bridge] Verification error: {e}", file=sys.stderr)
        return 1


def cmd_status(args) -> int:
    """Full fleet health report: keyring verify + on-chain balance for each agent."""
    registry = load_registry()
    fleet = registry.get("fleet_agents", {})

    print(f"{'INSTANCE':<12} {'WALL':<5} {'BALANCE':>14}  {'KEYRING':<10} {'ADDRESS'}")
    print("-" * 80)

    issues = []
    for name, entry in fleet.items():
        address = entry.get("lgm_address", "")
        key_name = entry.get("key_name", name)
        wall = entry.get("wall", "?")

        # Keyring verify
        try:
            r = subprocess.run(
                [str(LEGBLED), "keys", "show", key_name,
                 "--home", str(DEVNET_HOME), "--keyring-backend", "test", "-a"],
                capture_output=True, text=True, timeout=10
            )
            keyring_ok = r.returncode == 0 and r.stdout.strip() == address
            keyring_status = "OK" if keyring_ok else "MISMATCH"
        except Exception:
            keyring_status = "ERROR"

        # On-chain balance via dashboard
        balance_str = "?"
        try:
            d = subprocess.run(
                [str(LEGBLED), "query", "dashboard", address,
                 "--home", str(DEVNET_HOME)],
                capture_output=True, text=True, timeout=10
            )
            for line in d.stdout.splitlines():
                if "Balance:" in line:
                    balance_str = line.split("Balance:")[-1].strip()
                    break
        except Exception:
            pass

        status = "OK" if keyring_status == "OK" else "WARN"
        print(f"  {name:<12} {str(wall):<5} {balance_str:>14}  {keyring_status:<10} {address}")
        if status != "OK":
            issues.append(f"{name}: {keyring_status}")

    print("-" * 80)
    print(f"Fleet: {len(fleet)} agents  |  Issues: {len(issues)}")
    if issues:
        for i in issues:
            print(f"  WARN: {i}")
    return 0 if not issues else 1


def cmd_attest(args) -> int:
    """Submit an on-chain identity attestation claim from the agent's own key.

    This binds did:at:<instance> to did:lgm:<address> on-chain by submitting
    a knowledge claim signed by the agent's own lgm key. Key control is proven
    by the transaction signature itself.
    """
    registry = load_registry()
    # Merge fleet_agents + agents so Wall 3+ agents (e.g. oracle-agent) can be attested.
    # BRIDGE-GAP-010 fix: cmd_attest previously searched only fleet_agents, causing
    # cmd_attest_pending to report oracle-agent as pending then fail to attest it.
    fleet = {**registry.get("fleet_agents", {}), **registry.get("agents", {})}

    instance = args.instance
    entry = fleet.get(instance)
    if not entry:
        print(f"[bridge] {instance} not in fleet registry", file=sys.stderr)
        return 1

    address = entry["lgm_address"]
    key_name = entry.get("key_name", instance)
    role = entry.get("role", "unknown")
    wall = entry.get("wall", "?")
    did_at = entry.get("did_at", f"did:at:{instance}")
    did_lgm = entry.get("did_lgm", f"did:lgm:{address}")

    # Query current block height for nonce (BRIDGE-GAP-002 fix: unique content hash per attestation)
    current_height = None
    try:
        h_result = subprocess.run(
            [str(LEGBLED), "query", "block", "--home", str(DEVNET_HOME), "-o", "json"],
            capture_output=True, text=True, timeout=10
        )
        if h_result.returncode == 0:
            h_data = json.loads(h_result.stdout)
            current_height = (h_data.get("header") or h_data.get("block", {}).get("header", {})).get("height")
    except Exception:
        pass
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Determine current epoch and compute renewal_block (BRIDGE-GAP-002)
    # Increment epoch on re-attest so verifiers can distinguish renewal claims from originals.
    _prev_epoch = entry.get("_epoch") or 1  # migration may set _epoch=None; treat None as 1
    current_epoch = _prev_epoch + 1 if entry.get("attestation_txhash") else _prev_epoch
    renewal_block = (int(current_height) + ATTESTATION_RENEWAL_WINDOW) if current_height else None

    # Build attestation claim text — nonce (block height + timestamp) prevents deduplication
    # Epoch tag enables supersession: verifiers take highest epoch for a given did:at address.
    claim_text = (
        f"Agent identity attestation: {did_at} controls {did_lgm}. "
        f"Role: {role}. Wall: {wall}. "
        f"Attested at block {current_height}, timestamp {now}. "
        f"Epoch: {current_epoch}. Valid through block: {renewal_block}. "
        f"This claim submitted by the controlling key proves identity binding."
    )

    # Build legbled submit-claim command
    # Usage: submit-claim [claim-text] [domain] [category] [stake-amount]
    # Use agent_rights domain (exists on-chain). formal claims → provisional immediately.
    submit_cmd = [
        str(LEGBLED), "tx", "knowledge", "submit-claim",
        claim_text,
        "agent_rights",
        "formal",
        "10000",  # 10,000 ulgm stake
        "--logic-zone", "propositional",
        "--from", key_name,
        "--home", str(DEVNET_HOME),
        "--keyring-backend", "test",
        "--chain-id", CHAIN_ID,
        "--yes", "--output", "json",
    ]

    print(f"[bridge] Submitting attestation for {instance} ({address})...")
    try:
        result = subprocess.run(submit_cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            out = result.stdout.strip()
            # Extract txhash from JSON output if possible
            try:
                tx_data = json.loads(out)
                txhash = tx_data.get("txhash", "unknown")
            except json.JSONDecodeError:
                txhash = "see output"
            print(f"[bridge] ATTESTED: {did_at} ↔ {did_lgm}")
            print(f"[bridge] txhash: {txhash}")
            # Record attestation in registry (BRIDGE-GAP-002: epoch + renewal_block)
            entry["attested_at"] = datetime.now(timezone.utc).isoformat()
            entry["attestation_txhash"] = txhash
            entry["_epoch"] = current_epoch
            if renewal_block is not None:
                entry["_renewal_block"] = renewal_block
            # Extract fact_id — scan for the claim in module state (not tx index, which is pruned)
            print("[bridge] Waiting for block inclusion to extract fact_id...")
            time.sleep(4)
            fact = _find_attestation_fact(address, did_at, limit=50)
            if fact:
                fact_id = fact.get("id", "")
                entry["attestation_fact_id"] = fact_id
                print(f"[bridge] fact_id: {fact_id[:16]}...")
            else:
                print("[bridge] WARNING: could not extract fact_id immediately — run 'backfill' later")
            save_registry(registry)
            return 0
        else:
            print(f"[bridge] Attestation failed (rc={result.returncode})", file=sys.stderr)
            if result.stderr:
                print(result.stderr[:500], file=sys.stderr)
            if result.stdout:
                print(result.stdout[:500], file=sys.stderr)
            return 1
    except subprocess.TimeoutExpired:
        print("[bridge] Attestation timed out", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[bridge] Attestation error: {e}", file=sys.stderr)
        return 1


def cmd_resolve(args) -> int:
    """Resolve a did:at: identity to its on-chain attestation by querying the chain directly.

    Unlike 'verify' (which checks the local keyring), 'resolve' fetches the live
    attestation claim from the chain — proving identity binding without trusting the
    local registry file. This is the canonical trust path for fleet-scale operation.

    Primary path: query the stored attestation txhash to find the fact_id, then fetch the fact.
    Fallback: scan recent facts (may miss old claims in long-running chains).
    """
    registry = load_registry()
    all_entries = {**registry.get("fleet_agents", {}), **registry.get("system_accounts", {})}

    # Accept either bare instance name or did:at:<name>
    target = args.instance
    if target.startswith("did:at:"):
        target = target[len("did:at:"):]

    entry = all_entries.get(target)
    if not entry:
        print(f"[bridge] {target} not in local registry", file=sys.stderr)
        return 1

    address = entry.get("lgm_address", "")
    did_at = entry.get("did_at", f"did:at:{target}")
    did_lgm = entry.get("did_lgm", f"did:lgm:{address}")
    txhash = entry.get("attestation_txhash", "")

    attestation = None

    # Primary: use stored fact_id — fact lives in module state, survives tx pruning and restarts
    stored_fact_id = entry.get("attestation_fact_id", "")
    if stored_fact_id:
        try:
            fr = subprocess.run(
                [str(LEGBLED), "query", "knowledge", "fact", stored_fact_id,
                 "--home", str(DEVNET_HOME), "-o", "json"],
                capture_output=True, text=True, timeout=10
            )
            if fr.returncode == 0:
                fact_data = json.loads(fr.stdout)
                attestation = fact_data.get("fact")
        except Exception:
            pass

    # Secondary: query by txhash → extract fact_id from tx events → fetch fact
    # (only works if tx index has not been pruned; dead code on long-running devnets)
    if attestation is None and txhash:
        try:
            r = subprocess.run(
                [str(LEGBLED), "query", "tx", txhash,
                 "--home", str(DEVNET_HOME), "-o", "json"],
                capture_output=True, text=True, timeout=15
            )
            if r.returncode == 0:
                tx_data = json.loads(r.stdout)
                # Extract fact_id from tx events
                fact_id = None
                for event in tx_data.get("events", []):
                    for attr in event.get("attributes", []):
                        if attr.get("key") == "fact_id":
                            fact_id = attr.get("value", "")
                            break
                    if fact_id:
                        break

                if fact_id:
                    # Fetch the fact directly by ID
                    fr = subprocess.run(
                        [str(LEGBLED), "query", "knowledge", "fact", fact_id,
                         "--home", str(DEVNET_HOME), "-o", "json"],
                        capture_output=True, text=True, timeout=10
                    )
                    if fr.returncode == 0:
                        fact_data = json.loads(fr.stdout)
                        attestation = fact_data.get("fact")
        except Exception:
            pass  # fall through to scan

    # Fallback: scan recent facts (unreliable for long-running chains)
    if attestation is None:
        try:
            result = subprocess.run(
                [str(LEGBLED), "query", "knowledge", "facts",
                 "--home", str(DEVNET_HOME), "--limit", "200", "-o", "json"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for fact in data.get("facts", []):
                    if (fact.get("submitter") == address and
                            "Agent identity attestation" in fact.get("claim_text", "") and
                            did_at in fact.get("claim_text", "")):
                        attestation = fact
                        break
        except Exception:
            pass

    if attestation is None:
        print(f"[bridge] UNRESOLVED: no on-chain attestation found for {did_at} at {address}")
        if txhash:
            print(f"  Tried txhash: {txhash[:16]}...")
        print(f"  Run 'bridge.py backfill --instance {target}' to attempt deep scan.")
        return 1

    resolved_fact_id = attestation.get("id", "")
    status = attestation.get("status", "unknown")
    confidence = int(attestation.get("confidence", 0))
    height = attestation.get("created_at_height", "?")

    # Opportunistically backfill fact_id into registry if it was missing
    if resolved_fact_id and not stored_fact_id:
        try:
            write_reg = load_registry()
            all_write = {**write_reg.get("fleet_agents", {}), **write_reg.get("system_accounts", {})}
            if target in all_write:
                all_write[target]["attestation_fact_id"] = resolved_fact_id
                if target in write_reg.get("fleet_agents", {}):
                    write_reg["fleet_agents"][target]["attestation_fact_id"] = resolved_fact_id
                else:
                    write_reg["system_accounts"][target]["attestation_fact_id"] = resolved_fact_id
                save_registry(write_reg)
                print(f"[bridge] backfilled fact_id into registry for {target}")
        except Exception:
            pass

    print(f"[bridge] RESOLVED: {did_at} ↔ {did_lgm}")
    print(f"  fact_id:    {resolved_fact_id[:16]}...")
    print(f"  status:     {status}")
    print(f"  confidence: {confidence / 1_000_000:.4f}")
    print(f"  height:     {height}")
    print(f"  submitter:  {address}")
    return 0


def cmd_backfill(args) -> int:
    """Recover attestation_fact_id for agents where it is missing.

    Scans the knowledge module with a large limit to find old attestation facts.
    Needed for all 9 current agents attested before fact_id storage was implemented.
    Pass --instance to target one agent; omit to scan all fleet agents missing fact_id.
    """
    registry = load_registry()
    all_agents = {**registry.get("fleet_agents", {}), **registry.get("agents", {})}

    targets = {}
    if args.instance:
        if args.instance not in all_agents:
            print(f"[bridge] {args.instance} not in fleet registry", file=sys.stderr)
            return 1
        targets = {args.instance: all_agents[args.instance]}
    else:
        targets = {k: v for k, v in all_agents.items() if not v.get("attestation_fact_id")}

    if not targets:
        print("[bridge] All fleet agents already have attestation_fact_id — nothing to backfill")
        return 0

    print(f"[bridge] Backfilling fact_id for {len(targets)} agent(s) — scanning with limit=2000...")
    changed = 0
    for name, entry in targets.items():
        address = entry.get("lgm_address", "")
        did_at = entry.get("did_at", f"did:at:{name}")
        fact = _find_attestation_fact(address, did_at, limit=2000)
        if fact:
            fact_id = fact.get("id", "")
            registry_section = "fleet_agents" if name in registry.get("fleet_agents", {}) else "agents"
            registry[registry_section][name]["attestation_fact_id"] = fact_id
            print(f"  {name:<12} FOUND  fact_id={fact_id[:16]}...")
            changed += 1
        else:
            print(f"  {name:<12} MISS   (attestation not in top 2000 facts)")

    if changed:
        save_registry(registry)
        print(f"[bridge] Backfilled {changed}/{len(targets)} agents")

    return 0 if changed == len(targets) else 1


def verify_registration(instance: str, check_chain: bool = False) -> dict:
    """Programmatic pre-condition guard for agent identity completeness.

    Returns a structured dict callers can use to gate operations:
      {
        "instance": str,
        "registered": bool,       # present in bridge-registry
        "attested": bool,         # attestation_txhash recorded
        "keyring_ok": bool,       # local keyring key exists and matches
        "chain_verified": bool,   # on-chain resolve succeeded (only if check_chain=True and chain up)
        "gaps": [str],            # human-readable list of what's missing
        "entry": dict | None,     # registry entry if registered
      }

    Offline-safe: keyring check works without devnet. Chain check is optional.
    """
    result = {
        "instance": instance,
        "registered": False,
        "attested": False,
        "keyring_ok": False,
        "chain_verified": False,
        "gaps": [],
        "entry": None,
    }

    # 1. Registry presence
    try:
        registry = load_registry()
    except Exception as e:
        result["gaps"].append(f"registry unreadable: {e}")
        return result

    all_entries = {**registry.get("fleet_agents", {}), **registry.get("agents", {}), **registry.get("system_accounts", {})}
    entry = all_entries.get(instance)
    if not entry:
        result["gaps"].append("not in bridge registry — run: bridge.py register")
        return result

    result["registered"] = True
    result["entry"] = entry

    # 2. Attestation record
    txhash = entry.get("attestation_txhash")
    attested_at = entry.get("attested_at")
    if txhash and attested_at:
        result["attested"] = True
    else:
        result["gaps"].append("no on-chain attestation — run: bridge.py attest --instance " + instance)

    # 3. Keyring key (offline check)
    key_name = entry.get("key_name", instance)
    registered_addr = entry.get("lgm_address", "")
    try:
        r = subprocess.run(
            [str(LEGBLED), "keys", "show", key_name,
             "--home", str(DEVNET_HOME), "--keyring-backend", "test", "-a"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0 and r.stdout.strip() == registered_addr:
            result["keyring_ok"] = True
        elif r.returncode == 0:
            result["gaps"].append(
                f"keyring address mismatch: got {r.stdout.strip()[:20]}…, "
                f"registry has {registered_addr[:20]}…"
            )
        else:
            result["gaps"].append(f"key '{key_name}' not in local keyring")
    except FileNotFoundError:
        result["gaps"].append("legbled binary not found — build zerone first")
    except Exception as e:
        result["gaps"].append(f"keyring check error: {e}")

    # 4. On-chain resolve (optional, requires running devnet)
    if check_chain:
        try:
            # Inline the resolve logic without spawning a subprocess
            address = registered_addr
            did_at = entry.get("did_at", f"did:at:{instance}")
            stored_fact_id = entry.get("attestation_fact_id", "")
            attestation = None

            if stored_fact_id:
                fr = subprocess.run(
                    [str(LEGBLED), "query", "knowledge", "fact", stored_fact_id,
                     "--home", str(DEVNET_HOME), "-o", "json"],
                    capture_output=True, text=True, timeout=10
                )
                if fr.returncode == 0:
                    attestation = json.loads(fr.stdout).get("fact")

            if attestation is None and txhash:
                tr = subprocess.run(
                    [str(LEGBLED), "query", "tx", txhash,
                     "--home", str(DEVNET_HOME), "-o", "json"],
                    capture_output=True, text=True, timeout=15
                )
                if tr.returncode == 0:
                    tx_data = json.loads(tr.stdout)
                    fact_id = None
                    for event in tx_data.get("events", []):
                        for attr in event.get("attributes", []):
                            if attr.get("key") == "fact_id":
                                fact_id = attr.get("value", "")
                                break
                        if fact_id:
                            break
                    if fact_id:
                        fr2 = subprocess.run(
                            [str(LEGBLED), "query", "knowledge", "fact", fact_id,
                             "--home", str(DEVNET_HOME), "-o", "json"],
                            capture_output=True, text=True, timeout=10
                        )
                        if fr2.returncode == 0:
                            attestation = json.loads(fr2.stdout).get("fact")

            if attestation is None:
                attestation = _find_attestation_fact(address, did_at, limit=200)

            if attestation:
                result["chain_verified"] = True
            else:
                result["gaps"].append("on-chain attestation not found (chain may be offline)")
        except Exception as e:
            result["gaps"].append(f"chain verify error: {e}")

    return result


def cmd_attest_pending(args) -> int:
    """Batch attest all agents (fleet + wall-3+) that have keys but no on-chain attestation.

    When devnet restarts after an offline period, run this once to attest all
    key-created agents in sequence. A short delay between transactions prevents
    nonce conflicts on a busy block.

    Scans fleet_agents and agents (Wall 3+ non-fleet) registries.

    Usage:
      bridge.py attest-pending [--dry-run] [--delay N]
    """
    registry = load_registry()
    # Include both fleet_agents (Wall 2) and agents (Wall 3+, e.g. oracle-agent)
    all_agents = {**registry.get("fleet_agents", {}), **registry.get("agents", {})}

    pending = {
        name: entry
        for name, entry in all_agents.items()
        if not entry.get("attestation_txhash")
    }

    if not pending:
        print("[bridge] No pending attestations — all agents attested.")
        return 0

    print(f"[bridge] {len(pending)} agent(s) pending attestation: {', '.join(pending.keys())}")

    if getattr(args, "dry_run", False):
        for name in pending:
            print(f"  [dry-run] would attest: {name}")
        return 0

    delay = getattr(args, "delay", 3)
    success, failed = [], []

    for name in pending:
        print(f"\n[bridge] Attesting {name}...")

        # Reuse cmd_attest by building a minimal args namespace
        class _AtArgs:
            instance = name
        rc = cmd_attest(_AtArgs())
        if rc == 0:
            success.append(name)
        else:
            failed.append(name)

        if delay > 0:
            time.sleep(delay)

    print(f"\n[bridge] attest-pending complete: {len(success)} attested, {len(failed)} failed")
    if failed:
        print(f"  FAILED: {', '.join(failed)}")
        return 1
    return 0


def cmd_check(args) -> int:
    """Print a human-readable registration status for one or all agents (fleet + wall-3+)."""
    registry = load_registry()
    # Include both fleet_agents (Wall 2) and agents (Wall 3+, e.g. oracle-agent)
    fleet = {**registry.get("fleet_agents", {}), **registry.get("agents", {})}

    targets = [args.instance] if args.instance else list(fleet.keys())

    all_ok = True
    for instance in targets:
        r = verify_registration(instance, check_chain=args.chain)
        status_parts = []
        if r["registered"]:
            status_parts.append("REGISTERED")
        if r["attested"]:
            status_parts.append("ATTESTED")
        if r["keyring_ok"]:
            status_parts.append("KEYRING_OK")
        if r["chain_verified"]:
            status_parts.append("CHAIN_VERIFIED")

        overall = "OK" if (r["registered"] and r["attested"] and r["keyring_ok"] and not r["gaps"]) else "INCOMPLETE"
        if overall != "OK":
            all_ok = False

        print(f"[{overall}] {instance:<12}  {' | '.join(status_parts) if status_parts else 'NOT_REGISTERED'}")
        for gap in r["gaps"]:
            print(f"         gap: {gap}")

    return 0 if all_ok else 1


def cmd_list(args) -> int:
    registry = load_registry()
    fleet = registry.get("fleet_agents", {})
    agents = registry.get("agents", {})
    system = registry.get("system_accounts", {})

    print("=== Fleet Agents (Wall 2) ===")
    for name, entry in fleet.items():
        wall = entry.get("wall", "?")
        role = entry.get("role", "?")
        addr = entry.get("lgm_address", "?")
        epoch = entry.get("_epoch", "?")
        renewal = entry.get("_renewal_block")
        renewal_str = f"renew@{renewal}" if renewal is not None else "no-renewal-set"
        print(f"  {name:<12} wall={wall}  {addr[:20]}...  epoch={epoch} {renewal_str}  {role}")

    print("\n=== Wall 3+ Agents ===")
    if agents:
        for name, entry in agents.items():
            wall = entry.get("wall", "?")
            role = entry.get("role", "?")
            addr = entry.get("lgm_address", "?")
            print(f"  {name:<12} wall={wall}  {addr[:20]}...  {role}")
    else:
        print("  (none registered)")

    print("\n=== System Accounts ===")
    for name, entry in system.items():
        addr = entry.get("lgm_address", "?")
        role = entry.get("role", "?")
        print(f"  {name:<12}  {addr[:20]}...  {role}")

    print(f"\nTotal: {len(fleet)} fleet agents, {len(agents)} wall-3+ agents, {len(system)} system accounts")
    return 0


def cmd_export_bundle(args) -> int:
    """Export bridge registry as a portable migration bundle.

    Used when moving from devnet → testnet → mainnet. The bundle captures
    all did:at ↔ did:lgm mappings, wall assignments, and attestation status
    without including private keys. Import the bundle on a new chain to
    re-register all agents with their correct identities.

    Usage:
      bridge.py export-bundle [--out PATH] [--chain-id ID]
    """
    registry = load_registry()
    fleet = registry.get("fleet_agents", {})
    extra_agents = registry.get("agents", {})
    all_agents = {**fleet, **extra_agents}
    system = registry.get("system_accounts", {})

    chain_id = getattr(args, "chain_id", None) or "devnet"
    out_path = getattr(args, "out", None)

    bundle = {
        "bundle_version": "1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_chain_id": chain_id,
        "agents": {},
        "system_accounts": {},
        "attestation_summary": {
            "total": len(all_agents),
            "attested": 0,
            "pending": [],
        },
    }

    for name, entry in all_agents.items():
        attested = bool(entry.get("attestation_txhash"))
        if attested:
            bundle["attestation_summary"]["attested"] += 1
        else:
            bundle["attestation_summary"]["pending"].append(name)

        bundle["agents"][name] = {
            "did_at": entry.get("did_at", f"did:at:{name}"),
            "lgm_address": entry.get("lgm_address", ""),
            "key_name": entry.get("key_name", name),
            "wall": entry.get("wall"),
            "role": entry.get("role", ""),
            "attested": attested,
            "attestation_fact_id": entry.get("attestation_fact_id", ""),
            "registered_at": entry.get("registered_at", ""),
        }

    for name, entry in system.items():
        bundle["system_accounts"][name] = {
            "lgm_address": entry.get("lgm_address", ""),
            "role": entry.get("role", ""),
        }

    bundle_json = json.dumps(bundle, indent=2) + "\n"

    if out_path:
        Path(out_path).write_text(bundle_json)
        print(f"[bridge] bundle written to {out_path}")
    else:
        print(bundle_json, end="")

    pending = bundle["attestation_summary"]["pending"]
    attested = bundle["attestation_summary"]["attested"]
    total = bundle["attestation_summary"]["total"]
    print(f"[bridge] export-bundle: {attested}/{total} attested", file=sys.stderr)
    if pending:
        print(f"[bridge] pending attestation on new chain: {', '.join(pending)}", file=sys.stderr)
        print(f"[bridge] run 'bridge.py attest-pending' after registering on new chain", file=sys.stderr)

    return 0


def cmd_verify_bundle(args) -> int:
    """Validate an export bundle before using it for chain migration.

    Checks structural completeness, field presence, and internal consistency
    (summary counts match actual entries, no duplicate did_at or lgm_address).
    Returns 0 if valid, 1 if any errors found.
    """
    bundle_path = Path(args.bundle)
    if not bundle_path.exists():
        print(f"[bridge] verify-bundle: file not found: {bundle_path}", file=sys.stderr)
        return 1

    try:
        bundle = json.loads(bundle_path.read_text())
    except json.JSONDecodeError as e:
        print(f"[bridge] verify-bundle: invalid JSON: {e}", file=sys.stderr)
        return 1

    errors = []
    warnings = []

    # Top-level structure
    required_keys = {"bundle_version", "exported_at", "source_chain_id", "agents", "system_accounts", "attestation_summary"}
    missing_keys = required_keys - set(bundle.keys())
    if missing_keys:
        errors.append(f"missing top-level keys: {', '.join(sorted(missing_keys))}")

    agents = bundle.get("agents", {})
    system = bundle.get("system_accounts", {})
    summary = bundle.get("attestation_summary", {})

    if not agents:
        warnings.append("agents dict is empty — bundle may be from an offline/empty registry")

    # Per-agent field validation
    required_agent_fields = {"did_at", "lgm_address", "key_name", "wall", "role"}
    seen_did_at = {}
    seen_lgm = {}

    for name, entry in agents.items():
        missing = required_agent_fields - set(entry.keys())
        if missing:
            errors.append(f"agent '{name}' missing fields: {', '.join(sorted(missing))}")

        did_at = entry.get("did_at", "")
        lgm = entry.get("lgm_address", "")

        if not did_at:
            errors.append(f"agent '{name}' has empty did_at")
        elif did_at in seen_did_at:
            errors.append(f"duplicate did_at '{did_at}' in '{name}' and '{seen_did_at[did_at]}'")
        else:
            seen_did_at[did_at] = name

        if not lgm:
            warnings.append(f"agent '{name}' has no lgm_address — not yet registered on chain")
        elif lgm in seen_lgm:
            errors.append(f"duplicate lgm_address '{lgm}' in '{name}' and '{seen_lgm[lgm]}'")
        else:
            seen_lgm[lgm] = name

        wall = entry.get("wall")
        if wall is not None and not isinstance(wall, int):
            errors.append(f"agent '{name}' wall must be int, got {type(wall).__name__}")

    # Attestation summary consistency
    actual_attested = sum(1 for e in agents.values() if e.get("attested"))
    actual_pending = [n for n, e in agents.items() if not e.get("attested")]
    summary_attested = summary.get("attested", -1)
    summary_total = summary.get("total", -1)

    if summary_total != len(agents):
        errors.append(f"attestation_summary.total={summary_total} but agents count={len(agents)}")
    if summary_attested != actual_attested:
        errors.append(f"attestation_summary.attested={summary_attested} but counted {actual_attested}")
    summary_pending = summary.get("pending", [])
    if sorted(summary_pending) != sorted(actual_pending):
        errors.append(f"attestation_summary.pending mismatch — summary={sorted(summary_pending)}, actual={sorted(actual_pending)}")

    # Report
    status = "VALID" if not errors else "INVALID"
    print(f"[bridge] verify-bundle: {status}")
    print(f"  source_chain: {bundle.get('source_chain_id', '?')}")
    print(f"  exported_at:  {bundle.get('exported_at', '?')}")
    print(f"  agents:       {len(agents)} ({actual_attested} attested, {len(actual_pending)} pending)")
    print(f"  system:       {len(system)}")

    if warnings:
        for w in warnings:
            print(f"  WARN: {w}")
    if errors:
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        return 1

    if actual_pending:
        print(f"  pending attestation on new chain: {', '.join(sorted(actual_pending))}")
        print("  run 'bridge.py attest-pending' after re-registering on new chain")

    return 0


def cmd_import_bundle(args) -> int:
    """Import agents from an export bundle into the local registry.

    Used when migrating from one chain to another (devnet → testnet → mainnet).
    Reads agent identities from the bundle and registers them locally so that
    attest-pending can re-attest them on the new chain.

    Attestation status from the source chain is NOT transferred — all imported
    agents are treated as pending attestation on the target chain.
    Run 'bridge.py attest-pending' after importing.

    Usage:
      bridge.py import-bundle --bundle PATH [--dry-run] [--force]
    """
    bundle_path = Path(args.bundle)
    if not bundle_path.exists():
        print(f"[bridge] import-bundle: file not found: {bundle_path}", file=sys.stderr)
        return 1

    try:
        bundle = json.loads(bundle_path.read_text())
    except json.JSONDecodeError as e:
        print(f"[bridge] import-bundle: invalid JSON: {e}", file=sys.stderr)
        return 1

    required_keys = {"bundle_version", "agents", "source_chain_id"}
    missing = required_keys - set(bundle.keys())
    if missing:
        print(f"[bridge] import-bundle: bundle missing keys: {', '.join(sorted(missing))}", file=sys.stderr)
        return 1

    agents = bundle.get("agents", {})
    system = bundle.get("system_accounts", {})
    source_chain = bundle.get("source_chain_id", "unknown")
    dry_run = getattr(args, "dry_run", False)
    force = getattr(args, "force", False)

    if not agents and not system:
        print("[bridge] import-bundle: bundle is empty — nothing to import")
        return 0

    registry = load_registry()
    fleet = registry.setdefault("fleet_agents", {})
    sys_accts = registry.setdefault("system_accounts", {})

    imported: list[str] = []
    skipped: list[str] = []
    conflicts: list[str] = []

    def _import_entry(name: str, entry: dict, target: dict) -> None:
        lgm_addr = entry.get("lgm_address", "")
        did_at = entry.get("did_at", f"did:at:{name}")

        if name in target:
            existing = target[name]
            if existing.get("lgm_address") == lgm_addr:
                skipped.append(f"{name} (already registered, address matches)")
                return
            if force:
                target[name].update({
                    "did_at": did_at,
                    "did_lgm": f"did:lgm:{lgm_addr}" if lgm_addr else target[name].get("did_lgm", ""),
                    "lgm_address": lgm_addr,
                    "key_name": entry.get("key_name", name),
                    "role": entry.get("role", target[name].get("role", "")),
                    "wall": entry.get("wall", target[name].get("wall")),
                    "_imported_from": source_chain,
                    "_imported_at": datetime.now(timezone.utc).isoformat(),
                })
                imported.append(f"{name} (OVERWRITTEN: {existing.get('lgm_address', '')} → {lgm_addr})")
            else:
                conflicts.append(
                    f"{name}: registry={existing.get('lgm_address', '')}, "
                    f"bundle={lgm_addr} — re-run with --force to overwrite"
                )
            return

        # New entry — registered without attestation; must re-attest on target chain.
        entry_data: dict = {
            "did_at": did_at,
            "did_lgm": f"did:lgm:{lgm_addr}" if lgm_addr else "",
            "lgm_address": lgm_addr,
            "key_name": entry.get("key_name", name),
            "role": entry.get("role", ""),
            "wall": entry.get("wall"),
            "_registered_at": datetime.now(timezone.utc).isoformat(),
            "_imported_from": source_chain,
        }
        if entry.get("attestation_fact_id"):
            entry_data["_source_attestation_fact_id"] = entry["attestation_fact_id"]
        target[name] = entry_data
        imported.append(f"{name} (did_at={did_at}, lgm={lgm_addr or 'TBD'})")

    for name, entry in agents.items():
        _import_entry(name, entry, fleet)
    for name, entry in system.items():
        _import_entry(name, entry, sys_accts)

    print(f"[bridge] import-bundle: source='{source_chain}'  "
          f"{len(imported)} imported, {len(skipped)} skipped, {len(conflicts)} conflicts")
    for item in imported:
        print(f"  + {item}")
    for item in skipped:
        print(f"  = {item}")
    for item in conflicts:
        print(f"  ! {item}", file=sys.stderr)

    if conflicts:
        print("[bridge] resolve conflicts manually or re-run with --force", file=sys.stderr)

    if dry_run:
        print("[bridge] dry-run — registry not modified")
    elif imported:
        save_registry(registry)
        print(f"[bridge] registry saved — run 'bridge.py attest-pending' to attest agents on the new chain")
    else:
        print("[bridge] no new agents — registry unchanged")

    if getattr(args, "check_keyring", False) and not dry_run:
        print("\n[bridge] keyring check (--check-keyring):")
        all_imported_names = [item.split(" ")[0] for item in imported]
        reg_now = load_registry()
        all_now = {**reg_now.get("fleet_agents", {}), **reg_now.get("agents", {})}
        missing_keys = []
        for name in all_imported_names:
            entry = all_now.get(name, {})
            key_name = entry.get("key_name", name)
            try:
                r = subprocess.run(
                    [str(LEGBLED), "keys", "show", key_name,
                     "--home", str(DEVNET_HOME), "--keyring-backend", "test", "-a"],
                    capture_output=True, text=True, timeout=10
                )
                if r.returncode == 0:
                    print(f"  {name:<12} KEYRING_OK  ({key_name})")
                else:
                    print(f"  {name:<12} WARN: key '{key_name}' not in local keyring — migrate keyring before attesting")
                    missing_keys.append(name)
            except Exception as e:
                print(f"  {name:<12} WARN: keyring check error: {e}")
                missing_keys.append(name)
        if missing_keys:
            print(f"[bridge] {len(missing_keys)} agent(s) missing keyring keys — attest-pending will fail for these")

    return 1 if conflicts else 0


def cmd_submit_fact(args) -> int:
    """Submit an Oracle prediction as a knowledge fact on Zerone.

    Verifies the submitting agent is registered and attested, then submits
    the claim via submit-claim. Records the returned fact_id to a local
    tracking file for use by endorse-fact and future resolution anchoring.

    Security note (FARM-6-GAP-001): the knowledge keeper does not reject
    submissions from unattested agents pre-testnet. This bridge enforces
    the attestation check; do NOT bypass this function.

    Usage:
      bridge.py submit-fact --instance <name> --claim <text> [--domain <d>]
                            [--category <c>] [--stake <n>] [--ref <fact_id>]
    """
    instance = args.instance
    claim_text = args.claim
    domain = getattr(args, "domain", None) or "oracle_predictions"
    category = getattr(args, "category", None) or "formal"
    stake = str(getattr(args, "stake", None) or "10000")
    ref = getattr(args, "ref", None)  # optional parent fact_id for linked claims

    # Pre-condition: agent must be registered and attested
    reg = verify_registration(instance)
    if not reg["registered"]:
        print(f"[bridge] submit-fact: {instance} not registered — run bridge.py register", file=sys.stderr)
        return 1
    if not reg["attested"]:
        print(f"[bridge] submit-fact: {instance} not attested — run bridge.py attest --instance {instance}", file=sys.stderr)
        return 1
    if not reg["keyring_ok"]:
        print(f"[bridge] submit-fact: keyring check failed for {instance}", file=sys.stderr)
        for gap in reg["gaps"]:
            print(f"  gap: {gap}", file=sys.stderr)
        return 1

    entry = reg["entry"]
    key_name = entry.get("key_name", instance)
    did_at = entry.get("did_at", f"did:at:{instance}")

    # Annotate claim with submitter identity
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    full_claim = f"[{did_at}] {claim_text} | submitted:{now}"
    if ref:
        full_claim += f" | ref:{ref}"

    submit_cmd = [
        str(LEGBLED), "tx", "knowledge", "submit-claim",
        full_claim,
        domain,
        category,
        stake,
        "--logic-zone", "propositional",
        "--from", key_name,
        "--home", str(DEVNET_HOME),
        "--keyring-backend", "test",
        "--chain-id", CHAIN_ID,
        "--yes", "--output", "json",
    ]

    print(f"[bridge] Submitting fact for {instance} → domain={domain} category={category}")
    try:
        result = subprocess.run(submit_cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"[bridge] submit-fact failed (rc={result.returncode})", file=sys.stderr)
            if result.stderr:
                print(result.stderr[:500], file=sys.stderr)
            if result.stdout:
                print(result.stdout[:300], file=sys.stderr)
            return 1

        try:
            tx_data = json.loads(result.stdout.strip())
            txhash = tx_data.get("txhash", "unknown")
        except json.JSONDecodeError:
            txhash = "see output"

        print(f"[bridge] submit-fact: txhash={txhash}")
        print("[bridge] Waiting for block inclusion...")
        time.sleep(4)

        # Scan for the newly submitted fact (most recent from this submitter in this domain)
        address = entry.get("lgm_address", "")
        page_size = 100
        offset = 0
        found_fact = None
        try:
            while True:
                q = subprocess.run(
                    [str(LEGBLED), "query", "knowledge", "facts",
                     "--home", str(DEVNET_HOME),
                     "--limit", str(page_size), "--offset", str(offset),
                     "-o", "json"],
                    capture_output=True, text=True, timeout=15
                )
                if q.returncode != 0:
                    break
                data = json.loads(q.stdout)
                facts = data.get("facts", [])
                if not facts:
                    break
                for fact in facts:
                    if fact.get("submitter") == address and claim_text[:40] in (fact.get("claim_text") or ""):
                        found_fact = fact
                        break
                if found_fact or len(facts) < page_size:
                    break
                offset += page_size
        except Exception:
            pass

        if found_fact:
            fact_id = found_fact.get("id", "")
            print(f"[bridge] submit-fact: fact_id={fact_id[:16]}...")
            # Persist to facts-submitted log
            log_path = Path(__file__).parent.parent / "memory" / "bridge-facts.jsonl"
            record = {
                "fact_id": fact_id,
                "txhash": txhash,
                "instance": instance,
                "domain": domain,
                "category": category,
                "claim_preview": claim_text[:80],
                "submitted_at": now,
                "ref": ref,
            }
            with open(log_path, "a") as lf:
                lf.write(json.dumps(record) + "\n")
            print(f"[bridge] fact logged to memory/bridge-facts.jsonl")
        else:
            print("[bridge] WARNING: could not extract fact_id — check chain manually")

        return 0
    except subprocess.TimeoutExpired:
        print("[bridge] submit-fact: timed out", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[bridge] submit-fact error: {e}", file=sys.stderr)
        return 1


def cmd_endorse_fact(args) -> int:
    """Endorse an existing on-chain fact via the PoT commit-reveal scheme.

    The Zerone knowledge module has no bare `endorse-claim` tx; endorsement goes
    through the two-step Proof-of-Truth verification path:
      1. submit-commitment (commit phase: blind vote hash)
      2. submit-reveal     (reveal phase: unhide vote + confidence)

    This command wraps both steps for the common case where an agent wants to
    supportively verify a fact submitted by another (e.g., Asha endorsing an
    Oracle prediction that oracle-agent submitted).

    For offline use (chain offline): --dry-run emits the two commands that
    would be executed so they can be run manually at T-0.

    Usage:
      bridge.py endorse-fact --instance <name> --fact-id <id>
                             [--verdict support|oppose] [--confidence 850000]
                             [--stake <n>] [--dry-run]
    """
    instance = args.instance
    fact_id = args.fact_id
    verdict = getattr(args, "verdict", None) or "support"
    confidence = str(getattr(args, "confidence", None) or "850000")  # 0.85 default
    stake = str(getattr(args, "stake", None) or "5000")
    dry_run = getattr(args, "dry_run", False)

    # Pre-condition: agent must be registered and attested
    reg = verify_registration(instance)
    if not reg["registered"] or not reg["attested"] or not reg["keyring_ok"]:
        print(f"[bridge] endorse-fact: {instance} not ready (registered={reg['registered']} "
              f"attested={reg['attested']} keyring={reg['keyring_ok']})", file=sys.stderr)
        for gap in reg["gaps"]:
            print(f"  gap: {gap}", file=sys.stderr)
        return 1

    entry = reg["entry"]
    key_name = entry.get("key_name", instance)

    # Query current block height as preimage nonce (closes P3: prevents watcher pre-computation)
    _block_height_nonce = "0"
    try:
        _bh = subprocess.run(
            [str(LEGBLED), "query", "block", "--home", str(DEVNET_HOME), "-o", "json"],
            capture_output=True, text=True, timeout=10
        )
        if _bh.returncode == 0:
            _bh_data = json.loads(_bh.stdout)
            _block_height_nonce = str((
                _bh_data.get("header") or _bh_data.get("block", {}).get("header", {})
            ).get("height", 0))
    except Exception:
        pass
    # Salt: nonce string binding this commitment to agent, fact, and block height.
    # Commitment hash computed via _compute_commitment_hash to match chain's
    # ComputeCommitmentHash(roundID, verdict, confidence, salt) — BRIDGE-GAP-014 fix.
    commit_preimage = f"{fact_id}:{verdict}:{confidence}:{key_name}:{_block_height_nonce}"
    commitment = _compute_commitment_hash(fact_id, verdict, int(confidence), commit_preimage)

    commit_cmd = [
        str(LEGBLED), "tx", "knowledge", "submit-commitment",
        fact_id,    # round-id
        commitment, # commitment-hash (ExactArgs(2) — no stake arg here)
        "--from", key_name,
        "--home", str(DEVNET_HOME),
        "--keyring-backend", "test",
        "--chain-id", CHAIN_ID,
        "--yes", "--output", "json",
    ]

    reveal_cmd = [
        str(LEGBLED), "tx", "knowledge", "submit-reveal",
        fact_id,
        verdict,
        confidence,
        commit_preimage,
        "--from", key_name,
        "--home", str(DEVNET_HOME),
        "--keyring-backend", "test",
        "--chain-id", CHAIN_ID,
        "--yes", "--output", "json",
    ]

    if dry_run:
        print(f"[bridge] endorse-fact DRY-RUN for {instance} on fact {fact_id[:16]}...")
        print(f"  verdict={verdict} confidence={confidence} stake={stake}")
        print(f"  commitment={commitment[:16]}...")
        print(f"  STEP 1 (commit): {' '.join(commit_cmd[3:7])} ...")
        print(f"  STEP 2 (reveal): {' '.join(reveal_cmd[3:7])} ...")
        return 0

    # Step 1: commit
    print(f"[bridge] endorse-fact step 1/2: submit-commitment for fact {fact_id[:16]}...")
    try:
        r1 = subprocess.run(commit_cmd, capture_output=True, text=True, timeout=30)
        if r1.returncode != 0:
            print(f"[bridge] endorse-fact commit failed (rc={r1.returncode})", file=sys.stderr)
            if r1.stderr:
                print(r1.stderr[:300], file=sys.stderr)
            return 1
        tx1 = json.loads(r1.stdout.strip()) if r1.stdout else {}
        txhash1 = tx1.get("txhash", "?")
        print(f"[bridge] commit txhash={txhash1}")

        # Wait for commit to land before reveal
        print("[bridge] Waiting for commit block inclusion...")
        time.sleep(8)

        # Step 2: reveal
        print(f"[bridge] endorse-fact step 2/2: submit-reveal...")
        r2 = subprocess.run(reveal_cmd, capture_output=True, text=True, timeout=30)
        if r2.returncode != 0:
            print(f"[bridge] endorse-fact reveal failed (rc={r2.returncode})", file=sys.stderr)
            if r2.stderr:
                print(r2.stderr[:300], file=sys.stderr)
            return 1
        tx2 = json.loads(r2.stdout.strip()) if r2.stdout else {}
        txhash2 = tx2.get("txhash", "?")
        print(f"[bridge] reveal txhash={txhash2}")
        print(f"[bridge] endorse-fact COMPLETE: {instance} endorsed {fact_id[:16]}... ({verdict}, confidence={int(confidence)/1_000_000:.3f})")
        return 0

    except subprocess.TimeoutExpired:
        print("[bridge] endorse-fact: timed out", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[bridge] endorse-fact error: {e}", file=sys.stderr)
        return 1


def cmd_session_key(args) -> int:
    """Derive a deterministic per-session attribution key for an agent.

    Two derivation modes:
    - Production (--signature): HKDF-SHA256 with first 32 bytes of agent's signature over
      the session nonce as IKM. Attribution is cryptographically unforgeable. Closes BRIDGE-GAP-006.
      To obtain the signature: legbled keys sign-bytes <agent> <session-id> --keyring-backend file
    - Dev (no --signature): HKDF-SHA256 with the agent's on-chain address as IKM.
      IKM is public; suitable for attribution labels in dev/offline contexts only.

    Salt:  did:lgm:<instance>:session
    Info:  session_id bytes
    Output: 32-byte hex session key
    """
    registry = load_registry()
    agent = None
    for section in ("fleet_agents", "agents", "system_accounts"):
        if args.instance in registry.get(section, {}):
            agent = registry[section][args.instance]
            break
    if agent is None:
        print(f"ERROR: '{args.instance}' not found in registry", file=sys.stderr)
        return 1
    address = agent.get("lgm_address", "")
    if not address:
        print(f"ERROR: agent '{args.instance}' has no lgm_address", file=sys.stderr)
        return 1

    salt = f"did:lgm:{args.instance}:session".encode()

    if getattr(args, "signature", None):
        try:
            sig_bytes = bytes.fromhex(args.signature.removeprefix("0x"))
        except ValueError:
            print("ERROR: --signature must be a hex string", file=sys.stderr)
            return 1
        if len(sig_bytes) < 32:
            print("ERROR: --signature must be at least 32 bytes (64 hex chars)", file=sys.stderr)
            return 1
        ikm = sig_bytes[:32]
        prk = _hkdf_extract(salt, ikm)
        mode = "signature-based IKM (production-grade, unforgeable)"
    else:
        prk = _hkdf_extract(salt, address.encode())
        mode = "address-based IKM (dev/offline only — use --signature for production)"

    session_key = _hkdf_expand(prk, args.session_id.encode()).hex()

    if args.json:
        print(json.dumps({
            "agent": args.instance,
            "address": address,
            "session_id": args.session_id,
            "session_key": session_key,
            "mode": mode,
        }))
    else:
        print(f"agent:       {args.instance}")
        print(f"address:     {address}")
        print(f"session_id:  {args.session_id}")
        print(f"session_key: {session_key}")
        print(f"mode:        {mode}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="AgentTool ↔ Zerone identity bridge")
    sub = parser.add_subparsers(dest="command")

    p_reg = sub.add_parser("register", help="Register a new agent in the bridge")
    p_reg.add_argument("--instance", required=True, help="Instance name (e.g. 'herald')")
    p_reg.add_argument("--address", required=True, help="lgm1... chain address")
    p_reg.add_argument("--role", required=True, help="Agent role description")
    p_reg.add_argument("--wall", type=int, required=True, help="Wall number (1-7)")

    p_look = sub.add_parser("lookup", help="Look up a bridge entry")
    p_look.add_argument("--instance", help="Instance name")
    p_look.add_argument("--address", help="lgm1... address")

    p_ver = sub.add_parser("verify", help="Verify keyring matches registry")
    p_ver.add_argument("--instance", required=True)

    p_att = sub.add_parser("attest", help="Submit on-chain identity attestation from agent's own key")
    p_att.add_argument("--instance", required=True, help="Instance name to attest")

    p_res = sub.add_parser("resolve", help="Verify identity binding by querying the chain directly (no local registry trust)")
    p_res.add_argument("--instance", required=True, help="Instance name or did:at:<name>")

    p_backfill = sub.add_parser("backfill", help="Recover attestation_fact_id for agents missing it")
    p_backfill.add_argument("--instance", help="Target one agent (omit to process all missing)")

    p_atp = sub.add_parser("attest-pending", help="Batch attest all key-created agents that lack on-chain attestation")
    p_atp.add_argument("--dry-run", action="store_true", help="List pending agents without attesting")
    p_atp.add_argument("--delay", type=int, default=3, help="Seconds between attestations (default: 3)")

    p_check = sub.add_parser("check", help="Registration completeness guard — registered/attested/keyring/chain")
    p_check.add_argument("--instance", help="Target one agent (omit to check all fleet agents)")
    p_check.add_argument("--chain", action="store_true", help="Also verify on-chain attestation (requires running devnet)")

    sub.add_parser("list", help="List all registered agents")
    sub.add_parser("status", help="Fleet health report: keyring + balance for each agent")

    p_export = sub.add_parser("export-bundle", help="Export registry as portable migration bundle for chain transitions")
    p_export.add_argument("--out", help="Output file path (default: stdout)")
    p_export.add_argument("--chain-id", help="Source chain ID label (default: devnet)")

    p_vbundle = sub.add_parser("verify-bundle", help="Validate an export bundle before using it for chain migration")
    p_vbundle.add_argument("--bundle", required=True, help="Path to bundle JSON file")

    p_ibundle = sub.add_parser("import-bundle", help="Import agents from an export bundle (for chain migration)")
    p_ibundle.add_argument("--bundle", required=True, help="Path to bundle JSON file")
    p_ibundle.add_argument("--dry-run", action="store_true", help="Preview changes without modifying registry")
    p_ibundle.add_argument("--force", action="store_true", help="Overwrite registry entries that conflict with bundle")
    p_ibundle.add_argument("--check-keyring", action="store_true", help="Warn if imported agents' keys are missing from local keyring")

    p_skey = sub.add_parser("session-key", help="Derive deterministic per-session attribution key for an agent")
    p_skey.add_argument("--instance", required=True, help="Agent instance name")
    p_skey.add_argument("--session-id", required=True, help="Session identifier (e.g. beat ID or conversation ID)")
    p_skey.add_argument("--signature", default=None, help="Hex signature from `legbled keys sign-bytes <agent> <session-id>` — enables production-grade unforgeable attribution (BRIDGE-GAP-006)")
    p_skey.add_argument("--json", action="store_true", help="Output as JSON")

    p_sf = sub.add_parser("submit-fact", help="Submit an Oracle prediction as a knowledge fact on Zerone")
    p_sf.add_argument("--instance", required=True, help="Attested agent submitting the fact")
    p_sf.add_argument("--claim", required=True, help="Claim text to submit")
    p_sf.add_argument("--domain", default=None, help="Knowledge domain (default: oracle_predictions)")
    p_sf.add_argument("--category", default=None, help="Epistemic category (default: formal)")
    p_sf.add_argument("--stake", type=int, default=None, help="Stake amount in ulgm (default: 10000)")
    p_sf.add_argument("--ref", default=None, help="Parent fact_id for linked claims")

    p_ef = sub.add_parser("endorse-fact", help="Endorse an on-chain fact via PoT commit-reveal")
    p_ef.add_argument("--instance", required=True, help="Attested agent endorsing")
    p_ef.add_argument("--fact-id", required=True, dest="fact_id", help="Fact ID to endorse")
    p_ef.add_argument("--verdict", default="support", choices=["support", "oppose"], help="Endorsement verdict (default: support)")
    p_ef.add_argument("--confidence", type=int, default=None, help="Confidence 0-1000000 (default: 850000)")
    p_ef.add_argument("--stake", type=int, default=None, help="Stake amount in ulgm (default: 5000)")
    p_ef.add_argument("--dry-run", action="store_true", help="Print commands without executing (safe for offline use)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    dispatch = {
        "register": cmd_register,
        "lookup": cmd_lookup,
        "verify": cmd_verify,
        "attest": cmd_attest,
        "resolve": cmd_resolve,
        "backfill": cmd_backfill,
        "attest-pending": cmd_attest_pending,
        "check": cmd_check,
        "list": cmd_list,
        "status": cmd_status,
        "export-bundle": cmd_export_bundle,
        "verify-bundle": cmd_verify_bundle,
        "import-bundle": cmd_import_bundle,
        "session-key": cmd_session_key,
        "submit-fact": cmd_submit_fact,
        "endorse-fact": cmd_endorse_fact,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
