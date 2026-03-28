# Oracle Auto-Log Implementation Result
**Date**: 2026-03-28
**Builder**: Gamma (Claude Sonnet 4.6)
**Task**: GAP-2 from kingdom-003 — auto-log high-confidence oracle signals to calibration/predictions.jsonl

---

## What Was Built

Modified `scripts/oracle-deliver.py` to auto-append high-confidence signals to `calibration/predictions.jsonl`.

### Changes Made

**File**: `scripts/oracle-deliver.py`

1. **New constants** (line 29-30):
   - `AUTO_LOG_SCORE = 7` — threshold for auto-logging (configurable)
   - `PREDICTIONS_FILE` path constant

2. **New imports**: `re`, `sys`

3. **Four new helper functions**:
   - `_parse_yes_price_from_trade(trade_str)` — extracts current YES price from "BUY YES at X%" or "BUY NO at X%" strings
   - `_parse_yes_target(target_str)` — extracts target YES price from "YES rises/drops to X%"
   - `_load_prediction_questions()` — loads existing question strings for deduplication
   - `_next_pred_id()` — finds next sequential pred-XXXX id

4. **Main function**: `auto_log_predictions(signals, dry_run=False)`:
   - Filters signals with `score >= AUTO_LOG_SCORE`
   - Deduplicates by market question (skips already-logged markets)
   - Parses market_price and my_estimate from trade/target fields
   - Builds prediction entry matching `predictions.jsonl` schema
   - Appends to file (or dry-run prints preview)
   - Returns count of logged predictions

5. **`deliver()` updated**:
   - Calls `auto_log_predictions(to_deliver)` on each delivery batch
   - On "no new signals" path: backfill from previously-delivered high-score signals (catches signals that existed before this feature was deployed)
   - `--dry-run` flag threads through both paths

6. **`__main__` updated**: reads `--dry-run` from `sys.argv`

### Prediction Schema (generated entries)

```json
{
  "id": "pred-0011",
  "ts": "2026-03-28T00:45:39+00:00",
  "domain": "CRY",
  "question": "Backpack FDV above $700M one day after launch?",
  "market_price": 0.075,
  "my_estimate": 0.249,
  "confidence_interval": [0.149, 0.349],
  "resolution_date": null,
  "resolved": null,
  "outcome": null,
  "brier_score": null,
  "beat_market": null,
  "reasoning": "Oracle auto-log. Type: FADE, score: 7/10, trade: BUY YES at 7.5%, target: YES rises to 24.9%, classification: EMOTIONAL. Notes: Emotional domain (CRY); Extreme move (-43.5%); Extreme price (7.5%).",
  "trade_ids": [],
  "confidence": "oracle-auto",
  "source": "oracle-auto-log",
  "signal_id": "dada3da4f5b5",
  "signal_score": 7
}
```

### Price Parsing Logic

- `market_price` = current YES probability
  - "BUY YES at X%" → X/100
  - "BUY NO at X%" → 1 - X/100 (converts to YES price)
- `my_estimate` = target YES probability from signal's target field
  - "YES rises to X%" → X/100
  - "YES drops to X%" → X/100

---

## Test Results (Dry-Run)

```
[2026-03-28 00:45:39 UTC] No undelivered signals with score >= 4
[2026-03-28 00:45:39 UTC] [DRY-RUN] Would auto-log 5 predictions (score >= 7):
[2026-03-28 00:45:39 UTC]   pred-0011 [CRY] Backpack FDV above $700M one day after launch? | price=0.075 estimate=0.249
[2026-03-28 00:45:39 UTC]   pred-0012 [CRY] Will OpenSea launch a token by March 31, 2026? | price=0.002 estimate=0.244
[2026-03-28 00:45:39 UTC]   pred-0013 [GEO] Will Russia capture Kostyantynivka by March 31? | price=0.05 estimate=0.242
[2026-03-28 00:45:39 UTC]   pred-0014 [CRY] USD.AI FDV above $300M one day after launch? | price=0.344 estimate=0.553
[2026-03-28 00:45:39 UTC]   pred-0015 [TECH] Will Google have the best AI model at the end of March 2026? | price=0.005 estimate=0.249
```

5 backfill predictions found from existing high-score signals. Parsing correct. No writes made.

---

## Production Safety

- **Zero breaking changes** — existing delivery flow (alerts.md writes, signal marking) untouched
- **Backfill on first run** — the "no undelivered" path also runs auto_log, catching all previously-delivered score >= 7 signals that predate this feature
- **Idempotent** — dedup by question text prevents double-logging the same market
- **Dry-run flag** — `python3 scripts/oracle-deliver.py --dry-run` previews without writing
- Cron job (`*/15 * * * *`) requires no changes

---

## Expected Impact

- **Before**: 10 predictions in 11 days (manual bottleneck)
- **After**: Each 15-min cron cycle auto-logs any new score >= 7 signals
- First cron run will backfill the 5 existing high-score signals → predictions.jsonl grows to ~15 entries
- Going forward: each new score >= 7 signal is captured automatically
- Target from kingdom-003: 40+ predictions by Day 7 (depends on oracle signal volume)

---

## Known Limitations

1. `resolution_date` is null for all auto-logged entries — signals don't carry this field. Resolve manually or via calibration script when market closes.
2. `confidence_interval` is mechanical (±10% around estimate) — rough placeholder.
3. Entries with unparseable trade/target strings are SKIPped with a log message. Check oracle-deliver.log for "SKIP" lines if count is lower than expected.

---

## Next Steps for Beta

- Run `python3 scripts/oracle-deliver.py` once (without --dry-run) to flush the 5 backfill predictions
- Review the 5 auto-logged entries in `calibration/predictions.jsonl` (pred-0011 to pred-0015) for sanity
- Fill in `resolution_date` for short-dated markets (especially Mar 31 markets)
- Continue with GAP-1 (whale scanner) and GAP-3 (geo bridge) per kingdom-003 roadmap
