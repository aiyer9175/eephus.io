# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV X5: older prospect-list vintages as dated board points (docs/efv-v2/EFV_X5_OLDER_VINTAGES.md).

WHAT THIS IS. The label pool is the binding constraint on eFV (the feature frontier closed
at 39 arms, zero survivors). This module turns public archived prospect lists published
before the repository's first real-grader vintage (2011) into dated board points, resolves
each printed name to a person id through the outcome-blind resolver (efv_identity), and
COUNTS the (side, list vintage, person) rows the development list-vintage frame lv_dev would
gain. It reads no outcome: no WAR, no label, no debut outcome, no eFV, no consensus score
and no source score, on any row. It imports no label or WAR module (test-enforced).

SOURCES. Each source key below is NEW and is not in source_backtest.SCORED_SOURCES,
consensus.py or any served artifact. A list year is ingested only when it passes the four
registered eligibility rules (public, terms recorded, dated inside the V preseason window,
at least ELIGIBLE_MATCH_RATE of its side-routed rows resolved). Only facts are kept:
printed name, rank, organization, position, the printed letter grade where a list prints
one, the publication date, the URL and the archive capture timestamp.

DATING. A point's snapshot_date is its list's publication date (`published_on`), taken from
the page's own dateline, or, when no page prints one, the earliest archive capture that
holds the list (`date_basis` = capture_upper_bound, a date at or after the true
publication). No point is dated after its list publication; every publication date lies in
[V-01-01, V-05-01) of its list year V; every capture is at or after the publication.

MEMBERSHIP (registration s6, counts only). A row (record, V, side) is in the augmented
frame when the printed position routes it to the side (efv_dataset._side_match), it has a
point published inside the V window, the resolver gives a person id from the name index
through V - 1, and that id has no major league (sport 1) line in any season 2005 to V - 1.

