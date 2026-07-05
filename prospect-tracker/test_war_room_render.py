"""Draft War Room render guard. Writes a synthetic data/draft_live.json (the
artifact the draft-night poller produces), loads the prospx War Room sub-view,
and asserts it renders the priced pick board with a steal label and no JS
errors. The fixture is removed afterward so the feature stays dark (no artifact)
by default. Skips where playwright/chromium is unavailable.
"""
import os
import json
import functools
import http.server
import socketserver
import threading

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
ARTIFACT = os.path.join(ROOT, "data", "draft_live.json")

_LIVE = {
    "generated_at": "2026-07-13T20:00:00", "year": 2026, "status": "live",
    "pick_count": 2,
    "picks": [
        {"pick_overall": 25, "round": "1", "team": "SFG",
         "player_name": "Board Faller", "player_key": "draft_2026_x",
         "consensus_fv": 55, "efv": None, "mock_pick": 3, "board_delta": 22,
         "reach_or_steal": "steal", "exp_first6_war": 6.1,
         "exp_surplus_usd": 40_000_000, "signing_bonus_usd": 4_000_000,
         "slot_usd": 3_100_000, "bonus_vs_slot_usd": 900_000},
        {"pick_overall": 30, "round": "1", "team": "NYY",
         "player_name": "Unknown Name", "player_key": None,
         "consensus_fv": None, "efv": None, "mock_pick": None,
         "board_delta": None, "reach_or_steal": "off board",
         "exp_first6_war": 3.0, "exp_surplus_usd": 18_000_000,
         "signing_bonus_usd": 3_000_000, "slot_usd": 3_200_000,
         "bonus_vs_slot_usd": -200_000},
    ],
}


@pytest.fixture()
def live_artifact():
    had = os.path.exists(ARTIFACT)
    backup = open(ARTIFACT, encoding="utf-8").read() if had else None
    with open(ARTIFACT, "w", encoding="utf-8") as f:
        json.dump(_LIVE, f, indent=1)
    try:
        yield
    finally:
        if backup is not None:
            open(ARTIFACT, "w", encoding="utf-8").write(backup)
        elif os.path.exists(ARTIFACT):
            os.remove(ARTIFACT)


def _serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def test_war_room_renders_live_board(live_artifact):
    httpd, port = _serve()
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch()
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"chromium unavailable: {e}")
            page = browser.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/prospx/index.html#tab=draft&dview=war-room",
                      wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(3500)
            info = page.evaluate("""() => ({
              view: (typeof state!=='undefined') ? state.draftView : '?',
              wrStatus: (typeof _warRoom!=='undefined' && _warRoom.data) ? _warRoom.data.status : null,
              hasTitle: document.body.innerText.includes('Draft War Room'),
              hasSteal: document.body.innerText.toLowerCase().includes('steal'),
              hasOffBoard: document.body.innerText.toLowerCase().includes('off board'),
              rows: document.querySelectorAll('.detail-table tbody tr').length,
            })""")
            browser.close()
            assert info["view"] == "war-room"
            assert info["wrStatus"] == "live"
            assert info["hasTitle"], "War Room title missing"
            assert info["rows"] >= 2, f"expected priced pick rows, got {info['rows']}"
            assert info["hasSteal"], "steal label missing"
            assert info["hasOffBoard"], "off-board label missing"
            assert not errs, f"page errors: {errs[:3]}"
    finally:
        httpd.shutdown()
