# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The Trade Machine partner screen v1 (wiring W08; owner answer W-OQ4 (a), 2026-10-01).

WHAT IT IS. For one selected player, the 30 clubs: his own club first and
never ranked, the other 29 ranked by the published rule partner_v1 with every
factor printed beside the ranking. A screen, not a rumor board: a stated rule
over numbers the site already serves, with no claim that it predicts a trade.
docs/trademachine-2026-10/TRADE_PARTNER_SCREEN_GATE.md registers the rule
(sections 2.2 to 2.5), the frozen record (section 3) and the one look on
2027-08-05; section numbers below ("gate 3.2") point into it.

THE FLAG. TRADE_PARTNER_SCREEN_LIVE is the one definition of the Trade Machine
partner screen flag; build_site reads it for the page switch
(data-tm-partner="live" on the /trademachine/ shell). While it is False:
  * the slim slice goes to .cache/trade_partner_screen/preview/ and nothing
    under data/ is written;
  * the day's record entry and its chain index go to the same preview
    directory (gate 3.2: preview files are never scored), so the record
    mechanism runs every night without a frozen day being written;
  * the page shell carries no switch and assets/trademachine.js draws nothing.
W08_2_PARTNER_SCREEN_FLIP turns it on in one commit (docs/trademachine-2026-10/
FLIP_NOTES.md). While True the slice is data/trade_partner_slice.json, beside
data/franchise_board.json, the record is .cache/trade_partner_screen/record/
and the chain index is re-rendered to data/trade_partner_screen_chain.json.

THE SLICE. One slim slice of the Franchise board's club files (sections
roster, outlook, fin, farm, odds, and the trade panel of front_office, the
org trade profile of owner answer M8-3, shown with weight 0), plus the Club
Ledger's CBT sidecar fields the tax factor prices with (data/trade_cbt.json:
threshold, rates, surcharge tiers, bracket names, the season calendar). Clubs
are named through the one club resolver (build_site._club_code, the P8.3
resolver Q9_05 built). The slice holds no space, room or capacity field and
no single projected payroll (the Ledger NEVER list): the tax factor is the
marginal tax of the player's CBT charge, printed in the M27 form.

THE RULE. rank_screen() below, between the partner_v1 markers, is the Python
twin of _tmPartnerScreen in assets/trademachine.js (between its own markers).
Both compute factor scores in integer units of 1/56 and the Score in units of
1/112, so the two languages order clubs identically; the tests run both on the
same fixtures. The record writer hashes both rule texts (gate 3.1).

Deterministic for equal inputs apart from generated_at; never opens a socket;
nothing here is priced, graded or recorded as a ledger row (gate 8).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
CACHE = ROOT / ".cache"
JS_PATH = ROOT / "assets" / "trademachine.js"
GATE_PATH = ROOT / "docs" / "trademachine-2026-10" / "TRADE_PARTNER_SCREEN_GATE.md"

#: The flag (Part 8 class 2). False: the preview directory only, nothing served moves.
TRADE_PARTNER_SCREEN_LIVE = False

SCHEMA = 1
RULE_VERSION = "partner_v1"
SLICE_NAME = "trade_partner_slice.json"
CHAIN_PUBLIC_NAME = "trade_partner_screen_chain.json"
SCREEN_DIR = "trade_partner_screen"

JS_BEGIN = "// ---- Trade partner screen rule partner_v1 (begin)"
JS_END = "// ---- Trade partner screen rule partner_v1 (end)"
PY_BEGIN = "# ---- Trade partner screen rule partner_v1 (begin)"
PY_END = "# ---- Trade partner screen rule partner_v1 (end)"

#: The volume labels of the org trade profile (farm Tendencies, owner answer
#: M8-3). Only the volume label and the counts are carried: the direction tag
#: is not printed on the screen.
VOLUME_LABELS = ("trade-happy", "typical", "trade-reluctant")

#: The candidate fields of one record row, in order (gate 3.1).
CANDIDATE_FIELDS = ["club", "need", "contention", "tax", "pay", "score"]


