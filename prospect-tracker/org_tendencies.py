# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Organization Tendencies — per-org behavioral profiles for the PROSPX
farm detail pages (data/org_tendencies.json).

Eight panels, every number LEAGUE-RELATIVE (each org's value next to the
league mean/sd so the UI can draw z-bars and the labels can't drift from
the data that earned them):

  promotion    aggressive vs conservative: how young-for-level the org
               runs its prospects (age_vs_level) + promotions per active
               prospect over the trailing year (level_changes).
  draftPos     what the org drafts: pitcher share, prep share,
               up-the-middle share of signed picks (2021-present).
  draftTraits  WHO the org drafts: mean FG tool profile of its signed
               draftees vs the league draftee mean (power-over-hit,
               speed/athleticism, command-over-stuff...).
  arsenal      pitch-shape identity of the CURRENT pitching inventory:
               per-pitch-type usage vs league, fastball velocity. v1 is a
               PROFILE, not a conversion ledger — per-pitch usage history
               isn't stored, so "turns four-seamers into sinkers" claims
               wait for arsenal snapshots (documented fork).
  toolDev      what the org actually DEVELOPS: per-tool future-grade
               drift per prospect-year in org, from same-source snapshot
               pairs (2017-present grade history), minus the league mean.
               Includes pitch tools (fb/sl/cb/ch/cmd) — the honest version
               of "best at developing sliders". Plus the SC+ (Statcast
               composite) drift over the platform's metric history
               (early window, disclosed).
  ifa          quality vs quantity: bonus-pool concentration (top-signing
               share, HHI), seven-figure signings, volume per class.
  trades       trade-happy vs reluctant (volume z), prospect-capital
               direction (acquirer vs shipper), quality-vs-depth of
               acquired prospects (graded near trade date), cash-
               consideration involvement (parsed from MLB tx descriptions).
  health/slot  two extras: IL burden per active prospect, and draft-pool
               allocation style (over-slot rate; round-1 underslot
               cut-deals that spread pool money later).

