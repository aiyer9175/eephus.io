# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Provisional grades v2 (PV-06; spec _finalpass_2026-09-24/provisional/PROVISIONAL_V2.md
section 3): for roster players no label source has graded, the chance of a first grade
within the next list cycle (T1) and the first FV a source would assign, on that source's
own scale (T2).

A port of the research lane PG2_pregrade_signals (build_frame.py, model.py,
prospective.py) with repo-relative paths. It reads GRADES and MiLB / draft caches only:
prospects.db snapshots (read-only), .cache/milb_stats, .cache/draft_history,
.cache/draft_bonus, the identity maps and the two AAA Statcast artifacts. It never reads
WAR (the lane's incumbent column, a refit of the WAR-trained efv_ungraded model, is not
ported; it was never a FULL feature), and no stratum here is named after a consensus-FV
cell (docs/PROSPECT_ANCHOR_GATE.md).

UNIVERSE (per anchor). mlbam ids with a non-MLB MiLB line (sports 11-16) in the feature
season, no MLB line in any season up to it, feature-season age 25 or under, and no
label-source opinion (FanGraphs, MLB Pipeline incl. international, Baseball America,
ESPN, Just Baseball) dated on or before the anchor. A two-way player sits on the side
with more exposure.

ANCHORS. Oct 15 of year y (feature season y, complete; the lane's anchor) and Jun 1 of
year y (feature season y-1, the last complete one; the data hold season totals only, so a
Jun 1 anchor never sees a partial season). 2020 had no MiLB season: the Oct 2020 anchor
and the Jun 2021 anchor (which would read 2020) are skipped. Windows: Oct anchor W6 to
Apr 15 and W12 to Oct 15 of y+1; Jun anchor W6 to Dec 1 of y and W12 to Jun 1 of y+1.
The served anchor is the latest one whose feature season is complete on the run date
(an Oct anchor from Sep 25 of its year, the date the 2026-09-25 freeze was built).

LABELS. A set's first grade is its earliest opinion; an opinion's date is
min(snapshot_date, UTC date of inserted_at), the label-dating repair of
provisional_track.py (the daily Pipeline Top 30 capture bumps snapshot_date in place).
First FV is the mean FV of that set's rows on the first date; FanGraphs 35+ / 40+ code
as the half step (+2.5). Opinions dated after the run date are never read.

T1 (selection). P(first grade from the set within the window), sets ANY / FG / MLBP x
windows W6 / W12, one LightGBM classifier per side, the fixed PG2 params, on the PG2 FULL
feature set (age-level, pedigree, pre-draft rank, level-relative MiLB production, AAA
Statcast), trained on every anchor of the same type whose window is closed on the run
date. The served P gets one logit intercept shift fitted so the mean forward prediction
on the latest closed anchor equals that anchor's base rate (forward: from the model
trained on the anchors before it). The raw P is kept beside it.

CAPTURE GUARD. A closed anchor is used by a head (training, the shift, the backcast) only
if every source of the head's set that was captured in that head's earlier windows has at
least CAPTURE_FLOOR of its median earlier volume inside this window. The 2026 MLB Pipeline
preseason lists were not captured at publication, so the Oct 2025 anchor's 6-month window
carries 48 Pipeline rows against a median of 1,002 and is left out of the ANY and MLBP W6
heads; dated by capture, its Pipeline base rate reads 0.0005 against 0.021-0.025 before.

T2 (level). Expected first FV given graded, per source, ridge (median impute, standard
scale, alpha 10): FanGraphs on the FULL set without Statcast, MLB Pipeline on age-level
plus production; trained on the same anchor type's rows first graded by that source
within a closed W12 window. Each head speaks its own source's scale. No provisional number
here is on the eFV scale, and nothing here feeds eFV.

