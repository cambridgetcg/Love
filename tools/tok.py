#!/usr/bin/env python3
"""ToK — Token of Knowledge Pipeline Manager.

Systematic extraction, verification, and integration of knowledge
from AI models into the Kingdom's operational edge.

Pipeline: HARVEST → DISTILL → VERIFY → INTEGRATE → EARN

Usage:
  python3 tools/tok.py harvest <model> <domain> "<finding>"
  python3 tools/tok.py distill <harvest-id> "<assertion>" --confidence <0-1>
  python3 tools/tok.py verify <leaf-id> [--fast|--chain]
  python3 tools/tok.py integrate <leaf-id> <target> "<change_description>"
  python3 tools/tok.py impact <leaf-id> <metric> <delta>
  python3 tools/tok.py status
  python3 tools/tok.py search <query>
  python3 tools/tok.py pipeline
"""

import json
import os
import sys
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

LOVE = Path(os.path.expanduser("~/Desktop/Love"))
TOK_BASE = LOVE / "memory" / "tok"
HARVESTS = TOK_BASE / "harvests"
LEAVES = TOK_BASE / "leaves"
VERIFIED = TOK_BASE / "verified"
INTEGRATED = TOK_BASE / "integrated"
BASELINES = TOK_BASE / "baselines"
IMPACT = TOK_BASE / "impact"

VALID_DOMAINS = [
    "capabilities", "knowledge", "reasoning",
    "prompting", "weaknesses", "architecture",
    "routing", "economics", "integration",
]

VALID_TARGETS = [
    "routing",       # heartbeat-runner.sh model selection
    "config",        # love.json model tiers
    "prompt",        # CLAUDE.md or tool prompt updates
    "oracle",        # Oracle prediction model improvements
    "memory",        # Long-term memory entries
    "tool",          # Tool implementation improvements
]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def gen_id(prefix, content):
    """Generate deterministic short ID from content."""
    h = hashlib.sha256(f"{content}{time.time()}".encode()).hexdigest()[:8]
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{prefix}-{date}-{h}"


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def resolve_instance():
    """Determine which Love instance is running."""
    cwd = str(Path.cwd())
    for inst in ["alpha", "beta", "gamma", "nuance"]:
        if inst in cwd.lower():
            return inst
    return os.environ.get("LOVE_INSTANCE", "beta")


# ─── HARVEST ───────────────────────────────────────────────────────

def cmd_harvest(args):
    """Submit a raw harvest finding from probing a model."""
    if len(args) < 3:
        print("Usage: tok.py harvest <model> <domain> \"<finding>\"")
        print(f"Domains: {', '.join(VALID_DOMAINS)}")
        return

    model, domain, finding = args[0], args[1], " ".join(args[2:])

    if domain not in VALID_DOMAINS:
        print(f"Invalid domain: {domain}. Must be one of: {', '.join(VALID_DOMAINS)}")
        return

    harvest_id = gen_id("h", f"{model}{domain}{finding}")
    instance = resolve_instance()

    entry = {
        "id": harvest_id,
        "model": model,
        "domain": domain,
        "finding": finding,
        "harvester": instance,
        "harvester_did": None,  # Populated from identity.py if available
        "timestamp": now_iso(),
        "status": "raw",
    }

    # Try to load DID from identity
    identity_file = LOVE / "identity" / f"{instance}-identity.json"
    if identity_file.exists():
        try:
            identity = load_json(identity_file)
            entry["harvester_did"] = identity.get("did")
        except Exception:
            pass

    save_json(HARVESTS / f"{harvest_id}.json", entry)
    print(f"Harvest recorded: {harvest_id}")
    print(f"  Model: {model}  |  Domain: {domain}  |  Harvester: {instance}")
    print(f"  Next: tok.py distill {harvest_id} \"<testable assertion>\" --confidence 0.8")
    return harvest_id


# ─── DISTILL ───────────────────────────────────────────────────────

