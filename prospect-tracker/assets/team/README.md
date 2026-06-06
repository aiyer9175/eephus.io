# Team headshots

Drop a headshot here named by the member's **first name** (lowercase), then run
`python build_site.py`. The Development Team page picks it up automatically — no
JSON editing needed.

- Accepted: `noah.jpg`, `will.jpg`, `michael.png`, `anirudh.webp`, `joseph.jpg`,
  `charlie.jpg` (extensions tried in order: jpg, jpeg, png, webp).
- Until a file exists, the card shows a monogram (the member's initials) — so the
  page never has a broken image.
- Photos render **rectangular with sharp corners** (portrait, `object-fit: cover`,
  framed from the top). Aim for a roughly portrait/square source ≥ 320px wide.
- To use a different path/filename, set `"photo": "/assets/team/whatever.jpg"` on
  that member's entry in `content/team.json` (overrides the auto-detect).

Note: these must be images the member is OK publishing. We do **not** pull photos
from LinkedIn — that violates LinkedIn's terms and their image URLs are signed and
expire (they'd break). Ask each person for a headshot to drop in here.
