# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Fit the three shrink constants of eWAR's blended pitching basis S2b
(docs/ebr-2026-09-30/EBR_GATE.md part 11.3.2), once, before the skill look.

    python tools/pitch_basis_fit.py

THE RULE (B1's, swar_lab.fit_b1, the DEM+ K_INN precedent): for each term T in
{CQ, B, L} with exposure n (batted balls C for CQ and B, runners allowed N for
L), the pooled Pearson r of T / n in Y and in Y+1 over the 2016 to 2018
predictor pairs of pitchers with 50 or more IP in both seasons (positive
exposure in both), r clamped to 0.05 to 0.95, k = hm (1 - r) / r with hm the
mean harmonic exposure of the pairs, rounded to a whole unit.

WHAT IT READS. The three raw terms and their exposures from a dark preview build
of 2016 to 2019 with every constant unset (tools/build_swar.build with
k_consts None, out_path None: nothing is written). CQ is read on the actual
home-run count (the hr_fwar variant), the reading that does not depend on the
HR-arm clause the look computes; B and L do not depend on the variant. It never
reads S2, a delta, a test value, fWAR or any target, and it prints only the
pair counts, r, hm and k per term. Its output is copied into pitch_basis.py's
K_CQ, K_BAB, K_LOB and K_FIT_LOG by hand, in the build commit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

FIT_SEASONS = (2016, 2017, 2018)
MIN_IP = 50.0
R_CLAMP = (0.05, 0.95)
VARIANT = "pb_hr_fwar"
TERMS = {"cq": "c", "bab": "c", "lob": "n"}


def term_rows(payload: dict) -> dict:
    """{season: {mlbam: {"ip", "cq", "bab", "lob", "c", "n"}}} off a preview
    payload: the raw terms and exposures only."""
    out: dict = {}
    for s, blk in (payload.get("seasons") or {}).items():
        rows = {}
        for r in blk.get("pitchers") or []:
            t = (r.get("parts") or {}).get(VARIANT) or {}
            if t.get("c") is None:
                continue
            rows[int(r["mlbam"])] = {"ip": r.get("ip"), **{k: t.get(k) for k in ("cq", "bab", "lob", "c", "n")}}
        out[int(s)] = rows
    return out


def fit(rows: dict, seasons=FIT_SEASONS) -> dict:
    out = {}
    for term, expo in TERMS.items():
        x0, x1, hm, players = [], [], [], set()
        for y in seasons:
            a, b = rows.get(int(y)) or {}, rows.get(int(y) + 1) or {}
            for mid, r0 in a.items():
                r1 = b.get(mid)
                if r1 is None:
                    continue
                if (r0["ip"] or 0) < MIN_IP or (r1["ip"] or 0) < MIN_IP:
                    continue
                n0, n1 = r0[expo] or 0.0, r1[expo] or 0.0
                if n0 <= 0 or n1 <= 0 or r0[term] is None or r1[term] is None:
                    continue
                x0.append(r0[term] / n0)
                x1.append(r1[term] / n1)
                hm.append(2.0 / (1.0 / n0 + 1.0 / n1))
                players.add(mid)
        if len(x0) < 30:
            raise RuntimeError(f"{term}: {len(x0)} pairs, under 30")
        r_raw = float(np.corrcoef(x0, x1)[0, 1])
        r = min(max(r_raw, R_CLAMP[0]), R_CLAMP[1])
        hmm = float(np.mean(hm))
        out[term] = {"exposure": "batted balls" if expo == "c" else "runners allowed",
                     "n_pairs": len(x0), "n_players": len(players), "r_raw": round(r_raw, 4),
                     "r": round(r, 4), "hm": round(hmm, 1), "k": float(round(hmm * (1.0 - r) / r))}
    return out


def main() -> int:
    import build_swar as B
    payload = B.build(list(FIT_SEASONS) + [FIT_SEASONS[-1] + 1], out_path=None,
                      k_consts=(None, None, None), log=lambda *a: None)
    res = fit(term_rows(payload))
    print(json.dumps({"fit_seasons": list(FIT_SEASONS), "min_ip": MIN_IP, "variant": VARIANT,
                      "fwar_vintage_id": payload.get("fwar_vintage_id"), "terms": res}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
