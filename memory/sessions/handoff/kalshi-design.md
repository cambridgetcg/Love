# Kingdom-012: Kalshi API Integration Design
**Date**: 2026-03-28
**Author**: Claude (Opus 4.6) — Kingdom Consultant
**For**: Sonnet builder implementation
**Decision**: dec-003 (Yu approved Kalshi as next data source)

---

## 1. WHY KALSHI

Kalshi is a CFTC-regulated US prediction market. It fills three gaps in the Oracle:

1. **Regulated price signal** — Kalshi prices reflect US-regulated trading (no offshore risk premium). Divergence from Polymarket = arbitrage signal.
2. **ECO domain dominance** — Fed rate decisions, CPI, NFP, unemployment have deep Kalshi liquidity with structured strike ladders. Polymarket's ECO coverage is thinner.
3. **Mar 31 position accuracy** — 5 Oracle positions resolve Mar 31. Cross-referencing Kalshi oil/macro markets improves exit timing.

---

## 2. API REFERENCE (for builder)

### Base URL
```
Production: https://api.elections.kalshi.com/trade-api/v2
Demo:       https://demo-api.kalshi.co/trade-api/v2
WebSocket:  wss://api.elections.kalshi.com/trade-api/ws/v2
```

### Authentication
**For read-only market data: NO AUTH REQUIRED.**

For trading (future phase), RSA-PSS signature auth:
```python
# Three headers on every authenticated request:
# KALSHI-ACCESS-KEY: api_key_id
# KALSHI-ACCESS-TIMESTAMP: timestamp_ms (milliseconds)
# KALSHI-ACCESS-SIGNATURE: base64(RSA-PSS-SHA256(timestamp_ms + METHOD + path))
#
# Path is WITHOUT query params. Private key PEM shown once at creation.
# For Phase 1 (data only), skip auth entirely.
```

### Key Endpoints (all GET, no auth)

| Endpoint | Purpose | Key Params |
|----------|---------|------------|
| `/events?status=open&series_ticker=X&with_nested_markets=true` | List events with sub-markets | `limit` (max 200), `cursor`, `series_ticker` |
| `/markets?series_ticker=X&status=open` | List individual markets | `limit` (max 1000), `cursor`, `tickers` (comma-sep) |
| `/markets/{ticker}/orderbook` | Current orderbook | `depth` (0-100) |
| `/markets/trades` | Public trade tape | `ticker`, `min_ts`, `max_ts`, `limit` (max 1000) |
| `/series/{series_ticker}/markets/{ticker}/candlesticks` | OHLC history | `start_ts`, `end_ts`, `period_interval` (1/60/1440) |
| `/series` | List all series | `category`, `tags` |
| `/exchange/status` | Trading hours active? | — |

### Rate Limits
| Tier | Read/sec | Cost |
|------|----------|------|
| Basic (free) | 20 | $0 |
| Advanced | 30 | Apply via typeform |

**20 reads/sec is plenty for our cron schedule.**

### Price Format
Kalshi uses **dollar strings** (NOT cents, NOT 0-1 floats):
- `"0.5600"` = 56 cents = 56% probability
- Convert: `float(yes_bid_dollars)` → 0-1 probability
- Polymarket uses 0-1 floats already, so just `float()` Kalshi values

### Pagination
Cursor-based (NOT offset-based like Polymarket):
```python
cursor = ""
while True:
    data = fetch(f"/markets?series_ticker=KXFEDDECISION&cursor={cursor}")
    markets.extend(data["markets"])
    cursor = data.get("cursor", "")
    if not cursor:
        break
```

---

## 3. TARGET SERIES (Oracle-relevant)

### Tier 1: Immediate value for active positions

