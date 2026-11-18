"""
Simple login brute-force protection.

After LOGIN_MAX_ATTEMPTS failures for the same (email, IP) pair, further attempts are
refused for LOGIN_LOCKOUT_SECONDS. Counters live in Django's cache.

Limitations (state these honestly in the report): counters are per-process with the
default local-memory cache, and the IP is taken from REMOTE_ADDR. Behind a reverse proxy
configure the proxy to set REMOTE_ADDR correctly; do not trust X-Forwarded-For blindly.
"""
from django.conf import settings
from django.core.cache import cache


def _key(email: str, ip: str) -> str:
    return f"login-fail:{email.strip().lower()}:{ip}"


def client_ip(request) -> str:
    return request.META.get("REMOTE_ADDR", "unknown")


def is_locked(email: str, ip: str) -> bool:
    return cache.get(_key(email, ip), 0) >= settings.LOGIN_MAX_ATTEMPTS


def register_failure(email: str, ip: str) -> None:
    key = _key(email, ip)
    # add() sets the expiry only on the first failure, so the window is fixed, not sliding.
    cache.add(key, 0, settings.LOGIN_LOCKOUT_SECONDS)
    try:
        cache.incr(key)
    except ValueError:  # key expired between add() and incr()
        cache.set(key, 1, settings.LOGIN_LOCKOUT_SECONDS)


def reset(email: str, ip: str) -> None:
    cache.delete(_key(email, ip))


def allow(scope: str, identifier: str, limit: int, seconds: int) -> bool:
    """Count one use of `scope` by `identifier` in a fixed window; False once `limit` is exceeded."""
    key = f"rate:{scope}:{identifier.strip().lower()}"
    cache.add(key, 0, seconds)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, seconds)
        count = 1
    return count <= limit