Read-only consumer of the DB + committed sidecars (same contract as the
FA module): never writes prospect data. Wired into run_monthly after the
exports; safe to run standalone: python org_tendencies.py
"""

from __future__ import annotations

import json
import logging
import re
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import storage
from trades import canonical_org

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "org_tendencies.json"

DRAFT_FIRST_YEAR = 2021
TRADE_FIRST_DATE = "2022-01-01"
HIT_TOOLS = ("hit", "game_pwr", "raw_pwr", "speed", "field", "pitch_sel", "bat_ctrl")
PIT_TOOLS = ("fb", "sl", "cb", "ch", "cmd")
UP_MIDDLE = {"C", "SS", "CF", "2B"}
MIN_PAIR_DAYS = 60          # same-source snapshot pairs must span at least this
MIN_TOOL_PAIRS = 6          # org-tool cells below this report null, never noise


def _z(v, mean, sd):
    if v is None or mean is None or not sd:
        return None
    return round((v - mean) / sd, 2)


def _league_stats(values: dict[str, float | None]) -> dict:
    vals = [v for v in values.values() if v is not None]
    if len(vals) < 8:
        return {"mean": None, "sd": None}
    return {"mean": round(statistics.mean(vals), 4),
            "sd": round(statistics.pstdev(vals), 4) or None}


def _label(z, hi: str, lo: str, mid: str = "typical", cut: float = 0.5) -> str | None:
    if z is None:
        return None
    if z >= cut:
        return hi
    if z <= -cut:
        return lo
    return mid


# ============================================================================
# Inputs
# ============================================================================

def _timeseries_players() -> list[dict]:
    try:
        return json.loads((DATA_DIR / "timeseries.json").read_text(encoding="utf-8"))["players"]
    except (OSError, ValueError, KeyError):
        log.warning("org_tendencies: timeseries.json unavailable")
        return []


def _actives_by_org(players) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for p in players:
        if p.get("status") == "active" and p.get("org"):
            out[p["org"]].append(p)
    return dict(out)


# ============================================================================
# Panel 1 — promotion aggressiveness
# ============================================================================

def promotion_panel(by_org: dict[str, list[dict]], today: date) -> dict:
    cutoff = (today - timedelta(days=365)).isoformat()
    raw = {}
    for org, roster in by_org.items():
        diffs = [(p.get("age_vs_level") or {}).get("diff") for p in roster]
        diffs = [d for d in diffs if d is not None]
        promos = sum(1 for p in roster for lc in (p.get("level_changes") or [])
                     if lc.get("kind") == "promotion" and (lc.get("date") or "") >= cutoff)
        raw[org] = {
            "avlDiff": round(statistics.mean(diffs), 2) if diffs else None,
            "promoRate": round(promos / len(roster), 2) if roster else None,
            "n": len(roster),
        }
    lg_avl = _league_stats({o: r["avlDiff"] for o, r in raw.items()})
    lg_pr = _league_stats({o: r["promoRate"] for o, r in raw.items()})
    for r in raw.values():
        z_young = _z(r["avlDiff"], lg_avl["mean"], lg_avl["sd"])
        z_promo = _z(r["promoRate"], lg_pr["mean"], lg_pr["sd"])
        # Aggressive = young-for-level (negative avl z) AND promotes often.
        score = None
        if z_young is not None or z_promo is not None:
            parts = [v for v in (-(z_young or 0), z_promo or 0)
                     if z_young is not None or z_promo is not None]
            score = round(sum(parts) / 2, 2)
        r["zYoung"] = z_young
        r["zPromo"] = z_promo
        r["score"] = score
        r["label"] = _label(score, "aggressive", "conservative")
    return {"orgs": raw, "league": {"avlDiff": lg_avl, "promoRate": lg_pr}}


# ============================================================================
# Panels 2+3 — draft position & trait preferences (+ slot allocation)
# ============================================================================

def _is_pitcher_pos(pos: str | None) -> bool:
    head = (pos or "").upper().split("/")[0].strip()
    return head in ("P", "SP", "RP", "RHP", "LHP", "SP2")


def draft_panels(con) -> tuple[dict, dict, dict]:
    picks = con.execute("""
        SELECT r.team, r.draft_year, r.pick_overall, r.round_label, r.slot_usd,
               r.bonus_usd, p.position, p.player_type, r.player_key
        FROM draft_results r LEFT JOIN draft_players p USING (player_key)
        WHERE r.signed = 1 AND r.draft_year >= ?""", (DRAFT_FIRST_YEAR,)).fetchall()
    tools_by_key: dict[str, dict] = {}
    for key, tj in con.execute("""
        SELECT player_key, tools_json FROM draft_snapshots
        WHERE source = 'fangraphs' AND tools_json IS NOT NULL
          AND draft_year >= ? ORDER BY snapshot_date""", (DRAFT_FIRST_YEAR,)):
        try:
            tools_by_key[key] = json.loads(tj)        # latest per key wins
        except ValueError:
            continue
    pos_raw: dict[str, dict] = {}
    trait_acc: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    league_acc: dict[str, list] = defaultdict(list)
    slot_raw: dict[str, dict] = {}
    by_org: dict[str, list] = defaultdict(list)
    for row in picks:
        by_org[row[0]].append(row)
    for org, rows in by_org.items():
        n = len(rows)
        n_pos_known = sum(1 for r in rows if r[6])
        pitch = sum(1 for r in rows if _is_pitcher_pos(r[6]))
        prep = sum(1 for r in rows if (r[7] or "").upper().startswith("HS"))
        upmid = sum(1 for r in rows
                    if (r[6] or "").upper().split("/")[0] in UP_MIDDLE)
        pos_raw[org] = {
            "n": n,
            "pitchShare": round(pitch / n_pos_known, 3) if n_pos_known else None,
            "prepShare": round(prep / n_pos_known, 3) if n_pos_known else None,
            "upMidShare": round(upmid / n_pos_known, 3) if n_pos_known else None,
        }
        # slot allocation: rounds with published slots only
        slotted = [(r[5], r[4], r[3]) for r in rows if r[4] and r[5]]
        over = sum(1 for b, s, _ in slotted if b > s * 1.05)
        r1 = [(b, s) for b, s, rl in slotted if rl == "1"]
        r1_under = sum(1 for b, s in r1 if b < s * 0.95)
        slot_raw[org] = {
            "nSlotted": len(slotted),
            "overSlotShare": round(over / len(slotted), 3) if slotted else None,
            "r1UnderShare": round(r1_under / len(r1), 3) if r1 else None,
        }
        for r in rows:
            t = tools_by_key.get(r[8])
            if not t:
                continue
            for k in HIT_TOOLS + PIT_TOOLS:
                v = t.get(k)
                if isinstance(v, (int, float)) and 20 <= v <= 80:
                    trait_acc[org][k].append(float(v))
                    league_acc[k].append(float(v))
    lg_tool = {k: {"mean": round(statistics.mean(v), 2),
                   "sd": round(statistics.pstdev(v), 2) or None}
               for k, v in league_acc.items() if len(v) >= 60}
    traits = {}
    for org, acc in trait_acc.items():
        tilts = {}
        for k, vals in acc.items():
            if k in lg_tool and len(vals) >= 5:
                tilts[k] = _z(statistics.mean(vals), lg_tool[k]["mean"], lg_tool[k]["sd"])
        ranked = sorted((kv for kv in tilts.items() if kv[1] is not None),
                        key=lambda kv: -abs(kv[1]))
        traits[org] = {"tilts": tilts,
                       "top": [{"tool": k, "z": z} for k, z in ranked[:3] if abs(z) >= 0.4]}
    lg_pos = {k: _league_stats({o: r[k] for o, r in pos_raw.items()})
              for k in ("pitchShare", "prepShare", "upMidShare")}
    for org, r in pos_raw.items():
        r["zPitch"] = _z(r["pitchShare"], lg_pos["pitchShare"]["mean"], lg_pos["pitchShare"]["sd"])
        r["zPrep"] = _z(r["prepShare"], lg_pos["prepShare"]["mean"], lg_pos["prepShare"]["sd"])
        r["zUpMid"] = _z(r["upMidShare"], lg_pos["upMidShare"]["mean"], lg_pos["upMidShare"]["sd"])
    lg_slot = {k: _league_stats({o: r[k] for o, r in slot_raw.items()})
               for k in ("overSlotShare", "r1UnderShare")}
    for org, r in slot_raw.items():
        r["zOver"] = _z(r["overSlotShare"], lg_slot["overSlotShare"]["mean"], lg_slot["overSlotShare"]["sd"])
        r["label"] = _label(r.get("zOver"), "over-slot shoppers", "slot-disciplined")
    return ({"orgs": pos_raw, "league": lg_pos},
            {"orgs": traits, "league": lg_tool},
            {"orgs": slot_raw, "league": lg_slot})


# ============================================================================
# Panel 4 — current arsenal profile
# ============================================================================

def arsenal_panel(con, players: list[dict]) -> dict:
    """Pitch-shape identity of the org's PRODUCT: the MLB arsenals of the
    players it developed (pitch_arsenals stores Statcast arsenals, which
    exist once a player reaches MLB tracking — graduates and debuts). The
    org attribution is the developing org from the platform's own record,
    so 'sinker org' means 'their arms ARRIVE in MLB throwing sinkers'."""
    org_of = {p["player_key"]: p["org"] for p in players if p.get("org")}
    # Statcast arsenals exist for MLB-tracked players — the GRADUATES, who
    # live in the debuts sidecar (org = the platform's record of who
    # developed them), not the active board.
    try:
        debuts = json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8"))
        for p in (debuts if isinstance(debuts, list) else debuts.get("players") or []):
            if p.get("player_key") and p.get("org"):
                org_of.setdefault(p["player_key"], p["org"])
    except (OSError, ValueError):
        log.warning("org_tendencies: debuts.json unavailable — arsenal panel thin")
    usage: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    velo: dict[str, list] = defaultdict(list)
    n_arms: dict[str, int] = defaultdict(int)
    lg_usage: dict[str, float] = defaultdict(float)
    lg_total = 0.0
    for key, payload in con.execute("SELECT player_key, payload_json FROM pitch_arsenals"):
        org = org_of.get(key)
        if not org:
            continue
        try:
            a = json.loads(payload)
        except ValueError:
            continue
        n_arms[org] += 1
        if a.get("fb_velo"):
            velo[org].append(float(a["fb_velo"]))
        for p in a.get("pitches") or []:
            u = p.get("usage_pct") or 0
            usage[org][p.get("pitch_type") or "?"] += u
            lg_usage[p.get("pitch_type") or "?"] += u
            lg_total += u
    lg_share = {pt: v / lg_total for pt, v in lg_usage.items() if lg_total}
    raw = {}
    for org, mix in usage.items():
        tot = sum(mix.values()) or 1.0
        ratios = {}
        for pt, v in mix.items():
            share = v / tot
            base = lg_share.get(pt)
            if base and base >= 0.02 and share >= 0.01:
                ratios[pt] = round(share / base, 2)
        ranked = sorted(ratios.items(), key=lambda kv: -abs(kv[1] - 1.0))
        raw[org] = {
            "nArms": n_arms[org],
            "fbVelo": round(statistics.mean(velo[org]), 1) if velo.get(org) else None,
            "usageRatio": dict(ranked),
            "lean": [{"pt": pt, "x": x} for pt, x in ranked[:3] if abs(x - 1.0) >= 0.25],
        }
    lg_velo = _league_stats({o: r["fbVelo"] for o, r in raw.items()})
    for r in raw.values():
        r["zVelo"] = _z(r["fbVelo"], lg_velo["mean"], lg_velo["sd"])
    return {"orgs": raw, "league": {"fbVelo": lg_velo, "share": {
        pt: round(s, 4) for pt, s in sorted(lg_share.items(), key=lambda kv: -kv[1])}}}


# ============================================================================
# Panel 5 — tool development (grade drift per prospect-year in org)
# ============================================================================

def tool_dev_panel(con) -> dict:
    rows = con.execute("""
        SELECT player_key, source, snapshot_date, org, tools_json
        FROM snapshots
        WHERE tools_json IS NOT NULL AND org IS NOT NULL AND status = 'active'
        ORDER BY player_key, source, snapshot_date""").fetchall()
    acc: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"d": 0.0, "yr": 0.0, "n": 0}))
    prev = None
    for key, src, d, org, tj in rows:
        try:
            tools = {k: v for k, v in json.loads(tj).items()
                     if k in HIT_TOOLS + PIT_TOOLS and isinstance(v, (int, float))
                     and 20 <= v <= 80}
        except ValueError:
            prev = None
            continue
        cur = (key, src, d, org, tools)
        if prev and prev[0] == key and prev[1] == src and prev[3] == org:
            try:
                dt = (date.fromisoformat(d) - date.fromisoformat(prev[2])).days
            except ValueError:
                dt = 0
            if dt >= MIN_PAIR_DAYS:
                yrs = dt / 365.25
                for k, v1 in tools.items():
                    v0 = prev[4].get(k)
                    if v0 is not None:
                        slot = acc[org][k]
                        slot["d"] += v1 - v0
                        slot["yr"] += yrs
                        slot["n"] += 1
        prev = cur
    per_org: dict[str, dict[str, float]] = {}
    league_rates: dict[str, list] = defaultdict(list)
    for org, by_tool in acc.items():
        rates = {}
        for k, s in by_tool.items():
            if s["n"] >= MIN_TOOL_PAIRS and s["yr"] > 0:
                rates[k] = round(s["d"] / s["yr"], 2)
                league_rates[k].append(rates[k])
        per_org[org] = rates
    lg = {k: {"mean": round(statistics.mean(v), 2),
              "sd": round(statistics.pstdev(v), 2) or None}
          for k, v in league_rates.items() if len(v) >= 10}
    out = {}
    for org, rates in per_org.items():
        rel = {}
        for k, r in rates.items():
            if k in lg:
                rel[k] = {"rate": r, "vsLeague": round(r - lg[k]["mean"], 2),
                          "z": _z(r, lg[k]["mean"], lg[k]["sd"])}
        best = sorted((kv for kv in rel.items() if kv[1]["z"] is not None),
                      key=lambda kv: -kv[1]["z"])
        out[org] = {"tools": rel,
                    "best": [{"tool": k, "z": v["z"], "vsLeague": v["vsLeague"]}
                             for k, v in best[:3] if v["z"] >= 0.4],
                    "worst": [{"tool": k, "z": v["z"], "vsLeague": v["vsLeague"]}
                              for k, v in reversed(best[-2:]) if v["z"] <= -0.4]}
    # SC+ drift over the platform's metric history (short window — disclosed)
    sc_rows = con.execute("""
        SELECT player_key, org, snapshot_date, payload_json FROM metric_snapshots
        WHERE org IS NOT NULL ORDER BY player_key, snapshot_date""").fetchall()
    first_last: dict[tuple, list] = {}
    for key, org, d, payload in sc_rows:
        try:
            sc = json.loads(payload).get("statcast_plus")
        except ValueError:
            continue
        if sc is None:
            continue
        slot = first_last.setdefault((key, org), [None, None])
        if slot[0] is None:
            slot[0] = (d, sc)
        slot[1] = (d, sc)
    sc_acc: dict[str, list] = defaultdict(list)
    for (key, org), (a, b) in first_last.items():
        if a and b and a[0] != b[0]:
            sc_acc[org].append(b[1] - a[1])
    sc_org = {org: round(statistics.mean(v), 1) for org, v in sc_acc.items() if len(v) >= 5}
    lg_sc = _league_stats(sc_org)
    for org, v in sc_org.items():
        if org in out:
            out[org]["scPlusDrift"] = v
            out[org]["scPlusZ"] = _z(v, lg_sc["mean"], lg_sc["sd"])
    return {"orgs": out, "league": {"tools": lg, "scPlus": lg_sc}}


# ============================================================================
# Panel 6 — IFA strategy (quality vs quantity)
# ============================================================================

def ifa_panel() -> dict:
    try:
        classes = json.loads((DATA_DIR / "ifa_timeseries.json")
                             .read_text(encoding="utf-8"))["classes"]
    except (OSError, ValueError, KeyError):
        log.warning("org_tendencies: ifa_timeseries.json unavailable")
        return {"orgs": {}, "league": {}}
    per: dict[str, dict[int, list]] = defaultdict(dict)
    for cls in classes:
        for s in cls.get("signings") or []:
            org, b = s.get("org"), s.get("bonus_usd")
            if org:
                per[org].setdefault(cls["year"], []).append(b or 0)
    raw = {}
    for org, by_year in per.items():
        t1, hhi, mil, n = [], [], 0, 0
        for _yr, bonuses in by_year.items():
            known = [b for b in bonuses if b > 0]
            n += len(bonuses)
            mil += sum(1 for b in known if b >= 1_000_000)
            tot = sum(known)
            if tot and len(known) >= 3:
                shares = [b / tot for b in known]
                t1.append(max(shares))
                hhi.append(sum(s * s for s in shares))
        raw[org] = {
            "classes": len(by_year),
            "signingsPerClass": round(n / len(by_year), 1) if by_year else None,
            "top1Share": round(statistics.mean(t1), 3) if t1 else None,
            "hhi": round(statistics.mean(hhi), 3) if hhi else None,
            "sevenFigure": mil,
        }
    lg = {k: _league_stats({o: r[k] for o, r in raw.items()})
          for k in ("top1Share", "hhi", "signingsPerClass")}
    for r in raw.values():
        r["zConc"] = _z(r["hhi"], lg["hhi"]["mean"], lg["hhi"]["sd"])
        r["zVolume"] = _z(r["signingsPerClass"], lg["signingsPerClass"]["mean"],
                          lg["signingsPerClass"]["sd"])
        r["label"] = _label(r["zConc"], "quality (one big fish)", "quantity (spread the pool)",
                            "balanced")
    return {"orgs": raw, "league": lg}


# ============================================================================
# Panel 7 — trade tendencies
# ============================================================================

_CASH_RE = re.compile(r"^(?P<from>.+?) traded .+? to (?P<to>.+?) for (?P<ret>.+)\.?$")


def cash_direction(description: str) -> str | None:
    """Which side RECEIVED cash in an MLB tx description. 'A traded X to B
    for ... cash' → A received cash. Returns the receiving club name."""
    m = _CASH_RE.match(description or "")
    if not m:
        return None
    if "cash" in m.group("ret").lower():
        return m.group("from").strip()
    return None


