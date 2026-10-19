# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the eFV hitter position calibration lab
(docs/efv-v2/EFV_HITTER_POSITION_CALIBRATION.md): the listing resolver, the partially pooled
offset, the re-allocation, the two-way bootstrap, the quasi-likelihood slope, the dark
switch, the anchor-gate source scan and synthetic planted recoveries. No development label
is read here."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import numpy as np

import efv_hitter_position_calibration as HPC

ROOT = Path(__file__).resolve().parent


def _rows(n_per=150, *, mult=None, seed=11, year0=2017):
    """Synthetic hitter rows: two frames, three folds each; label = anchor(g) x the group's
    multiplier + noise, so a group effect of known size is planted."""
    mult = mult or {}
    rng = np.random.default_rng(seed)
    rows = []
    pid = 0
    for fid in ("lv_dev", "vm_dev"):
        for year in (year0, year0 + 1, year0 + 2):
            g = rng.uniform(35.0, 62.0, n_per)
            for j in range(n_per):
                grp = HPC.GROUPS[j % len(HPC.GROUPS)]
                mu = float(HPC.SRC.anchor_value([g[j]])[0]) * mult.get(grp, 1.0)
                y = max(0.0, mu + rng.normal(0.0, 0.4 + 0.2 * mu))
                rows.append({"key": f"p{pid}", "fid": fid, "year": year, "kg": f"{fid}|{year}",
                             "g": float(g[j]), "o": float(g[j]), "y": y, "group": grp,
                             "club": f"c{pid % 30}", "token": None, "how": "listed", "mlbam": None,
                             "asof": None})
                pid += 1
    return rows


class TestListing(unittest.TestCase):
    def test_most_demanding_of_a_multi_listing(self):
        self.assertEqual(HPC.resolve_listing(["2B/SS"])["group"], "SS/CF")
        self.assertEqual(HPC.resolve_listing(["1B", "C"])["token"], "C")
        self.assertEqual(HPC.resolve_listing(["CF", "OF"])["group"], "SS/CF")
        self.assertEqual(HPC.resolve_listing(["1B/3B"])["group"], "2B/3B")
        self.assertEqual(HPC.resolve_listing(["DH"])["group"], "1B/DH")

    def test_multi_tokens_list_each_member(self):
        self.assertEqual(HPC.resolve_listing(["MIF"])["token"], "SS")
        self.assertEqual(HPC.resolve_listing(["CI"])["token"], "3B")

    def test_generic_resolved_by_history_then_default(self):
        got = HPC.resolve_listing(["OF"], ["RF", "CF"])
        self.assertEqual((got["token"], got["how"]), ("CF", "generic_by_history"))
        got = HPC.resolve_listing(["OF"], ["1B"])
        self.assertEqual((got["group"], got["how"]), ("LF/RF", "generic_default"))
        self.assertEqual(HPC.resolve_listing(["INF"])["group"], "2B/3B")

    def test_pitcher_tokens_and_empty(self):
        self.assertEqual(HPC.resolve_listing(["RHP"])["group"], HPC.UNLISTED)
        self.assertEqual(HPC.resolve_listing([None, ""])["group"], HPC.UNLISTED)