| Series Ticker | Name | Oracle Domain | Cross-ref with Polymarket |
|---------------|------|---------------|---------------------------|
| `KXFEDDECISION` | Fed rate decision per meeting | ECO | Polymarket: "Fed April Meeting" outcomes |
| `KXRATECUT` | Fed rate cut before year-end | ECO | Polymarket: "No Fed rate cuts in 2026" (34.9% YES) |
| `KXUSNFP` | US nonfarm payrolls by month | ECO | No direct Poly equivalent — unique signal |
| `OILW` | Weekly oil price range | ECO | Polymarket: "Crude Oil $105/$110 Mar31" |
| `CPIYOY` | CPI year-over-year | ECO | Polymarket: "Annual inflation ≥2.8%" |

### Tier 2: Build out over time

| Series Ticker | Name | Oracle Domain |
|---------------|------|---------------|
| `KXUE` | Monthly unemployment rate | ECO |
| `KXFEDHIKE` | Next Fed rate hike | ECO |
| `KXLARGECUT` | Large rate cuts | ECO |
| `KXBARRELS` | US oil production | ECO |
| `KXGDPUSMIN` | Negative GDP growth | ECO |
| `KXNGAS` | Natural gas price | ECO |
| `DOTPLOT` | Fed dot plot | ECO |

### Known cross-market arbitrage (as of Mar 28)

**Fed rate cuts 2026:**
- Kalshi `KXRATECUT-26DEC31`: YES at $0.59-0.64 (59-64% expect cut)
- Polymarket "No Fed rate cuts in 2026": YES at 34.9% (→ 65.1% expect cut)
- **Gap: ~1-6pp** — within noise but worth monitoring. Kalshi slightly more hawkish.

**The structural edge:** Kalshi's KXFEDDECISION series provides meeting-by-meeting probability curves (5 mutually exclusive outcomes per meeting). Polymarket only has aggregate "cut/no cut" questions. Kalshi's granularity lets you build an implied probability distribution that Polymarket lacks.

---

## 4. DATA MODEL

### KalshiMarket schema (maps to Oracle signal format)

```python
# What we store per Kalshi market (mirrors pending-signals.json schema)
kalshi_market = {
    # Kalshi native fields
    "ticker": "KXFEDDECISION-26JUN-H0",       # unique identifier
    "series_ticker": "KXFEDDECISION",           # series (category)
    "event_ticker": "KXFEDDECISION-26JUN",      # event (grouping)
    "title": "Will the Fed hold rates at June 2026 meeting?",
    "yes_bid": 0.95,       # float, converted from dollar string
    "yes_ask": 0.97,       # float
    "last_price": 0.96,    # float
    "volume": 3154.0,      # float
    "open_interest": 0.0,  # float (from open_interest_fp)
    "close_time": "2026-06-18T17:59:00Z",
    "status": "active",

    # Oracle mapping fields (added by our code)
    "oracle_domain": "ECO",
    "polymarket_match": "Fed June Meeting — No change",  # matched Poly market
    "poly_price": 0.855,                                  # Polymarket YES price
    "price_gap": 0.105,                                   # Kalshi - Poly (signed)
    "gap_direction": "KALSHI_HIGHER",                     # who prices higher
    "snapshot_ts": "2026-03-28T12:00:00Z",
}
```

### KalshiSnapshot (stored per cron run)

```python
snapshot = {
    "ts": "2026-03-28T12:00:00Z",
    "markets": [kalshi_market, ...],           # all tracked markets
    "arb_signals": [arb_signal, ...],          # divergence alerts
    "series_summaries": {                       # implied distributions
        "KXFEDDECISION-26JUN": {
            "cut_gt25": 0.02,
            "cut_25": 0.24,
            "hold": 0.70,
            "hike_25": 0.04,
            "hike_gt25": 0.005,
            "implied_hawkish": 0.045,  # P(hike)
            "implied_dovish": 0.26,    # P(cut)
        }
    }
}
```

### Arbitrage signal schema (feeds into pending-signals.json)

