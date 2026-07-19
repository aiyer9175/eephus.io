# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""OFFLINE per-season leverage rebuild for the w3b lab lane.

mlb_leverage.fetch_season_leverage() walks the LIVE schedule endpoint and then
live-fetches any game missing from .cache/win_prob (thousands of requests +
404 noise on postponed/exhibition pks). This module produces the SAME
per-pitcher leverage dict (gmli / wpa / entry_inning / ...) with ZERO network:
it iterates the already-cached .cache/win_prob/*.json payloads directly (the
exact pattern of tools/win_prob_walker.py), derives each game's season from
its own payload (first play about.startTime year), and folds through the
UNCHANGED pure accumulators mlb_leverage._fold_game / mlb_leverage._finalize.

Only entry_inning is load-bearing for the w3b gates (rem_plus._is_opener needs
it to drop openers from the true-reliever pool - REM+ itself keeps leverage
out of the talent scale by design); gmli/wpa ride along untouched.

Chunkable + resumable: --start/--count over the sorted file list with a pickled
accumulator checkpoint, so the walk can run as several synchronous foreground
calls. --finalize writes leverage_{season}.json per season.

Run:  python offline_leverage.py --out OUT_DIR [--cache DIR]
      [--start N --count M] [--finalize]
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("EEPHUS_ROOT")
            or r"C:/Users/noah/baseball-projects/BaseballR/prospect-tracker")
sys.path.insert(0, str(ROOT))

import mlb_leverage  # noqa: E402  (pure fold/finalize only - no fetch calls)

DEFAULT_CACHE = ROOT / ".cache" / "win_prob"


def _arg(flag: str, default=None):
    if flag in sys.argv:
        return sys.argv[sys.argv.index(flag) + 1]
    return default


def main() -> None:
    cache = Path(_arg("--cache", DEFAULT_CACHE))
    out = Path(_arg("--out", "."))
    out.mkdir(parents=True, exist_ok=True)
    start = int(_arg("--start", 0))
    count = int(_arg("--count", 10 ** 9))
    ckpt = out / "lev_acc.pkl"

    files = sorted(p.name for p in cache.glob("*.json"))
    if start > 0:
        with open(ckpt, "rb") as fh:
            state = pickle.load(fh)
        assert state["next"] == start, (
            f"checkpoint expects start={state['next']}, got {start}")
        acc_by_season = state["acc"]
        stats = state["stats"]
    else:
        acc_by_season = {}
        stats = {"games": 0, "skipped": 0}

    chunk = files[start:start + count]
    t0 = time.time()
    for i, fn in enumerate(chunk):
        try:
            plays = mlb_leverage._plays_of(json.loads(
                (cache / fn).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            stats["skipped"] += 1
            continue
        if not plays:
            stats["skipped"] += 1
            continue
        about = plays[0].get("about") or {}
        st = about.get("startTime") or about.get("endTime") or ""
        try:
            season = int(st[:4])
        except ValueError:
            stats["skipped"] += 1
            continue
        acc = acc_by_season.setdefault(season, {})
        mlb_leverage._fold_game(acc, plays)
        stats["games"] += 1
        if i % 2000 == 0:
            print(f"  {start + i + 1}/{len(files)} "
                  f"({round(time.time() - t0, 1)}s)", flush=True)

    nxt = min(start + count, len(files))
    with open(ckpt, "wb") as fh:
        pickle.dump({"next": nxt, "acc": acc_by_season, "stats": stats}, fh)
    print(f"chunk done: files {start}..{nxt} of {len(files)} | "
          f"games {stats['games']} skipped {stats['skipped']} | "
          f"{round(time.time() - t0, 1)}s", flush=True)

    if "--finalize" in sys.argv:
        assert nxt == len(files), "cannot finalize before the walk is complete"
        summary = {}
        for season in sorted(acc_by_season):
            fin = mlb_leverage._finalize(acc_by_season[season])
            p = out / f"leverage_{season}.json"
            p.write_text(json.dumps(fin), encoding="utf-8")
            n_entry = sum(1 for v in fin.values()
                          if v.get("entry_inning") is not None)
            summary[season] = {"pitchers": len(fin),
                               "with_entry_inning": n_entry}
        (out / "offline_leverage_coverage.json").write_text(
            json.dumps({"cache_dir": str(cache), "files": len(files),
                        **stats, "seasons": summary}, indent=1),
            encoding="utf-8")
        print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
