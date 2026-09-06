"""M-ENG-1: the empirical win-expectancy table, and the state a decision sits in.

WHAT IT IS. WE(state) is the probability the HOME team wins, given the game state
before a play: inning, half, score difference, outs, and which bases are occupied.
It is estimated from this repo's own play corpus (1,448,967 plays across 2018,
2019 and 2021-2026) rather than taken from a published table, for one reason: a
decision metric has to be able to say what the alternative was worth, and an
outside table cannot be interrogated about its own sample, its own era, or its
own uncertainty.

WHY NOT JUST USE THE FEED'S WIN PROBABILITY. The corpus already carries MLB's
`wp_home_before` on every play, and it is used here as a CHECK rather than as the
engine. Two reasons. It is a black box, so a state it prices oddly cannot be
investigated. And it is a live in-game number that reflects the specific teams
playing, while a decision metric needs the value of a STATE to a generic team:
crediting a manager for having better players is exactly the confound the whole
module exists to avoid. The agreement between the two is published, and it is the
main evidence this table is not wrong.

THE STATE, and what is deliberately left out of it. Inning (capped), half, score
difference (capped), outs, and the three-bit base state. NOT included: the teams,
the batter, the pitcher, the park, the count. Those all matter to a real win
probability and every one of them would let a manager's roster leak into his
grade. The table is a league-average, context-free valuation of a situation, which
is the only thing a decision can be fairly scored against.

CAPPING IS NOT ROUNDING. Innings past the cap and score differences past the cap
are pooled, because the tail states are individually rare and a table that reports
a value from four observations is worse than one that says it is pooling. Every
cell carries its own n, and a cell under the minimum is served from its pooled
parent with `backed_off` set, so a caller can never silently read a number that
rests on nothing.

Offline. Reads .cache/pbp_corpus, writes data/win_expectancy.json.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / ".cache" / "pbp_corpus"
OUT = ROOT / "data" / "win_expectancy.json"

log = logging.getLogger(__name__)

#: Innings past this are pooled into it. Extra innings since 2020 start with a
#: runner on second (the `runner_placed` event), which makes the 10th a
#: structurally different game; it is pooled rather than modelled, and the
#: automatic-runner era is flagged on the artifact.
INNING_CAP = 9

#: Score differences past this are pooled at the cap. Beyond five runs the win
#: probability is close enough to flat that the extra resolution buys nothing and
#: costs sample.
DIFF_CAP = 5

#: A cell below this many observations is not served on its own. It backs off to
#: a pooled parent, and says so.
MIN_CELL_N = 200

SIDES = ("top", "bottom")


def base_code(on_first, on_second, on_third) -> int:
    """0..7. Bit 0 is first, bit 1 is second, bit 2 is third."""
    return (1 if on_first else 0) | (2 if on_second else 0) | (4 if on_third else 0)


BASE_LABELS = {
    0: "empty", 1: "1B", 2: "2B", 3: "1B2B",
    4: "3B", 5: "1B3B", 6: "2B3B", 7: "loaded",
}


def state_key(inning, half, score_diff, outs, base) -> str:
    """The canonical cell key. `score_diff` is HOME minus AWAY, from the home
    team's point of view, always, in every function in this module."""
    inn = min(int(inning), INNING_CAP)
    d = max(-DIFF_CAP, min(DIFF_CAP, int(score_diff)))
    return f"{inn}|{half}|{d}|{int(outs)}|{int(base)}"


def parent_key(inning, half, score_diff, outs, base) -> str:
    """The back-off cell: same inning, half, outs and bases, score difference
    collapsed to its sign. Chosen because score difference is the dimension with
    the most cells and the least curvature far from zero, so collapsing it costs
    the least information per observation recovered."""
    inn = min(int(inning), INNING_CAP)
    d = int(score_diff)
    sign = "lead" if d > 0 else ("trail" if d < 0 else "tied")
    return f"{inn}|{half}|{sign}|{int(outs)}|{int(base)}"


def _seasons(corpus: Path):
    d = corpus / "plays"
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())


