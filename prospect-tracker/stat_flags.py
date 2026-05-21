"""
Scouting flags — green / red rate-stat indicators per prospect.

For each tracked statistic on a prospect's current statline we compare the
value to (a) an absolute "projectable to MLB" threshold and (b) the
empirical average at the prospect's current level (`level_norms[level]`).
A flag fires when BOTH conditions agree — the stat is meaningfully above
or below average AND past an absolute threshold that survives a wonky
level-norm sample. The dual gate keeps us honest: a 5.5% BB% at a level
whose average is also 5.5% isn't a "good" walk rate, it's just typical of
a level where nobody walks much; we shouldn't paint that green.

Returned shape (list of dicts), tuned for direct rendering on the
prospect-detail page:

    [
      {
        "stat":          "ISO",
        "direction":     "green" | "red",
        "value":         0.180,           # raw numeric value
        "value_display": ".180",          # pre-formatted string
        "level":         "AA",
        "level_avg":     0.140,
        "delta":         0.040,
        "delta_display": "+.040",
        "category":      "power" | "discipline" | "contact" | "command" | "results",
        "note":          "Above-average power for level"
      },
      ...
    ]

Categories let the UI group flags meaningfully (e.g. "Power" badges sit
next to "Discipline" badges rather than mixing with "Command" badges from
the pitching side).

The thresholds are intentionally conservative — we'd rather flag fewer
prospects clearly than mark every above-median statistic as a "green
flag" and dilute the signal.
"""

from __future__ import annotations

from dataclasses import dataclass


# Minimum playing time before flags are computed. Below this we'd be
# reading noise — a 3-game hitter with one home run isn't a "power green
# flag", they're a small-sample artifact.
MIN_GAMES_HITTER = 15
MIN_IP_PITCHER   = 15.0


@dataclass(frozen=True)
class _HitterRule:
    stat: str
    category: str
    # Which keys to read on the statline and the level-norm perf block.
    statline_key: str
    norm_key: str
    # Format helpers — value formatting differs between rate (".180") and
    # percentage stats ("10.9%").
    fmt_value: str        # "rate3" | "pct" | "ops"
    # "above_good" = higher = better (ISO, OPS, BB%);
    # "below_good" = lower = better (K%).
    polarity: str
    # Green/red thresholds. Each is a (delta_vs_avg, absolute_floor) tuple
    # where BOTH conditions must clear for the flag to fire (the AND keeps
    # noisy level-norm samples from over-flagging).
    green_delta: float
    green_absolute: float
    red_delta: float
    red_absolute: float
    # Tooltip copy.
    green_note: str
    red_note: str


@dataclass(frozen=True)
class _PitcherRule:
    stat: str
    category: str
    statline_key: str
    norm_key: str
    fmt_value: str        # "rate2" | "era" | "whip"
    polarity: str         # below_good for ERA/WHIP/BB9/HR9; above_good for K9
    green_delta: float
    green_absolute: float
    red_delta: float
    red_absolute: float
    green_note: str
    red_note: str