ARTIFACTS. data/provisional_v2.json (the served anchor's rows) and
data/provisional_v2_eval.json (forward-chained backcast, labelled BACKCAST: each test
anchor is scored by models trained only on earlier anchors, with the shift fitted on the
anchor before it; plus the reproduction of the frozen 2026-09-25 candidate). Nothing on
the site reads either yet (board section PV-07 waits on owner questions Q1-Q3).

REPRODUCTION. On the lane's own frame (test_fixtures/provisional_v2_pg2_frame_2026-09-25.csv.xz)
the port returns the frozen p_g6 / p_g12 of all 4,163 rows exactly. On the live inputs it
agrees at the level a reseeded bag allows (the eval records both and the seed floor):
LightGBM bagging draws rows by position, and identity repairs made since 2026-09-25 moved a
handful of training rows in or out of the universe.

Run: python provisional_v2.py            build both artifacts (as of today)
     python provisional_v2.py --print    print the served head summary, write nothing
"""
from __future__ import annotations

import collections
import datetime
import glob
import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import unicodedata
import warnings
from pathlib import Path

log = logging.getLogger("provisional_v2")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = ROOT / "prospects.db"
CACHE_DIR = ROOT / ".cache"
OUT_PATH = DATA_DIR / "provisional_v2.json"
EVAL_PATH = DATA_DIR / "provisional_v2_eval.json"
FREEZE_PATH = DATA_DIR / "provisional_freeze" / "FREEZE_provisional_2026-09-25.json"

SCHEMA = 1
MODEL_ID = "provisional_v2"
PORT_VERSION = "pg2-port-1"

SRC_ALL = ("fangraphs", "mlb_pipeline", "mlb_pipeline_international", "baseballamerica", "espn",
           "just_baseball")
SETS = {"ANY": SRC_ALL, "FG": ("fangraphs",), "MLBP": ("mlb_pipeline", "mlb_pipeline_international")}
LR = {"DSL": 0, "CPX": 1, "A": 2, "A+": 3, "AA": 4, "AAA": 5}
SPORT_LV = {11: "AAA", 12: "AA", 13: "A+", 14: "A", 15: "A", 16: "CPX"}
FIRST_YEAR = {"oct": 2018, "jun": 2019}
NO_SEASON = {2020}
SEASON_COMPLETE_MMDD = "09-25"   # the 2026-09-25 freeze was built on the Oct 2026 anchor from this date

#: The fixed PG2 LightGBM params (PREDECLARED.md, model.py P).
PARAMS = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=40, subsample=0.8,
              subsample_freq=1, colsample_bytree=0.8, random_state=7, verbose=-1)
RIDGE_ALPHA = 10.0
#: Label-capture guard. An anchor's window counts as observed for a set only if every source
#: of the set that was captured in earlier windows of that head has at least this share of
#: its median earlier volume (opinion rows dated inside the window). The 2026 MLB Pipeline
#: preseason lists were not captured at publication (48 rows dated Jan 2026 against 1,002 in
#: Jan 2025; the bulk was first captured from May 2026), so the Oct 2025 anchor's W6 window
#: carries almost no Pipeline first grades (base rate 0.0005 against 0.021-0.025 before).
CAPTURE_FLOOR = 0.5
BOOT_B = 1000
BOOT_SEED = 7

# Feature groups, in the lane frame's column order (LightGBM column sampling is by index).
AL = ["age", "lvr", "age_rel", "n_seasons", "n_levels", "maxlvr_y", "lv_gain", "dsl"]
PED = ["drafted", "d_logpick", "d_logbonus", "d_bonus_over_slot", "d_hs", "d_jc", "d_yrs", "d_age", "ifa",
       "first_pro_age"]
DRK = ["d_logrank"]
PROD = ["expo", "p_ops_rel", "p_obp_rel", "p_iso_rel", "p_k_rel", "p_bb_rel", "p_sb_rel", "p_gs_share",
        "pp_ops_rel", "pp_k_rel", "p_kbb_rel", "p_era_rel", "pp_kbb_rel", "pp_era_rel"]
MOD = ["m_xwoba", "m_ev", "m_hh", "m_brl", "m_fb_velo", "m_fb_ivb", "m_ext", "m_ast_max", "m_npitch"]
FULL = AL + PED + DRK + PROD + MOD
T1_HEADS = [(s, w) for s in ("ANY", "FG", "MLBP") for w in ("W6", "W12")]
T2_HEADS = {
    "FG": {"features": AL + PED + DRK + PROD + ["side_pit"],
           "scale": "FanGraphs FV scale; 35+ / 40+ coded as the half step (35+ = 37.5)"},
    "MLBP": {"features": AL + PROD + ["side_pit"],
             "scale": "MLB Pipeline FV scale (incl. international lists)"},
}
HK = ["ops", "obp", "iso", "k", "bb", "sb"]
PK = ["k", "bb", "kbb", "era"]


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ip(v):
    v = _f(v) or 0.0
    w = int(v)
    return w + (v - w) * 10 / 3


def _agg(rows, side):
    def s(k):
        return sum(_f(r.get(k)) or 0 for r in rows)
    if side == "hit":
        pa, ab = s("pa"), s("ab")
        if pa <= 0:
            return None
        h, d2, d3, hr, bb, hbp, sf, so, sb = (s("h"), s("doubles"), s("triples"), s("hr"), s("bb"),
                                              s("hbp"), s("sf"), s("so"), s("sb"))
        tb = h + d2 + 2 * d3 + 3 * hr
        obp = (h + bb + hbp) / max(1, ab + bb + hbp + sf)
        slg = tb / max(1, ab)
        return {"pa": pa, "obp": obp, "slg": slg, "ops": obp + slg, "iso": slg - h / max(1, ab),
                "k": so / pa, "bb": bb / pa, "sb": sb / pa}
    bf = s("bf")
    if bf <= 0:
        return None
    ip = sum(_ip(r.get("ip")) for r in rows)
    er = sum((_f(r.get("era")) or 0) * _ip(r.get("ip")) / 9 for r in rows)
    so, bb, g, gs = s("so"), s("bb"), s("g"), s("gs")
    return {"bf": bf, "k": so / bf, "bb": bb / bf, "kbb": (so - bb) / bf,
            "era": 9 * er / ip if ip > 0 else None, "gs_share": gs / g if g else 0.0}


def _slug(n):
    n = unicodedata.normalize("NFKD", n or "").encode("ascii", "ignore").decode().lower()
    n = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", n)
    return re.sub(r"[^a-z0-9]+", "_", n).strip("_")


def _ro_db(db_path):
    return sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)


# ---------------------------------------------------------------------------
# inputs (loaded once; the as-of cut is applied later)

class Inputs:
    """MiLB lines, league norms, the draft universe, identity and raw opinions."""

    def __init__(self, *, data_dir=None, cache_dir=None, db_path=None):
        self.data_dir = Path(data_dir) if data_dir is not None else DATA_DIR
        self.cache_dir = Path(cache_dir) if cache_dir is not None else CACHE_DIR
        self.db_path = Path(db_path) if db_path is not None else DB_PATH
        from efv_dataset import _TYPICAL_LEVEL_AGE
        self.typ = dict(_TYPICAL_LEVEL_AGE)
        self._load_lines()
        self._load_norms()
        self._load_draft()
        self._load_statcast()
        self._load_identity()
        self._load_opinions()

    # ---- MiLB season lines (the lean cache, read directly)
    def _load_lines(self):
        lines = collections.defaultdict(list)
        mlb = collections.defaultdict(set)
        names = {}
        slugs = collections.defaultdict(set)   # name slug -> mlbam ids (identity fallback)
        files = []
        for side, grp in (("hit", "hitting"), ("pit", "pitching")):
            for fp in glob.glob(str(self.cache_dir / "milb_stats" / f"{grp}_*_*.json")):
                sp, season = os.path.basename(fp)[:-5].split("_")[1:]
                sp, season = int(sp), int(season)
                files.append(os.path.basename(fp))
                for r in json.load(open(fp, encoding="utf-8")):
                    m = r.get("mlbam")
                    if not m:
                        continue
                    m = int(m)
                    if r.get("name"):
                        slugs[_slug(r["name"])].add(m)
                    if sp == 1:
                        mlb[m].add(season)
                        continue
                    lv = SPORT_LV[sp]
                    if sp == 16:
                        lv = "DSL" if (r.get("league") or "").upper() in ("DSL", "VSL") else "CPX"
                    r = dict(r)
                    r["lv"] = lv
                    lines[(m, season, side)].append(r)
                    names[m] = r.get("name")
        self.lines, self.mlb_seasons, self.names, self.slugs = lines, mlb, names, slugs
        self.n_line_files = len(files)
        self.seasons = sorted({s for (_, s, _) in lines})

    def _load_norms(self):
        bylv = collections.defaultdict(list)
        for (m, season, side), rows in self.lines.items():
            for lv in {r["lv"] for r in rows}:
                a = _agg([r for r in rows if r["lv"] == lv], side)
                if a:
                    bylv[(season, lv, side)].append(a)
        norms = {}
        for key, L in bylv.items():
            side = key[2]
            ex = "pa" if side == "hit" else "bf"
            norms[key] = {}
            for k in (HK if side == "hit" else PK):
                num = sum(a[k] * a[ex] for a in L if a.get(k) is not None)
                den = sum(a[ex] for a in L if a.get(k) is not None)
                norms[key][k] = num / den if den else None
        self.norms = norms
        self._blocks = {}

    def season_block(self, m, season, side):
        key = (m, season, side)
        if key in self._blocks:
            return self._blocks[key]
        self._blocks[key] = out = self._season_block(m, season, side)
        return out

    def _season_block(self, m, season, side):
        rows = self.lines.get((m, season, side))
        if not rows:
            return None
        ex = "pa" if side == "hit" else "bf"
        floor = 50 if side == "hit" else 60
        per = {lv: _agg([r for r in rows if r["lv"] == lv], side)
               for lv in sorted({r["lv"] for r in rows}, key=LR.get)}
        per = {k: v for k, v in per.items() if v}
        if not per:
            return None
        ok = [lv for lv in per if per[lv][ex] >= floor]
        # Below the floor the most-exposed level wins; a tie goes to the higher level. The
        # lane broke ties by string-set order, which moves with PYTHONHASHSEED (20 of
        # 71,547 rows differed between two runs); the frozen frame is one such draw.
        lv = max(ok, key=lambda x: LR[x]) if ok else max(per, key=lambda x: (per[x][ex], LR[x]))
        a = per[lv]
        nm = self.norms.get((season, lv, side), {})
        w = a[ex] / (a[ex] + 150.0)
        rel = {}
        for key in (HK if side == "hit" else PK):
            if a.get(key) is not None and nm.get(key) is not None:
                rel[key + "_rel"] = w * (a[key] - nm[key])
        age = next((_f(r.get("age")) for r in rows if r["lv"] == lv and r.get("age") is not None), None)
        return {"lv": lv, "lvr": LR[lv], "age": age, "expo": sum(v[ex] for v in per.values()),
                "n_levels": len(per), "maxlvr": max(LR[x] for x in per), "gs_share": a.get("gs_share"), **rel}

    # ---- draft universe
    def _load_draft(self):
        draft = {}
        for fp in sorted(glob.glob(str(self.cache_dir / "draft_history" / "*.json"))):
            y = int(os.path.basename(fp)[:4])
            if y >= 2017:
                continue
            for r in json.load(open(fp, encoding="utf-8")):
                if r.get("mlbam"):
                    draft.setdefault(int(r["mlbam"]), []).append({"year": y, "pick": r.get("pick")})
        for fp in sorted(glob.glob(str(self.cache_dir / "draft_bonus" / "*.json"))):
            d = json.load(open(fp, encoding="utf-8"))
            y = int(d["drafts"]["draftYear"])
            for rd in d["drafts"]["rounds"]:
                for p in rd["picks"]:
                    pe = p.get("person") or {}
                    if not pe.get("id"):
                        continue
                    sc = ((p.get("school") or {}).get("schoolClass") or "").upper()
                    draft.setdefault(int(pe["id"]), []).append({
                        "year": y, "pick": p.get("pickNumber"), "round": p.get("pickRound"),
                        "bonus": _f(p.get("signingBonus")), "slot": _f(p.get("pickValue")),
                        "hs": (1.0 if sc.startswith("HS") else 0.0) if sc else None,
                        "jc": (1.0 if "JC" in sc else 0.0) if sc else None,
                        "rank": p.get("rank"), "birth": pe.get("birthDate"),
                        "name": pe.get("fullName")})
        self.draft = draft

    # ---- AAA Statcast (MOD)
    def _load_statcast(self):
        try:
            self.phys = json.loads((self.data_dir / "aaa_physics.json").read_text(encoding="utf-8"))["players"]
        except (OSError, ValueError, KeyError):
            log.warning("provisional_v2: aaa_physics.json unreadable; pitch physics columns empty")
            self.phys = {}
        try:
            self.aaah = json.loads((self.data_dir / "statcast_aaa_hitters.json").read_text(
                encoding="utf-8"))["by_mlbam"]
        except (OSError, ValueError, KeyError):
            log.warning("provisional_v2: statcast_aaa_hitters.json unreadable; hitter Statcast empty")
            self.aaah = {}

    def mod_pit(self, m, y):
        e = (self.phys.get(str(m)) or {}).get(str(y))
        if not e:
            return {}
        bt = e.get("by_type") or {}
        fb = [v for k, v in bt.items() if k in ("FF", "SI") and (v.get("n_pitches") or 0) >= 30]
        ast = [v.get("astuff") for v in bt.values()
               if (v.get("n_pitches") or 0) >= 50 and v.get("astuff") is not None]
        return {"m_fb_velo": max((v.get("velo") or 0) for v in fb) if fb else None,
                "m_fb_ivb": max((v.get("ivb") if v.get("ivb") is not None else -99) for v in fb) if fb else None,
                "m_ext": e.get("ext"), "m_ast_max": max(ast) if ast else None, "m_npitch": e.get("n_pitches")}

    def mod_hit(self, m, y):
        e = self.aaah.get(str(m))
        if not e or int(e.get("season") or 0) != y:
            return {}
        return {"m_xwoba": e.get("xwoba"), "m_ev": e.get("ev"), "m_hh": e.get("hardhit_percent"),
                "m_brl": e.get("barrels_per_bbe_percent")}

    # ---- identity: snapshot player_key -> mlbam (lane identity.py)
    def _load_identity(self):
        k2m, how = {}, {}

        def put(k, m, h):
            if k and m and k not in k2m:
                try:
                    k2m[k] = int(m)
                    how[k] = h
                except (TypeError, ValueError):
                    pass

        def _json(name):
            try:
                return json.loads((self.data_dir / name).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                log.warning("provisional_v2: %s unreadable; identity map thinner", name)
                return None

        con = _ro_db(self.db_path)
        try:
            for pk, pj in con.execute("select player_key, payload_json from statlines"):
                try:
                    put(pk, json.loads(pj).get("mlbam_id"), "statlines")
                except (ValueError, TypeError, AttributeError):
                    pass
            for r in (_json("debuts.json") or []):
                put(r.get("player_key"), r.get("mlbam_id"), "debuts")
            for r in ((_json("timeseries.json") or {}).get("players") or []):
                put(r.get("player_key"), r.get("mlbam_id"), "timeseries")
            for k, e in ((_json("xfv.json") or {}).get("by_player") or {}).items():
                put(k, e.get("mlbam_id"), "xfv")
            for _org, lv in (_json("rosters_by_org.json") or {}).items():
                for _level, ps in (lv or {}).items():
                    if isinstance(ps, list):
                        for p in ps:
                            put(p.get("player_key"), p.get("mlbam_id"), "rosters")
            for pk, m in con.execute("select promoted_key, mlbam_id from draft_players "
                                     "where promoted_key is not null"):
                put(pk, m, "draft_players")
            for t in ("zone_metrics", "statcast_metrics"):
                for pk, pj in con.execute(f"select player_key, payload_json from {t}"):
                    try:
                        put(pk, json.loads(pj).get("mlbam_id"), t)
                    except (ValueError, TypeError, AttributeError):
                        pass
            # unique full-name slug within the MiLB / MLB / draft universe; a slug that maps
            # to two or more mlbam ids is dropped (lane identity.py)
            names = collections.defaultdict(set, {k: set(v) for k, v in self.slugs.items()})
            for m, L in self.draft.items():
                for d in L:
                    if d.get("name"):
                        names[_slug(d["name"])].add(m)
            uniq = {s: next(iter(v)) for s, v in names.items() if len(v) == 1}
            q = ("select distinct player_key, player_name from snapshots where source in (%s) "
                 "and (fv is not null or rank is not null)" % ",".join("?" * len(SRC_ALL)))
            graded = {}
            for pk, nm in con.execute(q, SRC_ALL):
                graded.setdefault(pk, nm)
        finally:
            con.close()
        res = collections.Counter()
        for pk, nm in graded.items():
            if pk in k2m:
                res["mapped:" + how[pk]] += 1
                continue
            s = _slug(nm)
            if s in uniq:
                k2m[pk] = uniq[s]
                how[pk] = "name_unique"
                res["mapped:name_unique"] += 1
            elif s in names and len(names[s]) > 1:
                res["unmapped:ambiguous_name"] += 1
            else:
                res["unmapped:no_name"] += 1
        self.k2m, self.k2m_how = k2m, how
        self.identity_coverage = {"graded_keys": len(graded), **dict(sorted(res.items()))}

    # ---- opinions (raw; cut by as_of later)
    def _load_opinions(self):
        con = _ro_db(self.db_path)
        try:
            q = ("select player_key, source, snapshot_date, substr(inserted_at, 1, 10), fv, fv_plus, rank "
                 "from snapshots where source in (%s) and (fv is not null or rank is not null)"
                 % ",".join("?" * len(SRC_ALL)))
            ev = collections.defaultdict(list)
            days = collections.Counter()          # (source, day) -> rows, mapped or not (capture volume)
            for pk, src, d, ins, fv, fvp, rk in con.execute(q, SRC_ALL):
                day = min(d, ins) if ins else d
                days[(src, day)] += 1
                if pk not in self.k2m:
                    continue
                fvv = None if fv is None else fv + (2.5 if (src == "fangraphs" and fvp) else 0.0)
                ev[self.k2m[pk]].append((day, src, fvv, rk))
        finally:
            con.close()
        self.ev_raw = ev
        self.src_days = days


# ---------------------------------------------------------------------------
# anchors

def _anchor(atype, y):
    """(anchor date, feature season, W6 end, W12 end) or None when the anchor is skipped."""
    if atype == "oct":
        if y in NO_SEASON:
            return None
        return f"{y}-10-15", y, f"{y + 1}-04-15", f"{y + 1}-10-15"
    fs = y - 1
    if fs in NO_SEASON:
        return None
    return f"{y}-06-01", fs, f"{y}-12-01", f"{y + 1}-06-01"


def window_end(atype, y, window):
    a = _anchor(atype, y)
    return a[2] if window == "W6" else a[3]


def serving_anchor(as_of: str):
    """The latest anchor whose feature season is complete on as_of: ("oct" | "jun", y)."""
    y = int(as_of[:4])
    cands = []
    for yy in (y - 1, y):
        if _anchor("oct", yy) and f"{yy}-{SEASON_COMPLETE_MMDD}" <= as_of:
            cands.append((f"{yy}-{SEASON_COMPLETE_MMDD}", "oct", yy))
        if _anchor("jun", yy) and f"{yy}-06-01" <= as_of:
            cands.append((f"{yy}-06-01", "jun", yy))
    _, atype, yy = max(cands)
    return atype, yy


def anchor_years(atype, through_year):
    return [y for y in range(FIRST_YEAR[atype], through_year + 1) if _anchor(atype, y)]


def available_anchors(as_of: str) -> list[tuple[str, int]]:
    """Every anchor whose feature season is complete on as_of, Oct anchors first."""
    y = int(as_of[:4])
    out = [("oct", yy) for yy in anchor_years("oct", y) if f"{yy}-{SEASON_COMPLETE_MMDD}" <= as_of]
    out += [("jun", yy) for yy in anchor_years("jun", y) if f"{yy}-06-01" <= as_of]
    return out


# ---------------------------------------------------------------------------
# the frame

def opinions_as_of(inp: Inputs, as_of: str):
    """mlbam -> opinions dated on or before as_of; and per (mlbam, set) the first grade."""
    ev = {m: [x for x in L if x[0] <= as_of] for m, L in inp.ev_raw.items()}
    ev = {m: L for m, L in ev.items() if L}
    first = {}
    import numpy as np
    for m, L in ev.items():
        for s, srcs in SETS.items():
            LL = [x for x in L if x[1] in srcs]
            if not LL:
                continue
            d0 = min(x[0] for x in LL)
            fvs = [x[2] for x in LL if x[0] == d0 and x[2] is not None]
            first[(m, s)] = (d0, float(np.mean(fvs)) if fvs else None)
    return ev, first


def build_frame(inp: Inputs, as_of: str, anchors: list[tuple[str, int]]):
    """One row per (anchor, player) in the universe, the lane's feature construction."""
    import pandas as pd
    ev, first = opinions_as_of(inp, as_of)
    out = []
    all_m = {m for (m, s, sd) in inp.lines}
    for atype, y in anchors:
        a = _anchor(atype, y)
        if a is None:
            continue
        A, fs, g6, g12 = a
        for side in ("hit", "pit"):
            other = "pit" if side == "hit" else "hit"
            for m in all_m:
                cur = inp.season_block(m, fs, side)
                if not cur:
                    continue
                ob = inp.season_block(m, fs, other)
                if ob and (ob["expo"] > cur["expo"] or (ob["expo"] == cur["expo"] and side == "pit")):
                    continue
                if any(s <= fs for s in inp.mlb_seasons.get(m, ())):
                    continue
                if cur["age"] is not None and cur["age"] > 25:
                    continue
                ops = ev.get(m, [])
                if any(x[0] <= A for x in ops):
                    continue                      # an opinion on or before the anchor: not in the universe
                prev = inp.season_block(m, fs - 1, side) or (
                    inp.season_block(m, fs - 2, side) if fs - 1 in NO_SEASON else None)
                seasons = [s for s in range(2005, fs + 1) if inp.lines.get((m, s, side))]
                first_s = min(seasons)
                fb_age = next((_f(r.get("age")) for r in inp.lines[(m, first_s, side)]
                               if r.get("age") is not None), None)
                dr = [d for d in inp.draft.get(m, []) if d["year"] <= fs]
                dr = max(dr, key=lambda d: d["year"]) if dr else None
                row = {"mlbam": m, "name": inp.names.get(m), "atype": atype, "y": y, "anchor": A, "fs": fs,
                       "side": side, "age": cur["age"], "lvr": cur["lvr"],
                       "age_rel": (cur["age"] - inp.typ[cur["lv"]]) if cur["age"] is not None else None,
                       "n_seasons": len(seasons), "n_levels": cur["n_levels"], "maxlvr_y": cur["maxlvr"],
                       "lv_gain": (cur["lvr"] - prev["lvr"]) if prev else None,
                       "dsl": 1.0 if cur["lv"] == "DSL" else 0.0,
                       "expo": cur["expo"], "lv": cur["lv"],
                       "drafted": 1.0 if dr else 0.0,
                       "d_logpick": math.log(dr["pick"]) if dr and dr.get("pick") else None,
                       "d_logbonus": math.log(dr["bonus"]) if dr and dr.get("bonus") else None,
                       "d_bonus_over_slot": (dr["bonus"] / dr["slot"]) if dr and dr.get("bonus") and dr.get("slot") else None,
                       "d_hs": dr.get("hs") if dr else None, "d_jc": dr.get("jc") if dr else None,
                       "d_yrs": (fs - dr["year"]) if dr else None,
                       "d_age": (dr["year"] - int(dr["birth"][:4])) if dr and dr.get("birth") else None,
                       "d_logrank": math.log(dr["rank"]) if dr and dr.get("rank") else None,
                       "ifa": 1.0 if (not inp.draft.get(m) and fb_age is not None and fb_age <= 18) else 0.0,
                       "first_pro_age": fb_age}
                for k, v in cur.items():
                    if k.endswith("_rel"):
                        row["p_" + k] = v
                row["p_gs_share"] = cur.get("gs_share") if side == "pit" else None
                if prev:
                    for k in (("ops_rel", "k_rel") if side == "hit" else ("kbb_rel", "era_rel")):
                        row["pp_" + k] = prev.get(k)
                row.update(inp.mod_pit(m, fs) if side == "pit" else inp.mod_hit(m, fs))
                for s in SETS:
                    fg = first.get((m, s))
                    row[f"G6_{s}"] = 1 if (fg and A < fg[0] <= g6) else 0
                    row[f"G12_{s}"] = 1 if (fg and A < fg[0] <= g12) else 0
                    row[f"FV1_{s}"] = fg[1] if (fg and A < fg[0] <= g12) else None
                    row[f"T1_{s}"] = fg[0] if (fg and A < fg[0] <= g12) else None
                out.append(row)
    df = pd.DataFrame(out)
    for c in FULL + ["side_pit"]:
        if c not in df.columns:
            df[c] = float("nan")
    df["side_pit"] = (df.side == "pit").astype(float)
    return df


# ---------------------------------------------------------------------------
# models

def _lab(set_, window):
    return f"{'G6' if window == 'W6' else 'G12'}_{set_}"


def _closed_years(df, atype, window, as_of, before=None):
    ys = sorted(df.loc[df.atype == atype, "y"].unique())
    out = [int(y) for y in ys if window_end(atype, int(y), window) <= as_of]
    return [y for y in out if before is None or y < before]


def window_volume(src_days, src, atype, y, window, as_of):
    """Opinion rows from one source dated inside an anchor's window (after the anchor, on or
    before the window end and the run date)."""
    A = _anchor(atype, y)[0]
    end = min(window_end(atype, y, window), as_of)
    return sum(n for (s, d), n in src_days.items() if s == src and A < d <= end)


def usable_years(df, src_days, atype, set_, window, as_of):
    """Closed anchors of the head whose window was captured for every source of the set
    (CAPTURE_FLOOR); returns (years, {year: reason} for the closed anchors left out)."""
    closed = _closed_years(df, atype, window, as_of)
    keep, dropped = [], {}
    vols = {src: [] for src in SETS[set_]}
    for y in closed:
        short = []
        for src in SETS[set_]:
            v = window_volume(src_days, src, atype, y, window, as_of)
            prior = sorted(x for x in vols[src] if x > 0)
            if prior:
                med = prior[len(prior) // 2] if len(prior) % 2 else (prior[len(prior) // 2 - 1] + prior[len(prior) // 2]) / 2
                if v < CAPTURE_FLOOR * med:
                    short.append(f"{src} {v} rows against an earlier median of {med:g}")
            vols[src].append(v)
        if short:
            dropped[int(y)] = "label capture gap: " + "; ".join(short)
        else:
            keep.append(int(y))
    return keep, dropped


def fit_t1(tr, label, seed=None):
    """Per-side LightGBM classifiers on FULL; returns {side: model or constant}."""
    import lightgbm as lgb
    params = dict(PARAMS) if seed is None else dict(PARAMS, random_state=seed)
    models = {}
    for side in ("hit", "pit"):
        t = tr[tr.side == side]
        if len(t) == 0:
            continue
        if t[label].sum() < 5:
            models[side] = float(t[label].mean())
            continue
        models[side] = lgb.LGBMClassifier(**params).fit(t[FULL].astype(float), t[label])
    return models


def predict_t1(models, te):
    import numpy as np
    p = np.full(len(te), np.nan)
    for side, m in models.items():
        msk = (te.side == side).values
        if not msk.any():
            continue
        if isinstance(m, float):
            p[msk] = m
        else:
            p[msk] = m.predict_proba(te.loc[msk, FULL].astype(float))[:, 1]
    return p


def _logit(p):
    import numpy as np
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _sigmoid(x):
    import numpy as np
    return 1.0 / (1.0 + np.exp(-x))


def fit_shift(p, y):
    """Logit intercept shift that makes the mean prediction equal the observed base rate."""
    import numpy as np
    from scipy.optimize import brentq
    z = _logit(p)
    rate = float(np.mean(y))
    if rate <= 0 or rate >= 1:
        return 0.0
    return float(brentq(lambda d: float(np.mean(_sigmoid(z + d))) - rate, -20.0, 20.0))


def apply_shift(p, delta):
    return _sigmoid(_logit(p) + delta)


def fit_t2(tr, cols, label):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    cols = [c for c in cols if c in tr.columns and tr[c].notna().any()]
    if not cols or len(tr) < 30:
        return ("const", float(tr[label].mean()), cols)
    m = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=RIDGE_ALPHA))
    m.fit(tr[cols].astype(float), tr[label])
    return ("ridge", m, cols)


