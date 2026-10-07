# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""/projections/ display pass (DISPLAY_projections, 2026-10-07).

One pin per surface-quality finding the pass closed. Copy and markup run
through the MiniRacer harness of test_projections_smoke.py with fixture rows
of their own; keyboard reach and request counts run in headless Chromium on
the served page (they skip when the served artifacts are not built).
"""
from __future__ import annotations

import contextlib
import json
import re

import pytest

import test_projections_smoke as S

JS = S.JS


def _render_with(players: dict, hash_: str) -> str:
    """Render one hash with the smoke fixture's players plus `players`."""
    base = json.loads(S.DETAIL)
    base["players"].update(players)
    saved = S.DETAIL
    S.DETAIL = json.dumps(base)
    try:
        return S._render(hash_)
    finally:
        S.DETAIL = saved


SOTO_LIKE = {
    "key": "soto_like", "name": "Soto Like", "pos": "LF", "age": 28.0, "team": "NYM",
    "mlbam": 665742, "isPit": False,
    "career": [{"y": 2026, "pa": 482, "avg": ".275", "obp": ".393", "slg": ".515",
                "ops": ".908", "hr": 27, "sb": 9, "bbPct": 16.2, "kPct": 20, "iso": 0.24,
                "war": 3.0},
               {"y": 2022, "pa": 664, "avg": ".242", "obp": ".401", "slg": ".452",
                "ops": ".853", "hr": 27, "sb": 6, "bbPct": 16, "kPct": 14.5, "iso": 0.21,
                "war": 5.5}],
    "sc": {"season": 2026, "metrics": [
        {"label": "xwOBA", "value": "0.411", "pct": 98},
        {"label": "Luck (xwOBA-wOBA)", "value": "+0.031", "pct": 81}]},
    "skills": {"hem": {"season": 2026, "hemPlus": 142, "xhemPlus": 150, "wrcPlus": 150,
                       "qualified": True, "pa": 482}},
}
SKENES_LIKE = {
    "key": "skenes_like", "name": "Skenes Like", "pos": "SP", "age": 24.0, "team": "PIT",
    "mlbam": 694973, "isPit": True,
    "career": [{"y": 2026, "ip": "174.1", "era": 3.82, "kPct": 28.1, "bbPct": 7, "war": 4.1}],
    "arsenal": [{"pitch": "4-Seam Fastball", "usage": 40.8, "rv100": 0.4, "whiff": 29.7, "ba": 0.22},
                {"pitch": "Sweeper", "usage": 15.9, "rv100": 1.0, "whiff": 28.6, "ba": 0.162}],
    "skills": {"pitch": {"kind": "sp", "season": 2026, "role": "Ace", "ip": 174.333,
                         "semPlus": 120, "xsemPlus": 118, "gs": 30, "ipPerGs": 5.8}},
}


# ---------------------------------------------------------------------------
# Copy (QMLC02, QMLC05, QMLC06, QMLC13)
# ---------------------------------------------------------------------------
def test_offense_index_names_the_pool_its_anchor_is_built_on():
    """QMLC02: HEM+ is anchored on the PA-weighted 50+ PA pool
    (hem_plus.POOL_MIN_PA), not the 200 PA qualified set."""
    import hem_plus
    assert hem_plus.POOL_MIN_PA == 50.0
    idx = S._section(_render_with({"soto_like": SOTO_LIKE}, "#player=soto_like&ptab=hitting"),
                     "hitting-index")
    assert "100 = PA-weighted average of 50+ PA hitters" in idx
    assert "qualified hitter" not in idx


def test_statcast_percentiles_name_the_savant_pools():
    """QMLC02: the Savant pulls are min=25 batted balls (contact) and an
    unfloored expected-stats board; no card string calls either qualified."""
    import mlb_player_export as mpe
    assert "min=25" in mpe.LB["statcast"]
    sc = S._section(_render_with({"soto_like": SOTO_LIKE}, "#player=soto_like&ptab=hitting"),
                    "hitting-statcast")
    assert "25+ batted balls" in sc
    assert "qualified" not in sc.lower()
    assert "qualified MLB pool" not in JS