# Hitter rules. Tuned against MiLB league averages: a +0.045 ISO over
# level is roughly the gap between a 50 FV power profile and a 55 FV one;
# a 12% BB rate is the rough threshold scouts use to flag "advanced
# approach"; a sub-18% K rate is the line where contact ceases to be a
# concern at the MLB level.
HITTER_RULES: tuple[_HitterRule, ...] = (
    _HitterRule(
        stat="ISO", category="power",
        statline_key="iso", norm_key="avg_iso",
        fmt_value="rate3", polarity="above_good",
        green_delta=0.045, green_absolute=0.180,
        red_delta=-0.035,  red_absolute=0.090,
        green_note="Above-average power for level — projects MLB raw power.",
        red_note="Limited power output — raises bat-only profile risk.",
    ),
    _HitterRule(
        stat="BB%", category="discipline",
        statline_key="bb_pct", norm_key="avg_bb_pct",
        fmt_value="pct", polarity="above_good",
        green_delta=2.0,  green_absolute=11.0,
        red_delta=-2.0,   red_absolute=5.0,
        green_note="Patient approach — strong walk rate projects to MLB.",
        red_note="Aggressive zone control — sub-MLB walk rate at this level.",
    ),
    _HitterRule(
        stat="K%", category="contact",
        statline_key="k_pct", norm_key="avg_k_pct",
        fmt_value="pct", polarity="below_good",
        green_delta=-4.0, green_absolute=17.0,
        red_delta=4.0,    red_absolute=28.0,
        green_note="Strong contact rate — projects MLB-survivable swing-and-miss.",
        red_note="Concerning whiff profile — questions on whether contact translates.",
    ),
    _HitterRule(
        stat="OPS", category="results",
        statline_key="ops", norm_key="avg_ops",
        fmt_value="ops", polarity="above_good",
        green_delta=0.110, green_absolute=0.820,
        red_delta=-0.090,  red_absolute=0.620,
        green_note="Producing well above the level-average bat.",
        red_note="Under-performing the level baseline at the plate.",
    ),
)


# Pitcher rules. Calibrated against current MiLB averages — modern stuff
# pushes K/9 norms above 9 at upper levels, so we want >10.5 to genuinely
# project; HR/9 ≥ 1.5 is the rough "fly-ball-prone arm with command
# concerns" zone the user called out explicitly.
PITCHER_RULES: tuple[_PitcherRule, ...] = (
    _PitcherRule(
        stat="K/9", category="strikeouts",
        statline_key="k_per_9", norm_key="avg_k_per_9",
        fmt_value="rate2", polarity="above_good",
        green_delta=1.5, green_absolute=10.5,
        red_delta=-1.5,  red_absolute=7.0,
        green_note="Plus swing-and-miss for level — projects MLB strikeouts.",
        red_note="Below-average miss rate — relies on contact management.",
    ),
    _PitcherRule(
        stat="BB/9", category="command",
        statline_key="bb_per_9", norm_key="avg_bb_per_9",
        fmt_value="rate2", polarity="below_good",
        green_delta=-1.0, green_absolute=2.2,
        red_delta=1.0,    red_absolute=4.5,
        green_note="Plus command — walk rate translates cleanly upward.",
        red_note="Walks raise floor concerns — command needs to tighten.",
    ),
    _PitcherRule(
        # "longball" — HR/9 is a contact-quality stat from the pitcher's
        # side (how often opponents square it up), not contact ability
        # in the hitter sense. Keeping it on its own category keeps the
        # flag list sortable into a coherent pitcher tool order:
        # strikeouts → command → longball → run-prevention results.
        stat="HR/9", category="longball",
        statline_key="hr_per_9", norm_key="avg_hr_per_9",
        fmt_value="rate2", polarity="below_good",
        green_delta=-0.30, green_absolute=0.70,
        red_delta=0.40,    red_absolute=1.50,
        green_note="Keeps the ball in the park — durable shape against MLB hitters.",
        red_note="HR-prone profile — habitually punished at the level, harder at MLB.",
    ),
    _PitcherRule(
        stat="WHIP", category="results",
        statline_key="whip", norm_key="avg_whip",
        fmt_value="whip", polarity="below_good",
        green_delta=-0.12, green_absolute=1.10,
        red_delta=0.15,    red_absolute=1.45,
        green_note="Suppresses baserunners — fewer crooked innings at MLB.",
        red_note="Traffic constantly — concerning baserunner suppression.",
    ),
    _PitcherRule(
        stat="ERA", category="results",
        statline_key="era", norm_key="avg_era",
        fmt_value="era", polarity="below_good",
        green_delta=-0.60, green_absolute=3.00,
        red_delta=0.60,    red_absolute=4.80,
        green_note="Well under the level-average ERA.",
        red_note="Run-prevention trailing the level baseline.",
    ),
)


