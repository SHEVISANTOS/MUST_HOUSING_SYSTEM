import importlib.util
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ⬇️ CRITICAL FIX: Tell Python to look inside the 'apps' folder
sys.path.insert(0, str(BASE_DIR / 'apps'))
# KNOWN ISSUE (not fixed here - out of scope, would need a wider audit):
# this makes each app importable BOTH as its short name (e.g. `bookings`,
# which is what INSTALLED_APPS below uses) AND as `apps.<name>` (which is
# what every AppConfig.name in apps/*/apps.py is set to, and what the rest
# of the codebase uses for imports/urls, e.g. config/urls.py's
# include('apps.bookings.urls')). Both paths resolve to the same file but
# are DIFFERENT module identities to Python, so anything imported via the
# short path is a distinct, separately-registered copy of that module. This
# is normally invisible, but bit us once already: see the comment in
# apps/bookings/apps.py's ready() for the concrete failure it caused.
# Proper fix would be to either drop this sys.path hack and use `apps.X`
# everywhere, or set every AppConfig.name to match INSTALLED_APPS' short
# names - either way it touches all 4 apps, so deferred rather than done
# as a side effect of an unrelated feature.

# ⬇️ CRITICAL FIX: Add a fallback so it never crashes as None
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'fallback-dev-key-replace-in-vercel')

# Keep Debug False in production, but allow local override
DEBUG = os.getenv('DJANGO_DEBUG', 'False') == 'True'

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '192.168.1.113', '192.168.0.11' , '192.168.1.207']
# Extra hosts (e.g. the server's domain) - additive, comma-separated.
# Unset by default (no effect unless explicitly configured).
ALLOWED_HOSTS += [h.strip() for h in os.getenv('DJANGO_ALLOWED_HOSTS', '').split(',') if h.strip()]

# Needed once DEBUG=False and the site is served over plain HTTP from an
# IP/domain Django doesn't already trust by default for POST/CSRF - e.g. the
# Ubuntu server before a domain + HTTPS is set up. Empty by default (no
# effect unless explicitly configured); scheme defaults to http:// since
# that's the only thing an IP-only deployment without a domain/TLS cert can
# serve - override with a full "https://..." origin once HTTPS is in place.
CSRF_TRUSTED_ORIGINS = [
    o.strip() if '://' in o.strip() else f'http://{o.strip()}'
    for o in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()
]

# Behind nginx: trust its X-Forwarded-Proto header so Django knows a
# request arrived over HTTPS even though nginx terminates TLS and forwards
# to Gunicorn over plain HTTP. Only meaningful once nginx is actually
# setting that header (see deploy/nginx_vot_house_finding.conf).
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',  # {% load humanize %} / |intcomma - TZS thousand separators

    # Third party
    'crispy_bootstrap5',
    'whitenoise.runserver_nostatic',

    # ⬇️ CRITICAL FIX: Use simple names now that 'apps' is in sys.path
    'users',
    'properties',
    'bookings',
    'payments',
    'messaging',
    'notifications',
]

# django-extensions (shell_plus, runserver_plus, etc.) is a dev convenience
# tool, not a real runtime dependency - it's intentionally left out of
# requirements.txt (see requirements-dev.txt) so production installs stay
# lean. Load it only if it's actually installed, so an environment that
# skipped the dev requirements doesn't hard-crash on a missing dev tool.
if importlib.util.find_spec('django_extensions'):
    INSTALLED_APPS.append('django_extensions')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', 
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Messages configuration
from django.contrib.messages import constants as messages

MESSAGE_TAGS = {
    messages.DEBUG: 'alert-secondary',
    messages.INFO: 'alert-info',
    messages.SUCCESS: 'alert-success',
    messages.WARNING: 'alert-warning',
    messages.ERROR: 'alert-danger',
}

ROOT_URLCONF = 'config.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            
            'django.template.context_processors.debug',
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
            'apps.properties.context_processors.saved_property_ids',
            'apps.messaging.context_processors.unread_message_count',
            'apps.notifications.context_processors.unread_notification_count',
        ],
    },
}]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('NEON_DATABASE_URL'),
        conn_max_age=600,
        ssl_require=os.getenv('DB_SSL_REQUIRE', 'True') == 'True'
    )
}

# This now perfectly matches the simplified INSTALLED_APPS name
AUTH_USER_MODEL = 'users.User'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Dar_es_Salaam'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Use the modern Django 4.2+ storage setting
STORAGES = {
    # Django 4.2+ requires an explicit "default" entry (used for FileField/
    # ImageField uploads, e.g. property photos) once STORAGES is set at all -
    # there's no implicit fallback to the built-in default. Without this key,
    # every image upload fails with "Could not find config for 'default' in
    # settings.STORAGES", which is what was happening here.
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Media uploads (property photos, etc.) are served from local disk via the
# FileSystemStorage configured above - any R2_* env vars still present in
# .env are simply unused and ignored, not read here at all.
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django's default logging only prints to console when DEBUG=True, and with
# no ADMINS set, unhandled 500s in production went nowhere at all - not even
# journalctl. Send ERROR-level request failures (tracebacks included) to
# stderr, which Gunicorn/systemd captures into journalctl.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'loggers': {
        'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
    },
}

# PBKDF2 is deliberately slow (~1M iterations) to resist brute-forcing, and
# nearly every test creates/logs in users - the test suite spent most of its
# time hashing. Use a fast hasher for `manage.py test` only; real logins
# always use the default secure hashers.
if len(sys.argv) > 1 and sys.argv[1] == 'test':
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Tenancy contract tracking
ENDING_SOON_DAYS = int(os.getenv('ENDING_SOON_DAYS', '30'))

LOGIN_URL = 'users:login'
LOGIN_REDIRECT_URL = 'core:post_login_redirect' # Ensure 'core' app exists, or change to 'users:dashboard' etc.
LOGOUT_REDIRECT_URL = 'properties:list'