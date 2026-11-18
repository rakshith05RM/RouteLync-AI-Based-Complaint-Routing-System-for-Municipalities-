from django.contrib import admin, messages

from .models import MLModel, TrainingSample


@admin.register(TrainingSample)
class TrainingSampleAdmin(admin.ModelAdmin):
    list_display = ("short_text", "department", "source", "is_verified", "dataset_version")
    list_filter = ("department", "source", "is_verified", "dataset_version")
    search_fields = ("text",)
    readonly_fields = ("text_hash",)

    @admin.display(description="text")
    def short_text(self, obj):
        return obj.text[:80]


@admin.register(MLModel)
class MLModelAdmin(admin.ModelAdmin):
    list_display = ("version", "is_active", "accuracy", "f1_macro", "challenge_accuracy", "conf_threshold",
                    "dataset_size", "trained_at")
    readonly_fields = [f.name for f in MLModel._meta.fields if f.name not in ("is_active", "conf_threshold", "notes")]
    actions = ["activate_selected"]

    def has_add_permission(self, request):
        return False  # models are created by the training command, not by hand

    @admin.action(description="Activate the selected model")
    def activate_selected(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one model.", messages.ERROR)
            return
        queryset.first().activate()
        self.message_user(request, "Model activated.", messages.SUCCESS)
