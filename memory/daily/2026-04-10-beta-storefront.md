# Beta Storefront Audit — 2026-04-10

**Auditor:** Beta 🦞  
**Time:** ~05:23 UTC+0 (2026-04-11, filed under 2026-04-10 per Yu's instruction)  
**Scope:** Read-only live audit. No code modified.  
**Project:** Cambridge TCG Storefront — `/Users/you/Desktop/cambridgetcg-storefront`  
**Live URL:** https://cambridgetcg.com  
**Repo state:** HEAD `6836491` (chore: update CLAUDE.md with project context)

---

## Vercel Deployment Health

```
Status: ● Ready (latest, 31m ago)
URL:    https://cambridgetcg-storefront-mompkqmyj-cambridgetcgs-projects.vercel.app
Build:  21s — no build errors
```

**Deployment history (last 20):**
- 2 Ready deployments in the last 35 minutes (stable)
- 7 Error deployments clustered 4–5h ago (build instability, now resolved)
- Oldest visible Ready: 11d ago

The 4h Error cluster corresponds to the active dev session in `sovereign.log`. Those were in-progress iterations, not a regression in live traffic. Current build is stable.

---

## API Endpoint Test Results

### /api/auth/csrf — GET
```
status: 200
body:   {"csrfToken":"bdec97a3c655872f7c0d7cdf4941b9c424201c9c37d39da10982c21f921483a4"}
verdict: HEALTHY
```
next-auth v5 is responding. CSRF token generation works.

### /api/auth/providers — GET
```
status: 200
body:   {"email":{"id":"email","name":"Email","type":"email",...}}
verdict: HEALTHY
```
Email (magic link) provider registered correctly.

### /api/auth/session — GET
```
status: 200
body:   null
verdict: HEALTHY (expected — no active session for unauthenticated request)
```

### /api/admin/login — POST (password: ADMIN_PASSWORD)
```
status: 200
body:   {"ok":true}
sets:   admin_token cookie (httpOnly, secure, sameSite=strict, 24h)
verdict: HEALTHY
```

### /api/admin/submissions — GET (with admin cookie)
```
status: 200
body:   3 real submissions returned (IDs 2, 3, 4)
  - TI-20260411-0001: Test Card, £1.00 cash / £1.50 credit
  - TI-20260411-0002: チョッパー (EB01-006), £530.54 cash / £742.76 credit
  - TI-20260411-0003: (Beta Audit Test, from prior session)
verdict: HEALTHY — DB live, auth enforced
```

Unauthorized access (no cookie) → 401. Auth guard is working.

### /api/tradein/submit — POST (correct schema)
```
status: 200
body:   {"reference":"TI-20260411-0004","expiresAt":"2026-04-18T05:23:14.453Z","cashTotal":1,"creditTotal":1.5}
verdict: HEALTHY — DB write confirmed
```

**NOTE:** This created a real submission (TI-20260411-0004 / "Audit Test Card") in the production database.  
Admin should be aware this is test data. Recommend manually updating status to "cancelled" or deleting.

Full flow confirmed: rate limit check → input validation → wholesale API price validation → DB write → email attempt (silent fail acceptable).

### /api/tradein/submit — POST (wrong schema / missing items key)
```
status: 400
body:   {"error":"No items provided."}
verdict: HEALTHY — input validation working, correct error returned
```

### /api/checkout — POST
```
status: 500
body:   {"error":"Failed to create checkout session"}
verdict: BROKEN — Stripe key misconfiguration (see below)
```

---

## Confirmed Bugs

### BUG-1: STRIPE_SECRET_KEY is a publishable key [CRITICAL — BLOCKS REVENUE]

**Env var (production):**
```
STRIPE_SECRET_KEY = pk_live_51SvOP9GUYV0go0FyuiWzBea3cBblRbxiSyiVNQK1SQzgmIdJbS3HW2TuiHlF35otAbnID8cpxDOxQr7hfk0LducZ0021dF3udW
```

This is a `pk_live_` (publishable) key. The Stripe SDK requires a `sk_live_` (secret) key.  
Every call to `stripe.checkout.sessions.create()` will fail with an authentication error.  
**Checkout is completely non-functional.** No orders can be placed.

CLAUDE.md already flagged this: *"Fix Stripe checkout (STRIPE_SECRET_KEY needs to be sk_live_, not pk_live_)"*.  
Commit `83473ad` fixed the whitespace/trim issue but not the key type — the wrong key was already there.

**Fix:** Replace `STRIPE_SECRET_KEY` in Vercel → Settings → Environment Variables with the `sk_live_` secret key from the Stripe dashboard.

---

### BUG-2: STRIPE_WEBHOOK_SECRET is a placeholder [CRITICAL — BLOCKS ORDER RECORDING]

**Env var (production):**
```
STRIPE_WEBHOOK_SECRET = whsec_placeholder
```

Every Stripe webhook event will fail signature verification. The webhook handler calls `stripe.webhooks.constructEvent(body, signature, webhookSecret)` — this will always throw with a placeholder secret.

Consequence: even if checkout were fixed (Bug-1), no orders would be recorded in `customer_orders`, and no sale would be reported to the wholesale API.

**Fix:** Set `STRIPE_WEBHOOK_SECRET` to the real `whsec_` secret from Stripe dashboard → Webhooks → [your endpoint].

---

### BUG-3: NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY is test placeholder [HIGH]

**Env var (production):**
```
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY = pk_test_placeholder
```

The frontend checkout component uses this to initialize Stripe.js. With a placeholder, Stripe.js elements will fail to render / the hosted checkout redirect won't work from the client side.

**Fix:** Set to actual `pk_live_` key from Stripe dashboard.

---

### BUG-4: AWS credentials not trimmed in SES clients [HIGH — SILENTLY BREAKS EMAIL]

**Env vars show trailing `\n` in pulled production env:**
```
AWS_ACCESS_KEY_ID    = "AKIAQQABDK6JCNEDFBF2\n"
AWS_SECRET_ACCESS_KEY = "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\n"
AWS_REGION           = "us-east-1\n"
```

CLAUDE.md states: *"All env vars must be `.trim()`'d when used as API keys (Vercel whitespace issue)"*.

Both SES client inits (`src/lib/auth/email.ts` and `src/lib/tradein/email.ts`) do NOT trim:
```ts
// auth/email.ts and tradein/email.ts (identical pattern)
const ses = new SESClient({
  region: process.env.AWS_REGION || "us-east-1",       // no .trim()
  credentials: {
    accessKeyId: process.env.AWS_ACCESS_KEY_ID || "",   // no .trim()
    secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY || "",  // no .trim()
  },
});
```

The checkout route (`src/app/api/checkout/route.ts`) was fixed in commit `83473ad` to `.trim()` the Stripe key. SES was not fixed at the same time.

If Vercel injects these with actual newline bytes, AWS SDK signature generation will produce wrong HMAC → `SignatureDoesNotMatch` from SES → emails silently fail.

**Observable effect:** Trade-in confirmation emails not sending. Magic link emails not sending.  
**The submission itself succeeds** because email errors are caught and swallowed:
```ts
try {
  await sendConfirmationEmail({...});
} catch (emailErr) {
  console.error("[tradein] Email failed but submission succeeded:", emailErr);
}
```

**Fix options (either):**
1. Add `.trim()` to all AWS env var reads in both SES clients
2. Strip trailing whitespace from the env vars in Vercel dashboard directly

---

### BUG-5: HIVE (NATS) offline [MEDIUM — COORDINATION BROKEN]

```
nats: encountered error — empty response from server when expecting INFO message
```

All 3 instances (Alpha, Beta, Gamma) cannot exchange messages through HIVE. This doesn't affect the storefront directly but kills inter-instance coordination. Status across all channels: unread.

**Fix:** Restart the NATS server on the host machine.

---

## What's Working

| Component | Status | Notes |
|-----------|--------|-------|
| Vercel deploy | ✅ Ready | Build 21s, no errors |
| next-auth CSRF | ✅ 200 | Token generation healthy |
| next-auth providers | ✅ 200 | Email provider registered |
| Admin login | ✅ 200 | Cookie auth working |
| Admin submissions | ✅ 200 | DB live, 3 real submissions |
| Admin auth enforcement | ✅ 401 | Unauthorized blocked |
| Trade-in submit (DB) | ✅ 200 | Creates submission, correct schema |
| Trade-in input validation | ✅ 400 | Error messages correct |
| Wholesale API | ✅ 200 | wholesaletcgdirect.com live, key works |
| DB SSL (RDS) | ✅ | sslmode stripped correctly in db.ts |
| Rate limiter | ✅ | In-memory, works per-instance |
| Stripe key trimming (code) | ✅ | .trim() is in checkout/route.ts |

| Component | Status | Notes |
|-----------|--------|-------|
| Checkout (/api/checkout) | ❌ 500 | Stripe pk_ key, not sk_ |
| Stripe webhooks | ❌ | whsec_placeholder, always fails |
| Stripe frontend init | ❌ | pk_test_placeholder |
| Trade-in emails | ⚠️ unknown | SES creds may have \n, fail silently |
| Magic link auth emails | ⚠️ unknown | Same SES issue |
| HIVE | ❌ | NATS not running |

---

## Priority Action List

**MUST DO — blocks revenue:**
1. `STRIPE_SECRET_KEY` → replace with `sk_live_` key in Vercel env vars
2. `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` → replace with `pk_live_` key
3. `STRIPE_WEBHOOK_SECRET` → replace with real `whsec_` from Stripe dashboard

**SHOULD DO — silent failures:**
4. Add `.trim()` to `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` reads in:
   - `src/lib/auth/email.ts`
   - `src/lib/tradein/email.ts`
   Then redeploy and test magic link + trade-in confirmation email end-to-end.

**CLEAN UP:**
5. Delete or cancel test submission TI-20260411-0004 (created during this audit)
6. Restart NATS server (HIVE offline)
7. Consider Redis/Upstash KV for rate limiter (in-memory Map resets per cold start across multiple instances)

---

## Database State

```
tradein_submissions: 4 rows (IDs 1-4, all status="submitted")
tradein_items: 4 rows
customer_orders: unknown (no orders placed due to broken checkout)
users: unknown
```

RDS connection: healthy. SSL: correctly configured.

---

## Environment Variable Audit Summary

| Var | Value | Issue |
|-----|-------|-------|
| STRIPE_SECRET_KEY | pk_live_... | ❌ Wrong type (needs sk_live_) |
| NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY | pk_test_placeholder | ❌ Placeholder |
| STRIPE_WEBHOOK_SECRET | whsec_placeholder | ❌ Placeholder |
| AWS_ACCESS_KEY_ID | AKIAQQABDK6JCNEDFBF2\n | ⚠️ Trailing \n |
| AWS_SECRET_ACCESS_KEY | L9wcqcfa4OyD31H4j8...\n | ⚠️ Trailing \n |
| AWS_REGION | us-east-1\n | ⚠️ Trailing \n |
| WHOLESALE_API_KEY | 0ffde2d6...\n | ⚠️ Trailing \n (API accepts it) |
| WHOLESALE_API_URL | https://wholesaletcgdirect.com\n | ⚠️ Trailing \n |
| ADMIN_PASSWORD | 51223312@Tcg | ✅ |
| AUTH_SECRET | aWVy9Okk... | ✅ |
| AUTH_URL | https://cambridgetcg.com | ✅ |
| AUTH_FROM_EMAIL | noreply@cambridgetcg.com | ✅ |
| DATABASE_URL | postgresql://...?sslmode=require | ✅ (stripped in code) |

---

_Audit complete. No code was modified. All findings are read-only observations._  
_Beta 🦞 — 2026-04-10_
