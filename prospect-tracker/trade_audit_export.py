# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PROSPX Transactions Trade Audit, one row per real deal (data/trade_audit_deals.json).

THE QUESTION (wiring W07, owner ask 4, 2026-09-30). The Trade Machine prices a deal a
reader builds; the PROSPX Transactions tab audits the deals clubs actually made, on the
same Trade Machine value. The Trade Machine's "Comparable real trades" panel reads a built
deal against the nearest real ones, so it needs the audited deals without the 86 MB
timeseries file the Transactions tab reads.

WHAT THIS FILE IS. The Trade Audit's own deal list, rebuilt here exactly as the page
builds it (prospx renderRecentlyTraded, the acq=trade view with every row shown): every
active prospect whose latest acquisition is a trade, grouped by trade date and narrative,
the narrative's other players found by its position-name pattern, each side resolved from
the narrative, every party priced at today's trade_value_mm (the slim sidecar,
_taPriceParty's rules; a party with no trade value is $0 on his side, owner answer M9-1),
the narrative's bonus pool and cash credited to the side that received less, and the
realized-to-date leg from data/trade_realized.json (_taRealizedWar's rules, owner answer
M9-2). Only deals whose narrative names both clubs are kept: the page renders a card for
no other deal. test_trade_comps.py pins the rows against the served cards.

WHAT IT IS NOT. No verdict is stored: the page applies the shared BALANCED_THRESHOLD_MM.
Every value is today's, not the value on the deal date, and the realized leg runs through
the eWAR artifact's as-of date. A comparable deal is context, not a price precedent.

Run: `python trade_audit_export.py` (after tools/export_trade_values.py and
trade_realized_export.py, which write its inputs).
"""
from __future__ import annotations

import json
import math
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"
#: Redirected by tests: every input defaults to a file beside it.
OUT_PATH = DATA_DIR / "trade_audit_deals.json"
TIMESERIES_NAME = "timeseries.json"
DEBUTS_NAME = "debuts_lite.json"
INACTIVE_NAME = "inactive.json"
SLIM_NAME = "trade_values_slim.json"
BOARD_NAME = "trade_values.json"
REALIZED_NAME = "trade_realized.json"

SCHEMA = 1
#: Fewer deals than this is a dead read (the served audit carries about 270).
MIN_DEALS = 50
PARTY_FIELDS = ["name", "key", "side", "kind", "pos", "mm", "why", "rwar", "mlbam"]

# prospx ORG_NAMES, in the order _buildOrgMap walks its org list.
_ORG_ORDER = ["LAA", "HOU", "ATH", "TOR", "ATL", "MIL", "STL", "CHC", "ARI", "LAD",
              "SFG", "CLE", "SEA", "MIA", "NYM", "WSN", "BAL", "SDP", "PHI", "PIT",
              "TEX", "TBR", "BOS", "CIN", "COL", "KCR", "DET", "MIN", "CHW", "NYY"]
_ORG_NAMES = {
    "ARI": "Arizona Diamondbacks", "ATH": "Athletics", "ATL": "Atlanta Braves",
    "BAL": "Baltimore Orioles", "BOS": "Boston Red Sox", "CHC": "Chicago Cubs",
    "CHW": "Chicago White Sox", "CIN": "Cincinnati Reds", "CLE": "Cleveland Guardians",
    "COL": "Colorado Rockies", "DET": "Detroit Tigers", "HOU": "Houston Astros",
    "KCR": "Kansas City Royals", "LAA": "Los Angeles Angels", "LAD": "Los Angeles Dodgers",
    "MIA": "Miami Marlins", "MIL": "Milwaukee Brewers", "MIN": "Minnesota Twins",
    "NYM": "New York Mets", "NYY": "New York Yankees", "PHI": "Philadelphia Phillies",
    "PIT": "Pittsburgh Pirates", "SDP": "San Diego Padres", "SEA": "Seattle Mariners",
    "SFG": "San Francisco Giants", "STL": "St. Louis Cardinals", "TBR": "Tampa Bay Rays",
    "TEX": "Texas Rangers", "TOR": "Toronto Blue Jays", "WSN": "Washington Nationals",
}
_ORG_FROM_NAME: dict[str, str] = {}
for _o in _ORG_ORDER:
    _ORG_FROM_NAME[_ORG_NAMES[_o].lower()] = _o
    _ORG_FROM_NAME[_o.lower()] = _o

# JS \b before an ASCII letter: the previous character is not an ASCII word character.
_JSB = r"(?<![A-Za-z0-9_])"
_POS_TOKENS = ["3B", "2B", "1B", "SS", "LF", "CF", "RF", "OF", "DH", "C",
               "RHP", "LHP", "SHP", "MIRP", "SIRP", "TWP", "INF", "IF",
               "MI", "UTIL", "SP", "RP", "P"]
_POS_PAT = "|".join(_POS_TOKENS)
_MULTI_POS = f"(?:(?:{_POS_PAT})(?:/(?:{_POS_PAT}))*)"
_NAME_TOK = "[A-Z][A-Za-z\u00c0-\u00ff.'\u00b4\\-]+"
_NAME_PAT = rf"(?:{_NAME_TOK}(?:\s+{_NAME_TOK}){{0,3}})(?:\s+(?:Jr\.?|Sr\.?|II|III|IV))?"
_TRADE_ROW_RE = re.compile(rf"{_JSB}({_MULTI_POS})\s+({_NAME_PAT})")
_ORGS_RE = re.compile(r"^(.+?)\s+traded\s+.+?\s+to\s+(.+?)(?:\s+(?:for|in exchange|on)(?![A-Za-z0-9_])|\.|\Z)")
_IBP_RES = (
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:M|million)?\s*(?:in\s+)?(?:international\s+)?(?:bonus\s+pool|slot\s+money|signing\s+bonus\s+pool)",
    r"(?:international\s+)?(?:bonus\s+pool|slot\s+money)[^.]*\$\s*([\d,]+(?:\.\d+)?)\s*(?:M|million)?",
)
_CASH_RE = r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:M|million)?\s*(?:in\s+)?cash(?![A-Za-z0-9_])"


# ---------------------------------------------------------------------------
# JavaScript arithmetic and string helpers the page's numbers depend on.
# ---------------------------------------------------------------------------
def _js_round(x: float, scale: int) -> float:
    """Math.round(x * scale) / scale (halves round toward +infinity)."""
    return math.floor(x * scale + 0.5) / scale


def _substr(s: str, start: int, n: int) -> str:
    """String.prototype.substr: a negative start counts from the end."""
    if start < 0:
        start = max(len(s) + start, 0)
    return s[start:start + n]


def _js_parse_float(raw: str) -> float:
    m = re.match(r"\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)", raw)
    return float(m.group(1)) if m else float("nan")


def fold(name) -> str:
    """prospx _taFold: accent- and initial-folded name key."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = re.sub("[\u0300-\u036f]", "", s).lower()
    s = re.sub("[.'\u2019]", "", s)
    s = re.sub("[^a-z0-9]+", "_", s)
    return s.strip("_")


