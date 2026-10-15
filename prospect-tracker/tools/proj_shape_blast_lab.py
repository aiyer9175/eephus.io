# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""GATE 0.1 of docs/PROJ_PATH_SHAPE_GATE.md: the blast-radius bound.

Fits nothing. Reshapes the SERVED veteran `war` paths of data/mlb_projections.json
at the extremes of what a smoothness penalty can do, reprices each row's surplus
through the served salary path, and reports how far a pure SHAPE change can move
surNpv and surTotal and the trade-board order:

  IDENTITY   the served `war` path, as it ships
  MAXSMOOTH  the row's `warChamp` path rescaled to the served 5-year `war` total
  RAMP       a straight line with the served path's end-to-end slope
             (war[4] - war[0]) / 4, shifted to preserve the 5-year total

Repricing (section 0a): each season priced on the served `salPath` dollars at
proj_export._season_value_usd, the club option floor (salary_path
.club_option_floor), the tender cliff (salary_path.apply_cliff, mode full) and the
platform rate; the contract tail past 2031 chained from the reshaped 2031 value by
fa_market.chain_aging_tail on the row's champion path (warChamp + warChampTail),
which is the served seam. The rest-of-season leg (surTotal - surNpv) is held at
its served value: a reshape of the 2027-2031 path does not reach the season being
sold, and that is a default named in the artifact. IDENTITY is repriced by the
same function, every move is (reshape - identity) on that function, and the
function's reproduction of the served surNpv is published beside the result.

