# Red tests at the port head: triage (PORT_RED_TESTS_TRIAGE, 2026-10-22)

Owner P-8 (2026-10-22): clear the tests red at HEAD before the port's step L1. This is the
triage of the 90 ids `docs/port/BASELINE_PYTEST.txt` recorded red on the local build at
f7e4a5ce, rerun on the integration head 305ca53c (89 of the 90 still red; the dependency-lock
id had been fixed), plus the ids this pass found red on the way. Every row names its class and
either its fix commit or the reason it stays red for PORT_RED_TESTS_CLEAR.

Classes: STALE PIN (a test pinned to a state a later committed change replaced on purpose),
DEFECT (a real defect fixed at its cause, with a regression test where none caught it),
STALE ARTIFACT (a served artifact its exporter had not regenerated), ENVIRONMENT (red only on
this machine or in this worktree), DATA (the served data no longer matches the test's premise
and the exporter or an owner call is needed), BROWSER (needs a live DOM look that this pass
did not get to).

Commits on wt-PORT_RED_TESTS_TRIAGE, in order: e3e76b70 (methodology map), 192028b5 (area 1,
pages and pins), 5bc67b32 (area 2, glossary, registry, Model Updates, management), aae0758b
(area 3, stylesheets, scripts, static checks), 9b8a5b62 (area 4, rendered boards).

## 1. Fixed