def _desc_hash(s: str) -> str:
    """prospx _hashDesc: FNV-1a over UTF-16 code units, base 36."""
    h = 0x811C9DC5
    data = (s or "").strip().lower().encode("utf-16-le")
    for i in range(0, len(data), 2):
        h = (h ^ (data[i] | (data[i + 1] << 8))) & 0xFFFFFFFF
        h = (h * 0x01000193) & 0xFFFFFFFF
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        h, r = divmod(h, 36)
        out = digits[r] + out
        if not h:
            return out


# ---------------------------------------------------------------------------
# The page's pieces, one function each.
# ---------------------------------------------------------------------------
def latest_acquisition(p: dict) -> dict | None:
    """prospx latestAcquisition."""
    events = []
    for t in p.get("trades") or []:
        if t.get("to_org") == p.get("org") and t.get("trade_date"):
            events.append({"date": t["trade_date"], "method": "trade", "from_org": t.get("from_org"),
                           "to_org": t.get("to_org"), "description": t.get("description") or "",
                           "sort_key": t["trade_date"]})
    for tx in p.get("transactions") or []:
        k = str(tx.get("kind") or "").lower()
        method = None
        if k == "waiver_claim":
            method = "waiver"
        elif k.startswith("rule_5"):
            method = "rule_5"
        elif k == "contract_purchase":
            method = "contract_purchase"
        if not method:
            continue
        if tx.get("to_org") and tx.get("to_org") != p.get("org"):
            continue
        if not tx.get("date"):
            continue
        events.append({"date": tx["date"], "method": method, "from_org": tx.get("from_org") or None,
                       "to_org": tx.get("to_org") or p.get("org"),
                       "description": tx.get("description") or "", "sort_key": tx["date"]})
    a = p.get("acquisition")
    if a and a.get("method") and a.get("method") != "unknown":
        same_org = (not a.get("team_abbr")) or a.get("team_abbr") == p.get("org") or not p.get("org")
        d = a.get("signing_date") or (f"{a['year']}-01-01" if a.get("year") else None)
        if same_org and d:
            events.append({"date": d, "method": a["method"], "from_org": None, "to_org": p.get("org"),
                           "description": "", "sort_key": d})
    if not events:
        ca = p.get("current_acquisition")
        if ca and ca.get("method"):
            ev = ca.get("event") or {}

            def pick(k, default=None):
                v = ca.get(k)
                if v is None:
                    v = ev.get(k)
                return default if v is None else v
            d = pick("date")
            if d and ca.get("method"):
                return {"date": d, "method": ca["method"], "from_org": pick("from_org"),
                        "to_org": pick("to_org", p.get("org")),
                        "description": pick("description", ""), "sort_key": d}
        return None
    events.sort(key=lambda e: str(e["sort_key"]), reverse=True)
    return events[0]


