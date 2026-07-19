# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Regression guards for a batch of verified bug fixes:

  [6]  tools/build_star_odds_artifacts.py - write star_label_view.json BEFORE
       build_calibration_eval() reads it (read-before-write reorder).
  [24] tools/build_leaderboard_gamelogs.py - a zero-player pull must keep the
       prior good slice instead of blanking the served leaderboard.
  [19] storage._file_equals_bytes - streamed compare-before-write is byte-exact.
  [21] storage._checkpoint_and_maybe_vacuum / finish_run - end-of-run WAL
       truncate (always) + opt-in VACUUM (env PROSPECTS_DB_VACUUM=1).

The test functions take no pytest fixtures, so they are discoverable by pytest
AND runnable directly (`python test_verified_bugfixes.py`).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --------------------------------------------------------------------------- #
# [6] star-odds artifact ordering
# --------------------------------------------------------------------------- #
def test_star_odds_main_writes_label_view_before_eval():
    """build_calibration_eval() -> _realized_calibration() reads
    data/star_label_view.json, so main() must WRITE the label view before it
    builds the eval. Previously the eval ran first and always read the PREVIOUS
    run's labels (or {} on a fresh/cleared run)."""
    import tools.build_star_odds_artifacts as bso

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        seen = {}

        def fake_label():
            return {"counts": {"n_players": 0, "n_star_window": 0,
                               "n_star_career": 0}, "players": []}

        def fake_eval():
            # At eval-build time THIS run's label view must already be on disk,
            # else _realized_calibration reads stale/empty labels.
            seen["label_on_disk"] = (tmp / "star_label_view.json").exists()
            return {"gate": {"max_abs_dev": None, "pass": False}}

        saved = (bso._DATA, bso.build_label_view, bso.build_calibration_eval)
        try:
            bso._DATA = tmp
            bso.build_label_view = fake_label
            bso.build_calibration_eval = fake_eval
            bso.main()
        finally:
            bso._DATA, bso.build_label_view, bso.build_calibration_eval = saved

        assert seen.get("label_on_disk") is True, (
            "build_calibration_eval ran before star_label_view.json was written "
            "- read-before-write regression (finding [6])")
        assert (tmp / "star_label_view.json").exists()
        assert (tmp / "star_odds_eval.json").exists()


# --------------------------------------------------------------------------- #
# [24] leaderboard gamelogs: keep prior good slice on an empty pull
# --------------------------------------------------------------------------- #
def _blg_setup(tmp: Path, prior: dict | None):
    import tools.build_leaderboard_gamelogs as blg
    boot_path = tmp / "timeseries.json"
    out_path = tmp / "leaderboard_gamelogs.json"
    boot_path.write_text(json.dumps({"players": [
        {"player_key": "p1", "mlbam_id": 111, "overall_rank": 1},
        {"player_key": "p2", "mlbam_id": 222, "overall_rank": 2},
    ]}), encoding="utf-8")
    if prior is not None:
        out_path.write_text(json.dumps(prior), encoding="utf-8")
    return blg, boot_path, out_path


def test_leaderboard_gamelogs_keeps_prior_slice_on_empty_pull():
    """A zero-player pull (StatsAPI outage / deadline overrun) must NOT
    overwrite the served slice with {} - keep the prior good one (finding
    [24])."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        prior = {"generated_at": "2026-07-18T00:00:00Z", "season": 2026,
                 "as_of": "2026-07-18",
                 "players": {"p1": {"is_pitcher": False,
                                    "games": [{"d": "2026-07-18"}]}}}
        blg, boot_path, out_path = _blg_setup(tmp, prior)
        saved = (blg.BOOT, blg.OUT, blg._pull_one)
        try:
            blg.BOOT, blg.OUT = boot_path, out_path
            blg._pull_one = lambda *a, **k: None   # every player yields nothing
            summary = blg.build(season=2026, limit=0, workers=2)
        finally:
            blg.BOOT, blg.OUT, blg._pull_one = saved

        assert json.loads(out_path.read_text(encoding="utf-8")) == prior, (
            "empty pull overwrote the prior good slice (finding [24])")
        assert summary.get("kept_prior") is True
        assert summary.get("prior_players") == 1


def test_leaderboard_gamelogs_writes_when_pull_nonempty():
    """The normal path still writes the fresh slice when players are pulled."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        prior = {"season": 2026, "players": {"old": {"is_pitcher": False,
                                                     "games": []}}}
        blg, boot_path, out_path = _blg_setup(tmp, prior)
        saved = (blg.BOOT, blg.OUT, blg._pull_one)
        try:
            blg.BOOT, blg.OUT = boot_path, out_path
            blg._pull_one = lambda p, *a, **k: (
                (p["player_key"], {"is_pitcher": False,
                                   "games": [{"d": "2026-07-19"}]})
                if p.get("player_key") == "p1" else None)
            summary = blg.build(season=2026, limit=0, workers=2)
        finally:
            blg.BOOT, blg.OUT, blg._pull_one = saved

        written = json.loads(out_path.read_text(encoding="utf-8"))
        assert "p1" in written["players"] and "old" not in written["players"]
        assert summary.get("players") == 1
        assert not summary.get("kept_prior")


