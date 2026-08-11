# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for tools/backfill_vintages.py, the git reconstruction of the betting
validation clock.

WHAT THESE PROTECT, in the order the damage would be worst:

  1. THE CUTOFF IS THE COMMIT DATE. A backfilled vintage is honest only because
     a blob committed at time T cannot contain information created after T. Take
     the cutoff from the blob's own `as_of` instead and that guarantee is gone,
     because `as_of` describes the data a board was built from and a rebuild can
     stamp it with anything. A record that claims to know less than it does is a
     record that prices games whose results it already saw.

     THIS PROPERTY IS PINNED END TO END, against a real git repository built in
     a temp directory with pinned author and committer dates. It has to be:
     until 2026-08-09 this file never called `commit_history`, `extract`, `git`,
     `run` or `main`, so rewriting `commit_history` to key on the blob `as_of`
     left all 16 tests green and the property the list calls number 1 was not
     tested at all. `test_the_whole_tool_keys_on_the_commit_date_end_to_end` is
     the one that fails under that rewrite.

  2. SEASONS DO NOT POOL. Strictly-before is necessary and not sufficient. A
     2026-10-01 vintage is strictly before every 2027 game, so without a season
     fence the first backfill run after an offseason silently prices April 2027
     on the last week of 2026. That is not leakage, so no leakage arm can catch
     it; it is the pooling docs/diamond-betting.md caveat 1 forbids.

  3. FIRST WRITE WINS, ACROSS CLOCKS. A live nightly record is better evidence
     for its own date than a git blob is. The backfill must skip it and say so,
     never force it, and must not then claim the archive holds the git blob set
     for that date - the live 2026-08-05 record holds 2026-08-04 boards while
     git's 2026-08-05 blob set is newer than that.

  4. A BACKFILLED RECORD SAYS SO, FOREVER, AND AN ABSENT BLOCK IS UNKNOWN. The
     pre-registered leakage check grades the backfilled arm against the live
     arm. That check is unaskable if the two are indistinguishable on disk,
     blended into one count, or if an unlabelled record is filed into the live
     arm by default.

  5. A MISSING REQUIRED BOARD IS A NAMED SKIP. `reduce_current` returns None
     without all three team leaderboards; the plan has to refuse the date with a
     reason rather than write a half vintage or raise.

The plan layer is PURE (history in, rows out) so most of this needs no git
checkout, no network and no real archive. The end-to-end tests are the
exception and they build their own repository.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import leaderboard_vintages as lv

_SPEC = importlib.util.spec_from_file_location(
    "backfill_vintages", Path(__file__).parent / "tools" / "backfill_vintages.py")
bv = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bv)

ORGS = ("NYM", "PHI", "ATL", "WSN")


# ===========================================================================
# fixtures
# ===========================================================================
def _board_blobs(*, offense: float, as_of: str, season: str = "2026") -> dict[str, dict]:
    """The three boards in the real shape, as objects. `as_of` is the field the
    cutoff must NOT be taken from."""
    return {
        "hitter_leaderboards.json": {
            "season": season, "as_of": as_of,
            "teams": [{"team": o, "offense_plus": offense - 2 * i}
                      for i, o in enumerate(ORGS)],
            "hitters": [],
        },
        "starter_leaderboards.json": {
            "season": season, "as_of": as_of,
            "teams": [{"team": o, "rotation_plus": 104 - 3 * i, "starter_ip": 560.0}
                      for i, o in enumerate(ORGS)],
            "starters": [{"mlbam": 101 + i, "team": o, "sem_plus": 110 - 5 * i,
                          "ip_per_gs": 5.5, "role": "SP"} for i, o in enumerate(ORGS)],
        },
        "bullpen_leaderboards.json": {
            "season": season, "as_of": as_of,
            "teams": [{"team": o, "bullpen_plus": 101 - 2 * i, "relief_ip": 380.0}
                      for i, o in enumerate(ORGS)],
            "relievers": [{"mlbam": 201 + i, "team": o, "rem_plus": 103 - 4 * i}
                          for i, o in enumerate(ORGS)],
        },
    }


def _write_fake_leaderboards(data_dir: Path, *, offense: float, as_of: str,
                             season: str = "2026") -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    for name, blob in _board_blobs(offense=offense, as_of=as_of, season=season).items():
        (data_dir / name).write_text(json.dumps(blob), encoding="utf-8")


@pytest.fixture()
def store(tmp_path):
    d = tmp_path / "leaderboard_vintages"
    d.mkdir()
    lv.reset_cache()
    yield d
    lv.reset_cache()


def _hist(rows: dict[str, list[tuple[str, str]]]) -> dict:
    """A history map in the shape resolve_plan wants: newest first, every
    source present (an absent one is spelled as an empty list)."""
    return {name: list(reversed(sorted(rows.get(name, [])))) for name in bv.SOURCES}


def _backfill_provenance(date: str, sha: str = "a" * 40) -> dict:
    return bv.provenance_for({
        "date": date,
        "feature_cutoff": date,
        "commits": {n: sha for n in bv.SOURCES},
        "commit_dates": {n: date for n in bv.SOURCES},
    })


