# eFV v4: structured extraction of the as-of scouting report (EFV4_REPORT_LLM_EXTRACTION)

Status: READ ON THE DEVELOPMENT FRAMES, and once on the spent reserved frames. No arm is
selected; nothing served moves.

Written 2026-10-08 (late evening, US Eastern) under decisions EW2-8 to EW2-12 of
2026-10-08 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`). Research:
`_finalpass_2026-09-24/efv4/RESEARCH.md` section 2.3 (the instrument and the seven-step
leakage protocol). Preparation: `efv_w2_report_llm.py` (EFV4_REPORT_EXTRACT_PREP, commit
1dd9ed79). Read: `efv_w2_report_read.py`, artifact `data/_labs/efv_w2/efv_w2_report_llm.json`.
No em-dashes. Nothing here, in its code or in its artifacts, is grouped, counted or averaged
by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`); u_c enters only as a continuous
control. The displayed PROSPX consensus FV and every served eFV grade are unchanged.

## 1. The extraction

- Corpus: 5,830 (row, source) documents, 5,795 unique, on list vintages 2013 to 2019 (MLB
  Pipeline 2013 to 2019, FanGraphs 2019), each the row's own in-window report cleaned by
  `efv_text_features.clean_report` (grades, n/n pairs, FV, ETA and years stripped; the
  anachronism filter applied) and then redacted (player name forms, other persons, clubs,
  affiliates, schools, money, pick and rank numbers, ages). V 2011 and 2012 dropped; no
  reserved vintage built.
- Extractor: in-session subagents (EW2-10, no API key). Every output file names the model
  `claude-sonnet-5-5`; the research text assumed `claude-opus-5-5`. The store keys every
  extraction by (document sha256, control id, prompt sha256, model id), so the read is a
  replay of `data/_labs/efv_w2/report_extract.jsonl` (6,395 rows: 5,795 main documents
  plus 600 control documents; 160 files, 0 rejected, 0 invalid, 0 conflicts) and needs no
  model.
- Twelve fields per document (schema in `efv_w2_report_llm.FIELDS`): conviction,
  hedge_count, risk, injury_mention, makeup, body_projection, role_ceiling, role_floor,
  reliever_risk (pitchers), approach_concern (hitters), writer_level, arrival.

## 2. Columns, heads and the as-of rule

- One column per field and side (22 arms). A row with two documents (2019) takes the mean
  of each field and the maximum of the injury flag. `txt_writer_minus_stated` is the
  within-(side, V) percentile of writer_level minus the consensus percentile u_c.
- A document counts only when dated on or before the row's list date (0 were later).
  Coverage on lv_dev: hitters 2,677 of 2,795 text-vintage frame rows, pitchers 2,509 of
  2,681.
- Heads (protocol step 6): txt_arrival and txt_role_floor go to the timing head. Every
  other field goes to the skill head only when report_absent reads BALANCED on the FROZEN
  fWAR label (DS-03 probe on the lv_dev training rows of 2013 on). Read on 2026-10-08:
  hitters IMBALANCED (partial -0.1013, CI95 -0.1557 to -0.0494), pitchers BALANCED
  (-0.0569, CI95 -0.1101 to +0.0122). So hitter fields enter the timing head only;
  pitcher grade-side fields enter the skill head.
- DEFAULT (carry): a debut-cohort row (vm_dev, R-VM) and a list row of a later vintage
  (the spent R-LV, 2020 and 2021) carry the player's latest development-vintage value
  whose document date is on or before the row's own read date. No 2020 or 2021 document
  was extracted, so R-LV and R-VM coverage is partial (R-LV hitters 463 of 725 rows at 2020
  and 245 of 599 at 2021; R-VM test rows 3 of 82 hitters and 3 of 95 pitchers).

## 3. The controls (read before any arm)

- Test-retest (300 shuffle-donor documents re-extracted blind): rank correlation 0.68
  (hedge_count) to 0.97 (injury); exact agreement 0.43 (hedge_count) to 0.97.
- Name-redaction agreement (300 documents with names left in against their redacted
  twins): mean differences within 0.02 on every field except role_floor (-0.21 on 38
  pairs); rank correlations 0.65 to 0.98.
- Name-redaction invariance on the outcome (protocol step 3): per field, the partial
  correlation with the within-(side, V) W3 percentile given a quadratic in u_c and
  side-by-vintage effects, redacted against names left in, on the same 300 rows,
  player-clustered bootstrap (B 2,000). DEFAULT: the research text's "must not differ
  beyond its interval between the two runs" is read as either test failing, the
  names-in point outside the redacted CI95 or the paired difference's CI95 excluding
  zero. One field fails: role_ceiling (redacted -0.0513, names in +0.0227, difference
  +0.0740, CI95 +0.0067 to +0.1488): with names left in the extractor's role reading
  tracks the outcome more, the world-knowledge signature. role_ceiling is WITHHELD on
  both sides (its arms are not read). Under the narrower reading (point outside the
  redacted CI95 only) no field is withheld; that choice was fixed before any arm was read.
