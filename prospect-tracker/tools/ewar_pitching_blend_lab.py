#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""ewar_pitching_blend_lab - the eWAR pitching blend read (EWAR_PITCHING_BLEND).

docs/ewar-v3/EWAR_PITCHING_BLEND_GATE.md, owner decision EW3-50. Reads, never fetches
and never writes a cache:
  data/fwar_vintage.json                 F9 (fip, fipMinus), IP, roles
  war_source's Baseball-Reference copy   B9 (runs_above_avg, IPouts), the pair's franchise
  .cache/swar/preview/swar.json          RA9* (the target), the nopp rows
  .cache/pbp_runners                     plays, runners (bases, outs, scorers)
  .cache/pbp_corpus                      the pitcher of record and substitutions, 2018 on
  .cache/win_prob_hist                   the pitcher of record and substitutions, 2016 and 2017
  data/ewar_v3.json                      eWAR v3's runs per win (reported)
  and, for test (ii), every input of tools/ewar_team_accounting_lab.py

  python tools/ewar_pitching_blend_lab.py --frame     the frame census and refusals only
  python tools/ewar_pitching_blend_lab.py --planted   gate part 8 on the real design (no outcome)
  python tools/ewar_pitching_blend_lab.py --read      the one read: planted and identity checks,
                                                      then the tests; writes RECORD, refuses if it exists

Writes only data/_labs/ewar_pitching_blend/record.json (--read; --out overrides it).
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

import ewar_pitching_blend as PB  # noqa: E402

CACHE = ROOT / ".cache"
RECORD = ROOT / "data" / "_labs" / "ewar_pitching_blend" / "record.json"
PREVIEW = CACHE / "swar" / "preview" / "swar.json"
EWAR_V3 = ROOT / "data" / "ewar_v3.json"
VINTAGE = ROOT / "data" / "fwar_vintage.json"
RUNNER_DIR = CACHE / "pbp_runners"
CORPUS_DIR = CACHE / "pbp_corpus"
HIST_DIR = CACHE / "win_prob_hist"
MISSING_PITCHER_MAX = 0.005
OUTS_TOL = 0.01
K_EVENTS = {"strikeout", "strikeout_double_play", "strikeout_triple_play"}
BB_EVENTS = {"walk", "intent_walk"}


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