def test_run_prevention_innings_use_the_season_line_notation():
    """QMLC05: decimal 174.333 innings print as 174.1, the notation the
    season lines on the same card use."""
    html = _render_with({"skenes_like": SKENES_LIKE}, "#player=skenes_like&ptab=pitching")
    idx = S._section(html, "pitching-index")
    assert "174.1 IP" in idx and "174.3" not in idx
    assert "one and two outs" in html, "the IP header states the notation"


def test_season_lines_and_arsenal_keep_fixed_decimals():
    """QMLC06: ISO and BA against print three places with no leading zero,
    K% and BB% one place."""
    hit = _render_with({"soto_like": SOTO_LIKE}, "#player=soto_like&ptab=hitting")
    assert ">.240<" in hit and ">.210<" in hit
    assert ">.24<" not in hit and ">.21<" not in hit
    assert ">16.0%<" in hit and ">20.0%<" in hit
    pit = _render_with({"skenes_like": SKENES_LIKE}, "#player=skenes_like&ptab=pitching")
    ars = S._section(pit, "pitching-arsenal")
    assert ">.220<" in ars and ">.162<" in ars and "0.22" not in ars
    assert ">7.0%<" in pit


def test_accountability_legend_items_are_separated_and_baselines_named():
    """QMLC13: the four verdict items read as a list, and the coverage
    baseline column is not a second 'Baseline'."""
    assert "Baseline cov.</th>" in JS
    assert re.search(r'\.filter\(Boolean\)\.join\(`<span class="fa-sub" aria-hidden="true"> &middot; </span>`\)', JS)


# ---------------------------------------------------------------------------
# Keyboard (QMLA06, QMLA07, QMLA12): markup pins, then the browser
# ---------------------------------------------------------------------------
def test_scatter_dots_are_pointer_only_and_axis_pickers_are_named():
    assert '<a href="${href}" tabindex="-1"><circle' in JS
    assert 'aria-label="${name}"' in JS
    assert '_axSel("proj-sy", state.sy, "Y axis")' in JS and '_axSel("proj-sx", state.sx, "X axis")' in JS


@pytest.fixture(scope="module")
def server():
    from conftest import serve_site
    with serve_site() as base:
        yield base


@contextlib.contextmanager
def _page(server, hash_="", w=1280, h=900, wait="table.proj-board-table tbody tr[data-key]"):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    if S.ROOT.joinpath("data", "mlb_projections.json").exists() is False:
        pytest.skip("data/mlb_projections.json not built")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": w, "height": h})
            page._requests = []
            page.on("request", lambda r: page._requests.append(r.url))
            page.goto(server + "projections/" + hash_, wait_until="networkidle", timeout=60_000)
            page.wait_for_selector(wait, timeout=30_000)
            page.wait_for_timeout(300)
            yield page
        finally:
            browser.close()


def test_board_keyboard_reach(server):
    """QMLA06: Enter on a compare button leaves focus on that button.
    QMLA07: an open scatter adds no tab stop. QMLA12: both axis pickers have
    a name."""
    with _page(server) as page:
        btn = page.query_selector("button.proj-cmp-btn")
        key = btn.get_attribute("data-cmp-key")
        btn.focus()
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        assert page.evaluate("document.activeElement.dataset.cmpKey") == key
        info = page.evaluate("""() => {
          const d = document.querySelector('details.proj-warmap'); d.open = true;
          const dots = [...d.querySelectorAll('svg a')];
          const nm = id => { const e = document.getElementById(id);
            return (e.labels ? e.labels.length : 0) + (e.getAttribute('aria-label') ? 1 : 0); };
          return {dots: dots.length, stops: dots.filter(a => a.tabIndex >= 0).length,
                  sy: nm('proj-sy'), sx: nm('proj-sx')};
        }""")
        assert info["dots"] > 100 and info["stops"] == 0
        assert info["sy"] >= 1 and info["sx"] >= 1