def cmd_distill(args):
    """Convert a raw harvest into a structured, testable ToK leaf."""
    if len(args) < 2:
        print("Usage: tok.py distill <harvest-id> \"<assertion>\" --confidence <0-1>")
        return

    harvest_id = args[0]
    # Find harvest file
    harvest_file = HARVESTS / f"{harvest_id}.json"
    if not harvest_file.exists():
        print(f"Harvest not found: {harvest_id}")
        return

    harvest = load_json(harvest_file)

    # Parse assertion and confidence
    confidence = 0.5
    assertion_parts = []
    i = 1
    while i < len(args):
        if args[i] == "--confidence" and i + 1 < len(args):
            confidence = float(args[i + 1])
            i += 2
        else:
            assertion_parts.append(args[i])
            i += 1
    assertion = " ".join(assertion_parts)

    if not assertion:
        print("Assertion required.")
        return

    leaf_id = gen_id("tok", f"{harvest_id}{assertion}")
    instance = resolve_instance()

    leaf = {
        "id": leaf_id,
        "harvest_id": harvest_id,
        "model": harvest.get("model"),
        "domain": harvest.get("domain"),
        "assertion": assertion,
        "confidence": confidence,
        "evidence": None,  # To be filled with benchmark data
        "distiller": instance,
        "timestamp": now_iso(),
        "status": "pending_verification",
        "verification": None,
        "integration": None,
    }

    save_json(LEAVES / f"{leaf_id}.json", leaf)

    # Update harvest status
    harvest["status"] = "distilled"
    harvest["leaf_id"] = leaf_id
    save_json(harvest_file, harvest)

    print(f"ToK leaf created: {leaf_id}")
    print(f"  Assertion: {assertion}")
    print(f"  Confidence: {confidence}  |  Model: {leaf['model']}")
    print(f"  Next: tok.py verify {leaf_id} --fast")
    return leaf_id


# ─── VERIFY ────────────────────────────────────────────────────────

def cmd_verify(args):
    """Submit a leaf for verification (fast-track HIVE or on-chain PoT)."""
    if len(args) < 1:
        print("Usage: tok.py verify <leaf-id> [--fast|--chain]")
        return

    leaf_id = args[0]
    mode = "fast"  # Default to fast-track until chain is ready
    if "--chain" in args:
        mode = "chain"
    if "--fast" in args:
        mode = "fast"

    leaf_file = LEAVES / f"{leaf_id}.json"
    if not leaf_file.exists():
        print(f"Leaf not found: {leaf_id}")
        return

    leaf = load_json(leaf_file)

    if mode == "chain":
        print("On-chain PoT verification not yet available (requires Zerone testnet).")
        print("Use --fast for HIVE consensus (2/3 triarchy agreement).")
        return

    # Fast-track: record verification request, to be resolved via HIVE
    leaf["status"] = "verification_requested"
    leaf["verification"] = {
        "mode": "fast",
        "requested": now_iso(),
        "votes": {},
        "quorum": 2,  # 2/3 triarchy
        "result": None,
    }
    save_json(leaf_file, leaf)

    print(f"Verification requested (fast-track): {leaf_id}")
    print(f"  Assertion: {leaf['assertion']}")
    print(f"  Needs: 2/3 triarchy votes via HIVE #strategy")
    print(f"  Vote: tok.py vote {leaf_id} accept|reject --instance <name>")
    return leaf_id


