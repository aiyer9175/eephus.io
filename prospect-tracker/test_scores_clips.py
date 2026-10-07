# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Scores clips (SCORES_4a_VIDEO; plan 6.0 to 6.9, 8.4 and 12).

Owner answers: SC-VIDEO (a) MLB's own embed player (streamable.com/m/<slug>);
SC-PAID (a) the tripwire; SC-CARDVID (a) a duration chip on cards, no player.
Hermetic: the content fixtures are trimmed from the saved StatsAPI samples
(their prose keys hold a sentinel), the job runs on a fake StatsAPI in temp
directories, and nothing here touches the network, the repo's data/ or a real
.cache/scores/.

PINNED: the join of 6.1 (16, 9 and 3 result matches on 849845, 824055 and the
live 849846; 62 items of 775296 parse; a pickoff attempt's clip keeps its own
event and never captions the result; no guid-less item matches a play); the
clip object of 8.4 under branch (a) (`embed` is streamable.com/m/<slug>, no
mp4, hls or vtt); the 6.2 file pick on multi-asset items; `feeds_sportsbook`
from the taxonomy; an unknown media host gives F1 and `new_media_host`; an ABS
reel never becomes a star clip; a later read replaces the clip set; the kill
switch through the constant, EEPHUS_SCORES_EMBED=0 and the EMBED_OFF file; the
runtime fail-safe on a served `gating: true`; the SC-PAID tripwire (fails in
dev and CI, skips under EEPHUS_DEPLOY_RUN=1); the CSP guard; the content
cadence of 6.6; the budgets of 8.1.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import scores_core as sc  # noqa: E402
import scores_job as job  # noqa: E402
from test_scores_job import (FakeAPI, FakeClock, NOW, _game, base_games, base_payloads, env,  # noqa: E402,F401
                             load, run_once, schedule_of, seed_state)

UTC = timezone.utc
LG = None
PICKOFF_PLAY_ID = "44b66bc3-920e-3584-90d3-df6957d8faf5"     # 849845, ab 31: Pickoff Attempt 2B
TRIPWIRE_MSG = "S8-1 was decided for a non-commercial site; re-confirm embedding before the Diamond gate opens"
TRIPWIRE_SKIP = "OWNER ACTION PENDING: S8-1 re-confirmation before the Diamond gate"


def items(name):
    return load(name)["highlights"]["highlights"]["items"]


def content_with(name, extra=(), drop=()):
    doc = copy.deepcopy(load(name))
    its = doc["highlights"]["highlights"]["items"]
    its[:] = [it for it in its if it.get("slug") not in drop] + [copy.deepcopy(x) for x in extra]
    return doc


def pickoff_item():
    """A clip of 849845's ab 31 pickoff attempt: an earlier event of a plate
    appearance that ended in a flyout (the fixture plan 12 asks for)."""
    base = next(it for it in items("content_849845.json") if it.get("guid"))
    it = copy.deepcopy(base)
    it.update({"guid": PICKOFF_PLAY_ID, "slug": "max-fried-pickoff-attempt-to-second-x4410",
               "mediaPlaybackId": "aaaa0001-pickoff-csvm-diamondgcp-asset", "duration": "00:00:14"})
    for p in it["playbacks"]:
        p["url"] = re.sub(r"/[0-9a-f]{8}-[0-9a-f]{8}-[0-9a-f]{8}-csvm-diamondgcp-asset",
                          "/aaaa0001-pickoff-csvm-diamondgcp-asset", p["url"])
    return it


def final_file(content="content_849845.json", **kw):
    return sc.build_game_file(_game(849845, "F"), load("wp_849845_full.json"), load("box_849845.json"),
                              load("league_constants_2026.json"), generated_at="2026-09-30T00:00:00Z",
                              feed=load("feed_849845.json"),
                              content=load(content) if isinstance(content, str) else content, **kw)


