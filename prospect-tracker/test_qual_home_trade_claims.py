# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Three public claims on the homepage and the Trade Machine name the basis each
number actually rests on (surface-quality audit 2026-10-02, QUAL_4).

QHOC01: the homepage eFV Distribution pooled 2,439 production grades (rows the
export marks source_graded False, glossary xfv_ungraded) with 1,982 eFV grades
and called all 4,421 "graded prospects". The two bases are now separate series
and the caption counts the source-graded rows alone.

QHOC02: the Across eephus.io Free Agency card listed the top projGuar members
with no status filter, so a player whose option was exercised could lead it.
It now filters exactly as /fa/'s 'remaining' list does and says 'if he reaches
the market' beside a pending option.

QCLC01: the Trade Machine lede said MLB players are priced on projections while
695 debuted rows ride the locked eFV backgrade (registry row xfv_backgrade); the
lede names that basis and the row range tooltip branches on surplus_source."""

from __future__ import annotations

import json
import re
from pathlib import Path

import build_site

ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------------- QHOC01 ---- #

def _fx_players():
    rows = []
    # 12 source-graded rows plotted (grades 36..47) and 2 at the floor.
    for i, g in enumerate(range(36, 48)):
        rows.append({"player_key": f"qhoc_fx_e{i}", "fv_close": g, "source_graded": True})
    rows += [{"player_key": "qhoc_fx_ef1", "fv_close": 20, "source_graded": True},
             {"player_key": "qhoc_fx_ef2", "fv_close": 20, "source_graded": True}]
    # 7 production-grade rows plotted, 3 at the floor.
    for i, g in enumerate((22, 24, 25, 25, 27, 29, 31)):
        rows.append({"player_key": f"qhoc_fx_p{i}", "fv_close": g, "source_graded": False})
    rows += [{"player_key": f"qhoc_fx_pf{i}", "fv_close": 20, "source_graded": False}
             for i in range(3)]
    return rows


def test_histogram_labels_two_bases_and_caption_counts_source_graded(monkeypatch):
    monkeypatch.setattr(build_site, "_EFV_GRADES", {})
    out = build_site._efv_distribution_html(_fx_players())
    assert out
    caption = out.split("bands are")[0].rsplit("<div", 1)[-1]
    # The headline count is the source-graded plotted rows (12), not all 19.
    assert "12 source-graded prospects" in caption
    assert "19 " not in caption
    assert "2 at the eFV 20 floor" in caption
    # The production grades are their own labelled series, never called eFV.
    assert "7 " in caption and "production grades" in caption and "not eFV" in caption
    assert "production grade, no source grade" in out          # legend entry
    titles = re.findall(r"<title>([^<]*)</title>", out)
    prod_tips = [t for t in titles if t.startswith("Production grade")]
    efv_tips = [t for t in titles if t.startswith("eFV ") and "distribution" not in t]
    assert len(prod_tips) == 6                    # distinct grades 22,24,25,27,29,31
    assert sum(int(re.search(r" - (\d+) ", t).group(1)) for t in prod_tips) == 7
    assert sum(int(re.search(r" - (\d+) ", t).group(1)) for t in efv_tips) == 12
    assert not any("graded board" in t for t in prod_tips)
    assert all("source-graded board" in t for t in efv_tips)


def test_rows_without_the_flag_stay_on_the_efv_side(monkeypatch):
    monkeypatch.setattr(build_site, "_EFV_GRADES", {})
    rows = [{"player_key": f"qhoc_fx_n{i}", "fv_close": 30 + i} for i in range(11)]
    out = build_site._efv_distribution_html(rows)
    assert "11 source-graded prospects" in out
    assert "production grade" not in out


def test_served_caption_counts_match_the_source_graded_rows():
    data = build_site.load_site_data()
    if not data or not data.get("players"):
        import pytest
        pytest.skip("no timeseries payload")
    players = data["players"]
    n_e = n_p = 0
    for p in players:
        v = build_site._primary_fv(p)
        if not isinstance(v, (int, float)):
            continue
        if build_site._round_half_up(v) <= build_site._EFV_FLOOR:
            continue
        if p.get("source_graded") is False:
            n_p += 1
        else:
            n_e += 1
    out = build_site._efv_distribution_html(players)
    assert f"{n_e:,} source-graded prospects" in out
    if n_p:
        assert f"{n_p:,} " in out and "production grades" in out


# ---------------------------------------------------------------- QHOC02 ---- #

def _fa_strip(monkeypatch, members):
    real = build_site._cached_data_json

    def fake(name):
        if name == "fa_class.json":
            return {"class_year": 2027, "members": members}
        return real(name)

    monkeypatch.setattr(build_site, "_cached_data_json", fake)
    return build_site._xmod_cards_html(("fa",))


def _fa_keys(strip: str) -> list[str]:
    return re.findall(r'href="/fa/#player=([^"]+)"', strip)


def test_fa_card_drops_signed_and_exercised_members(monkeypatch):
    members = [
        {"key": "fx_signed", "name": "Fx Signed", "pos": "SP", "status": "signed",
         "projYears": 5, "projGuar": 300e6},
        {"key": "fx_exercised", "name": "Fx Exercised", "pos": "SP",
         "status": "option_exercised", "projYears": 4, "projGuar": 250e6},
        {"key": "fx_locked", "name": "Fx Locked", "pos": "C", "status": "locked",
         "projYears": 3, "projGuar": 90e6},
        {"key": "fx_pending", "name": "Fx Pending", "pos": "RP", "status": "pending_option",
         "projYears": 2, "projGuar": 80e6},
        {"key": "fx_third", "name": "Fx Third", "pos": "1B", "status": "locked",
         "projYears": 1, "projGuar": 20e6},
    ]
    strip = _fa_strip(monkeypatch, members)
    keys = _fa_keys(strip)
    assert keys == ["fx_locked", "fx_pending", "fx_third"]
    row = strip.split('/fa/#player=fx_pending"', 1)[1].split("</a>", 1)[0]
    assert "if he reaches the market" in row
    locked = strip.split('/fa/#player=fx_locked"', 1)[1].split("</a>", 1)[0]
    assert "if he reaches the market" not in locked


def test_served_fa_card_lists_no_off_board_member():
    fa = json.loads((ROOT / "data" / "fa_class.json").read_text(encoding="utf-8"))
    status = {m["key"]: m.get("status") for m in fa.get("members") or []}
    strip = build_site._xmod_cards_html(("fa",))
    keys = _fa_keys(strip)
    assert keys, "the Free Agency card is missing"
    assert not [k for k in keys if status.get(k) in ("signed", "option_exercised")]
    for k in keys:
        if status.get(k) == "pending_option":
            row = strip.split(f'/fa/#player={k}"', 1)[1].split("</a>", 1)[0]
            assert "if he reaches the market" in row


# ---------------------------------------------------------------- QCLC01 ---- #

def test_trademachine_lede_names_the_backgrade():
    page = build_site.build_trademachine()
    lede = page.split('class="section-sub">', 1)[1].split("</span></div>", 1)[0]
    assert "xfv_backgrade" in lede and "provisional" in lede
    assert "projections" in lede and "prospects on eFV" in lede
    built = (ROOT / "trademachine" / "index.html").read_text(encoding="utf-8")
    assert "registry row xfv_backgrade, provisional" in built


def test_bandwhat_branches_on_backgrade_surplus_source():
    js = (ROOT / "assets" / "trademachine.js").read_text(encoding="utf-8")
    block = js.split("const bandWhat =", 1)[1].split("let rangeTip", 1)[0]
    assert re.search(r'p\.surplus_source\s*===\s*"xfv_backgrade"', block)
    assert "locked prospect eFV backgrade (xfv_backgrade, provisional); " \
           "no projection prices this row" in block
    # the backgrade branch sits before the generic eFV fallback
    assert block.index('"xfv_backgrade"') < block.index('"eFV credible interval"')
