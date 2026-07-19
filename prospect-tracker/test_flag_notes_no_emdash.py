"""Regression guard (copy-audit follow-up to test_generated_notes_no_emdash):
stat_flags.py and movement.py generate user-facing prose that bakes into the
payloads the frontend renders as tooltips (flag `note` strings ->
timeseries.json / debuts.json / inactive.json card flags; movement driver
`tooltip` strings -> the movers chips). Neither module can join the em-dash
TARGETS wholesale (both hold legitimate em-dashes in code comments), so this
test narrowly asserts the *user-facing note/tooltip/label string lines* stay
clean per the owner's no-em-dash rule (house style is ' - ').
"""

import io
import re

EM = "—"  # em-dash
EN = "–"  # en-dash

# Lines that build user-facing display text in each generator.
PATTERNS = {
    # green_note= / red_note= rule copy + "note": payload keys (incl. f-strings)
    "stat_flags.py": re.compile(r'(green_note\s*=|red_note\s*=|["\']note["\']\s*:)'),
    # driver chips: {"label": ..., "tooltip": ...} rendered on movers surfaces
    "movement.py": re.compile(r'(["\']label["\']\s*:|["\']tooltip["\']\s*:)'),
}


def _offenders(path: str, pattern: re.Pattern) -> list[tuple[int, str]]:
    out = []
    for i, line in enumerate(io.open(path, encoding="utf-8"), 1):
        if not pattern.search(line):
            continue
        if EM in line or EN in line:
            out.append((i, line.strip()[:100]))
    return out


def test_stat_flags_notes_have_no_dash_chars():
    offenders = _offenders("stat_flags.py", PATTERNS["stat_flags.py"])
    assert not offenders, (
        "em/en-dash in a user-facing stat_flags.py note string "
        "(bakes into timeseries/debuts/inactive card tooltips; use ' - '):\n"
        + "\n".join(f"  stat_flags.py:{n}: {t}" for n, t in offenders)
    )


def test_movement_tooltips_have_no_dash_chars():
    offenders = _offenders("movement.py", PATTERNS["movement.py"])
    assert not offenders, (
        "em/en-dash in a user-facing movement.py driver label/tooltip "
        "(bakes into timeseries/inactive movement chips; use ' - '):\n"
        + "\n".join(f"  movement.py:{n}: {t}" for n, t in offenders)
    )
