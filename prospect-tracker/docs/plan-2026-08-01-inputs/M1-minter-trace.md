# LANE M1: A.J. Minter / expiring-vet class, end to end, as served 2026-08-01

All paths relative to `c:\Users\noah\baseball-projects\BaseballR\prospect-tracker`. Artifacts read directly from `data/` (trade_values.json generated_at `2026-08-01`, calibration `isotonic-real-v6-evframe-2026-07-31`, count 6105). Every number below re-verified against the served artifacts and code on 2026-08-01.

## 1. Minter's served rows TODAY

**data/trade_values.json — `unpriced` block** (he is in `unpriced`, NOT in `players[]`; 0 hits in `players[]`):
```json
{"key":"aj_minter","name":"A.J. Minter","org":"NYM","pos":"RP","thru":2026,"war5":0.6,"reason":"expiring"}
```
Top-level artifact keys: `generated_at, calibration, coverage, unpriced, count, players`. Coverage stamp as served: `vets 1321, priced_vets 740, priced_on_board 740, missing 0, unpriceable 581, unpriceable_expiring 221, unpriceable_no_contract 360`. The shipped `unpriced` array is only **240 rows (72 expiring + 168 no_contract)** — a subset of the 581, because `_unpriced_vets` excludes keys already on the board via another basis (see §2).

**data/mlb_projections.json — vet row** (`first_season: 2027`, `horizon: 5`, `current_season: 2026`, `dpw_usd: 15640340`): Minter DOES have 2027-2031 WAR — `"war":[0.23,0.15,0.15,0.01,0.03]`, `"warTotal":0.6`, plus `warChamp [0.28,0.16,0.06,0.0,0.0]`, `warPTH`, `warP10/P90`, `fip [4.18..5.45]`, `"thru":2026`, `"aav":7588208`, age 33, mlbam 621345 — but **no `sur`/`surNpv` keys at all** (contrast Aaron Judge: `thru 2031, aav 40000000, surNpv 23350804`). 740 vets carry surNpv; 221 surNpv-less vets have `thru==2026` (== all thru<2027); 360 have `thru` null.

**data/mlb_player_detail.json — `players.aj_minter`** (this is what the Trade Machine MLB search reads; 1,633 detail players, 740 with surNpv): `proj.surNpv: null`, `proj.sur: null`, plus an `fa` block: `{"status":"locked","type":"ufa","projYears":1,"projGuar":3560043,"projAav":3560043,"projAavP10":1166919,"projAavP90":12673947,"rational":3535245,"surplus":-24798,"dealPlus":99,"verdict":"market","prevAav":11000000,"enterProb":1.0}`. `surNpv` is copied verbatim from the projection vet row at mlb_player_export.py:505-510 (the `{k: v.get(k) for k in (... "sur","surNpv" ...)}` comprehension at 507-510 — a missing key becomes an explicit null).

**data/fa_class.json (class_year 2027, 228 members) — `members[133]`**: `{"key":"aj_minter","pos":"RP","age":32.8,"from":"MIN","status":"locked","type":"ufa","enterProb":1.0,"prevAav":11000000,"warY1":0.28,"warPath":[0.28,0.16,0.06,0.0,0.0],"projYears":1,"projGuar":3560043,"projAav":3560043,"rational":3535245,"surplus":-24798,"dealPlus":99,"verdict":"market",...}` with comps (Justin Wilson/Boone Logan/Kyle Finnegan) and team fits (LAD .447, NYM .387, NYY .365). Note `"from":"MIN"` — see Defects. His FA `warPath` equals the projection `warChamp` path, not `war`.

**data/fa_archive.json — `winters[10]` (year 2025), `signings[27]`**: `{"key":"aj_minter","pos":"RP/SU8","from":"ATL","to":"NYM","years":2,"guar":22000000,"aav":11000000,"warTd":0.4,"surplusTd":-3690794,"paidTd":11000000,"elapsed":0.5,"done":false}`.

