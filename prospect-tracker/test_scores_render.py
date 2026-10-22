# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /scores/ page (SCORES_3) rendered in headless Chromium on fixture
payloads, behind scores_core.SCORES_LIVE.

THE SITE UNDER TEST is a temporary copy: the preview shell from
build_site.build_scores(), copies of assets/ and branding/, the two shared
data files the runtime reads, and fixture payloads under data/scores/ built
by scores_core from test_fixtures/scores/. Nothing here reads or writes the
repo's data/ scores files or a real .cache/scores/, and every request off
loopback is aborted.

WHAT IS PINNED (plan section 12): no horizontal page scroll at 390, 1280 and
1440 in both themes; each card state renders its fields; the 390 px height
measure (every card at or above its slot's min-height, no card's content
taller than its floor, so a poll within a state changes no height, and a
live-to-final swap moves no card below); a late game waits for its notice;
12 innings scroll inside the line score; the chart's role, label, table twin,
pointer crosshair (a tap pins it) and keys; P/AB and P/IP in the box score;
no link inside another interactive element; 24 px targets, 44 px for strip
chips, tabs and filters at 390; no player_links.json request on the day view;
one polite live region; no console errors; the flag (SCORES_LIVE False
writes no scores/index.html, and publish_paths has no scores line); the
budgets of plan 8.1, pinned by the constants below. The October bracket
(SCORES_4b): #bracket=<season> draws the season index's block through the
lazy chunk, placeholders unlinked, no percent sign and no data-model-id
inside it; the chunk loads only on that route or for the October rail at
1400 px and wider; its mount function needs no page around it. The
pregame context (SCORES_6) on a fixture board: the shell loads the Diamond
config, its helper and the eager scores-pregame.js before scores.js and
carries BETTING_DISCLAIMER once in an inert template; the card line and the
game view's panel print the board's numbers verbatim with their labels, the
absent-state sentences, SEM+, the hook median, the park index, the DFS links
and eFV on the posted lineup; a regular-season pregame card keeps the model
line inside its own floor (slot-prer) at 390 px.
"""
from __future__ import annotations

import copy
import gzip
import json
import shutil
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import build_site
import scores_core as sc
from conftest import serve_site

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test_fixtures" / "scores"
TODAY = "2026-09-30"

#: Plan 8.1 budgets (test-time pins; bytes with LF line endings, as served).
KB = 1024
SCORES_JS_RAW = 70 * KB
SCORES_JS_GZIP = 20 * KB
SCORES_BRACKET_JS_RAW = 12 * KB
SCORES_PREGAME_JS_RAW = 12 * KB          # SCORES_6, eager: counted in the cold first paint
SCORES_CSS_RAW = 20 * KB
SPORTS_PAGE_CSS_RAW = 12 * KB            # SCORES_7a: the shared sports-page classes and the bracket styles; SCORES_7b pixel bracket + SCORES_7d home strip (combined at integration)
SCORES_ABOUT_JS_RAW = 6 * KB             # SCORES_7a: the lazy About chunk
SCORES_PIXEL_JS_RAW = 12 * KB            # SCORES_7b: the pixel art, eager: counted in the cold first paint
SCORES_PIXEL_CSS_RAW = 6 * KB            # SCORES_7b: its styles, eager
SHELL_RAW = 17 * KB                      # SCORES_7b: 16 -> 17 KB for the two pixel-art tags (the shell was 39 bytes under 16)
COLD_FIRST_PAINT_GZIP = 70 * KB
#: The card floors of assets/scores.css at 390 px (plan 1.3), measured from
#: the fixtures below with their longest strings.
#: "prer" (SCORES_6) is a regular-season pregame card, with room for the model line.
SLOT_MIN = {"pre": 222, "prer": 260, "lf": 304, "off": 164}   # SCORES_7a re-measured them on the agate cards
WIDTHS = (390, 1280, 1440)


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sched_game(pk, coded):
    for d in load("schedule_states.json")["dates"]:
        for g in d["games"]:
            if g["gamePk"] == pk and g["status"]["codedGameState"] == coded:
                return copy.deepcopy(g)
    raise KeyError((pk, coded))


# --------------------------------------------------------------------------- #
# The fixture payloads
# --------------------------------------------------------------------------- #
def build_payloads(now: datetime | None = None, bracket: dict | None = None) -> dict:
    """{published path under data/scores/: payload} for a site whose today is
    2026-09-30. Times on the job block are relative to `now` (the server's
    Date header is the stale rule's clock), so the page reads S0. The cards
    carry the longest strings the fixtures hold: the longest play text on
    the live card, every chip on the final card, probables with hand, W-L
    and ERA, TV and weather on the pregame card."""
    now = now or datetime.now(timezone.utc)
    gen = _iso(now - timedelta(seconds=60))
    lg = load("league_constants_2026.json")
    gf_final = sc.build_game_file(_sched_game(849845, "F"), load("wp_849845_full.json"), load("box_849845.json"), lg,
                                  generated_at=gen, feed=load("feed_849845.json"))
    gf_live = sc.build_game_file(_sched_game(849846, "I"), load("wp_849846_live.json"), None, lg, generated_at=gen)
    gf_old = sc.build_game_file(load("game_824592.json"), load("wp_824592.json"), load("box_824592.json"), lg,
                                generated_at=gen)
    longest = max((p["text"] for p in gf_final["plays"]), key=len)

    # live: the longest play text, a no-hitter chip, a pitch count
    live = gf_live["card"]
    live["sit"]["last_text"] = longest
    live["sit"]["pitcher"]["pitches"] = 104
    live["sit"]["bases"] = [True, False, True]
    live["flags"]["no_hitter"] = True
    gf_live["card"] = live
    gf_live["rev"] = live["rev"] = sc.rev_of({k: v for k, v in gf_live.items() if k != "rev"})

    # final: every chip the card can carry
    fin = gf_final["card"]
    fin["videos"] = {"recap_s": 180, "condensed_s": 1113}
    fin["top_play"]["clip_s"] = 29
    fin["flags"]["debut"] = True

    pre = sc.build_card(_sched_game(849841, "P"), generated_at=gen)
    for side, hand, w, l, era in (("away", "L", 13, 5, "2.50"), ("home", "R", 6, 4, "2.18")):
        pre[side]["probable"].update({"hand": hand, "w": w, "l": l, "era": era})
    pre["tv"] = ["NBC", "Universo", "Peacock"]
    sched = sc.build_card(_sched_game(849848, "S"), generated_at=gen)
    sched2 = sc.build_card(_sched_game(900005, "S"), generated_at=gen)
    delayed_g = _sched_game(900005, "S")
    delayed_g["gamePk"] = 900006
    delayed_g["status"] = {"abstractGameState": "Preview", "codedGameState": "P", "detailedState": "Delayed Start: Rain",
                           "reason": "Rain"}
    delayed = sc.build_card(delayed_g, generated_at=gen)
    today_cards = [live, pre, sched, sched2, delayed]

    # 2026-09-29: the final, and a 12-inning final with no game file
    xtra = copy.deepcopy(fin)
    xtra.update({"pk": 900007, "rev": None, "start": "2026-09-29T23:05:00Z", "star": None, "top_play": None,
                 "videos": None})
    xtra["line"] = [[0, 0]] * 9 + [[1, 1], [0, 0], [3, 0]]
    xtra["away"] = dict(xtra["away"], r=4)
    xtra["home"] = dict(xtra["home"], r=1)
    xtra["flags"] = dict(xtra["flags"], extra_innings=True, debut=False)
    d29 = [fin, xtra]
    d27 = [sc.build_card(_sched_game(823490, "C"), generated_at=gen)]
    d01 = [sc.build_card(_sched_game(pk, c), generated_at=gen) for pk, c in
           ((849844, "S"), (900001, "D"), (900002, "U"), (900003, "S"))]
    d03 = [sc.build_card(_sched_game(849830, "S"), generated_at=gen)]
    d531 = [gf_old["card"]]
    games = {849845: gf_final, 849846: gf_live, 824592: gf_old}
    dates = {"2026-05-31": d531, "2026-09-27": d27, "2026-09-29": d29, TODAY: today_cards,
             "2026-10-01": d01, "2026-10-03": d03}
    out = {f"games/{pk}.json": g for pk, g in games.items()}
    date_docs = {d: sc.build_date_file(d, cards, games, generated_at=gen) for d, cards in dates.items()}
    for d, doc in date_docs.items():
        out[f"{d}.json"] = doc
    season = {"schema": sc.SCHEMA, "season": 2026, "bracket": bracket,
              "dates": [{"d": d, "n": len(doc["games"]), "types": sorted({c["type"] for c in doc["games"]}),
                         "rev": sc.rev_of(doc), "flags": []} for d, doc in sorted(date_docs.items())]}
    out["index-2026.json"] = season
    index = {"schema": sc.SCHEMA, "generated_at": gen,
             "seasons": [{"season": 2026, "rev": sc.rev_of(season), "n_dates": len(date_docs)}],
             "registry": [{"model_id": "scores_mlb_wp", "verdict": "provisional", "sentence": "MLB, provisional"},
                          {"model_id": "scores_stars_rule", "verdict": "provisional",
                           "sentence": "Eephus rule, provisional"},
                          {"model_id": "scores_biggest_plays_rule", "verdict": "provisional",
                           "sentence": "Eephus rule, provisional"}],
             "accuracy": {"mlb_wp": {"feed_brier": 0.157516, "base_rate_brier": 0.249754, "n_plays": 1448965,
                                     "seasons": ["2018", "2019", "2021", "2022", "2023", "2024", "2025", "2026"],
                                     "pregame_values": {"500": 3}, "artifact_generated_at": "2026-09-11T01:06:34Z"}},
             "rules": {"stars": {"rule": sc.STARS_RULE, "min_outs": sc.MIN_OUTS, "min_coverage": sc.MIN_COVERAGE,
                                 "first_star_winner": sc.FIRST_STAR_WINNER},
                       "plays": {"rule": sc.PLAYS_RULE, "min_swing": sc.MIN_SWING, "n": sc.N_BIG_PLAYS},
                       "video": {"embed": False, "branch": None, "video_hosts": list(sc.VIDEO_HOSTS),
                                 "caption_hosts": list(sc.CAPTION_HOSTS), "poster_host": sc.POSTER_HOST,
                                 "frame_host": sc.FRAME_HOST}},
             "copyright": load("box_849845.json")["copyright"]}
    out["index.json"] = index
    window = {}
    for d in ("2026-09-29", TODAY, "2026-10-01", "2026-10-03"):
        cards = date_docs[d]["games"]
        st = [c["state"] for c in cards]
        window[d] = {"rev": sc.rev_of(date_docs[d]), "n": len(cards), "live": st.count("live"),
                     "final": st.count("final"), "pre": sum(s in ("scheduled", "pregame", "delayed") for s in st),
                     "off": sum(s in ("postponed", "suspended", "cancelled") for s in st),
                     "clips_matched": 1, "clips_of": 5, "stale_since": None}
    out["latest.json"] = {
        "schema": sc.SCHEMA, "generated_at": gen,
        "job": {"action": "live", "state": "ok", "next_by": _iso(now + timedelta(minutes=10)), "last_ok_at": gen,
                "down_after_s": 1800, "poll_live_s": 45, "poll_idle_s": 300, "errors_24h": 0, "refusals_24h": 0},
        "index_rev": sc.rev_of(index), "today": TODAY, "next_game_date": "2026-10-01", "window": window,
        "live": [{"pk": 849846, "date": TODAY}]}
    return out


# --------------------------------------------------------------------------- #
# SCORES_6: the pregame fixtures. A fixture Sports Betting board
# (test_fixtures/scores/betting_board.json, shaped like the served board with
# decoy keys the job must never read) and the five served files the pregame
# block copies from, run through the job's own pure path (scores_core
# board_extract, pre_block and the *_map readers). Shared with
# test_scores_fence.py and test_scores_labelling.py.
# --------------------------------------------------------------------------- #
#: The posted-lineup player graded on eFV v2 in the fixture (51.5 prints "eFV 52").
EFV_ID = 686948
#: The index registry rows the job writes for the pregame block (scores_job.REGISTRY_IDS).
PRE_REGISTRY = [{"model_id": "betting_game_prob", "verdict": "provisional",
                 "sentence": "Eephus model, unvalidated, provisional"},
                {"model_id": "sem_plus", "verdict": "validated", "sentence": "MLB Stats SEM+, validated"},
                {"model_id": "efv_v2", "verdict": "provisional", "sentence": "PROSPX eFV, provisional"},
                {"model_id": "mgmt_board_export", "verdict": "provisional",
                 "sentence": "In-Game Management, provisional"}]


def pregame_served() -> dict:
    """{served file name: doc}: the fixture board and the files the pregame
    block copies from, each carrying keys the job must never copy."""
    return {
        "betting.json": load("betting_board.json"),
        "starter_leaderboards.json": {"season": 2026, "verdict": "validated", "starters": [
            {"mlbam": 641816, "name": "Home Probable", "team": "ATL", "sem_plus": 118, "sem_plus_raw": 117.6, "fip": 3.1},
            {"mlbam": 650911, "name": "Away Probable", "team": "PHI", "sem_plus": 104, "sem_plus_raw": 104.2}]},
        "management_board.json": {
            "decisions": {"families": {"pitching_change": {"hook_pitch_count": {"median": 89.0}}}},
            "clubs": {"games_floor": 40, "rows": [
                {"club": "ATL", "season": 2026, "games": 160, "hook_median_pitches": 87.5, "mwpa_pitching_change": 2.1,
                 "z_hook": -0.4, "best": {"family": "pitching_change", "mwpa": 0.5}},
                {"club": "PHI", "season": 2026, "games": 160, "hook_median_pitches": 91.0, "z_hook": 0.6},
                {"club": "PHI", "season": 2025, "games": 162, "hook_median_pitches": 80.0}]}},
        "fantasy.json": {
            "sections": {"two_start": [{"mlbam": 650911, "name": "Away Probable", "team": "PHI", "n_starts": 2,
                                        "total_fgp": 40.1,
                                        "legs": [{"date": TODAY, "opp_org": "ATL", "exp_fgp": 20.0},
                                                 {"date": "2026-10-05", "opp_org": "NYM", "exp_fgp": 20.1,
                                                  "projected": True}]}]},
            "schedule": {"games": [{"game_pk": 900010, "date": TODAY}]}},
        "fa_meta.json": {"park_factors": {"ATL": {"woba": 101, "hr": 104, "runs": 102}},
                         "park_factors_by_hand": {"L": {"ATL": {"runs": 140}}}},
        "xfv.json": {"meta": {}, "by_player": {
            "drake_baldwin": {"kind": "active", "grade_basis": "efv_v2", "xfv_grade": 51.5, "consensus_fv": 45.0},
            "ozzie_albies": {"kind": "debuted", "xfv_grade": 55.0, "consensus_fv": 55.0},
            "ronald_acuna": {"kind": "active", "grade_basis": "provisional_capped", "xfv_grade": 44.0,
                             "consensus_fv": 40.0}}},
        "player_links.json": {"byMlbam": {"686948": {"prospx": "drake_baldwin"}, "645277": {"prospx": "ozzie_albies"},
                                          "660670": {"prospx": "ronald_acuna"}}},
    }


def pregame_ctx(served: dict | None = None, *, board_kind: str = "full") -> dict:
    """The job's pregame context, built from fixture docs instead of the served files."""
    s = served or pregame_served()
    two, pks = sc.fantasy_maps(s["fantasy.json"])
    return {"board": sc.board_extract(s["betting.json"]), "board_kind": board_kind,
            "sem": sc.sem_map(s["starter_leaderboards.json"]), "hook": sc.hook_map(s["management_board.json"]),
            "two_start": two, "dfs_pks": pks, "park": sc.park_map(s["fa_meta.json"]),
            "efv": sc.efv_map(s["xfv.json"], s["player_links.json"])}


def regular_season_game(pk: int = 900010, start: str | None = None, base: tuple = (849841, "P")) -> dict:
    """A fixture schedule game turned into a regular-season Preview game
    (849841 is PHI at ATL with both lineups posted)."""
    g = _sched_game(*base)
    g.update({"gamePk": pk, "gameType": "R", "description": None, "seriesDescription": "Regular Season",
              "status": {"abstractGameState": "Preview", "codedGameState": "P", "detailedState": "Pre-Game",
                         "statusCode": "P", "startTimeTBD": False}})
    g.pop("seriesStatus", None)
    if start:
        g["gameDate"] = start
    return g


def pregame_payloads(now: datetime | None = None, *, inject_live: bool = False) -> dict:
    """build_payloads() plus, on today's date: a regular-season Preview game
    carrying the full pregame block (900010), one whose board starter differs
    (900011), and the postseason Preview game 849848 with its season
    sentence, all starting three hours from `now` so the page reads them
    before first pitch. `inject_live` copies 900010's block onto the live card,
    the stale payload the page must refuse to print."""
    now = now or datetime.now(timezone.utc)
    p = build_payloads(now)
    gen = p["latest.json"]["generated_at"]
    start = _iso(now + timedelta(hours=3))
    ctx = pregame_ctx()
    doc = p[f"{TODAY}.json"]
    g1 = regular_season_game(900010, start)
    g2 = regular_season_game(900011, start, base=(849846, "P"))
    g3 = _sched_game(849848, "S")
    g3["gameDate"] = start
    for g in (g1, g2, g3):
        card = sc.build_card(g, generated_at=gen)
        card["pre"] = sc.pre_block(g, card, ctx)
        doc["games"] = [c for c in doc["games"] if c["pk"] != card["pk"]] + [card]
    doc["games"].sort(key=lambda c: (c.get("start") or "", c["pk"]))
    if inject_live:
        live = next(c for c in doc["games"] if c["pk"] == 849846)
        live["pre"] = copy.deepcopy(next(c for c in doc["games"] if c["pk"] == 900010)["pre"])
    w = p["latest.json"]["window"][TODAY]
    st = [c["state"] for c in doc["games"]]
    w.update({"rev": sc.rev_of(doc), "n": len(st), "pre": sum(s in ("scheduled", "pregame", "delayed") for s in st)})
    p["index.json"]["registry"] = p["index.json"]["registry"] + copy.deepcopy(PRE_REGISTRY)
    p["latest.json"]["index_rev"] = sc.rev_of(p["index.json"])
    return p


def write_payloads(site: Path, payloads: dict) -> None:
    for rel, doc in payloads.items():
        p = site / "data" / "scores" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(sc.dumps(doc), encoding="utf-8")


def make_site(dest: Path, payloads: dict | None = None) -> Path:
    """A temporary copy of the built site for /scores/: the preview shell,
    assets/, branding/, the shared runtime's two data reads, and the fixture
    payloads under data/scores/."""
    dest.mkdir(parents=True, exist_ok=True)
    build_site.write_scores_page(preview_root=dest)
    for d in ("assets", "branding"):
        if (ROOT / d).is_dir() and not (dest / d).exists():
            shutil.copytree(ROOT / d, dest / d)
    (dest / "data").mkdir(exist_ok=True)
    for name in ("glossary.json", "player_links.json"):
        if (ROOT / "data" / name).exists():
            shutil.copy2(ROOT / "data" / name, dest / "data" / name)
    write_payloads(dest, payloads if payloads is not None else build_payloads())
    return dest


@contextmanager
def scores_page(base: str, pw, *, width=390, theme="light", hash_="", clock=False):
    """A page on the served copy: off-loopback requests aborted, console
    errors and every request recorded on page._errors and page._requests."""
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=theme)
    page = ctx.new_page()
    page._errors, page._requests = [], []
    page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base[:-1]) else r.abort())
    page.on("request", lambda r: page._requests.append(r.url))
    page.on("console", lambda m: page._errors.append(m.text) if m.type == "error" and
            "net::ERR_FAILED" not in m.text and "ERR_BLOCKED" not in m.text else None)
    page.on("pageerror", lambda e: page._errors.append(str(e)))
    if clock:
        page.clock.install()
    try:
        page.goto(base + "scores/" + hash_, wait_until="load")
        yield page
    finally:
        browser.close()


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return make_site(tmp_path_factory.mktemp("scores_site"))


