# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The park terms of the park-matched xHEM+ part (EBR_GATE.md 11.12.2), read from caches.

    python tools/xhem_park_terms.py --identity   # the park term against published batting
    python tools/xhem_park_terms.py --fit        # fit b per arm on 2016 to 2019 and write the
                                                 # fit log docs/ebr-2026-09-30/xhem_parkmatch_fit.json

WHAT IT READS (never the network): FanGraphs' Guts park factors through
fg_leaderboards' cache (.cache/fangraphs/park_factors_{s}.json, the Basic (5yr)
column), the StatsAPI saber season cache and B-Ref's war_daily stints through
tools/fwar_replica_eval's readers (the replica's stint rule), lgR/PA from
data/league_constants.json, the frozen fWAR vintage (the identity check only) and the
swar preview .cache/swar/preview/swar.json (the fit only: S1x's g_batx, the arm, PA).

WHAT IT WRITES: with --fit, the fit log only. The fit reads same-season quantities of
the fit seasons 2016 to 2019 and nothing of a later season; no next-season quantity is
computed here.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import league_constants as LCM            # noqa: E402
import xhem_parkmatch as PM               # noqa: E402

PREVIEW_SWAR = ROOT / ".cache" / "swar" / "preview" / "swar.json"
FIT_PATH = ROOT / "docs" / "ebr-2026-09-30" / "xhem_parkmatch_fit.json"
PF_COLUMN = "Basic (5yr)"


def _sha(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


class ParkInputs:
    """One method per input, so a test or the lab's dry run supplies fixtures by
    subclassing. Nothing here fetches."""

    def __init__(self):
        self._cache: dict = {}

    def lg_r_pa(self, season: int) -> float:
        blk = LCM.load().get(int(season)) or LCM.solve_season(int(season))
        return float(blk["lg_r_pa"])

    def park_factors(self, season: int) -> dict[int, float]:
        """{StatsAPI club id: Basic (5yr) / 100} from the cached Guts table."""
        import fg_leaderboards as FG
        import fwar_replica_eval as R
        try:
            doc = FG.load("park_factors", int(season), R.FG_CACHE)
        except (FG.NotCached, FG.ShapeChanged) as exc:
            raise PM.ParkMatchStop(f"{season}: the Guts park factors are not cached ({exc})") from exc
        return {int(r["team_id"]): float(r[PF_COLUMN]) / 100.0 for r in doc["rows"]}

    def stints(self, season: int) -> dict[int, list[tuple]]:
        """{mlbam: [(club id, PA)]} for every hitting row of the StatsAPI saber cache,
        the season PA (the counting cache's) split by B-Ref stint shares."""
        import fwar_replica_eval as R
        rows, _amb = R.saber("hitting", int(season))
        counts = R.counts("hitting", int(season))
        st = R.stints_by_player("bat", int(season))
        tmap = R.team_map(st, rows)
        out: dict = {}
        for mid in set(rows) | set(counts):
            c = counts.get(mid) or {}
            pa = float(((c.get("stat") or {}).get("plateAppearances")) or 0.0)
            r = rows.get(mid) or c
            tid = (r.get("team") or {}).get("id")
            out[int(mid)] = PM.stint_pa(pa, st.get(mid) or [], tmap, tid)
        return out

    def park_rows(self, season: int) -> dict:
        """{"pf": {club: PF}, "stints": {mlbam: [(club, PA)]}, "P": {mlbam: P_i},
        "no_factor": [mlbam with a stint whose club has no factor]}."""
        s = int(season)
        if s in self._cache:
            return self._cache[s]
        pf = self.park_factors(s)
        lg = self.lg_r_pa(s)
        stints = self.stints(s)
        P, bad = {}, []
        for m, st in stints.items():
            if any(t not in pf for t, p in st if p > 0):
                bad.append(m)
                continue
            P[m] = PM.park_term([(p, pf[t]) for t, p in st if p > 0], lg)
        self._cache[s] = {"pf": pf, "stints": stints, "P": P, "no_factor": sorted(bad), "lg_r_pa": lg}
        return self._cache[s]

    def preview(self) -> dict:
        if not PREVIEW_SWAR.exists():
            raise PM.ParkMatchStop(f"the swar preview is absent ({PREVIEW_SWAR}); run python tools/build_swar.py")
        return json.loads(PREVIEW_SWAR.read_text(encoding="utf-8"))


def identity(inp: Optional[ParkInputs] = None, seasons=range(2016, 2027), log=print) -> dict:
    """Published batting - wRAA - P per PA, single-team hitters at 100 PA or more:
    one constant per league-season if P is FanGraphs' park term (11.12.1)."""
    import fwar_vintage
    import fwar_replica_eval as R
    inp = inp or ParkInputs()
    vin = fwar_vintage.load()
    out = {}
    for s in seasons:
        pr = inp.park_rows(s)
        vb = vin["seasons"][str(s)]["hitting"]
        rows, _ = R.saber("hitting", s)
        by: dict = {}
        for m, vals in vb["rows"].items():
            v = dict(zip(vb["fields"], vals))
            m = int(m)
            st = pr["stints"].get(m) or []
            pa = float(v.get("plateAppearances") or 0.0)
            if len(st) != 1 or pa < 100 or m not in pr["P"] or v.get("batting") is None:
                continue
            lg = ((rows.get(m) or {}).get("league") or {}).get("id")
            by.setdefault(str(lg), []).append((float(v["batting"]) - float(v["wRaa"]) - pr["P"][m]) / pa)
        blk = {}
        for lg, xs in by.items():
            mu = sum(xs) / len(xs)
            blk[lg] = {"n": len(xs), "mean_per_pa": mu,
                       "sd_per_pa": (sum((x - mu) ** 2 for x in xs) / len(xs)) ** 0.5}
        out[str(s)] = {"leagues": blk, "no_factor": len(pr["no_factor"])}
        log(f"  {s}: " + "; ".join(f"league {k} n {v['n']} sd {v['sd_per_pa']:.7f} per PA" for k, v in blk.items())
            + f"; rows without a factor {len(pr['no_factor'])}")
    return out


def fit(inp: Optional[ParkInputs] = None, log=print) -> dict:
    """b per arm on the fit seasons (11.12.2), from the preview's S1x g_batx, arm
    and PA and the park term; same-season quantities of 2016 to 2019 only."""
    inp = inp or ParkInputs()
    doc = inp.preview()
    rows = {a: [] for a in PM.ARMS}
    census = {}
    for s in PM.FIT_SEASONS:
        blk = (doc.get("seasons") or {}).get(str(s))
        if blk is None:
            raise PM.ParkMatchStop(f"the preview lacks fit season {s}")
        pr = inp.park_rows(s)
        n = {a: 0 for a in PM.ARMS}
        for h in blk.get("hitters") or []:
            if h.get("pitcher_batter"):
                continue
            pa = float(h.get("pa") or 0.0)
            bx = (h.get("parts") or {}).get("batx") or {}
            if pa <= 0 or bx.get("g") is None:
                continue
            m = int(h["mlbam"])
            if m not in pr["P"]:
                raise PM.ParkMatchStop(f"{s}: hitter {m} has PA and no park term")
            arm = "xhem" if bx.get("arm") == "xhem" else "hem"
            rows[arm].append({"season": s, "pa": pa, "g": float(bx["g"]), "P": pr["P"][m]})
            n[arm] += 1
        census[str(s)] = n
    res = {a: PM.fit_share(rows[a]) for a in PM.ARMS}
    for a, r in res.items():
        if r["b"] is None:
            raise PM.ParkMatchStop(f"the {a} arm's share is not estimable: {r}")
        log(f"  b[{a}] = {r['b']:.6f} (slope {r['slope']:.6f}, se {r['se']:.6f}, n {r['n']}, seasons {r['seasons']})")
    return {
        "what_this_is": ("The frozen shares b of the park-matched xHEM+ part (docs/ebr-2026-09-30/EBR_GATE.md "
                         "11.12.2): per arm, the PA-weighted least-squares slope of S1x's g_batx per PA on "
                         "fWAR's park term per PA, one intercept per season, fit seasons 2016 to 2019, clamped "
                         "to 0 to 1. Same-season quantities only; fitted once, before the read."),
        "fitted_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "fit_seasons": list(PM.FIT_SEASONS),
        "preview": {"path": ".cache/swar/preview/swar.json", "sha256": _sha(PREVIEW_SWAR),
                    "generated_at": doc.get("generated_at"), "fwar_vintage_id": doc.get("fwar_vintage_id")},
        "park_factor": "FanGraphs Guts, Basic (5yr), .cache/fangraphs/park_factors_{s}.json",
        "rows_by_season": census,
        "arms": {a: {k: (round(v, 9) if isinstance(v, float) else v) for k, v in r.items()} for a, r in res.items()},
        "b": {a: round(float(res[a]["b"]), 6) for a in PM.ARMS},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--identity", action="store_true")
    ap.add_argument("--fit", action="store_true")
    a = ap.parse_args(argv)
    if a.identity:
        print("park term identity (11.12.1): published batting - wRAA - P per PA, single-team, 100 PA+")
        identity()
    if a.fit:
        if FIT_PATH.exists():
            print(f"REFUSED: the fit is frozen ({FIT_PATH}); a refit is a new registration")
            return 2
        print("fit of b per arm on 2016 to 2019 (11.12.2)")
        rec = fit()
        FIT_PATH.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"written {FIT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