| Test id | Class | Fix |
|---|---|---|
| test_methodology_freshness::test_every_registry_model_has_a_documentation_decision | STALE PIN | e3e76b70: 42 rows mapped, 21 served rows to their entries, 21 unserved rows internal |
| test_arbitration_scaffold::test_a_new_module_appends_and_never_reorders_the_existing_ones | STALE PIN | 192028b5: Scores / Standings sits second by SC-NAV, skipped like the hub |
| test_awards_flag (3 ids) | STALE PIN | 192028b5: the PIXEL_BRAND masthead (c1366bd6) h1 shape |
| test_mlb_events_rows (4 baseline ids) | STALE PIN | 192028b5: masthead shape, the calendar kicker (PX-15) |
| test_mlb_events_rows::test_fa_flag_on_draws_the_column_sorts_and_folds (found red) | DEFECT | 192028b5: xm-surfaces.js faBoard() left the /fa/ detail row one cell short of the 17-cell header; it now pads the xM$ column; regression test in test_xm_surfaces.py |
| test_mlb_news_rename::test_news_page_head | STALE PIN | 192028b5 |
| test_library_rename::test_glossary_page_masthead_title_and_meta_read_library | STALE PIN | 192028b5 |
| test_source_updates::test_section_is_in_the_page_index_and_the_nightly | STALE PIN | 192028b5: the gl-app div carries data-sacc-tools-src since TL_21 |
| test_team_masthead::test_page_is_the_masthead | STALE PIN | 192028b5 |
| test_smoke_home_otd_account::test_sho02_otd_body_title_and_phone_wrap | STALE PIN | 192028b5: MLB ledger rows carry MLB's own sentence in the title by design (b23d211a) |
| test_share_cards::test_each_card_title_is_the_pages_masthead_title | STALE PIN | 192028b5: the hof card names the shelf page (AWARDS_10) while the masthead reads Awards / HoF |
| test_share_cards::test_each_card_line_is_cut_from_its_pages_meta_description | STALE ARTIFACT | 192028b5: the mlbstats and pal card lines re-cut from their pages' meta descriptions, assets/og re-rendered |
| test_pixel_icon_coverage (2 franchise ids) | STALE PIN | 192028b5: MODULE_STAGE['franchise'] reads the F-SCORE chip the page has served since FS_2F_FLIP |
| test_awards_copy::test_the_glossary_drafts_are_clean_and_land_only_at_the_flip | STALE PIN | 5bc67b32: compared by id, later lanes appended entries after the fourteen |
| test_claims_freshness::test_glossary_numbers_match_artifacts | STALE ARTIFACT | 5bc67b32: six WAR-rate entries re-derived from data/war_rate_plus_eval.json (eWAR v3 run); the four eWAR v2 gate rows retired with the v3 copy |
| test_eabs_board::test_glossary_and_registry_script_is_idempotent | STALE PIN | 5bc67b32: the script carries the served text of the 120aa7da copy pass |
| test_glossary_management_ids::test_the_management_ids_exist_with_the_module_tag | DEFECT | 5bc67b32: mgmt_decisions.REALIZED_SENTENCE drops a banned word; the management payloads regenerated |
| test_glossary_provenance::test_arkmetric_origin_names_the_platform | DEFECT | 5bc67b32: positional_ladder's origin names eephus.io |
| test_library_term_shelves (2 ids) | STALE ARTIFACT | 5bc67b32: mlb_transaction_log's section restated by tools/glossary_sections.py |
| test_prospx_lb_library::test_new_aliases_are_unique_across_the_glossary | DEFECT | 5bc67b32: fb_ivb's alias duplicated the induced_vertical_break term |
| test_wag_l13_repairs::test_the_one_series_claim_names_what_it_does_not_cover | STALE ARTIFACT | 5bc67b32: the eWAR entry names the industry tables it does not cover again |
| test_model_registry::test_every_eval_artifact_is_registered | STALE PIN | 5bc67b32: two committed companions cited on their parent rows; a historical plus-joined citation split into its paths |
| test_model_registry::test_stale_threshold_is_reachable | STALE PIN | 5bc67b32: STALE_DAYS 90 to 120 (oldest dated artifact 114 days), decision doc noted |
| test_model_report_cards::test_models_page_links_every_row_to_its_history | STALE ARTIFACT | 5bc67b32: data/model_updates.json refreshed (45 rows were missing), /models/updates/ rebuilt |
| test_model_updates::test_every_registry_model_is_present | STALE ARTIFACT | 5bc67b32 |
| test_model_updates::test_other_holds_at_most_ten_rows | DEFECT | 5bc67b32: model_updates.py routes unserved rows to Development after the route table, /awards/ to Hall of Fame, /scores/ to Scores / Standings; Other 30 to 4 |
| test_provisional_v2::test_the_registry_row_quotes_the_artifact | STALE ARTIFACT | 5bc67b32: the row quotes the a6c407a6 artifact |
| test_theme_tokens::test_no_stylesheet_names_a_token_that_does_not_exist | DEFECT | aae0758b: the runtime-set tokens get rest defaults on their component roots |
| test_design_tokens::test_fractional_font_sizes_bounded | DEFECT | aae0758b: three PROSPX leaderboard sizes snap to var(--fs-xs) |
| test_reduced_motion_px::test_the_px_block_draws_in_tokens_only | DEFECT | aae0758b: .px-spark.dn fills with var(--down) |
| test_value_ruler (2 ids) | DEFECT | aae0758b: the awards ruler fills live beside the ruler in site.css; awards.js draws its fallback through a class |
| test_mlbp_css_contract::test_every_emitted_mlbp_class_has_a_site_css_rule | DEFECT | aae0758b: .mlbp-realwar and .mlbp-fgwar get their rule |
| test_mlbstats_fit::test_the_served_shell_opts_every_section_into_csv_with_short_nav_labels | STALE PIN | aae0758b: the section order carries Baserunning (eBR flip) and Trends (TR_5) |
| test_mlbstats_windows::test_every_served_board_column_is_declared_or_explained | STALE ARTIFACT | aae0758b: 16 pitch-rate columns declared hidden on the window index, regenerated |
| test_team_basis_coverage::test_every_render_site_that_shows_a_team_mounts_the_note | DEFECT | aae0758b: the eabs board mounts the team-basis note |
| test_report_excerpt::test_copy_states_the_excerpt_limit | STALE PIN | aae0758b: the Library's chapters rewrite (8e40db54) dropped the sources note; /sources/ states the limit |
| test_wag_career_exposure::test_prospx_wag_copy_quotes_the_engine_rules | STALE PIN | aae0758b: the card reads percentile 0.80+ (COPY_3) |
| test_fa_readonly_prospx (2 ids) | STALE PIN | aae0758b: the IL days fetch (b23d211a); the FA storage section ends where the Staff Gems accessors begin |
| test_efv_x1_translate::test_no_served_module_imports_the_translation | STALE PIN | aae0758b: the labs and the gated eTools readers are allowed |
| test_gate2_untouched_by_path (the _destale_rate id) | STALE PIN | aae0758b: xm_export.py joined at the XM-FLIP |
| test_prospect_anchor_gate::test_serve_flag_defaults_false_and_is_read_at_one_site | DEFECT | aae0758b: a proj_export comment named the flag |
| test_betting_sidecar_isolation (2 baseline ids) | DEFECT | aae0758b: conftest watches every redirected writer and the bat-tracking folders |
| test_postseason_cache::test_the_tracked_set_is_in_git_and_ships_in_neither_deploy_consumer | DEFECT | aae0758b: a publish_paths.txt comment named the lab folder |
| test_sources_attribution::test_every_ingest_host_has_a_sources_row | DEFECT | aae0758b: /sources/ gains the Cot's Contracts row |
| test_trade_audit_basis::test_every_party_goes_through_the_one_pricer | STALE PIN | aae0758b: M9-1 scoped to the audit body (the xM$ copy says withheld) |
| test_wire_type_system::test_history_rows_carry_the_family_and_the_ev_il_pictogram | STALE PIN | aae0758b: the live MLB ledger stays out of the fixture |
| test_draft_upcoming_class::test_only_the_upcoming_chip_has_the_hourglass | STALE PIN | aae0758b: the pixel hourglass icon |
| test_debut_placeholder::test_no_matrix_row_reads_a_placeholder_day[hit] | STALE PIN | aae0758b: every redated key carries the real day; the map has no row left to move |
| test_control_theme_site (3 ids at 1440 dark) | DEFECT | 9b8a5b62: the Teams tab's season select sits in the module's control bar |
| test_mgmt_steal_context::test_the_served_percentiles_equal_the_cached_leaderboard_rows | STALE ARTIFACT | 9b8a5b62: data/management_steal_context.json regenerated on the refetched 2026 sprint cache |
| test_farm_finances_surplus::test_tiles_read_gross_cost_net_for_every_org | STALE PIN | 9b8a5b62: the harness extracts the two DvM helpers the composite calls |

