# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Smoke audit 2026-10-01, findings SHO02 and SHO03.

SHO02: the This Day rows (homepage rail and /history/) ellipsized the
position and the signing verb off most rows at 390 px. Every .otd-body now
carries title="<its full line>" from build_site, and at or below 480 px the
line wraps instead of ellipsizing.

SHO03: in the shared nav at phone width the account control (label hidden)
measured 31 x 38 px beside four 44 x 44 px controls; the max-width:640px
block of eephus-account.css now holds it to a 44 px touch target.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import build_site as B

ROOT = Path(__file__).parent


class _OtdBodies(HTMLParser):
    """Collect (title, text content) for every span.otd-body."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[str | None, str]] = []
        self._depth = 0
        self._title: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "span":
            return
        a = dict(attrs)
        if self._depth:
            self._depth += 1
        elif "otd-body" in (a.get("class") or "").split():
            self._depth, self._title, self._buf = 1, a.get("title"), []

    def handle_endtag(self, tag):
        if tag == "span" and self._depth:
            self._depth -= 1
            if not self._depth:
                self.rows.append((self._title, " ".join("".join(self._buf).split())))

    def handle_data(self, data):
        if self._depth:
            self._buf.append(data)


def _bodies(html_text: str) -> list[tuple[str | None, str]]:
    p = _OtdBodies()
    p.feed(html_text)
    p.close()
    return p.rows


def _media_block(css: str, query: str) -> str:
    """Concatenate the bodies of every @media block whose query is `query`."""
    out = []
    for m in re.finditer(r"@media\s*\(" + re.escape(query) + r"\)\s*\{", css):
        i, depth = m.end(), 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        out.append(css[m.end():i - 1])
    return "\n".join(out)


def _rule(block: str, selector_re: str) -> str:
    m = re.search(selector_re + r"\s*\{([^}]*)\}", block)
    return m.group(1) if m else ""


def test_sho02_otd_body_title_and_phone_wrap(monkeypatch):
    """Every .otd-body on the built homepage and /history/ (plus the four row
    builders fed a name that needs escaping) carries a title equal to its
    text content, and site.css wraps .otd-body at max-width:480px."""
    from datetime import date
    rows = []
    for rel in ("index.html", "history/index.html"):
        found = _bodies((ROOT / rel).read_text(encoding="utf-8"))
        assert found, f"{rel} has no .otd-body rows"
        rows += [(rel, t, x) for t, x in found]
    d = date(2019, 10, 1)
    g = {"player_name": 'Dan "D" O\'Neil & Co', "position": "RHP", "player_key": "k1"}
    built = (B._otd_debut_row(g, d) + B._otd_trade_row(g, {"from_org": "NYY", "to_org": "BOS"}, d)
             + B._otd_debut_row({"player_name": "No Pos"}, d))
    # The transaction and IL rows are built inside build_this_day from the
    # prospects.db ledgers; feed it a one-day ledger for today's date.
    t = date.today()
    mmdd = f"{t.month:02d}-{t.day:02d}"
    iso = f"{t.year - 3}-{mmdd}"
    monkeypatch.setattr(B, "_HIST_DB_CACHE", (
        {mmdd: [(iso, "SFA", "k1", "Boston Red Sox"), (iso, "SGN", "unknown-key", "")]},
        {mmdd: [(iso, "k1", "15-Day"), (iso, "unknown-key", "")]}))
    built += B.build_this_day({"players": [g], "graduates": []})
    rows += [("builder", t, x) for t, x in _bodies(built)]
    assert sum(r[0] == "builder" for r in rows) >= 7
    bad = [r for r in rows if r[1] != r[2]]
    css = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
    phone = _rule(_media_block(css, "max-width: 480px"), r"(?<![\w-])\.otd-body")
    assert not bad and re.search(r"white-space:\s*normal", phone), (bad[:5], phone)


def test_sho03_account_button_44px_at_phone_width():
    """The max-width:640px block of eephus-account.css gives the nav account
    button min-width:44px and min-height:44px."""
    css = (ROOT / "assets" / "eephus-account.css").read_text(encoding="utf-8")
    rule = _rule(_media_block(css, "max-width: 640px"), r"\.eph-nav-account \.eph-acct-btn")
    assert re.search(r"min-width:\s*44px", rule) and re.search(r"min-height:\s*44px", rule), rule
