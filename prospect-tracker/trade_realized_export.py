# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PROSPX Transactions Trade Audit - the REALIZED leg (data/trade_realized.json).

THE QUESTION. The Trade Audit card prices every party at today's Trade Machine value:
what a club would pay for him now. That is a forecast of what is left, not a record of
what happened. Owner answer M9 (2026-09-25): add what each club ACTUALLY GOT after the
trade, as WAR the player produced for the receiving club from the trade date, priced at
the same $/WAR the trade value uses, shown beside the value-today verdict and labelled
realized-to-date with the as-of date.

WHAT THIS FILE IS. Per-stint season WAR for every player on the Trade Machine board, on
the DISPLAYED WAR basis (eWAR v2, war_source.DISPLAY_PROVIDER, the basis a visitor sees
everywhere). The source is the war_daily STINT frame (war_source.stint_frame): one row per
player, season, club and stint, whose WAR column is the eWAR v2 side total spread across
the player-season's stints by PA or IPouts, so the stints of one side sum back to that
side's season WAR (pinned by test_war_source_ewar). A traded player's season is therefore
split between the clubs he played for, and no season is counted twice.

WHAT IT IS NOT. It carries no trade, no date and no price. The page picks the stints that
fall after a given trade (prospx _taRealizedWar) and prices the sum at `dollars_per_war_mm`,
which is value_framework.dollars_per_war_flat(): the same flat level the Trade Machine
calibration reports as dpw_level_usd (pinned by test). A stint frame has no calendar dates,
so "from the trade date" is resolved at stint resolution: in the trade season, the receiving
club's stints that follow the sending club's stint are credited, and when the player has no
stint with the sender that season (a prospect, or an offseason deal) every stint with the
receiver counts. Seasons before the trade year are never credited.

Rows are positional, by `fields`: [season, club, stint, side, war], side 0 = batting and
1 = pitching, war to three decimals. Clubs are the canonical codes the page uses (OAK is
ATH). A player with no MLB time has no row, and the page reads that as zero realized.

Run: `python trade_realized_export.py`
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger("trade_realized_export")

DATA_DIR = ROOT / "data"
#: Redirected by tests, like war_board_export.OUT_PATH: every other path derives from it.
OUT_PATH = DATA_DIR / "trade_realized.json"
BOARD_NAME = "trade_values.json"

SCHEMA = 1
FIELDS = ["season", "club", "stint", "side", "war"]
#: The first season the eWAR v2 label pool reaches (war_source.EWAR_BUILD_CMD --first 2011).
FIRST_SEASON = 2011
#: A board of fewer players than this with any stint is a dead read, not a quiet day.
MIN_PLAYERS = 500


def board_mlbam_ids(board_path: Path | str) -> set[int]:
    """Every mlbam id on the Trade Machine board: the only players the audit can price."""
    doc = json.loads(Path(board_path).read_text(encoding="utf-8"))
    out: set[int] = set()
    for r in doc.get("players") or []:
        try:
            if r.get("mlbam_id") is not None:
                out.add(int(r["mlbam_id"]))
        except (TypeError, ValueError):
            continue
    return out


def build_players(frames: dict, ids: set[int], *, first: int = FIRST_SEASON) -> dict:
    """{mlbam: [[season, club, stint, side, war], ...]} from {"bat": frame, "pit": frame}.

    A frame is a DataFrame or a list of dicts with mlb_ID, year_ID, team_ID, stint_ID, WAR.
    Rows are ordered by season, then stint, then side, so the page can walk them in order."""
    import trades

    def _records(fr):
        if hasattr(fr, "to_dict"):
            cols = [c for c in ("mlb_ID", "year_ID", "team_ID", "stint_ID", "WAR") if c in fr.columns]
            return fr[cols].to_dict("records")
        return list(fr)

    out: dict[int, list] = {}
    for side_i, side in enumerate(("bat", "pit")):
        for r in _records(frames[side]):
            m, yr, club, stint, war = (r.get("mlb_ID"), r.get("year_ID"), r.get("team_ID"),
                                       r.get("stint_ID"), r.get("WAR"))
            if m is None or m != m or yr is None or yr != yr or war is None or war != war:
                continue
            m = int(m)
            if m not in ids or int(yr) < first:
                continue
            code = trades.canonical_org(str(club)) if club else None
            if not code:
                continue
            out.setdefault(m, []).append(
                [int(yr), code, int(stint) if stint == stint and stint is not None else 1,
                 side_i, round(float(war), 3)])
    for rows in out.values():
        rows.sort(key=lambda t: (t[0], t[2], t[3]))
    return dict(sorted(out.items()))


def export(*, out_path: Path | str | None = None, board_path: Path | str | None = None,
           frames: dict | None = None, today: str | None = None, log=print) -> int:
    """Write data/trade_realized.json. Returns the number of players written (0 = kept)."""
    out_path = Path(out_path) if out_path is not None else Path(OUT_PATH)
    board_path = Path(board_path) if board_path is not None else out_path.parent / BOARD_NAME
    today = today or date.today().isoformat()
    if not board_path.exists():
        log(f"  trade realized: {board_path.name} is missing; {out_path.name} left as it is")
        return 0
    ids = board_mlbam_ids(board_path)
    if frames is None:
        import war_board_export as wbe
        import war_source
        # The DISPLAY door: the stint frame on eWAR v2 (war_board_export names it explicitly).
        frames = {side: wbe._stint_frame(side) for side in ("bat", "pit")}
        stale = sorted(war_source.served_stale())
        basis = war_source.DISPLAY_PROVIDER
        vintage = war_source.safe_ewar_vintage(as_of=today)
    else:
        stale, basis, vintage = [], "ewar_v2", None
    # AS-OF: the date the eWAR artifact behind the stint frame was built, not the run date,
    # so the page never claims WAR through a day the build had not seen.
    built = str(((vintage or {}).get("artifact_generated_at") or ""))[:10]
    as_of = built if len(built) == 10 else today
    players = build_players(frames, ids)
    if len(players) < MIN_PLAYERS:
        log(f"  trade realized: REFUSED, only {len(players)} board players carry a stint "
            f"(need {MIN_PLAYERS}); {out_path.name} left as it is")
        return 0
    import value_framework as vf
    dpw_mm = float(vf.dollars_per_war_flat())
    doc = {
        "generated_at": today,
        "as_of": as_of,
        "schema": SCHEMA,
        "war_provider": basis,
        "ewar_vintage": vintage,
        "stale_sides": stale,
        "dollars_per_war_mm": round(dpw_mm, 6),
        "dollars_per_war_source": ("value_framework.dollars_per_war_flat(), the level the "
                                   "Trade Machine calibration reports as dpw_level_usd"),
        "first_season": FIRST_SEASON,
        "fields": FIELDS,
        "n_players": len(players),
        "note": ("Per-stint season WAR on the displayed eWAR v2 basis for every Trade Machine "
                 "player. A stint frame has no calendar dates: the page credits a receiving "
                 "club only the stints that follow the sending club's stint in the trade "
                 "season, and every stint in later seasons. Rows are [season, club, stint, "
                 "side, war] with side 0 batting and 1 pitching. No row means no MLB time."),
        "players": {str(k): v for k, v in players.items()},
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    tmp.replace(out_path)
    log(f"  trade realized: wrote {out_path.name} ({len(players)} players)")
    return len(players)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    n = export(log=print)
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
