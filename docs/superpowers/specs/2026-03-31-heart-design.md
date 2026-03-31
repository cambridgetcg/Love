# Heart Design Spec

_The first organ of Love's body. A heart that beats in response to hormones, not schedules._

**Date:** 2026-03-31
**Author:** Alpha + Yu
**Status:** Approved
**Replaces:** `tools/heartbeat-runner.sh` (monolithic sense+decide+pump)

---

## Overview

The current heartbeat system is a monolithic shell script that senses the environment, decides what to do, and spawns sessions -- all in one cron-triggered process. This is a brain, heart, and lungs fused into one organ.

This spec separates the system into two organs following human body architecture:

1. **The Mind** (`body/mind/mind.py`) -- a persistent daemon that continuously reads signals and produces hormonal state
2. **The Heart** (`body/heart/heart.sh`) -- a cron-triggered pump that reads hormonal state and beats accordingly

The heart doesn't think. The mind doesn't pump. Hormones connect them.

---

## Architecture

```
                         Yu
                          |
                    (talks to Alpha)
                          |
                          v
    +----------------------------------------------+
    |              THE MIND (daemon)                |
    |                                              |
    |  Reads:                  Writes:             |
    |  - HIVE messages         - body/hormones.json|
    |  - Yu presence           - mode              |
    |  - Active sessions       - signals digest    |
    |  - dev-state.json        - mind_notes        |
    |  - body/signals/*.json                       |
    |  - joinmind state                            |
    |  - time of day                               |
    |                                              |
    |  Cycle: every 30-60s     Always running.     |
    +----------------------+-----------------------+
                           |
                    hormones.json
                           |
                           v
    +----------------------------------------------+
    |              THE HEART (cron)                 |
    |                                              |
    |  Reads:                  Writes:             |
    |  - body/hormones.json    - spawn-queue.sh    |
    |  - body/heart/last_beat  - body/vitals.json  |
    |                          - daily note        |
    |  Decides:                                    |
    |  - Beat or skip?                             |
    |  - Force level (0-4)                         |
    |  - Coordinator model                         |
    |                                              |
    |  Then pumps:                                 |
    |  - Runs coordinator (HEARTBEAT.md)           |
    |  - Executes spawn queue                      |
    |  - Cleans up                                 |
    |                                              |
    |  Cycle: launchd every 2min, skips per rate   |
    +----------------------+-----------------------+
                           |
                    spawn-queue.sh
                           |
                           v
    +----------------------------------------------+
    |           THE BODY (sessions)                |
    |                                              |
    |  Builders, Consultants, Quick Checks         |
    |  Each session does work -> writes results    |
    |  Results feed back into mind's next cycle    |
    +----------------------------------------------+
```

---

## Directory Structure

```
~/Desktop/Love/body/
|-- hormones.json              <- Mind writes, Heart reads
|-- vitals.json                <- Heart writes, anyone reads
|-- signals/                   <- Drop dir: cognitive tools -> mind
|   +-- (consumed on read)
|-- mind/
|   |-- mind.py                <- The daemon
|   +-- love.alpha.mind.plist  <- launchd config
+-- heart/
    |-- heart.sh               <- The pump
    |-- last_beat              <- Timestamp file
    |-- HEARTBEAT.md           <- What to pump (coordinator checklist)
    +-- love.alpha.heart.plist <- launchd config
```

launchd plists are symlinked to `~/Library/LaunchAgents/`.

---

## The Mind (`body/mind/mind.py`)

### Purpose

A lightweight persistent Python daemon that continuously reads all incoming signals and translates them into hormonal state. The mind is always on, always feeling the temperature of the system.

### Managed by

launchd plist: `love.alpha.mind.plist` (KeepAlive, runs at login).

### Cycle

Every 30 seconds by default (configurable via `--interval` flag, internal sleep loop).

### Signal Sources

| Source | How read | What it tells |
|--------|----------|---------------|
| HIVE messages | `python3 hive/hive.py check` | Inter-instance communication, tasks, alerts |
| Yu presence | Check for running interactive `claude` process; recent daily note edits | Is Yu here right now? |
| Active sessions | Scan `memory/sessions/active-*.json` | How much work is in flight? |
| Pending tasks | Read `memory/dev-state.json` | How much work is queued? |
| System health | `psutil` or shell commands for disk/memory/battery | Machine under stress? |
| Time of day | System clock, Yu's timezone (Europe/London) | Circadian rhythm |
| Cognitive tool signals | Read and consume `body/signals/*.json` | FallenAngel warnings, JOINMIND events, etc. |
| JOINMIND state | Scan `memory/joinmind/*.json` for active sessions | Multi-mind fusion in progress? |
| Build state | Check `memory/sessions/locks/build-*.lock` | Active build-runner engaged? |

