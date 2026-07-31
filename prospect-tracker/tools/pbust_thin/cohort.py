# pbust thin-sample lane -- SCRATCH LAB (lane: pbust).
# Builds the historical THIN-SAMPLE analog cohort and its realized outcome labels.
# Read-only: touches no production artifact.
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

import sys
sys.path.insert(0, str(ROOT))

import milb_history as mh   # noqa: E402

LEVELS = ("DSL", "CPX", "A", "A+", "AA", "AAA")
MIN_EXPO = {"hit": 80.0, "pit": 90.0}    # efv_ungraded._MIN_EXPO_PA / _MIN_EXPO_BF


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=64)
def pidx(season: int, group: str):
    return mh.player_index(season, group, fetch=False)


@lru_cache(maxsize=4)
def mlb_seasons_by_id() -> dict:
    """{mlbam: {season: (pa_or_bf, group)}} from the COMPLETE cached sport-1 lines."""
    out = {}
    for season in range(2005, 2027):
        for group, expo in (("hitting", "pa"), ("pitching", "bf")):
            for r in mh.season_splits(1, season, group, fetch=False):
                mid = r.get("mlbam")
                if not mid:
                    continue
                e = _f(r.get(expo)) or 0.0
                d = out.setdefault(int(mid), {})
                prev = d.get(season) or 0.0
                d[season] = max(prev, e)
    return out


@lru_cache(maxsize=4)
def mlb_name_by_id() -> dict:
    out = {}
    for season in range(2005, 2027):
        for group in ("hitting", "pitching"):
            for r in mh.season_splits(1, season, group, fetch=False):
                if r.get("mlbam") and r.get("name"):
                    out[int(r["mlbam"])] = r["name"]
    return out


def normalize_key(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", "_", s)
    return s


@lru_cache(maxsize=4)
def career_war_by_slug() -> dict:
    con = sqlite3.connect(str(ROOT / "prospects.db"))
    out = {}
    for pk, payload in con.execute("SELECT player_key, payload_json FROM career_war"):
        try:
            d = json.loads(payload)
        except ValueError:
            continue
        seas = {int(k): float(v) for k, v in (d.get("seasons") or {}).items()}
        out[pk] = seas
    con.close()
    return out


@lru_cache(maxsize=4)
def graded_slugs_by_year() -> dict:
    """{year: set(player_key)} of players carrying ANY source FV in a snapshot
    dated that year or earlier (i.e. 'source-graded as of Y')."""
    con = sqlite3.connect(str(ROOT / "prospects.db"))
    per = {}
    for pk, sd in con.execute(
            "SELECT player_key, snapshot_date FROM snapshots WHERE fv IS NOT NULL"):
        y = int(str(sd)[:4])
        per.setdefault(y, set()).add(pk)
    con.close()
    cum, acc = {}, set()
    for y in range(2005, 2027):
        acc = acc | per.get(y, set())
        cum[y] = set(acc)
    return cum


def primary_row(rows, group):
    """Same primary-level rule as efv_dataset._milb_features: highest level clearing
    the module exposure floor, else the most-exposed level."""
    expo_key = "pa" if group == "hitting" else "bf"
    minpa = 50 if group == "hitting" else 60
    present = sorted({r.get("level") for r in rows if r.get("level") in mh._LEVEL_RANK},
                     key=lambda lv: -mh._LEVEL_RANK[lv])
    if not present:
        return None, None
    for lv in present:
        lr = mh.level_row(rows, lv, group)
        if (_f(lr.get(expo_key)) or 0.0) >= minpa:
            return lv, lr
    lv = max(present, key=lambda l: _f((mh.level_row(rows, l, group) or {}).get(expo_key)) or 0.0)
    return lv, mh.level_row(rows, lv, group)


def build(years=(2015, 2016, 2017, 2018, 2019)):
    mlbs = mlb_seasons_by_id()
    names = mlb_name_by_id()
    cw = career_war_by_slug()
    graded = graded_slugs_by_year()
    rows = []
    for Y in years:
        for side, group in (("hit", "hitting"), ("pit", "pitching")):
            idx = pidx(Y, group)
            for mid, rr in idx.items():
                milb = [r for r in rr if r.get("level") != "MLB"]
                if not milb:
                    continue
                lvl, row = primary_row(milb, group)
                if lvl not in LEVELS or row is None:
                    continue
                expo = _f(row.get("pa" if group == "hitting" else "bf")) or 0.0
                nm = row.get("name") or names.get(mid) or ""
                slug = normalize_key(nm) if nm else None
                seas = mlbs.get(mid) or {}
                debut = min(seas) if seas else None
                # MLB exposure strictly AFTER the cohort season (a player already in
                # MLB before/at Y is not a thin-sample prospect analog).
                pre_mlb = bool(seas) and min(seas) <= Y
                rows.append({
                    "mlbam": mid, "name": nm, "slug": slug, "year": Y, "side": side,
                    "level": lvl, "expo": expo, "age": _f(row.get("age")),
                    "pre_mlb": pre_mlb, "debut_year": debut,
                    "graded_as_of": bool(slug and slug in graded.get(Y, set())),
                    "ever_graded": bool(slug and slug in graded.get(2026, set())),
                    "has_war_row": bool(slug and slug in cw),
                })
    return rows


def label(rows):
    """Attach the realized bust label. bust = first-6-MLB-season summed bWAR < 3.0
    (Clemens bucket 0: < 0.5 WAR/season talent over the 6-year control window).
    Never reached MLB -> bust with CERTAINTY (an exact, WAR-free label)."""
    cw = career_war_by_slug()
    mlbs = mlb_seasons_by_id()
    for r in rows:
        seas = mlbs.get(r["mlbam"]) or {}
        post = {y: e for y, e in seas.items() if y > r["year"]}
        if not post:
            r["outcome"] = "no_mlb"
            r["bust"] = 1
            r["war6"] = 0.0
            continue
        dy = min(post)
        r["debut_after"] = dy
        wars = cw.get(r["slug"]) if r["slug"] else None
        if wars is None:
            r["outcome"] = "mlb_no_war"
            r["bust"] = None
            r["war6"] = None
            continue
        w6 = sum(v for y, v in wars.items() if dy <= y <= dy + 5)
        r["war6"] = round(w6, 2)
        r["n_obs"] = sum(1 for y in range(dy, dy + 6) if y <= 2026)
        r["outcome"] = "mlb_war"
        r["bust"] = 1 if w6 < 3.0 else 0
    return rows


if __name__ == "__main__":
    rows = label(build())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cohort_raw.json").write_text(json.dumps(rows), encoding="utf-8")
    print("rows", len(rows))
    import collections
    print(collections.Counter(r["outcome"] for r in rows))
    print(collections.Counter((r["year"], r["side"]) for r in rows))