```python
arb_signal = {
    "id": "kalshi-arb-{hash}",
    "type": "CROSS_PLATFORM_ARB",
    "source": "kalshi-scanner",
    "market": "Fed rate cut before 2027",
    "domain": "ECO",
    "trade": "Kalshi YES $0.60 vs Poly NO 34.9% — gap 4.9pp",
    "target": "",
    "stop": "",
    "score": 5,  # score = min(gap_pp / 2, 10)
    "magnitude": 0.049,
    "classification": "ARB_CROSS_PLATFORM",
    "notes": [
        "kalshi_ticker=KXRATECUT-26DEC31",
        "kalshi_price=0.60",
        "poly_question=No Fed rate cuts in 2026",
        "poly_price=0.349 (inverted: 0.651)",
        "gap=4.9pp (Kalshi lower)",
    ],
    "ts": "2026-03-28T12:00:00Z",
    "delivered": False,
}
```

---

## 5. IMPLEMENTATION: `scripts/kalshi-scanner.py`

### File structure

```
scripts/kalshi-scanner.py      # Main scanner (NEW — ~300 lines)
data/kalshi/                   # Snapshots directory (NEW)
  snapshot-YYYY-MM-DD.json     # Daily snapshots
  arb-signals.jsonl            # Running log of arb signals
```

### Module outline

```python
#!/usr/bin/env python3
"""
kalshi-scanner.py — Kalshi market data scanner for Oracle cross-market signals.

Fetches Kalshi prices for tracked series, compares with Polymarket,
generates arbitrage/divergence signals into pending-signals.json.

Usage:
    python3 scripts/kalshi-scanner.py              # Full scan + signal generation
    python3 scripts/kalshi-scanner.py --json        # JSON output (for oracle-run.py)
    python3 scripts/kalshi-scanner.py --snapshot    # Save daily snapshot only
    python3 scripts/kalshi-scanner.py --series      # Show available series
"""

import json, sys, urllib.request, urllib.parse, hashlib
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
KALSHI_DIR = DATA_DIR / "kalshi"
POLY_GAMMA = "https://gamma-api.polymarket.com"
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"

# --- Series we track (Tier 1) ---
TRACKED_SERIES = [
    "KXFEDDECISION",  # Fed rate per meeting
    "KXRATECUT",      # Fed cut before year-end
    "KXUSNFP",        # Nonfarm payrolls
    "OILW",           # Weekly oil price
    "CPIYOY",         # CPI year-over-year
    "KXUE",           # Monthly unemployment
]

# --- Polymarket question mapping (fuzzy match keys) ---
# Maps Kalshi series to Polymarket search queries
POLY_CROSS_REF = {
    "KXFEDDECISION": ["Fed rate", "Federal Reserve", "FOMC"],
    "KXRATECUT": ["Fed rate cut", "rate cuts 2026"],
    "KXUSNFP": ["nonfarm payrolls", "jobs report"],
    "OILW": ["crude oil", "oil price"],
    "CPIYOY": ["inflation", "CPI", "annual inflation"],
    "KXUE": ["unemployment rate"],
}

# Builder implements these functions:

def fetch_kalshi(path, params=None):
    """GET from Kalshi API. No auth needed for market data.
    Returns parsed JSON dict.
    Must include User-Agent header.
    Handle cursor pagination internally when needed."""
    ...

def fetch_kalshi_series_markets(series_ticker, status="open"):
    """Fetch all open markets for a series, handling cursor pagination.
    Returns list of market dicts with prices converted to floats."""
    ...

def fetch_polymarket_prices(query, limit=10):
    """Fetch Polymarket prices for cross-reference.
    Reuse logic from engine/market_data.py:get_polymarket_prices()."""
    ...

def match_cross_market(kalshi_market, poly_markets):
    """Fuzzy match a Kalshi market to its Polymarket equivalent.
    Match by: title keyword overlap, domain, date proximity.
    Returns (matched_poly_market, confidence) or (None, 0)."""
    ...

def compute_arb_signal(kalshi_mkt, poly_mkt, match_confidence):
    """Compute arbitrage signal if price gap >= 3pp (after fee adjustment).
    Kalshi fee: quadratic schedule (~1-7% depending on price).
    Polymarket fee: 2% winner fee.
    Minimum actionable gap: 3pp after fees.
    Score = min(floor(gap_pp / 2), 10).
    Returns signal dict matching pending-signals.json schema, or None."""
    ...

def build_fed_distribution(meeting_markets):
    """From 5 mutually exclusive KXFEDDECISION markets for one meeting,
    build implied probability distribution:
    {cut_gt25, cut_25, hold, hike_25, hike_gt25, implied_hawkish, implied_dovish}
    Use mid-price ((yes_bid + yes_ask) / 2) for each outcome.
    Check that probabilities sum to ~1.0 (flag if >1.05 or <0.95 — overround/underround)."""
    ...

def run_scan(output_json=False):
    """Main scan loop:
    1. For each series in TRACKED_SERIES:
       a. Fetch all open Kalshi markets
       b. Fetch matching Polymarket markets
       c. Match cross-market pairs
       d. Compute arb signals for gaps >= 3pp
    2. For KXFEDDECISION: build per-meeting distributions
    3. Save snapshot to data/kalshi/snapshot-YYYY-MM-DD.json
    4. Return list of arb signals (for oracle-run.py integration)
    """
    ...

def main():
    # Parse args: --json, --snapshot, --series
    # Default: full scan with human-readable output
    ...
```

