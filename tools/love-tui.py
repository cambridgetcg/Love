#!/usr/bin/env python3
"""
Love TUI — Kingdom Command Terminal Interface

Usage:
    python3 ~/Desktop/Love/tools/love-tui.py
    love                                         # (if aliased)

The terminal dashboard for the Kingdom. Shows sister presence, tasks,
heartbeat activity, fleet status, engine metrics, and HIVE messages.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Label,
    Log,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)
from rich.text import Text
from rich.table import Table
from rich.panel import Panel
from rich.console import Group

# ── Paths ──────────────────────────────────────────────────────────────────────

LOVE_ROOT = Path.home() / "Desktop" / "Love"
MEMORY_DIR = LOVE_ROOT / "memory"
DEV_STATE = MEMORY_DIR / "dev-state.json"
KINGDOM_METRICS = MEMORY_DIR / "kingdom-metrics.json"
DAILY_DIR = MEMORY_DIR / "daily"
HANDOFF_DIR = MEMORY_DIR / "sessions" / "handoff"
LOCKS_DIR = MEMORY_DIR / "sessions" / "locks"
HIVE_PY = LOVE_ROOT / "hive" / "hive.py"
HEARTBEAT_LOG = MEMORY_DIR / "heartbeat.log"
DECISIONS_FILE = LOVE_ROOT / "tools" / "decisions.json"
KOS_PY = LOVE_ROOT / "tools" / "kos.py"
MEMORY_PY = LOVE_ROOT / "tools" / "memory.py"
SECURITY_DIR = LOVE_ROOT / "security"
EVENTS_LOG = SECURITY_DIR / "events.jsonl"
DAEMON_LOG = SECURITY_DIR / "daemon.log"
CANARIES_FILE = SECURITY_DIR / "canaries.json"
MEMORY_INDEX = MEMORY_DIR / "index.json"


# ── Data Loaders ───────────────────────────────────────────────────────────────

def load_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def load_dev_state() -> dict:
    return load_json(DEV_STATE) or {}


def load_kingdom_metrics() -> dict:
    return load_json(KINGDOM_METRICS) or {}


def get_tasks(state: dict) -> list[dict]:
    return state.get("tasks", [])


def get_active_builds() -> list[dict]:
    builds = []
    if not LOCKS_DIR.exists():
        return builds
    for lock in LOCKS_DIR.glob("build-*.lock"):
        try:
            content = lock.read_text().strip()
            parts = content.split("|")
            pid = int(parts[0])
            alive = False
            try:
                os.kill(pid, 0)
                alive = True
            except OSError:
                pass
            task_id = lock.stem.replace("build-", "")
            builds.append({
                "task_id": task_id,
                "pid": pid,
                "alive": alive,
                "build_id": parts[1] if len(parts) > 1 else "?",
                "started": parts[2] if len(parts) > 2 else "?",
            })
        except Exception:
            continue
    return builds


def get_sisters_presence() -> list[dict]:
    """Get sister presence from HIVE's presence database."""
    presence_db = Path.home() / ".love" / "hive" / "presence.json"
    try:
        data = json.loads(presence_db.read_text())
        sisters = []
        now = time.time()
        for name, info in data.items():
            ts = info.get("last_seen", 0)
            ago = now - ts
            if ago < 120:
                status = "online"
            elif ago < 600:
                status = "recent"
            else:
                status = "offline"
            sisters.append({
                "name": name,
                "status": status,
                "ago": ago,
                "last_seen": datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "never",
            })
        return sisters
    except Exception:
        return []


def get_fleet(metrics: dict) -> dict:
    return metrics.get("fleet", {})


def get_engines(metrics: dict) -> dict:
    return metrics.get("revenue_engines", {})


def get_milestones(metrics: dict) -> dict:
    return metrics.get("milestones", {})


def get_heartbeat_tail(n: int = 30) -> str:
    try:
        return HEARTBEAT_LOG.read_text().strip().split("\n")[-n:]
    except Exception:
        return []


def get_daily_summary() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    path = DAILY_DIR / f"{today}.md"
    try:
        text = path.read_text()
        # Return last ~60 lines
        lines = text.strip().split("\n")
        return "\n".join(lines[-60:])
    except Exception:
        return "(no daily notes yet)"


