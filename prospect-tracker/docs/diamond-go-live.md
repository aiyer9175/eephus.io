# Diamond go-live checklists

Written 2026-08-16 as part of the Diamond readiness program. Two ordered
checklists: one for turning Supabase on, one for flipping the gate. The gate
flip DEPENDS on Supabase being live: assets/eephus-diamond.js treats
`gating: true` with a dead account layer as gating-off plus a console warning
(the dead-man's switch), so flipping the flag first does nothing on purpose.

Nothing in this file is automation. Every line is an owner or webmaster action
with its verification command. Keep the order.

## A. Before Supabase go-live

1. Apply migrations 0001 through 0005 to the production project
   (supabase/migrations/). 0005 creates `bets`, the diamond badge seed,
   `profiles.diamond_until`, and the privileged-column guard trigger.
2. Verify the trigger from a CLIENT credential: a PATCH to
   `profiles.diamond_until` must be silently pinned (the guard exists so a
   user cannot grant themselves Diamond). Do this against production, not
   only locally.
3. Populate `assets/eephus-config.js` with the project url + anon key and
   COMMIT it. The anon key is designed to be public; RLS is the boundary.
   Committing survives the box's nightly `git checkout -- .`, which is the
   reason a hand-edited webroot copy does not work. If the owner objects to
   the key in the public repo, the alternative is post-rsync injection from
   /etc/eephus.env, and that choice must be recorded here.
4. Stand up an /auth/ landing route. The email-confirmation redirects that
   assets/eephus-account.js constructs point at /auth/, and nothing in the
   site map serves that path today: without it every confirmation link 404s.
   Verify by completing one real signup end to end.
5. Verify the bets merge: sign in on a browser holding localStorage bets
   (key eephus_bets_v1) and confirm mergeOnSignIn moves them to the account
   store (key eephus.bets.v1) without duplication.
6. Verify the diamond badge renders for a service-role-granted test account
   (eephus-ui.js BADGE_ICON.diamond).
7. Record the founding-cohort rule BEFORE the first grant: founding rate goes
   to accounts with `profiles.created_at` earlier than the gate-flip date,
   enforced at grant time by the service role. The /diamond/ page has promised
   founding status "for the people who were here during the preview" since
   2026-08-16; the grant script is where that promise is kept.
8. The efv_alerts delivery stays "not_wired" in copy until a delivery
   mechanism actually exists. Turning accounts on does not deliver alerts.

## B. Before `gating: true`

1. The gating contract v2 must be green: test_diamond_gating_contract.py
   passes (source conformance + the MiniRacer truth table including the
   dead-man case), and no module client reads EEPHUS_DIAMOND keys outside
   the helper.
2. Supabase is live per checklist A. The dead-man's switch neutralizes the
   flag otherwise, by design.
3. Entitlement re-render is proven: a signed-in Diamond member's first paint
   may be the preview, and the onEntitlement subscription must upgrade it
   without a reload (betting re-fetches the full payload; the row-capped
   boards re-render uncapped).
4. The gated-state page copy is the one build_site renders when
   _diamond_cfg() sees gating true. The founding-preview banner and the
   "Is any of this gated right now? No." FAQ must not survive the flip;
   they are selected by the parsed flag, so a rebuild after the config edit
   is what changes them. Verify on the built diamond/index.html.
5. Preview caps confirmed by the owner (diamond-config.js preview map;
   defaults dynasty 25 / redraft 25 / dfs 25 / cards 40).
6. Price parity green: the rendered page and diamond-config.js agree
   (pinned by test_diamond_scaffold.py; no literal survives in
   build_diamond source).
7. The published-payload path-leak allowlist is EMPTY for member-facing
   files (test_published_payload_hygiene.py; the burn-down list must not
   carry betting.json or any Diamond payload).
8. A grant runbook exists: who runs the service-role update, on what
   evidence of payment, and how a refund revokes (`diamond_until` back-dated).
   Stripe remains out of scope until an entity and a legal review exist
   (owner decision 2026-08-04); the grant path is the service role.
9. Announce before flipping. The FAQ has promised "plenty of notice" since
   the page shipped; the flip is a copy change plus a config edit plus a
   rebuild, and the notice is part of the product's honesty.

## C. What flipping the gate actually changes (so nobody over-promises)

Row caps on dynasty/redraft/dfs/cards and the preview payload on betting.
Every data file under /data/ stays public static JSON; the /diamond/ extras
card sells exactly that as a feature. The gate is conversion UX, not
secrecy. A real members-only data path (RLS-served payloads, files removed
from the webroot) is a separate, unscheduled decision recorded in the
master plan as owner decision D1, and it would break the public-artifact
promise for those files if taken.
