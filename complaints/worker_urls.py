from django.urls import path

from .views import worker

app_name = "worker"

urlpatterns = [
    path("", worker.WorkerDashboardView.as_view(), name="dashboard"),
    path("complaints/<int:pk>/", worker.WorkerDetailView.as_view(), name="detail"),
    path("complaints/<int:pk>/start/", worker.StartWorkView.as_view(), name="start"),
    path("complaints/<int:pk>/remark/", worker.FieldRemarkView.as_view(), name="remark"),
    path("complaints/<int:pk>/complete/", worker.CompleteWorkView.as_view(), name="complete"),
]