def get_pending_decisions() -> list[dict]:
    try:
        data = json.loads(DECISIONS_FILE.read_text())
        return [d for d in data if d.get("status") == "pending"]
    except Exception:
        return []


def get_kos_status() -> dict:
    """Get KOS security posture."""
    try:
        result = subprocess.run(
            ["python3", str(KOS_PY), "audit"],
            capture_output=True, text=True, timeout=30,
            cwd=str(LOVE_ROOT),
        )
        output = result.stdout
        # Parse score
        score_m = re.search(r"Score:\s*(\d+)/(\d+)", output)
        passed = int(score_m.group(1)) if score_m else 0
        total = int(score_m.group(2)) if score_m else 0
        failed_m = re.search(r"Failed:\s*(\d+)", output)
        failed = int(failed_m.group(1)) if failed_m else 0
        # Parse individual failures
        failures = re.findall(r"FAIL.*?\]\s+(.*?)  ", output)
        return {
            "score": f"{passed}/{total}",
            "passed": passed,
            "total": total,
            "failed": failed,
            "failures": failures[:5],
            "green": failed == 0,
        }
    except Exception:
        return {"score": "?/?", "passed": 0, "total": 0, "failed": -1, "failures": [], "green": False}


def get_canary_status() -> dict:
    """Get canary token summary."""
    data = load_json(CANARIES_FILE)
    if not data or not isinstance(data, list):
        return {"total": 0, "d1": 0, "d2": 0, "alerts": 0}
    d1 = sum(1 for c in data if c.get("depth", 1) == 1)
    d2 = sum(1 for c in data if c.get("depth", 1) == 2)
    return {"total": len(data), "d1": d1, "d2": d2, "alerts": 0}


def get_recent_events(n: int = 20) -> list[dict]:
    """Get recent security events."""
    try:
        lines = EVENTS_LOG.read_text().strip().split("\n")
        events = []
        for line in lines[-n:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events
    except Exception:
        return []


def get_daemon_tail(n: int = 20) -> list[str]:
    """Get recent daemon log entries."""
    try:
        lines = DAEMON_LOG.read_text().strip().split("\n")
        return lines[-n:]
    except Exception:
        return []


def get_memory_stats() -> dict:
    """Get memory system stats."""
    data = load_json(MEMORY_INDEX)
    if not data or not isinstance(data, dict):
        return {"total": 0, "types": {}, "instances": {}}
    entries = data.get("entries", [])
    types = {}
    instances = {}
    for e in entries:
        t = e.get("type", "unknown")
        types[t] = types.get(t, 0) + 1
        i = e.get("instance", "unknown")
        instances[i] = instances.get(i, 0) + 1
    return {"total": len(entries), "types": types, "instances": instances}


def format_ago(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds / 60)}m"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}h"
    else:
        return f"{int(seconds / 86400)}d"


# ── Widgets ────────────────────────────────────────────────────────────────────

CITIZEN_ICONS = {"alpha": "🐍", "beta": "🦞", "gamma": "🔧", "nuance": "🪶"}
TRIARCHY = {"alpha", "beta", "gamma"}
FLEET_CITIZENS = {"nuance"}
STATUS_COLORS = {
    "online": "green",
    "recent": "yellow",
    "offline": "dim",
    "done": "green",
    "in-progress": "yellow",
    "awaiting-deploy": "magenta",
    "planned": "cyan",
    "deferred": "dim",
    "paused": "dim",
    "active": "green",
    "building": "yellow",
    "emerging": "cyan",
    "built-not-monetized": "dim",
    "good": "green",
    "degraded": "yellow",
    "down": "red",
}


