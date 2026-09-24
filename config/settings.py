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

ALLOWED_HOSTS = ['.vercel.app', 'localhost', '127.0.0.1', '192.168.1.113', '192.168.0.11']

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
]

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
        ],
    },
}]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('NEON_DATABASE_URL'),
        conn_max_age=600,
        ssl_require=True
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
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = '/media/'              
MEDIA_ROOT = BASE_DIR / 'media'    

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Tenancy contract tracking
ENDING_SOON_DAYS = int(os.getenv('ENDING_SOON_DAYS', '30'))

# Shared secret Vercel Cron sends as "Authorization: Bearer <CRON_SECRET>"
# when calling scheduled task endpoints. Empty by default so the endpoint
# fails closed (rejects everything) until explicitly configured.
CRON_SECRET = os.getenv('CRON_SECRET', '')

LOGIN_URL = 'users:login'
LOGIN_REDIRECT_URL = 'core:post_login_redirect' # Ensure 'core' app exists, or change to 'users:dashboard' etc.
LOGOUT_REDIRECT_URL = 'users:login'