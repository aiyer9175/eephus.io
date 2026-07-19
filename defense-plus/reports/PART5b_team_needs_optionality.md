# Team-need / up-spectrum moves — can we predict the Betts/Rafaela-at-SS pattern?
Date: 2026-06-18 · `pipeline/20_team_needs.py`

## Question
Established players sometimes cover a MORE premium position than their own (Rafaela CF→SS,
Betts RF/2B→SS) to fill an org hole. The need is unobservable — but is *who gets asked* predictable?

## Findings
- **37%** of established players (career ≥200 GS) ever made an up-spectrum move.
- **Up-movers are far more VERSATILE, not faster:** versatility 3.9 vs 2.6 positions; sprint **27.0 vs 26.9 ft/s** (no difference). Multi-position history — not raw speed — is the signal.
- **Emergency-SS (the Betts/Rafaela case)** — 105 non-SS who covered SS while established: **versatility 4.4 vs 3.1**, sprint 27.3 (~59th pct). Athleticism gates eligibility *modestly*; versatility is the real marker.
- Whole-population AUC for "ever up-moves" is high (0.91) but **partly mechanical** — low-spectrum players (a 1B playing LF) count as "up" trivially. The honest signal is the versatility gap on *premium-position* coverage, not that AUC.

## Conclusion — capacity, not need
We **cannot** predict the org need (timing/whether a team has a hole) — it's idiosyncratic, exactly as expected. We **can** flag *capacity*: a versatile (4+ position) player is the one who'll be asked to cover SS/CF in a pinch. So the meaningful output is **positional optionality**, not a point prediction.

## Implication for Career+ (v1.2)
- Add a **positional-optionality** term for high-versatility players: a small probability each year of covering a *more* premium position (occasional + positional-adjustment value), and **wider position uncertainty**. This is upside-only and small — do NOT bake in specific up-moves.
- This also explains the 42% "up-spectrum" share of migration (Part 5): much of it is versatility-driven need coverage, not development.
- Versatility itself becomes a projectable feature (stable career trait); sprint speed is not the lever here.

## Files
- `pipeline/20_team_needs.py` → `reports/20_team_needs.csv`