def build(*, corpus: Path | None = None, seasons=None,
          min_cell_n: int = MIN_CELL_N) -> dict:
    """Estimate WE from the corpus. Returns the artifact dict."""
    import pandas as pd

    corpus = Path(corpus or CORPUS)
    want = list(seasons) if seasons else _seasons(corpus)
    if not want:
        raise FileNotFoundError(f"no play tables under {corpus / 'plays'}")

    cells: dict = {}
    parents: dict = {}
    feed_sum = feed_n = 0.0
    n_plays = 0
    used = []
    for season in want:
        files = sorted((corpus / "plays" / season).glob("*.parquet"))
        if not files:
            continue
        for f in files:
            df = pd.read_parquet(f, columns=[
                "game_pk", "inning", "half", "outs_before", "on_first",
                "on_second", "on_third", "home_score", "away_score",
                "wp_home_before"])
            for col in ("on_first", "on_second", "on_third"):
                if df[col].dtype == bool:
                    raise TypeError(
                        f"{col} is boolean in this corpus build. This function "
                        "reads occupancy with notna() because the documented "
                        "schema stores a runner id or NaN; a boolean column "
                        "means the schema changed and the base state would be "
                        "read wrong in a way that still produces a table.")
            # THE OUTCOME. One label per GAME, joined back onto every play in it:
            # did the home team win. Ties (a suspended game, a corrupt feed) are
            # dropped rather than split, because half a win is not an outcome
            # anyone observed.
            last = df.groupby("game_pk")[["home_score", "away_score"]].last()
            won = (last["home_score"] > last["away_score"]).astype(float)
            tied = last["home_score"] == last["away_score"]
            won = won[~tied]
            df = df[df["game_pk"].isin(won.index)]
            if df.empty:
                continue
            y = df["game_pk"].map(won).to_numpy()
            diff = (df["home_score"] - df["away_score"]).to_numpy()
            # OCCUPANCY IS `notna`, NOT `astype(bool)`. The corpus stores the
            # RUNNER'S PLAYER ID on each base, as a float64 with NaN for empty.
            # numpy's bool() of NaN is True, so astype(bool) reports every base
            # occupied and collapses the whole table onto the loaded state. That
            # is not a hypothetical: it is what this function did on its first
            # run, and it produced 576 cells that were all bases-loaded while
            # looking entirely healthy.
            base = (df["on_first"].notna().to_numpy().astype(int)
                    | (df["on_second"].notna().to_numpy().astype(int) << 1)
                    | (df["on_third"].notna().to_numpy().astype(int) << 2))
            inn = df["inning"].to_numpy()
            half = df["half"].astype(str).to_numpy()
            outs = df["outs_before"].to_numpy()
            wpb = df["wp_home_before"].to_numpy()
            for i in range(len(df)):
                k = state_key(inn[i], half[i], diff[i], outs[i], base[i])
                c = cells.get(k)
                if c is None:
                    c = cells[k] = [0, 0.0]
                c[0] += 1
                c[1] += y[i]
                pk = parent_key(inn[i], half[i], diff[i], outs[i], base[i])
                p = parents.get(pk)
                if p is None:
                    p = parents[pk] = [0, 0.0]
                p[0] += 1
                p[1] += y[i]
                w = wpb[i]
                if w == w and w is not None:      # not NaN
                    # THE FEED PUBLISHES PERCENT, 0.1 to 99.9, not a
                    # probability. Comparing it to a 0/1 outcome without the
                    # divide reports a mean absolute error of about 50, which
                    # is what the first run of this function printed.
                    feed_sum += abs(float(w) / 100.0 - y[i])
                    feed_n += 1
            n_plays += len(df)
            used.append(season)

    table = {}
    backed = 0
    for k, (n, s) in cells.items():
        if n >= min_cell_n:
            table[k] = {"we": round(s / n, 5), "n": int(n), "backed_off": False}
    # Second pass so every observed cell resolves, even the thin ones.
    for k, (n, s) in cells.items():
        if k in table:
            continue
        inn, half, d, outs, base = k.split("|")
        pk = parent_key(int(inn), half, int(d), int(outs), int(base))
        pn, ps = parents.get(pk, (0, 0.0))
        if pn >= min_cell_n:
            table[k] = {"we": round(ps / pn, 5), "n": int(pn),
                        "backed_off": True, "backed_off_to": pk,
                        "own_n": int(n)}
            backed += 1
        else:
            table[k] = {"we": round(s / n, 5), "n": int(n), "backed_off": False,
                        "thin": True}
    return {
        "generated_at": datetime.now(timezone.utc)
                        .replace(microsecond=0).isoformat(),
        "produced_by": "win_expectancy.py",
        "schema_version": 1,
        "seasons": sorted(set(used)),
        "n_plays": int(n_plays),
        "n_cells": len(table),
        "n_cells_backed_off": backed,
        "min_cell_n": min_cell_n,
        "inning_cap": INNING_CAP,
        "diff_cap": DIFF_CAP,
        "state": ("inning (capped), half, home-minus-away score difference "
                  "(capped), outs, 3-bit base state"),
        "state_excludes": (
            "the teams, the batter, the pitcher, the park and the count. Every "
            "one of them matters to a real win probability and every one would "
            "let a manager's roster leak into his grade. This is a "
            "league-average valuation of a SITUATION, which is the only thing a "
            "decision can be fairly scored against."),
        "feed_agreement": {
            "mean_abs_error_of_feed_wp_vs_outcome": (round(feed_sum / feed_n, 5)
                                                     if feed_n else None),
            "n": int(feed_n),
            "what_it_is": (
                "the MLB feed's own wp_home_before scored against the realized "
                "game outcome on the same plays. Reported as a CHECK, never as "
                "the engine: the feed is a black box and a live number that "
                "reflects the specific teams playing, and crediting a manager "
                "for having better players is the confound this module exists "
                "to avoid."),
        },
        "extra_innings_note": (
            "innings past the cap are pooled into it. Since 2020 extra innings "
            "start with an automatic runner on second, so the 10th is a "
            "structurally different game; it is pooled rather than modelled, "
            "and no decision family should read a capped-inning cell without "
            "saying so."),
        "table": table,
    }