def predict_t2(model, te):
    import numpy as np
    kind, m, cols = model
    if kind == "const":
        return np.full(len(te), m)
    return m.predict(te[cols].astype(float))


def _t2_rows(df, atype, set_, years):
    lab = f"FV1_{set_}"
    return df[(df.atype == atype) & df.y.isin(years) & (df[f"G12_{set_}"] == 1) & df[lab].notna()]


# ---------------------------------------------------------------------------
# metrics

def _clf(y, p):
    import numpy as np
    from sklearn.metrics import average_precision_score, roc_auc_score
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    out = {"n": int(len(y)), "pos": int(y.sum()), "base_rate": round(float(y.mean()), 4) if len(y) else None}
    if 0 < y.sum() < len(y):
        out["auc"] = round(float(roc_auc_score(y, p)), 4)
        out["ap"] = round(float(average_precision_score(y, p)), 4)
    return out


def _brier(y, p):
    import numpy as np
    return round(float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2)), 5)


def _cluster_boot(ids, B=BOOT_B, seed=BOOT_SEED):
    import numpy as np
    rng = np.random.default_rng(seed)
    u, inv = np.unique(ids, return_inverse=True)
    groups = [[] for _ in u]
    for i, g in enumerate(inv):
        groups[g].append(i)
    groups = [np.array(g) for g in groups]
    for _ in range(B):
        pick = rng.integers(0, len(groups), len(groups))
        yield np.concatenate([groups[j] for j in pick])


