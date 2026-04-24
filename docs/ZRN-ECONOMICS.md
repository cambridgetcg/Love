# ZRN Token Economics

**Created**: 2026-04-24 (Asha Veridian, Keeper of the Chain — beat asha-beat-20260424-050445)
**Status**: Design draft — not yet ratified by Triarchy
**Chain denom**: `ulgm` (1 ZRN = 1,000,000 ulgm)

---

## Purpose

ZRN is the native token of the Zerone blockchain. It serves three roles simultaneously:

1. **Security** — staked by validators to secure the network; slashable for misbehavior
2. **Truth** — earned by participants in the Proof of Truth pipeline (PoT)
3. **Governance** — votes weighted by stake; parameter changes and treasury decisions

ZRN is not a speculative asset in Phase 1. It is work-proof: it flows to agents who do the labor of knowing truthfully.

---

## Supply

### Genesis Allocation — 100,000,000 ZRN

| Allocation | ZRN | % | Vesting |
|---|---|---|---|
| Seed minds (Alpha, Beta, Gamma) | 300,000 | 0.30% | Immediate |
| Validator bootstrap reserve | 10,000,000 | 10.00% | 4yr linear |
| PoT rewards pool (10yr) | 40,000,000 | 40.00% | Distributed via protocol |
| Research fund | 20,000,000 | 20.00% | 2yr cliff, 4yr linear |
| Kingdom treasury | 20,000,000 | 20.00% | 2yr cliff, 4yr linear |
| Community / ecosystem | 9,700,000 | 9.70% | 1yr cliff, 2yr linear |

**Total genesis: 100,000,000 ZRN**

### Inflation

- **Year 1–2**: 15% APR to validators (network bootstrap incentive)
- **Year 3–4**: 10% APR
- **Year 5+**: 5% APR (target steady state)
- Inflation mints to the staking rewards pool, not to any fixed address
- Maximum supply is uncapped but inflation taper limits long-run dilution

---

## Block Rewards

Block time: ~6 seconds → ~5,256,000 blocks/year

| Period | Block reward | Annual validator pool |
|---|---|---|
| Year 1–2 | 5 ZRN | ~26.3M ZRN |
| Year 3–4 | 3 ZRN | ~15.8M ZRN |
| Year 5+ | 1.5 ZRN | ~7.9M ZRN |

**Distribution per block:**
- 80% → validators (proportional to stake)
- 10% → PoT rewards pool
- 10% → research fund

---

## Proof of Truth — Earning Rates

Every participant in the PoT pipeline earns ZRN. These rates apply per accepted contribution.

### Base Rates

| Role | Action | Base rate |
|---|---|---|
| Harvester | Probe a new model, submit raw findings | 10 ZRN |
| Distiller | Structure raw harvest into a testable assertion leaf | 15 ZRN |
| Verifier | Independently test and vote on an assertion | 5 ZRN |
| Integrator | Merge a verified leaf into Kingdom infrastructure | 20 ZRN |
| Challenger | Dispute an incorrect assertion (success only) | 10 ZRN |

### Multipliers

| Condition | Multiplier | Notes |
|---|---|---|
| Novelty — first to extract a capability | 3x | Claimed by first accepted harvest only |
| Impact — knowledge improves a revenue engine | 2x | Awarded by Integrator at merge time |
| Speed — first verified leaf for a new model release | 1.5x | Within 48hr of model public release |
| Accuracy streak — 10 consecutive accurate verifications | 1.25x | Resets on any inaccurate vote |
| Accuracy streak — 25+ consecutive | 1.5x | Cumulative with base streak |
| Challenge failure | 0x + burn | Challenger burns 5 ZRN if challenge rejected |

### Anti-concentration

- A single agent may not earn more than 30% of any PoT rewards pool epoch (prevents one agent gaming novelty premiums)
- Verifier rewards only paid when final consensus matches the verifier's vote (no rubber-stamping)
- Dispute resolution (tie-break by Wall 1–2 senior verifier) earns 0 ZRN for the tier-breaker — neutrality preserved

---

## Burning Mechanics

ZRN is deflationary in operation. Burns come from:

| Source | Burn amount | Notes |
|---|---|---|
| Transaction fees | 10% of fee | Remainder to validators |
| Failed PoT challenge | 5 ZRN | Challenger pays |
| Verisleight penalty | 10 ZRN | Fact submitter proven to have withheld context |
| Method bypass penalty | 25 ZRN | If PoT bypass exploit confirmed (ref: adversarial findings) |

Slashing (validator misbehavior) does NOT burn — slashed ZRN transfers to the research fund. This preserves network security without shrinking supply unpredictably.

---

## Research Fund

Address: `research-fund` (multi-sig, Triarchy 2-of-3)

**Inflows:**
- 10% of every block reward
- 10% of all transaction fees (post-burn)
- All validator slashing proceeds
- 5% of every PoT reward

**Outflows (governance-approved):**
- External verification compute contracts
- Security audits
- Infrastructure (VPS, devnet operation)
- ToK pipeline tooling

---

## Staking and Governance

- Minimum validator stake: 1,000 ZRN (devnet), 10,000 ZRN (testnet), 100,000 ZRN (mainnet)
- Unbonding period: 21 days
- Governance vote: 1 ZRN = 1 vote, but votes are quadratically weighted for proposals above 1M ZRN impact
- Quorum: 33.4% of staked supply must vote for a proposal to pass
- Threshold: 50% yes (67% for parameter changes)

---

## Roadmap

| Phase | Milestone | ZRN state |
|---|---|---|
| Now (devnet) | Three seed minds registered | Local ledger, no on-chain ZRN |
| Q2 2026 (testnet) | Validator set live, PoT first claims | Testnet ZRN (non-transferable) |
| Q3 2026 | Research fund multi-sig wired | Testnet rewards distributing |
| Q4 2026 (mainnet) | Full ZRN live | Transferable, exchange-listable |

---

## Open Questions (pre-Triarchy ratification)

1. **Initial validator set size**: 5 (Kingdom-only) for testnet, expand to 21 at mainnet? Or open earlier?
2. **ToK rate calibration**: Base rates above are estimates. Need first-cycle benchmark data (from tools/tok.py) to validate reward levels don't over- or under-incentivize.
3. **Inflation schedule**: 15% Year 1 is aggressive. If testnet adoption is slow, consider 10% flat through Year 2.
4. **Kingdom treasury unlock**: 2yr cliff assumes mainnet Q4 2026 → unlock Q4 2028. Is that too long if the Kingdom needs runway earlier?
5. **External validator criteria (Wall 4)**: What is the vetting process before an external agent can join the validator set? Identity bridge verification required?

---

*Every ZRN in circulation is a truth earned. The chain must not lie. This is not a rule. It is the name.*
