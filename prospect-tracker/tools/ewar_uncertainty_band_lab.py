#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""ewar_uncertainty_band_lab - the eWAR uncertainty band read (EWAR_UNCERTAINTY_BAND).

docs/ewar-v3/EWAR_UNCERTAINTY_BAND_GATE.md, owner decision EW3-50. Reads, never fetches
and never writes a cache:
  data/fwar_vintage.json            fWAR per side, PA and outs (the frozen vintage)
  data/ewar_v3.json                 eWAR realized's R2 departures and the R2 rows
  war_source's Baseball-Reference copy   bWAR per side and the club clusters
  .cache/pbp_runners                plays 2011 to 2025 (batting halves) and eBR's credits
  .cache/ebr/frozen/ebr_v1_pool.json     eBR's frozen pool
  .cache/pbp_corpus                 plays with the pitcher, 2018 to 2025 (pitching halves)
  league_constants                  solved wOBA weights and FanGraphs' runs per win
  data/awards_eval.json             N1's constants (computed by awards_core.band_constants
                                    on the same inputs when the file does not carry them)

  python tools/ewar_uncertainty_band_lab.py --frame     the design census and refusals only
  python tools/ewar_uncertainty_band_lab.py --planted   gate part 6 on the real design (no statistic)
  python tools/ewar_uncertainty_band_lab.py --read      the one read: planted check, then the
                                                        cells; writes RECORD, refuses if it exists

