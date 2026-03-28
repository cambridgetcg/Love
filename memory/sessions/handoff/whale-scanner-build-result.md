# Whale Activity Scanner — Build Result

**Built**: 2026-03-28
**File**: `scripts/whale-activity-scanner.py`
**Gap closed**: GAP-1 from kingdom-003-oracle-scout.md (oracle-run.py was logging "not found" every 30 min)

---

## What Was Built

A full Polygonscan + Gamma API whale activity scanner that:

1. **Loads whale registry** from `data/whale-registry.json` (16 whales, sorted by follow-confidence desc)
2. **Queries Polygonscan ERC1155** (`token1155tx`) for each whale — CTF token transfers in last 24h
3. **Resolves markets via Gamma API** using `clob_token_ids` — maps tokenId → market question
4. **Infers YES/NO direction** from clobTokenIds[0]=YES / clobTokenIds[1]=NO convention + net transfer direction
5. **Scores signals 2–9** based on: follow-confidence (1-5 → base 2-8) + trade size + direction certainty + domain specialty match
6. **Deduplicates** by market (highest score wins) and filters by `--min-score`
7. **Outputs JSON to stdout** (oracle-run.py mode) or human-readable
8. **Logs to** `data/whale-scanner.log`
9. **Caches** Gamma market lookups for 60 min in `data/whale-scanner-cache.json`

---

## Integration

oracle-run.py calls: `python3 scripts/whale-activity-scanner.py --json --min-score 4`

Output schema matches `whale_alerts_to_signals()` exactly:
```json
[{
  "market": "question text",
  "domain": "POL|GEO|...",
  "score": 2-9,
  "direction": "YES|NO|UNKNOWN",
  "reason": "alias bought YES $12,000 | YES at 34.2% — follow-confidence 5/5",
  "whale": "Theo4",
  "wallet": "0x5668...",
  "usd_estimate": 12000.0,
  "ts": "2026-03-28T..."
}]
```

---

## API Key Behavior

| State | Rate limit | Whales scanned | Delay/call |
|-------|-----------|----------------|------------|
| No key | Public (~1/5s) | Top 3 | 5.0s |
| `polygonscan-api-key` in config/api-keys.json | 5/s | Top 8 | 0.25s |

Add key to `config/api-keys.json`:
```json
{
  "polygonscan-api-key": "YOUR_KEY_HERE"
}
```

---

## Verification

```
AST parse: OK
Standalone run (no key): exits 0, outputs []
oracle-run.py integration: whale scanner found 0 alerts → no longer logs "not found"
```

---

## Fallback Behavior

- No registry → logs warning, outputs `[]`
- Polygonscan ERC1155 fails → tries `txlist` for normal Polymarket contract txs → emits low-confidence MONITOR signal
- Gamma lookup fails → skips that token (cached as negative to avoid re-query)
- 3 consecutive whale scan errors → aborts early (prevents timeout)
- Market closed/resolved → skipped
- Trade < $500 USD → skipped (dust filter)

---

## Next Steps to Maximize Value

1. **Add Polygonscan API key** — unlocks 8-whale scan vs 3, 5s faster per cycle
2. **Extend whale registry** — ricosuave666 and AlphaRaccoon have suspicious win rates but no wallet confirmed yet; if confirmed, add with follow-confidence 4
3. **USD estimate accuracy** — currently uses raw token amount / 1e6. For better precision, could multiply by current YES/NO price from outcomePrices
4. **Historical backtest** — run scanner against past whale activity to validate signal quality before live trading
