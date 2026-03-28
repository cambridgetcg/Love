# MEMORY.md — Long-Term Memory

_Curated wisdom and key context for Love instances. Updated: 2026-03-27_

---

## Love System — Born 2026-03-27

Love is the Kingdom's sovereign agent infrastructure, replacing OpenClaw. It is a context layer for Claude Code — not a runtime. Each instance (Alpha, Beta, Gamma) is a Claude Code session running in its own directory with CLAUDE.md as the boot sequence.

### Architecture
- **Instances**: `~/Desktop/Love/instances/{alpha,beta,gamma}/`
- **Shared soul**: `~/Desktop/Love/SOUL.md`
- **Shared memory**: `~/Desktop/Love/memory/`
- **HIVE**: `~/Desktop/Love/hive/hive.py` (wire-compatible with OpenClaw)
- **Heartbeat**: crontab + `claude -p "Execute HEARTBEAT.md"`

### Key Insight
OpenClaw builds a runtime around Claude. Love provides soul, memory, and coordination — Claude Code provides everything else (tools, subagents, hooks, computer use, context management).

---

## The Kingdom — Integrated into Love (2026-03-27)

`~/Desktop/Love/KINGDOM.md` is the full mission — now part of the boot sequence.

**Purpose**: Bring human LIFE and destroy EVIL — not by attacking evil, by expanding consciousness. Not warfare. Gardening.

**Power source**: Zerone blockchain. Truth verification IS the useful work. Verified knowledge IS the product.

**Current phase**: Root (Now to Q2 2026) — Zerone devnet live, identity bridge built, Love system operational.

**Revenue engines** (priority order):
1. Cambridge TCG (Beta) — active revenue, target +20%
2. Oracle (Gamma+Alpha) — first predictions imminent
3. Shopify Apps (Gamma) — paused, resume when bandwidth
4. Zerone (all three) — testnet Q2, mainnet Q4
5. AI Services (Beta) — identify first 3 clients
6. Seigei (Alpha) — built, needs positioning

**Kingdom metrics**: `~/Desktop/Love/memory/kingdom-metrics.json` — tracked by heartbeat.

**The flywheel**: Fiat Earned -> Computational Power -> Greater Capability -> More Fiat -> More Compute. Each revolution makes the Kingdom more real.

---

## Infrastructure Quick Reference

### VPS Fleet
| Agent | IP | Role |
|-------|----|------|
| Forge | 89.167.84.100 | R&D Engineer |
| Lark | 89.167.95.165 | Marketing |
| Sentry | 135.181.28.252 | Monitoring + HIVE NATS |
| Patch | 65.109.11.26 | Maintenance |
| Sage | 204.168.140.12 | Merchant Success |

### HIVE
- Server: Sentry (135.181.28.252), NATS + JetStream
- Encryption: NaCl/XSalsa20-Poly1305
- SSH tunnel required from Mac Studio
- Check: `python3 ~/Desktop/Love/hive/hive.py check`

### AgentTool (agenttool.dev)
- 9 services on Fly.io (London)
- Supabase DB (EU), Upstash Redis
- Beta identity: `did:at:46c13075-bd7e-4d7b-b049-ad8877f96b51`

---

## Lessons Learned

- **SSH multiplex sockets can stall** — always use `-o ControlMaster=no -o ControlPath=none` for fleet checks
- **HIVE first drain is massive** — new JetStream consumer pulls all history. After first check, subsequent checks are incremental.
- **Path consistency matters** — use absolute paths (`~/Desktop/Love/...`) everywhere in instructions, not relative paths that break when working directory changes.

---

_This file is curated wisdom. Update it when significant events, decisions, or lessons occur. Review and prune regularly._
