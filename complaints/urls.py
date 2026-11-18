from django.urls import path

from .views import citizen

app_name = "complaints"

urlpatterns = [
    path("new/", citizen.ComplaintCreateView.as_view(), name="new"),
    path("mine/", citizen.MyComplaintsView.as_view(), name="my_complaints"),
    path("<int:pk>/", citizen.ComplaintDetailView.as_view(), name="detail"),
    path("attempts/<int:pk>/discard/", citizen.AttemptDiscardView.as_view(), name="attempt_discard"),
    path("<int:pk>/confirm/", citizen.ConfirmResolutionView.as_view(), name="confirm"),
    path("<int:pk>/feedback/", citizen.FeedbackView.as_view(), name="feedback"),
    path("<int:pk>/reopen/", citizen.ReopenComplaintView.as_view(), name="reopen"),
    path("<int:pk>/proof-photo/", citizen.resolution_photo, name="resolution_photo"),
    path("<int:pk>/image/<int:image_id>/", citizen.complaint_image, name="image"),
]
