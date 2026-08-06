# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV movement alerts - the DATA FEED (data/efv_alerts.json).

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
/diamond/ advertised "eFV movement alerts" as a member benefit and nothing in
the tree produced them. This module produces the FEED: the top absolute board
eFV movers on a rebuild, with the driving explainer where the movement engine
has one. It does NOT deliver anything. Delivery (per-user watchlists, email or
push) needs the dormant account layer (assets/eephus-account.js runs fully
inert without assets/eephus-config.js), so the artifact stamps
`delivery: "not_wired"` and the page says so in those words. An unbacked claim
is exactly what this lane exists to retire; replacing it with a quieter
unbacked claim would be the same defect in a smaller font.

WHY IT READS THE SERVED `stock` BLOCK AND RECOMPUTES NOTHING
-------------------------------------------------------------
Every row here is copied off `players[].stock`, the movement block
storage.py already publishes into data/timeseries.json. That block is
movement.compute_genuine_movement with movement.xfv_movement's eFV "since last
real change" step layered on top, and it is already gated by
storage.xfv_history_is_on_board_basis() so a grade-scale transition cannot
publish itself as player movement.

Recomputing the delta here would have meant a SECOND grade chain. That exact
mistake cost /ifa/ a +12.3 FV error (fixed 2026-08-05), so the board grade on
each row comes from the caller's canonical map (build_site._load_xfv_grades,
which is efv_board_scale.board_value over data/xfv.json - one of the four
readers efv_board_scale names as THE board grade) and the move itself comes
from the engine. Nothing in this file does grade arithmetic.

The "is this a move" gate is likewise injected, not copied: build_site passes
`_genuine_mover_step`, the same selector the homepage Top Movers module uses.
One definition of a move for the site and the feed, so an alert can never fire
on something the board does not call a move.

THE FLOOR-TRANSITION PROBLEM (measured 2026-08-05, and it is not cosmetic)
---------------------------------------------------------------------------
On the live board, 316 of the 617 gated movers had an eFV 20.0 endpoint, and
312 of the 322 double-digit movers did. eFV 20.0 is the model's floor, so those
rows are a player entering or leaving the graded pool, not a re-grade of a
graded player.

Ranking the feed purely on absolute delta was the obvious first cut and it was
WRONG, measurably: the top 100 came back 100 of 100 floor transitions. Not one
re-grade survived the cut, so a reader following a graded prospect who moved
+3 would never once have seen him in a feed named "eFV movement alerts". A
headline list that is 100 percent one event type is a broken sample no matter
how defensible the sort key is.

Two fixes were available and only one of them is honest. Filtering the floor
rows out would put a second selection rule beside the board's own, so the feed
and the board would disagree about who moved. Instead the limit is SHARED: at
most FLOOR_SHARE_MAX of the slots go to floor transitions, the rest to
re-grades, each class ranked by absolute delta on its own, and the merged set
presented in delta order. Nothing is hidden and nothing is reweighted; a quota
on a headline list is a presentation choice, and both classes are counted in
the meta block. Every row still carries `at_floor` so a consumer can split them
again with one predicate.

SILENT-EMPTY POSTURE
--------------------
A movers feed that publishes zero movers reads downstream as "nothing moved",
which is indistinguishable from "the join broke" - the defect class that dark
started four surfaces on 2026-08-05. So the write path goes through
bullpen_export.guard_nonempty_block: an empty list never replaces a populated
one, the prior artifact is kept and stamped stale, and the failure is filed in
the ingest-health RED ledger. The guard is imported, not reimplemented.

Not a standalone script by design: it is a derived view of artifacts the
pipeline has already written, so it runs on the rebuild (build_site.main), the
same seam as data/positional_fit_ui.json and data/mlb_current_lines.json.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "efv_alerts.json"

_log = logging.getLogger(__name__)

# How many movers the feed carries. The gate admits ~600 rows on a live board;
# an alerts feed is a headline surface, not a mirror of the board, and 100 rows
# keeps the artifact small enough to fetch on a phone. Consumers that want the
# full set already have data/timeseries.json.
ALERT_LIMIT = 100

# Drivers per row. movement.py already caps the engine's list at
# MAX_DRIVERS_PER_CARD for the player card; an alert line has room for the
# cause and one corroborating detail, not five.
MAX_DRIVERS = 2

# The model's grade floor. A move with this endpoint is a pool entry or exit
# (see the floor-transition note above), which is a different event from a
# re-grade even though the board reports both as movement.
EFV_FLOOR = 20.0

