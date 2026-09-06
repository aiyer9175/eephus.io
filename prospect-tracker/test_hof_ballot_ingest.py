"""H-DATA-2: the ballot panel parser.

WHY A PARSER GETS THIS MUCH TEST. hof_data.py refuses to produce a Hall of Fame
label rather than guess a membership list, and this parser is what lifts that
refusal. Everything downstream, the censoring rule, the per-route breakdown, the
whole predictor, inherits whatever this returns. A parser that silently drops a
row does not fail loudly; it produces a slightly smaller Hall.

The fixtures below are hand-built and small on purpose. Each one encodes a defect
found against the live 2025 page while writing the tool, so a reader can see what
went wrong rather than diffing a 238 KB capture:

  * CC Sabathia's Baseball-Reference id is "sabatc.01", with a DOT. The obvious
    id pattern assumes five letters and three digits and drops him.
  * Names are separated from their markers by &nbsp;, so a name that is merely
    unescaped keeps a U+00A0 and joins to nothing.
  * An enshrined player carries <span class="hilite">HOF</span> after the name,
    which lands INSIDE the name unless it is removed, and which is a perfect
    outcome leak if it is ever treated as a feature.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import hof_ballot_ingest as hb          # noqa: E402


def _page(rows_html: str, table_id: str = "hof_BBWAA",
          needed: str = "296 votes needed") -> str:
    return f"""<html><body>
      <p>Ballot: {needed} for election.</p>
      <table class="stats_table" id="{table_id}" data-cols-to-freeze=",2">
      <thead><tr>
        <th data-stat="ranker">Rk</th><th data-stat="player">Name</th>
        <th data-stat="year_on_ballot">YoB</th><th data-stat="votes">Votes</th>
        <th data-stat="votes_pct">%vote</th>
        <th data-stat="hof_monitor">HOFm</th>
        <th data-stat="hof_standard">HOFs</th>
        <th data-stat="WAR_career">WAR</th>
        <th data-stat="WAR_peak7">WAR7</th>
        <th data-stat="JAWS">JAWS</th>
      </tr></thead>
      <tbody>{rows_html}</tbody></table></body></html>"""


def _row(pid, name, yob, votes, pct, extra="", monitor="100", standard="40",
         war="60.0", war7="43.7", jaws="51.8"):
    link = (f'<a href="/players/{pid[0]}/{pid}.shtml">{name}</a>'
            if pid else name)
    return (f'<tr><th data-stat="ranker">1</th>'
            f'<td data-stat="player">{link}{extra}</td>'
            f'<td data-stat="year_on_ballot">{yob}</td>'
            f'<td data-stat="votes">{votes}</td>'
            f'<td data-stat="votes_pct">{pct}</td>'
            f'<td data-stat="hof_monitor">{monitor}</td>'
            f'<td data-stat="hof_standard">{standard}</td>'
            f'<td data-stat="WAR_career">{war}</td>'
            f'<td data-stat="WAR_peak7">{war7}</td>'
            f'<td data-stat="JAWS">{jaws}</td></tr>')


# --------------------------------------------------------------------------
# The three defects
# --------------------------------------------------------------------------

def test_a_dotted_bbref_id_is_not_dropped():
    page = _page(_row("sabatc.01", "CC Sabathia", "1st", "342", "86.8%"))
    out = hb.parse_election_page(page, 2025)
    ids = [r["player_id"] for r in out["rows"]]
    assert ids == ["sabatc.01"], (
        f"got {ids}: an id containing a dot was dropped, so a real candidate "
        "becomes a hole in the panel")


def test_the_hof_marker_leaves_the_name_and_becomes_its_own_field():
    extra = '&nbsp;<span class="hilite">HOF</span>'
    page = _page(_row("beltrca01", "Carlos Beltran", "3rd", "277", "70.3%",
                      extra=extra))
    r = hb.parse_election_page(page, 2025)["rows"][0]
    assert r["player_name"] == "Carlos Beltran", (
        f"name came back as {r['player_name']!r}; the enshrinement marker or a "
        "non-breaking space is still inside it")
    assert r["bref_hof_marker_as_of_scrape"] is True


def test_a_non_breaking_space_never_survives_into_a_name():
    page = _page(_row("suzukic01", "Ichiro&nbsp;Suzuki", "1st", "393", "99.7%"))
    r = hb.parse_election_page(page, 2025)["rows"][0]
    assert " " not in r["player_name"]
    assert r["player_name"] == "Ichiro Suzuki"


def test_the_marker_is_labelled_as_a_leak_where_it_is_defined():
    src = (ROOT / "tools" / "hof_ballot_ingest.py").read_text(encoding="utf-8")
    i = src.index("_HOF_MARK_RE")
    head = src[max(0, i - 1200):i]
    assert "leak" in head.lower(), (
        "the enshrinement marker is captured without warning that it is true as "
        "of the scrape rather than as of the row's election year; used as a "
        "feature it hands a forward-chained model the answer")


# --------------------------------------------------------------------------
# The election arithmetic
# --------------------------------------------------------------------------

def test_ballots_cast_is_derived_from_votes_and_share():
    page = _page(_row("suzukic01", "Ichiro Suzuki", "1st", "393", "99.7%")
                 + _row("sabatc.01", "CC Sabathia", "1st", "342", "86.8%")
                 + _row("wagnebi02", "Billy Wagner", "10th", "325", "82.5%"))
    out = hb.parse_election_page(page, 2025)
    assert out["ballots_cast"] == 394, (
        f"got {out['ballots_cast']}: 393 of 99.7% is 394 ballots, and the 2025 "
        "election really did have 394")
    assert "median" in out["ballots_cast_method"]


def test_the_seventy_five_percent_rule_decides_elected():
    page = _page(_row("a", "Over", "1st", "300", "76.0%")
                 + _row("b", "Under", "1st", "290", "74.0%"))
    rows = {r["player_name"]: r for r in hb.parse_election_page(page, 2025)["rows"]}
    assert rows["Over"]["elected"] is True
    assert rows["Under"]["elected"] is False


def test_the_five_percent_rule_marks_a_drop_off():
    page = _page(_row("a", "Falls", "1st", "10", "2.5%")
                 + _row("b", "Survives", "1st", "40", "10.0%"))
    rows = {r["player_name"]: r for r in hb.parse_election_page(page, 2025)["rows"]}
    assert rows["Falls"]["dropped_off"] is True
    assert rows["Survives"]["dropped_off"] is False


def test_an_elected_player_is_never_also_a_drop_off():
    page = _page(_row("a", "Elected", "1st", "393", "99.7%"))
    r = hb.parse_election_page(page, 2025)["rows"][0]
    assert r["elected"] is True and r["dropped_off"] is False


def test_the_ballot_number_survives_its_ordinal():
    page = _page(_row("a", "Tenth", "10th", "325", "82.5%"))
    r = hb.parse_election_page(page, 2025)["rows"][0]
    assert r["ballot_number"] == 10


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

def test_the_veterans_table_is_read_and_labelled():
    page = _page(_row("a", "Committee Pick", "", "", ""),
                 table_id="hof_Veterans")
    rows = hb.parse_election_page(page, 2022)["rows"]
    assert rows and all(r["route"] == "VETERANS" for r in rows)


def test_a_veterans_row_gets_no_bbwaa_ballot_arithmetic():
    """The 75% rule and the ballot count belong to the writers' election. A
    committee row carrying them would state a fact about a vote that did not
    happen that way."""
    page = _page(_row("a", "Committee Pick", "", "", ""),
                 table_id="hof_Veterans")
    r = hb.parse_election_page(page, 2022)["rows"][0]
    assert r["ballots_cast"] is None
    assert r["elected"] is None


def test_statsapi_routes_split_writers_from_committees():
    payload = {"awards": [
        {"season": "2026", "notes": "Contemporary Era Ballot Selection",
         "player": {"id": 116999, "nameFirstLast": "Jeff Kent"}},
        {"season": "2025", "notes": "",
         "player": {"id": 400085, "nameFirstLast": "Ichiro Suzuki"}},
        {"season": "2022", "notes": "Golden Days Era Committee",
         "player": {"id": 121314, "nameFirstLast": "Gil Hodges"}},
    ]}
    out = hb.parse_statsapi(payload)
    by = {r["player_name"]: r for r in out}
    assert by["Jeff Kent"]["route"] == "VETERANS"
    assert by["Gil Hodges"]["route"] == "VETERANS"
    # Ichiro's note is EMPTY, and an empty note says nothing about the route.
    # This used to assert BBWAA, which is how the first build reported 342
    # writers' inductees against 12 committee ones; the committees have in fact
    # elected more players than the writers. The route is derived later, from
    # the ballot tables, and until then it is UNKNOWN.
    assert by["Ichiro Suzuki"]["route"] == "UNKNOWN"
    assert all(r["elected"] is True for r in out)
    assert by["Jeff Kent"]["route_note"], (
        "the raw note was dropped, so a route misclassification could never be "
        "audited from the artifact")


# --------------------------------------------------------------------------
# It must not invent anything
# --------------------------------------------------------------------------

def test_a_row_with_no_player_cell_is_skipped_not_guessed():
    page = _page('<tr><th data-stat="ranker">1</th>'
                 '<td data-stat="votes">10</td></tr>'
                 + _row("a", "Real", "1st", "300", "76.0%"))
    rows = hb.parse_election_page(page, 2025)["rows"]
    assert [r["player_name"] for r in rows] == ["Real"]


def test_a_missing_table_yields_no_rows_rather_than_an_error():
    out = hb.parse_election_page("<html><body>nothing here</body></html>", 1941)
    assert out["rows"] == [] and out["tables"] == []


def test_the_public_benchmarks_are_captured_in_the_same_pass():
    """H-DATA-4 scores the in-house shelf against B-Ref's own columns. Pulling
    them here means the bake-off never needs a second crawl of the same pages."""
    page = _page(_row("suzukic01", "Ichiro Suzuki", "1st", "393", "99.7%",
                      monitor="235", standard="42", war="60.0", war7="43.7",
                      jaws="51.8"))
    b = hb.parse_election_page(page, 2025)["benchmarks"]
    assert len(b) == 1
    assert b[0]["hof_monitor"] == 235.0
    assert b[0]["JAWS"] == 51.8
    assert b[0]["player_id"] == "suzukic01"


# --------------------------------------------------------------------------
# Against the real cached page, when there is one
# --------------------------------------------------------------------------

def test_the_real_2025_page_parses_to_the_known_election():
    p = ROOT / ".cache" / "hof" / "bref" / "hof_2025.html"
    if not p.exists():
        pytest.skip("the 2025 election page is not cached")
    out = hb.parse_election_page(p.read_text(encoding="utf-8"), 2025)
    assert out["ballots_cast"] == 394, (
        f"got {out['ballots_cast']}; the 2025 BBWAA election had 394 ballots "
        "and needed 296 for election")
    assert out["votes_needed"] == 296
    bbwaa = [r for r in out["rows"] if r["route"] == "BBWAA"]
    elected = sorted(r["player_name"] for r in bbwaa if r["elected"])
    assert elected == ["Billy Wagner", "CC Sabathia", "Ichiro Suzuki"], (
        f"got {elected}; the 2025 class was Suzuki, Sabathia and Wagner")
    ided = sum(1 for r in out["rows"] if r["player_id"])
    assert ided >= len(out["rows"]) - 1, (
        f"only {ided} of {len(out['rows'])} rows carry a Baseball-Reference id")


# --------------------------------------------------------------------------
# The encoding defect, which cost the ingest every accented player
# --------------------------------------------------------------------------

def test_the_fetch_decodes_utf8_explicitly_and_never_uses_r_text():
    """Baseball-Reference serves UTF-8 without always saying so, and the HTTP
    spec tells a client to assume ISO-8859-1 for text/* with no charset.
    requests obeys the spec, so r.text hands back the UTF-8 bytes of an accented
    character read one at a time. Written to a UTF-8 cache file that damage is
    permanent, and it does not look like an error, it looks like a name."""
    src = (ROOT / "tools" / "hof_ballot_ingest.py").read_text(encoding="utf-8")
    i = src.index("def fetch_year(")
    body = src[i:src.index("def fetch_statsapi(", i)]
    assert 'r.content.decode("utf-8"' in body, (
        "fetch_year no longer forces a UTF-8 decode, so every accented player "
        "will silently fail to join and land in the unresolved bucket")
    assert "p.write_text(r.text" not in body, (
        "fetch_year is caching requests' guessed decoding")


def test_a_latin1_double_decode_is_what_the_bug_looked_like():
    """Documents the damage so a future reader recognises it. This is the exact
    transformation that turned Carlos Beltran's name into a join failure."""
    good = "Beltr\u00e1n"                     # U+00E1, the real character
    damaged = good.encode("utf-8").decode("latin-1")
    assert damaged == "Beltr\u00c3\u00a1n"
    assert damaged != good


# --------------------------------------------------------------------------
# The join key
# --------------------------------------------------------------------------

def test_accents_normalise_away():
    assert hb._norm_name("Carlos Beltr\u00e1n") == "carlos beltran"
    assert hb._norm_name("Pedro Mart\u00ednez") == "pedro martinez"
    assert hb._norm_name("Iv\u00e1n Rodr\u00edguez") == "ivan rodriguez"


def test_generational_suffixes_normalise_away():
    """StatsAPI writes them and Baseball-Reference does not, so a suffix left in
    place sends a real inductee to the unresolved bucket looking like a
    non-player."""
    assert hb._norm_name("Tim Raines Sr.") == hb._norm_name("Tim Raines")
    assert hb._norm_name("Tony La Russa Jr.") == hb._norm_name("Tony La Russa")
    assert hb._norm_name("Ken Griffey Jr.") == hb._norm_name("Ken Griffey")


def test_normalisation_does_not_collapse_different_people():
    assert hb._norm_name("Pedro Martinez") != hb._norm_name("Dennis Martinez")


# --------------------------------------------------------------------------
# Route derivation
# --------------------------------------------------------------------------

def _ballot(name, year, route, elected, pid="x01"):
    return {"player_id": pid, "player_name": name, "election_year": year,
            "route": route, "elected": elected, "vote_pct": 0.9 if elected else 0.1}


def test_an_empty_note_is_never_defaulted_to_the_writers():
    """The defect that made derive_routes necessary. StatsAPI's notes field is
    empty on 333 of 354 recipients; treating empty as a writers' election
    reported 342 BBWAA against 12 committee inductees, when the committees have
    in fact elected more players than the writers."""
    out = hb.parse_statsapi({"awards": [
        {"season": "1980", "notes": "", "player": {"id": 1, "nameFirstLast": "Nobody"}}]})
    assert out[0]["route"] == "UNKNOWN", (
        f"an empty note resolved to {out[0]['route']}; it must stay UNKNOWN "
        "until the ballot tables say otherwise")


def test_a_writers_election_is_recovered_from_the_ballot():
    ind = hb.parse_statsapi({"awards": [
        {"season": "2025", "notes": "",
         "player": {"id": 1, "nameFirstLast": "Ichiro Suzuki"}}]})
    rows = [_ballot("Ichiro Suzuki", 2025, "BBWAA", True, "suzukic01")]
    got = hb.derive_routes(ind, rows)["inductees"][0]
    assert got["route"] == "BBWAA"
    assert "BBWAA" in got["route_source"]
    assert got["player_id"] == "suzukic01", (
        "the derivation did not carry the bbref id back, so the inductee still "
        "cannot be joined to the career frame")


def test_a_committee_election_is_recovered_from_the_veterans_table():
    ind = hb.parse_statsapi({"awards": [
        {"season": "2022", "notes": "",
         "player": {"id": 2, "nameFirstLast": "Gil Hodges"}}]})
    rows = [_ballot("Gil Hodges", 2022, "VETERANS", None, "hodgegi01")]
    got = hb.derive_routes(ind, rows)["inductees"][0]
    assert got["route"] == "VETERANS"
    assert "veterans" in got["route_source"].lower()


def test_a_statsapi_note_beats_the_ballot_join():
    """The note is the only direct statement either source makes about the
    route, so it wins outright when present."""
    ind = hb.parse_statsapi({"awards": [
        {"season": "2026", "notes": "Contemporary Era Ballot Selection",
         "player": {"id": 3, "nameFirstLast": "Jeff Kent"}}]})
    rows = [_ballot("Jeff Kent", 2026, "BBWAA", True)]
    got = hb.derive_routes(ind, rows)["inductees"][0]
    assert got["route"] == "VETERANS"
    assert got["route_source"] == "statsapi note"


def test_an_unmatched_inductee_stays_unknown_and_explains_itself():
    ind = hb.parse_statsapi({"awards": [
        {"season": "2006", "notes": "",
         "player": {"id": 4, "nameFirstLast": "Alex Pompez"}}]})
    got = hb.derive_routes(ind, [])["inductees"][0]
    assert got["route"] == "UNKNOWN"
    assert "manager" in got["route_source"] or "not found" in got["route_source"]


def test_a_losing_ballot_appearance_is_not_an_election():
    """Appearing on a ballot is not being elected. If this ever resolved, every
    candidate who was ever considered would read as a Hall of Famer."""
    ind = hb.parse_statsapi({"awards": [
        {"season": "2025", "notes": "",
         "player": {"id": 5, "nameFirstLast": "Andruw Jones"}}]})
    rows = [_ballot("Andruw Jones", 2025, "BBWAA", False, "jonesan01")]
    got = hb.derive_routes(ind, rows)["inductees"][0]
    assert got["route"] == "UNKNOWN", (
        "a candidate who appeared on the ballot and was NOT elected was "
        "resolved as a writers' inductee")