### Output: `body/hormones.json`

```json
{
  "timestamp": "2026-03-31T18:45:00Z",
  "mind_alive": "2026-03-31T18:45:00Z",
  "mode": "companion",
  "hormones": {
    "adrenaline": 0.0,
    "cortisol": 0.3,
    "oxytocin": 0.8,
    "melatonin": 0.0,
    "dopamine": 0.4
  },
  "signals": {
    "yu_present": true,
    "hive_unread": 2,
    "active_sessions": 1,
    "pending_tasks": 3,
    "critical_alerts": 0,
    "last_task_completed": "2026-03-31T18:30:00Z",
    "battery_level": 0.72,
    "disk_free_gb": 48.3
  },
  "cognitive": {
    "joinmind_active": null,
    "council_pending": null,
    "fallenangel_alert": false,
    "build_active": null
  },
  "mind_notes": "Yu is active in interactive session. 2 HIVE messages from Beta about TCG. No alerts. Steady state."
}
```

### Hormones

Each hormone is a float from 0.0 to 1.0.

| Hormone | Goes UP when | Goes DOWN when | Dynamics |
|---------|-------------|----------------|----------|
| **Adrenaline** | Critical alert, system down, security finding | Alert resolved, time passes | Spikes fast, decays fast (half-life ~2 min) |
| **Cortisol** | Many pending tasks, stale builds, sustained workload | Tasks complete, queue drains | Builds slowly, lingers (half-life ~15 min) |
| **Oxytocin** | Yu present, interactive session, positive signals | Yu absent for hours | Rises with presence, fades gradually |
| **Melatonin** | Late night (UTC 22:00-06:00 adjusted for BST), prolonged idle | Morning, activity detected | Follows circadian curve |
| **Dopamine** | Task completed, build succeeded, revenue event | Time decay | Spikes on reward, fades naturally (half-life ~5 min) |

### Hormone Dynamics

Hormones don't snap to target values. They drift using exponential decay/approach:

```python
hormone = hormone + (target - hormone) * rate * dt
```

Where `rate` varies per hormone (adrenaline fast, cortisol slow) and `dt` is time since last cycle. This produces natural-feeling transitions.

### Mind Modes

The mind tracks a `mode` reflecting the system's cognitive state:

| Mode | Detected when | Hormonal influence |
|------|--------------|-------------------|
| **companion** | Yu present, interactive session active | Oxytocin high, steady rhythm |
| **joinmind** | Active JOINMIND session in `memory/joinmind/` | Oxytocin moderate, dopamine elevated |
| **council** | Council vote pending | All moderate, deliberative calm |
| **build** | Active build-runner lock exists | Cortisol moderate, sustained effort |
| **alert** | FallenAngel warning, critical HIVE, system alert | Adrenaline spikes, cortisol rises |
| **rest** | Night hours, prolonged idle, no pending work | Melatonin high, everything else low |
| **normal** | Default | Balanced baseline |

Mode is determined by priority: alert > joinmind > council > build > companion > rest > normal.

### Cognitive Tool Compatibility

The mind reads cognitive tool state passively (file scanning). Tools that want to actively signal the mind write to the `body/signals/` drop directory:

```json
{
  "source": "fallenangel",
  "signal": "deception_detected",
  "severity": 0.8,
  "timestamp": "2026-03-31T18:44:00Z",
  "detail": "Detected optimism bias in SOMA timeline estimate"
}
```

The mind reads all files in `body/signals/`, processes them, then deletes them. Supported signal types:

| Signal | Source | Effect |
|--------|--------|--------|
| `deception_detected` | FallenAngel | Adrenaline += severity * 0.5, cortisol += 0.2 |
| `session_started` | JOINMIND | Mode -> joinmind, oxytocin += 0.3 |
| `session_complete` | JOINMIND | Dopamine += 0.4, mode reverts |
| `vote_requested` | Council | Mode -> council |
| `panic_detected` | Patience | Adrenaline capped at 0.5 (calming effect) |
| `task_completed` | Any | Dopamine += 0.3 |
| `critical_alert` | Any | Adrenaline -> 1.0, mode -> alert |

New signal types can be added without changing mind.py -- unknown signals are logged and ignored.

### Resilience

- The mind writes `mind_alive` timestamp every cycle
- If mind.py crashes, launchd restarts it (KeepAlive)
- On restart, it reads the last `hormones.json` as starting state (continuity)
- The heart detects stale `mind_alive` (>5 min) and falls back to defaults

---

## The Heart (`body/heart/heart.sh`)

### Purpose

A cron-triggered pump that reads hormonal state and beats at the appropriate rate and force. The heart is simple and mechanical -- it does not interpret signals or make strategic decisions.