**data/fantasy.json — `players[205]`**: mlbam 621345, NYM, ros: ip 11.8, era 4.18, whip 1.29, k9 8.7, sv 0.0, hld 0.5, `fpts_fgp 47.74`, skill `{rem_plus 103, gmli 0.75, saves 0, luck 0.004}`.

**data/bullpen_leaderboards.json — `relievers[130]`** (list; row carries `"key":"621345"`): `rem_plus 103` (raw 103.2), `riv_plus 96`, `xrem_plus 103`, role "Mop-up", ip 23.0, g 23, k_pct .2174, bb_pct .0217, fip 3.75, era 2.35, gmli 0.75, wpa -0.14, holds 1, `war_ip_plus_3yr 114` (pct 97, tag "provisional").

**data/pal.json**: three entries — `rp2sp[166]` (fit 48.8, flags needs_third/fb_heavy/platoon_risk), `pitch_add[145]` (rec: add Slider, target LHB, priority high), `reverse_platoon[40]` (L, reverse_index 0.202, extreme, weak_hand LHB).

**data/xfv.json — `by_player.aj_minter` EXISTS** (9,338 keys; the eFV backgrade universe covers him):
```json
{"side":"P","kind":"bust","xfv_grade":43.8,"xfv_war_6yr":1.55,
 "p_bucket":{"bust":0.704,...},"surplus_mm":8.3,"band_p10_mm":0.7,"band_p90_mm":28.5,
 "p_bust":0.704,"xfv_provisional":true}
```
This matters: the platform HAS a non-contract surplus number for Minter ($8.3M) that nothing serves (see Defects D2).

**Contract store (Spotrac-derived)**: there is no JSON/DB contract file — contracts are parsed on demand from cached team-page HTML at `prospect-tracker/.cache/spotrac_team_{slug}.html` (spotrac.py:422 `cache_key = f"spotrac_team_{team_slug}"`; three tables `dataTable-active/injured/dead`, spotrac.py:431; 30 team caches present incl. new-york-mets). `proj_export.py:1543-1547` builds them: `from spotrac import scrape_all_spotrac_contracts, build_contracts_by_key` then `contracts[key] = {**c, "team_code": slug_to_org.get(c.get("team_slug"))}`. Manual overrides from `data/contract_overrides.json` merge in storage.py:7754-7777 — but that merge lives INSIDE `export_timeseries_json` (def at storage.py:7546), i.e. the timeseries/board export path only; **`proj_export.build_payload` does NOT layer overrides, so an override cannot create or repair a surNpv** (the file currently holds only `colt_emerson`). Minter's record from `build_contracts_by_key(scrape_all_spotrac_contracts())` (re-derived from cache, byte-identical):
```json
{"player_name":"A.J. Minter","player_key":"aj_minter","spotrac_id":"20528","position":"RP",
 "team_slug":"new-york-mets","salary_usd":7588208,"aav_usd":7588208,"total_usd":7588208,
 "salary_by_year":{"2026":7588208},"years_remaining":1,"signed_through":2026,"current_year":2026}
```
(A DB sink also exists: `mlb_trade_players` contract columns, storage.py:1608-1621 schema / 3499-3539 upsert, v31.9c migration — not the pricing path.)

## 2. Exact classification code path

**Horizon constants — proj_export.py:59-60**:
```python
FIRST_SEASON = 2027          # first fully projected season (2026 is in progress)
HORIZON = 5                  # 2027..2031
```

**The surNpv-existence test — proj_export.py:283-312 `_apply_contract`** (inside `_veteran_rows`): for each of the 5 horizon seasons (`for t in range(HORIZON): season = FIRST_SEASON + t`, 299-300), `s_usd = sal.get(season)`; if no salary that season, `sur.append(None); continue`. Only if any horizon season has salary:
```python
if any_sal:
    m["sur"] = sur
    m["surNpv"] = int(npv)
```
where `npv += d_usd / ((1 + r) ** t)`, `d_usd = _season_value_usd(m["war"][t], t, dpw) - s_usd` (306-309); `r = float(vf._config()["discount_rate"])` (proj_export.py:255); `_season_value_usd` (proj_export.py:226-231) = `vf.tiered_war_value_usd(war) * (dpw_level/base_flat) * ((1+infl)**t)`. Minter's `salary_by_year = {2026: ...}` → `any_sal` never True → no surNpv. **2026 rest-of-season salary/production is structurally invisible to surplus.**