def _i(v):
    try:
        if v is None or v != v:
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ inputs
class Inputs:
    """Every input, one method each, so the dry run supplies fixtures."""

    def vintage(self) -> dict:
        import fwar_vintage
        if not fwar_vintage.available():
            raise PB.BlendRefusal("the frozen fWAR vintage is absent")
        return fwar_vintage.load()

    def preview(self) -> dict:
        if not PREVIEW.exists():
            raise PB.BlendRefusal("the eWAR v3 preview (.cache/swar/preview/swar.json) is absent")
        return json.loads(PREVIEW.read_text(encoding="utf-8"))

    def bwar_pit(self):
        import war_source
        df = war_source._load_last_good("pit")
        if df is None:
            raise PB.BlendRefusal("the Baseball-Reference copy (pit) is absent")
        return df

    def plays(self, season: int):
        """(plays, scorers, reached, pitchers, subs) DataFrames of one season's runner
        record and its pitcher source, or None when a part is missing."""
        import pandas as pd
        y = int(season)
        pa = RUNNER_DIR / "plays" / str(y) / f"pa-{y}.parquet"
        rn = RUNNER_DIR / "runners" / str(y) / f"runners-{y}.parquet"
        if not (pa.exists() and rn.exists()):
            return None
        plays = pd.read_parquet(pa, columns=["game_pk", "half", "inning", "at_bat_index", "batter_id",
                                             "event_type", "is_pa", "outs_before", "outs_after",
                                             "on_first", "on_second", "on_third"])
        runners = pd.read_parquet(rn, columns=["game_pk", "at_bat_index", "runner_id", "is_batter",
                                               "end", "is_out", "is_scoring"])
        cp = CORPUS_DIR / "plays" / str(y) / f"plays-{y}.parquet"
        ce = CORPUS_DIR / "events" / str(y) / f"events-{y}.parquet"
        if cp.exists() and ce.exists():
            pitchers = pd.read_parquet(cp, columns=["game_pk", "at_bat_index", "pitcher_id"])
            ev = pd.read_parquet(ce, columns=["game_pk", "event_type", "player_id", "replaced_player_id",
                                              "is_substitution"])
            ev = ev[ev["is_substitution"].fillna(False).astype(bool)
                    & (ev["event_type"] == "offensive_substitution")]
            subs = ev[["game_pk", "player_id", "replaced_player_id"]]
            src = "pbp_corpus"
        else:
            pitchers, subs = self._hist(y, sorted(plays["game_pk"].dropna().astype(int).unique()))
            if pitchers is None:
                return None
            src = "win_prob_hist"
        return {"plays": plays, "runners": runners, "pitchers": pitchers, "subs": subs, "source": src}

    def _hist(self, season: int, games):
        import pandas as pd
        try:
            import orjson
            loads = orjson.loads
        except ImportError:  # pragma: no cover
            loads = json.loads
        rows, subs, missing = [], [], 0
        for g in games:
            path = HIST_DIR / f"{int(g)}.json"
            if not path.exists():
                missing += 1
                continue
            for pl in loads(path.read_bytes()) or []:
                ab = _i(((pl.get("about") or {}).get("atBatIndex")))
                pid = _i((((pl.get("matchup") or {}).get("pitcher")) or {}).get("id"))
                if ab is not None and pid is not None:
                    rows.append((int(g), ab, pid))
                for ev in pl.get("playEvents") or []:
                    if not ev.get("isSubstitution"):
                        continue
                    if ((ev.get("details") or {}).get("eventType")) != "offensive_substitution":
                        continue
                    a = _i((ev.get("player") or {}).get("id"))
                    b = _i((ev.get("replacedPlayer") or {}).get("id"))
                    if a is not None and b is not None:
                        subs.append((int(g), a, b))
        if not rows:
            return None, None
        p = pd.DataFrame(rows, columns=["game_pk", "at_bat_index", "pitcher_id"])
        s = pd.DataFrame(subs, columns=["game_pk", "player_id", "replaced_player_id"])
        return p, s

    def fg_rpw(self, season: int) -> float:
        import league_constants
        lt = league_constants.league_totals(season)
        if not lt:
            raise PB.BlendRefusal(f"{season}: league_constants.league_totals returned nothing")
        return float(lt["rpw"])

    def ewar_v3(self) -> dict:
        if not EWAR_V3.exists():
            return {}
        return json.loads(EWAR_V3.read_text(encoding="utf-8"))

    def team_accounting(self):
        import ewar_team_accounting_lab as TAL
        return TAL.Inputs()

    def meta(self) -> dict:
        import war_source
        out = {"fwar_vintage_sha256": _sha(VINTAGE), "preview_sha256": _sha(PREVIEW),
               "ewar_v3_sha256": _sha(EWAR_V3), "bwar_pit_sha256": _sha(war_source._cache_path("pit")),
               "bwar_bat_sha256": _sha(war_source._cache_path("bat")), "runner_record": {}}
        for y in PB.FIT_SEASONS:
            out["runner_record"][str(y)] = {
                "pa": _sha(RUNNER_DIR / "plays" / str(y) / f"pa-{y}.parquet"),
                "runners": _sha(RUNNER_DIR / "runners" / str(y) / f"runners-{y}.parquet"),
                "corpus_plays": _sha(CORPUS_DIR / "plays" / str(y) / f"plays-{y}.parquet")}
        return out


