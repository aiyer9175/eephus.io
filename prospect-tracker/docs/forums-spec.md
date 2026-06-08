# Forums — feature spec (NOT YET BUILT)

> Status: **proposal**. The β v1.0 polish pass (2026-06) found the "Forums pillar"
> referenced in the brief and the homepage information architecture, but **no
> implementation exists** — 0 references in `prospx/index.html` or the editorial
> pages. Forums is a *feature* pass, deliberately out of scope for a *polish* pass.
> This doc captures the spec so it can be built on-system rather than bolted on.

## Where it lives

A new top-level pillar alongside **Articles** and **PROSPX**, served from
`/forums/`. Two homes:

- **Editorial shell** (`build_site.py`): thread index + thread pages rendered as
  static-ish pages sharing `assets/site.css` (same nameplate, sidebar, column
  rhythm as Home/Articles). Good for SEO + first paint.
- **PROSPX-embedded** posting/voting: the interactive layer (compose, vote,
  notifications) is JS, loaded the same way PROSPX loads its data — so a thread
  can embed live PROSPX widgets without a second design system.

Either way it needs a backend (see *Data + backend* — the only part that is
genuinely new infrastructure). Everything visual reuses what already exists.

## Must read as one system (guardrails)

The three motifs and the polish guardrails apply verbatim — Forums is not an
excuse for a generic comment widget:

- **Sharp corners everywhere.** Inherits the universal `border-radius:0 !important`
  in `assets/site.css`. Vote pills, the compose box, avatars-for-accounts excepted
  (circular avatars are the *one* sanctioned curve — and the first place that
  exception actually gets used).
- **On-type.** Body copy in the retro stack; vote counts / scores / any embedded
  metric in `--font-retro-mono`, tabular-aligned.
- **One formatter.** Any PROSPX number a post surfaces (FV, a `+`-metric, `$`
  surplus) renders through `formatMetric(value, type)` — the same source of truth
  the app and tooltips use, so a number quoted in a thread can't drift from the
  board. See `prospx/index.html` › `formatMetric`.
- **Accent is signal.** Refractor/holo treatments stay reserved for FV tier and
  elite signal — not for decorating forum chrome.

## Components (all compose from existing primitives)

| Component | Reuse | Notes |
|---|---|---|
| Thread list | `.row-link` rhythm, hairline column rules | newest / most-active / top sort, stable like the leaderboards |
| Thread page | masthead + `assets/site.css` article layout | title, OP, replies, sticky reply bar |
| Markdown render | the `markdown` lib already vendored for articles (`build_site.py`) | **server-side render + sanitize**; allowlist only — no raw HTML/script |
| Vote control | new `.vote` chip (sharp), mono count | optimistic UI, one vote/account, score = up − down |
| PROSPX embed | `headshotURL()`, `_fvHeadshotRingClass()`, `formatMetric()`, the GFX gradient builder | `@player:jesus_made` → inline player chip w/ FV pill + sparkline; `@farm:LAD` → farm rank chip |
| @mentions | new resolver against the player/org/user indexes | `@user` notifies; `@player`/`@farm`/`@fv` expand to live data chips |
| Notifications | small bell in the global controls (next to Watchlist) | reply-to-you, mention, FV-change-on-watched-thread; reuses the FV-change-alert plumbing |
| User avatar | **circular** (the sanctioned exception) | account photos only — never a prospect photo |

## @mention / embed grammar

One grammar, resolved at render so display always matches current data:

```
@user:handle      -> profile link + notification
@player:slug      -> player chip (photo · name · pos · FV pill · spark)
@farm:ABB         -> farm chip (org · rank · grade)
@fv:slug          -> just the consensus FV pill, inline
$dvm:slug         -> a single +-metric value, via formatMetric(v,'plus')
```

Unresolved handles render as plain text (no broken chips), mirroring how
`headshotURL()` already degrades to the silhouette.

## Data + backend (the new part)

- Tables: `forum_thread`, `forum_post`, `forum_vote`, `forum_user`,
  `forum_notification`, `forum_subscription`. The repo already uses SQLite
  (`prospects.db`) + a Supabase migration dir (`supabase/migrations/`) — Forums
  is a natural Supabase target (auth + row-level security + realtime for vote/
  notification push).
- Auth: Supabase auth gives the `forum_user` + the avatar (the circular-avatar
  exception). No new auth framework.
- Spam/abuse: server-side markdown sanitize (allowlist), rate-limit posts/votes
  per account, soft-delete + moderator flag. Out of scope for v1, but the schema
  should reserve `status` on post/thread.

## States (Phase-4 parity)

Loading (sharp skeletons on the type scale), empty ("No threads yet — start one"),
error, zero-vote, locked thread, long title overflow, deleted/flagged post,
mention to a graduated/inactive player (chip still resolves, badge reads
`graduated`). Match the existing empty/skeleton treatments — do not invent new ones.

## Build order (recommendation)

1. Schema + Supabase auth + read-only thread/post render (static, SEO).
2. `formatMetric`-routed PROSPX embeds (read-only chips) — highest-signal, no write path.
3. Compose + markdown sanitize + vote.
4. @mentions + notifications.
5. Moderation.

Stages 1–2 ship value (live, embeddable, branded read-only discussion) before any
write infrastructure exists.
