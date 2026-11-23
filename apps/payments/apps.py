from django.apps import AppConfig

class PaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.payments'

    def ready(self):
        from django.core import checks
        from apps.payments.verification import check_signing_key
        checks.register(check_signing_key, checks.Tags.security)