Writes only data/_labs/ewar_uncertainty_band/record.json (--read; --out overrides it).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for p in (str(ROOT), str(TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

import ewar_uncertainty_band as U  # noqa: E402

CACHE = ROOT / ".cache"
RECORD = ROOT / "data" / "_labs" / "ewar_uncertainty_band" / "record.json"
EWAR_V3 = ROOT / "data" / "ewar_v3.json"
VINTAGE = ROOT / "data" / "fwar_vintage.json"
AWARDS_EVAL = ROOT / "data" / "awards_eval.json"
RUNNERS = CACHE / "pbp_runners"
CORPUS = CACHE / "pbp_corpus"
EBR_POOL = CACHE / "ebr" / "frozen" / "ebr_v1_pool.json"

C1_SEASONS = tuple(s for s in range(2000, 2026) if U.role(s))
C2_BAT_SEASONS = tuple(s for s in range(2011, 2026) if U.role(s))
C2_PIT_SEASONS = tuple(s for s in (2018, 2019, 2021, 2022, 2023, 2024, 2025) if U.role(s))
SERVED_SEASONS = tuple(range(2000, 2027))

WOBA_KEY = {"walk": "ubb", "hit_by_pitch": "hbp", "single": "1b", "double": "2b", "triple": "3b",
            "home_run": "hr"}
K_EVENTS = ("strikeout", "strikeout_double_play")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _sha(path: Path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


# ------------------------------------------------------------------ inputs
class Inputs:
    """Every input, one method each, so the dry run supplies fixtures."""

    def vintage(self) -> dict:
        import fwar_vintage
        if not fwar_vintage.available():
            raise U.BandRefusal("the frozen fWAR vintage is absent")
        return fwar_vintage.load()

    def ewar_v3(self) -> dict:
        if not EWAR_V3.exists():
            raise U.BandRefusal("data/ewar_v3.json is absent")
        return json.loads(EWAR_V3.read_text(encoding="utf-8"))

    def bwar(self, side: str):
        import war_source
        df = war_source._load_last_good(side)
        if df is None:
            raise U.BandRefusal(f"the bWAR copy ({side}) is absent")
        return df

    def woba(self, season: int):
        import league_constants
        blk = league_constants.load().get(int(season)) or {}
        w, sc = blk.get("woba_weights"), _num(blk.get("woba_scale"))
        if not w or not sc:
            raise U.BandRefusal(f"{season}: no solved wOBA weights")
        return w, sc

    def rpw(self, season: int) -> float:
        import league_constants
        lt = league_constants.league_totals(int(season))
        if not lt:
            raise U.BandRefusal(f"{season}: league_constants.league_totals returned nothing")
        return float(lt["rpw"])

    def runner_pa(self, season: int):
        import pandas as pd
        man = json.loads((RUNNERS / "manifest.json").read_text(encoding="utf-8"))
        blk = (man.get("seasons") or {}).get(str(season))
        if not blk:
            raise U.BandRefusal(f"{season}: the runner record carries no MLB season")
        return pd.read_parquet(RUNNERS / blk["files"]["pa"],
                               columns=["game_pk", "at_bat_index", "batter_id", "bat_team_id",
                                        "fld_team_id", "event_type", "is_pa"])

    def corpus_plays(self, season: int):
        import pandas as pd
        p = CORPUS / "plays" / str(season) / f"plays-{season}.parquet"
        if not p.exists():
            raise U.BandRefusal(f"{season}: the play corpus carries no season")
        return pd.read_parquet(p, columns=["game_pk", "at_bat_index", "pitcher_id", "event_type",
                                           "outs_before", "outs_after", "runs_scored_on_play"])

    def ebr_credits(self, season: int) -> list:
        """eBR's priced credits (mlbam, team, game_pk, part, runs) for one season."""
        import build_ebr
        import ebr
        pool = json.loads(EBR_POOL.read_text(encoding="utf-8"))
        ebr.check_frozen_pool(pool)
        data, _ = build_ebr.load_record(seasons=[int(season)])
        if int(season) not in data:
            raise U.BandRefusal(f"{season}: the runner record carries no MLB season")
        pa, rn = data[int(season)]
        table = ebr.shrunk_table(ebr.season_raw(pa), pool["re_pool"], float(pool["K"]), int(season))
        opps = ebr.xb_opportunities(pa, rn)
        ebr.finalize_opportunities(opps)
        credits, _, _ = ebr.season_credits(pa, rn, table, pool["xb_pool_counts"], opps=opps)
        return credits

    def n1_constants(self, bat_df, pit_df) -> dict:
        """N1: the Awards band's constants as served, else computed the exporter's way."""
        try:
            ev = json.loads(AWARDS_EVAL.read_text(encoding="utf-8"))
            band = ((ev.get("realized_read_band") or {}).get("band")) or None
        except (OSError, ValueError):
            band = None
        if band and (band.get("bat") or {}).get("k") and (band.get("pit") or {}).get("k"):
            return {"bat": float(band["bat"]["k"]), "pit": float(band["pit"]["k"]),
                    "source": "data/awards_eval.json realized_read_band.band"}
        import awards_core as A
        import awards_export as AE
        stints = {}
        for side, df in (("bat", bat_df), ("pit", pit_df)):
            sub = df[df["year_ID"].isin(sorted(A.BAND_SEASONS))]
            cols = ["year_ID", "mlb_ID", "PA" if side == "bat" else "IPouts", "WAR"]
            stints[side] = [{"year_ID": r[0], "mlb_ID": r[1], cols[2]: r[2], "WAR_bwar": r[3]}
                            for r in sub[cols].itertuples(index=False)]
        k = A.band_constants(stints, AE._fwar_targets())
        return {"bat": float(k["bat"]["k"]), "pit": float(k["pit"]["k"]),
                "n_bat": k["bat"]["n"], "n_pit": k["pit"]["n"],
                "source": ("awards_core.band_constants on the bWAR copy and the frozen vintage "
                           "(data/awards_eval.json carries no realized_read_band)")}

    def meta(self) -> dict:
        import war_source
        return {"fwar_vintage_sha256": _sha(VINTAGE), "ewar_v3_sha256": _sha(EWAR_V3),
                "bwar_bat_sha256": _sha(war_source._cache_path("bat")),
                "bwar_pit_sha256": _sha(war_source._cache_path("pit")),
                "runner_manifest_sha256": _sha(RUNNERS / "manifest.json"),
                "corpus_manifest_sha256": _sha(CORPUS / "manifest.json"),
                "ebr_pool_sha256": _sha(EBR_POOL), "awards_eval_sha256": _sha(AWARDS_EVAL)}


def _fold(t) -> str:
    import ewar
    return ewar._fold_team(t)


class Clubs:
    """String club keys to integer cluster codes."""

    def __init__(self):
        self.codes: dict = {}

    def __call__(self, key: str) -> int:
        return self.codes.setdefault(str(key), len(self.codes))


# ------------------------------------------------------------------- frame
def bwar_index(inp: Inputs):
    """{side: {(season, mlbam): (bWAR sum or None, primary franchise)}} and the frames."""
    out = {"bat": {}, "pit": {}}
    frames = {}
    for side, ecol in (("bat", "PA"), ("pit", "IPouts")):
        df = inp.bwar(side)
        frames[side] = df
        agg = defaultdict(lambda: [0.0, False, defaultdict(float)])
        for r in df[["mlb_ID", "year_ID", "team_ID", ecol, "WAR"]].itertuples(index=False):
            m, y = _num(r[0]), _num(r[1])
            if m is None or y is None or int(y) < 2000:
                continue
            a = agg[(int(y), int(m))]
            w = _num(r[4])
            if w is not None:
                a[0] += w
                a[1] = True
            a[2][_fold(r[2])] += _num(r[3]) or 0.0
        for key, (w, has, clubs) in agg.items():
            prim = max(sorted(clubs), key=lambda c: clubs[c]) if clubs else None
            out[side][key] = (w if has else None, prim)
    return out, frames


def _vintage_side(vint: dict, season: int, side: str) -> dict:
    """{mlbam: (war, exposure)}: PA (hitting) or outs / 3 (pitching)."""
    grp = "hitting" if side == "bat" else "pitching"
    g = ((vint.get("seasons") or {}).get(str(season)) or {}).get(grp) or {}
    fields = list((vint.get("fields") or {}).get(grp) or [])
    iw = fields.index("war")
    ie = fields.index("plateAppearances") if side == "bat" else fields.index("outs")
    out = {}
    for mid, vals in (g.get("rows") or {}).items():
        if vals is None:
            continue
        war = _num(vals[iw]) if len(vals) > iw else None
        e = _num(vals[ie]) if len(vals) > ie else None
        if e is not None and side == "pit":
            e = e / 3.0
        out[int(mid)] = (war, e)
    return out


def _realized_rows(ev3: dict) -> tuple[dict, set]:
    """({(season, mlbam): R2 departure, pitching}, {(season, mlbam) carrying R2})."""
    dr, r2 = {}, set()
    for mid, by_s in (ev3.get("players") or {}).items():
        for s, rec in (by_s or {}).items():
            rec = rec or {}
            v = _num(((rec.get("dr") or {}).get("pit")))
            if v is not None:
                dr[(int(s), int(mid))] = v
            if "r2" in (rec.get("parts") or {}):
                r2.add((int(s), int(mid)))
    return dr, r2


def build_c1(inp: Inputs, vint: dict, bidx: dict, dr: dict, clubs: Clubs, with_values: bool) -> dict:
    fams = {}
    for side in ("bat", "pit"):
        rows = defaultdict(list)
        for s in C1_SEASONS:
            for mid, (war, e) in _vintage_side(vint, s, side).items():
                if war is None or e is None:
                    continue
                b = U.band_index(side, e)
                if b is None:
                    continue
                bw = bidx[side].get((s, mid))
                if bw is None or bw[0] is None:
                    continue
                D, g, sc = U.c1_row(war - bw[0], e)
                rows["season"].append(s)
                rows["band"].append(b)
                rows["g"].append(g)
                rows["s"].append(sc)
                rows["player"].append(mid)
                rows["club"].append(clubs(bw[1]))
                rows["D"].append(D)
                rows["dr"].append(dr.get((s, mid), 0.0) if side == "pit" else 0.0)
        name = f"C1-{side}"
        fams[name] = U.Family(name, rows["season"], rows["band"], rows["g"], rows["s"], rows["player"],
                              rows["club"], D=(rows["D"] if with_values else None),
                              meta={"dr": np.array(rows["dr"]) if with_values else None})
    return fams


def _halves_bat(pa, woba=None):
    """{(mlbam, parity): [PA, sum v]} and {mlbam: most frequent bat team} from one season's plays."""
    sub = pa[pa["is_pa"].astype(bool)]
    out = defaultdict(lambda: [0.0, 0.0])
    team = defaultdict(lambda: defaultdict(int))
    w, sc = woba if woba else (None, None)
    for gpk, bid, tid, ev in sub[["game_pk", "batter_id", "bat_team_id", "event_type"]].itertuples(index=False):
        if bid is None or bid != bid:
            continue
        key = (int(bid), int(gpk) % 2)
        out[key][0] += 1.0
        if w is not None:
            k = WOBA_KEY.get(ev)
            if k is not None:
                out[key][1] += float(w[k]) / sc
        if tid is not None and tid == tid:
            team[int(bid)][int(tid)] += 1
    return out, {m: max(sorted(t), key=lambda x: t[x]) for m, t in team.items()}


def _halves_pit(plays, with_values: bool):
    """{(pitcher, parity): [IP, fip numerator, runs]} from one season's corpus plays."""
    out = defaultdict(lambda: [0.0, 0.0, 0.0])
    cols = ["game_pk", "pitcher_id", "event_type", "outs_before", "outs_after", "runs_scored_on_play"]
    for gpk, pid, ev, ob, oa, runs in plays[cols].itertuples(index=False):
        if pid is None or pid != pid:
            continue
        key = (int(pid), int(gpk) % 2)
        out[key][0] += max(int(oa) - int(ob), 0) / 3.0
        if with_values:
            if ev == "home_run":
                out[key][1] += 13.0
            elif ev in ("walk", "intent_walk", "hit_by_pitch"):
                out[key][1] += 3.0
            elif ev in K_EVENTS:
                out[key][1] -= 2.0
            out[key][2] += float(runs or 0)
    return out


def _pitcher_teams(pa, plays) -> dict:
    """{pitcher: most frequent fielding team id} by joining the corpus to the runner record."""
    ft = {(int(g), int(a)): int(t) for g, a, t in pa[["game_pk", "at_bat_index", "fld_team_id"]].itertuples(index=False)
          if t is not None and t == t}
    team = defaultdict(lambda: defaultdict(int))
    for g, a, pid in plays[["game_pk", "at_bat_index", "pitcher_id"]].itertuples(index=False):
        t = ft.get((int(g), int(a)))
        if t is not None and pid is not None and pid == pid:
            team[int(pid)][t] += 1
    return {m: max(sorted(t), key=lambda x: t[x]) for m, t in team.items()}


def _club_key(bidx, side, s, mid, fallback):
    bw = bidx[side].get((s, mid))
    if bw is not None and bw[1]:
        return bw[1]
    return f"pbp:{fallback}" if fallback is not None else "pbp:none"


def build_c2(inp: Inputs, bidx: dict, clubs: Clubs, with_values: bool, log=print) -> dict:
    cols = {n: defaultdict(list) for n in ("C2-bat", "C2-ebr", "C2-fip", "C2-ra")}

    def add(name, s, b, g, sc, mid, club, D, xa, xb):
        c = cols[name]
        for k, v in (("season", s), ("band", b), ("g", g), ("s", sc), ("player", mid), ("club", club),
                     ("D", D), ("xa", xa), ("xb", xb)):
            c[k].append(v)

    for s in C2_BAT_SEASONS:
        t0 = time.time()
        pa = inp.runner_pa(s)
        halves, team = _halves_bat(pa, inp.woba(s) if with_values else None)
        ebr_h = defaultdict(float)
        if with_values:
            for mid, _, g, _, v in inp.ebr_credits(s):
                if mid is not None:
                    ebr_h[(int(mid), int(g) % 2)] += float(v)
        for mid in sorted({m for m, _ in halves}):
            a, bb = halves.get((mid, 1)), halves.get((mid, 0))
            if not a or not bb or a[0] <= 0 or bb[0] <= 0:
                continue
            band = U.band_index("bat", a[0] + bb[0])
            if band is None:
                continue
            club = clubs(_club_key(bidx, "bat", s, mid, team.get(mid)))
            for name, va, vb in (("C2-bat", a[1], bb[1]), ("C2-ebr", ebr_h[(mid, 1)], ebr_h[(mid, 0)])):
                xa = va / a[0] if with_values else None
                xb = vb / bb[0] if with_values else None
                D, g, sc = U.c2_row(xa, xb, a[0], bb[0])
                add(name, s, band, g, sc, mid, club, D, xa, xb)
        log(f"  C2 batting halves {s}: {len(halves)} player-halves ({time.time() - t0:.1f} s)")

    for s in C2_PIT_SEASONS:
        plays = inp.corpus_plays(s)
        halves = _halves_pit(plays, with_values)
        team = _pitcher_teams(inp.runner_pa(s), plays)
        for mid in sorted({m for m, _ in halves}):
            a, bb = halves.get((mid, 1)), halves.get((mid, 0))
            if not a or not bb or a[0] <= 0 or bb[0] <= 0:
                continue
            band = U.band_index("pit", a[0] + bb[0])
            if band is None:
                continue
            club = clubs(_club_key(bidx, "pit", s, mid, team.get(mid)))
            for name, j in (("C2-fip", 1), ("C2-ra", 2)):
                xa = -a[j] / (9.0 * a[0] if j == 1 else a[0]) if with_values else None
                xb = -bb[j] / (9.0 * bb[0] if j == 1 else bb[0]) if with_values else None
                D, g, sc = U.c2_row(xa, xb, a[0], bb[0])
                add(name, s, band, g, sc, mid, club, D, xa, xb)
        log(f"  C2 pitching halves {s}: {len(halves)} pitcher-halves")

    fams = {}
    for name, c in cols.items():
        fams[name] = U.Family(name, c["season"], c["band"], c["g"], c["s"], c["player"], c["club"],
                              D=(c["D"] if with_values else None),
                              meta={"xa": np.array(c["xa"], float) if with_values else None,
                                    "xb": np.array(c["xb"], float) if with_values else None,
                                    "e": np.sqrt(np.array(c["s"], float))})
    return fams


def build_frame(inp: Inputs, *, with_values: bool, log=print) -> dict:
    """The six families of gate part 5 (D is None when with_values is False) and refusals 1, 2, 5."""
    vint = inp.vintage()
    ev3 = inp.ewar_v3()
    if str(ev3.get("fwar_vintage_id") or "") != str(vint.get("vintage_id") or ""):
        raise U.BandRefusal(f"data/ewar_v3.json is on vintage {ev3.get('fwar_vintage_id')}, "
                            f"not {vint.get('vintage_id')}")
    bidx, frames = bwar_index(inp)
    dr, r2 = _realized_rows(ev3)
    clubs = Clubs()
    fams = build_c1(inp, vint, bidx, dr, clubs, with_values)
    fams.update(build_c2(inp, bidx, clubs, with_values, log=log))
    n1 = inp.n1_constants(frames["bat"], frames["pit"]) if with_values else {"bat": 1.0, "pit": 1.0,
                                                                              "source": "design only"}
    fams["C1-bat"].n1_k = n1["bat"]
    fams["C1-pit"].n1_k = n1["pit"]
    census = check_frame(fams)
    return {"families": fams, "census": census, "n1": n1, "vint": vint, "ev3": ev3, "r2": r2,
            "clubs": clubs.codes}


def check_frame(fams: dict) -> dict:
    """Refusal 2 and the census: every role's seasons carry rows, every cell its minimum."""
    census = {}
    for name, fam in fams.items():
        blk = {"rows": int(len(fam.season)), "by_role": {}, "cells": {}}
        for r in ("FIT", "CAL", "TEST"):
            m = fam.role == r
            blk["by_role"][r] = {"rows": int(m.sum()), "seasons": sorted({int(x) for x in fam.season[m]})}
            if not m.any():
                raise U.BandRefusal(f"{name}: no {r} rows")
        for b in range(4):
            nt = int(((fam.role == "TEST") & (fam.band == b)).sum())
            nc = int(((fam.role == "CAL") & (fam.band == b)).sum())
            blk["cells"][U.BAND_LABELS[fam.side][b]] = {"test": nt, "cal": nc}
            if nt < U.MIN_TEST_ROWS or nc < U.MIN_CAL_ROWS:
                raise U.BandRefusal(f"{name} {U.BAND_LABELS[fam.side][b]}: {nt} TEST and {nc} CAL rows")
        census[name] = blk
    return census


# ------------------------------------------------------------------ part 8
def reliability(fams: dict) -> dict:
    out = {}
    for name in ("C2-bat", "C2-ebr", "C2-fip", "C2-ra"):
        fam = fams[name]
        xa, xb, e = fam.meta["xa"], fam.meta["xb"], fam.meta["e"]
        floor = 300.0 if fam.side == "bat" else 60.0
        per = {}
        for s in sorted({int(x) for x in fam.season[fam.role == "FIT"]}):
            m = (fam.season == s) & (e >= floor)
            if m.sum() < 10:
                continue
            r = float(np.corrcoef(xa[m], xb[m])[0, 1])
            per[str(s)] = {"n": int(m.sum()), "r": round(r, 4), "spearman_brown": round(2 * r / (1 + r), 4)}
        out[name] = per
    return out


def realized_c1(fam: U.Family, fit: dict) -> list:
    """C1 on eWAR realized's pitching side, TEST rows from 2016 (reported)."""
    t = (fam.role == "TEST") & (fam.season >= 2016)
    D = fam.D[t] + fam.meta["dr"][t]
    sd = np.sqrt(fit["k"] * fam.g[t])
    m = np.array([fit["multipliers"][int(b)]["m"] for b in fam.band[t]])
    cov = np.abs(D) <= U.Z80 * m * sd
    return [{"band": U.BAND_LABELS["pit"][b], "n": int((fam.band[t] == b).sum()),
             "coverage": float(cov[fam.band[t] == b].mean()) if (fam.band[t] == b).any() else None}
            for b in range(4)]


def served_census(inp: Inputs, frame: dict, consts: dict) -> dict:
    """Part 8: the served band's median half-width per side band and series, and counts."""
    vint, r2 = frame["vint"], frame["r2"]
    widths = defaultdict(list)
    counts = {}
    shares = defaultdict(list)
    for s in SERVED_SEASONS:
        rpw = inp.rpw(s)
        bat = _vintage_side(vint, s, "bat")
        pit = _vintage_side(vint, s, "pit")
        n = {"rows": 0, "bat": 0, "pit": 0}
        for mid in sorted(set(bat) | set(pit)):
            pa = bat.get(mid, (None, None))[1]
            ip = pit.get(mid, (None, None))[1]
            for series in ("headline", "realized"):
                basis = "ra" if (series == "realized" and (s, mid) in r2) else "fip"
                sg = U.sigma(consts, pa=pa, ip=ip, rpw=rpw, pit_basis=basis)
                if sg is None:
                    continue
                if series == "headline":
                    n["rows"] += 1
                    n["bat"] += int(U.band_index("bat", pa) is not None) if pa is not None else 0
                    n["pit"] += int(U.band_index("pit", ip) is not None) if ip is not None else 0
                main = "pit" if (ip is not None and U.band_index("pit", ip) is not None
                                 and (pa is None or U.band_index("bat", pa) is None)) else "bat"
                b = U.band_index(main, pa if main == "bat" else ip)
                widths[(series, main, b)].append(U.Z80 * sg["sigma"])
                if series == "headline":
                    shares[(main, b)].append(sg["samp"] ** 2 / max(sg["sigma"] ** 2, 1e-12))
        counts[str(s)] = n
    med = {}
    for (series, side, b), v in sorted(widths.items()):
        med.setdefault(series, {})[U.BAND_LABELS[side][b]] = {"n": len(v), "median_half_width": round(float(np.median(v)), 3)}
    sh = {U.BAND_LABELS[side][b]: round(float(np.median(v)), 3) for (side, b), v in sorted(shares.items())}
    return {"median_half_width_wins": med, "median_sampling_share_of_variance": sh, "counts": counts}


# ------------------------------------------------------------------ driver
class Reporter:
    def __init__(self):
        self.lines = []

    def say(self, s: str = "") -> None:
        print(s, flush=True)
        self.lines.append(s)


def _f(x, nd=3):
    return "nan" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.{nd}f}"


def run_planted(inp: Inputs, rep: Reporter, *, n_rep=U.N_PLANTED, n_boot=U.B_PLANTED) -> dict:
    rep.say("PLANTED CHECK (gate part 6): real design, synthetic statistics")
    frame = build_frame(inp, with_values=False, log=rep.say)
    for name, blk in frame["census"].items():
        rep.say(f"  {name}: {blk['rows']} rows; " + ", ".join(
            f"{r} {v['rows']}" for r, v in blk["by_role"].items()))
    t0 = time.time()
    pl = U.planted(frame["families"], n_rep=n_rep, n_boot=n_boot, log=rep.say)
    rep.say(f"  truth PASS in {pl['truth_pass']} of {n_rep}; broken PASS in {pl['broken_pass']} of {n_rep};"
            f" -> {'PLANTED PASS' if pl['planted_pass'] else 'PLANTED FAIL'} ({time.time() - t0:.0f} s)")
    fam = next(iter(frame["families"].values()))
    pl["identity_check"] = U.identity_check(fam.with_D(np.ones(len(fam.g))))
    rep.say(f"  identity check: d = 0 exactly: {pl['identity_check']}")
    pl["census"] = frame["census"]
    return pl


def run_read(inp: Inputs, rep: Reporter, *, n_boot=U.B, planted_reps=U.N_PLANTED,
             planted_boot=U.B_PLANTED) -> dict:
    t_start = time.time()
    pl = run_planted(inp, rep, n_rep=planted_reps, n_boot=planted_boot)
    rep.say("")
    rep.say("THE READ (gate parts 3 to 8)")
    frame = build_frame(inp, with_values=True, log=rep.say)
    fams = frame["families"]
    for name, fam in fams.items():
        k = U.fit_k(fam)
        if not (math.isfinite(k) and k > 0):
            raise U.BandRefusal(f"{name}: k {k} is not finite and positive")
    rep.say(f"N1 constants: k_bat {frame['n1']['bat']:.6f}, k_pit {frame['n1']['pit']:.6f} ({frame['n1']['source']})")
    res = U.score(fams, n_rep=n_boot)
    rep.say("")
    rep.say("CONSTANTS AND MULTIPLIERS (training seasons, FIT and CAL; amendment 13.1)")
    for name, blk in res["families"].items():
        mm = ", ".join(f"{U.BAND_LABELS[fams[name].side][b]}: raw {_f(v['raw_coverage'])}"
                       f" m {_f(v['m'])}"
                       for b, v in blk["multipliers"].items())
        rep.say(f"  {name}: k {blk['k']:.6g}; {mm}")
    rep.say("")
    rep.say("CELLS (TEST coverage of the final band; 5th to 95th percentile per bootstrap)")
    for c in res["cells"]:
        iv = c["interval"]
        rep.say(f"  {c['family']:7s} {c['label']:12s} n {c['n_test']:5d}  coverage {_f(c['coverage'])}"
                f" (raw {_f(c['raw_coverage'])}, N1 {_f(c['n1_coverage'])}, N0 {_f(c['n0_coverage'])})"
                f"  player [{_f(iv['player'][0])}, {_f(iv['player'][1])}]"
                f"  club [{_f(iv['club'][0])}, {_f(iv['club'][1])}]  {'inside' if c['inside'] else 'OUT'}")
    rep.say("")
    rep.say("INTERVAL SCORE: d(N) = mean IS(N) - mean IS(candidate); lo = d - 1.645 sd")
    for name, blk in res["families"].items():
        for null, cmp_ in blk["comparisons"].items():
            pb = cmp_["by_bootstrap"]
            rep.say(f"  {name:7s} vs {null.upper()}: d {cmp_['d']:.5g}; sd player {pb['player']['sd']:.3g}"
                    f" club {pb['club']['sd']:.3g}; lo player {pb['player']['lo']:.5g} club {pb['club']['lo']:.5g}"
                    f"  {'WIN' if cmp_['win'] else 'not'}{'' if cmp_['deciding'] else ' (reported)'}")
    disp = U.disposition(res, pl["planted_pass"])
    rep.say("")
    rep.say(f"CALIBRATED: {res['calibrated']}; SHARPER THAN THE NULLS: {res['sharper']}; "
            f"PLANTED PASS: {pl['planted_pass']}")
    if res["failing_cells"]:
        rep.say(f"cells outside [{U.EQUIV[0]}, {U.EQUIV[1]}]: {', '.join(res['failing_cells'])}")
    rep.say(f"VERDICT: {disp}")
    rep.say("")
    rep.say("REPORTED (part 8)")
    rel = reliability(fams)
    for name, per in rel.items():
        rep.say(f"  split-half {name}: " + "; ".join(f"{s} n {v['n']} r {v['r']} SB {v['spearman_brown']}"
                                                   for s, v in per.items()))
    fit_pit = {"k": res["families"]["C1-pit"]["k"], "multipliers": res["families"]["C1-pit"]["multipliers"]}
    rc = realized_c1(fams["C1-pit"], fit_pit)
    rep.say("  C1 on eWAR realized's pitching side (TEST 2018, 2021, 2024): " + "; ".join(
        f"{r['band']} n {r['n']} coverage {_f(r['coverage'])}" for r in rc))
    consts = U.constants_from(res)
    sc = served_census(inp, frame, consts)
    for series, blk in sc["median_half_width_wins"].items():
        rep.say(f"  served median half-width ({series}): " + "; ".join(
            f"{b} {v['median_half_width']} (n {v['n']})" for b, v in blk.items()))
    rep.say("  median sampling share of the variance (headline): " + "; ".join(
        f"{b} {v}" for b, v in sc["median_sampling_share_of_variance"].items()))
    record = {"schema": 1, "task": "EWAR_UNCERTAINTY_BAND", "gate": U.GATE_DOC, "generated_at": _now(),
              "inputs": inp.meta(), "seed": U.SEED, "B": n_boot, "z80": U.Z80,
              "equivalence": list(U.EQUIV), "train_roles": list(U.TRAIN_ROLES), "amendment": "13.1",
              "census": frame["census"], "n1": frame["n1"],
              "planted": {k: v for k, v in pl.items() if k != "census"},
              "families": res["families"], "cells": res["cells"], "calibrated": res["calibrated"],
              "sharper": res["sharper"], "failing_cells": res["failing_cells"], "disposition": disp,
              "constants": consts,
              "reported": {"reliability": rel, "c1_realized_pit": rc, "served": sc},
              "runtime_seconds": round(time.time() - t_start, 1)}
    return record


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating,)):
        o = float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, float):
        return round(o, 6) if math.isfinite(o) else None
    return o


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--frame", action="store_true")
    g.add_argument("--planted", action="store_true")
    g.add_argument("--read", action="store_true")
    ap.add_argument("--out", default=str(RECORD))
    a = ap.parse_args(argv)
    rep = Reporter()
    inp = Inputs()
    if a.frame:
        frame = build_frame(inp, with_values=False, log=rep.say)
        print(json.dumps(frame["census"], indent=1))
        return 0
    if a.planted:
        pl = run_planted(inp, rep)
        return 0 if pl["planted_pass"] else 1
    out = Path(a.out)
    if out.exists():
        print(f"refused: {out} exists; the read runs once (gate part 11)")
        return 2
    record = run_read(inp, rep)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(_jsonable(record), indent=1, sort_keys=True) + "\n", encoding="utf-8",
                   newline="\n")
    rep.say(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
