# Accommodation Scraper (Booking.com, Trip.com, Agoda)

Finds 1-room/apartment listings in **Beijing, Shanghai, Zhangjiajie** for
**1–13 December 2026** that:

- sleep ≥ 4 people
- have ≥ 2 beds and ≥ 2 bathrooms
- are a single unit (apartment / villa / entire home — *not* two separate hotel rooms)
- cost ≤ **A$350 per night**

Results are written to `results/<city>/` as `matches.json`, `matches.csv`,
`rejected.json` (with reason codes), and `summary.txt`.

## Install

```bash
pip install -r requirements.txt
playwright install chromium
```

## Run

```bash
python main.py
```

Tweak search parameters in `config.py`. To watch the browser, set
`HEADLESS = False`.

## Layout

```
config.py            search criteria + city list
models.py            Listing dataclass
filters.py           filter logic (price, beds, baths, single-unit)
scrapers/
  base.py            shared Playwright setup, jitter, helpers
  booking.py         Booking.com  (apartments via nflt ht_id filter)
  agoda.py           Agoda        (hotelTypeId apartment/villa/home/condo)
  trip.py            Trip.com     (hotelType=apartment)
main.py              orchestrator → per-city output files
results/<city>/      matches + rejected + summary
```

## Caveats

These three sites have anti-bot protection and their DOM changes
frequently. The scraper:

- uses a real Chromium browser with realistic UA / locale / viewport
- adds jittered delays and human-like scrolling
- isolates selectors in each per-site module so they can be patched
  independently when a site rolls out new markup

If a city returns zero results, set `HEADLESS = False` in `config.py`,
re-run, and inspect what the site is rendering — usually it is a
selector change or a captcha challenge. Update the relevant
`_extract_cards` / `_extract_detail` selectors.

The filter is conservative: bathroom counts in particular are often
absent on search-result cards, so the detail page is visited for every
candidate. Listings where the property type doesn't match a single-unit
keyword (apartment / villa / condo / entire home / etc.) are rejected so
that "2 rooms" never means "two separate hotel rooms".

Please respect each site's ToS and robots.txt and rate-limit yourself
if running this often.
