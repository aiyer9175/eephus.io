#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""build_abs_ledger - the ABS challenge ledger over the cached game feeds.

docs/eabs-2026-10-15/ABS_LEDGER.md. Reads `.cache/game_feeds` (and, once fetched,
`.cache/EWAR_T4_ABS_LEDGER/aaa_feeds`), writes under data/_labs/abs_ledger/ only
(never shipped):

  mlb_2026.json   every challenge row of the 2026 MLB regular season, columnar,
                  with the challengers' names; refuses if one feed breaks the
                  invariant (per club, overturned rows = usedSuccessful and upheld
                  rows = usedFailed).
  milb.json       every challenge row of the minor-league feeds that carry
                  challenges, columnar, each feed's invariant result attached.
  coverage.json   frames, invariant, role checks, flags, and the AAA probe.

Subcommands:
  (none)          build the ledgers from the caches.
  --aaa-probe     fetch the registered AAA 2022-2025 probe (40 full feeds a season)
                  into .cache/EWAR_T4_ABS_LEDGER/aaa_probe/ and write its block.
  --aaa-fetch Y   fetch every final regular-season AAA game of season Y with the
                  fields filter into .cache/EWAR_T4_ABS_LEDGER/aaa_feeds/, after the
                  filtered and full payloads give identical rows on the probe games.

The ledger values nothing (no run value, no win value, no rating)."""
from __future__ import annotations

import argparse
import collections
import datetime as _dt
import gzip
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import abs_ledger as al  # noqa: E402

FEEDS = ROOT / ".cache" / "game_feeds"
TASK_CACHE = ROOT / ".cache" / "EWAR_T4_ABS_LEDGER"
PROBE_DIR = TASK_CACHE / "aaa_probe"
AAA_DIR = TASK_CACHE / "aaa_feeds"
CORPUS_PLAYS = ROOT / ".cache" / "pbp_corpus" / "plays"
OUT_DIR = ROOT / "data" / "_labs" / "abs_ledger"
PROBE_SEASONS = (2022, 2023, 2024, 2025)
PROBE_N = 40
MIN_GAP_S = 0.25
HOST = "https://statsapi.mlb.com"
USER_AGENT = "eephus.io research (ABS challenge ledger)"
FEED_FIELDS = ",".join((
    "gamePk", "gameData", "game", "pk", "type", "season", "datetime", "officialDate", "teams",
    "away", "home", "id", "sport", "parentOrgId", "absChallenges", "hasChallenges",
    "usedSuccessful", "usedFailed", "remaining", "status", "abstractGameState", "liveData",
    "linescore", "scheduledInnings", "plays", "allPlays", "about", "atBatIndex", "halfInning",
    "isTopInning", "inning", "isComplete", "matchup", "batter", "pitcher", "postOnFirst",
    "postOnSecond", "postOnThird", "count", "balls", "strikes", "outs", "result", "awayScore",
    "homeScore", "runners", "movement", "start", "end", "isOut", "details", "playIndex", "call",
    "code", "playEvents", "index", "pitchNumber", "isPitch", "isSubstitution", "position",
    "player", "reviewDetails", "isOverturned", "inProgress", "reviewType", "challengeTeamId",
    "additionalReviews", "pitchData", "coordinates", "pX", "pZ", "strikeZoneTop",
    "strikeZoneBottom", "boxscore", "players", "person", "battingOrder", "allPositions",
    "pitchers", "fullName"))


def _load(path: Path):
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    try:
        import orjson
        return orjson.loads(raw)
    except ImportError:  # pragma: no cover
        return json.loads(raw)


def _meta(feed: dict) -> tuple:
    gd = feed.get("gameData") or {}
    g = gd.get("game") or {}
    sport = (((gd.get("teams") or {}).get("home") or {}).get("sport") or {}).get("id")
    state = (gd.get("status") or {}).get("abstractGameState")
    return al._int(g.get("season")), g.get("type"), al._int(sport), state


def _names(feed: dict, rows: list) -> dict:
    out = {}
    for p in al._plays(feed):
        for e in [p] + list(p.get("playEvents") or []):
            for rd in al._reviews_of((e or {}).get("reviewDetails")):
                who = rd.get("player") or {}
                if who.get("id") is not None and who.get("fullName"):
                    out[int(who["id"])] = who["fullName"]
    return out


def scan_one(path: str):
    """One feed -> (file, season, type, level, state, rows, checks, invariant,
    names), or None for a feed outside every frame."""
    try:
        feed = _load(Path(path))
    except Exception as exc:  # a truncated cache file is reported, never fatal
        return {"file": os.path.basename(path), "error": str(exc)[:120]}
    season, gtype, level, state = _meta(feed)
    absc = (feed.get("gameData") or {}).get("absChallenges") or {}
    in_mlb = level == 1 and season == 2026 and gtype == "R"
    rows, checks = al.challenge_rows(feed)
    if not in_mlb and not rows and not absc.get("hasChallenges"):
        return None
    return {"file": os.path.basename(path), "season": season, "type": gtype, "level": level,
            "state": state, "rows": rows, "checks": checks, "inv": al.check_feed(feed, rows),
            "inv_zone": al.check_feed(feed, rows, kinds=("zone",)),
            "names": _names(feed, rows)}


def _scan(paths: list, procs: int = 4) -> list:
    with Pool(procs) as pool:
        got = pool.map(scan_one, [str(p) for p in paths], chunksize=40)
    return [g for g in got if g]


def _li_join(rows: list) -> int:
    """MLB's plate-appearance leverage index from the pbp corpus, in place."""
    import pandas as pd
    path = CORPUS_PLAYS / "2026"
    if not path.exists():
        return 0
    df = pd.read_parquet(path, columns=["game_pk", "at_bat_index", "leverage_index"])
    li = {(int(g), int(a)): (None if pd.isna(v) else round(float(v), 2))
          for g, a, v in df.itertuples(index=False)}
    n = 0
    for r in rows:
        v = li.get((r["game_pk"], r["at_bat_index"]))
        r["li_pa"] = v
        n += v is not None
    return n