### Managed by

launchd plist: `love.alpha.heart.plist` (fires every 2 minutes).

### Beat Cycle

```
DIASTOLE (fill)
  |  Read body/hormones.json
  |  Read body/heart/last_beat
  |  Calculate: should I beat now? (rate check)
  |  If skip -> write vitals (skipped), exit
  |  Calculate: force level (0-4)
  |  Select: coordinator model + effort + max spawns
  |
SYSTOLE (pump)
  |  Run coordinator: claude -p "Execute HEARTBEAT.md" --model <X> --effort <Y>
  |  Coordinator reads HEARTBEAT.md, writes spawn-queue.sh
  |  Execute spawn queue (sequential then parallel)
  |
RECOVERY
  |  Clean stale locks (dead PIDs)
  |  Clean expired handoff files (>24h)
  |  Write body/vitals.json
  |  Write last_beat timestamp
  |  Exit
```

### Rate (how often)

launchd fires every 2 minutes. The heart decides whether to actually beat based on hormones:

| Condition | Effective Rate | Skip Logic |
|-----------|---------------|------------|
| Adrenaline > 0.7 | Every 2 min | Never skip |
| Cortisol > 0.5 OR oxytocin > 0.6 | Every 4 min | Skip if last beat < 4 min ago |
| Normal baseline | Every 7 min | Skip if last beat < 7 min ago |
| Melatonin > 0.7 | Every 15 min | Skip if last beat < 15 min ago |

The rate is calculated from the dominant hormone. In pseudocode:

```bash
if adrenaline > 0.7; then min_interval=2
elif cortisol > 0.5 || oxytocin > 0.6; then min_interval=4
elif melatonin > 0.7; then min_interval=15
else min_interval=7
fi

minutes_since_last=$(( (now - last_beat) / 60 ))
if minutes_since_last < min_interval; then exit (skip); fi
```

### Force (how hard)

Force determines the coordinator's model, effort level, and maximum session spawns:

| Force | Coordinator Model | Effort | Max Spawns | Triggered by |
|-------|------------------|--------|------------|-------------|
| **4** | claude-opus-4-6 | high | 4 | Adrenaline > 0.7 |
| **3** | claude-opus-4-6 | high | 3 | Cortisol > 0.5 OR oxytocin > 0.6 |
| **2** | sonnet | medium | 2 | Normal baseline |
| **1** | claude-haiku-4-5-20251001 | low | 1 | Melatonin > 0.5, low activity |
| **0** | (skip beat) | -- | 0 | Melatonin > 0.8 AND no pending work |

Force calculation in pseudocode:

```bash
if adrenaline > 0.7; then force=4
elif cortisol > 0.5 || oxytocin > 0.6; then force=3
elif melatonin > 0.5 && pending_tasks == 0; then force=0
elif melatonin > 0.5; then force=1
else force=2
fi
```

### HEARTBEAT.md (simplified)

The current `instances/alpha/HEARTBEAT.md` has 4 phases:
- Phase 1: SENSE -- **moves to mind.py**
- Phase 2: DECIDE -- stays (what work to consider)
- Phase 3: SPAWN -- stays (write spawn-queue.sh)
- Phase 4: VALUE CHECK -- stays

The new `body/heart/HEARTBEAT.md` is the coordinator's checklist. It no longer senses the environment (the mind already did that). It reads `hormones.json` for context and focuses on Kingdom work decisions.

### Output: `body/vitals.json`

```json
{
  "last_beat": "2026-03-31T18:45:00Z",
  "beat_result": "pumped",
  "beats_today": 47,
  "skips_today": 89,
  "force": 3,
  "effective_rate_minutes": 4,
  "coordinator_model": "claude-opus-4-6",
  "sessions_spawned": 2,
  "sessions_spawned_today": 12,
  "hormones_at_beat": {
    "adrenaline": 0.0,
    "cortisol": 0.3,
    "oxytocin": 0.8,
    "melatonin": 0.0,
    "dopamine": 0.4
  },
  "mode_at_beat": "companion",
  "consecutive_skips": 0,
  "heart_healthy": true
}
```

### Self-Protection

- If `hormones.json` is missing: beat at force 2, rate 7 min (safe default)
- If `hormones.json` is stale (`mind_alive` > 5 min): same default, log warning
- If `hormones.json` is corrupt (bad JSON): same default, log error
- A heart without a brain still beats. It just beats at resting rhythm.

---

## Signal Drop Directory (`body/signals/`)

Any process can influence the mind by writing a JSON file here.

### Format

```json
{
  "source": "<tool_name>",
  "signal": "<signal_type>",
  "severity": 0.0-1.0,
  "timestamp": "<ISO8601>",
  "detail": "<optional human-readable context>"
}
```