def _covered(*dates: str) -> dict[str, str]:
    """The common case for `resolve_plan`: the archive holds each of these
    dates and its features are exactly that day's boards, which is what this
    tool's own writes produce."""
    return {d: d for d in dates}


# ---------------------------------------------------------------------------
# a real git repository, in a temp directory
# ---------------------------------------------------------------------------
def _git(args: list[str], cwd: Path, env: dict | None = None) -> str:
    e = dict(os.environ)
    e.update(env or {})
    # HOME/config are left alone but identity and signing are forced per
    # invocation, so a developer box with commit.gpgsign on cannot hang here.
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=e)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout


def _build_repo(root: Path, commits: list[dict]) -> Path:
    """A repository with prospect-tracker/data/ and one commit per entry.

    Each entry is {ad, cd, offense, as_of, season, msg}. `ad` and `cd` are
    pinned separately so the max(author, committer) rule is exercised by real
    git metadata rather than by calling `cutoff_date` on two strings."""
    root.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q", "-b", "main"], root)
    dd = root / "prospect-tracker" / "data"
    dd.mkdir(parents=True, exist_ok=True)
    for c in commits:
        blobs = _board_blobs(offense=c["offense"], as_of=c["as_of"],
                             season=c.get("season", "2026"))
        for name, blob in blobs.items():
            (dd / name).write_text(json.dumps(blob), encoding="utf-8")
        _git(["add", "-A"], root)
        _git(["-c", "user.name=t", "-c", "user.email=t@example.invalid",
              "-c", "commit.gpgsign=false", "commit", "-q", "-m", c["msg"]], root,
             {"GIT_AUTHOR_DATE": f"{c['ad']} 12:00:00 +0000",
              "GIT_COMMITTER_DATE": f"{c['cd']} 12:00:00 +0000"})
    return root


# The three-commit tree every end-to-end test runs against. Every `as_of` is
# BEHIND its commit date, and the third commit's author and committer dates
# differ, so a tool that read `as_of` or that took the author date alone lands
# on a different set of candidate dates.
_E2E_COMMITS = [
    dict(ad="2026-07-05", cd="2026-07-05", offense=110.0, as_of="2026-06-01", msg="c1"),
    dict(ad="2026-07-09", cd="2026-07-09", offense=120.0, as_of="2026-06-01", msg="c2"),
    dict(ad="2026-07-11", cd="2026-07-20", offense=130.0, as_of="2026-07-11", msg="c3"),
]
_E2E_CUTOFFS = ["2026-07-05", "2026-07-09", "2026-07-20"]


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    r = _build_repo(tmp_path / "repo", _E2E_COMMITS)
    monkeypatch.setattr(bv, "REPO", r)
    return r


# ===========================================================================
# 1. THE CUTOFF IS THE COMMIT DATE, NOT THE BLOB'S as_of
# ===========================================================================
def test_cutoff_is_the_later_of_author_and_committer_date():
    """A rebase moves the committer date and keeps the author date; `git commit
    --date` does the reverse. The later of the two is the first moment this tree
    can prove the blob existed, and proving a LATER existence is the safe
    direction."""
    assert bv.cutoff_date("2026-07-01", "2026-08-04") == "2026-08-04"
    assert bv.cutoff_date("2026-08-04", "2026-07-01") == "2026-08-04"
    assert bv.cutoff_date("2026-08-04", "2026-08-04") == "2026-08-04"


def test_commit_history_reads_the_commit_date_and_not_the_blob(repo):
    """The first real-git test. `commit_history` must report the three commit
    cutoffs, not the two distinct `as_of` values (2026-06-01, 2026-07-11) the
    blobs carry, and the third row must be 2026-07-20 (the committer date) and
    not 2026-07-11 (the author date)."""
    rows = bv.commit_history("hitter_leaderboards.json")
    assert [d for d, _ in rows] == list(reversed(_E2E_CUTOFFS))     # newest first
    assert len({sha for _, sha in rows}) == 3
    assert "2026-06-01" not in {d for d, _ in rows}