# --------------------------------------------------------------------------- #
# The join (plan 6.1)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("content,wp,pk,want", [
    ("content_849845.json", "wp_849845_full.json", 849845, 16),
    ("content_849845.json", "wp_849845_ext.json", 849845, 16),       # the job's fields= form
    ("content_824055.json", "wp_824055_playids.json", 824055, 9),
    ("content_849846_live.json", "wp_849846_live.json", 849846, 3),
])
def test_result_matches_on_the_sampled_games(content, wp, pk, want):
    w = load(wp)
    j = sc.join_clips(load(content), w, pk=pk)
    assert j["log"]["matched"] == want == len(j["result"])
    ids = {}
    for p in sc.complete_elements(w):
        pids = [e.get("playId") for e in p.get("playEvents") or [] if e.get("playId")]
        ids[sc._ab(p)] = pids
    for ab, cid in j["result"].items():
        c = j["clips"][cid]
        assert c["play_id"] in ids[ab] and c["play_id"] == ids[ab][-1], (ab, c["play_id"])
        assert c["event"] == "result" and c["kind"] == "play" and c["match"] == "play"


def test_775296_parses_its_62_items_and_finds_the_game_videos():
    its = sc._items_of(load("content_775296.json"))
    assert len(its) == 62
    j = sc.join_clips(load("content_775296.json"), [], pk=775296)
    assert j["result"] == {} and j["events"] == {}
    assert j["clips"][j["recap"]]["kind"] == "recap" and j["clips"][j["condensed"]]["kind"] == "condensed"


def test_no_guidless_item_matches_a_play_and_nothing_is_guessed():
    j = sc.join_clips(load("content_849845.json"), load("wp_849845_full.json"), pk=849845)
    guids = {it.get("guid") for it in items("content_849845.json") if it.get("guid")}
    for c in j["clips"].values():
        if c["kind"] == "play":
            assert c["play_id"] in guids
    # an interview tagged with a star's player id never becomes a play clip
    assert all(c["kind"] in ("play", "recap", "condensed") for c in j["clips"].values())


def test_a_pickoff_attempt_clip_keeps_its_event_and_never_captions_the_result():
    gf = final_file(content_with("content_849845.json", extra=[pickoff_item()]))
    row = next(r for r in gf["plays"] if r["ab"] == 31)
    assert row["clip"] is None, "the pickoff clip captioned the flyout"
    assert row["event_clips"] == [{"event": "pickoff_attempt", "label": "Pickoff attempt, bottom 4",
                                   "clip": "aaaa0001-pickoff-csvm-diamondgcp-asset"}]
    c = gf["clips"]["aaaa0001-pickoff-csvm-diamondgcp-asset"]
    assert c["event"] == "pickoff_attempt" and c["play_id"] == PICKOFF_PLAY_ID and c["dur_s"] == 14
    # Biggest plays and the stars use result clips only
    assert all(b["clip"] != c["id"] for b in gf["plays_big"])
    assert all(s["clip"] != c["id"] for s in gf["stars"])
    assert sc.validate_payload("game", gf, name="games/849845.json")["ok"]
    # the fields= form names the attempt by its short call label
    ext = sc.join_clips(content_with("content_849845.json", extra=[pickoff_item()]), load("wp_849845_ext.json"),
                        pk=849845)
    assert ext["events"][31][0]["event"] == "pickoff_attempt"


def test_ties_prefer_captions_then_in_game_highlight_then_date_then_slug():
    a = copy.deepcopy(next(it for it in items("content_849845.json") if it.get("guid") and it.get("cclocationVtt")))
    b = copy.deepcopy(a)
    b.update({"slug": "aaa-first-by-slug", "mediaPlaybackId": "bbbb0002-x-csvm-diamondgcp-asset",
              "cclocationVtt": None, "date": "2000-01-01T00:00:00Z"})
    j = sc.join_clips({"items": [b, a]}, load("wp_849845_full.json"), pk=849845)
    assert list(j["clips"]) == [a["mediaPlaybackId"]]           # captions beat an earlier date and slug
    c = copy.deepcopy(a)
    c.update({"slug": "zzz-later", "mediaPlaybackId": "cccc0003-x-csvm-diamondgcp-asset"})
    d = copy.deepcopy(a)
    d.update({"slug": "aaa-earlier", "mediaPlaybackId": "dddd0004-x-csvm-diamondgcp-asset"})
    j = sc.join_clips({"items": [c, d]}, load("wp_849845_full.json"), pk=849845)
    assert list(j["clips"]) == ["dddd0004-x-csvm-diamondgcp-asset"]


