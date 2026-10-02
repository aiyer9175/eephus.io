#!/usr/bin/env python
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The In-Game Management NIGHTLY refresh (owner answer 2026-09-25, census M10-05).

WHY IT EXISTS. The play corpus under .cache/pbp_corpus was rebuilt only by hand
(tools/build_pbp_corpus.py --force), so /management/ stayed on the corpus of the
last hand rebuild while the win-probability cache kept growing every night. On
2026-10-02 the served ledger stopped at 2026-09-24 while the cache already held
the season's last 44 games (2026-09-25 to 2026-09-27).

WHAT ONE NIGHT DOES, in order (run_daily step 9e-pre0e):
  1. tools/build_pbp_corpus.refresh_open_season: the OPEN season (this calendar
     year) is fingerprinted by content and rebuilt only when its win_prob files
     changed. Completed seasons stay frozen: never re-read, never rewritten.
  2. When the corpus moved (or an artifact was built from another corpus build),
     the same hand-run chain in the same order: management.py (the steal family,
     management_running.json), mgmt_bunt.py (management_bunt.json), the decision
     ledger and its shard writer (mgmt_decisions.build with freeze_before = the
     open season, so a completed season's shards keep their bytes), and
     mgmt_export.py (management_board.json). The steal and bunt families keep
     their fixed definitions; the win expectancy model and the frozen gate eval
     (management_gate_eval.json) are not refit or re-scored.
  3. Otherwise nothing downstream runs, and the result says why.

The /betting/ Dugout block and the /franchise/ board read management_board.json
at their own later steps, so they pick up the night's board; no priced cell reads
anything written here.

Offline: nothing here fetches. The win_prob cache is filled by the leaderboard
walks earlier in the night.

    python mgmt_nightly.py [--season 2026] [--force]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CORPUS = ROOT / ".cache" / "pbp_corpus"
WIN_PROB = ROOT / ".cache" / "win_prob"
#: The artifacts that stamp the corpus build they were priced from. One that
#: names another build than the manifest's is rebuilt even on an unchanged night
#: (a failed night, or a hand corpus rebuild without the downstream chain).
STAMPED = ("management_running.json", "management_bunt.json",
           "management_decisions.json")

log = logging.getLogger("mgmt_nightly")


def manifest_built_at(corpus: Path | None = None):
    try:
        m = json.loads((Path(corpus or CORPUS) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return m.get("built_at")


def stale_artifacts(built_at, data_dir: Path | None = None) -> list:
    """The stamped artifacts whose corpus_built_at is not `built_at`."""
    out = []
    d = Path(data_dir or ROOT / "data")
    for name in STAMPED:
        try:
            got = json.loads((d / name).read_text(encoding="utf-8")).get("corpus_built_at")
        except (OSError, ValueError):
            got = None
        if not built_at or got != built_at:
            out.append(name)
    return out


def rebuild_downstream(season: int, log_fn=None) -> dict:
    """The hand-run chain of commit 241d8239, in its order. Raises on a refusal so
    the caller files a red; nothing is written past the step that refused."""
    say = log_fn or log.info
    import management
    import mgmt_bunt
    import mgmt_decisions
    import mgmt_export

    run = management.build()
    management.write(run)
    say(f"mgmt nightly: running game {run.get('n_attempts_priced'):,} attempts priced")
    bunt = mgmt_bunt.price()
    if bunt.get("status") != "built":
        raise RuntimeError(f"mgmt_bunt refused: {bunt.get('status')}")
    mgmt_bunt.write(bunt)
    say(f"mgmt nightly: bunt {bunt.get('n_bunts_priced'):,} bunts priced")
    dec = mgmt_decisions.build(freeze_before=season)
    if dec.get("status") != "built":
        raise RuntimeError(f"mgmt_decisions refused: {dec.get('status')}")
    mgmt_decisions.OUT.write_text(
        json.dumps(dec, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    say(f"mgmt nightly: ledger {dec.get('n_all', 0):,} rows, through "
        f"{(dec.get('through_by_season') or {}).get(str(season))}")
    board = mgmt_export.build()
    mgmt_export.OUT.write_text(
        json.dumps(board, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    say(f"mgmt nightly: board {board['running_game']['n_attempts_priced']:,} attempts")
    return {"n_attempts_priced": run.get("n_attempts_priced"),
            "n_bunts_priced": bunt.get("n_bunts_priced"),
            "n_decisions": dec.get("n_all"),
            "through": (dec.get("through_by_season") or {}).get(str(season))}


def run(*, season: int | None = None, cache_dir: Path | None = None,
        corpus: Path | None = None, data_dir: Path | None = None,
        force: bool = False, log_fn=None, downstream=None) -> dict:
    """One night. Returns {"status": "rebuilt" | "skipped", "why", "corpus": the
    refresh result, ...}. `downstream` replaces rebuild_downstream (tests)."""
    from tools import build_pbp_corpus as bpc

    say = log_fn or log.info
    season = int(season or date.today().year)
    cache_dir = Path(cache_dir or WIN_PROB)
    corpus = Path(corpus or CORPUS)
    ref = bpc.refresh_open_season(cache_dir, corpus, season, force=force)
    say(f"mgmt nightly: corpus {ref['status']}: {ref['why']}")
    out = {"season": season, "corpus": ref}
    if ref["status"] in ("no_cache", "no_frozen_corpus"):
        out.update(status="skipped",
                   why=f"{ref['why']}; the committed management artifacts stand")
        return out
    built_at = manifest_built_at(corpus)
    stale = stale_artifacts(built_at, data_dir)
    if ref["status"] != "rebuilt" and not stale and not force:
        lead = ("win-probability corpus unchanged" if ref["status"] == "unchanged"
                else f"play corpus not rebuilt ({ref['status']})")
        out.update(status="skipped",
                   why=f"{lead} since the build of {built_at}: {ref['why']}")
        return out
    detail = (downstream or rebuild_downstream)(season, say)
    why = (ref["why"] if ref["status"] == "rebuilt"
           else f"corpus unchanged but {', '.join(stale)} named another build")
    out.update(status="rebuilt", why=why, built_at=built_at, **(detail or {}))
    return out


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--force", action="store_true",
                    help="rebuild the open season and the chain even when unchanged")
    a = ap.parse_args(argv)
    res = run(season=a.season, force=a.force)
    print(json.dumps({k: v for k, v in res.items() if k != "corpus"}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
