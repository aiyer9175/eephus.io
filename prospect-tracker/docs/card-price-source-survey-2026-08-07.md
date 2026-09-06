> RETIRED 2026-09-05. The Card Market module was removed from the site and the nightly pipeline (owner decision: not feasible with the current data; no licensed or feasible price source). This document stays as the historical record; nothing below is live.

# Card price source survey, 2026-08-07

Owner ask, verbatim: *"See if there is any other source we can scrape from."*

Answer, up front: **no source passes all three acceptance criteria today.** One
source (SportsCardsPro) passes two of three and fails the third on a contract
term that has a documented permission route, so it is the only candidate worth
the owner's time. Everything else fails on fetchability, on a login wall, or on
volume. The licensed fallback this repo has been carrying since the module
shipped, the SportsCardsPro CSV price guide, **does not contain what we thought
it contained** and would not have worked either; that correction is section 7.

This survey is a complete deliverable as a negative. It is not a request for
another pass.

---

## 1. Acceptance criteria (from the master plan, Lane H2)

A source passes only if all three hold.

**(a) Fetchable honestly.** It answers a plain GET carrying
`card_prices_ingest.USER_AGENT` (our real name, our real contact address) at the
pinned 5 second throttle floor. A 403, a JavaScript interstitial, or a sign-in
redirect is a FAIL. No UA spoofing, no headless browser, no proxy, no cookie
replay. The module's stated posture (`docs/diamond-cards.md` section 1) makes
the scraper the deletable half precisely so that we never have to argue about
this, and the owner was told the survey would respect it.

**(b) Terms compatible with publishing only the derived index.** Raw comps,
sale prices, sale dates and listing titles or ids are unpublishable and
test-pinned (`test_card_market.py:217`, `:258`). We still have to be allowed to
compute and publish a derived statistic on a public page.

**(c) Maps onto the existing contract.** Either the drop CSV column contract
(`docs/diamond-cards.md` section 3) or `SEARCH_URL_TEMPLATE` /
`EEPHUS_CARD_SCRAPE_URL` (`card_prices_ingest.py:108-111`), with no schema
change.

## 2. Method

Every status code below was measured, not recalled. The probe sent:

```
User-Agent: Mozilla/5.0 (compatible; eephus.io card-index/1.0;
  derived price index for a baseball analytics site,
  no raw listing republication; contact: arkndjl@gmail.com)
Accept: text/html,*/*
Accept-Language: en-US,en;q=0.9
```

through `card_prices_ingest.Throttle()` (5.0s floor, the test-pinned value),
redirects followed, 30s timeout. That is byte for byte what the module itself
would send from the box. `robots.txt` was read first for every host.

One deliberate second reading: where a host refused our UA, the page was also
requested through an unrelated fetcher with a different UA, to separate "they
block us" from "they block everyone". That is a diagnostic, not an attempt to
get in.

## 3. Results

| Source | robots | status with honest UA | verdict |
|---|---|---|---|
| eBay sold search (control) | allow-all, but the file's own comment forbids automated access | **403**, 1832 bytes, AkamaiGHost | FAIL (a) |
| PSA Auction Prices Realized | `Crawl-delay: 1`, APR not disallowed | **200 then redirect to `app.collectors.com/signin`** | FAIL (a), login wall |
| SportsCardsPro | allows `/game/`, `/console/`, `/search-products` | **200**, server rendered, 361KB card page | pass (a), pass (c), **FAIL (b)** |
| 130point | `Allow: /`, `Disallow: /api/` | **403**, Cloudflare "Just a moment..." challenge | FAIL (a) |
| COMC | content-signals header, crawl allowed | **403**, Cloudflare challenge | FAIL (a) |
| Heritage Auctions | selective bot bans | **403**, DataDome "Please enable JS" | FAIL (a) |
| Goldin | `Allow: /item/`, `/auction/` | **200** but a 4988 byte JS shell, zero results in HTML | FAIL (a) |
| Card Ladder | no robots.txt (404) | 200 marketing site only | FAIL (a), paid SaaS |
| eBay Marketplace Insights API | n/a | n/a | FAIL, Limited Release, closed to new applicants |
| TCDB | selective | 200 | FAIL (c), checklists, no prices |

### 3a. eBay, the control

`https://www.ebay.com/sch/i.html?_nkw=...&LH_Sold=1&LH_Complete=1&_ipg=60`
returned **403, exactly 1832 bytes, `Server: AkamaiGHost`**, an "Error Page |
eBay" document with `noindex,nofollow`. That is byte-identical to the block page
measured on 2026-08-06 with both our UA and a plain Chrome 126 UA, so the root
cause is confirmed unchanged and UA spoofing remains a measured dead end, not an
untried idea.

Worth recording because it is the actual terms position and not just an edge
rule: eBay's `robots.txt` opens `allow-all` and then says in a comment that *"The
use of robots or other automated means to access the eBay site without the
express permission of eBay is strictly prohibited."* So even if the 403 lifted
tomorrow, criterion (b) was never clean here.

