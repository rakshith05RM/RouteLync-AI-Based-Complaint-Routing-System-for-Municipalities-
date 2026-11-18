import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.http import JsonResponse
from django.views import View

from accounts import throttle
from accounts.mixins import RoleRequiredMixin
from accounts.models import Role

from . import service
from .providers import GeocoderError

logger = logging.getLogger("routelync")
ATTRIBUTION = "\u00a9 OpenStreetMap contributors"
BUSY = "Search is busy. Please try again in a moment."
DOWN = "Location search is unavailable right now. You can still place the pin on the map."


class GeoView(RoleRequiredMixin, View):
    allowed_roles = (Role.CITIZEN,)

    def limited(self, request):
        return not throttle.allow("geo", str(request.user.pk), settings.GEOCODER_RATE_PER_MINUTE, 60)

    def provider_error(self, exc):
        logger.warning("Geocoder problem: %s", exc.kind)
        if exc.kind == "rate_limited":
            return JsonResponse({"error": BUSY}, status=429)
        return JsonResponse({"error": DOWN}, status=502)


class SearchView(GeoView):
    def get(self, request):
        if self.limited(request):
            return JsonResponse({"error": BUSY}, status=429)
        try:
            results = service.search_places(request.GET.get("q", ""), request.user.pk)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except GeocoderError as exc:
            return self.provider_error(exc)
        return JsonResponse({"results": results, "attribution": ATTRIBUTION})


class ReverseView(GeoView):
    def get(self, request):
        if self.limited(request):
            return JsonResponse({"error": BUSY}, status=429)
        try:
            lat, lng = Decimal(request.GET.get("lat", "")), Decimal(request.GET.get("lng", ""))
        except InvalidOperation:
            return JsonResponse({"error": "Invalid coordinates."}, status=400)
        if not (lat.is_finite() and lng.is_finite() and -90 <= lat <= 90 and -180 <= lng <= 180):
            return JsonResponse({"error": "Invalid coordinates."}, status=400)
        try:
            result = service.reverse_place(float(lat), float(lng), request.user.pk)
        except GeocoderError as exc:
            return self.provider_error(exc)
        if result is None:
            return JsonResponse({"error": "No address was found for that point. You can type the address yourself."}, status=404)
        return JsonResponse({"result": result, "attribution": ATTRIBUTION})