class TestGroupFit(unittest.TestCase):
    def test_equal_groups_shrink_to_no_adjustment(self):
        A = HPC.Arrays(_rows(seed=3))
        fit = HPC.group_fit(A.y, A.v_a, A.grp, A.key)
        f = np.exp(fit["theta_star"] - fit["theta_bar"])
        self.assertLess(float(np.max(np.abs(f - 1.0))), 0.08)

    def test_planted_group_recovered(self):
        A = HPC.Arrays(_rows(mult={"SS/CF": 1.5, "1B/DH": 0.7}, n_per=300))
        fit = HPC.group_fit(A.y, A.v_a, A.grp, A.key)
        r = HPC.recovered_ratio(fit, HPC.GROUPS.index("SS/CF"))
        self.assertGreater(r, 1.25)
        self.assertGreater(fit["tau2"], 0.0)
        v, _f = HPC.cross_fit_group(A)
        self.assertGreater(float((A.sq_err(A.v_a) - A.sq_err(v)).mean()), 0.0)

    def test_reallocation_keeps_each_group_sum(self):
        A = HPC.Arrays(_rows(mult={"C": 0.6}))
        v, _f = HPC.cross_fit_group(A)
        for ix in A.group_ix.values():
            self.assertAlmostEqual(float(v[ix].sum()), float(A.y[ix].sum()), places=6)
            self.assertAlmostEqual(float(A.v_a[ix].sum()), float(A.y[ix].sum()), places=6)

    def test_held_out_players_excluded(self):
        A = HPC.Arrays(_rows(n_per=20))
        for k, ix in A.group_ix.items():
            self.assertFalse(set(A.key[ix]) & set(A.key[A.train_ix[k]]))


class TestBootstrapAndSlope(unittest.TestCase):
    def test_twoway_weights_shape_and_mean(self):
        players = np.asarray([f"p{i // 2}" for i in range(200)], dtype=object)
        clubs = np.asarray([f"c{i % 30}" for i in range(200)], dtype=object)
        W = HPC.twoway_weights(players, clubs, B=400, seed=1)
        self.assertEqual(W.shape, (400, 200))
        self.assertAlmostEqual(float(W.mean()), 1.0, delta=0.08)
        # rows sharing both the player and the club always carry the same weight
        players[60] = players[0]
        W = HPC.twoway_weights(players, clubs, B=50, seed=2)
        self.assertTrue(bool(np.all(W[:, 0] == W[:, 60])))

    def test_qmle_recovers_a_slope(self):
        rng = np.random.default_rng(5)
        x = rng.normal(size=(4000, 1))
        off = np.log(rng.uniform(0.5, 3.0, 4000))
        y = rng.poisson(np.exp(off + 0.3 * x[:, 0])).astype(float)
        b = HPC.qmle(y, off, x)
        self.assertAlmostEqual(float(b[0]), 0.3, delta=0.05)

    def test_versatility_standardized_missing_at_mean(self):
        X = np.asarray([[1.0, 0.2], [3.0, np.nan], [np.nan, 0.6], [2.0, 0.4]])
        Z = HPC.standardize(X, np.arange(4), term="versatility")
        self.assertEqual(float(Z[2, 0]), 0.0)
        self.assertEqual(float(Z[1, 1]), 0.0)


class TestSwitchAndScan(unittest.TestCase):
    def test_dark_switch_default_off(self):
        self.assertIs(HPC.HITTER_POSITION_CALIBRATION_ON, False)

    def test_no_fv_cell_group_in_source(self):
        """PROSPECT_ANCHOR_GATE: nothing is grouped at a consensus-FV cell edge and no group
        is named after an FV cell."""
        src = (ROOT / "efv_hitter_position_calibration.py").read_text(encoding="utf-8")
        code = "\n".join(line.split("#", 1)[0] for line in src.splitlines())
        self.assertIsNone(re.search(r"(>=|<=|==|<|>)\s*(45|50|55|60|65)(\.0)?\b", code))
        self.assertNotIn("consensus_fv", code)
        self.assertIsNone(re.search(r"fv_?cell|FV_CELL", code))

    def test_career_census_never_read(self):
        src = (ROOT / "efv_hitter_position_calibration.py").read_text(encoding="utf-8")
        self.assertNotIn('"positions_played.json"', src)
        self.assertNotIn("load_observed_positions", src)

    def test_reserved_years_absent_and_term_frame_floor(self):
        rows = _rows(n_per=10)
        self.assertFalse({r["year"] for r in rows} & {2020, 2021})
        self.assertEqual(HPC.TERM_FIRST_YEAR, 2021)


if __name__ == "__main__":
    unittest.main()
