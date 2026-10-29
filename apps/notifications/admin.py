from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'kind', 'body', 'read_at', 'created_at')
    list_filter = ('kind', 'created_at')
    search_fields = ('user__username', 'body')
    readonly_fields = ('created_at',)
