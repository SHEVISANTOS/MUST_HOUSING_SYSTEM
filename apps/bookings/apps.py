from django.apps import AppConfig

class BookingsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.bookings'

    def ready(self):
        # Absolute import, not relative: this app is registered in
        # INSTALLED_APPS as the short name 'bookings' (via the sys.path
        # hack in settings.py), but AppConfig.name here is 'apps.bookings'.
        # A relative import from this module resolves against whichever of
        # those two identities Python happened to load *this file* as,
        # which can differ from how models.py was already loaded elsewhere
        # (e.g. via config/urls.py's include('apps.bookings.urls')) -
        # causing Django to try to register the same models twice under
        # different module paths. Importing the fully-qualified path here
        # forces reuse of the already-loaded module instead.
        import apps.bookings.signals  # noqa: F401