Run: python tools/proj_shape_blast_lab.py [--out data/proj_shape_blast.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SERVED = ROOT / "data" / "mlb_projections.json"
OUT = ROOT / "data" / "proj_shape_blast.json"
SPEARMAN_DEMOTE = 0.9990          # section 0a consequence 1
HORIZON = 5


def _spearman(a: list[float], b: list[float]) -> float:
    def ranks(x):
        order = sorted(range(len(x)), key=lambda i: x[i])
        r = [0.0] * len(x)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
                j += 1
            avg = (i + j) / 2.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else 1.0


def reshape(row: dict, how: str) -> list[float] | None:
    war = [float(w) for w in row["war"][:HORIZON]]
    if how == "identity":
        return war
    tot = sum(war)
    if how == "maxsmooth":
        ch = [float(w) for w in (row.get("warChamp") or [])[:HORIZON]]
        if len(ch) < HORIZON or abs(sum(ch)) < 1e-9:
            return None
        k = tot / sum(ch)
        return [round(c * k, 2) for c in ch]
    if how == "ramp":
        b = (war[4] - war[0]) / 4.0
        c = tot / 5.0 - 2.0 * b
        return [round(c + b * t, 2) for t in range(HORIZON)]
    raise ValueError(how)


class Repricer:
    """The served legacy pricing (value_framework.dpw_path_active() False),
    re-run per row on a supplied 5-season WAR path."""

    def __init__(self, payload: dict):
        import fa_market as fm
        import proj_export as pe
        import salary_path as sp
        import value_framework as vf
        if vf.dpw_path_active():
            raise SystemExit("unified $/WAR path mode is active; this repricer "
                             "implements the legacy branch only")
        self.fm, self.pe, self.sp = fm, pe, sp
        self.dpw = float(payload["dpw_usd"])
        self.r = float(vf._config()["discount_rate"])
        self.first = int(payload["first_season"])
        self.mode = sp.SALARY_PATH_MODE

    def price(self, row: dict, war5: list[float],
              served_tail: bool = False) -> tuple[int, int]:
        sal = row.get("salPath") or []
        opts = {int(s): o for s, o in (row.get("salOpt") or [])}
        last = max(int(e[0]) for e in sal)
        n = last - self.first + 1
        seasons = [{"t": t, "season": self.first + t, "usd": None, "lo": None,
                    "hi": None, "tok": None, "src": None, "cut": False,
                    "opt": opts.get(self.first + t)} for t in range(n)]
        for e in sal:
            t = int(e[0]) - self.first
            seasons[t].update(usd=e[1], lo=e[2], hi=e[3], tok=e[4], src=e[5])
        war_px = list(war5)
        if n > HORIZON:
            champ_full = [float(c) for c in (row.get("warChamp") or [])[:HORIZON]] + \
                         [float(c) for c in (row.get("warChampTail") or [])]
            full = self.fm.chain_aging_tail(list(war5), champ_full, HORIZON,
                                            len(champ_full))
            war_px = list(war5) + [float(w) for w in full[HORIZON:]]
            if served_tail and row.get("warTail"):
                tail = [c for c in seasons[HORIZON:]]
                for c, w in zip(tail, row["warTail"]):
                    if w is not None and c["t"] < len(war_px):
                        war_px[c["t"]] = float(w)
        d_usd = []
        for c in seasons:
            if c["usd"] is None:
                d_usd.append(None)
                continue
            w = war_px[c["t"]] if c["t"] < len(war_px) else None
            d_usd.append(self.pe._season_value_usd(w or 0.0, c["t"], self.dpw) - c["usd"])
        d_usd, _dec = self.sp.club_option_floor(seasons, d_usd)
        any_priced = any(x is not None for x in d_usd)
        npv = sum(d / ((1 + self.r) ** t) for t, d in enumerate(d_usd) if d is not None)
        if self.mode == "full" and any_priced:
            npv, _cut = self.sp.apply_cliff({"seasons": seasons}, d_usd, self.r)
        ros = int(row.get("surTotal") or 0) - int(row.get("surNpv") or 0)
        return int(npv), int(ros + npv)


def run(out_path: Path = OUT) -> dict:
    t0 = time.time()
    raw = SERVED.read_bytes()
    payload = json.loads(raw)
    rows = [m for m in payload["vets"] if m.get("surNpv") is not None
            and m.get("salPath") and len(m.get("war") or []) >= HORIZON]
    rp = Repricer(payload)
    ident = {}
    repro_exact = repro_1k = 0
    repro_err = []
    for m in rows:
        ident[m["key"]] = rp.price(m, reshape(m, "identity"))
        npv, _tot = rp.price(m, reshape(m, "identity"), served_tail=True)
        err = abs(npv - int(m["surNpv"]))
        repro_err.append(err)
        repro_exact += err <= 1
        repro_1k += err <= 1000
    out_rs = {}
    for how in ("identity", "maxsmooth", "ramp"):
        mv_npv, mv_tot, rel, pre_t, post_t, skipped = [], [], [], [], [], 0
        for m in rows:
            w = reshape(m, how)
            if w is None:
                skipped += 1
                w = reshape(m, "identity")
            npv, tot = rp.price(m, w)
            n0, t0_ = ident[m["key"]]
            mv_npv.append(abs(npv - n0))
            mv_tot.append(abs(tot - t0_))
            if abs(t0_) >= 1e6:
                rel.append(abs(tot - t0_) / abs(t0_))
            pre_t.append(t0_)
            post_t.append(tot)
        out_rs[how] = {
            "n_rows": len(rows), "rows_without_reshape_kept_identity": skipped,
            "surNpv_abs_move_usd": {"mean": round(statistics.mean(mv_npv)),
                                    "median": round(statistics.median(mv_npv)),
                                    "max": max(mv_npv)},
            "surTotal_abs_move_usd": {"mean": round(statistics.mean(mv_tot)),
                                      "median": round(statistics.median(mv_tot)),
                                      "max": max(mv_tot)},
            "surTotal_mean_relative_move": round(statistics.mean(rel), 4) if rel else None,
            "n_rows_relative_basis": len(rel),
            "spearman_surTotal_pre_post": round(_spearman(pre_t, post_t), 6),
        }
    worst = min(out_rs[h]["spearman_surTotal_pre_post"] for h in ("maxsmooth", "ramp"))
    res = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gate": "docs/PROJ_PATH_SHAPE_GATE.md section 0a (GATE 0.1), produced under "
                "amendment A-2 23.2 (f) after the fWAR epoch's step Z entry",
        "read": "OWNER-WAIVED EARLY READ (owner EW3-5, 2026-10-14): the registered "
                "2026-09-25 date was missed under A-2 and the artifact is produced "
                "now, on the served payload of this day",
        "producer": "tools/proj_shape_blast_lab.py",
        "fits_anything": False,
        "served_artifact": {"path": "data/mlb_projections.json",
                            "generated_at": payload.get("generated_at"),
                            "sha256": hashlib.sha256(raw).hexdigest(),
                            "first_season": payload.get("first_season"),
                            "n_vets": payload.get("n_vets"),
                            "dpw_usd": payload.get("dpw_usd")},
        "pool": ("veteran rows carrying surNpv and a salary path with a five-season "
                 "`war` (registered at 895 on 2026-09-18; recounted here)"),
        "n_pool": len(rows),
        "repricer": {
            "method": ("served legacy pricing per row: proj_export._season_value_usd on "
                       "the served salPath dollars, salary_path.club_option_floor, "
                       "salary_path.apply_cliff (mode %s), rate %.3f; contract tail "
                       "chained by fa_market.chain_aging_tail on warChamp + "
                       "warChampTail" % (rp.mode, rp.r)),
            "default_ros_held": ("the rest-of-season leg (surTotal - surNpv) is held at "
                                 "its served value under every reshape"),
            "identity_reproduces_served_surNpv": {
                "within_1_usd": repro_exact, "within_1000_usd": repro_1k,
                "n": len(rows), "max_abs_error_usd": max(repro_err),
                "median_abs_error_usd": statistics.median(repro_err)},
            "identity_reproduction_reads": ("the served warTail for the seasons past "
                                            "2031; every reshape (IDENTITY included) "
                                            "re-chains its tail from its own 2031 "
                                            "value, which is the seam a refit would move"),
            "moves_are": "reshape minus IDENTITY, both on this repricer with the tail re-chained",
        },
        "reshapes": {
            "identity": "the served `war` path",
            "maxsmooth": "warChamp rescaled to the served 5-year `war` total",
            "ramp": ("straight line with slope (war[4]-war[0])/4, shifted so the "
                     "5-year total is preserved (both endpoints cannot be kept and "
                     "the total preserved at once; the slope and total are kept)"),
        },
        "results": out_rs,
        "spearman_demotion_threshold": SPEARMAN_DEMOTE,
        "reordering_criterion": (
            "DEMOTED to a regression guard: Spearman(pre, post) over surTotal is at or "
            "above 0.9990 under both extreme reshapes, so an unchanged order cannot "
            "discriminate and is not evidence for the refit"
            if worst >= SPEARMAN_DEMOTE else
            "NOT demoted: an extreme reshape reorders surTotal below Spearman 0.9990, "
            "so the order is recorded beside any flip (9.1 records it, gates nothing)"),
        "reading": [
            "This is a SHAPE-ONLY bound and says nothing about the level. A refit moves "
            "the level too; the level move is bounded by S3 (4.8) and by the dollar "
            "bands in section 9, not by this artifact.",
            "Landing inside every band is not evidence that an arm worked.",
        ],
        "wall_time_s": round(time.time() - t0, 1),
    }
    out_path.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    r = run(Path(a.out))
    print(json.dumps({k: r[k] for k in ("n_pool", "repricer", "results",
                                        "reordering_criterion")}, indent=1))