## 2. Residual, for PORT_RED_TESTS_CLEAR

| Test id | Class | What was found and what the clear needs |
|---|---|---|
| test_betting::test_every_published_slot_is_a_row_off_the_board | DATA | The served pick_of_the_day books fanduel while its board row books betrivers; the betting exporter needs the odds API and the published chain. Rebuild on the main tree inside the betting clocks. |
| test_betting_close_job::test_the_diagnosis_separates_not_scheduled_from_never_firing | ENVIRONMENT | No odds snapshot sits in the 14-day window on this machine, so snapshot_health takes its no-snapshot branch before the never-ran one. Green with a recent odds pull. |
| test_betting_sidecar_isolation::test_the_odds_snapshots_are_watched_even_though_they_are_not_redirected | ENVIRONMENT | The worktree's .cache is a junction to the main tree, so betting_ingest.CACHE_DIR resolves outside the checkout. Green on the main tree. |
| test_bust_inclusive_frame::test_a_player_with_real_major_league_war_is_not_a_bust | DATA | zach_britton's inactive.json row carries empty career_war and career_war_label blocks in both trees, so source_backtest's WAR screen (career_war_label.career_war) fires on nobody. storage.py's inactive payload (line 18829) no longer attaches the label block; find where the eWAR v3 relabel dropped it. |
| test_clemens_reconciliation (2 ids) | DATA, OWNER CALL | surplus_value_mm(50) is 68.1 on the model and 56.6 on the prospx_current table since CAL_KNOTS_REFIT_17M (eb4f8426, 2026-10-09) priced the model at the live $/WAR; the test pins the model under the table (41.2 under 48.2). Re-fitting or re-pinning is a do-not-reopen call: the owner decides whether the separation invariant still holds in that direction. |
| test_efv_surrogate_guard::test_vintage_frame_blob_is_pinned, test_efv_surrogate_look::test_t5_static_holds_on_this_tree | STALE PIN, OWNER CALL | efv_vintage_frame.py moved from blob 09430d3b to 21865698 at 44f0097b (EFV_TRAIN_THROUGH_2026, default False, 100 inserted lines, nothing removed). The s11 pin in both files and a dated 12.4 note in SURROGATE_2026_GATE.md are the restamp; a gate pin, so the owner says. |
| test_efv_v2_model::test_screen_flag_off_keeps_the_lists_the_heads_and_the_assembly | STALE PIN | The served heads come from the eFV v5 re-fit (8ae40518), not fit_v2 on vm. The running EFV_WEIGHT_INTEGRITY lane owns the served heads; restamp after it lands. |
| test_efv_w2_popmle (3 ids) | STALE PIN | 8ae40518 flipped POP_REPAIR_ON to True. The restamp: assert True in test_the_repair_is_dark_until_the_refit, and in the two norm tests set the flag False first to read the legacy loop, then True. Drafted here, not committed (the harness declined the edit). |
| test_proj_eval::test_run_source_is_pinned, test_run_rowmatch_source_is_pinned | STALE PIN | 629fd13d (aging v3 service) edited run and run_rowmatch without restamping. New hashes: run f7dbad25a1b58e50876b5c568165ff28e188c29969104b65c441046ff795e64d, run_rowmatch 6f495aacf08b30970b74a3d264a7a882ca62763b0f5aec1027b2fe7796a0aedf. Drafted here, not committed (the harness declined the edit). |
| test_efv_delta_chip_display::test_the_rendered_badge_and_its_tooltip_reconcile | BROWSER | 0 .fv-badge rendered under #rows on page one while the class appears 81 times in the source; 7d6e0d34 moved the tool consensus into the cards. Needs a live DOM look. |
| test_prospx_card_one_consensus (3 ids), test_prospx_surplus_card_basis | BROWSER | The card eyebrow read returns None and the detail wait times out on the player card after 7d6e0d34. Needs a live DOM look at the card header. |
| test_prospx_title_repetition | DEFECT | xm-surfaces.js puts PROSPECT_FAIR (two sentences) in every prospect row's title; 100 repeats. Move the definition to the column header title and keep "Fair $ only" per row. |
| test_prospx_board_layout (2 ids) | DEFECT | .player-row-col1 content is 98 px in a 96 px row at 1024 and 1100 px on 50 and 17 rows: a 2 px overflow since a row chip was added. |
| test_control_theme_site::test_the_lifted_fields_do_not_zoom_or_shrink_on_a_touch_screen | STALE PIN | #gx-surplus-side lives in the Methodology view's Value chapter since 8e40db54; the test's tab pass never opens that chapter (adding the chapter rail to its click list did not reach it). |
| test_control_window_dom::test_the_csv_carries_the_control_window | DATA | The CSV's Control thru for Junior Caminero is empty (ctrlThruOf); check the projections payload's control window for him. |
| test_fa_realized_ledger::test_the_served_archive_names_the_displayed_basis | STALE ARTIFACT | data/fa_archive.json still names basis ewar_v2; fa_export did not rerun at the eWAR v3 flip. Regenerate on the main tree (then tools/export_trade_values.py if proj_export runs). |
| test_mlbstats_display_pass::test_the_pager_turns_pages_and_csv_keeps_every_row | DEFECT | The hitters CSV carries one line more than the board's row count since the XM-FLIP; check the cells xm-surfaces injects against eephus-csv's row filter. |
| test_mlbstats_fit (3 fit ids at 390 and 768 px, found red) | DEFECT | Tables overflow their box on the boards that gained the pitch-rate columns: at 390 px hitters discipline, defense runs and catching, bullpen last 3 value, the six hitter drawers and baserunning (7 to 61 px over); at 768 px defense runs and the hitters skill drawer. |
| test_scores_render::test_chart_role_label_twin_crosshair_and_keys | BROWSER | .sc-tip is not visible after the hover; timing or a tooltip regression on the win probability chart. |
| test_standings_render::test_budgets_and_the_cold_first_paint | OWNER CALL | assets/standings.js is 47,972 bytes against the 45 KB JS_RAW budget since STANDINGS_8 (30c990d6). Trim or raise the budget to 48 KB with a dated note. |

## 3. The confirmation run

python -m pytest -q -p no:cacheprovider -rfE --tb=line <the 90 baseline ids, the 4 found-red ids, test_xm_surfaces's new id, test_share_cards's second id and test_asset_versioning.py> on the worktree at 9b8a5b62: 31 failed, 84 passed, 2 warnings in 825.89s (0:13:45). The 31 red are the rows of section 2 exactly (27 baseline ids and the 4 found red on the way: the three mlbstats_fit fit checks and the odds junction). Of the 90 baseline ids, 63 are green (62 cleared here, 1 already green at 305ca53c) and 27 stay red with their class above. The full-suite baseline of docs/port/BASELINE_PYTEST.txt is re-recorded by the runbook's L3 after the port's L1, not here.
