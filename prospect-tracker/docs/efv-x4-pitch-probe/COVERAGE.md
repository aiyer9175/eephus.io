# StatsAPI pitch tracking below Triple-A: coverage tables

Generated 2026-10-15T19:09:09Z by `tools/efv_x4_pitch_probe.py` from `data/_labs/efv_x4_pitch_probe.json`. Registration: `docs/efv-x4-pitch-probe/REGISTRATION.md` (sha256 58c7796052ab). Development probe; ships nothing.

Sample: 1440 games read (1439 fetched, 1 already cached, 0 failed, in the first network pass), two per home team, level and season (the first home game on or after May 15 and on or after Aug 1), each the raw `/api/v1.1/game/{gamePk}/feed/live` JSON cached under `.cache/efv_x4_pitch/feeds/`. A game is tracked for a field when the field is present on at least 80 percent of its pitches (of its balls in play for launch speed and angle). A cell is VELO-COVERED when release speed is tracked in at least half its sampled games, FULL-COVERED when release speed, spin, induced vertical break, extension, plate location, launch speed and launch angle each are.

## 1. Share of sampled games tracked, by level and season

| level | season | games | venues | release speed | spin rate | induced vertical break | horizontal break | extension | plate location (pX, pZ) | zone | pitch type | launch speed | launch angle | stringer pixel location (x, y; extra, unregistered) | VELO-COVERED | FULL-COVERED |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AAA | 2021 | 60 | 31 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% | no | no |
| AAA | 2022 | 60 | 30 | 37% | 37% | 37% | 37% | 37% | 37% | 37% | 37% | 37% | 37% | 100% | no | no |
| AAA | 2023 | 60 | 30 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | yes | yes |
| AAA | 2024 | 60 | 30 | 100% | 98% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | yes | yes |
| AAA | 2025 | 60 | 30 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | yes | yes |
| AAA | 2026 | 60 | 30 | 100% | 98% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% | yes | yes |
| AA | 2021 | 60 | 30 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% | no | no |
| AA | 2022 | 60 | 30 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% | no | no |
| AA | 2023 | 60 | 30 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% | no | no |
| AA | 2024 | 60 | 30 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% | no | no |
| AA | 2025 | 60 | 30 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% | no | no |
| AA | 2026 | 60 | 30 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% | no | no |
| A+ | 2021 | 60 | 30 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% | no | no |
| A+ | 2022 | 60 | 30 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% | no | no |
| A+ | 2023 | 60 | 30 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% | no | no |
| A+ | 2024 | 60 | 30 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% | no | no |
| A+ | 2025 | 60 | 30 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% | no | no |
| A+ | 2026 | 60 | 30 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% | no | no |
| A | 2021 | 60 | 29 | 30% | 30% | 30% | 30% | 30% | 30% | 30% | 30% | 30% | 30% | 100% | no | no |
| A | 2022 | 60 | 29 | 30% | 28% | 30% | 30% | 28% | 30% | 30% | 30% | 30% | 30% | 100% | no | no |
| A | 2023 | 60 | 30 | 27% | 27% | 27% | 27% | 27% | 27% | 27% | 27% | 27% | 27% | 100% | no | no |
| A | 2024 | 60 | 29 | 30% | 30% | 30% | 30% | 30% | 30% | 30% | 30% | 30% | 30% | 100% | no | no |
| A | 2025 | 60 | 29 | 30% | 28% | 30% | 30% | 30% | 30% | 30% | 30% | 30% | 30% | 100% | no | no |
| A | 2026 | 60 | 30 | 30% | 30% | 30% | 30% | 30% | 30% | 30% | 30% | 30% | 30% | 100% | no | no |

The last field column, the stringer's pixel location, is an extra the registration did not name (it was seen on the first sampled feed) and enters no rule: it is the Gameday operator's click on a drawn zone, not a measured location.

## 2. Release speed by park

Games with release speed tracked over games sampled, per venue and season (the venue as the feed names it).

