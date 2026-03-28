# Kingdom-003: Oracle Scout Assessment
**Date**: 2026-03-28
**Scout**: Claude (Sonnet 4.6)
**Repo**: `/Users/yu/Desktop/prediction-markets`
**Mission**: Map the Oracle's current state; identify path from 0/10 to 10/10 scored predictions within 2 weeks.

---

## 1. WHAT EXISTS

### Architecture Overview
A **multi-layered forecasting and trading observatory** designed to beat prediction markets through information asymmetry + calibrated probability estimation.

```
INPUTS                         SYNTHESIS                    OUTPUTS
────────────────────────────────────────────────────────────────────
Spike signals (oracle-run.py)  → engine/synthesise.py     → alerts.md
Whale signals (MISSING)        → engine/decision_engine.py → trade recs
Geo intelligence (injected)    → engine/scenario_tree.py  → scenarios
Betting lines (odds-api.py)    → engine/daily_briefing.py → morning brief
Domain knowledge (domains/)    → calibration.md            → Brier score
```

**Deployment stack:**
- Mac Studio: research, analysis, calibration
- Vultr Tokyo VPS (45.77.8.39): execution (geofence bypass)
- Polygon wallet: `0x4576F0B2b9Fe86359C6254Fc0C141d8C5090cDC3` (USDC.e)

### Data Sources

| Source | Status | Purpose | Config |
|--------|--------|---------|--------|
| Polymarket Gamma API | ✅ Live | Market metadata, prices, orderbook | hardcoded |
| Polymarket CLOB API | ✅ Live | Price history, trade execution | hardcoded |
| The Odds API | ✅ Live | Line movement, sharp money (20K quota) | `config/api-keys.json` |
| OddsPapi | ✅ Integrated | Pinnacle data, 348 books, historical CLV | `config/api-keys.json` |
| Betfair | ✅ Documented | Peer-to-peer exchange consensus | planned |
| FRED | ⚠️ Designed | CPI, PCE, unemployment, treasury yields | not wired |
| GDELT | ⚠️ Designed | Global event database (15-min updates) | not wired |
| Kalshi | ⚠️ Designed | Fed, CPI, NFP markets | not wired |
| Manifold | ⚠️ Designed | Long-horizon, AI questions | not wired |
| Guardian API | ⚠️ Designed | Full-text news GEO/ECO | not wired |
| BrightData | ⚠️ Ready | Web scraping ($960.45 balance) | not wired |

**Full spec**: `engine/DATA-SOURCES.md` (275 lines)

### Engine Modules (`engine/`)

| File | Lines | Function |
|------|-------|----------|
| `daily_briefing.py` | ~150 | Morning intel: predictions, spikes, portfolio state |
| `synthesise.py` | ~200 | Events → P(event) + confidence intervals |
| `scenario_tree.py` | ~200 | Event consequences across asset classes |
| `decision_engine.py` | ~200 | Kelly sizing, edge vs market, trade recs |
| `market_data.py` | ~450 | Unified API layer (Poly, Kalshi, Manifold, FRED, equities) |
| `betting_signals.py` | ~650 | STEAM moves, reverse line, dropping odds, CLV, divergence |
| `geo_layer.py` | ~200 | WW3 escalation level → regime adjustments (GLD/TLT/DXY) |

### Domains (10 total)

| Domain | Status | Markets Tracked | Research Depth |
|--------|--------|-----------------|----------------|
| GEO | 🔥 Active | 11 (Iran war focus) | sparse, needs update |
| POL | 🔥 Active | Fed Chair, 2028 election, UK | 2 deep research files |
| ECO | 🔥 Active | Fed rates, CPI, crude oil | moderate |
| TEC | 🌱 Seeded | — | ai-landscape-2026.md |
| LAW | 🌱 Seeded | — | regulatory-landscape-2026.md |
| FIN, CRY, SCI, SOC, ENV | 📄 Template | — | skeleton only |

### Strategies (14 playbooks)

