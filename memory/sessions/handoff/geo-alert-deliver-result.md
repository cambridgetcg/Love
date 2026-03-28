# GEO_ALERT Deliver Integration — Result

**Session:** Gamma (Builder)
**Date:** 2026-03-28
**Task:** Add GEO_ALERT signal type handling to oracle-deliver.py
**Status:** ✅ Complete

---

## Problem

`oracle-run.py` generates signals with `type="GEO_ALERT"` and `source="geo-bridge"`. These have:
- `trade` = `"GEO ESCALATION: title [region] — level N"` (descriptive, not `BUY YES/NO at X%`)
- `target` = `""` (empty — no numeric YES price target)
- `stop` = `""` (empty)
- `notes` = `["risk_posture=...", "global_escalation=...", "event_type=..."]`
- `classification` = `"GEO_ELEVATED" | "GEO_HIGH" | "GEO_TAIL_RISK"`

`oracle-deliver.py` had two gaps:

1. **`format_alert()`** — Would render `**Trade**: GEO ESCALATION: ...` (wrong label) and dump geo-specific note fields flat into `**Notes**` without surfacing severity/context clearly.
2. **`auto_log_predictions()`** — Would attempt to parse YES price from `trade` string, fail, and emit a noisy `SKIP` log for every GEO_ALERT with score ≥ 7. GEO alerts shouldn't enter calibration.jsonl anyway (no specific market YES price).

---

## Changes Made

**File:** `scripts/oracle-deliver.py`

### Change 1 — `format_alert()` GEO_ALERT branch (lines 74–98)

Added `is_geo` detection:
```python
is_geo = sig_type == "GEO_ALERT" or source in ("geo-bridge", "geo_intelligence")
```

GEO_ALERT path renders:
```markdown
## [GEO] Russia-Ukraine Escalation [Eastern Europe]
**Signal**: GEO_ALERT | **Source**: geo-bridge | **Score**: 9/10
**Severity**: TAIL_RISK
**Action**: GEO ESCALATION: Russia-Ukraine Escalation [Eastern Europe] — level 9
**Context**: global_escalation=9 | risk_posture=RISK_OFF | event_type=conflict
*Generated: 2026-03-28T...*
```

Existing SPIKE/FADE/HALF/BACK/MONITOR signals — **no change**, exactly same format as before.

### Change 2 — `auto_log_predictions()` GEO skip (lines 178–181)

```python
# GEO_ALERT signals are domain-wide alerts, not specific market price predictions —
# they have no YES price or numeric target to log into calibration.
if sig.get('type') == 'GEO_ALERT' or sig.get('source') in ('geo-bridge', 'geo_intelligence'):
    continue
```

Placed after dedup check, before the `_parse_yes_price_from_trade()` call. Eliminates the noisy SKIP log.

---

## Behavior Matrix

| Signal type | Score >= MIN_SCORE (4) | Score >= AUTO_LOG (7) | format_alert | auto_log |
|-------------|----------------------|----------------------|-------------|---------|
| FADE/HALF | ✅ Delivered | ✅ Auto-logged | Trade/Target/Stop format | ✅ Logged |
| BACK/MONITOR | ✅ Delivered | ✅ Auto-logged (if parseable) | Trade format | ✅ Logged |
| GEO_ALERT | ✅ Delivered | Skipped (intentional) | Severity/Action/Context format | ⛔ Skipped |

---

## What GEO_ALERT Delivery Looks Like

When `global_escalation >= 4`:
1. `oracle-run.py` generates GEO_ALERT signals with score 4–10
2. `oracle-deliver.py` picks them up on next run (score >= MIN_SCORE=4)
3. `format_alert()` renders with **Severity** + **Action** + **Context** labels
4. `auto_log_predictions()` skips them (not calibration entries)
5. Signal marked `delivered=True` in `pending-signals.json`

Domain-wide alert (no specific active_events):
```
## [GEO] GEO Domain Alert — RISK_OFF
**Signal**: GEO_ALERT | **Source**: geo-bridge | **Score**: 5/10
**Severity**: ELEVATED
**Action**: REVIEW GEO markets — escalation=5, posture=RISK_OFF
**Context**: global_escalation=5 | risk_posture=RISK_OFF
*Generated: ...*
```

---

## Files Changed

- `scripts/oracle-deliver.py` — 2 targeted edits, ~25 lines added, existing behavior unchanged

## Gaps Remaining

- Remaining gaps from geo-bridge-result.md still apply:
  1. Specific market fuzzy matching (geo signals use event titles, not Polymarket question strings)
  2. WW3 active_events schema may need adjustment when real events populate
