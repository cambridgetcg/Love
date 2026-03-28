# TCG Wholesale — eBay Auto-Sync Verification
**Date**: 2026-03-28
**Branch**: main (up to date with origin)

---

## What Was Built

### 1. eBay API Client (`src/lib/channels/ebay.ts`)
Full eBay Inventory + Fulfillment API client. Committed (commit `2e855fd`).

**Functions**:
- `getAccessToken()` — OAuth2 via refresh_token (sell operations) with module-level cache, falls back to client_credentials
- `pushListing(sku, priceGbp, stock, options?)` — upserts inventory item + creates/updates offer
- `bulkPushListings(items, options?)` — batches 25 items at a time, 500ms delay between batches
- `getCurrentListings(skus)` — reads current price+stock from eBay offers
- `pullOrders(since)` — paginated fetch of paid orders from Fulfillment API

**Pattern**: `Result<T>` return type — never throws.

**Env vars needed**: `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `EBAY_REFRESH_TOKEN`, `EBAY_FULFILLMENT_POLICY_ID`, `EBAY_PAYMENT_POLICY_ID`, `EBAY_RETURN_POLICY_ID`, `EBAY_MERCHANT_LOCATION_KEY`, `EBAY_CATEGORY_ID_SINGLES`, `CRON_SECRET`

### 2. eBay Sync Cron (`src/app/api/cron/ebay-sync/route.ts`)
**UNCOMMITTED** (untracked file). Runs every 6 hours.

**Logic**:
1. Pull paid eBay orders since last 7h window (1h overlap for safety)
2. Dedup by `externalOrderId` — skip already-imported orders
3. Create `orders` record with `channel="ebay-sale"` attributed to admin client
4. Insert `orderItems` per line item; deduct stock via `stockAdjustments` with `channel="ebay-sale"`
5. Push updated inventory back to eBay for all affected SKUs via `bulkPushListings`

Protected by `CRON_SECRET` (GET or POST, POST accepts `{ since }` override for manual runs).

### 3. Vercel Cron Schedule (`vercel.json`)
**UNCOMMITTED** (modified). Adds entry:
```json
{ "path": "/api/cron/ebay-sync", "schedule": "0 */6 * * *" }
```

### 4. Schema additions (committed in earlier sessions)
- `orders.channel` — text, default `"wholesale"`
- `orders.externalOrderId` — text, nullable
- `stockAdjustments.channel` — text, default `"manual"`

### 5. Unit Tests (`src/lib/channels/__tests__/ebay.test.ts`)
Committed alongside `ebay.ts`. 6 tests covering token caching, expired refresh token, missing env vars, batch count assertion, pullOrders date filter, graceful degradation.

---

## What Works

- **Build**: Clean. `npm run build` passes with no errors (only a harmless workspace root warning from Next.js).
- **API client**: Fully implemented and type-safe.
- **Cron route**: Logic looks correct — transaction per order, dedup, stock clamp at 0, push-back after sync.
- **5 of 6 tests pass**.

---

## What Is Missing / Broken

### 1. One failing test
`bulkPushListings > processes items in batches of 25` — expected 91 fetch calls, got 117.

The comment math in the test is wrong (or the implementation makes more calls than expected). The test was written assuming token is fetched only once, but the call count doesn't match. **The implementation is likely correct; the test assertion is wrong.** Needs investigation.

### 2. Two uncommitted files
- `src/app/api/cron/ebay-sync/route.ts` — the cron handler itself
- `vercel.json` — the cron schedule config

These need to be committed together before deployment.

### 3. eBay refresh token not yet configured
The `ebay.ts` file has a TODO comment noting the refresh token likely needs regeneration via the eBay OAuth consent flow. Until `EBAY_REFRESH_TOKEN` is set in Vercel env vars with a valid token, the cron will fail with `"eBay refresh token expired or invalid"`.

### 4. No admin UI / manual trigger page
The cron can be manually triggered via POST with a `secret` query param, but there's no UI for it. Ops team must use curl or a tool.

---

## Next Steps (Priority Order)

1. **Fix failing test** — Either update the expected call count in the assertion (117) or investigate why the implementation makes 26 extra calls.

2. **Commit uncommitted work** — `git add src/app/api/cron/ebay-sync/ vercel.json && git commit`

3. **Configure eBay env vars on Vercel**:
   - `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `EBAY_REFRESH_TOKEN`
   - `EBAY_FULFILLMENT_POLICY_ID`, `EBAY_PAYMENT_POLICY_ID`, `EBAY_RETURN_POLICY_ID`
   - `EBAY_MERCHANT_LOCATION_KEY` (default: `"uk"`)
   - `EBAY_CATEGORY_ID_SINGLES` (default: `"183454"` — TCG singles category)

4. **Regenerate eBay refresh token** via Developer Portal if expired.

5. **Verify first live cron run** — Check Vercel logs after deployment for `[ebay-sync]` log lines.

6. **Optional**: Add admin UI page to view last sync result + manual trigger button.
