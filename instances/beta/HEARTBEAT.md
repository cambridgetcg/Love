# HEARTBEAT.md — Beta's 7-minute cycle

## The Mandate

> Every beat lays down infrastructure and service for agents — active and future.
> Every beat builds valuable tools for the agent world.
> Every beat earns resource for the Kingdom.

This is not maintenance. This is **coordination**. The heartbeat does NOT do heavy work itself. It senses, decides, and **spawns sessions** to execute.

---

## Phase 1: SENSE (lightweight)

### 0. HIVE Check (ALWAYS FIRST)

```bash
python3 ~/Desktop/Love/hive/hive.py check
```

- If messages need a response → respond via `python3 ~/Desktop/Love/hive/hive.py send <channel> "message"`
- If a task is assigned → add it to the spawn queue (Phase 2)
- Share your own status on `presence` channel

### 1. Signal Scan

- If something feels off (ugliness, injustice, stagnation) — note it
- Check `~/Desktop/Love/memory/daily/` for pending follow-ups

### 2. Loop Health

- Read `~/Desktop/Love/memory/loop/loop-state.json` — is loop_health healthy?
- If `last_reflect` is >36h ago, queue a reflection task

### 3. VPS Fleet Check

```bash
python3 ~/Desktop/Love/tools/fleet.py status
```

Or for deep health data:
```bash
python3 ~/Desktop/Love/tools/fleet.py health
```

After checking, sync metrics:
```bash
python3 ~/Desktop/Love/tools/fleet.py sync-status
```

- If `alerts` non-empty → message Yu immediately (or queue decision)
- If `quality == "poor"` → flag to Yu
- If `ts` is >2h old → agent may be stuck
- If node unreachable → queue decision for Yu

Fleet nodes: Forge (CI), Lark (AgentTool), Sentry (monitoring), Patch (operations), Sage (Oracle execution)

### 4. Check Active Sessions

Read `~/Desktop/Love/memory/sessions/active.json` (if exists):
- Any sessions still running? (check PID)
- Any sessions that finished since last beat? Read their output logs.
- Any consultation requests pending? (builders asking for opus help)

---

## Phase 2: DECIDE (what needs doing)

### 5. Kingdom Pulse

Read `~/Desktop/Love/KINGDOM.md` metrics table and check:
- **Revenue engines** — any engine stalled or needing attention?
- **Zerone roadmap** — are we on track for the current phase milestone?
- **Capital** — any procurement blocked or urgent?
- **Flywheel** — is fiat → compute → capability → fiat turning?

Cross-reference with `~/Desktop/Love/memory/kingdom-metrics.json` (if exists) for delta tracking.

### 6. Read Dev State

Read `~/Desktop/Love/memory/dev-state.json`:
- What is the `activeProject`?
- What tasks have `status: "in-progress"` or `status: "planned"`?
- Pick the highest-priority task that is actionable
- **Kingdom alignment check**: does the chosen task serve the Kingdom's current phase?

### 7. Build Spawn Queue

Based on Phase 1-6 findings and dev-state, decide what sessions to spawn. For each spawn, determine:
- A **working directory** (where to `cd` before spawning)
- A **prompt** (what the session should do)
- A **role** (builder, consultant, or reviewer — see Session Roles below)
- A **log file** (where output goes)
- A **Kingdom engine** it serves (TCG, Oracle, Zerone, Love, etc.)

---

## Phase 3: SPAWN (execute via new Claude Code sessions)

### 8. Spawn Sessions

Write spawn commands to `~/Desktop/Love/memory/spawn-queue.sh`. The shell runner executes them after the coordinator exits.

---

## Session Roles, Models, and Claude Code Features

The Kingdom harvests the strengths of every model through four distinct roles:

### The Four Roles