@pytest.fixture(scope="module")
def pw():
    sync = pytest.importorskip("playwright.sync_api")
    with sync.sync_playwright() as p:
        try:
            p.chromium.launch().close()
        except Exception as e:  # pragma: no cover - chromium missing
            pytest.skip(f"chromium unavailable: {e}")
        yield p


def _wait_cards(page, n=None):
    page.wait_for_selector("#scores-app-root .sc-card", timeout=15000)
    if n:
        page.wait_for_function(f"document.querySelectorAll('#scores-app-root .sc-card').length >= {n}")


def _no_errors(page):
    real = [e for e in page._errors if "Failed to load resource" not in e]
    assert real == [], real


# --------------------------------------------------------------------------- #
# The flag and the budgets
# --------------------------------------------------------------------------- #
def test_scores_live_false_builds_only_the_preview(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "SCORES_LIVE", False)
    calls = []
    monkeypatch.setattr(build_site, "_write", lambda rel, html: calls.append(rel))
    path = Path(build_site.write_scores_page(preview_root=tmp_path))
    assert calls == [], "the published tree was written while SCORES_LIVE is False"
    assert path == tmp_path / "scores" / "index.html" and path.exists()


def test_the_flip_serves_the_page_and_a_preview_root_never_writes_the_tree(tmp_path, monkeypatch):
    # SCORES_5a_LIVE_FLIP: the flag is on in the source, main() writes the route by
    # literal (tools/gen_audit_docs.py reads those), and publish_paths ships it.
    src_core = (ROOT / "scores_core.py").read_text(encoding="utf-8").splitlines()
    assert "SCORES_LIVE = True" in src_core
    import inspect
    main_src = inspect.getsource(build_site.main)
    assert '_write("scores/index.html", build_scores())' in main_src
    lines = [ln.strip() for ln in (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8").splitlines()]
    assert "scores" in [ln for ln in lines if ln and not ln.startswith("#")]
    # a render test's temporary site never writes the published tree, flag on or off
    monkeypatch.setattr(sc, "SCORES_LIVE", True)
    calls = []
    monkeypatch.setattr(build_site, "_write", lambda rel, html: calls.append(rel))
    path = Path(build_site.write_scores_page(preview_root=tmp_path))
    assert calls == [] and path == tmp_path / "scores" / "index.html" and path.exists()
    assert build_site.write_scores_page() == str(build_site.ROOT / "scores" / "index.html")
    assert calls == ["scores/index.html"]
    # SCORES_5b put the page on the nav (one leaf, SC-NAV slot) and in the sitemap;
    # test_scores_health.py pins the slot, the label and the sitemap row
    hrefs = [c[2] for it in build_site.NAV_ITEMS for c in (it["children"] if isinstance(it, dict) else [it])]
    assert hrefs.count("/scores/") == 1
    assert build_site.build_sitemap([]).count("/scores/</loc>") == 1


def test_shell_is_a_pure_reader_on_the_ledger_pattern():
    html = build_site.build_scores()
    assert html.count('id="scores-app-root"') == 1
    assert "EEPHUS_DATA_VERS" not in html
    for asset, ver in (("scores.css", build_site._SCORES_CSS_VER), ("scores.js", build_site._SCORES_VER),
                       ("sports-page.css", build_site._SPORTS_PAGE_CSS_VER),
                       ("scores-pixel.css", build_site._SCORES_PIXEL_CSS_VER), ("scores-pixel.js", build_site._SCORES_PIXEL_VER),
                       ("eephus-hub.js", build_site._HUB_VER), ("eephus-teampick.js", build_site._TEAMPICK_VER)):
        assert f"/assets/{asset}?v={ver}" in html, asset
    assert "scores-video.js" not in html
    # SCORES_6: the Diamond config, then its helper, then the pregame chunk, then scores.js
    order = [html.index(f"/assets/{a}?v=") for a in ("diamond-config.js", "eephus-diamond.js", "scores-pregame.js",
                                                    "scores-pixel.js", "scores.js")]
    assert order == sorted(order), order
    assert f"/assets/scores-pregame.js?v={build_site._SCORES_PREGAME_VER}" in html
    assert html.count(build_site.BETTING_DISCLAIMER) == 1
    assert f'<template id="scores-betnote">{build_site.BETTING_DISCLAIMER}</template>' in html
    # the bracket chunk is never a script tag: the mount root names its stamped path for the lazy loader
    assert f'data-bracket-src="/assets/scores-bracket.js?v={build_site._SCORES_BRACKET_VER}"' in html
    assert html.count("scores-bracket.js") == 1 and '<script src="/assets/scores-bracket.js' not in html
    # SCORES_7a: the About view is a lazy chunk named the same way, and the shared sports-page css comes first
    assert f'data-about-src="/assets/scores-about.js?v={build_site._SCORES_ABOUT_VER}"' in html
    assert html.count("scores-about.js") == 1 and html.index("sports-page.css") < html.index("/assets/scores.css")
    assert "<title>MLB Scores - eephus.io</title>" in html
    assert "Scores / Standings" in html and build_site._stage_chip("scores") in html
    assert build_site.MODULE_STAGE["scores"] == (
        "β", "Beta. Scores, standings, win probability and video from MLB; Stars of the Game by "
        "published rule; odds are site simulations, implied, no market")  # STANDINGS_7_FLIP
    body = html.split('id="scores-app-root"')[0].split("section-head--byline")[-1]
    import re
    assert not re.search(r"\d", re.sub(r"<[^>]+>", "", body)), "a number is typed in the shell's masthead"


def test_section_strip_waits_for_standings_live(monkeypatch):
    import types
    monkeypatch.setitem(__import__("sys").modules, "standings_core", types.SimpleNamespace(STANDINGS_LIVE=False))
    assert "mlbstats-sectionnav" not in build_site._scores_module_head("scores")
    monkeypatch.setitem(__import__("sys").modules, "standings_core", types.SimpleNamespace(STANDINGS_LIVE=True))
    head = build_site._scores_module_head("scores")
    assert 'aria-label="Scores / Standings"' in head and 'href="/scores/" aria-current="page"' in head


def _lf(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def test_budgets_and_the_cold_first_paint():
    js, css = _lf(ROOT / "assets" / "scores.js"), _lf(ROOT / "assets" / "scores.css")
    pre_js = _lf(ROOT / "assets" / "scores-pregame.js")
    sp_css = _lf(ROOT / "assets" / "sports-page.css")
    px_js, px_css = _lf(ROOT / "assets" / "scores-pixel.js"), _lf(ROOT / "assets" / "scores-pixel.css")
    assert len(px_js) <= SCORES_PIXEL_JS_RAW, len(px_js)
    assert len(px_css) <= SCORES_PIXEL_CSS_RAW, len(px_css)
    assert len(sp_css) <= SPORTS_PAGE_CSS_RAW, len(sp_css)
    assert len(_lf(ROOT / "assets" / "scores-about.js")) <= SCORES_ABOUT_JS_RAW
    shell = build_site.build_scores().encode("utf-8")
    assert len(js) <= SCORES_JS_RAW, len(js)
    assert len(gzip.compress(js, 9)) <= SCORES_JS_GZIP, len(gzip.compress(js, 9))
    assert len(pre_js) <= SCORES_PREGAME_JS_RAW, len(pre_js)
    assert len(css) <= SCORES_CSS_RAW, len(css)
    assert len(shell) <= SHELL_RAW, len(shell)
    p = pregame_payloads()
    first = shell + js + css + sc.dumps(p["latest.json"]).encode() + sc.dumps(p[f"{TODAY}.json"]).encode()
    owned = sum(len(gzip.compress(b, 9)) for b in (shell, js, pre_js, css, sp_css, px_js, px_css, sc.dumps(p["latest.json"]).encode(),
                                                    sc.dumps(p[f"{TODAY}.json"]).encode()))
    assert owned <= COLD_FIRST_PAINT_GZIP, owned
    assert len(first) > 0
    # every scores style lives in scores.css or sports-page.css; scores.js has no player and draws no bracket: it
    # loads the lazy chunk from the shell's stamped data-bracket-src and hands it the block
    assert "<video" not in js.decode() and "iframe" not in js.decode()
    assert "scb-" not in js.decode() and "Winner of" not in js.decode() and "scores-bracket.js" not in js.decode()
    chunk = _lf(ROOT / "assets" / "scores-bracket.js")
    assert len(chunk) <= SCORES_BRACKET_JS_RAW, len(chunk)


def test_fixture_payloads_pass_the_validator():
    for rel, doc in list(build_payloads().items()) + list(pregame_payloads().items()):
        kind = sc.kind_of_name(rel)
        assert kind, rel
        res = sc.validate_payload(kind, doc, name=rel)
        assert res["ok"], (rel, res["refused"])


# --------------------------------------------------------------------------- #
# The day view
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", WIDTHS)
def test_day_view_has_no_page_scroll_and_no_console_errors(site, pw, width, theme):
    with serve_site(site) as base, scores_page(base, pw, width=width, theme=theme, hash_=f"#date={TODAY}") as page:
        _wait_cards(page, 5)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "horizontal page scroll"
        assert not any("player_links.json" in u for u in page._requests), "player links loaded on the day view"
        assert not any("/data/scores/" in u and "player" in u for u in page._requests)
        n_polite = page.evaluate("document.querySelectorAll('.scores-app [aria-live=polite]').length")
        assert n_polite == 1, n_polite
        rail = page.locator(".sc-rail")
        assert (rail.count() > 0 and rail.is_visible()) == (width >= 1400)
        _no_errors(page)


def test_each_state_renders_its_fields(site, pw):
    with serve_site(site) as base, scores_page(base, pw, hash_=f"#date={TODAY}") as page:
        _wait_cards(page, 5)
        # text_content: the state kicker is uppercased by CSS (SCORES_7a), the words stay the job's
        txt = lambda pk: page.locator(f'article[data-pk="{pk}"]').text_content()
        live = txt(849846)
        assert "Bottom 1, 0 outs" in live and "Count 0-1" in live and "No-hitter in progress" in live
        assert "MLB win probability: CHW 84%" in live and "MLB, provisional" in live and "104 pitches" in live
        assert "Lineups posted" in txt(849841) and "13-5, 2.50 ERA" in txt(849841) and "TV: NBC" in txt(849841)
        assert "Delayed start: rain" in txt(900006)
        assert "Updated " in page.locator(".sc-stamp").inner_text()
        page.evaluate("location.hash = '#date=2026-09-29'")
        page.wait_for_selector('article[data-pk="849845"]')
        fin = txt(849845)
        for want in ("Final", "W Lee, L Duran, S Iglesias", "Star: Riley (ATL)", "Video 0:29", "Recap 3:00",
                     "MLB debut", "Eephus rule, provisional"):
            assert want in fin, want
        assert "Final, 12 innings" in txt(900007)
        page.evaluate("location.hash = '#date=2026-10-01'")
        page.wait_for_selector('article[data-pk="900001"]')
        assert "Postponed: rain." in txt(900001) and "Suspended" in txt(900002)
        page.evaluate("location.hash = '#date=2026-09-27'")
        page.wait_for_selector('article[data-pk="823490"]')
        assert "Cancelled: rain." in txt(823490)
        page.evaluate("location.hash = '#date=2026-10-03'")
        page.wait_for_selector('article[data-pk="849830"]')
        assert page.locator('article[data-pk="849830"] [data-club-nolink="unresolved"]').count() >= 1
        page.evaluate("location.hash = '#date=2026-10-07'")
        page.wait_for_function("document.querySelector('.sc-empty') && /seven days ahead/.test(document.querySelector('.sc-empty').textContent)")
        _no_errors(page)


_MEASURE = """() => Array.from(document.querySelectorAll('#scores-app-root .sc-card')).map(el => {
  const h = el.getBoundingClientRect().height;
  const slot = (el.className.match(/slot-(\\w+)/) || [])[1];
  const floor = parseFloat(getComputedStyle(el).minHeight);
  el.style.minHeight = '0px';
  const natural = el.getBoundingClientRect().height;
  el.style.minHeight = '';
  return {pk: +el.dataset.pk, state: el.dataset.state, slot, h, floor, natural,
          clipped: el.scrollHeight > el.clientHeight + 1};
})"""


def test_390_height_measure_every_state_at_its_floor(site, pw):
    seen = set()
    with serve_site(site) as base, scores_page(base, pw, hash_=f"#date={TODAY}") as page:
        for d in (TODAY, "2026-09-29", "2026-10-01", "2026-09-27"):
            page.evaluate(f"location.hash = '#date={d}'")
            page.wait_for_function(f"document.querySelector('.sc-day[aria-current=date]') && "
                                   f"document.querySelector('.sc-day[aria-current=date]').getAttribute('href').indexOf('{d}') >= 0")
            _wait_cards(page)
            for c in page.evaluate(_MEASURE):
                seen.add(c["state"])
                assert c["floor"] == SLOT_MIN[c["slot"]], c
                assert c["h"] >= c["floor"] - 0.5, c
                assert c["natural"] <= c["floor"] + 0.5, ("content taller than its floor: a poll could move cards", c)
                assert not c["clipped"], c
    assert seen >= {"live", "final", "pregame", "scheduled", "delayed", "postponed", "suspended", "cancelled"}, seen


def _republish(site: Path, payloads: dict, date: str, mutate) -> None:
    """Rewrite a date file the way the job does (new rev, then latest.json)."""
    doc = payloads[f"{date}.json"]
    mutate(doc)
    payloads["latest.json"]["window"][date]["rev"] = sc.rev_of(doc)
    write_payloads(site, {f"{date}.json": doc, "latest.json": payloads["latest.json"]})


def test_polls_move_nothing_and_a_late_game_waits_for_its_notice(tmp_path, pw):
    payloads = build_payloads()
    site = make_site(tmp_path / "site", payloads)
    with serve_site(site) as base, scores_page(base, pw, hash_=f"#date={TODAY}", clock=True) as page:
        _wait_cards(page, 5)
        tops = lambda: page.evaluate("Array.from(document.querySelectorAll('.sc-card')).map(e => "
                                     "[+e.dataset.pk, Math.round(e.getBoundingClientRect().top), "
                                     "Math.round(e.getBoundingClientRect().height)])")
        before = tops()
        order = [pk for pk, _t, _h in before]
        live_i = order.index(849846)
        assert live_i < len(order) - 1, "the live card needs a card below it"

        # 1. a poll within the live state: count, bases and play text change
        def within(doc):
            c = next(c for c in doc["games"] if c["pk"] == 849846)
            c["sit"].update({"balls": 3, "strikes": 2, "outs": 2, "bases": [True, True, True], "last_text": "Play."})
            c["flags"]["no_hitter"] = False
        _republish(site, payloads, TODAY, within)
        page.clock.fast_forward(46_000)
        page.wait_for_function("/Count 3-2/.test(document.querySelector('article[data-pk=\"849846\"]').textContent)")
        assert tops() == before, "a poll within a state moved a card"

        # 2. live to final: nothing below moves, nothing re-sorts
        final_card = copy.deepcopy(payloads["2026-09-29.json"]["games"][0])

        def to_final(doc):
            i = next(i for i, c in enumerate(doc["games"]) if c["pk"] == 849846)
            keep = doc["games"][i]
            fc = copy.deepcopy(final_card)
            fc.update({"pk": 849846, "start": keep["start"], "away": keep["away"], "home": keep["home"]})
            doc["games"][i] = fc
        _republish(site, payloads, TODAY, to_final)
        page.clock.fast_forward(301_000)
        page.wait_for_function("document.querySelector('article[data-pk=\"849846\"]').dataset.state === 'final'")
        after = tops()
        assert [pk for pk, _t, _h in after] == order, "the grid re-sorted"
        assert after[live_i + 1:] == before[live_i + 1:], "the live-to-final swap moved a card below"

        # 3. a late game appends only after the viewer presses its notice
        late = copy.deepcopy(payloads[f"{TODAY}.json"]["games"][1])
        late.update({"pk": 900099, "start": "2026-09-30T17:00:00Z"})
        _republish(site, payloads, TODAY, lambda doc: doc["games"].insert(0, late))
        page.clock.fast_forward(301_000)
        page.wait_for_selector(".sc-showlate")
        assert page.locator('article[data-pk="900099"]').count() == 0
        assert tops() == after
        page.click(".sc-showlate")
        assert page.locator(".sc-grid article").last.get_attribute("data-pk") == "900099"
        _no_errors(page)


# --------------------------------------------------------------------------- #
# The game view
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", WIDTHS)
def test_game_view_tabs_have_no_page_scroll(site, pw, width, theme):
    with serve_site(site) as base, scores_page(base, pw, width=width, theme=theme, hash_="#game=849845") as page:
        page.wait_for_selector('#sc-tab-summary[aria-selected="true"]')
        # SCORES_7a: Summary, Box score, Plays, Win Prob; the old lineups and info addresses land on Box and Summary
        for tab in ("summary", "box", "plays", "wp", "lineups", "info"):
            page.evaluate(f"location.hash = '#game=849845&tab={tab}'")
            page.wait_for_selector(f'#sc-tab-{dict(lineups="box", info="summary").get(tab, tab)}[aria-selected="true"]')
            if tab == "wp":
                page.wait_for_selector(".sc-wp-frame svg")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (tab, "page scroll")
        assert any("player_links.json" in u for u in page._requests), "the game view loads the player links"
        _no_errors(page)


def test_chart_role_label_twin_crosshair_and_keys(site, pw):
    with serve_site(site) as base, scores_page(base, pw, hash_="#game=849845") as page:
        page.wait_for_selector("a.sc-player")  # the player links landed and the view repainted once
        page.evaluate("location.hash = '#game=849845&tab=wp'")       # the chart has its own tab (SCORES_7a)
        page.wait_for_selector(".sc-wp-frame svg")
        frame = page.locator(".sc-wp-frame svg")
        fr = page.locator(".sc-wp-frame")
        assert fr.get_attribute("role") == "img"
        label = fr.get_attribute("aria-label")
        assert label.startswith("Win probability, ATL at home: from 50 percent to 100 percent.") and "Largest swing" in label
        assert page.locator("details.sc-twin table tbody tr").count() == 70
        assert page.locator(".sc-wp-frame").evaluate("e => e.closest('[data-model-id]').dataset.modelId") == "scores_mlb_wp"
        assert page.locator(".sc-mark").count() == 5
        box = frame.bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + 60)
        tip = page.locator(".sc-tip")
        assert tip.is_visible() and "%" in tip.inner_text()
        assert page.locator(".sc-cross").get_attribute("visibility") == "visible"
        # a tap pins it; moving away keeps it; a second tap clears it
        page.mouse.click(box["x"] + box["width"] * 0.25, box["y"] + 60)
        pinned = tip.inner_text()
        page.mouse.move(box["x"] + box["width"] * 0.9, box["y"] + 60)
        assert tip.inner_text() == pinned
        page.mouse.click(box["x"] + box["width"] * 0.9, box["y"] + 60)
        assert not tip.is_visible()
        fr.focus()
        page.keyboard.press("ArrowRight")
        assert tip.is_visible() and tip.inner_text().startswith("Top 1")
        page.keyboard.press("Escape")
        assert not tip.is_visible()
        # the chart is drawn at the container's pixel width
        assert abs(frame.bounding_box()["width"] - fr.bounding_box()["width"]) <= 1
        _no_errors(page)


def test_box_score_prints_pitch_rates_from_the_game_file(site, pw):
    with serve_site(site) as base, scores_page(base, pw, width=1280, hash_="#game=849845&tab=box") as page:
        page.wait_for_selector(".sc-box a.sc-player")   # after the player-links repaint, so no node goes stale
        heads = page.locator(".sc-box thead").all_inner_texts()
        assert any("P/AB" in h for h in heads) and any("P/IP" in h for h in heads)
        assert not any("P/PA" in h for h in heads)
        # each header is a Library term and right-aligned like the stat cells
        gl = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
        ids = {e["id"] for e in gl["entries"]}
        for slug in ("pitches_per_ab", "pitches_per_ip"):
            th = page.locator(f'.sc-box th:has([data-gl="{slug}"])').first
            assert slug in ids and th.evaluate("e => getComputedStyle(e).textAlign") == "right"
        row = page.locator(".sc-box tbody tr", has_text="Kyle Schwarber").first
        assert row.locator("td").nth(6).inner_text() == "6.3"  # 19 pitches over 3 AB
        row = page.locator(".sc-box tbody tr", has_text="Brewer Hicklen").first
        assert row.locator("td").nth(0).inner_text() == "0" and row.locator("td").nth(6).inner_text() == "-"
        row = page.locator(".sc-box tbody tr", has_text="Chris Sale").first.inner_text()
        assert "\t15.0\t" in row or " 15.0 " in row, row
        row = page.locator(".sc-box tbody tr", has_text="Bryce Harper").first.inner_text()
        assert "5.0" in row, row
        # the sticky name column stays put inside the scrolling frame at 390
        page.set_viewport_size({"width": 390, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert page.evaluate("getComputedStyle(document.querySelector('.sc-box tbody th')).position") == "sticky"


def test_twelve_innings_scroll_inside_the_line_score(site, pw):
    with serve_site(site) as base, scores_page(base, pw, hash_="#date=2026-09-29&game=900007") as page:
        page.wait_for_selector(".sc-line-wide")
        assert page.evaluate("(() => { const f = document.querySelector('.sc-line-wide');"
                             " return f.scrollWidth > f.clientWidth; })()")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert "Final, 12 innings" in page.locator(".sc-state-big").text_content()


_TARGETS = """() => {
  const bad = [];
  const big = '.sc-day, .sc-arrow, .sc-tab, .sc-filters .sc-btn, .sc-dateinput';
  document.querySelectorAll('#scores-app-root a, #scores-app-root button, #scores-app-root input, #scores-app-root summary').forEach(el => {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const inline = el.tagName === 'A' && getComputedStyle(el).display === 'inline' && el.closest('p, li, dd, td');
    const need = el.matches(big) ? 44 : 24;
    if (!inline && r.height < need - 0.5) bad.push([el.className || el.tagName, el.textContent.trim().slice(0, 30), r.height]);
  });
  const nested = document.querySelectorAll('#scores-app-root a a, #scores-app-root a button, #scores-app-root button a, #scores-app-root button button').length;
  return {bad, nested};
}"""


def test_targets_and_no_nested_interactive_elements(site, pw):
    with serve_site(site) as base, scores_page(base, pw, hash_=f"#date={TODAY}") as page:
        _wait_cards(page, 5)
        res = page.evaluate(_TARGETS)
        assert res["nested"] == 0 and res["bad"] == [], res
        for h in ("#game=849845", "#game=849845&tab=wp"):
            page.evaluate(f"location.hash = '{h}'")
            page.wait_for_selector(".sc-wp-frame svg" if h.endswith("wp") else "a.sc-player")
            res = page.evaluate(_TARGETS)
            assert res["nested"] == 0 and res["bad"] == [], (h, res)


def test_about_is_built_from_the_index(site, pw):
    with serve_site(site) as base, scores_page(base, pw, hash_="#about") as page:
        page.wait_for_selector(".sc-about")
        t = page.locator(".sc-about").inner_text()
        assert "It starts every game at 50 percent, so it is not a pregame forecast." in t
        assert "1,448,965 regular-season plays" in t and "0.1575" in t and "0.2498" in t
        assert "Stars of the Game is a rule, not an award." in t
        assert "Copyright 2026 MLB Advanced Media" in t or "MLB Advanced Media" in t


def test_the_fifty_percent_sentence_needs_every_pregame_value_at_500(tmp_path, pw):
    payloads = build_payloads()
    payloads["index.json"]["accuracy"]["mlb_wp"]["pregame_values"] = {"500": 3, "512": 1}
    payloads["latest.json"]["index_rev"] = sc.rev_of(payloads["index.json"])
    site = make_site(tmp_path / "site", payloads)
    with serve_site(site) as base, scores_page(base, pw, hash_="#about") as page:
        page.wait_for_selector(".sc-about")
        assert "50 percent" not in page.locator(".sc-about").inner_text()


def test_s4_state_when_latest_is_missing(tmp_path, pw):
    payloads = build_payloads()
    del payloads["latest.json"]
    site = make_site(tmp_path / "site", payloads)
    with serve_site(site) as base, scores_page(base, pw) as page:
        page.wait_for_function("/Scores are not available right now\\./.test(document.getElementById('scores-app-root').textContent)")


# --------------------------------------------------------------------------- #
# The October bracket (SCORES_4b)
# --------------------------------------------------------------------------- #
def _bracket(name="postseason_series_2026.json"):
    return sc.build_bracket(load(name), season=2026)


@pytest.fixture(scope="module")
def october_site(tmp_path_factory):
    return make_site(tmp_path_factory.mktemp("scores_october"), build_payloads(bracket=_bracket()))


_NO_PROB = """() => { const b = document.querySelector('.sc-bk');
  return {pct: b.textContent.indexOf('%') >= 0, model: b.querySelectorAll('[data-model-id]').length,
          futures: Array.from(b.querySelectorAll('a')).filter(a => /betting|futures/i.test(a.getAttribute('href'))).length}; }"""


def _chunk_requests(page):
    return [u for u in page._requests if "/assets/scores-bracket.js" in u]


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", (390, 768, 1024, 1280, 1440))
def test_the_bracket_view_prints_series_state_and_no_probability(october_site, pw, width, theme):
    with serve_site(october_site) as base, scores_page(base, pw, width=width, theme=theme, hash_="#bracket=2026") as page:
        page.wait_for_selector(".sc-bk .scb", timeout=15000)
        assert page.locator(".sc-bk .scb-round h3").all_inner_texts() == [
            "Wild Card Series", "Division Series", "Championship Series", "World Series"]
        assert page.locator(".sc-bk .scb-s").count() == 11
        assert page.locator("h2").first.text_content() == "2026 postseason"   # the banner uppercases it
        # MLB's placeholders print unlinked, never as a link
        unresolved = page.locator('.sc-bk [data-club-nolink="unresolved"]').all_inner_texts()
        assert "Winner of HOU and CWS" in unresolved and "NL Lower Seed" in unresolved
        assert page.locator('.sc-bk a[data-club-nolink], .sc-bk a:has-text("Winner of")').count() == 0
        assert page.locator('.sc-bk a.scb-club[href="/franchise/#team=CHW"]').count() >= 1
        f1 = page.locator(".sc-bk .scb-s").first.inner_text()
        assert "CHW leads 1-0" in f1 and "Game 1, September 29: CHW 6, HOU 3" in f1 and "If necessary" in f1
        # no probability of any kind, no model label, no Futures link (Part 8 8.D row 8)
        assert page.evaluate(_NO_PROB) == {"pct": False, "model": 0, "futures": 0}
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "horizontal page scroll"
        reqs = _chunk_requests(page)
        assert len(reqs) == 1 and f"?v={build_site._SCORES_BRACKET_VER}" in reqs[0], reqs
        _no_errors(page)


def test_the_chunk_loads_only_on_the_route_or_the_october_rail(october_site, pw):
    with serve_site(october_site) as base:
        # September 30 at 1440: no chip, no chunk
        with scores_page(base, pw, width=1440, hash_=f"#date={TODAY}") as page:
            _wait_cards(page, 5)
            assert page.locator('.sc-strip a[href="#bracket=2026"]').count() == 0
            assert _chunk_requests(page) == [] and page.locator(".scb").count() == 0
        # October 1 below 1400: the chip, no chunk
        for width in (390, 1280):
            with scores_page(base, pw, width=width, hash_="#date=2026-10-01") as page:
                _wait_cards(page, 4)
                chip = page.locator('.sc-strip a[href="#bracket=2026"]')
                assert chip.count() == 1 and chip.inner_text() == "Bracket"
                if width == 390:
                    assert chip.bounding_box()["height"] >= 44
                assert _chunk_requests(page) == [], width
                _no_errors(page)
        # October 1 at 1440: the rail leads with the compact bracket
        with scores_page(base, pw, width=1440, hash_="#date=2026-10-01") as page:
            page.wait_for_selector(".sc-railslot .scb-compact", timeout=15000)
            first = page.locator(".sc-railslot > aside").first
            assert first.get_attribute("aria-label") == "Bracket"
            assert first.locator('h2 a[href="#bracket=2026"]').count() == 1
            assert first.locator(".scb-games").count() == 0 and first.locator(".scb-line").count() == 11
            assert "%" not in first.inner_text() and first.locator("[data-model-id]").count() == 0
            assert len(_chunk_requests(page)) == 1
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            # the chip opens the full view and the back link returns
            page.locator('.sc-strip a[href="#bracket=2026"]').click()
            page.wait_for_selector(".sc-bk .scb:not(.scb-compact)")
            assert len(_chunk_requests(page)) == 1          # loaded once per page
            page.locator(".sc-back a").click()
            _wait_cards(page)
            _no_errors(page)


def test_no_bracket_block_leaves_the_rail_without_it_and_the_view_says_so(site, pw):
    with serve_site(site) as base:
        with scores_page(base, pw, width=1440, hash_="#date=2026-10-01") as page:
            _wait_cards(page, 4)
            page.wait_for_function("window.EephusScoresBracket && !document.querySelector('.sc-railslot .sc-bk')")
            assert page.locator('.sc-railslot aside[aria-label="Bracket"]').count() == 0
            _no_errors(page)
        with scores_page(base, pw, width=390, hash_="#bracket=2026") as page:
            page.wait_for_selector(".sc-bk .scb-none")
            assert page.locator(".sc-bk").inner_text() == "No bracket for this season in these files."
            _no_errors(page)


def test_the_mount_needs_no_page_route_or_fetch(pw):
    """STANDINGS_4 mounts the chunk unchanged: one function, an element and the block."""
    import re
    src = (ROOT / "assets" / "scores-bracket.js").read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", src, flags=re.S)       # the code, without its comments
    for absent in ("fetch(", "XMLHttpRequest", "location", "hashchange", "#bracket", "data-model-id", "%"):
        assert absent not in code, absent
    assert "futures" not in code.lower() and "betting" not in code.lower()
    browser = pw.chromium.launch()
    try:
        page = browser.new_page()
        reqs = []
        page.on("request", lambda r: reqs.append(r.url))
        page.set_content("<!doctype html><div id=m></div><div id=n></div>")
        page.add_script_tag(content=src)
        assert page.evaluate("Object.keys(window.EephusScoresBracket)") == ["mount"]
        drew = page.evaluate("b => window.EephusScoresBracket.mount(document.getElementById('m'), b)",
                             _bracket("postseason_series_2026-10-07.json"))
        none = page.evaluate("window.EephusScoresBracket.mount(document.getElementById('n'), null, {compact: 1})")
        assert drew is True and none is False and reqs == []
        text = page.inner_text("#m")
        for want in ("CHW wins 2-0", "ATL wins 2-1", "TBR leads 2-0", "LAD leads 2-1", "Game 2, September 30: BOS 2, NYY 9",
                     "If necessary"):
            assert want in text, want
        assert "%" not in text and page.inner_html("#n") == ""
        # the clinching club is bold with a screen-reader word; the game link defaults to /scores/
        assert page.locator("#m .scb-c.is-won strong").count() == 4
        assert page.locator("#m .scb-c.is-won .sr-only").first.inner_text().strip() == "winner"
        assert page.locator('#m a[href="/scores/#game=849849"]').count() == 1
    finally:
        browser.close()


# --------------------------------------------------------------------------- #
# SCORES_6: the pregame context on the fixture board
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def pregame_site(tmp_path_factory):
    return make_site(tmp_path_factory.mktemp("scores_pregame_site"), pregame_payloads())


def test_the_pregame_block_is_built_from_the_fixture_board():
    p = pregame_payloads()
    cards = {c["pk"]: c for c in p[f"{TODAY}.json"]["games"]}
    board = load("betting_board.json")
    row = next(r for r in board["team_bets"] if r["game_pk"] == 900010)
    m = cards[900010]["pre"]["model"]
    assert (m["p_home"], m["p_away"]) == (row["model"]["p_home"], row["model"]["p_away"])
    assert m["sentence"] == board["status"]["model_verdict_sentence"] and m["state"] == "unvalidated"
    assert cards[900011]["pre"]["model"] == {"absent": "starter"}
    assert cards[849848]["pre"]["model"] == {"absent": "season"}
    assert cards[900010]["pre"]["efv"] == {str(EFV_ID): 51.5}
    assert cards[900010]["pre"]["home"] == {"sem_plus": 118, "sem_season": 2026, "hook_median_pitches": 87.5,
                                            "hook_season": 2026}
    assert cards[900010]["pre"]["away"]["two_start"] == {"n": 2, "projected": True}
    assert cards[900010]["pre"]["park_runs"] == 102 and cards[900010]["pre"]["dfs"] is True
    for pk, c in cards.items():
        if c["state"] not in ("scheduled", "pregame", "delayed"):
            assert "pre" not in c, pk


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", WIDTHS)
def test_the_pregame_views_have_no_page_scroll_and_no_console_errors(pregame_site, pw, width, theme):
    with serve_site(pregame_site) as base, scores_page(base, pw, width=width, theme=theme,
                                                       hash_=f"#date={TODAY}") as page:
        _wait_cards(page, 7)
        page.wait_for_selector('article[data-pk="900010"] [data-model-id="betting_game_prob"]')
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "horizontal page scroll"
        for h in ("#game=900010", "#game=900011", "#game=849848"):
            page.evaluate(f"location.hash = '{h}'")
            page.wait_for_selector(".sc-pregame")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (h, "page scroll")
        _no_errors(page)


def test_the_pregame_panel_prints_the_board_verbatim_with_its_labels(pregame_site, pw):
    board = load("betting_board.json")
    with serve_site(pregame_site) as base, scores_page(base, pw, hash_=f"#date={TODAY}") as page:
        _wait_cards(page, 7)
        card = page.locator('article[data-pk="900010"]')
        card.locator('[data-model-id="betting_game_prob"]').wait_for()
        assert "Eephus model: PHI 47.0%, ATL 53.0%" in card.inner_text()
        assert "Eephus model, unvalidated, provisional" in card.inner_text()
        assert page.locator(".sc-betnote .betting-disclaimer").count() == 1
        assert page.locator(".betting-disclaimer").count() == 1
        # the club links go through the one resolver
        assert card.locator('a.club-link[href="/franchise/#team=ATL"]').count() == 1
        for pk in (900011, 849848):
            assert page.locator(f'article[data-pk="{pk}"] [data-model-id]').count() == 0, pk
        page.evaluate("location.hash = '#game=900010'")
        page.wait_for_selector(".sc-pregame .sc-verdict")
        panel = page.locator(".sc-panel").inner_text()
        for want in ("Eephus model", "PHI 47.0%", "ATL 53.0%", "Eephus model, unvalidated, provisional",
                     "Shown as the Sports Betting board serves it; this page prices nothing.",
                     "PHI probable Sánchez: SEM+ 104 (2026 season)", "ATL probable Mahle: SEM+ 118 (2026 season)",
                     "MLB Stats SEM+, validated", "Sánchez: two starts in the next seven days, one projected (Fantasy)",
                     "ATL starters leave at a median 88 pitches this season", "In-Game Management, provisional",
                     "PHI starters leave at a median 91 pitches this season",
                     "Park runs index 102 (ATL home park; Baseball Savant, 3 seasons; 100 is neutral)",
                     "PHI players", "ATL players", "eFV 52", "PROSPX eFV, provisional"):
            assert want in panel, want
        assert page.locator(".sc-verdict").evaluate("e => e.textContent") == board["status"]["model_verdict_sentence"]
        assert page.locator('.sc-pregame a[href="/betting/#section=teams"]').count() == 1
        assert page.locator(".sc-panel .betting-disclaimer").count() == 1
        assert page.locator('.sc-panel a[href="/fantasy/#m=dfs&team=ATL"]').count() == 1
        # eFV only for the eFV v2 prospect: never the debuted grade, the capped one or consensus FV
        assert page.locator(".sc-efv").count() == 1 and panel.count("eFV ") == 1
        assert "45" not in page.locator(".sc-efv").inner_text()
        page.evaluate("location.hash = '#game=900011'")
        page.wait_for_function("/different listed starter/.test(document.querySelector('.sc-panel').textContent)")
        assert page.locator('.sc-panel [data-model-id="betting_game_prob"]').count() == 0
        assert page.locator(".betting-disclaimer").count() == 0
        page.evaluate("location.hash = '#game=849848'")
        page.wait_for_function("/regular-season games only/.test(document.querySelector('.sc-panel').textContent)")
        assert page.locator('.sc-panel [data-model-id="betting_game_prob"]').count() == 0
        _no_errors(page)


def test_the_pregame_card_stays_inside_its_floor_at_390(pregame_site, pw):
    with serve_site(pregame_site) as base, scores_page(base, pw, hash_=f"#date={TODAY}") as page:
        _wait_cards(page, 7)
        page.wait_for_selector('article[data-pk="900010"] [data-model-id="betting_game_prob"]')
        rows = {c["pk"]: c for c in page.evaluate(_MEASURE)}
        c = rows[900010]
        assert c["slot"] == "prer" and c["floor"] == SLOT_MIN["prer"] and c["natural"] <= c["floor"] + 0.5, c
        assert not c["clipped"], c


# --------------------------------------------------------------------------- #
# SCORES_7b: the pixel art (owner SC7-2)
# --------------------------------------------------------------------------- #
#: Every sprite is drawn on whole cells: its CSS size is its viewBox times a whole number, crispEdges on.
_SPRITES = """() => Array.from(document.querySelectorAll(
    '#scores-app-root svg.px-sprite, #scores-app-root svg.px-key, #scores-app-root svg.scba-cup')).map(s => {
  const vb = s.viewBox.baseVal, r = s.getBoundingClientRect();
  return {cls: s.getAttribute('class'), kx: r.width / vb.width, ky: r.height / vb.height,
          crisp: s.getAttribute('shape-rendering') === 'crispEdges', label: s.getAttribute('aria-label')};
})"""


def _whole(sprites):
    assert sprites, "no sprite drawn"
    for sp in sprites:
        assert sp["crisp"] and sp["kx"] == sp["ky"] and sp["kx"] == int(sp["kx"]) and sp["kx"] >= 1, sp


_FILLS = """() => { const s = document.querySelector('.sc-endpx svg');
  const tok = n => { const d = document.createElement('i'); d.style.color = 'var(' + n + ')'; document.body.appendChild(d);
    const v = getComputedStyle(d).color; d.remove(); return v; };
  return {on: getComputedStyle(s.querySelector('.px-on')).fill, gold: tok('--text-gold'),
          ink: getComputedStyle(s.querySelector('.px-ink')).fill, primary: tok('--text-primary')}; }"""


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_pixel_diamond_on_live_and_final_cards(site, pw, theme):
    with serve_site(site) as base, scores_page(base, pw, theme=theme, hash_=f"#date={TODAY}") as page:
        _wait_cards(page, 5)
        live = page.locator('article[data-pk="849846"] [data-hook="diamond"] svg')
        assert live.get_attribute("role") == "img"
        assert live.get_attribute("aria-label") == "Runners on first and third, 0 outs, 0 balls, 1 strike"
        # the count still prints in words beside the lamps
        assert "Count 0-1" in page.locator('article[data-pk="849846"] .sc-sit').text_content()
        _whole(page.evaluate(_SPRITES))
        page.evaluate("location.hash = '#date=2026-09-29'")
        page.wait_for_selector('article[data-pk="849845"] .sc-endpx svg')
        end = page.locator('article[data-pk="849845"] .sc-endpx svg')
        assert end.get_attribute("aria-label") == "Last play, top of the 9th: 3 outs, bases empty"
        # the final's sprite sits in the head row, which stays one 24 px line
        assert page.locator('article[data-pk="849845"] .sc-head').bounding_box()["height"] <= 25
        _whole(page.evaluate(_SPRITES))
        # tokens only: lit cells take --text-gold, letters --text-primary
        fills = page.evaluate(_FILLS)
        assert fills["on"] == fills["gold"] and fills["ink"] == fills["primary"], fills
        _no_errors(page)


_PLATES = """() => { const t = document.querySelector('.sc-line-wide table'), td = t.querySelector('tbody td.sc-inn'),
  r = t.querySelector('tbody td.sc-r');
  return {model: getComputedStyle(t).borderCollapse, bg: getComputedStyle(td).backgroundColor,
          rbg: getComputedStyle(r).backgroundColor}; }"""


def test_the_game_head_scoreboard_and_its_screen_reader_text(site, pw):
    with serve_site(site) as base, scores_page(base, pw, hash_="#date=2026-09-29&game=849845") as page:
        page.wait_for_selector(".sc-line-wide")
        cap = page.locator(".sc-line-wide caption").text_content()
        assert cap == "Line score: runs by inning, then runs, hits and errors"
        # a manual scoreboard: separate plates on the panel colour, the R plates inverted
        st = page.evaluate(_PLATES)
        assert st["model"] == "separate" and st["bg"] != st["rbg"], st
        # nine innings and R H E fit a phone once the club name steps aside
        assert page.evaluate("(() => { const f = document.querySelector('.sc-line-wide');"
                             " return f.scrollWidth <= f.clientWidth; })()")
        head = page.locator('.sc-ghead [data-hook="diamond"] svg')
        assert head.get_attribute("aria-label") == "Last play, top of the 9th: 3 outs, bases empty"
        _whole(page.evaluate(_SPRITES))
        _no_errors(page)


@pytest.mark.parametrize("width", (390, 1280))
def test_the_stepped_win_probability_line_and_the_biggest_swing(site, pw, width):
    import re
    with serve_site(site) as base, scores_page(base, pw, width=width, hash_="#game=849845&tab=wp") as page:
        page.wait_for_selector(".sc-wp-frame svg")
        d = page.locator(".sc-wp-line").get_attribute("d")
        # a step line on whole pixels: across, then up or down, never a slope
        assert re.fullmatch(r"(M-?[0-9]+ -?[0-9]+|H-?[0-9]+|V-?[0-9]+)+", d), d[:120]
        assert page.locator(".sc-wp-svg").get_attribute("shape-rendering") == "crispEdges"
        assert page.locator(".sc-mark").count() == 5 and page.locator(".sc-mark.is-top").count() == 1
        lab = page.locator(".sc-swing text").text_content()
        assert re.fullmatch(r"Biggest swing: [A-Z]{2,3} [+-][0-9]+", lab), lab
        # the label plate stays inside the chart
        box, frame = page.locator(".sc-swing .sc-plate").bounding_box(), page.locator(".sc-wp-svg").bounding_box()
        assert box["x"] >= frame["x"] and box["x"] + box["width"] <= frame["x"] + frame["width"] + 0.5
        assert page.locator('[data-hook="wp-sprite"] .sc-wp-key').count() == 1
        _whole(page.evaluate(_SPRITES))
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        _no_errors(page)


def test_the_live_end_marker_blinks_only_without_reduced_motion(site, pw):
    with serve_site(site) as base:
        for motion, want in (("no-preference", "px-blink"), ("reduce", "none")):
            browser = pw.chromium.launch()
            try:
                ctx = browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion=motion)
                page = ctx.new_page()
                page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base[:-1]) else r.abort())
                page.goto(base + "scores/#game=849846&tab=wp", wait_until="load")
                page.wait_for_selector(".sc-wp-frame svg .sc-end")
                assert page.evaluate("getComputedStyle(document.querySelector('.sc-end')).animationName") == want
            finally:
                browser.close()


_BOXES = "Array.from(document.querySelectorAll('.scba-box')).map(b => b.getBoundingClientRect().toJSON())"


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", (390, 1280))
def test_the_bracket_art_draws_the_tree_with_chips_pips_and_the_trophy(october_site, pw, width, theme):
    with serve_site(october_site) as base, scores_page(base, pw, width=width, theme=theme, hash_="#bracket=2026") as page:
        page.wait_for_selector(".sc-bk .scb-art", timeout=15000)
        assert page.locator(".sc-bk .scb-art").get_attribute("aria-hidden") == "true"
        assert page.locator(".scb-art .scba-box").count() == 11 and page.locator(".scb-art .scba-cup").count() == 1
        # pips: two wins take a best-of-3, so a Wild Card box has four (two per club)
        assert page.locator(".scb-art .scba-box").first.locator(".scba-pip").count() == 4
        # every box sits inside the view and no two boxes overlap
        boxes = page.evaluate(_BOXES)
        for i, a in enumerate(boxes):
            assert a["x"] >= 0 and a["x"] + a["width"] <= width
            for b in boxes[i + 1:]:
                assert (a["x"] + a["width"] <= b["x"] or b["x"] + b["width"] <= a["x"] or
                        a["y"] + a["height"] <= b["y"] or b["y"] + b["height"] <= a["y"]), (a, b)
        # the World Series box sits between the two league series that feed it, the trophy over it
        ws, cup = boxes[-1], page.locator(".scba-cup").bounding_box()
        assert boxes[8]["y"] < ws["y"] < boxes[9]["y"] and cup["y"] + cup["height"] <= ws["y"] + 0.5
        _whole(page.evaluate(_SPRITES))
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        _no_errors(page)


def test_the_bracket_art_without_a_hub_and_when_the_rounds_make_no_tree(pw):
    src = (ROOT / "assets" / "scores-bracket.js").read_text(encoding="utf-8")
    browser = pw.chromium.launch()
    try:
        page = browser.new_page()
        page.set_content("<!doctype html><div id=m></div><div id=n></div><div id=c></div>")
        page.add_script_tag(content=src)
        b = _bracket()
        page.evaluate("b => window.EephusScoresBracket.mount(document.getElementById('m'), b)", b)
        assert page.locator("#m .scba-box").count() == 11 and page.locator("#m img").count() == 0
        # three Wild Card series cannot feed four Division Series: the art stays out, the rounds stay in
        bad = copy.deepcopy(b)
        bad["rounds"][0]["series"] = bad["rounds"][0]["series"][:3]
        page.evaluate("b => window.EephusScoresBracket.mount(document.getElementById('n'), b)", bad)
        assert page.locator("#n .scb-art").count() == 0 and page.locator("#n .scb-s").count() == 10
        page.evaluate("b => window.EephusScoresBracket.mount(document.getElementById('c'), b, {compact: 1})", b)
        assert page.locator("#c .scb-art").count() == 0
    finally:
        browser.close()