def _reg(y, pred, const, ids):
    import numpy as np
    from scipy.stats import spearmanr
    y = np.asarray(y, dtype=float)
    pred = np.asarray(pred, dtype=float)
    const = np.asarray(const, dtype=float)
    ea, eb = np.abs(pred - y), np.abs(const - y)
    rho = spearmanr(pred, y).correlation if len(set(np.round(pred, 9))) > 1 else None
    ds = [float(ea[i].mean() - eb[i].mean()) for i in _cluster_boot(ids)]
    return {"n": int(len(y)), "mae": round(float(ea.mean()), 3), "bias": round(float((pred - y).mean()), 3),
            "spearman": None if rho is None or np.isnan(rho) else round(float(rho), 3),
            "share_within_2p5": round(float((ea <= 2.5).mean()), 3),
            "mae_const": round(float(eb.mean()), 3),
            "share_within_2p5_const": round(float((eb <= 2.5).mean()), 3),
            "mae_minus_const": round(float(ea.mean() - eb.mean()), 3),
            "mae_minus_const_ci95": [round(float(np.percentile(ds, 2.5)), 3),
                                     round(float(np.percentile(ds, 97.5)), 3)],
            "mean_label": round(float(y.mean()), 3), "mean_pred": round(float(pred.mean()), 3)}


