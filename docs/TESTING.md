# Testing

**664 automated tests**, all passing on SQLite, and run against **MySQL 8.0.46** (mysqlclient 2.3.0), including a fresh database built from the migrations and the demo setup.
Run them with `python manage.py test` (about 50 seconds; a fast password hasher is used only while testing).

## Where the tests are
| Area | Tests | Covers |
|---|---|---|
| `accounts` | 71 | registration with email verification (codes, expiry, attempts, resend, delivery failure), login policy, lockout, password reset and notices, profile, role access |
| `departments` | 58 | master data, constraints, staff profiles, department scoping, seeding |
| `complaints` | 338 | validators, form (compulsory photo, description check against measured example sets, location rules), rejected-submission drafts, location selection, submission, routing, priority rules, SLA, transitions, officer dashboard (filters, search, sort, drill-down, map), assignment, worker flow, resolution, resolution photo (mandatory, stored on the complaint, shown to the citizen), feedback, escalation, duplicates, end-to-end journey |
| `ml_engine` | 53 | preprocessing, dataset import/validation, training, evaluation, prediction, integrity checks |
| `adminpanel` | 76 | dashboard numbers, verification queue and corrections, users, departments/SLA, model and dataset management, audit log |
| `notifications` | 14 | who is told what, notification pages |
| `core` | 39 | error pages, static files, security checklist (access matrix, headers, rate limits, deploy check), location search (providers, caching, limits, signed selections, endpoints) |

## Mapping to the required test list
| Required | Where |
|---|---|
| Valid/invalid login, unauthorized dashboard access, password reset | `accounts/tests/test_login.py`, `test_access_control.py`, `test_password_reset.py` |
| Valid/invalid complaint, missing location, invalid ward, invalid and oversized image | `complaints/tests/test_forms.py`, `test_validators.py`, `test_submission.py` |
| Model loads, prediction works, poor input, metrics generated | `ml_engine/tests/test_pipeline.py`, `test_evaluate.py` |
| Citizen cannot open officer pages; Electricity officer cannot see Water complaints; worker cannot open admin; cannot modify another's complaint | `departments/tests/test_scoping.py`, `complaints/tests/test_officer_access.py`, `test_worker_flow.py`, `adminpanel/tests/test_access.py`, `core/tests_security.py` |
| Description compulsory; photo alone refused | `complaints/tests/test_forms.py` (`CompulsoryDescriptionTests`), `test_submission.py` |
| Resolved impossible without a photo; photo visible to the citizen | `complaints/tests/test_resolution_photo.py`, `test_transitions.py` |
| Submission, AI routing, department, assignment, work, resolution, feedback | `complaints/tests/test_end_to_end.py` (real trained model, real pages), `test_resolution_flow.py`, `test_feedback.py` |

## What the MySQL run found
Running the whole suite on a real MySQL server caught one problem SQLite hid: a decimal confidence stored in a DOUBLE column and
the same number stored inside a JSON column differ in the last digit, so an exact-equality assertion failed. The test now compares
with a tolerance; no application code was affected. All migrations apply cleanly, `check` reports no warnings, and the database
constraints, JSON fields, unique-NULL assignment key and row locking behave as designed.

## Not covered
- Real browsers (the JavaScript for GPS, ward filtering and maps was exercised only through server-rendered pages and manual runs).
- Load and concurrency testing beyond the locking rules.
- Real municipal data: all training data is synthetic.