def test_the_whole_tool_keys_on_the_commit_date_end_to_end(repo, store):
    """THE load-bearing test in this file, and the one the old suite did not
    have. It drives `commit_history` -> `resolve_plan` -> `extract` ->
    `snapshot` against a real repository and asserts on what lands on disk.

    Every blob here is stamped BEHIND its commit (`as_of` 2026-06-01 on the
    first two, 2026-07-11 on the third). A tool that keyed on `as_of` would
    produce candidate dates 2026-06-01 and 2026-07-11, would collapse the first
    two commits into one, and would write records whose covers_through is a
    month early - which is the direction that prices games whose results the
    features already contain."""
    res = bv.run(write=True, vintage_dir=store)

    assert [r["date"] for r in res["plan"]] == _E2E_CUTOFFS
    assert [r["date"] for r in res["plan"] if r["write"]] == _E2E_CUTOFFS
    assert res["n_written"] == 3
    assert sorted(lv.vintage_dates(vintage_dir=store)) == _E2E_CUTOFFS

    lv.reset_cache()
    for d in _E2E_CUTOFFS:
        rec = lv.load_vintage(d, vintage_dir=store)
        assert rec["covers_through"] == d, f"{d} took its cutoff from the blob"
        assert rec["vintage_date"] == d
        assert rec["provenance"]["source"] == lv.PROVENANCE_BACKFILL
        assert rec["provenance"]["cutoff_basis"] == "git commit date"

    # And the extraction really moved distinct content, not the same blob three
    # times: offense_plus is 110 / 120 / 130 across the three commits.
    offenses = [lv.load_vintage(d, vintage_dir=store)["teams"]["NYM"][0]
                for d in _E2E_CUTOFFS]
    assert offenses == [110.0, 120.0, 130.0]

    # The 2026-07-20 record is the amended one: its features are the 2026-07-11
    # author-dated blob and its stamp is the committer date, nine days later.
    late = lv.load_vintage("2026-07-20", vintage_dir=store)
    assert late["sources"]["hitter_leaderboards.json"]["as_of"] == "2026-07-11"
    assert late["provenance"]["feature_cutoff"] == "2026-07-20"


def test_extract_writes_the_blob_at_that_sha_and_nothing_newer(repo, tmp_path):
    """`extract` is the only thing standing between the plan and the working
    tree. Point it at the first commit and it must produce the 110 board, not
    the 130 one that is checked out."""
    hist = {n: bv.commit_history(n) for n in bv.SOURCES}
    plan = bv.resolve_plan(hist)
    first = [r for r in plan if r["date"] == "2026-07-05"][0]
    dest = tmp_path / "extracted"
    names = bv.extract(first["commits"], dest)
    assert set(names) == set(bv.REQUIRED)                # no fa_meta in this repo
    blob = json.loads((dest / "hitter_leaderboards.json").read_text(encoding="utf-8"))
    assert blob["teams"][0]["offense_plus"] == 110.0
    assert blob["as_of"] == "2026-06-01"


def test_a_backfilled_record_is_stamped_with_the_commit_date_not_the_blob_as_of(store, tmp_path):
    """The store-level half of property 1: given a commit date as `on_date`,
    `reduce_current` must take covers_through = max(as_of, on_date) and land on
    the commit date. This one passes `on_date` by hand and therefore does NOT
    exercise the tool; the end-to-end test above is what pins that."""
    data = tmp_path / "data"
    _write_fake_leaderboards(data, offense=110.0, as_of="2026-07-01")
    r = lv.snapshot(on_date="2026-08-04", data_dir=data, vintage_dir=store,
                    provenance=_backfill_provenance("2026-08-04"))
    rec = r["record"]
    assert rec["covers_through"] == "2026-08-04"
    # The lag is still RECORDED, because it is the honest measure of how old the
    # features are behind the stamp. It is just not the cutoff.
    assert rec["stale_sources"]["hitter_leaderboards.json"] == "2026-07-01"
    # And a game on the commit date itself is still refused: strictly before.
    lv.reset_cache()
    assert lv.as_of("2026-08-04", vintage_dir=store) is None
    assert lv.as_of("2026-08-05", vintage_dir=store)["vintage_date"] == "2026-08-04"


def test_a_blob_as_of_past_its_commit_date_still_raises_the_cutoff(store, tmp_path):
    """The max in `reduce_current` runs in both directions. A board stamped
    ahead of its commit is the one case where `as_of` may lift the cutoff, and
    it must, or the record would price a game the board might already contain.

    Measured 2026-08-09 over all 55 board commits in the 2026 history, this
    case does not occur: 0 blobs carry an as_of past their own commit. The
    branch is kept because the cutoff rule must not DEPEND on that measurement."""
    data = tmp_path / "data"
    _write_fake_leaderboards(data, offense=110.0, as_of="2026-08-09")
    rec = lv.snapshot(on_date="2026-08-04", data_dir=data, vintage_dir=store,
                      provenance=_backfill_provenance("2026-08-04"))["record"]
    assert rec["covers_through"] == "2026-08-09"


# ===========================================================================
# 2. main() NEVER WRITES WITHOUT --write
# ===========================================================================
def test_main_with_neither_flag_writes_nothing(repo, store, monkeypatch, capsys):
    """A tool that writes the archive when it is run with no arguments is a tool
    that gets run with no arguments. The archive is evidence that cannot be
    regenerated, so the bare invocation has to be inert."""
    monkeypatch.setattr(sys, "argv",
                        ["backfill_vintages.py", "--vintage-dir", str(store)])
    assert bv.main() == 0
    assert list(store.glob("*.json")) == []
    assert "nothing was written" in capsys.readouterr().out

    # --write --dry-run together resolve to the harmless one, in that order.
    monkeypatch.setattr(sys, "argv", ["backfill_vintages.py", "--write", "--dry-run",
                                      "--vintage-dir", str(store)])
    assert bv.main() == 0
    assert list(store.glob("*.json")) == []

    # And the negative is meaningful: the same call WITH --write does write.
    monkeypatch.setattr(sys, "argv", ["backfill_vintages.py", "--write",
                                      "--vintage-dir", str(store)])
    assert bv.main() == 0
    assert sorted(p.stem for p in store.glob("*.json")) == _E2E_CUTOFFS