def _to_float(v) -> float | None:
    """Pull a usable float out of statline / norm fields. Statline rate
    stats arrive as strings ('.180', '3.50'); norms arrive as floats."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s == "—":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fmt_value(val: float, fmt: str) -> str:
    if fmt == "rate3":
        # Drop the leading 0 on rate stats (".180" not "0.180") — same
        # convention as the rest of the slash-line display.
        return f"{val:.3f}".lstrip("0") if val >= 0 else "-" + f"{abs(val):.3f}".lstrip("0")
    if fmt == "rate2":
        return f"{val:.2f}"
    if fmt == "era":
        return f"{val:.2f}"
    if fmt == "whip":
        return f"{val:.2f}"
    if fmt == "ops":
        return f"{val:.3f}".lstrip("0") if val >= 0 else "-" + f"{abs(val):.3f}".lstrip("0")
    if fmt == "pct":
        return f"{val:.1f}%"
    return f"{val:.2f}"


def _fmt_delta(delta: float, fmt: str) -> str:
    sign = "+" if delta > 0 else ""  # negative numbers already carry their sign
    if fmt in ("rate3", "ops"):
        s = f"{abs(delta):.3f}".lstrip("0") or "0"
        return f"{sign}{'-' if delta < 0 else ''}{s}"
    if fmt in ("rate2", "era", "whip"):
        return f"{sign}{delta:.2f}"
    if fmt == "pct":
        return f"{sign}{delta:.1f}pp"
    return f"{sign}{delta:.2f}"


def _eval_rule(rule, value: float, level_avg: float | None):
    """Return ('green' | 'red' | None) for this rule against the player's
    value. Both the delta-vs-level and the absolute threshold must agree
    so we don't paint a player green just because the level baseline at
    DSL happens to be very low."""
    if rule.polarity == "above_good":
        if level_avg is not None and value >= level_avg + rule.green_delta and value >= rule.green_absolute:
            return "green"
        if value >= rule.green_absolute and level_avg is None:
            return "green"
        if level_avg is not None and value <= level_avg + rule.red_delta and value <= rule.red_absolute:
            return "red"
        if value <= rule.red_absolute and level_avg is None:
            return "red"
        return None
    # below_good
    if level_avg is not None and value <= level_avg + rule.green_delta and value <= rule.green_absolute:
        return "green"
    if value <= rule.green_absolute and level_avg is None:
        return "green"
    if level_avg is not None and value >= level_avg + rule.red_delta and value >= rule.red_absolute:
        return "red"
    if value >= rule.red_absolute and level_avg is None:
        return "red"
    return None


def compute_stat_flags(statline: dict | None,
                       level_norms: dict | None,
                       health: dict | None = None) -> list[dict]:
    """Build the prospect-page scouting-flags payload.

    `statline` is the per-player current-season statline (already a dict
    of the same shape `stats.statline_to_dict` produces). `level_norms`
    is the full `{level: {age, perf}}` blob compute_level_norms returns.
    `health` is the optional `health_profile` dict produced by storage —
    when present and indicating chronic-injury risk, we tack an
    "Injury-prone" red flag onto the result. Health flags are emitted
    even when the statline gates filter the per-stat rules out, because
    health doesn't depend on having enough recent playing time."""
    out: list[dict] = []

    # Health flag is the only signal that can fire WITHOUT a usable
    # statline — a player with no current season stats can still have
    # an injury pattern. So evaluate it up front.
    if health:
        stints = int(health.get("il_stints_12mo") or 0)
        days   = int(health.get("il_days_12mo") or 0)
        # Two ways to fire the chronic-injury flag:
        #   * 3+ separate IL placements in 12 months (recurring issues), OR
        #   * 200+ cumulative IL days (one major absence is enough).
        if stints >= 3 or days >= 200:
            out.append({
                "stat":          "Health",
                "direction":     "red",
                # Pack the count + days into the value display so the
                # row tells the story without a separate tooltip.
                "value":         stints,
                "value_display": f"{stints} IL stint{'s' if stints != 1 else ''} · {days}d",
                "level":         None,
                "level_avg":     None,
                "delta":         0,
                "delta_display": None,
                "category":      "health",
                "polarity":      "below_good",
                "note":          "Frequent / extended IL time over the last 12 months — durability risk.",
            })

    if not statline:
        return out
    level = statline.get("level")
    if not level:
        return out
    norm_perf = ((level_norms or {}).get(level) or {}).get("perf") or {}
    is_pitcher = bool(statline.get("is_pitcher"))

    # Sample-size gates — below these we don't have enough on the season
    # for any flag to be meaningful. Lets us skip everything for a player
    # who's logged a single inning or PA.
    if is_pitcher:
        ip = _to_float(statline.get("ip"))
        if ip is None or ip < MIN_IP_PITCHER:
            return out
        rules = PITCHER_RULES
    else:
        games = statline.get("games") or 0
        if games < MIN_GAMES_HITTER:
            return out
        rules = HITTER_RULES

    for rule in rules:
        value = _to_float(statline.get(rule.statline_key))
        if value is None:
            continue
        level_avg = _to_float(norm_perf.get(rule.norm_key))
        direction = _eval_rule(rule, value, level_avg)
        if direction is None:
            continue
        delta = value - level_avg if level_avg is not None else 0.0
        out.append({
            "stat":          rule.stat,
            "direction":     direction,
            "value":         round(value, 3),
            "value_display": _fmt_value(value, rule.fmt_value),
            "level":         level,
            "level_avg":     round(level_avg, 3) if level_avg is not None else None,
            "delta":         round(delta, 3),
            "delta_display": _fmt_delta(delta, rule.fmt_value) if level_avg is not None else None,
            "category":      rule.category,
            "polarity":      rule.polarity,
            "note":          rule.green_note if direction == "green" else rule.red_note,
        })
    return out


