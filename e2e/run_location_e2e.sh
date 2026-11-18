#!/bin/bash
# Browser test of the complaint-form location picker. Needs Python (this project), Node 18+ and `npm install` in this folder.
# It starts a local STAND-IN for the geocoder, starts the website on a throw-away SQLite database, drives a headless browser,
# and stops everything. It does NOT contact any real geocoding service.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$HERE")"
cd "$ROOT"
export DJANGO_DEBUG=True DB_ENGINE=sqlite DJANGO_SECRET_KEY=e2e-only-key-not-for-production-use-0123456789abcdef
rm -f db.sqlite3
python3 manage.py migrate -v0 && python3 manage.py seed_master_data --demo-users --password "Demo-Pass#12345" >/dev/null
python3 "$HERE/stub_photon.py" 8765 >/dev/null 2>&1 & STUB=$!
GEOCODER_PROVIDER=photon GEOCODER_BASE_URL=http://127.0.0.1:8765 python3 manage.py runserver 127.0.0.1:8123 --noreload >/dev/null 2>&1 & SERVER=$!
for i in $(seq 1 30); do curl -s -o /dev/null http://127.0.0.1:8123/accounts/login/ && break; sleep 1; done
(cd "$HERE" && node run.mjs); STATUS=$?
kill $STUB $SERVER 2>/dev/null; rm -f db.sqlite3
exit $STATUS