def parse_orgs(desc: str):
    """prospx _parseTradeOrgs: [from, to] from '<A> traded ... to <B>', else None."""
    if not desc:
        return None
    m = _ORGS_RE.match(desc.lower())
    if not m:
        return None
    from_name, to_name = m.group(1).strip(), m.group(2).strip()
    frm, to = _ORG_FROM_NAME.get(from_name), _ORG_FROM_NAME.get(to_name)
    if not frm:
        frm = next((v for k, v in _ORG_FROM_NAME.items() if from_name.endswith(k)), None)
    if not to:
        to = next((v for k, v in _ORG_FROM_NAME.items() if to_name.endswith(k)), None)
    return [frm, to] if (frm and to) else None


def resolve_side(desc: str, name: str, org_from: str, org_to: str):
    """prospx _resolveSideForName: after ' for ' -> org_from, else org_to; None if absent."""
    lower = (desc or "").lower()
    i = lower.find(name.lower())
    if i < 0:
        return None
    before = lower.rfind(" for ", 0, i + 4)
    if 0 < before < i:
        return org_from
    return org_to


def extract_names(desc: str) -> list[str]:
    """prospx _extractNames: every 'POS Name' run in the narrative."""
    out = []
    for m in _TRADE_ROW_RE.finditer(desc or ""):
        nm = re.sub(r"[.,;:!?]+\Z", "", m.group(2)).strip()
        if nm:
            out.append(nm)
    return out


def parse_extras(desc: str) -> dict:
    """prospx _parseTradeExtras: bonus pool and cash dollars named in the narrative, $M."""
    if not desc:
        return {"ibp_mm": 0, "cash_mm": 0}
    text = str(desc)
    ibp = 0.0
    cash = 0.0
    for pat in _IBP_RES:
        for m in re.finditer(pat, text, re.I):
            val = _js_parse_float((m.group(1) or "").replace(",", ""))
            if not math.isfinite(val):
                continue
            tail = _substr(text, m.start() + len(m.group(0)) - 12, 12).lower()
            if not re.search("(m|million)", tail) and val > 1000:
                val = val / 1_000_000
            ibp = max(ibp, val)
    for m in re.finditer(_CASH_RE, text, re.I):
        val = _js_parse_float((m.group(1) or "").replace(",", ""))
        if not math.isfinite(val):
            continue
        tail = _substr(text, m.start() + len(m.group(0)) - 12, 12).lower()
        if not re.search("(m|million)", tail) and val > 1000:
            val = val / 1_000_000
        cash = max(cash, val)
    return {"ibp_mm": _js_round(ibp, 100), "cash_mm": _js_round(cash, 100)}


def build_price_index(doc: dict) -> dict:
    """prospx _taBuildIndex over the slim sidecar (or the full board)."""
    by_key, by_name = {}, {}
    for r in (doc or {}).get("players") or []:
        if not r or not r.get("player_key"):
            continue
        by_key[r["player_key"]] = r
        f = fold(r.get("player_name"))
        if f:
            by_name.setdefault(f, []).append(r)
    as_of = str(doc.get("generated_at"))[:10] if doc and doc.get("generated_at") else None
    return {"byKey": by_key, "byName": by_name, "asOf": as_of}


