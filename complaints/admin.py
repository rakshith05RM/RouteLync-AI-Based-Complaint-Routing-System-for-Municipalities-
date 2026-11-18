from django.contrib import admin

from .models import Complaint, ComplaintImage, ComplaintLocation, ComplaintStatusHistory


class LocationInline(admin.StackedInline):
    model = ComplaintLocation
    extra = 0


class HistoryInline(admin.TabularInline):
    model = ComplaintStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "timestamp")
    can_delete = False


class ImageInline(admin.TabularInline):
    model = ComplaintImage
    extra = 0


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "priority", "department", "routing_method", "citizen", "created_at")
    list_filter = ("status", "priority", "department")
    search_fields = ("title", "description", "citizen__email")
    readonly_fields = ("status", "department", "predicted_department", "ai_confidence", "ai_probabilities", "ai_terms",
                       "ai_model", "ai_predicted_at", "cleaned_text", "routing_method", "routing_reason", "routed_at",
                       "priority_reason", "sla_deadline", "resolution_photo", "created_at", "updated_at")
    inlines = [LocationInline, ImageInline, HistoryInline]