RESERVED FRAMES. No list dated 2020 or later is ingested (R-LV is spent, R-VM is never
read: nothing here reads a debut). GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): nothing
is grouped, counted or averaged by consensus-FV level; the only strata are source, list
year, vintage, side and identity route.
"""
from __future__ import annotations

import html as _html
import re
from datetime import datetime
from pathlib import Path

import efv_dataset as D
import efv_identity as ID
import efv_vintage_frame as F
import source_backtest as SB

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv_x5"
POINTS_PATH = LAB_DIR / "older_vintage_points.json"
CENSUS_PATH = LAB_DIR / "older_vintage_census.json"
CACHE_DIR = ROOT / ".cache" / "EFV_X5_OLDER_VINTAGES"
REGISTRATION = "docs/efv-v2/EFV_X5_OLDER_VINTAGES.md"

#: The earliest list vintage the resolver can serve: its index starts at
#: efv_identity.FIRST_INDEX_SEASON, and a V row matches seasons through V - 1 only.
FIRST_VINTAGE = ID.FIRST_INDEX_SEASON + 1
#: The last vintage this task ingests: the development vintages end at 2019 and
#: R-LV (2020, 2021) is never touched.
LAST_VINTAGE = max(F.DEV_VINTAGES)
#: Registration s4.4: a (source, list year) is ingested only when at least this share
#: of its side-routed rows resolves to a person id.
ELIGIBLE_MATCH_RATE = 0.80
#: Registration s6: the first season of the major league line check on a new row.
MLB_CHECK_FIRST_SEASON = 2005
#: Registration s7: the census's E_cond lv reference (data/efv_label_pool_census.json).
FLOOR_REF_ID = "lv_econd_within"
SIDES = F.SIDES

#: The candidate sources (registration s3). `ingest` is the outcome of the eligibility
#: rules as run on 2026-10-15; `terms` and `access` are the recorded terms.
SOURCES: dict[str, dict] = {
    "ba_top100_hist": {
        "publisher": "Baseball America",
        "list": "preseason Top 100 Prospects",
        "access": "Internet Archive Wayback Machine copies of baseballamerica.com pages "
                  "(all-time Top 100 index, capture 2017-07-06; the dated year pages for "
                  "each list's dateline); Python fetch, 1.5 s between requests",
        "terms": "Baseball America content is copyrighted (baseballamerica.com terms of "
                 "use: personal, non-commercial use). The pages were free to read without "
                 "a login when captured. The Internet Archive serves its copies for "
                 "research. Only list facts are stored; raw captures stay in the "
                 "gitignored cache. Not a licence to republish.",
        "grade_field": "rank only (no FV, no letter grade)",
    },
    "ba_org10_hist": {
        "publisher": "Baseball America",
        "list": "organization Top 10 Prospects (offseason, one team per page)",
        "access": "Internet Archive Wayback Machine copies of baseballamerica.com "
                  "organization-top-10-prospects pages, 2007 to 2013 folders",
        "terms": "as ba_top100_hist",
        "grade_field": "rank within organization only",
    },
    "bp_top100_hist": {
        "publisher": "Baseball Prospectus (Kevin Goldstein)",
        "list": "preseason Top 100 (2007 to 2009) and Top 101 (2010, 2011)",
        "access": "baseballprospectus.com/news/article/<id>/ (articles marked 'This is a "
                  "free article'); robots.txt allows the path, Crawl-delay 2",
        "terms": "Baseball Prospectus terms and conditions: personal, non-commercial use. "
                 "Free articles, no login. Only list facts are stored.",
        "grade_field": "rank only",
    },
    "sickels_hist": {
        "publisher": "John Sickels, Minor League Ball (SB Nation)",
        "list": "organization Top 20 Prospects with letter grades",
        "access": "Internet Archive Wayback Machine copies of minorleagueball.com posts "
                  "(the live site refuses scripted connections); posts by John Sickels "
                  "only, community FanPosts and the hypothetical 'shadow' lists excluded",
        "terms": "Vox Media terms of use: personal, non-commercial use. Public posts, no "
                 "login. Only list facts and the printed letter grade are stored.",
        "grade_field": "rank within organization and a letter grade (A to C-), printed "
                       "as 'extremely preliminary' by the author",
    },
    "mlbcom_top50_hist": {
        "publisher": "MLB.com (Jonathan Mayo)",
        "list": "Top 50 Prospects",
        "access": "Wayback copies of mlb.mlb.com/mlb/minorleagues/prospects/y2009/ and "
                  "the open data-graph.mlb.com GraphQL host (slugs sel-pr-2009-top100 and "
                  "sel-pr-2010-top100 return 50 rows each; 2005 to 2008 return none)",
        "terms": "MLB Advanced Media terms of use; public pages.",
        "grade_field": "rank only",
    },
    "fg_hulet_hist": {
        "publisher": "FanGraphs (Marc Hulet)",
        "list": "organization top 10 lists",
        "access": "WebFetch only (FanGraphs HTML blocks Python)",
        "terms": "FanGraphs terms of use; free articles.",
        "grade_field": "rank within organization",
    },
}

#: Source keys that carry no FV and are never scored; asserted disjoint from
#: SCORED_SOURCES at import.
NEW_SOURCE_KEYS: frozenset[str] = frozenset(SOURCES)
assert not (NEW_SOURCE_KEYS & set(SB.SCORED_SOURCES))

_MONTHS = ("January|February|March|April|May|June|July|August|September|October|"
           "November|December")
DATELINE_RE = re.compile(rf"\b({_MONTHS}) (\d{{1,2}}), (20\d\d)\b")
_POS_RE = re.compile(r"^(?:[0-9]?[a-z]{1,4})(?:/[0-9]?[a-z]{1,4})*$", re.I)
#: A printed name longer than this is prose, not a list row.
_MAX_NAME_LEN = 48


# ---------------------------------------------------------------------------
# small helpers

def window(vintage: int) -> tuple[str, str]:
    """[start, end) of the V preseason window (source_backtest's constants)."""
    v = int(vintage)
    return f"{v}{SB._WINDOW_START_MMDD}", f"{v}{SB._WINDOW_END_MMDD}"


def in_window(day: str | None, vintage: int) -> bool:
    lo, hi = window(vintage)
    return bool(day) and lo <= str(day)[:10] < hi


def capture_day(ts: str | None) -> str | None:
    """A Wayback timestamp (YYYYMMDDhhmmss) as YYYY-MM-DD."""
    s = str(ts or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 and s[:8].isdigit() else None


def parse_dateline(text: str) -> str | None:
    """The first 'Month D, YYYY' in `text`, as YYYY-MM-DD."""
    m = DATELINE_RE.search(text or "")
    if not m:
        return None
    return datetime.strptime(" ".join(m.groups()), "%B %d %Y").date().isoformat()


def html_text(t: str, *, block_newlines: bool = False) -> str:
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", t or "", flags=re.S | re.I)
    if block_newlines:
        s = re.sub(r"(?i)<(?:/p|br\s*/?|/li|li[^>]*|p[^>]*|/h\d|h\d[^>]*)>", "\n", s)
    s = re.sub(r"<[^>]+>", " " if not block_newlines else "", s)
    s = _html.unescape(s)
    if block_newlines:
        return "\n".join(re.sub(r"[ \t\r\f\v]+", " ", x).strip()
                         for x in s.split("\n") if x.strip())
    return re.sub(r"\s+", " ", s)


def _clean_name(s: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


# ---------------------------------------------------------------------------
# parsers (pure: page text in, list facts out; no stat line or prose is kept)

_BA_ALLTIME_ROW = re.compile(r"<td[^>]*>\s*<strong>\s*(\d+)\.\s*(.*?)</strong>\s*</td>", re.S)


def parse_ba_alltime(page: str) -> dict[int, list[dict]]:
    """{list year: [{rank, name, pos, team}]} from BA's all-time Top 100 index. The
    page's second column (each player's later major league line) is never read."""
    out: dict[int, list[dict]] = {}
    parts = re.split(r'<div id="(\d{4})"></div>', page or "")
    for i in range(1, len(parts), 2):
        year, seg = int(parts[i]), parts[i + 1]
        rows = []
        for m in _BA_ALLTIME_ROW.finditer(seg):
            body = _clean_name(m.group(2))
            bits = [b.strip() for b in body.split(",")]
            if len(bits) < 3:
                continue
            rows.append({"rank": int(m.group(1)), "name": bits[0], "pos": bits[1],
                         "team": ", ".join(bits[2:]).strip()})
        out[year] = rows
    return out


def parse_ba_org10(page: str) -> dict:
    """{published_on, rows: [{rank, name, pos}]} from one BA organization Top 10 page.
    The dateline is the first date after the site navigation; the list is the block
    between 'TOP TEN PROSPECTS' and 'BEST TOOLS'."""
    s = html_text(page)
    i = s.find("Sitemap")
    s2 = s[i:] if i >= 0 else s
    pub = parse_dateline(s2)
    rows = []
    k = s2.find("TOP TEN PROSPECTS")
    if k >= 0:
        e = s2.find("BEST TOOLS", k)
        block = s2[k + len("TOP TEN PROSPECTS"): e if e > 0 else k + 800].strip()
        for m in re.finditer(r"(\d{1,2})\.\s+(.+?)(?=\s+\d{1,2}\.\s+|$)", block):
            bits = [b.strip() for b in m.group(2).split(",")]
            if len(bits) >= 2 and _POS_RE.match(bits[1]):
                rows.append({"rank": int(m.group(1)), "name": bits[0], "pos": bits[1]})
    rows = _ascending_run(rows)
    return {"published_on": pub, "rows": rows}


def _ascending_run(rows: list[dict]) -> list[dict]:
    """The first run of ranks 1, 2, 3 ... (stops at the first rank that does not go up,
    so a comment thread or a sidebar numbered list never extends a list)."""
    out: list[dict] = []
    for r in rows:
        if not out:
            if r["rank"] != 1:
                continue
        elif r["rank"] <= out[-1]["rank"]:
            break
        out.append(r)
    return out


def parse_bp_top100(page: str) -> dict:
    """{published_on, rows} from a Baseball Prospectus Top 100/101 article. Numbered
    paragraphs ('1. Name, POS, Team, age') or an ordered list (<ol>, rank = position)."""
    i = (page or "").find("article-content")
    head = (page or "")[:i] if i >= 0 else (page or "")
    pub = None
    for m in DATELINE_RE.finditer(html_text(head)):
        pub = datetime.strptime(" ".join(m.groups()), "%B %d %Y").date().isoformat()
    j = (page or "").find("Thank you for reading", i)
    seg = (page or "")[i: j if j > 0 else None] if i >= 0 else ""
    ordered = "<ol" in seg
    rows: list[dict] = []
    k = 0
    for ln in html_text(seg, block_newlines=True).split("\n"):
        m = re.match(r"^(\d{1,3})\.\s*(.+)$", ln)
        if m:
            rank, body = int(m.group(1)), m.group(2)
        elif ordered:
            rank, body = None, ln
        else:
            continue
        bits = [b.strip() for b in body.split(",")]
        if len(bits) < 3 or not _POS_RE.match(bits[1]) or len(bits[0]) > _MAX_NAME_LEN:
            continue
        k += 1
        rows.append({"rank": rank if rank is not None else k, "name": bits[0],
                     "pos": bits[1], "team": bits[2]})
    return {"published_on": pub, "rows": rows}


_SICKELS_BY = re.compile(r"by (John Sickels)\s+on (\w{3}) (\d{1,2}), (20\d\d)")
_SICKELS_ROW = re.compile(r"^\s*(\d{1,2})\)\s*([^,\n]+?),\s*([A-Za-z0-9/\-]+)\s*,\s*"
                          r"Grade\s+([A-F][+\-]?(?:/[A-F][+\-]?)?)", re.M)


def parse_sickels(page: str) -> dict:
    """{author, published_on, title, rows: [{rank, name, pos, grade}]} from one Minor
    League Ball post. The byline must be John Sickels's; the rows are the first
    ascending run of 'N) Name, POS, Grade X' lines."""
    s = html_text(page, block_newlines=True)
    b = _SICKELS_BY.search(s)
    pub = (datetime.strptime(f"{b.group(2)} {b.group(3)} {b.group(4)}", "%b %d %Y")
           .date().isoformat() if b else None)
    t = re.search(r"<title>(.*?)</title>", page or "", re.S | re.I)
    title = _clean_name(t.group(1)) if t else None
    rows = [{"rank": int(m.group(1)), "name": m.group(2).strip(), "pos": m.group(3),
             "grade": m.group(4)} for m in _SICKELS_ROW.finditer(s)]
    return {"author": b.group(1) if b else None, "published_on": pub, "title": title,
            "rows": _ascending_run(rows)}


def sickels_is_org_list(title: str | None) -> bool:
    """A Sickels organization list: 'Top 20 Prospects' (or 'Top 20+') in the title and
    not one of the hypothetical 'shadow' teams (unsigned draftees), which are not an
    organization's prospects."""
    t = (title or "").lower()
    return bool(re.search(r"top 20\+? prospects", t)) and "shadow" not in t


# ---------------------------------------------------------------------------
# the points artifact

def record_key(source: str, name: str) -> str:
    return f"x5:{source}:{ID.norm_name(name)}"


def build_records(lists: list[dict]) -> list[dict]:
    """Universe-shaped records from parsed lists. Each list is {source, list_year,
    published_on, date_basis, capture_ts, url, team (optional), rows}. One record per
    (source, normalized printed name); one point per list the name appears on."""
    recs: dict[str, dict] = {}
    for lst in lists:
        src = lst["source"]
        pub = lst["published_on"]
        for r in lst["rows"]:
            name = r.get("name")
            if not ID.norm_name(name):
                continue
            key = record_key(src, name)
            rec = recs.setdefault(key, {"player_key": key, "player_name": name,
                                        "position": (r.get("pos") or "").upper(),
                                        "source": src, "points": []})
            ps = {"rank": r.get("rank"), "grade": r.get("grade"), "fv_published": None,
                  "list_year": int(lst["list_year"]), "snapshot_date": pub,
                  "published_on": pub, "date_basis": lst["date_basis"],
                  "capture_ts": lst.get("capture_ts"), "url": lst.get("url"),
                  "team": r.get("team") or lst.get("team"),
                  "position_printed": r.get("pos")}
            rec["points"].append({"snapshot_date": pub, "per_source": {src: ps}})
    out = list(recs.values())
    for rec in out:
        rec["points"].sort(key=lambda p: p["snapshot_date"])
    out.sort(key=lambda r: r["player_key"])
    return out


def point_violations(records: list[dict]) -> list[str]:
    """Every breach of the dating rule (registration s5); [] when clean."""
    bad = []
    for rec in records:
        for p in rec.get("points") or []:
            for src, ps in (p.get("per_source") or {}).items():
                pub = ps.get("published_on")
                v = ps.get("list_year")
                tag = f"{rec.get('player_key')} {src} {v}"
                if src not in NEW_SOURCE_KEYS:
                    bad.append(f"{tag}: unknown source")
                if not pub or p.get("snapshot_date") != pub or ps.get("snapshot_date") != pub:
                    bad.append(f"{tag}: point not dated at its publication")
                if pub and v is not None and not in_window(pub, v):
                    bad.append(f"{tag}: published {pub} outside the {v} window")
                cap = capture_day(ps.get("capture_ts"))
                if pub and cap and cap < pub:
                    bad.append(f"{tag}: captured {cap} before publication {pub}")
                if v is not None and not (FIRST_VINTAGE <= int(v) <= LAST_VINTAGE):
                    bad.append(f"{tag}: vintage {v} outside {FIRST_VINTAGE}..{LAST_VINTAGE}")
                if int(str(pub or "0000")[:4]) >= min(F.RESERVED_LV):
                    bad.append(f"{tag}: dated in a reserved year")
    return bad


# ---------------------------------------------------------------------------
# membership and counts (registration s6)

def route_side(position: str | None) -> str | None:
    """The frame's side routing on a printed position (efv_dataset._side_match)."""
    rec = {"position": (position or "").upper()}
    for side in SIDES:
        if D._side_match(rec, side):
            return side
    return None


def _mlb_before(person_id: int, vintage: int) -> bool:
    return any(int(person_id) in F._mlb_ids(s)
               for s in range(MLB_CHECK_FIRST_SEASON, int(vintage)))


def resolve_list_rows(lst: dict, index: ID.NameIndex | None = None) -> list[dict]:
    """The resolver's answer for every row of one parsed list at its vintage: name,
    routed side, person id or None, route. The index holds seasons through V - 1."""
    V = int(lst["list_year"])
    if index is None:
        index = ID.build_index(V - 1)
    out = []
    for r in lst["rows"]:
        side = route_side(r.get("pos"))
        res = ID.resolve(r.get("name"), V, index, side) if side else None
        out.append({"name": r.get("name"), "side": side,
                    "person_id": res.person_id if res else None,
                    "how": res.how if res else "no_side"})
    return out


def match_rate(resolved: list[dict]) -> float | None:
    routed = [r for r in resolved if r["side"]]
    if not routed:
        return None
    return sum(1 for r in routed if r["how"] in ID.HOW_WITH_ID) / len(routed)


def augmented_rows(records: list[dict], vintage: int, *,
                   index: ID.NameIndex | None = None) -> list[dict]:
    """Every new-source row in the augmented frame at V (registration s6): one per
    (side, person id), with the sources and records that put it there."""
    V = int(vintage)
    if not (FIRST_VINTAGE <= V <= LAST_VINTAGE):
        raise ValueError(f"vintage {V} outside {FIRST_VINTAGE}..{LAST_VINTAGE}")
    F.guard_score_request(V, purpose="x5 count")
    if index is None:
        index = ID.build_index(V - 1)
    rows: dict[tuple[str, int], dict] = {}
    for rec in records:
        pts = [p for p in rec.get("points") or [] if in_window(p.get("snapshot_date"), V)]
        srcs = sorted({s for p in pts for s, ps in (p.get("per_source") or {}).items()
                       if ps.get("rank") is not None or ps.get("grade")
                       or ps.get("fv_published") is not None})
        if not srcs:
            continue
        side = route_side(rec.get("position"))
        if side is None:
            continue
        res = ID.resolve(rec.get("player_name"), V, index, side)
        if res.person_id is None:
            continue
        if _mlb_before(res.person_id, V):
            continue
        row = rows.setdefault((side, int(res.person_id)), {
            "side": side, "vintage": V, "person_id": int(res.person_id),
            "id_how": res.how, "sources": [], "records": []})
        row["sources"] = sorted(set(row["sources"]) | set(srcs))
        row["records"].append(rec["player_key"])
    return sorted(rows.values(), key=lambda r: (r["side"], r["person_id"]))


def current_frame_ids(vintage: int, universe: dict | None = None) -> dict[str, set[int]]:
    """{side: resolved ids} of the current lv frame at V (build_frame, milb and sidecars
    off; the outcome-blind id on each row). Empty below the first built vintage."""
    out: dict[str, set[int]] = {s: set() for s in SIDES}
    if int(vintage) not in F.DEV_VINTAGES:
        return out
    for side in SIDES:
        for r in F.build_frame(side, int(vintage), universe=universe, milb=False,
                               sidecars=False):
            if r.get("mlbam_id"):
                out[side].add(int(r["mlbam_id"]))
    return out


def mde95(n: float, sd_ref: float, n_ref: float, z: float) -> float | None:
    """The census floor curve: z * sd_ref * sqrt(n_ref / n)."""
    if not n or n <= 0:
        return None
    return float(z) * float(sd_ref) * (float(n_ref) / float(n)) ** 0.5
