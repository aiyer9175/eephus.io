# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""pixel_brand_src.py - the hand decisions behind every eephus.io pixel mark.

Owner ask 2 (2026-09-30), Part 8 pixel_branding lane, BR-01 / PB-01. Moved
into the tree from the design bundle (part8/branding/proposed/tools/). Every
number a person chose lives here as plain data; tools/pixel_brand.py renders
everything from this file plus the vendored PixelMplus12 TTF. Edit a number,
rerun the generator, and the diff shows exactly which pixels moved.

THE GRID. u = 1/12 em of PixelMplus12 (1,000 units per em, one pixel = 83.3
units). The letters are sampled from the TTF on u, never redrawn or
re-lettered (branding/README.md, "Do not redraw or re-letter the wordmark, or
swap the font"). The icon sprite's 12 x 12 core is the same 12-unit em. A
rendering is the grid at an integer scale s (u = s CSS px). The ball is the
one element below u: a hinted strike in whole CSS px, centred on the apex
column (odd strike at odd s).

Owner answers (DECISIONS_FOR_OWNER.md, Part 8 batch 5, 2026-09-30):
PB-Q1 B Stepped, PB-Q2 inward seams, PB-Q3 lilac '.io' in both themes,
PB-Q4 pitch, replay and glint.
"""

# ---------------------------------------------------------------- defaults
STYLE = "stepped"       # PB-Q1 answer B; alternatives "hinted" (A), "lamps" (C)
SEAMS = "inward"        # PB-Q2 answer, the classic ') ('; alternative "outward"

# ---------------------------------------------------------------- lockup
TEXT = "eephus.io"
DOT_FROM = 6            # '.io' takes --logo-dot
BASE = 18               # canvas row of glyph row r = 0 (r runs 9 .. -2)
ROWS = 21               # canvas rows; 'p' descends to row 20
ARC_END_ROW = 7         # the two end runs sit on this row
# The arc as run lengths from each end toward the apex (one row per run);
# the apex run takes the remaining columns. Symmetric by construction.
ARC_RUNS = (2, 3, 4, 5, 6)                      # 1 u arc (odd s, and s 2)
HALF_RUNS = (2, 2, 3, 3, 4, 4, 5, 5, 6, 8)      # half-u arc (even s from 4 up)
BANDS = 8               # ramp bands along the arc, sampled at band centres
LETTER_SPACING_U = 0    # extra u between glyphs (the face's own spacing is 1 u)

# DOM strikes: where each scale is used (plan section 3.3)
STRIKES = {"nav": 2, "sidebar": 2, "prospx_title": 3, "hero_phone": 4, "hero": 6,
           "og_small": 4, "og": 10}
# Which fragments play the one-shot pitch and the glint (PB-Q4: homepage hero
# only, the desktop strike and its phone twin; the nav replays on hover only).
PLAY_SCALES = (4, 6)
FRAGMENT_SCALES = (2, 4, 6)
# The PNG strikes the canvas exports paint (BR-08, PB-08): served from
# assets/brand/ beside their DOM fragments; the s 6 strike stays review art.
EXPORT_SCALES = (2, 4)

# ---------------------------------------------------------------- ball
# Ball strike size per lockup scale: 4 u, plus 1 at odd s so it centres on
# the apex column.
BALL_FOR_SCALE = {1: 5, 2: 8, 3: 13, 4: 16, 5: 21, 6: 24, 8: 32, 10: 40, 12: 48}
HAND_STRIKES = (8, 12, 13, 16, 24, 32)   # strikes with hand-tuned seam columns
# Circle radius trim per strike (r = n/2 - trim), picked by eye so each
# quadrant is one smooth run sequence (16: 4, 2, 1, 1, 2v, 4v).
CIRCLE_TRIM = {8: 0.15, 12: 0.15, 13: 0.3, 16: 0.3}
CIRCLE_TRIM_DEFAULT = 0.3
RIM_2PX_FROM = 28       # strikes this size and up get a 2 px rim
# Hinting: the LEFT seam's column per row (the right seam mirrors it);
# (col, width) for 2 px seams. Rows above the middle take the seam's top
# colour, rows below its bottom colour.
SEAM_COLS = {           # inward, the classic ') (' (PB-Q2 answer)
    8:  {2: 1, 3: 2, 4: 2, 5: 1},
    12: {2: 2, 3: 2, 4: 3, 5: 3, 6: 3, 7: 3, 8: 2, 9: 2},
    13: {2: 3, 3: 3, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 3, 10: 3},
    16: {3: 3, 4: 4, 5: 4, 6: 5, 7: 5, 8: 5, 9: 5, 10: 4, 11: 4, 12: 3},
    24: {4: 6, 5: 6, 6: 7, 7: 7, 8: 7, 9: 8, 10: 8, 11: 8, 12: 8, 13: 8, 14: 8,
         15: 7, 16: 7, 17: 7, 18: 6, 19: 6},
    32: {5: (8, 2), 6: (8, 2), 7: (9, 2), 8: (9, 2), 9: (10, 2), 10: (10, 2), 11: (10, 2),
         12: (11, 2), 13: (11, 2), 14: (11, 2), 15: (11, 2), 16: (11, 2), 17: (11, 2),
         18: (11, 2), 19: (11, 2), 20: (10, 2), 21: (10, 2), 22: (10, 2), 23: (9, 2),
         24: (9, 2), 25: (8, 2), 26: (8, 2)},
}
SEAM_COLS_OUT = {       # outward '( )', the SVG masters' anatomy (PB-Q2 alternative)
    8:  {2: 2, 3: 2, 4: 2, 5: 2},
    12: {2: 3, 3: 3, 4: 2, 5: 2, 6: 2, 7: 2, 8: 3, 9: 3},
    16: {3: 4, 4: 3, 5: 3, 6: 2, 7: 2, 8: 2, 9: 2, 10: 3, 11: 3, 12: 4},
}
# Procedural fallback for strikes with no hand columns (20, 40, 48 ...):
# seam stroke width by strike, and the seam circle's centre offset and
# radius as fractions of the strike's half width.
FALLBACK_SEAM_W = ((21, 1.0), (24, 1.4), (10_000, 1.8))
FALLBACK_SEAM_GEOM = {"inward": (1.32, 0.98), "outward": (0.55, 1.18)}

# ---------------------------------------------------------------- PROSPX mark
# 22 x 22 at 2x = 44 px, the served size (prospx/index.html .px-ball-mark).
# Never drawn below 40 px (branding/README.md: no P/X on a sub-40px mark).
# Outward stitched seams (the monogram needs the middle), the P/X in the bold
# serif the page renders today.
PX_SIZE = 22
PX_MIN_SCALE = 2
PX_P = ("#####.", ".##.##", ".##.##", ".##.##", ".####.", ".##...", ".##...", ".##...", "####..")
PX_X = ("##...##", ".##.##.", ".##.##.", "..###..", "..###..", "..###..", ".##.##.", ".##.##.", "##...##")
PX_SEAM = {3: 6, 4: 5, 5: 4, 6: 3, 7: 3, 8: 3, 9: 2, 10: 2, 11: 2, 12: 2, 13: 3, 14: 3,
           15: 3, 16: 4, 17: 5, 18: 6}
PX_P_AT, PX_X_AT, PX_TOP = 5, 10, 6

# ---------------------------------------------------------------- motion
# PB-Q4: pitch (homepage hero, once), hover replay on every wordmark, one
# glint per page view. CSS step-end only; the base style is the final frame.
MOTION = {
    "arc_ms": 600,        # the arc lights run by run over this span
    "min_step_ms": 8,     # floor on the per-run step
    "drop_ms": 240,       # four whole-pixel frames: -2 u, -1 u, +nudge, rest
    "drop_gap_ms": 40,    # after the last arc run
    "glint_after_ms": 1700,  # after the ball settles; hero only, once
    "glint_frame_ms": 120,   # dot, plus, dot
    "gif_frame_ms": 40,      # export GIF frame spacing
    "gif_hold_ms": 1600,     # the GIF holds its final frame, then stops (no loop)
}

# ---------------------------------------------------------------- palette
# Mirrors of site.css tokens (test_pixel_brand.py asserts they equal the
# :root and [data-theme="dark"] decks). Exports use these; the DOM uses var().
RAMP = {  # --iridescent stops, verbatim
    "light": ((0.00, "#B91C1C"), (0.35, "#C9A227"), (0.65, "#1F7A3A"), (1.00, "#0E2B4D")),
    "dark":  ((0.00, "#00D9FF"), (0.30, "#B47CFF"), (0.55, "#FF4FD8"), (0.78, "#FFD700"), (1.00, "#4FFF9E")),
}
SEAM_STOPS = {"light": (1, 2, 3, 4), "dark": (1, 2, 3, 5)}   # ramp stop per seam (a, b, d, e)
TOKENS = {  # (light, dark), each equal to the site.css deck value
    "text-primary":   ("#0F1B2D", "#ECEEF2"),
    "text-secondary": ("#4A5468", "#A6ABB5"),
    "bg-primary":     ("#F4F0E6", "#0C0C0E"),
    "bg-secondary":   ("#FAF5E6", "#1A1A1E"),
    "accent-lilac":   ("#6E56CF", "#9B8CFF"),
    "logo-dot":       ("#6E56CF", "#9B8CFF"),   # = var(--accent-lilac) in both decks (PB-Q3)
}
# The ball's cream face, kept from the vector compact mark (both themes);
# branding/marks/compact-mark.svg is now generated from this file (PB-09).
BALL_FACE = "#F6F1E4"

# ---------------------------------------------------------------- export art
# The dark share-card and app-icon field: near-black, a lilac glow, scanlines.
FIELD_BASE = (12, 12, 14)
FIELD_GLOW = (110, 92, 255)
FIELD_GLOW_PCT = 62        # glow strength at the centre, percent
FIELD_GLOW_MIX_PCT = 30    # share of the glow colour mixed into the base
FIELD_SCANLINE_PCT = 90    # dark scanline rows keep this share of their value
APP_ICON_BORDER = "#9B8CFF"   # the dark lilac, as the served app icons draw it
STAR_RAMP = ((0, 217, 255), (91, 200, 255), (139, 127, 255), (180, 124, 255), (255, 79, 216))
CARD_W, CARD_H = 1200, 630

# ---------------------------------------------------------------- modules
# (icon key in assets/eephus-icons.json, masthead title as served, route,
# card line cut from the page's own meta description). The card lines are
# owner copy (plan section 8, secondary defaults); they pass copy_lint.
MODULES = (
    ("prospx", "PROSPX", "/prospx/",
     "Prospect analytics: eFV grades, surplus value, and scouting consensus."),
    ("collegesavant", "CollegeSavant", "/collegesavant/",
     "Percentile profiles for college hitters and pitchers."),
    ("franchise", "Franchises", "/franchise/",
     "One page per club: the Franchise Index and its three branches."),
    ("fa", "MLB Free Agency", "/fa/",
     "The free-agent class: projected contracts with floor, mean and ceiling bands."),
    ("projections", "MLB Projections", "/projections/",
     "Five-year WAR projections for every MLB player: floor, mean and ceiling paths."),
    ("mlbstats", "MLB Stats", "/mlbstats/",
     "MLB leaderboards: every player by eWAR, HEM+, SEM+, REM+, RIV+ and DEM+."),
    ("pal", "Alchemy Lab", "/pal/",
     "MLB role and position conversions, pitch-add boards and the conversion backtest."),
    ("trademachine", "Trade Machine", "/trademachine/",
     "Value MLB trades in one currency: eFV surplus and projection surplus."),
    ("arbitration", "Arbitration Predictor", "/arbitration/",
     "Projected arbitration salaries for every eligible MLB player."),
    ("ledger", "Club Ledger", "/ledger/",
     "Every club's CBT payroll, commitments and controlled surplus, from Spotrac."),
    ("management", "In-Game Management", "/management/",
     "Every in-game decision in the play corpus, with the win probability that moved after it."),
    ("hof", "Hall of Fame", "/hof/",
     "Career WAR, WAR7 and JAWS for every ten-season player, with the ballot record."),
    ("fantasy", "Fantasy", "/fantasy/",
     "Redraft ranks, an eFV dynasty and keeper board, and DFS per-game projections."),
    ("betting", "Sports Betting", "/betting/",
     "Win probabilities against de-vigged prices. 21+, informational only."),
    ("diamond", "Diamond Pass", "/diamond/",
     "The eephus.io paid tier for fantasy and betting. Nothing is gated today."),
)
# The Awards card (AWARDS_10; AWARDS_PLAN 3 and 5.16), beside the hof card above,
# which stays unchanged because it names the shelf page. Drawn with the aw-podium
# icon; tools/pixel_brand.py writes assets/og/awards.png only while
# awards_core.AWARDS_LIVE is True, and into the awards preview otherwise.
AWARDS_CARD = ("awards", "MLB Awards", "/awards/",
               "The eephus selection for MVP, Cy Young, Rookie and Manager of the Year, superlatives, "
               "and a ballot of your own.")
AWARDS_CARD_ICON = "aw-podium"
DEFAULT_CARD_TAG = "sabermetrics"

# ---------------------------------------------------------------- the branding bundle
# PB-09 / BR-09: the export folders branding/marks, branding/animated,
# branding/social and branding/icons' transparent balls come from this file
# too, so no brand art depends on a system font or a hand-drawn vector.
# The animated mark (frames, GIF and the self-contained SVG) is the pitch at
# s 8: the half-u arc and the hand-tuned 32 px ball, padded 3 u for the drop.
ANIMATED_SCALE = 8
ANIMATED_PAD_U = 3
# Twitter/X art: avatars 400 x 400 (ball strike 32 at 9x, the PROSPX mark at
# 13x), banners 1500 x 500 with the lockup centred so the profile picture,
# which covers the banner's lower left corner, never sits on it.
AVATAR_SIZE = 400
AVATAR_BALL_SCALE = 9
AVATAR_PX_SCALE = 13
BANNER_W, BANNER_H = 1500, 500
BANNER_LOCKUP_SCALE = 12
BANNER_PX_SCALE = 8          # the PROSPX mark beside its title, 176 px
BANNER_TITLE_SCALE = 10      # "PROSPX" in PixelMplus12 Bold, 120 px cells
BANNER_TAG_SCALE = 3
BANNER_TAGS = {              # the banners' lines, kept from the vector-era art
    "eephus": "sabermetric / scouting analytics website",
    "prospx": "eephus.io prospect tracker",
}
# branding/icons/ball-transparent-<size>.png: ball strike 32 at a whole scale
# (6x, 16x, 32x fill the canvas exactly); the -monogram- twins centre the
# PROSPX mark at the largest whole scale that fits.
TRANSPARENT_SIZES = (192, 512, 1024)