def price_party(idx: dict, key, name, orgs) -> dict:
    """prospx _taPriceParty."""
    row = None
    if key:
        row = idx["byKey"].get(key)
        if not row and orgs:
            c = [r for r in idx["byName"].get(fold(name), []) if r.get("org") in orgs]
            if len(c) == 1:
                row = c[0]
    else:
        c = idx["byName"].get(fold(name), [])
        if len(c) > 1 and orgs:
            c = [r for r in c if r.get("org") in orgs]
        if len(c) > 1:
            return {"value": None, "kind": "unpriced", "why": "ambiguous"}
        row = c[0] if len(c) == 1 else None
    if not row:
        return {"value": None, "kind": "unpriced", "why": "no_row"}
    base = {"key": row.get("player_key"), "src": row.get("surplus_source") or None,
            "status": row.get("status") or None,
            "fv": float(row["fv"]) if row.get("fv") is not None else None,
            "pos": row.get("position") or None,
            "mlbam": int(row["mlbam_id"]) if row.get("mlbam_id") is not None else None}
    mm = row.get("trade_value_mm")
    try:
        mm = float(mm) if mm is not None else float("nan")
    except (TypeError, ValueError):
        mm = float("nan")
    if not math.isfinite(mm):
        return {**base, "value": None, "kind": "unpriced", "why": row.get("surplus_source") or "no_price"}
    return {**base, "value": mm, "kind": "tv"}


def realized_war(doc: dict, mlbam, dt, from_org, to_org) -> dict:
    """prospx _taRealizedWar: WAR credited to the receiving club since the trade."""
    none = {"war": 0, "seasons": [], "mlb": False}
    rows = (doc.get("players") or {}).get(str(mlbam)) if (doc and mlbam is not None) else None
    try:
        y0 = int(str(dt or "")[:4])
    except ValueError:
        return none
    if not rows or not to_org:
        return none
    by: dict[int, float] = {}
    credited = 0
    for side in (0, 1):
        mine = [r for r in rows if r[3] == side]
        cutoff = -1
        for r in mine:
            if r[0] == y0 and r[1] == from_org and r[2] > cutoff:
                cutoff = r[2]
        for r in mine:
            if r[1] != to_org or r[0] < y0:
                continue
            if r[0] == y0 and r[2] <= cutoff:
                continue
            by[r[0]] = by.get(r[0], 0) + float(r[4])
            credited += 1
    seasons = [{"season": k, "war": _js_round(by[k], 1000)} for k in sorted(by)]
    war = 0
    for s in seasons:
        war += s["war"]
    return {"war": _js_round(war, 1000), "seasons": seasons, "mlb": credited > 0}


def _last_point_fv(p: dict) -> float:
    pts = p.get("points") or []
    last = pts[-1] if pts else None
    return (last.get("consensus_fv_raw") or 0) if last else 0


def _pool(players: list) -> list:
    """getFilteredAcquired at acq=trade: newest first, ties by the last point's FV."""
    pool = []
    for p in players:
        acq = latest_acquisition(p)
        if acq and acq.get("method") == "trade":
            pool.append({"p": p, "acq": acq})
    pool.sort(key=lambda r: -_last_point_fv(r["p"]))
    pool.sort(key=lambda r: str(r["acq"].get("date") or ""), reverse=True)
    return pool