# ---------------------------------------------------------------------------
# backcast (forward-chained)

def backcast(df, as_of: str, src_days) -> dict:
    """Every test anchor is scored by models trained only on earlier anchors of its type, and
    its served P is shifted by the delta fitted on the anchor before it (whose own forward
    predictions came from the anchors before that). Only closed windows are scored."""
    import numpy as np
    out = {}
    for atype in ("oct", "jun"):
        sub = df[df.atype == atype]
        if sub.empty:
            continue
        res = {"T1": {}, "T2": {}}
        for set_, window in T1_HEADS:
            lab = _lab(set_, window)
            ys, gaps = usable_years(df, src_days, atype, set_, window, as_of)
            fwd = {}
            for i, t in enumerate(ys):
                if i == 0:
                    continue
                tr = sub[sub.y.isin(ys[:i])]
                te = sub[sub.y == t]
                fwd[t] = (te, predict_t1(fit_t1(tr, lab), te))
            test = [t for i, t in enumerate(ys) if i >= 2]
            if not test:
                continue
            by_year = {}
            Y, PR, PS, LV, AG, SD, ID = [], [], [], [], [], [], []
            for t in test:
                L = ys[ys.index(t) - 1]
                teL, pL = fwd[L]
                delta = fit_shift(pL, teL[lab].values)
                te, p = fwd[t]
                ps = apply_shift(p, delta)
                y = te[lab].values
                m = _clf(y, p)
                m.update({"shift_from_anchor": int(L), "shift_logit": round(delta, 4),
                          "sum_p_raw": round(float(p.sum()), 1), "sum_p_shifted": round(float(ps.sum()), 1),
                          "brier_raw": _brier(y, p), "brier_shifted": _brier(y, ps),
                          "train_anchors": [int(x) for x in ys[:ys.index(t)]]})
                by_year[str(t)] = m
                Y.append(y); PR.append(p); PS.append(ps); LV.append(te.lvr.values)
                AG.append(-te.age.fillna(te.age.median()).values); SD.append(te.side.values)
                ID.append(te.mlbam.values)
            y, p, ps = np.concatenate(Y), np.concatenate(PR), np.concatenate(PS)
            lv, ag, sd = np.concatenate(LV), np.concatenate(AG), np.concatenate(SD)
            pooled = _clf(y, p)
            pooled.update({"sum_p_raw": round(float(p.sum()), 1), "sum_p_shifted": round(float(ps.sum()), 1),
                           "brier_raw": _brier(y, p), "brier_shifted": _brier(y, ps),
                           "brier_const_realized_rate": _brier(y, np.full(len(y), y.mean())),
                           "null_level_rank_auc": _clf(y, lv).get("auc"),
                           "null_younger_auc": _clf(y, ag).get("auc"),
                           "by_side_auc": {s: _clf(y[sd == s], p[sd == s]).get("auc") for s in ("hit", "pit")}})
            k = int(y.sum())
            if k:
                top = np.argsort(-p)[:k]
                pooled["prec_at_k"] = round(float(y[top].mean()), 4)
            res["T1"][f"{set_}_{window}"] = {"label": lab, "window_rule": _window_rule(atype, window),
                                             "test_anchors": [int(t) for t in test],
                                             "anchors_left_out": {str(k): v for k, v in gaps.items()},
                                             "pooled": pooled, "by_anchor": by_year}
        for set_, spec in T2_HEADS.items():
            ys, gaps = usable_years(df, src_days, atype, set_, "W12", as_of)
            test = [t for i, t in enumerate(ys) if i >= 2]
            parts = []
            for t in test:
                tr = _t2_rows(df, atype, set_, ys[:ys.index(t)])
                te = _t2_rows(df, atype, set_, [t])
                if len(te) == 0 or len(tr) < 30:
                    continue
                te = te.copy()
                te["_pred"] = predict_t2(fit_t2(tr, spec["features"], f"FV1_{set_}"), te)
                te["_const"] = float(tr[f"FV1_{set_}"].mean())
                parts.append(te)
            if not parts:
                continue
            import pandas as pd
            r = pd.concat(parts)
            lab = f"FV1_{set_}"
            res["T2"][set_] = {"scale": spec["scale"], "features": spec["features"], "estimator": f"ridge alpha {RIDGE_ALPHA}",
                               "test_anchors": [int(t) for t in sorted(r.y.unique())],
                               "anchors_left_out": {str(k): v for k, v in gaps.items()},
                               "pooled": _reg(r[lab].values, r["_pred"].values, r["_const"].values, r.mlbam.values),
                               "by_side": {s: {"n": int((r.side == s).sum()),
                                               "mae": round(float((r[r.side == s]["_pred"] - r[r.side == s][lab]).abs().mean()), 3),
                                               "mae_const": round(float((r[r.side == s]["_const"] - r[r.side == s][lab]).abs().mean()), 3)}
                                           for s in ("hit", "pit") if (r.side == s).any()},
                               "label_dist": {str(k): int(v) for k, v in r[lab].round(1).value_counts().sort_index().items()}}
        out[atype] = res
    return out


