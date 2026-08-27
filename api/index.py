# api/index.py
import sys
import os
from pathlib import Path

# Add the project directory to the sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Set the Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MUST_HOUSING.config.settings")

# Initialize the Django WSGI application
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()