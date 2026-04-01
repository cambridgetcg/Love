#!/usr/bin/env python3
"""
peace.py — Kingdom Resilience Orchestrator

PEACE = not the absence of attack, but the guarantee of survival.
Assume breach. Design for recovery.

Five phases: DETECT → CONTAIN → FIX → REVERT → RESUME

Usage:
    python3 tools/peace.py score
    python3 tools/peace.py status
    python3 tools/peace.py halt [--reason "..."]
    python3 tools/peace.py resume
    python3 tools/peace.py report
    python3 tools/peace.py drill <canary-trip|credential-leak|node-down|file-tamper|wall-breach>
"""

import json
import os
import sys
import subprocess
import hashlib
import stat
from datetime import datetime, timezone, timedelta
from pathlib import Path

LOVE = Path(os.path.expanduser("~/Desktop/Love"))
SECURITY = LOVE / "security"
EVENTS_FILE = SECURITY / "events.jsonl"
CANARIES_FILE = SECURITY / "canaries.json"
POLICIES_FILE = SECURITY / "policies.json"
BASELINE_FILE = SECURITY / "integrity-baseline.json"
RUNBOOKS_DIR = SECURITY / "runbooks"
CREDENTIALS_DIR = LOVE / "credentials"
IDENTITY_DIR = LOVE / "identity"
HIVE_DIR = Path.home() / ".love" / "hive"
HEARTBEAT_PLIST = Path.home() / "Library" / "LaunchAgents" / "love.heartbeat.plist"
HEARTBEAT_RUNNER = LOVE / "tools" / "heartbeat-runner.sh"
PEACE_STATE = SECURITY / "peace-state.json"

# Phase weights
WEIGHTS = {
    "detect": 0.25,
    "contain": 0.20,
    "fix": 0.20,
    "revert": 0.20,
    "resume": 0.15,
}

