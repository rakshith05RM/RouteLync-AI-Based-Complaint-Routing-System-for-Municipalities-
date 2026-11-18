def site_info(request):
    from django.conf import settings
    """Makes brand strings available in every template."""
    return {
        "SITE_NAME": "RouteLync",
        "SITE_TAGLINE": "Smart Complaint Routing Platform",
        "EMAIL_CONSOLE": settings.EMAIL_BACKEND.endswith("console.EmailBackend"),
        "LOCATION_TILE_URL": settings.LOCATION_TILE_URL,
        "LOCATION_TILE_ATTRIBUTION": settings.LOCATION_TILE_ATTRIBUTION,
    }
