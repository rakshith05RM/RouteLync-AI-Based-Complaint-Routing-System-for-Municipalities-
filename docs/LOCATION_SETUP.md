# Location search and map selection

## How it works
The complaint form has a search box, a map with a draggable pin, and the "Use my current location" button. All of them feed one place in
the page, so the pin, the coordinates, the address and a **signed token** always describe the same place:

1. The browser asks RouteLync (`/geo/search/?q=...` or `/geo/reverse/?lat=..&lng=..`), never a third-party address directly.
2. RouteLync asks the configured geocoder (server side, with timeout, caching and per-person rate limit), marks each result as
   Bengaluru Urban/Rural, outside the service area, or unverified, and signs each result. Outside results are not hidden.
3. The form submits the coordinates plus the token. The server refuses a token that is forged, expired (2 hours), issued to someone else,
   or paired with different coordinates than the ones submitted.
4. A pin placed by hand or GPS is reverse-geocoded. Its marker stays visible even when the location is outside the service area or cannot
   be verified; submission is refused unless the signed selection confirms Bengaluru Urban or Bengaluru Rural. Nothing is replaced by a
   default city.

The place-search field and complete address are required. Area, ward, street, landmark and building are optional. The geocoder fills
available address details; wards are not inferred without official ward boundary data. The Area field offers Bengaluru Urban's five
corporations and Bengaluru Rural's four taluks, along with existing urban locality records. The chosen area must belong to the verified
service district.

Ward is a numeric text input with suggestions from existing ward records for the selected area. Suggestions are partial demo data, not
an official ward schedule. Citizens can type another ward number; a new number is recorded under the selected area when the complaint is
submitted. A rejected draft preserves the entered number without creating a ward record.

The complaint stores `latitude`, `longitude`, `formatted_address`, `place_id` and `location_source` (SEARCH, MAP or GPS).
The device location is requested only when the person presses the button and the browser allows it; nothing is tracked.

## Providers (`.env`)
| Variable | Meaning |
|---|---|
| `GEOCODER_PROVIDER` | `photon` (default; designed for search-as-you-type) or `nominatim` |
| `GEOCODER_BASE_URL` | empty = the provider's public server. Set your own server or a commercial one |
| `GEOCODER_API_KEY` | optional, sent only by the server, never to the browser |
| `GEOCODER_CONTACT_EMAIL`, `GEOCODER_USER_AGENT` | identify your application (Nominatim's policy asks for this) |
| `LOCATION_MAP_BOUNDS` | Initial map viewport `min_lat,min_lon,max_lat,max_lon`; this is for display only, not service eligibility |
| `LOCATION_TILE_URL`, `LOCATION_TILE_ATTRIBUTION`, `LOCATION_TILE_CSP_SOURCE` | Basemap tile URL pattern, required attribution, and allowed CSP image source; default is Esri World Street Map |

`SERVICE_AREA_BBOX` and `LOCATION_COORDINATES_REQUIRED` in older `.env` files are no longer used; district verification controls
eligibility, and a verified location is required.

**Usage limits you must respect.** The free public servers are for light use: OpenStreetMap's public Nominatim server **does not allow
autocomplete** and heavy use, and the public Photon server is fair-use only. For a demonstration with a few people they are fine; for real
traffic run your own instance or use a commercial service that speaks the same API (for example LocationIQ with its Nominatim-compatible
URL and key). The map uses Esri World Street Map tiles by default; the Esri endpoint was verified to return image tiles without an API
key. Configure a licensed provider and its required attribution for production traffic. If you configure a different tile host, set
`LOCATION_TILE_CSP_SOURCE` to that provider's origin as well. The GPS button requests
standard (not high-accuracy) browser location so laptops can use Wi-Fi/network positioning when they have no GPS receiver. Browsers
require HTTPS or localhost; desktop access may also require enabling browser site permission and Windows Location services.

## Privacy (mention in the report)
What the citizen types in the search box, and the coordinates they select, are sent from the server to the geocoding provider. The browser
itself never contacts the provider. Do not add a provider you are not allowed to send citizens' search text to.

## Known limits
- **Coverage depends on district or taluk metadata returned by the geocoder.** Known Bengaluru Urban/Rural taluks are mapped to their
  districts; unknown names are blocked, even when coordinates appear to be in Bengaluru. Verify Photon/Nominatim responses before production use.
- **Ward is not found automatically.** The wards in this project are sample data without map boundaries. Suggestions use records already
  in the database; new typed numbers can be saved but are not verified against an official schedule. Load the current official ward and
  Gram Panchayat ward schedule before treating these entries as authoritative, and add point-in-polygon lookup if automatic assignment
  is needed.
- Search quality and address detail coverage are the provider's, not RouteLync's.
- Geolocation in browsers works only on HTTPS or `localhost`.


## Bengaluru service districts
The complaint form accepts only geocoder results identified as Bengaluru Urban or Bengaluru Rural. The map viewport does not enforce
coverage. If the geocoder returns another district name, the place is kept visible but cannot be submitted until a supported place is
selected and verified.