def _summary(results: list, rows: list) -> dict:
    by = lambda k: dict(sorted(collections.Counter(str(r[k]) for r in rows).items()))  # noqa: E731
    over = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        over[(r["kind"], r["role"])][0] += 1
        over[(r["kind"], r["role"])][1] += bool(r["overturned"])
    flags = collections.Counter()
    for r in rows:
        for f in (r["flags"] or "").split(","):
            if f:
                flags[f] += 1
    chk = collections.Counter()
    for g in results:
        for k, v in g["checks"].items():
            chk[k] += v
    inv_bad = [g["file"] for g in results if not g["inv"]["ok"]]
    zone_bad = [g["file"] for g in results if not g["inv_zone"]["ok"]]
    named = [r for r in rows if r["role"] in ("batter", "pitcher", "catcher")]
    agree = sum(1 for r in named if (r["role"] == "batter") == (r["role_by_side"] == "batter")
                and r["role_by_side"] is not None)
    return {
        "games": len(results),
        "games_has_challenges": sum(1 for g in results if g["inv"]["has_challenges"]),
        "games_with_rows": sum(1 for g in results if g["rows"]),
        "rows": len(rows),
        "by_kind": by("kind"), "by_role": by("role"), "by_source": by("source"),
        "overturned_by_kind_role": {f"{k}|{r}": {"n": v[0], "overturned": v[1]}
                                    for (k, r), v in sorted(over.items())},
        "flags": dict(sorted(flags.items())),
        "checks": dict(sorted(chk.items())),
        "invariant": {"feeds_ok": len(results) - len(inv_bad), "feeds_mismatch": len(inv_bad),
                      "mismatch_files": sorted(inv_bad)[:200],
                      "zone_only_feeds_ok": len(results) - len(zone_bad),
                      "zone_only_note": ("added after the registration: the same comparison over zone rows "
                                         "only, because the 2025 Single-A feeds leave check-swing challenges "
                                         "out of absChallenges")},
        "role_by_side": {"rows_with_named_role": len(named), "agree": agree,
                         "rows_without_challenger_id": sum(1 for r in rows if r["challenger_id"] is None),
                         "by_value": by("role_by_side")},
    }


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, separators=(",", ":"), ensure_ascii=True)
        fh.write("\n")
    os.replace(tmp, path)