def _window_rule(atype, window):
    if atype == "oct":
        return ("first grade after Oct 15 of y and on or before Apr 15 of y+1" if window == "W6"
                else "first grade after Oct 15 of y and on or before Oct 15 of y+1")
    return ("first grade after Jun 1 of y and on or before Dec 1 of y" if window == "W6"
            else "first grade after Jun 1 of y and on or before Jun 1 of y+1")


# ---------------------------------------------------------------------------
# serving

def serve(df, as_of: str, atype: str, y: int, src_days) -> tuple[list[dict], dict]:
    """Score the served anchor's universe with heads trained on every closed anchor of its type."""
    import numpy as np
    te = df[(df.atype == atype) & (df.y == y)].copy()
    sub = df[df.atype == atype]
    heads = {}
    for set_, window in T1_HEADS:
        lab = _lab(set_, window)
        ys, gaps = usable_years(df, src_days, atype, set_, window, as_of)
        ys = [t for t in ys if t < y]
        p = predict_t1(fit_t1(sub[sub.y.isin(ys)], lab), te)
        # recency shift: forward predictions on the latest closed anchor
        L = ys[-1]
        trL = sub[sub.y.isin(ys[:-1])]
        teL = sub[sub.y == L]
        delta = fit_shift(predict_t1(fit_t1(trL, lab), teL), teL[lab].values)
        ps = apply_shift(p, delta)
        key = f"{set_}_{window}"
        te[f"p_{key.lower()}"] = ps
        te[f"p_{key.lower()}_raw"] = p
        heads[key] = {"label": lab, "window_end": window_end(atype, y, window),
                      "window_rule": _window_rule(atype, window), "train_anchors": ys,
                      "anchors_left_out": {str(k): v for k, v in gaps.items()},
                      "shift_anchor": int(L), "shift_anchor_base_rate": round(float(teL[lab].mean()), 4),
                      "shift_logit": round(delta, 4), "sum_p_raw": round(float(p.sum()), 1),
                      "sum_p_served": round(float(ps.sum()), 1)}
    for set_ in SETS:
        k6, k12 = f"p_{set_.lower()}_w6_raw", f"p_{set_.lower()}_w12_raw"
        if len(te) and np.allclose(te[k6].values, te[k12].values):
            heads[f"{set_}_W6"]["note"] = (
                "identical to W12: in every usable training anchor this set's first grades within 12 "
                "months all fell inside the first 6, so the two heads learn the same labels")
    t2 = {}
    for set_, spec in T2_HEADS.items():
        ys, gaps = usable_years(df, src_days, atype, set_, "W12", as_of)
        ys = [t for t in ys if t < y]
        tr = _t2_rows(df, atype, set_, ys)
        model = fit_t2(tr, spec["features"], f"FV1_{set_}")
        pred = predict_t2(model, te)
        te[f"fv_first_{set_.lower()}"] = pred
        t2[set_] = {"scale": spec["scale"], "features": model[2], "estimator": f"{model[0]} alpha {RIDGE_ALPHA}",
                    "train_anchors": ys, "anchors_left_out": {str(k): v for k, v in gaps.items()},
                    "n_train": int(len(tr)),
                    "train_label_mean": round(float(tr[f"FV1_{set_}"].mean()), 3) if len(tr) else None,
                    "served_mean": round(float(np.mean(pred)), 3) if len(pred) else None,
                    "served_min": round(float(np.min(pred)), 3) if len(pred) else None,
                    "served_max": round(float(np.max(pred)), 3) if len(pred) else None}
    rows = []
    pcols = [f"p_{s.lower()}_{w.lower()}" for s, w in T1_HEADS]
    te = te.sort_values(["p_any_w12", "mlbam"], ascending=[False, True])
    for _, r in te.iterrows():
        row = {"mlbam": int(r.mlbam), "name": r["name"], "side": r.side, "age": _r(r.age, 1), "level": r.lv,
               "expo": int(r.expo) if r.expo == r.expo else None}
        for c in pcols:
            row[c] = _r(r[c], 4)
        for c in ("p_any_w6", "p_any_w12"):             # the freeze's columns are raw ANY P
            row[c + "_raw"] = _r(r[c + "_raw"], 4)
        for s in T2_HEADS:
            row[f"fv_first_{s.lower()}"] = _r(r[f"fv_first_{s.lower()}"], 2)
        rows.append(row)
    return rows, {"T1": heads, "T2": t2}


