#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""ewar_team_accounting_lab - the eWAR team accounting read (EWAR_TEAM_ACCOUNTING).

docs/ewar-v3/EWAR_TEAM_ACCOUNTING_GATE.md, owner decision EW3-50. Reads, never
fetches and never writes a cache:
  data/fwar_vintage.json                     fWAR (F), the frozen vintage
  data/ewar_v3.json                          eWAR realized (E, the `dr` departures)
                                             and the headline (H, `dh`)
  .cache/ewar_v3/preview/ewar_v3_xhem.json   the headline with the dark xHEM+ part (Hx)
  war_source's Baseball-Reference copy       bWAR (B) and the club allocation
  .cache/statsapi_standings_<Y>.json         wins, losses, runs (ewar.standings)
  league_constants.league_totals(Y)          FanGraphs' runs per win
  .cache/fangraphs/park_factors_<Y>.json     part 8's park factor
  .cache/team_stats/<Y>_pit.json             part 8's defensive efficiency

  python tools/ewar_team_accounting_lab.py --frame     the frame census and refusals only
  python tools/ewar_team_accounting_lab.py --planted   gate part 6 on the real design (no outcome)
  python tools/ewar_team_accounting_lab.py --read      the one read: planted check, then the
                                                       cells; writes RECORD, refuses if it exists

