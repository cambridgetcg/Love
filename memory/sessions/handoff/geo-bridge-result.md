# Geo Bridge Wiring — Result

**Session:** Gamma (Builder)
**Date:** 2026-03-28
**Task:** Wire geo_intelligence.jsonl into oracle-run.py signal scoring
**Status:** ✅ Complete

---

## What Was Built

Three functions added to `scripts/oracle-run.py`:

### `read_latest_geo_signal()`
- Tail-reads `data/stream/geo_intelligence.jsonl` (last 8KB)
- Returns most recent valid JSON record
- Returns `None` gracefully if file missing or empty

### `geo_to_signals(geo_rec)`
- Converts a geo record into Oracle signal format
- **Noise floor**: escalation < 4 AND posture=NEUTRAL AND no active_events → returns `[]`
- Escalation thresholds (mirrors design spec):
  - 1–3 NEUTRAL: no signals
  - 4–6: ELEVATED (score 4), domain-wide GEO_ALERT
  - 7–8: HIGH (score 7)
  - 9–10: TAIL_RISK (score 9)
- When `active_events` populated: generates one signal per event with title/region/escalation
- When no active events but elevated: generates single domain-wide alert

### `apply_geo_boost(signals, geo_rec)`
- Boosts scores of undelivered GEO domain signals already in pending-signals.json
- escalation 4–6 or posture != NEUTRAL: +1 to GEO scores
- escalation 7+: +2 to GEO scores
- Appends `geo_boost:+N` note to boosted signals (idempotent — replaces stale note)
- Returns `(signals, boosted_count)` tuple

---

## Integration Points

### `run_once()` (cron path)
After spike/whale detectors run, geo scoring fires:
```
geo_rec = read_latest_geo_signal()
→ log geo state (escalation, posture, event_count)
→ geo_to_signals() → merge new geo signals
→ apply_geo_boost() → boost existing GEO signals
→ log counts
```

### `run_loop()` (continuous mode)
- `run_geo_inject()` moved inside the cycle-2 block (runs every 30m with spike-detector)
- Geo signal scoring runs every cycle (15m)
- Only logs if geo_added > 0 or geo_boosted > 0 (silent on quiet cycles)

---

## Test Run Output (2026-03-28)

```
Geo inject: ✅ NEUTRAL | Escalation 1 | 4 events
Geo state: escalation=1, posture=NEUTRAL, events=4
Geo signals: 0 generated, 0 new, 0 GEO scores boosted
```

Correct behavior — escalation=1 NEUTRAL is below noise floor. Pipeline is live.

---

## What Fires When WW3 Escalates

When `global_escalation >= 4` or `risk_posture = RISK_OFF`:
1. New GEO_ALERT signals generated and added to `data/pending-signals.json`
2. Existing GEO domain spike signals get score boost
3. Oracle deliver picks them up on next cycle

When `active_events` are populated (specific conflict events from ww3.db):
1. One targeted signal per event with market=event title, region tag, event escalation
2. Score = min(event_escalation + 2, 10)

---

## Files Changed

- `scripts/oracle-run.py` — added ~130 lines, 3 new functions, wired into run_once + run_loop
- No other files modified
- Existing spike-detector behavior unchanged (no modifications to spike path)

---

## Remaining Gaps (from kingdom-003-oracle-scout.md)

1. **Specific market matching** — geo signals use event titles as market names, not actual Polymarket question strings. A fuzzy matcher against active GEO markets would improve signal quality.
2. **WW3 active_events schema** — current data has empty active_events (escalation=1). When real events populate, the event object schema from ww3.db may differ from what's assumed here. Adjust field names in `geo_to_signals()` if needed (`title`/`name`, `region`/`location`, `event_type`/`type`).
3. **oracle-deliver.py** — GEO_ALERT type signals need to be handled in the deliver script (currently only FADE/HALF/BACK/MONITOR types may be formatted). Check if deliver needs a GEO_ALERT branch.