def build(procs: int = 4) -> dict:
    t0 = time.time()
    paths = sorted(FEEDS.glob("*.json"))
    extra = sorted(AAA_DIR.glob("*.json.gz")) if AAA_DIR.exists() else []
    results = _scan(paths + extra, procs)
    errors = [g for g in results if "error" in g]
    results = [g for g in results if "error" not in g]
    mlb = [g for g in results if g["level"] == 1 and g["season"] == 2026 and g["type"] == "R"]
    milb = [g for g in results if g not in mlb]
    bad = [g["file"] for g in mlb if not g["inv"]["ok"]]
    if bad:
        raise SystemExit(f"REFUSED: {len(bad)} MLB 2026 feeds break the invariant, first {bad[:10]}")
    mlb_rows = [r for g in mlb for r in g["rows"]]
    mlb_rows.sort(key=lambda r: (r["official_date"] or "", r["game_pk"], r["at_bat_index"], r["event_index"]))
    n_li = _li_join(mlb_rows)
    names = {}
    for g in mlb:
        names.update(g["names"])
    gen = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = "docs/eabs-2026-10-15/ABS_LEDGER.md"
    _write(OUT_DIR / "mlb_2026.json", {
        "schema": 1, "generated_at": gen, "registration": doc,
        "frame": "MLB 2026 regular season, every cached final feed in .cache/game_feeds",
        "values_nothing": "no run value, no win value, no rating: a measurement substrate",
        **al.columnar(mlb_rows),
        "names": {str(k): v for k, v in sorted(names.items())},
    })
    by_level = collections.defaultdict(list)
    for g in milb:
        for r in g["rows"]:
            r["invariant_ok"] = g["inv"]["ok"]
            r["invariant_zone_ok"] = g["inv_zone"]["ok"]
        by_level[g["level"]].append(g)
    fields = list(al.FIELDS) + ["invariant_ok", "invariant_zone_ok"]
    for lvl, gs in sorted(by_level.items()):
        lrows = sorted((r for g in gs for r in g["rows"]),
                       key=lambda r: (r["season"], r["official_date"] or "", r["game_pk"],
                                      r["at_bat_index"], r["event_index"]))
        lnames = {}
        for g in gs:
            lnames.update(g["names"])
        _write(OUT_DIR / MILB_FILES.get(lvl, f"level{lvl}.json"), _milb_doc(gen, doc, lvl, fields, lrows, lnames))
    frames = {"mlb_2026": dict(_summary(mlb, mlb_rows), li_joined=n_li)}
    groups = collections.defaultdict(list)
    for g in milb:
        groups[(g["level"], g["season"])].append(g)
    for (lvl, season), gs in sorted(groups.items()):
        frames[f"level{lvl}_{season}"] = _summary(gs, [r for g in gs for r in g["rows"]])
    cov_path = OUT_DIR / "coverage.json"
    prev = json.loads(cov_path.read_text(encoding="utf-8")) if cov_path.exists() else {}
    cov = {"schema": 1, "generated_at": gen, "registration": doc,
           "levels": {"1": "MLB", "11": "AAA", "12": "AA", "13": "High-A", "14": "Single-A", "16": "Rookie"},
           "files": {"mlb_2026.json": "MLB 2026", **{MILB_FILES.get(k, f"level{k}.json"): f"level {k}"
                                                     for k in sorted(by_level)}},
           "feeds_scanned": len(paths) + len(extra), "unreadable_feeds": [g["file"] for g in errors],
           "frames": frames, "aaa_probe": prev.get("aaa_probe"),
           "aaa_fetch": prev.get("aaa_fetch"),
           "seconds": round(time.time() - t0, 1)}
    _write(cov_path, cov)
    return cov


