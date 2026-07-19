# 08 — Advancement Pace+ Construction (methodology 1.0.0)

```
advancement_residual = area_pace − expected_peer_pace
z_raw   = residual / SD(residual | experience_year)
z_stab  = z_raw × m / (m + 1)          m = meaningful assignments (k=1 stabilizer)
AP+     = 100 + 10 × z_stab            (public; raw 100+10·z_raw kept internally)
display = clip(AP+, 70, 130)           (uncapped score retained internally)
```

Percentile: rank of z_stab within the same experience-year scoreable population
(`advancement_percentile`; UI displays min(·, 99)).

## Published distribution (45,627 scoreable as-of rows, 14,748 players)
mean 100.06, median 99.96, SD 7.14, min 52.4, max 149.5;
0.14% of rows below 70 and 0.40% above 130 hit the display cap.
SD < 10 by design: the stabilizer keeps thin histories out of the tails, so only
players with real level history can post extreme public values.

## Scale language (charter warning honored)
The scale is standardized-residual based. **118 does NOT mean "18% faster"** — public
copy must say "about two standard units faster than comparable players", never a
percentage. This is embedded in the methodology copy (13).

## Every published row also carries
raw observed pace, expected peer pace, residual, sample-quality tier, active pro
seasons, meaningful assignments, meaningful promotions, starting level, current level,
position group, entry pathway, reference population, methodology/data versions —
the full charter schema (12).

## Descriptive association, stated once
Players who eventually debuted average AP+ ≈ 108.5 at their last pre-debut as-of vs
≈ 97.9 for those who never did. This is reported as *face validity of the description*
(fast climbers reach the majors — near-tautological), not as predictive evidence, and
the isolation contract (11) guarantees no model can consume it.
