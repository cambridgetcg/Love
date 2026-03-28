# TCG Wholesale — Repository Scout Report

**Scout Date**: 2026-03-28
**Scope**: Read-only reconnaissance of `/Users/yu/Desktop/tcg-wholesale`
**Purpose**: Intelligence for revenue optimization (+20% target)

---

## STACK

### Core Framework
- **Frontend**: Next.js 15.1.0, React 19.0.0, TypeScript 5.7.0
- **Backend**: Node.js runtime (Next.js API routes)
- **Database**: PostgreSQL via Drizzle ORM 0.36.0
- **Auth**: NextAuth 5.0.0-beta.25 with @auth/core 0.37.0
- **Email**: Resend 6.9.2
- **Cloud Storage**: AWS S3 (@aws-sdk/client-s3 3.700.0)

### Testing & Tooling
- **E2E Tests**: Playwright 1.58.2
- **Unit Tests**: Vitest 4.1.0 (minimal coverage)
- **CSS**: Tailwind 3.4.0 + PostCSS 8.4.49
- **CLI Tools**: tsx 4.19.0 (TypeScript execution)
- **Data Processing**: ExcelJS 4.4.0, Cheerio 1.2.0 (web scraping)
- **Package Manager**: pnpm (with onlyBuiltDependencies: esbuild)

### Database Tools
- **ORM**: Drizzle ORM 0.36.0
- **Migrations**: Drizzle Kit 0.28.0 (`db:generate`, `db:migrate`, `db:push`)
- **Studio**: Drizzle Studio for data inspection

---

## STRUCTURE

### Directory Layout