**Board population — run_monthly.py:822-846** (the only call site in the repo): `tv_players = list(_ts_payload.get("players") or [])` + `debuts.json` + `graduates.json` (both optional, absence warned, 836-844), then `export_trade_values_json(tv_players, out_dir/"trade_values.json", level_norms=lnorms)` (run_monthly.py:845-846).

**export_trade_values_json — bayes_trade_value.py:4408-4467**: computes, calls `apply_platform_surplus` (4422), drops `inactive_dropped` (4427), stamps `calibration: vf.calibration_stamp()` (4445), `coverage: _projection_coverage(results, ...)` (4430/4448), and:
```python
"unpriced": _unpriced_vets(
    out_path.parent,
    {r.get("player_key") for r in results
     if r.get("trade_value_mm") is not None}),
```
(bayes_trade_value.py:4454-4457).

**apply_platform_surplus routing** (def at 4095; routing body 4121-4264): `proj_sur[k] = r["surNpv"]/1e6` only when surNpv non-null (4127-4128). Per record: prospects → xfv; MLB → `proj_sur[pk]` = src "projection" (4190-4191), else `x_sur * _backgrade_realized_factor(...)` = src "xfv_backgrade" (4192-4200), else "unchanged" (raw bayes value survives, 4234-4235). Then `_append_projection_only_rows` (4262, defined 4267-4315) appends vets with surNpv the prospect pool never had (`if not pk or pk in present or pk not in proj_sur: continue`, 4282), stamped `"board_entry": "projection_only"` (4304), bands null (4300-4301).

**`_unpriced_vets` — bayes_trade_value.py:4322-4362** (the function that routes Minter to `expiring`):
```python
for v in (proj.get("vets") or []):
    if not v.get("key") or v.get("surNpv") is not None:
        continue
    if on_board and v["key"] in on_board:
        continue                    # priced by another basis (eFV backgrade)
    thru = v.get("thru")
    out.append({
        "key": v["key"], "name": v.get("name"), "org": v.get("team"),
        "pos": v.get("pos"), "thru": thru,
        "war5": v.get("warTotal"),
        "reason": "expiring" if (thru is not None and thru < first) else "no_contract",
    })
out.sort(key=lambda r: -(r.get("war5") or 0))
```
(`first = proj.get("first_season") or 0`, line 4347). `_projection_coverage` (4365-4405) computes the stamp; note its `unpriceable_*` counts are the FULL 581 (no on_board exclusion, 4391-4393), while `unpriced` ships 240 (with exclusion, 4352-4353) — two different denominators in one artifact.

**Frontend render — assets/trademachine.js**: `_TM.unpriced = d.unpriced || []` on mount (1081); `_TM.detail` fetched from `/data/mlb_player_detail.json` (`_tmEnsureDetail`, 135-143). Search `_tmSearch` (169-214) has three pools with result caps 6/10/12: prospects from `DATA.players` (built by `_tmBuildProspectPool`, 1043-1051, which filters `!_tbIsMlb(p) && p.posterior_surplus_mm != null` — `_tbIsMlb` = status graduated/debuted, 422-424), MLB from mlb_player_detail.json requiring `d.proj.surNpv != null` (187), then unpriced rows (200-212) with the copy string:
```js
sub: u.reason === "expiring"
  ? `${u.pos || ""} · ${u.org || "FA"} · contract ends ${u.thru} - no controlled season to trade`
  : `${u.pos || ""} · ${u.org || "FA"} · no contract on file - cannot price surplus`,
```
Rendered dimmed/inert at 309-313: `<button class="tm-hit is-unpriced" type="button" disabled title="We project this player, but there is no contract surplus to put in a deal."> ... <span class="tm-val">not tradeable</span>` (CSS assets/trademachine.css:78-85).

