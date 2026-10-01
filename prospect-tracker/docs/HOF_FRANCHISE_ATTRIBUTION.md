# Hall of Fame franchise attribution

Frozen 2026-09-25 by owner answer (final-pass batch 6, census finding M10-12).
Written into the repo 2026-10-01. This document is the rule behind the /hof/
Franchises section and the /franchise/ Hall of Fame tile; both were dark until
it existed (commit 7d2a2edf named them dark on a frozen attribution rule and a
franchise spine that started in 1969).

## The rule

An inductee is credited to ONE franchise: the franchise with which he
accumulated the most Baseball-Reference WAR, summed over every stint in the
war_daily file (batting and pitching together, the same rows `hof_data.career_frame`
sums for career WAR). The code is `hof_data.franchise_credit` and
`hof_data.primary_franchise`; the wording the page prints is
`hof_data.FRANCHISE_RULE` and the date is `hof_data.FRANCHISE_RULE_FROZEN`.

Ties are exact ties on the two-decimal sums the file carries. They go to more
seasons with the franchise, then the earlier first season with it, then the
franchise key, so the answer never depends on row order. Measured 2026-10-01:
no inductee needed the tie-break.

The population is every inductee the ledger resolves to a playing record, on
any route (310 of 354 StatsAPI inductees on 2026-10-01). Credit is by PLAYING
WAR, so an inductee enshrined as a manager or executive is credited where he
played (Connie Mack reads Pittsburgh). The induction column keeps its three
states: a writers' election as a player is the only player induction the page
can verify, and every per-franchise count says how many of each.

## Rejected

- The cap on the plaque. No source in this tree records it, and the plaque
  role itself is unverified (H-DATA-PLAQUE).
- Most seasons, or most games, with a club. It credits a long decline over a
  short peak.
- Fractional credit as the headline. Each inductee counts once. The WAR each
  inductee earned with every franchise is still served beside the credit
  (`sections.franchises.inductees[].credit` in data/hof_board.json), and it sums
  to his career WAR.

## The map, 1871 to 2026

`data/franchise_spine.json` carries two blocks.

- `orgs`, 1969 to 2026, keyed on (team_ID, season). It is the /franchise/ club
  bWAR line and is unchanged.
- `history`, 1871 to 1968, keyed on (team_ID, lg, season), written by
  `tools/franchise_spine_history.py` from the war_daily parquets. Before 1969
  Baseball-Reference reuses a team code across unrelated clubs (BAL is the 1872
  Canaries, the 1882-1899 Orioles, the 1914-1915 Terrapins and the 1954 on
  Orioles), so the league is part of the key. war_daily carries a null lg_ID for
  the National Association; the block writes it as NA.

Lineage (the 30 current franchises before 1969) follows the grouping
Baseball-Reference and the Lahman database both use: a franchise starts when its
club entered the National League (1876), the American Association (1882) or the
American League (1901). A National Association club is a club of its own, so the
1871-1875 Boston Red Stockings are not the Braves and the 1871-1875 Chicago White
Stockings are not the Cubs. The 1901 Milwaukee Brewers start the Orioles; the
1901-1902 Baltimore Orioles start the Yankees; the 1901-1960 Senators are the
Twins.

DEFUNCT is the explicit bucket for every other season before 1969. Each defunct
club is written out with its own key (DEF-<code>-<first season>), so two defunct
clubs are never pooled when a player's primary franchise is chosen; they roll up
to DEFUNCT only on a per-franchise count. A defunct club is one team code, split
at a change of league family (nineteenth-century majors NA, NL, AA, UA, PL; the
Federal League; the seven Negro Leagues MLB recognised in 2020) and, for
nineteenth-century majors only, at a missing season. Negro Leagues codes are not
split on a gap, because the recognised seasons themselves have gaps. Eight named
merges then join the codes one club played under:

1. Chicago White Stockings, 1871 and 1874-1875 (no club after the 1871 fire).
2. Baltimore Orioles, AA 1882-1891 then NL 1892-1899 (BAL, BLN).
3. Washington Senators, AA 1891 then NL 1892-1899 (WAS, WHS).
4. Cleveland Blues (AA 1887-1888) then Spiders (NL 1889-1899) (CLE, CLV).
5. Indianapolis Hoosiers 1914 then Newark Peppers 1915, Federal League (IND, NEW).
6. Elite Giants: Nashville, Columbus 1935, Washington 1936-1937, Baltimore
   1938-1948 (NEG, CEG, WEG, BEG).
7. Eagles: Brooklyn 1935, Newark 1936-1948 (BE, NE).
8. Crawfords: Pittsburgh 1933-1938, then Toledo and Indianapolis 1939-1940 (PC, TC).

Measured 2026-10-01: 1,860 team-league-seasons before 1969, 1,278 to the 30
franchises and 582 to 161 defunct clubs.

## The outcome, measured 2026-10-01

310 inductees credited, 0 unmapped. 263 to a current franchise, 47 to a defunct
club (18 nineteenth-century major, 1 Federal League, 28 Negro Leagues). The four
Negro Leagues inductees bridged on 2026-09-24 (9bd4930a) resolve: Josh Gibson
and Ray Brown to the Homestead Grays (DEF-HG-1929), Oscar Charleston to the
Harrisburg Giants (DEF-HBG-1924), Cool Papa Bell to the St. Louis Stars
(DEF-SLS-1922). These figures are read off data/hof_board.json and are not
pinned here; the page prints them from the payload.

## Reproduce

    python tools/franchise_spine_history.py          # writes the history block
    python tools/franchise_spine_history.py --check  # exit 1 if it would move
    python hof_export.py                             # data/hof_board.json
    python franchise_export.py                       # data/franchise_board.json

Tests: test_hof_franchise.py (every stint since 1871 maps; one primary per
inductee; the credit sums to career WAR; the four bridged inductees resolve; the
tie-break), test_hof_export.py, test_franchise_export.py, test_franchise_spine.py.
