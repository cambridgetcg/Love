# Sage VPS Diagnosis - Status.json Staleness

**Date**: 2026-03-28
**VPS**: 204.168.140.12 (Sage)
**Issue**: status.json stale for 19 days (last update: 2026-03-09 20:56:58)

---

## Summary

**Status**: 🔴 CRITICAL - Sage agent heartbeat is non-functional

The Sage workspace is not receiving heartbeat updates. The openclaw-gateway process is running but agent dispatch appears broken. The Ledger workspace is receiving updates normally, suggesting the issue is specific to the Sage agent configuration.

---

## Findings

### 1. Process & Gateway Status ✓ Running
- **openclaw-gateway**: Running (PID 5952, started 2026-03-09 18:08)
- **Port**: 3001 (IPv4 and IPv6 bound)
- **Health check**: Responds `{"ok":true,"status":"live"}`
- **Config mode**: `local` (not cloud-connected)

### 2. Status File Status ✗ Stale
| File | Last Modified | Current |
|------|---------------|---------|
| `/root/.openclaw/workspace/memory/status.json` | 2026-03-09 20:56:58 | **STALE 19 days** |
| `/root/.openclaw/workspaces/ledger/status.json` | 2026-03-27 00:14 | ✓ Current |

The Ledger agent's status IS updating, so the gateway infrastructure works.

### 3. Scheduling Infrastructure
- **Crontab**: None configured (`no crontab for root`)
- **Systemd timers**: None for openclaw
- **Cron jobs file**: `/root/.openclaw/cron/jobs.json`
  - Contains one job: `sage-first-task` (marked `enabled: false`)
  - Status: **ERROR** - delivery failed on 2026-03-09
  - Error message: `"Channel is required (no configured channels detected). Set delivery.channel explicitly or use a main session with a previous channel."`
  - Configuration: `sessionTarget: "isolated"`, `delivery.mode: "announce"`, `delivery.channel: "last"`

### 4. Heartbeat Configuration ✓ Defined
- **File**: `/root/.openclaw/workspace/HEARTBEAT.md`
- **Frequency**: Every 60 minutes (per openclaw.json)
- **Expected behavior**:
  1. Read status.json
  2. Read daily memory file
  3. Check for pending tasks
  4. **Update status.json with current state**
- **Current status**: NOT executing

### 5. Gateway API Endpoints
- `GET /health` → ✓ Works (`{"ok":true,"status":"live"}`)
- `GET /` → ✓ Works (HTML UI returns)
- `GET /api/agents` → ✗ 404 Not Found
- `POST /api/agents/sage/heartbeat` → ✗ 404 Not Found

The agent API endpoints don't exist or are not registered.

### 6. Agent Configuration
- **Config file**: `/root/.openclaw/openclaw.json`
- **Agents configured**:
  - `sage` (id: "sage", default: true, workspace: `/root/.openclaw/workspace`)
  - `ledger` (id: "ledger", workspace: `/root/.openclaw/workspaces/ledger`)
- **Model**: `openai/gpt-5.4` (default)
- **Heartbeat**: `every: "60m"`

### 7. Recent Activity
- **Sage agent**: Completely inactive since 2026-03-09 20:57
- **Ledger agent**: Active (sessions.json updated 2026-03-28 07:14)
- **Update check**: Ran 2026-03-27 21:14 (system is checking for version updates)
- **Config audits**: Last write 2026-03-09 20:36

### 8. Log Files
- **Config audit log**: `/root/.openclaw/logs/config-audit.jsonl` (last entry 2026-03-09 20:36:57)
- **Cron run logs**: `/root/.openclaw/cron/runs/` (only contains one entry from initial failed task)
- **No systemd journal entries** for openclaw-gateway

---

## Root Cause

The Sage agent's heartbeat mechanism **never got initialized properly**. The initial cron job failed with a channel configuration error, and there is no fallback heartbeat system (no systemd timer, no crontab entry, no manual trigger script).

**Why the Ledger agent works but Sage doesn't**: The Ledger agent must be triggered differently—possibly through manual API calls or a different dispatch mechanism not present in the cron system.

---

## What's Broken

1. **No heartbeat dispatcher**: No crontab, systemd timer, or scheduled job running `sage-first-task` or any heartbeat equivalent
2. **Failed initialization**: The `sage-first-task` cron job errored on 2026-03-09 with channel configuration error
3. **No recovery mechanism**: The system didn't retry or fall back to an alternative trigger
4. **Missing agent API**: Gateway doesn't expose `/api/agents/sage/heartbeat` endpoint (or it's not initialized)
5. **Isolated delivery mode**: Job targets `sessionTarget: "isolated"` and `delivery.channel: "last"`, but "last" implies it should have a previous channel context

---

## What Would Fix It

### Option A: Fix the Original Cron Job (Recommended)
1. Modify `/root/.openclaw/cron/jobs.json`:
   - Change `"enabled": false` → `"enabled": true`
   - Change `"sessionTarget": "isolated"` → `"sessionTarget": "main"` (or provide explicit channel)
   - Change `"delivery.channel": "last"` → `"delivery.channel": "stdout"` or remove and use gateway default
2. Trigger the job manually or wait for the next system startup

### Option B: Add a Systemd Timer
Create `/etc/systemd/system/openclaw-sage-heartbeat.timer` and `.service` files to run heartbeat every 60 minutes via gateway API call.

### Option C: Add a Crontab Entry
Add entry to root's crontab:
```bash
*/60 * * * * curl -X POST -H "Authorization: Bearer <token>" http://localhost:3001/api/agents/sage/heartbeat
```
(Requires validating that this endpoint exists and works)

### Option D: Manual Script
Create `/usr/local/bin/sage-heartbeat.sh` to manually update status.json and trigger via cron/systemd.

---

## Criticality Assessment

**Impact**: 🟡 **MODERATE** (not critical, but concerning)

- **Why moderate, not critical**:
  - Sage agent is not actively failing or erroring
  - The gateway is stable and Ledger workspace is functioning
  - Status staleness is informational; the system isn't degrading

- **Why it still matters**:
  - No visibility into Sage agent health
  - Can't distinguish between "idle" and "broken"
  - Unknown if Sage has pending tasks waiting
  - If Sage is supposed to run proactive research (per HEARTBEAT.md), it's completely blocked

---

## Recommended Next Steps

1. **Quick fix**: Enable the existing cron job by changing `enabled: false` → `enabled: true` and fixing the delivery channel configuration
2. **Validation**: Trigger a manual heartbeat and verify status.json updates
3. **Monitoring**: Set up a systemd timer or crontab to ensure heartbeat runs every 60m going forward
4. **Investigation**: Determine why Ledger agent updates work but Sage doesn't—may reveal why the original job failed

