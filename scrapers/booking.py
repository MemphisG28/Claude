"""Booking.com scraper."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urlencode

from playwright.async_api import Page, TimeoutError as PWTimeout

from config import City, MAX_PAGES_PER_SITE
from models import Listing
from scrapers.base import BaseScraper


# Booking.com property type IDs for "single unit" stays
# 201 = apartment, 220 = villa, 213 = condo, 222 = holiday home,
# 219 = aparthotel, 216 = cottage, 224 = chalet, 226 = townhouse
APARTMENT_NFLT = "ht_id%3D201%3Bht_id%3D220%3Bht_id%3D213%3Bht_id%3D222%3Bht_id%3D216%3Bht_id%3D226"


class BookingScraper(BaseScraper):
    source = "booking.com"

    def search_url(self, city: City, offset: int = 0) -> str:
        params = {
            "ss": city.booking_dest,
            "checkin": self.criteria.check_in,
            "checkout": self.criteria.check_out,
            "group_adults": self.criteria.adults,
            "no_rooms": self.criteria.rooms,
            "group_children": 0,
            "selected_currency": self.criteria.currency,
            "lang": "en-au",
            "offset": offset,
        }
        return (
            "https://www.booking.com/searchresults.html?"
            + urlencode(params)
            + f"&nflt={APARTMENT_NFLT}"
        )

    async def scrape_city(self, city: City) -> list[Listing]:
        pw, ctx = await self.new_context()
        results: list[Listing] = []
        try:
            page = await ctx.new_page()
            seen_urls: set[str] = set()
            for page_idx in range(MAX_PAGES_PER_SITE):
                url = self.search_url(city, offset=page_idx * 25)
                print(f"  [booking] {city.name} page {page_idx + 1}: {url}")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                except PWTimeout:
                    print(f"  [booking] timeout loading {url}")
                    continue
                await self._dismiss_modals(page)
                await page.wait_for_timeout(2500)
                cards = await self._extract_cards(page, city)
                new_cards = [c for c in cards if c["url"] not in seen_urls]
                if not new_cards:
                    break
                for c in new_cards:
                    seen_urls.add(c["url"])
                for c in new_cards:
                    detail = await self._extract_detail(ctx, c["url"])
                    listing = Listing(
                        source=self.source,
                        city=city.name,
                        name=c["name"],
                        url=c["url"],
                        price_aud_per_night=c["price_per_night"],
                        total_price_aud=c["total_price"],
                        sleeps=detail.get("sleeps"),
                        bedrooms=detail.get("bedrooms"),
                        beds=detail.get("beds"),
                        bathrooms=detail.get("bathrooms"),
                        property_type=detail.get("property_type") or c.get("property_type"),
                        rating=c.get("rating"),
                        review_count=c.get("reviews"),
                        address=c.get("address"),
                        raw={"card": c, "detail": detail},
                    )
                    results.append(listing)
                    await self.jitter(0.6, 1.4)
                await self.jitter()
        finally:
            await ctx.close()
            await pw.stop()
        return results

    async def _dismiss_modals(self, page: Page) -> None:
        for sel in [
            'button[aria-label="Dismiss sign-in info."]',
            'button[aria-label*="Dismiss"]',
            '#onetrust-accept-btn-handler',
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1000):
                    await btn.click(timeout=1500)
            except Exception:
                pass

    async def _extract_cards(self, page: Page, city: City) -> list[dict]:
        nights = self._nights()
        cards = []
        try:
            await page.wait_for_selector('[data-testid="property-card"]', timeout=15000)
        except PWTimeout:
            return cards

        elements = await page.locator('[data-testid="property-card"]').all()
        for el in elements:
            try:
                name = (await el.locator('[data-testid="title"]').first.inner_text()).strip()
                link = await el.locator('a[data-testid="title-link"]').first.get_attribute("href")
                if link and link.startswith("/"):
                    link = "https://www.booking.com" + link
                price_text = ""
                for psel in [
                    '[data-testid="price-and-discounted-price"]',
                    '[data-testid="price-for-x-nights"]',
                ]:
                    try:
                        price_text = await el.locator(psel).first.inner_text(timeout=1000)
                        if price_text:
                            break
                    except Exception:
                        continue
                total = self.parse_price(price_text)
                per_night = (total / nights) if total else None

                rating = None
                reviews = None
                try:
                    rating_txt = await el.locator('[data-testid="review-score"]').first.inner_text(timeout=500)
                    m = re.search(r"(\d+(?:\.\d+)?)", rating_txt)
                    if m:
                        rating = float(m.group(1))
                    rev = re.search(r"(\d[\d,]*)\s+reviews", rating_txt)
                    if rev:
                        reviews = int(rev.group(1).replace(",", ""))
                except Exception:
                    pass

                ptype = None
                try:
                    ptype = (await el.locator('[data-testid="property-type-badge"]').first.inner_text(timeout=500)).strip()
                except Exception:
                    pass

                address = None
                try:
                    address = (await el.locator('[data-testid="address"]').first.inner_text(timeout=500)).strip()
                except Exception:
                    pass

                cards.append({
                    "name": name,
                    "url": link,
                    "price_per_night": per_night,
                    "total_price": total,
                    "rating": rating,
                    "reviews": reviews,
                    "property_type": ptype,
                    "address": address,
                })
            except Exception as e:
                print(f"  [booking] card parse error: {e}")
                continue
        return cards

    async def _extract_detail(self, ctx, url: str | None) -> dict:
        out: dict = {}
        if not url:
            return out
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2000)
            body = await page.content()
            # Property type heuristic
            m = re.search(r'"accommodation_type_name":"([^"]+)"', body)
            if m:
                out["property_type"] = m.group(1)
            # Beds / bedrooms / bathrooms from layout text
            text = await page.locator("body").inner_text(timeout=5000)
            for label, key in [
                (r"(\d+)\s+bedroom", "bedrooms"),
                (r"(\d+)\s+bed(?!room)", "beds"),
                (r"(\d+)\s+bathroom", "bathrooms"),
                (r"Sleeps\s+(\d+)", "sleeps"),
                (r"(\d+)\s+guests?", "sleeps"),
            ]:
                if key in out:
                    continue
                m = re.search(label, text, re.IGNORECASE)
                if m:
                    out[key] = int(m.group(1))
        except Exception as e:
            print(f"  [booking] detail error for {url}: {e}")
        finally:
            await page.close()
        return out

    def _nights(self) -> int:
        from datetime import date
        ci = date.fromisoformat(self.criteria.check_in)
        co = date.fromisoformat(self.criteria.check_out)
        return max((co - ci).days, 1)