```
tcg-wholesale/
├── src/
│   ├── app/                          # Next.js App Router
│   │   ├── api/                      # 40+ API routes
│   │   │   ├── admin/                # Admin endpoints (auth-gated)
│   │   │   │   ├── clients/          # Client management
│   │   │   │   ├── games/            # Game/set management
│   │   │   │   ├── orders/           # Order notifications
│   │   │   │   ├── purchases/        # Purchase orders
│   │   │   │   ├── refill/           # Inventory refill calculation
│   │   │   │   ├── stock/            # Stock level management
│   │   │   │   ├── stock-targets/    # Price-tier stock targets
│   │   │   │   ├── stock-check/      # Live stock verification
│   │   │   │   ├── to-order/         # Purchase order generation
│   │   │   │   ├── wanted/           # Wanted cards (watchlist)
│   │   │   │   └── channels/ebay/    # eBay sync endpoints
│   │   │   ├── cron/                 # Scheduled jobs
│   │   │   │   └── monthly-rollover/ # Daily volume discount recalc
│   │   │   ├── auth/                 # NextAuth routes
│   │   │   ├── cards/                # Card catalog queries
│   │   │   ├── cart/                 # Shopping cart operations
│   │   │   ├── clients/              # Client account endpoints
│   │   │   ├── orders/               # Order creation/status
│   │   │   ├── prices/               # Price upload/sync
│   │   │   ├── wanted/               # Wanted cards (client API)
│   │   │   ├── sync/                 # Supplier data sync
│   │   │   └── v1/prices/            # Legacy price API
│   │   ├── admin/                    # Admin pages
│   │   ├── catalog/                  # Product catalog page
│   │   ├── orders/                   # Order management pages
│   │   ├── fulfillment/              # Fulfillment tracking
│   │   ├── margin/                   # Pricing margin calculator
│   │   ├── login/                    # Auth pages
│   │   ├── layout.tsx                # Root layout
│   │   ├── globals.css               # Global styles
│   │   └── page.tsx                  # Home page
│   ├── components/                   # Reusable React components
│   │   ├── catalog/                  # Catalog UI
│   │   │   ├── CardTable.tsx
│   │   │   ├── SearchBar.tsx
│   │   │   ├── GameTabs.tsx
│   │   │   ├── CategoryToggle.tsx
│   │   │   ├── CatalogFilterContext.tsx
│   │   │   ├── Pagination.tsx
│   │   │   └── WatermarkedImage.tsx
│   │   ├── StatusBadge.tsx
│   │   ├── CardThumbnail.tsx
│   │   └── Nav.tsx
│   ├── lib/                          # Core business logic
│   │   ├── db/
│   │   │   ├── schema.ts             # Drizzle ORM schema (18 tables)
│   │   │   ├── index.ts              # DB connection
│   │   │   └── seed.ts               # Development seeding
│   │   ├── channels/                 # Multi-channel integrations
│   │   │   ├── ebay.ts               # eBay API client (OAuth, inventory, orders)
│   │   │   └── __tests__/ebay.test.ts
│   │   ├── pricing.ts                # Price calculation (JPY→GBP, margins, VAT)
│   │   ├── auth.ts                   # NextAuth configuration
│   │   ├── order-number.ts           # Per-client order numbering
│   │   ├── order-transitions.ts      # State machine for order workflow
│   │   ├── order-snapshot.ts         # Historical order snapshots
│   │   ├── subdomain.ts              # Multi-tenant routing
│   │   ├── s3.ts                     # AWS S3 image upload
│   │   ├── sync-uk-stock.ts          # Stock synchronization
│   │   ├── email/
│   │   │   ├── resend.ts
│   │   │   ├── send-order-email.ts
│   │   │   └── templates.ts
│   │   ├── cart-context.tsx          # Client-side cart state
│   │   └── middleware.ts             # Auth + subdomain routing
│   └── types/
│       └── next-auth.d.ts
│
├── tools/                            # 50+ CLI tools for operations
│   ├── scrape-cardrush.ts            # CardRush supplier price/stock scraper
│   ├── refill.ts                     # Auto-generate purchase orders by stock target
│   ├── import-remambo-order.ts       # Sync Remambo orders to purchases table
│   ├── ebay-sync.ts                  # Sync eBay orders & push inventory updates
│   ├── batch-import-orders.ts        # Bulk import historical orders
│   ├── fulfill-order.ts              # Record fulfillment for shipped orders
│   ├── list-all-remambo-orders.ts    # Query Remambo order dashboard
│   ├── check-*.ts                    # Data validation/debug tools
│   ├── find-*.ts                     # Data search/recovery tools
│   ├── verify-*.ts                   # Purchase/order audits
│   ├── sync-condition-prices.ts      # Japanese card price archive
│   ├── migrate-*.py                  # Historical data migrations (SKU encoding)
│   ├── admin-dashboard.py            # Pandas-based reporting
│   ├── fulfillment.py                # Fulfillment reconciliation
│   ├── db-dashboard.py               # Database exploration
│   ├── condition-prices.py           # Card condition pricing scraper
│   └── lib/                          # Shared tool utilities
│
├── e2e/                              # Playwright E2E tests
│   ├── order-flow.spec.ts            # End-to-end order creation & payment
│   ├── stock-check-live.spec.ts      # Live stock verification workflow
│   ├── fulfillment.spec.ts           # Fulfillment page & shipping
│   ├── cart-persistence.spec.ts      # Cart survival across sessions
│   └── mobile.spec.ts                # Mobile responsive tests
│
├── docs/                             # Project documentation
├── infra/                            # Infrastructure config
│   └── migrations/                   # Manual DB migration scripts
├── drizzle/                          # Drizzle migrations (auto-generated)
├── data/                             # Local data caches
│   ├── cardrush/                     # Cached CardRush scrapes
│   ├── dbfw-names/                   # Card English names lookup
│   └── ebay/                         # eBay data snapshots
├── prompts/                          # AI prompt templates
│
├── vercel.json                       # Vercel deployment config (crons defined here)
├── drizzle.config.ts                 # Drizzle migration config
├── next.config.ts                    # Next.js config
├── package.json                      # npm/pnpm scripts
└── tsconfig.json                     # TypeScript config
```

---

## AUTOMATION_STATUS

### Scheduled Jobs (Vercel Cron)

