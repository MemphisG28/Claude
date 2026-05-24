"""Base scraper: shared Playwright setup, retry, polite delays."""

from __future__ import annotations

import asyncio
import random
import re
from typing import Iterable

from playwright.async_api import BrowserContext, Page, async_playwright

from config import City, SearchCriteria
from models import Listing


USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]


class BaseScraper:
    source: str = "base"

    def __init__(self, criteria: SearchCriteria, headless: bool = True):
        self.criteria = criteria
        self.headless = headless

    async def jitter(self, lo: float = 1.5, hi: float = 3.5) -> None:
        await asyncio.sleep(random.uniform(lo, hi))

    async def new_context(self) -> tuple[object, BrowserContext]:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            locale="en-AU",
            timezone_id="Australia/Sydney",
            viewport={"width": 1440, "height": 900},
            extra_http_headers={"Accept-Language": "en-AU,en;q=0.9"},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        return pw, context

    async def scrape_city(self, city: City) -> list[Listing]:
        raise NotImplementedError

    @staticmethod
    def parse_price(text: str) -> float | None:
        if not text:
            return None
        cleaned = text.replace(",", "").replace("\xa0", " ")
        m = re.search(r"(\d+(?:\.\d+)?)", cleaned)
        return float(m.group(1)) if m else None

    @staticmethod
    def parse_int(text: str) -> int | None:
        if not text:
            return None
        m = re.search(r"(\d+)", text.replace(",", ""))
        return int(m.group(1)) if m else None
