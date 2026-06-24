# Part 8 — Frame / Body Type
Date: 2026-06-18 · `pipeline/24_frame_body.py` · height/weight from statsapi (3,768 fielders), BMI = 703·lb/in²

## 1. Frame by position — premium positions are lean
| pos | height | weight | BMI |
|---|---|--:|--:|
| SS | 6'0" | 200 | **27.0** |
| 2B | 5'11" | 197 | 27.5 |
| CF | 6'0" | 204 | 27.4 |
| LF | 6'0" | 208 | 27.9 |
| RF | 6'2" | 216 | 28.0 |
| 3B | 6'0" | 212 | 28.4 |
| 1B | 6'2" | 230 | **29.6** |
Up-the-middle (SS/2B/CF) are the leanest; 1B the biggest. A 230-lb SS is a ~3σ outlier.

## 2. Leaner → more range (within position)
corr(weight, OAA): SS −0.14, **CF −0.18**, 3B −0.16, 2B −0.01. Modest but real — lighter players have more range, strongest at CF (pure speed).

## 3. Heavier → slides off premium positions (Frame+ retention)
P(move off position next year), lean BMI 25 → heavy BMI 30:
- **SS: 16% → 27%** (BMI coef +0.14)
- CF: 23% → 31%
- 2B: 22% → 26%
Body strongly predicts position retention — a thick-framed SS is ~70% more likely to slide down than a lean one.

## 4. Heavier → ages faster defensively
age×BMI interaction on ΔOAA = **−0.043** (heavier decline faster with age). At age 30+: **heavy (BMI≥29) −0.68 OAA/yr vs lean (BMI≤26) +0.76.** Frame is a leading indicator of the defensive aging trajectory. *(Caveat: the lean +0.76 is partly survivorship; the robust signal is heavy-declines-faster.)*

## Use
Frame feeds three parts of the system:
- **Talent:** leaner = modestly more range.
- **Migration (Career+):** heavier → higher P(slide off premium position) — a body-conditioned migration term.
- **Aging (Career+):** heavier → faster defensive decline — a body-conditioned aging multiplier (like the component profiles).
- **Prospect prior (Part 6/7 + this):** a prospect's frame predicts his eventual position and defensive trajectory — exactly what the MiLB→MLB Defense+ prior needs.

## Files
- `pipeline/24_frame_body.py`, body cache `data/raw/body.parquet`
