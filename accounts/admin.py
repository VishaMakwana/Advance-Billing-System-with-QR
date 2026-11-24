from django.contrib import admin

from .models import Invoice, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("id", "customer_name", "user", "amount", "due_date", "created_at")
    list_filter = ("created_at", "due_date")
    search_fields = ("customer_name", "customer_email", "user__username")
    readonly_fields = ("created_at",)
