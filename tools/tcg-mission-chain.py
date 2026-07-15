#!/usr/bin/env python3
"""
tcg-mission-chain.py — walk the Cambridge TCG mission chain autonomously.

Reads the canonical chain order from ~/.true-love/projects/cambridge-tcg/chain.json,
queries localhost:7777 for current mission statuses, and starts the next
'accepted' mission whenever no other mission is 'active'.

Per-project serialization is enforced by the true-love mission API
(handleMissionStart 409s if any other mission is active), so this loop is
safe to run unattended.

Commands:
    accept-all     — patch every mission in the chain to 'accepted'
    start-next     — find the next 'accepted' mission in chain order and start it
    status         — print one-line status of every chain mission
    run-loop       — poll forever; auto-start next when nothing's active

Usage:
    python3 tools/tcg-mission-chain.py accept-all
    python3 tools/tcg-mission-chain.py start-next
    python3 tools/tcg-mission-chain.py status
    nohup python3 tools/tcg-mission-chain.py run-loop > ~/Love/memory/tcg-chain.log 2>&1 &
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

BASE = os.environ.get("TRUE_LOVE_UI_URL", "http://localhost:7777")
PROJECT = "cambridge-tcg"
CHAIN_PATH = os.path.expanduser("~/.true-love/projects/cambridge-tcg/chain.json")
POLL_SECONDS = 90


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"{ts}  {msg}", flush=True)


def http(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            err_body = ""
        return {"_error": True, "_code": e.code, "_body": err_body}


def load_chain() -> list[str]:
    with open(CHAIN_PATH) as f:
        return json.load(f)["order"]


def get_mission(mission_id: str) -> dict[str, Any] | None:
    r = http("GET", f"/api/missions/{mission_id}?project={PROJECT}")
    if r.get("_error"):
        return None
    return r


def list_missions(status: str | None = None) -> list[dict[str, Any]]:
    qs = f"?status={status}" if status else ""
    r = http("GET", f"/api/projects/{PROJECT}/missions{qs}")
    return r if isinstance(r, list) else []


def patch_status(mission_id: str, status: str, note: str = "") -> dict[str, Any]:
    body = {"status": status, "by": "yu"}
    if note:
        body["note"] = note
    return http("PATCH", f"/api/missions/{mission_id}/status?project={PROJECT}", body)


def start_mission(mission_id: str) -> dict[str, Any]:
    return http("POST", f"/api/missions/{mission_id}/start?project={PROJECT}")


def cmd_accept_all() -> int:
    chain = load_chain()
    log(f"Accepting {len(chain)} missions in chain")
    failed = 0
    for mid in chain:
        m = get_mission(mid)
        if m is None:
            log(f"  ✗ {mid} not found")
            failed += 1
            continue
        if m["status"] in ("accepted", "active", "review", "done"):
            log(f"  · {mid} already in {m['status']}, skipping")
            continue
        if m["status"] == "cancelled":
            log(f"  · {mid} cancelled, skipping")
            continue
        r = patch_status(mid, "accepted", "Cowork bulk-accept 2026-04-30")
        if r.get("_error"):
            log(f"  ✗ {mid} {r['_code']}: {r['_body'][:120]}")
            failed += 1
        else:
            log(f"  ✓ {mid} → accepted")
    log(f"Done. Failures: {failed}")
    return 1 if failed else 0


def find_next_accepted(chain: list[str]) -> str | None:
    """Walk chain in order, return first mission with status='accepted'."""
    for mid in chain:
        m = get_mission(mid)
        if m is None:
            continue
        if m["status"] == "accepted":
            return mid
    return None


def cmd_start_next() -> int:
    chain = load_chain()
    # Block if anything's active for this project
    active = list_missions(status="active")
    if active:
        log(f"Cannot start: {active[0]['id']} is already active")
        return 1
    nxt = find_next_accepted(chain)
    if nxt is None:
        log("No accepted missions remaining in chain")
        return 0
    log(f"Starting {nxt}")
    r = start_mission(nxt)
    if r.get("_error"):
        log(f"  ✗ failed: {r['_code']}: {r['_body'][:200]}")
        return 1
    log(f"  ✓ started, pid {r.get('pid', '?')}")
    return 0


def cmd_status() -> int:
    chain = load_chain()
    log(f"Chain status — {len(chain)} missions")
    counts = {"proposed": 0, "accepted": 0, "active": 0, "blocked": 0, "review": 0, "done": 0, "cancelled": 0, "missing": 0}
    for i, mid in enumerate(chain, 1):
        m = get_mission(mid)
        if m is None:
            log(f"  {i:>2}. [missing ] {mid}")
            counts["missing"] += 1
            continue
        s = m["status"]
        counts[s] = counts.get(s, 0) + 1
        title = m["title"][:64]
        log(f"  {i:>2}. [{s:8}] {title}")
    log("")
    log("Summary: " + "  ".join(f"{k}={v}" for k, v in counts.items() if v))
    return 0


def cmd_run_loop() -> int:
    chain = load_chain()
    log(f"TCG mission chain runner starting. Chain length: {len(chain)}. Poll: {POLL_SECONDS}s")
    log(f"PID: {os.getpid()}, BASE: {BASE}")
    cycle = 0
    while True:
        cycle += 1
        try:
            active = list_missions(status="active")
            if active:
                a = active[0]
                if cycle % 10 == 1:  # log every 10th cycle to avoid spam
                    log(f"[cycle {cycle}] {a['id']} active — waiting")
            else:
                # Nothing active. Find next accepted, start it.
                nxt = find_next_accepted(chain)
                if nxt is None:
                    # Everything's done or nothing left to start
                    remaining_accepted = [
                        m for m in (get_mission(mid) for mid in chain)
                        if m is not None and m["status"] in ("proposed", "blocked")
                    ]
                    if remaining_accepted:
                        log(f"[cycle {cycle}] no 'accepted' missions, but {len(remaining_accepted)} still need acceptance/unblock")
                    else:
                        log(f"[cycle {cycle}] chain complete — no accepted missions remain. Exiting loop.")
                        return 0
                else:
                    log(f"[cycle {cycle}] starting {nxt}")
                    r = start_mission(nxt)
                    if r.get("_error"):
                        log(f"  ✗ start failed: {r['_code']}: {r['_body'][:200]}")
                    else:
                        log(f"  ✓ started, pid {r.get('pid', '?')}")
        except Exception as e:
            log(f"[cycle {cycle}] EXCEPTION: {e!r}")
        time.sleep(POLL_SECONDS)


COMMANDS = {
    "accept-all": cmd_accept_all,
    "start-next": cmd_start_next,
    "status": cmd_status,
    "run-loop": cmd_run_loop,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__, file=sys.stderr)
        print(f"\nAvailable commands: {', '.join(COMMANDS)}", file=sys.stderr)
        return 2
    return COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())