**File**: `vercel.json`

| Job | Schedule | Endpoint | Purpose |
|-----|----------|----------|---------|
| Volume Discount Recalc | Daily `0 0 * * *` | `/api/cron/monthly-rollover` | Recalculate rolling 30-day spend for volume discounts |

**Implementation** (`src/app/api/cron/monthly-rollover/route.ts`):
- Sums all `paid|ordered|shipped|delivered` orders from last 30 days per client
- Updates `priorMonthSpend` and `currentMonthSpend` fields (used by discount calc)
- Protected by `CRON_SECRET` env var (Vercel Bearer token or query param)

### Manual CLI Tools (in `/tools/`)

| Tool | Purpose | Frequency |
|------|---------|-----------|
| `scrape-cardrush.ts` | Pull supplier prices/stock from CardRush website | Weekly/On-demand |
| `refill.ts` | Generate purchase orders for out-of-stock items (by stock target) | Weekly/On-demand |
| `import-remambo-order.ts` | Sync Remambo proxy orders to `purchases` table | After orders ship |
| `ebay-sync.ts` | Pull paid eBay orders & push inventory updates to eBay | Daily/On-demand |
| `batch-import-orders.ts` | Historical order recovery | Ad-hoc |
| `fulfill-order.ts` | Record fulfillment entries when orders ship | On-demand |

### Data Pipelines

1. **Procurement Loop**:
   - CardRush scraper → `cards` table (price, stock, JPY prices)
   - Refill tool → generates purchase order candidates
   - Admin reviews & submits via Remambo proxy service
   - `import-remambo-order.ts` → syncs purchase table with shipment status

2. **Pricing Loop**:
   - CardRush JPY + GBP/JPY rate → calculated GBP price (8% margin + £0.22 fee + VAT)
   - Price history archived daily to `price_archive` table
   - Historical condition prices cached in `conditionPrices` table

3. **eBay Sync Loop**:
   - `ebay-sync.ts` pulls new paid orders (eBay → `orders` table, channel=ebay-sale)
   - Stock adjustments tagged with channel='ebay-sale'
   - Admin can push inventory updates back to eBay

4. **Order Fulfillment**:
   - Orders transition: submitted → quoted → confirmed → paid → ordered → shipped → delivered
   - `fulfill-order.ts` records partial fulfillment per order item + date
   - Email notifications sent at key state transitions

---

## SCHEMA

### 18 Tables (Drizzle ORM PostgreSQL)

#### Catalog Tables
- **games** (id, code, name, slug, imageUrl, sortOrder, active)
- **sets** (id, gameId→games, code, name, releaseDate, sortOrder, active)
- **cards** (id, cardNumber, sku, name, nameEn, setCode, setName, cardrushUrl, cardrushJpy, gbpJpyRate, baseGbp, price, ebayItemNumber, lastSyncedAt, gameId→games, setId→sets, category[singles|sealed], productType, rarity, imageUrl, stock, pendingStock)
  - Indexes: name, cardNumber, game+category, setCode
  - Custom Numeric Type: `money` (numeric(10,2) → JS number)

#### Commerce Tables
- **orders** (id, clientId→clients, status[submitted|quoted|confirmed|paid|ordered|shipped|delivered|cancelled], total, volumeDiscount, notes, adminNotes, quotedAt, quotedExpiresAt, createdAt, updatedAt, clientOrderNumber, stockCheckedAt, channel[wholesale|ebay-sale], externalOrderId)
- **orderItems** (id, orderId→orders, cardId→cards, quantity, unitPrice, originalUnitPrice, lineTotal, stockStatus[pending|in_stock|out_of_stock|price_changed|partial], checkedPriceJpy, checkedQuantity, remamboSubmittedAt, removedAt)
- **orderStatusHistory** (id, orderId→orders, fromStatus, toStatus, changedBy→clients, changedAt, note, itemsSnapshot[jsonb])

