# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The Parlays builder labels its postseason legs (QREC01, owner INT-A1).

Owner decision 2026-10-01 (INT-A1): every priced postseason row and card carries
the label "never graded on a postseason game". The Teams cards and Pick of the
Day already did; the Parlays builder priced its legs with no label. A leg in
parlay_context.legs carries a game_pk and no game_type, so renderParlays joins
each leg to its game's team_bets row by game_pk and reads the label there, and
prints one note above the builder whenever any leg is postseason. The model
percentages and prices are unchanged.

The harness is test_betting's (py_mini_racer; skipped without it).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from test_betting import JS, SMOKE_PAYLOAD, _ctx, _fetch_js

ROOT = Path(__file__).resolve().parent
LABEL = "never graded on a postseason game"
NOTE = "Postseason legs: " + LABEL
OPTION_RE = re.compile(r'<option value="(\d+)">(.*?)</option>', re.S)


def _parlay_fn() -> str:
    start = JS.index("function renderParlays(")
    return JS[start:JS.index("function paintParlay(", start)]


def _bet(pk: int, home: str, away: str, game_type: str | None = None) -> dict:
    b = {"game_pk": pk, "date": "2026-10-03", "venue": "Park",
         "home": {"org": home, "probable": None}, "away": {"org": away, "probable": None},
         "model": {"p_home": 0.6, "p_away": 0.4, "fair_total": 8.5},
         "moneyline": [{"side": "home", "label": home, "model_prob": 0.6, "fair_odds": -150},
                       {"side": "away", "label": away, "model_prob": 0.4, "fair_odds": 150}],
         "runline": None, "total": {"line": None, "sides": None, "fair_total": 8.5},
         "market": None}
    if game_type:
        b["game_type"] = game_type
        b["postseason_label"] = LABEL
        b["series"] = "AL Division Series"
    return b


def _leg(pk: int, label: str, prob: float, odds: int) -> dict:
    return {"leg_id": f"{pk}:ml:home", "game_pk": pk, "label": label, "market": "h2h",
            "model_prob": prob, "odds": odds, "book": "book"}


def _render(payload: dict) -> str:
    c = _ctx(_fetch_js(main=json.dumps(payload)))
    return c.eval("__show('parlays')")


def _options(html: str) -> dict:
    return {int(i): txt for i, txt in OPTION_RE.findall(html)}


def test_render_parlays_joins_the_label_by_game_pk():
    src = _parlay_fn()
    assert "function legGame(" in src
    assert "bets[i].game_pk === l.game_pk" in src
    assert "postseasonLabel(legGame(l))" in src
    assert '"<strong>Postseason legs: "' in src


def test_a_postseason_leg_carries_the_label_and_a_regular_leg_does_not():
    d = json.loads(SMOKE_PAYLOAD)
    d["team_bets"] = [_bet(900001, "CLE", "CHW", "D"), _bet(800001, "PHI", "WSN")]
    d["parlay_context"]["legs"] = [_leg(900001, "CLE moneyline", 0.60326, -148),
                                   _leg(800001, "PHI moneyline", 0.62, -163)]
    html = _render(d)
    opts = _options(html)
    assert set(opts) == {0, 1}
    assert opts[0].endswith(" &middot; " + LABEL)
    # The price and the model percentage print exactly as before.
    assert opts[0].startswith("CLE moneyline (-148) &middot; model 60.3%")
    assert LABEL not in opts[1]
    assert opts[1] == "PHI moneyline (-163) &middot; model 62.0%"
    assert html.count(NOTE) == 1
    assert html.index(NOTE) < html.index('id="bt-legsel"')


def test_no_postseason_leg_means_no_note():
    d = json.loads(SMOKE_PAYLOAD)
    d["team_bets"] = [_bet(800001, "PHI", "WSN")]
    d["parlay_context"]["legs"] = [_leg(800001, "PHI moneyline", 0.62, -163)]
    html = _render(d)
    assert "Postseason legs" not in html
    assert LABEL not in html


def test_every_served_postseason_leg_is_labelled():
    path = ROOT / "data" / "betting.json"
    if not path.exists():
        pytest.skip("data/betting.json is not built on this checkout")
    d = json.loads(path.read_text(encoding="utf-8"))
    legs = (d.get("parlay_context") or {}).get("legs") or []
    post = {b.get("game_pk") for b in d.get("team_bets") or []
            if b.get("game_type") and b.get("game_type") != "R"}
    html = _render(d)
    opts = _options(html)
    assert len(opts) == len(legs)
    n_post = 0
    for i, leg in enumerate(legs):
        if leg.get("game_pk") in post:
            n_post += 1
            assert LABEL in opts[i], (i, opts[i])
        else:
            assert LABEL not in opts[i], (i, opts[i])
    assert (html.count("Postseason legs: ") == 1) == (n_post > 0)
