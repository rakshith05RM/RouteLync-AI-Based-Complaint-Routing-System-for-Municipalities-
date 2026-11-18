"""Extra browser-side protections added to every response."""

from django.conf import settings

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://cdn.jsdelivr.net",                       # Bootstrap's script; no inline scripts
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",   # inline style="" attributes are used
    "font-src 'self' https://fonts.gstatic.com",
    f"img-src 'self' data: {settings.LOCATION_TILE_CSP_SOURCE}",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
])
PERMISSIONS = "geolocation=(self), camera=(), microphone=(), payment=(), usb=()"


class SecurityHeadersMiddleware:
    """Content-Security-Policy limits where scripts, styles and images may load from, which contains the
    damage if an XSS bug is ever introduced. The Django admin site has its own scripts and is left out."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/admin/"):
            response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("Permissions-Policy", PERMISSIONS)
        return response
