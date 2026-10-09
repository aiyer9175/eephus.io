# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR v3 skill and position deltas, built DARK into a preview file.

    python tools/build_swar.py                      # 2016 to the last complete season
    python tools/build_swar.py --seasons 2021 2024  # a subset
    python tools/build_swar.py --out <path>         # a path under .cache/swar/ only

Registered in docs/ebr-2026-09-30/EBR_GATE.md part 9.4; the formulas live in
swar.py (pure) and this file only assembles their inputs and writes the preview.
It reads nothing but caches (the StatsAPI season caches, the fielding innings
and league-constants artifacts, the Savant expected-stats cache), the frozen
per-season fWAR vintage (data/fwar_vintage.json, the base of every test value),
the EM+ modules' own pool builders and the replica's feed-only pitcher chain
(tools/fwar_replica_eval.pitchers on its `plain_fip_loo_pf` arm, run twice per
home-run variant through its count_map hook). It writes ONE file,
.cache/swar/preview/swar.json, never data/ and never docs/. There is no serve
flag and no reader: EBR_3_EWAR_V3 wires the surfaces behind EWAR_V3_LIVE.

WHAT THE FILE HOLDS, per season: the ladder refit on the six-season window
ending at that season and its window; the pool summaries; per hitter-season
the fWAR base, each candidate part's g, its re-centred delta d (alone, per
season and side: the object the skill look scores) and its test value, both
batting arms; per pitcher-season the fWAR base, both home-run variants' dFIP,
dwar0, re-pinned Delta and test value, the L-B (unlevered) dwar0 as a
disclosure; and the coverage census (rows, ambiguous ids, nopp and
pitcher-batter rows, swingmen, xHEM+-arm rows). It relates no delta to any
next-season quantity: no year-to-year, split-half or forward statistic is
computed here, and tools/swar_lab.py (EWV3_SKILL_BUILD_LAB) is the only code
path that may.

