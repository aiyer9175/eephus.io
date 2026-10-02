# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Test support for the projected $/WAR path (VAL_5): SYNTHETIC series only.

Builds a series file shaped like data/fa_dpw_series.json with a dpw_path block
written from a synthetic truth, and switches the unified path on in-process
through value_framework.dpw_path_forced(True, series_path=<tmp copy>), never
the live file and never the environment. Nothing here reads a real series or
computes an error of any arm.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import dpw_path as dp

B = 2027
N = B - 1
F_LEVEL = 17_143_641.0


def synthetic_truth(n_winters: int = 12, last: int = N, growth: float = 0.035,
                    start: float = 9.0e6, wiggle: float = 0.04) -> dict[int, float]:
    """A deterministic synthetic per-winter level series (no randomness)."""
    out = {}
    first = last - n_winters + 1
    for i, w in enumerate(range(first, last + 1)):
        out[w] = start * (1.0 + growth) ** i * (1.0 + wiggle * ((-1) ** i))
    return out


def synthetic_block(*, level_n: float = 16.46e6, g_ref: float = dp.G_REF_DEFAULT,
                    R: float = dp.R_DEFAULT, options: dict | None = None,
                    companion_mode: str = "neutral_follow_path",
                    league_min_table: dict | None = None,
                    arb_growth: float = 0.022, min_growth: float = 0.054,
                    method: str = "carry_const", g_a: float | None = None,
                    basis_id: str = "synthetic00001") -> dict:
    """A dpw_path block with the schema the writer emits (DESIGN_v2 4.1)."""
    truth = synthetic_truth()
    path = dp.build_path(level_n, N, method=method, g_ref=g_ref, g_a=g_a)
    table = league_min_table or {2023: 720_000.0, 2024: 740_000.0, 2025: 760_000.0, 2026: 780_000.0}
    last_tab = max(table)
    s_t = max(B, last_tab)
    lmin, arb = {}, {}
    for s in range(min(table), dp.WRITTEN_THROUGH + 1):
        base = table.get(s, table[last_tab])
        if s <= s_t:
            lmin[s] = base
        elif companion_mode == "neutral_follow_path":
            lmin[s] = lmin[s_t] * path[s] / path[s_t]
        elif companion_mode == "own_trends":
            lmin[s] = lmin[s_t] * (1.0 + min_growth) ** (s - s_t)
        else:
            lmin[s] = lmin[s_t]
        if s <= s_t:
            arb[s] = 1.0
        elif companion_mode == "neutral_follow_path":
            arb[s] = path[s] / path[s_t]
        elif companion_mode == "own_trends":
            arb[s] = (1.0 + arb_growth) ** (s - s_t)
        else:
            arb[s] = 1.0
    opts = dict(dp.CONVENTION_DEFAULTS)
    opts["companion_mode"] = companion_mode
    opts.update(options or {})
    band = dp.band(path, N, truth, 0.03, method)
    return {
        "schema": "dpw_path_v2",
        "truth": {"estimator": {"id": dp.TRUTH_ESTIMATOR_ID, "numerator_rate": 0.07,
                                "denominator_rate": 0.07},
                  "by_winter": {str(k): v for k, v in truth.items()}},
        "served_level": {"basis": opts["level_basis"], "by_winter": {str(N): level_n}},
        "clock": {"base_season": B, "last_realized_winter": N},
        "discount": {"form_served": "net_flat", "form_literal": "net_7_flat", "R_nominal": R,
                     "g_ref": g_ref, "g_ref_rule": "keep_0409", "r_net": (1 + R) / (1 + g_ref) - 1},
        "path": {"method": method, "usd_by_season": {str(k): v for k, v in path.items()},
                 "kind_by_season": {str(k): v for k, v in dp.path_kinds(N, method).items()},
                 "band": {"p10": {str(k): v for k, v in band["p10"].items()},
                          "p90": {str(k): v for k, v in band["p90"].items()}}},
        "salary_index": {"mode": companion_mode, "last_tabled_min_season": last_tab, "s_T": s_t,
                         "league_min_growth": min_growth, "arb_growth": arb_growth,
                         "league_min_by_season": {str(k): v for k, v in lmin.items()},
                         "arb_index_scale_by_season": {str(k): v for k, v in arb.items()}},
        "options": {**opts, "source": "data/dpw_path_owner.json"},
        "gate": {"doc": "docs/dpw-2026-09-25/DPW_PATH_GATE.md"},
        "basis_id": basis_id,
    }


def write_series(path: Path, block: dict | None = None, *, level_usd: float = F_LEVEL) -> Path:
    """A series file with VAL_1's keys and, when given, a dpw_path block."""
    doc = {"method": "fa_signings_implied_v1", "model_version": "synthetic",
           "usd_per_war_by_winter": {str(k): int(v) for k, v in synthetic_truth().items()},
           "breakdown": {}, "pricing": {"class_year": B, "level_usd": int(level_usd),
                                        "anchor_winter": N, "carry_rate": 0.0416}}
    if block is not None:
        doc["dpw_path"] = block
    Path(path).write_text(json.dumps(doc), encoding="utf-8")
    return Path(path)


@contextmanager
def unified(tmp_path: Path, *, stages=None, block: dict | None = None, **block_kw):
    """Switch the unified path on in-process over a synthetic series copy."""
    import value_framework as vf
    p = write_series(Path(tmp_path) / "fa_dpw_series_synthetic.json",
                     block if block is not None else synthetic_block(**block_kw))
    with vf.dpw_path_forced(True, stages=stages, series_path=p):
        yield p
