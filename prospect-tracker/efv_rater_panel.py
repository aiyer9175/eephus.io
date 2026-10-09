# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The historical rater panel: list ingest and an outcome-blind identity pass
(EFV4_RATER_PANEL; owner EW2-10, 2026-10-08; registration docs/efv-v2/EFV4_RATER_PANEL.md).

WHAT THIS IS. The public preseason top-100 lists of raters the served consensus does not
carry on list vintages 2011 to 2016 (Baseball Prospectus Top 101 2011 to 2021, FanGraphs
top 100 2011 to 2014 and the 2015 top 200), parsed from the pages tools/efv4_rater_fetch.py
cached under .cache/efv4_raters/raw/, each entry resolved to a PROSPX player_key. The output
is data/_labs/efv_w2/rater_panel.json, which efv_w2_raters.py turns into one lab column.
Nothing served reads this module or its artifact.

DATING. A list counts for list vintage V only when its publication date (the page's own
datePublished) falls inside [V-01-01, V-05-01); a list dated outside is recorded and
dropped. No midseason list is ingested.

IDENTITY (outcome-blind, the efv_identity rule). An entry (name, position, team, list year
Y) is matched against the board snapshots in prospects.db dated in [Y-1-01-01, Y-05-01)
from the sources the consensus reads (MLB Pipeline and FanGraphs), and nothing else: the
name (accent-folded, letters only, generational suffix dropped; efv_identity.norm_name's
rule), the club the Pipeline org list placed him on that year, and the side (pitcher or
not). Steps: a unique exact name; else the exact-name candidates on the entry's club; else
on the entry's side; else a unique last name plus first initial on the entry's club. A
tie at every step stays unresolved and is recorded. The source of this module reads no
column about what happened to a player later (the AST pin in test_efv_w2_raters.py, the
test_efv_identity pattern), so a match can never depend on an outcome.