## 3. Tests pinning current behaviour (will need amending if expiring vets are priced)

**test_trade_board_coverage.py** (158 lines, repo root of prospect-tracker, not tests/):
- `test_every_priced_vet_is_on_the_trade_board` (45-55): `cov["missing"] == 0`.
- `test_coverage_block_is_stamped_into_the_artifact` (58-67): requires keys incl. `unpriceable_expiring`/`unpriceable_no_contract`; `priced_on_board + missing == priced_vets`.
- `test_unpriceable_vets_are_published_with_a_reason` (70-79): `r.get("reason") in ("expiring","no_contract")` for first 50 rows; **asserts `rows` non-empty** ("no unpriceable vets published at all - suspicious") — if the plan prices ALL of them this assertion inverts.
- `test_no_unpriceable_vet_leaked_into_the_valued_board` (82-90): `unpriced` ∩ `players[]` keys = ∅ — THE assertion that unpriced vets never enter players[].
- `test_projection_only_rows_price_on_the_projection_basis` (95-115): calls `btv._append_projection_only_rows` directly; asserts `n == len(records) == len(proj_sur)`, src "projection", bands null, `"fv" not in r and "xfv_grade" not in r` ("no grade may be invented").
- `test_existing_rows_are_never_duplicated` (118-129).
- `test_unpriceable_split_is_the_two_documented_reasons` (132-147): calls `btv._unpriced_vets(DATA)` WITHOUT on_board (so it sees the full 581); reason set ⊆ {expiring, no_contract}; expiring ⇔ `thru < first_season`; docstring names Minter the canonical case.
- `test_coverage_is_computed_off_valued_rows_only` (150-158).

**test_calibration_vintage.py**: `test_the_same_player_is_worth_the_same_on_every_surface` (112-146) — for every vet with surNpv whose board row has `surplus_source == "projection"`, `|trade_value_mm - surNpv/1e6| <= 0.15` (142). If expiring vets get priced on a NEW basis (rest-of-season, or eFV), they must either carry surNpv in mlb_projections too or a distinct surplus_source, else this fails. Also `test_all_surplus_artifacts_agree_on_the_calibration` (89-109) and `test_stamped_artifacts_match_the_live_config` (149-167) — any new pricing artifact needs the stamp.

**test_bayes_trade_value_policy.py**: no unpriced/expiring assertions (it pins the bayes compute policy: backgrade factors ~17-40, contract discount ~350, negative surplus ~832, etc.). Relevant only if the plan touches `_backgrade_realized_factor` or the fallback ordering.

**test_proj_export.py:123-131 `test_vet_surplus_only_on_contracted_seasons`**: "a veteran surplus claim requires a real contract" — `surNpv is not None ⇒ thru` truthy, and `sur` must contain a non-None entry. Pins the honesty rule the plan must renegotiate if it invents pre-arb/rest-of-season salaries. Also test_projections_smoke.py fixtures carry surNpv shapes (43-65).

## 4. Class census as served

Full expiring class (mlb_projections vets, surNpv null, thru < 2027): **221**. Split: **149 are ON the board anyway** (145 via `surplus_source: "xfv_backgrade"` + **4 via un-guarded raw bayes with `surplus_source: null`** — craig_kimbrel, patrick_corbin, jose_quintana, santiago_espinal; see D3), **72 ship as dimmed `unpriced` rows**. Recognizable names:

On-board-anyway (xfv_backgrade values that ignore the expiring contract): Tarik Skubal DET SP (war5 12.3, aav $32M) — board $44.7M rank #128; Jazz Chisholm Jr. NYY 2B (war5 6.8) — $49.6M rank #109; Gleyber Torres DET 2B (war5 5.5) — **$80.1M, board rank #54**; Daulton Varsho TOR ($48.5M), Ian Happ CHC ($54.1M), Randy Arozarena SEA ($4.5M), Trent Grisham NYY ($11.1M) also in this class, all xfv_backgrade.