def trades_panel(con) -> dict:
    rows = con.execute("""
        SELECT player_key, trade_date, from_org, to_org, source, description
        FROM trades WHERE trade_date >= ?""", (TRADE_FIRST_DATE,)).fetchall()
    fv_near = _fv_near_date_index(con)
    inb: dict[str, list] = defaultdict(list)
    out_n: dict[str, int] = defaultdict(int)
    deals: dict[str, set] = defaultdict(set)
    cash_recv: dict[str, int] = defaultdict(int)
    cash_any: dict[str, int] = defaultdict(int)
    for key, d, frm, to, _src, desc in rows:
        if to:
            inb[to].append((key, d))
            deals[to].add((d, frm, to))
        if frm:
            out_n[frm] += 1
            deals[frm].add((d, frm, to))
        if desc and "cash" in desc.lower():
            # mlb_api description rows often carry NULL org columns — both
            # clubs come from the description parse, never the columns.
            m = _CASH_RE.match(desc)
            if m:
                a = canonical_org(m.group("from").strip())
                b = canonical_org(m.group("to").strip())
                for org in (a, b):
                    if org:
                        cash_any[org] += 1
                recv = cash_direction(desc)
                recv_org = canonical_org(recv) if recv else None
                if recv_org:
                    cash_recv[recv_org] += 1
    raw = {}
    orgs = set(inb) | set(out_n)
    for org in orgs:
        if len(org or "") > 3:
            continue                                    # foreign league codes
        acquired = inb.get(org, [])
        fvs = [fv for fv in (fv_near(key, d) for key, d in acquired) if fv is not None]
        n_in, n_out = len(acquired), out_n.get(org, 0)
        n_deals = len(deals.get(org, ())) or 1
        raw[org] = {
            "in": n_in, "out": n_out, "volume": n_in + n_out,
            "netProspects": n_in - n_out,
            "prospectsPerDeal": round((n_in + n_out) / n_deals, 2),
            "acqFvMean": round(statistics.mean(fvs), 1) if fvs else None,
            "acqTopShare": round(sum(1 for v in fvs if v >= 50) / len(fvs), 2) if fvs else None,
            "nGraded": len(fvs),
            "cashReceived": cash_recv.get(org, 0),
            "cashInvolved": cash_any.get(org, 0),
        }
    lg = {k: _league_stats({o: r[k] for o, r in raw.items()})
          for k in ("volume", "netProspects", "acqTopShare", "prospectsPerDeal",
                    "cashReceived")}
    for r in raw.values():
        r["zVolume"] = _z(r["volume"], lg["volume"]["mean"], lg["volume"]["sd"])
        r["zNet"] = _z(r["netProspects"], lg["netProspects"]["mean"], lg["netProspects"]["sd"])
        r["zQuality"] = _z(r["acqTopShare"], lg["acqTopShare"]["mean"], lg["acqTopShare"]["sd"])
        r["zCash"] = _z(r["cashReceived"], lg["cashReceived"]["mean"], lg["cashReceived"]["sd"])
        r["volLabel"] = _label(r["zVolume"], "trade-happy", "trade-reluctant")
        r["dirLabel"] = _label(r["zNet"], "prospect acquirer", "prospect shipper (MLB buyer)",
                               "two-way")
        r["qdLabel"] = _label(r["zQuality"], "quality (top prospects)", "depth (volume)",
                              "balanced")
    return {"orgs": raw, "league": lg,
            "window": f"{TRADE_FIRST_DATE[:4]}-present",
            "note": ("prospect-capital lens: 'in'/'out' count tracked-prospect moves; "
                     "FV graded from board snapshots within ±120d of the trade — "
                     "ungraded moves are counted, never guessed")}