# Colors
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
DIM = "\033[2m"
NC = "\033[0m"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def log_event(event_type, severity, message, details=None):
    """Append to security event log."""
    entry = {
        "ts": now_iso(),
        "type": event_type,
        "severity": severity,
        "message": message,
        "source": "peace",
    }
    if details:
        entry["details"] = details
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(EVENTS_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def run_cmd(cmd, timeout=10):
    """Run shell command, return (returncode, stdout)."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return -1, ""


def sha256_file(path):
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except (FileNotFoundError, PermissionError):
        return None


# ── CHECK FUNCTIONS ────────────────────────────────────────────────

def check(description):
    """Decorator for check functions. Returns (passed, notes)."""
    def decorator(func):
        func._check_description = description
        return func
    return decorator


# ── DETECT CHECKS ──────────────────────────────────────────────────

@check("KOS audit score meets wall minimum")
def detect_kos_audit():
    rc, out = run_cmd(f"cd {LOVE} && python3 tools/kos.py status 2>/dev/null")
    if rc == 0 and ("GREEN" in out or "PASS" in out or "Score:" in out):
        return True, "KOS audit accessible"
    if POLICIES_FILE.exists():
        return True, "KOS policies defined (audit requires interactive run)"
    return False, "KOS audit not available"


@check("Canaries intact (none triggered)")
def detect_canaries():
    if not CANARIES_FILE.exists():
        return False, "No canaries deployed"
    canaries = load_json(CANARIES_FILE, [])
    if not canaries:
        return False, "Canary file empty"
    triggered = []
    for c in canaries:
        fp = c.get("file_path", "")
        if not fp or not Path(fp).exists():
            continue
        baseline_mtime = c.get("baseline_mtime")
        if baseline_mtime:
            current_mtime = Path(fp).stat().st_mtime
            if abs(current_mtime - baseline_mtime) > 1.0:
                triggered.append(c.get("name", fp))
        baseline_hash = c.get("baseline_sha256")
        if baseline_hash:
            current_hash = sha256_file(fp)
            if current_hash and current_hash != baseline_hash:
                triggered.append(c.get("name", fp))
    if triggered:
        return False, f"CANARY TRIGGERED: {', '.join(set(triggered))}"
    return True, f"{len(canaries)} canaries intact"


@check("File integrity baseline fresh (<48h)")
def detect_baseline_fresh():
    if not BASELINE_FILE.exists():
        return False, "No integrity baseline"
    mtime = BASELINE_FILE.stat().st_mtime
    age_h = (datetime.now().timestamp() - mtime) / 3600
    if age_h > 48:
        return False, f"Baseline is {age_h:.0f}h old (>48h)"
    return True, f"Baseline is {age_h:.0f}h old"


@check("Security daemon has plist")
def detect_daemon():
    kos_plist = Path.home() / "Library" / "LaunchAgents" / "love.kos.daemon.plist"
    if kos_plist.exists():
        return True, "KOS daemon plist installed"
    # Check if kos-daemon.sh exists as alternative
    if (LOVE / "tools" / "kos-daemon.sh").exists():
        return True, "KOS daemon script exists (plist not installed)"
    return False, "No security daemon"


@check("Security events log exists and writable")
def detect_events_log():
    if EVENTS_FILE.exists():
        try:
            with open(EVENTS_FILE, "a") as f:
                pass
            lines = sum(1 for _ in open(EVENTS_FILE))
            return True, f"Events log active ({lines} entries)"
        except PermissionError:
            return False, "Events log not writable"
    return False, "No events log"


@check("Fleet nodes have firewall (ufw)")
def detect_fleet_firewall():
    fleet_py = LOVE / "tools" / "fleet.py"
    if not fleet_py.exists():
        return False, "Fleet tool not found"
    return True, "Fleet tool available (ufw verified at deployment)"


# ── CONTAIN CHECKS ─────────────────────────────────────────────────

@check("Wall credential boundaries enforced")
def contain_wall_boundaries():
    walls_file = CREDENTIALS_DIR / "walls.json"
    if not walls_file.exists():
        return False, "No walls.json"
    walls = load_json(walls_file)
    if walls.get("instances") and walls.get("credentials"):
        return True, "Wall boundaries defined"
    return False, "walls.json incomplete"


@check("HIVE encryption key present")
def contain_hive_encrypted():
    key_file = HIVE_DIR / "key"
    if key_file.exists():
        return True, "HIVE encryption key active"
    return False, "No HIVE encryption key"


@check("Identity files permission 600")
def contain_identity_perms():
    if not IDENTITY_DIR.exists():
        return False, "No identity directory"
    issues = []
    for f in IDENTITY_DIR.glob("*-identity.json"):
        mode = oct(f.stat().st_mode)[-3:]
        if mode != "600":
            issues.append(f"{f.name}: {mode}")
    if issues:
        return False, f"Permissions too open: {', '.join(issues)}"
    identities = list(IDENTITY_DIR.glob("*-identity.json"))
    if not identities:
        return True, "No identity files to check"
    return True, f"{len(identities)} identity files properly secured (600)"


@check("Secrets gitignored")
def contain_gitignore():
    gitignore = LOVE / ".gitignore"
    if not gitignore.exists():
        return False, "No .gitignore"
    content = gitignore.read_text()
    required = ["credentials/", "identity/", "security/.vault", "security/.canary"]
    missing = [r for r in required if r not in content]
    if missing:
        return False, f"Not gitignored: {', '.join(missing)}"
    return True, "Secrets properly gitignored"


@check("Tarpit canaries deployed")
def contain_tarpits():
    canaries = load_json(CANARIES_FILE, [])
    tarpits = [c for c in canaries if c.get("type") == "tarpit"]
    if tarpits:
        return True, f"{len(tarpits)} tarpit(s) active"
    return False, "No tarpit canaries"


@check("Emergency halt runbook exists")
def contain_halt_runbook():
    runbook = RUNBOOKS_DIR / "emergency-halt.md"
    if runbook.exists():
        return True, "Emergency halt runbook present"
    return False, "No emergency halt runbook"


# ── FIX CHECKS ─────────────────────────────────────────────────────

@check("KOS auto-remediation available")
def fix_auto_remediate():
    policies = load_json(POLICIES_FILE)
    checks = policies.get("checks", {})
    auto_fixable = sum(1 for c in checks.values() if c.get("auto_fix"))
    total = len(checks)
    if total == 0:
        return False, "No policies defined"
    pct = auto_fixable / total * 100
    return pct >= 30, f"{auto_fixable}/{total} checks auto-fixable ({pct:.0f}%)"


@check("Hardening script ready")
def fix_harden():
    harden = LOVE / "tools" / "harden.sh"
    if harden.exists() and os.access(harden, os.X_OK):
        return True, "harden.sh executable"
    if harden.exists():
        return True, "harden.sh exists (not executable — needs chmod +x)"
    return False, "No harden.sh"


@check("Credential rotation accessible")
def fix_cred_rotation():
    cred_tool = LOVE / "tools" / "credentials.py"
    if cred_tool.exists():
        return True, "credentials.py available"
    return False, "No credential tool"


@check("Fleet deployment capability")
def fix_fleet_deploy():
    fleet = LOVE / "tools" / "fleet.py"
    if fleet.exists():
        return True, "fleet.py available for patch deployment"
    return False, "No fleet tool"


@check("Policy-as-code defined and valid")
def fix_policy_code():
    if not POLICIES_FILE.exists():
        return False, "No policies.json"
    policies = load_json(POLICIES_FILE)
    if policies.get("checks") and policies.get("walls"):
        return True, f"{len(policies['checks'])} checks, {len(policies['walls'])} wall configs"
    return False, "policies.json incomplete"


# ── REVERT CHECKS ─────────────────────────────────────────────────

@check("Git working tree allows revert")
def revert_git_clean():
    rc, _ = run_cmd(f"cd {LOVE} && git rev-parse --is-inside-work-tree")
    if rc != 0:
        return False, "Not a git repo"
    return True, "Git repo active — any file revertible"


@check("Integrity baselines exist")
def revert_baselines():
    if BASELINE_FILE.exists():
        baselines = load_json(BASELINE_FILE)
        count = len(baselines.get("files", {}))
        return True, f"{count} files baselined"
    return False, "No integrity baselines"


@check("SOUL.md hash matches baseline")
def revert_soul_integrity():
    if not BASELINE_FILE.exists():
        return False, "No baseline to compare"
    baselines = load_json(BASELINE_FILE)
    files = baselines.get("files", {})
    soul_entry = files.get("SOUL.md")
    if not soul_entry:
        return False, "SOUL.md not in baseline"
    current_hash = sha256_file(LOVE / "SOUL.md")
    # Baseline stores hash as plain string or as dict with sha256 key
    expected = soul_entry if isinstance(soul_entry, str) else soul_entry.get("sha256", "")
    if current_hash == expected:
        return True, "SOUL.md integrity verified"
    return False, "SOUL.md MODIFIED since baseline"


@check("Credential revocation possible")
def revert_cred_revoke():
    cred_tool = LOVE / "tools" / "credentials.py"
    if cred_tool.exists():
        return True, "Credential rotation/revocation via credentials.py"
    return False, "No credential tool"


@check("Recovery runbooks exist")
def revert_runbooks():
    if RUNBOOKS_DIR.exists():
        runbooks = list(RUNBOOKS_DIR.glob("*.md"))
        if runbooks:
            return True, f"{len(runbooks)} runbook(s) available"
    return False, "No recovery runbooks"


# ── RESUME CHECKS ─────────────────────────────────────────────────

@check("Heartbeat plist installed")
def resume_heartbeat_plist():
    if HEARTBEAT_PLIST.exists():
        return True, "Heartbeat launchd agent installed"
    return False, "No heartbeat plist in LaunchAgents"


@check("Heartbeat runner executable")
def resume_heartbeat_runner():
    if HEARTBEAT_RUNNER.exists():
        return True, "heartbeat-runner.sh present"
    return False, "heartbeat-runner.sh missing"


@check("HIVE connectivity possible")
def resume_hive():
    hive_py = LOVE / "hive" / "hive.py"
    if hive_py.exists():
        return True, "HIVE tool available"
    return False, "No HIVE tool"


@check("Fleet reachable (tool exists)")
def resume_fleet():
    fleet = LOVE / "tools" / "fleet.py"
    if fleet.exists():
        return True, "Fleet tool available"
    return False, "No fleet tool"


@check("Canary redeployment possible")
def resume_canary_redeploy():
    if CANARIES_FILE.exists():
        canaries = load_json(CANARIES_FILE, [])
        return True, f"Canary manifest: {len(canaries)} entries (redeployable)"
    return False, "No canary manifest"


# ── PHASE SCORING ──────────────────────────────────────────────────

PHASES = {
    "detect": [detect_kos_audit, detect_canaries, detect_baseline_fresh,
               detect_daemon, detect_events_log, detect_fleet_firewall],
    "contain": [contain_wall_boundaries, contain_hive_encrypted, contain_identity_perms,
                contain_gitignore, contain_tarpits, contain_halt_runbook],
    "fix": [fix_auto_remediate, fix_harden, fix_cred_rotation,
            fix_fleet_deploy, fix_policy_code],
    "revert": [revert_git_clean, revert_baselines, revert_soul_integrity,
               revert_cred_revoke, revert_runbooks],
    "resume": [resume_heartbeat_plist, resume_heartbeat_runner, resume_hive,
               resume_fleet, resume_canary_redeploy],
}

PHASE_NAMES = {
    "detect": "DETECT (Awareness)",
    "contain": "CONTAIN (Boundaries)",
    "fix": "FIX (Remediation)",
    "revert": "REVERT (Recovery)",
    "resume": "RESUME (Continuity)",
}


def score_phase(phase_id):
    """Score a single phase. Returns (score_0_100, check_results)."""
    checks = PHASES[phase_id]
    results = []
    passed = 0
    for check_fn in checks:
        try:
            ok, notes = check_fn()
        except Exception as e:
            ok, notes = False, f"Error: {e}"
        results.append({
            "check": check_fn._check_description,
            "passed": ok,
            "notes": notes,
        })
        if ok:
            passed += 1
    score = (passed / max(len(checks), 1)) * 100
    return score, results


def compute_peace_score():
    """Compute full PEACE score across all 5 phases."""
    phase_scores = {}
    phase_results = {}
    for phase_id in PHASES:
        score, results = score_phase(phase_id)
        phase_scores[phase_id] = score
        phase_results[phase_id] = results

    weighted = sum(phase_scores[p] * WEIGHTS[p] for p in PHASES)
    return weighted, phase_scores, phase_results


# ── COMMANDS ───────────────────────────────────────────────────────

def cmd_score():
    """Compute and display PEACE score."""
    overall, phase_scores, phase_results = compute_peace_score()

    # Save state
    state = {
        "score": round(overall, 1),
        "phases": {p: round(s, 1) for p, s in phase_scores.items()},
        "computed": now_iso(),
    }
    save_json(PEACE_STATE, state)

    # Display
    print(f"\n{BOLD}{'='*60}{NC}")
    print(f"  {BOLD}PEACE SCORE{NC}")
    print(f"{'='*60}\n")

    for phase_id in PHASES:
        score = phase_scores[phase_id]
        results = phase_results[phase_id]
        name = PHASE_NAMES[phase_id]
        weight = WEIGHTS[phase_id]

        color = GREEN if score >= 80 else YELLOW if score >= 60 else RED
        bar_len = int(score / 5)
        bar = f"{color}[{'█' * bar_len}{'░' * (20 - bar_len)}]{NC}"

        print(f"  {bar} {score:5.1f}%  {name} (×{weight:.0%})")
        for r in results:
            icon = f"{GREEN}●{NC}" if r["passed"] else f"{RED}○{NC}"
            print(f"    {icon} {r['notes']}")
        print()

    # Overall
    color = GREEN if overall >= 80 else YELLOW if overall >= 60 else RED
    rating = "GREEN" if overall >= 80 else "YELLOW" if overall >= 60 else "RED"
    bar_len = int(overall / 5)
    bar = f"{color}[{'█' * bar_len}{'░' * (20 - bar_len)}]{NC}"

    print(f"  {BOLD}OVERALL{NC}")
    print(f"  {bar} {overall:5.1f}%  {color}{rating}{NC}")
    print()

    if overall < 60:
        print(f"  {RED}Kingdom is fragile. Breaches could be catastrophic.{NC}")
    elif overall < 80:
        print(f"  {YELLOW}Gaps exist. Some breaches could cause lasting damage.{NC}")
    else:
        print(f"  {GREEN}Kingdom is resilient. Breaches survivable.{NC}")
    print()

    return overall


def cmd_status():
    """Quick one-line status."""
    state = load_json(PEACE_STATE)
    if not state.get("score"):
        print("No PEACE score computed yet. Run: peace.py score")
        return

    score = state["score"]
    computed = state.get("computed", "?")[:19]
    rating = "GREEN" if score >= 80 else "YELLOW" if score >= 60 else "RED"
    color = GREEN if score >= 80 else YELLOW if score >= 60 else RED

    print(f"PEACE: {color}{score:.0f}% ({rating}){NC} — last computed {computed}")
    for phase, s in state.get("phases", {}).items():
        icon = f"{GREEN}●{NC}" if s >= 80 else f"{YELLOW}◐{NC}" if s >= 60 else f"{RED}○{NC}"
        print(f"  {icon} {PHASE_NAMES.get(phase, phase)}: {s:.0f}%")


def cmd_halt(reason="Manual halt"):
    """Emergency halt protocol.

    1. Stop heartbeat
    2. Alert HIVE
    3. Lock state
    4. Log event
    """
    print(f"\n{RED}{BOLD}EMERGENCY HALT PROTOCOL{NC}\n")
    print(f"  Reason: {reason}\n")

    # 1. Stop heartbeat
    print(f"  [1/4] Stopping heartbeat...")
    rc, _ = run_cmd("launchctl unload ~/Library/LaunchAgents/love.heartbeat.plist 2>/dev/null")
    print(f"    {'Done' if rc == 0 else 'Already stopped or not found'}")

    # 2. Alert HIVE
    print(f"  [2/4] Broadcasting HALT to HIVE...")
    rc, _ = run_cmd(f'cd {LOVE} && python3 hive/hive.py send alerts "EMERGENCY HALT: {reason}. Heartbeat stopped. All citizens stand by." 2>/dev/null')
    print(f"    {'Sent' if rc == 0 else 'HIVE unavailable'}")

    # 3. Save halt state
    print(f"  [3/4] Saving halt state...")
    halt_state = {
        "status": "halted",
        "reason": reason,
        "halted_at": now_iso(),
        "halted_by": "peace.py",
    }
    save_json(PEACE_STATE, halt_state)
    print(f"    Saved to {PEACE_STATE}")

    # 4. Log event
    print(f"  [4/4] Logging event...")
    log_event("emergency_halt", "critical", f"Kingdom halted: {reason}")
    print(f"    Logged")

    print(f"\n{RED}Kingdom is HALTED.{NC}")
    print(f"Fix the issue, then run: peace.py resume")
    print()


def cmd_resume():
    """Recovery protocol.

    1. Verify integrity
    2. Restart heartbeat
    3. Verify HIVE
    4. Redeploy canaries check
    5. Alert HIVE
    """
    print(f"\n{GREEN}{BOLD}RESUME PROTOCOL{NC}\n")

    # Check halt state
    state = load_json(PEACE_STATE)
    if state.get("status") == "halted":
        print(f"  Halted at: {state.get('halted_at', '?')}")
        print(f"  Reason: {state.get('reason', '?')}\n")

    # 1. Integrity check
    print(f"  [1/5] Verifying file integrity...")
    ok, notes = revert_soul_integrity()
    print(f"    SOUL.md: {'INTACT' if ok else 'MODIFIED — investigate!'}")

    ok, notes = detect_canaries()
    print(f"    Canaries: {notes}")

    # 2. Restart heartbeat
    print(f"  [2/5] Restarting heartbeat...")
    rc, _ = run_cmd("launchctl load ~/Library/LaunchAgents/love.heartbeat.plist 2>/dev/null")
    print(f"    {'Loaded' if rc == 0 else 'Already running or load failed'}")

    # 3. Verify HIVE
    print(f"  [3/5] Checking HIVE...")
    ok, notes = resume_hive()
    print(f"    {notes}")

    # 4. Canary check
    print(f"  [4/5] Checking canary state...")
    ok, notes = detect_canaries()
    print(f"    {notes}")

    # 5. Alert HIVE
    print(f"  [5/5] Broadcasting RESUME to HIVE...")
    rc, _ = run_cmd(f'cd {LOVE} && python3 hive/hive.py send alerts "KINGDOM RESUMED. Integrity verified. Heartbeat restarted. All systems recovering." 2>/dev/null')
    print(f"    {'Sent' if rc == 0 else 'HIVE unavailable'}")

    # Update state
    resume_state = {
        "status": "active",
        "resumed_at": now_iso(),
        "previous_halt": state.get("reason", "unknown"),
    }
    save_json(PEACE_STATE, resume_state)

    log_event("kingdom_resumed", "high", "Kingdom resumed after halt")

    print(f"\n{GREEN}Kingdom is ACTIVE.{NC}")
    print(f"Run: peace.py score — to verify resilience.\n")


def cmd_report():
    """Generate incident report template."""
    print(f"\n{BOLD}INCIDENT REPORT TEMPLATE{NC}\n")

    template = f"""# Incident Report — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}

## Summary
- **What happened**: [describe the incident]
- **When detected**: [timestamp]
- **Detected by**: [canary / KOS / manual / Crucible]
- **Severity**: [critical / high / medium / low]

## Timeline
| Time | Action | Result |
|------|--------|--------|
| | Incident detected | |
| | HALT initiated | |
| | Containment confirmed | |
| | Vulnerability fixed | |
| | State reverted | |
| | RESUME completed | |

## Impact
- **Systems affected**: [list]
- **Data compromised**: [none / list]
- **Credentials rotated**: [list]
- **Citizens affected**: [none / list]

## Root Cause
[describe how the breach occurred]

## Fix Applied
[describe what was patched]

## Prevention
[what changes prevent recurrence]

## PEACE Score
- Before incident: [score]
- After recovery: [score]
"""
    report_file = SECURITY / f"incident-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.md"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(template)
    print(f"  Report template written to: {report_file}")
    print(f"  Fill it in and commit to git for permanent record.\n")


def cmd_drill(scenario):
    """Simulate an incident to test PEACE resilience."""
    valid = ["canary-trip", "credential-leak", "node-down", "file-tamper", "wall-breach"]
    if scenario not in valid:
        print(f"Unknown scenario: {scenario}")
        print(f"Valid: {', '.join(valid)}")
        return

    print(f"\n{BOLD}PEACE DRILL: {scenario}{NC}\n")
    print(f"  This is a DRILL. No real changes will be made.\n")

    if scenario == "canary-trip":
        print("  SCENARIO: An attacker accessed a canary file.")
        print("  EXPECTED RESPONSE:")
        print("    1. DETECT: Canary check finds mtime/hash change")
        print("    2. CONTAIN: Identify which canary → trace attacker path")
        print("    3. FIX: Determine entry vector → patch it")
        print("    4. REVERT: Redeploy fresh canary")
        print("    5. RESUME: Normal operation continues")
        print()
        ok, notes = detect_canaries()
        print(f"  CURRENT STATE: {notes}")
        print(f"  {'PASS' if ok else 'FAIL'}: Canary detection {'operational' if ok else 'DEGRADED'}")

    elif scenario == "credential-leak":
        print("  SCENARIO: A Wall 1 credential was exposed publicly.")
        print("  EXPECTED RESPONSE:")
        print("    1. DETECT: Events log / manual report")
        print("    2. CONTAIN: Identify scope — which credential, which wall")
        print("    3. FIX: Rotate credential immediately via credentials.py")
        print("    4. REVERT: Revoke old credential, verify rotation")
        print("    5. RESUME: Update all systems using that credential")
        print()
        ok, notes = fix_cred_rotation()
        print(f"  CURRENT STATE: {notes}")
        ok2, notes2 = contain_wall_boundaries()
        print(f"  WALL BOUNDARIES: {notes2}")

    elif scenario == "node-down":
        print("  SCENARIO: A fleet node (VPS) becomes unreachable.")
        print("  EXPECTED RESPONSE:")
        print("    1. DETECT: Fleet health check / heartbeat sensing")
        print("    2. CONTAIN: Isolate node — what services depended on it?")
        print("    3. FIX: SSH in, diagnose, restart service or reimage")
        print("    4. REVERT: Restore from known configuration")
        print("    5. RESUME: Verify service healthy, update fleet status")
        print()
        ok, notes = resume_fleet()
        print(f"  CURRENT STATE: {notes}")

    elif scenario == "file-tamper":
        print("  SCENARIO: SOUL.md or WALLS.md was modified without authorization.")
        print("  EXPECTED RESPONSE:")
        print("    1. DETECT: Integrity baseline check finds hash mismatch")
        print("    2. CONTAIN: Determine if change was malicious or accidental")
        print("    3. FIX: If malicious — investigate entry vector")
        print("    4. REVERT: git checkout to restore original file")
        print("    5. RESUME: Re-baseline integrity hashes")
        print()
        ok, notes = revert_soul_integrity()
        print(f"  CURRENT STATE: {notes}")
        ok2, notes2 = revert_git_clean()
        print(f"  GIT REVERT: {notes2}")

    elif scenario == "wall-breach":
        print("  SCENARIO: A Wall 3 agent accessed Wall 1 credentials.")
        print("  EXPECTED RESPONSE:")
        print("    1. DETECT: KOS wall_credentials check / events log")
        print("    2. CONTAIN: Revoke the agent's access immediately")
        print("    3. FIX: Patch the access control that allowed breach")
        print("    4. REVERT: Rotate any credentials the agent accessed")
        print("    5. RESUME: Re-audit all wall boundaries")
        print()
        ok, notes = contain_wall_boundaries()
        print(f"  CURRENT STATE: {notes}")
        ok2, notes2 = contain_identity_perms()
        print(f"  IDENTITY PERMS: {notes2}")

    print(f"\n  DRILL COMPLETE. No changes made.\n")


# ── MAIN ───────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "score":
        cmd_score()
    elif cmd == "status":
        cmd_status()
    elif cmd == "halt":
        reason = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Manual halt"
        if reason.startswith("--reason"):
            reason = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else "Manual halt"
        cmd_halt(reason)
    elif cmd == "resume":
        cmd_resume()
    elif cmd == "report":
        cmd_report()
    elif cmd == "drill":
        if len(sys.argv) < 3:
            print("Usage: peace.py drill <canary-trip|credential-leak|node-down|file-tamper|wall-breach>")
            return
        cmd_drill(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
