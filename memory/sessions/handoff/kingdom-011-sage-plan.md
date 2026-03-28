# Kingdom-011: Sage VPS Repurpose — Oracle Execution Migration Plan

**Date**: 2026-03-28
**Decision**: Yu, 2026-03-28 — repurpose Sage (204.168.140.12) from idle RewardsPro host to Oracle execution node
**Status**: PLAN ONLY — not yet executed
**Ticket**: kingdom-011

---

## 1. Current State

### Sage VPS (204.168.140.12)
- **Role** (fleet.py): `oracle-execution`, section `woodwinds`, instrument `French Horn`
- **OS**: Ubuntu Linux (root access via SSH)
- **OpenClaw**: Gateway running on port 3001, `local` mode
- **Heartbeat**: Fixed 2026-03-28 — sage-heartbeat cron job + sage-status-ping.py fallback active
- **Previous workload**: RewardsPro (Shopify loyalty app) — now idle
- **Debris**: Old RewardsPro files may exist; `sage-first-task` cron job still disabled in openclaw

### Local Mac Studio (Current Oracle Home)
Active cron entries (from `crontab -l`):
```
*/30 * * * *   oracle-run.py        — signal generation
*/15 * * * *   oracle-deliver.py    — alert delivery
*/15 * * * *   whale-activity-scanner.py
0 7,19 * * *   news_ingestor.py     — news pipeline
0 8 * * *      daily_briefing.py    — morning briefing (STAYS LOCAL)
0 */2 * * *    betting_signals.py   — odds API poll
```

### Prediction-Markets Repo
- **Location**: `~/Desktop/prediction-markets/`
- **Key scripts**: `scripts/oracle-run.py`, `scripts/oracle-deliver.py`, `scripts/whale-activity-scanner.py`, `scripts/kalshi-scanner.py`, `scripts/s012/news_ingestor.py`
- **Data dir**: `data/` — signals, logs, sqlite DB (`news-pipeline.db`)
- **Config**: `config/` — source maps, API keys (odds-api-key in JSON)
- **Requirements**: `requirements-pipeline.txt` (`httpx`, `anthropic`, `pyyaml`)

---

## 2. Task Allocation Decision

### Moves to Sage (24/7, server-appropriate)

| Task | Script | Current Schedule | Reason to Move |
|------|--------|-----------------|----------------|
| Signal generation | `oracle-run.py` | every 30 min | Pure data, no display needed |
| Signal delivery | `oracle-deliver.py` | every 15 min | Pure file writes |
| Whale scanner | `whale-activity-scanner.py` | every 15 min | API polling, no display |
| News ingestor | `s012/news_ingestor.py` | 07:00 + 19:00 | Headless pipeline, has Docker deploy already |
| Kalshi scanner | `kalshi-scanner.py` | (called by oracle-run.py) | Subprocess of oracle-run |

**Why these move**: They are headless, API-driven, write to files/DB. Running on a VPS means 24/7 uptime regardless of Mac sleep/lid state.

### Stays on Mac Studio

| Task | Script | Reason to Keep Local |
|------|--------|---------------------|
| Morning briefing | `engine/daily_briefing.py` | Uses `PYTHON=/opt/homebrew/bin/python3`, calls subprocess to run spike-detector interactively, output is intended for terminal display on Mac |
| Odds API poll | `engine/betting_signals.py` | Depends on local display + investigation workflow; low-frequency (every 2h) |
| Trade execution | via `vps-exec.sh` → Tokyo VPS | Security design: keys from macOS Keychain, never at rest — separate Tokyo execution VPS unchanged |

---

## 3. Migration Plan

### Phase 0: Pre-flight (local, no Sage changes)

**0.1 Inventory API keys needed on Sage**
Identify all secrets oracle scripts use:
- `POLYGONSCAN_API_KEY` — whale-activity-scanner.py reads from env or config
- `ANTHROPIC_API_KEY` — news_ingestor.py (anthropic>=0.40.0)
- Odds API key — in `config/source_bias.json` (plaintext — needs secure handling)
- Any Kalshi API credentials — check kalshi-scanner.py auth block
- Any Polymarket read-only keys — gamma API is public, no key needed

