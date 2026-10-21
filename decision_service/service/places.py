"""Google Places (New) lookups for option overviews.

Places content may only be cached briefly; the place ID may be stored. Callers keep
place IDs in option identity and fetch display content live through this module.
"""
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from decision_service.deadlines import remaining_timeout

BASE = "https://places.googleapis.com/v1"
PLACE_ID = re.compile(r"^[A-Za-z0-9_-]{10,300}$")
PHOTO_NAME = re.compile(r"^places/[A-Za-z0-9_-]{10,300}/photos/[A-Za-z0-9_-]{10,1000}$")
# Types that identify a region rather than a visitable venue.
REGION_TYPES = {"country", "administrative_area_level_1", "administrative_area_level_2", "locality", "colloquial_area", "continent"}
DETAIL_FIELDS = ",".join((
    "id", "displayName", "formattedAddress", "types", "primaryTypeDisplayName", "rating", "userRatingCount",
    "priceLevel", "priceRange", "websiteUri", "googleMapsUri", "editorialSummary", "reviewSummary", "photos",
    "regularOpeningHours.weekdayDescriptions",
))
PRICE = {"PRICE_LEVEL_FREE": 0, "PRICE_LEVEL_INEXPENSIVE": 1, "PRICE_LEVEL_MODERATE": 2, "PRICE_LEVEL_EXPENSIVE": 3, "PRICE_LEVEL_VERY_EXPENSIVE": 4}


class PlacesUnavailable(Exception):
    pass


class PlacesClient:
    def __init__(self, api_key=None, *, timeout=8):
        self.api_key = api_key or os.environ.get("GOOGLE_PLACES_API_KEY", "")
        self.timeout = timeout
        if not self.api_key:
            raise ValueError("GOOGLE_PLACES_API_KEY is required for place lookups")

    def _call(self, method, path, *, body=None, fields=None, raw=False):
        headers = {"x-goog-api-key": self.api_key}
        if fields:
            headers["x-goog-fieldmask"] = fields
        data = None
        if body is not None:
            headers["content-type"] = "application/json"
            data = json.dumps(body).encode()
        try:
            with urlopen(Request(BASE + path, data=data, headers=headers, method=method), timeout=remaining_timeout(self.timeout)) as response:
                payload = response.read(8_000_001)
                if len(payload) > 8_000_000:
                    raise ValueError("Oversized Places response")
                return (payload, response.headers.get("content-type", "")) if raw else json.loads(payload)
        except HTTPError as error:
            raise PlacesUnavailable(f"PLACES_HTTP_{error.code}") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise PlacesUnavailable("PLACES_UNAVAILABLE") from None

    def find(self, query, *, region=""):
        """Best text match for an option name, or None."""
        text = f"{query}, {region}" if region and region.casefold() not in query.casefold() else query
        result = self._call("POST", "/places:searchText", body={"textQuery": text[:300], "pageSize": 1},
                            fields="places.id,places.displayName,places.types,places.formattedAddress")
        places = result.get("places") or []
        return places[0] if places else None

    def details(self, place_id):
        if not PLACE_ID.fullmatch(place_id or ""):
            raise PlacesUnavailable("INVALID_PLACE_ID")
        return self._call("GET", f"/places/{quote(place_id)}", fields=DETAIL_FIELDS)

    def photo(self, name, *, width=800):
        if not PHOTO_NAME.fullmatch(name or ""):
            raise PlacesUnavailable("INVALID_PHOTO")
        return self._call("GET", f"/{name}/media?maxWidthPx={max(200, min(width, 1600))}", raw=True)


def is_region(place):
    return bool(REGION_TYPES & set(place.get("types") or []))


def overview(place):
    """Display-only summary; never frozen into a decision snapshot."""
    def text(value):
        return value.get("text", "") if isinstance(value, dict) else ""
    reviews = place.get("reviewSummary") or {}
    photos = []
    for photo in (place.get("photos") or [])[:4]:
        authors = [{"name": a.get("displayName", ""), "uri": a.get("uri", "")} for a in photo.get("authorAttributions") or []]
        if PHOTO_NAME.fullmatch(photo.get("name", "")):
            photos.append({"name": photo["name"], "attributions": authors})
    return {
        "source": "google_places", "place_id": place.get("id"), "name": text(place.get("displayName")),
        "address": place.get("formattedAddress", ""), "kind_label": text(place.get("primaryTypeDisplayName")),
        "rating": place.get("rating"), "rating_count": place.get("userRatingCount"),
        "price_level": PRICE.get(place.get("priceLevel")), "website": place.get("websiteUri", ""),
        "maps_url": place.get("googleMapsUri", ""), "summary": text(place.get("editorialSummary")),
        "review_summary": text(reviews.get("text")),
        "review_disclosure": text(reviews.get("disclosureText")),
        "opening_hours": (place.get("regularOpeningHours") or {}).get("weekdayDescriptions", [])[:7],
        "photos": photos,
    }
