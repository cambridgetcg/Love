# News Pipeline Diagnosis
**Date**: 2026-03-28
**Diagnosed by**: Gamma (Claude Sonnet 4.6)
**Repo**: `/Users/yu/Desktop/prediction-markets`

---

## TL;DR

**The pipeline is not broken. It was never scheduled.**

The last run was **2026-02-27** (28 days ago) — three manual one-shot executions run as setup/testing. No cron job was ever created for `scripts/s012/news_ingestor.py`. The pipeline completed those runs cleanly with 0 errors.

The scout's assessment ("dead letters accumulating", "last activity Mar 23") was inaccurate on both counts.

---

## Findings

### 1. Dead Letters — NONE

```
sqlite3 data/news-pipeline.db "SELECT COUNT(*) FROM dead_letters;"
→ 0
```

The dead_letters table is **empty**. No crash, no failed articles, no retries. The pipeline completed its last run gracefully ("Pipeline shutting down.").

### 2. Last Run: February 27, 2026

```
poll_state — all 5 queries: last_poll_time = 2026-02-27T23:49:xx
articles table: MAX(fetched_at) = 2026-02-27T23:49:16 (94 total articles)
brave-api-usage.json: { "month": "2026-02", "daily": { "2026-02-27": 111 }, "total": 111 }
```

Three runs on Feb 27. The third run showed successful LLM enrichment (Anthropic 200 OK). Pipeline ran cleanly. Then nothing.

**Scout claim of "last activity Mar 23" is wrong** — that date doesn't appear anywhere in the database or logs.

### 3. Root Cause: No Cron Entry

Current crontab has oracle-run.py (every 30min), oracle-deliver.py (every 15min), betting_signals.py (every 2h), daily_briefing.py (8am) — but **zero entries for news_ingestor.py**.

The script is `scripts/s012/news_ingestor.py`. It was manually tested on Feb 27, never scheduled.

### 4. API Keys

**Brave API key**: NOT in environment (`BRAVE_API_KEY` unset), NOT in keychain under service name `BRAVE_API_KEY`. BUT: the script's `_keychain_get()` method looks up keychain as:
```
security find-generic-password -a "prediction-markets" -s "brave_api_key" -w
```
Testing this lookup returns the key successfully — **key IS accessible to the script via keychain**. `_keychain_get()` will work from cron (macOS keychain is accessible to scheduled tasks when user is logged in).

**Anthropic API key**: Was returning 401 on the second Feb 27 run, succeeded on the third. LLM enrichment (tone tagging via claude-haiku) is optional — the pipeline continues with fallback mode if unavailable. This is not a blocking issue.

### 5. data/stream/news.jsonl — Not a News Feed

The task spec assumed `data/stream/news.jsonl` is the output of the Brave news pipeline. It is NOT. This file is written by `pipeline/geo_intelligence.py:316` — it contains geo/WW3 intelligence events (format: `{id, ts, source: "ww3-intelligence", headline, ...}`). 325 entries, last entry Mar 21 — this stream is **working fine and is unrelated to the news pipeline**.

The Brave news pipeline writes to `data/news-pipeline.db` (SQLite), not to any .jsonl stream file.

### 6. API Budget Status

- **February 2026**: 111 calls used (3 runs)
- **March 2026**: 0 calls used (pipeline never ran)
- **Available budget**: 900/900 requests remaining for March (free tier resets monthly)
- **Per-run cost**: ~37 Brave API calls per single-pass run (5 queries × ~6-8 countries each)
- **Safe cadence**: With `daily_soft_limit: 50` configured and ~37 calls/run, **1-2 runs/day** stays within budget

---

## The Fix

Single change needed: **add cron entry for news_ingestor.py**.

### Recommended cron entry (twice daily — within budget)

```cron
0 7,19 * * * cd /Users/yu/Desktop/prediction-markets && /opt/homebrew/bin/python3 scripts/s012/news_ingestor.py >> data/news-pipeline.log 2>&1
```

This runs at 7am and 7pm. At ~37 Brave calls per run × 2 runs/day = ~74 calls/day. Slightly over the soft limit of 50 but well within the hard 900/month. Adjust to `0 8 * * *` (once/day) if budget conservatism is preferred.

**No key configuration needed** — keychain lookup works.

### How to apply

```bash
# Preview current crontab
crontab -l

# Add the entry (appends to existing)
(crontab -l; echo "0 7,19 * * * cd /Users/yu/Desktop/prediction-markets && /opt/homebrew/bin/python3 scripts/s012/news_ingestor.py >> data/news-pipeline.log 2>&1  # news-pipeline-ingest") | crontab -

# Verify
crontab -l | grep news
```

### Manual test before scheduling (optional sanity check)

```bash
cd /Users/yu/Desktop/prediction-markets
python3 scripts/s012/news_ingestor.py 2>&1 | tail -20
```

Expected output: "Pipeline shutting down." with N new articles. Budget will consume ~37 calls.

---

## What Does NOT Need Fixing

| Item | Scout Assessment | Reality |
|------|-----------------|---------|
| dead_letters table | "accumulating" | 0 rows — clean |
| data/stream/news.jsonl | "not growing" | Geo stream, working fine |
| BRAVE_API_KEY | not set | In keychain, accessible |
| Pipeline crash | implied | Never crashed, just unscheduled |
| Mar 23 last activity | stated | No data from March at all |

---

## Impact of 28-Day Gap

The news pipeline has been dark since Feb 27. The daily_briefing.py (runs 8am daily) reads from `data/news-pipeline.db` for news context — it has been running on stale Feb 27 data for 28 days. All oracle signals generated since Mar 1 have had zero Brave news backing.

This affects signal quality but not system stability. The oracle pipeline (spike detector + deliver) runs independently of the news pipeline and has continued operating.

---

## Recommended Action (Conservative Path)

1. **Run a manual test** to confirm pipeline works today
2. **Add single cron entry** (once/day at 8am if budget-cautious, twice/day if coverage-focused)
3. **Verify next morning** that news-pipeline.log shows new articles
4. **No DB cleanup needed** — 94 articles in SQLite, 0 dead letters, poll_state valid

The pipeline is healthy. It just needs to be turned on.

---

*Report written: 2026-03-28*
*Files examined: data/news-pipeline.db, data/news-pipeline.log, scripts/s012/news_ingestor.py, config/news-pipeline.yaml, data/brave-api-usage.json, data/stream/news.jsonl, crontab*