def test_leaderboard_gamelogs_empty_pull_no_prior_writes_empty():
    """Cold start (no prior slice on disk): an empty pull writes an empty slice
    - there is nothing good to preserve, so behaviour is unchanged."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        blg, boot_path, out_path = _blg_setup(tmp, prior=None)
        saved = (blg.BOOT, blg.OUT, blg._pull_one)
        try:
            blg.BOOT, blg.OUT = boot_path, out_path
            blg._pull_one = lambda *a, **k: None
            blg.build(season=2026, limit=0, workers=2)
        finally:
            blg.BOOT, blg.OUT, blg._pull_one = saved
        assert out_path.exists()
        assert json.loads(out_path.read_text(encoding="utf-8"))["players"] == {}


def test_leaderboard_gamelogs_empty_pull_stale_season_not_preserved():
    """An empty pull for a NEW season must not preserve last season's slice
    (that would surface stale cross-season games), so it falls through to the
    empty write."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        prior = {"season": 2025, "as_of": "2025-09-01",
                 "players": {"p1": {"is_pitcher": False,
                                    "games": [{"d": "2025-09-01"}]}}}
        blg, boot_path, out_path = _blg_setup(tmp, prior)
        saved = (blg.BOOT, blg.OUT, blg._pull_one)
        try:
            blg.BOOT, blg.OUT = boot_path, out_path
            blg._pull_one = lambda *a, **k: None
            summary = blg.build(season=2026, limit=0, workers=2)
        finally:
            blg.BOOT, blg.OUT, blg._pull_one = saved
        written = json.loads(out_path.read_text(encoding="utf-8"))
        assert written["season"] == 2026 and written["players"] == {}
        assert not summary.get("kept_prior")


# --------------------------------------------------------------------------- #
# [19] streamed compare-before-write
# --------------------------------------------------------------------------- #
def test_file_equals_bytes_streaming_compare():
    """_file_equals_bytes must be byte-exact across chunk boundaries and length
    mismatches, matching the semantics of `path.read_bytes() == data` while
    never holding a second full copy (finding [19])."""
    import storage

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "f.bin"
        data = b"abcdefghij" * 1000   # 10,000 bytes
        p.write_bytes(data)

        # Identical - True, even with a tiny chunk forcing many reads that
        # straddle content boundaries.
        assert storage._file_equals_bytes(p, data, chunk=7) is True
        assert storage._file_equals_bytes(p, data, chunk=1 << 20) is True

        # Same length, one flipped byte in the middle - False.
        diff = bytearray(data)
        diff[5000] ^= 0xFF
        assert storage._file_equals_bytes(p, bytes(diff), chunk=7) is False

        # On-disk file LONGER than `data` (trailing bytes) - False.
        assert storage._file_equals_bytes(p, data[:-1], chunk=7) is False
        # On-disk file SHORTER than `data` - False.
        assert storage._file_equals_bytes(p, data + b"x", chunk=7) is False

        # Empty file / empty data edge cases.
        pe = Path(td) / "empty.bin"
        pe.write_bytes(b"")
        assert storage._file_equals_bytes(pe, b"") is True
        assert storage._file_equals_bytes(pe, b"x") is False


# --------------------------------------------------------------------------- #
# [21] end-of-run WAL truncate + opt-in VACUUM
# --------------------------------------------------------------------------- #
def test_checkpoint_and_optin_vacuum_are_best_effort():
    """finish_run() truncates the WAL, and VACUUM runs only when opted in via
    PROSPECTS_DB_VACUUM=1. Both are best-effort and must never fail a run
    (finding [21])."""
    import storage

    with tempfile.TemporaryDirectory() as td:
        dbp = Path(td) / "t.db"
        saved_db = storage.DB_PATH
        saved_env = os.environ.get("PROSPECTS_DB_VACUUM")
        try:
            storage.DB_PATH = dbp
            storage.init_db()
            rid = storage.start_run()

            # Default (no env): checkpoint only, no VACUUM, must not raise.
            os.environ.pop("PROSPECTS_DB_VACUUM", None)
            storage.finish_run(rid, 0, 0, notes="test")
            with storage.connect() as con:
                assert con.execute(
                    "SELECT COUNT(*) FROM runs").fetchone()[0] >= 1

            # WAL truncated/absent after the checkpoint(TRUNCATE).
            wal = Path(str(dbp) + "-wal")
            assert (not wal.exists()) or wal.stat().st_size == 0

            # Opt-in VACUUM path runs cleanly and leaves the DB queryable.
            os.environ["PROSPECTS_DB_VACUUM"] = "1"
            storage._checkpoint_and_maybe_vacuum()
            with storage.connect() as con:
                assert con.execute(
                    "SELECT COUNT(*) FROM runs").fetchone()[0] >= 1
        finally:
            storage.DB_PATH = saved_db
            if saved_env is None:
                os.environ.pop("PROSPECTS_DB_VACUUM", None)
            else:
                os.environ["PROSPECTS_DB_VACUUM"] = saved_env


def _main() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:   # noqa: BLE001 - standalone runner surfaces all
            failed += 1
            import traceback
            print(f"FAIL {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