# ---------------------------------------------------------------------------
# Tool-grade flags
#
# Scouting-grid analog of compute_stat_flags. Fires green/red callouts on
# raw per-tool grades and on the composite X+ indices. Same dict shape so
# the frontend renderer eats both arrays identically.
#
# Thresholds (per the spec, FanGraphs scouting primer):
#   green tool      : grade >= 60   ("plus")
#   carry-tool tag  : grade >= 65   (still green, but category="carry_tool"
#                     so the UI can paint a bolder pill)
#   red tool        : grade <= 35   (well below avg — actively a hole)
#   composite green : composite_*_plus >= 115
#   composite red   : composite_overall_plus <= 85
#
# Pitchers' grade names (FB / SL / CB / CH / Command) and hitters' grade
# names (Hit / Game Pwr / Raw Pwr / Speed / Field / Throw) come from the
# same canonical-key table the scrapers use.
# ---------------------------------------------------------------------------

_TOOL_LABELS_HITTER = {
    "hit": "Hit", "game_pwr": "Game power", "raw_pwr": "Raw power",
    "speed": "Speed", "field": "Field", "throw": "Throw",
}
_TOOL_LABELS_PITCHER = {
    "fb": "Fastball", "sl": "Slider", "cb": "Curveball",
    "ch": "Changeup", "cmd": "Command",
}
_TOOL_CATEGORY = {
    "hit": "contact", "game_pwr": "power", "raw_pwr": "power",
    "speed": "speed", "field": "defense", "throw": "arm",
    "fb": "stuff", "sl": "stuff", "cb": "stuff", "ch": "stuff",
    "cmd": "command",
}

TOOL_GREEN_GRADE = 60
TOOL_CARRY_GRADE = 65
TOOL_RED_GRADE   = 35
TOOL_PLUS_GREEN  = 115
TOOL_PLUS_RED    = 85