### 3b. PSA Auction Prices Realized: login wall, not a UA block

The APR index at `/auctionprices` returns 200. Both real data pages do not:

* set page `/auctionprices/baseball-cards/2024-bowman-chrome-prospect-autographs/269115`
  redirects to `app.collectors.com/signin?b=psa&r=...`
* card page `.../paul-skenes/11030710` redirects to the same signin, via
  `/spec/psa/11030710`

Requested again through an unrelated fetcher on a different UA: **403**. So APR
is gated on an account, not on our identity. Public search engines still index
the old URLs, which is why it reads as public from the outside. There is a paid
API behind `collectors-apis@collectors.com`; that is a purchase decision, not a
scrape, and it belongs with the other paid options in section 6.

### 3c. SportsCardsPro: the only real candidate

**(a) PASS.** `robots.txt` disallows only `/stripe-connect`, `/publish-offer`
and `/buy`; the price pages are allowed. Measured:

* set page `/console/baseball-cards-2024-bowman-chrome-prospects-autograph`:
  200, 686KB, fully server rendered
* card page `/game/baseball-cards-2024-bowman-chrome-prospects-autograph/<card>`:
  200, 361KB
* search `/search-products?q=...&type=prices`: 200, 493KB

No challenge, no interstitial, no sign-in. Cloudflare fronts the site but does
not challenge this UA.

**(c) PASS.** The card page carries per grade "completed auctions" tables in
plain HTML: `<td class="date">YYYY-MM-DD</td>`, listing title, and a price cell,
under an explicit grade tab (`PSA 10`, `Grade 9`, `SGC 10`, `Ungraded` and the
rest). That is `sold_date` + `price_usd` + `grade` + `title`, which is the drop
CSV column contract exactly and the `Comp` dataclass exactly. No schema change.

Density was measured on one representative card of the type the watchlist
tracks (2024 Bowman Chrome Prospects Autograph, PSA 10 target bucket), counts
only, no prices recorded:

| grade tab | sold rows served | inside a 45 day window |
|---|---|---|
| PSA 10 | 30 | **29** |
| Ungraded | 30 | 30 |
| Grade 9 | 30 | 9 |
| SGC 10 | 11 | 1 |

`MIN_COMPS` is 5. One page read per card per week would clear the index
threshold on the target bucket with room to spare, and the site's own volume
label for that card's PSA 10 row reads "2 sales per week". Feasibility is not
the problem here.

**(b) FAIL, and this is the whole verdict.** Their Terms of Service carries a
section headed *Price Data Acceptable Use*. The operative sentences, verbatim:

> All Price Data on the site is sole property of SportsCardsPro. "Price Data"
> includes current and historical pricing, trends, and any related information
> made available by PriceCharting via its website, API, or downloadable content.

> Price Data may be referenced on external websites provided that:
> SportsCardsPro is clearly cited as the source, and a visible hyperlink to
> SportsCardsPro is included on the external site

> Price Data can be used for your Internal Business Purposes if you maintain a
> valid and current Legendary subscription. "Internal business purposes" refers
> to usage by the subscriber and their authorized employees or contractors,
> strictly within the organization, and not for external display or
> redistribution.

> Price Data cannot be used in any software, application, or system that is
> accessible to third parties, including customers, clients, or the general
> public, without express written permission.

The eephus Card Index is a derived statistic computed from Price Data, published
on a public web page. That is a system accessible to the general public. The
"referenced with citation and a hyperlink" carve-out is for *referencing* their
numbers, not for deriving and publishing our own index off their history, and
the Legendary carve-out is explicitly internal only. So the honest reading is:
**this needs express written permission, and the terms tell us exactly where to
ask.** A subscription alone does not buy it.

This is not a technicality we can route around by being careful about what we
publish. The module already publishes only a derived value, and the clause
covers derived use.

### 3d. The rest, briefly

* **130point.com**: `robots.txt` allows `/`, but `https://130point.com/sales/`
  returns **403** with the Cloudflare "Just a moment..." JS challenge. Passing
  that requires executing their challenge script, which is the definition of the
  circumvention this survey is not allowed to attempt. Their search is also a
  POST form with no documented endpoint.
* **COMC**: same Cloudflare challenge, **403**. Separately it is asking-price
  inventory, not sold comps, so it fails (c) even if it opened.
* **Heritage Auctions**: **403** behind DataDome. High end lots only, so the
  volume would never reach `MIN_COMPS` for a modern prospect auto anyway.
* **Goldin**: 200, but the search page is a 4988 byte client-rendered shell with
  no result markup at all. Same volume objection as Heritage.
* **Card Ladder**: no `robots.txt`, marketing shell, paid SaaS with no public
  per-card data. Enterprise pricing, not a pipeline.