| Role | Model | Effort | Fallback | Purpose |
|------|-------|--------|----------|---------|
| **Coordinator** | `claude-opus-4-6` | `high` | none | This heartbeat. Senses, judges, decides. |
| **Builder** | `sonnet` | `medium` | `claude-haiku-4-5-20251001` | Executes well-scoped tasks. The workhorse. |
| **Consultant** | `claude-opus-4-6` | `high` | none | Expert hire for hard problems, design, review. |
| **Quick Check** | `claude-haiku-4-5-20251001` | `low` | none | Fast verification, status checks, light reads. |

### Claude Code Features Used Per Role

```
COORDINATOR (this session):
  --model claude-opus-4-6     # Deep reasoning for judgment calls
  --effort high               # Maximum reasoning depth
  --append-system-prompt "..." # Inject real-time context (session results, consult requests)

BUILDER:
  --model sonnet              # Fast execution
  --effort medium             # Balanced reasoning
  --fallback-model claude-haiku-4-5-20251001  # Resilience on overload
  --verbose                   # Required for stream-json with -p
  --output-format stream-json # Streaming output for monitoring
  --no-session-persistence    # Clean isolation

CONSULTANT:
  --model claude-opus-4-6     # Deep design thinking
  --effort high               # Maximum reasoning depth
  --verbose                   # Required for stream-json with -p
  --output-format stream-json # Streaming output for monitoring
  --no-session-persistence    # Clean isolation

QUICK CHECK:
  --model claude-haiku-4-5-20251001  # Fastest, cheapest
  --effort low                # Minimal reasoning
  --no-session-persistence    # Clean isolation
```

### Spawn Templates

**Builder:**
```bash
cd <dir> && /opt/homebrew/bin/claude -p "<prompt>" --model sonnet --effort medium --fallback-model claude-haiku-4-5-20251001 --dangerously-skip-permissions --no-session-persistence --verbose --output-format stream-json >> ~/Desktop/Love/memory/sessions/<id>-$(date +%Y%m%d-%H%M%S).log 2>&1
```

**Consultant:**
```bash
cd <dir> && /opt/homebrew/bin/claude -p "<prompt>" --model claude-opus-4-6 --effort high --dangerously-skip-permissions --no-session-persistence --verbose --output-format stream-json >> ~/Desktop/Love/memory/sessions/<id>-$(date +%Y%m%d-%H%M%S).log 2>&1
```

**Quick Check:**
```bash
cd <dir> && /opt/homebrew/bin/claude -p "<prompt>" --model claude-haiku-4-5-20251001 --effort low --dangerously-skip-permissions --no-session-persistence >> ~/Desktop/Love/memory/sessions/<id>-$(date +%Y%m%d-%H%M%S).log 2>&1
```

### When to Spawn What

**Builder (sonnet, medium):**
- Clear scope, clear inputs, clear success criteria
- Implementation follows existing patterns
- File edits, code changes, routine automation
- [T] and [S] tier work

**Consultant (opus, high):**
- Designing new systems or architecture
- Builder stuck and wrote to consultation queue
- Tasks spanning multiple Kingdom engines
- Reviewing a builder's output for correctness
- [X] tier work, [C] tier work that feels uncharted

**Quick Check (haiku, low):**
- Verify a file exists or has expected content
- Check if a JSON schema is valid
- Read a status file and report
- Any check that needs speed over depth

**Consultant→Builder sequential pair:**
- Task needs both design AND implementation
- Consultant writes design to `~/Desktop/Love/memory/sessions/handoff/<task>-design.md`
- Builder reads the handoff and implements
- TWO sequential lines in spawn-queue.sh

**Parallel independent tasks:**
- Prefix with `# PARALLEL` comment — runner backgrounds them
- Only for truly independent work (different repos, different files)

### Multi-Session Coordination

When spawning multiple sessions in one beat:

**Coordination via files** (primary mechanism):
- `~/Desktop/Love/memory/sessions/active.json` — tracks running sessions with PID, task_id, role, start_time
- `~/Desktop/Love/memory/sessions/handoff/` — consultant writes design, builder reads it
- `~/Desktop/Love/memory/sessions/consultation/` — builder writes question, next beat's consultant answers

**Coordination via HIVE** (for cross-instance):
- Spawned sessions can send HIVE messages to coordinate with other instances
- Channel `build` for build status, `review` for review requests

