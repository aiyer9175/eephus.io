# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The trade board joins the projection artifacts on the HUMAN, not the slug.

A player_key is a slug and 200 slugs name more than one human
(identity_collisions.json). Until 2026-09-24 apply_platform_surplus re-pointed
a board record at mlb_projections by player_key, so where the slug belonged to
a different human there, one human's dollars landed on the other's row:

  max_muncy on the board was the ATH infielder (mlbam 691777, 24.1) and in
  projections the LAD veteran (571970, 36). The board quoted the 24-year-old
  at the veteran's $54.3M, and the seeder, which also tested the slug, never
  gave the veteran a row of his own.

These cases run apply_platform_surplus against a temp data directory, so they
pin the join itself rather than whatever the served artifact happens to hold.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import bayes_trade_value as btv

HORIZON = 5


def _vet(key, mlbam, age, team, sur_total=None, war=1.0):
    row = {"key": key, "mlbam": mlbam, "name": key.split("__")[0].replace("_", " ").title(),
           "age": age, "src": "vet", "pos": "H", "team": team,
           "war": [war] * HORIZON, "warP10": [war - 1.0] * HORIZON,
           "warP90": [war + 1.0] * HORIZON, "warTotal": war * HORIZON}
    if sur_total is not None:
        row["surTotal"] = sur_total
        row["thru"] = 2028
        row["aav"] = 10_000_000
    return row


def _record(key, mlbam, age, org, status="debuted"):
    return {"player_key": key, "mlbam_id": mlbam, "player_name": key.title(),
            "status": status, "age": age, "org": org, "position": "SS",
            "trade_value_mm": 9.0, "posterior_surplus_mm": 9.0, "contract": {}}


class _Dir:
    def __init__(self, vets):
        self.dir = Path(tempfile.mkdtemp(prefix="tb_identity_"))
        (self.dir / "mlb_projections.json").write_text(json.dumps({
            "first_season": 2027, "horizon": HORIZON, "dpw_usd": 15_000_000.0,
            "ros_fraction": 0.3, "vets": vets, "prospects": []}), encoding="utf-8")
        (self.dir / "mlb_player_detail.json").write_text(
            json.dumps({"players": {}}), encoding="utf-8")
        (self.dir / "debuts.json").write_text(json.dumps({"players": []}), encoding="utf-8")
        (self.dir / "xfv.json").write_text(json.dumps({"by_player": {}}), encoding="utf-8")

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class ASlugHeldByTwoHumans(unittest.TestCase):
    """The max_muncy shape: the board's record and the projections row under the
    same slug are different mlbam ids."""

    def setUp(self):
        self.fx = _Dir([
            _vet("max_muncy", 571970, 36, "LAD", sur_total=54_312_088),
            _vet("max_muncy__691777", 691777, 24, "ATH"),
        ])
        self.records = [_record("max_muncy", 691777, 24.1, "ATH")]
        btv.apply_platform_surplus(self.records, self.fx.dir)

    def tearDown(self):
        self.fx.close()

    def _by_id(self, mlbam):
        rows = [r for r in self.records if r.get("mlbam_id") == mlbam]
        self.assertEqual(len(rows), 1, (mlbam, rows))
        return rows[0]

    def test_the_prospect_does_not_wear_the_veterans_price(self):
        row = self._by_id(691777)
        self.assertNotEqual(row.get("surplus_source"), "projection")
        self.assertNotEqual(row.get("trade_value_mm"), 54.3)
        # Its own projections row, named so a click lands on the right page.
        self.assertEqual(row.get("proj_key"), "max_muncy__691777")

    def test_the_veteran_gets_a_row_of_his_own(self):
        row = self._by_id(571970)
        self.assertEqual(row["surplus_source"], "projection")
        self.assertEqual(row["trade_value_mm"], 54.3)
        self.assertEqual(row["org"], "LAD")
        self.assertEqual(row["age"], 36)
        self.assertEqual(row["player_key"], "max_muncy__571970")
        self.assertEqual(row["proj_key"], "max_muncy")

    def test_board_keys_stay_unique(self):
        keys = [r["player_key"] for r in self.records]
        self.assertEqual(len(keys), len(set(keys)))

    def test_swapping_the_ids_moves_the_price_with_the_human(self):
        """The mutation the old slug join could not see: give the board record
        the veteran's id and the veteran's price follows the id, not the slug."""
        fx = _Dir([_vet("max_muncy", 571970, 36, "LAD", sur_total=54_312_088),
                   _vet("max_muncy__691777", 691777, 24, "ATH")])
        try:
            recs = [_record("max_muncy", 571970, 36.0, "LAD")]
            btv.apply_platform_surplus(recs, fx.dir)
            row = next(r for r in recs if r["player_key"] == "max_muncy")
            self.assertEqual(row["surplus_source"], "projection")
            self.assertEqual(row["trade_value_mm"], 54.3)
            self.assertNotIn("proj_key", row)
            self.assertFalse(any(r.get("mlbam_id") == 571970 and r is not row for r in recs))
        finally:
            fx.close()


class OneHumanUnderTwoSlugs(unittest.TestCase):
    """The rafael_flores shape: the board spells him rafael_flores_jr and
    projections rafael_flores. One human, one row, priced on projections."""

    def setUp(self):
        self.fx = _Dir([_vet("rafael_flores", 804668, 26, "PIT", sur_total=66_908_729)])
        self.records = [_record("rafael_flores_jr", 804668, 25.9, "PIT")]
        btv.apply_platform_surplus(self.records, self.fx.dir)

    def tearDown(self):
        self.fx.close()

    def test_priced_once_on_the_projection_basis(self):
        self.assertEqual(len(self.records), 1, self.records)
        row = self.records[0]
        self.assertEqual(row["player_key"], "rafael_flores_jr")
        self.assertEqual(row["surplus_source"], "projection")
        self.assertEqual(row["trade_value_mm"], 66.9)
        self.assertEqual(row["proj_key"], "rafael_flores")


class ARecordWithoutAnIdKeepsTheSlugJoin(unittest.TestCase):
    """No id is no evidence of a second human, so the join is what it always was."""

    def test_slug_join_is_unchanged(self):
        fx = _Dir([_vet("judge", 592450, 34, "NYY", sur_total=24_600_000)])
        try:
            recs = [_record("judge", None, 34.2, "NYY")]
            btv.apply_platform_surplus(recs, fx.dir)
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0]["surplus_source"], "projection")
            self.assertEqual(recs[0]["trade_value_mm"], 24.6)
            self.assertNotIn("proj_key", recs[0])
        finally:
            fx.close()


if __name__ == "__main__":
    unittest.main()