Dimmed/inert in search (top expiring rows of the served `unpriced`; the combined array is war5-sorted across BOTH reasons, so no_contract rows interleave — braydon_fisher 2.7, josh_smith 2.5, luis_ortiz__682847 2.0): Seiya Suzuki CHC OF (4.2), Taylor Ward BAL LF (4.2), Shota Imanaga CHC SP (2.1), Brandon Woodruff MIL SP (1.9), Sean Newcomb CHW RP (1.7), Steven Okert HOU RP (1.5), Raisel Iglesias ATL RP (1.1), Miguel Rojas LAD SS (1.0), Patrick Sandoval BOS SP (0.9), Kirby Yates LAA RP (0.8), then Minter-tier RPs. **161 of the 240 unpriced rows (45 of 72 expiring) already have an xfv.json surplus_mm available** (e.g. Ward $10.7M, Woodruff $29.9M, Minter $8.3M) that nothing serves.

Doc drift: docs/efv-2026-07-31/TRADE_BOARD_COVERAGE.md says 218/361/579 and Judge $24.6M (also echoed in the bayes_trade_value.py:4251-4252 comment and the coverage test docstring); the artifact serves 221/360/581 and Judge $23.35M (surNpv 23350804, board 23.4, src projection, board_entry projection_only) — the doc numbers were a point-in-time measurement, regen has moved them. Jazz Chisholm moved groups (doc line ~89: no_contract, "6.6 projected 5y WAR"; artifact: expiring, thru 2026 aav $10.2M, war5 6.8).

## 5. Defects found