RESERVED ROWS. Lists of years in efv_vintage_frame.RESERVED_LV (2020, 2021) are parsed
only when the committed registration names them (registration_names_reserved): the
registration document at HEAD carries the line RESERVED_MARKER. Until then those lists
are skipped and named.
"""
from __future__ import annotations

import html as _html
import json
import re
import sqlite3
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / ".cache" / "efv4_raters" / "raw"
MANIFEST = ROOT / ".cache" / "efv4_raters" / "manifest.json"
DB_PATH = ROOT / "prospects.db"
OUT_PATH = ROOT / "data" / "_labs" / "efv_w2" / "rater_panel.json"
REGISTRATION_DOC = "docs/efv-v2/EFV4_RATER_PANEL.md"
#: The line the committed registration carries once it names the reserved list years.
RESERVED_MARKER = "RESERVED LIST YEARS NAMED: 2020, 2021"
#: Mirrors efv_vintage_frame.RESERVED_LV (pinned equal in the tests; not imported, so
#: this module's import list stays the identity pass's own).
RESERVED_YEARS = frozenset({2020, 2021})
#: The window a list must be published in, as month-day bounds of its own year.
WINDOW_START_MMDD = "-01-01"
WINDOW_END_MMDD = "-05-01"
#: The board sources an identity match may read (the consensus's own raters).
ID_SOURCES = ("mlb_pipeline", "fangraphs")

#: list id -> (rater, year, layout). "numbered": "N. Name, POS, Team" lines (separator
#: a comma, a pipe or a period); "ol": an ordered HTML list of "Name, POS, Team" items.
LISTS: dict[str, tuple[str, int, str]] = {
    **{f"bp_{y}": ("bp", y, "numbered") for y in range(2011, 2018)},
    **{f"bp_{y}": ("bp", y, "ol") for y in (2018, 2019, 2020, 2021)},
    **{f"fg_{y}": ("fg", y, "numbered") for y in range(2011, 2016)},
}
RATER_NAMES = {"bp": "Baseball Prospectus Top 101", "fg": "FanGraphs top 100 (2015: top 200)"}

_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")
_NON_ALPHA = re.compile(r"[^a-z]")
_POS = (r"(?:[A-Z0-9]{1,4}(?:/[A-Z0-9]{1,4}){0,3}|Catcher|Outfielder|Infielder|Shortstop|"
        r"First base|Second base|Third base|Center field|Right field|Left field|"
        r"Right-handed pitcher|Left-handed pitcher)")
_NUMBERED = re.compile(r"^(\d{1,3})[.)]\s+(.+?)\s*[,|.]\s*(?:Jr\.?\s*[,|]\s*)?(" + _POS
                       + r")\s*[,|]\s*([^:(\[]+?)\s*(?:[:(\[].*)?$")
_ITEM = re.compile(r"^(.+?)\s*[,|]\s*(?:Jr\.?\s*[,|]\s*)?(" + _POS
                   + r")\s*[,|]\s*([^:(\[]+?)\s*(?:[:(\[].*)?$")
_PITCH_WORDS = ("hp", "pitcher", "sp", "rp")

#: Club codes (the StatsAPI-style codes the repo's boards use) and the strings the lists
#: and the Pipeline org-list names print for them.
CLUBS: dict[str, tuple[str, ...]] = {
    "ARI": ("diamondbacks", "d-backs", "dbacks", "arizona"),
    "ATL": ("braves", "atlanta"),
    "BAL": ("orioles", "baltimore"),
    "BOS": ("red sox", "boston"),
    "CHC": ("cubs", "chicago nl", "chicago (nl)", "chicago cubs"),
    "CHW": ("white sox", "chicago al", "chicago (al)", "chicago white sox"),
    "CIN": ("reds", "cincinnati"),
    "CLE": ("indians", "guardians", "cleveland"),
    "COL": ("rockies", "colorado"),
    "DET": ("tigers", "detroit"),
    "HOU": ("astros", "houston"),
    "KCR": ("royals", "kansas city"),
    "LAA": ("angels", "los angeles al", "los angeles (al)", "anaheim", "los angeles angels"),
    "LAD": ("dodgers", "los angeles nl", "los angeles (nl)", "los angeles dodgers"),
    "MIA": ("marlins", "miami", "florida"),
    "MIL": ("brewers", "milwaukee"),
    "MIN": ("twins", "minnesota"),
    "NYM": ("mets", "new york nl", "new york (nl)", "new york mets"),
    "NYY": ("yankees", "new york al", "new york (al)", "new york yankees"),
    "OAK": ("athletics", "oakland", "a's", "as"),
    "PHI": ("phillies", "philadelphia"),
    "PIT": ("pirates", "pittsburgh"),
    "SDP": ("padres", "san diego"),
    "SEA": ("mariners", "seattle"),
    "SFG": ("giants", "san francisco"),
    "STL": ("cardinals", "st. louis", "st louis", "saint louis"),
    "TBR": ("rays", "tampa bay", "tampa"),
    "TEX": ("rangers", "texas"),
    "TOR": ("blue jays", "toronto"),
    "WSN": ("nationals", "washington"),
}
_CLUB_OF: dict[str, str] = {a: code for code, al in CLUBS.items() for a in al}

#: Name variants a list prints for a player the boards carry under another name (folded
#: names, list form to board form). Names only, read off the two spellings; no outcome.
NAME_ALIASES: dict[str, str] = {
    "raulmondesi": "adalbertomondesi",
    "rauladalbertomondesi": "adalbertomondesi",
    "calebcowart": "kalebcowart",
    "deegordon": "deestrangegordon",
}


def norm_name(name: str | None) -> str:
    """Accent-folded, lower-case letters only, generational suffix removed (the
    efv_identity.norm_name rule)."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    s = _SUFFIX.sub("", s.lower())
    return _NON_ALPHA.sub("", s)