# ===========================================================================
# 3. SEASONS DO NOT POOL
# ===========================================================================
def test_as_of_refuses_a_vintage_from_a_different_season(store, tmp_path):
    """The offseason hazard, which no leakage arm can catch because there is no
    leak. The 2026-09-30 vintage is strictly before every 2027 date; it is still
    the wrong quantity, because offense_plus is a within-season aggregate."""
    data = tmp_path / "data"
    _write_fake_leaderboards(data, offense=110.0, as_of="2026-09-30", season="2026")
    lv.snapshot(on_date="2026-09-30", data_dir=data, vintage_dir=store,
                provenance=_backfill_provenance("2026-09-30"))
    _write_fake_leaderboards(data, offense=95.0, as_of="2027-04-02", season="2027")
    lv.snapshot(on_date="2027-04-02", data_dir=data, vintage_dir=store,
                provenance=_backfill_provenance("2027-04-02"))
    lv.reset_cache()

    # Same season, strictly before: served.
    assert lv.as_of("2026-10-01", vintage_dir=store)["vintage_date"] == "2026-09-30"
    assert lv.as_of("2027-04-03", vintage_dir=store)["vintage_date"] == "2027-04-02"
    # The sharp one. 2026-09-30 is the only record strictly before 2027-04-01,
    # and it must NOT be returned.
    assert lv.as_of("2027-04-01", vintage_dir=store) is None
    # A 2025 game reaches forward to nothing, which was already true, and a
    # 2028 game must not reach back across two boundaries either.
    assert lv.as_of("2025-09-01", vintage_dir=store) is None
    assert lv.as_of("2028-04-01", vintage_dir=store) is None


def test_record_season_falls_back_to_the_stamp_year_and_never_crosses(store, tmp_path):
    """A board that omitted `season` was still written inside the season it was
    aggregating, so the year of `vintage_date` is the honest fallback. It can
    never place a record in a season its stamp is not in."""
    assert lv.record_season({"season": "2027", "vintage_date": "2027-04-02"}) == "2027"
    assert lv.record_season({"vintage_date": "2027-04-02"}) == "2027"
    assert lv.record_season({"season": "", "vintage_date": "2026-08-05"}) == "2026"
    assert lv.record_season({"season": None, "vintage_date": None}) is None
    assert lv.game_season("2027-04-05") == "2027"
    assert lv.game_season("not a date") is None


def test_the_plan_refuses_a_candidate_whose_boards_are_from_last_season():
    """A January commit that only moved fa_meta resolves the boards back to the
    previous October. Writing it would stamp a 2027 cutoff over 2026 boards, and
    `as_of` would then be the only thing between that record and an April game.
    The tool refuses it outright so the record never exists."""
    plan = bv.resolve_plan(_hist({
        "hitter_leaderboards.json": [("2026-09-30", "h1")],
        "starter_leaderboards.json": [("2026-09-30", "s1")],
        "bullpen_leaderboards.json": [("2026-09-30", "p1")],
        "fa_meta.json": [("2027-01-15", "f1")],
    }))
    rows = {r["date"]: r for r in plan}
    assert rows["2026-09-30"]["write"] is True
    assert rows["2027-01-15"]["write"] is False
    assert "season boundary" in rows["2027-01-15"]["reason"]
    assert "2026" in rows["2027-01-15"]["reason"]


def test_blob_season_is_the_write_time_half_of_the_fence(tmp_path):
    """The pure fence compares calendar years of commit dates and cannot see a
    board REBUILT in January still aggregating last season. Only the blob's own
    `season` field can."""
    data = tmp_path / "data"
    _write_fake_leaderboards(data, offense=110.0, as_of="2027-01-15", season="2026")
    assert bv.blob_season(data) == "2026"
    _write_fake_leaderboards(data, offense=110.0, as_of="2027-04-02", season="2027")
    assert bv.blob_season(data) == "2027"
    assert bv.blob_season(tmp_path / "nothing-here") is None


def test_run_refuses_at_write_when_the_blob_season_disagrees_with_the_stamp(tmp_path,
                                                                           store,
                                                                           monkeypatch):
    """End to end. The 2027-01-20 commit is a real rebuild in a new calendar
    year that still carries season 2026, so the pure year fence passes and only
    the blob's own field catches it. Nothing may reach disk for that date."""
    r = _build_repo(tmp_path / "repo2", [
        dict(ad="2026-09-30", cd="2026-09-30", offense=110.0,
             as_of="2026-09-30", season="2026", msg="end of season"),
        dict(ad="2027-01-20", cd="2027-01-20", offense=112.0,
             as_of="2027-01-20", season="2026", msg="offseason rebuild of last year"),
    ])
    monkeypatch.setattr(bv, "REPO", r)
    res = bv.run(write=True, vintage_dir=store)

    assert [row["date"] for row in res["plan"] if row["write"]] == ["2026-09-30",
                                                                   "2027-01-20"]
    assert [x["date"] for x in res["refused_at_write"]] == ["2027-01-20"]
    assert "season boundary" in res["refused_at_write"][0]["reason"]
    assert res["n_written"] == 1
    assert sorted(p.stem for p in store.glob("*.json")) == ["2026-09-30"]


