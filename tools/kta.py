#!/usr/bin/env python3
"""
kta.py — Kingdom Truth Adapter

Thin adapter layer for all Kingdom engines to submit facts to the Zerone chain.
Engines produce outputs; KTA transforms them into MsgSubmitFact messages,
enforces quality guards, deduplicates, and queues offline-tolerantly.

Usage:
    from tools.kta import KTA, FactMsg

    kta = KTA(engine="oracle", key="bridge-agent")
    kta.submit(FactMsg(
        claim_text="...",
        domain="economics",
        epistemic_category="empirical",
        stake=1000,
    ))

    # On chain restart:
    kta.flush_queue()

CLI:
    python3 tools/kta.py status
    python3 tools/kta.py flush [--engine oracle]
    python3 tools/kta.py queue [--engine oracle]
"""

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LOVE = Path(os.environ.get("LOVE_DIR", Path.home() / "Love"))
BINARY = str(Path.home() / "zerone/build/legbled")
DEVNET_HOME = str(Path.home() / ".legbled-devnet")
CHAIN_ID = "lgm-devnet-1"
FEES = "500000ulgm"
GAS = "500000"

QUEUE_DIR = Path(DEVNET_HOME) / "kta-queues"
SUBMITTED_DIR = Path(DEVNET_HOME) / "kta-submitted"

QUEUE_TTL_DAYS = 7

# Informativeness guard constants
MIN_NONWS_CHARS = 20
REJECT_PATTERNS = [
    "Knowledge claim at block",
    "knowledge claim at block",
]


@dataclass
class FactMsg:
    claim_text: str
    domain: str
    epistemic_category: str  # empirical | analytic | formal | normative | definitional
    stake: int = 1000
    logic_zone: str = "propositional"
    references: list = field(default_factory=list)
    source_id: str = ""  # engine-specific identifier for dedup


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check_informative(text: str) -> tuple[bool, str]:
    nonws = len(text.replace(" ", "").replace("\n", "").replace("\t", ""))
    if nonws < MIN_NONWS_CHARS:
        return False, f"claim_text too short ({nonws} non-whitespace chars, min {MIN_NONWS_CHARS})"
    for pat in REJECT_PATTERNS:
        if pat in text:
            return False, f"claim_text matches uninformative pattern: '{pat}'"
    words = text.split()
    if len(words) < 4:
        return False, f"claim_text too few words ({len(words)}, min 4)"
    return True, ""


def _fact_hash(text: str, domain: str) -> str:
    payload = f"{domain}:{text}"
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