| level | venue | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|
| AAA | 121 Financial Ballpark | 0/2 | 0/2 | 2/2 | 2/2 |  |  |
| AAA | AutoZone Park | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | CHS Field | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Cheney Stadium | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Chickasaw Bricktown Ballpark | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Coca-Cola Park | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Constellation Field | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Coolray Field | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 |  |
| AAA | Dell Diamond | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Durham Bulls Athletic Park | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | ESL Ballpark |  |  |  |  |  | 2/2 |
| AAA | Fifth Third Field | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | First Horizon Park | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Frontier Field | 0/2 | 0/2 |  |  |  |  |
| AAA | Greater Nevada Field | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Gwinnett Field |  |  |  |  |  | 2/2 |
| AAA | Harbor Park | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Huntington Park | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Innovative Field |  |  | 2/2 | 2/2 | 2/2 |  |
| AAA | Isotopes Park | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Las Vegas Ballpark | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Louisville Slugger Field | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | NBT Bank Stadium | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | PNC Field | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Polar Park | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Principal Park | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Sahlen Field | 0/1 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Smith's Ballpark | 0/2 | 2/2 | 2/2 | 2/2 |  |  |
| AAA | Southwest University Park | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Sutter Health Park | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | The Ballpark at America First Square |  |  |  |  | 2/2 | 2/2 |
| AAA | Trenton Thunder Ballpark | 0/1 |  |  |  |  |  |
| AAA | Truist Field | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Victory Field | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AAA | Vystar Ballpark |  |  |  |  | 2/2 | 2/2 |
| AAA | Werner Park | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| AA | 7 17 Credit Union Park |  |  |  |  |  | 0/2 |
| AA | AT&T Field | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |  |
| AA | Arvest Ballpark | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| AA | Blue Wahoos Stadium | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| AA | Canal Park | 0/2 | 0/3 | 0/2 | 0/2 | 0/2 |  |
| AA | CarMax Park |  |  |  |  |  | 0/2 |
| AA | Covenant Health Park |  |  |  |  | 0/2 | 0/2 |
| AA | DABOS Park |  |  |  |  |  | 0/2 |
| AA | Delta Dental Park |  |  |  |  | 0/2 | 0/2 |
| AA | Delta Dental Stadium | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/3 |
| AA | Dickey-Stephens Park | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| AA | Dunkin' Donuts Park | 0/2 | 0/2 |  |  |  |  |
| AA | Dunkin' Park |  |  | 0/2 | 0/2 | 0/2 | 0/2 |
| AA | Equity Bank Park |  |  |  |  | 0/2 | 0/2 |
| AA | Erlanger Park |  |  |  |  |  | 0/2 |
| AA | FNB Field | 0/2 | 0/2 | 0/2 | 0/3 | 0/2 | 0/2 |
| AA | FirstEnergy Stadium | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/1 |
| AA | Hadlock Field | 0/2 | 0/2 | 0/2 | 0/2 |  |  |
| AA | Hammons Field | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |  |
| AA | Hodgetown | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| AA | Keesler Federal Park |  |  |  | 0/2 | 0/2 | 0/2 |
| AA | MGM Park | 0/2 | 0/2 | 0/2 |  |  |  |
| AA | Mirabito Stadium | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| AA | Momentum Bank Ballpark | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| AA | Montgomery Riverwalk Stadium | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |  |
| AA | Nelson Wolff Stadium | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| AA | ONEOK Field | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| AA | Peoples Natural Gas Field | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| AA | Prince George's Stadium | 0/2 | 0/1 | 0/2 | 0/2 | 0/2 | 0/2 |
| AA | Regions Field | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| AA | Riders Field | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| AA | Riverfront Stadium | 0/2 | 0/2 | 0/2 | 0/2 |  |  |
| AA | Route 66 Stadium |  |  |  |  |  | 0/2 |
| AA | Smokies Stadium | 0/2 | 0/2 | 0/2 | 0/2 |  |  |
| AA | Synovus Park |  |  |  |  | 0/2 | 0/2 |
| AA | TD Bank Ballpark | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| AA | The Diamond | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |  |
| AA | Toyota Field | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| AA | Trustmark Park | 0/2 | 0/2 | 0/2 | 0/2 |  |  |
| AA | UPMC Park | 0/2 | 0/2 | 0/2 | 0/1 | 0/2 | 0/2 |
| AA | Whataburger Field | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | ABC Supply Stadium | 0/1 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | AdventHealth Stadium |  | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | Avista Stadium | 0/2 | 0/2 | 0/2 | 0/3 | 0/2 | 0/2 |
| A+ | Bowling Green Ballpark | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | Classic Auto Group Park |  |  | 0/1 | 0/2 | 0/2 | 0/2 |
| A+ | Classic Park | 0/2 | 0/2 |  |  |  |  |
| A+ | Day Air Ballpark | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | Dow Diamond | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | Dozer Park | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | Dutchess Stadium | 0/2 | 0/2 |  |  |  |  |
| A+ | Everett Memorial Stadium |  |  |  |  |  | 0/2 |
| A+ | Fifth Third Park |  |  |  |  | 0/2 | 0/2 |
| A+ | First National Bank Field | 0/2 | 0/2 | 0/2 | 0/1 | 0/2 | 0/2 |
| A+ | FirstEnergy Park | 0/2 |  |  |  |  |  |
| A+ | Fluor Field at the West End | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | Four Winds Field | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | Frawley Stadium | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | Funko Field | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |  |
| A+ | Gesa Stadium | 0/2 | 0/2 | 0/3 | 0/2 | 0/2 | 0/2 |
| A+ | Heritage Financial Park |  |  | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | Hillsboro Ballpark |  |  |  |  | 0/2 |  |
| A+ | HomeTrust Park |  |  |  |  |  | 0/2 |
| A+ | Hops Ballpark |  |  |  |  |  | 0/2 |
| A+ | Jackson Field | 0/2 | 0/2 | 0/3 | 0/2 | 0/2 | 0/2 |
| A+ | L.P. Frans Stadium | 0/2 | 0/2 | 0/2 | 0/3 |  |  |
| A+ | LMCU Ballpark | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | Leidos Field at Ripken Stadium | 0/2 | 0/2 | 0/2 | 0/2 |  |  |
| A+ | Maimonides Park | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | McCormick Field | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |  |
| A+ | Modern Woodmen Park | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | Nat Bailey Stadium |  | 0/2 |  |  |  |  |
| A+ | Neuroscience Group Field | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | Nymeo Field |  |  |  |  |  | 0/2 |
| A+ | PK Park | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | Parkview Field | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | Perfect Game Field | 0/2 | 0/2 |  |  |  |  |
| A+ | Pohlman Field | 0/1 |  |  |  |  |  |
| A+ | Ripken Stadium |  |  |  |  | 0/2 |  |
| A+ | Rise 2 Greatness Field |  |  | 0/2 | 0/2 |  |  |
| A+ | Rogers Field at Nat Bailey Stadium |  |  | 0/1 | 0/1 | 0/2 | 0/2 |
| A+ | Ron Tonkin Field | 0/4 | 0/2 | 0/2 | 0/2 |  |  |
| A+ | ShoreTown Ballpark |  | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | State Mutual Stadium | 0/2 |  |  |  |  |  |
| A+ | Truist Stadium | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A+ | Veterans Memorial Stadium |  |  |  |  | 0/2 | 0/2 |
| A | Arthur W. Perdue Stadium | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A | Atrium Health Ballpark | 0/2 | 0/2 | 0/3 | 0/2 | 0/2 | 0/2 |
| A | Bank of the James Stadium | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |  |
| A | Banner Island Ballpark | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A | BayCare Ballpark | 3/3 | 2/2 | 2/2 | 2/2 | 1/1 | 2/2 |
| A | Carilion Clinic Field |  | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A | Chukchansi Park | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A | City Stadium |  |  |  |  |  | 0/2 |
| A | Clover Park | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| A | Excite Ballpark | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A | Five County Stadium | 0/2 | 0/2 | 0/1 | 0/2 | 0/2 |  |
| A | FredNats Ballpark | 0/2 |  |  |  |  |  |
| A | George M. Steinbrenner Field | 1/1 | 2/2 | 2/2 | 2/2 |  | 2/2 |
| A | Grainger Stadium | 0/2 | 0/2 | 0/2 | 0/2 |  |  |
| A | Haley Toyota Field | 0/2 |  |  |  |  |  |
| A | Hammond Stadium | 2/2 | 2/2 | 2/2 |  |  |  |
| A | Jackie Robinson Ballpark | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A | John Thurman Field | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |  |
| A | Joseph P. Riley, Jr. Ballpark | 0/2 | 0/2 | 0/2 | 0/1 | 0/2 | 0/2 |
| A | L.P. Frans Stadium |  |  |  |  | 0/2 | 0/1 |
| A | LECOM Park | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 2/2 |
| A | Lee Health Sports Complex |  |  |  | 2/2 | 2/2 | 2/2 |
| A | LoanMart Field | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |  |
| A | Morongo Field |  |  |  |  |  | 0/2 |
| A | ONT Field |  |  |  |  |  | 0/2 |
| A | Pelicans Ballpark |  | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A | Publix Field at Joker Marchant Stadium | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| A | Roger Dean Chevrolet Stadium | 5/5 | 4/4 | 2/2 | 4/4 | 4/4 | 4/4 |
| A | SEGRA Stadium | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A | SRP Park | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A | San Manuel Stadium | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A | Segra Park | 0/2 | 0/2 | 0/2 | 0/3 | 0/2 | 0/2 |
| A | TD Ballpark | 1/1 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| A | The Ballpark of the Palm Beaches |  |  | 0/2 |  |  |  |
| A | The Diamond | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A | TicketReturn.com Field | 0/2 |  |  |  |  |  |
| A | Truist Stadium |  |  |  |  |  | 0/1 |
| A | Valley Strong Ballpark | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A | Virginia Credit Union Stadium |  | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| A | Wilson Ballpark |  |  |  |  |  | 0/2 |
| A | Yankee Complex Field 2 |  |  |  |  | 2/2 |  |