# ===========================================================================
# 4. THE PLAN
# ===========================================================================
def test_a_date_missing_a_required_leaderboard_is_skipped_with_a_named_reason():
    """2026-06-30 in the real tree: the bullpen board is committed, the other
    two are not. `reduce_current` would return None; the plan refuses first and
    names which source is missing."""
    plan = bv.resolve_plan(_hist({
        "bullpen_leaderboards.json": [("2026-06-30", "b" * 40)],
        "fa_meta.json": [("2026-06-29", "f" * 40)],
    }))
    rows = {r["date"]: r for r in plan}
    assert rows["2026-06-30"]["write"] is False
    assert "hitter_leaderboards.json" in rows["2026-06-30"]["reason"]
    assert "starter_leaderboards.json" in rows["2026-06-30"]["reason"]
    assert "bullpen_leaderboards.json" not in rows["2026-06-30"]["reason"]
    assert not any(r["write"] for r in plan)


def test_fa_meta_is_optional_because_its_absence_is_already_a_supported_state():
    """The three team boards are irreplaceable; the park column is not. A record
    without parks prices its games on a neutral park and says so, which is the
    conservative direction, so a missing fa_meta must not cost a whole vintage."""
    plan = bv.resolve_plan(_hist({
        "hitter_leaderboards.json": [("2026-07-05", "h" * 40)],
        "starter_leaderboards.json": [("2026-07-05", "s" * 40)],
        "bullpen_leaderboards.json": [("2026-07-05", "p" * 40)],
    }))
    row = [r for r in plan if r["date"] == "2026-07-05"][0]
    assert row["write"] is True
    assert row["commits"]["fa_meta.json"] is None


def test_the_plan_takes_the_newest_blob_at_or_before_each_date():
    plan = bv.resolve_plan(_hist({
        "hitter_leaderboards.json": [("2026-07-05", "h1"), ("2026-07-14", "h2")],
        "starter_leaderboards.json": [("2026-07-05", "s1"), ("2026-07-14", "s2")],
        "bullpen_leaderboards.json": [("2026-07-05", "p1"), ("2026-07-14", "p2")],
        "fa_meta.json": [("2026-07-09", "f1")],
    }))
    rows = {r["date"]: r for r in plan}
    # 2026-07-09 only moved fa_meta, so the boards resolve back to the 07-05 set.
    assert rows["2026-07-09"]["commits"]["hitter_leaderboards.json"] == "h1"
    assert rows["2026-07-14"]["commits"]["hitter_leaderboards.json"] == "h2"
    assert rows["2026-07-05"]["feature_cutoff"] == "2026-07-05"
    assert rows["2026-07-09"]["feature_cutoff"] == "2026-07-05"


def test_a_date_with_no_new_board_is_not_written_as_a_fresher_stamp():
    """2026-08-03 in the real tree resolves to the 2026-08-01 boards plus a new
    fa_meta. Writing it would add no feature information and would pull the
    published vintage-age distribution down, making the archive look fresher
    than it is."""
    plan = bv.resolve_plan(_hist({
        "hitter_leaderboards.json": [("2026-08-01", "h1")],
        "starter_leaderboards.json": [("2026-08-01", "s1")],
        "bullpen_leaderboards.json": [("2026-08-01", "p1")],
        "fa_meta.json": [("2026-08-01", "f1"), ("2026-08-03", "f2")],
    }))
    rows = {r["date"]: r for r in plan}
    assert rows["2026-08-01"]["write"] is True
    assert rows["2026-08-03"]["write"] is False
    assert "no new leaderboard blob since 2026-08-01" in rows["2026-08-03"]["reason"]


def test_the_plan_is_stable_across_a_re_run():
    """A second run must plan nothing. The trap: if the duplicate check reset
    itself on an already-captured date, run two would find 08-01 captured, lose
    its comparison, and write the 08-03 duplicate run one had refused."""
    hist = _hist({
        "hitter_leaderboards.json": [("2026-08-01", "h1")],
        "starter_leaderboards.json": [("2026-08-01", "s1")],
        "bullpen_leaderboards.json": [("2026-08-01", "p1")],
        "fa_meta.json": [("2026-08-01", "f1"), ("2026-08-03", "f2")],
    })
    first = {r["date"] for r in bv.resolve_plan(hist) if r["write"]}
    assert first == {"2026-08-01"}
    second = [r for r in bv.resolve_plan(hist, _covered(*first)) if r["write"]]
    assert second == []