def _name_parts(name: str | None) -> tuple[str, str]:
    """(first initial, last name) on the folded name: the last token that is not a
    generational suffix."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    toks = [t for t in re.split(r"[\s]+", _SUFFIX.sub(" ", s.lower().replace(".", " ")))
            if _NON_ALPHA.sub("", t)]
    if not toks:
        return "", ""
    return _NON_ALPHA.sub("", toks[0])[:1], _NON_ALPHA.sub("", toks[-1])


def club_code(team: str | None) -> str | None:
    """The club code of a list's team string, or None."""
    t = re.sub(r"[\u2018\u2019`]", "'", str(team or "")).strip().lower()
    t = re.sub(r"\s+", " ", t).strip(" .,")
    if not t:
        return None
    if t in _CLUB_OF:
        return _CLUB_OF[t]
    best = None
    for alias, code in _CLUB_OF.items():         # longest alias contained in the string
        if len(alias) > 3 and re.search(r"(^|\b)" + re.escape(alias) + r"($|\b)", t):
            if best is None or len(alias) > len(best[0]):
                best = (alias, code)
    return best[1] if best else None


def is_pitcher_pos(pos: str | None) -> bool | None:
    p = str(pos or "").strip().lower()
    if not p:
        return None
    if p in ("p", "rhp", "lhp", "sp", "rp", "rhsp", "lhsp", "rhrp", "lhrp") or "pitcher" in p:
        return True
    return False


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------

def _text_lines(page: str) -> list[str]:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    t = re.sub(r"<(br|p|/p|/li|/h\d|/tr|/div)(\s[^>]*)?/?>", "\n", t, flags=re.I)
    t = _html.unescape(re.sub(r"<[^>]+>", "", t))
    t = t.replace("\xa0", " ").replace("\u2009", " ").replace("\ufffd", "'")
    return [re.sub(r"\s+", " ", ln).strip() for ln in t.split("\n") if ln.strip()]


def published(page: str) -> str | None:
    """The page's own publication day (schema.org datePublished), or None."""
    m = re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})', page)
    return m.group(1) if m else None


def parse_numbered(page: str) -> list[dict]:
    """Entries of a "N. Name, POS, Team" list; the first line at each rank wins (a
    reader comment repeating a rank later on the page is ignored)."""
    got: dict[int, dict] = {}
    for ln in _text_lines(page):
        m = _NUMBERED.match(ln)
        if not m:
            continue
        rank = int(m.group(1))
        if rank in got or rank < 1:
            continue
        name = m.group(2).strip().rstrip(",")
        if not re.search(r"[A-Za-z]", name) or len(name) > 40:
            continue
        got[rank] = {"rank": rank, "name": name, "pos": m.group(3).strip(),
                     "team": m.group(4).strip()}
    return [got[k] for k in sorted(got)]


def parse_ol(page: str) -> list[dict]:
    """Entries of the longest ordered HTML list whose items read "Name, POS, Team";
    the rank is the item's position."""
    best: list[dict] = []
    for body in re.findall(r"<ol[^>]*>(.*?)</ol>", page, flags=re.S | re.I):
        items = re.findall(r"<li[^>]*>(.*?)</li>", body, flags=re.S | re.I)
        out = []
        for i, it in enumerate(items, start=1):
            txt = _text_lines(it)
            m = _ITEM.match(" ".join(txt)) if txt else None
            if m:
                out.append({"rank": i, "name": m.group(1).strip(), "pos": m.group(2).strip(),
                            "team": m.group(3).strip()})
        if len(out) > len(best):
            best = out
    return best


def parse_list(page: str, layout: str) -> list[dict]:
    if layout == "numbered":
        return parse_numbered(page)
    if layout == "ol":
        return parse_ol(page)
    raise ValueError(f"unknown layout {layout!r}")


def in_window(day: str | None, year: int) -> bool:
    return bool(day) and f"{int(year)}{WINDOW_START_MMDD}" <= str(day)[:10] < (
        f"{int(year)}{WINDOW_END_MMDD}")


# ---------------------------------------------------------------------------
# the reserved-year rule
# ---------------------------------------------------------------------------