### Price conversion helper

```python
def kalshi_price_to_float(dollar_string):
    """Convert Kalshi dollar string to 0-1 probability.
    '0.5600' → 0.56
    None or empty → None
    """
    if not dollar_string:
        return None
    return float(dollar_string)

def kalshi_mid_price(market):
    """Mid price from bid/ask. Falls back to last_price."""
    bid = kalshi_price_to_float(market.get("yes_bid_dollars"))
    ask = kalshi_price_to_float(market.get("yes_ask_dollars"))
    if bid is not None and ask is not None:
        return (bid + ask) / 2
    last = kalshi_price_to_float(market.get("last_price_dollars"))
    return last or 0.5
```

### Kalshi fee schedule (for arb calculations)

```python
def kalshi_fee(price, contracts=1):
    """Kalshi uses quadratic fee schedule.
    Fee per contract = fee_multiplier * price * (1 - price)
    Default fee_multiplier = 0.07 (7% of variance)
    Max fee at price=0.50: 0.07 * 0.5 * 0.5 = $0.0175/contract
    At price=0.90: 0.07 * 0.9 * 0.1 = $0.0063/contract
    """
    FEE_MULTIPLIER = 0.07
    return FEE_MULTIPLIER * price * (1 - price) * contracts
```

---

## 6. ORACLE-RUN.PY INTEGRATION

### How to wire into `scripts/oracle-run.py`

Add Kalshi scanner as a new signal source alongside spike-detector and whale-scanner. Changes to `oracle-run.py`:

