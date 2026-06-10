# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""
build_site.py — static-site generator for the editorial pages of eephus.io.

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
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import markdown as md

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
SITE_ORIGIN = "https://eephus.io"   # absolute base for canonical + social-card (og/twitter) URLs

# Cache-bust assets/site.css by content hash so browsers/CDNs always pull the
# latest stylesheet after a rebuild — otherwise a stale cached CSS shows the old
# layout (frozen ticker, unstyled callout, etc.) even though the files updated.
def _asset_ver(rel: str) -> str:
    try:
        return hashlib.md5((ROOT / rel).read_bytes()).hexdigest()[:8]
    except OSError:
        return "1"
_CSS_VER = _asset_ver("assets/site.css")
_ACCT_VER = _asset_ver("assets/eephus-account.js")
_UI_VER = _asset_ver("assets/eephus-ui.js")
_ACCT_CSS_VER = _asset_ver("assets/eephus-account.css")
_BG_VER = _asset_ver("assets/eephus-bg.js")
_FA_VER = _asset_ver("assets/fa.js")

# eephus.io account layer (Parts 1-7), injected before </body> on every editorial
# page. OPTIONAL by design: assets/eephus-config.js is git-ignored and absent on
# the public tree, so its <script> 404s harmlessly and window.EEPHUS_SUPABASE stays
# undefined — eephus-account.js then runs fully inert (no Supabase SDK fetch, no
# behavior change) and the page renders exactly as today. When config IS present
# the module self-injects the SDK and lights up the account UI.
ACCOUNT_SCRIPTS = (
    f'<script src="/assets/eephus-config.js" defer></script>\n'
    f'<script src="/assets/eephus-account.js?v={_ACCT_VER}" defer></script>\n'
    f'<script src="/assets/eephus-ui.js?v={_UI_VER}" defer></script>\n'
    # Dark-theme phosphor-starfield background (shared with PROSPX). Rides the
    # per-page script block; inert (mounts nothing) under the light theme.
    f'<script src="/assets/eephus-bg.js?v={_BG_VER}" defer></script>'
)
# Account/forum stylesheet — linked in <head> after site.css on every editorial
# page (scoped under .eph-*; the circular avatar is the one sanctioned curve).
ACCOUNT_CSS_LINK = f'<link rel="stylesheet" href="/assets/eephus-account.css?v={_ACCT_CSS_VER}">'

# Unified prospect-photo resolution — mirrors PROSPX's headshotURL(): consult the
# resolved context map (data/photo_ctx.json, built by headshots.py) and use the
# REAL MiLB/MLB photo for resolved ids ('67'/'milb'); fall back to the generic
# silhouette overlay (always 200 — never a broken image) when unresolved/'none'.
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

NAV_ITEMS = [
    ("home",     "Home",             "/"),
    ("articles", "Articles",         "/articles/"),
    ("prospx",   "PROSPX",           "/prospx/"),
    ("fa",       "Free Agency",      "/fa/"),
    ("forums",   "Forums",           "/forums/"),
    ("team",     "Development Team",  "/team/"),
]

# PROSPX sub-sections — deep links into the app (section = `tab` query param in
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
    ("Glossary",      "/prospx/#tab=glossary"),
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

# --------------------------------------------------------------------------- #
# Brand: one version string + one beta badge, the eephus.io placeholder logo,
# and a shared X/social link. THE SINGLE SOURCE for the version is EEPHUS_VERSION
# here; the prospx/index.html static header mirrors the same literal (its own
# hand-edited file) and points back to this constant in a comment.
# --------------------------------------------------------------------------- #
EEPHUS_VERSION = "β v1.0"
BETA_BADGE = (
    f'<span class="eephus-beta" title="eephus.io is in beta — version 1.0">'
    f'{html.escape(EEPHUS_VERSION)}</span>'
)

# Modern X (Twitter) glyph — module-level so social links on every surface share
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

# eephus.io merged brand mark — the "signature pitch" arc is now PART of the
# lettering: the lob launches off the leading "e", crests with the ball at
# apex, and lands on the "o". Everything is em-scaled inside the nameplate,
# so the same mark renders at masthead (clamp 2.4-4rem) and sidebar (20px)
# sizes without separate art. Arc carries the cardinal→gold→green→navy
# masthead gradient (vector-effect keeps the stroke crisp under the
# stretch-to-width scaling); the ball is its own fixed-aspect SVG so it can
# never squash, punches through via .eephus-logo-ball (theme-aware bg fill),
# and the seam rides currentColor.
def eephus_merged_wordmark(uid: str, tag: str = "h1") -> str:
    grad = f"eephus-arc-{uid}"   # per-instance gradient id — two marks per page
    arc = (
        f'<svg class="ew-arc" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">'
        f'<defs><linearGradient id="{grad}" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%" stop-color="#B91C1C"/><stop offset="38%" stop-color="#C9A227"/>'
        '<stop offset="68%" stop-color="#1F7A3A"/><stop offset="100%" stop-color="#0E2B4D"/>'
        '</linearGradient></defs>'
        f'<path d="M 3 30 Q 50 -24 97 30" fill="none" stroke="url(#{grad})" '
        'stroke-width="2.4" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>'
        f'<svg class="ew-ball" viewBox="0 0 24 24" aria-hidden="true">'
        f'<circle class="eephus-logo-ball" cx="12" cy="12" r="8.5" stroke="url(#{grad})" stroke-width="3"/>'
        '<path class="eephus-logo-seam" d="M 6.5 10 Q 12 15.5 17.5 10" fill="none" '
        'stroke="currentColor" stroke-width="1.5"/></svg>'
    )
    return (f'<{tag} class="nameplate eephus-wordmark-merged">{arc}'
            f'eephus<span class="dot">.io</span></{tag}>')

