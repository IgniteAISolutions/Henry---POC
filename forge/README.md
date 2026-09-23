# Forge

Product copy engine for **Design 911**. Forge takes parts that are listed with no description, finds them elsewhere on the web by part number, checks the facts against each other, and writes the listing in the Design 911 house voice.

Built as a demo, on the same idea as E.V.A. It is not a production system.

```
part number ──► search ──► read pages ──► cross-check ──► write (OpenAI) ──► .xlsx
```

## Run it

### On Vercel (recommended for the demo)

1. Import `IgniteAISolutions/Henry---POC` into Vercel as a **new** project. Leave the existing `earthfare` project alone.
2. **Root Directory: `forge`**. The framework is detected as Next.js.
3. Settings → Environment Variables, for Production and Preview:
   - `OPENAI_API_KEY`, required, used to write the descriptions
   - `OPENAI_MODEL`, optional, defaults to `gpt-4o`
   - `GOOGLE_API_KEY` + `GOOGLE_CSE_ID`, or `BRAVE_API_KEY`, optional, gives better search (see below)
4. Redeploy after adding variables. Vercel only reads them at deploy time.

### Locally

```bash
cd forge
cp .env.example .env.local   # add OPENAI_API_KEY
npm install
npm run dev                  # http://localhost:3000
```

## Running the demo

1. Open the app. The left column lists the 10 Design 911 parts with no description. `Catalogue .xlsx` downloads that list: the "before".
2. Choose the evidence mode (top right):
   - **Auto** (default): searches the live web, and if that finds nothing carrying the part number, replays recorded evidence and says so on screen.
   - **Live**: live web only.
   - **Recorded**: replays the evidence captured on 23 Sep 2026. This is the safety net for bad venue wifi, and it runs the same way every time.
3. Press **Run all 10**. Each part goes through four stages in turn, and the view follows it.
4. `Export listings .xlsx` downloads the "after": finished copy, verdicts, and an Evidence sheet showing every source.

### The three moments worth pausing on

| Part | What happens | Why it matters |
|---|---|---|
| **94411021401** Idle control valve hose | 6 independent sites carry the part number. Rear position and fitment are corroborated. Verified. | The happy path, with receipts. |
| **99750396302GRV** Door sill panel | rosepassion says *rear left*, two Porsche dealers say *front*. Position is **left out of the copy**. | Forge doesn't pick a side or average. It drops the disputed fact. |
| **V04015005BT** Bracket | No page found carries this part number. **Forge refuses to write it.** | A guessed parts listing is how the wrong part gets ordered. |

Also worth telling: while this was being built, a search engine summary described **96410601401** as an *"alternator fan belt sensor"*. The only catalogue page carrying that number says **rear engine cover, 964**. Forge counts pages that carry the number, never summaries.

## How verification works

- A page contributes facts **only if the part number physically appears in it**. A search engine thinking a page is relevant isn't enough.
- Sources count as independent only if they're on **different domains**.
- A fact seen on 2+ sources is **corroborated**. Seen on one, it's **single-source**: usable, but flagged to the writer. When sources **disagree**, the fact is removed before the writer sees it.
- Spec-table rows and scraped fields are compared as one set of facts ("Material" on one site and "Composition" on another are the same fact).
- Fitment is agreed per model, then per engine and year range. A vehicle two sources agree on only carries detail that both agree on. If one says `924S 1988` and another says `924S 1985-89`, the copy says `924S` and the year disagreement is shown as left out. A wrong fitment line is the most expensive mistake in parts copy.
- Retailer search-results pages are never evidence. Forge follows their product links one hop and reads those pages instead.
- Verdicts: `verified` (strong agreement), `probable` (identity established, detail thinner), `conflicting` (written, disputed fields dropped), `unconfirmed` (not written unless you press *Write from catalogue data only*).

## The voice: read before the demo

The header badge shows where the house voice came from:

- **"Voice: reconstructed"** means the writer is working from structural rules derived from publicly indexed Design 911 copy (fitment first, `1997-99` year format, OE cross-references, associated fixings named). This is a reasoned reconstruction, not their actual prose.
- **"Voice: fitted to N real listings"** means `npm run harvest` has pulled real Design 911 descriptions into `data/voice-corpus.json`. The writer copies those, and they override the rules.

**Run the harvester before showing this to Design 911.** Don't claim "this is how you write" while the badge still says *reconstructed*.

```bash
npm run harvest -- --corpus 12          # real listings with descriptions -> data/voice-corpus.json
npm run harvest -- --find-missing 10    # candidate parts with no description -> data/products.candidates.json
npm run harvest -- --find-missing 10 --write-products   # replace the 10 demo parts
```

The harvester writes files, so run it on your machine, then commit `data/` and redeploy. The Vercel filesystem is read-only.

## Search providers

In order: Google Programmable Search (`GOOGLE_API_KEY` + `GOOGLE_CSE_ID`), then Brave (`BRAVE_API_KEY`), then **direct**, which needs no key and queries each specialist retailer's own search page. Direct works, but it's noisier, and some retailers block datacenter IPs such as Vercel's. With no search key, expect Auto mode to fall back to recorded evidence more often.

## Tests

```bash
npm test                 # verification, page reading, sanitiser, recorded demo run
npm run test:harvest     # harvester parsing against synthetic Design 911-shaped pages
```

## Where things live

```
data/products.json            the 10 parts (the "before")
data/evidence-fixtures.json   recorded evidence for Recorded / Auto modes, one real URL per record
data/voice-corpus.json        real Design 911 listings (empty until you harvest)
src/lib/search.ts             part-number search, pluggable providers
src/lib/scrape.ts             page reading, part-number confirmation, fact extraction
src/lib/verify.ts             corroboration, conflicts, confidence, verdict
src/lib/voice.ts              the Design 911 house style and prompt
src/lib/writer.ts             OpenAI call and sanitiser
src/lib/pipeline.ts           the four stages
src/lib/export.ts             spreadsheets
deliverables/                 the catalogue spreadsheet (npm run spreadsheet)
```

## Known limits

- The 10 parts' "no description" status is **inferred** from bare Design 911 page titles ("Original Porsche Part - 99761209005"). `npm run harvest -- --find-missing` confirms it against the page body.
- Recorded evidence was captured from search-index **titles and URLs**. Page bodies weren't fetched. Live mode reads the full pages.
- The harvester's selectors have **never been run against the real site**. They were built against synthetic pages because the build machine couldn't reach design911.co.uk. It tries JSON-LD first, then microdata, then common description containers. If the first real run finds nothing, capture one real page as a fixture in `scripts/harvest-lib.test.ts` and adjust `scripts/harvest-lib.ts`.
- Live OpenAI generation hasn't been run yet, for the same reason. The first Vercel deployment is its first real test.
- The app has no login. Anyone with the URL can press *Run all 10*, which spends a little OpenAI credit (roughly one US cent per part on `gpt-4o`). Keep Vercel Authentication on until the demo if that matters.

Not affiliated with or endorsed by Porsche AG or Design 911.