- Shuffled-document twin (protocol step 4): every read arm's full-frame twin (the column
  permuted across players inside each vintage) reads inside the wave-1 floor of its head
  and side (largest |twin| 0.0032 against the pitcher skill floor 0.0075; floors copied
  from `data/xfv_screen_wave1.json`, same lv_dev frame and frozen label).

## 4. The reads

E_cond, B 2,000, player-clustered, within (side, vintage) Spearman, frozen label
`fwar@2026-10-02-0341299c20ec`. lv_dev through the screening lab's own Frame and
measure_arm; vm_dev through `tools/efv_v3_backtest` development Inputs (base parity with
DS-16 and v3-at-base parity both reproduced, 3,692 rows). Spent frames through
`build_reserved` on the 10-08 confirmation's gate sha (v3-at-base parity 2,496 rows,
0 differ), labelled "spent frame, read after the 10-08 confirmation"; they chose nothing.

Arms that DS-06 admitted in at least one development fold (every other read arm was
refused in every lv_dev and vm_dev fold, so it is V2 there, delta 0):

| arm | head | lv_dev vs V2 (CI95) | vm_dev vs V2 (CI95) | R-LV spent | R-VM spent |
|---|---|---|---|---|---|
| rpt_writer_minus_stated_pit | skill | +0.0081 (-0.0035, +0.0193), 2/3 | +0.0024 (-0.0121, +0.0173), 3/7 | -0.0056 | 0 |
| rpt_writer_minus_stated_hit | timing | 0, 0/3 | +0.0078 (-0.0015, +0.0190), 6/7 | 0 | +0.0018 |
| rpt_conviction_pit | skill | +0.0018 (-0.0019, +0.0055), 1/3 | +0.0014 (-0.0055, +0.0083), 1/7 | -0.0040 | 0 |
| rpt_risk_hit | timing | +0.0008 (-0.0031, +0.0047), 3/3 | +0.0030 (-0.0114, +0.0158), 6/7 | +0.0020 | 0 |
| rpt_arrival_hit | timing | +0.0008 (-0.0025, +0.0044), 3/3 | -0.0118 (-0.0343, +0.0091), 6/7 | +0.0016 | 0 |
| rpt_hedge_count_hit | timing | -0.0003 (-0.0037, +0.0032), 2/3 | +0.0017 (-0.0043, +0.0080), 2/7 | 0.0000 | 0 |
| rpt_approach_concern_hit | timing | -0.0003 (-0.0019, +0.0013), 1/3 | +0.0005 (-0.0049, +0.0062), 6/7 | 0 | 0 |
| rpt_arrival_pit | timing | -0.0005 (-0.0013, +0.0003), 1/3 | 0, 0/7 | 0 | 0 |
| rpt_conviction_hit | timing | 0, 0/3 | -0.0013 (-0.0138, +0.0110), 6/7 | 0 | 0 |

Spent-frame admissions not seen on the development frames: rpt_reliever_risk_pit on R-LV
-0.0217 (CI95 -0.0464 to +0.0026), rpt_risk_pit -0.0062. Every number above, with the
consensus legs, is in the artifact's `summary`.

## 5. Reading

- Every development CI95 spans zero. The one arm above its wave-1 within floor on lv_dev,
  rpt_writer_minus_stated_pit (+0.0081 against 0.0075), has lb95 -0.0017 and its 2019 fold
  refused (the sign flipped in the 2018 training vintage), so it fails admission clause (a)
  and (d).
- EW2-10 ship rule (beat served V2 on lv_dev, vm_dev, R-LV and R-VM, pooled over sides):
  no arm, and no pair of the two writer_minus_stated arms, passes. The within statistic is
  a size-weighted mean over (side, vintage) groups and each arm moves one side only, so a
  pooled point is a weighted mean of its side's delta and 0; on R-LV the pitcher arm reads
  -0.0056 and the hitter arm 0, so any pooling is below zero.
- Matches the research prior: about 0 to +0.010 on lv-type frames, P(admitted) about 0.20,
  modal outcome NULL. The writer's own disagreement with the grade is the only field with
  a consistent positive sign on both development frames; it does not hold on the spent
  R-LV frame.

## 6. What landed

- `efv_w2_report_llm.py`: lv_values, carried_value, screen_column (the lab hook),
  store_model_id, control_receipt; ARMS in the lab's candidate shape.
- `efv_w2_report_read.py`: the controls, the head resolution, the development and spent
  reads, the ledger rows (development rows only; 40 rows: 20 arms on lv_dev and vm_dev).
- `tools/efv_screen_lab.py`: WAVE2_DEV registers `efv_w2_report_read` (wave 1 untouched).
- `data/_labs/efv_w2/report_extract.jsonl` (the replay store) and
  `data/_labs/efv_w2/efv_w2_report_llm.json` (the read), both off the webroot.