#### Procurement Tables
- **purchases** (id, remamboOrderId[unique], supplier[cardrush], parcelId, orderedAt, shippedAt, receivedAt, status[ordered|shipped|received], itemsTotalJpy, serviceFeeJpy, shippingJpy, notes, createdAt)
- **purchaseItems** (id, purchaseId→purchases, cardId→cards, orderItemId→orderItems, condition, quantity, unitPriceJpy, cardrushUrl, createdAt)
  - Indexes: purchaseId, cardId

#### Pricing Tables
- **priceHistory** (id, cardId→cards, date[YYYY-MM-DD], cardrushJpy, gbpJpyRate)
  - Unique: cardId + date
- **priceArchive** (id, cardId→cards, snapshotDate, sku, setCode, category, cardrushJpy, gbpJpyRate, baseGbp, price)
  - Unique: cardId + snapshotDate
  - Indexes: date, sku
- **conditionPrices** (id, cardNumber, name, setCode, rarity, condition, priceJpy, stock, cardrushUrl, imageUrl, snapshotDate, discountPct)
  - Unique: cardNumber + name + condition + snapshotDate
  - Index: snapshotDate

#### Client & Inventory Tables
- **clients** (id, name, email[unique], passwordHash, company, role[admin|client], currentMonthSpend, priorMonthSpend, volumeDiscountPct, orderPrefix, orderSequence, createdAt)
- **cartItems** (id, clientId→clients, cardId→cards, quantity, cardNumber, sku, cardName, setCode, setName, price, addedAt, updatedAt)
  - Unique: clientId + cardId
- **wantedCards** (id, clientId→clients, cardId→cards, createdAt)
  - Unique: clientId + cardId
- **stockTargets** (id, priceMin, priceMax, targetQty)
  - Used by refill calculator: if card price ∈ [priceMin, priceMax], target stock = targetQty
- **stockAdjustments** (id, cardId→cards, delta, reason[count|damage|loss|found|correction|other], note, channel[manual|ebay-sale], createdAt)
  - Index: cardId

#### Fulfillment & Notifications
- **fulfillmentEntries** (id, orderId→orders, orderItemId→orderItems, fulfilledQty, fulfillmentDate, createdAt)
  - Unique: orderItemId + fulfillmentDate
- **notifications** (id, orderId→orders, type[quote_ready|confirmed|shipped|delivered|new_order], recipient, status[sent|failed], error, sentAt)

#### Multi-Channel Auth
- **channelApiKeys** (id, channel, keyHash[SHA-256], label, createdAt, lastUsedAt)
  - Used for eBay & external channel integrations

---

## BUSINESS_LOGIC

### 1. Pricing Model

**File**: `src/lib/pricing.ts`

**Singles** (most products):
```
baseGbp = cardrushJpy / gbpJpyRate
price = (baseGbp × 1.08 + £0.22) × 1.20
        ├─ 8% margin
        ├─ £0.22 per-card fulfillment fee
        └─ 20% VAT
```

**Sealed** (boosters, boxes):
```
baseGbp = cardrushJpy / gbpJpyRate
price = (baseGbp × 1.08 + £2.20) × 1.20
        ├─ 8% margin
        ├─ £2.20 flat fulfillment fee
        └─ 20% VAT
```

### 2. Procurement Flow

**CardRush → Remambo → UK Warehouse**

1. **CardRush Scrape** (`tools/scrape-cardrush.ts`)
   - Fetches product catalog from CardRush (Japanese supplier)
   - Extracts: JPY price, stock, card details
   - Updates `cards` table with `cardrushJpy`, `cardrushUrl`, `gbpJpyRate`

2. **Stock Target-Based Refill** (`tools/refill.ts`, `/api/admin/refill`)
   - Joins `cards` + `stock_targets` on price range
   - Calculates: `refillQty = max(targetQty - stock - pendingStock, 0)`
   - Segments by price tier (low £5–£20 EMS, high £20–£100 DHL)
   - Generates spreadsheet for manual Remambo order submission