def compute_tool_flags(tools: dict | None, is_pitcher: bool) -> list[dict]:
    """Green/red flags driven by scouting tool grades.

    Returns a list of flag dicts in the same shape compute_stat_flags
    emits so the UI can concatenate the two and let one renderer handle
    both. `tools` is the dict built by storage._compute_tool_composites
    (carries `grades` + composite_* fields; X+ indices may be missing if
    this runs before the population-norm pass).
    """
    out: list[dict] = []
    if not tools:
        return out
    grades = tools.get("grades") or {}
    labels = _TOOL_LABELS_PITCHER if is_pitcher else _TOOL_LABELS_HITTER

    for key, grade in grades.items():
        if key not in labels:
            continue  # tool published but irrelevant for role (e.g. hit on a pitcher)
        try:
            g = float(grade)
        except (TypeError, ValueError):
            continue
        if g >= TOOL_CARRY_GRADE:
            out.append({
                "stat": labels[key],
                "direction": "green",
                "value": g,
                "value_display": str(int(g) if g.is_integer() else g),
                "level": None,
                "level_avg": 50,
                "delta": g - 50,
                "delta_display": f"+{int(g - 50)}",
                "category": _TOOL_CATEGORY.get(key, "tool"),
                "polarity": "above_good",
                "note": f"{int(g)} {labels[key].lower()} — carry tool.",
            })
        elif g >= TOOL_GREEN_GRADE:
            out.append({
                "stat": labels[key],
                "direction": "green",
                "value": g,
                "value_display": str(int(g) if g.is_integer() else g),
                "level": None,
                "level_avg": 50,
                "delta": g - 50,
                "delta_display": f"+{int(g - 50)}",
                "category": _TOOL_CATEGORY.get(key, "tool"),
                "polarity": "above_good",
                "note": f"{int(g)} {labels[key].lower()} — plus tool.",
            })
        elif g <= TOOL_RED_GRADE:
            out.append({
                "stat": labels[key],
                "direction": "red",
                "value": g,
                "value_display": str(int(g) if g.is_integer() else g),
                "level": None,
                "level_avg": 50,
                "delta": g - 50,
                "delta_display": f"{int(g - 50)}",
                "category": _TOOL_CATEGORY.get(key, "tool"),
                "polarity": "below_good",
                "note": f"{int(g)} {labels[key].lower()} — well below average.",
            })

    # Composite-level callouts. These read off the X+ indices, but those
    # are stamped in a second pass — when this is called from _serialize
    # the *_plus fields are still None. In that case we skip composite
    # flags and let a future re-flag pass pick them up if needed. Today
    # the second pass doesn't re-run compute_tool_flags, which is fine:
    # per-tool grades carry the most actionable signal anyway and the
    # composite is visible as its own pill in the UI.
    for plus_key, label in (
        ("composite_overall_plus", "Overall tools"),
        ("composite_off_plus",     "Offensive tools"),
        ("composite_def_plus",     "Defensive tools"),
        ("composite_stuff_plus",   "Stuff"),
        ("composite_cmd_plus",     "Command"),
    ):
        v = tools.get(plus_key)
        if v is None:
            continue
        if v >= TOOL_PLUS_GREEN:
            out.append({
                "stat": label,
                "direction": "green",
                "value": v,
                "value_display": f"{label} {v:+d}",
                "level": None,
                "level_avg": 100,
                "delta": v - 100,
                "delta_display": f"{v - 100:+d}",
                "category": "composite",
                "polarity": "above_good",
                "note": f"{label} index {v} — above-cohort toolset.",
            })
        elif plus_key == "composite_overall_plus" and v <= TOOL_PLUS_RED:
            out.append({
                "stat": label,
                "direction": "red",
                "value": v,
                "value_display": f"{label} {v:+d}",
                "level": None,
                "level_avg": 100,
                "delta": v - 100,
                "delta_display": f"{v - 100:+d}",
                "category": "composite",
                "polarity": "below_good",
                "note": f"{label} index {v} — below-cohort toolset.",
            })
    return out
