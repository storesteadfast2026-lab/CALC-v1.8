import json

from django.contrib import admin
from django.utils.html import format_html

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'event_type', 'severity', 'actor', 'client', 'external_file', 'message_short')
    list_filter = ('severity', 'event_type', 'client', 'created_at')
    search_fields = ('event_type', 'message', 'request_id', 'metadata')
    readonly_fields = (
        'actor', 'client', 'external_file', 'event_type', 'severity', 'message_display',
        'metadata_display', 'ip_address', 'request_id', 'created_at',
    )
    fieldsets = (
        (None, {
            'fields': ('created_at', 'severity', 'event_type', 'message_display'),
        }),
        ('Related records', {
            'fields': ('actor', 'client', 'external_file'),
        }),
        ('Technical details', {
            'fields': ('metadata_display', 'ip_address', 'request_id'),
            'classes': ('collapse',),
        }),
    )
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    @admin.display(description='Message')
    def message_display(self, obj):
        metadata = obj.metadata if isinstance(obj.metadata, dict) else {}
        trigger = metadata.get('trigger')
        filename = metadata.get('filename')
        if trigger not in ('AUTOMATIC', 'MANUAL') or not isinstance(filename, str) or not filename:
            return obj.message

        prefix = f'{trigger.title()} FTP · {filename}. '
        if obj.event_type == 'FTP_SCHEDULED_FILE_WAITING':
            return f'{prefix}Waiting to process. {obj.message}'
        if obj.event_type == 'FTP_SCHEDULED_FILE_ERROR':
            return f'{prefix}Processing failed. {obj.message}'
        if not obj.external_file_id or metadata.get('operational_data_changed') is not False:
            return obj.message
        if obj.event_type == 'FTP_SCHEDULED_FILE_REGISTERED':
            result = (
                f'New version #{obj.external_file_id} saved. Any earlier versions were kept.'
            )
        elif obj.event_type == 'FTP_SCHEDULED_FILE_UNCHANGED':
            result = f'Matches saved version #{obj.external_file_id}. No duplicate was saved.'
        else:
            return obj.message
        return (
            f'{prefix}{result} This run kept the current operational data in use. '
            'See the file record for validation status.'
        )

    @admin.display(description='Message')
    def message_short(self, obj):
        message = self.message_display(obj)
        if message != obj.message:
            return message
        return message if len(message) <= 100 else f'{message[:97]}...'

    @admin.display(description='Metadata')
    def metadata_display(self, obj):
        return format_html('<pre style="white-space:pre-wrap">{}</pre>', json.dumps(obj.metadata, indent=2))

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        # Defensive: the admin UI is read-only; events are created by application services.
        if not change:
            return
        super().save_model(request, obj, form, change)
