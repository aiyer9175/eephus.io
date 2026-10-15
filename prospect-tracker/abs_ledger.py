# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The ABS challenge ledger: one row per player challenge of a ball or strike call.

Registered in docs/eabs-2026-10-15/ABS_LEDGER.md before this file existed. Pure
readers over one StatsAPI game feed (`/api/v1.1/game/{pk}/feed/live`); the run
over the cache is tools/build_abs_ledger.py.

A row is a review of type MJ (the ABS zone challenge) or MZ (the minor-league
check-swing challenge, its own kind, never mixed into the zone kind). A review on
a pitch event is that pitch; a review on the play, or in the play's
additionalReviews, belongs to the play's last pitch, the case where the ruling
ended the plate appearance. Manager replay challenges and crew-chief reviews are
not rows.

The challenger's role is read at the moment of the pitch: the batter, else the
fielding side's pitcher, else its catcher, by a defense walk that starts from the
boxscore starters and seats every substitution in event order; else
`unresolved`. The ledger values nothing: no run value, no win value, no rating.

The invariant: per feed, per club, overturned rows equal
`gameData.absChallenges.<side>.usedSuccessful` and upheld rows equal
`usedFailed`. `check_feed` reports it; the builder refuses the MLB ledger on one
mismatch."""
from __future__ import annotations

ZONE = "MJ"
CHECK_SWING = "MZ"
KINDS = {ZONE: "zone", CHECK_SWING: "check_swing"}
#: The call pair each kind can turn over: the final call's inverse is the
#: original call when the challenge succeeded.
INVERSE = {"zone": {"B": "C", "C": "B"}, "check_swing": {"B": "S", "S": "B"}}

FIELDS = (
    "game_pk", "season", "level", "game_type", "official_date", "inning", "half",
    "at_bat_index", "event_index", "pitch_number", "source", "kind", "review_type",
    "challenge_team_id", "challenge_org", "challenger_id", "role", "challenge_side",
    "role_by_side", "batter_id",
    "pitcher_id", "catcher_id", "overturned", "final_call", "original_call",
    "balls_before", "strikes_before", "outs_before", "bases_before",
    "bat_score_before", "fld_score_before", "count_after_final",
    "count_after_original", "li_pa", "px", "pz", "sz_top", "sz_bot", "flags",
)
BASES = ("1B", "2B", "3B")


def _int(x, default=None):
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def _r3(x):
    """Feet to three decimals (a hundredth of an inch is below the tracking's
    resolution); None stays None."""
    try:
        return round(float(x), 3)
    except (TypeError, ValueError):
        return None


def _pid(obj):
    return _int((obj or {}).get("id")) if isinstance(obj, dict) else None


def _plays(feed: dict) -> list:
    plays = (((feed or {}).get("liveData") or {}).get("plays") or {}).get("allPlays") or []
    return sorted((p for p in plays if isinstance(p, dict)),
                  key=lambda p: _int(p.get("atBatIndex"), 0))


def _half(p: dict) -> str:
    about = p.get("about") or {}
    h = about.get("halfInning")
    if h:
        return "bottom" if str(h).lower() == "bottom" else "top"
    return "top" if about.get("isTopInning", True) else "bottom"


def _reviews_of(rd) -> list:
    if not isinstance(rd, dict):
        return []
    return [rd] + [a for a in (rd.get("additionalReviews") or []) if isinstance(a, dict)]


def count_after(balls: int, strikes: int, call) -> str | None:
    """The count a call leaves (`b-s`), or `BB` / `K` when it ends the plate
    appearance; None for a call that is neither a ball nor a strike."""
    if call == "B":
        return "BB" if balls + 1 >= 4 else f"{balls + 1}-{strikes}"
    if call in ("C", "S"):
        return "K" if strikes + 1 >= 3 else f"{balls}-{strikes + 1}"
    return None


def original_call(kind: str, final, overturned: bool):
    """The call on the field: the final call when it stood, its inverse within
    the kind's pair when it was overturned (None outside the pair)."""
    if not overturned:
        return final
    return INVERSE.get(kind, {}).get(final)