# ===========================================================================
# 5. FIRST WRITE WINS ACROSS THE TWO CLOCKS
# ===========================================================================
def test_the_plan_skips_a_date_the_live_store_already_holds():
    plan = bv.resolve_plan(_hist({
        "hitter_leaderboards.json": [("2026-08-05", "h1")],
        "starter_leaderboards.json": [("2026-08-05", "s1")],
        "bullpen_leaderboards.json": [("2026-08-05", "p1")],
    }), _covered("2026-08-05"))
    row = plan[0]
    assert row["write"] is False
    assert "already captured" in row["reason"] and "never forces" in row["reason"]


def test_the_marker_on_a_captured_date_is_what_the_archive_holds_not_what_git_holds():
    """THE 2026-08-05 CASE, exactly as it stands on this tree. The live record
    was reduced from boards stamped 2026-08-04; git's 2026-08-05 blob set has a
    fresh hitter board (939a076c). Advancing the marker with git's answer claims
    the archive holds a board it does not, and the next candidate resolving to
    that same set gets skipped as a duplicate of features nobody stored."""
    hist = _hist({
        "hitter_leaderboards.json": [("2026-08-04", "h1"), ("2026-08-05", "h2")],
        "starter_leaderboards.json": [("2026-08-04", "s1")],
        "bullpen_leaderboards.json": [("2026-08-04", "p1")],
        "fa_meta.json": [("2026-08-06", "f1")],
    })
    # The archive holds 08-04 and 08-05; the 08-05 record's own features are the
    # 08-04 boards, which is what `archive_feature_date` reports for it.
    plan = bv.resolve_plan(hist, {"2026-08-04": "2026-08-04",
                                  "2026-08-05": "2026-08-04"})
    rows = {r["date"]: r for r in plan}
    assert rows["2026-08-05"]["archive_feature_date"] == "2026-08-04"
    # 2026-08-06 resolves to the same three blobs as 2026-08-05 (h2, s1, p1).
    assert rows["2026-08-06"]["commits"]["hitter_leaderboards.json"] == "h2"
    assert rows["2026-08-06"]["feature_cutoff"] == "2026-08-05"
    assert rows["2026-08-06"]["write"] is True, (
        "the h2 board was never stored, so 08-06 is not a duplicate")


def test_an_archive_record_that_cannot_say_what_it_holds_never_fires_the_duplicate_rule():
    """None means unknown, and unknown must keep evidence rather than discard
    it: the marker does not advance and the next candidate is written."""
    hist = _hist({
        "hitter_leaderboards.json": [("2026-08-05", "h1")],
        "starter_leaderboards.json": [("2026-08-05", "s1")],
        "bullpen_leaderboards.json": [("2026-08-05", "p1")],
        "fa_meta.json": [("2026-08-06", "f1")],
    })
    rows = {r["date"]: r for r in bv.resolve_plan(hist, {"2026-08-05": None})}
    assert rows["2026-08-05"]["write"] is False
    assert rows["2026-08-06"]["write"] is True


def test_archive_feature_date_reads_a_backfill_exactly_and_a_live_record_by_as_of():
    """The two units that meet in the marker. A backfilled record answers with
    the git commit date it was built from; a live record has no commit and
    answers with the newest source `as_of`, which can only understate."""
    assert lv.archive_feature_date({
        "provenance": {"source": lv.PROVENANCE_BACKFILL,
                       "feature_cutoff": "2026-08-04"},
        "sources": {"hitter_leaderboards.json": {"as_of": "2026-07-28"}},
    }) == "2026-08-04"
    assert lv.archive_feature_date({
        "sources": {"hitter_leaderboards.json": {"as_of": "2026-08-04"},
                    "starter_leaderboards.json": {"as_of": "2026-08-04"},
                    "bullpen_leaderboards.json": {"as_of": "2026-07-28"}},
    }) == "2026-08-04"
    assert lv.archive_feature_date({"schema": 2}) is None
    assert lv.archive_feature_date(None) is None


def test_a_backfill_cannot_clobber_a_live_vintage(store, tmp_path):
    """Byte level. The live record is evidence of what a working tree said on
    its own night; a blob is a weaker claim about the same date."""
    data = tmp_path / "data"
    _write_fake_leaderboards(data, offense=110.0, as_of="2026-08-05")
    lv.snapshot(on_date="2026-08-05", data_dir=data, vintage_dir=store)
    before = (store / "2026-08-05.json").read_text(encoding="utf-8")

    _write_fake_leaderboards(data, offense=999.0, as_of="2026-08-05")
    r = lv.snapshot(on_date="2026-08-05", data_dir=data, vintage_dir=store,
                    provenance=_backfill_provenance("2026-08-05"))
    assert r["written"] is False and r["reason"] == "already captured"
    assert (store / "2026-08-05.json").read_text(encoding="utf-8") == before
    assert lv.provenance_source(json.loads(before)) == lv.PROVENANCE_LIVE