def build_deals(players: list, debuts: list, inactive: list, price_doc: dict,
                realized: dict | None) -> list[dict]:
    """Every deal the Trade Audit renders a card for, in the page's own order."""
    idx = build_price_index(price_doc)
    rz_ready = bool(realized and realized.get("players"))
    dpw = float(realized["dollars_per_war_mm"]) if (rz_ready and realized.get("dollars_per_war_mm") is not None) else None
    ident: dict[str, list] = {}
    seen_keys: set = set()
    for lst in (debuts or [], inactive or []):
        for p in lst:
            if not p or not p.get("player_name") or not p.get("player_key") or p["player_key"] in seen_keys:
                continue
            seen_keys.add(p["player_key"])
            f = fold(p["player_name"])
            if f:
                ident.setdefault(f, []).append(p)

    groups: dict[str, dict] = {}
    order: list[str] = []
    for row in _pool(players):
        p, acq = row["p"], row["acq"]
        desc = acq.get("description") or ""
        key = f"{acq.get('date')}|{_desc_hash(desc)}"
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"key": key, "date": acq.get("date"), "description": desc,
                               "a": None, "b": None, "players": [], "seen": [], "rows": 0}
            order.append(key)
        if not g["a"] or not g["b"]:
            orgs = parse_orgs(desc)
            if orgs:
                g["a"], g["b"] = orgs
        orgs = [g["a"], g["b"]] if (g["a"] and g["b"]) else None
        price = price_party(idx, p.get("player_key") or None, p.get("player_name"), orgs)
        mlbam = price.get("mlbam") if price.get("mlbam") is not None else (
            int(p["mlbam_id"]) if p.get("mlbam_id") is not None else None)
        debuted = (price["status"] != "active") if price.get("status") else bool(
            p.get("debut_date") or p.get("status") == "debuted")
        if g["a"] and g["b"]:
            side = resolve_side(desc, p.get("player_name") or "", g["a"], g["b"]) or acq.get("to_org")
        else:
            side = acq.get("to_org")
        g["players"].append({"name": p.get("player_name"), "key": price.get("key") or "",
                             "page_key": p.get("player_key") or "",
                             "frm": g["b"] if side == g["a"] else g["a"], "to": side,
                             "price": price, "mlbam": mlbam, "debuted": debuted,
                             "pos": p.get("position") or price.get("pos") or None, "tracked": True})
        g["seen"].append(fold(p.get("player_name")))
        g["rows"] += 1

    for key in order:
        g = groups[key]
        if not g["a"] or not g["b"]:
            continue
        desc = g["description"]
        for nm in extract_names(desc):
            slug = fold(nm)
            if slug in g["seen"]:
                continue
            if any(s.startswith(slug + "_") for s in g["seen"]):
                continue
            side = resolve_side(desc, nm, g["a"], g["b"])
            if not side:
                continue
            g["seen"].append(slug)
            cands = ident.get(slug) or []
            idn = cands[0] if len(cands) == 1 else None
            price = price_party(idx, idn["player_key"] if idn else None,
                                idn["player_name"] if idn else nm, [g["a"], g["b"]])
            mlbam = price.get("mlbam") if price.get("mlbam") is not None else (
                int(idn["mlbam_id"]) if (idn and idn.get("mlbam_id") is not None) else None)
            pos = price.get("pos") or (str(idn.get("position") or "").split("/")[0] if idn else None) or None
            debuted = (price["status"] != "active") if price.get("status") else bool(idn)
            g["players"].append({"name": idn["player_name"] if idn else nm, "key": price.get("key") or "",
                                 "page_key": idn["player_key"] if idn else "",
                                 "frm": g["b"] if side == g["a"] else g["a"], "to": side,
                                 "price": price, "mlbam": mlbam, "debuted": debuted,
                                 "pos": pos, "tracked": False})

    deals = []
    for key in order:
        g = groups[key]
        if not g["a"] or not g["b"]:
            continue
        x = parse_extras(g["description"])
        total_ibp, total_cash = x["ibp_mm"] or 0, x["cash_mm"] or 0
        a_in = b_in = 0.0
        for e in g["players"]:
            v = e["price"].get("value")
            if v is None:
                continue
            if e["to"] == g["a"]:
                a_in += v
            elif e["to"] == g["b"]:
                b_in += v
        a_ibp = b_ibp = a_cash = b_cash = 0.0
        if total_ibp > 0:
            if a_in < b_in:
                a_ibp = total_ibp
            elif b_in < a_in:
                b_ibp = total_ibp
            else:
                a_ibp = b_ibp = total_ibp / 2
        if total_cash > 0:
            if a_in < b_in:
                a_cash = total_cash
            elif b_in < a_in:
                b_cash = total_cash
            else:
                a_cash = b_cash = total_cash / 2
        a_mm = _js_round(a_in + a_ibp + a_cash, 10)
        b_mm = _js_round(b_in + b_ibp + b_cash, 10)
        net = _js_round(a_mm - b_mm, 10)
        rz_a = rz_b = 0.0
        rz_any = False
        parties = []
        for e in g["players"]:
            rz = (realized_war(realized, e["mlbam"], g["date"], e["frm"], e["to"]) if rz_ready
                  else {"war": 0, "seasons": [], "mlb": False})
            rz_any = rz_any or rz["mlb"]
            if e["to"] == g["a"]:
                rz_a += rz["war"]
            elif e["to"] == g["b"]:
                rz_b += rz["war"]
            if e["to"] not in (g["a"], g["b"]):
                continue
            pr = e["price"]
            parties.append({
                "name": e["name"], "key": e["page_key"] or "",
                "side": "a" if e["to"] == g["a"] else "b",
                "kind": "M" if e["debuted"] else "P",
                "pos": e["pos"] or "",
                "mm": pr.get("value"),
                "why": None if pr.get("value") is not None else (pr.get("why") or "no_row"),
                "rwar": rz["war"] if rz_ready else None,
                "mlbam": e["mlbam"],
            })
        rz_a, rz_b = _js_round(rz_a, 1000), _js_round(rz_b, 1000)
        a_rmm = _js_round(rz_a * dpw, 10) if dpw is not None else None
        b_rmm = _js_round(rz_b * dpw, 10) if dpw is not None else None
        rz_net = _js_round(a_rmm - b_rmm, 10) if (a_rmm is not None and b_rmm is not None) else None
        deals.append({
            "key": key, "date": g["date"], "a": g["a"], "b": g["b"],
            "a_mm": a_mm, "b_mm": b_mm, "net": net,
            "a_extra": _js_round(a_ibp + a_cash, 100), "b_extra": _js_round(b_ibp + b_cash, 100),
            "rz_a_war": rz_a if rz_ready else None, "rz_b_war": rz_b if rz_ready else None,
            "rz_a_mm": a_rmm, "rz_b_mm": b_rmm, "rz_net": rz_net,
            "rz_any": rz_any if rz_ready else None,
            "parties": [[pp[f] for f in PARTY_FIELDS] for pp in parties],
        })
    return deals


