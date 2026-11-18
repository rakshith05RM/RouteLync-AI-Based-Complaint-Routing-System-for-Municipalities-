from django.contrib import admin

from .models import Area, Department, FieldWorkerProfile, OfficerProfile, SLAConfiguration, Ward


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")

    def get_readonly_fields(self, request, obj=None):
        # The code is the ML class label, so it cannot be edited after creation.
        return ("code",) if obj else ()


class WardInline(admin.TabularInline):
    model = Ward
    extra = 1


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    inlines = [WardInline]


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ("number", "name", "area")
    list_filter = ("area",)
    search_fields = ("number", "name", "area__name")


@admin.register(OfficerProfile)
class OfficerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "designation", "is_department_head")
    list_filter = ("department", "is_department_head")
    search_fields = ("user__email", "user__full_name")


@admin.register(FieldWorkerProfile)
class FieldWorkerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "employee_code", "department", "is_available")
    list_filter = ("department", "is_available")
    search_fields = ("user__email", "user__full_name", "employee_code")


@admin.register(SLAConfiguration)
class SLAConfigurationAdmin(admin.ModelAdmin):
    list_display = ("priority", "hours")
