# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""RBE05 and RBE08 (2026-10-02): what the record and the paper-bet ROI panel
say beside their numbers.

RBE05. The public record's first row (CLE at KCR Over 8.0, slate 2026-09-26)
was published with the slate total-lean caveat on its slot row, 47 minutes
before the owner barred caveated totals from the slots, and the record row
dropped the caveat, the Poisson caveat and p_push. The row is append-only and
is never edited: `record_summary` now joins a note per caveated row at read
time, /betting/ and the /diamond/ record card render it, and `record_row`
copies the three fields onto every future row.

RBE08. The Record tab's ROI-by-tag bars summed moneyline, runline and total
under each tag beneath a caption saying tags are never pooled. The bars now
read data/betting_subledger.json by_market_by_tag, one cell per market per
tag, and the pooled fallback says it is pooled.

The served tests read the SERVED artifacts (data/betting_record.json,
data/betting_settlement.json, data/betting.json, data/betting_subledger.json,
data/betting_learning.json) and the slate locks the box wrote, so they hold
for whatever those say on the day they run.
"""
from __future__ import annotations

import html as htmllib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import betting_export as be  # noqa: E402

DATA = ROOT / "data"
SLOTS = ROOT / ".cache" / "betting" / "published_slots"


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _served_rows() -> list[dict]:
    p = DATA / "betting_record.json"
    if not p.exists():
        pytest.skip("data/betting_record.json is not on this checkout (it is gitignored)")
    return _load(p)


def _caveated_bet_ids(rows: list[dict]) -> set[str]:
    """Record rows whose published slot row carried total_level_caveat, read
    straight off the slate locks, independently of the code under test."""
    out = set()
    for r in rows:
        if r.get("total_level_caveat"):
            out.add(r["bet_id"])
            continue
        p = SLOTS / f"{r.get('slate_date')}.json"
        if not p.exists():
            continue
        s = ((_load(p).get("slots") or {}).get(r.get("slot")) or {}).get("row") or {}
        if not s.get("total_level_caveat"):
            continue
        if be.bet_id(r.get("slate_date"), s.get("game_pk"), s.get("market"),
                     s.get("side"), s.get("point")) == r.get("bet_id"):
            out.add(r["bet_id"])
    return out


def _served_summary(rows):
    settle = be.load_settlement(DATA / "betting_settlement.json")
    return be.record_summary(rows, clv={}, settlement=settle, slots_root=SLOTS)


# ---------------------------------------------------------------------------
# RBE05: the record discloses every caveated row
# ---------------------------------------------------------------------------
def test_every_served_caveated_row_gets_a_disclosure_from_the_exporter():
    rows = _served_rows()
    want = _caveated_bet_ids(rows)
    summ = _served_summary(rows)
    got = {d["bet_id"]: d for d in summ["disclosures"]}
    assert set(got) == want
    for bid in want:
        d = got[bid]
        assert d["kind"] == "total_level_caveat"
        assert d["total_level_caveat"] in d["note"]
        assert "append-only" in d["note"]
    reg = [d for d in summ["disclosures"] if d["scope"] == "regular_season"]
    if reg:
        assert summ["disclosure_note"].startswith(f"{len(reg)} of {summ['n_rows']} row")
    else:
        assert summ["disclosure_note"] is None


def test_the_first_record_row_is_disclosed_as_predating_the_bar():
    rows = _served_rows()
    row = next((r for r in rows if r.get("bet_id") == "a9eac0a8f35381b8"), None)
    if row is None or not (SLOTS / "2026-09-26.json").exists():
        pytest.skip("the 2026-09-26 row or its slate lock is not on this checkout")
    d = next(d for d in _served_summary(rows)["disclosures"]
             if d["bet_id"] == "a9eac0a8f35381b8")
    assert d["predates_bar"] is True
    assert d["source"] == "published slot lock"
    assert "47 minutes before the owner barred a caveated total" in d["note"]
    assert "Known model shape, not value" in d["note"]


def test_the_disclosure_moves_no_graded_count_unit_or_chain():
    """Every field the served record block already carries is unchanged by the
    join; the only new keys are the notes."""
    rows = _served_rows()
    summ = _served_summary(rows)
    served = _load(DATA / "betting.json").get("record") or {}
    if served.get("n_rows_all") != len(rows):
        pytest.skip("data/betting.json was built over a different record length")
    for k in ("n_rows", "n_settled", "n_open", "won", "lost", "push", "net_units",
              "roi_pct", "n_rows_all", "n_postseason_rows", "chain_sha"):
        assert summ[k] == served.get(k), k
    for k in ("n_rows", "won", "lost", "net_units", "roi_pct"):
        assert summ["postseason"][k] == (served.get("postseason") or {}).get(k), k


@pytest.mark.parametrize("name", ["betting.json", "betting_preview.json"])
def test_the_served_payload_record_block_discloses_every_caveated_row(name):
    """data/betting.json (and the preview slice the /diamond/ card reads) once
    the scheduled betting export has run with this code. A payload built before
    it carries no `disclosures` key at all, and that is the one state skipped."""
    rows = _served_rows()
    rec = _load(DATA / name).get("record") or {}
    if "disclosures" not in rec:
        pytest.skip(f"data/{name} predates the record notes; the next scheduled "
                    "betting export writes them")
    want = _caveated_bet_ids(rows)
    got = {d.get("bet_id") for d in rec["disclosures"] if d.get("note")}
    assert want <= got
    if any(d.get("scope") == "regular_season" for d in rec["disclosures"]):
        assert rec.get("disclosure_note")


def test_a_lock_that_published_another_bet_lends_no_caveat(tmp_path):
    lock = {"schema": be.SLOT_LOCK_SCHEMA, "slate_date": "2026-09-01", "slots": {
        "pick_of_the_day": {"row": {"game_pk": 9, "market": "total", "side": "under",
                                    "point": 8.5, "total_level_caveat": "Slate leans Over"}}}}
    (tmp_path / "2026-09-01.json").write_text(json.dumps(lock), encoding="utf-8")
    row = {"bet_id": be.bet_id("2026-09-01", 9, "total", "over", 8.5),
           "slate_date": "2026-09-01", "slot": "pick_of_the_day",
           "posted_at": "2026-09-01T12:00:00+00:00"}
    assert be.record_row_disclosures([row], slots_root=tmp_path) == []
    row["bet_id"] = be.bet_id("2026-09-01", 9, "total", "under", 8.5)
    out = be.record_row_disclosures([row], slots_root=tmp_path)
    assert len(out) == 1 and out[0]["predates_bar"] is True


def test_a_row_carrying_its_own_caveat_is_disclosed_from_the_row(tmp_path):
    row = {"bet_id": "x", "slate_date": "2026-11-01", "slot": "pick_of_the_day",
           "selection": "Over 9.0", "total_level_caveat": "Slate leans Over: shape",
           "posted_at": "2026-11-01T15:00:00+00:00"}
    out = be.record_row_disclosures([row], slots_root=tmp_path)
    assert out[0]["source"] == "record row"
    assert out[0]["predates_bar"] is False
    assert "the bar was off when it published" in out[0]["note"]


# ---------------------------------------------------------------------------
# RBE05: future rows carry the three fields (record_row -> write_record)
# ---------------------------------------------------------------------------
def _slot_row(**kw) -> dict:
    s = {"game_pk": 824057, "market": "total", "side": "over", "point": 8.0,
         "label": "Over 8.0", "matchup": "CLE at KCR", "odds": -113, "decimal": 1.885,
         "edge": 0.14486, "model_prob": 0.65721, "market_fair_prob": 0.51235,
         "ev_per_unit": 0.2082, "min_edge_used": 0.06, "provisional": True,
         "slot": "pick_of_the_day",
         "total_level_caveat": "Slate leans Over: Known model shape, not value.",
         "caveat": "this is a runline or total, and the margin model is a Poisson difference",
         "p_push": 0.12828}
    s.update(kw)
    return s


@pytest.mark.parametrize("suffix", [".json", ".jsonl"])
def test_write_record_keeps_the_three_slot_fields_on_the_row(tmp_path, suffix):
    slot = _slot_row()
    row = be.record_row(slot, slate_date="2026-10-05", evald=None,
                        posted_at="2026-10-05T12:00:00+00:00")
    path = tmp_path / f"record{suffix}"
    be.write_record([row], path=path)
    back = be.load_record(path)
    assert len(back) == 1
    for k in ("total_level_caveat", "caveat", "p_push"):
        assert back[0][k] == slot[k], k
    # ev_per_unit is recomputable from the row: on a whole-number total the
    # push-conditioned EV is (1 - p_push) * [p * (decimal - 1) - (1 - p)].
    p_cond = back[0]["model_prob"]
    ev = (1 - back[0]["p_push"]) * (p_cond * (back[0]["decimal"] - 1) - (1 - p_cond))
    assert ev == pytest.approx(back[0]["ev_per_unit"], abs=5e-4)
    # The row the file holds is the row the chain was folded over.
    assert be.chain_sha(back) == be.chain_sha([row])
    # And the row discloses itself through the summary.
    assert be.record_row_disclosures(back, slots_root=tmp_path)[0]["source"] == "record row"


def test_a_slot_row_without_the_fields_writes_them_as_none(tmp_path):
    slot = _slot_row(market="moneyline", side="home", point=None)
    for k in ("total_level_caveat", "caveat", "p_push"):
        slot.pop(k)
    row = be.record_row(slot, slate_date="2026-10-05", evald=None)
    assert row["total_level_caveat"] is None and row["caveat"] is None
    assert row["p_push"] is None


# ---------------------------------------------------------------------------
# Render: /betting/ record panel, ROI panel, and the /diamond/ record card
# ---------------------------------------------------------------------------
tb = pytest.importorskip("test_betting")


def _text(html: str) -> str:
    return htmllib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))).strip()


def _served_main_with_notes() -> dict:
    """The served board payload, its record block replaced by the exporter's
    own record_summary over the served rows when the served block predates
    the notes, so the render is checked on today's record either way."""
    main = _load(DATA / "betting.json")
    if "disclosures" not in (main.get("record") or {}):
        main["record"] = _served_summary(_served_rows())
    return main