MILB_FILES = {11: "aaa.json", 14: "single_a.json"}


def _milb_doc(gen: str, doc: str, lvl: int, fields: list, rows: list, names: dict) -> dict:
    return {
        "schema": 1, "generated_at": gen, "registration": doc, "level": lvl,
        "frame": ("minor-league feeds carrying challenges at this level: .cache/game_feeds and "
                  ".cache/EWAR_T4_ABS_LEDGER/aaa_feeds"),
        "values_nothing": "no run value, no win value, no rating: a measurement substrate",
        "invariant_note": ("invariant_ok false marks a feed whose rows do not equal its "
                           "absChallenges counts; such a feed is excluded from any stability frame. "
                           "invariant_zone_ok is the same comparison over zone rows only (added after "
                           "the registration: the 2025 Single-A feeds leave check-swing challenges out "
                           "of absChallenges)"),
        "role_by_side_note": ("challenge_side is the challenging club's side; role_by_side reads it "
                              "under the rule that only the batter challenges for the offense and only "
                              "the pitcher or catcher for the defense. Feeds before 2026 carry no "
                              "challenger id, so role is unresolved there and role_by_side is the read"),
        "fields": fields, "rows": [[r.get(f) for f in fields] for r in rows],
        "names": {str(k): v for k, v in sorted(names.items())},
    }


# --------------------------------------------------------------------------- #
# The AAA probe and fetch (network, polite, into .cache/EWAR_T4_ABS_LEDGER only)
# --------------------------------------------------------------------------- #
class _Http:
    def __init__(self):
        import requests
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self.last = 0.0

    def get(self, path: str, params: dict | None = None, tries: int = 3):
        for k in range(tries):
            wait = MIN_GAP_S - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            try:
                r = self.s.get(HOST + path, params=params, timeout=60)
            except Exception:
                time.sleep(2.0 * (k + 1))
                continue
            if r.status_code == 200:
                return r.content
            time.sleep(2.0 * (k + 1))
        return None


def aaa_schedule(http: _Http, season: int) -> list:
    """Final regular-season AAA game pks of a season, in schedule order, once each."""
    path = TASK_CACHE / "schedule" / f"aaa_{season}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        raw = http.get("/api/v1/schedule", {"sportId": 11, "season": season, "gameType": "R"})
        data = json.loads(raw)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    out, seen = [], set()
    for d in data.get("dates") or []:
        for g in d.get("games") or []:
            st = g.get("status") or {}
            pk = al._int(g.get("gamePk"))
            if st.get("abstractGameState") == "Final" and st.get("codedGameState") == "F" and pk not in seen:
                seen.add(pk)
                out.append(pk)
    return out


def _fetch_feed(http: _Http, pk: int, dest: Path, fields: str | None) -> Path | None:
    p = dest / f"{pk}.json.gz"
    if p.exists():
        return p
    raw = http.get(f"/api/v1.1/game/{pk}/feed/live", {"fields": fields} if fields else None)
    if raw is None:
        return None
    dest.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(gzip.compress(raw))
    os.replace(tmp, p)
    return p