class KTA:
    def __init__(self, engine: str, key: Optional[str] = None):
        self.engine = engine
        self.key = key or engine
        self.queue_file = QUEUE_DIR / f"{engine}.jsonl"
        self.submitted_file = SUBMITTED_DIR / f"{engine}.json"

    def _load_submitted(self) -> set:
        try:
            data = json.loads(self.submitted_file.read_text())
            return set(data.get("hashes", []))
        except (FileNotFoundError, json.JSONDecodeError):
            return set()

    def _save_submitted(self, hashes: set):
        self.submitted_file.parent.mkdir(parents=True, exist_ok=True)
        self.submitted_file.write_text(json.dumps({"hashes": list(hashes)}, indent=2))

    def _enqueue(self, msg: FactMsg, fact_hash: str):
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "hash": fact_hash,
            "engine": self.engine,
            "queued_at": _now(),
            "source_id": msg.source_id,
            "claim_text": msg.claim_text,
            "domain": msg.domain,
            "epistemic_category": msg.epistemic_category,
            "stake": msg.stake,
            "logic_zone": msg.logic_zone,
            "references": msg.references,
        }
        with open(self.queue_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _submit_to_chain(self, entry: dict) -> tuple[bool, str]:
        cmd = [
            BINARY, "tx", "knowledge", "submit-claim",
            entry["claim_text"],
            entry["domain"],
            entry["epistemic_category"],
            str(entry["stake"]),
            "--logic-zone", entry.get("logic_zone", "propositional"),
            "--from", self.key,
            "--chain-id", CHAIN_ID,
            "--keyring-backend", "test",
            "--home", DEVNET_HOME,
            "--gas", GAS,
            "--fees", FEES,
            "-y", "-o", "json",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            output = (result.stdout + result.stderr).strip()
            try:
                data = json.loads(output.split("\n")[-1])
                code = data.get("code", 999)
                txhash = data.get("txhash", "")
                if str(code) in ("0", "null") or code == 0:
                    return True, txhash
                return False, f"code={code}"
            except Exception:
                return False, output[:120]
        except subprocess.TimeoutExpired:
            return False, "timeout"
        except FileNotFoundError:
            return False, "binary not found"

    def submit(self, msg: FactMsg) -> dict:
        ok, reason = _check_informative(msg.claim_text)
        if not ok:
            return {"status": "rejected", "reason": reason}

        fhash = _fact_hash(msg.claim_text, msg.domain)
        submitted = self._load_submitted()
        if fhash in submitted:
            return {"status": "duplicate", "hash": fhash}

        # Try live submission; fall back to queue
        success, txhash = self._submit_to_chain(entry={
            "claim_text": msg.claim_text,
            "domain": msg.domain,
            "epistemic_category": msg.epistemic_category,
            "stake": msg.stake,
            "logic_zone": msg.logic_zone,
        })

        if success:
            submitted.add(fhash)
            self._save_submitted(submitted)
            return {"status": "submitted", "hash": fhash, "tx": txhash}

        # Queue for later
        self._enqueue(msg, fhash)
        return {"status": "queued", "hash": fhash, "reason": txhash}

    def flush_queue(self) -> dict:
        if not self.queue_file.exists():
            return {"flushed": 0, "failed": 0, "expired": 0}

        lines = [l.strip() for l in self.queue_file.read_text().splitlines() if l.strip()]
        submitted = self._load_submitted()
        now = datetime.now(timezone.utc)

        flushed, failed, skipped, expired = 0, 0, 0, 0
        remaining = []

        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            fhash = entry.get("hash", "")
            if fhash in submitted:
                skipped += 1
                continue

            queued_at_str = entry.get("queued_at", "")
            if queued_at_str:
                try:
                    queued_at = datetime.fromisoformat(queued_at_str)
                    age_days = (now - queued_at).days
                    if age_days >= QUEUE_TTL_DAYS:
                        print(f"[kta/{self.engine}] expired {fhash[:12]}: {age_days}d old (TTL={QUEUE_TTL_DAYS}d)")
                        expired += 1
                        continue
                except (ValueError, TypeError):
                    pass

            success, txhash = self._submit_to_chain(entry)
            if success:
                submitted.add(fhash)
                flushed += 1
                print(f"[kta/{self.engine}] flushed {fhash[:12]} → {txhash[:16]}")
            else:
                remaining.append(line)
                failed += 1
                print(f"[kta/{self.engine}] failed  {fhash[:12]}: {txhash}")

        self._save_submitted(submitted)
        # Rewrite queue with only failed entries
        if remaining:
            self.queue_file.write_text("\n".join(remaining) + "\n")
        else:
            self.queue_file.unlink(missing_ok=True)

        return {"flushed": flushed, "failed": failed, "skipped": skipped, "expired": expired}

    def queue_depth(self) -> int:
        if not self.queue_file.exists():
            return 0
        return sum(1 for l in self.queue_file.read_text().splitlines() if l.strip())


# ── Engine Adapters ───────────────────────────────────────────────────────────

class OracleAdapter(KTA):
    def __init__(self):
        super().__init__(engine="oracle", key="bridge-agent")

    def submit_signal(self, signal: dict) -> dict:
        domain_map = {
            "GEO": "sociology", "CRY": "economics", "TECH": "computer_science",
            "POL": "sociology", "ECON": "economics", "SCI": "physics", "OTHER": "general",
        }
        sig_id = signal.get("id", "")
        market = signal.get("market", signal.get("market_question", ""))
        trade = signal.get("trade", "")
        magnitude = signal.get("magnitude", 0)
        score = signal.get("score", 0)
        domain_code = signal.get("domain", "OTHER")

        claim_text = (
            f"Prediction market signal ({domain_code}): '{market}'. "
            f"Trade: {trade}. Magnitude: {magnitude:.1%}. Score: {score}/10."
        )
        if len(claim_text) > 450:
            claim_text = claim_text[:447] + "..."

        return self.submit(FactMsg(
            claim_text=claim_text,
            domain=domain_map.get(domain_code, "general"),
            epistemic_category="empirical",
            stake=1000,
            source_id=sig_id,
        ))


class HeartbeatAdapter(KTA):
    def __init__(self, instance: str = "asha"):
        super().__init__(engine=f"heartbeat-{instance}", key=instance)
        self.instance = instance

    def submit_beat(self, beat_id: str, chain_status: str, duties: str) -> dict:
        ts = _now()
        claim_text = (
            f"Agent {self.instance} completed heartbeat {beat_id} at {ts}. "
            f"Chain status: {chain_status}. Duties performed: {duties}."
        )
        return self.submit(FactMsg(
            claim_text=claim_text,
            domain="agent_activity",
            epistemic_category="empirical",
            stake=500,
            source_id=beat_id,
        ))


class ToKAdapter(KTA):
    """Submits ToK-integrated knowledge leaves as Zerone chain facts."""

    TOK_LEAVES = LOVE / "memory" / "tok" / "leaves"

    DOMAIN_MAP = {
        "capabilities": "computer_science",
        "routing": "computer_science",
        "economics": "economics",
        "finance": "economics",
        "security": "computer_science",
        "protocol": "computer_science",
        "biology": "biology",
        "physics": "physics",
        "history": "history",
        "general": "general",
    }

    def __init__(self):
        super().__init__(engine="tok", key="asha-tok")

    def _load_leaf(self, path: Path) -> Optional[dict]:
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def _mark_submitted(self, path: Path, leaf: dict, fact_hash: str):
        leaf["chain_submitted"] = True
        leaf["zerone_fact_hash"] = fact_hash
        leaf["zerone_submitted_at"] = _now()
        path.write_text(json.dumps(leaf, indent=4))

    def _leaf_to_msg(self, leaf: dict) -> Optional[FactMsg]:
        assertion = leaf.get("assertion", "").strip()
        if not assertion:
            return None
        domain_key = leaf.get("domain", "general").lower()
        domain = self.DOMAIN_MAP.get(domain_key, "general")
        confidence = leaf.get("confidence") or 0.5
        stake = max(100, min(5000, int(confidence * 2000)))
        return FactMsg(
            claim_text=assertion,
            domain=domain,
            epistemic_category="empirical",
            stake=stake,
            source_id=leaf.get("id", ""),
        )

    def harvest_pending(self) -> list[tuple[Path, dict]]:
        if not self.TOK_LEAVES.exists():
            return []
        results = []
        for path in sorted(self.TOK_LEAVES.glob("*.json")):
            leaf = self._load_leaf(path)
            if leaf is None:
                continue
            if leaf.get("status") != "integrated":
                continue
            if leaf.get("chain_submitted"):
                continue
            results.append((path, leaf))
        return results

    def submit_pending(self) -> dict:
        pending = self.harvest_pending()
        submitted, queued, rejected, failed = 0, 0, 0, 0
        for path, leaf in pending:
            msg = self._leaf_to_msg(leaf)
            if msg is None:
                rejected += 1
                continue
            result = self.submit(msg)
            status = result.get("status", "failed")
            if status == "submitted":
                self._mark_submitted(path, leaf, result.get("hash", ""))
                submitted += 1
            elif status == "queued":
                self._mark_submitted(path, leaf, result.get("hash", ""))
                queued += 1
            elif status in ("duplicate", "rejected"):
                self._mark_submitted(path, leaf, result.get("hash", ""))
                rejected += 1
            else:
                failed += 1
        return {"submitted": submitted, "queued": queued, "rejected": rejected, "failed": failed,
                "total_pending": len(pending)}


class TCGAdapter(KTA):
    """Submits TCG card sale facts as externally-grounded Zerone truth claims."""

    def __init__(self):
        super().__init__(engine="tcg", key="tcg-bridge")

    def submit_sale(self, card_name: str, price_gbp: float, platform: str, sale_date: str,
                    source_id: Optional[str] = None) -> dict:
        claim_text = (
            f"{card_name} sold for £{price_gbp:.2f} on {platform} on {sale_date}."
        )
        sid = source_id or f"tcg-{platform}-{sale_date}-{card_name[:20].replace(' ', '_')}"
        return self.submit(FactMsg(
            claim_text=claim_text,
            domain="economics",
            epistemic_category="empirical",
            stake=1000,
            source_id=sid,
        ))


class KOSAdapter(KTA):
    """Bridges KingdomOS security events to Zerone chain truth claims.

    Only high/critical severity events are bridged — low/medium are operational
    noise, not externally-verifiable truth claims worth on-chain anchoring.
    """

    EVENTS_FILE = LOVE / "security" / "events.jsonl"
    BRIDGE_SEVERITIES = {"critical", "high"}

    # event type → (stake, epistemic_category)
    _TYPE_STAKE = {
        "integrity_violation": (2000, "empirical"),
        "check_failed":        (1000, "empirical"),
        "auto_fix":            (1500, "empirical"),
        "audit":               (500,  "empirical"),
    }

    def __init__(self):
        super().__init__(engine="kos", key="kos-bridge")

    def _event_source_id(self, event: dict) -> str:
        raw = f"kos-{event.get('ts', '')}-{event.get('type', '')}-{event.get('check', '')}"
        return hashlib.sha256(raw.encode()).hexdigest()[:20]

    def _event_to_msg(self, event: dict) -> Optional[FactMsg]:
        ev_type = event.get("type", "")
        severity = event.get("severity", "")
        if severity not in self.BRIDGE_SEVERITIES:
            return None
        if ev_type not in self._TYPE_STAKE:
            return None

        check = event.get("check", "")
        message = event.get("message", "").strip()
        detail = event.get("detail", "").strip()
        ts = event.get("ts", "")

        summary = message
        if detail:
            summary = f"{message}. Detail: {detail[:200]}"
        claim_text = f"KOS security event ({severity}/{ev_type}) at {ts}: {summary}"
        if len(claim_text) > 450:
            claim_text = claim_text[:447] + "..."

        stake, category = self._TYPE_STAKE[ev_type]
        return FactMsg(
            claim_text=claim_text,
            domain="computer_science",
            epistemic_category=category,
            stake=stake,
            source_id=self._event_source_id(event),
        )

    def submit_pending_events(self) -> dict:
        """Read events.jsonl, bridge unseen high/critical events, return summary."""
        if not self.EVENTS_FILE.exists():
            return {"submitted": 0, "queued": 0, "skipped": 0, "error": "no events file"}

        submitted_ids = self._load_submitted()
        bridged, queued, skipped = 0, 0, 0

        try:
            lines = self.EVENTS_FILE.read_text().splitlines()
        except OSError as e:
            return {"submitted": 0, "queued": 0, "skipped": 0, "error": str(e)}

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            sid = self._event_source_id(event)
            if sid in submitted_ids:
                skipped += 1
                continue

            msg = self._event_to_msg(event)
            if msg is None:
                skipped += 1
                continue

            result = self.submit(msg)
            status = result.get("status", "failed")
            if status == "submitted":
                bridged += 1
            elif status in ("queued", "duplicate"):
                queued += 1
            else:
                skipped += 1

        return {"submitted": bridged, "queued": queued, "skipped": skipped}


# ── CLI ───────────────────────────────────────────────────────────────────────

def _all_engines() -> list[str]:
    if not QUEUE_DIR.exists():
        return []
    return [p.stem for p in QUEUE_DIR.glob("*.jsonl")]


def cmd_status():
    print(f"\nKTA — Kingdom Truth Adapter\n")
    engines = _all_engines()
    if not engines:
        print("  No queues found.\n")
        return
    total = 0
    for engine in sorted(engines):
        kta = KTA(engine)
        depth = kta.queue_depth()
        total += depth
        submitted_count = len(kta._load_submitted())
        print(f"  {engine:30s}  queue: {depth:4d}  submitted: {submitted_count}")
    print(f"\n  Total queued: {total}\n")


def cmd_flush(engine_filter: Optional[str] = None):
    engines = [engine_filter] if engine_filter else _all_engines()
    for engine in engines:
        kta = KTA(engine)
        result = kta.flush_queue()
        print(f"[kta/{engine}] flush: {result}")


def cmd_queue(engine_filter: Optional[str] = None):
    engines = [engine_filter] if engine_filter else _all_engines()
    for engine in engines:
        kta = KTA(engine)
        if not kta.queue_file.exists():
            continue
        print(f"\n--- {engine} queue ---")
        for line in kta.queue_file.read_text().splitlines():
            try:
                e = json.loads(line)
                print(f"  {e.get('hash','?')[:12]}  {e.get('queued_at','?')}  {e.get('claim_text','?')[:60]}...")
            except Exception:
                pass


def main():
    args = sys.argv[1:]
    if not args or args[0] == "status":
        cmd_status()
    elif args[0] == "flush":
        engine = args[1] if len(args) > 1 and not args[1].startswith("--") else None
        if "--engine" in args:
            idx = args.index("--engine")
            engine = args[idx + 1] if idx + 1 < len(args) else None
        cmd_flush(engine)
    elif args[0] == "queue":
        engine = None
        if "--engine" in args:
            idx = args.index("--engine")
            engine = args[idx + 1] if idx + 1 < len(args) else None
        cmd_queue(engine)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