# ---------------------------------------------------------------------------
# Luck sign (QMLC03), accountability disclosures (QMLC01, QMLC08, QMLC12)
# ---------------------------------------------------------------------------
def test_card_luck_is_xwoba_minus_woba_like_the_glossary_and_mlbstats(monkeypatch):
    """QMLC03: Soto read -0.026 on the card and +0.026 on /mlbstats/. The
    card now computes the glossary's sign (xwOBA minus wOBA)."""
    import mlb_player_export as mpe
    ex = [{"player_id": "1", "woba": "0.380", "est_woba": "0.411", "est_ba": ".290", "est_slg": ".570"},
          {"player_id": "2", "woba": "0.330", "est_woba": "0.320", "est_ba": ".250", "est_slg": ".400"},
          {"player_id": "3", "woba": "0.300", "est_woba": "0.300", "est_ba": ".240", "est_slg": ".380"}]
    monkeypatch.setattr(mpe, "_savant", lambda kind, y, side="batter": ex if kind == "expected" else [])
    block = mpe._statcast_block(1, False, 2026)
    luck = [m for m in block["metrics"] if m["label"].startswith("Luck")]
    assert luck == [{"label": "Luck (xwOBA-wOBA)", "value": "+0.031", "pct": 83}]
    g = json.loads((S.ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    xhem = next(e for e in g["entries"] if e.get("id") == "xhem_plus")
    assert "Luck = Savant xwOBA minus wOBA" in xhem["definition"]
    xiso = next(e for e in g["entries"] if e.get("id") == "xiso")
    assert "xwOBA minus wOBA" in xiso["methodology"] and "actual wOBA minus xwOBA" not in xiso["methodology"]


ACCT_ROWS = ("fa_war_paths_decay", "mlb_projections_prospects", "team_win_projections",
             "prospect_surplus")


def _registry_rows():
    reg = json.loads((S.ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    return {m["model_id"]: m for m in reg["models"]}


def test_the_accountability_rows_proj_export_publishes_are_the_ones_pinned_here():
    import proj_export
    assert tuple(mid for mid, _ in proj_export._ACCOUNTABILITY_MODELS) == ACCT_ROWS
    import inspect
    assert '"remeasure_pending"' in inspect.getsource(proj_export._accountability_block)


def test_veteran_paths_card_prints_the_remeasure_disclosure_from_the_registry():
    """QMLC01: the registry row carries the disclosure, and the card prints it
    beside the badge and under the holdout table (read, not typed)."""
    row = _registry_rows()["fa_war_paths_decay"]
    pending = row["remeasure_pending"]
    assert pending == "measured on the pre-repair labels; not re-measured on the served bundle"
    assert pending not in JS
    board = json.loads(S.BOARD)
    board["accountability"] = {
        "verdict_enum": ["validated", "provisional", "unvalidated", "deprecated"],
        "models": [{"label": "Veteran WAR paths", "model_id": "fa_war_paths_decay",
                    "verdict": "validated", "remeasure_pending": pending,
                    "eval_artifact": "data/proj_horizon_eval.json"}],
        "backtests": {"data/proj_horizon_eval.json": {
            "frame": "2022-2024 holdout",
            "champion": {"model": "proj_lgbm_v1", "horizons": [{"h": 1, "mae": 0.54, "bias": -0.1, "coverage": 0.81}]},
            "baseline": {"model": "marcel_decay_v2", "horizons": [{"h": 1, "mae": 0.62, "coverage": 0.67}]}}}}
    saved = S.BOARD
    S.BOARD = json.dumps(board)
    try:
        html = S._render("#view=accountability")
    finally:
        S.BOARD = saved
    assert html.count(pending) == 2
    assert 'proj-acct-pending' in html


def test_the_accountability_rows_carry_no_dash_banned_word_or_retired_name():
    """QMLC08 + QMLC12: what the card prints from these rows passes the
    owner's copy rules; the champion line no longer says it beat a challenger
    the table shows with the lower MAE."""
    import sys
    sys.path.insert(0, str(S.ROOT / "tools"))
    from copy_lint import BAN_RE
    rows = _registry_rows()
    for mid in ACCT_ROWS:
        for k, v in rows[mid].items():
            if not isinstance(v, str):
                continue
            assert not re.search(r"\w -- \w", v), f"{mid}.{k}: ' -- ' used as a dash"
            assert not re.search(r"\bxFV\b", v), f"{mid}.{k}: retired name xFV"
            hit = BAN_RE.search(v)
            assert not hit, f"{mid}.{k}: banned word {hit.group()!r}"
    pros = rows["mlb_projections_prospects"]
    assert "beat the" not in pros["champion"]
    assert "every challenger lost its pre-registered dual gate" in pros["champion"]
    assert "ranks better than any stat-line model" not in pros["notes"]


# ---------------------------------------------------------------------------
# Bytes (QMLP01, QMLP07, QMLP09)
# ---------------------------------------------------------------------------
def test_shards_follow_the_payload_and_a_redirected_data_dir(tmp_path, monkeypatch):
    """QMLP01: one card per player under DATA_DIR/mlb_player_detail/, with
    the board scalars the page reads; a player gone from the payload loses
    its shard."""
    import mlb_player_export as mpe
    monkeypatch.setattr(mpe, "DATA_DIR", tmp_path)
    (tmp_path / "mlb_player_detail").mkdir()
    (tmp_path / "mlb_player_detail" / "gone_guy.json").write_text("{}", encoding="utf-8")
    payload = {"generated_at": "2026-10-07", "first_season": 2027, "horizon": 5,
               "players": {"a_b": {"key": "a_b", "name": "A B"}, "c_d": {"key": "c_d"}}}
    assert mpe._export_shards(payload) == 2
    files = sorted(f.name for f in (tmp_path / "mlb_player_detail").iterdir())
    assert files == ["a_b.json", "c_d.json"]
    one = json.loads((tmp_path / "mlb_player_detail" / "a_b.json").read_text(encoding="utf-8"))
    assert one == {"generated_at": "2026-10-07", "first_season": 2027, "horizon": 5,
                   "key": "a_b", "player": {"key": "a_b", "name": "A B"}}


def test_fa_flag_marks_exactly_the_class_members(tmp_path, monkeypatch):
    """QMLP09: the board row carries the flag player_links.json carried."""
    import proj_export as pe
    monkeypatch.setattr(pe, "DATA_DIR", tmp_path)
    (tmp_path / "fa_class.json").write_text(json.dumps({"members": [{"key": "x"}, {"key": "z"}]}),
                                            encoding="utf-8")
    vets = [{"key": "x"}, {"key": "y", "fa": True}, {"key": "z"}]
    assert pe._stamp_fa_class(vets) == 2
    assert [v.get("fa") for v in vets] == [True, None, True]


def test_the_card_renders_from_its_shard_alone():
    """QMLP01: with only the shard on offer (no board, no whole set), the
    card paints on the shard's first_season and horizon."""
    saved = S._prelude

    def only_shards(hash_, fail_fetch=False):
        js = saved(hash_, fail_fetch)
        return js.replace("var fetch=function(url){var p=__payloads[url];",
                          "delete __payloads['/data/mlb_projections.json'];"
                          "delete __payloads['/data/mlb_player_detail.json'];"
                          "var fetch=function(url){var p=__payloads[url];")
    S._prelude = only_shards
    try:
        html = S._render("#player=vet_guy")
    finally:
        S._prelude = saved
    assert "mlbp-hero" in html and "Vet Guy" in html


def test_logos_are_asked_for_at_their_drawn_size():
    """QMLP07: no 500 x 500 master is requested for a 13 to 16 px mark."""
    assert "teamlogos/mlb/500/${slug}.png\"" not in JS
    assert "i/teamlogos/mlb/500/${slug}.png&h=${LOGO_PX}&w=${LOGO_PX}" in JS
    assert "H.teamLogoURL(org, LOGO_PX)" in JS


def test_board_and_card_bytes(server):
    """QMLP01/07/09 on the served page: the board fetches no identity map and
    no logo master; a card fetches its own shard, not the whole set."""
    board = json.loads((S.ROOT / "data" / "mlb_projections.json").read_text(encoding="utf-8"))
    with _page(server) as page:
        reqs = page._requests
        assert not any("teamlogos/mlb/500/" in u and "&h=" not in u for u in reqs)
        if board.get("n_fa") is not None:
            assert not any("player_links.json" in u for u in reqs)
    if not (S.ROOT / "data" / "mlb_player_detail" / "juan_soto.json").exists():
        pytest.skip("per-player shards not built")
    with _page(server, "#player=juan_soto", wait=".mlbp-hero") as page:
        reqs = page._requests
        assert sum("/data/mlb_player_detail/juan_soto.json" in u for u in reqs) == 1
        assert not any(u.endswith("/data/mlb_player_detail.json") for u in reqs)
        assert not any("player_links.json" in u for u in reqs)
        assert page.query_selector("#mlbp-hub .player-hub-strip") is not None
