#!/usr/bin/env bash
# Redeploy script for the Ubuntu/Gunicorn deployment. Run as the "deploy"
# user from /opt/vot-house-finding after the initial setup in
# DEPLOY_NOTES.md is done. Pulls the latest code, installs any new
# dependencies, applies migrations, collects static files, and restarts
# Gunicorn.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Pulling latest code"
git pull

echo "==> Installing dependencies"
source venv/bin/activate
pip install -r requirements.txt

echo "==> Applying database migrations"
python manage.py migrate

echo "==> Collecting static files"
python manage.py collectstatic --noinput

echo "==> Restarting application service"
sudo systemctl restart vot-house-finding

echo "==> Done. Service status:"
systemctl status vot-house-finding --no-pager -l | head -10