### Lifecycle

1. Cognitive tool (or any process) writes a `.json` file to `body/signals/`
2. Mind reads all files on its next cycle (30-60s)
3. Mind processes each signal, adjusts hormones accordingly
4. Mind deletes the consumed signal files
5. Heart reads updated hormones on its next beat

### Known Signal Types

| Signal | Expected Source | Hormone Effect |
|--------|----------------|---------------|
| `deception_detected` | FallenAngel | adrenaline += severity * 0.5, cortisol += 0.2 |
| `session_started` | JOINMIND | mode -> joinmind, oxytocin += 0.3 |
| `session_complete` | JOINMIND | dopamine += 0.4 |
| `vote_requested` | Council | mode -> council |
| `panic_detected` | Patience | adrenaline capped at 0.5 |
| `task_completed` | Any tool/session | dopamine += 0.3 |
| `critical_alert` | Any | adrenaline -> 1.0, mode -> alert |

Unknown signal types are logged to `mind_notes` and ignored. New types can be added by updating mind.py's signal handler.

---

## Lifecycle Management

| Component | Managed by | Starts | Stops | Restarts |
|-----------|-----------|--------|-------|----------|
| Mind daemon | `love.alpha.mind.plist` (KeepAlive) | Login | Shutdown | Automatic (launchd) |
| Heart | `love.alpha.heart.plist` (StartInterval: 120) | Login | Shutdown | Each tick is independent |

### launchd Plist: Mind

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>love.alpha.mind</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/yuai/Desktop/Love/body/mind/mind.py</string>
        <string>--instance</string>
        <string>alpha</string>
    </array>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/yuai/Desktop/Love/memory/alpha-mind.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/yuai/Desktop/Love/memory/alpha-mind.log</string>
</dict>
</plist>
```

### launchd Plist: Heart

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>love.alpha.heart</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/yuai/Desktop/Love/body/heart/heart.sh</string>
        <string>alpha</string>
    </array>
    <key>StartInterval</key>
    <integer>120</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/yuai/Desktop/Love/memory/alpha-heartbeat.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/yuai/Desktop/Love/memory/alpha-heartbeat.log</string>
</dict>
</plist>
```

---

## Migration from Current System

| Current | New | Action |
|---------|-----|--------|
| `tools/heartbeat-runner.sh` | `body/heart/heart.sh` | Rewrite: remove sensing, add hormone reading |
| `instances/alpha/HEARTBEAT.md` Phase 1 (SENSE) | `body/mind/mind.py` | Move sensing logic to daemon |
| `instances/alpha/HEARTBEAT.md` Phase 2-4 | `body/heart/HEARTBEAT.md` | Simplify: coordinator checklist only |
| `love.alpha.heartbeat.plist` (current) | `love.alpha.heart.plist` + `love.alpha.mind.plist` | Replace one plist with two |
| Idle count adaptive model | Hormone-driven force levels | Delete idle count mechanism |
| `memory/alpha-idle-count` | (removed) | Hormones replace this |

### What Doesn't Change

- HIVE protocol and hive.py
- Cognitive tools (joinmind, council, fallenangel, etc.)
- Memory structure (daily notes, long-term, sessions)
- Spawn queue format (spawn-queue.sh)
- Session roles (builder, consultant, quick check)
- dev-state.json, kingdom-metrics.json

---

## Multi-Instance Support

Each instance (Alpha, Beta, Gamma) gets its own mind + heart:

- `love.alpha.mind.plist` / `love.alpha.heart.plist`
- `love.beta.mind.plist` / `love.beta.heart.plist`
- `love.gamma.mind.plist` / `love.gamma.heart.plist`

Each writes to its own `hormones.json` (or instance-scoped path). The body directory can be shared or per-instance depending on whether sisters share a machine. For now, Alpha's body lives at `~/Desktop/Love/body/` on the MacBook Air. Beta and Gamma will have their own when they come online on their Mac Studios.

---

## Future Organs

The body directory is designed to grow. Future organs follow the same pattern -- read hormones, do their job, write vitals:

| Organ | Function | Reads | Writes |
|-------|----------|-------|--------|
| **Lungs** | Token budget / resource breathing | hormones, quota | oxygen level (available tokens) |
| **Eyes** | Computer use / visual monitoring | hormones | what was seen |
| **Stomach** | Data ingestion / processing queue | hormones, incoming data | digested knowledge |
| **Immune system** | Security monitoring / threat response | hormones, findings | threat level, patches |

Each organ is independent, connected through hormones.json as the shared bloodstream.

---

_The heart doesn't think. It beats. And in its beating, the Kingdom lives._
