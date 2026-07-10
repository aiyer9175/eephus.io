# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the financial scrapers — MLB.com draft bonus pool parser
and Spotrac team contract parser. These exercise the pure HTML/text
parsing functions with hardcoded fixtures so no network access is
needed. Run: python -m pytest test_scrapers_financial.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bs4 import BeautifulSoup

from scrapers import (
    _parse_structured_team_pools,
    _parse_structured_pick_values,
    _parse_inline_team_pools,
)
from spotrac import (
    _parse_team_contract_table,
    build_contracts_by_key,
)


# ---------------------------------------------------------------------------
# MLB.com draft bonus pool parser
# ---------------------------------------------------------------------------

class TestStructuredTeamPools:
    def test_bonus_pools_by_team_heading(self):
        # 2024-2025 format
        body = (
            "intro prose with $50,000 mention\n"
            '**Bonus pools by team**\n\n'
            "Orioles: $19,144,500  \n"
            "Mariners: $17,074,400  \n"
            "Angels: $16,656,400  \n"
            '**First Round**\n'
        )
        pools = _parse_structured_team_pools(body)
        assert pools.get("Orioles") == 19144500
        assert pools.get("Mariners") == 17074400
        assert pools.get("Angels") == 16656400

    def test_bonus_pools_compact_heading(self):
        # 2026 format
        body = (
            '**Bonus pools**  \n'
            "Pirates: $19,130,700  \n"
            "Rays: $19,009,300  \n"
            '**Next section**\n'
        )
        pools = _parse_structured_team_pools(body)
        assert pools.get("Pirates") == 19130700
        assert pools.get("Rays") == 19009300

    def test_bonus_pools_by_club_heading(self):
        # 2023 format
        body = (
            '**Bonus pools by club:**  \n'
            "Pirates: $16,185,700  \n"
            "Tigers: $15,747,200  \n"
            '**First Round**\n'
        )
        pools = _parse_structured_team_pools(body)
        assert pools.get("Pirates") == 16185700
        assert pools.get("Tigers") == 15747200

    def test_ignores_link_text_outside_heading(self):
        # The phrase "Bonus pools, pick values" appears in navigation
        # links. The ** anchor must skip those.
        body = (
            '<a href="...">Bonus pools, pick values</a>\n'
            "Pirates: $5,000,000  \n"
            '**Bonus pools**  \n'
            "Pirates: $19,130,700  \n"
            "Rays: $19,009,300  \n"
            '**First Round**\n'
        )
        pools = _parse_structured_team_pools(body)
        assert pools.get("Pirates") == 19130700  # not 5,000,000 from nav

    def test_empty_when_no_heading(self):
        assert _parse_structured_team_pools("just some text $1,000") == {}


class TestStructuredPickValues:
    def test_parses_numbered_picks(self):
        body = (
            "**First Round**\n\n"
            "1\\. Nationals: $11,075,900  \n"
            "2\\. Angels: $10,252,700  \n"
            "3\\. Mariners: $9,504,400  \n"
        )
        picks = _parse_structured_pick_values(body)
        by_overall = {p["pick_overall"]: p for p in picks}
        assert by_overall[1]["team"] == "Nationals"
        assert by_overall[1]["slot_usd"] == 11075900
        assert by_overall[2]["team"] == "Angels"
        assert by_overall[3]["team"] == "Mariners"

    def test_dedups_duplicate_pick_numbers(self):
        # Same pick mentioned twice (the article occasionally repeats
        # picks across subheadings). Dedup keeps the first occurrence.
        body = (
            "1\\. Nationals: $11,075,900\n"
            "1\\. Nationals: $11,075,900\n"
        )
        picks = _parse_structured_pick_values(body)
        assert len(picks) == 1

    def test_skips_implausible_pick_numbers(self):
        body = "999\\. Garbage: $1,000,000\n0\\. Garbage: $1,000\n"
        picks = _parse_structured_pick_values(body)
        assert picks == []


class TestInlineTeamPools:
    def test_inline_prose_pool_mentions(self):
        # 2021/2022 style prose
        body = (
            "Pittsburgh has the first selection ... and their total pool "
            "value is $14,394,000.\n"
            "Besides the Pirates, nine other teams have eight-figure bonus "
            "pools: the Tigers ($14,253,800), Rangers ($12,641,000), Reds "
            "($11,905,700), Orioles ($11,829,300)."
        )
        pools = _parse_inline_team_pools(body)
        # Inline mode catches the parenthesized teams; not Pirates (no
        # parens in that sentence) — that's the documented limitation.
        assert pools.get("Tigers") == 14253800
        assert pools.get("Rangers") == 12641000
        assert pools.get("Reds") == 11905700
        assert pools.get("Orioles") == 11829300


# ---------------------------------------------------------------------------
# Spotrac team contract parser
# ---------------------------------------------------------------------------

