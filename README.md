# Pokemon ETB Pricing Data Pipeline

Collects weekly pricing and metadata for Pokemon Elite Trainer Boxes (ETBs)
into MongoDB, for a personal research project modeling ETB market price vs.
an implied fair value. Data collection only — no trading logic, no frontend.

## Status per source

| Source | Status | Notes |
|---|---|---|
| PriceCharting | **Live scraper** | No API key needed; scrapes product pages (allowed by robots.txt) |
| Bulbapedia | **Live scraper** | Release date + card count from the set infobox |
| Google Trends | **Live** | Via `pytrends`, no key needed |
| TCGplayer | **Stubbed** | Real client_credentials + pricing logic implemented, but needs an app key (see below). Skipped cleanly until then. |
| 130point.com | **Manual CSV** | Site is Cloudflare-protected (JS challenge); can't be scraped respectfully. See below. |
| PSA pop report | **Manual CSV** | Same — Cloudflare-protected. See below. |

## Setup

1. **MongoDB.** Point `MONGO_URI` at any MongoDB instance. Easiest local option:
   ```
   docker run -d --name pokemon-etb-mongo -p 27017:27017 -v mongo-data:/data/db mongo:7
   ```
2. **Python deps:**
   ```
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Env vars.** Copy `.env.example` to `.env` and fill in:
   - `MONGO_URI`, `MONGO_DB_NAME` — defaults work with the Docker command above.
   - `TCGPLAYER_CLIENT_ID`, `TCGPLAYER_CLIENT_SECRET` — optional. Request an app
     key at https://docs.tcgplayer.com/docs/getting-started. Until both are
     set, the tcgplayer source is skipped and everything else still runs.

## Running

```
python run_weekly.py                 # fetch everything, write to Mongo
python run_weekly.py --dry-run       # fetch and print, don't touch Mongo
python run_weekly.py --log-level DEBUG
python run_weekly.py --config other_config.yaml
```

Logs go to stdout and `logs/pipeline.log`. Scraped HTML is cached under
`cache/` (per-domain, a few hours TTL) so repeated/dry-run invocations don't
re-hit sites unnecessarily.

## Adding a new ETB

Add an entry to `config.yaml` — no code changes needed:

```yaml
products:
  - id: my-new-set-etb            # slug, becomes the Mongo _id
    set_name: "My New Set"
    msrp: 79.99
    specialty_set_flag: false
    box_art_pokemon: "Pikachu"
    new_mechanic_flag: false
    google_trends_query: "My New Set ETB"
    source_urls:
      bulbapedia: "https://bulbapedia.bulbagarden.net/wiki/My_New_Set_(TCG)"
      pricecharting:
        etb_sealed:
          url: "https://www.pricecharting.com/game/<slug>/elite-trainer-box"
          label: "Ungraded"
```

Leave `release_date` / `set_size` / `jp_release_date` unset to have them
scraped from Bulbapedia automatically. Set them explicitly to override the
scrape — config always wins over scraped values.

### Finding the right PriceCharting URL and label

Search `https://www.pricecharting.com/search-products?type=prices&q=<set+name>+elite+trainer+box`,
open the real product page, and check the column headers in the price table —
they vary by product (a sealed ETB's real price usually shows up under
**"Ungraded"**, since there's nothing to grade; a single promo card page will
have **"PSA 10"**, **"Grade 9.5"**, etc.). Set `label` to match exactly what's
on the page. Don't guess the URL — an incorrect guess silently attaches the
wrong product's price history.

You can add more `pricecharting` entries per product for other price types:

```yaml
      pricecharting:
        etb_sealed:
          url: "https://www.pricecharting.com/game/<slug>/elite-trainer-box"
          label: "Ungraded"
        promo_psa10:
          url: "https://www.pricecharting.com/game/<slug>/<promo-card-slug>"
          label: "PSA 10"
        promo_raw:
          url: "https://www.pricecharting.com/game/<slug>/<promo-card-slug>"
          label: "Ungraded"
        booster_pack_loose:
          url: "https://www.pricecharting.com/game/<slug>/booster-pack"
          label: "Ungraded"
```

### TCGplayer (once you have a key)

```yaml
      tcgplayer:
        etb_sealed:
          product_id: 123456     # TCGplayer's numeric product ID, from the product URL
```

### 130point.com and PSA population (manual)

Both sites sit behind Cloudflare's bot-detection challenge, which blocks
plain scraping outright — and automating past that isn't something this
project does. Instead, look the numbers up yourself and add rows to the CSVs
under `manual_data/`:

- `manual_data/onepthirty.csv` — columns: `product_id, date, price_type, price, currency`
  (look up sold listings at https://130point.com/sales/)
- `manual_data/psa_pop.csv` — columns: `product_id, date, value`
  (look up population counts at https://www.psacard.com/pop)

`product_id` must match the `id` you used in `config.yaml`. These files are
read fresh on every run — no restart needed.

## Schema

- **`products`** — one doc per ETB: `_id`, `set_name`, `release_date`, `msrp`,
  `set_size`, `specialty_set_flag`, `box_art_pokemon`, `jp_release_date`,
  `new_mechanic_flag`, `source_urls`.
- **`price_snapshots`** — one doc per observation: `product_id`, `date`,
  `price_type` (`etb_sealed` / `promo_psa10` / `promo_raw` / `booster_pack_loose`),
  `source`, `price`, `currency`, `raw_payload`.
- **`scarcity_signals`**: `product_id`, `date`, `signal_type`
  (`psa_pop_count` / `google_trends_index` / `sellout_flag`), `value`, `source`.

`price_snapshots` and `scarcity_signals` are upserted on a natural key
(`product_id`, `date`, `price_type`/`signal_type`, `source`), so re-running
the pipeline for a date that's already recorded updates in place instead of
duplicating. Both collections have a compound index on `(product_id, date)`
for time-series queries.

## Tests

```
python -m pytest
```

All source modules are covered with mocked-network/mongomock tests, plus
fixtures captured from real pages (PriceCharting, Bulbapedia) so parsing
logic is exercised without live network access in CI. The PriceCharting,
Bulbapedia, and Google Trends modules have additionally been verified live
against the real sites during development.