def _fv_near_date_index(con):
    """fv(player_key, trade_date) — median board FV within ±120 days."""
    rows = con.execute("""
        SELECT player_key, snapshot_date, fv FROM snapshots
        WHERE fv IS NOT NULL ORDER BY player_key, snapshot_date""").fetchall()
    by_key: dict[str, list] = defaultdict(list)
    for key, d, fv in rows:
        by_key[key].append((d, fv))

    def lookup(key: str, trade_date: str) -> float | None:
        pts = by_key.get(key)
        if not pts:
            return None
        try:
            td = date.fromisoformat(trade_date[:10])
        except ValueError:
            return None
        near = [fv for d, fv in pts
                if abs((date.fromisoformat(d[:10]) - td).days) <= 120]
        return statistics.median(near) if near else None
    return lookup


# ============================================================================
# Panel 8 — IL burden
# ============================================================================

def health_panel(con, by_org: dict[str, list[dict]]) -> dict:
    keys_org = {p["player_key"]: org for org, roster in by_org.items() for p in roster}
    stints: dict[str, int] = defaultdict(int)
    for (key,) in con.execute("SELECT player_key FROM il_history"):
        org = keys_org.get(key)
        if org:
            stints[org] += 1
    raw = {}
    for org, roster in by_org.items():
        raw[org] = {"stintsPer100": round(100 * stints.get(org, 0) / len(roster), 1)
                    if roster else None}
    lg = _league_stats({o: r["stintsPer100"] for o, r in raw.items()})
    for r in raw.values():
        r["z"] = _z(r["stintsPer100"], lg["mean"], lg["sd"])
        r["label"] = _label(r["z"], "high IL burden", "healthy pipeline")
    return {"orgs": raw, "league": lg}


