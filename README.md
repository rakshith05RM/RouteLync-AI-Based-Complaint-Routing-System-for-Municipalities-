# RouteLync: Smart Complaint Routing Platform

A municipal grievance system covering **17 departments** (see `docs/CHANGES_17_DEPARTMENTS.md`). Citizens report a problem with a structured location; NLP and a Multinomial Naive Bayes
classifier route it to the right department; officers, field workers and administrators handle it through one website with
role-based access, SLA monitoring, escalation, notifications, analytics and an audit log.

Stack: Python, Django 5.2, MySQL 8, scikit-learn, NLTK, Bootstrap 5, Leaflet maps (Esri tiles by default), and Photon location search (Nominatim is also supported).

## Setup
```bash
python -m venv venv
venv\Scripts\activate                 # Windows   (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt       # if mysqlclient fails on Windows, see routelync/__init__.py (PyMySQL option)
copy .env.example .env                # Linux/macOS: cp .env.example .env, then edit the values
```
Generate a secret key: `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"`

MySQL (run as root, for example in MySQL Workbench):
```sql
CREATE DATABASE routelync_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'routelync_user'@'localhost' IDENTIFIED BY 'your-strong-password';
GRANT ALL PRIVILEGES ON routelync_db.* TO 'routelync_user'@'localhost';
GRANT ALL PRIVILEGES ON test_routelync_db.* TO 'routelync_user'@'localhost';   -- Django's test database
FLUSH PRIVILEGES;
```
For a quick check without MySQL set `DB_ENGINE=sqlite` in `.env`.

## Local files and data
Copy `.env.example` to `.env` and put real local settings only in `.env`. Keep `.env`, `staff_credentials.csv`, `datasets/`, `media/`,
`logs/`, and `db.sqlite3` out of Git. Dataset CSVs are not included in the repository; provide your own labelled CSV when
importing, training, or evaluating the model. Never commit real citizen or staff data.

## Email and location search (set these up for real use)
Out of the box emails are only **printed in the terminal** (development mode), and address search uses the public OpenStreetMap-based
services. See `docs/EMAIL_SETUP.md` (SMTP setup and `python manage.py send_test_email you@example.com`) and `docs/LOCATION_SETUP.md`
(providers, service area, usage limits). Manual tests that need the real world are in `docs/MANUAL_TESTS.md`.

## Run the demonstration
```bash
python manage.py migrate
python manage.py setup_demo --password "choose-a-password"     # development only
python manage.py runserver
```
Then follow `docs/DEMO_SCRIPT.md` (13-step scenario with accounts and exact inputs).
`python manage.py runserver` prints separate **Laptop URL** and **Phone URL** addresses for local development.
The phone must be on the same Wi-Fi; allow the server through Windows Firewall on private networks if prompted.
See `docs/EMAIL_SETUP.md` for details.

## Department and administrator logins
`python manage.py setup_staff_accounts --admin-email <email> --admin-password "<password>" --csv staff_credentials.csv` creates, for every
department, an officer, a head and two workers (`electricityofficer1@company.com` / `electricityofficer1@company` ...) and the
administrator, and renames any old demo accounts in place. The CSV contains generated login credentials: keep it private and do not
commit it. See `docs/STAFF_ACCOUNTS.md`.

## Everyday commands
| Command | Purpose |
|---|---|
| `python manage.py test` | 664 tests (SQLite or MySQL) |
| `python manage.py seed_master_data [--demo-users --password ...]` | departments, areas, wards, SLA hours, demo accounts |
| `python manage.py import_dataset FILE.csv [--dry-run]` | validate and import labelled training data |
| `python manage.py train_complaint_model --activate` | train, evaluate and register a model |
| `python manage.py evaluate_model path/to/labelled.csv` | score the active model on a labelled CSV you provide |
| `python manage.py predict_complaint "text"` | classify one complaint |
| `python manage.py check_sla` | SLA warnings and escalation; **schedule every 5 to 15 minutes** (cron / Task Scheduler) |
| `python manage.py send_test_email you@example.com` | check that real email delivery works with your `.env` |
| `python manage.py purge_old_attempts` | delete old rejected-submission drafts |
| `python manage.py route_pending_complaints` | route complaints stuck in "Submitted" after an outage |
| `python manage.py ml_report` / `export_diagrams` | regenerate `docs/ml_results.md`, `docs/er_diagram.mmd`, `docs/lifecycle.mmd` |

