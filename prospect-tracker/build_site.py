# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""
build_site.py - static-site generator for the editorial pages of eephus.io.

Reads `content/` and writes the static pages that share the PROSPX theme
(`assets/site.css`) + the site-wide nav:

    /              -> index.html              (Home: brand hero + module cards)
    /articles/     -> articles/index.html     (grid of article cards, newest first)
    /articles/<s>/ -> articles/<slug>/index.html  (one page per content/articles/<slug>.md)
    /team/         -> team/index.html          (from content/team.json)

PROSPX lives at /prospx/index.html and is NOT touched by this script (its nav +
asset paths were wired once, by hand). `run_monthly.py` (the data pipeline that
writes data/*.json) is also independent of this build.

Add an article = drop a markdown file in content/articles/ with frontmatter
(title/author/handle/date/summary) and rerun `python build_site.py`. Embed a
YouTube clip on its own line with `@youtube: <url-or-id>`.

Usage:  python build_site.py
"""
from __future__ import annotations

import functools
import hashlib
import html
import json
import math
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import markdown as md

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
SITE_ORIGIN = "https://eephus.io"   # absolute base for canonical + social-card (og/twitter) URLs

# Cache-bust assets/site.css by content hash so browsers/CDNs always pull the
# latest stylesheet after a rebuild - otherwise a stale cached CSS shows the old
# layout (frozen ticker, unstyled callout, etc.) even though the files updated.
def _asset_ver(rel: str) -> str:
    try:
        return hashlib.md5((ROOT / rel).read_bytes()).hexdigest()[:8]
    except OSError:
        return "1"
_CSS_VER = _asset_ver("assets/site.css")
_NAV_VER = _asset_ver("assets/eephus-nav.js")
_ACCT_VER = _asset_ver("assets/eephus-account.js")
_UI_VER = _asset_ver("assets/eephus-ui.js")
_ACCT_CSS_VER = _asset_ver("assets/eephus-account.css")
_BG_VER = _asset_ver("assets/eephus-bg.js")
_FA_VER = _asset_ver("assets/fa.js")
_GL_VER = _asset_ver("assets/eephus-gl.js")
_GLAPP_VER = _asset_ver("assets/glossary.js")
_PROJ_VER = _asset_ver("assets/projections.js")
_MLBSTATS_VER = _asset_ver("assets/mlbstats.js")
_PAL_VER = _asset_ver("assets/pal.js")
_TM_VER = _asset_ver("assets/trademachine.js")
_TM_CSS_VER = _asset_ver("assets/trademachine.css")
_HUB_VER = _asset_ver("assets/eephus-hub.js")
_GFX_VER = _asset_ver("assets/eephus-gfx.js")
_FANTASY_VER = _asset_ver("assets/fantasy.js")
_EXPORT_VER = _asset_ver("assets/eephus-export.js")
_PARKS_VER = _asset_ver("assets/parks.js")
_PARKS_CSS_VER = _asset_ver("assets/parks.css")

# eephus.io account layer (Parts 1-7), injected before </body> on every editorial
# page. OPTIONAL by design: assets/eephus-config.js is git-ignored and absent on
# the public tree, so its <script> 404s harmlessly and window.EEPHUS_SUPABASE stays
# undefined - eephus-account.js then runs fully inert (no Supabase SDK fetch, no
# behavior change) and the page renders exactly as today. When config IS present
# the module self-injects the SDK and lights up the account UI.
ACCOUNT_SCRIPTS = (
    f'<script src="/assets/eephus-config.js" defer></script>\n'
    f'<script src="/assets/eephus-account.js?v={_ACCT_VER}" defer></script>\n'
    f'<script src="/assets/eephus-ui.js?v={_UI_VER}" defer></script>\n'
    # Dark-theme phosphor-starfield background (shared with PROSPX). Rides the
    # per-page script block; inert (mounts nothing) under the light theme.
    f'<script src="/assets/eephus-bg.js?v={_BG_VER}" defer></script>\n'
    # Shared glossary runtime: data loader + ⌘K palette + term tooltips.
    f'<script src="/assets/eephus-gl.js?v={_GL_VER}" defer></script>\n'
    # Universal copy/export: a quiet chip on every table + chart (text + image).
    f'<script src="/assets/eephus-export.js?v={_EXPORT_VER}" defer></script>'
)
# Account/forum stylesheet - linked in <head> after site.css on every editorial
# page (scoped under .eph-*; the circular avatar is the one sanctioned curve).
ACCOUNT_CSS_LINK = f'<link rel="stylesheet" href="/assets/eephus-account.css?v={_ACCT_CSS_VER}">'

# Unified prospect-photo resolution - mirrors PROSPX's headshotURL(): consult the
# resolved context map (data/photo_ctx.json, built by headshots.py) and use the
# REAL MiLB/MLB photo for resolved ids ('67'/'milb'); fall back to the generic
# silhouette overlay (always 200 - never a broken image) when unresolved/'none'.
# Single source of truth so the homepage shows the same coverage as PROSPX,
# instead of the old hardcoded '67' that silhouetted every milb-only prospect.
def _load_photo_ctx() -> dict:
    try:
        return (json.loads((ROOT / "data" / "photo_ctx.json").read_text(encoding="utf-8")).get("ctx")) or {}
    except (OSError, ValueError, AttributeError):
        return {}
_PHOTO_CTX = _load_photo_ctx()

def _headshot_url(mlbam, px: int = 180) -> str | None:
    """Resolved rectangular prospect headshot URL via the unified chain, or None
    when there's no MLBAM id (caller renders the silhouette)."""
    if not mlbam:
        return None
    r = max(60, px * 2)
    ctx = _PHOTO_CTX.get(str(mlbam))
    if ctx in ("67", "milb"):
        return (f"https://img.mlbstatic.com/mlb-photos/image/upload/"
                f"w_{r},q_auto:best/v1/people/{mlbam}/headshot/{ctx}/current")
    # 'none' / not-yet-resolved → generic overlay (always returns an image:
    # the real headshot if one exists, else the silhouette) so it's never empty.
    return (f"https://img.mlbstatic.com/mlb-photos/image/upload/"
            f"d_people:generic:headshot:67:current.png/w_{r},q_auto:best/v1/people/{mlbam}/headshot/67/current")

# Owner-set order (2026-06-11): Home, PROSPX, CollegeSavant (directly under
# PROSPX), FA, Projections, Articles, Forums, Glossary, Team.
# 2026-06-12: the standalone Teams module merged into MLB Projections
# (Team Outlook view carries the org-dashboard columns); /teams/ now
# redirects there and the nav entry is gone.
# A nav entry is either a LEAF (key, label, href) or a GROUP dict
#   {"group": <label>, "key": <group key>, "children": [(key, label, href), ...]}
# rendered as a click dropdown in the top bar (_nav) and a nested sub-block in
# the homepage sidebar. The MLB-facing modules (Free Agency, Projections, MLB
# Stats) live under one "MLB Modules" group; PROSPX/CollegeSavant stay top-level
# (MiLB + amateur). This is the SINGLE source - _nav(), the sidebar, and the
# hand-maintained static nav copies (prospx + the two CollegeSavant pages) all
# mirror it; test_collegesavant_nav_in_sync guards the static copies.
NAV_ITEMS = [
    ("home",     "Home",             "/"),
    ("prospx",   "PROSPX",           "/prospx/"),
    ("collegesavant", "CollegeSavant", "/collegesavant/"),
    {"group": "MLB Modules", "key": "mlb", "children": [
        ("fa",          "Free Agency", "/fa/"),
        ("projections", "Projections", "/projections/"),
        ("mlbstats",    "MLB Stats",   "/mlbstats/"),
        ("pal",         "Alchemy Lab", "/pal/"),
        ("trademachine", "Trade Machine", "/trademachine/"),
        ("fantasy",     "Fantasy", "/fantasy/"),
    ]},
    ("articles", "Articles",         "/articles/"),
    ("forums",   "Forums",           "/forums/"),
    ("glossary", "Glossary",         "/glossary/"),
    ("team",     "Developers",        "/team/"),
]

def _nav_is_group(item) -> bool:
    """A NAV_ITEMS entry is a group when it's a dict (vs a (key,label,href) leaf)."""
    return isinstance(item, dict)

def nav_leaves() -> list[tuple]:
    """Flatten NAV_ITEMS (groups + leaves) to (key, label, href) in nav order -
    the canonical link set the static nav copies must mirror."""
    out: list[tuple] = []
    for item in NAV_ITEMS:
        if _nav_is_group(item):
            out.extend(item["children"])
        else:
            out.append(item)
    return out

# PROSPX sub-sections - deep links into the app (section = `tab` query param in
# the hash; `active` is the default so it has no param).
PROSPX_SUBNAV = [
    ("Prospects",     "/prospx/"),
    ("Farm Systems",  "/prospx/#tab=farm"),
    ("Leaderboards",  "/prospx/#tab=leaderboards"),
    ("Transactions",  "/prospx/#tab=traded"),
    ("Injured List",  "/prospx/#tab=injured"),
    ("Spotlights",    "/prospx/#tab=spotlights"),
    ("Debuted",       "/prospx/#tab=debuts"),
    ("MLB Draft",     "/prospx/#tab=draft"),
    ("International",  "/prospx/#tab=ifa"),
    ("Overseas",      "/prospx/#tab=overseas"),
    ("Time Machine",  "/prospx/#tab=timemachine"),
    ("Scatterplots",  "/prospx/#tab=charts"),
    # Glossary intentionally omitted - it's a top-level module of its own
    # ("Glossary & Methodology" in the Modules nav), so listing it here too
    # was redundant.
]

# Site-wide theme: read the shared key PROSPX uses (prospect-tracker.theme) and
# set <html data-theme> synchronously in <head> (no flash); toggle persists to
# the same key so light/dark stays in sync across the whole site incl. PROSPX.
THEME_INIT = (
    '<script>(function(){try{var t=localStorage.getItem("prospect-tracker.theme");'
    'if(!t)t=(window.matchMedia&&matchMedia("(prefers-color-scheme: dark)").matches)?"dark":"light";'
    'document.documentElement.setAttribute("data-theme",t);}catch(e){}})();'
    'function eephusToggleTheme(){try{var c=document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark";'
    'document.documentElement.setAttribute("data-theme",c);localStorage.setItem("prospect-tracker.theme",c);}catch(e){}}</script>'
)
THEME_BTN = (
    '<button type="button" class="home-theme-toggle" data-theme-toggle onclick="eephusToggleTheme()" aria-label="Toggle dark mode">'
    '<span class="lbl-dark">☾ Dark</span><span class="lbl-light">☀ Light</span></button>'
)

# Favicons + PWA + theme-color - SVG primary (crisp at any size), ICO + 32px PNG
# fallbacks, apple-touch for home-screen pins, the web manifest (installable
# identity), and theme-color for the mobile browser chrome (navy on light,
# near-black on dark). The artifacts are committed (tools/generate_brand_assets.py
# regenerates them when the brand changes); hand-edited pages (prospx,
# collegesavant) carry the same literal block.
FAVICON_LINKS = (
    '<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">\n'
    '<link rel="icon" href="/favicon.ico" sizes="32x32">\n'
    '<link rel="icon" href="/assets/favicon-32.png" type="image/png" sizes="32x32">\n'
    '<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">\n'
    '<link rel="manifest" href="/assets/site.webmanifest">\n'
    '<meta name="theme-color" content="#0E2B4D" media="(prefers-color-scheme: light)">\n'
    '<meta name="theme-color" content="#0C0C0E" media="(prefers-color-scheme: dark)">'
)

# Default Open Graph / Twitter share image - every page emits social-card tags
# (a shared eephus.io link should never render as a bare URL). Pages with a
# richer card (per-article share-card.png) override it.
DEFAULT_SHARE_IMAGE = f"{SITE_ORIGIN}/assets/share-default.png"

# Contact / feedback channel for the Open Beta - one address, linked from the
# footer of every page. Plain mailto keeps it dependency-free until the
# account layer ships.
FEEDBACK_MAILTO = (
    "mailto:arkndjl@gmail.com?subject=eephus.io%20beta%20feedback"
)

# Google Form embed for the /report/ "Report a bug" page. Owner: paste the
# embeddable form URL here (the .../viewform?embedded=true variant from the
# form's Send > <> embed dialog). Left empty, /report/ shows an on-theme
# placeholder card plus the mailto fallback until the form is wired up.
BUG_FORM_URL = ""

def _footer() -> str:
    """The shared page footer: identity line left, useful links right.
    Every editorial surface and the homepage emit the same block."""
    year = date.today().year
    links = (
        f'<a href="/team/">About</a>'
        f'<a href="/news/">Prospect News</a>'
        f'<a href="/parks/">Park Factors</a>'
        f'<a href="/sources/">Data Sources</a>'
        f'<a href="/glossary/">Glossary</a>'
        f'<a href="/report/">Report a bug</a>'
        f'<a href="https://x.com/eephus_io" target="_blank" rel="noopener noreferrer">@eephus_io</a>'
        f'<a href="{html.escape(DISCORD_URL)}" target="_blank" rel="noopener noreferrer">Discord</a>'
    )
    # Footer carries the compact mark (the favicon ball) so the identity closes
    # every page - it reads on both themes (cream face, navy outline).
    mark = ('<img src="/assets/favicon.svg" alt="" aria-hidden="true" '
            'style="width:18px;height:18px;vertical-align:-4px;margin-right:7px">')
    return (
        '<footer class="eephus-footer">\n'
        f'  <span>{mark}eephus.io - sabermetrics · {html.escape(EEPHUS_VERSION)}</span>\n'
        f'  <nav class="eephus-footer-links" aria-label="Footer">{links}</nav>\n'
        f'  <span>© {year} eephus.io</span>\n'
        '</footer>'
    )

# --------------------------------------------------------------------------- #
# Brand: one version string + one beta badge, the eephus.io placeholder logo,
# and a shared X/social link. THE SINGLE SOURCE for the version is EEPHUS_VERSION
# here; the prospx/index.html static header mirrors the same literal (its own
# hand-edited file) and points back to this constant in a comment.
# --------------------------------------------------------------------------- #
EEPHUS_VERSION = "β v1.0"
BETA_BADGE = (
    f'<span class="eephus-beta" title="eephus.io is in beta - version 1.0">'
    f'{html.escape(EEPHUS_VERSION)}</span>'
)

# Module lifecycle stage - β = in beta (the Open Beta launch promoted every
# module to beta). Rendered ONLY as a bordered chip on each module's own
# masthead (Open Beta polish: the nav links and the homepage sidebar carry no
# sigils; version is noted where you land, not where you browse). The homepage
# hero keeps the site-wide chip (eephus.io is in beta).
MODULE_STAGE = {
    "prospx": ("β", "PROSPX is in beta"),
    "trademachine": ("β", "Trade Machine is in beta - newly launched"),
    "fa": ("β", "MLB Free Agency is in beta - newly launched; numbers may shift as the model matures"),
    "projections": ("β", "MLB Projections is in beta - newly launched; numbers may shift as the model matures"),
    "mlbstats": ("β", "MLB Stats is in beta - newly launched; metrics may shift as the models mature"),
    "pal": ("β", "Alchemy Lab is in beta - newly launched; the conversion models are provisional"),
    "fantasy": ("β", "Fantasy is in beta - newly launched; ROS projections may shift as the models mature"),
    "forums": ("β", "Forums is in beta - newly launched"),
    "parks": ("β", "MiLB Park Factors is in beta - newly launched; the factors are a measured artifact, the surface is new"),
}

# Dev byline - the same "Created by" signature PROSPX renders above its
# masthead (prospx/index.html .build-banner). FA + Projections carry it too
# (owner ask 2026-06-12); the .build-banner rule lives in assets/site.css.
CREATED_BY_BANNER = (
    '<div class="build-banner" aria-label="Build version">Created by '
    '<span aria-hidden="true">🜎</span> Noah J. Dengler / @ARKNDJL</div>'
)

# Modern X (Twitter) glyph - module-level so social links on every surface share
# one mark. (build_team keeps its own local copy for the per-member chips.)
_X_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 '
          '8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 '
          '17.52h1.833L7.084 4.126H5.117z"/></svg>')

def _x_link(handle: str, cls: str = "") -> str:
    """An on-theme X link: glyph + @handle. Sharp corners, opens in a new tab.
    `cls` appends a modifier (e.g. eph-xlink--beta sizes it to the β chip)."""
    h = handle.lstrip("@")
    return (f'<a class="eph-xlink{" " + cls if cls else ""}" href="https://x.com/{html.escape(h)}" target="_blank" '
            f'rel="noopener noreferrer" aria-label="Follow @{html.escape(h)} on X">'
            f'{_X_SVG}<span class="eph-xlink-handle">@{html.escape(h)}</span></a>')

# Community Discord server - one module-level constant so every surface points
# at the same invite. Inline glyph mirrors the _X_SVG treatment (no external art).
DISCORD_URL = "https://discord.gg/X3BbVrJ4w"
_DISCORD_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.317 4.369a19.79 19.79 0 0 0-4.885-1.515.074.074 0 0 0-.079.037 '
                'c-.211.375-.445.865-.608 1.249a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.036 '
                '19.736 19.736 0 0 0-4.885 1.515.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 '
                '19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 '
                '13.1 13.1 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.126-.094.252-.192.372-.291a.074.074 0 0 1 .077-.01 '
                'c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.009c.12.099.246.198.373.292a.077.077 0 0 1-.006.127 '
                '12.3 12.3 0 0 1-1.873.891.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 '
                '19.84 19.84 0 0 0 6.002-3.03.077.077 0 0 0 .032-.055c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028z'
                'M8.02 15.331c-1.183 0-2.157-1.086-2.157-2.419 0-1.333.955-2.42 2.157-2.42 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.419-2.157 2.419z'
                'm7.975 0c-1.183 0-2.157-1.086-2.157-2.419 0-1.333.955-2.42 2.157-2.42 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.419-2.157 2.419z"/></svg>')

def _discord_link(cls: str = "") -> str:
    """An on-theme Discord link: glyph + label. Mirrors _x_link (sharp corners,
    new tab); points at the single DISCORD_URL invite. Glyph is inline SVG."""
    return (f'<a class="eph-xlink{" " + cls if cls else ""}" href="{html.escape(DISCORD_URL)}" target="_blank" '
            f'rel="noopener noreferrer" aria-label="Join the eephus.io Discord">'
            f'{_DISCORD_SVG}<span class="eph-xlink-handle">Discord</span></a>')

# eephus.io merged brand mark - the "signature pitch" arc is now PART of the
# lettering: the lob launches off the leading "e", crests with the ball at
# apex, and lands on the "o". Everything is em-scaled inside the nameplate,
# so the same mark renders at masthead (clamp 2.4-4rem) and sidebar (20px)
# sizes without separate art. Arc carries the cardinal→gold→green→navy
# masthead gradient (vector-effect keeps the stroke crisp under the
# stretch-to-width scaling); the ball is its own fixed-aspect SVG so it can
# never squash, punches through via .eephus-logo-ball (theme-aware bg fill),
# and the seam rides currentColor.
def eephus_merged_wordmark(uid: str, tag: str = "h1") -> str:
    grad = f"eephus-arc-{uid}" # per-instance gradient id - two marks per page
    arc = (
        f'<svg class="ew-arc" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">'
        f'<defs><linearGradient id="{grad}" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%" stop-color="#B91C1C"/><stop offset="38%" stop-color="#C9A227"/>'
        '<stop offset="68%" stop-color="#1F7A3A"/><stop offset="100%" stop-color="#0E2B4D"/>'
        '</linearGradient></defs>'
        f'<path d="M 3 30 Q 50 -24 97 30" pathLength="100" fill="none" stroke="url(#{grad})" '
        'stroke-width="2.4" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>'
        f'<svg class="ew-ball" viewBox="0 0 24 24" aria-hidden="true">'
        f'<circle class="eephus-logo-ball" cx="12" cy="12" r="8.5" stroke="url(#{grad})" stroke-width="3"/>'
        # Two seam arcs bulging outward (the px-ball / favicon read) so the apex
        # ball is clearly a baseball, not a plain circle.
        '<path class="eephus-logo-seam" d="M 16 5.6 Q 20.5 12 16 18.4" fill="none" stroke="currentColor" stroke-width="1.3"/>'
        '<path class="eephus-logo-seam" d="M 8 5.6 Q 3.5 12 8 18.4" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>'
    )
    return (f'<{tag} class="nameplate eephus-wordmark-merged">{arc}'
            f'eephus<span class="dot">.io</span></{tag}>')

def prospx_ball_logo(uid: str, px: int = 16) -> str:
    """The PROSPX baseball badge - a self-contained copy of the app
    masthead's .h1-logo SVG (cream ball, gradient seams, P/X monogram) for
    sidebar/nav lockups. Fills ride the theme tokens via inline style; the
    seam gradient keeps the masthead's literal stops (SVG gradients can't
    read CSS var()). ``uid`` keeps gradient ids unique per placement."""
    gid = f"px-seam-{uid}"
    return (
        f'<svg class="px-ball" width="{px}" height="{px}" viewBox="0 0 44 44" aria-hidden="true">'
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%" stop-color="#B91C1C"/><stop offset="35%" stop-color="#C9A227"/>'
        '<stop offset="65%" stop-color="#1F7A3A"/><stop offset="100%" stop-color="#0E2B4D"/>'
        '</linearGradient></defs>'
        '<circle cx="22" cy="22" r="19" style="fill:var(--bg-secondary);stroke:var(--text-primary);stroke-width:2"/>'
        f'<path stroke="url(#{gid})" d="M 32 8 Q 40 22 32 36" style="fill:none;stroke-width:3;stroke-linecap:round"/>'
        '<path d="M 32 8 Q 40 22 32 36" style="fill:none;stroke:var(--text-primary);stroke-width:1.2;stroke-linecap:round;stroke-dasharray:1.5 3"/>'
        f'<path stroke="url(#{gid})" d="M 12 8 Q 4 22 12 36" style="fill:none;stroke-width:3;stroke-linecap:round"/>'
        '<path d="M 12 8 Q 4 22 12 36" style="fill:none;stroke:var(--text-primary);stroke-width:1.2;stroke-linecap:round;stroke-dasharray:1.5 3"/>'
        '<g text-anchor="middle" style="font-family:\'Old English Text MT\',\'UnifrakturCook\',Georgia,serif;'
        'font-weight:800;fill:var(--text-primary);stroke:var(--bg-secondary);stroke-width:0.7;paint-order:stroke">'
        '<text x="18.5" y="30" font-size="22">P</text><text x="26" y="30" font-size="23">X</text></g>'
        '</svg>'
    )

def eephus_logo_lockup(badge: bool = True) -> str:
    """Homepage hero lockup: the merged arc-wordmark with the β tag and the
    @eephus_io chip stacked beside it (β on top, X under - the X chip carries
    the link accent so it reads clickable)."""
    chips = (
        f'<div class="eephus-logo-chips">{BETA_BADGE}'
        f'{_x_link("eephus_io", cls="eph-xlink--beta eph-xlink--live")}'
        f'{_discord_link(cls="eph-xlink--beta eph-xlink--live")}</div>'
    ) if badge else ""
    # eephus-logo--animate plays the one-shot arc-draw + ball-settle on the
    # homepage hero only (the nav/sidebar lockups stay static). Reduced-motion
    # shows the final frame; see assets/site.css.
    return f'<div class="eephus-logo eephus-logo--animate">{eephus_merged_wordmark("mast")}{chips}</div>'

# --------------------------------------------------------------------------- #
# Markdown + YouTube
# --------------------------------------------------------------------------- #
_YT_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/))([A-Za-z0-9_-]{11})"
)

def _youtube_id(raw: str) -> str | None:
    raw = raw.strip()
    m = _YT_RE.search(raw)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):   # bare id
        return raw
    return None

def _youtube_embed(video_id: str) -> str:
    src = f"https://www.youtube.com/embed/{video_id}"
    return (
        '<div class="video-embed">'
        f'<iframe src="{src}" title="YouTube video" loading="lazy" '
        'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; '
        'picture-in-picture" allowfullscreen></iframe></div>'
    )

def render_markdown(text: str) -> str:
    """Render article markdown to HTML, with a clean `@youtube: <url>` directive.
    The directive is swapped for a placeholder before conversion, then back to a
    responsive iframe afterward, so the markdown engine never mangles the embed."""
    placeholders: dict[str, str] = {}
    out_lines = []
    for line in text.splitlines():
        m = re.match(r"^\s*@youtube:\s*(\S+)\s*$", line)
        if m:
            vid = _youtube_id(m.group(1))
            if vid:
                token = f"@@YT_{len(placeholders)}@@"
                placeholders[token] = _youtube_embed(vid)
                out_lines.append("")
                out_lines.append(token)
                out_lines.append("")
                continue
        out_lines.append(line)
    body = md.markdown(
        "\n".join(out_lines),
        extensions=["extra", "sane_lists", "smarty"],
        output_format="html5",
    )
    for token, embed in placeholders.items():
        body = body.replace(f"<p>{token}</p>", embed).replace(token, embed)
    return body

# --------------------------------------------------------------------------- #
# Prospect deep-linking - turn the first mention of a known player's name into a
# link to their PROSPX detail page (/prospx/#player=<key>), the same deep link the
# homepage modules use. Matching is accent/'.'-insensitive so Will's "Rodríguez" /
# "Witt Jr" resolve against the data's "Rodriguez" / "Witt Jr.".
# --------------------------------------------------------------------------- #
def _norm_map(s: str):
    """Accent-stripped, lowercased copy of `s` plus an index map back to the
    original character positions (so we can wrap the original spelling)."""
    out, idx = [], []
    for i, ch in enumerate(s):
        for d in unicodedata.normalize("NFKD", ch):
            if unicodedata.combining(d):
                continue
            out.append(d.lower())
            idx.append(i)
    return "".join(out), idx

@functools.lru_cache(maxsize=1)
def _player_links() -> tuple:
    """(normalized full name, player_key) pairs from the live data layer (prospects +
    graduates), longest first. Only players with a real PROSPX page are linkable."""
    data = load_site_data() or {}
    seen, pairs = set(), []
    for p in (data.get("players") or []) + (data.get("graduates") or []):
        nm = (p.get("player_name") or "").strip()
        key = p.get("player_key")
        if not nm or not key or " " not in nm:      # full "First Last" names only
            continue
        norm = _norm_map(nm)[0].rstrip(".").strip()
        if len(norm) < 6 or norm in seen:
            continue
        seen.add(norm)
        pairs.append((norm, key))
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return tuple(pairs)

def _linkify_players(body_html: str) -> str:
    """Link the first mention of each known player name. Operates only on text nodes
    (tags + their attributes, e.g. image alt text, and existing <a>…</a> are skipped)."""
    pairs = _player_links()
    if not pairs:
        return body_html
    linked = set()
    parts = re.split(r'(<[^>]+>)', body_html)
    in_link = False
    for i, tok in enumerate(parts):
        if tok[:1] == "<":
            t = tok.lower()
            if t.startswith("<a"):
                in_link = True
            elif t.startswith("</a"):
                in_link = False
            continue
        if in_link or not tok.strip():
            continue
        nrm, idx = _norm_map(tok)
        hits = []
        for norm, key in pairs:
            if key in linked:
                continue
            pos = nrm.find(norm)
            if pos < 0:
                continue
            end = pos + len(norm)
            before = nrm[pos - 1] if pos > 0 else " "
            after = nrm[end] if end < len(nrm) else " "
            if before.isalnum() or after.isalnum():     # require clean word boundaries
                continue
            hits.append((idx[pos], idx[end - 1] + 1, key))
        if not hits:
            continue
        out, cur = [], 0
        for s, e, key in sorted(hits):
            if s < cur:                                 # drop overlapping matches
                continue
            href = f"/prospx/#player={html.escape(key)}"
            out.append(tok[cur:s])
            out.append(f'<a class="px-link" href="{href}">{html.escape(tok[s:e])}</a>')
            linked.add(key)
            cur = e
        out.append(tok[cur:])
        parts[i] = "".join(out)
    return "".join(parts)

# --------------------------------------------------------------------------- #
# Frontmatter
# --------------------------------------------------------------------------- #
def parse_article(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    meta: dict = {}
    body = raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            fm = raw[3:end].strip("\n")
            body = raw[end + 4:].lstrip("\n")
            for ln in fm.splitlines():
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    meta[k.strip()] = v.strip()
    meta.setdefault("title", path.stem.replace("-", " ").title())
    meta["slug"] = path.stem
    meta["body_html"] = _linkify_players(render_markdown(body))
    meta["date_sort"] = meta.get("date", "")
    meta["date_disp"] = _fmt_date(meta.get("date", ""))
    return meta

def _fmt_date(s: str) -> str:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").strftime("%B %-d, %Y")
    except (ValueError, AttributeError):
        try:  # Windows strftime has no %-d
            return datetime.strptime(s.strip(), "%Y-%m-%d").strftime("%B %d, %Y").replace(" 0", " ")
        except ValueError:
            return s

def _member_slug(name: str) -> str:
    """Stable per-person anchor slug for a Development Team card (e.g.
    'Will Cahoon' -> 'will-cahoon'). Used by both the team-card id and the
    article byline deep-link so they always line up."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")

def _team_index() -> dict:
    """name(lowercased) -> {slug, handle} from content/team.json - the single
    source of truth for dev-team identity + X handles. Empty on any error."""
    idx: dict = {}
    try:
        members = json.loads((CONTENT / "team.json").read_text(encoding="utf-8"))
    except Exception:
        return idx
    for m in members:
        nm = (m.get("name") or "").strip()
        if nm:
            idx[nm.lower()] = {"slug": _member_slug(nm), "handle": (m.get("handle") or None)}
    return idx

def _byline(meta: dict, sep: str = " · ", link_handle: bool = True) -> str:
    # link_handle=False when the byline sits INSIDE a card <a> (nested <a> is
    # invalid HTML and the browser splits the card apart) - render the author +
    # @handle as text there, and only deep-link on the standalone article page.
    author = (meta.get("author", "") or "").strip()
    member = _team_index().get(author.lower())  # None for guest authors
    # Author name → their Development Team card (deep-linked) when they're on the
    # team and we're allowed to emit a link; otherwise plain text. No broken
    # anchors - a guest author with no card simply isn't linked.
    if author and member and link_handle:
        author_html = (f'<a class="byline-author" href="/team/#member-{member["slug"]}">'
                       f'{html.escape(author)}</a>')
    elif author:
        author_html = f'<span class="author">{html.escape(author)}</span>'
    else:
        author_html = ""
    # Handle → X profile. Prefer the dev-team handle (single source of truth);
    # fall back to the article's own handle only for guests not on the team.
    # Missing handle → hidden, never a guessed URL.
    if member:
        handle = (member.get("handle") or "").lstrip("@") or None
    else:
        handle = (meta.get("handle") or "").lstrip("@") or None
    parts = [author_html] if author_html else []
    if handle:
        parts.append(
            f'<a class="byline-handle" href="https://x.com/{html.escape(handle)}" '
            f'target="_blank" rel="noopener noreferrer">@{html.escape(handle)}</a>'
            if link_handle else f'<span class="handle">@{html.escape(handle)}</span>'
        )
    if meta.get("date_disp"):
        parts.append(html.escape(meta["date_disp"]))
    return sep.join(parts)

# --------------------------------------------------------------------------- #
# Page shell
# --------------------------------------------------------------------------- #
def _nav(active: str) -> str:
    # The top bar runs one line, always - long labels get a short form
    # here (the homepage sidebar keeps the full names).
    short = {}
    items = []
    for item in NAV_ITEMS:
        if _nav_is_group(item):
            children = item["children"]
            active_in = any(k == active for k, _l, _h in children)
            clinks = []
            for k, l, h in children:
                ccls = ' class="is-active"' if k == active else ""
                clinks.append(f'<a href="{h}" role="menuitem"{ccls}>{html.escape(short.get(k, l))}</a>')
            gcls = " is-active" if active_in else ""
            # Native <details> dropdown: click-toggles, keyboard-accessible with
            # zero JS. assets/eephus-nav.js adds outside-click/Esc close and
            # fixed-positions the menu so it escapes the nav's overflow clip.
            items.append(
                f'<details class="eephus-nav-group{gcls}" data-nav-group>'
                f'<summary aria-haspopup="true">{html.escape(item["group"])}'
                f'<span class="nav-caret" aria-hidden="true">▾</span></summary>'
                f'<div class="eephus-nav-menu" role="menu">{"".join(clinks)}</div>'
                '</details>'
            )
        else:
            key, label, href = item
            cls = ' class="is-active"' if key == active else ""
            items.append(f'<a href="{href}"{cls}>{html.escape(short.get(key, label))}</a>')
    # Site-wide controls (right-aligned), matching PROSPX's primary nav: a
    # Watchlist deep-link into PROSPX + the Dark Mode toggle.
    controls = (
        '<div class="eephus-nav-controls">'
        '<button class="eephus-nav-ctrl" type="button" data-qk-open aria-label="Quick search (Ctrl+K)" title="Search any term or metric - Ctrl+K / ⌘K">'
        '<span aria-hidden="true">⌘K</span><span class="eephus-nav-ctrl-label">Search</span></button>'
        '<a class="eephus-nav-ctrl" href="/prospx/#tab=watchlist" aria-label="Watchlist">'
        '<span aria-hidden="true">★</span><span class="eephus-nav-ctrl-label">Watchlist</span></a>'
        '<button class="eephus-nav-ctrl" type="button" data-theme-toggle onclick="eephusToggleTheme()" aria-label="Toggle dark mode">'
        '<span class="theme-icon lbl-dark" aria-hidden="true">☾</span>'
        '<span class="theme-icon lbl-light" aria-hidden="true">☀</span>'
        '<span class="eephus-nav-ctrl-label"><span class="lbl-dark">Dark Mode</span><span class="lbl-light">Light Mode</span></span>'
        '</button></div>'
    )
    return (
        '<header class="eephus-nav">'
        f'<span class="eephus-brand"><a class="eephus-wordmark" href="/" aria-label="eephus.io home">'
        f'{eephus_merged_wordmark("nav", tag="span")}</a></span>'
        f'<nav class="eephus-links">{"".join(items)}</nav>'
        f'{controls}'
        "</header>"
    )

def _social_meta(title: str, description: str, image: str = "", url: str = "",
                 og_type: str = "website") -> str:
    """Open Graph + Twitter card tags so a shared link (X/Facebook/iMessage) renders a
    rich preview. Every page gets the default brand card; articles override `image`
    with their per-piece share card and `og_type` with "article"."""
    t, d = html.escape(title), html.escape(description)
    image = image or DEFAULT_SHARE_IMAGE
    tags = [f'<meta property="og:type" content="{html.escape(og_type)}">',
            f'<meta property="og:title" content="{t}">',
            f'<meta property="og:description" content="{d}">',
            '<meta property="og:site_name" content="eephus.io">']
    if url:
        tags += [f'<meta property="og:url" content="{html.escape(url)}">',
                 f'<link rel="canonical" href="{html.escape(url)}">']
    tags += [f'<meta property="og:image" content="{html.escape(image)}">',
             '<meta name="twitter:card" content="summary_large_image">',
             f'<meta name="twitter:title" content="{t}">',
             f'<meta name="twitter:description" content="{d}">',
             f'<meta name="twitter:image" content="{html.escape(image)}">']
    return "\n".join(tags)

def page(title: str, active: str, body: str, description: str = "",
         image: str = "", url: str = "", og_type: str = "website",
         robots: str = "") -> str:
    desc = html.escape(description or "eephus.io - sabermetrics")
    social = _social_meta(title, description or "eephus.io - sabermetrics",
                          image, url, og_type)
    robots_meta = (f'\n<meta name="robots" content="{html.escape(robots)}">'
                   if robots else "")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{THEME_INIT}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">{robots_meta}
<title>{html.escape(title)}</title>
<meta name="description" content="{desc}">
{social}
{FAVICON_LINKS}
<link rel="stylesheet" href="/assets/site.css?v={_CSS_VER}">
<script src="/assets/eephus-nav.js?v={_NAV_VER}" defer></script>
{ACCOUNT_CSS_LINK}
</head>
<body class="eephus-page">
{_nav(active)}
<main class="eephus-wrap">
{body}
</main>
{_footer()}
{ACCOUNT_SCRIPTS}
</body>
</html>
"""

# --------------------------------------------------------------------------- #
# Page builders
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Live PROSPX data (build-time). Reads the same data/*.json PROSPX uses so the
# homepage modules + wire feed regenerate on each build (run after run_monthly).
# --------------------------------------------------------------------------- #
DATA_DIR = ROOT / "data"
ORG_NAMES = {
    "ARI": "Diamondbacks", "ATH": "Athletics", "ATL": "Braves", "BAL": "Orioles",
    "BOS": "Red Sox", "CHC": "Cubs", "CHW": "White Sox", "CIN": "Reds",
    "CLE": "Guardians", "COL": "Rockies", "DET": "Tigers", "HOU": "Astros",
    "KCR": "Royals", "LAA": "Angels", "LAD": "Dodgers", "MIA": "Marlins",
    "MIL": "Brewers", "MIN": "Twins", "NYM": "Mets", "NYY": "Yankees",
    "PHI": "Phillies", "PIT": "Pirates", "SDP": "Padres", "SEA": "Mariners",
    "SFG": "Giants", "STL": "Cardinals", "TBR": "Rays", "TEX": "Rangers",
    "TOR": "Blue Jays", "WSN": "Nationals",
}

# --------------------------------------------------------------------------- #
# eFV grade map (data/xfv.json -> {player_key: headline xfv_grade}).
#
# eFV is the flagship outcome-grounded FV model (the PROSPX primary grade). The
# homepage Top Prospects module historically ranked + displayed CONSENSUS
# `fv_close`; this map lets it lead with eFV instead, with consensus as the
# fallback for any player eFV abstains on (no MiLB track record => absent from
# by_player). Loaded once at module import - missing/corrupt file => empty map,
# so the homepage behaves EXACTLY as before. Since the 2026-07-06 quantile flip
# the DISPLAYED eFV site-wide is `xfv_grade` (RAW, as of the 2026-07-25 unification;
# it was `xfv_grade_quantile` between 2026-07-06 and then) (the model ranking on the
# 20-80 consensus scale; the grade surplus is priced on) - prefer it here so the
# homepage Top Prospects grade matches the PROSPX board and /projections/, with
# the realized grade, then the raw grade, as legacy fallbacks.
def _load_xfv_grades() -> dict:
    try:
        doc = json.loads((DATA_DIR / "xfv.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    try:
        from efv_board_scale import board_value as _scale
    except Exception:                                       # pragma: no cover
        def _scale(rec):
            return (rec or {}).get("xfv_grade")
    out = {}
    for key, rec in (doc.get("by_player") or {}).items():
        rec = rec or {}
        # BASIS REPAIR 2026-07-25. The board was unified on xfv_grade (one number
        # for display, sort and overall_rank - see storage.BOARD_GRADE_FIELD and
        # prospx efvBoardValue), so reading xfv_grade_quantile FIRST here made the
        # homepage Top Prospects module disagree with the board it is supposed to
        # mirror: same player, different FV. Precedence now matches the board exactly.
        # Do not reorder these without changing BOARD_GRADE_FIELD too.
        #
        # W-SIDESCALE 2026-07-25: the board SCALE is owned by efv_board_scale, not by
        # this reader. board_value() re-derives from `xfv_grade_model_raw` when the
        # artifact has been stamped, so the homepage grade equals the prospx board
        # grade for the same player under either state of the flag, and there is no
        # second copy of the coefficients here to drift.
        g = _scale(rec)
        if g is None:
            g = rec.get("xfv_grade_realized")
        if g is None:
            g = rec.get("xfv_grade_quantile")
        if isinstance(g, (int, float)):
            out[key] = float(g)
    return out
_EFV_GRADES = _load_xfv_grades()

def _primary_fv(p: dict):
    """RAW primary FV for a player: the eFV grade when eFV has a grade for this
    player_key, else the consensus close. Consensus is the fallback EVERYWHERE
    so players eFV abstains on are unchanged. Returns a float or None.

    NB: raw (unrounded) - callers that DISPLAY a grade must ceil-round per the
    repo's grades-round-UP rule; sort/tier logic uses the raw value."""
    g = _EFV_GRADES.get(p.get("player_key"))
    if g is not None:
        return g
    fv = p.get("fv_close")
    if fv is None:
        fv = p.get("consensus_fv")
    return fv

def _fmt_iso_date(s: str | None) -> str:
    if not s:
        return " - "
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%B %d, %Y").replace(" 0", " ")
    except ValueError:
        return " - "

def load_site_data() -> dict | None:
    ts_path = DATA_DIR / "timeseries.json"
    if not ts_path.exists():
        return None
    ts = json.loads(ts_path.read_text(encoding="utf-8"))
    grads = []
    dpath = DATA_DIR / "debuts.json"
    if dpath.exists():
        d = json.loads(dpath.read_text(encoding="utf-8"))
        grads = d if isinstance(d, list) else (d.get("players") or d.get("debuts") or [])
    # The homepage surfaces daily-fresh content (movers, transactions,
    # graduates), so its "Data as of" tracks the freshest run (daily refresh
    # when one has happened, else the monthly generated_at).
    fresh = ts.get("data_freshness") or {}
    as_of_iso = fresh.get("transactions_updated_at") or ts.get("generated_at")
    return {
        "as_of": _fmt_iso_date(as_of_iso),
        "players": ts.get("players") or [],
        "org_summary": ts.get("org_summary") or [],
        "graduates": grads,
    }

def _player_href(key: str) -> str:
    # "fa:" keys belong to the Free Agency surface (separate from PROSPX) - 
    # they deep-link the /fa/ player card, not a PROSPX player page.
    if key and key.startswith("fa:"):
        return f"/fa/#player={key[3:]}"
    return f"/prospx/#player={key}" if key else "/prospx/"

# ORG abbreviation -> ESPN logo slug (mirrors ESPN_LOGO_SLUGS in prospx/index.html).
ESPN_SLUGS = {
    "ARI": "ari", "ATH": "ath", "ATL": "atl", "BAL": "bal", "BOS": "bos",
    "CHC": "chc", "CHW": "chw", "CIN": "cin", "CLE": "cle", "COL": "col",
    "DET": "det", "HOU": "hou", "KCR": "kc",  "LAA": "laa", "LAD": "lad",
    "MIA": "mia", "MIL": "mil", "MIN": "min", "NYM": "nym", "NYY": "nyy",
    "PHI": "phi", "PIT": "pit", "SDP": "sd",  "SEA": "sea", "SFG": "sf",
    "STL": "stl", "TBR": "tb",  "TEX": "tex", "TOR": "tor", "WSN": "wsh",
}

def _team_logo(org: str | None, cls: str = "row-logo") -> str:
    """Clean ESPN CDN team logo (falls back to the ORG abbreviation chip).
    `cls` lets callers reuse it at other sizes (e.g. the ticker's tk-logo)."""
    if not org:
        return ""
    o = html.escape(org)
    slug = ESPN_SLUGS.get(org, org.lower())
    return (f'<img class="{cls}" src="https://a.espncdn.com/i/teamlogos/mlb/500/{slug}.png" alt="{o}" loading="lazy" '
            f"onerror=\"this.outerHTML='<span class=&quot;{cls}&quot; style=&quot;font:700 9px var(--font-retro-mono);display:inline-flex;align-items:center;justify-content:center&quot;>{o}</span>'\">")

def _fv_label(p: dict) -> str:
    # Lead with the eFV grade when eFV has graded this player (round-to-NEAREST: eFV is the
    # true-model grade, so it rounds nearest, not up). For players eFV abstains on, keep the
    # EXACT prior behavior: the published consensus label off points[] (which carries
    # snapping / '+' upside), else ceil(fv_close) (consensus FV still rounds up).
    g = _EFV_GRADES.get(p.get("player_key"))
    if g is not None:
        # eFV rounds to NEAREST, HALF-UP -- matching the JS efvGradeDisplay
        # (Math.round) that the PROSPX board + player card + projections all use.
        # Python's built-in round() is banker's (half-to-even), so round(64.5)=64
        # while Math.round(64.5)=65 -> the homepage disagreed with the board on any
        # x.5 grade (e.g. franklin_arias 64.5). math.floor(g+0.5) is half-up for the
        # always-positive 20-80 grade range.
        return str(int(math.floor(g + 0.5)))
    pts = p.get("points") or []
    if pts and pts[-1].get("consensus_fv_label") is not None:
        return str(pts[-1]["consensus_fv_label"])
    fv = p.get("fv_close")
    return str(int(math.ceil(fv))) if fv is not None else " - "

def _fv_tier_class(label: str) -> str:
    """Tier class from the DISPLAYED integer, not the raw grade.

    Keying tiers on the raw grade while printing the rounded one meant the
    number and its colour could disagree: roch_cholowsky (eFV 59.9) printed
    "60" in a plain pill while franklin_arias (60.3) and leo_de_vries (60.2)
    printed the same "60" in gold, and jesus_made (60.9) printed "61" without
    reaching holo. Any raw grade in [59.5, 60) or [60.5, 61) hit this window.

    This is the JS rule (fvClass parses the label it is handed), so the
    generated homepage and the PROSPX board can no longer disagree."""
    m = re.match(r"-?\d+", (label or "").strip())
    if not m:
        return "fv-pill"
    disp = int(m.group())
    if disp >= 61:
        return "fv-pill holo"
    if disp >= 60:
        return "fv-pill gold"
    return "fv-pill"


def _fv_pill(p: dict) -> str:
    label = _fv_label(p)
    return f'<span class="{_fv_tier_class(label)}">{html.escape(label)}</span>'

def _meta(*parts) -> str:
    return html.escape(" · ".join(str(x) for x in parts if x))

# --------------------------------------------------------------------------- #
# Real consensus-grade movement, computed from the player's own points[].
#
# `stock` in timeseries.json is the PERFORMANCE-ANCHORED MOVEMENT ENGINE
# (spotlights.compute_movement): its `delta` is a composite score (perf +
# skills + list-jump + pedigree) and its from/to dates are simply the last two
# snapshots - with daily TJStats Live captures that's "yesterday → today" for
# every active prospect. The homepage was written against the legacy
# stock_movement shape (a true FV delta over a meaningful window) and silently
# broke when storage switched the field to the engine: the wire showed engine
# scores as "▲ +5 FV" items dated at the latest Live refresh. These helpers
# read the published grade history directly so a "+N FV" on the homepage is
# always a real grade change - and wire items are dated when the consensus
# actually moved, not when a daily capture re-confirmed it.
# --------------------------------------------------------------------------- #
def _label_series(p: dict) -> list[tuple[str, int]]:
    """(snapshot_date, consensus grade as int) per point, oldest → newest."""
    out = []
    for pt in (p.get("points") or []):
        d = pt.get("snapshot_date")
        try:
            v = int(round(float(pt.get("consensus_fv_label"))))
        except (TypeError, ValueError):
            continue
        if d:
            out.append((str(d)[:10], v))
    return out

def _fv_window_delta(p: dict, days: int = 365) -> int | None:
    """Consensus-grade change over the trailing window (label units). Anchor
    mirrors consensus.stock_movement v12: latest grade minus the grade at the
    snapshot closest to (latest − days) without crossing it; falls back to the
    earliest snapshot when history is shorter than the window."""
    series = _label_series(p)
    if len(series) < 2:
        return None
    last_d, last_v = series[-1]
    try:
        cutoff = date.fromisoformat(last_d) - timedelta(days=days)
    except ValueError:
        return last_v - series[-2][1]
    prior_v = series[0][1]
    for d, v in series[:-1]:
        try:
            if date.fromisoformat(d) <= cutoff:
                prior_v = v
            else:
                break
        except ValueError:
            continue
    return last_v - prior_v

def _latest_fv_change(p: dict) -> tuple[str, int, int] | None:
    """The most recent ACTUAL grade change as (date_of_change, step,
    new_grade). None when the published grade has never moved. This is what
    the wire treats as FV news - daily Live re-confirmations of an unchanged
    grade are not events.

    CAUTION: when the change pair ends at the rolling daily Live point, the
    returned date is that point's snapshot_date - which the daily capture
    RE-STAMPS to today on every run. The wire must not consume it raw (a
    player would ride the most-recent-day bucket forever); _collect_events
    pins it through the first-seen ledger below."""
    series = _label_series(p)
    for i in range(len(series) - 1, 0, -1):
        prev_v = series[i - 1][1]
        cur_d, cur_v = series[i]
        if cur_v != prev_v:
            return (cur_d, cur_v - prev_v, cur_v)
    return None


# First-seen ledger for wire FV items (the fa_events stamping pattern).
# The daily Live snapshot re-dates its point every run, so a grade change
# detected against it would re-date daily and pin the player to the wire's
# most-recent-day bucket indefinitely (Cleiner Ramirez, 3 straight days,
# 2026-06-12 report). The ledger records the date each (player, new grade)
# was FIRST published and serves that date forever after.
_WIRE_FV_LEDGER = DATA_DIR / "wire_fv_first_seen.json"

def _wire_fv_first_seen(ledger: dict, key: str, new_fv: int, seen_date: str) -> str:
    entry = ledger.get(key)
    if entry and entry.get("fv") == new_fv:
        return entry["first_seen"]
    ledger[key] = {"fv": new_fv, "first_seen": seen_date}
    return seen_date

def _load_wire_fv_ledger() -> dict:
    try:
        d = json.loads(_WIRE_FV_LEDGER.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}

def _save_wire_fv_ledger(ledger: dict, live_keys: set) -> None:
    """Prune departed players, write only on real change (stable output so
    test runs and no-op rebuilds never churn the committed file)."""
    pruned = {k: v for k, v in sorted(ledger.items()) if k in live_keys}
    raw = json.dumps(pruned, indent=0, sort_keys=True)
    try:
        if _WIRE_FV_LEDGER.exists() and _WIRE_FV_LEDGER.read_text(encoding="utf-8") == raw:
            return
    except OSError:
        pass
    _WIRE_FV_LEDGER.write_text(raw, encoding="utf-8")

_HOME_MOVER_RECENCY_DAYS = 365

def _genuine_mover_step(p: dict) -> int | None:
    """Homepage Top Movers selector: the de-noised grade step from the movement
    engine (carried on `stock`), gated to genuine, recent moves.

    eFV is the site's primary grade, so the PRIMARY mover signal is the eFV
    "since last real change" step (basis="xfv"): the eFV trajectory already
    de-bands (walks back to the last >=0.5 step), so an eFV move IS a genuine
    move and needs no source-confidence gate. Where a player has no eFV history
    the engine falls back to the de-noised same-source consensus step
    (basis="same_source"), which DOES keep its confidence gate (it excludes
    panel-composition shifts and lone-outlier re-grades). Because the homepage
    module is a recency surface ("moving now"), the step must have landed within
    the trailing year. Returns the signed integer grade step (>=2 in magnitude)
    or None. The per-player stock chips keep showing each player's last real move
    regardless of age; this module is the recent-movers view."""
    st = p.get("stock") or {}
    basis = st.get("basis")
    if st.get("delta") is None or st.get("direction") in ("flat", "debuted", None):
        return None
    if basis == "xfv":
        pass                                          # eFV step is self-de-noised
    elif basis == "same_source":
        if st.get("confidence") not in ("high", "medium"):
            return None
    else:
        return None
    try:
        moved = date.fromisoformat(str(st.get("to_date"))[:10])
    except (TypeError, ValueError):
        return None
    if moved < date.today() - timedelta(days=_HOME_MOVER_RECENCY_DAYS):
        return None
    step = int(round(st["delta"]))
    return step if abs(step) >= 2 else None

def _row_mover(p: dict, d: int) -> str:
    up = d > 0
    # Mini FV-history sparkline - reinforces the stock-chart identity. Colored
    # by direction; the curve stays smooth (the sharp-corner rule is for UI
    # chrome, not plotted lines).
    spark = _fv_sparkline(p.get("points"), "var(--accent-green)" if up else "var(--accent-red)", w=58, h=20)
    spark_html = f'<span class="row-spark">{spark}</span>' if spark else '<span class="row-spark"></span>'
    # Rank + team logo lead the row (same idiom as Top Prospects); position +
    # FV chip sit before the move delta so a mover reads like a ranked entry
    # with its grade, not just an arrow. Rank slot stays present (blank) when a
    # player has no overall rank so the columns line up.
    rank = p.get("overall_rank")
    rank_html = f'<span class="row-rank">{rank}</span>' if rank else '<span class="row-rank"></span>'
    return (f'<a class="row-link" href="{_player_href(p.get("player_key"))}">'
            f'{rank_html}{_team_logo(p.get("org"))}'
            f'<span class="row-name">{html.escape(p.get("player_name") or "")}</span>'
            f'<span class="row-meta">{_meta(p.get("position"))}</span>'
            f'{spark_html}{_fv_pill(p)}'
            f'<span class="row-delta {"up" if up else "down"}">{"▲" if up else "▼"} {"+" if up else ""}{d}</span></a>')

def _row_top(p: dict, rank: int) -> str:
    return (f'<a class="row-link" href="{_player_href(p.get("player_key"))}">'
            f'<span class="row-rank">{rank}</span>{_team_logo(p.get("org"))}'
            f'<span class="row-name">{html.escape(p.get("player_name") or "")}</span>'
            f'<span class="row-meta">{_meta(p.get("position"))}</span>{_fv_pill(p)}</a>')

def display_metric_for(p: dict) -> dict:
    """Single source of truth for which realized metric a player's shared
    "value" slot shows. The metric ESCALATES with on-field information:

      graduated to MLB          -> WAR  (career-since-debut bWAR + WAR/yr)
      prospect, settled sample  -> WAG  (regressed WAR-above-grade)
      prospect / no real sample -> FV   (the scouting-consensus projection)

    Why: WAG (WAR Above Grade) is only meaningful once a real sample has
    stabilized. It is misleading on a graduate (who now has actual MLB WAR to
    show) and on a prospect who hasn't played a pro season. So a graduate shows
    WAR, and a sub-threshold prospect shows FV - never a WAG number.

    The sample gate is the WAG model's OWN `below_meaningful_exposure` flag
    (config wag.meaningful_exposure = 200 PA / 80 IP ≈ ⅓ season); display and
    methodology share one source of truth rather than a re-invented threshold.

    NB on the data model: WAG (`debuted_value.wag`) is computed FROM a player's
    MLB sample, so in practice only graduates carry one - the WAG branch below is
    reachable only if a pre-graduation WAG is ever added; today every WAG-carrier
    graduates to the WAR branch. That is intended, not dead weight.

    Returns {metric: 'WAR'|'WAG'|'FV'|None, cls, html} - `metric` labels the
    value so a number sitting in a shared slot is never mistaken for another now
    that the slot can hold any of three. `html` is render-ready and HTML-safe."""
    cw = p.get("career_war") or {}
    is_grad = (p.get("status") == "debuted") or (cw.get("career_war") is not None)

    # 1) Graduated -> raw MLB WAR (career-since-debut bWAR). WAR/yr stays in
    # the hover tooltip only - as a visible suffix it was noise on the
    #    homepage grad rows, where most players have one partial MLB season
    #    and the per-year rate is just the WAR number echoed back.
    if is_grad:
        war = cw.get("career_war")
        if war is None:
            # bWAR hasn't posted yet (brand-new debut) - keep it a WAR slot and be
            # honest the sample hasn't landed; never fabricate a number.
            return {"metric": "WAR", "cls": "flat",
                    "html": '<span class="row-meta" title="MLB WAR not yet posted"> - WAR</span>'}
        war_r = round(war, 1) + 0.0          # collapse -0.0
        cls = "up" if war_r > 0 else ("down" if war_r < 0 else "flat")
        wpy = cw.get("war_per_yr")
        nseas = cw.get("war_seasons_count")
        title = f"{war_r:.1f} career bWAR"
        if isinstance(wpy, (int, float)):
            title += f" · {wpy:.2f}/yr"
        if nseas:
            title += f" · {nseas} MLB season{'s' if nseas != 1 else ''}"
        return {"metric": "WAR", "cls": cls,
                "html": (f'<span class="row-delta {cls}" title="{html.escape(title)}">'
                         f'{war_r:.1f} WAR</span>')}

    # 2) Still a prospect with a SETTLED sample -> WAG (WAR above grade).
    wag = (p.get("debuted_value") or {}).get("wag") or {}
    rw = wag.get("regressed_wag")
    if rw is not None and not wag.get("below_meaningful_exposure"):
        wag_r = round(rw, 1) + 0.0
        cls = "up" if wag_r > 0 else ("down" if wag_r < 0 else "flat")
        sign = "+" if wag_r > 0 else ""      # negatives carry their own '-'; zero is unsigned
        return {"metric": "WAG", "cls": cls,
                "html": f'<span class="row-delta {cls}">{sign}{wag_r:.1f} WAG</span>'}

    # 3) No meaningful on-field sample yet -> FV (PRIMARY: eFV when graded, else
    #    the scouting consensus). `_primary_fv` already falls back fv_close ->
    #    consensus_fv; keep `fv` as a last-ditch legacy fallback.
    fv = _primary_fv(p) or p.get("fv")
    if fv is not None:
        return {"metric": "FV", "cls": "flat",
                "html": (f'<span class="row-meta" title="Final prospect FV - no MLB sample yet">'
                         f'FV {int(round(fv))}</span>')}   # eFV-primary -> rounds to NEAREST
    return {"metric": None, "cls": "flat", "html": '<span class="row-meta">debut</span>'}


def _row_grad(g: dict) -> str:
    # "Recent Debuts": overall rank + the debut date (same compact gold stamp
    # as Today in Prospect History) + the player's final prospect FV. Career
    # WAR / WAG still live on the player + Debuted pages.
    rank = g.get("overall_rank")
    rank_html = f'<span class="row-rank">{rank}</span>' if rank else '<span class="row-rank"></span>'
    date_html = ""
    dd = g.get("debut_date")
    if dd:
        try:
            date_html = f'<span class="otd-when">{html.escape(_otd_date(date.fromisoformat(str(dd)[:10])))}</span>'
        except ValueError:
            pass
    return (f'<a class="row-link" href="{_player_href(g.get("player_key"))}">'
            f'{rank_html}{date_html}{_team_logo(g.get("org"))}'
            f'<span class="row-name">{html.escape(g.get("player_name") or "")}</span>'
            f'<span class="row-meta">{_meta(g.get("position"))}</span>{_fv_pill(g)}</a>')

def _recent_trades_html(players: list, n: int = 5) -> str:
    """'Recent Trades' module - the latest prospect trades from the tracked
    pool, newest first. Top 5, to sit level with Recent Graduates in the
    bottom grid row."""
    trs = []
    for p in players:
        for tr in (p.get("trades") or []):
            dt = str(tr.get("trade_date") or "")[:10]
            if len(dt) == 10:
                trs.append((dt, p, tr))
    # Recency floor mirrors the Top Movers window so "Recent Trades" can't show a
    # year-old deal as recent; ISO date strings compare lexicographically. With
    # nothing recent the module returns "" and drops out of the grid entirely.
    cutoff = (date.today() - timedelta(days=_HOME_MOVER_RECENCY_DAYS)).isoformat()
    trs = [t for t in trs if t[0] >= cutoff]
    if not trs:
        return ""
    trs.sort(key=lambda t: t[0], reverse=True)
    rows = []
    for dt, p, tr in trs[:n]:
        frm = html.escape(tr.get("from_org") or "?")
        to = html.escape(tr.get("to_org") or "?")
        rank = p.get("overall_rank")
        rank_html = f'<span class="row-rank">{rank}</span>' if rank else '<span class="row-rank"></span>'
        # From -> to as team logos (same idiom as Today in Prospect History's
        # trade rows), replacing the old "FRM ⇄ TO" text.
        logos = (f'<span class="trade-logos" title="Traded {frm} → {to}">'
                 f'{_team_logo(tr.get("from_org"), "otd-logo")}'
                 f'<span class="otd-arrow">→</span>'
                 f'{_team_logo(tr.get("to_org"), "otd-logo")}</span>')
        rows.append(
            f'<a class="row-link" href="{_player_href(p.get("player_key"))}">'
            f'{rank_html}{logos}'
            f'<span class="row-name">{html.escape(p.get("player_name") or "")}</span>'
            f'<span class="row-meta">{_meta(p.get("position"))}</span>'
            f'<span class="row-meta">{dt[5:7]}/{dt[8:10]}</span>'
            # FV chip trails the row so it lines up with the Recent Debuts
            # FV column beside it (both modules end with a flush-right pill).
            f'{_fv_pill(p)}</a>'
        )
    return _home_module("Recent Trades", "/prospx/#tab=traded", "All transactions", "".join(rows))

def _row_farm(o: dict, rank: int) -> str:
    # Match the PROSPX board: it shows the trailing-window letter (7y default)
    # first, falling back to the canonical overall grade. Both sides read the
    # same org_summary objects, so the homepage must use the same lookup.
    grade = ((o.get("letter_by_window") or {}).get("7y")
             or (o.get("grades") or {}).get("overall") or " - ")
    gcls = " gold" if str(grade).startswith("A") else ""
    name = ORG_NAMES.get(o.get("org"), o.get("org") or " - ")
    return (f'<a class="row-link" href="/prospx/#farm-org={html.escape(o.get("org") or "")}">'
            f'<span class="row-rank">{rank}</span>{_team_logo(o.get("org"))}'
            f'<span class="row-name">{html.escape(name)}</span>'
            f'<span class="row-meta">{o.get("count", "")} prospects</span>'
            f'<span class="fv-pill{gcls}">{html.escape(str(grade))}</span></a>')

# One mass re-grade (a single source dropping a 17-player international list)
# would otherwise fill the entire 12/14-item wire by itself; cap FV items per
# day (biggest grade steps win) so debuts / promotions / IL news from the same
# window keep their slots.
_WIRE_MAX_FV_PER_DAY = 6

@functools.lru_cache(maxsize=None)
def _cached_data_json(name: str) -> dict:
    """Parse a build-time JSON sidecar at most once per build. The home
    wire (_load_fa_events_for_wire) and the cross-module strip both read
    fa_class.json / mlb_projections.json; without this they were parsed
    twice each run. Committed sidecars don't change mid-build, so the cache
    is safe - callers must treat the result as read-only (shared instance)."""
    try:
        return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

def _load_fa_events_for_wire() -> list:
    """Recent winter events from the FA module's own export (the events
    block in data/fa_class.json). Additive: an absent or pre-events export
    just yields no items. Dates are the pipeline's first-seen stamps."""
    return _cached_data_json("fa_class.json").get("events") or []

def _collect_events(players: list, graduates: list, fa_events: list | None = None) -> list:
    # Each event is (date, typ, glyph, ticker_text, key, org, name, val):
    # `ticker_text` is the one-string form the scrolling WIRE marquee uses;
    # `name`/`val` are the structured halves the sidebar feed lays out as
    # name-left / value-right (PROSPX row idiom - no wrapping, scannable).
    # Internally a trailing weight orders same-date items editorially - 
    # debut > trade > promo/demo > IL > FV, bigger grade steps leading the
    # FV items. Stripped before return.
    ev = []
    def add(dt, typ, glyph, text, key, org=None, name="", val="", weight=0):
        if dt:
            ev.append((str(dt)[:10], typ, glyph, text, key, org, name, val, weight))
    fv_items = []
    fv_ledger = _load_wire_fv_ledger()
    for p in players:
        nm = p.get("player_name") or ""
        key = p.get("player_key")
        org = p.get("org")
        # FV news = the most recent GENUINE grade move carried on stock. Two
        # bases qualify: "xfv" (the live PRIMARY grade - movement.py emits a
        # numeric delta with a string "eFV NN.N" to_label) and the legacy
        # "same_source" consensus move (only sources grading the player at both
        # endpoints count, gated on high/medium confidence). Panel-composition
        # shifts (basis "panel_update") and thin samples (confidence "low")
        # never reach the wire. Dated at FIRST SIGHT via the ledger (the raw
        # change date rides the daily Live point and re-stamps to today every
        # run - see _latest_fv_change CAUTION). When stock is absent (older
        # payloads / tests), fall back to the raw grade-change detector.
        mv = p.get("stock") or {}
        chg = None
        if p.get("status") != "debuted":
            if (mv.get("basis") == "same_source" and mv.get("delta") is not None
                    and mv.get("direction") not in ("flat", "debuted")
                    and mv.get("confidence") in ("high", "medium")):
                step = int(round(mv["delta"]))
                try:
                    new_grade = int(round(float(mv.get("to_label"))))
                except (TypeError, ValueError):
                    new_grade = None
                if abs(step) >= 2 and new_grade is not None:
                    chg = (str(mv.get("to_date"))[:10], step, new_grade)
            elif (mv.get("basis") == "xfv" and mv.get("delta") is not None
                    and mv.get("direction") not in ("flat", "debuted")):
                step = int(round(mv["delta"]))
                # to_label is the string "eFV NN.N" for the xfv basis; pull the
                # number out and round it to nearest (eFV is the true-model grade).
                _m = re.search(r"-?\d+(?:\.\d+)?", str(mv.get("to_label") or ""))
                try:
                    new_grade = int(round(float(_m.group()))) if _m else None
                except (TypeError, ValueError):
                    new_grade = None
                if abs(step) >= 2 and new_grade is not None:
                    chg = (str(mv.get("to_date"))[:10], step, new_grade)
            elif "stock" not in p:
                raw = _latest_fv_change(p)
                if raw and abs(raw[1]) >= 2:
                    chg = (str(raw[0])[:10], raw[1], raw[2])
        if chg:
            d_first = _wire_fv_first_seen(fv_ledger, key, chg[2], chg[0])
            fv_items.append((d_first, chg[1], nm, key, org))
        for lc in (p.get("level_changes") or []):
            if lc.get("kind") in ("promotion", "demotion"):
                promo = lc["kind"] == "promotion"
                lvls = f'{lc.get("from_level", "?")}→{lc.get("to_level", "?")}'
                add(lc.get("date"), "promo" if promo else "demo", "↑" if promo else "↓",
                    f'{nm} {"promoted" if promo else "demoted"} {lvls}', key, org,
                    name=nm, val=lvls, weight=80)
        for tr in (p.get("trades") or []):
            orgs = f'{tr.get("from_org", "?")}→{tr.get("to_org", "?")}'
            add(tr.get("trade_date"), "trade", "⇄", f'{nm} traded {orgs}', key,
                tr.get("to_org") or org, name=nm, val=orgs, weight=90)
        il = p.get("il_status") or {}
        if il.get("is_on_il") and il.get("since"):
            il_label = f'{il.get("type", "")} IL'.strip()
            add(il.get("since"), "il", "✚", f'{nm} to {il_label}', key, org,
                name=nm, val=il_label, weight=70)
    _save_wire_fv_ledger(fv_ledger, {p.get("player_key") for p in players})
    for g in graduates:
        add(g.get("debut_date"), "debut", "★", f'{g.get("player_name", "")} debuted · {g.get("org", "")}',
            g.get("player_key"), g.get("org"),
            name=g.get("player_name") or "", val="debut", weight=100)
    # Free-agency winter events (signings / option resolutions / QOs) from
    # the FA module's export. "fa:"-prefixed keys route to /fa/, never to a
    # PROSPX player page; the signing org carries the logo.
    for e in (fa_events or []):
        nm = e.get("name") or ""
        key = f'fa:{e.get("key", "")}'
        t = e.get("type")
        if t == "signing":
            terms = ("MiLB deal" if e.get("milb")
                     else f'{e.get("years", "?")}y/${(e.get("guar") or 0) / 1e6:.0f}M')
            add(e.get("date"), "signing", "✎", f'{nm} signs · {e.get("to", "?")} {terms}',
                key, e.get("to"), name=nm, val=terms, weight=95)
        elif t == "option_declined":
            add(e.get("date"), "signing", "✎", f'{nm} declines option - enters FA class',
                key, e.get("from"), name=nm, val="opt-out → FA", weight=85)
        elif t == "option_exercised":
            add(e.get("date"), "signing", "✎", f'{nm} option exercised - off the FA board',
                key, e.get("from"), name=nm, val="option exercised", weight=85)
        elif t == "qo_offered":
            add(e.get("date"), "signing", "✎", f'{nm} receives qualifying offer',
                key, e.get("from"), name=nm, val="QO offered", weight=84)
    # TJStats board movers are intentionally NOT folded into the wire/ticker
    # (owner ask 2026-06-13). tjstats.export_movers still writes the movers
    # sidecar + source events for the consensus; only the wire display drops.
    by_day: dict[str, list] = {}
    for it in fv_items:
        by_day.setdefault(it[0], []).append(it)
    for day, items in by_day.items():
        items.sort(key=lambda t: -abs(t[1]))
        for d8, step, nm, key, org in items[:_WIRE_MAX_FV_PER_DAY]:
            up = step > 0
            val = f'{"+" if up else ""}{step} FV'
            add(d8, "up" if up else "down", "▲" if up else "▼",
                f'{nm} {"▲" if up else "▼"} {val}', key, org,
                name=nm, val=val, weight=abs(step))
    ev.sort(key=lambda e: (e[0], e[8]), reverse=True)
    return [e[:8] for e in ev]

# Event type -> coarse filter category for the /news/ page filter chips.
_EVENT_CAT = {"debut": "debut", "trade": "trade", "promo": "move", "demo": "move",
              "il": "il", "up": "fv", "down": "fv", "signing": "signing"}

def _feed_day_header(dt: str, gfx: bool = False) -> str:
    """One thin date header row that deep-links into Time Machine at that date
    (the full board as of that day). Shared by the homepage feed + /news/.
    gfx=True (the /news/ page only) adds a per-date Generate GFX chip that
    renders THAT day's items - all of them - as a shareable card (the
    data-gfx-date delegation in _NEWS_GFX_JS wires it to the shared engine)."""
    ts = f"{dt[5:7]}/{dt[8:10]}" if len(dt) >= 10 else dt
    btn = ""
    if gfx and len(dt) >= 10:
        md = f"{int(dt[5:7])}/{int(dt[8:10])}"
        btn = (f'<button class="chip egfx-chip egfx-day-chip" type="button" data-gfx-date="{dt}" '
               f'title="Generate a shareable graphic of every news item from {dt}">'
               f'<span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>GFX {md}</button>')
    return (f'<div class="feed-day"><span class="feed-day-date">{ts}</span>'
            f'{btn}'
            f'<a class="feed-day-tm" href="/prospx/#tab=timemachine&tm={dt}" '
            f'title="Time Machine - the full board as of {dt}">Time Machine →</a></div>')

def _feed_item_html(typ, glyph, text, key, org, name, val, cat: str = "") -> str:
    """One wire row: logo | name (ellipsized) | colored value chip. The type
    glyph lives only in the value chip. `cat` (optional) tags the row for the
    /news/ filter chips. Shared by the homepage feed + the /news/ page."""
    logo = _team_logo(org, "feed-logo") if org else ""
    data_cat = f' data-cat="{html.escape(cat)}"' if cat else ""
    return (f'<a class="feed-item" href="{_player_href(key)}"{data_cat}>'
            f'{logo}<span class="feed-name">{html.escape(name or text)}</span>'
            f'<span class="feed-val {typ}">{glyph} {html.escape(val)}</span></a>')

def _news_detail(p: dict, typ: str) -> str:
    """Scouting line under a player's name on the /news/ page: position, age,
    overall rank, and ETA - or career WAR for a debut. Empty when the event has
    no resolved player record (e.g. FA signings, keyed off the PROSPX map)."""
    if not p:
        return ""
    parts = []
    if p.get("position"):
        parts.append(str(p["position"]))
    if p.get("age") is not None:
        parts.append(f'{p["age"]:.1f} yo')
    if p.get("overall_rank"):
        parts.append(f'#{int(p["overall_rank"])}')
    if typ == "debut":
        cw = p.get("career_war")
        war = cw.get("career_war") if isinstance(cw, dict) else cw
        if war is not None and abs(war) >= 0.1:  # skip the +0.0 of a fresh debut
            parts.append(f"{war:+.1f} career WAR")
    else:
        yr = (p.get("eta") or {}).get("year")
        if yr:
            parts.append(f"ETA {yr}")
    return _meta(*parts)

def _news_item_html(typ, glyph, text, key, org, name, val, cat, pmap) -> str:
    """Richer /news/ row: logo | name + scouting line | current-FV chip | event
    chip. Reuses _feed_item_html's classes so it inherits the wire palette; the
    detail line + FV pill are scoped to .news-feed in CSS, so the homepage
    sidebar wire is untouched. `pmap` maps player_key -> record (players +
    graduates); rows with no match (FA signings) degrade to the plain layout."""
    logo = _team_logo(org, "feed-logo") if org else ""
    data_cat = f' data-cat="{html.escape(cat)}"' if cat else ""
    p = pmap.get(key) if pmap else None
    detail = _news_detail(p, typ)
    meta = f'<span class="news-meta">{detail}</span>' if detail else ""
    fv = _fv_pill(p) if (p and p.get("fv_close") is not None) else ""
    return (f'<a class="feed-item news-item" href="{_player_href(key)}"{data_cat}>'
            f'{logo}'
            f'<span class="news-main"><span class="feed-name">{html.escape(name or text)}</span>{meta}</span>'
            f'{fv}'
            f'<span class="feed-val {typ}">{glyph} {html.escape(val)}</span></a>')

def _feed_html(events: list, n: int = 12) -> str:
    # Day-grouped wire (homepage sidebar): a thin per-date header carries the
    # timestamp + Time Machine link; rows are structured logo|name|value chip.
    out = []
    last_day = None
    for dt, typ, glyph, text, key, org, name, val in events[:n]:
        if dt != last_day:
            last_day = dt
            out.append(_feed_day_header(dt))
        out.append(_feed_item_html(typ, glyph, text, key, org, name, val))
    return "".join(out)

def _ticker_html(events: list, n: int = 14) -> str:
    # Each item is a mouse-clickable link to the player (or spotlights), color-
    # coded by type. tabindex=-1 keeps it out of the keyboard/AT path - the
    # ticker is aria-hidden decoration; the sidebar Prospect Wire feed is the
    # accessible, keyboard-navigable equivalent.
    items = []
    known = ("up", "down", "promo", "demo", "il", "debut", "trade", "signing")
    for dt, typ, glyph, text, key, org, name, val in events[:n]:
        cls = typ if typ in known else "glyph"
        href = _player_href(key) if key else "/prospx/#tab=spotlights"
        logo = _team_logo(org, "tk-logo") if org else ""
        items.append(f'<a href="{html.escape(href)}" tabindex="-1">{logo}'
                     f'<span class="{cls}">{glyph}</span> {html.escape(text)}</a>')
    if not items:
        items = ['<span><span class="glyph">◆</span> PROSPX - live prospect wire</span>']
    return " ".join(items * 2)  # duplicated for seamless scroll

def _news_recent_events(events: list, window_days: int = 30,
                        max_items: int = 500, min_items: int = 60) -> list:
    """The /news/ page's event window: recent activity, falling back to the
    most-recent `min_items` when the window is sparse (off-season). Shared by
    the rendered feed and the Generate GFX data blob so the graphic always
    digests exactly the feed the reader is looking at."""
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    recent = [e for e in events if e[0] >= cutoff]
    if len(recent) < min_items:
        recent = events[:min_items]
    return recent[:max_items]

def _news_feed_html(events: list, pmap: dict | None = None) -> str:
    """Day-grouped feed for the standalone /news/ page: a richer row than the
    homepage sidebar (name + scouting line + current-FV chip), windowed to
    recent activity and tagged with data-cat so the filter chips can show/hide
    by category. Each day is wrapped in a .news-day block so a filtered-empty
    day hides cleanly. `pmap` resolves player_key -> record for the detail."""
    recent = _news_recent_events(events)
    out = []
    last_day = None
    open_day = False
    for dt, typ, glyph, text, key, org, name, val in recent:
        if dt != last_day:
            if open_day:
                out.append("</div>")
            last_day = dt
            out.append('<div class="news-day">')
            out.append(_feed_day_header(dt, gfx=True))
            open_day = True
        out.append(_news_item_html(typ, glyph, text, key, org, name, val,
                                   _EVENT_CAT.get(typ, ""), pmap))
    if open_day:
        out.append("</div>")
    return "".join(out)

# Tiny dependency-free filter for the /news/ chips: toggles row visibility by
# data-cat and hides any day block left with no visible items (mirrors the
# glossary/FA static-page chip idiom).
_NEWS_FILTER_JS = """<script>
(function(){
  var bar=document.getElementById('news-filter-bar'),feed=document.getElementById('news-feed');
  if(!bar||!feed)return;
  var empty=null;
  bar.addEventListener('click',function(e){
    var b=e.target.closest('[data-news-filter]');if(!b)return;
    var f=b.getAttribute('data-news-filter');
    bar.querySelectorAll('[data-news-filter]').forEach(function(x){x.classList.toggle('active',x===b);});
    var shown=0;
    feed.querySelectorAll('.news-day').forEach(function(day){
      var any=false;
      day.querySelectorAll('.feed-item').forEach(function(it){
        var show=(f==='all')||it.getAttribute('data-cat')===f;
        it.style.display=show?'':'none';if(show){any=true;shown++;}
      });
      day.style.display=any?'':'none';
    });
    if(!empty){
      empty=document.createElement('div');
      empty.className='news-empty';
      empty.style.cssText='padding:2rem 1rem;text-align:center;color:var(--text-tertiary,#888);';
      feed.appendChild(empty);
    }
    if(shown===0){empty.textContent='No items in this category.';empty.style.display='';}
    else{empty.style.display='none';}
  });
})();
</script>"""

# Server-rendered "Generate GFX" chip - mirrors EEPHUS_GFX.chipHTML() (the
# engine loads deferred, so the static page ships the chip itself and the
# inline wire-up below just listens for the click).
def _gfx_chip_html(chip_id: str) -> str:
    return (f'<button class="chip egfx-chip" id="{chip_id}" type="button" '
            'title="Generate a shareable graphic (theme-aware, multiple formats)">'
            '<span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>Generate GFX</button>')

def _news_gfx_blob(recent: list, pmap: dict, max_events: int | None = None) -> str:
    """The /news/ Generate GFX data model: the current feed's events as a
    compact JSON list of {date, typ, glyph, name, pos, org, val, mlbam?,
    pctx?, logo?}, embedded as an inert application/json script the digest
    AND per-date specs read client-side. Carries the SAME windowed list the
    rendered feed shows (the per-date card contract: every item from that
    date, nothing silently dropped), so no cap beyond the feed's own window.
    mlbam + pctx let the client rebuild the resolved headshot URL (the
    _headshot_url chain: pctx '67'/'milb' = the real photo context; absent =
    the generic-overlay form); logo is the org's ESPN CDN logo slug."""
    items = []
    for dt, typ, glyph, text, key, org, name, val in (
            recent if max_events is None else recent[:max_events]):
        p = pmap.get(key) or {}
        it = {"date": dt, "typ": typ, "glyph": glyph,
              "name": name or text, "pos": p.get("position") or "",
              "org": org or "", "val": val}
        mlbam = p.get("mlbam_id")
        if mlbam:
            it["mlbam"] = mlbam
            ctx = _PHOTO_CTX.get(str(mlbam))
            if ctx in ("67", "milb"):
                it["pctx"] = ctx
        if org and org in ESPN_SLUGS:
            it["logo"] = ESPN_SLUGS[org]
        items.append(it)
    blob = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    # "</" would terminate the script element mid-blob; the JSON-safe escape keeps it inert.
    return ('<script type="application/json" id="news-gfx-data">'
            + blob.replace("</", "<\\/") + "</script>")

# Inline wire-up for the /news/ Generate GFX affordances: the header chip
# builds the whole-digest board spec; each date header's "GFX m/d" chip builds
# a per-date card spec (kind:"newsday") that renders EVERY item from that date
# with headshots + team logos. Both read the embedded data blob and hand off
# to the shared EEPHUS_GFX engine (same modal the FA / Projections surfaces
# use). Twitter-card 1200px width; the per-date card grows taller as needed.
_NEWS_GFX_JS = """<script>
(function(){
  var el=document.getElementById('news-gfx-data'),evs=[];
  try{evs=JSON.parse(el?el.textContent:'[]')||[];}catch(e){}
  var TYPE={debut:'Debut',trade:'Trade',promo:'Promo',demo:'Demo',il:'IL',
            up:'FV up',down:'FV down',signing:'Signing'};
  var CLR={up:'pos',down:'neg',il:'neg',debut:'accent'};
  var CDN='https://img.mlbstatic.com/mlb-photos/image/upload/';
  function shotURL(e){
    if(!e.mlbam)return null;
    if(e.pctx)return CDN+'w_96,q_auto:best/v1/people/'+e.mlbam+'/headshot/'+e.pctx+'/current';
    return CDN+'d_people:generic:headshot:67:current.png/w_96,q_auto:best/v1/people/'+e.mlbam+'/headshot/67/current';
  }
  function logoURL(e){
    return e.logo?'https://a.espncdn.com/i/teamlogos/mlb/500/'+e.logo+'.png':null;
  }
  function mdOf(d){return d.length>=10?(+d.slice(5,7))+'/'+(+d.slice(8,10)):d;}
  function _newsDigestSpec(){
    var rows=evs.map(function(e){
      var sub=[e.pos,e.org].filter(Boolean).join(' - ');
      return {cells:[
        {t:mdOf(String(e.date||''))},
        {t:TYPE[e.typ]||e.typ||''},
        {t:e.name||'',sub:sub},
        {t:(e.glyph?e.glyph+' ':'')+(e.val||''),c:CLR[e.typ]}
      ]};
    });
    var now=new Date();
    var mon=now.toLocaleDateString('en-US',{month:'short',day:'numeric'});
    var iso=now.getFullYear()+'-'+String(now.getMonth()+1).padStart(2,'0')+'-'+
            String(now.getDate()).padStart(2,'0');
    return {kind:'board',module:'Prospect News',accentToken:'--accent-lilac',
      title:'Prospect News - '+mon,
      subtitle:evs.length+' moves - debuts, trades, promos, FV',
      url:'eephus.io/news',filenameBase:'prospect-news-'+iso,format:'twitter',
      board:{defaultCount:25,counts:[10,25,50],columns:[
        {label:'Date',frac:0.10},
        {label:'Type',frac:0.15},
        {label:'Player',frac:0.45},
        {label:'Event',frac:0.30}
      ],rows:rows}};
  }
  function _newsDaySpec(day){
    var items=evs.filter(function(e){return String(e.date||'').slice(0,10)===day;})
      .map(function(e){
        return {name:e.name||'',sub:[e.pos,e.org].filter(Boolean).join(' - '),
                type:TYPE[e.typ]||e.typ||'',
                val:(e.glyph?e.glyph+' ':'')+(e.val||''),c:CLR[e.typ]||null,
                shot:shotURL(e),logo:logoURL(e)};
      });
    var dt=new Date(day+'T12:00:00');
    var lbl=isNaN(+dt)?day:dt.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
    return {kind:'newsday',module:'Prospect News',accentToken:'--accent-lilac',
      title:'Prospect News - '+lbl,dateLabel:lbl,
      subtitle:items.length+(items.length===1?' update':' updates')+' - every move from this date',
      url:'eephus.io/news',filenameBase:'prospect-news-'+day,items:items};
  }
  var chip=document.getElementById('news-gfx-chip');
  if(chip)chip.addEventListener('click',function(){
    if(window.EEPHUS_GFX)window.EEPHUS_GFX.open(_newsDigestSpec());
  });
  var feed=document.getElementById('news-feed');
  if(feed)feed.addEventListener('click',function(ev){
    var b=ev.target.closest('[data-gfx-date]');
    if(b&&window.EEPHUS_GFX)window.EEPHUS_GFX.open(_newsDaySpec(b.getAttribute('data-gfx-date')));
  });
})();
</script>"""

def build_news(data: dict | None = None) -> str:
    """/news/ - the expanded Prospect News page: the full recent event feed
    (debuts, trades, promotions/demotions, IL, FV grade changes, FA signings),
    day-grouped with category filter chips. Same event pipeline + row markup as
    the homepage sidebar feed, just a wider window. Reached by clicking the
    Prospect News header (sidebar feed or top ticker) on the homepage."""
    data = data or load_site_data() or {}
    events = _collect_events(data.get("players") or [], data.get("graduates") or [],
                             _load_fa_events_for_wire())
    # player_key -> record, so each row can carry the player's current FV chip
    # and scouting line. Active prospects win ties; graduates fill the debuts.
    pmap: dict = {}
    for p in (data.get("players") or []):
        if p.get("player_key"):
            pmap[p["player_key"]] = p
    for g in (data.get("graduates") or []):
        if g.get("player_key") and g["player_key"] not in pmap:
            pmap[g["player_key"]] = g
    feed = _news_feed_html(events, pmap)
    recent = _news_recent_events(events)
    chip_defs = [("all", "All"), ("debut", "Debuts"), ("trade", "Trades"),
                 ("move", "Moves"), ("il", "IL"), ("fv", "FV"), ("signing", "Signings")]
    chips = "".join(
        f'<button class="chip{" active" if c == "all" else ""}" '
        f'data-news-filter="{c}">{html.escape(lbl)}</button>'
        for c, lbl in chip_defs)
    body = (
        '<div class="news-app">'
        '<div class="section-head"><h1>Prospect News</h1>'
        '<span class="section-sub">the full recent prospect wire - filterable by event type</span>'
        f'{_gfx_chip_html("news-gfx-chip")}</div>'
        '<p class="news-intro">Every move on the board - prospect debuts, trades, promotions and '
        'demotions, IL placements, genuine FV grade changes, and Free Agency signings - newest first. '
        'The homepage shows the latest dozen; this is the full recent feed (last ~30 days), with each '
        "player's current FV grade and scouting line. Filter by type, or jump into Time Machine on any "
        'date to see the whole board as it stood.</p>'
        f'<div class="filter-bar" id="news-filter-bar"><span class="filter-label">Filter</span>{chips}</div>'
        f'<div class="sb-feed news-feed" id="news-feed">{feed}</div>'
        '</div>'
        # Page-scoped sizing for the per-date GFX chips (site.css owns the base
        # .chip/.egfx-chip look; this only shrinks them into the thin day rows).
        '<style>.news-feed .feed-day{gap:10px;}'
        '.news-app .news-feed button.chip.egfx-day-chip{margin-left:auto;font-size:10px;'
        'padding:2px 8px;line-height:1.5;}</style>'
        + _news_gfx_blob(recent, pmap)
        + _NEWS_FILTER_JS
        + _NEWS_GFX_JS
        # Shared Generate GFX engine (same two-script injection as /fa/).
        + f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        + f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
    )
    return page("Prospect News - eephus.io", "news", body,
                "The full recent eephus.io prospect wire: debuts, trades, promotions, IL moves, "
                "FV grade changes, and Free Agency signings - filterable by type.",
                url=f"{SITE_ORIGIN}/news/")

def _fv_sparkline(points: list, color: str, w: int = 150, h: int = 34) -> str:
    vals = [pt.get("consensus_fv_raw") for pt in (points or []) if pt.get("consensus_fv_raw") is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    step = w / (len(vals) - 1)
    pts = " ".join(f"{i*step:.1f},{h-2-((v-lo)/span)*(h-4):.1f}" for i, v in enumerate(vals))
    return (f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:{h}px;display:block;">'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" '
            'stroke-linejoin="round" stroke-linecap="round"/></svg>')

def _spotlight_html(players: list) -> str:
    # Biggest riser with FV history - rendered as a baseball card. Ranked by the
    # de-noised genuine same-source move (the same selector the Top Movers
    # module uses), so the "+N FV" caption is a true FV statement and the hero
    # card never disagrees with the movers list or the per-player stock chips.
    cands = [(d, p) for p in players
             if p.get("status") != "debuted"
             and (d := _genuine_mover_step(p)) is not None and d > 0]
    if not cands:
        return ""
    d, p = max(cands, key=lambda t: t[0])
    # Tier the holo border off the DISPLAYED integer, matching _fv_pill (a raw
    # threshold here disagreed with the pill rendered inside the same card).
    holo = " holo" if "holo" in _fv_tier_class(_fv_label(p)) else ""
    url = _headshot_url(p.get("mlbam_id"), 180)   # unified chain (resolves milb-only ids)
    photo = f"background-image:url('{url}');" if url else ""
    spark = _fv_sparkline(p.get("points"), "var(--accent-green)")
    return (
        '<div class="sb-group"><div class="sb-group-label">Spotlight - Top Riser</div>'
        f'<a class="spotlight{holo}" href="{_player_href(p.get("player_key"))}" style="text-decoration:none;color:inherit;">'
        f'<div class="sp-photo" style="{photo}"></div>'
        '<div style="flex:1;min-width:0;display:flex;flex-direction:column;justify-content:center;gap:2px;">'
        f'<div class="sp-name">{html.escape(p.get("player_name") or "")}</div>'
        f'<div class="sp-meta">{_meta(p.get("position"), p.get("org"))}</div>'
        # flex-wrap + nowrap chip: under the wide MS-Gothic metrics the pill +
        # delta can outgrow the narrow sidebar column - wrap the chip as a unit
        # below the pill instead of letting it overflow into the card border.
        f'<div style="display:flex;align-items:center;gap:8px;row-gap:2px;margin-top:4px;flex-wrap:wrap;">{_fv_pill(p)}'
        f'<span class="row-delta up" style="font-family:var(--font-retro-mono);font-size:12px;white-space:nowrap;">▲ +{d} FV</span></div>'
        f'{spark}</div></a></div>'
    )

# Homepage teaser rotation - curated Arkmetrics showcase. The phrases are
# label expansions (hints), not definitions; the canonical entry lives in
# data/glossary.json and the link deep-links it by slug.
_GLOSSARY_TERMS = [
    ("dvm_plus", "DvM+", "development vs. mean"),
    ("tvi", "Sur+", "FV-implied surplus value"),
    ("rps_plus", "RPS+", "rate performance vs. same-age peers"),
    ("statcast_plus", "SC+", "Statcast composite"),
    ("wag", "WAG", "WAR above grade"),
    ("tool", "Tool+", "20-80 tool composite"),
]

def page_home(title: str, inner: str, description: str = "") -> str:
    desc = html.escape(description or "eephus.io - sabermetrics")
    social = _social_meta(title, description or "eephus.io - sabermetrics",
                          url=f"{SITE_ORIGIN}/")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{THEME_INIT}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{desc}">
{social}
{FAVICON_LINKS}
<link rel="stylesheet" href="/assets/site.css?v={_CSS_VER}">
{ACCOUNT_CSS_LINK}
</head>
<body class="eephus-page eephus-home">
{inner}
{_footer()}
{ACCOUNT_SCRIPTS}
</body>
</html>
"""

def _home_module(kicker: str, see_all_href: str, see_all: str, body: str, full: bool = False) -> str:
    head = (f'<div class="kicker"><h2>{html.escape(kicker)}</h2>'
            f'<a class="see-all" href="{see_all_href}">{html.escape(see_all)} →</a></div>')
    return f'<section class="home-module{" full" if full else ""}">{head}{body}</section>'

def _debut_org(g: dict) -> str | None:
    """Org the player DEBUTED with - point-in-time, never the current org.
    Primary source: the debut-season MLB stat row (its first org is the debut
    org by construction - the first MLB appearance IS the debut). If that exact
    season isn't retained in career_stats (older debuts get trimmed - e.g.
    Alzolay debuted 2019 with CHC but career_stats starts 2021, still CHC,
    while his current org is NYM), use the EARLIEST retained MLB season as the
    proxy - far closer to the debut than the current org. Only when there are
    no MLB stat rows at all do we fold the trade history back from the current
    org. Mirrors the career-table rule: a historical event never silently
    wears the current org."""
    dd = str(g.get("debut_date") or "")[:10]
    if not dd:
        return g.get("org")
    try:
        debut_year = int(dd[:4])
    except ValueError:
        return g.get("org")

    def _row_org(row: dict) -> str | None:
        stints = [s for s in (row.get("stints") or []) if s.get("org")]
        return stints[0]["org"] if stints else row.get("org")

    mlb_rows = [r for r in (g.get("career_stats") or [])
                if str(r.get("level") or "") == "MLB" and r.get("season") is not None]
    # Exact debut-season row - the first MLB appearance IS the debut.
    for row in mlb_rows:
        if row.get("season") == debut_year:
            o = _row_org(row)
            if o:
                return o
    # Debut season trimmed: the earliest retained MLB season is the best proxy.
    if mlb_rows:
        o = _row_org(min(mlb_rows, key=lambda r: r["season"]))
        if o:
            return o
    # No MLB stat rows at all: unwind post-debut trades from the current org.
    org = g.get("org")
    for tr in sorted((g.get("trades") or []), key=lambda t: t.get("trade_date") or "", reverse=True):
        td = str(tr.get("trade_date") or "")[:10]
        if td and td > dd:
            org = tr.get("from_org") or org
        else:
            break
    return org

def _wag_badge(g: dict) -> str:
    """A graduate's WAG (WAR Above Grade) as a signed, color-classed chip -
    how the player has performed against their FV-implied expectation. Gated
    on the WAG model's own meaningful-exposure flag (the same gate
    display_metric_for() uses), so a thin sample shows nothing rather than a
    misleading number. Returns "" when there's no settled WAG to show."""
    wag = (g.get("debuted_value") or {}).get("wag") or {}
    rw = wag.get("regressed_wag")
    if rw is None or wag.get("below_meaningful_exposure"):
        return ""
    wag_r = round(rw, 1) + 0.0                # collapse -0.0
    cls = "up" if wag_r > 0 else ("down" if wag_r < 0 else "flat")
    sign = "+" if wag_r > 0 else ""           # negatives carry their own '-'; zero unsigned
    return (f'<span class="otd-wag row-delta {cls}" '
            f'title="WAR Above Grade - career WAR/yr vs the player\'s FV-implied expectation">'
            f'{sign}{wag_r:.1f} WAG</span>')


def _otd_date(d: "date") -> str:
    """Compact numeric mono date stamp for the This Day rows: "6/20/15".
    Replaces the verbose "June 20, 2015" + separate "Ny ago" tag (the
    two-digit year already says how long ago it was), tightening each row."""
    return f"{d.month}/{d.day}/{d.strftime('%y')}"


def _otd_debut_row(g: dict, d: "date", data_cat: str = "") -> str:
    """One debut-anniversary row (shared by the homepage This Day module and
    the full /history/ page). Shows the org the player DEBUTED with, not where
    they play now - this is a history row. WAG sits LEFT of the FV chip so
    every row's FV chip lines up in the same right-hand column."""
    nm = html.escape(g.get("player_name") or "")
    pos = g.get("position") or ""
    logo = _team_logo(_debut_org(g), "otd-logo")
    cat = f' data-cat="{data_cat}"' if data_cat else ""
    return (
        f'<a class="otd-row" href="{_player_href(g.get("player_key"))}"{cat}>'
        f'<span class="otd-when">{html.escape(_otd_date(d))}</span>'
        f'<span class="otd-body">{logo} <strong>{nm}</strong> debuted{(" · " + html.escape(pos)) if pos else ""}</span>'
        f'{_wag_badge(g)}{_fv_pill(g)}</a>'
    )


def _otd_trade_row(p: dict, tr: dict, d: "date", data_cat: str = "") -> str:
    """One trade-anniversary row (shared by the homepage module and /history/):
    the trade's from->to org logos, point-in-time."""
    nm = html.escape(p.get("player_name") or "")
    pos = p.get("position") or ""
    logos = (f'{_team_logo(tr.get("from_org"), "otd-logo")}'
             f'<span class="otd-arrow">→</span>'
             f'{_team_logo(tr.get("to_org"), "otd-logo")}')
    cat = f' data-cat="{data_cat}"' if data_cat else ""
    return (
        f'<a class="otd-row otd-trade" href="{_player_href(p.get("player_key"))}"{cat}>'
        f'<span class="otd-when">{html.escape(_otd_date(d))}</span>'
        f'<span class="otd-body">{logos} <strong>{nm}</strong>{(" · " + html.escape(pos)) if pos else ""} traded</span>'
        f'{_fv_pill(p)}</a>'
    )


def _this_day_html(graduates: list, players: list | None = None, n: int = 5) -> str:
    """'This day in prospect history' - graduates who debuted on (or within a
    few days of) today's calendar date in past seasons, plus prospect trades
    that happened on the same calendar date. Up to `n` debut rows, exact-date
    anniversaries first, then by prominence (final FV, then WAG); each row
    carries the player's FV chip and (for debuts) their WAG. Shows the org each
    player DEBUTED with / the trade's from->to orgs (point-in-time, not where
    they play now - this is a history module). Links into Time Machine at the
    lead anniversary date."""
    today = date.today()

    def _anniv_prox(d: "date") -> int | None:
        """Days between `d`'s nearest anniversary and today; None if the
        date is this year/later or doesn't map onto a nearby year (Feb 29).
        Checks the adjacent years too so a late-Dec/early-Jan anniversary
        survives the year boundary; the event date itself never counts
        (a days-old December debut is not history on Jan 1)."""
        if d.year >= today.year:
            return None
        prox = None
        for yr in (today.year - 1, today.year, today.year + 1):
            try:
                anniv = date(yr, d.month, d.day)
            except ValueError:
                continue
            if anniv == d:
                continue
            p = abs((anniv - today).days)
            prox = p if prox is None else min(prox, p)
        return prox if prox is not None and prox <= 4 else None

    # ---- Debuts on this day ----
    cands = []  # (date_proximity, -prominence, debut_date, grad)
    for g in graduates:
        dd = g.get("debut_date")
        if not dd:
            continue
        try:
            d = date.fromisoformat(str(dd)[:10])
        except ValueError:
            continue
        prox = _anniv_prox(d)
        if prox is None:
            continue
        prom = g.get("fv_close") or ((g.get("debuted_value") or {}).get("wag") or {}).get("regressed_wag") or 0
        cands.append((prox, -float(prom), d, g))
    cands.sort(key=lambda c: c[:2])

    rows = [_otd_debut_row(g, d) for _, _, d, g in cands[:n]]

    # ---- Trades on this day ----
    # Aggregate prospect trades across the active board (timeseries) + graduates,
    # deduped by player_key (board wins, it's fresher). Only mlb_api trades carry
    # an exact calendar date, so inferred-date trades are excluded by source.
    entities = {}
    for src in (players or [], graduates):
        for p in src:
            k = p.get("player_key")
            if k and k not in entities:
                entities[k] = p
    trade_cands = []  # (prox, -fv, trade_date, entity, trade)
    for p in entities.values():
        for tr in (p.get("trades") or []):
            if tr.get("source") != "mlb_api":
                continue
            td = str(tr.get("trade_date") or "")[:10]
            try:
                d = date.fromisoformat(td)
            except ValueError:
                continue
            # Trades must fall EXACTLY on today's calendar date (prox == 0),
            # not merely near it - "Trades on this day" means this day.
            prox = _anniv_prox(d)
            if prox != 0:
                continue
            fv = p.get("fv_close") or 0
            trade_cands.append((prox, -float(fv), d, p, tr))
    trade_cands.sort(key=lambda c: c[:2])

    trade_rows = [_otd_trade_row(p, tr, d) for _, _, d, p, tr in trade_cands[:n]]

    if not rows and not trade_rows:
        return ""
    trades_block = (
        f'<div class="otd-subhead">Trades on this day</div>{"".join(trade_rows)}'
        if trade_rows else ""
    )
    return (
        '<section class="home-module otd-module">'
        '<div class="kicker"><h2>Today in Prospect History</h2>'
        '<a class="see-all" href="/history/">See all →</a></div>'
        + "".join(rows) + trades_block +
        '</section>'
    )

# --------------------------------------------------------------------------- #
# /history/ - the full Today in Prospect History page (generalizes the
# homepage This Day module: every exact-date match, plus the prospects.db
# transaction + IL ledgers the homepage never reads).
# --------------------------------------------------------------------------- #

# Transaction codes surfaced on /history/ (MLB StatsAPI type_code values):
# SGN = signed (draft/int'l), SFA = signed as a free agent, DFA = declared
# free agency, TR = trade. Verbs are per-row row copy.
_HIST_TX_CODES = ("SGN", "TR", "DFA", "SFA")
_HIST_TX_VERBS = {"SGN": "signed", "SFA": "signed as a free agent",
                  "DFA": "declared free agency", "TR": "traded"}

# One-pass, once-per-build cache of the prospects.db history ledgers grouped
# by calendar date. ~175k dated transaction events across 7,471 payloads
# group in ~0.3s; il_history is tiny. Module-level so a rebuild that calls
# build_this_day() more than once (tests) never re-reads the DB.
_HIST_DB_CACHE: tuple[dict, dict] | None = None

def _load_history_db() -> tuple[dict, dict]:
    """Group prospects.db player_transactions (SGN/TR/DFA/SFA only) and
    il_history by MM-DD. STRICTLY read-only (file:...?mode=ro) - the build
    must never write the pipeline's DB. Returns
    ({mmdd: [(iso_date, code, player_key, team_name), ...]},
     {mmdd: [(iso_since, player_key, il_type), ...]}); empty dicts when the
    DB is absent (cold checkouts / CI without a seeded DB)."""
    global _HIST_DB_CACHE
    if _HIST_DB_CACHE is not None:
        return _HIST_DB_CACHE
    tx: dict[str, list] = {}
    il: dict[str, list] = {}
    db = ROOT / "prospects.db"
    if db.exists():
        try:
            con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
            try:
                seen: set = set()
                for key, pj in con.execute(
                        "SELECT player_key, payload_json FROM player_transactions"):
                    try:
                        events = json.loads(pj) or []
                    except ValueError:
                        continue
                    for t in events:
                        code = t.get("type_code")
                        if code not in _HIST_TX_CODES:
                            continue
                        dt = str(t.get("date") or "")
                        if len(dt) < 10:
                            continue
                        sig = (key, dt[:10], code)
                        if sig in seen:
                            continue
                        seen.add(sig)
                        team = t.get("to_team_name") or t.get("from_team_name") or ""
                        tx.setdefault(dt[5:10], []).append((dt[:10], code, key, team))
                seen.clear()
                for key, since, il_type in con.execute(
                        "SELECT player_key, since, il_type FROM il_history"):
                    s = str(since or "")
                    if len(s) < 10 or (key, s[:10]) in seen:
                        continue
                    seen.add((key, s[:10]))
                    il.setdefault(s[5:10], []).append((s[:10], key, il_type or ""))
            finally:
                con.close()
        except sqlite3.Error:
            pass
    _HIST_DB_CACHE = (tx, il)
    return _HIST_DB_CACHE

def _org_from_team_name(team: str | None) -> str | None:
    """MLB club abbreviation from a transaction's full team name ("Seattle
    Mariners" -> SEA) via nickname suffix match; None for minor-league
    affiliates / foreign clubs (they get no big-league logo, correctly)."""
    if not team:
        return None
    for abbr, nick in ORG_NAMES.items():
        if team.endswith(nick):
            return abbr
    return None

def _name_from_key(key: str) -> str:
    """Readable fallback name for a DB player_key with no board/graduate
    record ("travis_kuhn" -> "Travis Kuhn"; the "__noid" disambiguator and
    friends are dropped)."""
    base = (key or "").split("__")[0]
    return base.replace("_", " ").title()

# /history/ category filter - same tiny dependency-free idiom as the /news/
# chips (_NEWS_FILTER_JS): toggle .otd-row visibility by data-cat, hide any
# section left with no visible rows.
_HIST_FILTER_JS = """<script>
(function(){
  var bar=document.getElementById('hist-filter-bar'),wrap=document.getElementById('hist-sections');
  if(!bar||!wrap)return;
  var empty=null;
  bar.addEventListener('click',function(e){
    var b=e.target.closest('[data-hist-filter]');if(!b)return;
    var f=b.getAttribute('data-hist-filter');
    bar.querySelectorAll('[data-hist-filter]').forEach(function(x){x.classList.toggle('active',x===b);});
    var shown=0;
    wrap.querySelectorAll('.hist-section').forEach(function(sec){
      var any=false;
      sec.querySelectorAll('.otd-row').forEach(function(it){
        var show=(f==='all')||it.getAttribute('data-cat')===f;
        it.style.display=show?'':'none';if(show){any=true;shown++;}
      });
      sec.style.display=any?'':'none';
    });
    if(!empty){
      empty=document.createElement('div');
      empty.className='news-empty';
      empty.style.cssText='padding:2rem 1rem;text-align:center;color:var(--text-tertiary,#888);';
      wrap.appendChild(empty);
    }
    if(shown===0){empty.textContent='No items in this category.';empty.style.display='';}
    else{empty.style.display='none';}
  });
})();
</script>"""

def build_this_day(data: dict | None = None) -> str:
    """/history/ - Today in Prospect History as a full page: every debut
    anniversary and prospect trade landing on today's exact calendar date
    (past seasons only), plus the prospects.db transaction ledger (signings /
    free agency, 2019+) and IL placements (2017+) for the same MM-DD.

    Big eFV moves are DELIBERATELY not a section: data/xfv_history.json dates
    grade changes at model snapshot re-runs (over half of all |delta| >= 3
    steps share one monthly restamp date), so a calendar-day match would
    misstate when the move actually happened. Revisit if the history ever
    carries first-seen event dates."""
    data = data or load_site_data() or {}
    players = data.get("players") or []
    graduates = data.get("graduates") or []
    today = date.today()
    mmdd = f"{today.month:02d}-{today.day:02d}"
    mon_d = f"{today.strftime('%B')} {today.day}"

    # player_key -> record; active board wins ties, graduates fill the rest
    # (same dedupe the news page + homepage trades use).
    pmap: dict = {}
    for p in players:
        if p.get("player_key"):
            pmap[p["player_key"]] = p
    for g in graduates:
        if g.get("player_key") and g["player_key"] not in pmap:
            pmap[g["player_key"]] = g

    def _is_anniv(d: "date") -> bool:
        # Exact calendar date, past seasons only (the full page never uses the
        # homepage's near-date padding - "on this day" means this day here).
        return d.year < today.year and (d.month, d.day) == (today.month, today.day)

    # ---- Debut anniversaries (every exact match, prominence-ordered) -------
    debut_cands = []
    for g in graduates:
        try:
            d = date.fromisoformat(str(g.get("debut_date") or "")[:10])
        except ValueError:
            continue
        if not _is_anniv(d):
            continue
        prom = g.get("fv_close") or ((g.get("debuted_value") or {}).get("wag") or {}).get("regressed_wag") or 0
        debut_cands.append((-float(prom), d, g))
    debut_cands.sort(key=lambda c: c[0])
    debut_rows = [_otd_debut_row(g, d, data_cat="debut") for _, d, g in debut_cands]

    # ---- Trades on this day (exact-dated mlb_api rows only) ----------------
    trade_cands = []
    for p in pmap.values():
        for tr in (p.get("trades") or []):
            if tr.get("source") != "mlb_api":
                continue
            try:
                d = date.fromisoformat(str(tr.get("trade_date") or "")[:10])
            except ValueError:
                continue
            if _is_anniv(d):
                trade_cands.append((-float(p.get("fv_close") or 0), d, p, tr))
    trade_cands.sort(key=lambda c: c[0])
    trade_rows = [_otd_trade_row(p, tr, d, data_cat="trade") for _, d, p, tr in trade_cands]

    # ---- Transaction ledger (SGN / SFA / DFA / TR) -------------------------
    tx_all, il_all = _load_history_db()
    tx_today = [t for t in tx_all.get(mmdd, []) if int(t[0][:4]) < today.year]
    # Known board/graduate players first (FV-ranked), then the rest of the
    # ledger newest-first; capped - July draft-signing anniversaries alone can
    # run to hundreds of rows.
    tx_today.sort(key=lambda t: t[0], reverse=True)
    tx_today.sort(key=lambda t: (0, -(_primary_fv(pmap[t[2]]) or 0)) if t[2] in pmap else (1, 0))
    TX_CAP = 40
    tx_rows = []
    for dt, code, key, team in tx_today[:TX_CAP]:
        p = pmap.get(key)
        nm = html.escape((p or {}).get("player_name") or _name_from_key(key))
        pos = (p or {}).get("position") or ""
        d = date.fromisoformat(dt)
        verb = _HIST_TX_VERBS.get(code, "moved")
        logo = _team_logo(_org_from_team_name(team), "otd-logo")
        cat = "trade" if code == "TR" else "signing"
        inner = (f'<span class="otd-when">{html.escape(_otd_date(d))}</span>'
                 f'<span class="otd-body">{logo} <strong>{nm}</strong> {verb}'
                 f'{(" · " + html.escape(pos)) if pos else ""}</span>')
        if p:
            tx_rows.append(f'<a class="otd-row" href="{_player_href(key)}" data-cat="{cat}">{inner}{_fv_pill(p)}</a>')
        else:
            tx_rows.append(f'<div class="otd-row" data-cat="{cat}">{inner}</div>')
    if len(tx_today) > TX_CAP:
        tx_rows.append(
            '<div class="otd-more" style="margin:8px 4px;font-family:var(--font-retro-mono);'
            'font-size:11px;color:var(--text-tertiary);">'
            f'+ {len(tx_today) - TX_CAP} more transactions on {html.escape(mon_d)} in the ledger</div>')

    # ---- IL on this day ----------------------------------------------------
    il_today = [t for t in il_all.get(mmdd, []) if int(t[0][:4]) < today.year]
    il_today.sort(key=lambda t: t[0], reverse=True)
    il_rows = []
    for dt, key, il_type in il_today:
        p = pmap.get(key)
        nm = html.escape((p or {}).get("player_name") or _name_from_key(key))
        pos = (p or {}).get("position") or ""
        d = date.fromisoformat(dt)
        label = f"{il_type} IL".strip() if il_type else "IL"
        inner = (f'<span class="otd-when">{html.escape(_otd_date(d))}</span>'
                 f'<span class="otd-body">✚ <strong>{nm}</strong> placed on the {html.escape(label)}'
                 f'{(" · " + html.escape(pos)) if pos else ""}</span>')
        if p:
            il_rows.append(f'<a class="otd-row" href="{_player_href(key)}" data-cat="il">{inner}{_fv_pill(p)}</a>')
        else:
            il_rows.append(f'<div class="otd-row" data-cat="il">{inner}</div>')

    # ---- assemble ----------------------------------------------------------
    def _section(title: str, rows: list) -> str:
        if not rows:
            return ""
        return ('<section class="home-module otd-module hist-section">'
                f'<div class="kicker"><h2>{html.escape(title)}</h2></div>'
                + "".join(rows) + '</section>')

    sections = (
        _section("Debut anniversaries", debut_rows)
        + _section("Trades on this day", trade_rows)
        + _section("Signings & free agency on this day", tx_rows)
        + _section("IL on this day", il_rows)
    )
    if not sections:
        sections = ('<p class="news-intro">No tracked prospect history lands on '
                    f'{html.escape(mon_d)} yet. Check back tomorrow.</p>')

    chip_defs = [("all", "All"), ("debut", "Debuts"), ("trade", "Trades"),
                 ("signing", "Signings"), ("il", "IL")]
    chips = "".join(
        f'<button class="chip{" active" if c == "all" else ""}" '
        f'data-hist-filter="{c}">{html.escape(lbl)}</button>'
        for c, lbl in chip_defs)

    body = (
        '<div class="news-app hist-app">'
        f'<div class="section-head"><h1>Today in Prospect History - {html.escape(mon_d)}</h1>'
        '<span class="section-sub">debut anniversaries, trades, signings &amp; IL moves on this calendar date</span></div>'
        f'<p class="news-intro">Everything the tracker knows about {html.escape(mon_d)} across past '
        'seasons: MLB debut anniversaries from the graduate pool (with each player\'s WAG - how the '
        'career has run against the grade), prospect trades on this exact date, signings and '
        'free-agency moves from the transaction ledger (2019 to present), and injured-list '
        'placements (2017 to present). Exact calendar-date matches only. The homepage module shows '
        'a five-row taste; this page is the whole day.</p>'
        f'<div class="filter-bar" id="hist-filter-bar"><span class="filter-label">Filter</span>{chips}</div>'
        f'<div id="hist-sections" style="max-width:760px;">{sections}</div>'
        '<p class="news-intro" style="font-size:11px;">Why no "big eFV moves" section: the model\'s '
        'grade history stamps changes at snapshot re-run dates, not the day the change actually '
        'happened, so a calendar-day anniversary there would mislead.</p>'
        '</div>'
        + _HIST_FILTER_JS
    )
    return page("Today in Prospect History - eephus.io", "", body,
                "Today in prospect history on eephus.io: MLB debut anniversaries, prospect trades, "
                "signings, and IL moves that happened on this calendar date in past seasons.",
                url=f"{SITE_ORIGIN}/history/")

def _date_callout() -> str:
    """Date-aware countdown when the MLB Draft or Int'l signing period is near.

    Events carry a (start, end) range rather than a single date - the MLB
    Draft runs three days (Jul 11-13), not one, so "days until" has to count
    down to the START, and the callout needs an in-progress state for the
    days the event is actually happening, not just before/after.
    """
    today = date.today()
    yr = today.year
    events = [
        (date(yr, 7, 11), date(yr, 7, 13), "MLB Draft", "/prospx/#tab=draft"),
        (date(yr if today <= date(yr, 1, 15) else yr + 1, 1, 15),
         date(yr if today <= date(yr, 1, 15) else yr + 1, 1, 15),
         "International signing period", "/prospx/#tab=ifa"),
    ]
    for start, end, name, href in sorted(events, key=lambda e: e[0]):
        if today > end:
            continue
        days = (start - today).days
        if start <= today <= end:
            tag, when = "◆ Live", "Underway"
        elif 0 <= days <= 45:
            tag = "◆ Upcoming"
            when = "Tomorrow" if days == 1 else f"in {days} days"
        else:
            continue
        md = start.strftime("%b %d").replace(" 0", " ")
        if end != start:
            md += "-" + end.strftime("%d").lstrip("0")
        return (f'<a class="home-callout" href="{href}">'
                f'<span class="cal-tag">{tag}</span>'
                f'<span class="cal-msg"><strong>{html.escape(name)}</strong> · {md} · {when}</span>'
                f'<span class="cal-go">View →</span></a>')
    return ""

def _scatter_teaser() -> str:
    """Tiny inline scatter linking to the Scatterplots builder - a visual nudge,
    not live data (kept featherweight; the real plot lives in PROSPX)."""
    import random
    rnd = random.Random(date.today().toordinal())
    pts = "".join(
        f'<circle cx="{rnd.uniform(8, 142):.0f}" cy="{rnd.uniform(6, 42):.0f}" r="2.2" '
        f'fill="var(--accent-{"green" if rnd.random() > .5 else "gold"})" opacity="0.85"/>'
        for _ in range(16))
    svg = (f'<svg viewBox="0 0 150 48" preserveAspectRatio="none" aria-hidden="true">'
           f'<line x1="6" y1="44" x2="144" y2="44" stroke="var(--border)" stroke-width="1"/>'
           f'<line x1="6" y1="4" x2="6" y2="44" stroke="var(--border)" stroke-width="1"/>{pts}</svg>')
    return (f'<a class="scatter-teaser" href="/prospx/#tab=charts">'
            f'<div class="st-svg">{svg}</div>'
            f'<div class="st-txt"><strong>Build a scatterplot</strong>'
            f'<span>Any X/Y metric · color &amp; size encodings · brush-to-zoom</span></div>'
            f'<span class="st-go">Scatterplots →</span></a>')

def _cross_module_strip() -> str:
    """Across eephus.io - the homepage's window into the non-PROSPX
    modules (cohesion: every module surfaces on the front page). Reads
    the committed sidecars at build time; any missing file just drops
    its card."""
    cards = []
    # MLB Free Agency - top of the current class board
    try:
        fa = _cached_data_json("fa_class.json")
        top = sorted((m for m in fa.get("members") or [] if m.get("projGuar")),
                     key=lambda m: -m["projGuar"])[:3]
        rows = "".join(
            f'<a class="xmod-row" href="/fa/#player={html.escape(m["key"])}">'
            f'<span class="xmod-name">{html.escape(m["name"])}</span>'
            f'<span class="xmod-sub">{html.escape(m.get("pos") or "")}</span>'
            f'<span class="xmod-val">{m.get("projYears") or "?"}y / ${(m["projGuar"] / 1e6):.0f}M</span></a>'
            for m in top)
        if rows:
            cards.append(('$ Free Agency', '/fa/',
                          f'{fa.get("class_year", 2027) - 1}-{str(fa.get("class_year", 2027))[2:]} projected market leaders', rows))
    except (OSError, ValueError, KeyError):
        pass
    # MLB Projections - 5y WAR leaders
    try:
        mp = _cached_data_json("mlb_projections.json")
        top = sorted((v for v in mp.get("vets") or [] if v.get("warTotal")),
                     key=lambda v: -v["warTotal"])[:3]
        rows = "".join(
            f'<a class="xmod-row" href="/projections/#player={html.escape(v["key"])}">'
            f'<span class="xmod-name">{html.escape(v["name"])}</span>'
            f'<span class="xmod-sub">{html.escape(v.get("pos") or "")}{" · two-way" if v.get("twoWay") else ""}</span>'
            f'<span class="xmod-val">{v["warTotal"]:.1f} WAR</span></a>'
            for v in top)
        if rows:
            cards.append(('Δ MLB Projections', '/projections/',
                          'five-year bWAR leaders', rows))
    except (OSError, ValueError, KeyError):
        pass
    # Trade Machine - top surplus trade values (prospects + MLB, one currency)
    try:
        tv = _cached_data_json("trade_values.json")
        top = sorted((p for p in tv.get("players") or [] if p.get("trade_value_mm") is not None),
                     key=lambda p: -p["trade_value_mm"])[:3]
        rows = "".join(
            f'<a class="xmod-row" href="/trademachine/">'
            f'<span class="xmod-name">{html.escape(p.get("player_name") or "")}</span>'
            f'<span class="xmod-sub">{html.escape(p.get("position") or "")} · {html.escape(p.get("org") or "")}</span>'
            f'<span class="xmod-val">${p["trade_value_mm"]:.0f}M</span></a>'
            for p in top)
        if rows:
            cards.append(('⇄ Trade Machine', '/trademachine/',
                          'surplus trade value, prospects + MLB', rows))
    except (OSError, ValueError, KeyError):
        pass
    # CollegeSavant - static teaser (its data bundles stay in-module)
    cards.append(('✪ CollegeSavant', '/collegesavant/',
                  'college baseball percentiles',
                  '<a class="xmod-row" href="/collegesavant/"><span class="xmod-name">Hitter dashboard</span><span class="xmod-val">EV · xwOBA · discipline →</span></a>'
                  '<a class="xmod-row" href="/collegesavant/pitcher_index.html"><span class="xmod-name">Pitcher dashboard</span><span class="xmod-val">Stuff+ · shapes →</span></a>'))
    # MLB Stats / REM+ - top relievers by REM+ (the reliever run-prevention metric)
    try:
        bl = _cached_data_json("bullpen_leaderboards.json")
        top = sorted((r for r in bl.get("relievers") or [] if r.get("rem_plus") is not None),
                     key=lambda r: -r["rem_plus"])[:3]
        rows = "".join(
            f'<a class="xmod-row" href="/mlbstats/">'
            f'<span class="xmod-name">{html.escape(r.get("name") or "")}</span>'
            f'<span class="xmod-sub">{html.escape(r.get("team") or "")}{" · " + html.escape(r["role"]) if r.get("role") else ""}</span>'
            f'<span class="xmod-val">{round(r["rem_plus"])} REM+</span></a>'
            for r in top)
        if rows:
            cards.append(('▦ MLB Stats', '/mlbstats/',
                          'top relievers by REM+', rows))
    except (OSError, ValueError, KeyError):
        pass
    # Alchemy Lab - top RP->SP conversion candidates by FIT score
    try:
        pal = _cached_data_json("pal.json")
        top = sorted((c for c in pal.get("rp2sp") or [] if c.get("fit") is not None),
                     key=lambda c: -c["fit"])[:3]
        rows = "".join(
            f'<a class="xmod-row" href="/pal/">'
            f'<span class="xmod-name">{html.escape(c.get("name") or "")}</span>'
            f'<span class="xmod-sub">{html.escape(c.get("team") or "")}</span>'
            f'<span class="xmod-val">{round(c["fit"])} FIT</span></a>'
            for c in top)
        if rows:
            cards.append(('⚗ Alchemy Lab', '/pal/',
                          'top reliever-to-starter conversion candidates', rows))
    except (OSError, ValueError, KeyError):
        pass
    # MiLB Park Factors - the most offense-inflating venues on the current
    # 3-season window (display-only context; no model reads these).
    try:
        pf = _cached_data_json("milb_park_factors.json")
        venues = pf.get("venues") or []
        year = max((int(y) for v in venues for y in (v.get("window_run_pf") or {})),
                   default=None)
        # venue_id -> the level its clubs played at in that window
        lvl_of: dict = {}
        for t in pf.get("team_seasons") or []:
            if year is not None and year - 2 <= t.get("season", 0) <= year:
                lvl_of.setdefault(t.get("venue_id"), t.get("level"))
        rated = [(v, (v.get("window_run_pf") or {}).get(str(year))) for v in venues]
        top = sorted(((v, f) for v, f in rated if f is not None),
                     key=lambda vf: -vf[1])[:3]
        rows = "".join(
            f'<a class="xmod-row" href="/parks/">'
            f'<span class="xmod-name">{html.escape(v.get("venue_name") or "")}</span>'
            f'<span class="xmod-sub">{html.escape(lvl_of.get(v.get("venue_id")) or "")}</span>'
            f'<span class="xmod-val">{f:.2f} run PF</span></a>'
            for v, f in top)
        if rows:
            cards.append(('◊ Park Factors', '/parks/',
                          f'MiLB venues that add the most offense ({year} window)', rows))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    body = "".join(
        f'<div class="xmod-card"><div class="xmod-head"><span class="xmod-title">{title}</span>'
        f'<a class="xmod-link" href="{href}">open →</a></div>'
        f'<div class="xmod-sub-head">{html.escape(sub)}</div>{rows}</div>'
        for title, href, sub, rows in cards)
    return (f'<div class="xmod-strip"><div class="xmod-eyebrow">Across eephus.io</div>'
            f'<div class="xmod-grid">{body}</div></div>')


_HOME_DRAWER_JS = '''<script>
/* Homepage sidebar drawer (<=900px): the hamburger in .sb-brand opens the
   search + module list + wire feed; Esc / outside click close it; resizing
   back to desktop resets the state. Desktop widths ignore all of this
   (the .home-nav-toggle is display:none above 900px). */
(function () {
  "use strict";
  var sb = document.getElementById("home-sidebar");
  var btn = sb ? sb.querySelector(".home-nav-toggle") : null;
  if (!sb || !btn) return;
  function set(open) {
    if (open) sb.setAttribute("data-nav-open", "");
    else sb.removeAttribute("data-nav-open");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    btn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  }
  btn.addEventListener("click", function () { set(!sb.hasAttribute("data-nav-open")); });
  document.addEventListener("click", function (e) {
    if (sb.hasAttribute("data-nav-open") && !sb.contains(e.target)) set(false);
  });
  document.addEventListener("keydown", function (e) {
    if ((e.key === "Escape" || e.key === "Esc") && sb.hasAttribute("data-nav-open")) {
      set(false);
      btn.focus();
    }
  });
  var mq = window.matchMedia ? window.matchMedia("(max-width: 900px)") : null;
  if (mq) {
    var onmq = function () { if (!mq.matches) set(false); };
    if (mq.addEventListener) mq.addEventListener("change", onmq);
    else if (mq.addListener) mq.addListener(onmq);
  }
})();
</script>'''


def build_home(articles: list[dict], data: dict | None = None) -> str:
    """Homepage = sidebar + newspaper-style main, with live PROSPX modules + a
    prospect wire feed read from the build-time data layer."""
    data = data or {}
    players = data.get("players") or []
    org_summary = data.get("org_summary") or []
    graduates = data.get("graduates") or []
    as_of = data.get("as_of", " - ")
    today = datetime.now().strftime("%A, %B %d, %Y").replace(" 0", " ")
    events = _collect_events(players, graduates, _load_fa_events_for_wire())

    # ---- sidebar ----
    # The sidebar has room for fuller module names than the horizontal
    # header nav, so a couple of labels expand here (key → sidebar label).
    # Every module carries a terminal-safe glyph (PROSPX carries its ball
    # badge instead). Lifecycle sigils live on module mastheads, not here.
    sidebar_labels = {"fa": "MLB Free Agency", "projections": "MLB Projections",
                      "collegesavant": "CollegeSavant",
                      "glossary": "Glossary & Methodology"}
    sidebar_icons = {"home": "⌂", "articles": "¶", "fa": "$", "projections": "Δ",
                     "collegesavant": "✪", "glossary": "§", "forums": "❝",
                     "team": "⚒", "mlbstats": "▦", "pal": "⚗", "trademachine": "⇄",
                     "fantasy": "◈"}
    def _sb_link(key, label, href, grouped=False):
        classes = []
        if key == "home":
            classes.append("is-active")   # the sidebar only renders on the homepage
        if grouped:
            classes.append("sb-grouped")
        cls = f' class="{" ".join(classes)}"' if classes else ""
        icon = (prospx_ball_logo("sbnav") if key == "prospx"
                else f'<span class="sb-ico" aria-hidden="true">{sidebar_icons.get(key, "›")}</span>')
        return f'<a href="{href}"{cls}>{icon}{html.escape(label)}</a>'
    nav = []
    for item in NAV_ITEMS:
        if _nav_is_group(item):
            # A nested, always-expanded sub-block in the vertical rail (the
            # dropdown is for the horizontal top bar; the rail has room).
            nav.append(f'<div class="sb-subhead">{html.escape(item["group"])}</div>')
            for k, l, h in item["children"]:
                nav.append(_sb_link(k, l, h, grouped=True))   # leaf label under the subhead
        else:
            key, label, href = item
            nav.append(_sb_link(key, sidebar_labels.get(key, label), href))
    sub = "".join(f'<a href="{href}"><span class="px-glyph">›</span>{html.escape(label)}</a>'
                  for label, href in PROSPX_SUBNAV)
    feed = _feed_html(events, 12) or '<div class="feed-item" style="color:#6f8a76;">No recent activity.</div>'
    spotlight = _spotlight_html(players)
    search = ('<input class="sb-search" type="search" placeholder="Search prospects…" aria-label="Search prospects" '
              "onkeydown=\"if(event.key==='Enter'&&this.value.trim()){location.href='/prospx/#q='+encodeURIComponent(this.value.trim());}\">")
    # Mobile drawer (<=900px): the homepage does not load eephus-nav.js, so the
    # sidebar carries its own hamburger + inline wiring; site.css collapses
    # everything but .sb-brand until [data-nav-open]. Desktop is unaffected
    # (.home-nav-toggle is display:none above 900px).
    drawer_btn = ('<button type="button" class="home-nav-toggle" '
                  'aria-controls="home-sidebar" aria-expanded="false" '
                  'aria-label="Open menu">☰</button>')
    sidebar = (
        '<aside class="home-sidebar" id="home-sidebar">'
        f'<div class="sb-brand"><a class="wm" href="/">{eephus_merged_wordmark("sb", tag="span")}</a>{THEME_BTN}{drawer_btn}</div>'
        # eephus.io - account entry point for the homepage (page_home has no
        # .eephus-nav top bar). refreshNav() in eephus-ui.js injects the Sign-in /
        # avatar control into any .eephus-nav-controls, including this sidebar slot.
        '<div class="sb-account eephus-nav-controls"></div>'
        f'{search}'
        f'<div class="sb-group"><div class="sb-group-label">Modules</div><nav class="sb-nav">{"".join(nav)}</nav></div>'
        # Prospect News feed sits high (where the PROSPX sub-nav used to be);
        # the PROSPX sub-nav drops below the spotlight feature.
        f'<div class="sb-group"><div class="sb-feed"><div class="feed-head"><a href="/news/" title="All prospect news"><span class="blip"></span>Prospect News<span class="feed-head-more">all →</span></a></div>{feed}</div></div>'
        f'{spotlight}'
        f'<div class="sb-group"><div class="sb-group-label sb-group-label--lockup">{prospx_ball_logo("sbgrp", 14)}PROSPX</div><nav class="sb-subnav">{sub}</nav></div>'
        '</aside>'
        + _HOME_DRAWER_JS
    )

    # ---- top wire ticker ----
    # Decorative scrolling marquee - duplicates the accessible Prospect Wire feed
    # in the sidebar, so it's hidden from assistive tech (aria-hidden) to avoid
    # reading the same items twice / announcing a moving region.
    ticker = (f'<div class="home-ticker" aria-hidden="true"><span class="ticker-tag"><a href="/news/"><span class="blip"></span>News</a></span>'
              f'<div class="ticker-track">{_ticker_html(events)}</div></div>')

    # ---- masthead ----
    masthead = (
        '<div class="masthead">'
        f'{eephus_logo_lockup()}'
        '<div class="dateline"><span>Sabermetric Analysis</span>'
        f'<span>{html.escape(today)}</span><span>Data as of {html.escape(as_of)}</span></div></div>'
    )
    # Draft War Room banner: hidden by default, revealed by a small client-side
    # check ONLY while the live draft feed reports status "live" (draft night).
    # Links into the PROSPX draft section's War Room view. No em dashes (copy rule).
    masthead += (
        '<div id="draft-war-room-banner" style="display:none;margin:10px 0 0;">'
        '<a href="/prospx/#tab=draft&amp;dview=war-room" '
        'style="display:block;padding:10px 14px;border-radius:8px;'
        'background:var(--brand-navy,#0E2B4D);color:#fff;font-weight:600;'
        'text-decoration:none;">'
        '<span class="blip"></span> The MLB Draft is live. Open the Draft War Room '
        'to see every pick priced against our board in surplus dollars.</a></div>'
        '<script>(function(){try{fetch("/data/draft_live.json",{cache:"no-cache"})'
        '.then(function(r){return r.ok?r.json():null;})'
        '.then(function(j){if(j&&j.status==="live"){'
        'var e=document.getElementById("draft-war-room-banner");if(e)e.style.display="";}})'
        '.catch(function(){});}catch(e){}})();</script>'
    )

    # ---- lead story (latest article) + secondary ----
    latest = articles[0] if articles else None
    if latest:
        lead = (
            '<article class="lead-story no-img">'
            '<div><div class="lead-kicker">Latest</div>'
            f'<h1>{html.escape(latest["title"])}</h1>'
            f'<div class="byline">{_byline(latest, link_handle=False)}</div>'
            f'<p class="excerpt">{html.escape(latest.get("summary", ""))}</p>'
            f'<a class="read" href="/articles/{latest["slug"]}/">Read the full story →</a></div>'
            '</article>'
        )
    else:
        lead = '<article class="lead-story no-img"><div><div class="lead-kicker">Latest</div><h1>No articles yet</h1></div></article>'
    sec = articles[1:4]
    if sec:
        secondary = ('<div class="secondary-stories">' + "".join(
            f'<a href="/articles/{a["slug"]}/"><div class="s-kicker">{html.escape(a.get("date_disp", ""))}</div>'
            f'<h3>{html.escape(a["title"])}</h3></a>' for a in sec) + '</div>')
    elif latest:
        # Single-piece front: only one story so far. Keep the broadsheet rhythm
        # (the same double rule the secondary row carries) and say so plainly
        # rather than leaving a bare gap under the lead.
        secondary = ('<div class="more-soon-strip"><span>More analysis soon</span>'
                     '<a href="/articles/">All articles →</a></div>')
    else:
        secondary = ""

    # ---- live PROSPX modules ----
    # Top Movers = biggest GENUINE moves from the de-noised movement engine
    # (movement.compute_genuine_movement, carried on each player's `stock`):
    # only same-source consensus steps count, so a source merely re-publishing
    # or the panel changing no longer fires a fake mover. Gated to the trailing
    # year so the homepage stays a "moving now" surface, matching the FV
    # sparkline beside each row. The driver-chip view lives on the PROSPX
    # spotlights tab this module links to.
    mv = [(d, p) for p in players
          if p.get("status") != "debuted"
          and (d := _genuine_mover_step(p)) is not None]
    # Top 5 movers: 3 biggest risers + 2 biggest fallers (the module shows both
    # directions; the spotlights tab it links to carries the full list).
    risers = sorted((t for t in mv if t[0] > 0), key=lambda t: -t[0])[:3]
    fallers = sorted((t for t in mv if t[0] < 0), key=lambda t: t[0])[:2]
    movers_body = "".join(_row_mover(p, d) for d, p in risers + fallers)
    movers = _home_module("Top Movers", "/prospx/#tab=spotlights", "All movers", movers_body) if movers_body else ""

    # Rank by PRIMARY FV (eFV when graded, else consensus close), RAW/unrounded -- the eFV
    # DECIMAL, matching the board's efvRankValue. The board's v42 tiebreak on an exact-decimal
    # tie is the '+' upside flag, then the JS-only Tiebreaker Score (TBS), then name; the
    # homepage can match the primary + '+' but not TBS, so it approximates the rest by stable
    # order. (Was tie-broken by consensus FV, which the board no longer uses since v42.)
    def _top_key(p):
        return (_primary_fv(p) if _primary_fv(p) is not None else -1,
                1 if p.get("fv_close_plus") else 0)
    topN = sorted(players, key=_top_key, reverse=True)[:5]
    top_body = "".join(_row_top(p, i) for i, p in enumerate(topN, 1))
    topp = _home_module("Top Prospects", "/prospx/", "Full board", top_body) if top_body else ""

    gr = sorted((g for g in graduates if g.get("debut_date")), key=lambda g: g["debut_date"], reverse=True)[:5]
    grad_body = "".join(_row_grad(g) for g in gr)
    grads = _home_module("Recent Debuts", "/prospx/#tab=debuts", "All debuts", grad_body) if grad_body else ""

    fm = sorted((o for o in org_summary if o.get("farm_rank")), key=lambda o: o["farm_rank"])[:5]
    farm_body = "".join(_row_farm(o, o.get("farm_rank") or i) for i, o in enumerate(fm, 1))
    farm = _home_module("Top Farm Systems", "/prospx/#tab=farm", "Farm systems", farm_body) if farm_body else ""

    slug, term, defn = _GLOSSARY_TERMS[datetime.now().timetuple().tm_yday % len(_GLOSSARY_TERMS)]
    glossary = (f'<div class="glossary-teaser"><span>Today\'s term: <strong>{html.escape(term)}</strong> - {html.escape(defn)}</span>'
                f'<a href="/glossary/#g={slug}">Glossary →</a></div>')

    callout = _date_callout()
    otd = _this_day_html(graduates, players)
    trades_mod = _recent_trades_html(players)
    scatter = _scatter_teaser()
    cross = _cross_module_strip()
    # eephus.io - Forums module (third content pillar). Hydrated client-side by
    # eephus-ui.js (#eph-home-forums): bump/Hot ordering, last-active first.
    forums_mod = _home_module("Forums", "/forums/", "All discussions",
                              '<div id="eph-home-forums"></div>', full=True)
    main = (
        '<main class="home-main">'
        f'{masthead}{callout}{lead}{secondary}'
        # 2-col grid, paired by row: [This Day | Top Movers] (today's activity),
        # [Top Prospects | Farm] (rankings), [Recent Graduates | Recent Trades]
        # (recent transactions).
        f'<div class="module-cols">{otd}{movers}{topp}{farm}{grads}{trades_mod}</div>'
        f'{cross}'
        f'{forums_mod}'
        f'<div class="teaser-row">{glossary}{scatter}</div>'
        '</main>'
    )
    inner = f'{ticker}<div class="home-shell">{sidebar}{main}</div>'
    return page_home("eephus.io - sabermetrics", inner,
                     "MiLB prospect board with outcome-grounded eFV grades, top prospects, movers, graduates, and analysis.")

def build_articles_index(articles: list[dict]) -> str:
    cards = []
    for a in articles:
        excerpt = html.escape(a.get("summary", ""))
        cards.append(
            f'<a class="card article-card" href="/articles/{a["slug"]}/">'
            '<div class="eyebrow">Article</div>'
            f'<p class="meta">{_byline(a, link_handle=False)}</p>'
            f'<h3>{html.escape(a["title"])}</h3>'
            f"<p>{excerpt}</p>"
            '<span class="card-cta">Read →</span></a>'
        )
    grid = "".join(cards) or '<p>No articles yet.</p>'
    body = (
        '<div class="section-head"><h1>Articles</h1></div>'
        f'<div class="article-grid">{grid}</div>'
    )
    return page("Articles - eephus.io", "articles", body, "Long-form baseball analysis from eephus.io.",
                url=f"{SITE_ORIGIN}/articles/")

def build_forums_index() -> str:
    """The /forums/ index - the third content pillar. The thread list is hydrated
    client-side by eephus-ui.js (#eph-forums-index): bump / Hot ordering, most
    recently active first. Static shell gives SEO + first paint + a nav home."""
    body = (
        '<div class="section-head"><h1>Forums '
        f'<span class="eephus-beta" title="{html.escape(MODULE_STAGE["forums"][1])}">β beta</span></h1>'
        '<span class="section-sub">Discussion across prospects, farm systems, and articles</span></div>'
        '<div class="eph-forums-index-page"><div id="eph-forums-index"></div></div>'
    )
    return page("Forums - eephus.io", "forums", body,
                "Community discussion across prospects, farm systems, and articles on eephus.io.",
                url=f"{SITE_ORIGIN}/forums/")

def build_fa() -> str:
    """The /fa/ Free Agency app - its own surface, SEPARATE from PROSPX.

    Static shell + assets/fa.js, which fetches the fa_export.py sidecars
    (data/fa_class.json / fa_archive.json / fa_meta.json) directly. Shares the
    site chrome and styles (.fa-app block in site.css) but loads none of the
    PROSPX boot payload or script. Views route via #view= (board / fits /
    archive / model / glossary)."""
    # Derive the class label + archive count from the data so the subtitle never goes stale.
    _fa_cy = _cached_data_json("fa_class.json").get("class_year") or 2027
    _fa_span = f"{_fa_cy - 1}-{str(_fa_cy)[2:]}"
    _fa_winters = len(_cached_data_json("fa_archive.json").get("winters") or []) or 12
    body = (
        '<div class="fa-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}<h1>MLB Free Agency '
        f'<span class="eephus-beta" title="{html.escape(MODULE_STAGE["fa"][1])}">β beta</span></h1></div>'
        f'<span class="section-sub">the {_fa_span} class, constructed from data · '
        f'projected markets, rational value &amp; team fits · {_fa_winters} archived winters</span></div>'
        '<div id="fa-banner"></div>'
        '<div class="filter-bar"><span class="filter-label">View</span>'
        '<span id="fa-view-chips"></span></div>'
        '<div id="fa-rows"></div>'
        '</div>'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/fa.js?v={_FA_VER}" defer></script>'
    )
    return page("Free Agency - eephus.io", "fa", body,
                "The 2026-27 MLB free-agent class: projected contracts (projLength / projGuarantee / "
                "projAAV with floor-mean-ceiling bands), rational value vs predicted price, deal "
                "verdicts, team fits, and twelve archived winters with a realized-surplus ledger.",
                url=f"{SITE_ORIGIN}/fa/")


# Trade Machine markup - now the body of its own top-level /trademachine/ module
# (was a view inside MLB Projections; originally a PROSPX module by Anirudh Iyer).
# The board + evaluator run from assets/trademachine.js on the standalone data
# files; this is the markup the module mounts into.
_TRADE_MACHINE_BODY = ("""<div class="newsprint-eyebrow">
    <span class="newsprint-eyebrow-label">Trade Machine</span>
    <span class="newsprint-eyebrow-meta">build + value a deal both ways: prospects on eFV surplus, MLB players on projection surplus &middot; then the full Bayesian trade-value board &middot; module by Anirudh Iyer</span>
  </div>
  <div id="trade-machine"></div>
  <div class="trademachine-board-head detail-title" style="margin:18px 0 4px;font-size:13px;">Trade-value board <span class="detail-title-sub">Bayesian surplus, contract-aware, positional scarcity, opt-out adjusted</span></div>
  <div class="filter-toggle-row">
    <button class="filter-toggle" type="button" data-collapse-target="tradeboard-filter-bar" aria-expanded="false" title="Show / hide Trade Board filters">
      <span class="filter-toggle-label">Filter &amp; Sort</span>
      <span class="filter-toggle-arrow" aria-hidden="true">&#9662;</span>
    </button>
  </div>
  <div id="tradeboard-filter-bar" class="filter-bar collapsible-filter-bar">
    <div class="filter-group"><span class="filter-label">Pool</span>
      <button class="chip active" data-tb-pool="all" type="button">All</button>
      <button class="chip" data-tb-pool="milb" type="button">MiLB</button>
      <button class="chip" data-tb-pool="mlb" type="button">MLB</button>
    </div>
    <div class="filter-group"><span class="filter-label">Tier</span>
      <button class="chip active" data-tb-tier="all" type="button">All tiers</button>
      <button class="chip" data-tb-tier="elite" type="button">Elite ($40M+)</button>
      <button class="chip" data-tb-tier="high" type="button">High ($20-40M)</button>
      <button class="chip" data-tb-tier="mid" type="button">Mid ($8-20M)</button>
    </div>
    <div class="filter-group"><span class="filter-label">Position</span>
      <button class="chip active" data-tb-pos="all" type="button">All</button>
      <button class="chip" data-tb-pos="C" type="button">C</button>
      <button class="chip" data-tb-pos="1B" type="button">1B</button>
      <button class="chip" data-tb-pos="2B" type="button">2B</button>
      <button class="chip" data-tb-pos="SS" type="button">SS</button>
      <button class="chip" data-tb-pos="3B" type="button">3B</button>
      <button class="chip" data-tb-pos="LF" type="button">LF</button>
      <button class="chip" data-tb-pos="CF" type="button">CF</button>
      <button class="chip" data-tb-pos="RF" type="button">RF</button>
      <button class="chip" data-tb-pos="SP" type="button">SP</button>
      <button class="chip" data-tb-pos="RP" type="button">RP</button>
    </div>
    <div class="filter-group"><span class="filter-label">Org</span>
      <select class="chip" id="tb-org-filter" title="Filter Trade Board by organization"><option value="all">All orgs</option></select>
    </div>
    <div class="filter-group"><span class="filter-label">Exact pos</span>
      <select class="chip" id="tb-exact-pos-filter" title="Filter Trade Board by primary position"><option value="all">All positions</option></select>
    </div>
    <div class="filter-group"><span class="filter-label">Sort</span>
      <select class="chip" id="tb-sort-select" title="Sort Trade Board">
        <option value="trade_desc">Trade value</option>
        <option value="age_asc">Youngest</option>
        <option value="age_desc">Oldest</option>
        <option value="fv_desc">FV</option>
        <option value="org_asc">Org</option>
        <option value="pos_asc">Position</option>
      </select>
    </div>
  </div>
  <div style="padding:8px 0 4px;">
    <input id="tb-search" type="search" placeholder="Search player name..." style="width:100%;max-width:340px;padding:7px 10px;border-radius:6px;border:1px solid var(--border-subtle);background:var(--bg-secondary);color:var(--text-primary);font-size:13px;" autocomplete="off" spellcheck="false">
  </div>
  <div id="tb-group-panel" style="display:none;margin:8px 0;padding:12px 16px;background:var(--bg-secondary);border:1px solid var(--border-subtle);border-radius:8px;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span id="tb-group-title" style="font-weight:700;font-size:13px;"></span>
      <button onclick="document.getElementById('tb-group-panel').style.display='none';" style="background:none;border:none;color:var(--text-secondary);cursor:pointer;font-size:16px;">&#10005;</button>
    </div>
    <div id="tb-group-body"></div>
  </div>
  <div id="tradeboard-content"><div class="spinner-wrap"><span class="spinner"></span></div></div>""")

# Legacy redirect shim for /projections/: the Trade Machine used to live here as
# a #view=trademachine tab. It is now its own top-level module at /trademachine/,
# but old bookmarks and inbound hash links (incl. the #tm=<seed> player deep-link)
# must still land on it. A hash change can't be caught by a server redirect, so
# this runs client-side on /projections/ and forwards, preserving the tm= seed.
_PROJ_TM_REDIRECT = """<script>
(function(){
  function forward(){
    var h=location.hash||'';
    if(!(/(?:^|[#&])(?:view|tab)=trademachine/.test(h) || /[#&]tm=/.test(h))) return;
    var m=/[#&]tm=([^&]+)/.exec(h);
    location.replace('/trademachine/' + (m?('#tm='+m[1]):''));
  }
  window.addEventListener('hashchange', forward);
  forward();
})();
</script>"""

# Standalone /trademachine/ init: mount the board on load, and re-mount on a
# hashchange so an inbound #tm=<seed> re-seeds the evaluator.
_TRADE_MACHINE_INIT = """<script>
(function(){
  function mount(){ if(window.TradeMachine && window.TradeMachine.mount) window.TradeMachine.mount(); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', mount); else mount();
  window.addEventListener('hashchange', mount);
})();
</script>"""


def build_projections() -> str:
    """The /projections/ MLB Projections app - the FA module's projection
    engine applied to the whole league plus post-ETA PROSPX prospects.
    Static shell + assets/projections.js, which fetches the proj_export.py
    sidecar (data/mlb_projections.json). Styles ride the .fa-app block plus
    a small .proj-app extension in site.css. The Trade Machine is now its own
    top-level module at /trademachine/ (a redirect shim forwards old
    #view=trademachine bookmarks there)."""
    body = (
        '<div class="fa-app proj-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}<h1>MLB Projections '
        f'<span class="eephus-beta" title="{html.escape(MODULE_STAGE["projections"][1])}">β beta</span></h1></div>'
        '<span class="section-sub">five-year bWAR paths for every MLB player · floor / mean / ceiling '
        'probability buckets · contract surplus on salary-known seasons · prospects join at their PROSPX ETA</span></div>'
        '<div id="proj-view-projections">'
        '<div id="proj-banner"></div>'
        '<div class="filter-bar" id="proj-filters"></div>'
        '<div id="proj-rows"></div>'
        '</div>'
        '</div>'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/projections.js?v={_PROJ_VER}" defer></script>'
        + _PROJ_TM_REDIRECT
    )
    return page("MLB Projections - eephus.io", "projections", body,
                "Five-year bWAR projections for every MLB player - floor/mean/ceiling probability "
                "buckets, aging-curve decay, contract surplus on salary-known seasons, and PROSPX "
                "prospects joining at their projected ETA.",
                url=f"{SITE_ORIGIN}/projections/")


def build_trademachine() -> str:
    """The /trademachine/ Trade Machine module (top-level, module by Anirudh
    Iyer). Build and value a deal both ways - prospects on eFV surplus, MLB
    players on projection surplus - then the full Bayesian trade-value board.
    Static shell + assets/trademachine.js on the standalone trade_values.json /
    mlb_projections.json data. Was formerly a #view=trademachine tab inside MLB
    Projections."""
    body = (
        # id="proj-view-trademachine" is kept for trademachine.js, which scopes its
        # filter + collapse wiring to that id; .tm-app carries the standalone theming.
        '<div class="fa-app proj-app tm-app" id="proj-view-trademachine">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}<h1>Trade Machine '
        f'<span class="eephus-beta" title="{html.escape(MODULE_STAGE["trademachine"][1])}">β beta</span></h1></div>'
        '<span class="section-sub">build and value a deal both ways: prospects on eFV surplus, MLB players '
        'on projection surplus, then the full Bayesian trade-value board</span></div>'
        + _TRADE_MACHINE_BODY +
        '</div>'
        f'<link rel="stylesheet" href="/assets/trademachine.css?v={_TM_CSS_VER}">'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/trademachine.js?v={_TM_VER}" defer></script>'
        + _TRADE_MACHINE_INIT
    )
    return page("Trade Machine - eephus.io", "trademachine", body,
                "Build and value MLB trades both ways - prospects on outcome-grounded eFV surplus, "
                "MLB players on projection surplus, on one currency - plus the full Bayesian "
                "trade-value board (contract-aware, positional scarcity, opt-out adjusted).",
                url=f"{SITE_ORIGIN}/trademachine/")

def build_mlbstats() -> str:
    """The /mlbstats/ MLB Stats module - league-wide MLB stat leaderboards.
    First (and for now only) section is Bullpen Leaderboards: REM+ reliever
    ratings, team Bullpen+ quality, and bullpen charts, all computed from
    MLB play-by-play (gmLI/WPA self-computed from the StatsAPI winProbability
    feed; FIP-based skill core). Static shell + assets/mlbstats.js, which fetches
    the bullpen_export.py sidecar (data/bullpen_leaderboards.json). Styles ride
    the .fa-app block plus a small .mlbstats-app extension in site.css. The
    section nav is built to grow as more MLB stat sections land."""
    body = (
        '<div class="fa-app mlbstats-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}'
        f'<h1>MLB Stats <span class="eephus-beta" title="{html.escape(MODULE_STAGE["mlbstats"][1])}">β beta</span></h1></div>'
        '<span class="section-sub">League-wide MLB stat leaderboards. Bullpen Leaderboards - '
        'REM+ reliever skill, RIV+ impact, team Bullpen+ quality, and bullpen charts; Starter '
        'Leaderboards - SEM+ starter run-prevention skill, team Rotation+, and rotation charts; and '
        'Hitter Leaderboards - HEM+ offensive-rate skill, team Offense+, and lineup charts; and '
        'Leverage Leaderboards - realized in-game WPA impact for batters and starters, computed '
        'from the MLB season.</span></div>'
        # Section nav (built as a tablist; sections join here as they ship).
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="MLB Stats sections">'
        '<button type="button" class="mlbstats-sectionbtn active" data-mlbsection="bullpen" role="tab" aria-selected="true">Bullpen Leaderboards</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mlbsection="starters" role="tab" aria-selected="false">Starter Leaderboards</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mlbsection="hitters" role="tab" aria-selected="false">Hitter Leaderboards</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-mlbsection="leverage" role="tab" aria-selected="false">Leverage Leaderboards</button>'
        '</div>'
        '<div id="mlbstats-section-bullpen" class="mlbstats-section">'
        '<div id="mlbstats-banner"></div>'
        '<div id="mlbstats-app-root"></div>'
        '</div>'
        '<div id="mlbstats-section-starters" class="mlbstats-section" hidden>'
        '<div id="mlbstats-starters-root"></div>'
        '</div>'
        '<div id="mlbstats-section-hitters" class="mlbstats-section" hidden>'
        '<div id="mlbstats-hitters-root"></div>'
        '</div>'
        '<div id="mlbstats-section-leverage" class="mlbstats-section" hidden>'
        '<div id="mlbstats-leverage-root"></div>'
        '</div>'
        '</div>'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/mlbstats.js?v={_MLBSTATS_VER}" defer></script>'
    )
    return page("MLB Stats - eephus.io", "mlbstats", body,
                "MLB stat leaderboards from eephus.io - REM+ reliever skill and RIV+ impact, team "
                "Bullpen+ quality, SEM+ starter run-prevention, and HEM+ hitter offense, computed "
                "from the MLB season.",
                url=f"{SITE_ORIGIN}/mlbstats/")

def build_pal() -> str:
    """The /pal/ Alchemy Lab - role-conversion evaluation for MLB players.
    Both halves of the surface now ship. Pitcher role conversion:
    RP->SP Candidates (which relievers profile as
    starters), SP->RP Candidates (which starters would shine in relief), and
    Conversion History (an archive of past SP<->RP switches that doubles as
    the model's backtest set, plus pitch-mix changes). Backtest evidence is
    per direction: SP->RP validated, RP->SP structural screen only.
    Hitter positional conversion: Position Fit (which hitters are worth more
    runs at a different position), from the positional_fit.py conversion model.
    Static shell + assets/pal.js, which fetches the pal_export.py sidecar
    (data/pal.json) plus the slim positional-fit view built here
    (data/positional_fit_ui.json - the full artifact never ships). Reuses the
    arsenal / velocity / platoon Statcast data, the validated REM+ model, and
    PROSPX prospect role history. Styles ride the .fa-app block plus the
    .mlbstats-app / .pal-app extensions in site.css."""
    body = (
        '<div class="fa-app mlbstats-app pal-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}'
        f'<h1>Alchemy Lab <span class="eephus-beta" title="{html.escape(MODULE_STAGE["pal"][1])}">β beta</span></h1></div>'
        '<span class="section-sub">Players in the wrong job. Which relievers profile as starters and which starters '
        'would shine in relief, which hitters are worth more runs at a different position, plus the history of the '
        'conversions that worked and the ones that did not. The backtest grades each lane on its own: the '
        'starter-to-relief signal is validated, the reliever-to-starter list is a structural screen, and the '
        'position-conversion matrix is validated for the SIZE of a move but not for guessing which players clubs '
        'actually move.</span></div>'
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="PAL sections">'
        '<button type="button" class="mlbstats-sectionbtn active" data-palsection="rp2sp" role="tab" aria-selected="true">RP&rarr;SP Candidates</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-palsection="sp2rp" role="tab" aria-selected="false">SP&rarr;RP Candidates</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-palsection="posfit" role="tab" aria-selected="false">Position Fit</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-palsection="history" role="tab" aria-selected="false">Conversion History</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-palsection="pitchadd" role="tab" aria-selected="false">Pitch-Add Lab</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-palsection="platoon" role="tab" aria-selected="false">Reverse-Platoon Radar</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-palsection="prospects" role="tab" aria-selected="false">Prospect Watch</button>'
        '</div>'
        '<div id="pal-section" class="mlbstats-section">'
        '<div id="pal-banner"></div>'
        '<div id="pal-app-root"></div>'
        '</div>'
        '</div>'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/pal.js?v={_PAL_VER}" defer></script>'
    )
    return page("Alchemy Lab - eephus.io", "pal", body,
                "Alchemy Lab: which MLB relievers profile as starters, which starters would shine in relief, "
                "and which hitters are worth more runs at a different position, with a backtested history of past "
                "role conversions. Arsenal depth, command, platoon splits, role-adjusted velocity and a fitted "
                "positional ladder, computed from Statcast.",
                url=f"{SITE_ORIGIN}/pal/")

def build_fantasy() -> str:
    """The /fantasy/ Fantasy module - rest-of-season fantasy rankings + daily SP
    streamers, scored in the user's league format (Ottoneu FanGraphs Points
    default, SABR points, 5x5, 4x4). Static shell + assets/fantasy.js, which
    fetches the fantasy_export.py sidecar (data/fantasy.json): ROS projections
    from the FA/Projections engine, per-player counting-stat vectors the client
    re-scores per system, the probable-pitcher schedule, and eight sections
    (Daily Streamers, Two-Start SP, ROS SP/RP/Hitters, Buy/Sell, Closer Grid,
    Call-up Watch). Styles ride the .fa-app / .mlbstats-app blocks in site.css."""
    body = (
        '<div class="fa-app mlbstats-app fantasy-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}'
        f'<h1>Fantasy <span class="eephus-beta" title="{html.escape(MODULE_STAGE["fantasy"][1])}">β beta</span></h1></div>'
        '<span class="section-sub">Rest-of-season fantasy rankings and daily streamers, scored in YOUR league format - '
        'Ottoneu FanGraphs Points (default), SABR Points, Old School 5x5, or Ottoneu 4x4. ROS projections from the same '
        'engine as the MLB Projections board; matchup + regression context from REM+/SEM+/HEM+, team Offense+/Bullpen+, '
        'and xStat luck gaps.</span></div>'
        # League scoring selector (fantasy.js fills it from data/fantasy.json scoring_catalog; default FanGraphs Points).
        '<div id="fantasy-scoring" class="fantasy-scoring-bar" aria-label="League scoring format"></div>'
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="Fantasy sections">'
        '<button type="button" class="mlbstats-sectionbtn active" data-fantasysection="streamers" role="tab" aria-selected="true">Daily Streamers</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-fantasysection="two_start" role="tab" aria-selected="false">Two-Start SP</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-fantasysection="ros_sp" role="tab" aria-selected="false">ROS SP</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-fantasysection="ros_rp" role="tab" aria-selected="false">ROS RP</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-fantasysection="ros_hitter" role="tab" aria-selected="false">ROS Hitters</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-fantasysection="buysell" role="tab" aria-selected="false">Buy / Sell</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-fantasysection="closers" role="tab" aria-selected="false">Closer Grid</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-fantasysection="callups" role="tab" aria-selected="false">Call-up Watch</button>'
        '</div>'
        '<div id="fantasy-section" class="mlbstats-section">'
        '<div id="fantasy-banner"></div>'
        '<div id="fantasy-app-root"></div>'
        '</div>'
        '</div>'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        f'<script src="/assets/fantasy.js?v={_FANTASY_VER}" defer></script>'
    )
    return page("Fantasy - eephus.io", "fantasy", body,
                "Rest-of-season fantasy baseball rankings and daily SP streamers from eephus.io, scored in your league "
                "format (Ottoneu FanGraphs Points, SABR, 5x5, 4x4): SP/RP/hitter ROS ranks, two-start pitchers, "
                "buy-low/sell-high regression candidates, and a closer depth grid.",
                url=f"{SITE_ORIGIN}/fantasy/")

def build_parks() -> str:
    """The /parks/ MiLB Park Factors module - the venue context board.

    Static shell + assets/parks.js, which fetches data/milb_park_factors.json
    (tools/park_line_lab.py): 202 venues across sports 11/12/13/14/16, run and
    home-run factors per venue-season plus the vintage-safe 3-season window,
    joined client-side to the club-season rows that carry level / league /
    affiliate / home-game counts.

    DISPLAY ONLY. Nothing on this page feeds a model. The experiment that built
    the table (efv_park_line.py) is flag-gated off under a registered fail
    verdict, and the Method section says that on the page rather than burying
    it. The board also shows the UNCLAMPED factors; the clamps in the artifact
    belong to that disabled model path, not to the display.

    Not in NAV_ITEMS on purpose: the nav definition is mirrored by three
    hand-maintained static copies (prospx + the two CollegeSavant pages) that
    test_collegesavant_nav_in_sync pins, so a nav row lands with those copies.
    Discovery meanwhile rides the footer link, the homepage Across-eephus.io
    strip, and sitemap.xml."""
    body = (
        '<div class="fa-app mlbstats-app parks-app">'
        f'<div class="section-head section-head--byline"><div class="section-head-titles">{CREATED_BY_BANNER}'
        f'<h1>MiLB Park Factors <span class="eephus-beta" title="{html.escape(MODULE_STAGE["parks"][1])}">β beta</span></h1></div>'
        '<span class="section-sub">Where a minor-league stat line was earned. Run and home-run park '
        'factors for every affiliated venue from Triple-A down through the complex and Dominican '
        'leagues, built from home-versus-road scoring, centered on the league-season and shrunk toward '
        'neutral by sample. Amarillo runs a 1.21 run factor and a 1.43 home-run factor; Arkansas runs '
        '0.84. Two hitters with the same slash line did not do the same thing.</span></div>'
        '<div class="mlbstats-sectionnav" role="tablist" aria-label="Park Factors sections">'
        '<button type="button" class="mlbstats-sectionbtn active" data-parksection="board" role="tab" aria-selected="true">Venue Board</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-parksection="leagues" role="tab" aria-selected="false">League Spread</button>'
        '<button type="button" class="mlbstats-sectionbtn" data-parksection="method" role="tab" aria-selected="false">Method &amp; Sample</button>'
        '</div>'
        '<div id="parks-section" class="mlbstats-section">'
        '<div id="parks-banner"></div>'
        '<div id="parks-app-root"></div>'
        '</div>'
        '</div>'
        f'<link rel="stylesheet" href="/assets/parks.css?v={_PARKS_CSS_VER}">'
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/parks.js?v={_PARKS_VER}" defer></script>'
    )
    return page("MiLB Park Factors - eephus.io", "parks", body,
                "Minor-league park factors for every affiliated venue: run and home-run factors by "
                "season and on a vintage-safe three-season window, with the level, affiliate and "
                "home-game sample behind each one. Built from home-versus-road scoring, league-centered "
                "and sample-shrunk. Display only, no model reads them.",
                url=f"{SITE_ORIGIN}/parks/")

def build_glossary() -> str:
    """The /glossary/ unified Glossary & Methodology module - the canonical
    definition layer's page. Static shell + assets/glossary.js; definitions
    come from data/glossary.json via the shared eephus-gl.js runtime. The
    How to Read guide, methodology derivations + interactive widgets, and
    the source-vs-source backtest were ported here from the retired PROSPX
    Glossary/Methodology tab (owner decision 2026-06-10)."""
    intro = (
        '<div class="gl-intro">'
        "<p>Every number on eephus.io resolves to an entry on this page. The glossary is the "
        "platform's single source of truth: the PROSPX board, the Free Agency module, the "
        "command palette (Ctrl+K from anywhere), and every hover definition read from the same "
        "file that renders these cards.</p>"
        "<p>The analytical frame throughout is resource allocation. A prospect is a "
        "cost-controlled asset whose scouting grade implies a production forecast; a free agent "
        "is a priced asset whose contract is the market's forecast. For any priced decision the "
        "platform keeps two independently derived numbers - what the production is worth "
        "(rational value, surplus) and what the market pays (predicted or actual contract) - and "
        "never blends them, because the gap between them is the entire point.</p>"
        "<p>WAR site-wide is Baseball-Reference's bWAR: one source, every surface. Where samples "
        "are thin the models shrink toward the mean and say so; where data is missing the site "
        "shows a plain dash, never a guess.</p>"
        "<p>Model derivations and the interactive teaching widgets live under Methodology; the "
        "source-vs-source backtest under Source Comparison grades the site's own consensus "
        "against its inputs - misses included.</p>"
        "</div>"
    )
    body = (
        '<div class="gl-app">'
        '<div class="section-head"><h1>Glossary &amp; Methodology</h1>'
        '<span class="section-sub">every term, model derivation, and the track record behind the site</span></div>'
        f"{intro}"
        '<div class="filter-bar"><span class="gl-microlabel">View</span>'
        '<button class="chip active" data-glossary-view="terms">Terms</button>'
        '<button class="chip" data-glossary-view="guide">How to Read</button>'
        '<button class="chip" data-glossary-view="methodology">Methodology</button>'
        '<button class="chip" data-glossary-view="models">Models &amp; Proofs</button>'
        '<button class="chip" data-glossary-view="source-comparison">Source Comparison</button>'
        # Outbound link (not a view toggle) to the full attribution page, so the
        # Data Sources & Attribution page is reachable from this section, not just
        # the footer. The trailing arrow signals it navigates away.
        '<a class="chip gl-chip-out" href="/sources/">Data Sources &amp; Attribution →</a>'
        '</div>'
        '<div id="gl-termbar">'
        '<input id="gl-search" class="gl-search" type="search" placeholder="Search terms, abbreviations, definitions…" aria-label="Search glossary">'
        '<div class="filter-bar" id="gl-cats"></div>'
        '<div id="gl-az"></div>'
        '</div>'
        '<div id="guide-body" style="display:none;"></div>'
        '<div id="methodology-body" style="display:none;"></div>'
        '<div id="models-body" style="display:none;"></div>'
        '<div id="source-comparison-body" style="display:none;"></div>'
        '<div id="glossary-rows"></div>'
        '</div>'
        # Shared GFX engine (hub + gfx, the FA / news inject pattern): powers
        # the Source Comparison "Generate GFX" share card. Loaded BEFORE
        # glossary.js so window.EEPHUS_GFX exists when the view renders.
        f'<script src="/assets/eephus-hub.js?v={_HUB_VER}" defer></script>'
        f'<script src="/assets/eephus-gfx.js?v={_GFX_VER}" defer></script>'
        '<script src="/data/value_framework.js" defer></script>'
        f'<script src="/assets/glossary.js?v={_GLAPP_VER}" defer></script>'
    )
    return page("Glossary & Methodology - eephus.io", "glossary", body,
                "Definitions, model mechanics, and methodology for every metric on eephus.io - "
                "PROSPX prospect analytics, MLB Free Agency, and the statistical foundations.",
                url=f"{SITE_ORIGIN}/glossary/")

def build_article_page(a: dict) -> str:
    body = (
        '<a class="back-link" href="/articles/">← All articles</a>'
        '<article class="article">'
        '<header class="article-header">'
        f'<h1>{html.escape(a["title"])}</h1>'
        f'<div class="byline">{_byline(a)}</div>'
        "</header>"
        + (f'<p class="article-summary">{html.escape(a["summary"])}</p>' if a.get("summary") else "")
        + f'<div class="article-body">{a["body_html"]}</div>'
        "</article>"
        # eephus.io - article comment thread (the same forum component PROSPX uses),
        # auto-mounted client-side by eephus-ui.js from these data-* hints.
        f'<div id="eph-forum-mount" class="eph-article-forum" data-forum-scope="article" '
        f'data-forum-key="{html.escape(a["slug"])}" data-forum-title="{html.escape(a["title"])}"></div>'
    )
    # Per-article social card (assets/articles/<slug>/share-card.png) is optional - 
    # only emit og:image/twitter when one was generated for this piece.
    slug = a["slug"]
    card = ROOT / "assets" / "articles" / slug / "share-card.png"
    image = f"{SITE_ORIGIN}/assets/articles/{slug}/share-card.png" if card.exists() else ""
    return page(f'{a["title"]} - eephus.io', "articles", body, a.get("summary", ""),
                image=image, url=f"{SITE_ORIGIN}/articles/{slug}/", og_type="article")

def build_team() -> str:
    team = json.loads((CONTENT / "team.json").read_text(encoding="utf-8"))
    # Twitter / LinkedIn icon SVGs (same marks as the old masthead chips, rehomed
    # here on the team page where per-person socials belong).
    _TW_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 '
               '8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 '
               '17.52h1.833L7.084 4.126H5.117z"/></svg>')
    _LI_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 '
               '0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 '
               '5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 '
               '0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>')
    # Personal website - globe glyph (stroke-style, rides currentColor like the rest).
    _WEB_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm7.93 '
                '9h-3.46a15.6 15.6 0 0 0-1.21-5.07A8.03 8.03 0 0 1 19.93 11zM12 4.06c.93 1.28 1.85 3.7 2.16 '
                '6.94H9.84c.31-3.24 1.23-5.66 2.16-6.94zM4.07 13h3.46c.18 1.85.6 3.6 1.21 5.07A8.03 8.03 0 0 1 4.07 '
                '13zm3.46-2H4.07a8.03 8.03 0 0 1 4.67-5.07A15.6 15.6 0 0 0 7.53 11zM12 19.94c-.93-1.28-1.85-3.7-2.16-6.94h4.32c-.31 '
                '3.24-1.23 5.66-2.16 6.94zm3.26-1.87c.61-1.47 1.03-3.22 1.21-5.07h3.46a8.03 8.03 0 0 1-4.67 5.07z"/></svg>')
    # GitHub mark.
    _GH_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 '
               '9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 '
               '18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 '
               '2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 '
               '1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 '
               '2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 '
               '3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 '
               '22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>')
    # Email - classic envelope mark (rides currentColor like the rest).
    _MAIL_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 '
                 '2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5-8-5V6l8 5 8-5v2z"/></svg>')
    def _initials(name: str) -> str:
        parts = [p for p in name.split() if p[:1].isalpha()]
        if not parts:
            return "?"
        return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else parts[0][1:2])).upper()
    def _team_photo(m: dict) -> str | None:
        # Explicit `photo` path wins; otherwise auto-detect assets/team/<first>.<ext>
        # so a member just drops a file (e.g. assets/team/noah.jpg) and rebuilds - 
        # no JSON edit, and no 404 since we only emit <img> when the file exists.
        if m.get("photo"):
            return m["photo"]
        slug = (m["name"].split() or [""])[0].lower()
        for ext in ("jpg", "jpeg", "png", "webp"):
            if (ROOT / "assets" / "team" / f"{slug}.{ext}").exists():
                return f"/assets/team/{slug}.{ext}"
        return None
    # Credit badges: a LOGO mark per credit (no text), the role name on hover.
    # A crown perches on every "Creator" badge (the founder mark); non-creator
    # roles (e.g. Site Design) wear the mark alone. Marks ride currentColor so
    # the per-module accent (and both themes) flow through one style hook.
    _CROWN = ('<svg class="team-badge-crown" viewBox="0 0 24 14" aria-hidden="true">'
              '<path d="M2 12h20l-1.6-8-4.9 4L12 2 8.5 8 3.6 4z" fill="currentColor" '
              'stroke="rgba(0,0,0,.28)" stroke-width="0.5" stroke-linejoin="round"/>'
              '<circle cx="2" cy="3.2" r="1.3" fill="currentColor"/>'
              '<circle cx="12" cy="1.3" r="1.4" fill="currentColor"/>'
              '<circle cx="22" cy="3.2" r="1.3" fill="currentColor"/></svg>')
    _M_PROJ = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 17l5-5 4 3 8-9" fill="none" '
               'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
               '<circle cx="3" cy="17" r="1.5" fill="currentColor"/><circle cx="8" cy="12" r="1.5" fill="currentColor"/>'
               '<circle cx="12" cy="15" r="1.5" fill="currentColor"/><circle cx="20" cy="6" r="1.7" fill="currentColor"/></svg>')
    _M_FA = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5v19" stroke="currentColor" '
             'stroke-width="2" stroke-linecap="round"/><path d="M16.5 6.6C15.4 5.4 13.8 4.8 12 4.8c-2.5 0-4.5 '
             '1.3-4.5 3.4 0 2.1 1.8 2.9 4.5 3.6 2.7.6 4.8 1.5 4.8 3.8s-2.1 3.7-4.8 3.7c-2 0-3.8-.7-4.9-2" '
             'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    _M_CAP = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4 2.5 8.5 12 13l9.5-4.5z" fill="none" '
              'stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/><path d="M6.5 11v4.2c0 1.3 2.5 '
              '2.4 5.5 2.4s5.5-1.1 5.5-2.4V11" fill="none" stroke="currentColor" stroke-width="1.9" '
              'stroke-linecap="round" stroke-linejoin="round"/><path d="M21.5 8.5v5" stroke="currentColor" '
              'stroke-width="1.9" stroke-linecap="round"/></svg>')
    _M_PEN = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20l1.2-4.2L15 6l3 3-9.8 9.8L4 20z" '
              'fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/><path d="M13.5 7.5l3 3" '
              'stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>')
    _M_STAR = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l2.6 5.3 5.8.8-4.2 4.1 1 5.8L12 16.9 '
               '6.8 19l1-5.8L3.6 9.1l5.8-.8z" fill="none" stroke="currentColor" stroke-width="1.8" '
               'stroke-linejoin="round"/></svg>')
    _M_WEB = ('<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" '
              'stroke="currentColor" stroke-width="1.9"/><path d="M3 12h18M12 3c2.5 2.5 2.5 15.5 0 18M12 3c-2.5 '
              '2.5-2.5 15.5 0 18" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>')
    # Trade Machine: two opposing arrows (the ⇄ swap glyph the module wears site-wide),
    # so the Trade Machine creator no longer shares the generic star with Writer/Analyst.
    _M_TRADE = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h13M14 6l3 3-3 3M20 15H7M10 12l-3 3 3 3" '
                'fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    # eephus.io (the whole site): an infield diamond with the pitcher's mound.
    _M_SITE = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l9 9-9 9-9-9z" fill="none" '
               'stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>'
               '<circle cx="12" cy="12" r="1.6" fill="currentColor"/></svg>')
    # MLB Stats: leaderboard bars on a baseline.
    _M_STATS = ('<svg viewBox="0 0 24 24" aria-hidden="true"><g fill="none" stroke="currentColor" '
                'stroke-width="2" stroke-linecap="round"><path d="M5 20v-7"/><path d="M12 20V5"/>'
                '<path d="M19 20v-10"/></g><path d="M3 20h18" fill="none" stroke="currentColor" '
                'stroke-width="1.4" stroke-linecap="round"/></svg>')
    # Alchemy Lab: an Erlenmeyer flask.
    _M_ALCHEMY = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3h6M10 3v6l-4.4 8.4a2 2 0 0 0 '
                  '1.8 2.9h9.2a2 2 0 0 0 1.8-2.9L14 9V3" fill="none" stroke="currentColor" '
                  'stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>'
                  '<path d="M7.7 15h8.6" stroke="currentColor" stroke-width="1.4"/></svg>')
    def _badge_for(note: str, uid: str) -> str:
        n = note.lower()
        if "prospx" in n:                         mark, accent = prospx_ball_logo(uid, 24), "var(--accent-gold)"
        elif "projection" in n:                   mark, accent = _M_PROJ, "var(--accent-cyan)"
        elif "free agency" in n:                  mark, accent = _M_FA, "var(--accent-green)"
        elif "collegesavant" in n or "college" in n: mark, accent = _M_CAP, "var(--accent-lilac)"
        elif "eephus" in n:                       mark, accent = _M_SITE, "var(--accent-gold)"
        elif "stats" in n:                        mark, accent = _M_STATS, "var(--neon-amber)"
        elif "alchemy" in n:                      mark, accent = _M_ALCHEMY, "var(--neon-violet)"
        elif "webmaster" in n or "web" in n:      mark, accent = _M_WEB, "var(--accent-navy)"
        elif "design" in n:                       mark, accent = _M_PEN, "var(--text-secondary)"
        elif "trade" in n:                        mark, accent = _M_TRADE, "var(--accent-orange)"
        else:                                     mark, accent = _M_STAR, "var(--accent-red)"   # Writer/Analyst + any unmapped role
        creator = "creator" in n or "lead" in n or "webmaster" in n   # crown any lead/creator/webmaster role
        cls = "team-badge" + (" is-creator" if creator else "")
        label = html.escape(note)
        return (f'<span class="{cls}" title="{label}" aria-label="{label}" '
                f'style="--badge-accent:{accent}">{_CROWN if creator else ""}'
                f'<span class="team-badge-mark">{mark}</span></span>')
    # School affiliation: the school's wordmark mark (or an image at school_logo,
    # if a member provides one) plus the full name. Add a school to _SCHOOL_MARKS
    # to give its short mark a brand color.
    _SCHOOL_MARKS = {"New York University": {"short": "NYU", "color": "#57068C", "logo": "nyu.png"},
                     "University of Oklahoma": {"short": "OU", "color": "#841617", "logo": "ou.png"},
                     "Boston University": {"short": "BU", "color": "#CC0000", "logo": "bu.png"},
                     "Utah College": {"short": "UTAH", "color": "#CC0000", "logo": "utah.png"},
                     "University of California, Los Angeles": {"short": "UCLA", "color": "#2774AE", "logo": "ucla.png"},
                     "Merrimack College": {"short": "MACK", "color": "#003263", "logo": "merrimack.png"}}
    def _school_html(m: dict) -> str:
        school = (m.get("school") or "").strip()
        if not school:
            return ""
        sm = _SCHOOL_MARKS.get(school) or {}
        # Logo image (explicit school_logo, or the school's default) is used ONLY
        # when the file exists on disk - otherwise we fall back to the wordmark so
        # a missing file never renders a broken icon. A bare filename resolves
        # under assets/team/; an absolute path is used as given.
        logo = (m.get("school_logo") or sm.get("logo") or "").strip()
        mark = ""
        if logo:
            rel = logo.lstrip("/") if "/" in logo else f"assets/team/{logo}"
            if (ROOT / rel).exists():
                mark = (f'<img class="team-school-logo" src="/{html.escape(rel)}" '
                        f'alt="{html.escape(school)} logo" loading="lazy">')
        if not mark and sm.get("short"):
            mark = f'<span class="team-school-mark" style="color:{sm["color"]};">{html.escape(sm["short"])}</span>'
        return f'<div class="team-school" title="{html.escape(school)}">{mark}<span>{html.escape(school)}</span></div>'
    cards = []
    for m in team:
        handle = (m.get("handle") or "").lstrip("@")
        linkedin = (m.get("linkedin") or "").strip().rstrip("/").rsplit("/", 1)[-1]
        # Headshot: provided image (rectangular, sharp) over a monogram fallback
        # that shows when there's no photo or the file 404s - never a broken image.
        mono = f'<span class="team-monogram" aria-hidden="true">{html.escape(_initials(m["name"]))}</span>'
        photo = _team_photo(m)
        if photo:
            img = (f'<img src="{html.escape(photo)}" alt="{html.escape(m["name"])}" '
                   f'loading="lazy" onerror="this.style.display=\'none\'">')
            photo_html = f'<div class="team-photo">{mono}{img}</div>'
        else:
            photo_html = f'<div class="team-photo">{mono}</div>'
        chips = []
        if handle:
            chips.append(f'<a class="team-soc" href="https://x.com/{html.escape(handle)}" target="_blank" '
                         f'rel="noopener" title="Twitter / X - @{html.escape(handle)}" aria-label="Twitter / X - @{html.escape(handle)}">{_TW_SVG}</a>')
        if linkedin:
            chips.append(f'<a class="team-soc" href="https://www.linkedin.com/in/{html.escape(linkedin)}/" target="_blank" '
                         f'rel="noopener" title="LinkedIn - {html.escape(m["name"])}" aria-label="LinkedIn - {html.escape(m["name"])}">{_LI_SVG}</a>')
        email = (m.get("email") or "").strip()
        if email:
            chips.append(f'<a class="team-soc" href="mailto:{html.escape(email)}" '
                         f'title="Email - {html.escape(email)}" aria-label="Email - {html.escape(email)}">{_MAIL_SVG}</a>')
        website = (m.get("website") or "").strip()
        if website:
            _host = website.split("//", 1)[-1].strip("/")
            chips.append(f'<a class="team-soc" href="{html.escape(website)}" target="_blank" '
                         f'rel="noopener" title="Website - {html.escape(_host)}" aria-label="Website - {html.escape(_host)}">{_WEB_SVG}</a>')
        github = (m.get("github") or "").strip().rstrip("/").rsplit("/", 1)[-1]
        if github:
            chips.append(f'<a class="team-soc" href="https://github.com/{html.escape(github)}" target="_blank" '
                         f'rel="noopener" title="GitHub - {html.escape(github)}" aria-label="GitHub - {html.escape(github)}">{_GH_SVG}</a>')
        socials_html = f'<div class="team-socials">{"".join(chips)}</div>' if chips else ""
        # Optional credit pills (e.g. "PROSPX Creator"). `note` may be a single
        # string or a list - members with several credits get one pill each,
        # wrapped in a flex row so they reflow cleanly inside the card.
        notes = m.get("note")
        if isinstance(notes, str):
            notes = [notes]
        notes = [n for n in (notes or []) if n]
        # Module credit badges (a logo mark per role, a crown on creator/lead/webmaster
        # roles, full role name on hover) render on the FRONT face under the socials.
        note_html = (
            '<div class="team-notes">'
            + "".join(_badge_for(n, f'{_member_slug(m["name"])}-{i}') for i, n in enumerate(notes))
            + "</div>"
        ) if notes else ""
        slug = _member_slug(m["name"])
        # Back face: the owner fills in the specific sections / models / metrics
        # each developer built later. Optional `back` field in team.json (a list
        # of strings, or a preformatted HTML string) drives it; absent -> a plain
        # placeholder so the flip always has something to show.
        back = m.get("back")
        if isinstance(back, str) and back.strip():
            back_body = back
        elif isinstance(back, list) and back:
            back_body = ('<ul class="team-back-list">'
                         + "".join(f'<li>{html.escape(str(b))}</li>' for b in back if b)
                         + "</ul>")
        else:
            back_body = '<p class="team-back-empty">Detailed contributions coming soon.</p>'
        front_face = (
            f'<div class="card team-card-face team-card-front">{photo_html}'
            f'<p class="name">{html.escape(m["name"])}</p>{_school_html(m)}{socials_html}{note_html}'
            '<span class="team-flip-hint" aria-hidden="true">flip &#8635;</span></div>'
        )
        back_face = (
            '<div class="card team-card-face team-card-back">'
            f'<div class="team-back-head">{html.escape(m["name"])}</div>{back_body}'
            '<span class="team-flip-hint" aria-hidden="true">back &#8635;</span></div>'
        )
        cards.append(
            f'<div class="team-card team-flip" id="member-{slug}" tabindex="0" role="button" '
            f'aria-pressed="false" aria-label="{html.escape(m["name"])} - activate to flip the card for contribution details">'
            f'<div class="team-card-inner">{front_face}{back_face}</div></div>'
        )
    follow = (
        '<div class="team-follow"><span class="team-follow-label">Follow</span>'
        f'{_x_link("eephus_io")}{_x_link("MLBPROSPX")}{_discord_link()}</div>'
    )
    mission = (
        "<p class=\"team-mission\">eephus.io is a collaborative sabermetric analysis project "
        "created by us, the development team (listed below). We are all college "
        "students actively pursuing futures in baseball. Please contact any of us "
        "for questions, feedback, or opportunities.</p>"
    )
    # Click / keyboard flip: toggles .is-flipped on a card. Clicks on the social
    # links (or any future back-face link/button) do NOT flip, so links still
    # work. Self-contained inline script (page() inserts body raw); plain ASCII,
    # no em-dashes (copy gate scans generated HTML).
    flip_js = (
        '<script>(function(){'
        'function toggle(card){var f=card.classList.toggle("is-flipped");'
        'card.setAttribute("aria-pressed",f?"true":"false");}'
        'document.querySelectorAll(".team-flip").forEach(function(card){'
        'card.addEventListener("click",function(e){'
        'if(e.target.closest("a,button"))return;toggle(card);});'
        'card.addEventListener("keydown",function(e){'
        'if(e.key==="Enter"||e.key===" "){e.preventDefault();toggle(card);}});'
        '});})();</script>'
    )
    body = (
        '<div class="section-head"><h1>Developers</h1></div>'
        f'{mission}'
        f'{follow}'
        f'<div class="team-grid">{"".join(cards)}</div>'
        f'{flip_js}'
    )
    return page("Developers - eephus.io", "team", body, "The team behind eephus.io.",
                url=f"{SITE_ORIGIN}/team/")

# --------------------------------------------------------------------------- #
# /teams/ - RETIRED standalone module (merged into MLB Projections
# 2026-06-12). The org-dashboard columns (farm rank/score, farm surplus,
# top prospect, cross-module links) now ride the Team Outlook view's
# baked farm blocks (proj_export._org_farm_blocks). The URL stays alive
# as a redirect so bookmarks and external links keep working.
# --------------------------------------------------------------------------- #
def build_sources() -> str:
    """/sources/ - data sources and attribution. Trust page for the Open Beta:
    names every upstream the platform reads, what it's used for, and the
    editorial stance (consensus across sources; no single list republished)."""
    rows = [
        ("FanGraphs", "https://www.fangraphs.com/",
         "Prospect rankings, FV grades, tool grades, and scouting reports (one of the "
         "seven PROSPX consensus inputs); league stats and park factors."),
        ("MLB Pipeline", "https://www.mlb.com/prospects",
         "Prospect rankings and grades (consensus input); draft bonus pools and slot values."),
        ("Baseball America", "https://www.baseballamerica.com/",
         "Prospect rankings and grades (consensus input)."),
        ("ESPN", "https://www.espn.com/mlb/",
         "Prospect rankings (consensus input); team logo imagery on internal surfaces."),
        ("The Athletic", "https://www.nytimes.com/athletic/",
         "Prospect rankings (consensus input)."),
        ("Just Baseball", "https://www.justbaseball.com/",
         "Prospect rankings (consensus input)."),
        ("TJStats", "https://x.com/TJStats",
         "Prospect rankings (consensus input) and movers wire."),
        ("MLB Stats API / Baseball Savant", "https://baseballsavant.mlb.com/",
         "Game logs, transactions, rosters, Statcast tracking data (pitch, batted-ball, "
         "and zone metrics), and player headshots via MLB static media."),
        ("Baseball-Reference", "https://www.baseball-reference.com/",
         "bWAR - the WAR framework used site-wide - plus historical player pages."),
        ("pybaseball", "https://github.com/jldbc/pybaseball",
         "Open-source Python toolkit used to pull Statcast, FanGraphs, and "
         "Baseball-Reference data programmatically."),
        ("Spotrac", "https://www.spotrac.com/",
         "Contracts, payrolls, free-agent classes, and international signing trackers."),
    ]
    cards = "".join(
        f'<div class="card source-card"><h3><a href="{html.escape(url)}" target="_blank" '
        f'rel="noopener noreferrer">{html.escape(name)}</a></h3><p>{html.escape(use)}</p></div>'
        for name, url, use in rows
    )
    body = (
        '<div class="section-head"><h1>Data Sources &amp; Attribution</h1>'
        '<span class="section-sub">every upstream the platform reads, and how it is used</span></div>'
        '<div class="gl-intro">'
        "<p>eephus.io is a sabermetric analysis platform. PROSPX grades are a consensus "
        "built across seven independent industry sources - the value added is the aggregation, "
        "calibration, and track-record audit, not any single list. No source's rankings or "
        "reports are republished wholesale; excerpts appear with attribution in the spirit of "
        "commentary and analysis. All trademarks and data remain the property of their owners.</p>"
        "<p>If you represent one of these sources and have a question or concern, email "
        '<a href="mailto:arkndjl@gmail.com">arkndjl@gmail.com</a> and it will be addressed '
        "promptly.</p>"
        "</div>"
        f'<div class="article-grid">{cards}</div>'
    )
    return page("Data Sources & Attribution - eephus.io", "", body,
                "Every data source behind eephus.io - prospect ranking inputs, Statcast and "
                "league data, contracts - and how each is used.",
                url=f"{SITE_ORIGIN}/sources/")


def build_bug_report() -> str:
    """/report/ - the "Report a bug" destination linked from every footer.
    Embeds the owner's Google Form when BUG_FORM_URL is set; otherwise shows
    an on-theme placeholder card with the mailto fallback so the page is never
    a dead end during the Open Beta."""
    intro = (
        '<div class="gl-intro"><p>Found something off? Tell us what happened and we '
        'will take a look. Please note which section the bug is in - the form below '
        'has a picker for it.</p></div>'
    )
    if BUG_FORM_URL:
        form = (
            f'<iframe src="{html.escape(BUG_FORM_URL)}" width="100%" height="820" '
            'style="border:0" title="Report a bug form">Loading the form...</iframe>'
        )
    else:
        form = (
            '<div class="card">'
            '<h3>The bug report form will appear here once it is configured.</h3>'
            '<p>In the meantime, email the details - including which section the bug is '
            'in - to <a href="' + FEEDBACK_MAILTO + '">arkndjl@gmail.com</a> and we will '
            'sort it out.</p>'
            '</div>'
        )
    body = (
        '<div class="section-head"><h1>Report a bug</h1>'
        '<span class="section-sub">tell us what broke and where</span></div>'
        f'{intro}{form}'
    )
    return page("Report a bug - eephus.io", "", body,
                "Report a bug on eephus.io - tell us what happened and which section "
                "it is in.",
                url=f"{SITE_ORIGIN}/report/")


def build_404() -> str:
    """The not-found page (nginx: `error_page 404 /404.html;`). On-theme,
    no dead ends: home link + the module rail + the palette hint."""
    body = (
        '<div class="section-head"><h1>404 - lost ball in the lights</h1>'
        '<span class="section-sub">that page does not exist, or it moved</span></div>'
        '<div class="gl-intro">'
        '<p>Try the <a href="/">homepage</a>, or jump straight into a module: '
        '<a href="/prospx/">PROSPX</a> · <a href="/collegesavant/">CollegeSavant</a> · '
        '<a href="/fa/">Free Agency</a> · <a href="/projections/">Projections</a> · '
        '<a href="/mlbstats/">MLB Stats</a> · <a href="/pal/">Alchemy Lab</a> · '
        '<a href="/glossary/">Glossary</a>.</p>'
        '<p>Looking for a player? Press <strong>Ctrl+K</strong> (⌘K on Mac) anywhere on the '
        'site and type a name.</p>'
        '</div>'
    )
    return page("Page not found - eephus.io", "", body,
                "Page not found on eephus.io.", robots="noindex")


def build_robots() -> str:
    """robots.txt - crawl everything except the data payloads (multi-MB JSON
    sidecars are for the apps, not crawlers) and the resolver stubs."""
    return (
        "User-agent: *\n"
        "Disallow: /data/\n"
        "Disallow: /player/\n"
        "Disallow: /teams/\n"
        "Allow: /\n"
        f"Sitemap: {SITE_ORIGIN}/sitemap.xml\n"
    )


def build_sitemap(articles: list[dict]) -> str:
    """sitemap.xml over the canonical public surfaces. lastmod is the build
    date for app pages (data refreshes nightly) and the article date for
    articles."""
    today = date.today().isoformat()
    pages = [
        ("/", "daily", "1.0"),
        ("/news/", "daily", "0.8"),
        ("/history/", "daily", "0.6"),
        ("/prospx/", "daily", "1.0"),
        ("/collegesavant/", "weekly", "0.8"),
        ("/collegesavant/pitcher_index.html", "weekly", "0.7"),
        ("/fa/", "daily", "0.9"),
        ("/projections/", "daily", "0.9"),
        ("/mlbstats/", "daily", "0.8"),
        ("/pal/", "daily", "0.8"),
        ("/trademachine/", "daily", "0.8"),
        ("/fantasy/", "daily", "0.8"),
        ("/parks/", "weekly", "0.6"),
        ("/articles/", "weekly", "0.7"),
        ("/forums/", "daily", "0.6"),
        ("/glossary/", "weekly", "0.7"),
        ("/sources/", "monthly", "0.3"),
        ("/team/", "monthly", "0.3"),
        ("/report/", "monthly", "0.2"),
    ]
    urls = []
    for path, freq, prio in pages:
        urls.append(
            f"  <url><loc>{SITE_ORIGIN}{path}</loc><lastmod>{today}</lastmod>"
            f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>"
        )
    for a in articles:
        lastmod = a.get("date_sort") or today
        urls.append(
            f"  <url><loc>{SITE_ORIGIN}/articles/{a['slug']}/</loc><lastmod>{lastmod}</lastmod>"
            f"<changefreq>monthly</changefreq><priority>0.6</priority></url>"
        )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")


def build_teams_redirect() -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Teams - eephus.io</title>
{FAVICON_LINKS}
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url=/projections/#view=teams">
<script>location.replace("/projections/#view=teams");</script>
</head><body>
<p style="font-family:monospace;padding:2rem;">The Teams dashboard moved into
<a href="/projections/#view=teams">MLB Projections &rarr; Team Outlook</a>.</p>
</body></html>
"""

# --------------------------------------------------------------------------- #
# Derived BROWSER payloads
# --------------------------------------------------------------------------- #
# Some model artifacts are far too heavy (or too internal) to hand a browser.
# data/positional_fit.json is 580KB of per-player evidence rows and is pinned
# in deploy/data_exclude.txt (it never reaches the webroot), and swing_plus.json
# is a model input rather than a served payload. These builders bake the SLIM,
# display-only slice each surface actually needs into its own data/*.json, which
# ships normally. Nothing is recomputed here: every number is copied straight
# off the model artifact, and anything the artifact does not carry is simply
# absent rather than filled in.
# --------------------------------------------------------------------------- #

def _team_by_mlbam() -> dict:
    """{mlbam: team} from the cross-module identity map (player_links.json).
    The positional-fit artifact carries no team; the links map is the same
    join every module already uses to cross-link a player."""
    links = _cached_data_json("player_links.json")
    out = {}
    for row in (links.get("byMlbam") or {}).values():
        try:
            mid = int(row.get("mlbam"))
        except (TypeError, ValueError):
            continue
        if row.get("team"):
            out[mid] = row["team"]
    return out


def build_positional_fit_payload() -> dict | None:
    """Slim, display-only view of data/positional_fit.json for the Alchemy Lab
    Position Fit section.

    Carries the fitted ladder (with its CI and the folklore ladder it replaces),
    the out-of-sample conversion accuracy, the DEMOTION-PREDICTION NULL, and one
    row per qualified hitter. The full artifact keeps the per-player evidence
    logs and the unqualified rows; none of that is served."""
    src = _cached_data_json("positional_fit.json")
    if not src or not src.get("players"):
        return None
    teams = _team_by_mlbam()
    fit = src.get("fit") or {}
    ladder = fit.get("ladder") or {}
    conv = src.get("conversion_accuracy") or {}
    val = src.get("validation") or {}

    def _display_name(raw: str | None) -> str:
        """The artifact stores BRef-style "Last, First"; every other surface on
        the site prints "First Last"."""
        if not raw or "," not in raw:
            return raw or ""
        last, _, first = raw.partition(",")
        return f"{first.strip()} {last.strip()}".strip()

    def _pos_history(p: dict, fit: dict) -> list[dict]:
        """Per (season, position) defensive line plus its reliability weight.

        Collapses the model's own evidence log to what a reader needs: how much he
        played there, what the glove did, and HOW MUCH TO TRUST IT. The last one is
        the part that was missing, and without it the other two mislead: 40 innings
        in right field and 900 at first are not comparable readings of a player even
        though both print an OAA.
        """
        sig = (fit.get("signal") or {})
        out = []
        for e in (p.get("evidence") or []):
            pos = e.get("pos")
            inn = e.get("inn") or 0.0
            k = ((sig.get(pos) or {}).get("k_inn") or 0.0)
            out.append({
                "season": e.get("season"), "pos": pos, "inn": inn,
                "oaa": e.get("oaa"), "frp": e.get("frp"),
                "z": e.get("z_read"),
                # None rather than a fabricated 0 when the position has no fitted
                # constant (catchers, and anything Savant does not cover).
                "rel": round(inn / (inn + k), 3) if k > 0 and inn > 0 else None,
            })
        # newest first, then by exposure, so the most informative line leads
        out.sort(key=lambda r: (-(r["season"] or 0), -(r["inn"] or 0)))
        return out

    # ---- Rng+ (legs), display-only, LF/CF destinations ONLY -----------------
    # Owner ask 1's surviving half. The ARM half was measured and no-shipped
    # (docs/efv-2026-07-30/CONVERSION_ARM_GATE_VERDICT.md): context-adjusted, the
    # infield arm spread collapses to 1.94 mph against a within-position sd of
    # 3.80, and 3B minus SS is +0.50, so arm barely selects positions. Sprint
    # speed does, but ONLY in the outfield, and that restriction is the finding
    # rather than caution about it. Measured against OAA per 1000 innings at the
    # position played (>=400 inn, 2016-2026): CF r=+0.428 [+0.342,+0.507],
    # LF +0.416 [+0.323,+0.501], but SS -0.020 [-0.122,+0.083] and 3B -0.004
    # [-0.108,+0.100]. A speed meter on an infield row would be a picture of a
    # measured zero.
    #
    # RF IS EXCLUDED even though it clears the headline bar (+0.269
    # [+0.167,+0.365]), because its PURE-CORNER subgroup does not: right fielders
    # with under 100 career CF innings are r=+0.075 [-0.111,+0.256], which cannot
    # clear zero. The RF signal is carried by displaced centre fielders, so the
    # column would be telling corner-only right fielders something not measured
    # on players like them. LF survives the identical test (+0.359
    # [+0.163,+0.528], n=89) and is not restriction-of-range.
    #
    # NOTHING here enters the model: positional_fit's own field() gets no sprint
    # term. OAA already contains the legs, so a sprint feature would double-count,
    # which is the same argument that rejected the arm feature.
    _RNG_SHIP = ("LF", "CF")
    _RNG_R = {"CF": {"r": 0.428, "ci95": [0.342, 0.507]},
              "LF": {"r": 0.416, "ci95": [0.323, 0.501]},
              "RF": {"r": 0.269, "ci95": [0.167, 0.365],
                     "excluded": "pure-corner subgroup r=+0.075 CI [-0.111,+0.256]"}}
    _rng_meta: dict = {}
    _sprint: dict = {}
    _pos_pool: dict = {}
    try:
        import savant_sprint as _ss
        _by = (_ss._payload().get("by_mlbam") or {})
        _season = int(src.get("target_season") or 0)

        def _fts(mlbam):
            """Current season, else one back, with the season we actually used."""
            yr = (_by.get(str(mlbam)) or {})
            for s in (_season, _season - 1):
                rec = yr.get(str(s))
                if rec and rec.get("ft_s"):
                    return float(rec["ft_s"]), s
            return None, None

        _pool = [float(r["ft_s"]) for _m, ys in _by.items()
                 for _s, r in ys.items() if _s == str(_season) and r.get("ft_s")]
        if len(_pool) >= 50:
            _mu = sum(_pool) / len(_pool)
            _sd = (sum((x - _mu) ** 2 for x in _pool) / len(_pool)) ** 0.5
            # Incumbent pools for the per-destination percentile: everyone with
            # >=400 innings at that position over the trailing three seasons. This
            # is the number a reader acts on, because "28.3 ft/s" means nothing
            # until you know it is the 28th percentile of centre fielders and the
            # 77th of left fielders.
            for _pos in _RNG_SHIP:
                _inn: dict = {}
                for _p in src["players"]:
                    tot = sum((e.get("inn") or 0.0) for e in (_p.get("evidence") or [])
                              if e.get("pos") == _pos
                              and (e.get("season") or 0) >= _season - 2)
                    if tot >= 400:
                        _inn[_p.get("mlbam")] = tot
                vals = sorted(v for v in (_fts(m)[0] for m in _inn) if v is not None)
                if len(vals) >= 20:
                    _pos_pool[_pos] = vals
            for _p in src["players"]:
                f, yr = _fts(_p.get("mlbam"))
                if f is None:
                    continue
                pct = {}
                for _pos, vals in _pos_pool.items():
                    below = sum(1 for v in vals if v < f)
                    pct[_pos] = int(round(100.0 * below / len(vals)))
                _sprint[_p.get("mlbam")] = {
                    "plus": round(100.0 + 10.0 * (f - _mu) / _sd),
                    "fts": round(f, 1), "season": yr, "pct": pct,
                }
            _rng_meta = {
                "anchor": {"season": _season, "n": len(_pool),
                           "mean": round(_mu, 2), "sd": round(_sd, 2)},
                "scale": "100 + 10z on the current-season MLB position-player pool",
                "shipPositions": list(_RNG_SHIP),
                "r": _RNG_R,
                "pools": {k: {"n": len(v), "p10": v[int(0.10 * (len(v) - 1))],
                              "p50": v[int(0.50 * (len(v) - 1))],
                              "p90": v[int(0.90 * (len(v) - 1))]}
                          for k, v in _pos_pool.items()},
                "note": ("Display only. Sprint speed is not a model input: OAA already "
                         "contains the legs, so adding it would double-count."),
            }
    except Exception:
        log.exception("Rng+ block skipped; Position Fit renders without it")

    def _row(p: dict) -> dict:
        pos_totals = {k: v.get("def_total") for k, v in (p.get("by_position") or {}).items()
                      if v.get("feasible") and v.get("def_total") is not None}
        row = {
            "mlbam": p.get("mlbam"),
            "name": _display_name(p.get("name")),
            "age": p.get("age"),
            "pa": p.get("pa"),
            "pos": p.get("current_pos"),
            "best": p.get("best_pos"),
            "gain": p.get("gain_runs_per_650"),
            "gainSe": p.get("gain_se"),
            "demPos": p.get("demotion_pos"),
            "demGain": p.get("demotion_gain"),
            "demSe": p.get("demotion_se"),
            "demPlayer": p.get("demotion_gain_player_part"),
            "demLeague": p.get("demotion_gain_league_part"),
            "gloveZ": p.get("glove_z"),
            "gloveZSe": p.get("glove_z_se"),
            "gloveRuns": p.get("glove_runs_per_650_at_current"),
            "bat": p.get("bat_runs_per_650"),
            "misplaced": bool(p.get("flagged_misplaced")),
            "demoted": bool(p.get("flagged_demotion")),
            "byPos": pos_totals,
            # Per-position defensive HISTORY, newly served 2026-07-30 (owner ask 1:
            # "check their OAA/DRS at specific positions they've played to see which
            # position they've performed best at, while also calibrating this for
            # sample size"). The evidence log was already computed and deliberately
            # not served; the missing half was the sample-size read, which is what
            # makes the comparison legitimate.
            #
            # `rel` is that read: innings/(innings + k_inn) for the position, using
            # the per-position stabilization constants the model already FITTED
            # (fit.signal.k_inn, 632 innings at CF through 2,539 at 1B). Identical
            # raw OAA means very different things at the two ends of that range, so
            # a reader comparing a player's spots without it would be comparing
            # confidence as if it were performance. 1.0 means a fully stabilized
            # read; 0.2 means treat the number as a rumour.
            "hist": _pos_history(p, fit),
        }
        if p.get("mlbam") in teams:
            row["team"] = teams[p["mlbam"]]
        if p.get("mlbam") in _sprint:
            row["rng"] = _sprint[p["mlbam"]]
        return {k: v for k, v in row.items() if v is not None}

    rows = [_row(p) for p in src["players"]
            if p.get("qualified") and not p.get("c_out_of_scope")
            and p.get("current_pos") and p.get("gain_runs_per_650") is not None]
    rows.sort(key=lambda r: -(r.get("gain") or 0))
    return {
        "generated_at": src.get("generated_at"),
        "model": src.get("model"),
        "season": src.get("target_season"),
        "valueIdentity": src.get("value_identity"),
        "nPlayers": src.get("n_players"),
        "nQualified": src.get("n_qualified"),
        "nFlagged": src.get("n_flagged"),
        "nFlaggedDemotion": src.get("n_flagged_demotion"),
        "flagRule": src.get("flag_rule"),
        "outOfScope": src.get("out_of_scope"),
        "sources": src.get("sources"),
        "caveats": src.get("caveats"),
        "rngMeta": _rng_meta or None,
        "ladder": {
            "units": ladder.get("units"),
            "method": ladder.get("method"),
            "values": ladder.get("values"),
            "ci95": ladder.get("ci95"),
            "folklore": ladder.get("folklore_ladder"),
            "r2": ladder.get("r2"),
            "residSd": ladder.get("resid_sd"),
            "nPlayerSeasons": ladder.get("n_player_seasons"),
            "seasons": ladder.get("seasons"),
            "minPa": ladder.get("min_pa"),
        },
        "accuracy": {
            "nConversions": conv.get("n_conversions"),
            "minInningsEachSide": conv.get("min_innings_each_side"),
            "mae": conv.get("mae"),
            "rmse": conv.get("rmse"),
            "corr": conv.get("corr_with_actual"),
            "advantage": conv.get("mae_advantage_over"),
            "permNull95": conv.get("perm_null95_mae_advantage"),
            "nTimeSplits": conv.get("n_time_splits"),
            "seasonAdvantageMean": conv.get("season_advantage_mean"),
            "seasonAdvantagePositiveIn": conv.get("season_advantage_positive_in"),
        },
        "demotionNull": {
            "nScored": val.get("n_scored"),
            "nMovedDown": val.get("n_moved_down"),
            "baseRate": val.get("base_rate_moved_down"),
            "auc": val.get("auc"),
            "modelMinus": val.get("model_minus"),
            "permNull95": val.get("perm_null95_auc_minus_half"),
            "nTimeSplits": val.get("n_time_splits"),
            "seasonAucMean": val.get("season_auc_mean"),
            "seasonAucSd": val.get("season_auc_sd"),
            "flagRule": val.get("flag_rule"),
            "flagRuleControl": val.get("flag_rule_control"),
            "destinationTop1": val.get("destination_top1"),
            "promotionSide": val.get("promotion_side"),
            "labelDefinition": val.get("label_definition"),
        },
        "rows": rows,
    }


# Bat-speed delta. swing_plus.json is a model input (per-season Swing+ from MLB
# bat tracking, 2024+). Only players with BOTH of the last two tracked seasons
# have a computable year-over-year delta - everyone else gets an explicit
# no-data state on the card rather than a chip implying coverage we don't have.
# The alert cut is the 10th percentile of the MEASURED delta distribution in
# this same population (a distributional flag, not a validated predictor), so
# no threshold is hand-set here.
_SWING_MIN_N = 180          # the swing_plus low_n convention (partial tracking)


def build_swing_delta_payload() -> dict | None:
    src = _cached_data_json("swing_plus.json")
    players = (src or {}).get("players") or {}
    if not players:
        return None
    seasons: set[int] = set()
    for row in players.values():
        for y in (row.get("seasons") or {}):
            try:
                seasons.add(int(y))
            except (TypeError, ValueError):
                pass
    if len(seasons) < 2:
        return None
    latest, prior = sorted(seasons)[-1], sorted(seasons)[-2]
    out, deltas = {}, []
    n_latest_only = 0
    for mlbam, row in players.items():
        ss = row.get("seasons") or {}
        a, b = ss.get(str(prior)), ss.get(str(latest))
        if not b or b.get("swing_plus") is None:
            continue
        if not a or a.get("swing_plus") is None:
            n_latest_only += 1
            continue
        d = round(float(b["swing_plus"]) - float(a["swing_plus"]), 1)
        deltas.append(d)
        out[str(mlbam)] = {
            "d": d,
            "prior": round(float(a["swing_plus"]), 1),
            "latest": round(float(b["swing_plus"]), 1),
            "nPrior": a.get("n_swings"),
            "nLatest": b.get("n_swings"),
            "lowN": bool((a.get("n_swings") or 0) < _SWING_MIN_N
                         or (b.get("n_swings") or 0) < _SWING_MIN_N),
        }
    if len(deltas) < 30:
        return None
    ds = sorted(deltas)

    def _pct(q: float) -> float:
        i = q * (len(ds) - 1)
        lo, hi = int(math.floor(i)), int(math.ceil(i))
        return round(ds[lo] + (ds[hi] - ds[lo]) * (i - lo), 2)

    return {
        "generated_at": src.get("generated_at"),
        "model": src.get("model"),
        "priorSeason": prior,
        "latestSeason": latest,
        "minSwings": _SWING_MIN_N,
        "n": len(out),
        "nLatestOnly": n_latest_only,
        "nScored": src.get("n_scored"),
        "dist": {"p10": _pct(0.10), "p25": _pct(0.25), "p50": _pct(0.50),
                 "p75": _pct(0.75), "p90": _pct(0.90),
                 "mean": round(sum(ds) / len(ds), 2)},
        "players": out,
    }


# Current-season MLB stat line, keyed by MLBAM, for the modules whose rows carry
# no stats of their own (the FA class board is a market payload). Every field is
# lifted verbatim from a shipped leaderboard; nothing is recomputed. NOTE what is
# NOT here: this site DERIVES no wRC+ and no xFIP, so neither is derived into
# this payload - HEM+ (offense-rate index) and FIP/ERA are the numbers the site
# actually computes.
#
# Sharpened 2026-07-31, because the MLB Stats hitter board now shows a wRC+
# column and a reader could otherwise read "no wRC+" as contradicting it. Both
# statements are true and they are about different things: the site derives no
# wRC+ of its own, and the board's wRC+ is MLB's PUBLISHED value read verbatim
# (hitter_export.load_published_wrc_plus). Display is not derivation. This
# payload deliberately stays a derived-numbers payload and does not carry the
# published figure, so a downstream module cannot mistake a passed-through
# industry number for one of ours.
def build_current_lines_payload() -> dict | None:
    hit = _cached_data_json("hitter_leaderboards.json")
    sp = _cached_data_json("starter_leaderboards.json")
    rp = _cached_data_json("bullpen_leaderboards.json")
    if not (hit.get("hitters") or sp.get("starters")):
        return None
    out: dict[str, dict] = {}
    for h in (hit.get("hitters") or []):
        if h.get("mlbam") is None:
            continue
        out[str(h["mlbam"])] = _clean_line({
            "side": "hit", "team": h.get("team"), "bats": h.get("bats"),
            "pa": h.get("pa"), "hr": h.get("hr"), "sb": h.get("sb"),
            "avg": h.get("avg"), "obp": h.get("obp"), "slg": h.get("slg"),
            "ops": h.get("ops"), "woba": h.get("woba_raw"),
            "hem": h.get("hem_plus"), "xhem": h.get("xhem_plus"),
            "tier": h.get("tier"), "qual": h.get("qualified"),
        })
    for s in (sp.get("starters") or []):
        if s.get("mlbam") is None:
            continue
        out[str(s["mlbam"])] = _clean_line({
            "side": "sp", "team": s.get("team"), "role": s.get("role"),
            "ip": s.get("ip"), "gs": s.get("gs"), "era": s.get("era"),
            "fip": s.get("fip"), "kPct": s.get("k_pct"), "bbPct": s.get("bb_pct"),
            "sem": s.get("sem_plus"), "xsem": s.get("xsem_plus"),
            "qual": s.get("qualified"),
        })
    for r in (rp.get("relievers") or []):
        if r.get("mlbam") is None or str(r["mlbam"]) in out:
            continue
        out[str(r["mlbam"])] = _clean_line({
            "side": "rp", "team": r.get("team"), "role": r.get("role"),
            "ip": r.get("ip"), "era": r.get("era"), "fip": r.get("fip"),
            "kPct": r.get("k_pct"), "bbPct": r.get("bb_pct"),
            "rem": r.get("rem_plus"), "gmli": r.get("gmli"),
            "qual": r.get("qualified"),
        })
    if not out:
        return None
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d"),
        "season": hit.get("season") or sp.get("season"),
        "asOf": hit.get("as_of") or sp.get("as_of"),
        "note": ("Current-season MLB lines lifted verbatim from the eephus.io "
                 "leaderboards. This site derives no wRC+ and no xFIP of its "
                 "own, so neither is served here: HEM+ is the offense-rate "
                 "index it does compute and FIP / SEM+ / REM+ are the "
                 "run-prevention numbers. The MLB Stats hitter board does show "
                 "a wRC+ column, but that figure is MLB's published wRC+ "
                 "displayed verbatim rather than anything this site derives, "
                 "and it is deliberately not carried in this payload."),
        "n": len(out),
        "players": out,
    }


def _clean_line(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


# --------------------------------------------------------------------------- #
def _write(rel: str, content: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  wrote {rel}")

def main() -> None:
    print("build_site.py - generating editorial pages")
    art_dir = CONTENT / "articles"
    articles = [parse_article(p) for p in sorted(art_dir.glob("*.md"))] if art_dir.exists() else []
    articles.sort(key=lambda a: a.get("date_sort", ""), reverse=True)  # newest first

    data = load_site_data()
    print(" data layer:", "loaded" if data else "MISSING (run run_monthly) - modules will be empty")

    _write("index.html", build_home(articles, data))
    _write("news/index.html", build_news(data))
    _write("history/index.html", build_this_day(data))
    _write("articles/index.html", build_articles_index(articles))
    for a in articles:
        _write(f"articles/{a['slug']}/index.html", build_article_page(a))
    _write("forums/index.html", build_forums_index())
    _write("fa/index.html", build_fa())
    _write("projections/index.html", build_projections())
    _write("mlbstats/index.html", build_mlbstats())
    _write("pal/index.html", build_pal())
    _write("trademachine/index.html", build_trademachine())
    _write("fantasy/index.html", build_fantasy())
    _write("parks/index.html", build_parks())
    _write("glossary/index.html", build_glossary())
    _write("teams/index.html", build_teams_redirect())
    _write("team/index.html", build_team())
    _write("sources/index.html", build_sources())
    _write("report/index.html", build_bug_report())
    _write("404.html", build_404())
    _write("robots.txt", build_robots())
    _write("sitemap.xml", build_sitemap(articles))

    # Derived browser payloads (slim, display-only slices of heavier or
    # non-shipping model artifacts). Absent source => the file is left exactly
    # as it was, and the surface paints its own empty state.
    for rel, builder in (("data/positional_fit_ui.json", build_positional_fit_payload),
                         ("data/swing_delta.json", build_swing_delta_payload),
                         ("data/mlb_current_lines.json", build_current_lines_payload)):
        payload = builder()
        if payload:
            _write(rel, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        else:
            print(f"  skipped {rel} (source artifact missing or too thin)")
    print(f"done - {len(articles)} article(s).")

if __name__ == "__main__":
    main()