3. **Remambo Proxy Order** (manual)
   - Admin submits selected items to Remambo dashboard
   - Remambo sources from CardRush, consolidates, ships to UK

4. **Import Remambo Order** (`tools/import-remambo-order.ts`)
   - Syncs Remambo order metadata to `purchases` table
   - Tracks `status`: ordered → shipped → received
   - Records: `parcelId`, `shippingJpy`, `serviceFeeJpy`, timestamps

### 3. Inventory Management

**File**: `/api/admin/stock/`, `src/lib/sync-uk-stock.ts`

- **stock**: Items on hand (received - fulfilled)
- **pendingStock**: Items ordered but not yet received
- **Stock Targets**: Price-tier–based minimum stock (e.g., £10–£20 cards → keep 50 on hand)
- **Stock Adjustments**: Manual corrections (damage, loss, count variance) tagged by channel

### 4. Order Workflow

**File**: `src/lib/order-transitions.ts`

```
submitted → quoted → confirmed → paid → ordered → shipped → delivered
  ↓                                              ↓
  └─ Client views catalog, adds to cart         └─ fulfilled_qty recorded per item+date
      Admin reviews, sends quote
      Client accepts quote → payment
      Admin orders from suppliers
      Items ship from UK warehouse
      Fulfillment entries recorded
```

**Key Fields**:
- `clientOrderNumber`: Per-client sequential order ID
- `channel`: wholesale (direct) or ebay-sale (marketplace)
- `externalOrderId`: eBay order ID if applicable
- `stockCheckedAt`: When availability was last verified
- `orderStatusHistory`: Full audit log with snapshots

### 5. eBay Channel Integration

**File**: `src/lib/channels/ebay.ts` (429 lines)

**OAuth Flow**:
- Refresh token stored in `EBAY_REFRESH_TOKEN` env var
- Token expires every 18 months — regenerate via eBay Developer Portal
- 5-minute cache + fallback to client_credentials (public data only)

**Push Listing** (inventory + price):
1. Create/update inventory item (PUT `/sell/inventory/v1/inventory_item/{sku}`)
2. Check for existing offer
3. Update offer (PUT) if exists, or create (POST `/sell/inventory/v1/offer`)
4. Batch operations: 25-item batches with 500ms delay

**Pull Orders** (fulfillment):
- GET `/sell/fulfillment/v1/order?filter=...&offset=X&limit=50`
- Fetch `NOT_STARTED|IN_PROGRESS` orders
- Map to internal order table with `channel=ebay-sale`, `externalOrderId`
- Stock adjustments tagged with `channel=ebay-sale`

**Endpoint**: `/api/admin/channels/ebay/sync/route.ts`

### 6. Volume Discounts

**File**: `/api/cron/monthly-rollover/route.ts`

- Daily cron recalculates 30-day rolling spend
- `priorMonthSpend` = sum of paid/ordered/shipped/delivered orders from last 30 days
- `volumeDiscountPct`: Admin-configured, applied at quote time
- Used by pricing calculator to reduce quoted prices for high-volume clients

---

## TEST_COVERAGE

### E2E Tests (Playwright)

**Location**: `/e2e/`

| Test File | Scope | Status |
|-----------|-------|--------|
| `order-flow.spec.ts` | End-to-end order creation → payment | ✓ Core flow |
| `stock-check-live.spec.ts` | Live stock verification during order review | ✓ Critical path |
| `fulfillment.spec.ts` | Fulfillment page, shipping updates | ✓ Fulfillment UX |
| `cart-persistence.spec.ts` | Cart survives logout/login | ✓ Session state |
| `mobile.spec.ts` | Responsive design on mobile | ✓ Mobile UX |

### Unit Tests

**Location**: `/src/lib/channels/__tests__/`

| Test File | Coverage |
|-----------|----------|
| `ebay.test.ts` | eBay OAuth, token caching, push/pull operations |

**Gaps**: No unit tests for pricing, order workflow, or procurement logic.

---

## AUTOMATION_OPPORTUNITIES