class ScreenRefusal(RuntimeError):
    """The slice or the record cannot be written honestly; the previous files stand."""


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
def paths(live: bool | None = None, data_dir: Path | None = None,
          cache_dir: Path | None = None) -> dict:
    """Where tonight's files go. Tests pass their own directories."""
    live = TRADE_PARTNER_SCREEN_LIVE if live is None else bool(live)
    d = Path(data_dir or DATA)
    c = Path(cache_dir or CACHE) / SCREEN_DIR
    if live:
        return {"live": True, "slice": d / SLICE_NAME, "record": c / "record",
                "public_chain": d / CHAIN_PUBLIC_NAME}
    pv = c / "preview"
    return {"live": False, "slice": pv / SLICE_NAME, "record": pv,
            "public_chain": pv / CHAIN_PUBLIC_NAME}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _canon(obj) -> bytes:
    """Gate 3.2: the canonical bytes every hash is taken over."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _ny_date(now: _dt.datetime) -> str:
    from zoneinfo import ZoneInfo
    return now.astimezone(ZoneInfo("America/New_York")).date().isoformat()


def detect_machine() -> str:
    """`box` on the production nightly, `local` anywhere else (the bracket record's rule)."""
    from bracket_sim import detect_machine as _dm
    return _dm()


def _num(v):
    """A finite number or None (a bool is not a number here)."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _between(text: str, begin: str, end: str) -> str:
    t = text.replace("\r\n", "\n")
    i = t.index(begin)
    j = t.index(end, i)
    return t[i:j + len(end)]


def rule_sha256(js_text: str | None = None) -> str:
    """Gate 3.1: SHA-256 of the JS rule's text between its markers, LF line endings."""
    src = js_text if js_text is not None else JS_PATH.read_text(encoding="utf-8")
    return _sha(_between(src, JS_BEGIN, JS_END).encode("utf-8"))


def rule_py_sha256(py_text: str | None = None) -> str:
    """The Python twin's source hash, the same way."""
    src = py_text if py_text is not None else Path(__file__).read_text(encoding="utf-8")
    return _sha(_between(src, PY_BEGIN, PY_END).encode("utf-8"))


# ---------------------------------------------------------------------------
# the slice (gate 2.2)
# ---------------------------------------------------------------------------
def _club_code(x):
    """The one club resolver (P8.3, Q9_05): build_site._club_code."""
    import build_site
    return build_site._club_code(x)


def _days(cal: dict | None, as_of: str):
    """The CBT block's day count (_tmCbtDaysLeft): days left counting today, and the length."""
    if not cal or not cal.get("start") or not cal.get("end") or not as_of:
        return None
    d = lambda s: _dt.date.fromisoformat(str(s)[:10]).toordinal()  # noqa: E731
    n = d(cal["end"]) - d(cal["start"]) + 1
    t = d(as_of)
    left = n if t < d(cal["start"]) else max(0, d(cal["end"]) - t + 1)
    return {"left": left, "len": n}


def _winter_frame_live() -> bool:
    """W03's switch (owner answer OUTLOOK (a), Q9_03): proj_export.TEAM_OUTLOOK_WINTER_FRAME.
    Not defined at this commit, so the served frame is the one the screen reads."""
    try:
        import proj_export
    except Exception:                      # noqa: BLE001
        return False
    return bool(getattr(proj_export, "TEAM_OUTLOOK_WINTER_FRAME", False))


def tax_frame(cbt: dict, as_of: str) -> dict:
    """Gate 2.2 Tax: the current tax year on the as-of date. While the CBT
    sidecar's season is still being played it is that season, prorated by the
    days left; after its last regular-season day it is the next season, in
    full until its own calendar starts and prorated after."""
    now, nxt = int(cbt["season_now"]), int(cbt["class_year"])
    cal = cbt.get("calendar") or {}
    d_now = _days(cal.get(str(now)), as_of)
    if d_now and d_now["left"] > 0:
        season, dl = now, d_now
    else:
        season, dl = nxt, _days(cal.get(str(nxt)), as_of)
    started = bool(dl) and dl["left"] < dl["len"]
    return {"season": season, "season_now": now,
            "days_left": dl["left"] if dl else None, "days": dl["len"] if dl else None,
            "started": started}


def build_slice(as_of: str, data_dir: Path | None = None) -> dict:
    """The slim slice of the Franchise board and the CBT sidecar. Raises
    ScreenRefusal when a club does not resolve or a club file is missing."""
    d = Path(data_dir or DATA)
    board = _read_json(d / "franchise_board.json")
    cbt = _read_json(d / "trade_cbt.json")
    shard_dir = d / ((board.get("shards") or {}).get("dir") or "franchise_clubs")
    codes = list(board.get("codes") or [])
    if len(codes) != 30:
        raise ScreenRefusal(f"the Franchise board names {len(codes)} clubs, not 30")
    tf = tax_frame(cbt, as_of)
    season = tf["season"]
    class_year = int(board.get("class_year") or cbt["class_year"])
    # Gate 2.2 Contention: OUTLOOK wins for the class year before its first
    # regular-season game, ODDS playoff_pct from that game on.
    in_season = (season == int(board.get("season_now") or 0)) and tf["started"]
    winter = _winter_frame_live()
    if in_season:
        contention = {"section": "odds", "key": "playoff_pct", "season": season,
                      "label": f"{season} playoff odds", "frame": "in-season odds"}
    else:
        contention = {"section": "outlook", "key": f"wins_{class_year}", "season": class_year,
                      "label": f"Team Outlook {class_year} wins",
                      "frame": ("as of signings (Team Outlook winter frame)" if winter
                                else "the served frame (Team Outlook before free agency moves)")}
    clubs = {}
    for code in codes:
        canon = _club_code(code)
        if canon != code:
            raise ScreenRefusal(f"club {code!r} resolves to {canon!r} through the club resolver")
        p = shard_dir / f"{code}.json"
        if not p.is_file():
            raise ScreenRefusal(f"club file missing: {p.name}")
        sec = _read_json(p).get("sections") or {}
        ro, ou, fi = sec.get("roster") or {}, sec.get("outlook") or {}, sec.get("fin") or {}
        fa, od = sec.get("farm") or {}, sec.get("odds") or {}
        lineup = {str(r[5]): r[3] for r in (ro.get("lineup") or []) if len(r) > 5}
        starters = {}
        for a in ro.get("alignment") or []:
            if len(a) > 5 and a[0] not in starters:
                starters[a[0]] = {"name": a[1], "key": str(a[5]), "hem_plus": _num(lineup.get(str(a[5])))}
        wins = None
        for row in ou.get("by_year") or []:
            if row and int(row[0]) == class_year:
                wins = _num(row[1])
        blk = ((cbt.get("clubs") or {}).get(code) or {}).get(str(season)) or {}
        if season == class_year:
            tax = _num(fi.get(f"tax_payroll_{season}"))
            pv = fi.get(f"payor_{season}")
            payor = pv.get("value") if isinstance(pv, dict) else pv
        else:
            tax = _num(blk.get("tax_payroll_usd"))
            payor = blk.get("tier")
        trades = next((x for x in ((sec.get("front_office") or {}).get("panels") or [])
                       if x.get("key") == "trades"), None)
        profile = None
        if trades:
            rows = {r[0]: r[2] for r in trades.get("rows") or [] if r and len(r) > 2}
            profile = {"volume": next((t for t in trades.get("tags") or [] if t in VOLUME_LABELS), None),
                       "players_moved": rows.get("volume"), "net_prospects": rows.get("netProspects"),
                       "window": trades.get("window")}
        clubs[code] = {
            "name": next((c.get("name") for c in board.get("clubs") or [] if c.get("code") == code), code),
            "roster": {"starters": starters, "team_dem_plus": _num(ro.get("team_dem_plus")),
                       "offense_plus": _num(ro.get("offense_plus")),
                       "rotation_plus": _num(ro.get("rotation_plus")),
                       "bullpen_plus": _num(ro.get("bullpen_plus"))},
            "outlook": {f"wins_{class_year}": wins},
            "fin": {f"tax_payroll_{season}": int(tax) if tax is not None else None,
                    f"payor_{season}": payor,
                    "threshold_usd": _num(blk.get("threshold_usd")),
                    "threshold_carry_forward": bool(blk.get("carry_forward"))},
            "farm": {"farm_surplus_mm": _num(fa.get("farm_surplus_mm"))},
            "odds": {"playoff_pct": _num(od.get("playoff_pct"))},
            "trade_profile": profile,
        }
    basis = board.get("basis") or {}
    return {
        "schema": SCHEMA,
        "rule_version": RULE_VERSION,
        "as_of": as_of,
        "board_generated_at": board.get("generated_at"),
        "cbt_generated_at": cbt.get("generated_at"),
        "season_now": int(cbt["season_now"]),
        "class_year": class_year,
        "contention": contention,
        "tax": {"season": season, "days_left": tf["days_left"], "days": tf["days"],
                "rates": cbt.get("rates"), "surcharge_tiers_usd": cbt.get("surcharge_tiers_usd"),
                "brackets": cbt.get("brackets"), "payor_basis": cbt.get("payor_basis")},
        "sources": {
            "need": "franchise_clubs/<CODE> roster: alignment starter joined to lineup HEM+, "
                    "team_dem_plus, offense_plus, rotation_plus, bullpen_plus",
            "contention": f"franchise_clubs/<CODE> {contention['section']}: "
                          + ("odds.playoff_pct" if in_season else f"outlook.by_year {class_year} wins"),
            "tax": (f"franchise_clubs/<CODE> fin.tax_payroll_{season} and payor_{season}"
                    if season == class_year else f"trade_cbt clubs <CODE> {season} tax payroll and tier")
                   + "; threshold, rates and tiers from trade_cbt (the Club Ledger CBT sidecar)",
            "pay": "franchise_clubs/<CODE> farm.farm_surplus_mm",
            "odds": "franchise_clubs/<CODE> odds.playoff_pct",
            "trade_profile": "franchise_clubs/<CODE> front_office trades panel (owner answer M8-3), weight 0",
            "basis": {k: basis.get(k) for k in ("hitters", "starters", "bullpen", "defense",
                                                 "projections", "team_outlook_eval")},
        },
        "clubs": clubs,
    }


def slice_bytes(sl: dict) -> bytes:
    return json.dumps(sl, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


# ---------------------------------------------------------------------------
# the rule: the Python twin of _tmPartnerScreen (gate 2.2 to 2.5)
# ---------------------------------------------------------------------------
# ---- Trade partner screen rule partner_v1 (begin)
TM_PARTNER_FIELD = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")
TM_PARTNER_SP = ("SP", "RHP", "LHP", "P")
TM_PARTNER_RP = ("RP", "CL", "SIRP", "MIRP", "CP")
TM_PARTNER_ORDER = ("C", "SS", "CF", "2B", "3B", "1B", "LF", "RF", "OF", "SP", "RP",
                    "CL", "RHP", "LHP", "P", "DH")


def partner_slot(pos):
    """The Trade Machine's primary position, then the slot: a fielder at his
    position, DH, SP or RP. Any other position (OF, INF, TWP) has no slot."""
    s = str(pos or "").upper().strip()
    if not s:
        return None
    parts = [x.strip() for x in s.split("/") if x.strip()]
    prim = next((x for x in TM_PARTNER_ORDER if x in parts), parts[0] if parts else "")
    if prim in TM_PARTNER_FIELD or prim == "DH":
        return prim
    if prim in TM_PARTNER_SP:
        return "SP"
    if prim in TM_PARTNER_RP:
        return "RP"
    return None


def _partner_num(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _partner_bill(tax, threshold, tier, rates, tiers):
    """_tmCbtBill, operation for operation, so both languages give the same double."""
    over = float(tax) - float(threshold)
    t1, t2, t3 = float(tiers[0]), float(tiers[1]), float(tiers[2])
    t = str(tier or "Non-Tax").strip()
    k = "2" if t.startswith("2nd") else ("3+" if t.startswith("3") else "1")
    base = float(rates["base_rate_by_payor_year"][k])
    sur = rates["surcharge_rates"]
    s1 = float(sur["tier1"])
    s2 = float(sur["tier2_first"] if k == "1" else sur["tier2_repeat"])
    s3 = float(sur["tier3"])
    if over <= 0:
        return 0.0, "under"

    def clip(x, lo, hi):
        return max(lo, min(hi, x))
    bill = (base * min(over, t1)
            + (base + s1) * clip(over - t1, 0, t2 - t1)
            + (base + s2) * clip(over - t2, 0, t3 - t2)
            + (base + s3) * max(over - t3, 0))
    bracket = ("base" if over <= t1 else "surcharge_1" if over <= t2
               else "surcharge_2" if over <= t3 else "surcharge_3")
    return bill, bracket


def partner_tax(fin, season, charge, frac, rates, tiers):
    """Gate 2.2 Tax, the M27 form: the club's tax payroll before and after the
    player's CBT charge (prorated in season), the threshold, the brackets, the
    payor tier, and the marginal tax in whole dollars (lower counts more)."""
    before = _partner_num((fin or {}).get(f"tax_payroll_{season}"))
    thr = _partner_num((fin or {}).get("threshold_usd"))
    tier = (fin or {}).get(f"payor_{season}") or "Non-Tax"
    if before is None or thr is None or not rates or not tiers:
        return None
    moved = float(charge) * frac
    after = before + moved
    b0, k0 = _partner_bill(before, thr, tier, rates, tiers)
    b1, k1 = _partner_bill(after, thr, tier, rates, tiers)
    return {"before": before, "after": after, "moved": moved, "threshold": thr,
            "carry": bool((fin or {}).get("threshold_carry_forward")), "tier": tier,
            "bracket_before": k0, "bracket_after": k1,
            "marginal": math.floor((b1 - b0) + 0.5)}


def partner_factor(cands, value_of, higher):
    """Gate 2.3 step 1: rank the candidates that carry a value, ties at their
    average rank, score (29 - rank) / 28, returned as 56ths: 58 - 2 x rank. A
    candidate with no value gets None (it scores 0.5, gate 2.3 step 3)."""
    have = []
    for c in cands:
        v = _partner_num(value_of(c))
        if v is not None:
            have.append((c, v))
    have.sort(key=lambda cv: ((-cv[1] if higher else cv[1]), cv[0]))
    out = {c: None for c in cands}
    i = 0
    while i < len(have):
        j = i
        while j + 1 < len(have) and have[j + 1][1] == have[i][1]:
            j += 1
        for k in range(i, j + 1):
            out[have[k][0]] = 58 - (i + j + 2)
        i = j + 1
    return out


def rank_screen(sl, player):
    """partner_v1 for one player ({slot, club, cbt_usd}): None when he has no
    slot or no club in the slice; else his club, the slot and the 29
    candidates in rule order, each with its raw inputs, its four factor
    scores and its Score (units: 1/112)."""
    clubs = (sl or {}).get("clubs") or {}
    slot = (player or {}).get("slot")
    own = (player or {}).get("club")
    if not slot or own not in clubs:
        return None
    codes = sorted(clubs)
    cands = [c for c in codes if c != own]
    field = slot in TM_PARTNER_FIELD
    con = sl["contention"]
    tx = sl["tax"]
    season = tx["season"]
    frac = 1.0
    if tx.get("days") and tx.get("days_left") is not None:
        frac = tx["days_left"] / tx["days"]
    charge = _partner_num(player.get("cbt_usd")) or 0.0
    raw = {}
    for c in codes:
        r = clubs[c].get("roster") or {}
        st = (r.get("starters") or {}).get(slot) if field else None
        if field:
            need_a = st.get("hem_plus") if st else None
            need_b = r.get("team_dem_plus")
        else:
            need_a = r.get({"DH": "offense_plus", "SP": "rotation_plus", "RP": "bullpen_plus"}[slot])
            need_b = None
        raw[c] = {
            "need_a": _partner_num(need_a), "need_b": _partner_num(need_b),
            "starter": st.get("name") if st else None,
            "contention": _partner_num((clubs[c].get(con["section"]) or {}).get(con["key"])),
            "tax": partner_tax(clubs[c].get("fin"), season, charge, frac, tx.get("rates"),
                               tx.get("surcharge_tiers_usd")),
            "pay": _partner_num((clubs[c].get("farm") or {}).get("farm_surplus_mm")),
        }
    fa = partner_factor(cands, lambda c: raw[c]["need_a"], False)
    fb = partner_factor(cands, lambda c: raw[c]["need_b"], False) if field else None
    fc = partner_factor(cands, lambda c: raw[c]["contention"], True)
    ft = partner_factor(cands, lambda c: raw[c]["tax"]["marginal"] if raw[c]["tax"] else None, False)
    fp = partner_factor(cands, lambda c: raw[c]["pay"], True)

    def u(x):
        return 28 if x is None else x
    rows = []
    for c in cands:
        need = (u(fa[c]) + u(fb[c])) if field else 2 * u(fa[c])
        cont, tax, pay = 2 * u(fc[c]), 2 * u(ft[c]), 2 * u(fp[c])
        rows.append({"club": c, "raw": raw[c],
                     "missing": [k for k, f in (("need", fa[c]), ("need_dem", fb[c] if field else 0),
                                                ("contention", fc[c]), ("tax", ft[c]), ("pay", fp[c]))
                                 if f is None],
                     "u": {"need": need, "contention": cont, "tax": tax, "pay": pay,
                           "score": need + cont + tax + pay}})
    rows.sort(key=lambda x: (-x["u"]["score"], -x["u"]["need"], -x["u"]["contention"],
                             -x["u"]["pay"], x["club"]))
    for i, x in enumerate(rows):
        x["order"] = i + 1
    return {"rule": "partner_v1", "slot": slot, "own": own, "own_raw": raw[own],
            "season": season, "charge": charge, "frac": frac, "rows": rows,
            "top": [x["club"] for x in rows[:5]]}
# ---- Trade partner screen rule partner_v1 (end)


# ---------------------------------------------------------------------------
# the players the screen answers for (gate 2.5)
# ---------------------------------------------------------------------------
def cbt_charge(kind: str, proj: dict | None, season: int, season_now: int) -> tuple:
    """_tmCbtCharge's twin: (usd, known) for one asset in `season`."""
    if kind == "prospect":
        return 0.0, True
    if not proj:
        return 0.0, False
    aav = _num(proj.get("aav"))
    if season == season_now:
        if aav is not None and proj.get("thru") is not None and int(proj["thru"]) >= season:
            return aav, True
        return 0.0, False
    row = next((r for r in proj.get("salPath") or [] if r and int(r[0]) == season), None)
    if not row:
        return 0.0, True
    opt = next((o for o in proj.get("salOpt") or [] if o and int(o[0]) == season), None)
    optional = bool(opt) and opt[1] in ("club", "mutual")
    if row[4] != "signed" or row[5] != "contract" or optional:
        return 0.0, True
    return (aav if aav is not None else (_num(row[1]) or 0.0)), True


def _is_mlb(p: dict) -> bool:
    return p.get("status") in ("graduated", "debuted")


def players(sl: dict, data_dir: Path | None = None) -> tuple[list, dict]:
    """Every player the Trade Machine prices (its search pools): prospects on
    the board, MLB players with a projection surplus, and board-valued MLB
    players. Returns (players, skipped counts by reason)."""
    d = Path(data_dir or DATA)
    tv = _read_json(d / "trade_values.json")
    det = (_read_json(d / "mlb_player_detail.json").get("players") or {})
    season, season_now = sl["tax"]["season"], sl["season_now"]
    out, seen = [], set()
    skipped = {"no_slot": 0, "no_club": 0}
    no_slot_pos: dict = {}

    def add(scope, key, mlbam, name, pos, org, proj, kind):
        if (scope, key) in seen:
            return
        seen.add((scope, key))
        slot = partner_slot(pos)
        club = _club_code(org) if org else None
        if not slot:
            skipped["no_slot"] += 1
            p = str(pos or "").strip() or "(none)"
            no_slot_pos[p] = no_slot_pos.get(p, 0) + 1
            return
        if not club or club not in sl["clubs"]:
            skipped["no_club"] += 1
            return
        usd, known = cbt_charge(kind, proj, season, season_now)
        out.append({"id": int(mlbam) if mlbam not in (None, "") else key, "key": key,
                    "name": name, "scope": scope, "slot": slot, "club": club,
                    "cbt_usd": usd, "cbt_known": known})

    for p in tv.get("players") or []:
        if p and not _is_mlb(p) and p.get("posterior_surplus_mm") is not None:
            add("prospect", p.get("player_key"), p.get("mlbam_id"), p.get("player_name"),
                p.get("position"), p.get("org"), None, "prospect")
    for k, v in det.items():
        pr = v.get("proj") or {}
        if pr.get("surTotal") is not None or pr.get("surNpv") is not None:
            add("mlb", k, v.get("mlbam"), v.get("name"), v.get("pos"), v.get("team"), pr, "mlb")
    for p in tv.get("players") or []:
        if p and _is_mlb(p) and p.get("posterior_surplus_mm") is not None:
            key = p.get("proj_key") or p.get("player_key")
            dv = det.get(key) or {}
            add("mlb", key, p.get("mlbam_id"), p.get("player_name"), p.get("position"),
                p.get("org"), dv.get("proj"), "mlb")
    skipped["no_slot_by_position"] = dict(sorted(no_slot_pos.items()))
    return out, skipped


# ---------------------------------------------------------------------------
# the record (gate 3)
# ---------------------------------------------------------------------------
def _f(units: int, per: int) -> float:
    return round(units / per, 6)


def player_row(sl: dict, pl: dict) -> dict | None:
    sc = rank_screen(sl, pl)
    if not sc:
        return None
    cands = [[x["club"], _f(x["u"]["need"], 112), _f(x["u"]["contention"], 112),
              _f(x["u"]["tax"], 112), _f(x["u"]["pay"], 112), _f(x["u"]["score"], 112)]
             for x in sc["rows"]]
    return {"id": pl["id"], "key": pl["key"], "name": pl["name"], "scope": pl["scope"],
            "slot": pl["slot"], "club": pl["club"], "cbt_usd": pl["cbt_usd"],
            "cbt_known": pl["cbt_known"], "candidates": cands, "top5": sc["top"]}


def build_entry(sl: dict, sl_bytes: bytes, pls: list, skipped: dict, *,
                now: _dt.datetime, machine: str, js_text: str | None = None) -> dict:
    """One as-of day's entry: the header and one row per player (gate 3.1)."""
    rows = []
    for pl in sorted(pls, key=lambda p: (p["scope"], p["club"], p["slot"], p["cbt_usd"], str(p["id"]))):
        r = player_row(sl, pl)
        if r:
            rows.append(r)
    missing = {}
    for code, c in sl["clubs"].items():
        gaps = []
        r = c.get("roster") or {}
        for pos in TM_PARTNER_FIELD:
            st = (r.get("starters") or {}).get(pos)
            if not st or st.get("hem_plus") is None:
                gaps.append(f"hem_plus_{pos}")
        for k in ("team_dem_plus", "offense_plus", "rotation_plus", "bullpen_plus"):
            if r.get(k) is None:
                gaps.append(k)
        con = sl["contention"]
        if (c.get(con["section"]) or {}).get(con["key"]) is None:
            gaps.append(con["key"])
        if (c.get("fin") or {}).get(f"tax_payroll_{sl['tax']['season']}") is None:
            gaps.append(f"tax_payroll_{sl['tax']['season']}")
        if (c.get("farm") or {}).get("farm_surplus_mm") is None:
            gaps.append("farm_surplus_mm")
        if gaps:
            missing[code] = gaps
    contender = {code: (None if (c.get("odds") or {}).get("playoff_pct") is None
                        else (c["odds"]["playoff_pct"] >= 0.25))
                 for code, c in sorted(sl["clubs"].items())}
    return {
        "header": {
            "as_of": sl["as_of"],
            "generated_at": now.astimezone(_dt.timezone.utc).isoformat(timespec="seconds"),
            "machine": machine,
            "rule_version": RULE_VERSION,
            "rule_sha256": rule_sha256(js_text),
            "rule_py_sha256": rule_py_sha256(),
            "slice_sha256": _sha(sl_bytes),
            "contender_flag": {"threshold": 0.25, "basis": "odds.playoff_pct", "clubs": contender},
            "missing_inputs": missing,
            "skipped_players": skipped,
            "candidate_fields": CANDIDATE_FIELDS,
            "slice": sl,
        },
        "n_players": len(rows),
        "players": rows,
    }


def replay(entry: dict) -> bool:
    """Gate 3.1: every stored row recomputed from the entry's own inputs, byte for byte."""
    sl = entry["header"]["slice"]
    for r in entry["players"]:
        pl = {k: r[k] for k in ("id", "key", "name", "scope", "slot", "club", "cbt_usd", "cbt_known")}
        if _canon(player_row(sl, pl)) != _canon(r):
            return False
    return True


def _write_atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)


def _row_hash(row: dict) -> str:
    return _sha(_canon({k: v for k, v in row.items() if k != "row_hash"}))


def load_chain(rec_dir: Path) -> dict:
    p = Path(rec_dir) / "chain.json"
    if not p.is_file():
        return {"schema": SCHEMA, "rows": []}
    ch = _read_json(p)
    verify_chain(ch)
    return ch


def verify_chain(ch: dict) -> None:
    prev = None
    last = ""
    for r in ch.get("rows") or []:
        if r.get("prev_row_hash") != prev:
            raise ScreenRefusal(f"chain breaks at {r.get('as_of')}")
        if _row_hash(r) != r.get("row_hash"):
            raise ScreenRefusal(f"chain row {r.get('as_of')} was edited")
        if str(r.get("as_of")) <= last:
            raise ScreenRefusal(f"chain row {r.get('as_of')} is out of order")
        last = str(r.get("as_of"))
        prev = r["row_hash"]


def _amended(version: str, sha: str) -> bool:
    """Gate 3.3: a new rule version is admitted only when the gate names it and its hash."""
    try:
        g = GATE_PATH.read_text(encoding="utf-8")
    except OSError:
        return False
    return version in g and sha in g


def write_day(entry: dict, rec_dir: Path, public_chain: Path) -> dict:
    """Freeze one day (gate 3.2): first write wins, no earlier date ever, the
    rule hash checked against the chain's first entry of the same version."""
    rec_dir = Path(rec_dir)
    h = entry["header"]
    as_of = h["as_of"]
    day = rec_dir / f"{as_of}.json.gz"
    ch = load_chain(rec_dir)
    rows = ch["rows"]
    if day.exists() or any(r["as_of"] == as_of for r in rows):
        return {"status": "exists", "as_of": as_of, "path": str(day)}
    if rows and as_of < rows[-1]["as_of"]:
        raise ScreenRefusal(f"{as_of} is earlier than the chain's last day {rows[-1]['as_of']}")
    first = next((r for r in rows if r["rule_version"] == h["rule_version"]), None)
    if first and first["rule_sha256"] != h["rule_sha256"]:
        raise ScreenRefusal(f"rule text changed under {h['rule_version']}: "
                            f"{h['rule_sha256'][:12]} against {first['rule_sha256'][:12]}")
    if not first and rows and not _amended(h["rule_version"], h["rule_sha256"]):
        raise ScreenRefusal(f"rule version {h['rule_version']} has no dated amendment in the gate")
    canon = _canon(entry)
    content = _sha(canon)
    _write_atomic(day, gzip.compress(canon, compresslevel=9, mtime=0))
    row = {"as_of": as_of, "machine": h["machine"], "rule_version": h["rule_version"],
           "rule_sha256": h["rule_sha256"], "content_sha256": content,
           "prev_row_hash": rows[-1]["row_hash"] if rows else None}
    row["row_hash"] = _row_hash(row)
    ch = {"schema": SCHEMA, "rows": rows + [row]}
    raw = json.dumps(ch, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    _write_atomic(rec_dir / "chain.json", raw)
    _write_atomic(Path(public_chain), raw)
    return {"status": "written", "as_of": as_of, "path": str(day), "content_sha256": content,
            "bytes": day.stat().st_size, "n_players": entry["n_players"]}


def read_day(path: Path) -> dict:
    return json.loads(gzip.decompress(Path(path).read_bytes()).decode("utf-8"))


# ---------------------------------------------------------------------------
# the nightly entry point
# ---------------------------------------------------------------------------
def run(*, now: _dt.datetime | None = None, machine: str | None = None, live: bool | None = None,
        data_dir: Path | None = None, cache_dir: Path | None = None, log_fn=print) -> dict:
    """Write tonight's slice and the day's entry where the flag says. A
    refusal raises ScreenRefusal and leaves the previous files standing."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    as_of = _ny_date(now)
    where = paths(live, data_dir, cache_dir)
    sl = build_slice(as_of, data_dir)
    raw = slice_bytes(sl)
    _write_atomic(where["slice"], raw)
    pls, skipped = players(sl, data_dir)
    entry = build_entry(sl, raw, pls, skipped, now=now, machine=machine or detect_machine())
    if not replay(entry):
        raise ScreenRefusal("the entry does not replay from its own inputs")
    res = write_day(entry, where["record"], where["public_chain"])
    res.update({"live": where["live"], "slice": str(where["slice"]), "slice_bytes": len(raw),
                "skipped": skipped})
    log_fn(f"trade partner screen ({'live' if where['live'] else 'preview'}): slice "
           f"{len(raw) / 1e3:.1f} KB; day {as_of} {res['status']}; "
           f"{entry['n_players']} players, skipped {skipped['no_slot']} with no slot and "
           f"{skipped['no_club']} with no club")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Trade Machine partner screen slice and frozen record")
    ap.add_argument("--now", default=None, help="ISO datetime with offset (default: now)")
    args = ap.parse_args(argv)
    now = _dt.datetime.fromisoformat(args.now) if args.now else None
    try:
        run(now=now)
    except ScreenRefusal as exc:
        print(f"REFUSED: {exc}; the previous files stand")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
