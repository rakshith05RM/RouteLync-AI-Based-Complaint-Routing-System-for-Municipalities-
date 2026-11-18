"""
Talking to a geocoding service and turning its answer into one common shape. Nothing here is user-controlled except
the search text, which is URL-encoded; the server address always comes from settings (no request forgery).
"""
import json
import logging
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger("routelync")
MAX_BYTES = 1_000_000
DEFAULT_URLS = {"photon": "https://photon.komoot.io", "nominatim": "https://nominatim.openstreetmap.org"}


class GeocoderError(Exception):
    """kind: "unavailable" (down, timeout), "rate_limited", or "bad_response"."""

    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}")
        self.kind = kind


def parse_bbox(text=None):
    """(min_lat, min_lon, max_lat, max_lon) or None."""
    text = settings.LOCATION_MAP_BOUNDS if text is None else text
    if not text or not text.strip():
        return None
    try:
        a, b, c, d = (float(x) for x in text.split(","))
    except ValueError:
        logger.error("LOCATION_MAP_BOUNDS is not 'min_lat,min_lon,max_lat,max_lon': %r", text)
        return None
    return (min(a, c), min(b, d), max(a, c), max(b, d))


def service_area_for_district(district):
    """Return the supported district name, or None for unknown/out-of-service districts."""
    normalized = re.sub(r"\s+(district|taluk|taluka|taluku)$", "", " ".join((district or "").lower().split()))
    normalized = normalized.replace("bangalore", "bengaluru")
    if normalized in ("bengaluru urban", "bengaluru rural"):
        return "Bengaluru Urban" if normalized.endswith("urban") else "Bengaluru Rural"
    if normalized in {"bengaluru north", "bengaluru south", "bengaluru east", "yelahanka", "anekal"}:
        return "Bengaluru Urban"
    if normalized in {"doddaballapura", "devanahalli", "nelamangala", "hoskote", "hosakote"}:
        return "Bengaluru Rural"
    return None


def inside_area(lat, lng, district="") -> bool:
    """Check that the coordinates are valid and the geocoder identified a supported district."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    return (-90 <= lat <= 90 and -180 <= lng <= 180
            and service_area_for_district(district) is not None)


def _get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": settings.GEOCODER_USER_AGENT, "Accept": "application/json",
                                                   "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(request, timeout=settings.GEOCODER_TIMEOUT) as response:      # noqa: S310 - fixed https base
            raw = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise GeocoderError("rate_limited" if exc.code == 429 else "unavailable", f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
        raise GeocoderError("unavailable", exc.__class__.__name__) from exc
    if len(raw) > MAX_BYTES:
        raise GeocoderError("bad_response", "too large")
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise GeocoderError("bad_response", "not JSON") from exc


def _base():
    return (settings.GEOCODER_BASE_URL or DEFAULT_URLS.get(settings.GEOCODER_PROVIDER, DEFAULT_URLS["photon"])).rstrip("/")


def _label(*parts):
    out = []
    for part in parts:
        part = (part or "").strip()
        if part and (not out or part.lower() != out[-1].lower()):
            out.append(part)
    return ", ".join(out)


def _record(provider, ident, lat, lng, name, street, area_hint, city, state="", house="", district=""):
    street_full = f"{house} {street}".strip() if house and street else street
    return {"id": f"{provider}:{ident}", "name": name or "", "street": street or "", "area_hint": area_hint or "", "city": city or "",
            "district": district or "", "label": _label(name, street_full, area_hint, city, district, state),
            "lat": round(float(lat), 6), "lng": round(float(lng), 6)}


# ------------------------------------------------------------------------------------------------ Photon
def _photon_record(feature):
    try:
        lng, lat = feature["geometry"]["coordinates"][:2]
        p = feature.get("properties", {})
        name = p.get("name", "")
        if name and name == p.get("street"):
            name = ""
        return _record("photon", f"{p.get('osm_type', '')}{p.get('osm_id', '')}", lat, lng, name, p.get("street", ""),
                       p.get("district") or p.get("locality") or p.get("suburb") or "", p.get("city") or p.get("county") or "",
                       p.get("state", ""), p.get("housenumber", ""),
                       p.get("state_district") or p.get("county") or "")
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def _photon_search(query, bbox):
    params = {"q": query, "limit": 8, "lang": "en"}
    if bbox:
        params["bbox"] = f"{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}"
    data = _get_json(f"{_base()}/api/?{urllib.parse.urlencode(params)}")
    if not isinstance(data, dict) or not isinstance(data.get("features"), list):
        raise GeocoderError("bad_response", "unexpected shape")
    return [r for r in map(_photon_record, data["features"]) if r]


def _photon_reverse(lat, lng):
    data = _get_json(f"{_base()}/reverse?{urllib.parse.urlencode({'lat': lat, 'lon': lng, 'lang': 'en'})}")
    if not isinstance(data, dict) or not isinstance(data.get("features"), list):
        raise GeocoderError("bad_response", "unexpected shape")
    records = [r for r in map(_photon_record, data["features"]) if r]
    return records[0] if records else None


# --------------------------------------------------------------------------------------------- Nominatim
def _nominatim_record(item):
    try:
        a = item.get("address", {}) or {}
        street = a.get("road") or a.get("pedestrian") or a.get("footway") or ""
        area = a.get("suburb") or a.get("neighbourhood") or a.get("city_district") or a.get("quarter") or ""
        city = a.get("city") or a.get("town") or a.get("village") or ""
        district = a.get("state_district") or a.get("district") or a.get("county") or ""
        name = item.get("name") or ""
        if name in (street, area, city):
            name = ""
        return _record("nominatim", item["place_id"], item["lat"], item["lon"], name, street, area, city,
                       a.get("state", ""), a.get("house_number", ""), district)
    except (KeyError, TypeError, ValueError):
        return None


def _nominatim_params(extra):
    params = {"format": "jsonv2", "addressdetails": 1, **extra}
    if settings.GEOCODER_API_KEY:
        params["key"] = settings.GEOCODER_API_KEY
    if settings.GEOCODER_CONTACT_EMAIL:
        params["email"] = settings.GEOCODER_CONTACT_EMAIL
    return urllib.parse.urlencode(params)


def _nominatim_search(query, bbox):
    extra = {"q": query, "limit": 8}
    if bbox:
        extra.update(viewbox=f"{bbox[1]},{bbox[2]},{bbox[3]},{bbox[0]}", bounded=1)
    data = _get_json(f"{_base()}/search?{_nominatim_params(extra)}")
    if not isinstance(data, list):
        raise GeocoderError("bad_response", "unexpected shape")
    return [r for r in map(_nominatim_record, data) if r]


def _nominatim_reverse(lat, lng):
    data = _get_json(f"{_base()}/reverse?{_nominatim_params({'lat': lat, 'lon': lng})}")
    if not isinstance(data, dict) or data.get("error"):
        return None
    return _nominatim_record(data)


PROVIDERS = {"photon": (_photon_search, _photon_reverse), "nominatim": (_nominatim_search, _nominatim_reverse)}


def provider_functions():
    try:
        return PROVIDERS[settings.GEOCODER_PROVIDER]
    except KeyError:
        raise GeocoderError("unavailable", f"unknown provider {settings.GEOCODER_PROVIDER!r}")