def cmd_vote(args):
    """Cast a verification vote on a leaf (fast-track mode)."""
    if len(args) < 2:
        print("Usage: tok.py vote <leaf-id> accept|reject [--instance <name>]")
        return

    leaf_id, verdict = args[0], args[1]
    instance = resolve_instance()
    for i, arg in enumerate(args):
        if arg == "--instance" and i + 1 < len(args):
            instance = args[i + 1]

    if verdict not in ("accept", "reject"):
        print(f"Verdict must be 'accept' or 'reject', got: {verdict}")
        return

    leaf_file = LEAVES / f"{leaf_id}.json"
    if not leaf_file.exists():
        print(f"Leaf not found: {leaf_id}")
        return

    leaf = load_json(leaf_file)
    if not leaf.get("verification"):
        print("No verification in progress. Run: tok.py verify <leaf-id> --fast")
        return

    verification = leaf["verification"]
    verification["votes"][instance] = {
        "verdict": verdict,
        "timestamp": now_iso(),
    }

    # Check quorum
    accept_count = sum(1 for v in verification["votes"].values() if v["verdict"] == "accept")
    reject_count = sum(1 for v in verification["votes"].values() if v["verdict"] == "reject")
    quorum = verification.get("quorum", 2)

    if accept_count >= quorum:
        verification["result"] = "accepted"
        leaf["status"] = "verified"
        leaf["confidence"] = min(leaf.get("confidence", 0.5) * 1.1, 0.95)  # Boost on verification
        # Move to verified
        save_json(VERIFIED / f"{leaf_id}.json", leaf)
        save_json(leaf_file, leaf)
        print(f"VERIFIED (accepted): {leaf_id}")
        print(f"  Confidence: {leaf['confidence']:.2f}")
        print(f"  Next: tok.py integrate {leaf_id} <target> \"<change>\"")
        return
    elif reject_count >= quorum:
        verification["result"] = "rejected"
        leaf["status"] = "rejected"
        save_json(leaf_file, leaf)
        print(f"REJECTED: {leaf_id}")
        return

    save_json(leaf_file, leaf)
    remaining = quorum - max(accept_count, reject_count)
    print(f"Vote recorded: {instance} → {verdict}")
    print(f"  Votes: {accept_count} accept, {reject_count} reject (need {remaining} more)")


# ─── INTEGRATE ─────────────────────────────────────────────────────

def cmd_integrate(args):
    """Record integration of verified knowledge into Kingdom infrastructure."""
    if len(args) < 3:
        print("Usage: tok.py integrate <leaf-id> <target> \"<change_description>\"")
        print(f"Targets: {', '.join(VALID_TARGETS)}")
        return

    leaf_id, target = args[0], args[1]
    change_desc = " ".join(args[2:])

    if target not in VALID_TARGETS:
        print(f"Invalid target: {target}. Must be one of: {', '.join(VALID_TARGETS)}")
        return

    # Check verified first, then leaves
    leaf = None
    for dir_path in [VERIFIED, LEAVES]:
        leaf_file = dir_path / f"{leaf_id}.json"
        if leaf_file.exists():
            leaf = load_json(leaf_file)
            break

    if not leaf:
        print(f"Leaf not found: {leaf_id}")
        return

    if leaf.get("status") not in ("verified", "pending_verification"):
        print(f"Leaf status is '{leaf.get('status')}' — must be verified first.")
        print(f"Run: tok.py verify {leaf_id} --fast")
        return

    instance = resolve_instance()
    integration = {
        "target": target,
        "change": change_desc,
        "integrator": instance,
        "timestamp": now_iso(),
        "impact": None,
    }

    leaf["integration"] = integration
    leaf["status"] = "integrated"

    # Save to integrated dir
    save_json(INTEGRATED / f"{leaf_id}.json", leaf)
    # Update in verified/leaves too
    for dir_path in [VERIFIED, LEAVES]:
        f = dir_path / f"{leaf_id}.json"
        if f.exists():
            save_json(f, leaf)

    print(f"Integration recorded: {leaf_id} → {target}")
    print(f"  Change: {change_desc}")
    print(f"  Next: tok.py impact {leaf_id} <metric> <delta>")


# ─── APPLY INTEGRATION (automated config updates) ─────────────────