Writes only data/_labs/ewar_team_accounting/record.json (--read; --out overrides it).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for p in (str(ROOT), str(TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

import ewar_team_accounting as TA  # noqa: E402

CACHE = ROOT / ".cache"
RECORD = ROOT / "data" / "_labs" / "ewar_team_accounting" / "record.json"
EWAR_V3 = ROOT / "data" / "ewar_v3.json"
XHEM_PREVIEW = CACHE / "ewar_v3" / "preview" / "ewar_v3_xhem.json"
VINTAGE = ROOT / "data" / "fwar_vintage.json"
PYTHAG_EXPONENT = 0.287


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
            raise TA.AccountingRefusal("the frozen fWAR vintage is absent")
        return fwar_vintage.load()

    def ewar_v3(self) -> dict:
        if not EWAR_V3.exists():
            raise TA.AccountingRefusal("data/ewar_v3.json is absent")
        return json.loads(EWAR_V3.read_text(encoding="utf-8"))

    def xhem_preview(self):
        if not XHEM_PREVIEW.exists():
            return None
        return json.loads(XHEM_PREVIEW.read_text(encoding="utf-8"))

    def bwar(self, side: str):
        import war_source
        df = war_source._load_last_good(side)
        if df is None:
            raise TA.AccountingRefusal(f"the bWAR copy ({side}) is absent")
        return df

    def standings(self, seasons) -> dict:
        import ewar
        return ewar.standings(seasons)

    def fg_rpw(self, season: int) -> float:
        import league_constants
        lt = league_constants.league_totals(season)
        if not lt:
            raise TA.AccountingRefusal(f"{season}: league_constants.league_totals returned nothing")
        return float(lt["rpw"])

    def bref_rpw(self, bat, pit):
        import ewar
        return ewar.runs_per_win(bat, pit)

    def park(self, season: int):
        """{bref club: pf - 1} or {} when no complete file exists."""
        import build_rpw_fit
        try:
            pf, _, _ = build_rpw_fit.park_factors(season, CACHE)
        except Exception:  # noqa: BLE001 - a missing factor is a gap in part 8, not a stop
            return {}
        names = self._team_names(season)
        return {names[t]: v - 1.0 for t, v in pf.items() if t in names}

    def team_pitching(self, season: int) -> dict:
        """{bref club: StatsAPI season pitching line} or {}."""
        p = CACHE / "team_stats" / f"{season}_pit.json"
        if not p.exists():
            return {}
        rows = json.loads(p.read_text(encoding="utf-8")).get("rows") or []
        out = {}
        for r in rows:
            b = _bref_of_name(r.get("name"))
            if b:
                out[b] = r.get("stat") or {}
        return out

    def _team_names(self, season: int) -> dict:
        p = CACHE / "team_stats" / f"{season}_pit.json"
        if not p.exists():
            return {}
        rows = json.loads(p.read_text(encoding="utf-8")).get("rows") or []
        return {int(r["team_id"]): _bref_of_name(r.get("name")) for r in rows
                if _bref_of_name(r.get("name"))}

    def meta(self) -> dict:
        import war_source
        return {"fwar_vintage_sha256": _sha(VINTAGE), "ewar_v3_sha256": _sha(EWAR_V3),
                "xhem_preview_sha256": _sha(XHEM_PREVIEW),
                "bwar_bat_sha256": _sha(war_source._cache_path("bat")),
                "bwar_pit_sha256": _sha(war_source._cache_path("pit"))}


def _bref_of_name(name):
    import ewar
    name = (name or "").strip()
    for k, v in ewar._CLUB_TO_BREF.items():
        if name.endswith(k):
            return v
    return None


def _fold(t) -> str:
    import ewar
    return ewar._fold_team(t)


# ------------------------------------------------------------------- frame
def _player_departures(blob: dict, key: str) -> dict:
    """{(side, season, mlbam): departure wins} for key 'dr' or 'dh'."""
    out = {}
    for mid, by_s in (blob.get("players") or {}).items():
        for s, rec in (by_s or {}).items():
            for side, v in ((rec or {}).get(key) or {}).items():
                fv = _num(v)
                if fv:
                    out[(side, int(s), int(mid))] = fv
    return out


def build_frame(inp: Inputs, seasons, log=print) -> dict:
    """The design, the series and the departure for one set of seasons (gate part 3)."""
    seasons = tuple(int(s) for s in seasons)
    vint = inp.vintage()
    vid = str(vint.get("vintage_id") or "")
    ev3 = inp.ewar_v3()
    if str(ev3.get("fwar_vintage_id") or "") != vid:
        raise TA.AccountingRefusal(f"data/ewar_v3.json is on vintage {ev3.get('fwar_vintage_id')}, not {vid}")
    xh = inp.xhem_preview()
    xh_note = None
    if xh is None:
        xh_note = "absent"
    elif str(xh.get("fwar_vintage_id") or "") != vid:
        xh_note = f"on vintage {xh.get('fwar_vintage_id')}, skipped"
        xh = None

    stand = inp.standings(seasons)
    clubs = []
    for s in seasons:
        st = stand.get(s) or {}
        TA.check_standings(s, st)
        for c in sorted(st):
            clubs.append((s, c, st[c]))
    col = {(s, c): i for i, (s, c, _) in enumerate(clubs)}
    n_c = len(clubs)

    bat_df, pit_df = inp.bwar("bat"), inp.bwar("pit")

    # stints per side: {(season, mlbam): [(club, exposure, games)]}; bWAR rows per club
    stints = {"bat": {}, "pit": {}}
    b_rows = []          # (side, player key, col, WAR)
    unmapped = []
    for side, df, ecol in (("bat", bat_df, "PA"), ("pit", pit_df, "IPouts")):
        cols = ["mlb_ID", "player_ID", "year_ID", "team_ID", ecol, "G", "WAR"]
        for r in df[cols].itertuples(index=False):
            y = _num(r[2])
            if y is None or int(y) not in seasons:
                continue
            y = int(y)
            club = _fold(r[3])
            if (y, club) not in col:
                unmapped.append(f"{y} {r[3]}")
                continue
            mid = _num(r[0])
            key = f"m{int(mid)}" if mid is not None else f"b{r[1]}"
            if mid is not None:
                stints[side].setdefault((y, int(mid)), []).append((club, _num(r[4]), _num(r[5])))
            war = _num(r[6])
            if war is not None:
                b_rows.append((side, key, col[(y, club)], war))
    if unmapped:
        raise TA.AccountingRefusal(f"bWAR stint clubs outside the standings: {sorted(set(unmapped))[:10]}")

    # vintage rows
    dr = _player_departures(ev3, "dr")
    dh = _player_departures(ev3, "dh")
    dx = _player_departures(xh, "dh") if xh else {}
    v_rows = []          # (side, season, mlbam, war, shares)
    unalloc = {s: {"rows": 0, "abs_wins": 0.0} for s in seasons}
    null_war = 0
    for s in seasons:
        blk = (vint.get("seasons") or {}).get(str(s)) or {}
        for grp, side in (("hitting", "bat"), ("pitching", "pit")):
            g = blk.get(grp) or {}
            fields = list((vint.get("fields") or {}).get(grp) or [])
            iw = fields.index("war")
            for mid, vals in (g.get("rows") or {}).items():
                war = _num(vals[iw]) if vals is not None and len(vals) > iw else None
                if war is None:
                    null_war += 1
                    continue
                sh = TA.allocation_shares(stints[side].get((s, int(mid)), []))
                if not sh:
                    unalloc[s]["rows"] += 1
                    unalloc[s]["abs_wins"] += abs(war) + abs(dr.get((side, s, int(mid)), 0.0))
                    continue
                v_rows.append((side, s, int(mid), war, sh))
    for s, u in unalloc.items():
        if u["abs_wins"] > TA.UNALLOCATED_MAX_WINS:
            raise TA.AccountingRefusal(f"{s}: unallocated vintage value {u['abs_wins']:.3f} wins")
    have ={(side, s, mid) for side, s, mid, _, _ in v_rows}
    orphan = sorted({k for k in list(dr) + list(dh) + list(dx) if k[1] in seasons and k not in have})
    orphan_abs = sum(abs(dr.get(k, 0.0)) + abs(dh.get(k, 0.0)) + abs(dx.get(k, 0.0)) for k in orphan)
    if orphan_abs > TA.UNALLOCATED_MAX_WINS:
        raise TA.AccountingRefusal(f"departures on rows the vintage lacks: {orphan_abs:.3f} wins")

    keys = sorted({f"m{mid}" for _, _, mid, _, _ in v_rows} | {k for _, k, _, _ in b_rows})
    pidx = {k: i for i, k in enumerate(keys)}
    n_p = len(keys)
    names = ["F", "E", "H"] + (["Hx"] if xh else [])
    mats = {k: {"bat": np.zeros((n_p, n_c)), "pit": np.zeros((n_p, n_c))} for k in names + ["B"]}
    dep_p, dep_s, dep_sh, dep_v = [], [], [], []
    for side, s, mid, war, sh in v_rows:
        i = pidx[f"m{mid}"]
        k3 = (side, s, mid)
        vals = {"F": war, "E": war + dr.get(k3, 0.0), "H": war + dh.get(k3, 0.0)}
        if xh:
            vals["Hx"] = war + dx.get(k3, 0.0)
        row = np.zeros(n_c)
        for club, share in sh.items():
            row[col[(s, club)]] = share
        for k in names:
            mats[k][side][i] += vals[k] * row
        if side == "pit" and dr.get(k3):
            dep_p.append(i)
            dep_s.append(s)
            dep_sh.append(row)
            dep_v.append(dr[k3])
    for side, key, j, war in b_rows:
        mats["B"][side][pidx[key], j] += war

    # runs per win
    fg = {s: inp.fg_rpw(s) for s in seasons}
    by_team, by_season = inp.bref_rpw(bat_df, pit_df)
    ev3_rpw = {s: float(((ev3.get("checks") or {}).get(str(s)) or {}).get("rpw") or float("nan"))
               for s in seasons}
    xh_rpw = ({s: float(((xh.get("checks") or {}).get(str(s)) or {}).get("rpw") or float("nan"))
               for s in seasons} if xh else {})
    rpw = {"F": np.array([fg[s] for s, _, _ in clubs]),
           "E": np.array([ev3_rpw[s] for s, _, _ in clubs]),
           "B": np.array([float(by_team.get((s, c), by_season.get(s, float("nan")))) for s, c, _ in clubs])}
    rpw["H"] = rpw["E"]
    if xh:
        rpw["Hx"] = np.array([xh_rpw[s] for s, _, _ in clubs])
    for k, v in rpw.items():
        if not np.all(np.isfinite(v)):
            raise TA.AccountingRefusal(f"series {k}: a runs-per-win value is missing")

    franchise_codes = {c: i for i, c in enumerate(sorted({c for _, c, _ in clubs}))}
    design = TA.Design(season=[s for s, _, _ in clubs], club=[c for _, c, _ in clubs],
                       franchise=[franchise_codes[c] for _, c, _ in clubs],
                       g=[r["w"] + r["l"] for _, _, r in clubs], w=[r["w"] for _, _, r in clubs],
                       rs=[r["rs"] for _, _, r in clubs], ra=[r["ra"] for _, _, r in clubs],
                       players=keys, seasons=seasons)
    series = {k: TA.Series(bat=mats[k]["bat"], pit=mats[k]["pit"], rpw=rpw[k]) for k in names + ["B"]}
    dep = TA.Departure(player=np.array(dep_p, int), season=np.array(dep_s, int),
                       shares=np.array(dep_sh).reshape(len(dep_sh), n_c), value=np.array(dep_v, float))

    # refusals 4 and 5
    checks = {}
    for s in seasons:
        m = design.season == s
        rec = {}
        for k in names:
            tot_rows = sum((war + {"F": 0.0, "E": dr.get((sd, s2, mid), 0.0),
                                   "H": dh.get((sd, s2, mid), 0.0),
                                   "Hx": dx.get((sd, s2, mid), 0.0)}[k])
                           for sd, s2, mid, war, _ in v_rows if s2 == s)
            club_tot = float(sum(series[k].sums()[0][m]) + sum(series[k].sums()[1][m]))
            if abs(club_tot - tot_rows) > TA.SUM_TOL * max(1.0, len(v_rows) / 1000.0):
                raise TA.AccountingRefusal(f"{s} {k}: club sums {club_tot} differ from rows {tot_rows}")
            rec[k] = club_tot
        b_tot = sum(w for side, key, j, w in b_rows if design.season[j] == s)
        b_club = float(series["B"].sums()[0][m].sum() + series["B"].sums()[1][m].sum())
        if abs(b_club - b_tot) > TA.SUM_TOL * max(1.0, len(b_rows) / 1000.0):
            raise TA.AccountingRefusal(f"{s} B: club sums {b_club} differ from rows {b_tot}")
        rec["B"] = b_club
        bound = float(((ev3.get("checks") or {}).get(str(s)) or {}).get("r2_rounding_bound") or 1e-6)
        if abs(rec["E"] - rec["F"]) > bound + 1e-6:
            raise TA.AccountingRefusal(f"{s}: eWAR realized total {rec['E']} differs from fWAR {rec['F']}")
        if abs(rec["H"] - rec["F"]) > 1e-9 * max(1.0, abs(rec["F"])) + 1e-9 and s < 2026:
            raise TA.AccountingRefusal(f"{s}: headline total {rec['H']} differs from fWAR {rec['F']}")
        rec["unallocated"] = unalloc[s]
        checks[str(s)] = rec

    census = {"club_seasons": n_c, "players": n_p, "vintage_rows": len(v_rows),
              "vintage_null_war": null_war, "bwar_rows": len(b_rows), "departure_rows": len(dep_v),
              "departure_abs_wins": float(np.abs(dep.value).sum()) if len(dep_v) else 0.0,
              "orphan_departures": len(orphan), "xhem_preview": xh_note or "used",
              "series": names + ["B"], "season_totals": checks,
              "rpw": {k: {str(s): float(v[design.season == s][0]) if k != "B" else None
                          for s in seasons} for k, v in rpw.items()}}
    log(f"frame {seasons[0]}..{seasons[-1]}: {n_c} club-seasons, {n_p} players, "
        f"{len(v_rows)} vintage rows ({null_war} null), {len(b_rows)} bWAR stint rows, "
        f"{len(dep_v)} departure rows; Hx {census['xhem_preview']}")
    return {"design": design, "series": series, "dep": dep, "census": census,
            "v_rows": v_rows, "col": col, "clubs": clubs}


def factors(inp: Inputs, fr: dict) -> dict:
    """Gate part 8's four club-season factors (NaN where an input is missing)."""
    design, v_rows, col = fr["design"], fr["v_rows"], fr["col"]
    n = design.n
    park = np.full(n, np.nan)
    der = np.full(n, np.nan)
    for s in design.seasons:
        pk = inp.park(s)
        tp = inp.team_pitching(s)
        for i in np.flatnonzero(design.season == s):
            c = design.club[i]
            if c in pk:
                park[i] = pk[c]
            st = tp.get(c)
            if st:
                h, hr = _num(st.get("hits")), _num(st.get("homeRuns"))
                bf, so = _num(st.get("battersFaced")), _num(st.get("strikeOuts"))
                bb, hbp = _num(st.get("baseOnBalls")), _num(st.get("hitByPitch"))
                if None not in (h, hr, bf, so, bb, hbp) and bf - so - bb - hbp - hr > 0:
                    der[i] = 1.0 - (h - hr) / (bf - so - bb - hbp - hr)
        m = (design.season == s) & np.isfinite(der)
        if m.sum() > 2 and np.std(der[m]) > 0:
            der[m] = (der[m] - der[m].mean()) / np.std(der[m])
    vint = inp.vintage()
    fields = list((vint.get("fields") or {}).get("pitching") or [])
    ix = {f: fields.index(f) for f in ("gmli", "gamesPitched", "gamesStarted", "outs") if f in fields}
    num = np.zeros(n)
    den = np.zeros(n)
    if len(ix) == 4:
        rows = {}
        for s in design.seasons:
            for mid, vals in ((((vint.get("seasons") or {}).get(str(s)) or {}).get("pitching") or {})
                              .get("rows") or {}).items():
                rows[(s, int(mid))] = vals
        for side, s, mid, war, sh in v_rows:
            if side != "pit":
                continue
            vals = rows.get((s, mid))
            if not vals:
                continue
            gm, gp, gs, outs = (_num(vals[ix[k]]) for k in ("gmli", "gamesPitched", "gamesStarted", "outs"))
            if None in (gm, gp, gs, outs) or gp <= 0 or gs / gp >= 0.5:
                continue
            for club, share in sh.items():
                j = col[(s, club)]
                num[j] += share * outs * (gm - 1.0)
                den[j] += share * outs
    lev = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)
    import rpw_fit
    seq = design.w - rpw_fit.pythag_wins(design.rs, design.ra, design.g, PYTHAG_EXPONENT)
    return {"park": park, "defense": der, "leverage": lev, "sequencing": seq}


# ------------------------------------------------------------------ runs
def run_planted(inp: Inputs, log=print) -> dict:
    fr = build_frame(inp, TA.PRIMARY_SEASONS, log=lambda *a: None)
    design, ser, dep = fr["design"], fr["series"], fr["dep"]
    # Nothing below reads design.w, rs or ra: planted() replaces them first, and the
    # identity check runs on a synthetic design.
    t0 = time.time()
    out = {}
    for sig in (TA.PLANTED_SIGMA_RD, TA.PLANTED_SIGMA_RD_ALT):
        out[f"sd_{int(sig)}"] = TA.planted(design, ser["F"], dep, reps=TA.PLANTED_REPS,
                                           boot_b=TA.PLANTED_B, perm_n=TA.PLANTED_PERM,
                                           sigma_rd=sig, sigma_w=TA.PLANTED_SIGMA_W,
                                           seed=TA.SEED, log=log)
        log(f"planted sd {sig:g} runs: truth PASS {out[f'sd_{int(sig)}']['truth_pass']}/{TA.PLANTED_REPS}, "
            f"fake PASS {out[f'sd_{int(sig)}']['fake_pass']}/{TA.PLANTED_REPS}, "
            f"PLANTED PASS {out[f'sd_{int(sig)}']['planted_pass']} ({time.time() - t0:.0f}s)")
    rng = np.random.default_rng(TA.SEED)
    bat, pit = ser["F"].sums()
    syn = TA.synthetic_design(design, bat + pit, ser["F"].rpw, rng, TA.PLANTED_SIGMA_RD, TA.PLANTED_SIGMA_W)
    out["identity"] = TA.identity_check(syn, ser["F"])
    log(f"identity check: F against itself, all d zero {out['identity']['all_d_zero']}, "
        f"verdict {out['identity']['verdict']}")
    out["planted_pass"] = out[f"sd_{int(TA.PLANTED_SIGMA_RD)}"]["planted_pass"] and out["identity"]["ok"]
    return out


def _fmt(x, nd=3):
    return "null" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.{nd}f}"


