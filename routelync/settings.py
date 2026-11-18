"""
RouteLync — Django settings.

All secrets and environment-specific values come from environment variables
(loaded from a local .env file in development). Nothing sensitive is hard-coded.
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SITE_URL = os.environ.get("SITE_URL", "http://127.0.0.1:8000").rstrip("/")
_site_url = urlsplit(SITE_URL)
if _site_url.scheme not in {"http", "https"} or not _site_url.hostname:
    raise ImproperlyConfigured("SITE_URL must be an absolute http:// or https:// URL.")
SITE_HOST = _site_url.hostname


# ---------------------------------------------------------------- Core security
DEBUG = env_bool("DJANGO_DEBUG", False)  # safe default: OFF unless explicitly enabled

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "insecure-dev-only-key-do-not-use-in-production"
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DEBUG is False.")

#ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
#ALLOWED_HOSTS = env_list(
 #   "DJANGO_ALLOWED_HOSTS",
  #  "127.0.0.1,localhost,timer-various-evidence-competitors.trycloudflare.com"
#)

ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    "127.0.0.1,localhost,timer-various-evidence-competitors.trycloudflare.com"
)
if SITE_HOST not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(SITE_HOST)
CSRF_TRUSTED_ORIGINS = [
    "https://*.trycloudflare.com",
]

# ---------------------------------------------------------------- Applications
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # RouteLync apps (more are added in later phases)
    "core",
    "accounts",
    "departments",
    "complaints",
    "ml_engine",
    "notifications",
    "audit",
    "adminpanel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "routelync.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_info",
                "notifications.context_processors.unread_notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "routelync.wsgi.application"
ASGI_APPLICATION = "routelync.asgi.application"

# ---------------------------------------------------------------- Database
DB_ENGINE = os.environ.get("DB_ENGINE", "mysql").lower()

if DB_ENGINE == "sqlite":
    # Only for quick local checks / automated tests without MySQL.
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ.get("DB_NAME", "routelync_db"),
            "USER": os.environ.get("DB_USER", ""),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DB_PORT", "3306"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {
                "charset": "utf8mb4",
                # Strict mode rejects silently truncated/invalid data (data integrity).
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }

# ---------------------------------------------------------------- Authentication
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"   # role router; see accounts/roles.py
LOGOUT_REDIRECT_URL = "core:home"

# Password-reset links expire after 1 hour (Django default is 3 days).
PASSWORD_RESET_TIMEOUT = 60 * 60

# Login brute-force protection (see accounts/throttle.py)
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60

# Email verification codes (OTP)
OTP_TTL_MINUTES = 10                   # a code stops working after this long
OTP_MAX_ATTEMPTS = 5                   # wrong guesses allowed per code
OTP_RESEND_COOLDOWN_SECONDS = 60       # minimum gap between two emails to the same person
OTP_MAX_SENDS_PER_HOUR = 5
OTP_VERIFY_LIMIT_PER_HOUR = 20         # verification attempts per email address, across all codes

# Rate limits for public forms (per hour). Login lockout is separate (see accounts/throttle.py).
REGISTER_LIMIT_PER_IP = 10
RESET_LIMIT_PER_IP = 10
RESET_LIMIT_PER_EMAIL = 3

# Local-memory cache is per-process: fine for development and the demo.
# For a multi-process deployment use a shared cache (Redis / database cache).
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Sessions: expire on inactivity-style window, not readable from JavaScript.
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 hours
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# ---------------------------------------------------------------- Internationalisation
LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True  # timestamps stored in UTC, shown in local time (needed for SLA maths)

# ---------------------------------------------------------------- Static & media
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Complaint-image rules (enforced in Phase 4 validators)
MAX_IMAGE_SIZE_MB = int(os.environ.get("MAX_IMAGE_SIZE_MB", "5"))
ALLOWED_IMAGE_FORMATS = ("JPEG", "PNG", "WEBP")
MAX_IMAGE_PIXELS_ALLOWED = 25_000_000  # width x height cap (decompression-bomb protection)
COMPLAINT_MIN_WORDS = 5                # a complaint needs a real written description (the classifier reads text only)
MAX_ATTEMPTS_PER_DAY = 10              # rejected submissions kept per citizen per day (they are drafts, not complaints)
ATTEMPT_RETENTION_DAYS = 14
REOPEN_WINDOW_DAYS = 7                 # a citizen may reopen a resolved complaint within this many days
SLA_WARNING_FRACTION = 0.25            # warn officers when this share of the SLA window is left
ESCALATION_LEVEL2_AFTER_HOURS = 24     # hours after level 1 before administrators are told
# Possible-duplicate detection (flags for human review; nothing is merged automatically)
DUPLICATE_WINDOW_DAYS = 30             # only compare with complaints submitted this recently
DUPLICATE_THRESHOLD_NEARBY = 0.65      # text similarity needed when street or GPS location also matches
DUPLICATE_THRESHOLD_WARD = 0.80        # stricter when only the ward matches
DUPLICATE_NEARBY_METRES = 150
MAX_COMPLAINTS_PER_DAY = 20            # simple anti-spam limit per citizen
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # hard cap on request body size

# ---------------------------------------------------------------- Email
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)          # port 465 providers; do not combine with TLS
EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "10"))  # seconds; a slow mail server must not hang a page
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "RouteLync <no-reply@routelync.local>")
DEFAULT_REPLY_TO_EMAIL = os.environ.get("DEFAULT_REPLY_TO_EMAIL", "no-reply@routelync.local")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
























# ---------------------------------------------------------------- Browser-side hardening
SECURE_REFERRER_POLICY = "same-origin"          # do not leak complaint URLs to other sites
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
CSRF_FAILURE_VIEW = "core.views.csrf_failure"   # friendly page instead of a bare 403
# W021 asks for HSTS preloading, which is a permanent public commitment for the whole domain; a deliberate "no".
SILENCED_SYSTEM_CHECKS = ["security.W021"]

# ---------------------------------------------------------------- Production hardening
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

# Domain used for the department staff logins made by `manage.py setup_staff_accounts`, e.g. electricityofficer1@<domain>
STAFF_EMAIL_DOMAIN = os.environ.get("STAFF_EMAIL_DOMAIN", "company.com")

# ---------------------------------------------------------------- Location search (geocoding)
# The browser never talks to the geocoder directly: it asks RouteLync (/geo/search/, /geo/reverse/), which keeps any API key
# private, limits and caches requests, and signs each result so an address cannot be paired with different coordinates.
#
# GEOCODER_PROVIDER: "photon" (built for search-as-you-type; the public instance is fair-use only) or "nominatim"
# (OpenStreetMap's public server FORBIDS autocomplete and heavy use: for production run your own instance or use a
# commercial Nominatim-compatible service such as LocationIQ and put its URL and key below).
GEOCODER_PROVIDER = os.environ.get("GEOCODER_PROVIDER", "photon").lower()
GEOCODER_BASE_URL = os.environ.get("GEOCODER_BASE_URL", "").rstrip("/")      # empty = the provider's public default
GEOCODER_API_KEY = os.environ.get("GEOCODER_API_KEY", "")                    # server-side only, never sent to the browser
GEOCODER_CONTACT_EMAIL = os.environ.get("GEOCODER_CONTACT_EMAIL", "")        # Nominatim's policy asks for a contact
GEOCODER_USER_AGENT = os.environ.get("GEOCODER_USER_AGENT", "RouteLync/1.0 (municipal complaint routing)")
GEOCODER_TIMEOUT = float(os.environ.get("GEOCODER_TIMEOUT", "5"))
GEOCODER_CACHE_SECONDS = 60 * 60
GEOCODER_RATE_PER_MINUTE = 30                                                # requests per signed-in person
# The area served: "min_lat,min_lon,max_lat,max_lon". Empty = no restriction. The default covers the whole of Karnataka.
# It is a rectangle, so it also takes in thin strips of neighbouring states along the border (see docs/LOCATION_SETUP.md).
# For Bengaluru only, use 12.70,77.35,13.25,77.85
LOCATION_MAP_BOUNDS = os.environ.get("LOCATION_MAP_BOUNDS", "12.65,77.18,13.50,77.95")
LOCATION_TILE_URL = os.environ.get(
    "LOCATION_TILE_URL",
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}")
LOCATION_TILE_ATTRIBUTION = os.environ.get(
    "LOCATION_TILE_ATTRIBUTION",
    "Tiles &copy; Esri — Sources: Esri, HERE, Garmin, OpenStreetMap contributors, "
    "and the GIS User Community")
LOCATION_TILE_CSP_SOURCE = os.environ.get(
    "LOCATION_TILE_CSP_SOURCE", "https://server.arcgisonline.com")

# ---------------------------------------------------------------- Machine learning
ML_MODELS_DIR = BASE_DIR / "ml_models"      # trained artefacts (joblib) + metadata
DATASETS_DIR = BASE_DIR / "datasets"
ML_RANDOM_STATE = 42                         # fixed seed: reproducible split and training
ML_TEST_SIZE = 0.20
ML_MIN_SAMPLES_PER_CLASS = 20                # refuse to train on tiny classes
ML_TARGET_PRECISION = 0.95                   # desired accuracy of AUTO-routed complaints
ML_MIN_THRESHOLD = 0.50                      # confidence threshold is never set below this

# ---------------------------------------------------------------- Logging
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "routelync.log",
            "maxBytes": 2 * 1024 * 1024,
            "backupCount": 3,
            "formatter": "standard",
        },
    },
    "loggers": {
        # Technical errors go here; users only ever see friendly error pages.
        "routelync": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["file"], "level": "WARNING", "propagate": False},
    },
}

# ---------------------------------------------------------------- Delivering notifications outside the app
# Every in-app notification can also be emailed and/or sent on WhatsApp (see docs/NOTIFICATIONS.md).
# Credentials come only from the environment, never from the code.
NOTIFY_EMAIL_ENABLED = env_bool("NOTIFY_EMAIL_ENABLED", True)
NOTIFY_WHATSAPP_ENABLED = env_bool("NOTIFY_WHATSAPP_ENABLED", False)          # needs a provider account, see below
NOTIFY_EXTERNAL_ROLES = env_list("NOTIFY_EXTERNAL_ROLES", "CITIZEN,OFFICER,FIELD_WORKER,ADMIN")
NOTIFY_ASYNC = env_bool("NOTIFY_ASYNC", True)        # send in a background thread so a slow provider never slows a page
WHATSAPP_PROVIDER = os.environ.get("WHATSAPP_PROVIDER", "twilio").strip().lower()   # "twilio" or "meta"
WHATSAPP_COUNTRY_CODE = os.environ.get("WHATSAPP_COUNTRY_CODE", "91")         # added to the 10-digit mobile numbers on file
WHATSAPP_TIMEOUT = int(os.environ.get("WHATSAPP_TIMEOUT", "8"))
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")             # e.g. +14155238886 (the Twilio sandbox number)
META_WHATSAPP_TOKEN = os.environ.get("META_WHATSAPP_TOKEN", "")
META_WHATSAPP_PHONE_ID = os.environ.get("META_WHATSAPP_PHONE_ID", "")
WHATSAPP_TEMPLATE_NAME = os.environ.get("WHATSAPP_TEMPLATE_NAME", "")         # approved template with ONE body variable {{1}}
WHATSAPP_TEMPLATE_LANG = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")

# ---------------------------------------------------------------- Tests only
# A deliberately fast (insecure) hasher makes the test suite quick. It is active ONLY when running
# `manage.py test`; the one test that checks real hashing re-enables PBKDF2 explicitly.
if "test" in sys.argv:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    # Public-form rate limits are effectively off so unrelated tests are not throttled; throttle tests lower them.
    REGISTER_LIMIT_PER_IP = RESET_LIMIT_PER_IP = RESET_LIMIT_PER_EMAIL = 10_000
    OTP_RESEND_COOLDOWN_SECONDS = 0     # the cooldown tests set their own value
    NOTIFY_EMAIL_ENABLED = False        # delivery tests switch these on explicitly
    NOTIFY_WHATSAPP_ENABLED = False
    NOTIFY_ASYNC = False
    GEOCODER_RATE_PER_MINUTE = 10_000