# --------------------------------------------------------------------------- #
# The clip object (plan 8.4), branch (a)
# --------------------------------------------------------------------------- #
def test_branch_a_clip_object_holds_the_embed_and_no_media_file():
    assert sc.VIDEO_BRANCH == "a"
    gf = final_file()
    assert gf["clips"], "no clip attached"
    for c in gf["clips"].values():
        slug = c["page"].rsplit("/", 1)[1]
        assert c["page"] == f"https://www.mlb.com/video/{slug}" and re.fullmatch(r"[a-z0-9-]+", slug)
        assert c["embed"] == f"https://streamable.com/m/{slug}"
        assert not {"mp4", "hls", "vtt"} & set(c), c
        assert set(c) == {"id", "kind", "match", "play_id", "event", "embed", "feeds_sportsbook", "poster",
                          "dur_s", "posted_at", "seen_at", "page"}
        assert c["poster"]["w480"].startswith("https://img.mlbstatic.com/mlb-images/image/upload/w_480,h_270")
        assert c["poster"]["w960"].startswith("https://img.mlbstatic.com/mlb-images/image/upload/w_960,h_540")
        assert 1 <= c["dur_s"] <= 3600
        assert len(sc.dumps(c).encode("utf-8")) <= 1.2 * 1024, "one clip object over its 1.2 KB budget"
    text = sc.dumps(gf)
    assert "PROSE-SENTINEL" not in text, "MLB prose reached the game file"
    for bad in ("highBit", "trickplay", "portrait", "HTTP_CLOUD_WIRED", ".mp4", ".m3u8", ".vtt", "16000K"):
        assert bad not in text, bad


def test_the_6_2_file_pick_reads_the_items_own_asset():
    it = next(i for i in items("content_849845.json") if i["slug"].startswith("jesus-luzardo-in-play-out-s-to-austin-ri"))
    mp4 = [p["url"] for p in it["playbacks"] if p["name"] == "mp4Avc"]
    assert len(mp4) == 3 and it["mediaPlaybackId"] not in mp4[0]
    assert it["mediaPlaybackId"] in sc.pick_file(it, "mp4Avc")
    assert sc.pick_file({"playbacks": [{"name": "mp4Avc", "url": "https://x/a.mp4"}], "mediaPlaybackId": "zz"},
                        "mp4Avc") == "https://x/a.mp4"


def test_feeds_sportsbook_comes_from_the_taxonomy():
    j = sc.join_clips(load("content_849845.json"), load("wp_849845_full.json"), pk=849845)
    plays = [c for c in j["clips"].values() if c["kind"] == "play"]
    assert plays and all(c["feeds_sportsbook"] for c in plays)           # 16 of 16 play clips carry fan-duel
    assert j["clips"][j["recap"]]["feeds_sportsbook"] is False
    assert set(sc.SPORTSBOOK_TAGS) == {"fan-duel", "bet-mgm"}
    betmgm = next(it for it in items("content_824055.json") if "bet-mgm" in sc._taxonomy(it))
    tax_only = copy.deepcopy(betmgm)
    tax_only["keywordsAll"] = [k for k in tax_only["keywordsAll"] if k.get("value") != "fan-duel"]
    assert sc.clip_object(tax_only, kind="recap", match="game")["feeds_sportsbook"] is True


def test_an_unknown_media_host_gives_f1_and_new_media_host():
    it = copy.deepcopy(next(i for i in items("content_849845.json") if i.get("guid")))
    for p in it["playbacks"]:
        p["url"] = p["url"].replace("mlb-cuts-diamond.mlb.com", "darkroom-clips.mlb.com")
    notes: dict = {}
    c = sc.clip_object(it, kind="play", match="play", notes=notes)
    assert c["embed"] is None and c["page"].startswith("https://www.mlb.com/video/")
    assert "darkroom-clips.mlb.com" in notes["new_media_host"]
    j = sc.join_clips({"items": [it]}, load("wp_849845_full.json"), pk=849845)
    assert j["log"]["new_media_host"] == ["darkroom-clips.mlb.com"] and j["log"]["f1"] == 1
    # a poster off the allowlisted CDN is dropped, never stored
    it2 = copy.deepcopy(next(i for i in items("content_849845.json") if i.get("guid")))
    it2["image"] = {"templateUrl": None, "cuts": [{"width": 480, "height": 270, "src": "https://evil.example.com/x.jpg"}]}
    notes = {}
    assert sc.clip_object(it2, kind="play", match="play", notes=notes)["poster"] is None
    assert notes["new_media_host"] == ["evil.example.com"]