def registration_names_reserved(root: Path = ROOT) -> bool:
    """True when the registration document committed at HEAD carries RESERVED_MARKER
    and the status word REGISTERED. A working-tree edit does not count."""
    try:
        r = subprocess.run(["git", "show", f"HEAD:./{REGISTRATION_DOC}"], cwd=root,
                           capture_output=True, text=True, timeout=30, encoding="utf-8")
    except (OSError, subprocess.SubprocessError):
        return False
    if r.returncode != 0:
        return False
    return RESERVED_MARKER in r.stdout and "REGISTERED" in r.stdout


# ---------------------------------------------------------------------------
# the identity index (board snapshots only)
# ---------------------------------------------------------------------------

class BoardIndex:
    """{folded name: {player_key: {"clubs": set, "pitcher": bool | None}}} over the
    board snapshots of ID_SOURCES dated in [Y-1-01-01, Y-05-01)."""

    def __init__(self, year: int, by_name: dict, by_last: dict):
        self.year = int(year)
        self.by_name = by_name
        self.by_last = by_last

    @classmethod
    def from_db(cls, year: int, path: Path | str = DB_PATH) -> "BoardIndex":
        lo, hi = f"{int(year) - 1}-01-01", f"{int(year)}{WINDOW_END_MMDD}"
        con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
        try:
            q = ("SELECT player_key, player_name, position, interval_label, source "
                 "FROM snapshots WHERE snapshot_date >= ? AND snapshot_date < ? AND source IN "
                 f"({','.join('?' for _ in ID_SOURCES)})")
            rows = con.execute(q, (lo, hi, *ID_SOURCES)).fetchall()
        finally:
            con.close()
        return cls.from_rows(year, rows)

    @classmethod
    def from_rows(cls, year: int, rows) -> "BoardIndex":
        """rows: (player_key, player_name, position, list name, source)."""
        by_name: dict = {}
        by_last: dict = {}
        for pk, name, pos, list_name, _src in rows:
            if not pk or not name:
                continue
            ent = by_name.setdefault(norm_name(name), {}).setdefault(
                pk, {"clubs": set(), "pitcher": None})
            m = re.match(r"^.*?\d{4}\s+(.+?)\s+Top\s+\d+\s*$", str(list_name or ""))
            if m:
                c = club_code(m.group(1))
                if c:
                    ent["clubs"].add(c)
            p = is_pitcher_pos(pos)
            if p is not None and ent["pitcher"] is None:
                ent["pitcher"] = p
            fi, last = _name_parts(name)
            if last:
                by_last.setdefault((fi, last), set()).add(norm_name(name))
        return cls(year, by_name, by_last)

    def resolve(self, name: str, pos: str | None, team: str | None) -> tuple[str | None, str, int]:
        """(player_key or None, how, number of candidates at the deciding step)."""
        club = club_code(team)
        pit = is_pitcher_pos(pos)
        nm = norm_name(name)
        cands = dict(self.by_name.get(nm) or {})
        how = "name"
        if not cands and nm in NAME_ALIASES:
            cands = dict(self.by_name.get(NAME_ALIASES[nm]) or {})
            how = "alias"
        if not cands:
            fi, last = _name_parts(name)
            names = self.by_last.get((fi, last)) or set()
            for nm in names:
                cands.update(self.by_name.get(nm) or {})
            how = "last_name_initial"
            if not cands:
                return None, "no_candidate", 0
            on_club = {k: v for k, v in cands.items() if club and club in v["clubs"]
                       and (pit is None or v["pitcher"] is None or v["pitcher"] == pit)}
            if len(on_club) == 1:
                return next(iter(on_club)), how + "_club", 1
            return None, "no_candidate" if not on_club else "ambiguous", len(on_club)
        if len(cands) == 1:
            return next(iter(cands)), how, 1
        on_club = {k: v for k, v in cands.items() if club and club in v["clubs"]}
        if len(on_club) == 1:
            return next(iter(on_club)), how + "_club", 1
        pool = on_club or cands
        on_side = {k: v for k, v in pool.items() if pit is not None and v["pitcher"] == pit}
        if len(on_side) == 1:
            return next(iter(on_side)), how + "_side", 1
        return None, "ambiguous", len(pool)


