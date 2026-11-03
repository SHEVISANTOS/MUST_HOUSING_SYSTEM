#!/usr/bin/env bash
# Redeploy the Ubuntu/Gunicorn deployment. Run as "santos" from anywhere:
#   /srv/must_housing/scripts/deploy_ubuntu.sh
# Override SERVICE / HEALTH_URL via env vars for a different server layout.
set -euo pipefail

SERVICE="${SERVICE:-must-housing}"
HEALTH_URL="${HEALTH_URL:-https://housing.162-35-28-34.sslip.io/healthz}"

cd "$(dirname "$0")/.."

echo "==> Fetching latest code"
git fetch origin

# staticfiles/ is git-tracked and rewritten by every collectstatic, so local
# changes there are expected noise. Anything else modified is a real
# server-side edit that reset --hard would destroy - stop instead.
real_changes=$(git status --porcelain --untracked-files=no | grep -v ' staticfiles/' || true)
if [ -n "$real_changes" ]; then
    echo "ABORT: tracked files modified on the server (would be lost by reset):" >&2
    echo "$real_changes" >&2
    exit 1
fi

# Untracked code under apps/ or config/ survives reset --hard but never
# reaches git - exactly how config/uploads.py sat orphaned for a week.
stray=$(git status --porcelain --untracked-files=all apps config | grep '^??' | grep -v '__pycache__' || true)
if [ -n "$stray" ]; then
    echo "WARNING: untracked server-only code (not in git - commit it or delete it):"
    echo "$stray"
fi

echo "==> Resetting to origin/main"
git reset --hard origin/main

echo "==> Installing dependencies"
source venv/bin/activate
python -m pip install -q -r requirements.txt

echo "==> Applying database migrations"
python manage.py migrate --noinput

echo "==> Collecting static files"
python manage.py collectstatic --noinput -v0

echo "==> Restarting $SERVICE"
sudo systemctl restart "$SERVICE"

echo "==> Waiting for $HEALTH_URL"
for _ in $(seq 1 15); do
    if [ "$(curl -sk -o /dev/null -w '%{http_code}' --max-time 5 "$HEALTH_URL")" = 200 ]; then
        echo "==> Deployed $(git log -1 --oneline) - healthy."
        exit 0
    fi
    sleep 2
done

echo "FAILED: $HEALTH_URL not healthy after 30s. Recent logs:" >&2
sudo journalctl -u "$SERVICE" -n 40 --no-pager >&2
exit 1
