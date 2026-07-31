# pbust thin-sample lane -- SCRATCH LAB (lane: pbust).
# Forward-chained provisional scoring of the historical thin-sample cohort:
# for cohort year Y, fit the no-FV production ridge on labeled matrix rows with
# decision_year < Y ONLY, then score every cohort row exactly as efv_ungraded.build
# scores a live row (same _vec, _war clip, _grade map, sub-floor cameo cap).
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import milb_history as mh   # noqa: E402

# read-only memoization of the season index (the module builds it fresh per call;
# scoring 24k rows x 5 seasons would otherwise rebuild it ~120k times)
_raw_player_index = mh.player_index
mh.player_index = lru_cache(maxsize=128)(_raw_player_index)   # type: ignore[assignment]

import efv_ungraded as eu          # noqa: E402
from efv_model import _vec         # noqa: E402
from efv_dataset import matrix_path, _milb_features   # noqa: E402
from prospect_path import _fit_ridge, _fit_linear_calibration   # noqa: E402


@lru_cache(maxsize=8)
def _matrix(side: str):
    return json.loads(matrix_path(side).read_text(encoding="utf-8"))


def fit_asof(side: str, year: int):
    """eu.fit_nofv restricted to rows whose decision_year < `year` (forward-chained).

    NOT USABLE for cohort years 2015-2019: the labeled matrix carries a milb block only
    from 2014 on, so decision_year<Y leaves n = 3..163 rows. The production path
    (fit_production) is used instead; see the leak note in analyze.py.
    """
    is_pit = side == "pit"
    rows = [r for r in _matrix(side)
            if bool(r.get("is_pitcher")) == is_pit and r.get("milb")
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    data = [d for d in eu._prep(rows, side) if d["decision_year"] < year]
    if len(data) < 60:
        return None
    ridge = _fit_ridge(data, eu._keys(side))
    raw = {r["player_key"]: eu._predict_clipped(ridge, r["feats"]) for r in data}
    cal = _fit_linear_calibration([(raw[r["player_key"]], r["target"]) for r in data])
    a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
    return ridge, a, b, len(data)


@lru_cache(maxsize=4)
def fit_production(side: str):
    """The EXACT fit the served provisional grade uses (efv_ungraded.fit_nofv)."""
    ridge, a, b = eu.fit_nofv(side)
    return ridge, a, b, None


def score(rows, years):
    fits = {}
    out = []
    for i, r in enumerate(rows):
        Y, side = r["year"], r["side"]
        if Y not in years:
            continue
        key = side
        if key not in fits:
            fits[key] = fit_production(side)
            print(f"  production fit {side}", flush=True)
        ridge, a, b, _ = fits[key]
        m = _milb_features(r["mlbam"], Y + 1, None, side)
        if not m or m.get("k_rel") is None:
            continue
        feats = _vec({"consensus_fv_raw": eu._GRADE_MAP[side]["BASE"],
                      "position": "P" if side == "pit" else "SS", "milb": m}, side)
        war = eu._war(ridge, a, b, feats)
        grade = eu._grade(war, side)
        # sub-floor cameo cap, same rule as the live build (exposure of the primary
        # level line the features were keyed on)
        if r["expo"] < (eu._MIN_EXPO_BF if side == "pit" else eu._MIN_EXPO_PA):
            grade = min(grade, eu._SUBFLOOR_GRADE)
        d = dict(r)
        d["war_pred"] = round(war, 3)
        d["grade"] = grade
        d["milb_level_asof"] = m.get("milb_level")
        d["age_asof"] = m.get("age")
        d["n_milb_seasons"] = m.get("n_milb_seasons")
        # keep the feature vector so the gate lab can REFIT the ridge on every
        # bootstrap draw without re-deriving features (they are fixed per row)
        d["feats"] = {k: feats.get(k, 0.0) for k in eu._keys(side)}
        out.append(d)
        if (i + 1) % 2000 == 0:
            print(f"  {i+1}/{len(rows)} scored={len(out)}", flush=True)
    return out


if __name__ == "__main__":
    years = tuple(int(x) for x in (sys.argv[1].split(",") if len(sys.argv) > 1
                                   else ["2015", "2016", "2017", "2018", "2019"]))
    MIN = {"hit": 80.0, "pit": 90.0}
    rows = json.loads((HERE / "cohort_raw.json").read_text(encoding="utf-8"))
    rows = [r for r in rows
            if not r["pre_mlb"] and r["expo"] >= MIN[r["side"]]
            and not r["graded_as_of"] and r["year"] in years]
    print("cohort rows to score:", len(rows), flush=True)
    scored = score(rows, set(years))
    (HERE / "cohort_scored.json").write_text(json.dumps(scored), encoding="utf-8")
    print("scored", len(scored))
