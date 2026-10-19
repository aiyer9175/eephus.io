# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""B1's fit for the eWAR v3 skill look (docs/ebr-2026-09-30/EBR_GATE.md part
9.5, 'B1 = a uniformly shrunk fWAR, (x * n + m * k) / (n + k), one k per side
fitted on 2016 to 2018 predictor pairs ... before the look, on published fWAR
only').

    python tools/swar_b1_fit.py
    python tools/swar_b1_fit.py --amended     # part 11.2.1's B1: one k per component

Reads the preview tools/build_swar.py writes, through swar_lab.exposure_rows,
which keeps ONLY each player-season's published fWAR and its exposure (PA for
hitters, IP for pitchers): no candidate part, delta or test value is read, so
the fit computes no statistic of any candidate part. Prints the fit log; the
constants it prints are frozen by hand into swar_lab.B1_K and
swar_lab.B1_FIT_LOG, once, before the look. Writes nothing.

--amended (EBR_GATE.md 11.2.1, 11.4.4, 11.6.2): one k per component, from B0
and the component's own target only (swar_lab.component_pairs with
with_tests=False, after swar_lab.assemble with deltas=False, so no candidate
part, delta or test value is computed or read): batting (wRAA per PA against
wRAA per PA in Y+1), pitching (war0 per IP against RA9* runs prevented per IP),
fielding (Fld + Frm per PA against Baseball-Reference runs_field per PA), the
catcher frame (B0 per PA against DRS per PA), PE-P (war0 per game against RSB
per game) on the 2016 to 2018 predictor pairs, and PE-H (wRAA per PA against
wRAA plus realized starter wear per PA) on the 2018 to 2019 pair. The constants
it prints are frozen by hand into swar_lab.B1_K_AMENDED and
swar_lab.B1_AMENDED_FIT_LOG, once, before the look.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import swar_lab as L  # noqa: E402


def amended(log=print) -> dict:
    inputs = L.LabInputs()
    payload = inputs.preview()
    L.check_preview(payload, range(2016, 2020), inputs.vintage_id())
    L.check_amended_preview(payload)
    rows = L.season_rows(payload)
    consts = L.assemble(rows, inputs, range(2016, 2020), L.B1_AMENDED_SEASONS["peh"] + (2019,), log,
                        deltas=False)
    log(f"amended B1 fit; preview vintage {payload.get('fwar_vintage_id')}, generated "
        f"{payload.get('generated_at')}; inputs {json.dumps(inputs.input_meta(), sort_keys=True)}")
    log(f"floors: hitters {L.MIN_PA:g} PA, pitchers {L.MIN_IP:g} IP, in both seasons; catcher frame "
        f"300 innings at C in Y")
    out = {}
    for comp, seasons in L.B1_AMENDED_SEASONS.items():
        pairs = L.component_pairs(rows, comp, seasons, consts, with_tests=False)
        f = L.fit_b1_pairs(pairs)
        f["fit_seasons"] = list(seasons)
        f["exposure"] = L.COMPONENTS[comp]["n"]
        out[comp] = f
        log(f"  {comp:4s} pairs {f['n_pairs']:,}  players {f['n_players']:,}  r {f['r_raw']:.4f} "
            f"(clamped {f['r']:.4f})  hm {f['hm']:.1f} {f['exposure']}  k {f['k']:.0f} {f['exposure']}")
    log(json.dumps(out, sort_keys=True))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--amended", action="store_true", help="part 11.2.1's component constants")
    args = ap.parse_args(argv)
    if args.amended:
        amended()
        return 0
    inputs = L.LabInputs()
    payload = inputs.preview()
    L.check_preview(payload, range(2016, 2020), inputs.vintage_id())
    exp = L.exposure_rows(payload)
    print(f"B1 fit on predictor seasons {list(L.B1_FIT_SEASONS)} (outcomes "
          f"{L.B1_FIT_SEASONS[0] + 1} to {L.B1_FIT_SEASONS[-1] + 1}); preview vintage "
          f"{payload.get('fwar_vintage_id')}, generated {payload.get('generated_at')}")
    print(f"floors: hitters {L.MIN_PA:g} PA, pitchers {L.MIN_IP:g} IP, in both seasons")
    out = {}
    for side, unit in ((L.HIT, "PA"), (L.PIT, "IP")):
        f = L.fit_b1(exp, side)
        out[side] = f
        print(f"  {side}  pairs {f['n_pairs']:,}  players {f['n_players']:,}  r {f['r_raw']:.4f} "
              f"(clamped {f['r']:.4f})  hm {f['hm']:.1f} {unit}  k {f['k']:.0f} {unit}")
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