def aaa_probe() -> dict:
    http = _Http()
    block = {"design": "docs/eabs-2026-10-15/ABS_LEDGER.md section 5", "per_season": {}}
    for season in PROBE_SEASONS:
        pks = aaa_schedule(http, season)
        n = len(pks)
        pick = sorted({pks[round(i * (n - 1) / (PROBE_N - 1))] for i in range(PROBE_N)}) if n else []
        got = []
        for pk in pick:
            p = _fetch_feed(http, pk, PROBE_DIR / str(season), None)
            if p is not None:
                got.append(p)
        res = [scan_one(str(p)) for p in got]
        res = [r for r in res if r and "error" not in r]
        rows = [x for r in res for x in r["rows"]]
        kinds = collections.Counter(x["kind"] for x in rows)
        block["per_season"][str(season)] = {
            "games_final_scheduled": n, "games_sampled": len(pick), "feeds_read": len(got),
            "games_has_challenges": sum(1 for r in res if r["inv"]["has_challenges"]),
            "games_with_rows": sum(1 for r in res if r["rows"]),
            "rows": len(rows), "rows_per_sampled_game": round(len(rows) / len(got), 2) if got else None,
            "by_kind": dict(kinds),
            "by_role": dict(collections.Counter(x["role"] for x in rows)),
            "invariant_ok_feeds": sum(1 for r in res if r["inv"]["ok"]),
            "invariant_ok_feeds_with_challenges": sum(1 for r in res if r["inv"]["ok"] and r["inv"]["has_challenges"]),
        }
        print(season, json.dumps(block["per_season"][str(season)]), flush=True)
    cov_path = OUT_DIR / "coverage.json"
    cov = json.loads(cov_path.read_text(encoding="utf-8")) if cov_path.exists() else {"schema": 1}
    cov["aaa_probe"] = block
    _write(cov_path, cov)
    return block


def _row_key(rows: list) -> list:
    return [tuple(r.get(f) for f in al.FIELDS) for r in rows]


def aaa_fetch(season: int, limit: int | None = None) -> dict:
    """Fields-filtered fetch of a season, after the filtered-vs-full equality
    check on every probe game of that season."""
    http = _Http()
    probe = sorted((PROBE_DIR / str(season)).glob("*.json.gz"))
    if not probe:
        raise SystemExit(f"REFUSED: no probe feeds for {season}; run --aaa-probe first")
    eq_dir = TASK_CACHE / "aaa_fields_check" / str(season)
    mism = []
    for p in probe:
        pk = int(p.name.split(".")[0])
        q = _fetch_feed(http, pk, eq_dir, FEED_FIELDS)
        full_rows, _ = al.challenge_rows(_load(p))
        filt_rows, _ = al.challenge_rows(_load(q))
        if _row_key(full_rows) != _row_key(filt_rows):
            mism.append(pk)
    if mism:
        raise SystemExit(f"REFUSED: the fields filter changes the rows on {len(mism)} probe games: {mism[:10]}")
    pks = aaa_schedule(http, season)
    if limit:
        pks = pks[:limit]
    ok = miss = 0
    t0 = time.time()
    for i, pk in enumerate(pks):
        src = eq_dir / f"{pk}.json.gz"
        if src.exists() and not (AAA_DIR / f"{pk}.json.gz").exists():
            AAA_DIR.mkdir(parents=True, exist_ok=True)
            (AAA_DIR / f"{pk}.json.gz").write_bytes(src.read_bytes())
        if _fetch_feed(http, pk, AAA_DIR, FEED_FIELDS) is None:
            miss += 1
        else:
            ok += 1
        if i % 250 == 0:
            print(season, i, len(pks), round(time.time() - t0), flush=True)
    cov_path = OUT_DIR / "coverage.json"
    cov = json.loads(cov_path.read_text(encoding="utf-8")) if cov_path.exists() else {"schema": 1}
    fetch = cov.get("aaa_fetch") or {}
    fetch[str(season)] = {"games_final_scheduled": len(aaa_schedule(http, season)), "fetched": ok,
                          "missing": miss, "fields_check_games": len(probe), "fields_check_mismatch": 0}
    cov["aaa_fetch"] = fetch
    _write(cov_path, cov)
    return fetch[str(season)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ABS challenge ledger (data/_labs/abs_ledger, never shipped)")
    ap.add_argument("--aaa-probe", action="store_true")
    ap.add_argument("--aaa-fetch", type=int)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args(argv)
    if a.aaa_probe:
        aaa_probe()
        return 0
    if a.aaa_fetch:
        print(json.dumps(aaa_fetch(a.aaa_fetch, a.limit)))
        return 0
    cov = build(a.procs)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ("overturned_by_kind_role",)}
                      for k, v in cov["frames"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