| ID | Name | Phase | Backtested |
|----|------|-------|------------|
| S004 | Contrarian Overreaction | ALBEDO | ✅ |
| S006 | Time Decay | ALBEDO | ✅ |
| S007 | Cross-Market Arb | ALBEDO | ✅ |
| P01/P03 | New Market First-Mover | ALBEDO | ✅ |
| P04/R04 | Fast Resolution | Active | ✅ |
| S016 | Insider Follow | Active | partial |
| S001 | Hold to Resolution | Pending | — |
| S011 | Bond Rotation | Design | — |
| S012 | LLM Ensemble | Planned | — |

### Calibration (`calibration/`)
- **10 predictions logged**, 16 resolutions
- **Brier score: 0.208** (vs market 0.291) — 28% better
- **Beat rate: 56%** (9/16 markets)
- **NO expertise: 83% beat rate** on NO predictions
- **YES weakness: 40% beat rate** — systematic underestimation
- 18 lessons captured: `calibration/lessons.md` (L01-L18, T12-T18)

---

## 2. WHAT IS WORKING

### Live Pipelines (confirmed running March 28)

| System | Cron | Uptime | Volume |
|--------|------|--------|--------|
| Oracle spike-detector | every 30 min | 11 days | 246 signals generated |
| Oracle alert delivery | every 15 min | 11 days | 224 signals delivered |
| Betting signals | daily | — | `data/betting-signals.log` (27KB) |
| Daily briefing | morning | — | `data/briefing.log` (18KB) |

**Evidence**: `data/oracle-status.json` — last run `2026-03-28 00:00:03`, status: `LIVE`, uptime since `2026-03-17 14:05 UTC`

**Signal pipeline**: `oracle-run.py` → `data/pending-signals.json` (149KB, 150+ queued) → `oracle-deliver.py` → `data/oracle-alerts.md` (83KB, 2748 lines)

### Active Trading
- 12 positions open (`data/active-positions.json`, Mar 21)
- GEO-heavy: Iran ceasefire, conflict by May 15, Kharg Island, regime fall, crude oil hedges
- Timeframes: 5 positions resolve Mar 31, 7 resolve Apr 12-30
- ~$60 deployed, $1,250 bankroll (Phase 1 limit)

### Prediction Accuracy (proven)
- 56% beat rate is real; calibration system working
- Fast-resolution events (SOTU batch) generate 12 resolutions in 24h — gold calibration signal

---

## 3. WHAT IS MISSING FOR FIRST LIVE PREDICTIONS

### Critical Gaps (blocking scored predictions)

**GAP-1: Whale scanner script missing** (SEVERITY: HIGH)
`oracle-run.py` logs "Whale scanner not found — skipping" every 30 min.
Expected: `scripts/whale-activity-scanner.py`
Impact: 0 on-chain whale signals; one of two oracle signal legs is dark.

**GAP-2: Prediction logging rate = 1/day** (SEVERITY: HIGH)
Only 10 predictions logged in 11 days. For scored predictions you need 50+ to measure calibration.
Root cause: Human bottleneck. Oracle fires 224 alerts but humans aren't converting to logged predictions.
Fix: Auto-log high-confidence oracle signals directly to `predictions.jsonl`.

**GAP-3: Geo bridge not wired into Oracle** (SEVERITY: MEDIUM)
`pipeline/geo_intelligence.py` (463 lines) exists and `data/stream/geo_intelligence.jsonl` is being populated, but oracle-run.py does NOT read this stream.
Confirmed in `pipeline/oracle-ww3-fusion-design.md`: "Oracle reads the geo_intelligence.jsonl stream — currently Oracle doesn't ingest this file."
Fix: Wire geo_intelligence.jsonl ingestion into oracle-run.py signal scoring.

**GAP-4: News pipeline stalled** (SEVERITY: MEDIUM)
Last `data/news-pipeline.db` activity: Mar 23. Dead letters accumulating in SQLite.
Daily briefing (Mar 27) still running but quality degrading without fresh news.
Fix: Diagnose dead_letters table, clear and restart news ingest.

**GAP-5: Domain research sparse** (SEVERITY: MEDIUM)
6 of 10 domains (FIN, CRY, SCI, SOC, ENV, FIN) have template-only files.
Predictions in these domains will be unanchored — higher error rate.
Fix: At minimum seed CRY and FIN with current context.

**GAP-6: Bankroll state corrupted** (SEVERITY: LOW for predictions, HIGH for trading)
`bankroll/state.json` shows `current: $215.69` vs `$1,250 initial` with only `$60 deployed` and `0 resolutions`.
Tracking bug makes PnL reporting unreliable.