def test_a_bad_slug_or_missing_id_drops_the_item():
    it = copy.deepcopy(next(i for i in items("content_849845.json") if i.get("guid")))
    it["slug"] = "Bad Slug?"
    assert sc.clip_object(it, kind="play", match="play") is None
    it = copy.deepcopy(next(i for i in items("content_849845.json") if i.get("guid")))
    it["mediaPlaybackId"] = None
    assert sc.clip_object(it, kind="play", match="play") is None
    assert sc.parse_duration("00:00:29") == 29 and sc.parse_duration("01:00:01") is None
    assert sc.parse_duration("bad") is None and sc.parse_duration("00:00:00") is None


# --------------------------------------------------------------------------- #
# Attach (plan 8.3): Biggest plays, stars, the card
# --------------------------------------------------------------------------- #
def test_biggest_plays_stars_and_the_card_read_result_clips():
    gf = final_file()
    res = {r["ab"]: r["clip"] for r in gf["plays"]}
    for b in gf["plays_big"]:
        assert b["clip"] == res[b["ab"]]
        assert (b["clip_state"] is None) == bool(b["clip"])
        assert b["clip_state"] in (None, "none")                  # final, no pending flag from the job
    assert [b["clip"] is not None for b in gf["plays_big"]] == [True, True, True, False, False]
    # stars are hitters here: each gets the clip of his highest-credit plate appearance
    by = {s["name"]: s["clip"] for s in gf["stars"]}
    assert all(by.values()), by
    riley = next(s for s in gf["stars"] if s["name"].endswith("Riley"))
    assert gf["clips"][riley["clip"]]["page"].endswith("jhoan-duran-in-play-run-s-to-austin-riley-kkhhvg-x2885")
    card = gf["card"]
    assert card["top_play"]["clip_s"] == 29
    assert card["videos"] == {"recap_s": 180, "condensed_s": 1113}
    # every referenced clip resolves and nothing else is stored
    refs = {r["clip"] for r in gf["plays"] if r["clip"]} | {b["clip"] for b in gf["plays_big"] if b["clip"]} | \
        {s["clip"] for s in gf["stars"] if s["clip"]}
    refs |= {c["id"] for c in gf["clips"].values() if c["kind"] in ("recap", "condensed")}
    assert set(gf["clips"]) == refs
    assert sc.validate_payload("game", gf, name="games/849845.json")["ok"]
    assert len(sc.dumps(gf).encode("utf-8")) <= 80 * 1024
    # the date file carries durations only
    date = sc.build_date_file("2026-09-29", [card], {849845: gf}, generated_at="2026-09-30T00:00:00Z")
    assert sc.find_urls(date) == []
    assert sc.validate_payload("date", date, name="2026-09-29.json")["ok"]


def test_clip_state_pending_while_a_clip_may_still_post():
    gf = final_file(clips_pending=True)
    assert [b["clip_state"] for b in gf["plays_big"]][3:] == ["pending", "pending"]
    no_read = sc.build_game_file(_game(849845, "F"), load("wp_849845_full.json"), load("box_849845.json"),
                                 load("league_constants_2026.json"), generated_at="2026-09-30T00:00:00Z")
    assert all(b["clip_state"] == "pending" and b["clip"] is None for b in no_read["plays_big"])
    old = sc.build_game_file(_game(849845, "F"), load("wp_849845_full.json"), load("box_849845.json"),
                             load("league_constants_2026.json"), generated_at="2026-09-30T00:00:00Z",
                             clips_pending=False)
    assert all(b["clip_state"] == "none" for b in old["plays_big"])


