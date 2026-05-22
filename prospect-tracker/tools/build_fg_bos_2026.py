"""One-off: scrape the May 2026 FG Red Sox top-48 article into FG-board CSVs.

Source article: https://blogs.fangraphs.com/boston-red-sox-top-48-prospects/
Authors: Brendan Gawlowski, Eric Longenhagen — published 2026-05-22.

The article isn't a Board export — it's a per-team writeup. But each
prospect block has the same shape FG uses on The Board:
  * `<div class="top-prospects-tool">` per prospect
      - header with "<rank>. <Name>, <Pos>" + Video link
      - bio table (Age, Height, Weight, B/T, FV)
      - tool grades table (Hit/Raw/Game/Run/Field/Throw or FB/SL/CB/CH/CMD/Sits-Tops)
      - prose writeup in `<div class="prospects-list-summary">`

We emit four CSVs into data/fangraphs_imports/bos2026may/ matching the
exact column shape `fangraphs_csv.py` expects (summary, position,
pitching, physical). The existing ingest path then handles dedup,
publish-date detection (mtime fallback → today), and storage.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ARTICLE_URL = "https://blogs.fangraphs.com/boston-red-sox-top-48-prospects/"
ARTICLE_CACHE = ROOT / ".cache" / "fg_bos_2026.html"
OUT_DIR = ROOT / "data" / "fangraphs_imports" / "bos2026may"
SLUG = "bos2026may"
ORG = "BOS"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def fetch_article(force: bool = False) -> str:
    if ARTICLE_CACHE.exists() and not force:
        return ARTICLE_CACHE.read_text(encoding="utf-8")
    ARTICLE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(ARTICLE_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    ARTICLE_CACHE.write_text(r.text, encoding="utf-8")
    return r.text


# Smart-quote/prime cleanup for height fields ("5′ 11″" -> 5'11").
def _clean_height(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.replace("′", "'").replace("″", '"')
    s = s.replace("’", "'").replace("”", '"')
    return re.sub(r"\s+", "", s) or None


def _player_id_from_href(href: str | None) -> str | None:
    # /players/franklin-arias/sa3021845/stats/...
    if not href:
        return None
    m = re.search(r"/players/[^/]+/([a-zA-Z0-9]+)/", href)
    return m.group(1) if m else None


def _parse_kv_table(table) -> dict[str, str]:
    """Bio table is one row of alternating key/value cells.
    e.g. ['Age', '20.5', 'Height', '5′ 11″', 'Weight', '170', 'Bat / Thr', 'R / R', 'FV', '60']
    """
    out: dict[str, str] = {}
    if not table:
        return out
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        for i in range(0, len(cells) - 1, 2):
            k = cells[i].strip().lower()
            v = cells[i + 1].strip()
            if k:
                out[k] = v
    return out


def _parse_tool_table(table) -> dict[str, str]:
    """Tool-grade table: header row + value row, headers like
    'Hit', 'Raw Power', 'Game Power', 'Run', 'Fielding', 'Throw' (hitters)
    or 'Fastball', 'Slider', 'Curveball', 'Changeup', 'Command', 'Sits/Tops' (pitchers).
    Returns {lowercased_header: value_string}."""
    out: dict[str, str] = {}
    if not table:
        return out
    rows = table.find_all("tr")
    if len(rows) < 2:
        return out
    headers = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["td", "th"])]
    values = [c.get_text(" ", strip=True) for c in rows[1].find_all(["td", "th"])]
    for h, v in zip(headers, values):
        if h:
            out[h] = v
    return out


def parse_master_table(soup: BeautifulSoup) -> dict[int, dict]:
    """The 49-row table with Rk/Name/Age/Highest Level/Position/ETA/FV."""
    tables = soup.find_all("table")
    for t in tables:
        rows = t.find_all("tr")
        if len(rows) < 10:
            continue
        hdr = [c.get_text(strip=True).lower() for c in rows[0].find_all(["td", "th"])]
        if hdr[:7] == ["rk", "name", "age", "highest level", "position", "eta", "fv"]:
            out: dict[int, dict] = {}
            for r in rows[1:]:
                cells = [c.get_text(" ", strip=True) for c in r.find_all(["td", "th"])]
                if len(cells) < 7:
                    continue
                try:
                    rk = int(cells[0])
                except ValueError:
                    continue
                out[rk] = {
                    "rank":    rk,
                    "name":    cells[1].strip(),
                    "age":     cells[2].strip(),
                    "level":   cells[3].strip(),
                    "pos":     cells[4].strip(),
                    "eta":     cells[5].strip(),
                    "fv":      cells[6].strip(),
                }
            return out
    return {}


# "Signed: International Signing Period, 2023 from Dominican Republic (BOS)"
# "Drafted: 2nd round, 2024 (BOS)"
_SIGN_RE = re.compile(
    r"(?P<verb>Signed|Drafted)\s*:\s*(?P<details>.+?)(?:\((?P<org>[A-Z]{2,4})\))?\s*$"
)


def _parse_sign_line(text: str) -> dict[str, str | int | None]:
    """Pull sign_year + sign_market + signed_from + sign_org from the
    one-liner FG ships in the bio cell."""
    if not text:
        return {}
    text = text.strip()
    # Year is the first 4-digit token.
    year_m = re.search(r"(19|20)\d{2}", text)
    year = int(year_m.group(0)) if year_m else None
    # Org is the trailing parenthesized 2-4 letter code, if any.
    org_m = re.search(r"\(([A-Z]{2,4})\)\s*$", text)
    org = org_m.group(1) if org_m else None
    # Market is "Draft" for drafted players, "International" for IFA.
    if text.lower().startswith("drafted"):
        market = "Draft"
    elif "international" in text.lower():
        market = "International"
    else:
        market = None
    # Signed-from is whatever follows " from " (school, country, etc.).
    from_m = re.search(r"\bfrom\s+(.+?)(?:\s*\([A-Z]{2,4}\))?\s*$", text)
    signed_from = from_m.group(1).strip() if from_m else None
    return {
        "sign_year":   year,
        "sign_market": market,
        "sign_org":    org,
        "signed_from": signed_from,
    }


def parse_prospect_block(block, master_row: dict | None) -> dict:
    """Return a flat dict combining header, bio, tool grades, writeup."""
    out: dict = {"rank": None, "name": None, "pos": None, "fv": None,
                 "age": None, "ht": None, "wt": None, "bats": None,
                 "throws": None, "sign_year": None, "sign_market": None,
                 "sign_org": None, "signed_from": None, "video": None,
                 "player_id": None, "tools": {}, "sits_tops": None,
                 "report": None, "level": None, "eta": None}

    hdr = block.find("h3")
    if hdr:
        text = hdr.get_text(" ", strip=True)
        # "1. Franklin Arias , SS"
        m = re.match(r"(\d+)\.\s+(.+?)\s*,\s*(.+)$", text)
        if m:
            out["rank"] = int(m.group(1))
            out["name"] = m.group(2).strip()
            out["pos"]  = m.group(3).strip()
        a = hdr.find("a", href=True)
        if a:
            out["player_id"] = _player_id_from_href(a["href"])

    if master_row:
        out["level"] = master_row.get("level")
        out["eta"]   = master_row.get("eta")
        # Master table has decimal age; prefer it for the Age column.
        try:
            out["age"] = float(master_row.get("age"))
        except (TypeError, ValueError):
            pass

    video_a = block.find("div", class_="header-video")
    if video_a:
        a = video_a.find("a", href=True)
        if a:
            out["video"] = a["href"]

    tg = block.find("div", class_="table-grey")
    if tg:
        # The "Signed/Drafted:" preamble lives in its own <div> child
        # ahead of the tables. Walk children until we find one whose text
        # opens with that pattern.
        sign_text = ""
        for child in tg.children:
            if not hasattr(child, "name") or child.name not in ("div", "p"):
                continue
            t = child.get_text(" ", strip=True)
            if t.lower().startswith(("signed:", "drafted:")):
                sign_text = t
                break
        if sign_text:
            out.update(_parse_sign_line(sign_text))

        tables = tg.find_all("table")
        # Bio table is always first; tool table is whichever later table
        # has non-empty rows (pitcher blocks ship an empty placeholder
        # table between bio + tools, so position-by-index isn't safe).
        if tables:
            bio = _parse_kv_table(tables[0])
            if "age" in bio:
                try:
                    out["age"] = float(bio["age"])
                except ValueError:
                    pass
            out["ht"] = _clean_height(bio.get("height"))
            try:
                out["wt"] = int(re.sub(r"[^\d]", "", bio.get("weight", "")) or 0) or None
            except ValueError:
                out["wt"] = None
            bt = bio.get("bat / thr") or bio.get("bat/thr")
            if bt and "/" in bt:
                b, t = [x.strip() for x in bt.split("/", 1)]
                out["bats"]   = b or None
                out["throws"] = t or None
            if "fv" in bio:
                out["fv"] = bio["fv"]
        tool_table = None
        for cand in tables[1:]:
            parsed = _parse_tool_table(cand)
            if parsed:
                tool_table = parsed
                break
        if tool_table:
            out["sits_tops"] = tool_table.pop("sits/tops", None)
            out["tools"] = tool_table

    ws = block.find("div", class_="prospects-list-summary")
    if ws:
        paragraphs: list[str] = []
        for p in ws.find_all("p"):
            t = p.get_text(" ", strip=True)
            if t:
                paragraphs.append(t)
        if paragraphs:
            out["report"] = "\n\n".join(paragraphs)

    return out


# Tool-name normalization (lowercased article header -> FG CSV column).
HITTER_TOOL_HEADERS = {
    "hit":         "Hit",
    "raw power":   "Raw Pwr",
    "game power":  "Game Pwr",
    "run":         "Spd",
    "speed":       "Spd",
    "fielding":    "Fld",
    "field":       "Fld",
    "throw":       "Throw",   # NOTE: not a position-board column; we drop.
    "pitch sel":   "Pitch Sel",
    "bat ctrl":    "Bat Ctrl",
}
PITCHER_TOOL_HEADERS = {
    "fastball":  "FB",
    "slider":    "SL",
    "curveball": "CB",
    "changeup":  "CH",
    "cutter":    "Cutter",
    "splitter":  "Splitter",
    "command":   "CMD",
    "control":   "CMD",
}


def _is_pitcher(pos: str | None) -> bool:
    if not pos:
        return False
    return any(p in pos.upper() for p in ("SP", "RP", "MIRP", "SIRP", "RHP", "LHP"))


def write_csvs(prospects: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- summary ---
    summary_cols = ["Top 100", "Org Rk", "Name", "Org", "Pos", "Current Level",
                    "ETA", "FV", "Risk", "Trend", "Age", "Ht", "Wt", "B", "T",
                    "Sign Yr", "Sign Mkt", "Sign Org", "Bonus", "Signed From",
                    "Report", "Video", "PlayerId"]
    with (OUT_DIR / f"summary-{SLUG}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(summary_cols)
        for p in prospects:
            w.writerow([
                "",                          # Top 100 (this is org-only list)
                p.get("rank"),
                p.get("name"),
                ORG,
                p.get("pos"),
                p.get("level"),
                p.get("eta"),
                p.get("fv"),
                "",                          # Risk (not published in article)
                "",                          # Trend
                p.get("age"),
                p.get("ht"),
                p.get("wt"),
                p.get("bats"),
                p.get("throws"),
                p.get("sign_year"),
                p.get("sign_market"),
                p.get("sign_org") or ORG,
                "",                          # Bonus (not published in article)
                p.get("signed_from"),
                p.get("report"),
                p.get("video"),
                p.get("player_id"),
            ])

    # --- position (hitters only) ---
    position_cols = ["Name", "Pos", "Org", "Top 100", "Org Rk", "Age",
                     "Hit", "Pitch Sel", "Bat Ctrl", "Game Pwr", "Raw Pwr",
                     "Spd", "Fld", "Avg EV", "Hard Hit%", "Max EV", "FV",
                     "PlayerId"]
    with (OUT_DIR / f"position-{SLUG}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(position_cols)
        for p in prospects:
            if _is_pitcher(p.get("pos")):
                continue
            tools = p.get("tools") or {}
            row = {h: tools.get(label.lower()) or tools.get(label)
                   for label, h in HITTER_TOOL_HEADERS.items()}
            w.writerow([
                p.get("name"), p.get("pos"), ORG, "", p.get("rank"), p.get("age"),
                tools.get("hit"),
                tools.get("pitch sel"),
                tools.get("bat ctrl"),
                tools.get("game power"),
                tools.get("raw power"),
                tools.get("run") or tools.get("speed"),
                tools.get("fielding") or tools.get("field"),
                "", "", "",
                p.get("fv"),
                p.get("player_id"),
            ])

    # --- pitching (pitchers only) ---
    pitching_cols = ["Name", "Pos", "Org", "Top 100", "Org Rk", "Age",
                     "TJ Date", "FB Type", "FB", "SL", "CB", "CH", "CMD",
                     "RPM FB", "RPM Break", "Sits", "Tops", "FV", "PlayerId"]
    with (OUT_DIR / f"pitching-{SLUG}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(pitching_cols)
        for p in prospects:
            if not _is_pitcher(p.get("pos")):
                continue
            tools = p.get("tools") or {}
            sits = tops = ""
            st = p.get("sits_tops") or ""
            # "93-97 / 101" -> sits=93-97, tops=101
            if "/" in st:
                a, b = st.split("/", 1)
                sits = a.strip()
                tops = b.strip()
            elif st:
                sits = st.strip()
            w.writerow([
                p.get("name"), p.get("pos"), ORG, "", p.get("rank"), p.get("age"),
                "", "",                       # TJ Date, FB Type (not in article)
                tools.get("fastball"),
                tools.get("slider"),
                tools.get("curveball"),
                tools.get("changeup") or tools.get("splitter"),
                tools.get("command") or tools.get("control"),
                "", "",                       # RPM FB, RPM Break
                sits, tops,
                p.get("fv"),
                p.get("player_id"),
            ])

    # --- physical: emit header-only file. The article doesn't publish
    #   Frame/Athl/Levers/Arm/Perf/Delivery grades, but the ingest pipeline
    #   accepts a missing physical CSV — so we just don't write one.


def main(force: bool = False) -> int:
    html = fetch_article(force=force)
    soup = BeautifulSoup(html, "html.parser")
    master = parse_master_table(soup)
    blocks = soup.find_all("div", class_="top-prospects-tool")
    prospects: list[dict] = []
    for b in blocks:
        # Pull rank from the h3 first so we can look up the master row.
        hdr = b.find("h3")
        if not hdr:
            continue
        m = re.match(r"(\d+)\.", hdr.get_text(" ", strip=True))
        rk = int(m.group(1)) if m else None
        prospects.append(parse_prospect_block(b, master.get(rk) if rk else None))

    prospects.sort(key=lambda r: r.get("rank") or 999)
    write_csvs(prospects)
    print(f"Wrote {len(prospects)} prospect rows to {OUT_DIR}")
    n_hit = sum(1 for p in prospects if not _is_pitcher(p.get("pos")))
    n_pit = sum(1 for p in prospects if _is_pitcher(p.get("pos")))
    n_wri = sum(1 for p in prospects if p.get("report"))
    n_tools = sum(1 for p in prospects if p.get("tools"))
    print(f"  hitters: {n_hit}, pitchers: {n_pit}, with writeups: {n_wri}, with tools: {n_tools}")
    return 0


if __name__ == "__main__":
    sys.exit(main(force="--force" in sys.argv))
