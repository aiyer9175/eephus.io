# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Development attribution: which club developed a player, tenure by tenure.

Owner answer FP2-4 (2026-09-25): farm credit for a graduate goes to the club that
actually developed him, not the club that signed or acquired him and not the club
he plays for now. Design: docs/farm-attribution-2026-09-25/DEVELOPMENT_ATTRIBUTION.md.

Three steps, each a plain function so a test can drive it without a database:

  1. ORG CALENDAR. A player's dated history is cut into ORG TENURES
     (org, start, end). The calendar comes from the dated transactions
     (player_transactions): a signing, trade, waiver claim, Rule 5 move or return
     opens a tenure with the club that received him; a release or an election of
     free agency opens an unaffiliated stretch (org None) that credits nobody.
     Clubs resolve from the team id through staff_units (the season's affiliation
     map), else from the team name. A player without a transactions payload falls
     back to his trades (the farm history's documented rule), then to the
     point-in-time listed org, then to his current org. The calendar ends at the
     end of development: the MLB debut for a graduate, today for everyone else.

  2. TENURE GROWTH. Same-source consecutive grade pairs (one outlet's list to
     its next list on the same player) are the only growth that counts, the
     rule org_tendencies' toolDev already keeps, so cross-source noise never
     reads as development. A pair that spans an org change is split by days
     across the tenures it spans, instead of being dropped. Growth is measured
     on the expected-WAR scale of the FV grade (storage._fv_to_expected_war,
     the scale DvM+ already uses), so a 55 to 60 jump counts more than a 40 to
     45 jump. A tenure's growth is the mean over the outlets that observed it.

  3. SHARES. The signing club is credited with the value at acquisition, V0
     (the expected WAR of the first listed grade); each club is credited with
     the positive growth of its own tenures. Share = credit / total credit, so
     the shares sum to one. A tenure that lowered the grade earns zero, never a
     negative share; growth while unaffiliated credits nobody. With no
     positive credit anywhere the signing club takes the whole share.

A graduate's realized MLB value (WAR, contract surplus) is apportioned by these
shares. This is accounting, not a causal estimate: it says where the measured
grade growth happened, not what any club added.

Nothing here reads an outcome. No realized-WAR statistic is computed by grade
cell (docs/PROSPECT_ANCHOR_GATE.md) and nothing is fitted.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Iterable

log = logging.getLogger(__name__)

#: Outlets whose published grades count as growth. The ingest-only rows
#: (draft_signing, performance_ingest, mlb_pipeline_international and the
#: statcast-by-age list) publish no scouting grade series and stay out.
GROWTH_SOURCES = ("fangraphs", "mlb_pipeline", "baseballamerica", "espn",
                  "just_baseball", "tjstats")

#: Transaction types that put a player with a club (the receiving club).
ORG_JOIN_TYPES = frozenset({"SGN", "SFA", "DR", "TR", "CLW", "R5", "R5M", "RTN",
                            "ACQ", "OBT", "PUR", "CP"})
#: Joins that may land with a club outside affiliated ball (an independent or
#: foreign club), which opens an unaffiliated stretch.
UNAFFILIATED_JOIN_TYPES = frozenset({"SFA", "SGN", "ACQ", "OBT", "PUR"})
#: Released, elected free agency, retired: no club until the next join.
ORG_LEAVE_TYPES = frozenset({"REL", "DFA", "RET"})

TOOL_KEYS = ("hit", "game_pwr", "raw_pwr", "speed", "field", "pitch_sel", "bat_ctrl",
             "throw", "fb", "sl", "cb", "ch", "ct", "cmd")


def consolidate_pwr(tools: dict) -> dict:
    """Add the one Power grade `pwr` to an outlet's tool map by consensus.py's rule
    (the half-grade mean of game and raw power when both are printed, else the one
    printed). storage.TOOL_GROUPS["pwr"] reads this key; without it PowerDvM+ had no
    tenure growth on any club (docs/farm-attribution-2026-09-25/ETOOLS_DVM_GATE.md 0.3).
    An outlet's own `pwr` is kept."""
    if "pwr" not in tools:
        g, r = tools.get("game_pwr"), tools.get("raw_pwr")
        if g is not None and r is not None:
            tools["pwr"] = round(((g + r) / 2) * 2) / 2
        elif g is not None:
            tools["pwr"] = g
        elif r is not None:
            tools["pwr"] = r
    return tools


def _days(a: str, b: str) -> int:
    try:
        return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days
    except (TypeError, ValueError):
        return 0


@dataclass
class Tenure:
    org: str | None        # canonical club code; None = unaffiliated
    start: str             # ISO date, inclusive
    end: str               # ISO date, exclusive (the next tenure's start)

    def as_list(self) -> list:
        return [self.org, self.start, self.end]


@dataclass
class PlayerAttribution:
    player_key: str
    tenures: list[Tenure]
    basis: str                              # transactions | trades | listed_org | current_org
    signing_org: str | None
    v0: float | None                        # expected WAR of the first listed grade
    growth: list[float | None]              # per tenure, None when no outlet observed it
    shares: list[tuple[str, float]]         # (org, share), largest first, sums to 1
    tool_growth: dict[str, dict[str, float]] = field(default_factory=dict)  # org -> tool -> WAR-scale growth

    def share_of(self, org: str) -> float:
        return next((s for o, s in self.shares if o == org), 0.0)

    def as_payload(self) -> dict:
        return {"shares": [[o, s] for o, s in self.shares],
                "signing_org": self.signing_org,
                "basis": self.basis,
                "tenures": [t.as_list() for t in self.tenures]}


# --------------------------------------------------------------------------
# 1. Org calendar
# --------------------------------------------------------------------------

def org_events(txs: Iterable[dict], resolve: Callable[[dict], str | None]) -> list[tuple[str, str | None]]:
    """Dated club changes from one player's raw transactions, oldest first.

    resolve(tx) returns the receiving club code for a join, or None when the
    receiving team is not an affiliated club."""
    out: list[tuple[str, str | None]] = []
    for tx in sorted((t for t in (txs or []) if isinstance(t, dict)),
                     key=lambda t: (t.get("date") or "", t.get("id") or 0)):
        code = (tx.get("type_code") or "").upper()
        d = (tx.get("date") or "")[:10]
        if not d:
            continue
        if code in ORG_JOIN_TYPES:
            org = resolve(tx)
            if org:
                out.append((d, org))
            elif code in UNAFFILIATED_JOIN_TYPES and (tx.get("to_team_name") or tx.get("to_team_id")):
                out.append((d, None))
        elif code in ORG_LEAVE_TYPES:
            out.append((d, None))
    return out


def tenures_from_events(events: list[tuple[str, str | None]], start: str | None, end: str) -> list[Tenure]:
    """Runs of one club between dated events, clipped to [start, end).

    Before the first event the player is placed with the first affiliated club
    the events name (a list can publish him before the signing posts). Returns
    [] when the events name no affiliated club at all."""
    lead = next((i for i, (_, o) in enumerate(events) if o), None)
    if lead is None:
        return []
    events = events[lead:]                  # amateur-side releases before the first club do not count
    first_org = events[0][1]
    begin = min([events[0][0]] + ([start] if start else []))
    runs: list[list] = [[first_org, begin]]
    for d, org in events:
        if d >= end:
            break
        if d <= runs[-1][1]:
            # same-day or earlier event: the latest state on that day wins
            if org != runs[-1][0]:
                if len(runs) > 1 and runs[-2][0] == org:
                    runs.pop()
                else:
                    runs[-1][0] = org
            continue
        if org != runs[-1][0]:
            runs.append([org, d])
    out = []
    for i, (org, s) in enumerate(runs):
        e = runs[i + 1][1] if i + 1 < len(runs) else end
        if s < e:
            out.append(Tenure(org, s, e))
    return out


def tenures_from_trades(trades: list[dict], start_org: str | None, start: str, end: str) -> list[Tenure]:
    """The farm history's documented fallback: the pre-trade club, then each
    trade's receiving club from the trade date. trades rows carry date/from/to."""
    rows = sorted((t for t in trades if t.get("date") and t.get("to")), key=lambda t: t["date"])
    org = rows[0]["from"] if rows else start_org
    if not org:
        return []
    events = [(start, org)] + [(t["date"], t["to"]) for t in rows]
    return tenures_from_events(events, start, end)


def org_on(tenures: list[Tenure], d: str) -> str | None:
    for t in tenures:
        if t.start <= d < t.end:
            return t.org
    if tenures and d >= tenures[-1].end:
        return tenures[-1].org
    return tenures[0].org if tenures else None


def split_pair(a: str, b: str, tenures: list[Tenure]) -> list[tuple[int, float]]:
    """Fractions of the interval (a, b] that fall in each tenure, by days.

    A pair inside one tenure returns [(i, 1.0)]. A same-day pair or one outside
    the calendar returns the tenure that holds b with weight 1."""
    span = _days(a, b)
    if span <= 0 or not tenures:
        return [(_index_on(tenures, b), 1.0)] if tenures else []
    out = []
    for i, t in enumerate(tenures):
        lo = max(a, t.start)
        hi = min(b, t.end)
        n = _days(lo, hi)
        if n > 0:
            out.append((i, n / span))
    if not out:
        return [(_index_on(tenures, b), 1.0)]
    tot = sum(f for _, f in out)
    return [(i, f / tot) for i, f in out]


def _index_on(tenures: list[Tenure], d: str) -> int:
    for i, t in enumerate(tenures):
        if t.start <= d < t.end:
            return i
    return len(tenures) - 1 if tenures and d >= tenures[-1].end else 0


# --------------------------------------------------------------------------
# 2. Tenure growth and 3. shares
# --------------------------------------------------------------------------

def _value_fn_default():
    from storage import _fv_to_expected_war
    return _fv_to_expected_war


def same_source_pairs(obs_by_source: dict[str, list[tuple]]) -> Iterable[tuple]:
    """(source, (date_a, fv_a, tools_a), (date_b, fv_b, tools_b)) for every
    consecutive pair of one outlet's lists on one player."""
    for src, obs in obs_by_source.items():
        for x, y in zip(obs, obs[1:]):
            yield src, x, y


def tenure_growth(obs_by_source: dict[str, list[tuple]], tenures: list[Tenure],
                  value_fn: Callable, tool_since: str | None = None
                  ) -> tuple[list[float | None], dict[int, dict[str, float]]]:
    """Per-tenure grade growth (expected-WAR scale), mean over the outlets that
    observed each tenure, plus per-tenure per-tool growth on the same scale.
    Tool pairs starting before `tool_since` are left out (ToolDvM+ keeps its
    trailing window)."""
    n = len(tenures)
    g_src: dict[str, list[float]] = {}
    seen_src: dict[str, list[bool]] = {}
    tool_src: dict[str, dict[int, dict[str, float]]] = {}
    tool_seen: dict[str, dict[int, set]] = {}
    for src, (da, fa, ta), (db, fb, tb) in same_source_pairs(obs_by_source):
        parts = split_pair(da, db, tenures)
        va, vb = value_fn(fa), value_fn(fb)
        g = g_src.setdefault(src, [0.0] * n)
        s = seen_src.setdefault(src, [False] * n)
        for i, f in parts:
            s[i] = True
            if va is not None and vb is not None:
                g[i] += (vb - va) * f
        if ta and tb and (tool_since is None or da >= tool_since):
            ts_ = tool_src.setdefault(src, defaultdict(dict))
            tseen = tool_seen.setdefault(src, defaultdict(set))
            for k, x in ta.items():
                y = tb.get(k)
                if y is None:
                    continue
                wx, wy = value_fn(x), value_fn(y)
                if wx is None or wy is None:
                    continue
                for i, f in parts:
                    ts_[i][k] = ts_[i].get(k, 0.0) + (wy - wx) * f
                    tseen[i].add(k)
    growth: list[float | None] = []
    for i in range(n):
        vals = [g_src[s][i] for s in g_src if seen_src[s][i]]
        growth.append(sum(vals) / len(vals) if vals else None)
    tools: dict[int, dict[str, float]] = {}
    for i in range(n):
        acc: dict[str, list[float]] = defaultdict(list)
        for src, by_t in tool_src.items():
            for k in tool_seen[src].get(i, ()):
                acc[k].append(by_t[i].get(k, 0.0))
        if acc:
            tools[i] = {k: sum(v) / len(v) for k, v in acc.items()}
    return growth, tools


def development_shares(v0: float | None, tenures: list[Tenure], growth: list[float | None],
                       signing_org: str | None) -> list[tuple[str, float]]:
    """Acquisition value to the signing club, each club's positive tenure growth
    to that club; shares normalised to sum to one (4 decimals, largest first)."""
    credit: dict[str, float] = defaultdict(float)
    sign = signing_org or next((t.org for t in tenures if t.org), None)
    if sign and v0 and v0 > 0:
        credit[sign] += v0
    for t, g in zip(tenures, growth):
        if t.org and g is not None and g > 0:
            credit[t.org] += g
    total = sum(credit.values())
    if total <= 0:
        return [(sign, 1.0)] if sign else []
    raw = sorted(((o, c / total) for o, c in credit.items() if c > 0), key=lambda kv: (-kv[1], kv[0]))
    shares = [(o, round(s, 4)) for o, s in raw]
    shares = [(o, s) for o, s in shares if s > 0]
    drift = round(1.0 - sum(s for _, s in shares), 4)
    if shares and drift:
        o, s = shares[0]
        shares[0] = (o, round(s + drift, 4))
    return shares


# --------------------------------------------------------------------------
# Loading and the whole-league build
# --------------------------------------------------------------------------

def _mlb30() -> set[str]:
    from storage import MLB_30_ORGS
    return set(MLB_30_ORGS)


def _canon(o):
    if not o:
        return None
    from trades import canonical_org
    c = canonical_org(o)
    return c if c in _mlb30() else None


def load_team_org_map(con) -> dict[tuple[int, int], str]:
    """(team_id, season) -> club code from staff_units; MLB clubs keyed for
    every season they appear. {} when the table is absent."""
    out: dict[tuple[int, int], str] = {}
    try:
        rows = con.execute("SELECT team_id, season, org_code FROM staff_units "
                           "WHERE team_id IS NOT NULL AND org_code IS NOT NULL").fetchall()
    except sqlite3.OperationalError:
        return out
    for tid, season, org in rows:
        c = _canon(org)
        if c:
            out[(int(tid), int(season))] = c
    return out


def make_resolver(team_org: dict[tuple[int, int], str]) -> Callable[[dict], str | None]:
    by_team: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for (tid, season), org in team_org.items():
        by_team[tid].append((season, org))
    for tid in by_team:
        by_team[tid].sort()

    def resolve(tx: dict) -> str | None:
        tid = tx.get("to_team_id")
        d = (tx.get("date") or "")[:4]
        if tid is not None and d.isdigit():
            seasons = by_team.get(int(tid))
            if seasons:
                yr = int(d)
                exact = next((o for s, o in seasons if s == yr), None)
                if exact:
                    return exact
                orgs = {o for _, o in seasons}
                if len(orgs) == 1:          # an MLB club, or an affiliate that never moved
                    return next(iter(orgs))
                # nearest season at or before the date, else the first after it
                before = [o for s, o in seasons if s <= yr]
                return before[-1] if before else seasons[0][1]
        return _canon(tx.get("to_team_name"))
    return resolve


def load_observations(con, keys: set[str] | None = None) -> dict[str, dict[str, list[tuple]]]:
    """player_key -> source -> [(date, fv, tools)] for the growth outlets,
    one row per (source, date), oldest first."""
    q = ("SELECT player_key, source, snapshot_date, fv, tools_json FROM snapshots "
         "WHERE status = 'active' AND fv IS NOT NULL AND source IN (%s) "
         "ORDER BY player_key, source, snapshot_date, id" % ",".join("?" * len(GROWTH_SOURCES)))
    out: dict[str, dict[str, dict[str, tuple]]] = defaultdict(lambda: defaultdict(dict))
    for key, src, d, fv, tj in con.execute(q, GROWTH_SOURCES):
        if keys is not None and key not in keys:
            continue
        tools = None
        if tj:
            try:
                tools = {k: float(v) for k, v in json.loads(tj).items()
                         if k in TOOL_KEYS and isinstance(v, (int, float)) and 20 <= v <= 80}
            except (ValueError, TypeError, AttributeError):
                tools = None
        if tools:
            consolidate_pwr(tools)
        out[key][src][d[:10]] = (d[:10], float(fv), tools or None)
    return {k: {s: [by_d[d] for d in sorted(by_d)] for s, by_d in srcs.items()} for k, srcs in out.items()}


def load_transactions(con, keys: set[str] | None = None) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    try:
        rows = con.execute("SELECT player_key, payload_json FROM player_transactions").fetchall()
    except sqlite3.OperationalError:
        return out
    for key, pj in rows:
        if keys is not None and key not in keys:
            continue
        try:
            p = json.loads(pj)
        except (TypeError, ValueError):
            continue
        if isinstance(p, list):
            out[key] = p
    return out


@dataclass
class PlayerInfo:
    player_key: str
    current_org: str | None = None
    status: str = "active"                  # active | debuted | inactive
    debut_date: str | None = None
    listed_org: str | None = None           # last point-in-time org before the debut


class Attribution:
    """Per-player tenures and shares for a set of players."""

    def __init__(self, players: dict[str, PlayerAttribution], diagnostics: dict):
        self.players = players
        self.diagnostics = diagnostics

    def get(self, key: str) -> PlayerAttribution | None:
        return self.players.get(key)

    def graduate_credit(self, key: str, fallback_org: str | None) -> list[tuple[str, float, bool]]:
        """[(org, share, is_signing_club)] for one graduate; the fallback club
        takes the whole share when the player has no attribution."""
        pa = self.players.get(key)
        if pa is None or not pa.shares:
            return [(fallback_org, 1.0, True)] if fallback_org else []
        return [(o, s, o == pa.signing_org) for o, s in pa.shares]

    def calendar(self, key: str) -> list[Tenure]:
        pa = self.players.get(key)
        return pa.tenures if pa else []


def attribute_player(key: str, info: PlayerInfo, obs: dict[str, list[tuple]], txs: list[dict] | None,
                     trades: list[dict], signing_hint: str | None, resolve: Callable,
                     value_fn: Callable, today: str, tool_since: str | None = None) -> PlayerAttribution:
    end = (info.debut_date or today)[:10] if info.status == "debuted" and info.debut_date else today
    obs = {s: [o for o in rows if o[0] <= end] for s, rows in obs.items()}
    obs = {s: rows for s, rows in obs.items() if rows}
    first_obs = min((rows[0][0] for rows in obs.values()), default=None)
    start = min([d for d in (first_obs,) if d] or [end])
    tenures: list[Tenure] = []
    basis = ""
    if txs:
        events = org_events(txs, resolve)
        tenures = tenures_from_events(events, start, end) if events else []
        if tenures and info.status == "active" and info.current_org and tenures[-1].org != info.current_org:
            tenures = []                    # the payload misses his latest move: use the fallback
        basis = "transactions" if tenures else ""
    if not tenures and trades:
        tenures = tenures_from_trades(trades, info.listed_org or info.current_org, start, end)
        basis = "trades" if tenures else ""
    if not tenures:
        org = (info.listed_org if info.status == "debuted" else None) or info.current_org or info.listed_org
        if org and start < end:
            tenures = [Tenure(org, start, end)]
            basis = "listed_org" if org == info.listed_org and info.status == "debuted" else "current_org"
    v0 = None
    if first_obs:
        vals = [value_fn(rows[0][1]) for rows in obs.values() if rows[0][0] == first_obs]
        vals = [v for v in vals if v is not None]
        v0 = sum(vals) / len(vals) if vals else None
    growth, tools = tenure_growth(obs, tenures, value_fn, tool_since) if tenures else ([], {})
    first_club = next((t.org for t in tenures if t.org), None)
    if basis == "transactions":
        # the dated signing names the club; an acquisitions row can carry an
        # unsigned earlier draft pick (a 28th-rounder who went to college)
        signing = first_club
    else:
        signing = signing_hint or first_club or info.listed_org or info.current_org
    shares = development_shares(v0, tenures, growth, signing)
    tool_by_org: dict[str, dict[str, float]] = defaultdict(dict)
    for i, by_tool in tools.items():
        org = tenures[i].org
        if not org:
            continue
        for k, v in by_tool.items():
            tool_by_org[org][k] = tool_by_org[org].get(k, 0.0) + v
    return PlayerAttribution(key, tenures, basis or "none", signing, v0, growth, shares, dict(tool_by_org))


def build(infos: Iterable[PlayerInfo], *, trades_by_player: dict | None = None,
          acquisitions: dict | None = None, con=None, today: str | None = None,
          value_fn: Callable | None = None, observations: dict | None = None,
          transactions: dict | None = None, team_org: dict | None = None,
          tool_since: str | None = None) -> Attribution:
    """Attribute every player in `infos`. Database reads (observations,
    transactions, staff_units) come from `con` unless passed in directly."""
    value_fn = value_fn or _value_fn_default()
    today = (today or date.today().isoformat())[:10]
    infos = {i.player_key: PlayerInfo(i.player_key, _canon(i.current_org), i.status, i.debut_date,
                                      _canon(i.listed_org))
             for i in infos if i.player_key}
    keys = set(infos)
    if con is not None:
        if observations is None:
            observations = load_observations(con, keys)
        if transactions is None:
            transactions = load_transactions(con, keys)
        if team_org is None:
            team_org = load_team_org_map(con)
    observations = observations or {}
    transactions = transactions or {}
    resolve = make_resolver(team_org or {})
    out: dict[str, PlayerAttribution] = {}
    basis_n: dict[str, int] = defaultdict(int)
    multi = 0
    for key, info in infos.items():
        trades = []
        for t in (trades_by_player or {}).get(key) or []:
            d, f, to = t.get("trade_date") or t.get("date"), _canon(t.get("from_org")), _canon(t.get("to_org"))
            if d and f and to:
                trades.append({"date": d[:10], "from": f, "to": to})
        acq = (acquisitions or {}).get(key) or {}
        hint = _canon(acq.get("team_name")) if acq.get("method") in ("draft", "international_fa") else None
        pa = attribute_player(key, info, observations.get(key) or {}, transactions.get(key),
                              trades, hint, resolve, value_fn, today, tool_since)
        out[key] = pa
        basis_n[pa.basis] += 1
        if len(pa.shares) > 1:
            multi += 1
    diag = {"n_players": len(out), "basis": dict(sorted(basis_n.items())), "n_multi_club": multi}
    log.info("dev_attribution: %s", diag)
    return Attribution(out, diag)