# Ceiling on the share of the feed floor transitions may take. Half, because
# both event types are real movement and neither deserves to be the whole list:
# on the measured board an uncapped delta sort gave floor transitions 100 of 100
# slots, and a cap the other way (excluding them) would hide the single largest
# thing the model did that night. Slots a short class cannot fill go to the
# other one, so a quiet week for either still fills the feed.
FLOOR_SHARE_MAX = 0.5

# Fields copied verbatim off the served `stock` block. Listed rather than
# splatted so a future engine field cannot silently widen the public schema.
_STOCK_FIELDS = ("direction", "delta", "basis", "confidence", "strength",
                 "from_label", "to_label", "from_date", "to_date")


def _num(v):
    return float(v) if isinstance(v, (int, float)) else None


def _at_floor(stock: dict) -> bool:
    """True when either endpoint of the move sits on the eFV floor.

    Read off the engine's own endpoint LABELS ("eFV 47.7" / "eFV 20.0") rather
    than re-derived from a grade, so this flag can never disagree with the move
    it is describing. A label the engine did not format ("- ") simply fails the
    parse and the row reports False, which is the honest answer for a row whose
    endpoints are unknown."""
    for label in (stock.get("from_label"), stock.get("to_label")):
        text = str(label or "").replace("eFV", "").strip()
        try:
            if abs(float(text) - EFV_FLOOR) < 0.05:
                return True
        except ValueError:
            continue
    return False


def _driver_rows(stock: dict) -> list:
    """The engine's explainer chips, trimmed to the fields an alert needs.

    The engine's driver dicts carry per-stat plumbing (baseline_label, stat,
    current) that a card renders and an alert does not, and several of those
    fields are None on the live artifact. Carrying the whole dict would put
    nulls in a documented public schema."""
    out = []
    for d in (stock.get("drivers") or [])[:MAX_DRIVERS]:
        if not isinstance(d, dict) or not d.get("label"):
            continue
        row = {"label": d["label"], "valence": d.get("valence") or "neutral"}
        if d.get("tooltip"):
            row["tooltip"] = d["tooltip"]
        out.append(row)
    return out


def build_alerts(players: list, *, mover_step, board_grades: dict | None = None,
                 limit: int = ALERT_LIMIT) -> list:
    """The mover rows, biggest absolute eFV move first.

    `mover_step` is the caller's gate (build_site._genuine_mover_step): it
    returns the signed integer grade step for a genuine, recent move and None
    for everything else. Injecting it keeps ONE definition of "a move" for the
    homepage module, the board and this feed.

    `board_grades` is {player_key: board eFV grade} from the caller's canonical
    map. It can lag the movement endpoints by one run (data/xfv.json and
    data/xfv_history.json are written by different pipeline steps), which is
    why `to_label` is carried alongside rather than replaced by it."""
    grades = board_grades or {}
    rows = []
    for p in players or []:
        stock = p.get("stock") or {}
        try:
            step = mover_step(p)
        except Exception:                  # noqa: BLE001 - one bad row never kills the feed
            _log.debug("mover gate raised for %s", p.get("player_key"), exc_info=True)
            continue
        if step is None:
            continue
        delta = _num(stock.get("delta"))
        if delta is None:
            continue
        key = p.get("player_key")
        row = {
            "player_key": key,
            "name": p.get("player_name") or "",
            "org": p.get("org") or "",
            "position": p.get("position") or "",
            "level": p.get("current_level") or "",
            "status": p.get("status") or "",
            "overall_rank": p.get("overall_rank"),
            # The DISPLAYED step, identical to the number the homepage movers
            # module prints for the same player (the gate rounds it half-up).
            "step": step,
            # The raw engine delta. eFV is not a scouting FV, so it rounds to
            # NEAREST, never up (repo rule: ceiling is for FV and tool grades).
            "delta": round(delta, 2),
            "board_grade": grades.get(key),
            "at_floor": _at_floor(stock),
            "href": f"/prospx/#player={key}" if key else "/prospx/",
            "drivers": _driver_rows(stock),
        }
        for f in _STOCK_FIELDS:
            if f == "delta":
                continue
            if stock.get(f) is not None:
                row[f] = stock[f]
        rows.append(row)
    rows.sort(key=_rank_key)
    if not limit or len(rows) <= limit:
        return rows
    # SHARED LIMIT. Rank each class on its own and give floor transitions no
    # more than FLOOR_SHARE_MAX of the slots (see the module docstring for the
    # measurement that forced this). Whatever one class cannot fill goes to the
    # other, so the feed is always `limit` long while it has the candidates.
    floor = [r for r in rows if r["at_floor"]]
    regrade = [r for r in rows if not r["at_floor"]]
    floor_slots = min(len(floor), int(limit * FLOOR_SHARE_MAX))
    regrade_slots = min(len(regrade), limit - floor_slots)
    floor_slots = min(len(floor), limit - regrade_slots)
    merged = regrade[:regrade_slots] + floor[:floor_slots]
    merged.sort(key=_rank_key)
    return merged