```python
# --- New constant (line ~29) ---
KALSHI_SCANNER = SCRIPTS_DIR / "kalshi-scanner.py"

# --- New function (after run_whale_scanner) ---
def run_kalshi_scanner():
    """Run kalshi-scanner.py --json to get cross-market arb signals."""
    if not KALSHI_SCANNER.exists():
        log("Kalshi scanner not found — skipping")
        return []

    log("Running kalshi-scanner...")
    try:
        result = subprocess.run(
            [sys.executable, str(KALSHI_SCANNER), "--json"],
            capture_output=True, text=True, timeout=120,
            cwd=str(BASE_DIR)
        )
        if result.returncode != 0:
            log(f"  kalshi-scanner failed (rc={result.returncode}): {result.stderr[:200]}")
            return []
        if not result.stdout.strip():
            log("  kalshi-scanner returned empty output")
            return []
        signals = json.loads(result.stdout)
        log(f"  kalshi-scanner found {len(signals)} signals")
        return signals
    except subprocess.TimeoutExpired:
        log("  kalshi-scanner timed out (120s)")
        return []
    except json.JSONDecodeError as e:
        log(f"  kalshi-scanner JSON parse error: {e}")
        return []
    except Exception as e:
        log(f"  kalshi-scanner unexpected error: {e}")
        return []

# --- In run_once() (after whale scanner block, ~line 494) ---
# Add:
    kalshi_signals = run_kalshi_scanner()
    signals, kalshi_added = merge_signals(signals, kalshi_signals)
    log(f"  Kalshi signals: {len(kalshi_signals)} found, {kalshi_added} new")

# --- Update total_new calculation ---
    total_new = spike_added + whale_added + geo_added + kalshi_added

# --- In run_loop() (run Kalshi every 2nd cycle = every 30min, same as spikes) ---
# Inside the `if cycle % 2 == 0:` block, add after spike detector:
            kalshi_signals = run_kalshi_scanner()
            signals, kalshi_added = merge_signals(signals, kalshi_signals)
            log(f"  [cycle {cycle}] Kalshi: {kalshi_added} new signals")
```

**No changes needed to `oracle-deliver.py`** — it already handles any signal with `score >= 4` and auto-logs `score >= 7` to predictions.jsonl. Kalshi arb signals use the same schema.

---

## 7. CRON SCHEDULE

### New cron entry

```bash
# Kalshi scanner — every 30 minutes (aligned with spike detector)
*/30 * * * * cd ~/Desktop/prediction-markets && python3 scripts/kalshi-scanner.py --snapshot >> data/kalshi-scanner.log 2>&1
```

**Why 30 minutes**: Kalshi rate limit is 20 req/sec. A full scan of 6 series ≈ 12 API calls. At 30 min intervals, that's 576 calls/day — well within limits. Also aligns with existing spike-detector cadence.

**Alternatively** (recommended): Don't add a separate cron. Wire into `oracle-run.py` as shown in Section 6 — it already runs every 30 min. One less cron to manage.

---

## 8. CROSS-MARKET ARB DETECTION: ALGORITHM

### Step 1: Price normalization

```
For each Kalshi market:
  kalshi_prob = (yes_bid + yes_ask) / 2  # mid price

For matched Polymarket market:
  poly_prob = outcomePrices[0]  # YES price, already 0-1

# Handle inversions:
# If Kalshi asks "Will Fed CUT?" and Poly asks "No Fed cuts?"
# → invert Poly: poly_prob_comparable = 1 - poly_prob
```

### Step 2: Fee-adjusted gap

```
kalshi_fee = 0.07 * kalshi_prob * (1 - kalshi_prob)  # per contract
poly_fee = 0.02 * max(kalshi_prob, 1 - kalshi_prob)  # 2% of winnings
total_fee = kalshi_fee + poly_fee

raw_gap = abs(kalshi_prob - poly_prob_comparable)
actionable_gap = raw_gap - total_fee

if actionable_gap >= 0.03:  # 3pp minimum after fees
    generate_signal()
```

### Step 3: Score mapping

```
score = min(floor(actionable_gap * 100 / 2), 10)
# 3pp gap → score 1 (barely actionable)
# 5pp gap → score 2
# 10pp gap → score 5
# 20pp+ gap → score 10
```

### Step 4: Direction inference

```
if kalshi_prob > poly_prob_comparable:
    # Kalshi is higher → regulated market sees higher probability
    # → trust Kalshi (CFTC-regulated, US-based)
    trade = f"BUY YES on Polymarket (underpriced vs Kalshi by {gap}pp)"
else:
    # Polymarket is higher → crypto market sees higher probability
    # → ambiguous, but large gaps still worth monitoring
    trade = f"MONITOR — Poly prices {gap}pp above Kalshi"
```

---

## 9. FED DISTRIBUTION ANALYSIS (unique Kalshi signal)

