"""Orchestrator: scrape every source for every city, filter, save per-city."""

from __future__ import annotations

import asyncio
import csv
import json
import os
from datetime import datetime

from config import CITIES, CRITERIA, HEADLESS, RESULTS_DIR
from filters import passes
from models import Listing
from scrapers import ALL_SCRAPERS


async def scrape_city(city) -> list[Listing]:
    all_listings: list[Listing] = []
    for ScraperCls in ALL_SCRAPERS:
        scraper = ScraperCls(CRITERIA, headless=HEADLESS)
        print(f"\n=== {scraper.source} :: {city.name} ===")
        try:
            listings = await scraper.scrape_city(city)
            print(f"  → {len(listings)} raw listings from {scraper.source}")
            all_listings.extend(listings)
        except Exception as e:
            print(f"  ! {scraper.source} failed for {city.name}: {e}")
    return all_listings


def save_city(city, kept: list[Listing], rejected: list[tuple[Listing, list[str]]]) -> None:
    city_dir = os.path.join(RESULTS_DIR, city.slug)
    os.makedirs(city_dir, exist_ok=True)

    matches_path = os.path.join(city_dir, "matches.json")
    with open(matches_path, "w", encoding="utf-8") as f:
        json.dump([l.to_dict() for l in kept], f, indent=2, ensure_ascii=False)

    csv_path = os.path.join(city_dir, "matches.csv")
    cols = [
        "source", "name", "price_aud_per_night", "total_price_aud",
        "sleeps", "bedrooms", "beds", "bathrooms",
        "property_type", "rating", "review_count", "url",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for l in kept:
            d = l.to_dict()
            w.writerow({k: d.get(k) for k in cols})

    rejected_path = os.path.join(city_dir, "rejected.json")
    with open(rejected_path, "w", encoding="utf-8") as f:
        json.dump(
            [{"listing": l.to_dict(), "reasons": reasons} for l, reasons in rejected],
            f, indent=2, ensure_ascii=False,
        )

    summary_path = os.path.join(city_dir, "summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"City: {city.name}\n")
        f.write(f"Scraped: {datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"Dates: {CRITERIA.check_in} → {CRITERIA.check_out}\n")
        f.write(
            f"Filters: sleeps≥{CRITERIA.adults}, beds≥{CRITERIA.min_beds}, "
            f"baths≥{CRITERIA.min_bathrooms}, price≤A${CRITERIA.max_price_aud_per_night:.0f}/night, "
            f"single unit only\n\n"
        )
        f.write(f"Matches: {len(kept)}\n")
        f.write(f"Rejected: {len(rejected)}\n\n")
        by_source: dict[str, int] = {}
        for l in kept:
            by_source[l.source] = by_source.get(l.source, 0) + 1
        for src, n in by_source.items():
            f.write(f"  {src}: {n}\n")
    print(f"  Saved → {city_dir}/")


async def main() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    for city in CITIES:
        print(f"\n########## {city.name.upper()} ##########")
        listings = await scrape_city(city)
        kept: list[Listing] = []
        rejected: list[tuple[Listing, list[str]]] = []
        for l in listings:
            ok, reasons = passes(l)
            if ok:
                kept.append(l)
            else:
                rejected.append((l, reasons))
        kept.sort(key=lambda l: (l.price_aud_per_night or 9e9))
        print(f"\n{city.name}: {len(kept)} matches, {len(rejected)} rejected")
        save_city(city, kept, rejected)


if __name__ == "__main__":
    asyncio.run(main())