def _rank_key(r: dict):
    """Biggest absolute move first. `overall_rank` breaks a delta tie toward
    the better prospect and the name settles the rest, so the order is stable
    across runs on identical input (a feed that reshuffles itself looks like
    movement that did not happen)."""
    return (-abs(r["delta"]), -abs(r["step"]),
            r["overall_rank"] if r.get("overall_rank") else 10 ** 6,
            r["name"])


def build_payload(players: list, *, mover_step, board_grades: dict | None = None,
                  source_as_of: str | None = None, limit: int = ALERT_LIMIT) -> dict:
    """The full artifact, guard applied. Returns the dict to serve.

    Callers write the return value as-is. The guard runs HERE rather than in
    the caller so the refuse-to-publish-empty decision and the artifact it
    protects can never be separated by a refactor."""
    alerts = build_alerts(players, mover_step=mover_step,
                          board_grades=board_grades, limit=limit)
    served, guard_meta = _guard(alerts)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    n_floor = sum(1 for r in served if r.get("at_floor"))
    return {
        "generated_at": now,
        # Vintage of the board this feed was cut from, so a reader can tell a
        # stale feed from a quiet week without diffing two files.
        "as_of": source_as_of or now,
        "basis": "efv_board_delta",
        # DELIVERY IS NOT WIRED. The account layer is inert without
        # assets/eephus-config.js, so there is no per-user watchlist to fan
        # these out to. Stamped in the artifact, not only in the copy, so a
        # consumer reading the JSON alone cannot mistake this for a live alert
        # stream.
        "delivery": "not_wired",
        "delivery_note": ("This is the feed only. Per-user watchlists and "
                          "delivery need the account layer, which is dormant. "
                          "Nothing is emailed or pushed from this artifact."),
        "n_alerts": len(served),
        "n_up": sum(1 for r in served if r.get("direction", "").startswith("up")),
        "n_down": sum(1 for r in served if r.get("direction", "").startswith("down")),
        # See the floor-transition note in the module docstring: a row with an
        # eFV 20.0 endpoint is a pool entry or exit, not a re-grade, and on the
        # live board those dominate the double-digit moves. Both counts are
        # published so a consumer can see the mix without recomputing it.
        "n_at_floor": n_floor,
        "n_regrade": len(served) - n_floor,
        "floor_note": (f"{n_floor} of {len(served)} rows have an eFV "
                       f"{EFV_FLOOR:g} endpoint, which is the model floor: the "
                       "player entered or left the graded pool rather than "
                       "being re-graded. Those two event types share the feed "
                       f"(floor transitions are capped at "
                       f"{int(FLOOR_SHARE_MAX * 100)} percent of the slots) "
                       "because ranking on absolute move alone gave them every "
                       "slot. Filter on at_floor to split them again."),
        "limit": limit,
        "guard": guard_meta,
        "alerts": served,
    }


def _guard(alerts: list) -> tuple[list, dict]:
    """Refuse to publish an empty feed over a populated one.

    Delegates to bullpen_export.guard_nonempty_block, the sanctioned template
    (2026-08-05): keep the prior block, stamp it stale with the vintage being
    served, and file the failure RED so the deploy shell prints it on the same
    run. Imported lazily and best-effort for the same reason _ingest_red is
    best-effort: the reporting path must never be the reason a rebuild fails.
    If the import itself is unavailable the empty-refusal still holds - the
    prior artifact is simply left in place, which is the same served outcome
    without the health ledger entry."""
    if alerts:
        return alerts, {"key": "alerts", "n": len(alerts), "stale": False}
    try:
        from bullpen_export import guard_nonempty_block
    except Exception:                      # noqa: BLE001 - degrade, never fail the build
        _log.error("efv_alerts: 0 movers and bullpen_export.guard_nonempty_block "
                   "is unavailable; keeping whatever artifact is on disk")
        prev = _prev_alerts()
        return prev, {"key": "alerts", "n": len(prev), "stale": bool(prev),
                      "reason": "0 movers this run; guard module unavailable"}
    return guard_nonempty_block(
        alerts, OUT_PATH, key="alerts", source="efv_alerts",
        label="eFV movement alerts")


def _prev_alerts() -> list:
    try:
        doc = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except Exception:                      # noqa: BLE001 - missing/corrupt prior == no prior
        return []
    block = doc.get("alerts") if isinstance(doc, dict) else None
    return block if isinstance(block, list) else []
