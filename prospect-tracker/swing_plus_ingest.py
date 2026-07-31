# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
#
# Swing+ model (c) 2026 Will Cahoon (@willcolqhn) - vendored inference
# (vendor_swing_plus.py + model/swing_plus/swing_plus_model_v1.joblib),
# consumed with attribution. eephus.io runs scoring only.

"""Swing+ ingestion - scores MLB bat-tracking swings through Will
Cahoon's Swing+ model and writes the platform sidecar.

WHO GETS A SCORE (the honest data boundary, stated everywhere this
surfaces): Statcast bat tracking exists ONLY at the MLB level, 2024+.
There is NO public MiLB bat tracking at any season (verified against
the Savant minors aggregates 2023-2026). So Swing+ renders on players
with MLB swings - debuted prospects, FA-class hitters, projections
veterans - and a pre-debut prospect card shows it only after the
player debuts.

PIPELINE
  pool      hitters with an mlbam id from: debuts.json (debut 2024+),
            the FA class (fa_class.json), and /projections/ veterans -
            extensible via score_pool(mlbams).
  fetch     per (player, season) pitch-level CSV from the Savant
            statcast_search API (batters_lookup), seasons 2024+,
            cached under .cache/swing_pitches/ (current season uses a
            short TTL; closed seasons are immutable). Polite: 1.5s
            throttle, full param skeleton (sparse params fall back
            silently - the Phase-4b lesson).
  score     vendor_swing_plus.SwingPlusModel.score_to_leaderboard on
            the pooled swings (the model applies its own competitive-
            swing filter; profiles under its min_swings floor are
            EXCLUDED, and kept scores shrink toward 100 with weight
            n_swings/(n_swings+reliability_k)).
  output    data/swing_plus.json: {mlbam: {swing_plus, n_swings,
            seasons, name}} + provenance block.

Run: python swing_plus_ingest.py [--limit N]   (also wired into
run_monthly after the statcast steps; cache makes reruns cheap)
"""

from __future__ import annotations

import json
import logging
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "swing_plus.json"
CACHE_DIR = ROOT / ".cache" / "swing_pitches"
MODEL_PATH = ROOT / "model" / "swing_plus" / "swing_plus_model_v1.joblib"

FIRST_TRACKING_SEASON = 2024          # MLB bat tracking begins
THROTTLE_S = 1.5
CURRENT_TTL_S = 6 * 86400             # current-season refetch cadence

# Full statcast_search skeleton + per-batter filter. Sparse param sets
# fall back to defaults silently, so every field rides along.
SEARCH = ("https://baseballsavant.mlb.com/statcast_search/csv?all=true"
          "&hfPT=&hfAB=&hfBBT=&hfPR=&hfZ=&stadium=&hfBBL=&hfNewZones="
          "&hfGT=R%7C&hfC=&hfSea={season}%7C&hfSit=&player_type=batter"
          "&hfOuts=&opponent=&pitcher_throws=&batter_stands=&hfSA="
          "&game_date_gt=&game_date_lt=&hfInfield=&team=&position="
          "&hfOutfield=&hfRO=&home_road=&hfFlag=&hfPull=&metric_1=&hfInn="
          "&min_pitches=0&min_results=0&group_by=name"
          "&sort_col=pitches&player_event_sort=api_p_release_speed"
          "&sort_order=desc&min_pas=0&type=details"
          "&batters_lookup%5B%5D={mlbam}")

_NEED_COLS = ("batter", "bat_speed", "swing_length", "attack_angle",
              "attack_direction", "swing_path_tilt",
              "intercept_ball_minus_batter_pos_x_inches",
              "intercept_ball_minus_batter_pos_y_inches", "type")
_last_fetch = 0.0


def _throttle() -> None:
    global _last_fetch
    dt = time.time() - _last_fetch
    if dt < THROTTLE_S:
        time.sleep(THROTTLE_S - dt)
    _last_fetch = time.time()


