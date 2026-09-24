# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""An IL stint ends when the transaction feed shows the player back or gone.

WHY THIS EXISTS (census M02-03, 2026-09-24, four verifiers CONFIRMED or PARTLY).
fetch_il_status walked SC (status change) rows only, so a stint ended only on an
activation row. MiLB returns very often emit none: the club reassigns the player
("assigned to Portland Sea Dogs from Greenville Drive") or releases him. The served
IL carried Kai Roberts on a 7-day stint from 2025-04-04 with 110 games in 2026, and
the stale flag reached the IL tab, the injury chip, the healthy filter, the farm IL
counts, the tiebreak drag and the ETA health push.

The fixtures below are the real transaction rows (MLB Stats API shape) of the
players the verifiers named, trimmed to the rows that matter.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import stats


def _tx(tid, d, code, desc, eff=None, frm=None, to=None):
    row = {"id": tid, "date": d, "effectiveDate": eff or d, "typeCode": code,
           "description": desc}
    if to is not None:
        row["toTeam"] = {"id": to, "name": "to club"}
    if frm is not None:
        row["fromTeam"] = {"id": frm, "name": "from club"}
    return row


def _norm(d, code, desc, frm=None):
    """A normalized player_transactions row as stored before 2026-09-24 (no id)."""
    return {"date": d, "type_code": code, "description": desc,
            "from_team_id": frm, "from_team_name": "", "to_team_id": 1,
            "to_team_name": ""}


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


@pytest.fixture
def feed(monkeypatch):
    """Point fetch_il_status at an in-memory transaction list."""
    holder = {"games": []}

    def _get(url, **kw):
        if "gameLog" in url:
            if "group=hitting" not in url:
                return _Resp({"stats": []})
            splits = [{"date": d, "team": {"id": club}} for d, club in holder["games"]]
            return _Resp({"stats": [{"splits": splits}]})
        return _Resp({"transactions": holder["txs"]})

    monkeypatch.setattr(stats.requests, "get", _get)

    def _set(txs, games=()):
        holder["txs"] = txs
        holder["games"] = list(games)
        return stats.fetch_il_status(1)
    return _set


KAI = [
    _tx(1, "2025-04-04", "SC", "Lake Elsinore Storm placed OF Kai Roberts on the 7-day injured list."),
    _tx(2, "2025-05-03", "ASG", "Lake Elsinore Storm sent OF Kai Roberts on a rehab assignment to ACL Padres.", frm=103),
    _tx(3, "2025-05-20", "ASG", "OF Kai Roberts assigned to Fort Wayne TinCaps from Lake Elsinore Storm.", frm=103),
]


def test_reassignment_after_rehab_ends_the_stint(feed):
    assert feed(KAI) is None
    stints = stats.derive_injury_history(KAI)
    assert len(stints) == 1
    assert stints[0]["active"] is False
    assert stints[0]["until"] == "2025-05-20"
    assert stints[0]["days"] == 46


def test_rehab_alone_keeps_the_stint_open(feed):
    rec = feed(KAI[:2])
    assert rec and rec["is_on_il"] and rec["since"] == "2025-04-04"
    assert stats.derive_injury_history(KAI[:2])[0]["active"] is True


def test_rehab_then_reassignment_ends_the_stint(feed):
    # Aidan Miller: placed 2026-03-27, rehab at Clearwater 09-05, then
    # reassigned to Reading 09-08 and played AA games after it.
    txs = [
        _tx(10, "2026-03-27", "SC", "Lehigh Valley IronPigs placed SS Aidan Miller on the 7-day injured list."),
        _tx(11, "2026-09-05", "ASG", "Lehigh Valley IronPigs sent SS Aidan Miller on a rehab assignment to Clearwater Threshers.", frm=1410),
        _tx(12, "2026-09-08", "ASG", "SS Aidan Miller assigned to Reading Fightin Phils from Lehigh Valley IronPigs.", frm=1410),
    ]
    assert feed(txs) is None
    assert feed(txs[:2])["since"] == "2026-03-27"


@pytest.mark.parametrize("code,desc", [
    ("REL", "Daytona Tortugas released RHP Dalvin Rosario."),
    ("RET", "RHP Davis Sharpe retired."),
    ("DFA", "RHP Some Player elected free agency."),
])
def test_release_retirement_or_free_agency_ends_the_stint(feed, code, desc):
    txs = [_tx(20, "2025-04-26", "SC", "Daytona Tortugas placed RHP Dalvin Rosario on the 7-day injured list."),
           _tx(21, "2025-08-13", code, desc)]
    assert feed(txs) is None
    assert stats.derive_injury_history(txs)[0]["until"] == "2025-08-13"