## 3. Release speed by league below Triple-A

| level | league (as the feed names it) | seasons sampled | games sampled | games tracked |
|---|---|---|---|---|
| AA | Double-A Central | 2021 | 20 | 0 |
| AA | Double-A Northeast | 2021 | 24 | 0 |
| AA | Double-A South | 2021 | 16 | 0 |
| AA | Eastern League | 2022 to 2026 | 120 | 0 |
| AA | Southern League | 2022 to 2026 | 80 | 0 |
| AA | Texas League | 2022 to 2026 | 100 | 0 |
| A+ | High-A Central | 2021 | 24 | 0 |
| A+ | High-A East | 2021 | 24 | 0 |
| A+ | High-A West | 2021 | 12 | 0 |
| A+ | Midwest League | 2022 to 2026 | 120 | 0 |
| A+ | Northwest League | 2022 to 2026 | 60 | 0 |
| A+ | South Atlantic League | 2022 to 2026 | 120 | 0 |
| A | California League | 2022 to 2026 | 80 | 0 |
| A | Carolina League | 2022 to 2026 | 120 | 0 |
| A | Florida State League | 2022 to 2026 | 100 | 88 |
| A | Low-A East | 2021 | 24 | 0 |
| A | Low-A Southeast | 2021 | 20 | 18 |
| A | Low-A West | 2021 | 16 | 0 |

## 4. Verdict by the registered rule

- Coverage below Triple-A REAL (a sub-AAA cell of 2021 to 2023 VELO-COVERED): **no**.
- Sub-AAA cells VELO-COVERED, any season: none.
- Control, Triple-A release speed share of sampled games by season: 2021 0%, 2022 37%, 2023 100%, 2024 100%, 2025 100%, 2026 100%.
- Sub-AAA leagues with a tracked sampled game (tracked/sampled): A Florida State League (88/100), A Low-A Southeast (18/20).
