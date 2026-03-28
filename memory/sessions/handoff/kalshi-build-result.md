# Kalshi Scanner Build Result
**Date**: 2026-03-28
**Built by**: Claude Sonnet 4.6
**Status**: COMPLETE — all phases implemented and tested

---

## What Was Built

### New file: `scripts/kalshi-scanner.py` (~310 lines)

All six functions from the design doc implemented:

| Function | Status |
|----------|--------|
| `fetch_kalshi(path, params)` | HTTP GET with User-Agent, error handling |
| `fetch_kalshi_series_markets(series_ticker)` | Cursor pagination, vol<10 filter |
| `kalshi_price_to_float()` / `kalshi_mid_price()` | Dollar string → float, bid/ask mid |
| `kalshi_fee(price)` | Quadratic: `0.07 * p * (1-p)` |
| `fetch_polymarket_prices(query)` | Gamma API cross-reference |
| `match_cross_market(title, poly_markets, invert)` | Word-overlap Jaccard, invert flag |
| `compute_arb_signal(...)` | Fee-adjusted gap, 3pp minimum, score = floor(gap_pp/2) |
| `build_fed_distribution(meeting_markets)` | 5-outcome FOMC distribution, overround flag |
| `run_scan(output_json)` | Full pipeline, snapshot save, arb JSONL append |
| `show_series()` | Market count + volume per series |
| `main()` | `--json`, `--snapshot`, `--series` flags |

### New directory: `data/kalshi/`
- `snapshot-2026-03-28.json` — first snapshot (created on test run)
- `arb-signals.jsonl` — running arb signal log (1 signal on first run)

### Modified: `scripts/oracle-run.py`
- Added `KALSHI_SCANNER` path constant
- Added `run_kalshi_scanner()` function (mirrors `run_whale_scanner()` pattern)
- Wired into `run_once()` after whale scanner — `kalshi_added` counted in `total_new`
- Wired into `run_loop()` inside `cycle % 2 == 0` block (every 30 min, same as spikes)

---

## Test Results

```
$ python3 scripts/kalshi-scanner.py --series

KXFEDDECISION        71 markets  vol=$7,940,819  [OK]
KXRATECUT             1 markets  vol=$   63,588  [OK]
KXUSNFP               0 markets  vol=$        0  [EMPTY]
OILW                  0 markets  vol=$        0  [EMPTY]
CPIYOY                0 markets  vol=$        0  [EMPTY]
KXUE                 37 markets  vol=$   16,374  [OK]
```

```
$ python3 scripts/kalshi-scanner.py --snapshot

[KXFEDDECISION] 71 markets
  15 meeting distributions built (KXFEDDECISION-26APR through KXFEDDECISION-28JAN)
  Example: KXFEDDECISION-26APR: hold=95.5% cut=3.0% hike=2.0% [OK]

[KXRATECUT] 1 market
  ARB: KXRATECUT-26DEC31 raw_gap=10.6pp net=7.7pp score=3

Snapshot: data/kalshi/snapshot-2026-03-28.json
Markets:  109 total
Arb signals: 1
Fed distributions: 15 meetings
```

```
$ python3 scripts/kalshi-scanner.py --json | python3 -c "..."
Signals: 1
  [3] BUY YES on Polymarket (underpriced vs Kalshi by 7.7pp)
```

---

## Active Arb Signal Detected

**KXRATECUT-26DEC31 vs Polymarket "No Fed rate cuts in 2026"**
- Kalshi: ~59% YES (rate cut will happen)
- Polymarket: "No Fed rate cuts" ~34.9% YES → 65.1% comparable
- Raw gap: 10.6pp, net after fees: 7.7pp
- Score: 3 (actionable — design doc threshold was 3pp minimum)
- Trade: BUY YES on Polymarket (underpriced vs Kalshi)

This confirms the known gap from design doc section 3.

---

## Key API Findings

- **KXUSNFP, OILW, CPIYOY** all returned EMPTY (no active markets with vol>=10 as of Mar 28)
- **KXFEDDECISION** is the richest series: 71 markets, $7.9M volume, 15 meetings through Jan 2028
- **KXUE** has 37 markets but very thin ($16K volume) — matches low enough to skip most arb
- **FOMC distributions** show systematic underround on near-term meetings (e.g., Jan 2028, Jul 2027) — probabilities sum to ~95%, suggesting illiquid outer strikes

---

## What's Ready for Oracle

- `oracle-run.py` will log `"Kalshi signals: N found, M new"` on every run
- Arb signals use `source="kalshi-scanner"`, `type="CROSS_PLATFORM_ARB"`, `domain="ECO"`
- Signals are deduplicated by deterministic ID (`kalshi-arb-{hash}`) — safe to run repeatedly
- oracle-deliver.py requires no changes — handles any signal with `score >= 4` already

---

## Follow-on Tasks (not built)

- No separate cron added (design doc recommends wiring into oracle-run.py only — done)
- KXUSNFP/OILW/CPIYOY: monitor monthly — these open near data release dates
- `match_confidence` threshold of 0.10 is conservative — may need tuning if matches remain sparse
- Fed distribution vs Polymarket comparison (`vs_polymarket` field) not fully wired — data is in snapshot but not computed against ECO/active.md prices automatically