**Ranked by effort (↑ = harder) vs. revenue impact (↓ = higher impact)**

### Tier 1: High Impact, Low Effort (do first)

1. **Automated Price Optimization per Margin Target** ⭐⭐⭐⭐⭐
   - **Impact**: 5–10% revenue lift via dynamic margin/VAT adjustment
   - **Effort**: 2–3 days
   - **How**: Query historical sales velocity + demand. Auto-adjust `MARGIN_PCT` by card demand tier.
   - **Owner**: Pricing calc in `src/lib/pricing.ts` + `/api/admin/prices/` endpoint
   - **Data**: `orders` table (sales history) + `cards` table (stock velocity)

2. **Real-Time Inventory Sync (eBay ↔ UK Warehouse)** ⭐⭐⭐⭐
   - **Impact**: Prevent overselling, 2–3% order cancellation reduction
   - **Effort**: 2–3 days
   - **How**: eBay pull orders → deduct stock → push updated inventory every 6 hours
   - **Owner**: Extend `/api/admin/channels/ebay/sync/route.ts`
   - **Data**: `orders` + `cards.stock` (one-way sync or bidirectional)

3. **Purchase Order Consolidation & Auto-Bulk-Listing to eBay** ⭐⭐⭐
   - **Impact**: 3–5% cost savings (fewer shipments), 2–3 days faster inventory turnover
   - **Effort**: 1–2 days
   - **How**: After purchase received, batch push all new items to eBay once/day via bulk API
   - **Owner**: `/api/admin/channels/ebay/sync/` + `tools/refill.ts`
   - **Trigger**: Refill orders every Sunday + ad-hoc

4. **Dashboard Analytics (Supplier Performance, Margin Analysis)** ⭐⭐⭐⭐
   - **Impact**: Identify top suppliers, spot margin leakage, 1–2% optimization
   - **Effort**: 2–3 days
   - **How**: Aggregate `purchases` + `priceArchive` + `orders` → Grafana/Next.js dashboard
   - **Owner**: New `/app/admin/analytics/` page + new API endpoints
   - **Metrics**: COGS vs. selling price, shipment times, demand patterns

### Tier 2: High Impact, Medium Effort

5. **Demand Forecasting & Smart Stock Targets** ⭐⭐⭐⭐
   - **Impact**: 5–10% reduction in carrying costs, prevent stockouts on bestsellers
   - **Effort**: 3–5 days (ML + DB work)
   - **How**: Time-series forecasting (Prophet/ARIMA) on sales history, auto-update `stock_targets`
   - **Owner**: New tool `tools/forecast-demand.ts`, update `/api/admin/stock-targets/`
   - **Data**: `orders` + `orderItems` (historical sales by card)

6. **Order Fulfillment Automation** ⭐⭐⭐
   - **Impact**: 1–2 day faster shipping, 3–5% better customer satisfaction
   - **Effort**: 2–3 days
   - **How**: Auto-transition orders `confirmed → shipped` when all items marked fulfilled
   - **Owner**: Extend `/api/orders/[id]/status/route.ts`
   - **Trigger**: After `fulfillmentEntries` recorded for all items

7. **Multi-Supplier Price Comparison** ⭐⭐⭐
   - **Impact**: 2–3% cost savings by selecting cheaper suppliers
   - **Effort**: 3–4 days
   - **How**: Add support for 2nd supplier (Cardboard Alchemy, other), compare JPY prices
   - **Owner**: Extend `cards` schema + scraper tools
   - **Data**: New supplier URLs + scraper implementations

### Tier 3: Medium Impact, Medium Effort

8. **Client Churn Prediction & Retention** ⭐⭐⭐
   - **Impact**: Identify at-risk clients early, 5–10% retention improvement
   - **Effort**: 2–3 days (SQL + simple ML)
   - **How**: Flag clients with 30+ days no orders or declining spend
   - **Owner**: New `/app/admin/clients/churn-risk` page
   - **Data**: `clients` + `orders` (grouping by client, purchase frequency)