def eephus_logo_lockup(badge: bool = True) -> str:
    """Homepage hero lockup: the merged arc-wordmark with the β tag and the
    @eephus_io chip stacked beside it (β on top, X under — the X chip carries
    the link accent so it reads clickable)."""
    chips = (
        f'<div class="eephus-logo-chips">{BETA_BADGE}'
        f'{_x_link("eephus_io", cls="eph-xlink--beta eph-xlink--live")}</div>'
    ) if badge else ""
    return f'<div class="eephus-logo">{eephus_merged_wordmark("mast")}{chips}</div>'

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
# Prospect deep-linking — turn the first mention of a known player's name into a
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
    """name(lowercased) -> {slug, handle} from content/team.json — the single
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
    # invalid HTML and the browser splits the card apart) — render the author +
    # @handle as text there, and only deep-link on the standalone article page.
    author = (meta.get("author", "") or "").strip()
    member = _team_index().get(author.lower())  # None for guest authors
    # Author name → their Development Team card (deep-linked) when they're on the
    # team and we're allowed to emit a link; otherwise plain text. No broken
    # anchors — a guest author with no card simply isn't linked.
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
    items = []
    for key, label, href in NAV_ITEMS:
        cls = ' class="is-active"' if key == active else ""
        items.append(f'<a href="{href}"{cls}>{html.escape(label)}</a>')
    # Site-wide controls (right-aligned), matching PROSPX's primary nav: a
    # Watchlist deep-link into PROSPX + the Dark Mode toggle.
    controls = (
        '<div class="eephus-nav-controls">'
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
        f'<span class="eephus-brand"><a class="eephus-wordmark" href="/">eephus.io</a>{BETA_BADGE}</span>'
        f'<nav class="eephus-links">{"".join(items)}</nav>'
        f'{controls}'
        "</header>"
    )

def _social_meta(title: str, description: str, image: str = "", url: str = "") -> str:
    """Open Graph + Twitter card tags so a shared link (X/Facebook/iMessage) renders a
    rich preview. Emitted only when a page supplies an absolute share-card `image`."""
    t, d = html.escape(title), html.escape(description)
    tags = ['<meta property="og:type" content="article">',
            f'<meta property="og:title" content="{t}">',
            f'<meta property="og:description" content="{d}">',
            '<meta property="og:site_name" content="eephus.io">']
    if url:
        tags += [f'<meta property="og:url" content="{html.escape(url)}">',
                 f'<link rel="canonical" href="{html.escape(url)}">']
    if image:
        tags += [f'<meta property="og:image" content="{html.escape(image)}">',
                 '<meta name="twitter:card" content="summary_large_image">',
                 f'<meta name="twitter:title" content="{t}">',
                 f'<meta name="twitter:description" content="{d}">',
                 f'<meta name="twitter:image" content="{html.escape(image)}">']
    return "\n".join(tags)

def page(title: str, active: str, body: str, description: str = "",
         image: str = "", url: str = "") -> str:
    desc = html.escape(description or "eephus.io — editorial baseball analytics portal")
    social = _social_meta(title, description or "eephus.io — editorial baseball analytics portal",
                          image, url) if image else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{THEME_INIT}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{desc}">
{social}
<link rel="stylesheet" href="/assets/site.css?v={_CSS_VER}">
{ACCOUNT_CSS_LINK}
</head>
<body class="eephus-page">
{_nav(active)}
<main class="eephus-wrap">
{body}
</main>
<footer class="eephus-footer">
  <span>eephus.io — editorial baseball analytics</span>
  <span>© {date.today().year} eephus.io</span>
</footer>
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

def _fmt_iso_date(s: str | None) -> str:
    if not s:
        return "—"
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%B %d, %Y").replace(" 0", " ")
    except ValueError:
        return "—"

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
    # "fa:" keys belong to the Free Agency surface (separate from PROSPX) —
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
    pts = p.get("points") or []
    if pts and pts[-1].get("consensus_fv_label") is not None:
        return str(pts[-1]["consensus_fv_label"])
    fv = p.get("fv_close")
    return str(round(fv)) if fv is not None else "—"

def _fv_pill(p: dict) -> str:
    fv = p.get("fv_close")
    cls = "fv-pill"
    if fv is not None and fv >= 61:
        cls += " holo"
    elif fv is not None and fv >= 60:
        cls += " gold"
    return f'<span class="{cls}">{html.escape(_fv_label(p))}</span>'

def _meta(*parts) -> str:
    return html.escape(" · ".join(str(x) for x in parts if x))

# --------------------------------------------------------------------------- #
# Real consensus-grade movement, computed from the player's own points[].
#
# `stock` in timeseries.json is the PERFORMANCE-ANCHORED MOVEMENT ENGINE
# (spotlights.compute_movement): its `delta` is a composite score (perf +
# skills + list-jump + pedigree) and its from/to dates are simply the last two
# snapshots — with daily TJStats Live captures that's "yesterday → today" for
# every active prospect. The homepage was written against the legacy
# stock_movement shape (a true FV delta over a meaningful window) and silently
# broke when storage switched the field to the engine: the wire showed engine
# scores as "▲ +5 FV" items dated at the latest Live refresh. These helpers
# read the published grade history directly so a "+N FV" on the homepage is
# always a real grade change — and wire items are dated when the consensus
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

def _latest_fv_change(p: dict) -> tuple[str, int] | None:
    """The most recent ACTUAL grade change as (date_of_change, step). None when
    the published grade has never moved. This is what the wire treats as FV
    news — daily Live re-confirmations of an unchanged grade are not events."""
    series = _label_series(p)
    for i in range(len(series) - 1, 0, -1):
        prev_v = series[i - 1][1]
        cur_d, cur_v = series[i]
        if cur_v != prev_v:
            return (cur_d, cur_v - prev_v)
    return None

def _row_mover(p: dict, d: int) -> str:
    up = d > 0
    # Mini FV-history sparkline — reinforces the stock-chart identity. Colored
    # by direction; the curve stays smooth (the sharp-corner rule is for UI
    # chrome, not plotted lines).
    spark = _fv_sparkline(p.get("points"), "var(--accent-green)" if up else "var(--accent-red)", w=58, h=20)
    spark_html = f'<span class="row-spark">{spark}</span>' if spark else '<span class="row-spark"></span>'
    # Team logo leads the row — same idiom as Top Prospects / Recent Graduates,
    # so the org reads at a glance and the meta cell can drop the code.
    return (f'<a class="row-link" href="{_player_href(p.get("player_key"))}">'
            f'{_team_logo(p.get("org"))}'
            f'<span class="row-name">{html.escape(p.get("player_name") or "")}</span>'
            f'<span class="row-meta">{_meta(p.get("position"))}</span>'
            f'{spark_html}'
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
    WAR, and a sub-threshold prospect shows FV — never a WAG number.

    The sample gate is the WAG model's OWN `below_meaningful_exposure` flag
    (config wag.meaningful_exposure = 200 PA / 80 IP ≈ ⅓ season); display and
    methodology share one source of truth rather than a re-invented threshold.

    NB on the data model: WAG (`debuted_value.wag`) is computed FROM a player's
    MLB sample, so in practice only graduates carry one — the WAG branch below is
    reachable only if a pre-graduation WAG is ever added; today every WAG-carrier
    graduates to the WAR branch. That is intended, not dead weight.

    Returns {metric: 'WAR'|'WAG'|'FV'|None, cls, html} — `metric` labels the
    value so a number sitting in a shared slot is never mistaken for another now
    that the slot can hold any of three. `html` is render-ready and HTML-safe."""
    cw = p.get("career_war") or {}
    is_grad = (p.get("status") == "debuted") or (cw.get("career_war") is not None)

    # 1) Graduated -> raw MLB WAR (career-since-debut bWAR). WAR/yr stays in
    #    the hover tooltip only — as a visible suffix it was noise on the
    #    homepage grad rows, where most players have one partial MLB season
    #    and the per-year rate is just the WAR number echoed back.
    if is_grad:
        war = cw.get("career_war")
        if war is None:
            # bWAR hasn't posted yet (brand-new debut) — keep it a WAR slot and be
            # honest the sample hasn't landed; never fabricate a number.
            return {"metric": "WAR", "cls": "flat",
                    "html": '<span class="row-meta" title="MLB WAR not yet posted">— WAR</span>'}
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

    # 3) No meaningful on-field sample yet -> FV (the scouting-consensus projection).
    fv = p.get("fv_close") or p.get("consensus_fv") or p.get("fv")
    if fv is not None:
        return {"metric": "FV", "cls": "flat",
                "html": (f'<span class="row-meta" title="Final prospect FV — no MLB sample yet">'
                         f'FV {int(round(fv))}</span>')}
    return {"metric": None, "cls": "flat", "html": '<span class="row-meta">debut</span>'}