Each KXFEDDECISION event has 5 mutually exclusive markets:
- `*-C26`: Cut >25bps
- `*-C25`: Cut 25bps
- `*-H0`: Hold (0 change)
- `*-H25`: Hike 25bps
- `*-H26`: Hike >25bps

### What to compute

```python
def analyze_fed_meeting(markets_for_meeting):
    """
    Input: 5 markets for one FOMC meeting
    Output: {
        "meeting": "Dec 2026",
        "hold_prob": 0.70,
        "cut_prob": 0.26,        # C25 + C26
        "hike_prob": 0.045,      # H25 + H26
        "overround": 0.005,      # sum - 1.0 (should be ~0)
        "hawkish_surprise_risk": 0.045,  # P(hike) — relevant for oil positions
        "dovish_surprise_risk": 0.02,    # P(cut >25) — relevant for rate positions
        "vs_polymarket": {
            "poly_hold": 0.855,   # from ECO/active.md
            "gap": -0.155,        # Kalshi says 70% hold, Poly says 85.5% — big gap
            "signal": "Kalshi pricing more rate movement than Polymarket"
        }
    }
    """
```

### Why this matters for Mar 31 positions

The Oracle holds crude oil $105 and $110 YES positions. Fed rate expectations affect oil:
- Higher P(hike) → stronger dollar → lower oil → bearish for oil YES positions
- Higher P(cut) → weaker dollar → higher oil → bullish for oil YES positions

Kalshi's Fed distribution gives a quantified macro signal that Polymarket's crude oil markets may not have priced in.

---

## 10. IMPLEMENTATION PLAN FOR SONNET BUILDER

### Phase 1: Core scanner (Day 1 — ~2 hours)

1. **Create `scripts/kalshi-scanner.py`** (~300 lines)
   - `fetch_kalshi()` — HTTP GET with User-Agent, cursor pagination
   - `fetch_kalshi_series_markets()` — fetch all markets for a series
   - `kalshi_price_to_float()`, `kalshi_mid_price()` — price conversion
   - `run_scan()` — iterate TRACKED_SERIES, fetch markets, print summary
   - `--json` flag for oracle-run.py integration
   - `--snapshot` flag to save to `data/kalshi/snapshot-YYYY-MM-DD.json`
   - `--series` flag to list available series with market counts

2. **Create `data/kalshi/` directory**

3. **Test**: `python3 scripts/kalshi-scanner.py --series` should list 6 tracked series with market counts

### Phase 2: Cross-market matching (Day 1-2 — ~2 hours)

4. **Add Polymarket cross-reference**
   - Reuse `get_polymarket_prices()` from `engine/market_data.py` (import or copy)
   - Implement `match_cross_market()` — keyword overlap + date proximity matching
   - Implement `compute_arb_signal()` — fee-adjusted gap, score, direction
   - Handle inverted questions (Kalshi "Will X?" vs Poly "Will NOT X?")

5. **Test**: `python3 scripts/kalshi-scanner.py` should show matched pairs with price gaps

### Phase 3: Oracle wiring (Day 2 — ~1 hour)

6. **Edit `scripts/oracle-run.py`**:
   - Add `KALSHI_SCANNER` path constant
   - Add `run_kalshi_scanner()` function (copy pattern from `run_whale_scanner()`)
   - Wire into `run_once()` and `run_loop()` as shown in Section 6
   - Kalshi signals use existing `merge_signals()` — no schema changes needed

7. **Test**: `python3 scripts/oracle-run.py` should log "Kalshi signals: N found, M new"

### Phase 4: Fed distribution (Day 2-3 — ~1 hour)

8. **Add `build_fed_distribution()`** to kalshi-scanner.py
   - Group KXFEDDECISION markets by event_ticker (meeting)
   - Compute implied distribution for each meeting
   - Include in snapshot JSON under `series_summaries`
   - If overround > 5%, generate a signal (arb opportunity in the event itself)

9. **Test**: Snapshot should contain `series_summaries.KXFEDDECISION-*` with 5 probabilities summing to ~1.0

