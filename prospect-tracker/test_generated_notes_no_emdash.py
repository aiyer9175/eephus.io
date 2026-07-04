"""Regression guard for RC-7: storage.py generates card-flag / statline note
text that bakes into the debuts.json / inactive.json sidecars, which sit
outside the copy-gate's payload scope. The whole file cannot join the em-dash
TARGETS (it has hundreds of legitimate em-dashes in code comments), so this
test narrowly asserts that the *user-facing note/raw f-strings* stay clean.
"""

import io
import re

EM = "—"  # em-dash
EN = "–"  # en-dash

# Lines that build user-facing display text: a "note"/"raw" JSON-ish key, or a
# note = f"..." assignment. These strings surface as card-flag tooltips.
NOTE_LINE = re.compile(r'(["\']note["\']\s*:|["\']raw["\']\s*:|\bnote\s*=\s*f?["\'])')


def test_storage_generated_notes_have_no_dash_chars():
    offenders = []
    for i, line in enumerate(io.open("storage.py", encoding="utf-8"), 1):
        if not NOTE_LINE.search(line):
            continue
        if EM in line or EN in line:
            offenders.append((i, line.strip()[:100]))
    assert not offenders, (
        "em/en-dash in a user-facing storage.py note string "
        "(bakes into debuts.json/inactive.json card tooltips; use ' - '):\n"
        + "\n".join(f"  storage.py:{n}: {t}" for n, t in offenders)
    )