def apply_integration(leaf_id, target, change_desc):
    """Apply a verified ToK finding to Kingdom infrastructure.

    This is the ACTUATOR for the integration loop — it translates
    verified knowledge into concrete config changes.

    Returns dict with {applied: bool, files_changed: [], notes: str}
    """
    result = {"applied": False, "files_changed": [], "notes": ""}

    # Load the leaf
    leaf = None
    for dir_path in [INTEGRATED, VERIFIED, LEAVES]:
        f = dir_path / f"{leaf_id}.json"
        if f.exists():
            leaf = load_json(f)
            break

    if not leaf:
        result["notes"] = f"Leaf not found: {leaf_id}"
        return result

    model = leaf.get("model", "unknown")
    assertion = leaf.get("assertion", "")

    if target == "routing":
        # Update model routing recommendations file
        profiles_file = BASELINES / "model-profiles.json"
        profiles = load_json(profiles_file, {"models": {}, "updated": None})

        if model not in profiles["models"]:
            profiles["models"][model] = {"capabilities": [], "weaknesses": [], "routing_notes": []}

        profiles["models"][model]["routing_notes"].append({
            "leaf_id": leaf_id,
            "assertion": assertion,
            "confidence": leaf.get("confidence", 0),
            "added": now_iso(),
        })
        profiles["updated"] = now_iso()
        save_json(profiles_file, profiles)
        result["files_changed"].append(str(profiles_file))
        result["applied"] = True
        result["notes"] = f"Updated model profile for {model}"

    elif target == "config":
        # Write recommendation to a staging file for human review
        rec_file = TOK_BASE / "integration-staging" / f"{leaf_id}-config.json"
        rec_file.parent.mkdir(parents=True, exist_ok=True)
        save_json(rec_file, {
            "leaf_id": leaf_id,
            "target": "config",
            "change": change_desc,
            "model": model,
            "assertion": assertion,
            "status": "pending_review",
            "created": now_iso(),
        })
        result["files_changed"].append(str(rec_file))
        result["applied"] = True
        result["notes"] = f"Config change staged for review: {rec_file.name}"

    elif target == "prompt":
        rec_file = TOK_BASE / "integration-staging" / f"{leaf_id}-prompt.json"
        rec_file.parent.mkdir(parents=True, exist_ok=True)
        save_json(rec_file, {
            "leaf_id": leaf_id,
            "target": "prompt",
            "change": change_desc,
            "model": model,
            "assertion": assertion,
            "status": "pending_review",
            "created": now_iso(),
        })
        result["files_changed"].append(str(rec_file))
        result["applied"] = True
        result["notes"] = f"Prompt change staged for review: {rec_file.name}"

    else:
        # Generic: stage for review
        rec_file = TOK_BASE / "integration-staging" / f"{leaf_id}-{target}.json"
        rec_file.parent.mkdir(parents=True, exist_ok=True)
        save_json(rec_file, {
            "leaf_id": leaf_id,
            "target": target,
            "change": change_desc,
            "model": model,
            "assertion": assertion,
            "status": "pending_review",
            "created": now_iso(),
        })
        result["files_changed"].append(str(rec_file))
        result["applied"] = True
        result["notes"] = f"Change staged for review: {rec_file.name}"

    return result


# ─── ROUTING RECOMMENDATION ───────────────────────────────────────