* **eBay Marketplace Insights API**: the official, non-scraping route to 90 days
  of eBay sold history. It is a Limited Release API requiring business level
  approval, eBay's own documentation states it is restricted and not open to new
  users, and 2026 developer reports are of flat denials outside major partners.
  Recorded so nobody spends a week applying.

---

## 4. Verdict

**No compliant source exists today.** Ranked by how close they came:

1. **SportsCardsPro**, fetchable and shape-perfect, blocked only by a contract
   term with a stated permission route. One email.
2. **PSA APR paid API**, a purchase, terms unknown until asked.
3. Everything else, dead.

Nothing was wired, the scraper stays disarmed, and `EEPHUS_CARD_SCRAPE_URL` is
unchanged. `n_priced` is still 0, and after this program the board says so in
the loud way rather than the quiet one (`fetch_blocked`, section 4c of the
runbook).

## 5. Recommendation to the owner

Three doors, in the order I would take them.

**Door 1, ask SportsCardsPro (recommended, costs one email).** Their terms name
the route: *"To request permission, contact ..."*. What we would be asking for is
narrow and easy to say yes to: permission to read their public card pages at one
request per 5 seconds and publish a derived index for about forty cards, with
SportsCardsPro cited as the source and a visible hyperlink on the page, and no
republication of any individual sale. That is close to the "referenced with
citation" case they already allow, and the citation plus link is a cost we
should be happy to pay anyway. If they say yes, wiring is a parser function in
`card_prices_ingest.py` and a `SEARCH_URL_TEMPLATE` change, nothing else.

**Door 2, manual CSV drops (costs operator time, zero legal exposure, works
today).** The drop path already exists, is first class, and needs no network.
The honest cost: to keep 40 cards priced under a 45 day window at
`MIN_COMPS = 5`, somebody hand-assembles a few hundred sale rows a month, and
the index silently degrades if that stops.

**Door 3, buy the SportsCardsPro Legendary subscription ($49/month).** DO NOT
take this door expecting it to solve the problem. See section 7: the paid CSV
does not contain sales history, and the subscription's data rights are
explicitly internal-only, so it fails (b) and (c) both. It is listed here only
because the repo has been recommending it for three weeks and somebody would
otherwise buy it.

If none of the three is taken, the correct end state is the one the board is now
in: 40 cards tracked, 0 priced, `fetch_blocked` filed as a RED, and the page
saying in words that the tap is off. That is a legitimate place to sit.

---

## 6. What was deliberately not attempted

Recorded so the next person does not "discover" these as ideas:

* Rotating or spoofing User-Agents. Measured ineffective against eBay on
  2026-08-06 (identical 1832 byte block for our UA and a plain Chrome UA) and
  banned by the master plan regardless.
* Executing a Cloudflare or DataDome challenge, headless browsers, proxies,
  residential IPs, cookie replay. The module's posture treats the scraper as
  deletable specifically so that we never need these.
* Third party "eBay sold data" resellers. They are reselling access obtained by
  the exact means we just declined to use, and buying it does not change what it
  is.
* Any source requiring an account whose terms we would accept by signing up.
  That is a decision for the owner, not for a survey.

---

## 7. Correction: the licensed fallback in section 7 of the runbook was wrong

`docs/diamond-cards.md` has said since the module shipped that the
SportsCardsPro CSV price guide is "the clean swap ... map its export onto the
column contract in section 3 ... no model change, no page change, no schema
change." **That is false, and it was never verified.**

Measured from their own API and CSV documentation:

> The API and CSV only support current item values in various grades and
> conditions. **Historic prices and historic sales are not supported.**

The CSV columns are one current value per grade per card (`manual-only-price` is
PSA 10, `graded-price` is Grade 9, `loose-price` is Ungraded, plus
`sales-volume`, the yearly unit count). There is no `sold_date` and no per sale
`price_usd`, because there are no sales in it at all.

Consequences, both fatal on their own:

1. **It cannot feed the drop contract.** `parse_drop_csv` requires a price *and*
   a date per row and skips rows that have neither. A price guide has one row
   per card per day.
2. **Even if it were reshaped, the arithmetic would stop meaning what the
   module says it means.** `card_index` takes a trimmed median of sold comps in
   a 45 day window with `MIN_COMPS = 5`. Fed daily guide snapshots, it would
   take a median of five of *their* already-computed medians and publish it as
   "a grade-mix adjusted trimmed median of sold comps". That sentence would be
   false on the page, the trim band would have nothing to trim, and the whole
   published method block would be describing a computation that did not happen.

The runbook has been corrected. The lesson is the ordinary one: a fallback that
nobody has fetched is a plan, not a fallback.

---

## 8. Reproducing this

The probe is not committed (it makes network requests and belongs to a session,
not to the pipeline). To repeat it, request each URL in section 3 with
`card_prices_ingest.USER_AGENT` through `card_prices_ingest.Throttle()` and
record the status code, byte count, `Server` header and final URL after
redirects. The eBay control should return 403 at 1832 bytes; if it does not,
that is news and the whole survey should be re-run.