def _record_ctx(main: dict, *, subledger: bool = True):
    routes = {"main": json.dumps(main),
              "learning": (DATA / "betting_learning.json").read_text(encoding="utf-8"),
              "evald": (DATA / "betting_model_eval.json").read_text(encoding="utf-8")}
    if subledger:
        routes["subledger"] = (DATA / "betting_subledger.json").read_text(encoding="utf-8")
    return tb._ctx(tb._fetch_js(**routes))


def test_the_betting_record_panel_renders_every_note_beside_the_record():
    main = _served_main_with_notes()
    rec = main["record"]
    html = _record_ctx(main).eval("__show('record')")
    text = _text(html)
    if rec.get("disclosure_note"):
        assert rec["disclosure_note"] in text
    for d in rec.get("disclosures") or []:
        assert d["note"] in text
    if rec.get("disclosures"):
        i_rec = text.index("The public record")
        i_note = text.index(rec["disclosures"][0]["note"][:40])
        assert i_rec < i_note < text.index("Raw file:")


def _roi_sections(html: str) -> dict:
    """{market: [(tag, roi, n), ...]} off the rendered ROI panel."""
    out = {}
    parts = re.split(r'data-bt-roi-market="([^"]+)"', html)
    for i in range(1, len(parts), 2):
        m, body = parts[i], parts[i + 1]
        svg = body[:body.index("</svg>")]
        tags = re.findall(r'text-anchor="end">([^<]+)</text>', svg)
        bars = re.findall(r'data-roi="([^"]+)" data-n="([^"]+)"', svg)
        out[m] = [(t, float(r), int(n)) for t, (r, n) in zip(tags, bars)]
    return out