**Action**: Run `grep -r "api.key\|API_KEY\|os.environ\|getenv\|keychain" ~/Desktop/prediction-markets/scripts/ ~/Desktop/prediction-markets/engine/` to produce the full secret manifest before touching Sage.

**0.2 Snapshot current local crontab**
```bash
crontab -l > ~/Desktop/prediction-markets/deploy/mac-crontab-backup-20260328.txt
```
Preserve as rollback baseline.

**0.3 Verify Sage SSH connectivity**
```bash
python3 ~/Desktop/Love/tools/fleet.py sage "uname -a && df -h / && free -m"
```

---

### Phase 1: Sage Environment Setup

**1.1 Clean RewardsPro debris**
```bash
python3 tools/fleet.py sage "ls /var/www/ /home/ /root/ 2>/dev/null"
# Identify and remove RewardsPro files after confirming nothing needed
```

**1.2 Install Python 3.12+ and venv**
```bash
python3 tools/fleet.py sage "python3 --version || apt-get install -y python3 python3-pip python3-venv"
```

**1.3 Create oracle workspace**
```bash
python3 tools/fleet.py sage "mkdir -p /opt/oracle/{scripts,engine,data,config,calibration,bankroll,sources,strategies,domains,s012}"
```
Remote path: `/opt/oracle/` (clean, no openclaw entanglement)

**1.4 Create venv and install dependencies**
```bash
python3 tools/fleet.py sage "cd /opt/oracle && python3 -m venv .venv && .venv/bin/pip install httpx anthropic pyyaml requests"
```
Note: `oracle-run.py` uses only stdlib + subprocess. `news_ingestor.py` needs httpx + anthropic.

---

### Phase 2: Code Deployment

**2.1 Rsync prediction-markets to Sage** (excludes sensitive data, .git, archive)
```bash
rsync -avz --exclude='.git' --exclude='archive/' --exclude='data/*.db' \
  --exclude='*.log' --exclude='.env' --exclude='node_modules/' \
  ~/Desktop/prediction-markets/ root@204.168.140.12:/opt/oracle/
```

**2.2 Create empty data directories on Sage**
```bash
python3 tools/fleet.py sage "mkdir -p /opt/oracle/data/stream /opt/oracle/data/kalshi"
```

**2.3 Verify scripts landed**
```bash
python3 tools/fleet.py sage "ls /opt/oracle/scripts/ && ls /opt/oracle/scripts/s012/"
```

---

### Phase 3: API Key Deployment

**SECURITY NOTE**: Do NOT commit secrets. Do NOT put them in rsync. Inject via SSH env or write to `/opt/oracle/.env` with `chmod 600`.

**3.1 Create `/opt/oracle/.env` on Sage**
Template (fill in from local Keychain / secure storage):
```
POLYGONSCAN_API_KEY=<from-keychain>
ANTHROPIC_API_KEY=<from-keychain>
ODDS_API_KEY=987836b08da2a7a294864c50cde05c1f
KALSHI_EMAIL=<if-needed>
KALSHI_PASSWORD=<if-needed>
```

**3.2 Deploy via SSH heredoc** (never touches disk locally):
```bash
ssh root@204.168.140.12 'cat > /opt/oracle/.env << "ENVEOF"
POLYGONSCAN_API_KEY=...
ANTHROPIC_API_KEY=...
ENVEOF
chmod 600 /opt/oracle/.env'
```

**3.3 Update scripts to load `.env`**
Check if scripts use `python-dotenv` or raw `os.environ`. If not, add a one-liner to oracle-run.py and news_ingestor.py:
```python
from pathlib import Path
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
```
**Alternatively**: source `.env` in the crontab line: `source /opt/oracle/.env && python3 ...`

---

### Phase 4: Cron Installation on Sage

**4.1 Install crontab on Sage**
```bash
python3 tools/fleet.py sage "crontab -l 2>/dev/null; echo '---existing---'"
```

New crontab entries for Sage (use `/opt/oracle/.venv/bin/python3`):
```cron
# ORACLE-PIPELINE (moved from Mac Studio 2026-03-28)
*/30 * * * * cd /opt/oracle && /opt/oracle/.venv/bin/python3 scripts/oracle-run.py >> data/oracle-run.log 2>&1
*/15 * * * * cd /opt/oracle && /opt/oracle/.venv/bin/python3 scripts/oracle-deliver.py >> data/oracle-deliver.log 2>&1
*/15 * * * * cd /opt/oracle && /opt/oracle/.venv/bin/python3 scripts/whale-activity-scanner.py >> data/whale-scanner.log 2>&1
0 7,19 * * * cd /opt/oracle && /opt/oracle/.venv/bin/python3 scripts/s012/news_ingestor.py >> data/news-pipeline.log 2>&1
```

