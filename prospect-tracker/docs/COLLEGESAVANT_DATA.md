# CollegeSavant data: what the apps serve and where a refresh comes from

Written 2026-10-09 with REDESIGN_collegesavant (site-pass plan 5.3).

## What is on the page

Both apps read vendored season files under `collegesavant/`, received 2026-06-11 and not
refreshed since (`DATA_RECEIVED` in `app.js` and `pitcher_app.js`). The files carry no game
dates.

| app | season | scope | file |
|---|---|---|---|
| Hitters | 2025 | Big Ten only, 184 hitters, 16 teams, no PA column | `hitter_year_data.js` (year 2025), `hitter_bip_2025.js` |
| Hitters | 2024 | national, 3,607 hitters, 336 teams | `hitter_year_data.js` (year 2024), `hitter_bip_2024.js` |
| Pitchers | 2026 | national, 842 arms, 315 teams | `pitcher_data.js` (year 2026), `pitcher_pitch_data_2026.js` |
| Pitchers | 2025 | Big Ten only, 199 arms, 16 teams | `pitcher_data.js` (year 2025), `pitcher_pitch_data_2025.js` |
| Pitchers | 2024 | national, 4,485 arms, 486 teams | `pitcher_data.js` (year 2024), `pitcher_pitch_data_2024.js` |

Each app header prints a dataset badge ("2025 · Big Ten · archive", "2026 · national") and
one season picker, both from the loaded file (`collegesavant/cs_season.js`): the season and
scope come from the app's `yearPool`, the picker lists the seasons the file holds, newest
first, and "archive" marks a season older than the year the files were received. A season
picked on either app is kept for the browser session and used by the other app when its file
holds that season. `test_collegesavant_season_bar.py` pins this.

## Dependency: the 2026 hitter file

There is no 2026 hitter file. The hitter app therefore opens on the 2025 Big Ten archive while
the pitcher app opens on 2026 national.

The CollegeSavant files come from the CollegeSavant pipeline (Will Cahoon's data, external to
this repository). Refreshing them is a data request to that pipeline, not a code task here.
When a 2026 hitter file arrives:

1. add its rows to `hitter_year_data.js` with `"year": 2026` and ship `hitter_bip_2026.js`;
2. add 2026 to `BIP_YEARS` in `app.js`;
3. set `DATA_RECEIVED` in both apps to the day the files were received;
4. restamp through `build_site.restamp_hand_authored_pages()`.

The badge, the picker and the data line follow the file with no other change.
