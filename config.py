"""Search parameters for the accommodation scraper."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SearchCriteria:
    check_in: str = "2026-12-01"
    check_out: str = "2026-12-13"
    adults: int = 4
    rooms: int = 1
    min_beds: int = 2
    min_bathrooms: int = 2
    max_price_aud_per_night: float = 350.0
    currency: str = "AUD"


@dataclass(frozen=True)
class City:
    name: str
    slug: str
    booking_dest: str
    agoda_city_id: str
    trip_city_id: str


CITIES: list[City] = [
    City(
        name="Beijing",
        slug="beijing",
        booking_dest="Beijing",
        agoda_city_id="8401",
        trip_city_id="1",
    ),
    City(
        name="Shanghai",
        slug="shanghai",
        booking_dest="Shanghai",
        agoda_city_id="9395",
        trip_city_id="2",
    ),
    City(
        name="Zhangjiajie",
        slug="zhangjiajie",
        booking_dest="Zhangjiajie",
        agoda_city_id="32925",
        trip_city_id="775",
    ),
]

CRITERIA = SearchCriteria()
RESULTS_DIR = "results"
MAX_PAGES_PER_SITE = 5
HEADLESS = True