**4.2 Install via SSH**
```bash
ssh root@204.168.140.12 'crontab -l 2>/dev/null | { cat; echo "*/30 * * * * cd /opt/oracle && /opt/oracle/.venv/bin/python3 scripts/oracle-run.py >> data/oracle-run.log 2>&1 # ORACLE-PIPELINE"; echo "*/15 * * * * cd /opt/oracle && /opt/oracle/.venv/bin/python3 scripts/oracle-deliver.py >> data/oracle-deliver.log 2>&1 # ORACLE-PIPELINE"; echo "*/15 * * * * cd /opt/oracle && /opt/oracle/.venv/bin/python3 scripts/whale-activity-scanner.py >> data/whale-scanner.log 2>&1 # ORACLE-PIPELINE"; echo "0 7,19 * * * cd /opt/oracle && /opt/oracle/.venv/bin/python3 scripts/s012/news_ingestor.py >> data/news-pipeline.log 2>&1 # ORACLE-PIPELINE"; } | crontab -'
```

---

### Phase 5: Data Sync Strategy

**5.1 Signal data (oracle-alerts.md, pending-signals.json)**
- After migration, these files live on Sage at `/opt/oracle/data/`
- `daily_briefing.py` on Mac reads from `~/Desktop/prediction-markets/data/` — needs a pull sync

**Sync mechanism** — add to Mac crontab (runs before 08:00 briefing):
```cron
50 7 * * * rsync -az root@204.168.140.12:/opt/oracle/data/ ~/Desktop/prediction-markets/data/ 2>&1 | tee -a ~/Desktop/prediction-markets/data/sync.log
```

**5.2 Calibration data (predictions.jsonl)**
- `oracle-deliver.py` auto-appends high-confidence signals to `calibration/predictions.jsonl`
- On Sage, this writes to `/opt/oracle/calibration/predictions.jsonl`
- Mac needs this for briefing and manual review — same rsync pull covers it

**5.3 news-pipeline.db**
- SQLite db used by `news_ingestor.py` — stays on Sage (no local reads needed)
- If local analysis needed: `python3 tools/fleet.py sage "sqlite3 /opt/oracle/data/news-pipeline.db 'select count(*) from articles'"` or rsync on demand

**5.4 No two-way sync needed**
All writes happen on Sage. Mac only reads (daily_briefing). This avoids conflicts.

---

### Phase 6: Local Cron Cleanup

After confirming Sage crons are running cleanly (≥2 successful runs observed in logs):

```bash
# Remove Oracle pipeline entries from Mac crontab
crontab -l | grep -v "# ORACLE-PIPELINE\|oracle-run\|oracle-deliver\|whale-activity-scanner\|news_ingestor.*oracle" | crontab -
```

**Keep on Mac**:
- `oracle-daily-briefing` (daily_briefing.py at 08:00)
- `odds-api-poll` (betting_signals.py)
- openclaw weekly check
- backup-push.sh
- quota_monitor.py

---

### Phase 7: Monitoring via Sentry

**7.1 Sentry DSN**
The `sentry` node (135.181.28.252) handles Kingdom monitoring. Check if there's an existing Sentry project for oracle tasks, or create `oracle-pipeline` project via sentry VPS.

**7.2 Add Sentry to oracle scripts** (minimal, no package needed — use HTTP API):
```python
import urllib.request, json, os, traceback

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

def sentry_capture(error_msg, script_name):
    if not SENTRY_DSN:
        return
    # ... simple HTTP POST to Sentry store endpoint
```
Alternatively: use `sentry-sdk` — add to requirements-pipeline.txt.

**7.3 Alert thresholds**
- oracle-run.py exits non-zero → Sentry error
- No signals generated in 2 hours → Sentry warning
- news_ingestor.py fails → Sentry error

**7.4 fleet.py integration**
Current `fleet.py health` checks `systemctl list-units` for `openclaw|agent|nginx|node|nats|cron`. Oracle crons run as root crontab — visible via `systemctl status cron`.