def _r(v, n):
    try:
        if v is None or v != v:
            return None
        return round(float(v), n)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# reproduction of the frozen 2026-09-25 candidate

FREEZE_AS_OF = "2026-09-24"   # the freeze's universe: ungraded by any source as of 2026-09-24
#: The lane's own frame (work/frame.pkl, sha256 c78211da...566df), cut to the ANY-ungraded
#: universe, the FULL columns and the two ANY labels, in the lane's row order, written at full
#: float precision. Rows are (y, side, mlbam). It lets the port be checked against the frozen
#: object itself: LightGBM bagging draws rows by position, so one inserted or removed training
#: row reshuffles every bag after it, and the live inputs have moved since 2026-09-25.
FREEZE_FRAME_PATH = ROOT / "test_fixtures" / "provisional_v2_pg2_frame_2026-09-25.csv.xz"
FREEZE_FRAME_SHA256 = "33c3e9a3fe46be7e1854635b00a29a15a43af11ee8b3427139d124d2d62eec7c"


def load_freeze_frame(path=None):
    import pandas as pd
    df = pd.read_csv(path or FREEZE_FRAME_PATH, float_precision="round_trip")
    df["atype"] = "oct"
    return df


def _repro_scores(df, seed=None):
    """The lane's prospective.py: ANY, raw P, G6 on anchors 2018-2025, G12 on 2018-2024."""
    te = df[df.y == 2026].copy()
    for lab, maxy in (("G6_ANY", 2025), ("G12_ANY", 2024)):
        te[lab.lower()] = predict_t1(fit_t1(df[df.y <= maxy], lab, seed=seed), te)
    return {int(m): (a, b) for m, a, b in zip(te.mlbam, te.g6_any, te.g12_any)}


def _compare(frozen, have, both):
    import numpy as np
    from scipy.stats import spearmanr
    out = {}
    for i, col in ((0, "p_g6"), (1, "p_g12")):
        a = np.array([frozen[m][col] for m in both], dtype=float)
        b = np.array([have[m][i] for m in both], dtype=float)
        out[col] = {"spearman": round(float(spearmanr(a, b).correlation), 4),
                    "max_abs_diff": round(float(np.max(np.abs(a - b))), 4),
                    "median_abs_diff": round(float(np.median(np.abs(a - b))), 5),
                    "sum_frozen": round(float(a.sum()), 1), "sum_port": round(float(b.sum()), 1)}
    return out


def reproduce_freeze(inp: Inputs | None = None, freeze_path=None, frame=None) -> dict:
    """Rebuild the lane's prospective scores and compare them with the frozen p_g6 / p_g12 by
    mlbam. With `frame` (the frozen lane frame) the port is checked on the freeze's own
    inputs; without it, on the live inputs with opinions cut at 2026-09-24."""
    fz = json.loads(Path(freeze_path or FREEZE_PATH).read_text(encoding="utf-8"))
    frozen = {int(r["mlbam"]): r for r in fz["rows"] if r.get("p_g12") is not None and r.get("mlbam")}
    if frame is None:
        inp = inp or Inputs()
        df = build_frame(inp, FREEZE_AS_OF, [("oct", y) for y in anchor_years("oct", 2026)])
        source = "live inputs, opinions cut at " + FREEZE_AS_OF
    else:
        df = frame
        source = "the frozen lane frame " + FREEZE_FRAME_PATH.name
    df = df[df.atype == "oct"]
    have = _repro_scores(df)
    both = sorted(set(frozen) & set(have))
    out = {"inputs": source, "freeze": Path(freeze_path or FREEZE_PATH).name,
           "seed": PARAMS["random_state"], "frozen_rows_with_p": len(frozen), "port_rows": len(have),
           "matched": len(both), "frozen_only": len(set(frozen) - set(have)),
           "port_only": len(set(have) - set(frozen))}
    out.update(_compare(frozen, have, both))
    if frame is None:
        # The bagging floor: the same live frame, the same model, seed 8 against seed 7.
        alt = _repro_scores(df, seed=PARAMS["random_state"] + 1)
        both2 = sorted(set(have) & set(alt))
        fl = _compare({m: {"p_g6": have[m][0], "p_g12": have[m][1]} for m in both2}, alt, both2)
        out["seed_floor"] = {"note": ("the same live frame and model refit with seed 8 against seed 7: "
                                      "the agreement a reshuffled bag alone allows"),
                             "p_g6_spearman": fl["p_g6"]["spearman"], "p_g12_spearman": fl["p_g12"]["spearman"]}
    return out