def _row_grad(g: dict) -> str:
    # Recent graduates are MLB players now, so the shared value slot shows WAR
    # (not WAG) via the single display_metric_for() escalation helper.
    wtxt = display_metric_for(g)["html"]
    return (f'<a class="row-link" href="{_player_href(g.get("player_key"))}">'
            f'{_team_logo(g.get("org"))}<span class="row-name">{html.escape(g.get("player_name") or "")}</span>'
            f'<span class="row-meta">{_meta(g.get("position"), g.get("org"))}</span>{wtxt}</a>')

def _recent_trades_html(players: list, n: int = 6) -> str:
    """'Recent Trades' module — the latest prospect trades from the tracked
    pool, newest first. Fills the grid slot beside This Day in Prospect
    History so the front page bottom row reads as a full spread."""
    trs = []
    for p in players:
        for tr in (p.get("trades") or []):
            dt = str(tr.get("trade_date") or "")[:10]
            if len(dt) == 10:
                trs.append((dt, p, tr))
    if not trs:
        return ""
    trs.sort(key=lambda t: t[0], reverse=True)
    rows = []
    for dt, p, tr in trs[:n]:
        frm = html.escape(tr.get("from_org") or "?")
        to = html.escape(tr.get("to_org") or "?")
        rows.append(
            f'<a class="row-link" href="{_player_href(p.get("player_key"))}">'
            f'{_team_logo(tr.get("to_org") or p.get("org"))}'
            f'<span class="row-name">{html.escape(p.get("player_name") or "")}</span>'
            f'<span class="row-meta">{_meta(p.get("position"))}</span>'
            f'<span class="row-meta" title="Traded {frm} → {to}">{frm} ⇄ {to}</span>'
            f'<span class="row-meta">{dt[5:7]}/{dt[8:10]}</span></a>'
        )
    return _home_module("Recent Trades", "/prospx/#tab=traded", "All transactions", "".join(rows))