def fetch_player_season(mlbam: int, season: int, fetch: bool = True) -> Path | None:
    """Cached per-(player, season) pitch CSV. Closed seasons immutable;
    the current season refetches on a short TTL."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{mlbam}_{season}.csv"
    if path.exists():
        if season < date.today().year:
            return path
        if time.time() - path.stat().st_mtime <= CURRENT_TTL_S:
            return path
    if not fetch:
        return path if path.exists() else None
    _throttle()
    url = SEARCH.format(season=season, mlbam=mlbam)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            path.write_bytes(r.read())
    except Exception as e:                                    # noqa: BLE001
        log.warning("swing fetch failed %s/%s: %s", mlbam, season, e)
        return path if path.exists() else None
    return path


def default_pool() -> dict[int, str]:
    """{mlbam: name} - debuted prospects (2024+ debuts) + FA-class
    hitters + projections veterans (hitters only where side is known)."""
    pool: dict[int, str] = {}
    try:
        for d in json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8")):
            dd = d.get("debut_date") or ""
            pos = (d.get("position") or "").upper()
            if (d.get("mlbam_id") and dd[:4].isdigit()
                    and int(dd[:4]) >= FIRST_TRACKING_SEASON
                    and pos not in ("P", "SP", "RP", "LHP", "RHP")):
                # TWP stays IN the pool - two-way hitters swing too
                pool[int(d["mlbam_id"])] = d.get("player_name") or ""
    except (OSError, ValueError):
        log.warning("swing pool: debuts.json unavailable")
    try:
        fa = json.loads((DATA_DIR / "fa_class.json").read_text(encoding="utf-8"))
        # Members carry pos/name only (no MLBAM id) - resolve by name via the
        # shared war_daily index, same as fa_export. Unresolvable/ambiguous
        # names just stay out of the pool.
        import fa_ident
        season = date.today().year
        for p in fa.get("members") or []:
            pos = (p.get("pos") or "").upper()
            name = p.get("name") or ""
            if not name or not pos or pos.startswith(("SP", "RP", "P", "LHP", "RHP")):
                continue
            mid = fa_ident.resolve(name, range(season - 4, season))
            if mid:
                pool.setdefault(int(mid), name)
    except Exception:                                         # noqa: BLE001
        log.warning("swing pool: fa_class.json unavailable or FA resolve failed")
    # two-way projections vets (the Ohtani case: debut pre-2024 and a
    # pitcher-coded position would otherwise exclude the best swing in
    # the sport)
    try:
        mp = json.loads((DATA_DIR / "mlb_projections.json").read_text(encoding="utf-8"))
        for v in mp.get("vets") or []:
            if v.get("twoWay") and v.get("mlbam"):
                pool.setdefault(int(v["mlbam"]), v.get("name") or "")
    except (OSError, ValueError):
        pass
    return pool


def score_pool(pool: dict[int, str], fetch: bool = True,
               limit: int | None = None) -> dict:
    import warnings
    import pandas as pd
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")     # cross-version sklearn unpickle
        from vendor_swing_plus import SwingPlusModel
        model = SwingPlusModel(MODEL_PATH)
    # The artifact's real sample knobs, surfaced for provenance: profiles
    # under min_swings are excluded; kept scores shrink toward 100 with
    # weight n/(n+reliability_k).
    knobs = {"min_swings": int(model.min_swings),
             "reliability_k": int(model.reliability_k)}
    seasons = range(FIRST_TRACKING_SEASON, date.today().year + 1)
    frames = []
    mlbams = sorted(pool)
    if limit:
        mlbams = mlbams[:limit]
    fetched = 0
    for mlbam in mlbams:
        for season in seasons:
            path = fetch_player_season(mlbam, season, fetch=fetch)
            if path is None:
                continue
            try:
                df = pd.read_csv(path, usecols=lambda c: c in _NEED_COLS,
                                 low_memory=False)
            except (ValueError, OSError):
                continue
            if "bat_speed" not in df.columns or df["bat_speed"].notna().sum() == 0:
                continue
            df["season"] = season
            frames.append(df)
            fetched += 1
    if not frames:
        return {"players": {}, "n_scored": 0, **knobs}
    pitches = pd.concat(frames, ignore_index=True)
    # group_by=[] pools every season's swings into ONE per-batter score
    # (the model's reliability shrink handles small samples).
    # The vendored pipelines score on df[features].values: df[features] preserves the
    # FITTED column order, so the predictions are correct even though the array carries
    # no names. The "X does not have valid feature names" UserWarning (and the cross-
    # version unpickle notice, which can re-fire on first predict) are precautionary
    # only - scores are validated ~100-centered. Suppress at this boundary, matching
    # the load wrap above; a genuine break would surface as out-of-range scores, not here.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        board = model.score_pitch_level(pitches, group_by=[])
    out: dict[str, dict] = {}
    for row in board.itertuples(index=False):
        mid = int(row.batter)
        out[str(mid)] = {
            "swing_plus": round(float(row.swing_plus), 1),
            "n_swings": int(row.n_swings),
            "name": pool.get(mid, ""),
        }
    # Per-season Swing+ slices (W6, DISPLAY-ONLY): the SAME competitive-swing
    # filter and the SAME k=360 reliability shrink, grouped by season instead
    # of pooled. Deliberate display-only choice: seasons under the model's
    # min_swings floor (180) are still SCORED but flagged low_n true rather
    # than dropped - 2024 bat tracking has partial coverage and dropping the
    # season would blank a card's trend line. The shrink already pulls thin
    # seasons hard toward 100, so a low_n slice reads conservatively. Nothing
    # downstream scores on these slices; the pooled swing_plus above is the
    # served number and is computed first, untouched, from the same swings.
    orig_min = model.min_swings
    try:
        model.min_swings = 2        # season floor off; n=1 lacks a std anyway
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sboard = model.score_pitch_level(pitches, group_by=["season"])
    finally:
        model.min_swings = orig_min
    for row in sboard.itertuples(index=False):
        mid = str(int(row.batter))
        if mid not in out:
            continue                # season slices only for pooled-scored bats
        sl = {"swing_plus": round(float(row.swing_plus), 1),
              "n_swings": int(row.n_swings)}
        if sl["n_swings"] < orig_min:
            sl["low_n"] = True
        out[mid].setdefault("seasons", {})[str(int(row.season))] = sl
    for rec in out.values():
        if "seasons" in rec:
            rec["seasons"] = dict(sorted(rec["seasons"].items()))
    return {"players": out, "n_scored": len(out), "n_player_seasons": fetched,
            **knobs}


def run(persist: bool = True, fetch: bool = True,
        limit: int | None = None) -> dict:
    pool = default_pool()
    log.info("swing_plus pool: %d hitters", len(pool))
    res = score_pool(pool, fetch=fetch, limit=limit)
    payload = {
        "generated_at": date.today().isoformat(),
        "model": "swing_plus v1.0.0 (Will Cahoon, vendored inference)",
        "data_boundary": "MLB bat tracking 2024+ only - no public MiLB "
                         "tracking exists; pre-debut prospects cannot score",
        # the artifact's real sample knobs (the old min_swings_full_strength
        # field misdescribed the model; no consumer read it)
        "min_swings": res.get("min_swings"),
        "reliability_k": res.get("reliability_k"),
        "n_scored": res["n_scored"],
        "players": res["players"],
    }
    if persist and res["n_scored"]:
        OUT_PATH.write_text(json.dumps(payload, separators=(",", ":")),
                            encoding="utf-8")
        log.info("wrote %s (%d players)", OUT_PATH, res["n_scored"])
    return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    lim = None
    if "--limit" in sys.argv:
        lim = int(sys.argv[sys.argv.index("--limit") + 1])
    rep = run(limit=lim)
    top = sorted(rep["players"].items(),
                 key=lambda kv: -kv[1]["swing_plus"])[:10]
    print(f"scored {rep['n_scored']} hitters")
    for mid, r in top:
        print(f"  {r['swing_plus']:6.1f}  {r['name']} ({mid}, n={r['n_swings']})")
