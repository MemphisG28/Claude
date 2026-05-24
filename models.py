"""Data model for a single accommodation listing."""

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Listing:
    source: str
    city: str
    name: str
    url: str
    price_aud_per_night: Optional[float]
    total_price_aud: Optional[float]
    sleeps: Optional[int]
    bedrooms: Optional[int]
    beds: Optional[int]
    bathrooms: Optional[int]
    property_type: Optional[str]
    rating: Optional[float]
    review_count: Optional[int]
    address: Optional[str]
    raw: dict

    def to_dict(self) -> dict:
        return asdict(self)