def test_a_pitcher_star_takes_his_one_player_reel_and_never_an_abs_reel():
    j = sc.join_clips(load("content_849845.json"), load("wp_849845_full.json"), pk=849845)
    assert set(j["reels"]) == {519242, 666200}                 # Sale and Luzardo, neither an ABS reel
    gf = final_file()
    sale = {"rank": 3, "id": 519242, "name": "Chris Sale", "team": "ATL", "score": 1, "basis": "runs",
            "why": "", "clip": None}
    gf["stars"][2] = sale
    sc.attach_clips(gf, j, load("wp_849845_full.json"), load("box_849845.json"), pending=False)
    c = gf["clips"][gf["stars"][2]["clip"]]
    assert c["kind"] == "reel" and c["match"] == "player" and "chris-sale-strikes-out-nine" in c["page"]
    # an ABS reel tagged with one player and a pitching-reel tag never becomes his clip
    abs_reel = copy.deepcopy(next(it for it in items("content_849845.json")
                                  if {"abs", "challenge"} <= sc._taxonomy(it)))
    abs_reel["keywordsAll"].append({"type": "taxonomy", "value": "highlight-reel-pitching"})
    abs_reel["keywordsAll"] = [k for k in abs_reel["keywordsAll"] if k["type"] != "player_id"] + \
        [{"type": "player_id", "value": "519242"}]
    j2 = sc.join_clips({"items": [abs_reel]}, load("wp_849845_full.json"), pk=849845)
    assert j2["reels"] == {}
    gf2 = final_file({"highlights": {"highlights": {"items": [abs_reel]}}})
    gf2["stars"][2] = dict(sale)
    sc.attach_clips(gf2, j2, load("wp_849845_full.json"), load("box_849845.json"), pending=False)
    assert gf2["stars"][2]["clip"] is None or gf2["clips"][gf2["stars"][2]["clip"]]["kind"] != "reel"


def test_a_later_read_replaces_the_clip_set():
    early = content_with("content_849845.json")
    riley = next(it for it in early["highlights"]["highlights"]["items"]
                 if it["slug"] == "jhoan-duran-in-play-run-s-to-austin-riley-kkhhvg-x2885")
    # first listing: on bdata-producedclips, no captions, a provisional cut
    for p in riley["playbacks"]:
        p["url"] = re.sub(r"https://mlb-cuts-diamond\.mlb\.com/FORGE/[^ ]+?/([^/]+)$",
                          r"https://bdata-producedclips.mlb.com/\1", p["url"])
    riley["cclocationVtt"] = None
    riley["duration"] = "00:00:21"
    gf1 = final_file(early, seen_at="2026-09-30T02:00:00Z")
    gf2 = final_file(seen_at="2026-09-30T03:00:00Z")
    cid = riley["mediaPlaybackId"]
    assert gf1["clips"][cid]["embed"] == gf2["clips"][cid]["embed"]   # both hosts are allowlisted
    assert gf1["clips"][cid]["dur_s"] == 21 and gf2["clips"][cid]["dur_s"] == 29
    assert gf1["rev"] != gf2["rev"]
    # an item MLB no longer lists leaves the payload and its row falls to F3
    gone = final_file(content_with("content_849845.json", drop=("jhoan-duran-in-play-run-s-to-austin-riley-kkhhvg-x2885",)))
    assert cid not in gone["clips"]
    top = gone["plays_big"][0]
    assert top["clip"] is None and top["clip_state"] == "none" and gone["card"]["top_play"]["clip_s"] is None


def test_trim_content_keeps_no_prose_and_no_forbidden_rendition():
    t = sc.trim_content(load("content_849845.json"))
    text = json.dumps(t)
    assert len(t["items"]) == 40
    for bad in ("PROSE-SENTINEL", "highBit", "trickplay", "HTTP_CLOUD_WIRED", "headline", "blurb"):
        assert bad not in text, bad
    # the trimmed form joins exactly as the raw read
    a = sc.join_clips(t, load("wp_849845_full.json"), pk=849845)
    b = sc.join_clips(load("content_849845.json"), load("wp_849845_full.json"), pk=849845)
    assert a["clips"] == b["clips"]


# --------------------------------------------------------------------------- #
# The switch, the fail-safe and the tripwire (plan 6.7)
# --------------------------------------------------------------------------- #
def test_the_kill_switch_through_the_constant_the_env_and_the_flag_file(env, monkeypatch):
    out, store = env["paths"]["out"], env["paths"]["store"]
    out.mkdir(parents=True, exist_ok=True)
    assert job.embed_status(out) == (True, "on")
    monkeypatch.setattr(sc, "SCORES_EMBED_VIDEO", False)
    assert job.embed_effective(out) is False
    monkeypatch.setattr(sc, "SCORES_EMBED_VIDEO", True)
    monkeypatch.setenv("EEPHUS_SCORES_EMBED", "0")
    assert job.embed_status(out) == (False, "EEPHUS_SCORES_EMBED=0")
    monkeypatch.delenv("EEPHUS_SCORES_EMBED")
    (store / job.EMBED_OFF_NAME).write_text("", encoding="utf-8")       # .cache/scores/EMBED_OFF here
    assert job.embed_effective(out) is False
    (store / job.EMBED_OFF_NAME).unlink()
    (out / job.EMBED_OFF_NAME).write_text("", encoding="utf-8")         # /opt/eephus/scores/EMBED_OFF on the box
    assert job.embed_effective(out) is False
    (out / job.EMBED_OFF_NAME).unlink()
    assert job.embed_effective(out) is True
    src = (ROOT / "scores_core.py").read_text(encoding="utf-8").splitlines()
    assert "SCORES_EMBED_VIDEO = True" in src and 'SCORES_EMBED_RECONFIRMED = ""' in src


