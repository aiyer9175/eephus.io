# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the eFV side and role calibration lab (docs/efv-v2/EFV_SIDE_ROLE_CALIBRATION.md):
the isotonic fit, the grade map, the dark switch, the anchor-gate source scan and a synthetic
planted recovery. No development label is read here."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import numpy as np

import efv_side_role_calibration as SRC

ROOT = Path(__file__).resolve().parent


def _rows(n_per=120, *, pit_mult=1.0, relief_mult=1.0, seed=7):
    """Synthetic rows: two frames, three folds each, both sides; label = anchor(g) x mult +
    noise, so a side or role effect of known size is planted."""
    rng = np.random.default_rng(seed)
    rows = []
    pid = 0
    for fid in ("lv_dev", "vm_dev"):
        for year in (2017, 2018, 2019):
            for side in ("hit", "pit"):
                g = rng.uniform(35.0, 62.0, n_per)
                for j in range(n_per):
                    role = None
                    m = 1.0
                    if side == "pit":
                        role = ("STARTER", "RELIEF", "SHORT-START")[j % 3]
                        m = pit_mult * (relief_mult if role == "RELIEF" else 1.0)
                    mu = float(SRC.anchor_value([g[j]])[0]) * m
                    y = max(0.0, mu + rng.normal(0.0, 0.5 + 0.2 * mu))
                    rows.append({"key": f"p{pid}", "side": side, "fid": fid, "year": year,
                                 "kg": f"{fid}|{year}", "g": float(g[j]), "o": float(g[j]),
                                 "role": role, "y": y})
                    pid += 1
    return rows


class TestPava(unittest.TestCase):
    def test_increasing_and_strict(self):
        x = np.array([1, 2, 2, 3, 4, 5, 6], dtype=float)
        y = np.array([3, 1, 2, 2, 5, 4, 6], dtype=float)
        xs, ys = SRC.pava(x, y)
        self.assertTrue(np.all(np.diff(ys) > 0))
        self.assertTrue(np.all(np.diff(xs) > 0))

    def test_monotone_input_untouched(self):
        x = np.arange(10.0)
        xs, ys = SRC.pava(x, x * 2)
        np.testing.assert_allclose(ys, x * 2)


class TestGradeMap(unittest.TestCase):
    def test_identity_when_curves_match(self):
        cur = SRC.pava(np.arange(30.0, 70.0), np.linspace(0.0, 10.0, 40))
        g = np.array([35.0, 45.5, 61.2])
        got = SRC.inverse_project(cur, SRC.f_eval(cur, g), g)
        np.testing.assert_allclose(got, g, atol=1e-9)

    def test_lower_side_curve_maps_lower_and_stays_monotone(self):
        pool = SRC.pava(np.arange(30.0, 70.0), np.linspace(0.0, 10.0, 40))
        side = (pool[0], pool[1] * 0.7)
        g = np.linspace(30.0, 69.0, 200)
        gp = SRC.inverse_project(pool, SRC.f_eval(side, g), g)
        self.assertTrue(np.all(np.diff(gp) >= -1e-12))
        self.assertTrue(np.all(gp <= g + 1e-9))
        self.assertLess(float(gp[-50]), float(g[-50]))

    def test_flat_ends_keep_the_grade(self):
        pool = SRC.pava(np.array([40.0, 50.0, 60.0]), np.array([0.0, 1.0, 2.0]))
        got = SRC.inverse_project(pool, np.array([-5.0, 99.0]), np.array([30.0, 75.0]))
        np.testing.assert_allclose(got, [30.0, 75.0])


class TestSwitchAndScan(unittest.TestCase):
    def test_dark_switch_default_off(self):
        self.assertIs(SRC.SIDE_ROLE_CALIBRATION_ON, False)

    def test_no_fv_cell_group_in_source(self):
        """PROSPECT_ANCHOR_GATE: nothing is grouped at a consensus-FV cell edge and no group is
        named after an FV cell (registration section 0, points 2 and 3)."""
        src = (ROOT / "efv_side_role_calibration.py").read_text(encoding="utf-8")
        code = "\n".join(line.split("#", 1)[0] for line in src.splitlines())
        self.assertIsNone(re.search(r"(>=|<=|==|<|>)\s*(45|50|55|60|65)(\.0)?\b", code))
        self.assertNotIn("consensus_fv", code)
        self.assertIsNone(re.search(r"fv_?cell|FV_CELL", code))

    def test_reserved_years_absent(self):
        rows = _rows(n_per=10)
        self.assertFalse({r["year"] for r in rows} & {2020, 2021})


class TestPlantedRecovery(unittest.TestCase):
    def test_side_effect_moves_pitchers_down(self):
        rows = _rows(pit_mult=0.6)
        A = SRC.Arrays(rows)
        gp = SRC.cross_fit(A, "b")
        top = A.g > np.quantile(A.g, 0.8)
        pit, hit = A.side == "pit", A.side == "hit"
        self.assertLess(float((gp - A.g)[pit & top].mean()), 0.0)
        self.assertGreater(float((gp - A.g)[hit & top].mean()), 0.0)
        var = SRC.frame_var(A)
        self.assertGreater(float((SRC.sq_err(A, A.g, var) - SRC.sq_err(A, gp, var)).mean()), 0.0)

    def test_side_map_never_reorders_a_side(self):
        rows = _rows(pit_mult=0.7)
        A = SRC.Arrays(rows)
        gp = SRC.cross_fit(A, "b")
        for k, ix in A.group_ix.items():
            for s in SRC.SIDES:
                sub = ix[A.side[ix] == s]
                order = sub[np.argsort(A.g[sub])]
                self.assertTrue(np.all(np.diff(gp[order]) >= -1e-9), k)

    def test_role_map_moves_relievers(self):
        rows = _rows(relief_mult=0.5)
        A = SRC.Arrays(rows)
        gb = SRC.cross_fit(A, "b")
        gc = SRC.cross_fit(A, "c")
        rel = (A.side == "pit") & (A.role == "RELIEF")
        self.assertLess(float((gc - gb)[rel].mean()), 0.0)

    def test_incumbent_is_identity(self):
        A = SRC.Arrays(_rows(n_per=20))
        np.testing.assert_array_equal(SRC.cross_fit(A, "a"), A.g)

    def test_production_maps_monotone(self):
        A = SRC.Arrays(_rows(pit_mult=0.7, relief_mult=0.6))
        maps = SRC.production_maps(A)
        for cand in ("b", "c"):
            for tab in maps[cand].values():
                self.assertTrue(np.all(np.diff(np.asarray(tab)) >= -1e-9))
        self.assertEqual(len(maps["grid"]), len(maps["b"]["hit"]))


if __name__ == "__main__":
    unittest.main()