class WinExpectancy:
    """A loaded table with a safe lookup."""

    def __init__(self, art: dict):
        self.art = art
        self.table = art["table"]

    @classmethod
    def load(cls, path: Path | None = None) -> "WinExpectancy":
        p = Path(path or OUT)
        return cls(json.loads(p.read_text(encoding="utf-8")))

    def we(self, inning, half, score_diff, outs, base) -> float | None:
        """Home win probability for the state, or None when the table has never
        seen it. None, never a default: a decision priced off a made-up 0.5 is
        worse than a decision that reports it could not be priced."""
        c = self.table.get(state_key(inning, half, score_diff, outs, base))
        return None if c is None else float(c["we"])

    def cell(self, inning, half, score_diff, outs, base) -> dict | None:
        return self.table.get(state_key(inning, half, score_diff, outs, base))

    def offense_we(self, inning, half, score_diff, outs, base) -> float | None:
        """Win probability for the team AT BAT.

        The table is stated from the home team's point of view throughout, so
        the batting team's probability is the table value in the bottom half and
        its complement in the top. Every decision family must call this rather
        than `we`, because a manager's decision is good or bad for HIS team.
        """
        v = self.we(inning, half, score_diff, outs, base)
        if v is None:
            return None
        return v if str(half).lower().startswith("bot") else 1.0 - v


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s: %(message)s")
    art = build()
    if "--dry-run" not in argv:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(art, indent=1) + "\n", encoding="utf-8")
    print(f"seasons {art['seasons']}")
    print(f"plays {art['n_plays']:,}  cells {art['n_cells']:,} "
          f"({art['n_cells_backed_off']:,} backed off to a pooled parent)")
    fa = art["feed_agreement"]
    print(f"feed wp mean abs error vs outcome: "
          f"{fa['mean_abs_error_of_feed_wp_vs_outcome']} over {fa['n']:,} plays")
    we = WinExpectancy(art)
    print("\nsanity, bottom of the 9th, tied, bases empty, by outs:")
    for o in (0, 1, 2):
        print(f"   {o} out: home WE = {we.we(9, 'bottom', 0, o, 0)}")
    print("sanity, top of the 1st, tied, bases empty, 0 out: "
          f"{we.we(1, 'top', 0, 0, 0)}")
    if "--dry-run" not in argv:
        print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