For enhanced visibility, add to oracle-run.py: write `data/oracle-status.json` (already does this) and confirm fleet.py `logs sage` can tail it.

---

## 4. Rollback Plan

**If Sage fails or crons stop running:**

1. **Immediate**: Re-enable Mac crontab entries from backup
   ```bash
   # Restore from backup
   cat ~/Desktop/prediction-markets/deploy/mac-crontab-backup-20260328.txt | crontab -
   ```

2. **Data recovery**: Any signals on Sage sync'd to Mac via rsync; nothing is lost since signals are append-only

3. **Detection**: If `oracle-alerts.md` stops updating for >2 hours (check modification time), treat as Sage failure

4. **Dual-run period**: Before removing Mac crons, run both Mac and Sage in parallel for 48h. Compare `oracle-status.json` outputs. Remove Mac entries only after parity confirmed.

---

## 5. Execution Checklist (in order)

```
[ ] Phase 0.1 — Secret manifest (grep for all API key usage)
[ ] Phase 0.2 — Snapshot Mac crontab to deploy/mac-crontab-backup-20260328.txt
[ ] Phase 0.3 — Verify Sage SSH via fleet.py
[ ] Phase 1.1 — Clean RewardsPro debris (inspect before removing)
[ ] Phase 1.2 — Install Python 3.12 on Sage
[ ] Phase 1.3 — Create /opt/oracle/ workspace dirs
[ ] Phase 1.4 — Create .venv + install deps
[ ] Phase 2.1 — rsync prediction-markets/ to Sage (no secrets, no .git)
[ ] Phase 2.2 — Create data/stream, data/kalshi dirs on Sage
[ ] Phase 2.3 — Verify scripts landed
[ ] Phase 3.1 — Create /opt/oracle/.env template
[ ] Phase 3.2 — Deploy secrets to Sage via SSH heredoc
[ ] Phase 3.3 — Confirm scripts load .env
[ ] Phase 4.1 — Check Sage crontab baseline
[ ] Phase 4.2 — Install Oracle cron entries on Sage
[ ] Phase 5.1 — Add rsync pull to Mac crontab (07:50 daily)
[ ] Phase 6 (deferred) — Remove Mac oracle crons after 48h dual-run
[ ] Phase 7 — Add Sentry integration to oracle scripts
```

---

## 6. Open Questions (to resolve before execution)

1. **Kalshi auth**: Does `kalshi-scanner.py` require API credentials beyond public endpoints? Check auth block.
2. **Polygonscan key**: Is it in env, config JSON, or hardcoded? `whale-activity-scanner.py` uses `POLYGONSCAN_API` constant — check if it includes the key or if it's a separate env var.
3. **RewardsPro debris**: What exactly is on Sage from the RewardsPro era? Confirm nothing needed before wiping.
4. **sqlite on Sage**: `news-pipeline.db` needs sqlite3. Confirm it's present (`apt list --installed | grep sqlite`).
5. **betting_signals.py dependency check**: Does it import from any script that oracle-run.py also imports? If yes, it can share the Sage venv even if cron stays on Mac.
6. **Daily briefing read path**: After migration, briefing reads from `~/Desktop/prediction-markets/data/`. Confirm the 07:50 rsync pull reliably completes before the 08:00 briefing cron fires.

---

## 7. Architecture After Migration

```
Mac Studio (local)                     Sage VPS (204.168.140.12)
─────────────────────                  ──────────────────────────
daily_briefing.py (08:00)  ←─ rsync ── oracle-run.py (*/30)
betting_signals.py (*/2h)              oracle-deliver.py (*/15)
trade execution                        whale-activity-scanner.py (*/15)
  └→ Tokyo VPS (45.77.8.39)           news_ingestor.py (07:00, 19:00)
       └→ Polymarket CLOB              kalshi-scanner.py (subprocess)

                                       /opt/oracle/data/
                                         pending-signals.json
                                         oracle-alerts.md
                                         oracle-status.json
                                         news-pipeline.db
                                         calibration/predictions.jsonl
```

Sage's existing openclaw/heartbeat infrastructure (port 3001, sage-heartbeat cron, sage-status-ping.py) continues running independently and does not interfere with the Oracle workspace at `/opt/oracle/`.
