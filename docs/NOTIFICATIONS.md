# Notifications by email and WhatsApp

Every notification RouteLync creates in the app (complaint submitted, sent to a department, worker assigned, work started,
work completed and awaiting verification, resolved, rejected, reopened, escalated, and so on) is **also sent by email and, if you switch it on, by WhatsApp**.
The wording is exactly what the person sees in the app, so citizens never receive internal details (priority, AI results,
staff names). Each message carries a link back to the complaint.

## 1. Why you may have received nothing so far
RouteLync starts with the **console email backend**: emails (including the sign-up verification code and password reset) are
printed in the terminal that runs the server and are never delivered. Set up SMTP first, see `docs/EMAIL_SETUP.md`, then:
```bash
python manage.py send_test_email you@example.com
```
Set `SITE_URL` in `.env` to your real address, because it is used to build the links inside the messages.

## 2. Email
Nothing more to do once SMTP works. Email goes to every user whose address is verified. Ensure
`NOTIFY_EMAIL_ENABLED=True`; setting it to `False` disables notification email even when SMTP is configured. Limit it to
some roles with `NOTIFY_EXTERNAL_ROLES=CITIZEN`. Emails include a mobile-friendly tracking button and a plain-text link.

## 3. WhatsApp
RouteLync sends to the **mobile number the person registered** (10 digits, `WHATSAPP_COUNTRY_CODE` is added, default 91).
WhatsApp needs a provider account. Pick one in `.env`:

### Option A: Twilio (quickest to try)
1. Create a Twilio account and open *Messaging, Try it out, Send a WhatsApp message* (the sandbox).
2. From each phone that should receive messages, send the join code shown there to the sandbox number.
3. `.env`:
```
NOTIFY_WHATSAPP_ENABLED=True
WHATSAPP_PROVIDER=twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxx
TWILIO_WHATSAPP_FROM=+14155238886
```
The sandbox only reaches phones that joined it. For real citizens you need an approved WhatsApp sender and message template with Twilio.

### Option B: Meta WhatsApp Cloud API (official, direct)
1. Create a Meta developer app with the WhatsApp product and a business phone number.
2. Create and get approved a message template whose body is exactly `RouteLync update: {{1}}` (one variable).
3. `.env`:
```
NOTIFY_WHATSAPP_ENABLED=True
WHATSAPP_PROVIDER=meta
META_WHATSAPP_TOKEN=<permanent access token>
META_WHATSAPP_PHONE_ID=<phone number id>
WHATSAPP_TEMPLATE_NAME=<your approved template name>
```
Without a template only free-form text is possible, and WhatsApp delivers it only within 24 hours after the person last
messaged your number. So for a complaint system a template is required.

### Check it
```bash
python manage.py send_test_whatsapp 9876543210
```
It prints the provider and either "accepted" or the exact reason (wrong credentials, network, and so on). "Accepted" means the
provider took the message; delivery to the handset is then up to WhatsApp (sandbox join, template approval, number reachable).

## Important: consent and policy
WhatsApp only allows business messages to people who agreed to receive them. The registration form currently says nothing about
WhatsApp, so before using real citizens' numbers, add a clear consent line on the registration page, or collect an opt-in. Meta and
Twilio can suspend accounts that message people without consent.

## How it behaves
* Sent only **after the database transaction commits**, so an action that fails and rolls back never sends a message.
* When a worker submits completed work, the citizen is told it is awaiting department verification. The separate
  resolution email is sent only after an officer verifies the work.
* Sent in a **background thread** (`NOTIFY_ASYNC=True`) so a slow provider never slows a page. For large traffic, move delivery
  to a proper task queue (for example Celery) instead of threads.
* A failure on one channel never stops the other, never breaks the page, and is logged **without** addresses, numbers,
  message text or secrets (see `logs/routelync.log`).
* Credentials are read only from the environment (`.env`), never stored in code or the database.
* Delivery is best-effort: the in-app notification always exists, even if email or WhatsApp fails.