def _side_map(feed: dict) -> dict:
    """MLBAM id -> 'away' / 'home' from the boxscore rosters."""
    out = {}
    teams = (((feed.get("liveData") or {}).get("boxscore") or {}).get("teams")) or {}
    for side in ("away", "home"):
        for key, pl in ((teams.get(side) or {}).get("players") or {}).items():
            pid = _pid((pl or {}).get("person")) or _int(str(key).replace("ID", ""))
            if pid is not None:
                out[pid] = side
    return out


def starting_defense(feed: dict) -> dict:
    """{side: {'1': starting pitcher, '2': starting catcher}} from the boxscore:
    the side's first `pitchers` entry, and the starter (`battingOrder` ending in
    00) whose first `allPositions` entry is catcher."""
    out = {"away": {}, "home": {}}
    teams = (((feed.get("liveData") or {}).get("boxscore") or {}).get("teams")) or {}
    for side in ("away", "home"):
        t = teams.get(side) or {}
        pitchers = t.get("pitchers") or []
        if pitchers:
            out[side]["1"] = _int(pitchers[0])
        for key, pl in (t.get("players") or {}).items():
            bo = str((pl or {}).get("battingOrder") or "")
            ap = (pl or {}).get("allPositions") or []
            if bo.endswith("00") and ap and str((ap[0] or {}).get("code")) == "2":
                out[side]["2"] = _pid(pl.get("person")) or _int(str(key).replace("ID", ""))
    return out


def _club_ids(feed: dict) -> dict:
    teams = (feed.get("gameData") or {}).get("teams") or {}
    return {side: (teams.get(side) or {}) for side in ("away", "home")}


def _org_code(team: dict, level) -> str | None:
    try:
        import trades
    except ImportError:  # pragma: no cover - the repo always has trades
        return None
    tid = team.get("parentOrgId") if _int(level) != 1 else team.get("id")
    return trades.canonical_org_from_id(tid) if tid is not None else None


def _bases_code(occ: set) -> str:
    return "".join(str(i + 1) if b in occ else "_" for i, b in enumerate(BASES))


