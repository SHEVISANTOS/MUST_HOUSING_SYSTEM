from django.contrib import admin
from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ('sender', 'body', 'created_at', 'read_at')
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('property', 'tenant', 'landlord', 'booking', 'updated_at')
    list_filter = ('created_at',)
    search_fields = ('property__title', 'tenant__username', 'landlord__username')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [MessageInline]
