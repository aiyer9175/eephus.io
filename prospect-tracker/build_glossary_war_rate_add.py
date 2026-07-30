# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One-time glossary add (2026-07-29): the WAR/PA+ and WAR/IP+ family.

Six entries, because there are six distinct things on the boards:

  war_pa_plus          hitter board, batting bWAR per plate appearance
  war_pa_plus_3yr      its frozen trailing-window companion
  war_ip_plus_sp       starter board, pitching bWAR per inning, STARTER pool
  war_ip_plus_sp_3yr   its frozen trailing-window companion
  war_ip_plus_rp       reliever board, pitching bWAR per inning, RELIEVER pool
  war_ip_plus_rp_3yr   its frozen trailing-window companion

The two WAR/IP+ entries are separate on purpose. The starter board and the
reliever board carry a column with the same title over the same field name, and
the values are NOT comparable: a reliever banks more WAR per inning than a
starter of equal talent, so each is anchored on its own pool, exactly as SEM+ and
REM+ are two metrics rather than one. Each entry names its anchor pool, and the
warning is in both.

The forward numbers in the methodology text are read from
data/war_rate_plus_eval.json at build time rather than typed in, so the published
copy cannot drift away from the measurement it describes.

Idempotent: each insert is guarded on the slug, so a re-run only restamps the
version. Kept for provenance like its siblings (build_glossary_gmli_add.py,
build_glossary_consensus_weight_note.py).
"""

from __future__ import annotations

import json
from pathlib import Path

from build_glossary_data import glossary_version

ROOT = Path(__file__).parent
PATH = ROOT / "data" / "glossary.json"
EVAL_PATH = ROOT / "data" / "war_rate_plus_eval.json"
LEDGER = "data/war_rate_plus_eval.json"
MULTIYR_LEDGER = "data/war_rate_plus_multiyear_eval.json"

ORIGIN = "Arkmetric, created by Noah J. Dengler, original to eephus.io."

# how each gate baseline reads in plain prose
_BASE_LABEL = {
    "war_total": "plain season bWAR with no rate at all",
    "rate": "the same rate left unstandardized",
    "ops_plus": "OPS+",
    "ra9_inv": "runs allowed per nine",
    "plus_shrunk": "a sample-shrunk version of itself",
}


def _figs() -> dict:
    """Per-pool forward figures from the committed ledger."""
    art = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    out = {}
    for pool, blk in art["pools"].items():
        v = blk["verdict"]
        g2 = v["g2_ship_vs_best_baseline"]
        w = blk["window_gate"].get("g4_window_beats_one_season") or {}
        wr = (blk["window_gate"].get("results_by_convention") or {}).get("v2") or {}
        out[pool] = {
            "n": blk["n_forward_pairs"],
            "rho": g2["rho_primary"],
            "base": g2["best_baseline"],
            "base_rho": g2["rho_baseline"],
            "g2": bool(g2["pass"]),
            "placebo_rho": blk["results_by_convention"]["v2"]["rho_baselines"]["placebo"],
            "seasons": f"{min(blk['pred_seasons'])}-{max(blk['out_seasons'])}",
            "win_n": blk["window_gate"].get("n_forward_pairs"),
            "win_rho": wr.get("rho_window"),
            "win_one": wr.get("rho_one_season"),
            "g4": bool(w.get("pass")),
        }
    return out


def _scale_para(anchor: str, denom: str, gate: str) -> str:
    return (
        f"Anchored at 100 with ten points per standard deviation of the anchor "
        f"pool, which is {anchor}. That is a different ruler from the HEM+ / SEM+ "
        f"/ REM+ columns beside it: those are ratios to the pool average, where a "
        f"point is about one percent. Ten WAR-rate points is one full standard "
        f"deviation, so 120 is a top-2.5-percent season and 80 is a bottom-2.5-"
        f"percent one. A ratio index cannot be built here at all, because the "
        f"league average WAR per {denom} is a hair above zero and individual "
        f"values go negative, so dividing by the pool average would flip sign and "
        f"blow up. Ten points per standard deviation is the only honest scale for "
        f"a signed near-zero-mean rate.\n\n"
        f"Two volume floors, doing two different jobs. Everyone at or above the "
        f"pool floor sets the pool average and spread; only players at or above "
        f"{gate} get a published value, so a brief hot stretch cannot print a "
        f"number. The value is not shrunk toward the average and not clamped at "
        f"either end, so what you read is what the player actually banked, "
        f"including the tail. Right at the display gate the sample is still "
        f"small, which is why the default board view also applies its usual "
        f"qualified filter."
    )


def _forward_para(f: dict, label: str) -> str:
    base = _BASE_LABEL.get(f["base"], f["base"])
    if f["g2"]:
        return (
            f"Forward-checked out of sample, and it won. Over {f['seasons']} "
            f"(excluding 2020) and {f['n']} year-to-year pairs, {label} predicts "
            f"next season's WAR rate at a Spearman correlation of {f['rho']}, "
            f"against {f['base_rho']} for {base}, with the paired bootstrap gap "
            f"holding above zero. Accountability artifact: {LEDGER}."
        )
    return (
        f"Forward-checked out of sample, and it lost. Over {f['seasons']} "
        f"(excluding 2020) and {f['n']} year-to-year pairs, {label} predicts next "
        f"season's WAR rate at a Spearman correlation of {f['rho']}, while {base} "
        f"predicts the same thing at {f['base_rho']}. It is not noise: a "
        f"zero-information control on the same pairs scores {f['placebo_rho']}, so "
        f"the number carries real signal about the player. It simply does not "
        f"forecast better than the plainest alternative, because a season of "
        f"playing time is itself a talent signal that a per-trip rate throws away. "
        f"So this is registered as a descriptive display index with no validated "
        f"verdict and no eval artifact attached, rather than dressed up with a "
        f"backtest it did not pass. Read it as what a player banked, not as a "
        f"forecast. Measurement ledger: {LEDGER}."
    )


def _window_para(f: dict, label: str, denom: str, est: str) -> str:
    head = (
        f"The {denom}-weighted mean of the player's single-season {label} across "
        f"the trailing three seasons, so a partial current season counts for what "
        f"it is worth and the fuller prior seasons carry more. Established means "
        f"two or more seasons and {est} in the window; below that the value is "
        f"marked provisional with a star.\n\n"
        f"This column is a FROZEN vintage, not a live number. The values are read "
        f"verbatim from {MULTIYR_LEDGER} and are never recomputed when the board "
        f"is built, so a row can show a same-day one-year value beside a "
        f"three-year value frozen weeks earlier, and a player who entered the pool "
        f"after that file was generated is simply blank. The board payload carries "
        f"the generation date so the gap is visible rather than silent.\n\n"
    )
    if f["g4"] and f["win_rho"] is not None:
        return head + (
            f"Forward-checked: over {f['win_n']} pairs the three-year read "
            f"predicts next season's WAR rate at a Spearman correlation of "
            f"{f['win_rho']} against {f['win_one']} for a single season on the "
            f"same players, with the paired gap confidence floor above zero, so "
            f"more sample really is a steadier read."
        )
    if f["win_rho"] is not None:
        return head + (
            f"Forward-checked and unresolved: over {f['win_n']} pairs the "
            f"three-year read predicts next season's WAR rate at a Spearman "
            f"correlation of {f['win_rho']} against {f['win_one']} for a single "
            f"season on the same players, and the paired gap does not clear zero. "
            f"It is offered as a longer window on the same scale, not as a better "
            f"forecast."
        )
    return head + "Measurement ledger: " + LEDGER + "."


def _entries() -> list[dict]:
    f = _figs()
    two_way = (
        "Two-way players are handled by keeping the two sides of bWAR apart "
        "rather than by any discount factor. Batting WAR is divided by plate "
        "appearances on the hitter board and pitching WAR by innings on a pitcher "
        "board, so a two-way player carries two different indexes on two "
        "different boards and both are correct."
    )
    src = (
        "Source: Baseball-Reference WAR (bWAR), the site-wide WAR standard, with "
        "the batting and pitching sides read from separate keys so the two are "
        "never summed onto one number."
    )
    return [
        {
            "id": "war_pa_plus",
            "term": "WAR/PA+",
            "category": "custom-index",
            "module": ["mlbstats"],
            "aliases": ["WAR/PA+", "WAR per PA", "WAR rate (hitters)",
                        "war rate plus"],
            "priority": 23,
            "definition": (
                "How much total value a hitter banked per trip to the plate, on a "
                "100-anchored scale where ten points is one standard deviation of "
                "the hitter pool. Batting bWAR divided by plate appearances. It "
                "answers a different question from HEM+: HEM+ is offensive rate "
                "alone, while WAR/PA+ carries fielding, baserunning and the "
                "positional adjustment, so a good defender at a hard position can "
                "sit well above his HEM+ and a designated hitter well below it. "
                "Needs 100 plate appearances to show."
            ),
            "methodology": (
                _scale_para("hitters with 50 or more plate appearances",
                            "plate appearance", "100 plate appearances")
                + "\n\n" + src + " " + two_way + "\n\n"
                + _forward_para(f["hit"], "WAR/PA+")
            ),
            "seeAlso": ["war_pa_plus_3yr", "hem_plus", "war",
                        "war_ip_plus_sp", "war_ip_plus_rp"],
            "shelf": "ark",
            "origin": ORIGIN,
        },
        {
            "id": "war_pa_plus_3yr",
            "term": "WAR/PA+ (3yr)",
            "category": "custom-index",
            "module": ["mlbstats"],
            "aliases": ["WAR/PA+ 3yr", "three-year WAR/PA+", "trailing WAR/PA+"],
            "priority": 24,
            "definition": (
                "A hitter's WAR/PA+ over the trailing three seasons, weighted by "
                "plate appearances. Steadier than one season, because a WAR rate "
                "carries fielding and baserunning on top of the bat and all three "
                "bounce around in a single year. Same 100-anchored, ten-points-"
                "per-standard-deviation scale as WAR/PA+."
            ),
            "methodology": _window_para(f["hit"], "WAR/PA+", "plate-appearance",
                                        "600 plate appearances"),
            "seeAlso": ["war_pa_plus", "hem_plus_3yr", "war_ip_plus_sp_3yr",
                        "war_ip_plus_rp_3yr"],
            "shelf": "ark",
            "origin": ORIGIN,
        },
        {
            "id": "war_ip_plus_sp",
            "term": "WAR/IP+ (starter pool)",
            "category": "custom-index",
            "module": ["mlbstats"],
            "aliases": ["WAR/IP+", "WAR per IP", "WAR rate (starters)"],
            "priority": 23,
            "definition": (
                "How much value a starting pitcher banked per inning, on a "
                "100-anchored scale where ten points is one standard deviation of "
                "the STARTER pool. Pitching bWAR divided by innings pitched, "
                "anchored on starters only. It reads run prevention and workload "
                "together, where SEM+ is run-prevention rate alone. It does not "
                "compare with the reliever board's WAR/IP+: relievers bank more "
                "WAR per inning than starters of equal talent, so the two boards "
                "are anchored on separate pools and are never pooled into one "
                "ranking. Needs 40 innings to show."
            ),
            "methodology": (
                _scale_para("starters with 20 or more innings", "inning",
                            "40 innings")
                + "\n\n" + src + " " + two_way + "\n\n"
                + _forward_para(f["SP"], "starter WAR/IP+")
            ),
            "seeAlso": ["war_ip_plus_sp_3yr", "war_ip_plus_rp", "sem_plus",
                        "war", "war_pa_plus"],
            "shelf": "ark",
            "origin": ORIGIN,
        },
        {
            "id": "war_ip_plus_sp_3yr",
            "term": "WAR/IP+ (starter pool, 3yr)",
            "category": "custom-index",
            "module": ["mlbstats"],
            "aliases": ["WAR/IP+ 3yr (starters)", "three-year starter WAR/IP+"],
            "priority": 24,
            "definition": (
                "A starter's WAR/IP+ over the trailing three seasons, weighted by "
                "innings. Same starter-anchored, ten-points-per-standard-deviation "
                "scale as WAR/IP+, over a longer window."
            ),
            "methodology": _window_para(f["SP"], "starter WAR/IP+", "innings",
                                        "120 innings"),
            "seeAlso": ["war_ip_plus_sp", "sem_plus_3yr", "war_ip_plus_rp_3yr",
                        "war_pa_plus_3yr"],
            "shelf": "ark",
            "origin": ORIGIN,
        },
        {
            "id": "war_ip_plus_rp",
            "term": "WAR/IP+ (reliever pool)",
            "category": "custom-index",
            "module": ["mlbstats"],
            "aliases": ["WAR/IP+ (relievers)", "WAR rate (relievers)"],
            "priority": 23,
            "definition": (
                "How much value a reliever banked per inning, on a 100-anchored "
                "scale where ten points is one standard deviation of the RELIEVER "
                "pool. Pitching bWAR divided by innings pitched, anchored on "
                "relievers only. It does not compare with the starter board's "
                "WAR/IP+: a reliever banks more WAR per inning than a starter of "
                "equal talent, so the two boards are anchored on separate pools "
                "and are never pooled into one ranking. Unlike REM+ it is not "
                "leverage-blind by construction, because bWAR carries the runs a "
                "pitcher actually prevented; the gmLI and WPA columns still hold "
                "the deployment story on their own. Needs 30 innings to show."
            ),
            "methodology": (
                _scale_para("relievers with 20 or more innings", "inning",
                            "30 innings")
                + "\n\n" + src + " " + two_way + "\n\n"
                + _forward_para(f["RP"], "reliever WAR/IP+")
            ),
            "seeAlso": ["war_ip_plus_rp_3yr", "war_ip_plus_sp", "rem_plus",
                        "riv_plus", "war"],
            "shelf": "ark",
            "origin": ORIGIN,
        },
        {
            "id": "war_ip_plus_rp_3yr",
            "term": "WAR/IP+ (reliever pool, 3yr)",
            "category": "custom-index",
            "module": ["mlbstats"],
            "aliases": ["WAR/IP+ 3yr (relievers)", "three-year reliever WAR/IP+"],
            "priority": 24,
            "definition": (
                "A reliever's WAR/IP+ over the trailing three seasons, weighted by "
                "innings. Same reliever-anchored, ten-points-per-standard-"
                "deviation scale as WAR/IP+, over a longer window."
            ),
            "methodology": _window_para(f["RP"], "reliever WAR/IP+", "innings",
                                        "40 innings"),
            "seeAlso": ["war_ip_plus_rp", "rem_plus_3yr", "war_ip_plus_sp_3yr",
                        "war_pa_plus_3yr"],
            "shelf": "ark",
            "origin": ORIGIN,
        },
    ]


def main() -> None:
    d = json.loads(PATH.read_text(encoding="utf-8"))
    entries = d["entries"]
    added, updated = [], []
    # anchor the family right after the HEM+ 3yr entry so the plus metrics read
    # together on the Arkmetrics shelf
    at = next((i for i, e in enumerate(entries) if e["id"] == "hem_plus_3yr"),
              len(entries) - 1) + 1
    for ent in _entries():
        idx = next((i for i, e in enumerate(entries) if e["id"] == ent["id"]), None)
        if idx is None:
            entries.insert(at, ent)
            at += 1
            added.append(ent["id"])
        else:
            # a re-run after a fresh lab pass refreshes the measured figures
            entries[idx] = ent
            updated.append(ent["id"])
    ids = {e["id"] for e in entries}
    dangling = [(e["id"], r) for e in _entries() for r in e["seeAlso"] if r not in ids]
    if dangling:
        raise SystemExit(f"dangling seeAlso references: {dangling}")
    d["version"] = glossary_version()
    # Match the committed serialization EXACTLY (ensure_ascii=False, indent=2, no
    # trailing newline). The older sibling adders use indent=1, which reformats all
    # 6,200 lines and buries a 145-line content change in a whole-file diff. This
    # file is hand-reviewed pure copy, so the diff has to stay readable.
    PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8",
                    newline="")
    print(f"added {added or 'none'}, refreshed {updated or 'none'}")
    print(f"wrote {PATH.name} - {len(entries)} entries, version {d['version']}")


if __name__ == "__main__":
    main()