SEASONS. 2016 (DEM+'s first season on the one Statcast frame) to the last
COMPLETE season, a season being complete on November 1 of its own year
(war_source.EWAR_FREEZE_MONTH_DAY, the cadence eWAR v2 freezes on), so the
live season is never read from a cache that may still move.

STOPS. The frozen vintage absent, a season of the frame not frozen, a Savant
expected-stats cache absent for a season 2016 or later (the gate: that STOPs
the build, never a refetch), or any part 9.4 invariant failing raises
BuildStop, and nothing is written. The sha256 of data/ewar.json is taken before
and after the build and must not move (invariant 8).
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dem_plus                          # noqa: E402  (constants by reference, for the stamp)
import fwar_vintage                      # noqa: E402
import league_constants as LCM           # noqa: E402
import positional_fit as PF              # noqa: E402
import rem_plus                          # noqa: E402
import saber_feed                        # noqa: E402
import sem_plus                          # noqa: E402
import swar                              # noqa: E402
import war_source                        # noqa: E402  (a constant, read only)
import fwar_replica_eval as R            # noqa: E402  (its own fg_leaderboards import stays)

CACHE = ROOT / ".cache"
OUT_DIR = CACHE / "swar" / "preview"
OUT_PATH = OUT_DIR / "swar.json"
EWAR_PATH = ROOT / "data" / "ewar.json"
FIELDING_PATH = ROOT / "data" / "fielding_innings.json"
SAVANT_DIR = CACHE / "savant_mlb"

FIRST_SEASON = 2016
#: The replica's feed-only pitcher arm (PITCHER_ARMS[0]): plain FIP, the
#: leave-one-out FIP- park factor, B-Ref role innings, no IFFB, no framing.
PITCHER_ARM = "plain_fip_loo_pf"
PITCHER_ARM_KW = {"pf_source": "fip_minus"}
#: Zero-sum tolerance, in runs (hitters) and wins (pitchers), part 9.4 invariant 6.
ZERO_SUM_TOL = 1e-9
#: The pure chain in swar.py must reproduce the replica's count_map arm to this.
CHAIN_TOL = 1e-9


class BuildStop(RuntimeError):
    """A precondition or invariant failed: nothing is written."""


class MissingSource(BuildStop):
    """A season's input source is absent (the Savant cache, the vintage)."""


def last_complete_season(today: Optional[_dt.date] = None) -> int:
    """The newest season complete on `today`: its own November 1 has passed."""
    today = today or _dt.date.today()
    m, d = war_source.EWAR_FREEZE_MONTH_DAY
    return today.year if (today.month, today.day) >= (m, d) else today.year - 1


def sha256_of(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


# --------------------------------------------------------------------------
# the production inputs (caches, the vintage, the EM+ pools, the replica chain)
# --------------------------------------------------------------------------

def _group_rows(block: dict) -> dict[int, dict]:
    """A frozen vintage group as {mlbam: {field: value}}."""
    fields = list(block.get("fields") or [])
    return {int(mid): dict(zip(fields, vals)) for mid, vals in (block.get("rows") or {}).items()}


class Inputs:
    """Every input the build reads, one method each, so a test can supply
    fixtures by subclassing. Nothing here fetches."""

    def __init__(self):
        self._vintage = None
        self._feeds = None

    # -- the frozen fWAR vintage (the base)
    def vintage(self) -> dict:
        if self._vintage is None:
            if not fwar_vintage.available():
                raise MissingSource("the frozen fWAR vintage (data/fwar_vintage.json) is absent")
            self._vintage = fwar_vintage.load()
        return self._vintage

    def frozen_seasons(self) -> list[int]:
        return fwar_vintage.fwar_seasons(self.vintage())

    def vintage_id(self) -> str:
        return str(self.vintage().get("vintage_id") or "")

    def feed_group(self, season: int, group: str) -> tuple[dict[int, dict], list[int]]:
        """({mlbam: {field: value}}, ambiguous ids) of one frozen group."""
        sb = (self.vintage().get("seasons") or {}).get(str(int(season))) or {}
        gb = sb.get(group) or {}
        if gb.get("status") != "frozen":
            raise MissingSource(f"{season} {group} is not frozen in the vintage")
        return _group_rows(gb), [int(x) for x in (gb.get("ambiguous_ids") or [])]

    # -- the StatsAPI season caches (the replica's readers, caches only)
    def hitting_counts(self, season: int) -> dict[int, dict]:
        """{mlbam: {"stat": {...}, "code": position code, "name": ...}}."""
        out = {}
        for pid, r in R.counts("hitting", season).items():
            out[int(pid)] = {"stat": r.get("stat") or {},
                             "code": str((r.get("position") or {}).get("code") or ""),
                             "name": (r.get("player") or {}).get("fullName", "")}
        return out

    def pitching_counts(self, season: int) -> dict[int, dict]:
        """{mlbam: {"stat": {...}, "abbr": position abbreviation, "name": ...}}."""
        out = {}
        for pid, r in R.counts("pitching", season).items():
            out[int(pid)] = {"stat": r.get("stat") or {},
                             "abbr": str((r.get("position") or {}).get("abbreviation") or ""),
                             "name": (r.get("player") or {}).get("fullName", "")}
        return out

    # -- fielding innings (data/fielding_innings.json)
    def fielding(self, season: int) -> dict[int, dict[str, float]]:
        try:
            blob = json.loads(FIELDING_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise MissingSource(f"data/fielding_innings.json unreadable ({exc})") from exc
        rows = (blob.get("seasons") or {}).get(str(int(season))) or {}
        return {int(mid): {p: float((v or {}).get("inn") or 0.0) for p, v in byp.items()}
                for mid, byp in rows.items()}

    # -- the league constants
    def constants(self, season: int) -> dict:
        blk = LCM.constants(int(season))
        if not blk or "woba_weights" not in blk:
            raise MissingSource(f"league constants for {season} are not solved")
        tot = LCM.league_totals(int(season)) or {}
        rpw = tot.get("rpw")
        if rpw is None:
            raise MissingSource(f"league_totals({season}) carries no rpw")
        return {"woba_weights": dict(blk["woba_weights"]), "woba_scale": float(blk["woba_scale"]),
                "lg_woba": float(blk["lg_woba"]), "rpw": float(rpw),
                "rpw_constants": float(blk["rpw"]),
                "lg_ra9": float(blk["lg_ra9"]), "lg_era": float(blk["lg_era"]),
                "fip_constant": float(blk["fip_constant"])}

    # -- the Savant expected-stats cache (the served xHEM+ column's source, never refetched)
    def savant(self, season: int) -> list[tuple[int, float, float]]:
        path = SAVANT_DIR / f"expected_batter_{int(season)}.csv"
        if not path.exists():
            raise MissingSource(f"xwOBA source {season}: {path.name} is not cached")
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        out = []
        for r in csv.DictReader(io.StringIO(text)):
            try:
                out.append((int(r["player_id"]), float(r["est_woba"]), float(r["pa"])))
            except (TypeError, ValueError, KeyError):
                continue
        return out

    # -- our ladder, refit on the six seasons ending at `season`
    def ladder(self, season: int) -> dict:
        if self._feeds is None:
            self._feeds = PF.Feeds()
        fit = PF.fit_ladder(self._feeds, last=int(season), boot=0)
        return {"values": dict(fit["values"]), "inn_per_pa": float(fit["inn_per_pa"]),
                "window": [int(fit["seasons"][0]), int(fit["seasons"][1])],
                "n_player_seasons": int(fit["n_player_seasons"]), "r2": fit.get("r2")}

    # -- the replica's feed-only pitcher chain
    def pitcher_chain(self, season: int, count_map: Optional[dict] = None) -> dict[int, dict]:
        """{mlbam: {ip, g, gs, start_ip, lg9, pf, fip, gm, war0}} off the
        replica's priced rows on PITCHER_ARM, the counts overridden by `count_map`."""
        res = R.pitchers(int(season), keep_rows=True, count_map=count_map, **PITCHER_ARM_KW)
        if "components" not in res:
            raise MissingSource(f"the replica could not price {season} ({res.get('error')})")
        out = {}
        for rec in res["_rows"]:
            out[int(rec["pid"])] = {
                "ip": rec["ip"], "g": rec["g"], "gs": rec["gs"], "start_ip": rec["start_ip"],
                "lg9": rec["lg9"], "pf": rec["pf"], "fip": rec["fip"], "gm": rec["gm"],
                "war0": sum(ln["war0"] for ln in rec["lines"]), "name": rec.get("name", ""),
            }
        return out


# --------------------------------------------------------------------------
# one season
# --------------------------------------------------------------------------

def _num(v, default=0.0) -> float:
    try:
        f = float(v)
        return default if f != f else f
    except (TypeError, ValueError):
        return default


def _r(v, nd=6):
    return None if v is None else round(float(v), nd)


def hitter_rows(season: int, inp: Inputs, savant=None) -> tuple[list[swar.HitterRow], dict]:
    """The hitting side: every hitting-group row of the vintage joined to its
    counting line, fielding innings and Savant value."""
    feed, ambiguous = inp.feed_group(season, "hitting")
    counts = inp.hitting_counts(season)
    fld = inp.fielding(season)
    savant = inp.savant(season) if savant is None else savant
    xw = {mid: ew for mid, ew, pa in savant if ew and ew > 0}
    rows, n_no_counts = [], 0
    for mid, f in feed.items():
        c = counts.get(mid)
        st = (c or {}).get("stat") or {}
        if c is None:
            n_no_counts += 1
        rows.append(swar.HitterRow(
            mlbam=mid, name=(c or {}).get("name", ""),
            pa=_num(st.get("plateAppearances")), ab=_num(st.get("atBats")), h=_num(st.get("hits")),
            doub=_num(st.get("doubles")), trip=_num(st.get("triples")), hr=_num(st.get("homeRuns")),
            bb=_num(st.get("baseOnBalls")), ibb=_num(st.get("intentionalWalks")),
            hbp=_num(st.get("hitByPitch")), sf=_num(st.get("sacFlies")),
            code=(c or {}).get("code", ""), inn_by_pos=dict(fld.get(mid) or {}),
            fwar=_num(f.get("war")), pos_fg=_num(f.get("positional")), fld=_num(f.get("fielding")),
            frm=saber_feed.framing_residual(f), xwoba=xw.get(mid),
        ))
    return rows, {"ambiguous_ids": ambiguous, "hitters_without_counts": n_no_counts}


def pitcher_rows(season: int, inp: Inputs, chain: dict[int, dict]) -> tuple[list[swar.PitcherRow], dict]:
    """The pitching side: every pitching-group row of the vintage joined to its
    season line and the replica's priced row."""
    feed, ambiguous = inp.feed_group(season, "pitching")
    counts = inp.pitching_counts(season)
    rows, n_no_chain = [], 0
    for mid, f in feed.items():
        c = counts.get(mid)
        st = (c or {}).get("stat") or {}
        rec = chain.get(mid)
        if rec is None:
            n_no_chain += 1
        rows.append(swar.PitcherRow(
            mlbam=mid, name=(c or {}).get("name", ""),
            ip=_num((rec or {}).get("ip", _num(st.get("outs")) / 3.0)),
            g=_num((rec or {}).get("g", _num(st.get("gamesPlayed")))),
            gs=_num((rec or {}).get("gs", _num(st.get("gamesStarted")))),
            start_ip=_num((rec or {}).get("start_ip")),
            tbf=_num(st.get("battersFaced")), k=_num(st.get("strikeOuts")),
            bb=_num(st.get("baseOnBalls")), hbp=_num(st.get("hitByPitch")), hr=_num(st.get("homeRuns")),
            abbr=(c or {}).get("abbr", "P"), fwar=_num(f.get("war")), gmli=f.get("gmli"),
        ))
    return rows, {"ambiguous_ids": ambiguous, "pitchers_without_chain": n_no_chain}


def build_season(season: int, inp: Inputs) -> dict:
    K = inp.constants(season)
    W, scale, lgw, rpw = K["woba_weights"], K["woba_scale"], K["lg_woba"], K["rpw"]
    ladder = inp.ladder(season)
    savant = inp.savant(season)
    hitters, h_meta = hitter_rows(season, inp, savant)
    hem_pool = swar.batting_pool(hitters)
    xbar = swar.savant_pool_mean(savant)
    sav_n = sum(1 for _m, ew, pa in savant if pa >= swar.XHEM_POOL_MIN_PA and ew > 0)

    pa = {r.mlbam: r.pa for r in hitters}
    g = {p: {} for p in swar.HITTER_PARTS}
    detail = {}
    for r in hitters:
        gb = swar.batting_delta(r, hem_pool, W, scale)
        g["pos"][r.mlbam] = swar.position_delta(r, ladder["values"], ladder["inn_per_pa"])
        g["bat"][r.mlbam] = gb
        g["batx"][r.mlbam] = swar.xbatting_delta(r, gb, xbar, lgw, scale, W)
        g["fld"][r.mlbam] = swar.fielding_delta(r)
        detail[r.mlbam] = {
            "woba": swar.woba_actual(r, W), "woba_skill": swar.woba_skill(r, hem_pool, W),
            "xwoba": r.xwoba, "xhem_arm": swar.uses_xhem_arm(r, xbar),
            "rel": swar.fielding_reliability(r),
            "pos_ours": swar.ladder_positional(r.pa, r.inn_by_pos, ladder["values"], ladder["inn_per_pa"]),
        }
    pitcher_batters = {r.mlbam for r in hitters if swar.is_pitcher_batter(r.code, r.inn_by_pos)}
    d = {p: swar.recentre(g[p], pa, pitcher_batters) for p in swar.HITTER_PARTS}

    # -- pitchers: the replica chain on the actual counts, then once per home-run variant
    chain = inp.pitcher_chain(season)
    pitchers, p_meta = pitcher_rows(season, inp, chain)
    sp_pool, rp_pool = swar.pitching_pools(pitchers)
    nopp = {r.mlbam for r in pitchers if swar.is_nopp(r.abbr)}
    ip = {r.mlbam: r.ip for r in pitchers}
    variants = {}
    chain_gap = 0.0
    for variant in swar.HR_VARIANTS:
        cm = swar.count_map(pitchers, sp_pool, rp_pool, variant)
        skill_chain = inp.pitcher_chain(season, count_map=cm)
        dw, dfips, lb = {}, {}, {}
        for r in pitchers:
            a, s = chain.get(r.mlbam), skill_chain.get(r.mlbam)
            if a is None or s is None or r.mlbam in nopp or r.ip <= 0:
                dw[r.mlbam], dfips[r.mlbam], lb[r.mlbam] = 0.0, 0.0, 0.0
                continue
            tgt = swar.blend_target(swar.start_share(a["start_ip"], a["ip"]), sp_pool, rp_pool)
            df = swar.dfip(r, swar.shrunk_counts(r, tgt, variant))
            dfips[r.mlbam] = df
            dw[r.mlbam] = s["war0"] - a["war0"]
            # the pure chain at the published gmLI must reproduce the replica's arm
            pure = swar.dwar0(a["ip"], a["g"], a["gs"], a["start_ip"], a["lg9"], a["pf"], a["fip"],
                              df, K["lg_ra9"], K["lg_era"], a["gm"])
            chain_gap = max(chain_gap, abs(pure - dw[r.mlbam]))
            # L-B: gmLI 1 in both arms, a disclosure
            lb[r.mlbam] = swar.dwar0(a["ip"], a["g"], a["gs"], a["start_ip"], a["lg9"], a["pf"],
                                     a["fip"], df, K["lg_ra9"], K["lg_era"], 1.0)
        delta = swar.pitching_delta(dw, ip, nopp)
        variants[variant] = {"dfip": dfips, "dwar0": dw, "delta": delta, "lb_dwar0": lb}

    # -- invariants (part 9.4, 6 and 7) on this season
    checks = {"zero_sum": {}, "chain_gap_max_abs": chain_gap}
    for p in swar.HITTER_PARTS:
        s = sum(d[p].values())
        checks["zero_sum"][p] = s
        if abs(s) > ZERO_SUM_TOL:
            raise BuildStop(f"{season} {p}: re-centred delta sums to {s!r}, not 0")
    for variant in swar.HR_VARIANTS:
        s = sum(variants[variant]["delta"].values())
        checks["zero_sum"][variant] = s
        if abs(s) > ZERO_SUM_TOL:
            raise BuildStop(f"{season} {variant}: re-pinned Delta sums to {s!r}, not 0")
    for m in pitcher_batters:
        if any(g[p][m] != 0.0 or d[p][m] != 0.0 for p in swar.HITTER_PARTS):
            raise BuildStop(f"{season}: pitcher-batter {m} carries a non-zero delta")
    for variant in swar.HR_VARIANTS:
        if any(variants[variant]["delta"][m] != 0.0 for m in nopp):
            raise BuildStop(f"{season} {variant}: a nopp row carries a non-zero Delta")
    if chain_gap > CHAIN_TOL:
        raise BuildStop(f"{season}: the pure chain departs from the replica's count_map arm by {chain_gap!r}")

    # -- rows
    h_out = []
    for r in hitters:
        pb = r.mlbam in pitcher_batters
        dt = detail[r.mlbam]
        parts = {}
        for p in swar.HITTER_PARTS:
            parts[p] = {"g": _r(g[p][r.mlbam]), "d": _r(d[p][r.mlbam]),
                        "test": _r(swar.hitter_test_value(r.fwar, d[p][r.mlbam], rpw))}
        parts["bat"].update({"woba": _r(dt["woba"], 4), "woba_skill": _r(dt["woba_skill"], 4)})
        parts["batx"].update({"xwoba": _r(dt["xwoba"], 4), "arm": "xhem" if dt["xhem_arm"] else "hem"})
        parts["fld"]["rel"] = _r(dt["rel"], 4)
        parts["pos"].update({"pos_ours": _r(dt["pos_ours"], 4), "pos_fg": _r(r.pos_fg, 4)})
        h_out.append({"mlbam": r.mlbam, "name": r.name, "pa": r.pa, "fwar": r.fwar,
                      "pitcher_batter": pb, "parts": parts})
    p_out = []
    for r in pitchers:
        a = chain.get(r.mlbam) or {}
        sigma = swar.start_share(a.get("start_ip", 0.0), a.get("ip", 0.0))
        parts = {}
        for variant in swar.HR_VARIANTS:
            v = variants[variant]
            parts[variant] = {"dfip": _r(v["dfip"][r.mlbam]), "dwar0": _r(v["dwar0"][r.mlbam]),
                              "delta": _r(v["delta"][r.mlbam]),
                              "test": _r(swar.pitcher_test_value(r.fwar, v["delta"][r.mlbam])),
                              "lb_dwar0": _r(v["lb_dwar0"][r.mlbam])}
        p_out.append({"mlbam": r.mlbam, "name": r.name, "ip": _r(r.ip, 3), "g": r.g, "gs": r.gs,
                      "tbf": r.tbf, "sigma": _r(sigma, 4), "swingman": swar.is_swingman(r.gs, r.g),
                      "nopp": r.mlbam in nopp, "gmli": r.gmli, "fwar": r.fwar,
                      "in_chain": r.mlbam in chain, "parts": parts})

    both = {r.mlbam for r in hitters} & {r.mlbam for r in pitchers}
    two_way = both - pitcher_batters - nopp
    census = {
        "rows_hitters": len(hitters), "rows_pitchers": len(pitchers),
        "ambiguous_ids_hitting": len(h_meta["ambiguous_ids"]),
        "ambiguous_ids_pitching": len(p_meta["ambiguous_ids"]),
        "hitters_without_counts": h_meta["hitters_without_counts"],
        "pitchers_without_chain": p_meta["pitchers_without_chain"],
        "pitcher_batter_rows": len(pitcher_batters),
        "nopp_rows": len(nopp),
        "swingmen": sum(1 for r in pitchers if swar.is_swingman(r.gs, r.g)),
        "xhem_arm_rows": sum(1 for r in hitters if detail[r.mlbam]["xhem_arm"]),
        # ids on both sides: pitcher-batters (pre-2022 NL pitchers hitting),
        # position players who pitched (nopp) and the two-way players shrunk on
        # both sides (neither mark)
        "rows_on_both_sides": len(both),
        "two_way_rows": len(two_way),
        "hitters_pa_zero": sum(1 for r in hitters if r.pa <= 0),
        "hem_pool_n": hem_pool.n, "sem_pool_n": sp_pool.n, "rem_pool_n": rp_pool.n,
        "savant_pool_n": sav_n,
    }
    return {
        "season": season, "rpw": rpw, "rpw_constants": K["rpw_constants"],
        "lg_woba": lgw, "woba_scale": scale, "woba_weights": W,
        "ladder": ladder,
        "pools": {"hem": {"n": hem_pool.n, "means": swar.pool_means(hem_pool), "mean_woba": hem_pool.mean_woba},
                  "sem": {"n": sp_pool.n, "rates": swar.pool_rates(sp_pool), "cfip": sp_pool.cfip},
                  "rem": {"n": rp_pool.n, "rates": swar.pool_rates(rp_pool), "cfip": rp_pool.cfip},
                  "savant": {"n": sav_n, "xbar": xbar}},
        "census": census, "checks": checks,
        "hitters": h_out, "pitchers": p_out,
    }


# --------------------------------------------------------------------------
# the build
# --------------------------------------------------------------------------

def frame_seasons(inp: Inputs, seasons=None, today: Optional[_dt.date] = None) -> list[int]:
    want = sorted(int(s) for s in seasons) if seasons else list(range(FIRST_SEASON, last_complete_season(today) + 1))
    frozen = set(inp.frozen_seasons())
    missing = [s for s in want if s not in frozen]
    if missing:
        raise MissingSource(f"seasons not frozen in the vintage: {missing}")
    if any(s < FIRST_SEASON for s in want):
        raise BuildStop(f"the skill and position deltas start at {FIRST_SEASON}")
    return want


def _refuse_out(path: Path) -> None:
    rp = Path(path).resolve()
    for forbidden in (ROOT / "data", ROOT / "docs"):
        try:
            rp.relative_to(forbidden.resolve())
        except ValueError:
            continue
        raise BuildStop(f"refusing to write under {forbidden.name}/: {path}")


def write_preview(payload: dict, out_path: Path = OUT_PATH) -> Path:
    """Atomic write (a sibling temp file, then os.replace), compact JSON."""
    out_path = Path(out_path)
    _refuse_out(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + f".tmp{os.getpid()}")
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n"
    with open(tmp, "w", encoding="ascii", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, out_path)
    return out_path


def build(seasons=None, inp: Optional[Inputs] = None, out_path: Optional[Path] = OUT_PATH,
          today: Optional[_dt.date] = None, log=print) -> dict:
    inp = inp or Inputs()
    ewar_before = sha256_of(EWAR_PATH)
    want = frame_seasons(inp, seasons, today)
    out_seasons = {}
    for y in want:
        log(f"  swar preview: {y}...")
        out_seasons[str(y)] = build_season(y, inp)
    ewar_after = sha256_of(EWAR_PATH)
    if ewar_before != ewar_after:
        raise BuildStop("data/ewar.json moved during the build")
    census = {k: sum(b["census"][k] for b in out_seasons.values())
              for k in next(iter(out_seasons.values()))["census"]} if out_seasons else {}
    payload = {
        "schema": swar.SWAR_VERSION,
        "what_this_is": ("eWAR v3 skill and position deltas (candidate parts 3 to 6), a DARK "
                         "preview: fWAR from the frozen vintage plus each part's re-centred "
                         "delta alone; served nowhere, read by no exporter"),
        "registration": "docs/ebr-2026-09-30/EBR_GATE.md part 9.4",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "fwar_vintage_id": inp.vintage_id(),
        "seasons_built": want,
        "pitcher_arm": PITCHER_ARM,
        "leverage": {"served_arm": "L-A (the published gmLI levers both arms)",
                     "disclosure": "lb_dwar0: gmLI 1 in both arms, never served"},
        "hr_variants": list(swar.HR_VARIANTS),
        "constants_by_reference": {
            "bat_k": dict(swar.BAT_K), "pit_k": dict(swar.PIT_K),
            "fielding_k_inn": dict(dem_plus.K_INN),
            "xhem_arm_min_pa": swar.XHEM_ARM_MIN_PA, "xhem_pool_min_pa": swar.XHEM_POOL_MIN_PA,
            "swingman_band": [rem_plus.MAX_START_SHARE, sem_plus.MIN_START_SHARE],
        },
        "ewar_json_sha256": {"before": ewar_before, "after": ewar_after},
        "census_total": census,
        "seasons": out_seasons,
    }
    if out_path is not None:
        write_preview(payload, Path(out_path))
        log(f"wrote {out_path}")
    return payload


CENSUS_COLUMNS = (
    ("rows_hitters", "hit"), ("rows_pitchers", "pit"),
    ("ambiguous_ids_hitting", "amb_h"), ("ambiguous_ids_pitching", "amb_p"),
    ("hitters_without_counts", "no_cnt"), ("pitchers_without_chain", "no_chn"),
    ("pitcher_batter_rows", "pbat"), ("nopp_rows", "nopp"), ("swingmen", "swing"),
    ("xhem_arm_rows", "xhem"), ("two_way_rows", "twoway"), ("rows_on_both_sides", "both"),
)


def print_census(payload: dict, log=print) -> None:
    """The coverage census, one row per season and a total; the column keys
    are printed in full first so a short header reads unambiguously."""
    for key, short in CENSUS_COLUMNS:
        log(f"  {short:7s} = {key}")
    log("season " + " ".join(f"{short:>7s}" for _k, short in CENSUS_COLUMNS))
    for s, b in payload["seasons"].items():
        c = b["census"]
        log(f"{s:6s} " + " ".join(f"{c[k]:>7d}" for k, _s in CENSUS_COLUMNS))
    c = payload["census_total"]
    log(f"{'total':6s} " + " ".join(f"{c[k]:>7d}" for k, _s in CENSUS_COLUMNS))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", nargs="*", type=int)
    ap.add_argument("--out", help="write the preview here (under .cache/swar/ only)")
    args = ap.parse_args(argv)
    out = Path(args.out) if args.out else OUT_PATH
    try:
        out.resolve().relative_to((CACHE / "swar").resolve())
    except ValueError:
        print(f"refusing --out outside .cache/swar/: {out}", file=sys.stderr)
        return 2
    try:
        payload = build(args.seasons, out_path=out)
    except BuildStop as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 1
    print_census(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
