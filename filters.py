"""Apply the user's filtering criteria to scraped listings."""

from config import CRITERIA
from models import Listing


SINGLE_UNIT_TYPES = {
    "apartment",
    "apartments",
    "condo",
    "condominium",
    "serviced apartment",
    "entire apartment",
    "entire home",
    "entire place",
    "villa",
    "house",
    "vacation home",
    "holiday home",
    "studio",
    "loft",
    "townhouse",
    "cottage",
    "bungalow",
}

EXCLUDE_TYPES = {
    "hotel",
    "hostel",
    "guesthouse",
    "guest house",
    "resort",
    "motel",
    "ryokan",
    "bed and breakfast",
    "b&b",
    "capsule",
    "inn",
}


def is_single_unit(property_type: str | None) -> bool:
    """Reject hotel-style listings where '2 rooms' means two separate units."""
    if not property_type:
        return False
    pt = property_type.lower()
    if any(bad in pt for bad in EXCLUDE_TYPES):
        return False
    return any(good in pt for good in SINGLE_UNIT_TYPES)


def passes(listing: Listing) -> tuple[bool, list[str]]:
    """Return (passes, reasons_failed)."""
    fails: list[str] = []

    if listing.price_aud_per_night is None:
        fails.append("price unknown")
    elif listing.price_aud_per_night > CRITERIA.max_price_aud_per_night:
        fails.append(
            f"price ${listing.price_aud_per_night:.0f} > "
            f"${CRITERIA.max_price_aud_per_night:.0f}"
        )

    if listing.sleeps is not None and listing.sleeps < CRITERIA.adults:
        fails.append(f"sleeps {listing.sleeps} < {CRITERIA.adults}")

    if listing.beds is not None and listing.beds < CRITERIA.min_beds:
        fails.append(f"beds {listing.beds} < {CRITERIA.min_beds}")

    if listing.bathrooms is not None and listing.bathrooms < CRITERIA.min_bathrooms:
        fails.append(f"baths {listing.bathrooms} < {CRITERIA.min_bathrooms}")

    if not is_single_unit(listing.property_type):
        fails.append(f"not single unit (type={listing.property_type!r})")

    return (len(fails) == 0, fails)