# ===========================================================================
# 6. A BACKFILLED RECORD IS DISTINGUISHABLE FROM A LIVE ONE
# ===========================================================================
def test_a_backfilled_record_carries_its_provenance(store, tmp_path):
    data = tmp_path / "data"
    _write_fake_leaderboards(data, offense=110.0, as_of="2026-07-05")
    rec = lv.snapshot(on_date="2026-07-05", data_dir=data, vintage_dir=store,
                      provenance=_backfill_provenance("2026-07-05", sha="c" * 40))["record"]
    p = rec["provenance"]
    assert p["source"] == lv.PROVENANCE_BACKFILL
    assert p["cutoff_basis"] == "git commit date"
    assert p["commit"] == "c" * 40
    assert p["commits"]["hitter_leaderboards.json"] == "c" * 40
    assert lv.provenance_source(rec) == lv.PROVENANCE_BACKFILL


def test_an_absent_provenance_block_is_unknown_and_not_live(store, tmp_path):
    """The unsafe default, corrected 2026-08-09. Directing an absent block into
    the live arm hides a backfill inside the one arm the leakage check compares
    against. The five real pre-provenance records are named by date, which is
    evidence about those five files; nothing else gets the benefit."""
    data = tmp_path / "data"
    _write_fake_leaderboards(data, offense=110.0, as_of="2026-08-06")
    rec = lv.snapshot(on_date="2026-08-06", data_dir=data, vintage_dir=store)["record"]
    assert rec["provenance"]["source"] == lv.PROVENANCE_LIVE
    assert lv.provenance_source(rec) == lv.PROVENANCE_LIVE

    # Grandfathered by date, not by the absence of a block.
    assert lv.provenance_source({"schema": 2, "vintage_date": "2026-08-05"}) == \
        lv.PROVENANCE_LIVE
    assert "2026-08-09" in lv.PROVENANCE_GRANDFATHERED_LIVE
    # Everything else with no block is UNKNOWN.
    assert lv.provenance_source({"schema": 2, "vintage_date": "2026-08-10"}) == \
        lv.PROVENANCE_UNKNOWN
    assert lv.provenance_source({"schema": 2, "teams": {}}) == lv.PROVENANCE_UNKNOWN
    assert lv.provenance_source(None) == lv.PROVENANCE_UNKNOWN
    assert lv.PROVENANCE_UNKNOWN not in (lv.PROVENANCE_LIVE, lv.PROVENANCE_BACKFILL)


def test_coverage_names_the_unknown_arm_instead_of_folding_it_into_live(store, tmp_path):
    """`n_vintages_live` used to be len(dates) - n_backfilled, which is the
    unsafe default written as arithmetic. An unlabelled record has to land in
    its own count or the arm split is grading a mixture."""
    data = tmp_path / "data"
    _write_fake_leaderboards(data, offense=110.0, as_of="2026-08-11")
    lv.snapshot(on_date="2026-08-11", data_dir=data, vintage_dir=store,
                provenance=_backfill_provenance("2026-08-11"))
    lv.snapshot(on_date="2026-08-12", data_dir=data, vintage_dir=store)
    # A record with no provenance block, dated after the grandfathered five.
    rec = json.loads((store / "2026-08-12.json").read_text(encoding="utf-8"))
    rec.pop("provenance")
    rec["vintage_date"] = "2026-08-13"
    (store / "2026-08-13.json").write_text(json.dumps(rec), encoding="utf-8")
    lv.reset_cache()

    cov = lv.coverage(vintage_dir=store)
    assert cov["n_vintages"] == 3
    assert cov["n_vintages_backfilled"] == 1
    assert cov["n_vintages_live"] == 1
    assert cov["n_vintages_unknown_provenance"] == 1
    assert "1 UNKNOWN provenance" in cov["note"]


def test_provenance_names_the_commit_that_set_the_cutoff():
    """The three boards are not always committed together: 2026-08-05 has a
    fresh hitter board over an 08-04 starter and bullpen. `commit` must be the
    newest REQUIRED blob, which is the one the cutoff rests on, and fa_meta must
    never be it (it carries no game feature)."""
    p = bv.provenance_for({
        "date": "2026-08-05", "feature_cutoff": "2026-08-05",
        "commits": {"hitter_leaderboards.json": "new", "starter_leaderboards.json": "old",
                    "bullpen_leaderboards.json": "old", "fa_meta.json": "park"},
        "commit_dates": {"hitter_leaderboards.json": "2026-08-05",
                         "starter_leaderboards.json": "2026-08-04",
                         "bullpen_leaderboards.json": "2026-08-04",
                         "fa_meta.json": "2026-08-09"},
    })
    assert p["commit"] == "new"
    assert p["feature_cutoff"] == "2026-08-05"


