from django.urls import path

from . import views as v

app_name = "adminpanel"

urlpatterns = [
    path("", v.DashboardView.as_view(), name="dashboard"),
    path("complaints/", v.ComplaintsView.as_view(), name="complaints"),
    path("complaints/<int:pk>/", v.ComplaintDetailView.as_view(), name="complaint"),
    path("complaints/<int:pk>/route/", v.RouteView.as_view(), name="route"),
    path("complaints/<int:pk>/reject/", v.RejectView.as_view(), name="reject"),
    path("complaints/<int:pk>/duplicates/<int:flag_id>/review/", v.DuplicateReviewView.as_view(), name="duplicate_review"),
    path("queue/", v.QueueView.as_view(), name="queue"),
    path("users/", v.UsersView.as_view(), name="users"),
    path("users/new/", v.UserCreateView.as_view(), name="user_new"),
    path("users/<int:pk>/<str:action>/", v.UserActionView.as_view(), name="user_action"),
    path("departments/", v.DepartmentsView.as_view(), name="departments"),
    path("departments/new/", v.DepartmentCreateView.as_view(), name="department_new"),
    path("departments/<int:pk>/<str:active>/", v.DepartmentToggleView.as_view(), name="department_toggle"),
    path("sla/", v.SLAView.as_view(), name="sla"),
    path("ai/", v.AIView.as_view(), name="ai"),
    path("ai/train/", v.TrainView.as_view(), name="train"),
    path("ai/<int:pk>/activate/", v.ActivateView.as_view(), name="activate"),
    path("ai/<int:pk>/threshold/", v.ThresholdView.as_view(), name="threshold"),
    path("ai/try/", v.ModelTraceView.as_view(), name="trace"),
    path("ai/dataset/", v.DatasetView.as_view(), name="dataset"),
    path("ai/dataset/upload/", v.DatasetUploadView.as_view(), name="dataset_upload"),
    path("ai/dataset/add/", v.AddSampleView.as_view(), name="dataset_add"),
    path("ai/dataset/export/", v.DatasetExportView.as_view(), name="dataset_export"),
    path("audit/", v.AuditView.as_view(), name="audit"),
]
