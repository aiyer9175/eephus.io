# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Industry free-agent prediction capture (task FA_PRED_CAPTURE, plan 3.E.6).

Measurement only. This tool FETCHES and PARSES; it scores nothing. No
comparison, error or head-to-head is computed here: the forward capture is
scored after the class signs, and the retro rows are read only by the FA
destination gate (docs/fa-2026-10/FA_DESTINATION_GATE.md) after its
registration. Nothing served reads what this writes.

Owner answer FA-DEST-3 (b), 2026-09-30: MLBTR's predicted team is kept, and
MLBTR's 2015-2025 Top 50 posts are fetched ONCE (about 11 pages, cached) for
the gate's retro comparator. Orchestrator ruling R9 assigns that retro fetch
here (subcommands retro-fetch and retro-build).

WHERE THINGS GO
  raw retro cache   .cache/fa_predictions/mlbtr_retro/<offseason>.html
  retro rows        data/_labs/fa_predictions/mlbtr_retro_2015_2025.json
  forward raw       .cache/fa_predictions/<source>/<capture date>.html
  forward rows      data/_labs/fa_predictions/2026_27_<source>_<capture date>.json
data/_labs/ ships in neither deploy consumer, so nothing here is republished.

FETCH DISCIPLINE (tools/ingest_arbitration_ledger.py measured an MLBTR TCP
firewall after about 14 rapid requests): single-threaded, a long delay with
jitter between requests, a PERMANENT cache that is never re-fetched, and a
circuit breaker that aborts the batch on the first error. robots.txt
(checked 2026-10-08) disallows none of these article paths and asks a
1 second crawl delay; MLBTR publishes no terms-of-use page (its footer links
only About, Commenting Policy and Privacy Policy).

USAGE
    python tools/fa_predictions_capture.py retro-fetch   # each page once, resumes
    python tools/fa_predictions_capture.py retro-build   # parse cache -> lab JSON
