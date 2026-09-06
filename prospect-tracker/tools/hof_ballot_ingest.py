"""H-DATA-2: the Hall of Fame ballot panel, 1936 to the present.

WHAT IT IS FOR. hof_data.py can already build the whole feature half of the Hall
of Fame frame: career WAR, WAR7, JAWS, ink, era factors, position class. It
refuses to produce a LABEL, and the refusal is deliberate: `label_frame()` raises
`BallotSourceMissing` rather than guessing a membership list, because a Hall of
Fame model whose positive class was assembled from memory is not a model of
anything. This tool builds the source that refusal points at.

TWO UPSTREAMS, AND THEY ANSWER DIFFERENT QUESTIONS.

  Baseball-Reference election pages (/awards/hof_<year>.shtml) carry the FULL
  BBWAA BALLOT: every candidate, their vote count, their vote share and which
  year of their eligibility window it was. This is the only source for the people
  who were considered and NOT elected, which is most of the label's information.
  The same tables carry B-Ref's own HoF Monitor, HoF Standards and JAWS columns,
  which are the public answer key the in-house benchmark shelf (H-DATA-4) is
  scored against, so they are captured in the same pass.

  StatsAPI /awards/MLBHOF/recipients carries the INDUCTEES by any route, with a
  `notes` field naming the route ("Contemporary Era Ballot Selection" and so on).
  The writers elect only some Hall of Famers; the era and veterans committees
  elect the rest, on a different and much longer clock. Owner decision 12 makes
  any-route induction the PRIMARY label, so this source is not a nice-to-have.

THE ROUTE FIELD IS THE WHOLE POINT OF MERGING THEM. Pooling two selection
processes into one label without recording which one acted is how a fold whose
positives are mostly committee inductions comes to look like model skill. Every
row carries its route, and the artifact publishes the per-route counts so a
reader can see the mixture rather than infer it.

WHAT THIS TOOL WILL NOT DO. It will not invent a row. A year whose page is
missing, empty or unparseable is recorded in `years_failed` with the reason, and
the artifact says how many years it covers, because a ballot panel silently
missing a decade would bias every censoring rule built on top of it.

Politeness: Baseball-Reference asks for at most about 20 requests a minute. The
default throttle is well inside that, pages are cached under .cache/hof/bref/,
and a cached year is never refetched.
"""
from __future__ import annotations

import argparse
import html as _html
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
CACHE = ROOT / ".cache" / "hof"
BREF_CACHE = CACHE / "bref"
OUT = DATA / "hof_ballots.json"
BENCH_OUT = DATA / "hof_public_benchmarks.json"

BREF_URL = "https://www.baseball-reference.com/awards/hof_{year}.shtml"
STATSAPI_URL = "https://statsapi.mlb.com/api/v1/awards/MLBHOF/recipients"

#: The first BBWAA election. Nothing before this exists to fetch.
FIRST_ELECTION = 1936

#: Seconds between Baseball-Reference requests. B-Ref asks for roughly 20 a
#: minute; 3.5 s is about 17 and leaves headroom. Do not lower this to make a
#: backfill finish sooner: the cost of being rate-limited mid-run is a partial
#: panel, and a partial panel is worse than a slow one.
BREF_THROTTLE_S = 3.5

log = logging.getLogger("hof_ballot_ingest")

#: B-Ref player ids are mostly [a-z]{5}[a-z0-9]{3}, but not always: CC Sabathia
#: is "sabatc.01", with a dot. A pattern that assumes the common shape silently
#: drops those rows, which is how a real player becomes a hole in the panel.
_ID_RE = re.compile(r'/players/[a-z0-9]/([a-z0-9.\-\']+?)\.shtml')
_TAG_RE = re.compile(r"<[^>]+>")

#: Words that mark a committee election in StatsAPI's prose `notes` field. The
#: list is deliberately generous: misfiling a committee pick as a writers' pick
#: pollutes the secondary label, and the raw note survives on every row so a
#: reader can audit the call.
_VETERANS_WORDS: tuple[str, ...] = (
    "veteran", "committee", "era ballot", "era committee", "contemporary",
    "golden days", "early baseball", "today's game", "modern baseball",
    "expansion era", "pre-integration", "old timers", "special election",
)


def _text(fragment: str) -> str:
    # NBSP to a plain space before stripping. B-Ref separates a name from its
    # markers with &nbsp;, and a name that keeps a U+00A0 will not join to
    # anything and will not compare equal to the same name from another source.
    return _html.unescape(_TAG_RE.sub("", fragment)).replace(" ", " ").strip()