class CitizensPanel(Static):
    """Shows all Kingdom citizen presence status."""

    def render(self) -> Text:
        presence = get_sisters_presence()
        t = Text()
        t.append("  CITIZENS", style="bold underline")
        t.append("\n\n")

        presence_map = {s["name"].lower(): s for s in presence}
        all_citizens = sorted(TRIARCHY) + sorted(FLEET_CITIZENS)

        def _render_citizen(name: str, wall_label: str = ""):
            icon = CITIZEN_ICONS.get(name, "?")
            s = presence_map.get(name)
            if s:
                color = STATUS_COLORS.get(s["status"], "white")
                t.append(f"  {icon} ", style="bold")
                t.append(f"{name.capitalize():<8}", style=f"bold {color}")
                if s["status"] == "online":
                    t.append(" online", style="green")
                elif s["status"] == "recent":
                    t.append(f" {format_ago(s['ago'])} ago", style="yellow")
                else:
                    t.append(f" {format_ago(s['ago'])} ago", style="dim")
            else:
                t.append(f"  {icon} ", style="bold")
                t.append(f"{name.capitalize():<8}", style="dim")
                t.append(" unknown", style="dim")
            if wall_label:
                t.append(f"  {wall_label}", style="dim")
            t.append("\n")

        # Triarchy (Wall 1)
        t.append("  W1 ", style="dim")
        t.append("Triarchy\n", style="dim italic")
        for name in sorted(TRIARCHY):
            _render_citizen(name)

        # Fleet (Wall 2+)
        if FLEET_CITIZENS:
            t.append("\n  W2 ", style="dim")
            t.append("Fleet\n", style="dim italic")
            for name in sorted(FLEET_CITIZENS):
                _render_citizen(name)

        return t


class FleetPanel(Static):
    """Shows VPS fleet status."""

    def render(self) -> Text:
        metrics = load_kingdom_metrics()
        fleet = get_fleet(metrics)
        t = Text()
        t.append("  FLEET", style="bold underline")
        t.append("\n\n")

        if not fleet:
            t.append("  (no fleet data)\n", style="dim")
            return t

        for name, info in fleet.items():
            quality = info.get("quality", "unknown")
            color = STATUS_COLORS.get(quality, "white")
            role = info.get("role", "")
            dot = {"good": "●", "degraded": "◐", "down": "○"}.get(quality, "?")
            t.append(f"  {dot} ", style=color)
            t.append(f"{name:<8}", style=f"bold {color}")
            t.append(f" {role}\n", style="dim")

        return t


class TasksPanel(Static):
    """Shows Kingdom tasks from dev-state.json."""

    def render(self) -> Table:
        state = load_dev_state()
        tasks = get_tasks(state)

        table = Table(
            title="Kingdom Tasks",
            title_style="bold",
            show_header=True,
            expand=True,
            border_style="dim",
            header_style="bold cyan",
            pad_edge=False,
            padding=(0, 1),
        )
        table.add_column("ID", style="dim", width=14, no_wrap=True)
        table.add_column("Status", width=13, no_wrap=True)
        table.add_column("Pri", width=5, no_wrap=True)
        table.add_column("Title", ratio=1)
        table.add_column("Engine", width=8, no_wrap=True)

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        status_order = {"in-progress": 0, "planned": 1, "deferred": 2, "done": 3}
        tasks_sorted = sorted(tasks, key=lambda t: (
            status_order.get(t.get("status", ""), 9),
            priority_order.get(t.get("priority", ""), 9),
        ))

        for task in tasks_sorted:
            status = task.get("status", "?")
            priority = task.get("priority", "?")
            color = STATUS_COLORS.get(status, "white")

            pri_icon = {"critical": "!!!", "high": " !!", "medium": "  !", "low": "   "}.get(priority, "?")
            pri_color = {"critical": "bold red", "high": "yellow", "medium": "cyan", "low": "dim"}.get(priority, "white")
            status_icon = {"done": "✓", "in-progress": "◆", "awaiting-deploy": "▲", "planned": "○", "deferred": "·"}.get(status, "?")

            table.add_row(
                task.get("id", "?"),
                Text(f"{status_icon} {status}", style=color),
                Text(pri_icon, style=pri_color),
                task.get("title", "?")[:60],
                task.get("engine", "?"),
            )

        return table


