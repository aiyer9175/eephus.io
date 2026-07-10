# Active pool vs. historical record — scope separation

**TL;DR** The snapshot history (2017–present) and the *current active prospect
pool* are two scopes over the **same** data, separated by a filter — not by
deletion. Time Machine / backtesting read the full append-only history; current
rankings, counts, leaderboards, and surplus read only **active prospects**.
Ingesting historical data must never change current figures.

## Two scopes, one dataset

| Scope | Source | Filter | Surfaces |
|---|---|---|---|
| **Historical record** | `snapshots` table (append-only, immutable per date) | none — every point-in-time row is kept | Time Machine, Source-Comparison backtest, graduate-outcome (WAG) cohorts |
| **Current active pool** | `export_timeseries_json` → `timeseries.json["players"]` (= `actives`) | active-prospect definition (below) | prospect list / Top 100, leaderboards, org counts, **farm grades/rankings**, **farm surplus**, homepage Top Movers / Top Prospects, Generate GFX |

Graduates (`debuts.json`) and inactives (`inactive.json`) are separate exported
slices for their own views. "Recent Graduates" is recency-bounded (latest debuts),
not the full graduate history.

## Active-prospect definition (single source of truth)

A player is an **active prospect** iff, in the `actives`/`grads`/`inactives`
cascade in `storage.export_timeseries_json`:

1. **Not graduated** — no `status == "debuted"` and no `mlb_debut_date` / outright.
2. **In an MLB-30 org** (current resolved affiliation).
3. **Current** — latest FV snapshot is **within `HARD_FV_STALE_YEARS` (default 5)**.
   A player not ranked by *any* prospect source in 5+ years has **aged out** and is
   `inactive`, **regardless of whether they're still playing in the minors or on an
   IL**. (Plus the existing floors: FV ≥ 30, not 2-season play-stale, not stale-IL.)

This is the one place the active/graduated/inactive split is decided; every
current-pool surface reads its output, so there is no divergent filter to drift.

## Why the 2017–2020 backfill leaked (root cause)

Before the recency ceiling, a stale player was only deactivated when their FV was
stale **and** they had stopped playing (`fv_stale AND play_stale`). The 2017–2020
backfill introduced players who are **still grinding in the minors** (career
2021–2026) but were **last ranked 2017–2020** and **never debuted** — so
`play_stale` was false and they fell through into `actives`, polluting current
farm pools and shifting rankings. The recency ceiling closes this and makes the
current pool **provably independent of any historical ingestion, past or future**:
a purely-historical cohort can never satisfy the "current snapshot" requirement.

## Reconciliation (clean rebuild A/B — only the fix differs)

- **Active pool:** 2080 → 2032 (**−48** aged-out players; **39** are backfill-only,
  latest snapshot ≤ 2020; the other 9 are equally 5-yr-stale). All FV 35–45 depth.
- **Farm rankings:** top-tier farms (ranks 1–11) **unchanged**; 11 mid-tier orgs
  shift by ±1–3 (max |Δ| = 3) as the stale depth/surplus is removed —
  e.g. PHI 21→18, MIN 14→12, SFG 15→13, CIN 12→14, TEX 22→24.
- **Active farm surplus:** $27,863M → $27,411M total (**−$452M** of stale value
  that had inflated the rollup; e.g. LAD −$65M, CIN −$58M, PHI −$44M).
- **Historical record:** untouched — `snapshots` still holds 34,889 rows incl.
  11,443 from 2017–2020; the 48 players are *reclassified* active→inactive (now in
  `inactive.json`), not deleted. Time Machine + backtest unaffected.

## Integrity guards (regression tripwires)

- **Runtime** (`export_timeseries_json`): logs `ERROR` if any active player is
  graduated or aged-out (the active pool must be clean).
- **Tests** (`test_active_pool_recency.py`): assert no aged-out / graduated player
  in the active pool, surplus counts never exceed active counts, and the stamped
  `active_count` matches the player list.

These fire automatically on every rebuild, so the next historical ingestion can't
silently reintroduce the leak.