def _read(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def export(*, out_path: Path | str | None = None, data_dir: Path | str | None = None,
           today: str | None = None, log=print) -> int:
    """Write data/trade_audit_deals.json. Returns the number of deals written (0 = kept)."""
    out_path = Path(out_path) if out_path is not None else Path(OUT_PATH)
    data_dir = Path(data_dir) if data_dir is not None else out_path.parent
    today = today or date.today().isoformat()
    ts_path = data_dir / TIMESERIES_NAME
    price_path = data_dir / SLIM_NAME
    if not price_path.exists():
        price_path = data_dir / BOARD_NAME
    missing = [p.name for p in (ts_path, price_path, data_dir / DEBUTS_NAME, data_dir / INACTIVE_NAME)
               if not p.exists()]
    if missing:
        log(f"  trade audit deals: {', '.join(missing)} missing; {out_path.name} left as it is")
        return 0
    ts = _read(ts_path)
    price_doc = _read(price_path)
    rz_path = data_dir / REALIZED_NAME
    realized = _read(rz_path) if rz_path.exists() else None
    if realized is not None and not realized.get("players"):
        realized = None
    deals = build_deals(ts.get("players") or [], _read(data_dir / DEBUTS_NAME),
                        _read(data_dir / INACTIVE_NAME), price_doc, realized)
    if len(deals) < MIN_DEALS:
        log(f"  trade audit deals: REFUSED, only {len(deals)} deals (need {MIN_DEALS}); "
            f"{out_path.name} left as it is")
        return 0
    doc = {
        "generated_at": today,
        "schema": SCHEMA,
        "source": ("PROSPX Transactions Trade Audit (acq=trade, every row), rebuilt by "
                   "trade_audit_export.py with the page's own rules"),
        "values_as_of": str(price_doc.get("generated_at") or "")[:10] or None,
        "values_source": price_path.name,
        "realized_as_of": (str(realized.get("as_of"))[:10] if realized and realized.get("as_of") else None),
        "dollars_per_war_mm": (realized.get("dollars_per_war_mm") if realized else None),
        "party_fields": PARTY_FIELDS,
        "note": ("One row per real deal the Trade Audit prices. Every value is today's Trade "
                 "Machine trade value, not the value on the deal date; a party with no trade "
                 "value counts $0 on his side (mm null, why says why). a_extra and b_extra are "
                 "the bonus pool and cash the narrative names, credited to the side that "
                 "received less, as the audit does. The realized leg is WAR for the receiving "
                 "club since the deal through realized_as_of, priced at dollars_per_war_mm. "
                 "No verdict is stored: the page applies the shared balanced band."),
        "count": len(deals),
        "deals": deals,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    tmp.replace(out_path)
    log(f"  trade audit deals: wrote {out_path.name} ({len(deals)} deals)")
    return len(deals)


def main(argv: list[str] | None = None) -> int:
    n = export(log=print)
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