def test_a_switch_change_is_published_and_is_a_due_reason(env):
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
    seed_state(env, week_date="2026-09-30")
    assert run_once(env, api, clock)["exit"] == 0
    idx = json.loads((env["out"] / "index.json").read_text(encoding="utf-8"))
    assert idx["rules"]["video"]["embed"] is True and idx["rules"]["video"]["branch"] == "a"
    (env["paths"]["store"] / job.EMBED_OFF_NAME).write_text("", encoding="utf-8")
    state = job.load_state(env["paths"])
    d = job.decide(NOW + timedelta(seconds=30), job.read_json(env["paths"]["slate"]), state,
                   tick=job.tick_of((NOW + timedelta(seconds=30)).timestamp()), embed=job.embed_effective(env["out"]))
    assert "embed_switch" in d["due"]
    later = NOW + timedelta(minutes=2)
    assert run_once(env, api, clock, now=later)["exit"] == 0
    idx = json.loads((env["out"] / "index.json").read_text(encoding="utf-8"))
    latest = json.loads((env["out"] / "latest.json").read_text(encoding="utf-8"))
    assert idx["rules"]["video"]["embed"] is False
    assert latest["index_rev"] == sc.rev_of((env["out"] / "index.json").read_bytes())


def test_the_runtime_fail_safe_reads_the_served_diamond_config(env, monkeypatch):
    out = env["paths"]["out"]
    assets = env["web"] / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    cfg = (ROOT / "assets" / "diamond-config.js").read_text(encoding="utf-8")
    (assets / "diamond-config.js").write_text(cfg, encoding="utf-8")
    assert job.embed_effective(out) is True
    on = re.sub(r"gating:\s*false", "gating: true", cfg)
    assert on != cfg
    (assets / "diamond-config.js").write_text(on, encoding="utf-8")
    ok, why = job.embed_status(out)
    assert ok is False and "SC-PAID" in why
    monkeypatch.setattr(sc, "SCORES_EMBED_RECONFIRMED", "2026-10-07")
    assert job.embed_effective(out) is True
    # a comment naming the gate never trips it
    assert sc.diamond_gating_on("// gating: true is the upsell\nwindow.X = { gating: false };") is False


def _tripwire(config_text: str, embed_video: bool, reconfirmed: bool, environ) -> None:
    """SC-PAID (a): fail in dev and CI; skip on the box (the
    test_phase4b_evals.py precedent) so the nightly keeps publishing."""
    if sc.diamond_gating_on(config_text) and embed_video and not reconfirmed:
        if environ.get("EEPHUS_DEPLOY_RUN") == "1":
            pytest.skip(TRIPWIRE_SKIP)
        pytest.fail(TRIPWIRE_MSG)


def test_sc_paid_tripwire():
    """The live tripwire: the Diamond gate may not open while embedding is on
    without a dated owner re-confirmation of S8-1."""
    _tripwire((ROOT / "assets" / "diamond-config.js").read_text(encoding="utf-8"), sc.SCORES_EMBED_VIDEO,
              sc.embed_reconfirmed(), os.environ)


def test_the_tripwire_fails_in_dev_and_skips_under_a_deploy_run():
    on = "window.EEPHUS_DIAMOND = { gating: true };"
    with pytest.raises(pytest.fail.Exception, match=re.escape(TRIPWIRE_MSG)):
        _tripwire(on, True, False, {})
    with pytest.raises(pytest.skip.Exception, match=re.escape(TRIPWIRE_SKIP)):
        _tripwire(on, True, False, {"EEPHUS_DEPLOY_RUN": "1"})
    _tripwire(on, True, True, {})                       # re-confirmed: passes
    _tripwire(on, False, False, {})                     # embedding off: passes
    _tripwire("window.EEPHUS_DIAMOND = { gating: false };", True, False, {})


