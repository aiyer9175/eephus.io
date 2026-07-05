"""Draft War Room live poller.

During the MLB draft (July 12-13) a cron on the nginx box calls
`build_draft_live` every 60-90 seconds. It joins the live pick feed to our
committed draft board and prices each pick in surplus dollars, then writes a
single READ-ONLY artifact `data/draft_live.json` for the front end.

Launch-critical invariants:
  * This poller is STRICTLY READ-ONLY toward site state. It NEVER writes to
    prospects.db or draft_timeseries.json and NEVER triggers promotion or the
    mock-draft kill. It writes ONLY the out_path artifact, atomically (temp
    file in the same dir, then os.replace).
  * No new dependencies - stdlib plus existing repo modules only.
  * It degrades gracefully: any API failure still writes a valid artifact with
    an empty picks list and a status field, so the front end can show a
    "waiting for picks" state instead of breaking.

The poll cadence lives in the cron, not here. One build is cheap to repeat.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

# Existing repo helpers (reused, not reimplemented).
import scrapers                       # scrape_mlb_draft_tracker
import storage                        # _pick_slot_expected_war
import fa_market                      # _slot_surplus_usd
from prospect_savant import _norm_name  # accent/punct-stripping name key

_REPO = Path(__file__).resolve().parent.parent
_DEFAULT_BOARD = _REPO / "data" / "draft_timeseries.json"
_DEFAULT_OUT = _REPO / "data" / "draft_live.json"

# A pick this many spots off the board rank counts as a steal or a reach.
# Inside the window it reads as "on board" (roughly where we had him).
_STEAL_REACH_THRESHOLD = 5
# Position tags that mark a pitcher, for the clemens_2026 role-split tier lookup.
_PITCHER_POS = {"RHP", "LHP", "SP", "RP", "MIRP", "SIRP", "CL", "P"}


def _current_draft_year() -> int:
    today = datetime.date.today()
    # The draft runs in July; before then the "current" class is this year.
    return today.year


def _load_board(board_path, year: int):
    """Return (board_by_norm_name, mock_pick_by_key) for the given class year.

    board_by_norm_name: normalized player name -> prospect dict.
    mock_pick_by_key:   player_key -> mock overall pick number.
    Missing/unreadable board yields two empty dicts (everything off board)."""
    board: dict[str, dict] = {}
    mock: dict[str, int] = {}
    try:
        data = json.loads(Path(board_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return board, mock
    cls = None
    for c in data.get("classes") or []:
        if c.get("year") == year:
            cls = c
            break
    if not cls:
        return board, mock
    for p in cls.get("prospects") or []:
        nm = _norm_name(p.get("player_name"))
        if nm and nm not in board:
            board[nm] = p
    md = cls.get("mock_draft") or {}
    for mp in md.get("picks") or []:
        key = mp.get("player_key")
        po = mp.get("pick_overall")
        if key and po is not None and key not in mock:
            mock[key] = po
    return board, mock


def _board_efv(prospect: dict):
    """The board eFV grade if the board carries one, else None. The committed
    board does not currently expose eFV per prospect, so this stays None until
    it does - guarded so the artifact schema is stable either way."""
    for k in ("efv", "efv_grade", "xfv_grade"):
        v = prospect.get(k)
        if v is not None:
            return v
    return None


def _price_pick(row: dict, board: dict, mock: dict) -> dict:
    pick_overall = row.get("pick_overall")
    name = row.get("player_name") or ""
    prospect = board.get(_norm_name(name))

    player_key = None
    consensus_fv = None
    efv = None
    mock_pick = None
    board_delta = None
    reach_or_steal = "off board"

    if prospect:
        player_key = prospect.get("player_key")
        consensus_fv = prospect.get("consensus_fv")
        efv = _board_efv(prospect)
        mock_pick = mock.get(player_key)
        cpick = prospect.get("consensus_pick")
        if cpick is not None and pick_overall is not None:
            # board_delta = actual pick minus our board rank. A player who FALLS
            # past his rank (drafted later than we ranked him) is a STEAL for the
            # team that takes him, so positive = steal; drafted earlier than his
            # rank = reach (negative); within the +/- threshold = on board.
            board_delta = int(pick_overall) - int(cpick)
            if board_delta >= _STEAL_REACH_THRESHOLD:
                reach_or_steal = "steal"
            elif board_delta <= -_STEAL_REACH_THRESHOLD:
                reach_or_steal = "reach"
            else:
                reach_or_steal = "on board"
        else:
            reach_or_steal = "on board"

    bonus = row.get("bonus_usd")
    slot = row.get("slot_usd")
    bonus_vs_slot = (bonus - slot) if (bonus is not None and slot is not None) else None

    # Phase 6: implied pick surplus = clemens_2026 tier value for the drafted
    # player's FV/role minus the cost (actual signing bonus if known, else the
    # expected slot). Uses the committed board's FV + role; None when we can't
    # place the player on the board or have no real cost (never guesses a bonus).
    implied_surplus = implied_basis = clemens_tier = None
    if prospect is not None and consensus_fv is not None:
        import valuation_sets as _vs
        _pos = prospect.get("position")
        _pt = str(prospect.get("player_type") or "")
        _is_pit = str(_pos or "").upper() in _PITCHER_POS or _pt.endswith("p")
        _ips = _vs.implied_pick_surplus(consensus_fv, _is_pit, bonus_usd=bonus, slot_usd=slot)
        if _ips:
            implied_surplus, implied_basis, clemens_tier = (
                _ips["surplus_usd"], _ips["basis"], _ips["tier_value_usd"])

    return {
        "pick_overall": pick_overall,
        "round": row.get("round_label"),
        "team": row.get("team"),
        "player_name": name,
        "player_key": player_key,
        "consensus_fv": consensus_fv,
        "efv": efv,
        "mock_pick": mock_pick,
        "board_delta": board_delta,
        "reach_or_steal": reach_or_steal,
        "exp_first6_war": storage._pick_slot_expected_war(pick_overall),
        "exp_surplus_usd": fa_market._slot_surplus_usd(pick_overall)
        if pick_overall is not None else None,
        "signing_bonus_usd": bonus,
        "slot_usd": slot,
        "bonus_vs_slot_usd": bonus_vs_slot,
        "implied_pick_surplus_usd": implied_surplus,
        "implied_pick_surplus_basis": implied_basis,   # 'actual_bonus' | 'expected_slot'
        "clemens_tier_value_usd": clemens_tier,
    }


def _atomic_write(out_path, payload: dict) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + f".tmp.{os.getpid()}")
    tmp.write_text(
        json.dumps(payload, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(tmp, out)  # atomic on the same filesystem


def build_draft_live(year: int, force: bool = True, board_path=None,
                     out_path=None, now_iso: str | None = None) -> dict:
    """Join the live pick feed to the committed board, price each pick, and
    return the artifact dict. Writes it to out_path when out_path is given.

    STRICTLY READ-ONLY toward site state: touches only out_path on disk."""
    if now_iso is None:
        now_iso = datetime.datetime.now().isoformat()
    if board_path is None:
        board_path = _DEFAULT_BOARD

    board, mock = _load_board(board_path, year)

    status = "live"
    rows: list[dict] = []
    try:
        rows = scrapers.scrape_mlb_draft_tracker(year, force=force) or []
    except Exception:
        # Any scrape failure degrades to a valid, empty artifact.
        rows = []
        status = "error"

    picks = [_price_pick(r, board, mock) for r in rows]
    if status != "error" and not picks:
        status = "waiting"

    payload = {
        "generated_at": now_iso,
        "year": year,
        "status": status,
        "pick_count": len(picks),
        "picks": picks,
    }

    if out_path is not None:
        _atomic_write(out_path, payload)
    return payload


if __name__ == "__main__":
    yr = int(sys.argv[1]) if len(sys.argv) > 1 else _current_draft_year()
    build_draft_live(yr, force=True, out_path=_DEFAULT_OUT)
    print(f"draft_live.json written for {yr}")