@pytest.mark.parametrize("pos", ["1B", "2B", "3B", "OF", "RHP"])
def test_bare_activation_with_any_position_token_ends_the_stint(feed, pos):
    txs = [_tx(30, "2025-07-08", "SC", f"Fresno Grizzlies placed {pos} Tommy Hopfe on the 7-day injured list."),
           _tx(31, "2025-07-22", "SC", f"Spokane Indians activated {pos} Tommy Hopfe.")]
    assert feed(txs) is None


def test_bare_activation_without_an_open_stint_is_ignored(feed):
    txs = [_tx(40, "2025-03-06", "SC", "activated CF Kai Roberts."),
           _tx(41, "2025-04-04", "SC", "Lake Elsinore Storm placed OF Kai Roberts on the 7-day injured list.")]
    assert feed(txs)["since"] == "2025-04-04"


def test_backdated_placement_is_sequenced_and_dated_by_effective_date(feed):
    # Zac Leigh: the placement row's date is his 06-26 arrival at Iowa, its
    # effectiveDate 07-30 is the real placement (he pitched through 07-28).
    txs = [
        _tx(933442, "2026-06-26", "SC", "Iowa Cubs placed RHP Zac Leigh on the 7-day injured list.", eff="2026-07-30"),
        _tx(922889, "2026-06-26", "ASG", "RHP Zac Leigh assigned to Iowa Cubs from ACL Cubs.", frm=408),
        _tx(933861, "2026-07-31", "SC", "Iowa Cubs transferred RHP Zac Leigh from the 7-day injured list to the 60-day injured list."),
    ]
    rec = feed(txs)
    assert rec["since"] == "2026-07-30"
    assert rec["type"] == "60-day"


def test_backdated_placement_after_same_day_activation_stays_open(feed):
    # Luis Hernandez: "activated" (936439) and "placed" (940736, effective
    # 09-01) share date 07-24; the placement was entered later.
    txs = [
        _tx(936439, "2026-07-24", "SC", "San Jose Giants activated SS Luis Hernandez."),
        _tx(940736, "2026-07-24", "SC", "San Jose Giants placed SS Luis Hernandez on the 7-day injured list.", eff="2026-09-01"),
        _tx(931068, "2026-07-24", "ASG", "SS Luis Hernandez assigned to San Jose Giants from ACL Giants.", frm=408),
    ]
    rec = feed(txs)
    assert rec and rec["since"] == "2026-09-01"


def test_same_day_reassignment_entered_after_the_placement_ends_it(feed):
    # Will Gagnon: placed by Ontario (937296) then reassigned to Great Lakes
    # (937547) the same day; he pitched for Great Lakes from 08-14.
    txs = [
        _tx(937296, "2026-08-12", "SC", "Ontario Tower Buzzers placed RHP Will Gagnon on the 7-day injured list."),
        _tx(937547, "2026-08-12", "ASG", "RHP Will Gagnon assigned to Great Lakes Loons from Ontario Tower Buzzers.", frm=526),
    ]
    assert feed(txs) is None


def test_same_day_arrival_entered_before_the_placement_keeps_it(feed):
    txs = [
        _tx(936599, "2026-08-09", "ASG", "SS Bryan Gonzalez Garcia assigned to Ontario Tower Buzzers from ACL Dodgers.", frm=408),
        _tx(941495, "2026-08-09", "SC", "Ontario Tower Buzzers placed C Bryan Gonzalez Garcia on the 7-day injured list.", eff="2026-09-06"),
    ]
    assert feed(txs)["since"] == "2026-09-06"


def test_normalized_rows_without_ids_need_a_later_date():
    # Stored rows written before the id field existed: a same-day
    # reassignment cannot be ordered against the placement, so it must not
    # clear it; a later one does.
    place = _norm("2026-08-12", "SC", "Ontario Tower Buzzers placed RHP Will Gagnon on the 7-day injured list.")
    same = _norm("2026-08-12", "ASG", "RHP Will Gagnon assigned to Great Lakes Loons from Ontario Tower Buzzers.", frm=526)
    later = _norm("2026-08-20", "ASG", "RHP Will Gagnon assigned to Great Lakes Loons from Ontario Tower Buzzers.", frm=526)
    assert stats.derive_injury_history([place, same])[-1]["active"] is True
    assert stats.derive_injury_history([place, later])[-1]["active"] is False


