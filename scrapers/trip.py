"""Trip.com scraper."""

from __future__ import annotations

import json
import re
from urllib.parse import urlencode

from playwright.async_api import Page, TimeoutError as PWTimeout

from config import City, MAX_PAGES_PER_SITE
from models import Listing
from scrapers.base import BaseScraper


class TripScraper(BaseScraper):
    source = "trip.com"

    def search_url(self, city: City, page_num: int = 1) -> str:
        params = {
            "city": city.trip_city_id,
            "checkin": self.criteria.check_in.replace("-", "/"),
            "checkout": self.criteria.check_out.replace("-", "/"),
            "adult": self.criteria.adults,
            "children": 0,
            "crn": self.criteria.rooms,
            "curr": self.criteria.currency,
            "locale": "en-AU",
            "searchBoxArg": "t",
            "searchType": "CT",
            "hotelType": "apartment",
            "page": page_num,
        }
        return "https://www.trip.com/hotels/list?" + urlencode(params)

    async def scrape_city(self, city: City) -> list[Listing]:
        pw, ctx = await self.new_context()
        results: list[Listing] = []
        try:
            page = await ctx.new_page()
            seen_urls: set[str] = set()
            for page_idx in range(1, MAX_PAGES_PER_SITE + 1):
                url = self.search_url(city, page_num=page_idx)
                print(f"  [trip] {city.name} page {page_idx}: {url}")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                except PWTimeout:
                    continue
                await self._dismiss_modals(page)
                await page.wait_for_timeout(3500)
                for _ in range(4):
                    await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1200)
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
            'button:has-text("Accept")',
            'button:has-text("OK")',
            '.popup_close',
            '[data-testid="close-button"]',
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=800):
                    await btn.click(timeout=1200)
            except Exception:
                pass

    async def _extract_cards(self, page: Page, city: City) -> list[dict]:
        nights = self._nights()
        cards: list[dict] = []
        try:
            await page.wait_for_selector('.long-list, [data-testid="hotel-list"], .hotel-info, .hotel-card', timeout=15000)
        except PWTimeout:
            pass

        # Trip.com varies; try multiple roots
        selectors = [
            '.long-list .hotel-info',
            '[data-testid="hotel-card"]',
            '.hotel-card',
            'div.hotel_new_list',
        ]
        elements = []
        for sel in selectors:
            elements = await page.locator(sel).all()
            if elements:
                break
        for el in elements:
            try:
                name = ""
                for nsel in ["h2", "h3", '[data-testid="hotel-name"]', '.name', '.hotel-name']:
                    try:
                        name = (await el.locator(nsel).first.inner_text(timeout=500)).strip()
                        if name:
                            break
                    except Exception:
                        continue
                if not name:
                    continue
                link = ""
                try:
                    link = await el.locator("a").first.get_attribute("href")
                except Exception:
                    pass
                if link and link.startswith("/"):
                    link = "https://www.trip.com" + link
                price_text = ""
                for psel in [
                    '.real-price',
                    '[data-testid="price"]',
                    'span:has-text("A$")',
                    '.price',
                ]:
                    try:
                        price_text = await el.locator(psel).first.inner_text(timeout=500)
                        if price_text:
                            break
                    except Exception:
                        continue
                per_night = self.parse_price(price_text)
                total = per_night * nights if per_night else None

                rating = None
                reviews = None
                try:
                    rtxt = await el.locator(".score, .rating-num, [data-testid='score']").first.inner_text(timeout=500)
                    m = re.search(r"(\d+(?:\.\d+)?)", rtxt)
                    if m:
                        rating = float(m.group(1))
                except Exception:
                    pass
                try:
                    rvtxt = await el.locator(".review-num, .review-count").first.inner_text(timeout=500)
                    m = re.search(r"(\d[\d,]*)", rvtxt)
                    if m:
                        reviews = int(m.group(1).replace(",", ""))
                except Exception:
                    pass

                ptype = None
                try:
                    ptype = (await el.locator(".hotel-type, .type-tag").first.inner_text(timeout=500)).strip()
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
                    "address": None,
                })
            except Exception as e:
                print(f"  [trip] card parse error: {e}")
                continue
        return cards

    async def _extract_detail(self, ctx, url: str | None) -> dict:
        out: dict = {}
        if not url:
            return out
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2500)
            text = await page.locator("body").inner_text(timeout=5000)
            m = re.search(r"Property type[:\s]+([A-Za-z &]+)", text)
            if m:
                out["property_type"] = m.group(1).strip().split("\n")[0]
            for label, key in [
                (r"(\d+)\s+bedroom", "bedrooms"),
                (r"(\d+)\s+bed(?!room)", "beds"),
                (r"(\d+)\s+bathroom", "bathrooms"),
                (r"(\d+)\s+guests?", "sleeps"),
                (r"Sleeps\s+(\d+)", "sleeps"),
            ]:
                if key in out:
                    continue
                m = re.search(label, text, re.IGNORECASE)
                if m:
                    out[key] = int(m.group(1))
        except Exception as e:
            print(f"  [trip] detail error for {url}: {e}")
        finally:
            await page.close()
        return out

    def _nights(self) -> int:
        from datetime import date
        ci = date.fromisoformat(self.criteria.check_in)
        co = date.fromisoformat(self.criteria.check_out)
        return max((co - ci).days, 1)