# ------------------------------------------------------------------ appearances
def appearances(rec: dict, season: int) -> tuple[dict, dict]:
    """Gate part 3: {(game, pitcher): {order, outs, k, bb, hbp, hr, r}} and the census.
    Runs are charged to the scoring runner's owner."""
    plays = rec["plays"].merge(rec["pitchers"], on=["game_pk", "at_bat_index"], how="left")
    plays = plays.sort_values(["game_pk", "at_bat_index"], kind="mergesort").reset_index(drop=True)
    n_plays = len(plays)
    missing = int(plays["pitcher_id"].isna().sum())
    if n_plays == 0 or missing / n_plays > MISSING_PITCHER_MAX:
        raise PB.BlendRefusal(f"{season}: {missing} of {n_plays} plays lack a pitcher of record")
    # a play without a pitcher takes the previous play's pitcher in the same half (then the next)
    grp = plays["game_pk"].astype(str) + "|" + plays["half"].astype(str)
    plays["pitcher_id"] = plays.groupby(grp)["pitcher_id"].transform(lambda s: s.ffill().bfill())
    if plays["pitcher_id"].isna().any():
        raise PB.BlendRefusal(f"{season}: a half-inning has no pitcher of record at all")

    runners = rec["runners"]
    sc = runners[runners["is_scoring"].fillna(False).astype(bool)]
    scorers: dict = {}
    for g, a, rid in zip(sc["game_pk"].tolist(), sc["at_bat_index"].tolist(), sc["runner_id"].tolist()):
        if _i(rid) is not None:
            scorers.setdefault((int(g), int(a)), []).append(int(rid))
    bat = runners[runners["is_batter"].fillna(False).astype(bool)]
    reached = set()
    for g, a, rid, end, io_ in zip(bat["game_pk"].tolist(), bat["at_bat_index"].tolist(),
                                   bat["runner_id"].tolist(), bat["end"].tolist(), bat["is_out"].tolist()):
        if _i(rid) is None or bool(io_):
            continue
        if end is not None and str(end) not in ("None", "nan", "<NA>"):
            reached.add((int(g), int(a), int(rid)))
    subs: dict = {}
    for g, pid, rep in zip(rec["subs"]["game_pk"].tolist(), rec["subs"]["player_id"].tolist(),
                           rec["subs"]["replaced_player_id"].tolist()):
        if _i(pid) is not None and _i(rep) is not None:
            subs.setdefault(int(g), {})[int(pid)] = int(rep)

    app: dict = {}
    cols = {c: plays[c].tolist() for c in ("game_pk", "half", "inning", "at_bat_index", "batter_id",
                                           "event_type", "is_pa", "outs_before", "outs_after",
                                           "on_first", "on_second", "on_third", "pitcher_id")}
    runs_total = 0
    unplaced = 0
    owner: dict = {}
    key_prev = None
    for i in range(n_plays):
        g = int(cols["game_pk"][i])
        key = (g, cols["half"][i], cols["inning"][i])
        if key != key_prev:
            owner = {}
            key_prev = key
        pit = int(cols["pitcher_id"][i])
        a = int(cols["at_bat_index"][i])
        rec_a = app.get((g, pit))
        if rec_a is None:
            rec_a = app[(g, pit)] = {"outs": 0.0, "k": 0, "bb": 0, "hbp": 0, "hr": 0, "r": 0}
        for c in ("on_first", "on_second", "on_third"):
            rid = _i(cols[c][i])
            if rid is None or rid in owner:
                continue
            rep = (subs.get(g) or {}).get(rid)
            if rep is not None and rep in owner:
                owner[rid] = owner[rep]
            else:
                owner[rid] = pit
                unplaced += 1
        ob, oa = _i(cols["outs_before"][i]), _i(cols["outs_after"][i])
        if ob is not None and oa is not None and oa > ob:
            rec_a["outs"] += float(oa - ob)
        ev = cols["event_type"][i]
        if bool(cols["is_pa"][i]):
            if ev in K_EVENTS:
                rec_a["k"] += 1
            elif ev in BB_EVENTS:
                rec_a["bb"] += 1
            elif ev == "hit_by_pitch":
                rec_a["hbp"] += 1
            elif ev == "home_run":
                rec_a["hr"] += 1
        sc_here = scorers.get((g, a), ())
        for rid in sc_here:
            own = owner.get(rid, pit)
            app.setdefault((g, own), {"outs": 0.0, "k": 0, "bb": 0, "hbp": 0, "hr": 0, "r": 0})["r"] += 1
            owner.pop(rid, None)
            runs_total += 1
        b = _i(cols["batter_id"][i])
        if b is not None and (g, a, b) in reached and b not in sc_here:
            owner[b] = pit
    r_sum = sum(v["r"] for v in app.values())
    if r_sum != runs_total or runs_total != len(sc):
        raise PB.BlendRefusal(f"{season}: runs charged {r_sum} differ from runs scored {len(sc)}")
    census = {"plays": n_plays, "plays_without_pitcher": missing, "appearances": len(app),
              "runs": runs_total, "runners_unplaced": unplaced, "pitcher_source": rec["source"],
              "outs": float(sum(v["outs"] for v in app.values()))}
    return app, census