#: B-Ref marks an enshrined player with a <span class="hilite">HOF</span> after
#: the name. That is a genuine fact and it is a DANGEROUS one: it is true AS OF
#: THE SCRAPE, not as of the election year on the row. Carlos Beltran's 2025 row
#: carries it while his 2025 result was 70.3%, short of the 75% bar. Fed to a
#: forward-chained model as a feature it is a perfect leak of the outcome. It is
#: captured because it is a free cross-check on the label, and it is named
#: `bref_hof_marker_as_of_scrape` so that nobody can use it without reading what
#: it is.
_HOF_MARK_RE = re.compile(r'<span class="hilite">\s*HOF\s*</span>', re.I)


def _name_and_marker(cell_html: str) -> tuple[str, bool]:
    """(clean name, is-enshrined-as-of-scrape) from a player cell."""
    marked = bool(_HOF_MARK_RE.search(cell_html))
    name = _text(_HOF_MARK_RE.sub("", cell_html))
    # Some rows carry a trailing bare "HOF" with no span.
    name = re.sub(r"\s*\bHOF\b\s*$", "", name).strip()
    return name, marked


def _num(s):
    if s is None:
        return None
    s = str(s).replace(",", "").replace("%", "").strip()
    if not s or s in ("-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _table(page: str, table_id: str) -> str | None:
    """The raw HTML of one table, or None. B-Ref sometimes buries a table in an
    HTML comment; both placements are handled by searching the whole page."""
    marker = f'id="{table_id}"'
    i = page.find(marker)
    if i < 0:
        return None
    tail = page[i:]
    j = tail.find("</table>")
    return tail[:j] if j > 0 else tail


def parse_election_page(page: str, year: int) -> dict:
    """Rows for one election year, from the page HTML. PURE: no network, no
    clock, no disk, so it is testable against a committed fixture.

    Returns {"rows": [...], "benchmarks": [...], "ballots_cast": int|None,
             "votes_needed": int|None, "tables": [...]}.
    """
    out_rows, bench = [], []
    tables = []
    for table_id, route in (("hof_BBWAA", "BBWAA"),
                            ("hof_Veterans", "VETERANS")):
        tbl = _table(page, table_id)
        if tbl is None:
            continue
        tables.append(table_id)
        body_m = re.search(r"<tbody>(.*?)$", tbl, re.S)
        if not body_m:
            continue
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body_m.group(1), re.S):
            if "thead" in row or 'class="over_header"' in row:
                continue
            raw = dict(re.findall(r'data-stat="([^"]+)"[^>]*>(.*?)</t[hd]>',
                                  row, re.S))
            cells = {k: _text(v) for k, v in raw.items()}
            if not cells.get("player"):
                continue
            name, hof_mark = _name_and_marker(raw.get("player", ""))
            m = _ID_RE.search(row)
            pid = m.group(1) if m else None
            yob = cells.get("year_on_ballot") or ""
            ballot_number = _num(re.sub(r"[^0-9]", "", yob)) if yob else None
            votes = _num(cells.get("votes"))
            pct = _num(cells.get("votes_pct"))
            out_rows.append({
                "player_id": pid,
                "player_name": name,
                "bref_hof_marker_as_of_scrape": hof_mark,
                "election_year": int(year),
                "route": route,
                "ballot_number": int(ballot_number) if ballot_number else None,
                "votes": int(votes) if votes is not None else None,
                "ballots_cast": None,          # filled by the caller, see below
                "vote_pct": (pct / 100.0) if pct is not None else None,
                # `elected` is NOT decided here. The BBWAA table's 75% rule is
                # applied by the caller against the year's real ballot count, and
                # committee elections are confirmed against StatsAPI, because a
                # table's own formatting is not a fact about an election.
                "elected": None,
                "dropped_off": None,
                "source": "baseball-reference",
            })
            # The public answer key, captured in the same pass so the benchmark
            # bake-off never needs a second crawl.
            b = {k: _num(cells.get(k)) for k in
                 ("hof_monitor", "hof_standard", "WAR_career", "WAR_peak7",
                  "JAWS")}
            if pid and any(v is not None for v in b.values()):
                b.update({"player_id": pid, "election_year": int(year),
                          "player_name": name,
                          "JAWS_pos": cells.get("JAWS_pos") or None})
                bench.append(b)

    m_needed = re.search(r"(\d[\d,]*)\s*votes needed", page, re.I)
    needed = _num(m_needed.group(1)) if m_needed else None
    # BALLOTS CAST, derived and cross-checked rather than scraped. B-Ref does not
    # print it in a stable place, but votes and vote share are both published, so
    # the count follows from any row with a non-zero share. Several rows are
    # used and the median taken, because a single row's rounded percentage can
    # be off by one ballot.
    ests = []
    for r in out_rows:
        if r["route"] != "BBWAA":
            continue
        if r["votes"] and r["vote_pct"]:
            ests.append(r["votes"] / r["vote_pct"])
    ballots = None
    if ests:
        ests.sort()
        ballots = int(round(ests[len(ests) // 2]))
    elif needed:
        # 75% of the ballots cast, inverted. Weaker, and flagged as such.
        ballots = int(round(needed / 0.75))
    for r in out_rows:
        if r["route"] == "BBWAA":
            r["ballots_cast"] = ballots
            if r["vote_pct"] is not None:
                r["elected"] = bool(r["vote_pct"] >= 0.75)
                # The five percent rule: a candidate under 5% falls off the
                # ballot. Applied only where the share is known.
                r["dropped_off"] = bool(r["vote_pct"] < 0.05
                                        and not r["elected"])
    return {"rows": out_rows, "benchmarks": bench, "ballots_cast": ballots,
            "votes_needed": int(needed) if needed else None,
            "ballots_cast_method": ("median of votes/share over BBWAA rows"
                                    if ests else
                                    "inverted from the 75% votes-needed line"
                                    if needed else None),
            "tables": tables}


def parse_statsapi(payload: dict) -> list[dict]:
    """Inductees by any route, from the StatsAPI awards payload. PURE.

    The `notes` field names the route in prose ("Contemporary Era Ballot
    Selection", "Veterans Committee", and so on). Anything that does not name a
    committee is treated as the writers' ballot, and the raw note is carried
    through so a misclassification can be found rather than guessed at.
    """
    out = []
    for a in (payload.get("awards") or []):
        p = a.get("player") or {}
        season = a.get("season")
        note = str(a.get("notes") or "")
        low = note.lower()
        # THE ROUTE IS MOSTLY NOT IN THIS FIELD, and assuming otherwise was the
        # first version's mistake. Measured on the live payload 2026-09-06:
        # `notes` is EMPTY on 333 of 354 recipients, and of the 21 that carry
        # one, several say things like "No cap logo on plaque" that have nothing
        # to do with how the player was elected. Defaulting an empty note to the
        # writers' ballot reported 342 BBWAA inductees against 12 committee
        # ones, which is badly wrong: the committees have elected far more than
        # twelve players.
        #
        # So an empty or uninformative note yields UNKNOWN, and the route is
        # DERIVED afterwards by joining to the Baseball-Reference ballot tables,
        # which do record it (a player in that year's hof_Veterans table was a
        # committee selection; one clearing 75% in hof_BBWAA was a writers'
        # pick). See derive_routes below.
        if any(w in low for w in _VETERANS_WORDS):
            route = "VETERANS"
        else:
            route = "UNKNOWN"
        out.append({
            "mlbam_id": p.get("id"),
            "player_name": p.get("nameFirstLast"),
            "election_year": int(season) if season else None,
            "route": route,
            "route_note": note or None,
            "elected": True,
            "source": "statsapi",
        })
    return out


def _norm_name(n: str) -> str:
    """A join key that survives the two sources' punctuation differences.

    StatsAPI writes "Ken Griffey Jr." and Baseball-Reference "Ken Griffey Jr";
    accents, periods and case all differ. Stripped to lowercase letters and
    single spaces, which is crude and is checked by the resolution rate the
    artifact publishes rather than assumed to work.
    """
    import unicodedata
    n = unicodedata.normalize("NFKD", str(n or ""))
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^A-Za-z ]", " ", n).lower()
    n = re.sub(r"\s+", " ", n).strip()
    # GENERATIONAL SUFFIXES DIFFER BETWEEN THE SOURCES. StatsAPI writes "Tim
    # Raines Sr." and "Tony La Russa Jr."; Baseball-Reference writes neither.
    # Dropping the suffix costs nothing here (no two Hall of Famers share a full
    # name in the same election year) and recovers rows that would otherwise
    # land in UNKNOWN and look like non-players.
    n = re.sub(r"\b(jr|sr|ii|iii|iv)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def derive_routes(inductees: list[dict], ballot_rows: list[dict]) -> dict:
    """Resolve each inductee's election route from the ballot tables. PURE.

    Mutates nothing: returns {"inductees": [...], "stats": {...}} with a
    `route_source` on every row saying HOW the route was decided, because a
    route that cannot be traced is a route nobody should trust.

    THE RULES, in order:
      1. A committee named in the StatsAPI note wins outright. It is the only
         direct statement either source makes.
      2. Otherwise, look for the player in that election year's Baseball-Reference
         tables. A row in hof_Veterans is a committee selection. A BBWAA row at
         or above 75% is a writers' pick.
      3. Anything else stays UNKNOWN. It is NOT defaulted to the writers, which
         is what produced the 342-to-12 split that made this function necessary.
    """
    by_year_name = {}
    for r in ballot_rows:
        by_year_name.setdefault(
            (r["election_year"], _norm_name(r["player_name"])), []).append(r)

    out, stats = [], {"note": 0, "ballot": 0, "adjacent": 0,
                      "unknown": 0}
    for ind in inductees:
        row = dict(ind)
        if row.get("route") == "VETERANS":
            row["route_source"] = "statsapi note"
            stats["note"] += 1
            out.append(row)
            continue
        hits = by_year_name.get(
            (row.get("election_year"), _norm_name(row.get("player_name"))), [])
        vet = [h for h in hits if h["route"] == "VETERANS"]
        won = [h for h in hits if h["route"] == "BBWAA" and h.get("elected")]
        if vet and not won:
            row["route"] = "VETERANS"
            row["route_source"] = "baseball-reference veterans table"
            row["player_id"] = vet[0].get("player_id")
            stats["ballot"] += 1
        elif won:
            row["route"] = "BBWAA"
            row["route_source"] = "baseball-reference BBWAA table, elected"
            row["player_id"] = won[0].get("player_id")
            row["vote_pct"] = won[0].get("vote_pct")
            stats["ballot"] += 1
        else:
            # THE ADJACENT YEAR, and only for committees. The era committees vote
            # in DECEMBER for the following summer's class, so StatsAPI stamps
            # 2021 where Baseball-Reference tables 2022, and six real inductees
            # (Hodges, Kaat, Minoso, Oliva, O'Neil, Fowler) fell into the
            # unresolved bucket looking like non-players. Owner decision 12
            # already requires the artifact to say which clock each row is on,
            # so this is that rule applied rather than a fudge.
            #
            # DELIBERATELY NOT APPLIED TO THE WRITERS. The BBWAA votes and the
            # result is announced in the same January, so a writers' row has no
            # year ambiguity, and allowing a one-year slide there would let a
            # candidate who failed in one year be credited with a neighbouring
            # year's election.
            adj = []
            for dy in (1, -1):
                for h in by_year_name.get(
                        ((row.get("election_year") or 0) + dy,
                         _norm_name(row.get("player_name"))), []):
                    if h["route"] == "VETERANS":
                        adj.append((dy, h))
            if adj:
                dy, h = adj[0]
                row["route"] = "VETERANS"
                row["route_source"] = (
                    "baseball-reference veterans table, "
                    f"{dy:+d} year (era committees vote in December for the "
                    "following summer's class, so the two sources stamp "
                    "different years)")
                row["player_id"] = h.get("player_id")
                row["ballot_year_offset"] = dy
                stats["adjacent"] += 1
            else:
                row["route"] = "UNKNOWN"
                row["route_source"] = (
                    "not found in that year's ballot tables or the adjacent "
                    "one; most likely a manager, executive, umpire or Negro "
                    "Leagues honouree, none of whom appear on a player ballot")
                stats["unknown"] += 1
        out.append(row)
    return {"inductees": out, "stats": stats}


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _session():
    import feed_cache
    return feed_cache.SESSION


def fetch_year(year: int, *, refresh: bool = False, session=None) -> str | None:
    """One election page, cached. Returns HTML or None."""
    BREF_CACHE.mkdir(parents=True, exist_ok=True)
    p = BREF_CACHE / f"hof_{year}.html"
    if p.exists() and not refresh:
        return p.read_text(encoding="utf-8", errors="replace")
    s = session or _session()
    try:
        r = s.get(BREF_URL.format(year=year), timeout=45)
    except Exception as exc:                              # noqa: BLE001
        log.warning("hof %d: request failed: %s", year, exc)
        return None
    if r.status_code != 200 or len(r.content) < 2000:
        log.warning("hof %d: status %s, %d bytes", year, r.status_code,
                    len(r.content))
        return None
    # DECODE AS UTF-8 EXPLICITLY, never r.text. Baseball-Reference serves UTF-8
    # and does not always say so in the Content-Type, and the HTTP spec tells a
    # client to assume ISO-8859-1 for text/* with no charset. requests obeys the
    # spec, so r.text hands back "BeltrÃ¡n": the UTF-8 bytes of an
    # accented character read one byte at a time. Written to a UTF-8 file that
    # damage is baked in permanently, and it does not look like an error, it
    # looks like a name. It cost this ingest a silent join failure on every
    # accented player, which is a large and non-random slice of the Hall.
    text = r.content.decode("utf-8", errors="replace")
    p.write_text(text, encoding="utf-8")
    time.sleep(BREF_THROTTLE_S)
    return text


def fetch_statsapi(*, refresh: bool = False, session=None) -> dict | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / "statsapi_recipients.json"
    if p.exists() and not refresh:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    s = session or _session()
    try:
        r = s.get(STATSAPI_URL, timeout=45)
        r.raise_for_status()
    except Exception as exc:                              # noqa: BLE001
        log.warning("statsapi recipients failed: %s", exc)
        return None
    # Explicit, for the same reason fetch_year is explicit. This endpoint sends
    # application/json and requests decodes that as UTF-8 per spec, so it is
    # correct today; relying on a header to keep being right is what damaged
    # every accented name on the Baseball-Reference side.
    text = r.content.decode("utf-8", errors="replace")
    p.write_text(text, encoding="utf-8")
    return json.loads(text)


def build(*, first: int = FIRST_ELECTION, last: int | None = None,
          refresh: bool = False, write: bool = True) -> dict:
    last = last or datetime.now(timezone.utc).year
    rows, bench, years_ok, years_failed = [], [], [], []
    years_no_election: list[int] = []
    per_year = {}
    for year in range(first, last + 1):
        page = fetch_year(year, refresh=refresh)
        if not page:
            years_failed.append({"year": year, "why": "not fetched"})
            continue
        try:
            parsed = parse_election_page(page, year)
        except Exception as exc:                          # noqa: BLE001
            years_failed.append({"year": year, "why": f"parse failed: {exc}"})
            continue
        if not parsed["rows"]:
            # NOT A FAILURE. The writers held no election in several years
            # (1940, 1941, 1943, 1944 and 1946 among them), so the page exists
            # and carries no ballot table. Recording that as a fetch failure
            # would invite somebody to "fix" it by inventing rows.
            years_no_election.append(year)
            continue
        rows.extend(parsed["rows"])
        bench.extend(parsed["benchmarks"])
        years_ok.append(year)
        per_year[str(year)] = {
            "n_rows": len(parsed["rows"]),
            "ballots_cast": parsed["ballots_cast"],
            "ballots_cast_method": parsed["ballots_cast_method"],
            "votes_needed": parsed["votes_needed"],
            "tables": parsed["tables"],
        }

    sapi = fetch_statsapi(refresh=refresh)
    inductees = parse_statsapi(sapi) if sapi else []
    derived = derive_routes(inductees, rows)
    inductees = derived["inductees"]
    route_stats = derived["stats"]

    n_id = sum(1 for r in rows if r["player_id"])
    by_route = {}
    for r in rows:
        by_route[r["route"]] = by_route.get(r["route"], 0) + 1
    ind_route = {}
    for r in inductees:
        ind_route[r["route"]] = ind_route.get(r["route"], 0) + 1

    art = {
        "generated_at": datetime.now(timezone.utc)
                        .replace(microsecond=0).isoformat(),
        "produced_by": "tools/hof_ballot_ingest.py",
        "schema_version": 1,
        "election_years_covered": years_ok,
        "n_election_years": len(years_ok),
        "years_failed": years_failed,
        "years_with_no_election": years_no_election,
        "years_with_no_election_note": (
            "the page was fetched and parsed and carried no ballot table. The "
            "writers did not hold an election every year; this is a fact about "
            "the Hall of Fame, not a gap in the ingest, and it is listed apart "
            "from years_failed so nobody tries to fill it."),
        "per_year": per_year,
        "n_ballot_rows": len(rows),
        "n_ballot_rows_with_bbref_id": n_id,
        "bbref_id_coverage": (round(n_id / len(rows), 4) if rows else None),
        "ballot_rows_by_route": by_route,
        "n_statsapi_inductees": len(inductees),
        "statsapi_inductees_by_route": ind_route,
        "route_resolution": {
            "from_statsapi_note": route_stats["note"],
            "from_ballot_tables": route_stats["ballot"],
            "from_adjacent_year_committee": route_stats["adjacent"],
            "unresolved": route_stats["unknown"],
            "resolved_share": (round(
                (route_stats["note"] + route_stats["ballot"]
                 + route_stats["adjacent"]) / len(inductees), 4)
                if inductees else None),
            "adjacent_year_rule": (
                "applied to COMMITTEE rows only. The era committees vote in "
                "December for the following summer's class, so the two sources "
                "stamp different years. The writers vote and announce in the "
                "same January, so no year slide is allowed there: it would let "
                "a candidate who failed in one year be credited with a "
                "neighbouring year's election."),
            "why_not_from_the_note": (
                "StatsAPI's notes field is EMPTY on 333 of 354 recipients and "
                "several of the 21 that carry one say things like 'No cap logo "
                "on plaque'. Defaulting an empty note to the writers' ballot "
                "reported 342 BBWAA against 12 committee inductees, which is "
                "badly wrong. An unresolved route stays UNKNOWN and is never "
                "defaulted."),
            "what_unknown_usually_means": (
                "a manager, executive, umpire or Negro Leagues honouree, none "
                "of whom appear on a player ballot, or a name the join did not "
                "match. Both are visible in the rows themselves."),
        },
        "rows": rows,
        "statsapi_inductees": inductees,
        "bref_hof_marker_is_as_of_scrape_not_as_of_row": (
            "every ballot row carries bref_hof_marker_as_of_scrape, which is "
            "Baseball-Reference's own enshrinement flag AT THE MOMENT THE PAGE "
            "WAS FETCHED and not at the row's election year. Carlos Beltran's "
            "2025 row carries it while his 2025 result was 70.3%, short of the "
            "75% bar. As a model feature it is a perfect leak of the outcome. "
            "Use it to cross-check the label and never as an input."),
        "route_matters": (
            "the writers elect some Hall of Famers and the era and veterans "
            "committees elect the rest, on a different and much longer clock. "
            "Owner decision 12 makes any-route induction the primary label, so "
            "every row carries its route and the per-route counts are published: "
            "a fold whose positives are mostly committee inductions must not be "
            "able to pass as model skill."),
        "what_is_not_here": (
            "no row is invented. A year that could not be fetched or parsed is "
            "in years_failed with its reason, and the covered-year list is "
            "published, because a panel silently missing a decade would bias "
            "every censoring rule built on it. The StatsAPI side is keyed by "
            "MLBAM id and is NOT yet joined to the bbref ids the rest of the "
            "module uses; that join is a separate step and until it runs the "
            "committee inductees are a list rather than a label."),
    }
    if write:
        DATA.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(art, indent=1) + "\n", encoding="utf-8")
        BENCH_OUT.write_text(json.dumps({
            "generated_at": art["generated_at"],
            "produced_by": "tools/hof_ballot_ingest.py",
            "source": ("Baseball-Reference election pages: their own HoF "
                       "Monitor, HoF Standards, career WAR, WAR7 and JAWS "
                       "columns, captured in the same pass as the ballots"),
            "purpose": ("the public answer key for H-DATA-4. The in-house "
                        "benchmark shelf is scored AGAINST these, so the module "
                        "is benchmarked against the public work rather than "
                        "asserted over it."),
            "n_rows": len(bench),
            "rows": bench,
        }, indent=1) + "\n", encoding="utf-8")
    return art


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--first", type=int, default=FIRST_ELECTION)
    ap.add_argument("--last", type=int, default=None)
    ap.add_argument("--refresh", action="store_true",
                    help="refetch pages already cached")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s: %(message)s",
                        stream=sys.stdout)
    art = build(first=args.first, last=args.last, refresh=args.refresh,
                write=not args.dry_run)
    print(f"election years: {art['n_election_years']} "
          f"({min(art['election_years_covered'])}-"
          f"{max(art['election_years_covered'])})"
          if art["election_years_covered"] else "no years parsed")
    print(f"ballot rows: {art['n_ballot_rows']} "
          f"({art['bbref_id_coverage']} carry a bbref id) "
          f"by route {art['ballot_rows_by_route']}")
    print(f"statsapi inductees: {art['n_statsapi_inductees']} "
          f"by route {art['statsapi_inductees_by_route']}")
    if art["years_failed"]:
        print(f"years failed: {len(art['years_failed'])}")
        for y in art["years_failed"][:10]:
            print(f"   {y['year']}: {y['why']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