"""
from __future__ import annotations

import argparse
import hashlib
import html as _html
import json
import random
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CACHE_ROOT = ROOT / ".cache" / "fa_predictions"
RETRO_CACHE = CACHE_ROOT / "mlbtr_retro"
LAB_DIR = ROOT / "data" / "_labs" / "fa_predictions"
RETRO_PATH = LAB_DIR / "mlbtr_retro_2015_2025.json"

PARSER_VERSION = "mlbtr-top50-1"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
MIN_DELAY = 10.0
JITTER = 5.0
TIMEOUT = 30

#: Each offseason's MLBTR "Top 50 Free Agents With Predictions" post, located
#: 2026-10-08 by title search on mlbtraderumors.com. One post per offseason;
#: a season whose post cannot be read is recorded missing, never substituted.
RETRO_URLS: dict[str, str] = {
    "2015-16": "https://www.mlbtraderumors.com/2015/11/2015-16-top-50-mlb-free-agents-with-predictions.html",
    "2016-17": "https://www.mlbtraderumors.com/2016/11/2016-17-top-50-mlb-free-agents-predictions.html",
    "2017-18": "https://www.mlbtraderumors.com/2017/11/2017-18-top-50-mlb-free-agents-with-predictions.html",
    "2018-19": "https://www.mlbtraderumors.com/2018/11/mlb-free-agent-predictions-2019.html",
    "2019-20": "https://www.mlbtraderumors.com/2019/11/mlb-free-agent-predictions-2020.html",
    "2020-21": "https://www.mlbtraderumors.com/2020/11/mlb-free-agent-predictions-2021.html",
    "2021-22": "https://www.mlbtraderumors.com/2021/11/top-50-mlb-free-agent-rankings.html",
    "2022-23": "https://www.mlbtraderumors.com/2022/11/mlb-trade-rumors-top-50-free-agents-predictions-2022-23.html",
    "2023-24": "https://www.mlbtraderumors.com/2023/11/2023-24-top-50-free-agents-with-predictions.html",
    "2024-25": "https://www.mlbtraderumors.com/2024/11/2024-25-top-50-mlb-free-agents-with-predictions.html",
    "2025-26": "https://www.mlbtraderumors.com/2025/11/2025-26-top-50-mlb-free-agents-with-predictions.html",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _meta_path(raw: Path) -> Path:
    return raw.with_suffix(raw.suffix + ".meta.json")


# --------------------------------------------------------------------------- fetch
def fetch_once(url: str, dest: Path) -> Path:
    """Fetch ``url`` to ``dest`` exactly once. A cached file is never
    re-fetched. Raises on any non-200 or connection error (circuit breaker)."""
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        status = getattr(r, "status", 200)
        body = r.read()
        final_url = r.geturl()
    if status != 200:
        raise RuntimeError(f"HTTP {status} for {url}")
    dest.write_bytes(body)
    _meta_path(dest).write_text(json.dumps({
        "url": url, "final_url": final_url, "http_status": status,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
        "fetched_with": "python urllib, single request",
    }, indent=1), encoding="utf-8")
    return dest


def retro_fetch() -> int:
    todo = [(off, url) for off, url in RETRO_URLS.items()
            if not (RETRO_CACHE / f"{off}.html").exists()]
    print(f"retro-fetch: {len(RETRO_URLS) - len(todo)} cached, {len(todo)} to fetch")
    for i, (off, url) in enumerate(todo):
        if i:
            time.sleep(MIN_DELAY + random.uniform(0, JITTER))
        dest = RETRO_CACHE / f"{off}.html"
        try:
            fetch_once(url, dest)
        except Exception as e:                                # noqa: BLE001
            # Circuit breaker: stop the batch at the first failure.
            err = RETRO_CACHE / f"{off}.err.json"
            err.parent.mkdir(parents=True, exist_ok=True)
            err.write_text(json.dumps({
                "url": url, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "error": f"{type(e).__name__}: {e}"}, indent=1), encoding="utf-8")
            print(f"retro-fetch: ABORT at {off}: {type(e).__name__}: {e}")
            return 2
        print(f"retro-fetch: {off} {dest.stat().st_size} bytes")
    return 0


# --------------------------------------------------------------------------- parse
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _text(fragment: str) -> str:
    t = _TAG.sub(" ", fragment)
    t = _html.unescape(t).replace("\xa0", " ")
    return _WS.sub(" ", t).strip()


def _article_body(page: str) -> str:
    """The post body only (sidebars repeat 'Top 50' widgets)."""
    m = re.search(r'<div[^>]+class="[^"]*entry-content[^"]*"[^>]*>', page)
    if not m:
        return page
    body = page[m.end():]
    end = re.search(r'<div[^>]+class="[^"]*(?:sharedaddy|post-tags|entry-footer|'
                    r'jp-relatedposts|comments)[^"]*"', body)
    return body[: end.start()] if end else body


_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
}

# The contract inside a ranked header: "Seven years, $217MM" / "11 years,
# $400MM" / "One year, $8MM". Years as a word or a digit; money in $MM.
_CONTRACT = re.compile(
    r"\b(?P<years>\d{1,2}|" + "|".join(_NUM_WORDS) + r")[\s-]+years?\s*,?\s*"
    r"\$(?P<total>\d+(?:\.\d+)?)\s*(?:MM|M\b|million)", re.I)


def _years(tok: str) -> int | None:
    tok = tok.lower()
    if tok.isdigit():
        return int(tok)
    return _NUM_WORDS.get(tok)


# "12. Mike Leake - Giants. Five years, $80MM ." (2015-16 to 2020-21: one team)
# "1. Carlos Correa . Ten years, $320MM." (2021-22 to 2023-24: writers' picks next)
# "1. Juan Soto : Thirteen years, $600MM" (2024-25)
# "1. Kyle Tucker , RF: 11 years, $400MM" (2025-26: position in the header)
_RANKED = re.compile(r"^(?P<rank>\d{1,2})\.\s+(?P<rest>\S.*)$")
_DASH = re.compile(r"\s+[\u2013\u2014-]\s+")

_TEAMS = (
    "Angels", "Astros", "Athletics", "A's", "Blue Jays", "Braves", "Brewers",
    "Cardinals", "Cubs", "Diamondbacks", "D-backs", "Dodgers", "Giants",
    "Guardians", "Indians", "Mariners", "Marlins", "Mets", "Nationals",
    "Orioles", "Padres", "Phillies", "Pirates", "Rangers", "Rays", "Red Sox",
    "Reds", "Rockies", "Royals", "Tigers", "Twins", "White Sox", "Yankees",
)
_TEAM_RE = re.compile(r"(?<![\w-])(" + "|".join(
    re.escape(t) for t in sorted(_TEAMS, key=len, reverse=True)) + r")(?![\w-])", re.I)


_TEAM_CANON = {t.lower(): t for t in _TEAMS}


def _team(raw: str) -> str | None:
    """The one club named in ``raw`` (case-insensitive, so 'D-Backs' reads as
    'D-backs'), else None (never a guess)."""
    found = {_TEAM_CANON[t.lower()] for t in _TEAM_RE.findall(raw)}
    return found.pop() if len(found) == 1 else None


def _blocks(body: str) -> list[str]:
    """Split the body into text blocks at block-level boundaries."""
    parts = re.split(r"(?i)</?(?:p|h[1-6]|li|div|br)\b[^>]*>", body)
    return [t for t in (_text(p) for p in parts) if t]


def _writer_picks(blk: str) -> list[dict] | None:
    """'Tim Dierkes: Tigers / SA: Phillies' or "Tim Dierkes' prediction:
    Yankees / ..." -> [{"writer_label", "team_raw", "team"}]; None when the
    block is not a picks line."""
    parts = [p.strip() for p in blk.split("/")]
    out = []
    for p in parts:
        if ":" not in p:
            return None
        label, team_raw = p.rsplit(":", 1)
        label = re.sub(r"[\u2019']s?\s+prediction\s*$", "", label.strip(), flags=re.I).strip()
        team_raw = team_raw.strip()
        if not label or len(label) > 40 or not team_raw or len(team_raw) > 40:
            return None
        out.append({"writer_label": label, "team_raw": team_raw, "team": _team(team_raw)})
    return out if out and any(o["team"] for o in out) else None


def _writer_names(rows: list[dict]) -> dict[str, str]:
    """Map each short writer label in a post (first name or initials) to the
    full name the post spells out at least once ('Tim Dierkes')."""
    full = set()
    for r in rows:
        for p in r.get("pred_team_by_writer") or ():
            if " " in p["writer_label"]:
                full.add(p["writer_label"])
    alias = {}
    for name in full:
        alias[name] = name
        alias[name.split()[0]] = name
        alias["".join(w[0] for w in name.split()).upper()] = name
    return alias


def parse_mlbtr(page: str) -> list[dict]:
    """Rows of an MLBTR Top 50 post: rank, player_name, position, age,
    predicted years, total and AAV (both in $MM), the predicted team (the
    one club the 2015-16 to 2020-21 posts name) or each writer's team pick
    (2021-22 on), and the raw prediction text read. A field the post does
    not print is None, never inferred: the headers carry no age, and only
    the 2025-26 header carries a position. Ranks must run 1, 2, 3, ... in
    order; a numbered line out of sequence is prose, not an entry."""
    blocks = _blocks(_article_body(page))
    rows: list[dict] = []
    picks_window = 0
    for blk in blocks:
        h = _RANKED.match(blk)
        if h and int(h.group("rank")) == len(rows) + 1:
            rest = h.group("rest")
            m = _CONTRACT.search(rest)
            pre = rest[: m.start()] if m else rest.split(". ", 1)[0]
            team_raw = None
            dm = _DASH.search(pre)
            if dm:
                name, team_raw = pre[: dm.start()], pre[dm.end():]
                team_raw = re.sub(r"[\s.:,]+$", "", team_raw)
            else:
                name = re.sub(r"(?:\s+[.:]|:)\s*$", "", pre.rstrip())
            pos = None
            if "," in name:
                name, pos = (s.strip() for s in name.split(",", 1))
                pos = re.sub(r"[\s.:]+$", "", pos) or None
            # "Michael Brantley." (one 2022-23 header) loses the stray period;
            # a generational "Jr." keeps its own.
            name = re.sub(r"(?<!Jr)(?<!Sr)\.$", "", name.strip()).strip()
            row = {"rank": int(h.group("rank")), "player_name": name,
                   "position": pos, "age": None,
                   "pred_years": None, "pred_total_mm": None, "pred_aav_mm": None,
                   "pred_team_raw": team_raw,
                   "pred_team": _team(team_raw) if team_raw else None,
                   "pred_team_by_writer": None,
                   "prediction_text": rest[: m.end()] if m else rest[:200]}
            if m:
                yrs = _years(m.group("years"))
                tot = float(m.group("total"))
                row["pred_years"] = yrs
                row["pred_total_mm"] = tot
                row["pred_aav_mm"] = round(tot / yrs, 3) if yrs else None
            rows.append(row)
            picks_window = 0 if team_raw else 3
            continue
        if rows and picks_window:
            picks_window -= 1
            picks = _writer_picks(blk) if len(blk) < 400 else None
            if picks:
                rows[-1]["pred_team_by_writer"] = picks
                rows[-1]["prediction_text"] += " | " + blk
                picks_window = 0
    alias = _writer_names(rows)
    for r in rows:
        for p in r.get("pred_team_by_writer") or ():
            p["writer"] = alias.get(p["writer_label"])
    return rows


# --------------------------------------------------------------------------- resolve
def resolve_rows(rows: list[dict], class_year: int) -> list[str]:
    """Attach mlbam_id and the reason through the FA module's identity helper
    (fa_ident.resolve_with_reason, the window the FA board uses:
    range(class_year - 4, class_year)). Returns the unresolved names."""
    import fa_ident
    missing = fa_ident.index_sides_missing()
    if missing:
        raise RuntimeError(f"identity index missing side(s) {missing}; refusing a "
                           "partial resolution")
    unresolved = []
    for r in rows:
        mid, why = fa_ident.resolve_with_reason(r["player_name"],
                                                range(class_year - 4, class_year))
        r["mlbam_id"] = mid
        r["id_reason"] = why
        if mid is None:
            unresolved.append(r["player_name"])
    return unresolved


def retro_build() -> int:
    seasons: dict[str, dict] = {}
    missing: dict[str, str] = {}
    for off, url in RETRO_URLS.items():
        raw = RETRO_CACHE / f"{off}.html"
        if not raw.exists():
            err = RETRO_CACHE / f"{off}.err.json"
            missing[off] = (json.loads(err.read_text(encoding="utf-8"))["error"]
                            if err.exists() else "not fetched")
            continue
        meta = json.loads(_meta_path(raw).read_text(encoding="utf-8"))
        rows = parse_mlbtr(raw.read_text(encoding="utf-8", errors="replace"))
        class_year = int(off[:4]) + 1
        unresolved = resolve_rows(rows, class_year)
        seasons[off] = {
            "source_url": url, "captured_at": meta["captured_at"],
            "raw_file": f".cache/fa_predictions/mlbtr_retro/{off}.html",
            "raw_sha256": _sha256(raw), "parser_version": PARSER_VERSION,
            "class_year": class_year, "n_rows": len(rows),
            "n_unresolved": len(unresolved), "unresolved": unresolved,
            "rows": rows,
        }
        print(f"retro-build: {off} rows={len(rows)} unresolved={len(unresolved)}")
    out = {
        "what": ("MLB Trade Rumors' Top 50 Free Agents With Predictions, offseasons "
                 "2015-16 through 2025-26, fetched once and parsed. Measurement input "
                 "for the FA destination gate's retro comparator (owner answer "
                 "FA-DEST-3 (b)); nothing is scored here and nothing served reads it."),
        "attribution": {
            "source": "MLB Trade Rumors (mlbtraderumors.com)",
            "posts": {off: s["source_url"] for off, s in seasons.items()},
            "use": "internal measurement only; never republished",
        },
        "parser_version": PARSER_VERSION,
        "money_unit": "USD millions",
        "id_resolution": "fa_ident.resolve_with_reason(name, range(class_year - 4, class_year))",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "offseasons_captured": sorted(seasons),
        "offseasons_missing": missing,
        "seasons": seasons,
    }
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    RETRO_PATH.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n",
                          encoding="utf-8", newline="\n")
    print(f"retro-build: wrote {RETRO_PATH}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("retro-fetch", "retro-build"))
    a = ap.parse_args(argv)
    return {"retro-fetch": retro_fetch, "retro-build": retro_build}[a.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
