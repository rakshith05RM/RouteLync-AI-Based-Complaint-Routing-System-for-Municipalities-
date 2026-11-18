"""Search and reverse-lookup with caching, service-area status and signed results."""
import hashlib
import logging

from django.conf import settings
from django.core import signing
from django.core.cache import cache

from . import providers
from .providers import GeocoderError, service_area_for_district

logger = logging.getLogger("routelync")
SALT = "routelync.location"
TOKEN_MAX_AGE = 2 * 60 * 60
MIN_QUERY = 3
MAX_QUERY = 120


def sign_selection(user_id, lat, lng, place_id="", label="", source="SEARCH", *, district="", area_hint="") -> str:
    """Binds an address (or nothing) to coordinates. The complaint form refuses a pairing this server did not issue."""
    service_area = service_area_for_district(district)
    status = "available" if service_area else "unavailable" if district else "unknown"
    return signing.dumps({"u": user_id, "lat": f"{float(lat):.6f}", "lng": f"{float(lng):.6f}", "id": place_id,
                          "label": label[:300], "src": source, "district": district[:100], "area_hint": area_hint[:100],
                          "service_area": service_area or "", "service_area_status": status},
                         salt=SALT, compress=True)


def read_selection(token, user_id):
    """The payload, or None if the token is forged, expired, or was issued to somebody else."""
    try:
        payload = signing.loads(token, salt=SALT, max_age=TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None
    return payload if payload.get("u") == user_id else None


def _cached(key_parts, fetch):
    key = "geo:" + hashlib.sha256("|".join(map(str, key_parts)).encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return hit
    value = fetch()
    cache.set(key, value, settings.GEOCODER_CACHE_SECONDS)       # failures raise before this line and are never cached
    return value


def search_places(query: str, user_id: int):
    query = " ".join((query or "").split())[:MAX_QUERY]
    if len(query) < MIN_QUERY:
        raise ValueError(f"Type at least {MIN_QUERY} characters.")
    search, _ = providers.provider_functions()
    found = _cached(("search", settings.GEOCODER_PROVIDER, settings.GEOCODER_BASE_URL, query.lower()),
                    lambda: search(query, None))
    for result in found:
        district = result["district"]
        if not district:
            district = next((candidate for candidate in (result["name"], result["city"], result["area_hint"])
                             if service_area_for_district(candidate)), "")
            result["district"] = district
        result["service_area"] = service_area_for_district(district) or ""
        result["service_area_status"] = ("available" if result["service_area"] else
                                         "unavailable" if result["district"] else "unknown")
        result["token"] = sign_selection(user_id, result["lat"], result["lng"], result["id"], result["label"], "SEARCH",
                                         district=district, area_hint=result["area_hint"])
    return found


def reverse_place(lat: float, lng: float, user_id: int):
    """The address and service status at a point, or None if the provider knows no address."""
    _, reverse = providers.provider_functions()
    key = (round(lat, 5), round(lng, 5))
    found = _cached(("reverse", settings.GEOCODER_PROVIDER, settings.GEOCODER_BASE_URL, *key), lambda: reverse(*key) or {})
    if not found:
        return None
    service_area = service_area_for_district(found["district"])
    status = "available" if service_area else "unavailable" if found["district"] else "unknown"
    return {**found, "service_area": service_area or "", "service_area_status": status,
            "token": sign_selection(user_id, lat, lng, found["id"], found["label"], "MAP",
                                    district=found["district"], area_hint=found["area_hint"])}