- **D1 — Trade Machine search cannot find 840 valued board rows.** `_tmSearch`'s prospect pool excludes `status: debuted/graduated` (trademachine.js:1045 `!_tbIsMlb(p)`), the MLB pool requires `proj.surNpv != null` in mlb_player_detail.json (trademachine.js:187), and `unpriced` excludes anyone on_board. Result: every graduated/debuted player valued via `xfv_backgrade` (or the null-src fallback) with null surNpv — measured **840 rows** (recomputed 2026-08-01: valued players[] rows with status graduated/debuted whose detail entry lacks surNpv; includes the 9 null-src rows; 0 active-status rows are lost, since every active row with a value carries posterior_surplus_mm) — including Skubal ($44.7M), Torres ($80.1M), Chisholm ($49.6M), Moncada ($80.2M) — is on the tradeBOARD ranking but returns **silence** from the Trade Machine add-search. That is precisely the failure the unpriced block was built to kill ("Returning nothing for a real major-leaguer reads as 'the site has never heard of him'", trademachine.js:195-199), and it contradicts `_unpriced_vets`' own docstring (bayes_trade_value.py:4325-4330: publishing Skubal as not-tradeable "would be false" — instead he's simply absent).
- **D2 — Same class, three treatments.** An expiring vet is (a) valued at a 6-year-control eFV backgrade number if he was ever a tracked prospect (Torres $80.1M with 2 months of control), (b) "not tradeable" if he wasn't (Minter, despite xfv.json carrying surplus_mm 8.3 for him), (c) reachable in the Trade Machine only if surNpv exists. The stated rationale ("A pending free agent is not a trade asset; the FA module prices him", bayes_trade_value.py:4334-4335) is enforced for only 72 of 221 class members; deadline rentals are in reality the most-traded asset class.
- **D3 — Raw bayes values survive un-guarded via the "unchanged" fallback.** 9 valued rows have `surplus_source: null` (bayes_trade_value.py:4234-4235). Full served list: **Jose Quintana, age 38, COL, fv 0.0, contract thru 2026 @$6M — trade_value_mm 95.9, tier "elite", grade "A", board rank #40**; Max Clark DET $65.3M rank #74 (null src despite fv 58, status debuted); Craig Kimbrel age 39 — $23.5M rank #347 (board org TBR while mlb_projections says NYM @ aav $548,129 — the artifacts also disagree on his org); Patrick Corbin TOR $14.4M; Rowan Wick SFG $3.6M; Jose Ortega SDP $2.9M; Kelvin Herrera HOU $2.5M (age 18.6 — a prospect-named row served as a debuted vet); Alex Cook TBR $1.3M; Santiago Espinal TEX $0.1M. Four of the nine (Quintana, Kimbrel, Corbin, Espinal) are expiring-class members, so the `_unpriced_vets` on_board exclusion treats their broken values as "priced by another basis", they escape the unpriced ledger, and `test_no_unpriceable_vet_leaked_into_the_valued_board` passes.
- **D4 — Two denominators in one artifact.** `coverage.unpriceable*` counts all 581 surNpv-less vets (bayes_trade_value.py:4391-4404, no on_board exclusion); the `unpriced` array ships 240 (with exclusion, 4352-4353). Nothing in the artifact explains why 221 ≠ 72; any consumer summing `unpriced` by reason against the stamp will "detect" a regression.
- **D5 — fa_class.json serves Minter `"from": "MIN"`** (fa_export.py:300 `"from": row.get("from_team")`; from_team parsed from Spotrac's fa_avail_2027 page by fa_sources.py — `_parse_available_compact` :223 reads the team-logo img via `_TEAM_IMG_RE`, `_parse_available_table` :269 reads the details-cell text's last token — and the cached page itself shows a Twins logo `min_2023.png` + "MIN" text in Minter's row; verified in `prospect-tracker/.cache/spotrac_fa_avail_2027.html`). Every other artifact and the platform's own contract store say NYM (`team_slug new-york-mets`). Source error passed through with no reconciliation against the contract join.
- **D6 — 2026 rest-of-season control is structurally unpriceable.** `_apply_contract` only prices seasons ≥ FIRST_SEASON (proj_export.py:299-300), so from now until the season flips, every player's current-season salary and production are outside surplus on every surface; the dimmed copy "no controlled season to trade" (trademachine.js:209) is false at the August deadline — the current season IS the controlled season being traded. `test_vet_surplus_only_on_contracted_seasons` (test_proj_export.py:123) pins the current rule.
- **Context**: the efv_score.py:2066 `run_backgrade` NameError P0 is real and confirmed — inside `run_backgrade` (def at 1966), line 2066 is `factors = _relabel_pace_factor(factors, r.get("milb"))` where `r` is bound only inside a set comprehension at line 1986 (Python 3 comprehension scope does not leak), so the milb-featured branch raises NameError and kills the regen tail that refreshes xfv.json — any plan pricing expiring vets off xfv backgrade values inherits that staleness risk; and the nightly monthly does NOT run efv_export (memory: fifteen-asks), so a plan changing proj_export/bayes_trade_value needs the manual export + `--rebuild-only` second pass to actually serve.

### Verification log

Adversarial verification 2026-08-01: every numeric/path/line claim re-checked against the live repo; JSON claims recomputed from the served artifacts; classification logic re-executed in Python.

Corrections applied:
1. **§4 miscount fixed**: "149 are ON the board anyway via xfv_backgrade" was wrong in composition — recomputed: of 149 expiring-class members on the board, 145 have `surplus_source:"xfv_backgrade"` and **4 have `surplus_source: null`** (raw-bayes fallback: craig_kimbrel, patrick_corbin, jose_quintana, santiago_espinal). These 4 are the expiring-class subset of D3's 9.
2. **§1 contract-store scope corrected/expanded**: the contract_overrides.json merge (storage.py:7754-7777, not 7754-7773) lives inside `export_timeseries_json` (def storage.py:7546) — the timeseries/board path — NOT in `proj_export.build_payload`, so an override cannot create or fix a surNpv. File currently holds only colt_emerson. Load-bearing for any plan that reaches for overrides to price an expiring vet.
3. **D3 completed**: enumerated all 9 null-src rows (brief named only 3); added Kimbrel board-org TBR vs mlb_projections NYM @ $548,129 disagreement and the Kelvin Herrera age-18.6 anomaly; corrected the framing "never-prospect vets" (Max Clark fv 58 and Alex Cook fv 35 are in the nine).
4. **D5 sharpened**: added the actual parse sites (fa_sources.py `_parse_available_compact`:223 logo-img regex / `_parse_available_table`:269 details-cell last-token) and the exact cache evidence (`min_2023.png` thumb + "MIN" text in the Minter row). Cache dir clarified to `prospect-tracker/.cache` (also for spotrac_team_{slug}.html; 30 team caches present).
5. **§1 fa block completed**: added the omitted `projAavP10:1166919` / `projAavP90:12673947` keys; added detail-file scale (1,633 players, 740 with surNpv).
6. **§3 precision**: test asserts `n == len(records) == len(proj_sur)` (not just `n == len(proj_sur)`); `test_unpriceable_split_is_the_two_documented_reasons` calls `_unpriced_vets(DATA)` without on_board (sees all 581); test_bayes_trade_value_policy line cites loosened to approximate (~17-40/~350/~832 — content confirmed at those regions).
7. **§4 precision**: doc path is docs/efv-2026-07-31/TRADE_BOARD_COVERAGE.md; the dimmed-list names are the top EXPIRING rows — the combined unpriced array interleaves no_contract rows (braydon_fisher/josh_smith/luis_ortiz__682847); added board ranks for Skubal (#128)/Chisholm (#109) and values for Varsho/Happ/Arozarena/Grisham; Judge board row confirmed (23.4, src projection, board_entry projection_only).
8. **Context claim upgraded from asserted to verified**: efv_score.py:2066 NameError reproduced by scope analysis (`r` bound only in a comprehension at 1986; enclosing def `run_backgrade` at 1966).
9. **Minor cite fixes**: `apply_platform_surplus` def is at bayes_trade_value.py:4095 (routing body 4121-4264 as stated); rationale quote is at 4334-4335; docstring cite 4325-4330; trademachine.css block is 78-85; storage.py DB sink is 1608-1621/3499-3539; run_monthly export call is 845-846 (single call site); added `_tmEnsureDetail` fetch (trademachine.js:135-143) and search result caps 6/10/12.

Confirmed as-is (no change): Minter unpriced row JSON byte-exact; top-level keys; coverage stamp 1321/740/740/0/581/221/360; unpriced 240 = 72+168; Minter projections row (war/warChamp/warPTH/fip/thru/aav/age/mlbam, no sur/surNpv); 740/221/360 splits; detail surNpv/sur null; fa_class 2027 228 members, members[133], age 32.8, from MIN, comps, fits; fa_archive winters[10] year 2025 signings[27] byte-exact; fantasy players[205]; bullpen relievers[130]; pal rp2sp[166]/pitch_add[145]/reverse_platoon[40]; xfv by_player 9,338 keys, Minter entry byte-exact (surplus_mm 8.3); Spotrac contract record byte-exact (re-derived from cache); FIRST_SEASON/HORIZON at 59-60; _apply_contract 283-312 logic and formulas; _season_value_usd 226-231; discount_rate at 255; run_monthly 822-846; export_trade_values_json 4408-4467 incl. 4422/4427/4430/4445/4448/4454-4457; routing 4127-4128/4190-4200/4234-4235; _append_projection_only_rows 4267-4315 incl. 4282/4300-4301/4304; _unpriced_vets 4322-4362 code quote byte-exact incl. 4347/4352-4353; _projection_coverage 4365-4405; trademachine.js 169-214/187/195-199/200-212/209/309-313/422-424/1043-1051/1045/1081 all byte-checked; test_trade_board_coverage.py is 158 lines with all eight test ranges as cited; test_calibration_vintage 112-146 (tolerance 0.15)/89-109/149-167; test_proj_export 123-131; test_projections_smoke fixtures 43-65; class census 221/149/72; expiring names + war5/aav values; 161-of-240 and 45-of-72 xfv-coverage counts (Ward 10.7/Woodruff 29.9/Minter 8.3); doc drift 218/361/579 + Judge $24.6M vs served 221/360/581 + $23.35M; Chisholm group move; D1 measured 840 (reproduced exactly); D2, D4, D6 logic reproduced. All six defects are real.
