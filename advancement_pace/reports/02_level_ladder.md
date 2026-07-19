# 02 — Canonical Level Ladder (LEVEL_MAP_VERSION 1.0.0)

```
rank 1  Rk   Complex / Rookie   (sportId 16: ACL, FCL, DSL)
rank 2  A    Low-A              (sportId 14)
rank 3  A+   High-A             (sportId 13)
rank 4  AA   Double-A           (sportId 12)
rank 5  AAA  Triple-A           (sportId 11)
        MLB  terminal event, NOT a rung
```

**MLB handling.** MLB is excluded from the MiLB-only scale. Including the debut as a
"6th rung" would (a) mix the metric with the debut decision, which is owned by
opportunity/timing modeling on the predictive side, and (b) make pre-debut and
post-debut scores incomparable. The debut is recorded as a terminal event: seasons
after `mlb_debut_season` are excluded; the score freezes at the last pre-debut as-of.

**Special populations** (charter checklist):
- **DSL / ACL / FCL** — all report under sportId 16 and cannot be separated at this
  grain; they share rank 1. Entry age + entry pathway carry the DSL-vs-domestic
  distinction into the peer baseline (a 17-year-old international amateur is compared
  with that cohort).
- **Former short-season leagues (pre-2021)** — historical short-season A reported under
  sportIds outside {11,12,13,14,16} are excluded; era buckets in the baseline separate
  pre/post-2021 development environments. Unmapped-sport rows dropped this build: 0.
- **Low-A/Single-A renames (2021)** — absorbed by sportId (14 is always the low
  full-season level).
- **Rehab assignments** — not separable from ordinary assignments in season lines, but
  three protections make them inert: post-debut seasons are excluded entirely; the
  highest-meaningful-level construction means low-level PA can never reduce ladder
  height for players still climbing; and the 30-PA meaningful threshold removes
  most rehab-length stints.
- **Fall/winter leagues, independent/foreign leagues, spring training, taxi placements**
  — absent from the season-line sources; structurally cannot create advancement steps.
  Foreign-professional signees appear when they first play affiliated ball (usually AA/AAA
  entries in the `undrafted_other` pathway) and are peer-adjusted within that rare cohort.

The map lives in `level_map.py` and is versioned; any reordering or added level bumps
`LEVEL_MAP_VERSION` and the methodology version.