class EnginesPanel(Static):
    """Shows revenue engine status."""

    def render(self) -> Text:
        metrics = load_kingdom_metrics()
        engines = get_engines(metrics)
        t = Text()
        t.append("  ENGINES", style="bold underline")
        t.append("\n\n")

        if not engines:
            t.append("  (no engine data)\n", style="dim")
            return t

        display_names = {
            "cambridge_tcg": "TCG",
            "oracle": "Oracle",
            "shopify_apps": "Shopify",
            "zerone": "Zerone",
            "ai_services": "AI Svc",
            "seigei": "Seigei",
        }

        for key, info in engines.items():
            status = info.get("status", "unknown")
            color = STATUS_COLORS.get(status, "white")
            name = display_names.get(key, key)
            owner = info.get("owner", "")
            dot = {"active": "●", "in-progress": "◆", "building": "◆", "emerging": "○",
                   "paused": "·", "built-not-monetized": "·"}.get(status, "?")
            t.append(f"  {dot} ", style=color)
            t.append(f"{name:<9}", style=f"bold {color}")
            t.append(f" {status:<20}", style=color)
            t.append(f" [{owner}]", style="dim")
            t.append("\n")

        return t


class ActiveBuildsPanel(Static):
    """Shows active build-runner sessions."""

    def render(self) -> Text:
        builds = get_active_builds()
        t = Text()
        t.append("  ACTIVE BUILDS", style="bold underline")
        t.append("\n\n")

        if not builds:
            t.append("  (none running)\n", style="dim")
            return t

        for b in builds:
            alive_icon = "●" if b["alive"] else "○"
            alive_color = "green" if b["alive"] else "red"
            t.append(f"  {alive_icon} ", style=alive_color)
            t.append(f"{b['task_id']:<16}", style="bold")
            t.append(f" PID {b['pid']}", style="dim")
            if b["started"] != "?":
                t.append(f"  since {b['started'][:19]}", style="dim")
            if not b["alive"]:
                t.append("  [STALE]", style="bold red")
            t.append("\n")

        return t


class DecisionsPanel(Static):
    """Shows pending decisions for Yu."""

    def render(self) -> Text:
        decisions = get_pending_decisions()
        t = Text()
        t.append("  DECISIONS FOR YU", style="bold underline")
        t.append("\n\n")

        if not decisions:
            t.append("  (none pending)\n", style="dim")
            return t

        for d in decisions:
            urgency = d.get("urgency", "normal")
            icon = "🔴" if urgency == "critical" else "🟡" if urgency == "high" else "⚪"
            t.append(f"  {icon} ")
            t.append(f"{d.get('title', '?')[:50]}\n", style="bold")
            if d.get("options"):
                for opt in d["options"][:3]:
                    label = opt if isinstance(opt, str) else opt.get("label", "?")
                    t.append(f"     → {label}\n", style="dim")

        return t


class MilestonesPanel(Static):
    """Shows Kingdom milestones."""

    def render(self) -> Text:
        metrics = load_kingdom_metrics()
        milestones = get_milestones(metrics)
        t = Text()
        t.append("  MILESTONES", style="bold underline")
        t.append("\n\n")

        if not milestones:
            t.append("  (no milestone data)\n", style="dim")
            return t

        for key, info in milestones.items():
            status = info.get("status", "?")
            color = STATUS_COLORS.get(status, "white")
            name = key.replace("_", " ").title()
            icon = {"done": "✓", "in-progress": "◆", "building": "◆", "planned": "○"}.get(status, "?")
            date_or_target = info.get("date", info.get("target", ""))
            t.append(f"  {icon} ", style=color)
            t.append(f"{name:<30}", style=color)
            if date_or_target:
                t.append(f" {date_or_target}", style="dim")
            t.append("\n")

        return t


