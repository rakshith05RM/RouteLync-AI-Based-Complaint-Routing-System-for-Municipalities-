# Changes: email verification, photo, description check, rejected submissions, location search

## Baseline before the changes
489 automated tests passing. Email used the development console backend (printed in the terminal; nothing reached an inbox), registration
signed people in without checking their email, the complaint photo was optional, the description was checked for length and gibberish only,
and there was no address search (a GPS button stored raw coordinates).

## What changed, by phase of the brief
| Phase | Change | Main files |
|---|---|---|
| 1 Email | Accounts start unverified; 6-digit code by email (hashed, expiring, one-use, attempt limit, resend cooldown/cap); login refused until verified; same page for existing addresses; reset email, single-use link, "password changed" notice; failures reported honestly; `send_test_email`; deploy check for real email | `accounts/otp.py`, `registration.py`, `emails.py`, `views.py`, `core/checks.py` |
| 2 Photo | Photo required in the form and in `submit_complaint`; the administrator page shows it; old complaints without photos still work | `complaints/forms.py`, `services/submission.py` |
| 3 Description | Server-side municipal-issue check with five outcomes (accepted, accepted-for-review, unclear, nonsense, unsupported, too short); a good title cannot rescue an empty description | `complaints/municipal_terms.py`, `services/description_check.py` |
| 4 Not submitted | Rejected submissions kept as drafts (text and photo), shown under "Not submitted" on the citizen's page with the reason, edit/resubmit, remove; never a complaint, never counted; double submit creates one complaint | `models/attempts.py`, `services/attempts.py`, `views/citizen.py` |
| 5 Location | Search with dropdown (real geocoder through the server), draggable pin, reverse lookup, GPS to address; coordinates required and inside the service area; address and pin bound by a signed token; stored place id and address | `core/geo/`, `static/js/location_picker.js`, `forms.py` |

## Upgrade notes
Run `python manage.py migrate`. Existing user accounts are marked verified by the migration, so nobody is locked out. Existing complaints are untouched.
New variables are listed in `.env.example`.

## Measured results (small hand-written sets; indicative only)
Description check: before widening its vocabulary it wrongly rejected 3 of 30 fresh valid complaints (10%) and 18 of the 64 independent
challenge-set complaints (28%), and accepted none of 18 junk examples. After widening, on a second fresh set it wrongly rejected 1 of 20 (5%)
and accepted none of 10 junk examples. The final tuned sets show no errors; that shows the rules still work, not that they generalise.

## Bugs found by testing (and fixed)
- The demo and seed accounts were not marked verified, so the new rule blocked them (found by the browser test).
- A tap on a search result on a touch screen also hit the map beneath it (found by the browser test).
- The geocoder address lost a trailing slash only when overridden in settings.
- Django's own password-reset form swallows email errors and then claims success; it is replaced by one that reports the failure.
- Keyboard-mash text of only two words was reported as "too short" instead of "not a municipal issue".

## Decisions that differ from, or go beyond, the brief
- **The description check uses rules and a visible vocabulary, not an external AI service.** It is explainable and free, but it is
  English-oriented; local-language text is accepted and routed to a person rather than judged.
- **The ward is not detected from the map** (no ward boundary data); the citizen chooses it.
- **A short complaint is accepted if it names a real problem** ("Large pothole near the school gate"); the word minimum is only one signal.
- A reset link also counts as proof of email ownership and verifies a pending account.
- Registering an address that already has an account never reveals it on screen (the owner is told by email).

## Tested and not tested
Tested automatically: everything above, with a test email backend, mocked SMTP failures and stand-in geocoder responses, plus a real headless-browser
run of the location picker against a local stand-in geocoder (`e2e/`). **Not tested from this environment:** delivery to a real inbox, and the real geocoding
services. Follow `docs/MANUAL_TESTS.md` for those.
