from django.urls import path

from .geo import views

app_name = "geo"

urlpatterns = [
    path("search/", views.SearchView.as_view(), name="search"),
    path("reverse/", views.ReverseView.as_view(), name="reverse"),
]