def challenge_rows(feed: dict, li_by_ab: dict | None = None) -> tuple[list, dict]:
    """(rows, checks) for one feed. Rows are dicts keyed by FIELDS. `checks`
    counts the role and walk checks: `pa_checked`, `pitcher_walk_mismatch`
    (the walk's pitcher against matchup.pitcher on each plate appearance's
    last pitch), `side_role_mismatch`, `no_start_catcher`."""
    gd = feed.get("gameData") or {}
    game = gd.get("game") or {}
    level = _int(((_club_ids(feed)["home"]).get("sport") or {}).get("id"))
    clubs = _club_ids(feed)
    side_of_team = {_int(clubs[s].get("id")): s for s in ("away", "home")}
    sched = _int(((feed.get("liveData") or {}).get("linescore") or {}).get("scheduledInnings"), 9) or 9
    season = _int(game.get("season"))
    gtype = game.get("type") or "R"
    side_of = _side_map(feed)
    defense = starting_defense(feed)
    checks = {"pa_checked": 0, "pitcher_walk_mismatch": 0, "side_role_mismatch": 0,
              "no_start_catcher": int(not defense["away"].get("2")) + int(not defense["home"].get("2"))}
    li_by_ab = li_by_ab or {}
    rows = []
    prev = None
    for p in _plays(feed):
        about = p.get("about") or {}
        inning, half = _int(about.get("inning"), 0), _half(p)
        ab = _int(p.get("atBatIndex"), _int(about.get("atBatIndex")))
        fld = "home" if half == "top" else "away"
        bat = "away" if half == "top" else "home"
        # Plate appearance start state: the previous play's end within the half.
        if prev is not None and (_int((prev.get("about") or {}).get("inning"), 0), _half(prev)) == (inning, half):
            outs0 = _int((prev.get("count") or {}).get("outs"), 0)
            m = prev.get("matchup") or {}
            occ0 = {b for b, k in zip(BASES, ("postOnFirst", "postOnSecond", "postOnThird")) if m.get(k)}
        else:
            outs0 = 0
            occ0 = {"2B"} if (inning > sched and gtype == "R" and (season or 0) >= 2020) else set()
        if prev is not None:
            r = prev.get("result") or {}
            score0 = {"away": _int(r.get("awayScore"), 0), "home": _int(r.get("homeScore"), 0)}
        else:
            score0 = {"away": 0, "home": 0}
        runners = sorted(((_int((rn.get("details") or {}).get("playIndex"), 10 ** 6), i, rn)
                          for i, rn in enumerate(p.get("runners") or []) if isinstance(rn, dict)),
                         key=lambda t: (t[0], t[1]))
        events = [e for e in (p.get("playEvents") or []) if isinstance(e, dict)]
        batter = _pid((p.get("matchup") or {}).get("batter"))
        snap = {}
        last_pitch_pos = None

        def state_at(j: int, e: dict) -> dict:
            k = _int(e.get("index"), j)
            occ, runs = set(occ0), 0
            for pi, _i, rn in runners:
                if pi >= k:
                    break
                mv = rn.get("movement") or {}
                st, en = mv.get("start"), mv.get("end")
                if st in occ:
                    occ.discard(st)
                if en in BASES and not mv.get("isOut"):
                    occ.add(en)
                elif en == "score" and not mv.get("isOut"):
                    runs += 1
            pc = None
            for q in range(j - 1, -1, -1):
                if isinstance(events[q].get("count"), dict):
                    pc = events[q]["count"]
                    break
            balls = _int((pc or {}).get("balls"), 0) if pc else 0
            strikes = _int((pc or {}).get("strikes"), 0) if pc else 0
            outs = _int((pc or {}).get("outs"), outs0) if pc else outs0
            sc = dict(score0)
            sc[bat] += runs
            return {"balls": balls, "strikes": strikes, "outs": outs, "bases": _bases_code(occ),
                    "bat_score": sc[bat], "fld_score": sc[fld]}

        def make_row(j: int, e: dict, rd: dict, source: str, d_snap: dict) -> dict | None:
            rt = rd.get("reviewType")
            if rt not in KINDS:
                return None
            kind = KINDS[rt]
            flags = []
            details = e.get("details") or {}
            final = (details.get("call") or {}).get("code")
            over = bool(rd.get("isOverturned"))
            orig = original_call(kind, final, over)
            if final not in INVERSE[kind]:
                flags.append("call_suspect")
                if source != "event":
                    flags.append("attach_suspect")
            if rd.get("inProgress"):
                flags.append("in_progress")
            st = state_at(j, e)
            caf = count_after(st["balls"], st["strikes"], final)
            cao = count_after(st["balls"], st["strikes"], orig)
            ec = e.get("count") or {}
            if caf and caf not in ("BB", "K") and caf != f"{_int(ec.get('balls'), -1)}-{_int(ec.get('strikes'), -1)}":
                flags.append("count_mismatch")
            who = _pid(rd.get("player"))
            pitcher, catcher = d_snap[fld].get("1"), d_snap[fld].get("2")
            if who is not None and who == batter:
                role = "batter"
            elif who is not None and who == pitcher:
                role = "pitcher"
            elif who is not None and who == catcher:
                role = "catcher"
            else:
                role = "unresolved"
            tid = _int(rd.get("challengeTeamId"))
            cside = side_of_team.get(tid)
            if role == "batter" and cside != bat or role in ("pitcher", "catcher") and cside != fld:
                flags.append("side_role_mismatch")
                checks["side_role_mismatch"] += 1
            side_word = "batting" if cside == bat else "fielding" if cside == fld else None
            pd = e.get("pitchData") or {}
            co = pd.get("coordinates") or {}
            return {
                "game_pk": _int(feed.get("gamePk")) or _int(game.get("pk")), "season": season,
                "level": level, "game_type": gtype,
                "official_date": (gd.get("datetime") or {}).get("officialDate"),
                "inning": inning, "half": half, "at_bat_index": ab,
                "event_index": _int(e.get("index"), j), "pitch_number": _int(e.get("pitchNumber")),
                "source": source, "kind": kind, "review_type": rt,
                "challenge_team_id": tid,
                "challenge_org": _org_code(clubs.get(cside) or {}, level) if cside else None,
                "challenger_id": who, "role": role, "challenge_side": side_word,
                "role_by_side": {"batting": "batter", "fielding": "pitcher_or_catcher"}.get(side_word),
                "batter_id": batter,
                "pitcher_id": pitcher, "catcher_id": catcher, "overturned": over,
                "final_call": final, "original_call": orig,
                "balls_before": st["balls"], "strikes_before": st["strikes"],
                "outs_before": st["outs"], "bases_before": st["bases"],
                "bat_score_before": st["bat_score"], "fld_score_before": st["fld_score"],
                "count_after_final": caf, "count_after_original": cao,
                "li_pa": li_by_ab.get(ab),
                "px": _r3(co.get("pX")), "pz": _r3(co.get("pZ")),
                "sz_top": _r3(pd.get("strikeZoneTop")), "sz_bot": _r3(pd.get("strikeZoneBottom")),
                "flags": ",".join(flags) or None,
            }

        for j, e in enumerate(events):
            if e.get("isSubstitution") and isinstance(e.get("position"), dict):
                code = str(e["position"].get("code") or "")
                who = _pid(e.get("player"))
                if code in {str(c) for c in range(1, 10)} and who is not None and who in side_of:
                    defense[side_of[who]][code] = who
            if e.get("isPitch"):
                last_pitch_pos = j
                snap = {s: dict(defense[s]) for s in ("away", "home")}
            for rd in _reviews_of(e.get("reviewDetails")):
                row = make_row(j, e, rd, "event", {s: dict(defense[s]) for s in ("away", "home")})
                if row:
                    rows.append(row)
        play_rd = _reviews_of(p.get("reviewDetails"))
        for n, rd in enumerate(play_rd):
            if rd.get("reviewType") not in KINDS:
                continue
            if last_pitch_pos is None:
                checks.setdefault("play_review_without_pitch", 0)
                checks["play_review_without_pitch"] += 1
                continue
            row = make_row(last_pitch_pos, events[last_pitch_pos], rd,
                           "play" if n == 0 else "play_additional", snap)
            if row:
                rows.append(row)
        if last_pitch_pos is not None and (about.get("isComplete", True)):
            checks["pa_checked"] += 1
            mp = _pid((p.get("matchup") or {}).get("pitcher"))
            if mp is not None and snap.get(fld, {}).get("1") != mp:
                checks["pitcher_walk_mismatch"] += 1
                # Re-seat the matchup's pitcher so one missed substitution does
                # not carry into every later plate appearance.
                defense[fld]["1"] = mp
        prev = p
    return rows, checks