def test_webmaster_doc_names_both_overrides_and_their_latency():
    text = (ROOT / "deploy" / "WEBMASTER.md").read_text(encoding="utf-8")
    assert "touch /opt/eephus/scores/EMBED_OFF" in text and "EEPHUS_SCORES_EMBED=0" in text
    assert "next cron tick" in text and "SCORES_EMBED_RECONFIRMED" in text
    assert "git checkout -- ." in text


def test_csp_guard_any_policy_allows_the_branch_hosts():
    """No Content-Security-Policy exists today; any future one must allow
    MLB's frame host and poster CDN (branch (a))."""
    pol = []
    for p in list((ROOT / "deploy").rglob("*")) + [ROOT / "build_site.py"]:
        if p.is_file() and p.suffix in (".md", ".conf", ".txt", ".sh", ".py", ".example", ""):
            for m in re.finditer(r"Content-Security-Policy[\"'\s:]+[\"']?([^\"'\n]+)", p.read_text(encoding="utf-8",
                                                                                                errors="ignore")):
                pol.append((p.name, m.group(1)))
    for name, value in pol:
        directives = {d.strip().split(" ")[0]: d for d in value.split(";") if d.strip()}
        frame = directives.get("frame-src") or directives.get("child-src") or directives.get("default-src") or ""
        img = directives.get("img-src") or directives.get("default-src") or ""
        assert "streamable.com" in frame, (name, "frame-src must allow streamable.com")
        assert "img.mlbstatic.com" in img, (name, "img-src must allow img.mlbstatic.com")


def test_data_sources_records_the_video_branch():
    text = (ROOT / "DATA_SOURCES.md").read_text(encoding="utf-8")
    block = next((b for b in re.split(r"\r?\n- ", text) if "streamable.com" in b), "")
    assert "SC-VIDEO (a)" in block and "2026-09-30" in block and "EMBED_OFF" in block


# --------------------------------------------------------------------------- #
# The job: content inside the limiter, the cadence of 6.6, the run log
# --------------------------------------------------------------------------- #
def test_a_final_reads_its_content_and_publishes_clips(env):
    clock = FakeClock()
    pay = base_payloads()
    api = FakeAPI(clock, schedule_of(*base_games()), content={849845: load("content_849845.json")}, **pay)
    seed_state(env, week_date="2026-09-30")
    res = run_once(env, api, clock)
    assert res["exit"] == 0, res
    assert sorted(api.urls("content")) == ["https://statsapi.mlb.com/api/v1/game/849845/content",
                                           "https://statsapi.mlb.com/api/v1/game/849846/content"]
    assert res["requests"] <= job.MAX_REQUESTS_PER_RUN
    gf = json.loads((env["out"] / "games" / "849845.json").read_text(encoding="utf-8"))
    assert len(gf["clips"]) >= 16 and gf["card"]["top_play"]["clip_s"] == 29
    assert all(b["clip"] for b in gf["plays_big"][:3])
    # a missing clip may still post within 24 h of the final (first seen final
    # here, so stamped at first pitch plus 3 h), and not after
    seen = job.parse_stamp(job.load_state(env["paths"])["games"]["849845"]["final_seen_at"])
    want = "pending" if (NOW - seen).total_seconds() < sc.CLIP_PENDING_S else "none"
    assert [b["clip_state"] for b in gf["plays_big"][3:]] == [want, want]
    g = _game(849845, "F")
    assert job.clips_pending(g, {"final_seen_at": job.iso(NOW - timedelta(hours=23))}, NOW) is True
    assert job.clips_pending(g, {"final_seen_at": job.iso(NOW - timedelta(hours=25))}, NOW) is False
    assert job.clips_pending(_game(849846, "I"), {}, NOW) is True
    latest = json.loads((env["out"] / "latest.json").read_text(encoding="utf-8"))
    assert latest["window"]["2026-09-29"]["clips_matched"] == 3 and latest["window"]["2026-09-29"]["clips_of"] == 5
    date = (env["out"] / "2026-09-29.json").read_text(encoding="utf-8")
    assert "https://" not in date
    work = json.loads((env["paths"]["work"] / "849845.json").read_text(encoding="utf-8"))
    assert "PROSE-SENTINEL" not in json.dumps(work) and work["content_at"]
    log = [json.loads(ln) for ln in (env["paths"]["store"]).glob("runlog-*.jsonl").__next__().read_text(
        encoding="utf-8").splitlines()]
    assert log[-1]["clips"]["849845"]["matched"] == 16 and log[-1]["clips"]["849845"]["new_media_host"] == []
    assert log[-1]["clips"]["849845"]["f3_big"] == 2