def _row_farm(o: dict, rank: int) -> str:
    grade = (o.get("grades") or {}).get("overall") or "—"
    gcls = " gold" if str(grade).startswith("A") else ""
    name = ORG_NAMES.get(o.get("org"), o.get("org") or "—")
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

def _load_fa_events_for_wire() -> list:
    """Recent winter events from the FA module's own export (the events
    block in data/fa_class.json). Additive: an absent or pre-events export
    just yields no items. Dates are the pipeline's first-seen stamps."""
    try:
        d = json.loads((DATA_DIR / "fa_class.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return d.get("events") or []

def _collect_events(players: list, graduates: list, fa_events: list | None = None) -> list:
    # Each event is (date, typ, glyph, ticker_text, key, org, name, val):
    # `ticker_text` is the one-string form the scrolling WIRE marquee uses;
    # `name`/`val` are the structured halves the sidebar feed lays out as
    # name-left / value-right (PROSPX row idiom — no wrapping, scannable).
    # Internally a trailing weight orders same-date items editorially —
    # debut > trade > promo/demo > IL > FV, bigger grade steps leading the
    # FV items. Stripped before return.
    ev = []
    def add(dt, typ, glyph, text, key, org=None, name="", val="", weight=0):
        if dt:
            ev.append((str(dt)[:10], typ, glyph, text, key, org, name, val, weight))
    fv_items = []
    for p in players:
        nm = p.get("player_name") or ""
        key = p.get("player_key")
        org = p.get("org")
        # FV news = the most recent REAL grade change, dated at the change.
        # Never stock.delta — that's the movement engine's composite score
        # stamped with the latest (daily Live) snapshot date, which flooded
        # the wire with fake "▲ +N FV today" items for every top prospect.
        chg = None if p.get("status") == "debuted" else _latest_fv_change(p)
        if chg and abs(chg[1]) >= 2:
            fv_items.append((str(chg[0])[:10], chg[1], nm, key, org))
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
            add(e.get("date"), "signing", "✎", f'{nm} declines option — enters FA class',
                key, e.get("from"), name=nm, val="opt-out → FA", weight=85)
        elif t == "option_exercised":
            add(e.get("date"), "signing", "✎", f'{nm} option exercised — off the FA board',
                key, e.get("from"), name=nm, val="option exercised", weight=85)
        elif t == "qo_offered":
            add(e.get("date"), "signing", "✎", f'{nm} receives qualifying offer',
                key, e.get("from"), name=nm, val="QO offered", weight=84)
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

def _feed_html(events: list, n: int = 12) -> str:
    # Day-grouped wire: each date gets one thin header row that deep-links
    # into Time Machine at that date (the full board as of that day), and the
    # item rows drop the per-row timestamp the header now carries. Item rows
    # stay structured: logo | name (ellipsized) | colored value chip — the
    # type glyph lives only in the value chip.
    out = []
    last_day = None
    for dt, typ, glyph, text, key, org, name, val in events[:n]:
        if dt != last_day:
            last_day = dt
            ts = f"{dt[5:7]}/{dt[8:10]}" if len(dt) >= 10 else dt
            out.append(
                f'<div class="feed-day"><span class="feed-day-date">{ts}</span>'
                f'<a class="feed-day-tm" href="/prospx/#tab=timemachine&tm={dt}" '
                f'title="Time Machine — the full board as of {dt}">Time Machine →</a></div>')
        logo = _team_logo(org, "feed-logo") if org else ""
        out.append(f'<a class="feed-item" href="{_player_href(key)}">'
                   f'{logo}<span class="feed-name">{html.escape(name or text)}</span>'
                   f'<span class="feed-val {typ}">{glyph} {html.escape(val)}</span></a>')
    return "".join(out)

def _ticker_html(events: list, n: int = 14) -> str:
    # Each item is a mouse-clickable link to the player (or spotlights), color-
    # coded by type. tabindex=-1 keeps it out of the keyboard/AT path — the
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
        items = ['<span><span class="glyph">◆</span> PROSPX — live prospect wire</span>']
    return " ".join(items * 2)  # duplicated for seamless scroll

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
    # Biggest riser with FV history — rendered as a baseball card. Ranked by
    # the REAL trailing-1y grade change (label units), so the "+N FV" caption
    # is a true FV statement (stock.delta is the engine's composite score).
    cands = [(d, p) for p in players
             if p.get("status") != "debuted"
             and (d := _fv_window_delta(p)) is not None and d > 0]
    if not cands:
        return ""
    d, p = max(cands, key=lambda t: t[0])
    fv = p.get("fv_close")
    holo = " holo" if (fv is not None and fv >= 61) else ""
    url = _headshot_url(p.get("mlbam_id"), 180)   # unified chain (resolves milb-only ids)
    photo = f"background-image:url('{url}');" if url else ""
    spark = _fv_sparkline(p.get("points"), "var(--accent-green)")
    return (
        '<div class="sb-group"><div class="sb-group-label">Spotlight — Top Riser</div>'
        f'<a class="spotlight{holo}" href="{_player_href(p.get("player_key"))}" style="text-decoration:none;color:inherit;">'
        f'<div class="sp-photo" style="{photo}"></div>'
        '<div style="flex:1;min-width:0;display:flex;flex-direction:column;justify-content:center;gap:2px;">'
        f'<div class="sp-name">{html.escape(p.get("player_name") or "")}</div>'
        f'<div class="sp-meta">{_meta(p.get("position"), p.get("org"))}</div>'
        # flex-wrap + nowrap chip: under the wide MS-Gothic metrics the pill +
        # delta can outgrow the narrow sidebar column — wrap the chip as a unit
        # below the pill instead of letting it overflow into the card border.
        f'<div style="display:flex;align-items:center;gap:8px;row-gap:2px;margin-top:4px;flex-wrap:wrap;">{_fv_pill(p)}'
        f'<span class="row-delta up" style="font-family:var(--font-retro-mono);font-size:12px;white-space:nowrap;">▲ +{d} FV</span></div>'
        f'{spark}</div></a></div>'
    )

_GLOSSARY_TERMS = [
    ("DvM+", "development vs. mean"),
    ("Sur+", "FV-implied surplus value"),
    ("RPS+", "rate performance vs. same-age peers"),
    ("SC+", "Statcast composite"),
    ("WAG", "WAR above grade"),
    ("Tool+", "20–80 tool composite"),
]

def page_home(title: str, inner: str, description: str = "") -> str:
    desc = html.escape(description or "eephus.io — baseball prospect analytics")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{THEME_INIT}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{desc}">
<link rel="stylesheet" href="/assets/site.css?v={_CSS_VER}">
{ACCOUNT_CSS_LINK}
</head>
<body class="eephus-page eephus-home">
{inner}
<footer class="eephus-footer">
  <span>eephus.io — editorial baseball analytics</span>
  <span>© {date.today().year} eephus.io</span>
</footer>
{ACCOUNT_SCRIPTS}
</body>
</html>
"""

def _home_module(kicker: str, see_all_href: str, see_all: str, body: str, full: bool = False) -> str:
    head = (f'<div class="kicker"><h2>{html.escape(kicker)}</h2>'
            f'<a class="see-all" href="{see_all_href}">{html.escape(see_all)} →</a></div>')
    return f'<section class="home-module{" full" if full else ""}">{head}{body}</section>'

def _debut_org(g: dict) -> str | None:
    """Org the player DEBUTED with — point-in-time, never the current org.
    Primary source: the debut-season MLB stat row (its first org is the debut
    org by construction — the first MLB appearance IS the debut). Fallback:
    fold the trade history back across every trade dated after the debut.
    Mirrors the career-table rule: a historical event never silently wears
    the current org."""
    dd = str(g.get("debut_date") or "")[:10]
    if not dd:
        return g.get("org")
    try:
        debut_year = int(dd[:4])
    except ValueError:
        return g.get("org")
    for row in g.get("career_stats") or []:
        if row.get("season") == debut_year and str(row.get("level") or "") == "MLB":
            stints = [s for s in (row.get("stints") or []) if s.get("org")]
            if stints:
                return stints[0]["org"]
            if row.get("org"):
                return row["org"]
    org = g.get("org")
    for tr in sorted((g.get("trades") or []), key=lambda t: t.get("trade_date") or "", reverse=True):
        td = str(tr.get("trade_date") or "")[:10]
        if td and td > dd:
            org = tr.get("from_org") or org
        else:
            break
    return org

def _this_day_html(graduates: list, n: int = 5) -> str:
    """'This day in prospect history' — graduates who debuted on (or within a
    few days of) today's calendar date in past seasons. Up to `n` rows,
    exact-date anniversaries first, then by prominence (final FV, then WAG).
    Shows the org each player DEBUTED with (point-in-time via _debut_org),
    and links into Time Machine at the lead anniversary date."""
    today = date.today()
    cands = []  # (date_proximity, -prominence, debut_date, grad)
    for g in graduates:
        dd = g.get("debut_date")
        if not dd:
            continue
        try:
            d = date.fromisoformat(str(dd)[:10])
        except ValueError:
            continue
        if d.year >= today.year:
            continue
        try:
            anniv = date(today.year, d.month, d.day)
        except ValueError:
            continue
        prox = abs((anniv - today).days)
        if prox > 4:
            continue
        prom = g.get("fv_close") or ((g.get("debuted_value") or {}).get("wag") or {}).get("regressed_wag") or 0
        cands.append((prox, -float(prom), d, g))
    if not cands:
        return ""
    cands.sort(key=lambda c: c[:2])
    rows = []
    for _, _, d, g in cands[:n]:
        yrs = today.year - d.year
        nm = html.escape(g.get("player_name") or "")
        # The org shown is the one the player DEBUTED with, not where they
        # play now — this is a history module.
        org_then = _debut_org(g)
        meta = _meta(g.get("position"), org_then)
        when = f"{d.strftime('%B')} {d.day}, {d.year}"   # no %-d (unsupported on Windows)
        rows.append(
            f'<a class="otd-row" href="{_player_href(g.get("player_key"))}">'
            f'<span class="otd-when">{html.escape(when)}</span>'
            f'<span class="otd-body"><strong>{nm}</strong> debuted — {meta}</span>'
            f'<span class="otd-ago">{yrs}y ago</span></a>'
        )
    lead_date = cands[0][2]
    return (
        '<section class="home-module otd-module">'
        '<div class="kicker"><h2>This Day in Prospect History</h2>'
        f'<a class="see-all" href="/prospx/#tab=timemachine&tm={lead_date.isoformat()}">Time Machine →</a></div>'
        + "".join(rows) +
        '</section>'
    )

def _date_callout() -> str:
    """Date-aware countdown when the MLB Draft or Int'l signing period is near."""
    today = date.today()
    yr = today.year
    events = [
        (date(yr, 7, 13), "MLB Draft", "/prospx/#tab=draft"),
        (date(yr if today <= date(yr, 1, 15) else yr + 1, 1, 15),
         "International signing period", "/prospx/#tab=ifa"),
    ]
    for d, name, href in sorted(events, key=lambda e: e[0]):
        days = (d - today).days
        if 0 <= days <= 45:
            when = "Today" if days == 0 else ("Tomorrow" if days == 1 else f"in {days} days")
            md = d.strftime("%b %d").replace(" 0", " ")
            return (f'<a class="home-callout" href="{href}">'
                    f'<span class="cal-tag">◆ Upcoming</span>'
                    f'<span class="cal-msg"><strong>{html.escape(name)}</strong> · {md} · {when}</span>'
                    f'<span class="cal-go">View →</span></a>')
    return ""

def _scatter_teaser() -> str:
    """Tiny inline scatter linking to the Scatterplots builder — a visual nudge,
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

def build_home(articles: list[dict], data: dict | None = None) -> str:
    """Homepage = sidebar + newspaper-style main, with live PROSPX modules + a
    prospect wire feed read from the build-time data layer."""
    data = data or {}
    players = data.get("players") or []
    org_summary = data.get("org_summary") or []
    graduates = data.get("graduates") or []
    as_of = data.get("as_of", "—")
    today = datetime.now().strftime("%A, %B %d, %Y").replace(" 0", " ")
    events = _collect_events(players, graduates, _load_fa_events_for_wire())

    # ---- sidebar ----
    nav = []
    for key, label, href in NAV_ITEMS:
        cls = ' class="is-active"' if key == "home" else ""
        nav.append(f'<a href="{href}"{cls}>{html.escape(label)}</a>')
    sub = "".join(f'<a href="{href}"><span class="px-glyph">›</span>{html.escape(label)}</a>'
                  for label, href in PROSPX_SUBNAV)
    feed = _feed_html(events, 12) or '<div class="feed-item" style="color:#6f8a76;">No recent activity.</div>'
    spotlight = _spotlight_html(players)
    search = ('<input class="sb-search" type="search" placeholder="Search prospects…" aria-label="Search prospects" '
              "onkeydown=\"if(event.key==='Enter'&&this.value.trim()){location.href='/prospx/#q='+encodeURIComponent(this.value.trim());}\">")
    sidebar = (
        '<aside class="home-sidebar">'
        f'<div class="sb-brand"><a class="wm" href="/">{eephus_merged_wordmark("sb", tag="span")}</a>{THEME_BTN}</div>'
        # eephus.io — account entry point for the homepage (page_home has no
        # .eephus-nav top bar). refreshNav() in eephus-ui.js injects the Sign-in /
        # avatar control into any .eephus-nav-controls, including this sidebar slot.
        '<div class="sb-account eephus-nav-controls"></div>'
        f'{search}'
        f'<div class="sb-group"><div class="sb-group-label">Sections</div><nav class="sb-nav">{"".join(nav)}</nav></div>'
        f'<div class="sb-group"><div class="sb-group-label">PROSPX</div><nav class="sb-subnav">{sub}</nav></div>'
        f'{spotlight}'
        f'<div class="sb-group"><div class="sb-feed"><div class="feed-head"><span class="blip"></span>Prospect Wire</div>{feed}</div></div>'
        '</aside>'
    )

    # ---- top wire ticker ----
    # Decorative scrolling marquee — duplicates the accessible Prospect Wire feed
    # in the sidebar, so it's hidden from assistive tech (aria-hidden) to avoid
    # reading the same items twice / announcing a moving region.
    ticker = (f'<div class="home-ticker" aria-hidden="true"><span class="ticker-tag"><span class="blip"></span>Wire</span>'
              f'<div class="ticker-track">{_ticker_html(events)}</div></div>')

    # ---- masthead ----
    masthead = (
        '<div class="masthead">'
        f'{eephus_logo_lockup()}'
        '<div class="dateline"><span>Baseball Prospect Analytics</span>'
        f'<span>{html.escape(today)}</span><span>Data as of {html.escape(as_of)}</span></div></div>'
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
    secondary = ('<div class="secondary-stories">' + "".join(
        f'<a href="/articles/{a["slug"]}/"><div class="s-kicker">{html.escape(a.get("date_disp", ""))}</div>'
        f'<h3>{html.escape(a["title"])}</h3></a>' for a in sec) + '</div>') if sec else ""

    # ---- live PROSPX modules ----
    # Top Movers = biggest REAL grade changes over the trailing year (label
    # units, ≥2 grade points), matching the FV sparkline drawn beside each
    # row. The engine-flavored movers (performance-anchored, with driver
    # chips) live on the PROSPX spotlights tab this module links to.
    mv = [(d, p) for p in players
          if p.get("status") != "debuted"
          and (d := _fv_window_delta(p)) is not None and abs(d) >= 2]
    risers = sorted((t for t in mv if t[0] > 0), key=lambda t: -t[0])[:5]
    fallers = sorted((t for t in mv if t[0] < 0), key=lambda t: t[0])[:4]
    movers_body = "".join(_row_mover(p, d) for d, p in risers + fallers)
    movers = _home_module("Top Movers", "/prospx/#tab=spotlights", "All movers", movers_body) if movers_body else ""

    topN = sorted(players, key=lambda p: (p.get("fv_close") if p.get("fv_close") is not None else -1), reverse=True)[:8]
    top_body = "".join(_row_top(p, p.get("overall_rank") or i) for i, p in enumerate(topN, 1))
    topp = _home_module("Top Prospects", "/prospx/", "Full board", top_body) if top_body else ""

    gr = sorted((g for g in graduates if g.get("debut_date")), key=lambda g: g["debut_date"], reverse=True)[:6]
    grad_body = "".join(_row_grad(g) for g in gr)
    grads = _home_module("Recent Graduates", "/prospx/#tab=debuts", "All graduates", grad_body) if grad_body else ""

    # Top 6 farms (was 4) so the module fills its grid cell instead of leaving
    # dead space beside the six-row Recent Graduates column.
    fm = sorted((o for o in org_summary if o.get("farm_rank")), key=lambda o: o["farm_rank"])[:6]
    farm_body = "".join(_row_farm(o, o.get("farm_rank") or i) for i, o in enumerate(fm, 1))
    farm = _home_module("Farm Spotlight", "/prospx/#tab=farm", "Farm systems", farm_body) if farm_body else ""

    term, defn = _GLOSSARY_TERMS[datetime.now().timetuple().tm_yday % len(_GLOSSARY_TERMS)]
    glossary = (f'<div class="glossary-teaser"><span>Today\'s term: <strong>{html.escape(term)}</strong> — {html.escape(defn)}</span>'
                f'<a href="/prospx/#tab=glossary">Glossary →</a></div>')

    callout = _date_callout()
    otd = _this_day_html(graduates)
    trades_mod = _recent_trades_html(players)
    scatter = _scatter_teaser()
    # eephus.io — Forums module (third content pillar). Hydrated client-side by
    # eephus-ui.js (#eph-home-forums): bump/Hot ordering, last-active first.
    forums_mod = _home_module("Forums", "/forums/", "All discussions",
                              '<div id="eph-home-forums"></div>', full=True)
    main = (
        '<main class="home-main">'
        f'{masthead}{callout}{lead}{secondary}'
        f'<div class="module-cols">{movers}{topp}{grads}{farm}{otd}{trades_mod}</div>'
        f'{forums_mod}'
        f'<div class="teaser-row">{glossary}{scatter}</div>'
        '</main>'
    )
    inner = f'{ticker}<div class="home-shell">{sidebar}{main}</div>'
    return page_home("eephus.io — baseball prospect analytics", inner,
                     "Live MiLB prospect movers, top prospects, graduates, and analysis.")

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
    return page("Articles — eephus.io", "articles", body, "Long-form baseball analysis from eephus.io.")

def build_forums_index() -> str:
    """The /forums/ index — the third content pillar. The thread list is hydrated
    client-side by eephus-ui.js (#eph-forums-index): bump / Hot ordering, most
    recently active first. Static shell gives SEO + first paint + a nav home."""
    body = (
        '<div class="section-head"><h1>Forums</h1>'
        '<span class="section-sub">Discussion across prospects, farm systems, and articles</span></div>'
        '<div class="eph-forums-index-page"><div id="eph-forums-index"></div></div>'
    )
    return page("Forums — eephus.io", "forums", body,
                "Community discussion across prospects, farm systems, and articles on eephus.io.")

def build_fa() -> str:
    """The /fa/ Free Agency app — its own surface, SEPARATE from PROSPX.

    Static shell + assets/fa.js, which fetches the fa_export.py sidecars
    (data/fa_class.json / fa_archive.json / fa_meta.json) directly. Shares the
    site chrome and styles (.fa-app block in site.css) but loads none of the
    PROSPX boot payload or script. Views route via #view= (board / fits /
    archive / model / glossary)."""
    body = (
        '<div class="fa-app">'
        '<div class="section-head"><h1>MLB Free Agency</h1>'
        '<span class="section-sub">the 2026-27 class, constructed from data · '
        'projected markets, rational value &amp; team fits · twelve archived winters</span></div>'
        '<div id="fa-banner"></div>'
        '<div class="filter-bar"><span class="filter-label">View</span>'
        '<span id="fa-view-chips"></span></div>'
        '<div id="fa-rows"></div>'
        '</div>'
        f'<script src="/assets/fa.js?v={_FA_VER}" defer></script>'
    )
    return page("Free Agency — eephus.io", "fa", body,
                "The 2026-27 MLB free-agent class: projected contracts (mYears / mGuarantee / mAAV), "
                "rational value vs predicted price, team fits, and twelve archived winters with a "
                "realized-surplus ledger.")

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
        # eephus.io — article comment thread (the same forum component PROSPX uses),
        # auto-mounted client-side by eephus-ui.js from these data-* hints.
        f'<div id="eph-forum-mount" class="eph-article-forum" data-forum-scope="article" '
        f'data-forum-key="{html.escape(a["slug"])}" data-forum-title="{html.escape(a["title"])}"></div>'
    )
    # Per-article social card (assets/articles/<slug>/share-card.png) is optional —
    # only emit og:image/twitter when one was generated for this piece.
    slug = a["slug"]
    card = ROOT / "assets" / "articles" / slug / "share-card.png"
    image = f"{SITE_ORIGIN}/assets/articles/{slug}/share-card.png" if card.exists() else ""
    return page(f'{a["title"]} — eephus.io', "articles", body, a.get("summary", ""),
                image=image, url=f"{SITE_ORIGIN}/articles/{slug}/")

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
    # Personal website — globe glyph (stroke-style, rides currentColor like the rest).
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
    def _initials(name: str) -> str:
        parts = [p for p in name.split() if p[:1].isalpha()]
        if not parts:
            return "?"
        return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else parts[0][1:2])).upper()
    def _team_photo(m: dict) -> str | None:
        # Explicit `photo` path wins; otherwise auto-detect assets/team/<first>.<ext>
        # so a member just drops a file (e.g. assets/team/noah.jpg) and rebuilds —
        # no JSON edit, and no 404 since we only emit <img> when the file exists.
        if m.get("photo"):
            return m["photo"]
        slug = (m["name"].split() or [""])[0].lower()
        for ext in ("jpg", "jpeg", "png", "webp"):
            if (ROOT / "assets" / "team" / f"{slug}.{ext}").exists():
                return f"/assets/team/{slug}.{ext}"
        return None
    cards = []
    for m in team:
        handle = (m.get("handle") or "").lstrip("@")
        linkedin = (m.get("linkedin") or "").strip().rstrip("/").rsplit("/", 1)[-1]
        # Headshot: provided image (rectangular, sharp) over a monogram fallback
        # that shows when there's no photo or the file 404s — never a broken image.
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
                         f'rel="noopener" title="Twitter / X — @{html.escape(handle)}" aria-label="Twitter / X — @{html.escape(handle)}">{_TW_SVG}</a>')
        if linkedin:
            chips.append(f'<a class="team-soc" href="https://www.linkedin.com/in/{html.escape(linkedin)}/" target="_blank" '
                         f'rel="noopener" title="LinkedIn — {html.escape(m["name"])}" aria-label="LinkedIn — {html.escape(m["name"])}">{_LI_SVG}</a>')
        website = (m.get("website") or "").strip()
        if website:
            _host = website.split("//", 1)[-1].strip("/")
            chips.append(f'<a class="team-soc" href="{html.escape(website)}" target="_blank" '
                         f'rel="noopener" title="Website — {html.escape(_host)}" aria-label="Website — {html.escape(_host)}">{_WEB_SVG}</a>')
        github = (m.get("github") or "").strip().rstrip("/").rsplit("/", 1)[-1]
        if github:
            chips.append(f'<a class="team-soc" href="https://github.com/{html.escape(github)}" target="_blank" '
                         f'rel="noopener" title="GitHub — {html.escape(github)}" aria-label="GitHub — {html.escape(github)}">{_GH_SVG}</a>')
        socials_html = f'<div class="team-socials">{"".join(chips)}</div>' if chips else ""
        # Optional subtle note (only Noah gets "PROSPX Creator") — small mono pill.
        note_html = (
            f'<p class="team-note">{html.escape(m["note"])}</p>' if m.get("note") else ""
        )
        cards.append(
            f'<div class="card team-card" id="member-{_member_slug(m["name"])}">{photo_html}'
            f'<p class="name">{html.escape(m["name"])}</p>{note_html}{socials_html}</div>'
        )
    follow = (
        '<div class="team-follow"><span class="team-follow-label">Follow</span>'
        f'{_x_link("eephus_io")}{_x_link("MLBPROSPX")}</div>'
    )
    body = (
        '<div class="section-head"><h1>Development Team</h1></div>'
        f'{follow}'
        f'<div class="team-grid">{"".join(cards)}</div>'
    )
    return page("Development Team — eephus.io", "team", body, "The team behind eephus.io.")

# --------------------------------------------------------------------------- #
def _write(rel: str, content: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  wrote {rel}")

def main() -> None:
    print("build_site.py — generating editorial pages")
    art_dir = CONTENT / "articles"
    articles = [parse_article(p) for p in sorted(art_dir.glob("*.md"))] if art_dir.exists() else []
    articles.sort(key=lambda a: a.get("date_sort", ""), reverse=True)  # newest first

    data = load_site_data()
    print("  data layer:", "loaded" if data else "MISSING (run run_monthly) — modules will be empty")

    _write("index.html", build_home(articles, data))
    _write("articles/index.html", build_articles_index(articles))
    for a in articles:
        _write(f"articles/{a['slug']}/index.html", build_article_page(a))
    _write("forums/index.html", build_forums_index())
    _write("fa/index.html", build_fa())
    _write("team/index.html", build_team())
    print(f"done — {len(articles)} article(s).")

if __name__ == "__main__":
    main()