**GAP-7: API keys in git** (SEVERITY: LOW for function, HIGH for security)
`config/api-keys.json` contains plaintext odds-api keys committed to repository.

### What's NOT Missing
- ✅ Market data access (Polymarket API working, no auth needed)
- ✅ Calibration schema (predictions.jsonl + resolutions.jsonl format solid)
- ✅ Strategy playbooks (S004/S006/S007/P03/P04 all documented)
- ✅ Scoring infrastructure (Brier score calculator in `scripts/calibration-report.py`)
- ✅ Domain framework (active.md structure good for GEO/POL/ECO)

---

## 4. RECOMMENDED NEXT STEPS: 0/10 → 10/10 IN 2 WEEKS

### Week 1: Fix Signal Quality + Volume (Days 1-7)

**Day 1-2: Unlock whale signals**
1. Write `scripts/whale-activity-scanner.py` — query Polygonscan for top wallet activity on Polymarket contracts
2. Wire output to `data/pending-signals.json` with same schema as spike-detector
3. Verify in oracle-run.log: "Whale scanner: N signals found"

**Day 2-3: Wire geo bridge**
1. In `scripts/oracle-run.py`, add ingestion of `data/stream/geo_intelligence.jsonl`
2. Score geo signals same as spike signals (conflict escalation → score bump for GEO domain markets)
3. Test: escalation event should elevate relevant GEO market alerts

**Day 3-4: Auto-log high-confidence signals**
1. In `scripts/oracle-deliver.py`, add: if signal.score >= 7, auto-log to `calibration/predictions.jsonl`
2. Include market price at time of signal, confidence = "oracle-auto", reasoning = signal.context
3. Target: 10+ auto-logged predictions per day (replace manual bottleneck)

**Day 4-5: Restart news pipeline**
1. Check `data/news-pipeline.db` dead_letters — identify failing feed
2. Clear dead letters, restart news ingest script
3. Verify `data/stream/news.jsonl` is growing again

**Day 6-7: Fix bankroll tracking + secure keys**
1. Audit `bankroll/state.json` against `data/active-positions.json` positions
2. Reconcile current balance (wallet query or manual audit)
3. Move `config/api-keys.json` to `.gitignore`, use env vars or secrets vault

### Week 2: Increase Resolution Rate + Calibrate (Days 8-14)

**Day 8-9: Target fast-resolution markets**
1. Run `scripts/fast-resolution-screener.py` daily
2. Log predictions on markets resolving within 7 days (aim: 20+ per week)
3. Use `calibration/fast-resolution-calendar.md` (60-day calendar already built)

**Day 10-11: Seed CRY + FIN domains**
1. Research current BTC/ETH context for CRY domain
2. Add equity market context (SPX levels, VIX, earnings season) to FIN domain
3. These feed synthesise.py with better priors for those domains

**Day 12-13: Close first positions + capture resolutions**
1. Mar 31 positions resolving (5 positions) → immediately log to resolutions.jsonl
2. Add lessons (L19+) for each resolution
3. Run `calibration-report.py` with updated N

**Day 14: Score assessment**
1. Target: 30+ predictions logged, 15+ resolutions, Brier < 0.20
2. Run full calibration report
3. Identify which oracle signals correlate with actual beat-market performance

### Score Milestones

| Day | Target N predictions | Target resolutions | Target Brier | Metric |
|-----|---------------------|-------------------|--------------|--------|
| 3 | 10 auto-logged | 10 (existing) | 0.208 | baseline |
| 7 | 40 | 10 | 0.200 | whale+geo wired |
| 10 | 70 | 20 | 0.190 | news restored |
| 14 | 120 | 40 | 0.180 | fast-res harvested |

---

## 5. GAMMA VS BETA ATTENTION MAP

### Needs GAMMA (builder — write code, build systems)