def check_feed(feed: dict, rows: list, kinds=None) -> dict:
    """The invariant for one feed: per side, rows overturned against
    usedSuccessful and rows upheld against usedFailed (over the rows whose kind
    is in `kinds`, default every kind). Returns
    `{ok, has_challenges, sides: {side: {won, lost, feed_won, feed_lost}}}`."""
    if kinds is not None:
        rows = [r for r in rows if r["kind"] in kinds]
    gd = feed.get("gameData") or {}
    absc = gd.get("absChallenges") or {}
    clubs = _club_ids(feed)
    out = {"ok": True, "has_challenges": bool(absc.get("hasChallenges")), "sides": {}}
    for side in ("away", "home"):
        tid = _int(clubs[side].get("id"))
        mine = [r for r in rows if r["challenge_team_id"] == tid]
        won = sum(1 for r in mine if r["overturned"])
        lost = len(mine) - won
        b = absc.get(side) or {}
        fw, fl = _int(b.get("usedSuccessful"), 0), _int(b.get("usedFailed"), 0)
        out["sides"][side] = {"won": won, "lost": lost, "feed_won": fw, "feed_lost": fl}
        if (won, lost) != (fw, fl):
            out["ok"] = False
    stray = [r for r in rows if r["challenge_team_id"] not in {_int(clubs[s].get("id")) for s in ("away", "home")}]
    if stray:
        out["ok"] = False
        out["stray_team_rows"] = len(stray)
    return out


def columnar(rows: list) -> dict:
    """{fields, rows} with each row a list in FIELDS order."""
    return {"fields": list(FIELDS), "rows": [[r.get(f) for f in FIELDS] for r in rows]}