def test_assignment_without_a_from_club_does_not_end_the_stint(feed):
    # Spring and organization-level assignments ("assigned to San Diego
    # Padres.") carry no from-club and say nothing about health.
    txs = [_tx(50, "2026-03-27", "SC", "Lehigh Valley IronPigs placed SS Aidan Miller on the 7-day injured list."),
           _tx(51, "2026-04-10", "ASG", "SS Aidan Miller assigned to Philadelphia Phillies Prospects.")]
    assert feed(txs)["since"] == "2026-03-27"


def test_explicit_activation_and_new_placement_still_work(feed):
    txs = [
        _tx(60, "2025-08-17", "SC", "Greenville Drive placed SS Henry Godbout on the 7-day injured list."),
        _tx(61, "2025-08-28", "SC", "Greenville Drive activated SS Henry Godbout from the 7-day injured list."),
        _tx(62, "2026-06-02", "SC", "Greenville Drive placed SS Henry Godbout on the 7-day injured list."),
        _tx(63, "2026-06-08", "SC", "Greenville Drive transferred SS Henry Godbout from the 7-day injured list to the 60-day injured list."),
    ]
    rec = feed(txs)
    assert rec["since"] == "2026-06-02" and rec["type"] == "60-day"
    txs.append(_tx(64, "2026-07-31", "ASG", "Greenville Drive sent SS Henry Godbout on a rehab assignment to Salem RidgeYaks.", frm=428))
    assert feed(txs)["since"] == "2026-06-02"
    txs.append(_tx(65, "2026-08-11", "ASG", "SS Henry Godbout assigned to Portland Sea Dogs from Greenville Drive.", frm=428))
    assert feed(txs) is None
    hist = stats.derive_injury_history(txs)
    assert [s["active"] for s in hist] == [False, False]
    assert hist[0]["days"] == 11 and hist[1]["until"] == "2026-08-11"


def test_a_game_for_the_placing_club_ends_the_stint(feed):
    # Tate Kuehner: Nashville (556) placed him 05-21 (backdated to 2025-05-22)
    # and moved him to the 60-day; he pitched for Nashville again from 08-16
    # with no activation row.
    txs = [
        _tx(910832, "2025-05-22", "SC", "Nashville Sounds placed LHP Tate Kuehner on the 7-day injured list.", eff="2026-05-21", to=556),
        _tx(924108, "2026-06-29", "SC", "Nashville Sounds transferred LHP Tate Kuehner from the 7-day injured list to the 60-day injured list.", to=556),
    ]
    assert feed(txs, games=[("2026-05-20", 556)])["since"] == "2026-05-21"
    assert feed(txs, games=[("2026-05-20", 556), ("2026-08-16", 556)]) is None


def test_rehab_games_for_another_club_keep_the_stint(feed):
    # Boston Baro: Brooklyn (453) placed him; his games after it are rehab
    # games for FCL Mets (468) and St. Lucie (507).
    txs = [
        _tx(892353, "2026-03-18", "SC", "Brooklyn Cyclones placed SS Boston Baro on the 60-day injured list.", to=453),
        _tx(910792, "2026-05-21", "ASG", "Brooklyn Cyclones sent SS Boston Baro on a rehab assignment to FCL Mets.", frm=453),
    ]
    rec = feed(txs, games=[("2026-05-21", 468), ("2026-08-22", 507)])
    assert rec and rec["since"] == "2026-03-18"


# ---------------------------------------------------------------------------
# Served artifact invariant. data/timeseries.json is regenerated nightly and
# gitignored, so the check skips when it is absent.
# ---------------------------------------------------------------------------

_TS = Path(__file__).parent / "data" / "timeseries.json"


def test_served_il_rows_have_no_exit_after_the_placement():
    if not _TS.exists():
        pytest.skip("data/timeseries.json not built")
    ts = json.loads(_TS.read_text(encoding="utf-8"))
    bad = []
    for p in ts.get("players") or []:
        il = p.get("il_status") or {}
        if not il.get("is_on_il"):
            continue
        since = il.get("since") or ""
        for t in p.get("transactions") or []:
            if (t.get("type_code") or "").upper() in ("REL", "RET", "DFA") \
                    and (t.get("date") or "") > since:
                bad.append((p["player_key"], since, t.get("date"), t.get("type_code")))
    assert not bad, f"{len(bad)} on-IL rows released or retired after the placement: {bad[:5]}"