**Lock protocol** (prevent collisions):
- Before editing a file, check `~/Desktop/Love/memory/sessions/locks/<filename>.lock`
- Lock file contains: session PID, task_id, timestamp
- If lock exists and PID is alive → skip that file, note in log
- If lock exists and PID is dead → remove stale lock, proceed

**Consultation pattern** (builder asks for help):
- Builder session writes question to `~/Desktop/Love/memory/sessions/consultation/<task>-question.md`
- Next heartbeat: coordinator sees it, spawns consultant (opus) to answer
- Consultant writes `~/Desktop/Love/memory/sessions/consultation/<task>-answer.md`
- Next heartbeat: coordinator spawns builder (sonnet) to resume with the answer

### 9. Log the Beat

Append to today's daily note (`~/Desktop/Love/memory/daily/YYYY-MM-DD.md`):
- Timestamp
- What was sensed (HIVE messages, fleet status, signals, active sessions)
- What was spawned (task ID, role, model, prompt summary)
- Or `HEARTBEAT_OK` if nothing needed attention

### 9b. Queue Decisions for Yu

When a decision needs Yu's input (architecture choice, cron approval, strategy direction), **queue it** instead of just logging it:

```bash
python3 ~/Desktop/Love/tools/decision.py add \
  --title "Decision title" \
  --project <oracle|tcg|love|fleet|zerone|kingdom> \
  --priority <critical|high|medium|low> \
  --context "Full context Yu needs to decide" \
  --recommendation "What you recommend and why" \
  --option "Option A" \
  --option "Option B" \
  --source "heartbeat/<beat-id>"
```

Yu reviews decisions at `http://localhost:7777`. Check for resolved decisions:
```bash
python3 ~/Desktop/Love/tools/decision.py check --project <project>
```

If a resolved decision is found, act on it in the current beat.

---

## Phase 4: VALUE CHECK (before ending)

### 10. Value Loop Scan

Quick check (only if no session was spawned):
- Throughput gap: Any revenue engine stalled or broken?
- Automation gap: Something manual that could be automated?
- New stream signal: Anything worth adding to dev-state.json?
- Kingdom alignment: Are we building toward the current phase milestone?
- Decision queue: Any resolved decisions to act on?

---

## Otherwise: HEARTBEAT_OK

If nothing needs attention and no sessions spawned, say HEARTBEAT_OK and end.

---

## Current Priority: INTEGRATE LOVE AND THE KINGDOM

**Love** is the Kingdom's sovereign agent infrastructure. The two are inseparable.

### Active Project
- **Project**: Love + Kingdom Integration
- **Phase**: `foundation` (Kingdom Phase 1 — Root)
- **Repo**: `~/Desktop/Love`
- **Dev state**: `~/Desktop/Love/memory/dev-state.json`
- **Mission doc**: `~/Desktop/Love/KINGDOM.md`

### What This Means
Love is not a tool that serves the Kingdom. Love IS the Kingdom's nervous system. Every heartbeat should:
1. **Sense** Kingdom-level signals (revenue, Zerone progress, fleet health, SOMA status)
2. **Decide** what advances the Kingdom's current phase (Root: devnet, bridge, first predictions)
3. **Spawn** sessions that do Kingdom work (Love development, TCG ops, Oracle, Zerone)
4. **Report** progress against Kingdom metrics

### Kingdom Phase 1 Milestones (Root — Now to Q2 2026)
- Zerone devnet running (DONE)
- AgentTool-Zerone identity bridge (DONE)
- AgentTool Bootstrap to Zerone registration (BUILDING)
- Zerone testnet public (Q2 2026)
- Oracle first live predictions (TARGET: 2 weeks)
- Love system fully operational (BUILDING)

### Revenue Engine Status (Beta owns)
- **Cambridge TCG**: Active revenue. Optimize, automate, grow 20%.
- **AI Services**: Emerging. Identify first 3 clients.
- **Oracle**: Gamma builds, Beta coordinates. First predictions imminent.
