"""Agoda scraper."""

from __future__ import annotations

import json
import re
from urllib.parse import urlencode

from playwright.async_api import Page, TimeoutError as PWTimeout

from config import City, MAX_PAGES_PER_SITE
from models import Listing
from scrapers.base import BaseScraper


class AgodaScraper(BaseScraper):
    source = "agoda.com"

    def search_url(self, city: City, page_num: int = 1) -> str:
        params = {
            "city": city.agoda_city_id,
            "checkIn": self.criteria.check_in,
            "checkOut": self.criteria.check_out,
            "adults": self.criteria.adults,
            "rooms": self.criteria.rooms,
            "children": 0,
            "currency": self.criteria.currency,
            "locale": "en-au",
            "selectedproperty": "",
            "hotelTypeId": "31,33,34,29",  # 31=apartment, 33=villa, 34=home, 29=condo
            "page": page_num,
        }
        return "https://www.agoda.com/search?" + urlencode(params)

    async def scrape_city(self, city: City) -> list[Listing]:
        pw, ctx = await self.new_context()
        results: list[Listing] = []
        try:
            page = await ctx.new_page()
            seen_urls: set[str] = set()
            for page_idx in range(1, MAX_PAGES_PER_SITE + 1):
                url = self.search_url(city, page_num=page_idx)
                print(f"  [agoda] {city.name} page {page_idx}: {url}")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                except PWTimeout:
                    continue
                await self._dismiss_modals(page)
                await page.wait_for_timeout(3500)
                # Lazy load
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
            'button[aria-label*="Close"]',
            'button[aria-label*="close"]',
            'button:has-text("Accept")',
            'button:has-text("OK")',
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
            await page.wait_for_selector('li[data-hotelid], [data-selenium="hotel-item"]', timeout=15000)
        except PWTimeout:
            return cards

        # Prefer data-hotelid elements
        elements = await page.locator('li[data-hotelid]').all()
        if not elements:
            elements = await page.locator('[data-selenium="hotel-item"]').all()
        for el in elements:
            try:
                name = ""
                for nsel in ['[data-selenium="hotel-name"]', "h3", "h2"]:
                    try:
                        name = (await el.locator(nsel).first.inner_text(timeout=600)).strip()
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
                    link = "https://www.agoda.com" + link
                price_text = ""
                for psel in [
                    '[data-selenium="display-price"]',
                    '[data-element-name="hotel-card-display-price"]',
                    'span:has-text("A$")',
                ]:
                    try:
                        price_text = await el.locator(psel).first.inner_text(timeout=600)
                        if price_text:
                            break
                    except Exception:
                        continue
                per_night = self.parse_price(price_text)
                total = per_night * nights if per_night else None

                rating = None
                reviews = None
                try:
                    rscore = await el.locator('[data-selenium="hotel-review-score"]').first.inner_text(timeout=500)
                    m = re.search(r"(\d+(?:\.\d+)?)", rscore)
                    if m:
                        rating = float(m.group(1))
                except Exception:
                    pass
                try:
                    rtext = await el.locator('[data-selenium="review-text"], [data-selenium="hotel-review-count"]').first.inner_text(timeout=500)
                    m = re.search(r"(\d[\d,]*)", rtext)
                    if m:
                        reviews = int(m.group(1).replace(",", ""))
                except Exception:
                    pass

                ptype = None
                try:
                    ptype = (await el.locator('[data-selenium="area-city"], [data-selenium="hotel-tag"]').first.inner_text(timeout=500)).strip()
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
                print(f"  [agoda] card parse error: {e}")
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
            # Property type
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
            # Pull JSON-LD for property type fallback
            try:
                ld = await page.locator('script[type="application/ld+json"]').first.inner_text(timeout=800)
                data = json.loads(ld)
                if isinstance(data, dict) and "@type" in data and "property_type" not in out:
                    out["property_type"] = str(data["@type"])
            except Exception:
                pass
        except Exception as e:
            print(f"  [agoda] detail error for {url}: {e}")
        finally:
            await page.close()
        return out

    def _nights(self) -> int:
        from datetime import date
        ci = date.fromisoformat(self.criteria.check_in)
        co = date.fromisoformat(self.criteria.check_out)
        return max((co - ci).days, 1)
