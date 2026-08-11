# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Reconstruct leaderboard vintages from git history. Moves the betting
validation clock from 2027 to 2026-09-16.

THE ARGUMENT, WHICH IS THE WHOLE TOOL. `leaderboard_vintages` was written on
the premise that a past vintage cannot be recovered: the leaderboards are a full
recompute over the season to date and nothing keeps the intermediate states.
That is true of RECOMPUTING them and false of READING them. data/*_leaderboards
.json is a TRACKED artifact, so every rebuild since 2026-07-05 is sitting in git
history as a blob. A blob committed at time T provably cannot contain
information created after T. A vintage reduced from that blob and stamped with
the COMMIT DATE is therefore leak-free by exactly the same argument the nightly
clock runs on, and it is available today rather than in nine months.

THE CUTOFF IS THE COMMIT DATE, NEVER THE BLOB'S OWN `as_of`, AND THAT IS A RULE
OF CONSTRUCTION. The `as_of` field describes the data a board was built from and
a rebuild may stamp it with whatever it likes; the commit date describes when
the board provably existed in this tree and no rebuild can move it backwards.
The rule is therefore safe whether or not the two ever came apart here, which is
the whole reason to take it from the commit. MEASURED 2026-08-09 over all 55
board commits in the 2026 history: ZERO blobs carry an `as_of` past their own
commit date, and 2 sit one day behind it (f3b6338a, 017d3bc2), so the rule costs
at most one day of coverage on this tree. Leakage arm 3 pins the same property
empirically on what was written: 0 forward-dated violations over 10 records.

  (An earlier draft of this docstring cited d50c1afb, "Regen: one coherent
  vintage behind the identity repair", as a case where a regen stamped `as_of`
  away from the calendar. That is FALSE and was removed on 2026-08-09: the
  commit date and all three of its blob `as_of` values are 2026-08-04. There is
  no such divergence anywhere in this history. Do not reintroduce the claim.)

The commit date is max(author date, committer date), because a rebase or a
cherry-pick can move one and not the other and the later of the two is the first
moment the blob provably existed in this tree.

`reduce_current` then takes covers_through = max(the sources' as_of, on_date),
so passing the commit date as on_date can only ever make a vintage price FEWER
games than the truth, never more. The conservative direction is free here.

SEASONS DO NOT POOL, AND THIS TOOL IS THE THING THAT WOULD BREAK IT. The 2026
history starts 2026-06-09, so every candidate date and every blob is inside one
season and no fence fires today. The first run after an offseason is different:
git would offer September and October board commits, and a record written from
them is strictly before every 2027 game, so `leaderboard_vintages.as_of` would
hand April 2027 a September 2026 view of the league unless something says no.
Two fences, because they catch different halves of it:

  * `leaderboard_vintages.as_of` refuses a record whose season differs from the
    game's. That is the one that has to hold, because it also covers records
    this tool never wrote.
  * this tool refuses a candidate date whose CALENDAR YEAR is not the year of
    the blobs behind it (a January commit still carrying last year's boards),
    and refuses again at write time if the reduced record's own `season` field
    disagrees with the stamp year. Both are named skips, never silent.

WHAT IT REFUSES TO DO.

  * It never overwrites. First write wins is `snapshot()`'s own rule and this
    tool never passes force. A live nightly record is the better evidence for
    its date (it saw the working tree, not a commit), so an overlap resolves to
    the live one and the skip is counted and named.
  * It never writes a day whose required blobs are no newer than what the
    ARCHIVE already covers. That day carries no new leaderboard information; all
    it would add is a FRESHER STAMP over identical features, which makes the
    published vintage-age distribution flatter than the archive really is. The
    cost is a slightly newer fa_meta park index on such a day, and park factors
    are a multi-year regressed index that barely moves inside a season
    (leaderboard_vintages.PARK_SOURCE says so). One day is affected in the
    2026 tree, 2026-08-03.

    The comparison is against THE ARCHIVE, not against git, and the difference
    is not academic: the live 2026-08-05 record was reduced from boards whose
    as_of is 2026-08-04, while the git blob set for 2026-08-05 is 939a076c with
    as_of 2026-08-05. Advancing the marker with git's answer on an
    already-captured date claimed the archive held features it never held, and
    a later candidate resolving to that same set would have been skipped as a
    duplicate of a record that does not contain it.
  * It never touches data/. It extracts blobs into a temp directory and points
    `snapshot(data_dir=...)` at that.

MEASURED ON THE 2026 TREE (2026-08-09): 35 candidate dates, 13 reduce cleanly,
10 written (2026-07-05 through 2026-08-04), 22 skipped for a missing required
board, 2 as already captured live and 1 (2026-08-03) as adding no new board.
Gradable completed games went 41 -> 414, and the vintage backtest reached
`status: "graded"` for the first time at n = 221. Vintage age at grading, game
weighted over 414 dates: median 3 days, p90 10.7, max 13, the 07-16 to 07-29
gap being the worst stretch. (That p90 read 11 before 2026-08-09, on a
nearest-rank shortcut that took index int(0.9n); the interpolated value is
10.7. Calendar weighted, n = 36: median 2, p90 9.5, max 13.) Writing the
duplicate 08-03 day would have reported that median as 2 while adding no
leaderboard information at all, which is the whole reason the rule exists. The
three pre-registered leakage arms all cleared; they and the discard rule are in
docs/diamond-betting.md section 5a.

A re-run on 2026-08-09 after the six corrections below plans 0 writes and the
same 35 candidate rows, so no stored record changed.

    python tools/backfill_vintages.py --dry-run   # print the plan, write nothing
    python tools/backfill_vintages.py --write     # do it (idempotent, re-runnable)
    python tools/backfill_vintages.py --json      # the plan as an object
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger("backfill_vintages")

# The three team leaderboards are REQUIRED: `reduce_current` returns None
# without all three anyway, and a vintage missing one would price games on a
# broken prevention blend. fa_meta only supplies the park column, whose absence
# is already a supported state (the record stores parks null and the reader
# prices those games on a neutral park and counts them).
REQUIRED = ("hitter_leaderboards.json", "starter_leaderboards.json",
            "bullpen_leaderboards.json")
OPTIONAL = ("fa_meta.json",)
SOURCES = REQUIRED + OPTIONAL

# Path inside the repo, which is one level above the package this file lives in.
GIT_PREFIX = "prospect-tracker/data"


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------
def git(*args: str) -> str:
    p = subprocess.run(["git", *args], cwd=str(REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout


def cutoff_date(author_date: str, committer_date: str) -> str:
    """The date a blob provably existed, as YYYY-MM-DD.

    max(author, committer) and not either one alone. A rebase rewrites the
    committer date and keeps the author date; `git commit --date` does the
    reverse. The later of the two is the first moment this tree can prove the
    content existed, and proving a LATER existence is the safe direction: a
    vintage stamped late prices fewer games, a vintage stamped early prices
    games whose results it may already contain."""
    return max(author_date, committer_date)


def commit_history(rel_name: str) -> list[tuple[str, str]]:
    """[(cutoff_date, sha)] for one data file, NEWEST FIRST."""
    raw = git("log", "--format=%H|%ad|%cd", "--date=short",
              "--", f"{GIT_PREFIX}/{rel_name}")
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        sha, ad, cd = line.split("|")
        rows.append((cutoff_date(ad, cd), sha))
    return rows


def blob_at_or_before(history: list[tuple[str, str]], day: str) -> tuple[str, str] | None:
    """(sha, its cutoff date) for the newest commit of a file dated <= day."""
    for d, sha in history:                                   # newest first
        if d <= day:
            return sha, d
    return None


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------
def resolve_plan(history: dict[str, list[tuple[str, str]]],
                 covered: dict[str, str | None] | None = None) -> list[dict]:
    """One row per candidate date, in date order, each either writable or
    skipped with a named reason.

    PURE. `history` is {file name: [(cutoff_date, sha)] newest first}.

    `covered` is what the store ALREADY HOLDS: {captured date: the newest
    feature date that record demonstrably contains, or None when it cannot say}.
    It is not a set of dates, and the value is not optional decoration. The
    duplicate rule asks "does this candidate bring a board the archive does not
    already have", and on an already-captured date the answer has to come from
    the archive record, never from git. Those disagree on this tree: the live
    2026-08-05 record was built from boards stamped 2026-08-04 while git's
    2026-08-05 blob set (939a076c) carries 2026-08-05. Feeding git's answer back
    in would let a later candidate be skipped as a duplicate of features the
    archive never held. `leaderboard_vintages.archive_feature_date` computes the
    value and documents the one unit mismatch (a live record answers in `as_of`,
    which can only understate a commit date, so the error direction is "write a
    day that adds little", never "skip a day that adds a board").

    None as a value means the record cannot say what it holds. The marker then
    does not advance, and the duplicate rule simply cannot fire off that date,
    which is the direction that keeps evidence."""
    have = dict(covered or {})
    days = sorted({d for rows in history.values() for d, _ in rows})
    plan: list[dict] = []
    # The newest feature date the archive is known to COVER, which advances on a
    # write and on an already-captured date alike. Advancing it on both is what
    # makes a re-run reproduce the same plan: if it only advanced on writes, the
    # second run would find every earlier date already captured, reset its
    # comparison to nothing, and write the duplicate day the first run correctly
    # skipped. It is monotone: a live record whose sources lag must not roll the
    # marker backwards and reopen a day an earlier record already covers.
    last_covered_feature: str | None = None
    last_covered_date: str | None = None
    for day in days:
        picks = {name: blob_at_or_before(history.get(name) or [], day)
                 for name in SOURCES}
        row = {
            "date": day,
            "write": False,
            "reason": "",
            "commits": {n: (p[0] if p else None) for n, p in picks.items()},
            "commit_dates": {n: (p[1] if p else None) for n, p in picks.items()},
        }
        missing = [n for n in REQUIRED if not picks.get(n)]
        if missing:
            row["reason"] = ("no blob at or before this date for required source(s) "
                             + ", ".join(missing))
            plan.append(row)
            continue
        # The honest feature date: the newest REQUIRED blob behind this record.
        # It equals `date` on every row this tool writes, because a day that
        # adds no new required blob is skipped below, but it is stamped anyway
        # so an archive can be audited without re-running git.
        row["feature_cutoff"] = max(picks[n][1] for n in REQUIRED)
        if day in have:
            # First write wins, and a live record is the better evidence for its
            # own date: it read the working tree, which is a superset of what was
            # committed. Never force.
            held = have.get(day)
            row["archive_feature_date"] = held
            row["reason"] = "already captured; first write wins and this tool never forces"
            if held and (last_covered_feature is None or held > last_covered_feature):
                last_covered_feature, last_covered_date = held, day
            plan.append(row)
            continue
        # THE SEASON FENCE, pure half. A candidate whose calendar year is not the
        # year of the blobs behind it is an offseason or a new-year commit still
        # carrying last season's boards. Writing it would stamp a January cutoff
        # over a season that ended in October, and `as_of` would then be the only
        # thing standing between it and an April game. Refuse it here as well,
        # so the archive never contains the record at all.
        if row["feature_cutoff"][:4] != day[:4]:
            row["reason"] = (f"season boundary: a {day[:4]} stamp over "
                             f"{row['feature_cutoff'][:4]} boards would pool two seasons; "
                             "leaderboards are a within-season aggregate")
            plan.append(row)
            continue
        if last_covered_feature is not None and row["feature_cutoff"] <= last_covered_feature:
            row["reason"] = (f"no new leaderboard blob since {last_covered_date} "
                             f"(archive covers features through {last_covered_feature}); a "
                             "later stamp over identical features would only make the "
                             "archive look fresher than it is")
            plan.append(row)
            continue
        row["write"] = True
        last_covered_feature, last_covered_date = row["feature_cutoff"], day
        plan.append(row)
    return plan


def extract(picks: dict[str, str | None], dest: Path) -> list[str]:
    """`git show <sha>:<path>` every resolved blob into `dest`. Returns the
    names actually written, so a caller can see that fa_meta was absent."""
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for name, sha in picks.items():
        if not sha:
            continue
        (dest / name).write_text(git("show", f"{sha}:{GIT_PREFIX}/{name}"),
                                 encoding="utf-8")
        out.append(name)
    return out


def provenance_for(row: dict) -> dict:
    """The block that makes a backfilled record distinguishable forever.

    `commit` is the sha of the newest REQUIRED blob, which is the one that sets
    the cutoff. The per-source map is kept beside it because the three boards
    are not always committed together (2026-08-05 has a fresh hitter board over
    an 08-04 starter and bullpen), and an auditor re-running this tool needs to
    land on the same four blobs."""
    newest = max(REQUIRED, key=lambda n: (row["commit_dates"][n] or "", n))
    return {
        "source": "git-backfill",
        "cutoff_basis": "git commit date",
        "commit": row["commits"][newest],
        "commits": dict(row["commits"]),
        "commit_dates": dict(row["commit_dates"]),
        "feature_cutoff": row.get("feature_cutoff"),
        "tool": "tools/backfill_vintages.py",
        "note": ("reduced from blobs committed at or before this date; the cutoff is the "
                 "commit date (max of author and committer), never the blob's own as_of, "
                 "because as_of describes the data a board was built from and a rebuild "
                 "can stamp it with anything, while a commit date cannot move backwards"),
    }


def blob_season(data_dir: Path) -> str | None:
    """The season the extracted hitter board claims, as a 4-digit string.

    The write-time half of the season fence. The pure fence in `resolve_plan`
    compares calendar years of commit dates and cannot see a board that was
    REBUILT in January still aggregating last season; only the blob's own
    `season` field can. Read from the hitter board because that is the field
    `reduce_current` copies into the record. None on an unreadable or unlabelled
    blob: that is not a season disagreement, and `reduce_current` refuses a
    board it cannot parse on its own."""
    try:
        d = json.loads((Path(data_dir) / REQUIRED[0]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    s = str((d or {}).get("season") or "").strip()
    return s if len(s) == 4 and s.isdigit() else None


def run(*, write: bool, vintage_dir: Path | None = None, log_fn=None) -> dict:
    """Plan and, when `write`, execute. Returns the plan plus what happened."""
    import leaderboard_vintages as lv

    vdir = Path(vintage_dir) if vintage_dir else lv.VINTAGE_DIR
    history = {name: commit_history(name) for name in SOURCES}
    # What the ARCHIVE holds on each captured date, not merely that it holds
    # something. See resolve_plan: git's answer for an already-captured date is
    # not the archive's, and using it skips days whose features were never
    # stored.
    covered = {d: lv.archive_feature_date(lv.load_vintage(d, vintage_dir=vdir))
               for d in lv.vintage_dates(vintage_dir=vdir)}
    plan = resolve_plan(history, covered)

    out = {
        "mode": "write" if write else "dry-run",
        "vintage_dir": str(vdir),
        "existing_before": sorted(covered),
        "archive_feature_dates": dict(sorted(covered.items())),
        "n_candidate_dates": len(plan),
        "n_writable": sum(1 for r in plan if r["write"]),
        "written": [],
        "skipped": [{"date": r["date"], "reason": r["reason"]}
                    for r in plan if not r["write"]],
        # Kept apart from `skipped`, which is a property of the PLAN. A refusal
        # here happened after the blobs were read, so it is a different fact and
        # a reader must be able to tell "the plan never wanted this day" from
        # "the plan wanted it and the content vetoed it".
        "refused_at_write": [],
        "plan": plan,
    }
    if not write:
        return out

    for row in plan:
        if not row["write"]:
            continue
        with tempfile.TemporaryDirectory(prefix="vintage-backfill-") as td:
            dd = Path(td) / "data"
            names = extract(row["commits"], dd)
            # Second half of the season fence, and the last point before a file
            # exists. A blob whose own season disagrees with the stamp year is
            # refused rather than written and left for `as_of` to filter.
            season = blob_season(dd)
            if season and season != row["date"][:4]:
                reason = (f"season boundary: blobs say season {season}, the stamp would "
                          f"say {row['date'][:4]}; refusing rather than storing a record "
                          "two seasons wide")
                log.warning("backfill_vintages: %s %s", row["date"], reason)
                out["refused_at_write"].append({"date": row["date"], "reason": reason})
                continue
            res = lv.snapshot(on_date=row["date"], data_dir=dd, vintage_dir=vdir,
                              provenance=provenance_for(row), log_fn=log_fn)
        rec = res.get("record") or {}
        out["written"].append({
            "date": row["date"],
            "written": bool(res.get("written")),
            "reason": res.get("reason"),
            "covers_through": rec.get("covers_through"),
            "n_teams": rec.get("n_teams"),
            "n_pitchers": rec.get("n_pitchers"),
            "n_parks": rec.get("n_parks"),
            "sources_extracted": names,
        })
    out["n_written"] = sum(1 for r in out["written"] if r["written"])
    out["coverage"] = lv.coverage(vintage_dir=vdir)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconstruct leaderboard vintages from git.")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and write nothing (the default)")
    ap.add_argument("--write", action="store_true",
                    help="write the plan into the vintage store; never overwrites")
    ap.add_argument("--json", action="store_true", help="emit the plan as JSON")
    ap.add_argument("--vintage-dir", default=None,
                    help="write somewhere other than .cache/leaderboard_vintages")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")

    # The default is the harmless one. A tool that writes the archive when it is
    # run with no arguments is a tool that gets run with no arguments.
    do_write = bool(args.write) and not args.dry_run
    res = run(write=do_write, vintage_dir=Path(args.vintage_dir) if args.vintage_dir else None,
              log_fn=print if do_write else None)

    if args.json:
        print(json.dumps(res, indent=1))
        return 0

    print(f"{res['mode']}: {res['n_candidate_dates']} candidate dates, "
          f"{res['n_writable']} writable, {len(res['skipped'])} skipped")
    for row in res["plan"]:
        if row["write"]:
            print(f"  WRITE {row['date']}  features {row.get('feature_cutoff')}  "
                  f"{row['commits'][REQUIRED[0]][:8]}")
    for s in res["skipped"]:
        print(f"  skip  {s['date']}: {s['reason']}")
    for s in res.get("refused_at_write") or []:
        print(f"  REFUSED {s['date']}: {s['reason']}")
    if do_write:
        print(f"\nwrote {res.get('n_written')} vintages")
        cov = res["coverage"]
        print(f"store: {cov['n_vintages']} vintages "
              f"({cov['n_vintages_backfilled']} backfilled, {cov['n_vintages_live']} live), "
              f"{cov['first']} .. {cov['last']}, "
              f"earliest gradable game {cov['earliest_gradable_game_date']}")
        age = cov.get("vintage_age_days") or {}
        if age.get("n"):
            print(f"vintage age ({age['basis']}): median {age['median_days']}d, "
                  f"p90 {age['p90_days']}d, max {age['max_days']}d")
    else:
        print("\nnothing was written. Re-run with --write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
