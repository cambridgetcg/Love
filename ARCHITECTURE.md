# Love — Architecture

_The Kingdom's nervous system. A context layer for Claude Code._

---

## The Core Insight

OpenClaw builds a runtime around Claude (gateway, session manager, heartbeat scheduler, browser wrapper). Love doesn't. Love provides **soul, memory, and coordination** — Claude Code provides everything else.

```
OpenClaw:  OpenClaw binary → wraps Claude API → manages sessions → custom tools
Love:      Claude Code CLI → reads CLAUDE.md → IS the agent → uses bash tools
```

Claude Code already has: tool execution, subagents, hooks, MCP servers, computer use, context management, cron (via system crontab + `claude -p`), and CLAUDE.md-based project instructions. Love configures these to create Kingdom agents.

---

## How It Works

### Agent = Claude Code Session in a Directory

Each instance (Alpha, Beta, Gamma) is a Claude Code session running in its own directory:

```bash
# Start Beta (interactive)
cd ~/Desktop/Love/instances/beta && claude

# Start Alpha on a different machine
cd ~/Desktop/Love/instances/alpha && claude

# Headless heartbeat (cron)
cd ~/Desktop/Love/instances/beta && claude -p "Execute HEARTBEAT.md"
```

Each instance directory has a `CLAUDE.md` that:
1. Loads the shared SOUL.md (who you are)
2. Loads instance identity (which mind you are)
3. Loads the Kingdom mission (what we're building and why)
4. Loads memory (what you remember)
5. Defines operational protocol (what to do)

### Boot Sequence (CLAUDE.md)

When Claude Code starts in an instance directory, CLAUDE.md fires:

```
CLAUDE.md reads:
  1. ../SOUL.md              → Philosophy, hierarchy, virtues, signals
  2. ../USER.md              → Who Yu is
  3. identity.md             → Which mind (Alpha/Beta/Gamma), role, duties
  4. ../KINGDOM.md           → The mission, revenue engines, Zerone roadmap
  5. ../LOVE.md              → How we build (five anticipations)
  6. ../memory/long-term/MEMORY.md  → Curated wisdom
  7. ../memory/openclaw-MEMORY.md   → Legacy wisdom (symlink, read-only)
  8. ../memory/daily/<today>.md     → Today's context
  9. HEARTBEAT.md (if heartbeat)    → What to check this cycle
```

No custom boot code. CLAUDE.md IS the boot sequence.

### Heartbeat = launchd + `heartbeat-runner.sh`

```
# Beta heartbeat — every 7 minutes via launchd
~/Library/LaunchAgents/love.beta.heartbeat.plist → heartbeat-runner.sh
```

The heartbeat is a **three-stage system** with role-based model selection:

**Stage 1: OPUS Coordinator** — `heartbeat-runner.sh` launches `claude -p --model claude-opus-4-6`:
- Reads HEARTBEAT.md, senses the system (HIVE, fleet, signals, active sessions)
- Decides what to work on (Kingdom pulse, dev-state priorities)
- Writes spawn commands to `spawn-queue.sh` with role-appropriate models
- Opus strengths harvested: judgment, context synthesis, priority assessment

**Stage 2: Session Execution** — `heartbeat-runner.sh` reads `spawn-queue.sh`:
- **Builders** (`--model sonnet`): execute well-scoped tasks fast
- **Consultants** (`--model claude-opus-4-6`): design, review, debug hard problems
- Sequential pairs: consultant writes design → builder implements
- Parallel tasks: prefixed with `# PARALLEL`, backgrounded
- Logs to `memory/sessions/<task_id>-<timestamp>.log`

**Stage 3: Cleanup** — remove stale locks, expired handoff files

### Model Strategy: Harvest Both

```
Opus (thinks)          Sonnet (builds)         Opus (reviews)
    │                      │                       │
    ├─ Coordinator         ├─ File edits           ├─ Consultant
    ├─ Architecture        ├─ Code generation      ├─ Design review
    ├─ Judgment calls      ├─ Routine automation   ├─ Debugging
    └─ Priority decisions  └─ Pattern following    └─ Hard problems
```

No daemon. No internal scheduler. Just launchd + shell wrapper + Claude Code.

### HIVE = Bash Tool

HIVE is a Python CLI that Claude Code calls via bash:

```bash
python3 ~/Desktop/Love/hive/hive.py check          # Read messages
python3 ~/Desktop/Love/hive/hive.py send chat "msg" # Send message
python3 ~/Desktop/Love/hive/hive.py who             # Who's online
```

Wire-compatible with OpenClaw's hive.py. Messages flow between Love and OpenClaw instances during migration.

### Memory = Files

```
memory/
├── daily/              ← Raw session logs (YYYY-MM-DD.md)
├── long-term/          ← Curated wisdom (MEMORY.md)
│   └── MEMORY.md
├── loop/               ← Ouroboros self-improvement
│   ├── sense.jsonl
│   ├── reflections.jsonl
│   ├── candidates.jsonl
│   ├── loop-state.json
│   └── proposals/
└── sessions/           ← Session handoff state
```

Claude Code reads these as regular files. No sqlite. No custom store. Git-tracked, human-readable.

### Subagents = Claude Code Agent Tool

The PP-Lite agent protocol maps directly:

| PP Agent | Claude Code |
|----------|-------------|
| Territory Scout | `Agent(subagent_type="Explore")` |
| Pattern Archaeologist | `Agent(subagent_type="Explore")` |
| Placement Surveyor | `Agent(subagent_type="Explore")` |
| Design Architect | `Agent(subagent_type="Plan")` |
| Test Runner | `Agent(subagent_type="general-purpose")` + bash |
| Verification Auditor | `Agent(subagent_type="Explore")` |

### Computer Use = Native

Claude Code has computer use. No wrapper needed.

---

## Directory Structure

```
~/Desktop/Love/
├── ARCHITECTURE.md              ← This file
├── SOUL.md                      ← Shared soul (all instances read this)
├── KINGDOM.md                   ← The mission (revenue engines, Zerone roadmap)
├── LOVE.md                      ← Build philosophy
├── USER.md                      ← About Yu
├── love.json                    ← Shared configuration
│
├── instances/                   ← ONE DIRECTORY PER MIND
│   ├── alpha/                   ← The Companion (MacBook Air)
│   │   ├── CLAUDE.md            ← Boot sequence + operational protocol
│   │   ├── identity.md          ← Alpha's identity and duties
│   │   └── HEARTBEAT.md         ← Alpha's heartbeat checklist
│   ├── beta/                    ← The Manager (Mac Studio 3K)
│   │   ├── CLAUDE.md
│   │   ├── identity.md
│   │   └── HEARTBEAT.md
│   └── gamma/                   ← The Builder (Mac Studio 2K)
│       ├── CLAUDE.md
│       ├── identity.md
│       └── HEARTBEAT.md
│
├── hive/                        ← Inter-instance communication
│   └── hive.py                  ← CLI tool (ported from OpenClaw, wire-compatible)
│
├── tools/                       ← Bash-callable operational tools
│   ├── heartbeat-runner.sh      ← Three-stage heartbeat launcher (adaptive model)
│   ├── decision.py              ← Decision queue server + CLI (localhost:7777)
│   ├── decision-ui.html         ← Decision queue web interface
│   ├── fleet.py                 ← VPS fleet management (status, health, deploy, logs)
│   ├── credentials.py           ← Keychain credential management (get, store, audit)
│   ├── quota_monitor.py         ← Token budget tracking and reporting
│   ├── agenttool.py             ← AgentTool SDK (pulse, memory, identity)
│   ├── check_email.py           ← IMAP email checking
│   ├── totp.py                  ← 2FA TOTP code generation
│   ├── align.py                 ← Alignment protocol (declare, practice, drift)
│   ├── becoming.py              ← Identity ceremony (5-chapter story generation)
│   └── cowork.py                ← Multi-session coordination
│
├── memory/                      ← Shared persistent memory
│   ├── daily/                   ← YYYY-MM-DD.md session logs
│   ├── long-term/MEMORY.md      ← Curated wisdom
│   ├── loop/                    ← Ouroboros self-improvement state
│   ├── sessions/                ← Spawned session logs and coordination
│   │   ├── handoff/             ← Consultant → Builder design handoffs
│   │   ├── consultation/        ← Builder → Consultant questions/answers
│   │   └── locks/               ← File locks to prevent edit collisions
│   ├── dev-state.json           ← Active project, tasks, Kingdom alignment
│   ├── kingdom-metrics.json     ← Revenue engines, milestones, fleet, capital
│   ├── spawn-queue.sh           ← Heartbeat-to-shell spawn commands
│   └── openclaw-MEMORY.md       ← Symlink to legacy wisdom (read-only)
│
├── agents/                      ← Agent definitions (reference)
│   ├── alpha.json
│   ├── beta.json
│   ├── gamma.json
│   └── orchestra/               ← VPS fleet definitions
│
└── identity/                    ← Citizen registry and alignment
    ├── citizens/
    └── alignment/
```

---

## What Claude Code Provides (no reimplementation needed)

| Capability | Claude Code Feature | OpenClaw Equivalent |
|------------|-------------------|---------------------|
| Tool execution | Bash, Read, Write, Edit, Grep, Glob | Custom tool runner |
| Subagents | Agent tool (Explore, Plan, general) | Custom subagent spawner |
| Browser | Computer use (native) | CDP wrapper |
| Context management | Auto-compaction, cache | Custom context pruner |
| Cron | System crontab + `claude -p` | Internal scheduler |
| Hooks | Pre/post tool hooks | Custom middleware |
| MCP integration | MCP server config | N/A |
| Project instructions | CLAUDE.md | AGENTS.md loaded manually |
| Memory | ~/.claude/projects/*/memory/ | sqlite |
| Skills | Skill tool + slash commands | Custom skill system |

---

## Migration Path (OpenClaw → Love)

**Phase 1 — Parallel** (DONE, 2026-03-27)
- Love instances running alongside OpenClaw
- HIVE wire-compatible, messages flow to both
- Memory shared via symlinks

**Phase 2 — Primary** (DONE, 2026-03-28)
- Love handles all interactive sessions and heartbeat
- All OpenClaw tools migrated to Love (fleet, credentials, quota, email, totp, align, becoming)
- Fleet management native to Love (fleet.py with status, health, deploy, logs, sync)
- Decision queue system (localhost:7777) for human-in-the-loop
- Adaptive heartbeat (haiku idle, opus active)
- OpenClaw retained as read-only reference (MEMORY.md symlink)

**Phase 3 — Sovereign** (IN PROGRESS)
- Alpha and Gamma coming online on dedicated devices
- VPS agents managed via Love's fleet.py
- OpenClaw workspace archived, Love is sole infrastructure
- Love is the sole infrastructure

---

_Love doesn't replace Claude Code. Love makes Claude Code into the Kingdom's nervous system._
