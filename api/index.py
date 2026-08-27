# api/index.py
import sys
import os
from pathlib import Path

# 1. Add the project root to sys.path (so it can find the 'config' folder)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 2. Set the Django settings module (Must match manage.py exactly)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# 3. Initialize the Django WSGI application
from django.core.wsgi import get_wsgi_application

# 4. Vercel looks for a variable named 'app'
app = get_wsgi_application()