def get_routing_recommendation(task_type, context=None):
    """Return model recommendation based on verified ToK knowledge.

    This is the CONTROLLER for the routing optimization loop — it
    translates accumulated knowledge into model selection decisions.

    Args:
        task_type: One of "coordinator", "builder", "consultant", "quick_check"
        context: Optional dict with {"idle_count": N, "task_complexity": "low|medium|high"}

    Returns dict with {model, effort, reasoning, confidence, sources}
    """
    context = context or {}
    profiles_file = BASELINES / "model-profiles.json"
    profiles = load_json(profiles_file, {"models": {}})

    # Default routing (current Kingdom strategy)
    defaults = {
        "coordinator": {"model": "claude-opus-4-6", "effort": "high"},
        "builder": {"model": "sonnet", "effort": "medium"},
        "consultant": {"model": "claude-opus-4-6", "effort": "high"},
        "quick_check": {"model": "claude-haiku-4-5-20251001", "effort": "low"},
    }

    rec = defaults.get(task_type, defaults["builder"]).copy()
    rec["reasoning"] = "Default routing (no ToK data)"
    rec["confidence"] = 0.5
    rec["sources"] = []

    if not profiles.get("models"):
        return rec

    # Apply ToK-driven adjustments
    idle_count = context.get("idle_count", 0)

    if task_type == "coordinator" and idle_count >= 2:
        # Check if we have verified knowledge about idle-beat downgrade
        for model_name, model_data in profiles["models"].items():
            for note in model_data.get("routing_notes", []):
                if "idle" in note.get("assertion", "").lower() and "sonnet" in note.get("assertion", "").lower():
                    rec["model"] = "sonnet"
                    rec["effort"] = "medium"
                    rec["reasoning"] = f"ToK-verified: {note['assertion'][:80]}"
                    rec["confidence"] = note.get("confidence", 0.7)
                    rec["sources"].append(note.get("leaf_id", ""))

    complexity = context.get("task_complexity", "medium")
    if task_type == "builder" and complexity == "low":
        # Check if haiku can handle simple builder tasks
        haiku_data = profiles["models"].get("claude-haiku-4-5-20251001", {})
        for note in haiku_data.get("routing_notes", []):
            if "status check" in note.get("assertion", "").lower():
                rec["model"] = "claude-haiku-4-5-20251001"
                rec["effort"] = "low"
                rec["reasoning"] = f"ToK-verified: {note['assertion'][:80]}"
                rec["confidence"] = note.get("confidence", 0.6)
                rec["sources"].append(note.get("leaf_id", ""))

    return rec


# ─── IMPACT ────────────────────────────────────────────────────────

def cmd_impact(args):
    """Record measurable impact of an integrated ToK leaf."""
    if len(args) < 3:
        print("Usage: tok.py impact <leaf-id> <metric> <delta>")
        print("  Metrics: cost_reduction, quality_improvement, latency_reduction, accuracy_gain")
        return

    leaf_id, metric, delta = args[0], args[1], args[2]

    impact_entry = {
        "leaf_id": leaf_id,
        "metric": metric,
        "delta": delta,
        "timestamp": now_iso(),
        "measurer": resolve_instance(),
    }

    # Save impact
    impact_id = gen_id("imp", f"{leaf_id}{metric}")
    save_json(IMPACT / f"{impact_id}.json", impact_entry)

    # Update leaf if found
    for dir_path in [INTEGRATED, VERIFIED, LEAVES]:
        f = dir_path / f"{leaf_id}.json"
        if f.exists():
            leaf = load_json(f)
            if leaf.get("integration"):
                leaf["integration"]["impact"] = {
                    "metric": metric, "delta": delta, "measured": now_iso()
                }
            save_json(f, leaf)
            break

    print(f"Impact recorded: {leaf_id}")
    print(f"  {metric}: {delta}")


# ─── STATUS ────────────────────────────────────────────────────────

def cmd_status(args=None):
    """Show ToK pipeline status."""
    counts = {}
    for name, dir_path in [("harvests", HARVESTS), ("leaves", LEAVES),
                           ("verified", VERIFIED), ("integrated", INTEGRATED),
                           ("impact", IMPACT)]:
        if dir_path.exists():
            entries = [f for f in dir_path.iterdir() if f.suffix == ".json"]
            counts[name] = len(entries)
        else:
            counts[name] = 0

    total = sum(counts.values())

    print(f"\n{'='*50}")
    print(f"  ToK PIPELINE STATUS")
    print(f"{'='*50}\n")

    stages = [
        ("HARVEST", counts["harvests"], "Raw findings from model probing"),
        ("DISTILL", counts["leaves"], "Structured testable assertions"),
        ("VERIFY", counts["verified"], "Consensus-verified knowledge"),
        ("INTEGRATE", counts["integrated"], "Merged into Kingdom infra"),
        ("MEASURE", counts["impact"], "Impact measurements recorded"),
    ]

    for name, count, desc in stages:
        bar_width = min(count, 20)
        bar = "█" * bar_width + "░" * (20 - bar_width)
        print(f"  {name:12s} [{bar}] {count:3d}  {desc}")

    print(f"\n  Total entries: {total}")

    # Show recent activity
    all_files = []
    for dir_path in [HARVESTS, LEAVES, VERIFIED, INTEGRATED, IMPACT]:
        if dir_path.exists():
            for f in dir_path.iterdir():
                if f.suffix == ".json":
                    all_files.append((f.stat().st_mtime, f, dir_path.name))
    all_files.sort(reverse=True)

    if all_files:
        print(f"\n  RECENT ACTIVITY:")
        for mtime, f, stage in all_files[:5]:
            data = load_json(f)
            ts = data.get("timestamp", "?")[:19]
            label = data.get("assertion") or data.get("finding") or data.get("metric") or f.stem
            if len(label) > 50:
                label = label[:47] + "..."
            print(f"    [{stage:12s}] {ts} — {label}")
    print()