def halves(app: dict) -> dict:
    """{pitcher: {ip_o, ip_e, f_o, f_e, b_o, b_e}}: appearances in game order alternate."""
    by_p: dict = {}
    for (g, pit), v in app.items():
        by_p.setdefault(pit, []).append((g, v))
    out = {}
    for pit, lst in by_p.items():
        lst.sort(key=lambda t: t[0])
        acc = [{"outs": 0.0, "k": 0, "bb": 0, "hbp": 0, "hr": 0, "r": 0} for _ in range(2)]
        for j, (_g, v) in enumerate(lst):
            h = acc[j % 2]
            for k in h:
                h[k] += v[k]
        rec = {}
        for tag, h in zip(("o", "e"), acc):
            ip = h["outs"] / 3.0
            rec["ip_" + tag] = ip
            if ip > 0:
                rec["f_" + tag] = -(13.0 * h["hr"] + 3.0 * (h["bb"] + h["hbp"]) - 2.0 * h["k"]) / ip
                rec["b_" + tag] = -9.0 * h["r"] / ip
            else:
                rec["f_" + tag] = float("nan")
                rec["b_" + tag] = float("nan")
        out[pit] = rec
    return out


# ------------------------------------------------------------------ frame
def build_frame(inp: Inputs, log=print) -> dict:
    """Rows (every non-nopp vintage pitcher-season of the fit seasons), their halves,
    the pairs of test (i) and the census (gate parts 2, 3, 5 and 10)."""
    seasons = PB.FIT_SEASONS
    vint = inp.vintage()
    vid = str(vint.get("vintage_id") or "")
    prev = inp.preview()
    if str(prev.get("fwar_vintage_id") or "") != vid:
        raise PB.BlendRefusal(f"the preview is on vintage {prev.get('fwar_vintage_id')}, not {vid}")
    fields = list((vint.get("fields") or {}).get("pitching") or [])
    ix = {f: fields.index(f) for f in ("fip", "fipMinus", "outs", "gamesPitched", "gamesStarted")}

    # Baseball-Reference: per (season, mlbam) runs_above_avg, IPouts; the largest stint's club
    import ewar
    bdf = inp.bwar_pit()
    bref: dict = {}
    for r in bdf[["mlb_ID", "year_ID", "team_ID", "IPouts", "runs_above_avg"]].itertuples(index=False):
        mid, y = _num(r[0]), _num(r[1])
        if mid is None or y is None or int(y) not in seasons + (2026,):
            continue
        ipo, raa = _num(r[3]), _num(r[4])
        if ipo is None:
            continue
        rec = bref.setdefault((int(y), int(mid)), {"ipouts": 0.0, "raa": 0.0, "raa_ok": True, "club": None,
                                                   "club_ipo": -1.0})
        rec["ipouts"] += ipo
        if raa is None:
            rec["raa_ok"] = False
        else:
            rec["raa"] += raa
        if ipo > rec["club_ipo"]:
            rec["club_ipo"] = ipo
            rec["club"] = ewar._fold_team(r[2])

    prows = {}
    for s, blk in (prev.get("seasons") or {}).items():
        for r in blk.get("pitchers") or []:
            prows[(int(s), int(r["mlbam"]))] = r

    cols = {k: [] for k in ("season", "player", "role", "ip", "f9", "b9", "ip_o", "ip_e",
                            "f_o", "f_e", "b_o", "b_e")}
    census = {"seasons": {}}
    half_by_season = {}
    for y in seasons:
        rec = inp.plays(y)
        if rec is None:
            raise PB.BlendRefusal(f"{y}: the runner record or its pitcher source is missing")
        app, cen = appearances(rec, y)
        half_by_season[y] = halves(app)
        census["seasons"][str(y)] = cen
        log(f"appearances {y}: {cen['appearances']} from {cen['pitcher_source']}, plays {cen['plays']} "
            f"({cen['plays_without_pitcher']} without a pitcher), runs {cen['runs']}, "
            f"unplaced runners {cen['runners_unplaced']}")
    for y in seasons:
        blk = ((vint.get("seasons") or {}).get(str(y)) or {}).get("pitching") or {}
        rows = blk.get("rows") or {}
        lg_num = lg_den = 0.0
        league_outs = 0.0
        tmp = []
        nopp = no_b = 0
        for mid, vals in rows.items():
            mid = int(mid)
            outs = _num(vals[ix["outs"]]) or 0.0
            league_outs += outs
            if outs <= 0:
                continue
            pr = prows.get((y, mid))
            if pr is not None and pr.get("nopp"):
                nopp += 1
                continue
            fip, fm = _num(vals[ix["fip"]]), _num(vals[ix["fipMinus"]])
            ip = outs / 3.0
            if fip is not None:
                lg_num += ip * fip
                lg_den += ip
            tmp.append((mid, ip, fm, _num(vals[ix["gamesStarted"]]) or 0.0,
                        _num(vals[ix["gamesPitched"]]) or 0.0))
        app_outs = census["seasons"][str(y)]["outs"]
        if league_outs <= 0 or abs(app_outs - league_outs) / league_outs > OUTS_TOL:
            raise PB.BlendRefusal(f"{y}: appearance outs {app_outs} against the vintage's {league_outs}")
        lg_fip = lg_num / lg_den
        hy = half_by_season[y]
        for mid, ip, fm, gs, gp in tmp:
            f9 = lg_fip * (100.0 - fm) / 100.0 if fm is not None else float("nan")
            b = bref.get((y, mid))
            if b and b["ipouts"] > 0 and b["raa_ok"]:
                b9 = 9.0 * b["raa"] / (b["ipouts"] / 3.0)
            else:
                b9 = float("nan")
                no_b += 1
            h = hy.get(mid) or {}
            cols["season"].append(y)
            cols["player"].append(mid)
            cols["role"].append(int(PB.role_code([gs], [gp])[0]))
            cols["ip"].append(ip)
            cols["f9"].append(f9)
            cols["b9"].append(b9)
            for k in ("ip_o", "ip_e", "f_o", "f_e", "b_o", "b_e"):
                cols[k].append(h.get(k, float("nan")))
        census["seasons"][str(y)].update({"league_outs_vintage": league_outs, "lg_fip": lg_fip,
                                           "rows": len(tmp), "nopp": nopp, "without_bref": no_b})
    season = np.array(cols["season"])
    ip = np.array(cols["ip"], float)
    f9 = PB.centre_within_season(np.array(cols["f9"], float), ip, season)
    b9 = PB.centre_within_season(np.array(cols["b9"], float), ip, season)
    rows = PB.Rows(season=season, player=cols["player"], role=cols["role"], ip=ip, f9=f9, b9=b9,
                   **{k: cols[k] for k in ("ip_o", "ip_e", "f_o", "f_e", "b_o", "b_e")})
    # pairs (test (i))
    at = {(int(s), int(p)): i for i, (s, p) in enumerate(zip(rows.season, rows.player))}
    clubs = sorted({b["club"] for b in bref.values() if b.get("club")})
    ccode = {c: i for i, c in enumerate(clubs)}
    py, py1, pclub, ptarget, pra9y = [], [], [], [], []
    drop = {"no_b": 0, "no_target": 0, "no_club": 0}
    for i in range(rows.n):
        y = int(rows.season[i])
        if y not in PB.PREDICTOR_SEASONS or rows.ip[i] < PB.PAIR_FLOOR_IP:
            continue
        j = at.get((y + 1, int(rows.player[i])))
        if j is None or rows.ip[j] < PB.PAIR_FLOOR_IP:
            continue
        if not np.isfinite(rows.b9[i]) or not np.isfinite(rows.f9[i]):
            drop["no_b"] += 1
            continue
        t = _num((prows.get((y + 1, int(rows.player[i]))) or {}).get("ra9_star"))
        if t is None:
            drop["no_target"] += 1
            continue
        club = (bref.get((y, int(rows.player[i]))) or {}).get("club")
        if club is None:
            drop["no_club"] += 1
            continue
        py.append(i)
        py1.append(j)
        pclub.append(ccode[club])
        ptarget.append(-t)
        pra9y.append(_num((prows.get((y, int(rows.player[i]))) or {}).get("ra9_star")))
    census["pairs"] = {"n": len(py), "dropped": drop,
                       "by_season": {str(s): int(sum(1 for i in py if rows.season[i] == s))
                                     for s in PB.PREDICTOR_SEASONS}}
    census["rows"] = {"n": rows.n, "both_sources": int(rows.both().sum()), "split": int(rows.split().sum())}
    log(f"frame: {rows.n} pitcher-seasons ({census['rows']['both_sources']} with both sources, "
        f"{census['rows']['split']} split rows); {len(py)} pairs {census['pairs']['by_season']}")
    return {"rows": rows, "pair_y": np.array(py, int), "pair_y1": np.array(py1, int),
            "pair_club": np.array(pclub, int), "target": np.array(ptarget, float),
            "ra9_y": np.array([np.nan if v is None else -v for v in pra9y], float),
            "census": census, "bref": bref}