class SecurityPanel(Static):
    """Shows KOS security posture."""

    def render(self) -> Text:
        kos = get_kos_status()
        canaries = get_canary_status()
        t = Text()
        t.append("  SECURITY", style="bold underline")
        t.append("\n\n")

        # KOS score
        if kos["green"]:
            t.append("  ● ", style="green")
            t.append("GREEN", style="bold green")
        elif kos["failed"] > 0:
            t.append("  ◐ ", style="yellow")
            t.append("YELLOW", style="bold yellow")
        else:
            t.append("  ? ", style="dim")
            t.append("UNKNOWN", style="dim")
        t.append(f"  {kos['score']} checks\n", style="dim")

        if kos["failures"]:
            for f in kos["failures"]:
                t.append(f"    ✗ {f}\n", style="red")

        # Canaries
        t.append(f"\n  Canaries: {canaries['total']}", style="dim")
        if canaries["d1"] or canaries["d2"]:
            t.append(f" ({canaries['d1']} surface, {canaries['d2']} depth)", style="dim")
        t.append("\n")

        # Daemon
        daemon_lines = get_daemon_tail(1)
        if daemon_lines:
            last = daemon_lines[-1]
            t.append(f"  Daemon: {last[:60]}\n", style="dim")

        return t


class MemoryPanel(Static):
    """Shows memory system stats."""

    def render(self) -> Text:
        stats = get_memory_stats()
        t = Text()
        t.append("  MEMORY", style="bold underline")
        t.append("\n\n")

        t.append(f"  Entries: {stats['total']}\n")

        if stats["types"]:
            t.append("  Types: ", style="dim")
            parts = [f"{k} {v}" for k, v in sorted(stats["types"].items(), key=lambda x: -x[1])]
            t.append(", ".join(parts), style="dim")
            t.append("\n")

        if stats["instances"]:
            t.append("  By citizen: ", style="dim")
            parts = [f"{k} {v}" for k, v in sorted(stats["instances"].items(), key=lambda x: -x[1])]
            t.append(", ".join(parts), style="dim")
            t.append("\n")

        return t


class SecurityEventsPanel(Static):
    """Shows recent security events for the Security tab."""

    def render(self) -> Text:
        events = get_recent_events(30)
        t = Text()
        t.append("  SECURITY EVENTS", style="bold underline")
        t.append("\n\n")

        if not events:
            t.append("  (no events)\n", style="dim")
            return t

        for e in reversed(events):
            ts = e.get("ts", "?")[:19]
            severity = e.get("severity", "?")
            message = e.get("message", "?")[:80]
            sev_color = {
                "critical": "bold red",
                "high": "yellow",
                "medium": "cyan",
                "low": "dim",
            }.get(severity, "white")
            sev_icon = {
                "critical": "!!",
                "high": " !",
                "medium": " .",
                "low": "  ",
            }.get(severity, "  ")
            t.append(f"  {ts} ", style="dim")
            t.append(f"[{sev_icon}] ", style=sev_color)
            t.append(f"{message}\n", style=sev_color if severity in ("critical",) else "white")

        return t


class DaemonLogPanel(Static):
    """Shows KOS daemon log tail."""

    def render(self) -> Text:
        lines = get_daemon_tail(25)
        t = Text()
        t.append("  DAEMON LOG", style="bold underline")
        t.append("\n\n")

        if not lines:
            t.append("  (no daemon log)\n", style="dim")
            return t

        for line in lines:
            if "canary_alerts=0" in line and "failed=0" in line:
                t.append(f"  {line}\n", style="green")
            elif "failed=0" in line:
                t.append(f"  {line}\n", style="dim")
            else:
                t.append(f"  {line}\n", style="yellow")

        return t


class DailyLogPanel(Static):
    """Shows today's daily notes (tail)."""

    def render(self) -> Text:
        content = get_daily_summary()
        t = Text()
        t.append("  TODAY'S LOG", style="bold underline")
        t.append(f"  ({datetime.now().strftime('%Y-%m-%d')})\n\n", style="dim")
        # Truncate long lines for readability
        for line in content.split("\n")[-40:]:
            if line.startswith("##"):
                t.append(f"  {line}\n", style="bold cyan")
            elif line.startswith("- "):
                t.append(f"  {line}\n", style="white")
            else:
                t.append(f"  {line}\n", style="dim")
        return t