def test_a_failed_content_read_never_blocks_the_game(env):
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(*base_games()), **base_payloads())
    api.status[("content", None)] = (500, {})
    seed_state(env, week_date="2026-09-30")
    res = run_once(env, api, clock)
    assert res["exit"] == 0 and res["counts"].get("content_fetch_failed") == 2
    gf = json.loads((env["out"] / "games" / "849845.json").read_text(encoding="utf-8"))
    assert gf["clips"] == {} and gf["stars"]
    st = job.load_state(env["paths"])
    assert not st["games"]["849845"].get("backoff_until")


def test_content_cadence_follows_plan_6_6():
    t = 10_000.0
    assert job.content_due({}, t)                                          # never read
    assert not job.content_due({"content_epoch": t - 300}, t)               # inside 600 s, nothing wanted
    assert job.content_due({"content_epoch": t - 600}, t)
    want = {"content_epoch": t - 250, "content_due_at": t - 10}
    assert job.content_due(want, t)                                        # a clipless top play, 240 s gap
    assert not job.content_due(dict(want, content_epoch=t - 200), t)        # under 240 s
    assert not job.content_due(dict(want, content_due_at=t + 30), t)        # the play ended under 90 s ago
    # finals, refreshes and the finalize read carry content with the other final reads
    g = _game(849845, "F")
    tasks = job.plan_tasks([g], {"games": {}}, NOW, "idle", job.tick_of(NOW.timestamp()))
    assert tasks[0]["calls"] == ["wp", "box", "feed", "content"]
    st = {"games": {"849845": {"final_built": True, "final_seen_at": job.iso(NOW - timedelta(minutes=61))}}}
    tasks = job.plan_tasks([g], st, NOW, "due", job.tick_of(NOW.timestamp()))
    assert tasks[0]["why"] == "final_refresh_60" and "content" in tasks[0]["calls"]
    st = {"games": {}, "pending": {"finalize": [849845]}}
    st["games"]["849845"] = {"final_built": True, "refreshed": [60, 180]}
    tasks = job.plan_tasks([g], st, NOW, "week", job.tick_of(NOW.timestamp()))
    assert any(t_["why"] == "finalize" and "content" in t_["calls"] for t_ in tasks)


def test_content_due_at_is_90_s_after_a_clipless_top_play():
    wp = load("wp_849845_ext.json")             # the job's fields= read carries about.endTime
    gf = final_file()
    at = job.content_due_at(wp, gf)
    ends = {sc._ab(p): job.parse_stamp(p["about"]["endTime"]).timestamp() for p in sc.complete_elements(wp)}
    clipless = [b["ab"] for b in gf["plays_big"] if not b["clip"]]
    assert at == min(ends[a] for a in clipless) + job.CONTENT_AFTER_PA_S
    for b in gf["plays_big"]:
        b["clip"] = "x"
    assert job.content_due_at(wp, gf) is None


def test_a_live_game_reads_content_inside_the_limiter(env):
    clock = FakeClock()
    api = FakeAPI(clock, schedule_of(_game(849846, "I")), content={849846: load("content_849846_live.json")},
                  wp={849846: load("wp_849846_live.json")}, box={849846: load("box_849845.json")})
    seed_state(env, week_date="2026-09-30")
    res = run_once(env, api, clock)
    assert res["exit"] == 0 and api.urls("content") == ["https://statsapi.mlb.com/api/v1/game/849846/content"]
    st = job.load_state(env["paths"])["games"]["849846"]
    assert st["content_epoch"] and "content_due_at" in st
    # the next live tick inside 240 s reads no content
    later = NOW + timedelta(minutes=2)
    run_once(env, api, clock, now=later)
    assert len(api.urls("content")) == 1
    # a budget of 2 requests rolls the content read over instead of exceeding it
    lim = job.Limiter(clock=clock, sleep=clock.sleep, max_requests=2)
    f = job.Fetcher(lim, api)
    f.schedule("2026-09-30", "2026-09-30")
    f.content(849846)
    with pytest.raises(job.BudgetExhausted):
        f.content(849846)