# Synthetic Spotrac yearly-table fixture mirroring the real DOM shape
# (year header columns + data-export salary cells).
SPOTRAC_FIXTURE = """
<table id="dataTable-active">
  <thead>
    <tr>
      <th>Player (3)</th>
      <th>Pos</th>
      <th>Age</th>
      <th>2026</th>
      <th>2027</th>
      <th>2028</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td data-export="Kyle Tucker">
        <a href="https://www.spotrac.com/mlb/player/_/id/17620/kyle-tucker">Kyle Tucker</a>
      </td>
      <td data-export="RF">RF</td>
      <td data-export="29">29</td>
      <td data-export="57195000"><a href="javascript:void(0)">$57,195,000 23.4%</a></td>
      <td data-export="57195000"><a href="javascript:void(0)">$57,195,000 23.2%</a></td>
      <td data-export=" ">UFA</td>
    </tr>
    <tr>
      <td data-export="Shohei Ohtani">
        <a href="https://www.spotrac.com/mlb/player/_/id/24661/shohei-ohtani">Shohei Ohtani</a>
      </td>
      <td data-export="SP">SP/DH</td>
      <td data-export="31">31</td>
      <td data-export="46081476"><a href="javascript:void(0)">$46,081,476 18.9%</a></td>
      <td data-export="46081476"><a href="javascript:void(0)">$46,081,476 18.7%</a></td>
      <td data-export="46081476"><a href="javascript:void(0)">$46,081,476 18.4%</a></td>
    </tr>
    <tr>
      <td data-export="Pre-Arb Player">
        <a href="https://www.spotrac.com/mlb/player/_/id/12345/pre-arb-player">Pre-Arb Player</a>
      </td>
      <td data-export="CF">CF</td>
      <td data-export="24">24</td>
      <td data-export="760000"><a href="javascript:void(0)">$760,000 0.3%</a></td>
      <td data-export=" "></td>
      <td data-export=" "></td>
    </tr>
  </tbody>
</table>
"""


class TestSpotracTeamContractParser:
    def _table(self):
        soup = BeautifulSoup(SPOTRAC_FIXTURE, "html.parser")
        return soup.find("table", id="dataTable-active")

    def test_parses_multi_year_contract(self):
        rows = _parse_team_contract_table(self._table(), "los-angeles-dodgers")
        by_name = {r["player_name"]: r for r in rows}
        # Kyle Tucker — 2026 + 2027 salaries, 2028 UFA.
        tucker = by_name["Kyle Tucker"]
        assert tucker["years_remaining"] == 2
        assert tucker["aav_usd"] == 57195000
        assert tucker["total_usd"] == 114390000
        assert tucker["signed_through"] == 2027
        assert tucker["salary_by_year"] == {2026: 57195000, 2027: 57195000}
        assert tucker["spotrac_id"] == "17620"
        assert tucker["position"] == "RF"

    def test_parses_long_term_deal(self):
        rows = _parse_team_contract_table(self._table(), "los-angeles-dodgers")
        by_name = {r["player_name"]: r for r in rows}
        ohtani = by_name["Shohei Ohtani"]
        assert ohtani["years_remaining"] == 3
        assert ohtani["aav_usd"] == 46081476
        assert ohtani["total_usd"] == 138244428
        assert ohtani["spotrac_id"] == "24661"

    def test_parses_pre_arb_single_year(self):
        rows = _parse_team_contract_table(self._table(), "los-angeles-dodgers")
        by_name = {r["player_name"]: r for r in rows}
        pre_arb = by_name["Pre-Arb Player"]
        assert pre_arb["years_remaining"] == 1
        assert pre_arb["aav_usd"] == 760000
        assert pre_arb["salary_by_year"] == {2026: 760000}


class TestBuildContractsByKey:
    def test_dedups_by_player_key_keep_highest_aav(self):
        rows = [
            {"player_name": "Alice", "player_key": "alice", "aav_usd": 1_000_000},
            {"player_name": "Alice", "player_key": "alice", "aav_usd": 5_000_000},
            {"player_name": "Bob",   "player_key": "bob",   "aav_usd": 2_000_000},
        ]
        out = build_contracts_by_key(rows)
        assert out["alice"]["aav_usd"] == 5_000_000  # higher AAV wins
        assert out["bob"]["aav_usd"] == 2_000_000
        assert len(out) == 2

    def test_skips_rows_without_player_key(self):
        rows = [
            {"player_name": "Alice", "player_key": "alice", "aav_usd": 1_000_000},
            {"player_name": "Ghost", "player_key": None, "aav_usd": 99_000_000},
            {"player_name": "NoKey", "aav_usd": 50_000_000},
        ]
        out = build_contracts_by_key(rows)
        assert list(out.keys()) == ["alice"]