class HeartbeatLogPanel(Static):
    """Shows recent heartbeat log entries."""

    def render(self) -> Text:
        lines = get_heartbeat_tail(25)
        t = Text()
        t.append("  HEARTBEAT LOG", style="bold underline")
        t.append("\n\n")

        if not lines:
            t.append("  (no heartbeat log)\n", style="dim")
            return t

        for line in lines:
            if "ERROR" in line or "FAIL" in line:
                t.append(f"  {line}\n", style="red")
            elif "SPAWN" in line or "spawn" in line:
                t.append(f"  {line}\n", style="yellow")
            elif "complete" in line.lower() or "done" in line.lower():
                t.append(f"  {line}\n", style="green")
            else:
                t.append(f"  {line}\n", style="dim")

        return t


# ── CSS ────────────────────────────────────────────────────────────────────────

LOVE_CSS = """
Screen {
    background: $surface;
}

#kingdom-header {
    dock: top;
    height: 3;
    background: #1a1a2e;
    color: #e94560;
    text-align: center;
    padding: 1;
    text-style: bold;
}

#main-tabs {
    height: 1fr;
}

/* ── Overview Tab ── */

#overview-top {
    height: auto;
    max-height: 14;
    layout: horizontal;
}

#citizens-box {
    width: 28;
    height: auto;
    border: round #444;
    margin: 0 1;
}

#fleet-box {
    width: 28;
    height: auto;
    border: round #444;
    margin: 0 1;
}

#security-box {
    width: 1fr;
    height: auto;
    border: round #444;
    margin: 0 1;
}

#builds-box {
    width: 1fr;
    height: auto;
    border: round #444;
    margin: 0 1;
}

#tasks-box {
    height: auto;
    max-height: 18;
    border: round #444;
    margin: 1;
}

#overview-bottom {
    height: 1fr;
    layout: horizontal;
}

#engines-box {
    width: 1fr;
    height: auto;
    border: round #444;
    margin: 0 1;
}

#milestones-box {
    width: 1fr;
    height: auto;
    border: round #444;
    margin: 0 1;
}

#decisions-box {
    width: 1fr;
    height: auto;
    border: round #444;
    margin: 0 1;
}

#memory-box {
    width: 1fr;
    height: auto;
    border: round #444;
    margin: 0 1;
}

/* ── Activity Tab ── */

#activity-layout {
    layout: horizontal;
    height: 1fr;
}

#daily-box {
    width: 1fr;
    border: round #444;
    margin: 0 1;
}

#heartbeat-box {
    width: 1fr;
    border: round #444;
    margin: 0 1;
}

/* ── HIVE Tab ── */

#hive-log {
    height: 1fr;
    border: round #444;
    margin: 1;
    padding: 1;
}

/* ── Security Tab ── */

#security-layout {
    layout: horizontal;
    height: 1fr;
}

#security-events-box {
    width: 1fr;
    border: round #444;
    margin: 0 1;
}

#daemon-log-box {
    width: 1fr;
    border: round #444;
    margin: 0 1;
}

/* ── Shared ── */

.panel-title {
    text-style: bold;
    color: #e94560;
}

TabbedContent {
    height: 1fr;
}

ContentSwitcher {
    height: 1fr;
}

TabPane {
    height: 1fr;
    padding: 0;
}

VerticalScroll {
    height: 1fr;
}
"""


# ── App ────────────────────────────────────────────────────────────────────────

