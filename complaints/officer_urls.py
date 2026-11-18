from django.urls import path

from .views import officer

app_name = "officer"

urlpatterns = [
    path("", officer.DashboardView.as_view(), name="dashboard"),
    path("locations/", officer.LocationBrowseView.as_view(), name="locations"),
    path("map/", officer.MapView.as_view(), name="map"),
    path("complaints/<int:pk>/", officer.ComplaintDetailView.as_view(), name="detail"),
    path("complaints/<int:pk>/assign/", officer.AssignView.as_view(), name="assign"),
    path("complaints/<int:pk>/unassign/", officer.UnassignView.as_view(), name="unassign"),
    path("complaints/<int:pk>/remark/", officer.RemarkView.as_view(), name="remark"),
    path("complaints/<int:pk>/priority/", officer.PriorityView.as_view(), name="priority"),
    path("complaints/<int:pk>/escalate/", officer.EscalateView.as_view(), name="escalate"),
    path("complaints/<int:pk>/duplicates/<int:flag_id>/review/", officer.DuplicateReviewView.as_view(), name="duplicate_review"),
    path("complaints/<int:pk>/reject/", officer.RejectView.as_view(), name="reject"),
    path("complaints/<int:pk>/review/", officer.ReviewView.as_view(), name="review"),
]