## Where things are
| Role | Lands on |
|---|---|
| Citizen | `/complaints/mine/` |
| Department officer | `/officer/` (queue, by location, map, detail) |
| Field worker | `/worker/` |
| Administrator | `/admin-panel/` (dashboard, complaints, verification queue, AI model, users, departments, audit) |
| Django admin (areas, wards, raw data) | `/admin/` |

## Project layout
`accounts` (users, auth) · `departments` (master data, scoping) · `complaints` (models, services, views; business rules live in
`complaints/services/`) · `ml_engine` (NLP, training, prediction, explainability) · `notifications` · `audit` ·
`adminpanel` (administrator screens and analytics) · `core` (shared validators, error pages, security headers, demo commands) ·
`datasets/` (local data, not committed) · `docs/`.

## Documentation
`docs/DEMO_SCRIPT.md` · `docs/DIAGRAMS.md` · `docs/ml_results.md` · `docs/VIVA_NOTES.md` · `docs/REPORT_MAP.md` ·
`docs/TESTING.md` · `docs/SECURITY.md` · `docs/NOTIFICATIONS.md`

## Before real use
Set `DJANGO_DEBUG=False`, a long random `DJANGO_SECRET_KEY`, real `DJANGO_ALLOWED_HOSTS`, serve over HTTPS, set an upload size limit on
the web server, do not expose `media/` directly, configure SMTP for password-reset email, and use a shared cache (for example
Redis) for rate limits. Before enabling WhatsApp for real citizens, collect their consent and configure a provider. Run
`python manage.py check --deploy` before deployment.

## Rules a citizen meets when reporting a problem
- **Email verification:** a new account is created in a pending state and a 6-digit code is emailed (works once, 10 minutes, 5 guesses, resend cooldown).
- **A photo is compulsory**, and so is a **written description that really explains a municipal issue** (at least 5 words, rules in
  `complaints/municipal_terms.py`). Nonsense, unclear or out-of-scope text is refused with a clear message, kept as a draft under
  "Not submitted" on the citizen's page, and never becomes a complaint.
- **A location is compulsory**: choose a place from search, tap the map, or use the current location and wait for address verification.
  Complaints are accepted only in Bengaluru Urban and Bengaluru Rural; out-of-area locations remain visible on the map but cannot be submitted.
  Place search and the complete address are required; area, ward and street are optional.
See `docs/CHANGES_PHASE1.md` for details and measured results.

## Two rules that are deliberate design decisions
1. **The complaint description and citizen photo are both compulsory.** The description must meet `COMPLAINT_MIN_WORDS` and the municipal-issue check. The classifier reads text only, so the photo supports the report but cannot replace its description.
2. **A complaint cannot become "Resolved" without a photo of the completed fix.** The field worker must attach it, it is stored on the
   complaint as `resolution_photo` (separate from the citizen's own photo), the status change is refused without it, and the citizen
   sees it with their progress timeline once the officer has verified the work.

## Honest notes
Training data is synthetic. Accuracy on a random split of it is optimistic; a separate hand-written challenge set is the fairer
figure (see `docs/ml_results.md`). Email notifications work after SMTP is configured, and WhatsApp notifications are optional.
SMS, image-based routing, and multilingual routing are not implemented.

## Email and WhatsApp notifications
Complaint updates are also sent by email and, optionally, WhatsApp. See `docs/NOTIFICATIONS.md` and `docs/EMAIL_SETUP.md`.