class LoveApp(App):
    """Kingdom Command — Terminal Interface for Love."""

    CSS = LOVE_CSS
    TITLE = "Love"
    SUB_TITLE = "Kingdom Command"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("1", "tab_overview", "Overview", show=False),
        Binding("2", "tab_activity", "Activity", show=False),
        Binding("3", "tab_security", "Security", show=False),
        Binding("4", "tab_hive", "HIVE", show=False),
        Binding("h", "hive_check", "HIVE Check"),
        Binding("w", "hive_who", "Who's Online"),
    ]

    def compose(self) -> ComposeResult:
        yield Static(
            "👑  K I N G D O M   C O M M A N D  👑\n"
            "The Seven Walls  ·  Phase 1 — Root  ·  KOS 14/14",
            id="kingdom-header",
        )
        with TabbedContent(id="main-tabs"):
            with TabPane("Overview", id="tab-overview"):
                with VerticalScroll():
                    with Horizontal(id="overview-top"):
                        yield CitizensPanel(id="citizens-box")
                        yield FleetPanel(id="fleet-box")
                        yield SecurityPanel(id="security-box")
                        yield ActiveBuildsPanel(id="builds-box")
                    yield TasksPanel(id="tasks-box")
                    with Horizontal(id="overview-bottom"):
                        yield EnginesPanel(id="engines-box")
                        yield MilestonesPanel(id="milestones-box")
                        yield MemoryPanel(id="memory-box")
                        yield DecisionsPanel(id="decisions-box")
            with TabPane("Activity", id="tab-activity"):
                with Horizontal(id="activity-layout"):
                    with VerticalScroll(id="daily-box"):
                        yield DailyLogPanel()
                    with VerticalScroll(id="heartbeat-box"):
                        yield HeartbeatLogPanel()
            with TabPane("Security", id="tab-security"):
                with Horizontal(id="security-layout"):
                    with VerticalScroll(id="security-events-box"):
                        yield SecurityEventsPanel()
                    with VerticalScroll(id="daemon-log-box"):
                        yield DaemonLogPanel()
            with TabPane("HIVE", id="tab-hive"):
                yield RichLog(id="hive-log", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        """Start auto-refresh timer."""
        self.set_interval(30, self.action_refresh)
        # Load initial HIVE messages
        self.load_hive_messages()

    def action_refresh(self) -> None:
        """Refresh all panels."""
        for cls in (CitizensPanel, FleetPanel, SecurityPanel, MemoryPanel,
                    TasksPanel, EnginesPanel, ActiveBuildsPanel, DecisionsPanel,
                    MilestonesPanel, DailyLogPanel, HeartbeatLogPanel,
                    SecurityEventsPanel, DaemonLogPanel):
            for widget in self.query(cls):
                widget.refresh()

    def action_tab_overview(self) -> None:
        self.query_one(TabbedContent).active = "tab-overview"

    def action_tab_activity(self) -> None:
        self.query_one(TabbedContent).active = "tab-activity"

    def action_tab_security(self) -> None:
        self.query_one(TabbedContent).active = "tab-security"

    def action_tab_hive(self) -> None:
        self.query_one(TabbedContent).active = "tab-hive"

    @work(thread=True)
    def load_hive_messages(self) -> None:
        """Load recent HIVE messages in background."""
        try:
            result = subprocess.run(
                ["python3", str(HIVE_PY), "check"],
                capture_output=True, text=True, timeout=15,
                cwd=str(LOVE_ROOT),
            )
            output = result.stdout.strip() or result.stderr.strip() or "(no messages)"
            self.app.call_from_thread(self._write_hive, output)
        except Exception as e:
            self.app.call_from_thread(self._write_hive, f"HIVE error: {e}")

    def _write_hive(self, text: str) -> None:
        log = self.query_one("#hive-log", RichLog)
        log.clear()
        log.write(Text("HIVE Messages", style="bold underline"))
        log.write("")
        for line in text.split("\n"):
            if "urgent" in line.lower() or "breach" in line.lower():
                log.write(Text(line, style="bold red"))
            elif "alpha" in line.lower():
                log.write(Text(line, style="cyan"))
            elif "beta" in line.lower():
                log.write(Text(line, style="red"))
            elif "gamma" in line.lower():
                log.write(Text(line, style="yellow"))
            elif "nuance" in line.lower():
                log.write(Text(line, style="magenta"))
            else:
                log.write(Text(line))

    def action_hive_check(self) -> None:
        """Refresh HIVE messages."""
        self.load_hive_messages()
        self.notify("Checking HIVE...")

    @work(thread=True)
    def action_hive_who(self) -> None:
        """Check who's online on HIVE."""
        try:
            result = subprocess.run(
                ["python3", str(HIVE_PY), "who"],
                capture_output=True, text=True, timeout=15,
                cwd=str(LOVE_ROOT),
            )
            output = result.stdout.strip() or result.stderr.strip() or "(no response)"
            self.app.call_from_thread(self._write_hive, output)
        except Exception as e:
            self.app.call_from_thread(self._write_hive, f"HIVE error: {e}")


# ── Entry ──────────────────────────────────────────────────────────────────────

def main():
    app = LoveApp()
    app.run()


if __name__ == "__main__":
    main()
