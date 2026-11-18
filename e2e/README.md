# Browser test for the location picker

Checks, in a real headless browser against the running site: search with a dropdown and debounce, keyboard use, provider
errors, tapping and dragging the map pin, current location, the touch screen, refusing a submission without a location,
the final saved coordinates, and that no JavaScript error or Content-Security-Policy violation occurs.

```bash
cd e2e && npm install          # once
./run_location_e2e.sh          # Linux, macOS, or Git Bash / WSL on Windows
```
Set `CHROME_PATH` to your Chrome or Edge executable to use it (the bundled Chromium works on Linux only).
The geocoder is a local stand-in (`stub_photon.py`), so this proves RouteLync's own code, not the real service
(see `docs/MANUAL_TESTS.md` for that).
