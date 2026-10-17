# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""MiLB fielding runs (MFR) sidecar for the PROSPX prospect pages: data/milb_fielding_runs.json.

Served because docs/sdr-2026-08-18/MILB_FIELDING_RUNS_GATE.md estimand (b) PASSED on its one
read (data/milb_fielding_runs_eval.json): pre-debut MFR ranks later MLB fielding runs. The
gate's part 6 licenses a defense block by position (runs per 1,000 innings, a reliability band
from the shrinkage, the levels it was measured at). Descriptive: never a grade, rank or sort
input, and it enters no eFV, eWAR or projection number.

Per tracked hitter (players.is_pitcher = 0 with a StatsAPI id on its statline), per position
with INN_FLOOR or more MiLB innings over 2021 to 2026 (seasons before the MLB debut season for
a player who has debuted, the validated predictor's window):
    mfr          AAA-equivalent fielding runs per 1,000 innings (the gate's MFR), one decimal
    inn          MiLB innings at the position
    rel          reliability inn / (inn + k), k the position's split-half constant
    band         low (< 0.35), medium (< 0.60) or high reliability
    levels       [level, innings] by innings, the levels the reading comes from
    seasons      [first, last] season of the innings

The claim line is derived from the eval artifact at export time; nothing is hardcoded. With
MILB_FIELDING_RUNS_SERVE False, or a missing or unpassed eval artifact, or missing season
tables, nothing is written (the committed file stays as it is).

    python milb_fielding_runs_export.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import milb_fielding_runs as M  # noqa: E402

#: The serving switch (gate part 6). False writes nothing.
MILB_FIELDING_RUNS_SERVE = True

DATA = ROOT / "data"
OUT_PATH = DATA / "milb_fielding_runs.json"
EVAL_PATH = DATA / "milb_fielding_runs_eval.json"
DB_PATH = ROOT / "prospects.db"
BANDS = ((0.35, "low"), (0.60, "medium"), (1.01, "high"))
MAX_POSITIONS = 4


def band_of(rel: float) -> str:
    for cut, name in BANDS:
        if rel < cut:
            return name
    return "high"


def first_mlb_season() -> dict[int, int]:
    first: dict[int, int] = {}
    for s in range(2000, M.LAST_MLB + 1):
        p = M.STATSAPI_FIELD / f"fld_{s}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for blk in d.get("stats") or []:
            for sp in blk.get("splits") or []:
                pid = (sp.get("player") or {}).get("id")
                if pid is not None and int(pid) not in first:
                    first[int(pid)] = s
    return first


def tracked_hitters(db_path: Path = DB_PATH) -> dict[str, int]:
    """{player_key: mlbam} for tracked non-pitchers with a StatsAPI id on their statline."""
    out: dict[str, int] = {}
    with sqlite3.connect(db_path) as con:
        hitters = {r[0] for r in con.execute(
            "SELECT player_key FROM players WHERE COALESCE(is_pitcher, 0) = 0")}
        for pk, pj in con.execute("SELECT player_key, payload_json FROM statlines"):
            if pk not in hitters:
                continue
            try:
                mid = (json.loads(pj) or {}).get("mlbam_id")
            except (TypeError, ValueError):
                continue
            if mid:
                out[pk] = int(mid)
    return out


def claim_from_eval(ev: dict) -> str:
    b = ev["b_mlb"]["primary"]
    t1, t2 = b["T1"], b["T2"]
    return (f"Validated once (MILB_FIELDING_RUNS_GATE): among players who debuted 2022 to 2024, "
            f"pre-debut MFR ranked later MLB fielding runs at Spearman {t1['point']:.2f} with "
            f"B-Ref rfield ({t1['n']} players, LB95 {t1['lb95']:.2f}) and {t2['point']:.2f} with "
            f"OAA ({t2['n']} players, LB95 {t2['lb95']:.2f}). Not shown to add to the scouting "
            f"field grade (that read was underpowered).")


def build_payload(st, meta: dict, ev: dict, key2mlbam: dict[str, int], debut: dict[int, int],
                  generated_at: str | None = None) -> dict:
    kpos = meta["k"]
    F = {s: float(meta["levels"]["F"][M.SPORTS[s]]) for s in M.SPORTS}
    want = set(key2mlbam.values())
    s = st[st.pid.isin(want)].copy()
    if len(s):
        d = s.pid.map(debut).astype("float")
        s = s[d.isna() | (s.season < d.fillna(9999))]
    by: dict = {}
    if len(s):
        g = M.mfr(s, kpos, F, keys=("pid", "pos"))
        g = g[g.inn >= M.INN_FLOOR]
        lv = (s.groupby(["pid", "pos", "sport"]).inn.sum().reset_index())
        span = s.groupby(["pid", "pos"]).season.agg(["min", "max"])
        for r in g.sort_values(["pid", "inn"], ascending=[True, False]).itertuples(index=False):
            pid, pos = int(r.pid), int(r.pos)
            rec = by.setdefault(str(pid), {"positions": []})
            if len(rec["positions"]) >= MAX_POSITIONS:
                continue
            levels = lv[(lv.pid == pid) & (lv.pos == pos)].sort_values("inn", ascending=False)
            rel = float(r.reliability)
            rec["positions"].append({
                "pos": M.POS_NAME[str(pos)], "mfr": round(float(r.mfr), 1),
                "inn": int(round(float(r.inn))), "rel": round(rel, 2), "band": band_of(rel),
                "levels": [[M.SPORTS[int(x.sport)], int(round(float(x.inn)))]
                           for x in levels.itertuples(index=False) if x.inn >= 1],
                "seasons": [int(span.loc[(pid, pos), "min"]), int(span.loc[(pid, pos), "max"])],
            })
            if pid in debut:
                rec["pre_debut_only"] = True
    keys = {k: str(v) for k, v in key2mlbam.items() if str(v) in by}
    return {
        "generated_at": generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gate": M.GATE_DOC,
        "eval_artifact": "data/milb_fielding_runs_eval.json",
        "what": ("MiLB fielding runs (MFR): fielding runs above the level-position average per "
                 "1,000 innings from MiLB play-by-play 2021 to 2026, shrunk by reliability and "
                 "put on an AAA-equivalent scale. Descriptive; never a grade, rank or sort input."),
        "units": "AAA-equivalent runs per 1,000 innings",
        "claim": claim_from_eval(ev),
        "inn_floor": M.INN_FLOOR,
        "reliability_bands": {"low": "< 0.35", "medium": "0.35 to 0.60", "high": ">= 0.60"},
        "level_factors": meta["levels"]["F"],
        "n_players": len(by),
        "key_to_mlbam": keys,
        "by_mlbam": by,
    }


def run(persist: bool = True, *, tables=None, eval_path: Path = EVAL_PATH,
        out_path: Path = OUT_PATH, db_path: Path = DB_PATH) -> dict | None:
    import pandas as pd
    if not MILB_FIELDING_RUNS_SERVE:
        print("milb_fielding_runs_export: MILB_FIELDING_RUNS_SERVE is False; nothing written")
        return None
    tables = Path(tables) if tables else M.TABLES
    st_path, meta_path = tables / "season_table.parquet", tables / "build_meta.json"
    if not (st_path.exists() and meta_path.exists() and eval_path.exists()):
        print("milb_fielding_runs_export: season tables or eval artifact missing; nothing written")
        return None
    ev = json.loads(eval_path.read_text(encoding="utf-8"))
    if ev.get("dry_run") or (ev.get("verdicts") or {}).get("b") != "PASS":
        print("milb_fielding_runs_export: the eval artifact does not carry a (b) PASS; nothing written")
        return None
    st = pd.read_parquet(st_path)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    payload = build_payload(st, meta, ev, tracked_hitters(db_path), first_mlb_season())
    if persist:
        out_path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"milb_fielding_runs_export: wrote {out_path.name} ({payload['n_players']} players)")
    return payload


if __name__ == "__main__":
    run()