def planted_design(fr: dict) -> PB.PlantedDesign:
    return PB.PlantedDesign(rows=fr["rows"], pair_y=fr["pair_y"], pair_y1=fr["pair_y1"],
                            pair_club=fr["pair_club"], seasons=tuple(PB.FIT_SEASONS))


def run_planted(fr: dict, log=print) -> dict:
    t0 = time.time()
    out = PB.planted(planted_design(fr), reps=PB.PLANTED_REPS, boot_b=PB.PLANTED_B, seed=PB.SEED, log=log)
    log(f"planted: truth {out['truth_pass']}/{out['reps']}, fake {out['fake_pass']}/{out['reps']}, "
        f"w mean abs diff {out['w_mean_abs_diff']:.4f}, PLANTED PASS {out['planted_pass']} "
        f"({time.time() - t0:.0f}s)")
    return out


def _plain(x, nd):
    return "null" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.{nd}f}"


def _fmt(x, nd=4):
    return "null" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:+.{nd}f}"


# ------------------------------------------------------------------ test (ii)
def club_series(inp: Inputs, fr: dict, w_build: np.ndarray, log=print) -> dict:
    """Gate part 6: the yardstick's frame, F, B and C (F plus the blend's departure)."""
    import ewar_team_accounting as TA
    import ewar_team_accounting_lab as TAL
    tinp = inp.team_accounting()
    tf = TAL.build_frame(tinp, TA.PRIMARY_SEASONS, log=log)
    design, ser = tf["design"], tf["series"]
    rows = fr["rows"]
    rpw_f = {s: inp.fg_rpw(s) for s in TA.PRIMARY_SEASONS}
    in_frame = np.isin(rows.season, TA.PRIMARY_SEASONS)
    rpw_row = np.array([rpw_f.get(int(s), np.nan) for s in rows.season])
    # F9 and B9 are both present on the carry rows; rows without B9 carry d = 0
    raw = PB.departure_wins(rows.f9, rows.b9, w_build, rows.ip, np.where(in_frame, rpw_row, 1.0),
                            rows.season, in_frame)
    dmap = {(int(s), int(p)): float(v) for s, p, v in zip(rows.season, rows.player, raw) if v != 0.0}
    pidx = {k: i for i, k in enumerate(design.players)}
    dep_p, dep_s, dep_sh, dep_v = [], [], [], []
    n_c = design.n
    missing_abs = 0.0
    seen = set()
    for side, s, mid, war, sh in tf["v_rows"]:
        if side != "pit":
            continue
        v = dmap.get((s, mid))
        if not v:
            continue
        seen.add((s, mid))
        row = np.zeros(n_c)
        for club, share in sh.items():
            row[tf["col"][(s, club)]] = share
        dep_p.append(pidx[f"m{mid}"])
        dep_s.append(s)
        dep_sh.append(row)
        dep_v.append(v)
    for k, v in dmap.items():
        if k not in seen:
            missing_abs += abs(v)
    if missing_abs > TA.UNALLOCATED_MAX_WINS:
        raise PB.BlendRefusal(f"blend departures on rows the yardstick lacks: {missing_abs:.3f} wins")
    dep = TA.Departure(player=np.array(dep_p, int), season=np.array(dep_s, int),
                       shares=np.array(dep_sh).reshape(len(dep_sh), n_c), value=np.array(dep_v, float))
    c = TA.with_departure(ser["F"], dep, dep.value)
    c_rpwe = TA.Series(bat=c.bat, pit=c.pit, rpw=ser["E"].rpw)
    out = {"design": design, "series": {"F": ser["F"], "B": ser["B"], "E": ser["E"], "C": c,
                                        "C_rpwE": c_rpwe},
           "dep": dep, "unallocated_abs_wins": missing_abs,
           "season_sums": {str(s): float(dep.value[dep.season == s].sum()) for s in TA.PRIMARY_SEASONS},
           "abs_wins": float(np.abs(dep.value).sum())}
    log(f"club series C: {len(dep_v)} departure rows, {out['abs_wins']:.3f} absolute wins, "
        f"unallocated {missing_abs:.4f}")
    return out


