from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("complaints/", include("complaints.urls")),
    path("officer/", include("complaints.officer_urls")),
    path("worker/", include("complaints.worker_urls")),
    path("notifications/", include("notifications.urls")),
    path("admin-panel/", include("adminpanel.urls")),
    path("geo/", include("core.geo_urls")),
]

# Friendly error pages (active when DEBUG is False)
handler400 = "core.views.bad_request"
handler403 = "core.views.permission_denied"
handler404 = "core.views.page_not_found"
handler500 = "core.views.server_error"

# NOTE: uploaded media is deliberately NOT served directly, not even in development.
# Complaint images are streamed by an authorised view (complaints:image) so that only people
# allowed to see a complaint can see its photo. In production, do not expose MEDIA_ROOT
# through the web server either.