| Task | File | Priority |
|------|------|----------|
| Write whale-activity-scanner.py | `scripts/whale-activity-scanner.py` (NEW) | 🔴 P0 |
| Wire geo_intelligence.jsonl into oracle-run.py | `scripts/oracle-run.py:~100` | 🔴 P0 |
| Auto-log high-score signals to predictions.jsonl | `scripts/oracle-deliver.py:~80` | 🔴 P0 |
| Fix dead_letters in news-pipeline.db | `scripts/` (diagnose) | 🟡 P1 |
| Fix bankroll state.json tracking | `bankroll/` (audit + fix) | 🟡 P1 |
| Secure API keys (env vars) | `config/api-keys.json` → `.gitignore` | 🟢 P2 |
| Seed CRY domain research | `domains/CRY/research/` | 🟢 P2 |
| Wire FRED API into market_data.py | `engine/market_data.py:~200` | 🟢 P2 |

### Needs BETA (coordinator — research, analysis, judgment calls)

| Task | Artifact | Priority |
|------|----------|----------|
| Review 224 delivered alerts for missed high-quality signals | `data/oracle-alerts.md` | 🔴 P0 |
| Log predictions on Mar 31 expiry markets (5 positions) | `calibration/predictions.jsonl` | 🔴 P0 |
| Update `domains/GEO/active.md` (last updated Mar 21) | `domains/GEO/active.md` | 🟡 P1 |
| Update `domains/POL/active.md` (last updated Mar 9 — stale) | `domains/POL/active.md` | 🟡 P1 |
| Evaluate Mar 31 position exits: Iran ceasefire, Kharg Island | `data/active-positions.json` | 🟡 P1 |
| Identify S004 opportunities in post-war market environment | `strategies/playbooks/S004` | 🟡 P1 |
| Assess whale registry: ricosuave666 current positioning | `data/whale-registry.json` | 🟢 P2 |
| Calibration lesson capture post-first resolutions | `calibration/lessons.md` | 🟢 P2 |

---

## QUICK REFERENCE: KEY FILE PATHS

```
engine/
├── oracle-run.py (cron 30min, ENTRY POINT)
├── oracle-deliver.py (cron 15min)
├── betting_signals.py (~650 lines, The Odds API + OddsPapi)
├── geo_layer.py (~200 lines, WW3 → regime, NOT YET WIRED)
├── market_data.py (~450 lines, unified API layer)
├── daily_briefing.py (~150 lines)
├── synthesise.py (~200 lines)
├── decision_engine.py (~200 lines)
└── DATA-SOURCES.md (275 lines, full source spec)

data/
├── oracle-alerts.md (83KB, 2748 lines — delivered signals)
├── oracle-run.log (316KB — 11 days execution trace)
├── oracle-status.json (system health: LIVE)
├── pending-signals.json (149KB — 150+ queued)
├── active-positions.json (12 live trades, Mar 21)
├── betting-signals.log (27KB — daily line movement)
├── briefing.log (18KB — morning intel)
└── news-pipeline.db (812KB — SQLite, STALLED Mar 23)

calibration/
├── predictions.jsonl (10 entries — NEEDS MORE)
├── resolutions.jsonl (16 entries)
├── calibration.md (Brier 0.208, 56% beat rate)
├── lessons.md (18 lessons L01-L18)
└── by-domain/ (GEO.json, POL.json, ECO.json)

pipeline/
├── geo_intelligence.py (463 lines — NOT WIRED)
└── oracle-ww3-fusion-design.md (design spec)

config/
└── api-keys.json (⚠️ PLAINTEXT KEYS IN GIT)

bankroll/
└── state.json (⚠️ CORRUPTED: $215.69 vs $1,250 initial)
```

---

## ASSESSMENT SUMMARY

**Current state: 3/10**
- Oracle is technically live and running (infrastructure solid)
- Signal quality is limited (whale scanner missing, geo bridge unwired)
- Prediction volume is too low for meaningful calibration (10 in 11 days)
- No resolutions yet (first batch: Mar 31)

**Path to 10/10:**
1. Wire the two dark signal legs (whale scanner + geo bridge) — **2 days**
2. Auto-log high-score alerts to calibration — **1 day**
3. Harvest Mar 31 resolutions + fast-resolution screener — **ongoing**
4. Reach N=50+ predictions with N=20+ resolutions — **~10 days**

The machinery is 80% built. The gap is signal integration and prediction volume. Both are Gamma tasks (code changes) + Beta tasks (market monitoring). First real calibration signal arrives Mar 31.