def test_the_roi_panel_draws_the_served_by_market_by_tag_cells():
    sub = _load(DATA / "betting_subledger.json")
    cells = sub.get("by_market_by_tag") or {}
    html = _record_ctx(_load(DATA / "betting.json")).eval("__show('record')")
    got = _roi_sections(html)
    want = {m: sorted((k, float(c["roi"]), int(c["n_settled"]))
                      for k, c in tags.items() if c.get("roi") is not None)
            for m, tags in cells.items()}
    want = {m: v for m, v in want.items() if v}
    assert want, "the served sub-ledger has no settled cell"
    assert "pooled" not in got
    assert {m: sorted(v) for m, v in got.items()} == want
    text = _text(html)
    assert "never pooled" not in text
    assert "one bar per market per selection rule" in text
    assert "No bar sums two markets or two tags" in text


def test_the_roi_fallback_says_its_bars_are_pooled():
    html = _record_ctx(_load(DATA / "betting.json"), subledger=False).eval("__show('record')")
    text = _text(html)
    learning = _load(DATA / "betting_learning.json")
    if not ((learning.get("latest") or {}).get("shadow_by_tag")):
        pytest.skip("the served learning artifact carries no shadow_by_tag block")
    assert "pooled" in _roi_sections(html)
    assert "Pooled across markets" in text
    assert "Each bar is pooled across markets" in text
    assert "never pooled" not in text


def test_the_diamond_record_card_renders_the_note():
    ds = pytest.importorskip("test_diamond_scaffold")
    rec = _served_main_with_notes()["record"]
    if not rec.get("disclosure_note"):
        pytest.skip("no regular-season row behind the served record is caveated")
    htm = ds._record_html(preview={"generated_at": "2026-10-02T00:00:00Z", "record": rec})
    text = _text(htm)
    assert "The betting record" in text
    assert rec["disclosure_note"] in text
    for d in rec["disclosures"]:
        if d["scope"] == "regular_season":
            assert d["note"][:60] in text
