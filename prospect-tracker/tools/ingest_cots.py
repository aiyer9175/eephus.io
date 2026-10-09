# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""One scripted capture of Cot's Baseball Contracts (Baseball Prospectus), then manual drops.

SOURCE AND ATTRIBUTION
Cot's Baseball Contracts is a public set of contract sheets compiled by Baseball
Prospectus (https://legacy.baseballprospectus.com/compensation/cots/). Every use
of it on this site carries the attribution text in ATTRIBUTION below. The sheet
footer reads "Major League Baseball trademarks and copyrights are used with
permission of MLB Advanced Media, L.P. All rights reserved." and "Copyright
(c) <year> Baseball Prospectus, LLC."; the capture stores whichever of those
lines the sheet carries in its receipt. The sheet states no licence for reuse,
so the capture is private research input: the raw pages stay in the gitignored
.cache/cots/ and only derived, attributed facts (the deferral check and a lab
file of arbitration cases) are written.

OWNER ANSWER 2026-09-30, X05-20 = (b): "Yes, one scripted capture with
attribution". One scripted capture, cached with attribution, then maintained by
manual drops. This tool therefore REFUSES a second capture unless --force is
given with a dated reason (--reason "2026-11-02 sheet restructured, ...").

WHAT IT CAPTURES
The 30 club sheets, one request each, 30 requests in a single pass (the plan
says "under 30"; the 30 club sheets are the minimum that carries every club's
players, and division pages are empty, so no index request is made). Every
sheet lists, per player, the current contract and the contract history with the
arbitration notes ("avoided arbitration, $21M-$17M", "won arbitration case with
Houston 2/13/19 ($13.5M-$11.425M)") and the deferral and option notes. Two
consumers:
  (a) the 2011-2023 arbitration backfill chosen in ARB-CLUB-1 (b): exchanged
      cases, filings and hearing results by club and winter. Only players still
      on a club sheet carry their history, so the backfill is PARTIAL by
      construction and the output says so.
  (b) deferrals and options for the deferral check (data/cots_deferral_check.json).

POLITENESS
User-Agent names the site and a contact; 6 s delay plus jitter between
requests, single-threaded; the first non-200 or connection error aborts the
batch (the MLBTR lesson in ingest_arbitration_ledger.py: a retry loop converts
a soft block into a hard one).

CACHE AND RECEIPTS
Each response is stored at .cache/cots/<sheet>_<fetched_at>.html with a
receipts file .cache/cots/receipts.json naming, per sheet, the URL, the fetch
time, the byte count and sha256, the licence or terms lines found, and the
attribution text. The .cache directory is gitignored: the receipts are not in
the repository.

MANUAL DROP PATH (replaces scripted pulls from here on)
Save a sheet's page source (browser: View Source, or Save Page As, HTML only)
as .cache/cots/<sheet>_<YYYYMMDDTHHMMSSZ>.html where <sheet> is the club slug
(for example new-york-yankees) and the timestamp is the UTC time you saved it,
then add a line {"sheet": ..., "fetched_at": ..., "source": "manual drop",
"url": <page url>, "terms_lines": [...]} to the "drops" list in receipts.json
(`python tools/ingest_cots.py drop <file> --sheet <slug>` does both). The
newest file per sheet wins in `build`. A winter's check is: drop the sheets
after the signing deadline, run `build`, read the coverage block.

USAGE
    python tools/ingest_cots.py capture                 # the one scripted pass
    python tools/ingest_cots.py capture --force --reason "2026-11-02 why"
    python tools/ingest_cots.py drop FILE --sheet new-york-yankees
    python tools/ingest_cots.py build                   # cache -> artifacts
    python tools/ingest_cots.py check                   # offline parse of the cache
"""
from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import random
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "cots"
RECEIPTS = CACHE / "receipts.json"
DEFERRALS_PATH = ROOT / "data" / "deferrals.json"
CHECK_PATH = ROOT / "data" / "cots_deferral_check.json"
ARB_LAB_PATH = ROOT / "data" / "_labs" / "cots_arb_cases.json"

BASE = "https://legacy.baseballprospectus.com/compensation/cots/"
ATTRIBUTION = "Cot's Contracts (Baseball Prospectus)"
UA = ("ProspectTracker/1.0 (eephus.io research capture; one pass; "
      "contact arkndjl@gmail.com)")
MIN_DELAY = 6.0
JITTER = 3.0
TIMEOUT = 30
MAX_REQUESTS = 30
BACKFILL_FIRST, BACKFILL_LAST = 2011, 2023

# slug -> path under BASE, read off the sheet's own club menu (2026-10-08).
SHEETS = {
    "baltimore-orioles": "al-east/baltimore-orioles/",
    "boston-red-sox": "al-east/boston-red-sox/",
    "new-york-yankees": "al-east/new-york-yankees/",
    "tampa-bay-rays": "al-east/tampa-bay-rays/",
    "toronto-blue-jays": "al-east/toronto-blue-jays/",
    "chicago-white-sox": "american-league/chicago-white-sox/",
    "cleveland-guardians": "american-league/cleveland-guardians/",
    "detroit-tigers": "american-league/detroit-tigers/",
    "kansas-city-royals": "american-league/kansas-city-royals/",
    "minnesota-twins": "american-league/minnesota-twins/",
    "athletics": "al-west/athletics/",
    "houston-astros": "al-west/houston-astros/",
    "los-angeles-angels": "al-west/los-angeles-angels/",
    "seattle-mariners": "al-west/seattle-mariners/",
    "texas-rangers": "al-west/texas-rangers/",
    "atlanta-braves": "national-league/atlanta-braves/",
    "miami-marlins": "national-league/miami-marlins/",
    "new-york-mets": "national-league/new-york-mets/",
    "philadelphia-phillies": "national-league/philadelphia-phillies/",
    "washington-nationals": "national-league/washington-nationals/",
    "chicago-cubs": "national-league-central/chicago-cubs/",
    "cincinnati-reds": "national-league-central/cincinnati-reds/",
    "milwaukee-brewers": "national-league-central/milwaukee-brewers/",
    "pittsburgh-pirates": "national-league-central/pittsburgh-pirates/",
    "st-louis-cardinals": "national-league-central/st-louis-cardinals/",
    "arizona-diamondbacks": "nl-west/arizona-diamondbacks/",
    "colorado-rockies": "nl-west/colorado-rockies/",
    "los-angeles-dodgers": "nl-west/los-angeles-dodgers/",
    "san-diego-padres": "nl-west/san-diego-padres/",
    "san-francisco-giants": "nl-west/san-francisco-giants/",
}

_TERMS_RE = re.compile(
    r"(Major League Baseball trademarks and copyrights.*?All rights reserved\.|"
    r"Copyright\s*(?:&copy;|\(c\)|©)?\s*\d{4}\s*Baseball Prospectus, LLC\.?"
    r"(?:\s*All rights reserved\.?)?|"
    r"[^<>.]{0,80}terms of (?:use|service)[^<>.]{0,80}\.)", re.I)

_SEASON_RE = re.compile(r"\((\d{4})(?:\s*-\s*(\d{2,4}))?\)")
_CONTRACT_RE = re.compile(r"^(\d+)\s+years?\b")
_MONEY_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)\s*(MM|M|K)?\b", re.I)
_DATE_RE = r"(\d{1,2}/\d{1,2}/\d{2})"
_CASE_RE = re.compile(
    r"\b(won|lost)\s+arbitration\s+case\s+with\s+(.+?)\s+" + _DATE_RE +
    r"(?:\s*\(\s*(\$[^-)]+)-\s*(\$[^)]+)\))?", re.I)
_AVOID_RE = re.compile(
    r"\b(?:re-signed|signed|renewed|agreed)\b.*?\bby\s+(.+?)\s+(?:" + _DATE_RE +
    r"\s*)?\(\s*avoided arbitration(?:,\s*(\$[^-)]+)-\s*(\$[^)]+))?\)", re.I)
_DEFER_RE = re.compile(r"defer", re.I)
_OPTION_RE = re.compile(r"\b(opt(?:s|ed)? out|opt-out|option|buyout)\b", re.I)


# --------------------------------------------------------------- helpers
def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slugify(name: str) -> str:
    """Ledger key convention: lower-case ascii, non-alphanumerics to underscore."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\.?$", "", s.strip().lower()).strip()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def parse_money(txt: str) -> float | None:
    m = _MONEY_RE.search(txt or "")
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").upper()
    if unit in ("M", "MM"):
        v *= 1e6
    elif unit == "K":
        v *= 1e3
    elif v < 10_000 and "," not in m.group(1):
        return None  # a bare '$162' with its unit dropped on the sheet: unreadable
    return round(v)


def parse_contract_label(label: str) -> dict:
    """'9 years/$360M (2023-31)' -> years, total_usd, first/last season."""
    out = {"label": label, "years": None, "total_usd": None,
           "first_season": None, "last_season": None}
    m = _CONTRACT_RE.match(label)
    if m:
        out["years"] = int(m.group(1))
    elif re.match(r"^1\s+year\b", label):
        out["years"] = 1
    if "/" in label:
        out["total_usd"] = parse_money(label.split("/", 1)[1])
    s = _SEASON_RE.search(label)
    if s:
        a = int(s.group(1))
        out["first_season"] = a
        b = s.group(2)
        if b:
            b = int(b)
            out["last_season"] = b if b > 99 else (a // 100) * 100 + b
        else:
            out["last_season"] = a
    return out


# --------------------------------------------------------------- parsing
def parse_sheet(html: str, sheet: str) -> list[dict]:
    """A club sheet -> player records.

    Each record: name, pos, summary, contracts (label + notes), facts (the
    non-contract top-level lines: draft, agent, ML service).
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    players = []
    for p in soup.find_all("p"):
        name_span = None
        for sp in p.find_all("span"):
            if "130%" in (sp.get("style") or ""):
                name_span = sp
                break
        if name_span is None:
            continue
        ul = p.find_next_sibling("ul")
        if ul is None:
            continue
        name = re.sub(r"\s+", " ", name_span.get_text(" ", strip=True))
        italics = [s.get_text(strip=True) for s in p.find_all("span")
                   if "italic" in (s.get("style") or "")]
        pos = italics[0] if italics else ""
        texts = [t.strip() for t in p.get_text("\n").split("\n") if t.strip()]
        summary = texts[-1] if len(texts) > 2 else ""
        contracts, facts = [], []
        for li in ul.find_all("li", recursive=False):
            head = li.find("span", recursive=False)
            label = re.sub(r"\s+", " ", head.get_text(" ", strip=True)) if head else \
                re.sub(r"\s+", " ", li.get_text(" ", strip=True))
            sub = li.find("ul")
            notes = []
            if sub is not None:
                for n in sub.find_all("li"):
                    own = n.find("span", recursive=False)
                    t = own.get_text(" ", strip=True) if own else n.get_text(" ", strip=True)
                    t = re.sub(r"\s+", " ", t)
                    if t:
                        notes.append(t)
            if _CONTRACT_RE.match(label) or re.match(r"^1\s+year\b", label):
                c = parse_contract_label(label)
                c["notes"] = notes
                contracts.append(c)
            else:
                facts.append(label)
        players.append({"sheet": sheet, "name": name, "pos": pos,
                        "summary": summary, "contracts": contracts,
                        "facts": facts})
    return players


def _usd_pair(a: str | None, b: str | None):
    if not a or not b:
        return None, None
    x, y = parse_money(a), parse_money(b)
    if x is None or y is None:
        return None, None
    return max(x, y), min(x, y)


def arbitration_events(player: dict) -> list[dict]:
    """Arbitration cases and filings read off one-year contract notes."""
    out = []
    for c in player["contracts"]:
        season = c["first_season"]
        for note in c["notes"]:
            m = _CASE_RE.search(note)
            if m:
                hi, lo = _usd_pair(m.group(4), m.group(5))
                out.append({
                    "player": player["name"], "sheet": player["sheet"],
                    "season": season, "kind": "hearing",
                    "result": "player_won" if m.group(1).lower() == "won" else "club_won",
                    "club_raw": m.group(2).strip(), "date": m.group(3),
                    "player_figure_usd": hi, "club_figure_usd": lo,
                    "salary_usd": c["total_usd"], "note": note})
                continue
            m = _AVOID_RE.search(note)
            if m:
                hi, lo = _usd_pair(m.group(3), m.group(4))
                out.append({
                    "player": player["name"], "sheet": player["sheet"],
                    "season": season, "kind": "settled",
                    "result": "avoided_arbitration",
                    "club_raw": m.group(1).strip(), "date": m.group(2),
                    "player_figure_usd": hi, "club_figure_usd": lo,
                    "salary_usd": c["total_usd"], "note": note})
    return out


def deferral_events(player: dict) -> list[dict]:
    out = []
    for c in player["contracts"]:
        hits = [n for n in c["notes"] if _DEFER_RE.search(n)]
        if not hits and not _DEFER_RE.search(c["label"]):
            continue
        out.append({
            "player": player["name"], "player_slug": slugify(player["name"]),
            "sheet": player["sheet"], "contract": c["label"],
            "years": c["years"], "total_usd": c["total_usd"],
            "class_year": c["first_season"], "last_season": c["last_season"],
            "notes": hits or [c["label"]]})
    return out


def option_events(player: dict) -> list[dict]:
    out = []
    for c in player["contracts"]:
        for n in c["notes"]:
            if _OPTION_RE.search(n):
                kind = ("opt_out" if re.search(r"opt(?:s|ed)?[ -]out", n, re.I)
                        else "buyout" if re.search(r"buyout", n, re.I)
                        else "option")
                out.append({"player": player["name"], "sheet": player["sheet"],
                            "contract": c["label"], "kind": kind, "note": n})
    return out


# --------------------------------------------------------------- capture
def _load_receipts() -> dict:
    if RECEIPTS.exists():
        return json.loads(RECEIPTS.read_text(encoding="utf-8"))
    return {"attribution": ATTRIBUTION, "captures": [], "sheets": [], "drops": []}


def _save_receipts(r: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    RECEIPTS.write_text(json.dumps(r, indent=1), encoding="utf-8")


def terms_lines(html: str) -> list[str]:
    seen, out = set(), []
    for m in _TERMS_RE.finditer(html):
        t = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def capture_refused(receipts: dict, force: bool, reason: str | None) -> str | None:
    """Return the refusal message, or None when a capture may proceed."""
    if not receipts.get("captures"):
        return None
    if not force:
        last = receipts["captures"][-1]
        return (f"REFUSED: a scripted capture already ran ({last['started_at']}, "
                f"{last['n_ok']} sheets). The owner answer allows ONE; use the "
                "manual drop path, or pass --force with --reason 'YYYY-MM-DD why'.")
    if not reason or not re.match(r"^\d{4}-\d{2}-\d{2}\b\s*\S", reason):
        return "REFUSED: --force needs --reason starting with an ISO date and a reason."
    return None


def capture(force: bool = False, reason: str | None = None) -> int:
    receipts = _load_receipts()
    msg = capture_refused(receipts, force, reason)
    if msg:
        print(msg, file=sys.stderr)
        return 2
    CACHE.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run = {"started_at": started, "forced": bool(force), "reason": reason,
           "user_agent": UA, "n_ok": 0, "aborted": None}
    n = 0
    for slug, path in SHEETS.items():
        if n >= MAX_REQUESTS:
            run["aborted"] = "request cap"
            break
        url = BASE + path
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                body = resp.read()
                status = resp.status
        except (urllib.error.URLError, OSError) as e:
            run["aborted"] = f"{slug}: {e!r}"
            break
        n += 1
        if status != 200:
            run["aborted"] = f"{slug}: HTTP {status}"
            break
        fetched = _now_stamp()
        fp = CACHE / f"{slug}_{fetched}.html"
        fp.write_bytes(body)
        html = body.decode("utf-8", errors="replace")
        receipts["sheets"].append({
            "sheet": slug, "url": url, "fetched_at": fetched,
            "file": fp.name, "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "terms_lines": terms_lines(html), "attribution": ATTRIBUTION,
            "source": "scripted capture"})
        run["n_ok"] += 1
        _save_receipts(receipts)
        print(f"[{n}/{len(SHEETS)}] {slug} {len(body)} bytes", flush=True)
        time.sleep(MIN_DELAY + random.uniform(0, JITTER))
    run["n_requests"] = n
    receipts["captures"].append(run)
    _save_receipts(receipts)
    if run["aborted"]:
        print("ABORTED:", run["aborted"], file=sys.stderr)
        return 1
    return 0


def drop(file: str, sheet: str) -> int:
    if sheet not in SHEETS:
        print(f"unknown sheet {sheet}", file=sys.stderr)
        return 2
    CACHE.mkdir(parents=True, exist_ok=True)
    body = Path(file).read_bytes()
    stamp = _now_stamp()
    fp = CACHE / f"{sheet}_{stamp}.html"
    fp.write_bytes(body)
    r = _load_receipts()
    r["drops"].append({"sheet": sheet, "fetched_at": stamp, "file": fp.name,
                       "source": "manual drop", "url": BASE + SHEETS[sheet],
                       "bytes": len(body),
                       "sha256": hashlib.sha256(body).hexdigest(),
                       "terms_lines": terms_lines(body.decode("utf-8", "replace")),
                       "attribution": ATTRIBUTION})
    _save_receipts(r)
    print("dropped", fp.name)
    return 0


# --------------------------------------------------------------- build
def newest_files() -> dict[str, Path]:
    best: dict[str, Path] = {}
    for fp in sorted(CACHE.glob("*_*.html")):
        slug = fp.name.rsplit("_", 1)[0]
        if slug in SHEETS:
            best[slug] = fp  # sorted by name: the stamp sorts last
    return best


def load_ledger_keys(path: Path = DEFERRALS_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8")).get("players", {})


def deferral_check(deferred: list[dict], ledger: dict) -> dict:
    """The M04-25 coverage check: deferred signings in the capture vs the ledger."""
    by_name: dict[str, list[str]] = {}
    for k in ledger:
        by_name.setdefault(k.rsplit(":", 1)[0], []).append(k)
    rows = []
    for d in deferred:
        key = f"{d['player_slug']}:{d['class_year']}"
        in_ledger = key in ledger
        entry = ledger.get(key) or {}
        rows.append({
            "player": d["player"], "ledger_key": key, "in_ledger": in_ledger,
            "ledger_deferred": entry.get("deferred") if in_ledger else None,
            "ledger_names_other_years": [] if in_ledger else by_name.get(d["player_slug"], []),
            "sheet": d["sheet"], "contract": d["contract"],
            "total_usd": d["total_usd"], "class_year": d["class_year"],
            "last_season": d["last_season"], "notes": d["notes"]})
    rows.sort(key=lambda r: (r["in_ledger"], r["ledger_deferred"] is not False, -(r["total_usd"] or 0), r["player"]))
    winters = sorted({r["class_year"] for r in rows if r["class_year"]})
    return {"n_deferred_signings": len(rows),
            "n_in_ledger": sum(r["in_ledger"] for r in rows),
            "n_without_ledger_entry": sum(not r["in_ledger"] for r in rows),
            "n_ledger_entry_says_no_deferral": sum(
                r["in_ledger"] and r["ledger_deferred"] is False for r in rows),
            "winters_covered": winters, "signings": rows}


def build(cache_dir: Path | None = None) -> dict:
    files = newest_files()
    receipts = _load_receipts()
    players: list[dict] = []
    for slug, fp in sorted(files.items()):
        players += parse_sheet(fp.read_text(encoding="utf-8", errors="replace"), slug)
    deferred, options, arb = [], [], []
    for p in players:
        deferred += deferral_events(p)
        options += option_events(p)
        arb += arbitration_events(p)
    ledger = load_ledger_keys()
    chk = deferral_check(deferred, ledger)
    opt_counts: dict[str, int] = {}
    for o in options:
        opt_counts[o["kind"]] = opt_counts.get(o["kind"], 0) + 1
    fetched = sorted({s["fetched_at"] for s in receipts["sheets"] + receipts["drops"]
                      if s["sheet"] in files})
    artifact = {
        "_doc": [
            "Deferral check per plan row M04-25 / X05-20: every deferred signing "
            "found on the Cot's Contracts club sheets, matched against the "
            "curated ledger data/deferrals.json by player_key:class_year.",
            "Source: " + ATTRIBUTION + ". One scripted capture (owner answer "
            "X05-20 = b, 2026-09-30) then manual drops; see tools/ingest_cots.py.",
            "Measurement only: no served valuation number reads this file. The "
            "sheets carry only players on a club sheet at the capture date, so "
            "the signings listed are a floor on the deferred deals, not a census.",
        ],
        "attribution": ATTRIBUTION,
        "source_url": BASE,
        "fetched_at_range": [fetched[0], fetched[-1]] if fetched else [],
        "n_sheets": len(files),
        "n_players_parsed": len(players),
        "ledger_file": "data/deferrals.json",
        "ledger_threshold_note": ("the ledger's own ship gate covers guarantees "
                                  ">= $200M; this check looks below it"),
        "deferral_coverage": chk,
        "options": {"n": len(options), "by_kind": opt_counts},
    }
    lab = {
        "_doc": ["Arbitration cases read off the Cot's Contracts club sheets for the "
                 "2011-2023 backfill (ARB-CLUB-1 b). Lab file: ships in neither deploy "
                 "consumer. Source: " + ATTRIBUTION + ".",
                 "PARTIAL by construction: a case appears only for a player still on a "
                 "club sheet at the capture date."],
        "attribution": ATTRIBUTION,
        "backfill_window": [BACKFILL_FIRST, BACKFILL_LAST],
        "fetched_at_range": artifact["fetched_at_range"],
        "n_cases": len(arb),
        "cases": arb,
    }
    return {"artifact": artifact, "lab": lab, "n_arb_in_window": sum(
        1 for a in arb if a["season"] and BACKFILL_FIRST <= a["season"] <= BACKFILL_LAST)}


def _club_codes(cases: list[dict]) -> None:
    try:
        sys.path.insert(0, str(ROOT))
        import trades
    except Exception:
        return
    for c in cases:
        c["club"] = trades.canonical_org(c["club_raw"])


def write(res: dict) -> None:
    _club_codes(res["lab"]["cases"])
    res["lab"]["n_in_backfill_window"] = res["n_arb_in_window"]
    CHECK_PATH.write_text(json.dumps(res["artifact"], indent=1) + "\n", encoding="utf-8")
    ARB_LAB_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARB_LAB_PATH.write_text(json.dumps(res["lab"], indent=1) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture")
    c.add_argument("--force", action="store_true")
    c.add_argument("--reason")
    d = sub.add_parser("drop")
    d.add_argument("file")
    d.add_argument("--sheet", required=True)
    sub.add_parser("build")
    sub.add_parser("check")
    a = ap.parse_args(argv)
    if a.cmd == "capture":
        return capture(a.force, a.reason)
    if a.cmd == "drop":
        return drop(a.file, a.sheet)
    res = build()
    if a.cmd == "build":
        write(res)
    art = res["artifact"]["deferral_coverage"]
    print(f"sheets {res['artifact']['n_sheets']}  players {res['artifact']['n_players_parsed']}  "
          f"deferred {art['n_deferred_signings']}  without ledger {art['n_without_ledger_entry']}  "
          f"arb cases {res['lab']['n_cases']} (window {res['n_arb_in_window']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