def run_read(inp: Inputs, out_path: Path, log=print, planted_block: dict | None = None) -> dict:
    if out_path.exists():
        raise TA.AccountingRefusal(f"the record exists ({out_path}); the read runs once")
    t0 = time.time()
    log(f"EWAR_TEAM_ACCOUNTING read, {_now()}, {TA.VERSION}, seed {TA.SEED}, B {TA.BOOT_B}")
    if planted_block is None:
        planted_block = run_planted(inp, log=log)
    fr = build_frame(inp, TA.PRIMARY_SEASONS, log=log)
    design, ser, dep = fr["design"], fr["series"], fr["dep"]
    ser = dict(ser)
    ser["E_rpwF"] = TA.Series(bat=ser["E"].bat, pit=ser["E"].pit, rpw=ser["F"].rpw)
    reported = [k for k in ("H", "Hx", "E_rpwF") if k in ser]
    log("scoring begins")
    res = TA.score(design, ser, "E", ("F", "B"), boot_b=TA.BOOT_B, seed=TA.SEED,
                   perm_n=TA.PERM_N, dep=dep, null_key="F",
                   planted_pass=planted_block["planted_pass"], reported=reported, log=log)
    for c in ("F", "B"):
        for o in TA.OUTCOMES:
            cells = res["cells"][c][o]
            log(f"E vs {c} {o}: RMSE {c} {_fmt(res['points'][c][o]['rmse'])} E "
                f"{_fmt(res['points']['E'][o]['rmse'])}, d {_fmt(cells['season']['d'])}; "
                + "; ".join(f"{k} sd {_fmt(cells[k]['sd'])} lo {_fmt(cells[k]['lo'])} hi {_fmt(cells[k]['hi'])}"
                            for k in TA.BOOTS))
        log(f"disposition E vs {c}: {res['dispositions'][c]}")
    for o, v in (res["permutation_null"] or {}).items():
        log(f"permutation null {o}: d(F) {_fmt(v['d_vs_null'])}, q95 {_fmt(v['perm_q95'])}, "
            f"cleared {v['cleared']}")
    log(f"VERDICT: {res['verdict']}")
    for k in sorted(res["points"]):
        log(f"points {k}: " + ", ".join(
            f"{o} RMSE {_fmt(res['points'][k][o]['rmse'])} Rsq {_fmt(res['points'][k][o]['rsq'])}"
            for o in TA.OUTCOMES) + f", wins at the fixed baseline RMSE "
            f"{_fmt(res['points'][k]['wins_fixed_baseline']['rmse'])}")
    for r in reported:
        log(f"reported {r}: " + json.dumps(res["reported"][r]["disposition_reported"]))
    fac = factors(inp, fr)
    miss = TA.miss_table(design, {k: ser[k] for k in ("E", "F", "B") + (("Hx",) if "Hx" in ser else ())}, fac)
    for k, rec in miss.items():
        for o in TA.OUTCOMES:
            log(f"miss {k} {o}: joint Rsq {_fmt(rec[o]['joint_rsq'])}; " + "; ".join(
                f"{n} r {_fmt((v or {}).get('r'))} slope {_fmt((v or {}).get('slope'), 2)}"
                for n, v in rec[o]["factors"].items()))
    # 2020, reported alone (points only)
    sens = None
    try:
        fr20 = build_frame(inp, (TA.SENSITIVITY_SEASON,), log=log)
        s20 = dict(fr20["series"])
        sens = {"points": TA.point_cells(fr20["design"], s20), "census": fr20["census"]}
        log("2020 points: " + ", ".join(f"{k} wins RMSE {_fmt(v['wins']['rmse'])} rd RMSE {_fmt(v['rd']['rmse'])}"
                                        for k, v in sens["points"].items()))
    except TA.AccountingRefusal as e:
        sens = {"refused": str(e)}
        log(f"2020 not reported: {e}")
    record = {
        "schema": 1, "version": TA.VERSION, "gate": TA.GATE_DOC, "generated_at": _now(),
        "task": "EWAR_TEAM_ACCOUNTING", "owner_decision": "EW3-50",
        "inputs": inp.meta(), "frame": fr["census"], "planted": planted_block,
        "read": {k: res[k] for k in ("points", "cells", "dispositions", "reported", "permutation_null",
                                     "null_cleared", "planted_pass", "verdict", "boot_b", "seed")},
        "miss": miss, "sensitivity_2020": sens,
        "runtime_s": round(time.time() - t0, 1),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(TA.to_jsonable(record), indent=1, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
    log(f"wrote {out_path} ({time.time() - t0:.0f}s)")
    return record


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--frame", action="store_true")
    g.add_argument("--planted", action="store_true")
    g.add_argument("--read", action="store_true")
    ap.add_argument("--out", default=str(RECORD))
    a = ap.parse_args(argv)
    inp = Inputs()
    if a.frame:
        fr = build_frame(inp, TA.PRIMARY_SEASONS)
        print(json.dumps(TA.to_jsonable({k: v for k, v in fr["census"].items() if k != "season_totals"}),
                         indent=1)[:4000])
        return 0
    if a.planted:
        out = run_planted(inp)
        print(json.dumps(TA.to_jsonable({k: (v if k == "identity" or not isinstance(v, dict)
                                             else {kk: vv for kk, vv in v.items() if kk != "rows"})
                                         for k, v in out.items()}), indent=1))
        return 0
    run_read(inp, Path(a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