# ------------------------------------------------------------------ the read
def run_read(inp: Inputs, out_path: Path, log=print) -> dict:
    import ewar_team_accounting as TA
    if out_path.exists():
        raise PB.BlendRefusal(f"the record exists ({out_path}); the read runs once")
    t0 = time.time()
    log(f"EWAR_PITCHING_BLEND read, {_now()}, {PB.VERSION}, seed {PB.SEED}, B {PB.BOOT_B}")
    fr = build_frame(inp, log=log)
    rows = fr["rows"]
    planted_block = run_planted(fr, log=log)

    # weights: forward folds for the predictor seasons, and the build's fit
    models: dict = {}
    w_fwd = PB.forward_weights(rows, PB.PREDICTOR_SEASONS, PB.FIT_SEASONS, models)
    build = PB.fit(rows, PB.FIT_SEASONS)
    w_build = build.weights(rows.role, rows.ip)
    med = PB.cell_medians(rows, np.ones(rows.n, bool))
    weights_table = build.table(med)
    for t in weights_table:
        log(f"weights {t['role']} {t['band']}: w at median IP {_plain(t['ip_median'], 1)} = "
            f"{_plain(t['w_at_median'], 3)} ({t['source']}; split {t['n_split']}, season {t['n_season']}); "
            f"sigma2_F {t['sigma2_F']:.2f} sigma2_B {t['sigma2_B']:.2f} sigma_FB {t['sigma_FB']:.2f}; "
            f"T_FF {t['T_FF']:.4f} T_BB {t['T_BB']:.4f} T_FB {t['T_FB']:.4f}")
    folds = {str(y): m.table(PB.cell_medians(rows, np.isin(rows.season, m.train))) for y, m in models.items()}

    y, y1 = fr["pair_y"], fr["pair_y1"]
    half = PB.blend(rows.f9[y], rows.b9[y], np.full(len(y), 0.5))
    pairs = PB.Pairs(season=rows.season[y], player=rows.player[y], club=fr["pair_club"], target=fr["target"],
                     series={"blend": PB.blend(rows.f9[y], rows.b9[y], w_fwd[y]), "F9": rows.f9[y],
                             "B9": rows.b9[y], "half": half, "RA9s_Y": fr["ra9_y"]})
    ident = PB.identity_check(pairs)
    log(f"identity check: gap {ident['gap_F9']}, all zero {ident['all_zero']}, ok {ident['ok']}")
    if not np.all(np.isfinite(pairs.series["RA9s_Y"])):
        pairs.series["RA9s_Y"] = np.where(np.isfinite(pairs.series["RA9s_Y"]), pairs.series["RA9s_Y"],
                                          np.nanmean(pairs.series["RA9s_Y"]))
    log("scoring begins")
    t_i = PB.test_i(pairs, reported=("half", "RA9s_Y"), boot_b=PB.BOOT_B, seed=PB.SEED, log=log)
    for c, cell in t_i["cells"].items():
        log(f"test (i) blend vs {c}: rho blend {t_i['rho']['blend']:.4f} {c} {t_i['rho'][c]:.4f}, gap "
            f"{_fmt(cell['gap'])}; " + "; ".join(
                f"{k} sd {cell['boot'][k]['sd']:.4f} lo {_fmt(cell['boot'][k]['lo'])} p {cell['boot'][k]['p']:.4f}"
                for k in PB.BOOTS_I))
    log(f"test (i) p_i {t_i['p_i']:.5f}")

    # test (ii)
    cs = club_series(inp, fr, w_build, log=log)
    series = cs["series"]
    res = TA.score(cs["design"], series, "C", ("F", "B"), boot_b=TA.BOOT_B, seed=TA.SEED,
                   dep=None, reported=("C_rpwE",), log=log)
    pts = res["points"]
    k_star = "F" if pts["F"]["ra"]["rmse"] <= pts["B"]["ra"]["rmse"] else "B"
    cell = res["cells"][k_star]["ra"]
    d = cell["season"]["d"]
    t_ii = PB.test_ii({k: cell[k] for k in TA.BOOTS}, d)
    t_ii["k_star"] = k_star
    log(f"test (ii): K* {k_star}, RMSE_RA {k_star} {pts[k_star]['ra']['rmse']:.3f} C {pts['C']['ra']['rmse']:.3f}, "
        f"d {d:+.3f}; " + "; ".join(f"{k} sd {v['sd']:.3f} lo {v['lo']:+.3f} p {v['p']:.5f}"
                                   for k, v in t_ii["boot"].items())
        + f"; NON-INFERIOR {t_ii['non_inferior']}, p_ii {t_ii['p_ii']:.5f}")
    for c in ("F", "B"):
        for o in TA.OUTCOMES:
            cc = res["cells"][c][o]
            log(f"C vs {c} {o} (reported): RMSE {c} {pts[c][o]['rmse']:.3f} C {pts['C'][o]['rmse']:.3f} "
                f"d {cc['season']['d']:+.3f}; " + "; ".join(
                    f"{k} lo {cc[k]['lo']:+.3f} hi {cc[k]['hi']:+.3f}" for k in TA.BOOTS))
    dec = PB.decide(t_i["p_i"], t_ii["p_ii"], planted_block["planted_pass"], ident["ok"])
    log(f"Holm: p_i {dec['p_i']:.5f}, p_ii {dec['p_ii']:.5f}, rejects {dec['holm_rejects']}")
    log(f"VERDICT: {dec['verdict']}")

    # reported: the 20 IP floor, the yardstick's planted check on C's departure
    rep20 = None
    try:
        rep20 = reported_floor(fr, w_fwd, 20.0)
        log(f"reported, 20 IP floor: n {rep20['n']}, rho blend {rep20['rho']['blend']:.4f} "
            f"F9 {rep20['rho']['F9']:.4f} B9 {rep20['rho']['B9']:.4f}")
    except Exception as e:  # noqa: BLE001 - a reported block never stops the read
        rep20 = {"error": str(e)}
    ta_planted = TA.planted(cs["design"], series["F"], cs["dep"], reps=TA.PLANTED_REPS, boot_b=TA.PLANTED_B,
                            perm_n=TA.PLANTED_PERM, sigma_rd=TA.PLANTED_SIGMA_RD, sigma_w=TA.PLANTED_SIGMA_W,
                            seed=TA.SEED, log=None)
    log(f"reported, the yardstick's planted check on C's departure pool: truth {ta_planted['truth_pass']}/"
        f"{TA.PLANTED_REPS}, fake {ta_planted['fake_pass']}/{TA.PLANTED_REPS}")
    w_dist = {}
    for ro in range(len(PB.ROLES)):
        for b in range(len(PB.BAND_NAMES)):
            m = (rows.role == ro) & (rows.band == b) & rows.both()
            if m.any():
                w_dist[f"{PB.ROLES[ro]} {PB.BAND_NAMES[b]}"] = {
                    "n": int(m.sum()), "mean": float(w_build[m].mean()), "p10": float(np.percentile(w_build[m], 10)),
                    "p90": float(np.percentile(w_build[m], 90))}
    record = {
        "schema": 1, "version": PB.VERSION, "gate": PB.GATE_DOC, "generated_at": _now(),
        "task": "EWAR_PITCHING_BLEND", "owner_decision": "EW3-50",
        "inputs": inp.meta(), "frame": fr["census"], "planted": {k: v for k, v in planted_block.items()},
        "identity": ident, "weights": {"build": weights_table, "folds": folds, "distribution": w_dist},
        "test_i": t_i,
        "test_ii": {"cell": t_ii, "points": res["points"], "cells": res["cells"],
                    "reported": res["reported"], "departure": {
                        "abs_wins": cs["abs_wins"], "season_sums": cs["season_sums"],
                        "unallocated_abs_wins": cs["unallocated_abs_wins"]},
                    "yardstick_planted_on_C": {k: ta_planted[k] for k in ("truth_pass", "fake_pass")}},
        "decision": dec, "reported_floor_20": rep20,
        "runtime_s": round(time.time() - t0, 1),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(PB.to_jsonable(record), indent=1, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
    log(f"wrote {out_path} ({time.time() - t0:.0f}s)")
    return record


def reported_floor(fr: dict, w_fwd: np.ndarray, floor: float) -> dict:
    """Reported, deciding nothing: test (i)'s points at a lower IP floor (no bootstrap)."""
    rows = fr["rows"]
    keep = (rows.ip[fr["pair_y"]] >= floor) & (rows.ip[fr["pair_y1"]] >= floor)
    y = fr["pair_y"][keep]
    p = PB.Pairs(season=rows.season[y], player=rows.player[y], club=fr["pair_club"][keep],
                 target=fr["target"][keep],
                 series={"blend": PB.blend(rows.f9[y], rows.b9[y], w_fwd[y]), "F9": rows.f9[y], "B9": rows.b9[y]})
    return {"n": p.n, "rho": {k: PB.rho_pooled(p, k) for k in p.series}}


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
        fr = build_frame(inp)
        print(json.dumps(PB.to_jsonable(fr["census"]), indent=1)[:6000])
        return 0
    if a.planted:
        fr = build_frame(inp)
        out = run_planted(fr)
        print(json.dumps(PB.to_jsonable({k: v for k, v in out.items() if k not in ("truth", "fake")}), indent=1))
        return 0
    run_read(inp, Path(a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