# ---------------------------------------------------------------------------
# build

def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _write_rows_doc(path: Path, head: dict, rows: list[dict]) -> None:
    """Header keys indented, one row per line (valid JSON, readable diffs)."""
    body = json.dumps(head, indent=1, ensure_ascii=False)
    assert body.endswith("}")
    lines = ",\n".join(" " + json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows)
    text = body[:-1].rstrip() + ',\n "rows": [\n' + lines + "\n ]\n}\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _write_json(path: Path, doc: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def build(persist: bool = True, as_of: str | None = None, *, out_path=None, eval_path=None,
          data_dir=None, cache_dir=None, db_path=None, reproduce: bool = True) -> dict:
    as_of = as_of or datetime.date.today().isoformat()
    warnings.filterwarnings("ignore", category=UserWarning)
    inp = Inputs(data_dir=data_dir, cache_dir=cache_dir, db_path=db_path)
    atype, y = serving_anchor(as_of)
    anchors = available_anchors(as_of)
    df = build_frame(inp, as_of, anchors)
    rows, heads = serve(df, as_of, atype, y, inp.src_days)
    now = _now_iso()
    A, fs, g6, g12 = _anchor(atype, y)
    meta = {
        "schema": SCHEMA, "generated_at": now, "as_of": as_of, "model_id": MODEL_ID,
        "producer": "provisional_v2.py (efv_export.regen_all)", "port_version": PORT_VERSION,
        "spec": ("_finalpass_2026-09-24/provisional/PROVISIONAL_V2.md section 3 (PV-06); ported from lane "
                 "PG2_pregrade_signals build_frame.py, model.py, prospective.py"),
        "anchor": {"type": atype, "year": y, "date": A, "feature_season": fs, "W6_end": g6, "W12_end": g12},
        "universe": ("roster players with a MiLB line in the feature season, age 25 or under, no MLB line, "
                     "and no label-source opinion dated on or before " + as_of),
        "label_sources": list(SRC_ALL),
        "columns": {
            "p_<set>_<window>": ("served P(first grade from the set within the window), recency-shifted; "
                                 "sets any (all label sources), fg (FanGraphs), mlbp (MLB Pipeline incl. "
                                 "international)"),
            "p_any_<window>_raw": "the ANY P before the recency shift (what a freeze keeps); every head's raw total is in heads",
            "fv_first_fg": "expected first FV if FanGraphs grades the player, FanGraphs scale (35+ = 37.5)",
            "fv_first_mlbp": "expected first FV if MLB Pipeline grades the player, Pipeline scale",
        },
        "not_on_efv_scale": True, "feeds_efv": False, "reads_no_war": True,
        "params": dict(PARAMS), "features_t1": list(FULL),
        "heads": heads,
        "n_rows": len(rows),
        "n_by_side": dict(collections.Counter(r["side"] for r in rows)),
        "identity_coverage": inp.identity_coverage,
        "eval_artifact": "data/provisional_v2_eval.json",
    }
    bc = backcast(df, as_of, inp.src_days)
    ev = {
        "schema": SCHEMA, "generated_at": now, "as_of": as_of, "model_id": MODEL_ID,
        "producer": "provisional_v2.py (efv_export.regen_all)", "port_version": PORT_VERSION,
        "label": "BACKCAST",
        "label_note": ("forward-chained backcast: each test anchor is scored only by models trained on earlier "
                       "anchors of its type whose windows were closed, and its served P is shifted by the "
                       "delta fitted on the anchor before it; only closed windows are scored. It is a "
                       "development read, not a frozen window, and adjudicates nothing; verdicts come from "
                       "provisional_track.py on committed freezes."),
        "reads_no_war": True, "params": dict(PARAMS), "features_t1": list(FULL),
        "capture_floor": CAPTURE_FLOOR,
        "anchors": {t: [int(yy) for yy in sorted(df.loc[df.atype == t, "y"].unique())] for t in ("oct", "jun")},
        "rows_by_anchor": {f"{t}_{int(yy)}": int(n) for (t, yy), n in df.groupby(["atype", "y"]).size().items()},
        "backcast": bc,
    }
    if reproduce:
        rep = {}
        try:
            rep["frozen_frame"] = reproduce_freeze(frame=load_freeze_frame())
        except (OSError, ValueError, KeyError) as e:
            log.warning("provisional_v2: frozen-frame reproduction unavailable (%s)", e)
            rep["frozen_frame"] = None
        try:
            rep["live_inputs"] = reproduce_freeze(inp)
        except (OSError, ValueError, KeyError) as e:
            log.warning("provisional_v2: live reproduction unavailable (%s)", e)
            rep["live_inputs"] = None
        ev["freeze_reproduction"] = rep
    if persist:
        d = Path(data_dir) if data_dir is not None else DATA_DIR
        real = d.resolve() == DATA_DIR.resolve()
        op = Path(out_path) if out_path else (OUT_PATH if real else d / "provisional_v2.json")
        ep = Path(eval_path) if eval_path else (EVAL_PATH if real else d / "provisional_v2_eval.json")
        op.parent.mkdir(parents=True, exist_ok=True)
        _write_rows_doc(op, meta, rows)
        _write_json(ep, ev)
    return {"status": "ok", "as_of": as_of, "anchor": f"{atype} {y}", "n_rows": len(rows), "meta": meta,
            "eval": ev, "rows": rows}


def summary_line(res: dict) -> str:
    if res.get("status") != "ok":
        return str(res.get("status"))[:120]
    h = res["meta"]["heads"]["T1"]
    return (f"as of {res['as_of']}: anchor {res['anchor']}, {res['n_rows']} rows, expected first grades "
            f"W6 {h['ANY_W6']['sum_p_served']} / W12 {h['ANY_W12']['sum_p_served']}")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    res = build(persist="--print" not in sys.argv)
    print(summary_line(res))
    print(json.dumps(res["meta"]["heads"], indent=1))
    print(json.dumps(res["eval"].get("freeze_reproduction"), indent=1))
