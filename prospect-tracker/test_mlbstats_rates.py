# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The pooled-rate recipe moved out of tools/mlbstats_window_lab.py into the
public mlbstats_rates.py (LT-02, docs/master-plan-2026-09-24-final-pass.md).

A REPRODUCTION PIN. Every expected value below was captured from the lab's own
_hitter_rates, _pitcher_rates and _pooled BEFORE the move (branch head
3d9426b3), on the fixture accumulators beside it, so the public functions must
return exactly what the lab returned. The lab must also import the public
functions back rather than keep a copy: one recipe, no second formula."""
from __future__ import annotations

import inspect
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

import mlbstats_rates as mr  # noqa: E402
from tools import mlbstats_window_lab as lab  # noqa: E402

HITTER_FIXTURES = {'empty': {},
                   'floats': {'2b': 97.0,
                              '3b': 11.0,
                              'ab': 1611.0,
                              'bb': 191.0,
                              'cs': 9.0,
                              'h': 452.0,
                              'hbp': 22.0,
                              'hr': 71.0,
                              'ibb': 14.0,
                              'pa': 1843.0,
                              'sb': 33.0,
                              'sf': 13.0,
                              'so': 401.0},
                   'missing': {'ab': 45, 'h': 12, 'pa': 50},
                   'small': {'2b': 2,
                             '3b': 0,
                             'ab': 33,
                             'bb': 3,
                             'cs': 0,
                             'h': 7,
                             'hbp': 1,
                             'hr': 1,
                             'ibb': 0,
                             'pa': 37,
                             'sb': 0,
                             'sf': 0,
                             'so': 12},
                   'typical': {'2b': 50,
                               '3b': 5,
                               'ab': 1000,
                               'bb': 90,
                               'cs': 3,
                               'h': 300,
                               'hbp': 10,
                               'hr': 40,
                               'ibb': 5,
                               'pa': 1100,
                               'sb': 10,
                               'sf': 8,
                               'so': 200},
                   'zero_ab': {'2b': 0,
                               '3b': 0,
                               'ab': 0,
                               'bb': 2,
                               'cs': 0,
                               'h': 0,
                               'hbp': 0,
                               'hr': 0,
                               'ibb': 0,
                               'pa': 2,
                               'sb': 0,
                               'sf': 0,
                               'so': 0}}

HITTER_EXPECTED = {'empty': {'_woba_den': 0.0,
                             'avg': None,
                             'babip': None,
                             'bb_pct': None,
                             'iso': None,
                             'k_pct': None,
                             'obp': None,
                             'ops': None,
                             'slg': None,
                             'woba_raw': None},
                   'floats': {'_woba_den': 1823.0,
                              'avg': 0.281,
                              'babip': 0.331,
                              'bb_pct': 0.1036,
                              'iso': 0.206,
                              'k_pct': 0.2176,
                              'obp': 0.362,
                              'ops': 0.849,
                              'slg': 0.487,
                              'woba_raw': 0.368},
                   'missing': {'_woba_den': 45.0,
                               'avg': 0.267,
                               'babip': 0.267,
                               'bb_pct': 0.0,
                               'iso': 0.0,
                               'k_pct': 0.0,
                               'obp': 0.267,
                               'ops': 0.533,
                               'slg': 0.267,
                               'woba_raw': 0.237},
                   'small': {'_woba_den': 37.0,
                             'avg': 0.212,
                             'babip': 0.3,
                             'bb_pct': 0.0811,
                             'iso': 0.152,
                             'k_pct': 0.3243,
                             'obp': 0.297,
                             'ops': 0.661,
                             'slg': 0.364,
                             'woba_raw': 0.297},
                   'typical': {'_woba_den': 1103.0,
                               'avg': 0.3,
                               'babip': 0.339,
                               'bb_pct': 0.0818,
                               'iso': 0.18,
                               'k_pct': 0.1818,
                               'obp': 0.361,
                               'ops': 0.841,
                               'slg': 0.48,
                               'woba_raw': 0.366},
                   'zero_ab': {'_woba_den': 2.0,
                               'avg': None,
                               'babip': None,
                               'bb_pct': 1.0,
                               'iso': None,
                               'k_pct': 0.0,
                               'obp': 1.0,
                               'ops': None,
                               'slg': None,
                               'woba_raw': 0.69}}

PITCHER_FIXTURES = {'empty': {},
                    'missing': {'g': 10, 'outs': 30, 'so': 9},
                    'odd_outs': {'ao': 4,
                                 'bb': 3,
                                 'cg': 0,
                                 'er': 4,
                                 'g': 3,
                                 'go': 6,
                                 'gs': 1,
                                 'hbp': 0,
                                 'hld': 0,
                                 'hr': 1,
                                 'outs': 13,
                                 'pit': 90,
                                 'r': 5,
                                 'so': 5,
                                 'strk': 55,
                                 'sv': 0,
                                 'tbf': 22},
                    'reliever': {'ao': 180,
                                 'bb': 70,
                                 'cg': 0,
                                 'er': 61,
                                 'g': 190,
                                 'go': 210,
                                 'gs': 0,
                                 'hbp': 9,
                                 'hld': 31,
                                 'hr': 17,
                                 'outs': 581,
                                 'pit': 3150,
                                 'r': 66,
                                 'so': 230,
                                 'strk': 2040,
                                 'sv': 44,
                                 'tbf': 790},
                    'starter': {'ao': 400,
                                'bb': 120,
                                'cg': 1,
                                'er': 140,
                                'g': 60,
                                'go': 500,
                                'gs': 60,
                                'hbp': 12,
                                'hld': 0,
                                'hr': 45,
                                'outs': 1080,
                                'pit': 6000,
                                'r': 150,
                                'so': 400,
                                'strk': 3900,
                                'sv': 0,
                                'tbf': 1500},
                    'zero_outs': {'ao': 0,
                                  'bb': 1,
                                  'cg': 0,
                                  'er': 2,
                                  'g': 1,
                                  'go': 1,
                                  'gs': 0,
                                  'hbp': 0,
                                  'hld': 0,
                                  'hr': 1,
                                  'outs': 0,
                                  'pit': 15,
                                  'r': 2,
                                  'so': 0,
                                  'strk': 7,
                                  'sv': 0,
                                  'tbf': 3}}

# (fixture, starter) -> the lab's output before the move.
PITCHER_EXPECTED = {('empty', False): {'bb_pct': None,
                                       'era': None,
                                       'hr9': None,
                                       'k_bb_pct': None,
                                       'k_pct': None},
                    ('empty', True): {'bb_pct': None,
                                      'era': None,
                                      'gb_pct': None,
                                      'hr9': None,
                                      'ip_per_gs': None,
                                      'k_bb_pct': None,
                                      'k_pct': None,
                                      'strike_pct': None},
                    ('missing', False): {'bb_pct': None,
                                         'era': 0.0,
                                         'hr9': 0.0,
                                         'k_bb_pct': None,
                                         'k_pct': None},
                    ('missing', True): {'bb_pct': None,
                                        'era': 0.0,
                                        'gb_pct': None,
                                        'hr9': 0.0,
                                        'ip_per_gs': None,
                                        'k_bb_pct': None,
                                        'k_pct': None,
                                        'strike_pct': None},
                    ('odd_outs', False): {'bb_pct': 0.1364,
                                          'era': 8.31,
                                          'hr9': 2.08,
                                          'k_bb_pct': 0.0909,
                                          'k_pct': 0.2273},
                    ('odd_outs', True): {'bb_pct': 0.1364,
                                         'era': 8.31,
                                         'gb_pct': 0.6,
                                         'hr9': 2.08,
                                         'ip_per_gs': 4.33,
                                         'k_bb_pct': 0.0909,
                                         'k_pct': 0.2273,
                                         'strike_pct': 0.6111},
                    ('reliever', False): {'bb_pct': 0.0886,
                                          'era': 2.83,
                                          'hr9': 0.79,
                                          'k_bb_pct': 0.2025,
                                          'k_pct': 0.2911},
                    ('reliever', True): {'bb_pct': 0.0886,
                                         'era': 2.83,
                                         'gb_pct': 0.5385,
                                         'hr9': 0.79,
                                         'ip_per_gs': None,
                                         'k_bb_pct': 0.2025,
                                         'k_pct': 0.2911,
                                         'strike_pct': 0.6476},
                    ('starter', False): {'bb_pct': 0.08,
                                         'era': 3.5,
                                         'hr9': 1.12,
                                         'k_bb_pct': 0.1867,
                                         'k_pct': 0.2667},
                    ('starter', True): {'bb_pct': 0.08,
                                        'era': 3.5,
                                        'gb_pct': 0.5556,
                                        'hr9': 1.12,
                                        'ip_per_gs': 6.0,
                                        'k_bb_pct': 0.1867,
                                        'k_pct': 0.2667,
                                        'strike_pct': 0.65},
                    ('zero_outs', False): {'bb_pct': 0.3333,
                                           'era': None,
                                           'hr9': None,
                                           'k_bb_pct': -0.3333,
                                           'k_pct': 0.0},
                    ('zero_outs', True): {'bb_pct': 0.3333,
                                          'era': None,
                                          'gb_pct': 1.0,
                                          'hr9': None,
                                          'ip_per_gs': None,
                                          'k_bb_pct': -0.3333,
                                          'k_pct': 0.0,
                                          'strike_pct': 0.4667}}

# ((num, den, nd), the lab's output before the move)
POOLED_EXPECTED = [((None, 3, 3), None),
                   ((5, None, 3), None),
                   ((5, 0, 3), None),
                   ((5, 0.0, 3), None),
                   ((1, 3, 3), 0.333),
                   ((2, 3, 2), 0.67),
                   ((10, 7, 4), 1.4286),
                   ((-1, 9, 3), -0.111),
                   ((405.0, 120.0, 2), 3.38),
                   ((0, 5, 3), 0.0)]


def test_public_hitter_rates_reproduce_the_lab_outputs():
    for name, acc in HITTER_FIXTURES.items():
        assert mr.hitter_rates(dict(acc)) == HITTER_EXPECTED[name], name


def test_public_pitcher_rates_reproduce_the_lab_outputs():
    for (name, starter), want in PITCHER_EXPECTED.items():
        got = mr.pitcher_rates(dict(PITCHER_FIXTURES[name]), starter=starter)
        assert got == want, (name, starter)


def test_public_pooled_reproduces_the_lab_outputs():
    for args, want in POOLED_EXPECTED:
        assert mr.pooled(*args) == want, args


def test_the_lab_imports_the_public_recipe_back():
    """The window boards call the public functions under the lab's old names,
    so the League tab and the windows share one recipe."""
    assert lab._hitter_rates is mr.hitter_rates
    assert lab._pitcher_rates is mr.pitcher_rates
    assert lab._pooled is mr.pooled
    assert lab._r is mr._r and lab._num is mr._num


def test_no_second_copy_of_the_recipe_in_the_lab():
    src = inspect.getsource(lab)
    for name in ("_hitter_rates", "_pitcher_rates", "_pooled", "_num", "_r"):
        assert f"def {name}(" not in src, f"the lab still defines {name}"