# ============================================================================
# Payload
# ============================================================================

def _filter_mlb30(panel: dict, mlb30: set) -> dict:
    """Foreign-league and stale org codes (postings, renames) never get a
    tendencies page — every panel is filtered to the 30 live MLB orgs."""
    panel["orgs"] = {o: r for o, r in panel["orgs"].items() if o in mlb30}
    return panel


def build_payload() -> dict:
    players = _timeseries_players()
    by_org = _actives_by_org(players)
    mlb30 = set(by_org)
    with storage.connect() as con:
        draft_pos, draft_traits, slot = draft_panels(con)
        payload = {
            "generated_at": date.today().isoformat(),
            "windows": {"draft": f"{DRAFT_FIRST_YEAR}-present",
                        "trades": f"{TRADE_FIRST_DATE[:4]}-present",
                        "gradeHistory": "2017-present (same-source snapshot pairs)",
                        "promotion": "active roster, trailing 365d"},
            "promotion": promotion_panel(by_org, date.today()),
            "draftPos": _filter_mlb30(draft_pos, mlb30),
            "draftTraits": _filter_mlb30(draft_traits, mlb30),
            "slot": _filter_mlb30(slot, mlb30),
            "arsenal": _filter_mlb30(arsenal_panel(con, players), mlb30),
            "toolDev": _filter_mlb30(tool_dev_panel(con), mlb30),
            "ifa": _filter_mlb30(ifa_panel(), mlb30),
            "trades": _filter_mlb30(trades_panel(con), mlb30),
            "health": health_panel(con, by_org),
            "notes": [
                "every value is league-relative: z = (org − league mean) / league sd across the 30 orgs; labels only fire at |z| ≥ 0.5",
                "arsenal profiles the MLB pitch mixes of the players each org DEVELOPED (Statcast arsenals exist from MLB tracking) — what their arms throw when they arrive; per-pitch usage HISTORY isn't archived yet, so conversion claims (four-seam → sinker) are a documented v2 fork",
                "toolDev measures grade drift per prospect-year inside the org from SAME-SOURCE snapshot pairs (≥60d apart) — cross-source noise never counts as development",
                "SC+ drift covers the platform's metric-snapshot window only (2026-05 onward) — an early read, labeled as such",
                "trade quality/depth grades acquired prospects from board snapshots within ±120 days of the trade; ungraded moves count toward volume only",
            ],
        }
    return payload


def export() -> int:
    payload = build_payload()
    raw = json.dumps(payload, separators=(",", ":"))
    OUT_PATH.write_text(raw, encoding="utf-8")
    log.info("org tendencies export: %dKB, %d orgs",
             len(raw) // 1024, len(payload["promotion"]["orgs"]))
    return len(raw)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(export())