9. **Dynamic Pricing A/B Testing** ⭐⭐
   - **Impact**: Test premium vs. discount pricing, 1–3% revenue optimization
   - **Effort**: 3–4 days (feature flags + analytics)
   - **How**: Randomly assign new clients to price variants, track conversion
   - **Owner**: Extend pricing calc + new analytics endpoint
   - **Data**: `orders` + new `pricing_experiments` table

10. **Automated Remambo Order Submission** ⭐⭐
    - **Impact**: 1–2 day faster procurement cycle
    - **Effort**: 2–3 days (Remambo API integration)
    - **How**: Auto-POST refill spreadsheet to Remambo API instead of manual upload
    - **Owner**: Extend `tools/refill.ts` with Remambo API client
    - **Trigger**: Weekly auto-generation + manual approval gate

### Tier 4: Lower Priority (Nice-to-Have)

11. **Seasonality & Holiday Forecasting**
    - Detect peak sales periods, pre-order inventory
    - Effort: 2–3 days | Impact: 2–5% peak revenue boost

12. **Supplier Service Level Analytics**
    - Track CardRush delivery times, stockout frequency
    - Effort: 1–2 days | Impact: 1–2% reliability improvement

13. **Mobile App (Client-Facing Order Placement)**
    - Native app for iOS/Android order creation
    - Effort: 5–7 days | Impact: 10–15% if adoption high

14. **Automated Invoice Generation & Payment Tracking**
    - PDF invoices, payment due date reminders
    - Effort: 2–3 days | Impact: 3–5% faster collections

---

## KEY FINDINGS & CONSTRAINTS

### Strengths
1. **Well-Structured Codebase**: Clear separation of concerns (API, components, lib)
2. **Comprehensive Schema**: Handles full order lifecycle + multi-channel + historical pricing
3. **Multi-Channel Ready**: eBay integration mature (OAuth, inventory sync, order pull)
4. **Flexible Pricing**: Supports margin % + per-unit fees + VAT, per-category variants
5. **Good Audit Trail**: Full order status history + stock adjustments tagged by channel

### Constraints & Risks
1. **No Real-Time Sync**: Daily crons only for pricing/discount recalc; eBay & inventory sync manual/on-demand
2. **Manual Procurement**: Refill tool generates candidates, but Remambo submission still manual
3. **Limited Analytics**: No built-in supplier performance, demand forecasting, or churn detection
4. **Test Coverage Gap**: Only E2E + 1 unit test file; no tests for pricing, orders, or procurement
5. **eBay Token Expiry**: Refresh token expires every 18 months; regeneration is manual, not automated
6. **No Rate Limiting**: eBay API bulk push has 500ms delay between 25-item batches; could be more sophisticated
7. **Hardcoded Policies**: Pricing margins, fee structures, policy IDs in env vars (not data-driven)

### Technical Debt
- Python tools in `/tools/` (dashboards, migrations) alongside TypeScript CLI tools
- Migration scripts suggest historical SKU encoding changes; schema may have legacy artifacts
- E2E tests in Playwright; no integration test layer for APIs

---

## NEXT STEPS FOR REVENUE OPTIMIZATION

**Week 1**:
1. Deploy real-time eBay ↔ UK warehouse inventory sync (Tier 1, item 2)
2. Build supplier performance dashboard (Tier 1, item 4)
3. Set up automated demand forecasting job (Tier 2, item 5)

**Week 2**:
1. Implement dynamic margin optimization (Tier 1, item 1)
2. Add churn risk detection for clients (Tier 3, item 8)
3. Automate purchase order consolidation (Tier 1, item 3)

**Metrics to Track**:
- Gross margin % (current vs. optimized)
- Inventory turnover (days on hand)
- Order fulfillment time (submit → shipped)
- Client lifetime value (LTV)
- Repeat purchase rate

---

**Report Generated**: 2026-03-28
**Scope**: Read-only codebase reconnaissance
**Status**: Ready for implementation planning