# ---------------------------------------------------------------------------
# the panel
# ---------------------------------------------------------------------------

def _manifest() -> dict:
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def build_panel(*, raw_dir: Path = RAW_DIR, db_path: Path | str = DB_PATH,
                allow_reserved: bool | None = None) -> dict:
    """The panel document: every list with its entries resolved, and every list that was
    skipped with the reason."""
    if allow_reserved is None:
        allow_reserved = registration_names_reserved()
    man = _manifest()
    lists, skipped = {}, []
    indexes: dict[int, BoardIndex] = {}
    for lid, (rater, year, layout) in sorted(LISTS.items()):
        if year in RESERVED_YEARS and not allow_reserved:
            skipped.append({"list": lid, "reason": "reserved list year; the registration "
                                                   "does not name it yet"})
            continue
        path = Path(raw_dir) / f"{lid}.html"
        if not path.exists():
            skipped.append({"list": lid, "reason": "page not cached"})
            continue
        page = path.read_text(encoding="utf-8", errors="replace")
        day = published(page)
        entries = parse_list(page, layout)
        if not entries:
            skipped.append({"list": lid, "reason": "no list on the cached page (paywall)",
                            "published": day})
            continue
        if not in_window(day, year):
            skipped.append({"list": lid, "reason": f"published {day}, outside "
                                                   f"[{year}{WINDOW_START_MMDD}, "
                                                   f"{year}{WINDOW_END_MMDD})"})
            continue
        if year not in indexes:
            indexes[year] = BoardIndex.from_db(year, db_path)
        idx = indexes[year]
        out, n_res, hows = [], 0, {}
        for e in entries:
            pk, how, n = idx.resolve(e["name"], e["pos"], e["team"])
            n_res += int(pk is not None)
            hows[how] = hows.get(how, 0) + 1
            out.append(dict(e, club=club_code(e["team"]), pitcher=is_pitcher_pos(e["pos"]),
                            player_key=pk, how=how, n_candidates=n))
        keys = [x["player_key"] for x in out if x["player_key"]]
        dup = sorted({k for k in keys if keys.count(k) > 1})
        src = (man.get("lists") or {}).get(lid) or {}
        lists[lid] = {"rater": rater, "rater_name": RATER_NAMES[rater], "year": year,
                      "published": day, "url": src.get("final_url") or src.get("url"),
                      "n_entries": len(out), "last_rank": max(x["rank"] for x in out),
                      "n_resolved": n_res, "resolved_share": round(n_res / len(out), 4),
                      "how": dict(sorted(hows.items())), "duplicate_keys": dup,
                      "entries": out}
    return {"schema": 1, "item": "EFV4_RATER_PANEL", "produced_by": "efv_rater_panel.py",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "registration": REGISTRATION_DOC, "reserved_years_built": bool(allow_reserved),
            "window": f"[V{WINDOW_START_MMDD}, V{WINDOW_END_MMDD})",
            "id_sources": list(ID_SOURCES),
            "attribution": {"bp": "Baseball Prospectus, Top 101 prospects "
                                  "(baseballprospectus.com)",
                            "fg": "FanGraphs prospect lists (blogs.fangraphs.com): Marc "
                                  "Hulet 2011 to 2014, Kiley McDaniel 2015"},
            "skipped_sources": man.get("skipped") or [],
            "lists": lists, "skipped_lists": skipped}


def write_panel(doc: dict, out: Path = OUT_PATH) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=False) + "\n"
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out)
    return out


def load_panel(path: Path = OUT_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    d = build_panel()
    write_panel(d)
    for lid, blk in d["lists"].items():
        print(lid, blk["published"], blk["n_entries"], blk["n_resolved"], blk["how"],
              blk["duplicate_keys"])
    for s in d["skipped_lists"]:
        print("skipped", s)