# ===========================================================================
# 7. COVERAGE REPORTS THE ARMS SEPARATELY AND MEASURES STALENESS HONESTLY
# ===========================================================================
def test_coverage_counts_backfilled_and_live_separately(store, tmp_path):
    """One blended number would hide a nightly outage behind a healthy looking
    archive, and would make the leakage arm split unaskable."""
    data = tmp_path / "data"
    _write_fake_leaderboards(data, offense=110.0, as_of="2026-07-05")
    for d in ("2026-07-05", "2026-07-07", "2026-07-14"):
        lv.snapshot(on_date=d, data_dir=data, vintage_dir=store,
                    provenance=_backfill_provenance(d))
    for d in ("2026-08-05", "2026-08-06"):
        lv.snapshot(on_date=d, data_dir=data, vintage_dir=store)
    lv.reset_cache()

    cov = lv.coverage(vintage_dir=store)
    assert cov["n_vintages"] == 5
    assert cov["n_vintages_backfilled"] == 3
    assert cov["n_vintages_live"] == 2
    assert cov["n_vintages_unknown_provenance"] == 0
    assert (cov["n_vintages_backfilled"] + cov["n_vintages_live"]
            + cov["n_vintages_unknown_provenance"]) == cov["n_vintages"]
    assert "3 backfilled" in cov["note"] and "2 live" in cov["note"]
    assert "UNKNOWN" not in cov["note"]


def test_p90_is_an_interpolated_percentile_and_not_the_maximum():
    """The small-n bug, fixed 2026-08-09. `vals[int(n * 0.9)]` at n = 10 lands
    on index 9, the MAXIMUM, so a p90 of a nine-ones-and-a-thirteen sample read
    13. The interpolated value is 2.2. At n = 414 the shortcut was the 90.1th
    percentile and read 11 against a true 10.7, which is why this hid."""
    flat_then_spike = [1] * 9 + [13]
    assert lv._percentile(flat_then_spike, 0.9) == 2.2
    assert flat_then_spike[int(len(flat_then_spike) * 0.9)] == 13      # the old answer
    assert lv._percentile(flat_then_spike, 0.5) == 1
    # An exactly representable position stays exact, and an integral result
    # stays an int so a flat distribution still reads "3 days".
    assert lv._percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], 0.9) == 10
    assert lv._percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.5) == 5.5
    assert lv._percentile([7], 0.9) == 7
    assert lv._percentile([1, 2], 0.0) == 1 and lv._percentile([1, 2], 1.0) == 2


def test_coverage_publishes_how_stale_the_pricing_vintage_is(store, tmp_path):
    """A graded count alone hides a fortnight-old feature set. The 07-16 to
    07-29 gap in the real archive is 13 days wide and a reader is entitled to
    see it."""
    data = tmp_path / "data"
    _write_fake_leaderboards(data, offense=110.0, as_of="2026-07-05")
    for d in ("2026-07-14", "2026-07-16", "2026-07-29"):
        lv.snapshot(on_date=d, data_dir=data, vintage_dir=store,
                    provenance=_backfill_provenance(d))
    lv.reset_cache()

    age = lv.coverage(vintage_dir=store)["vintage_age_days"]
    assert age["basis"] == "calendar days inside the archive"
    assert age["max_days"] == 13            # 2026-07-29 priced off the 07-16 vintage
    assert age["median_days"] >= 1

    # Game weighted is a different question and gets a different answer: three
    # games on one day count three times, an off day counts zero.
    game_age = lv.coverage(vintage_dir=store,
                           game_dates=["2026-07-17"] * 9 + ["2026-07-29"])["vintage_age_days"]
    assert game_age["basis"] == "graded game dates"
    assert game_age["n"] == 10
    assert game_age["median_days"] == 1
    assert game_age["max_days"] == 13
    # nine 1s and one 13. The p90 of that is 2.2, not the 13 the nearest-rank
    # shortcut reported.
    assert game_age["p90_days"] == 2.2


def test_the_age_distribution_does_not_reach_across_a_season(store, tmp_path):
    """It has to report exactly what `as_of` would serve. A 2027 date whose only
    earlier cutoff is 2026 has NO usable vintage, not a 190-day-old one, and
    counting it as stale would put a number on a record the reader can never
    use."""
    data = tmp_path / "data"
    _write_fake_leaderboards(data, offense=110.0, as_of="2026-09-30", season="2026")
    lv.snapshot(on_date="2026-09-30", data_dir=data, vintage_dir=store,
                provenance=_backfill_provenance("2026-09-30"))
    _write_fake_leaderboards(data, offense=95.0, as_of="2027-04-02", season="2027")
    lv.snapshot(on_date="2027-04-02", data_dir=data, vintage_dir=store,
                provenance=_backfill_provenance("2027-04-02"))
    lv.reset_cache()

    age = lv.coverage(vintage_dir=store,
                      game_dates=["2026-10-01", "2027-04-01", "2027-04-05"]
                      )["vintage_age_days"]
    # 2026-10-01 is 1 day past the 2026 cutoff; 2027-04-05 is 3 past the 2027
    # one; 2027-04-01 has no same-season vintage at all and is dropped.
    assert age["n"] == 2
    assert age["max_days"] == 3


def test_coverage_on_an_empty_store_reports_all_counts_as_zero(store):
    cov = lv.coverage(vintage_dir=store)
    assert cov["n_vintages_backfilled"] == 0 and cov["n_vintages_live"] == 0
    assert cov["n_vintages_unknown_provenance"] == 0
    assert cov["vintage_age_days"] is None