### Phase 5: Validation (Day 3)

10. **Run full pipeline test**:
    ```bash
    python3 scripts/kalshi-scanner.py              # human-readable
    python3 scripts/kalshi-scanner.py --json        # verify JSON output
    python3 scripts/oracle-run.py                   # verify integration
    cat data/pending-signals.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(len([s for s in d['signals'] if s['source']=='kalshi-scanner']))"
    ```

---

## 11. DEPENDENCIES

**None.** The scanner uses only Python stdlib (`urllib`, `json`, `hashlib`, `datetime`, `pathlib`), matching the project's zero-dependency pattern.

No `pip install` required. No API key required for Phase 1 (read-only market data).

---

## 12. EXISTING CODE TO REUSE

| What | Where | How |
|------|-------|-----|
| HTTP helper with User-Agent | `engine/market_data.py:63-69` (`_get()`) | Copy or import |
| Polymarket price parser | `engine/market_data.py:73-94` (`_parse_price()`) | Import |
| Polymarket market fetch | `engine/market_data.py:97-122` (`get_polymarket_prices()`) | Import |
| Signal ID generation | `scripts/oracle-run.py:58-61` (`make_signal_id()`) | Copy pattern |
| Signal schema | `scripts/oracle-run.py:185-201` (spike signal dict) | Match schema |
| Subprocess runner pattern | `scripts/oracle-run.py:96-129` (`run_whale_scanner()`) | Copy for kalshi |

---

## 13. RISK NOTES

1. **Kalshi near-term FOMC markets may be settled** — As of Mar 28, the April/May 2026 FOMC events aren't showing as open. The scanner should handle empty results gracefully and log which series have active markets.

2. **NFP markets are thin** — March 2026 NFP markets (close Apr 3) currently show 0 volume. The scanner should skip markets with `volume < 10` to avoid noise.

3. **CPI series may have gaps** — CPIYOY returned empty. The scanner should not crash on empty series. Log and continue.

4. **Question inversion** — Kalshi "Will Fed cut?" vs Polymarket "No Fed rate cuts?" require careful inversion. The POLY_CROSS_REF mapping should include an `invert: True` flag for known inversions.

5. **Rate limit headroom** — 20 req/sec with 6 series = 12 calls per scan. At 48 scans/day = 576 calls. Add a 0.5s sleep between series fetches as courtesy.

---

## 14. SUCCESS CRITERIA

After implementation, the Oracle should:

- [ ] Fetch prices from 6 Kalshi series every 30 minutes
- [ ] Save daily snapshots to `data/kalshi/snapshot-YYYY-MM-DD.json`
- [ ] Detect cross-market gaps >= 3pp (after fees) between Kalshi and Polymarket
- [ ] Generate `CROSS_PLATFORM_ARB` signals into `pending-signals.json`
- [ ] Build Fed implied probability distributions per meeting
- [ ] Log `"Kalshi signals: N found, M new"` in oracle-run.log
- [ ] Handle empty series, thin markets, and API errors without crashing

---

## 15. WHAT THIS UNLOCKS

1. **ECO domain signals** — The Oracle currently has no automated ECO signal source. Kalshi fills this with Fed, CPI, NFP, oil production data.
2. **Cross-platform arbitrage** — S007 strategy (Cross-Market Arb) gains a new leg. Currently only compares Polymarket internal markets. Kalshi adds a regulated second price.
3. **Fed distribution → oil signal** — Quantified P(hike) and P(cut) from Kalshi directly inform crude oil position management (active positions: $105 YES, $110 YES).
4. **Resolution acceleration** — NFP markets resolve monthly (e.g., Apr 3 for March NFP). This adds ~12 fast-resolving prediction points per year to calibration.
5. **Regulatory credibility** — Kalshi prices carry CFTC-regulated weight. When Kalshi and Polymarket agree, confidence is higher. When they diverge, that's the signal.