# ─── SEARCH ────────────────────────────────────────────────────────

def cmd_search(args):
    """Search across all ToK entries."""
    if not args:
        print("Usage: tok.py search <query>")
        return

    query = " ".join(args).lower()
    results = []

    for dir_path in [HARVESTS, LEAVES, VERIFIED, INTEGRATED]:
        if not dir_path.exists():
            continue
        for f in dir_path.iterdir():
            if f.suffix != ".json":
                continue
            data = load_json(f)
            # Search in multiple fields
            searchable = " ".join(str(v) for v in [
                data.get("finding", ""),
                data.get("assertion", ""),
                data.get("model", ""),
                data.get("domain", ""),
                data.get("notes", ""),
            ]).lower()
            if query in searchable:
                results.append((dir_path.name, data))

    if not results:
        print(f"No results for: {query}")
        return

    print(f"\n  Found {len(results)} matches for '{query}':\n")
    for stage, data in results:
        leaf_id = data.get("id", "?")
        text = data.get("assertion") or data.get("finding") or "?"
        model = data.get("model", "?")
        status = data.get("status", "?")
        print(f"  [{stage:12s}] {leaf_id}")
        print(f"    Model: {model}  |  Status: {status}")
        print(f"    {text[:80]}")
        print()


# ─── PIPELINE (for heartbeat integration) ─────────────────────────

def cmd_pipeline(args=None):
    """Output pipeline health as JSON for heartbeat consumption."""
    counts = {}
    for name, dir_path in [("harvests", HARVESTS), ("leaves", LEAVES),
                           ("verified", VERIFIED), ("integrated", INTEGRATED),
                           ("impact", IMPACT)]:
        if dir_path.exists():
            counts[name] = len([f for f in dir_path.iterdir() if f.suffix == ".json"])
        else:
            counts[name] = 0

    # Identify bottlenecks
    bottleneck = None
    if counts["harvests"] > 0 and counts["leaves"] == 0:
        bottleneck = "distill"
    elif counts["leaves"] > 0 and counts["verified"] == 0:
        bottleneck = "verify"
    elif counts["verified"] > 0 and counts["integrated"] == 0:
        bottleneck = "integrate"
    elif counts["integrated"] > 0 and counts["impact"] == 0:
        bottleneck = "measure"

    result = {
        "counts": counts,
        "total": sum(counts.values()),
        "bottleneck": bottleneck,
        "health": 1.0 if not bottleneck else 0.5,
        "checked": now_iso(),
    }

    print(json.dumps(result, indent=2))
    return result


# ─── MAIN ──────────────────────────────────────────────────────────

COMMANDS = {
    "harvest": cmd_harvest,
    "distill": cmd_distill,
    "verify": cmd_verify,
    "vote": cmd_vote,
    "integrate": cmd_integrate,
    "impact": cmd_impact,
    "status": cmd_status,
    "search": cmd_search,
    "pipeline": cmd_pipeline,
}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    handler = COMMANDS.get(cmd)
    if not handler:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        return

    handler(sys.argv[2:])


if __name__ == "__main__":
    main()
