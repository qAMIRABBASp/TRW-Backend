from django.contrib import admin
from .models import Event, Registration


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "start_datetime", "capacity", "reserved_count", "price", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title",)


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "last_name",
        "event",
        "status",
        "amount",
        "payment_authority",
        "payment_ref_id",
        "created_at",
    )
    list_filter = ("status", "event")
    search_fields = ("first_name", "last_name", "email", "phone")
