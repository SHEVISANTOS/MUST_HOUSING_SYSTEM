#!/usr/bin/env bash
# MUST Housing (VOT House Finding): periodic health check + email alert.
# Monitor-only, unlike votstay-autoupdate.sh - this does NOT auto-pull code
# or restart anything, it only checks and alerts; deploys stay a manual,
# reviewed step. Run as root by must-housing-monitor.timer.
# Logs: journalctl -u must-housing-monitor
set -uo pipefail

HOST=housing.162-35-28-34.sslip.io
ALERT_EMAIL=shevijeremiah@gmail.com
# Reuses VOT-Stay's Brevo account/recipient rather than provisioning a
# second one - same convention votstay-sshdigest.sh already uses for
# server-wide alerts.
VOTSTAY_ENV=/home/santos/VOT-Stay/.env
BACKUP_DIR=/var/backups/must_housing
STATE=/var/lib/must-housing-monitor
SERVICE=must-housing

mkdir -p "$STATE"
REPORT=$(mktemp); trap 'rm -f "$REPORT"' EXIT
STATUS=OK

say()  { echo "$*" | tee -a "$REPORT"; }
warn() { [ "$STATUS" = FAILED ] || STATUS=WARNING; say "WARNING: $*"; }
fail() { STATUS=FAILED; say "FAILED: $*"; }

say "== MUST Housing health check $(date '+%F %T %Z') on $(hostname) =="

# 1. Service up (app + the shared services it depends on)
for s in nginx postgresql "$SERVICE"; do
  systemctl is-active --quiet "$s" || fail "service $s is not running"
done

# 2. App + DB actually reachable (not just that Gunicorn accepted the TCP connection)
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "https://$HOST/healthz")
[ "$code" = 200 ] && say "Health: OK (/healthz 200)" || fail "/healthz returned $code"

# 3. TLS certificate
echo | openssl s_client -servername "$HOST" -connect "$HOST:443" 2>/dev/null \
  | openssl x509 -noout -checkend $((14*86400)) >/dev/null \
  && say "TLS: certificate valid > 14 days" || warn "TLS certificate expires within 14 days (check: certbot renew)"

# 4. The nightly backup is actually running (not just configured)
if find "$BACKUP_DIR" -maxdepth 1 -name 'must_housing-db-*.dump' -mtime -2 2>/dev/null | grep -q .; then
  say "Backup: a DB backup exists from the last 2 days"
else
  warn "no DB backup found in $BACKUP_DIR from the last 2 days"
fi

say "== Result: $STATUS =="

# 5. Alert e-mail (Brevo), deduped by signature so a standing issue doesn't
# re-email every run - re-alerts once/day if still unresolved.
if [ "$STATUS" != OK ]; then
  sig=$(grep -E '^(WARNING|FAILED)' "$REPORT" | sort | sha256sum | cut -c1-16)
  last=$(cat "$STATE/last-alert" 2>/dev/null || true)
  if [ "$sig" != "$last" ] || [ -n "$(find "$STATE/last-alert" -mmin +1440 2>/dev/null)" ]; then
    KEY=$(grep -E '^BREVO_API_KEY=' "$VOTSTAY_ENV" | cut -d= -f2- | tr -d '"')
    FROM=$(grep -E '^BREVO_SENDER_EMAIL=' "$VOTSTAY_ENV" | cut -d= -f2- | tr -d '"')
    if [ -n "$KEY" ] && [ -n "$FROM" ]; then
      body=$(python3 -c 'import json,sys; print(json.dumps({
        "sender":{"email":sys.argv[1],"name":"MUST Housing server"},
        "to":[{"email":sys.argv[2]}],
        "subject":"[MUST Housing] server check: "+sys.argv[3],
        "textContent":open(sys.argv[4]).read()}))' "$FROM" "$ALERT_EMAIL" "$STATUS" "$REPORT")
      curl -s -o /dev/null -w 'Alert e-mail: HTTP %{http_code}\n' --max-time 20 \
        -H "api-key: $KEY" -H 'content-type: application/json' \
        -d "$body" https://api.brevo.com/v3/smtp/email
      echo "$sig" > "$STATE/last-alert"
    else
      echo "Alert e-mail skipped: no BREVO_API_KEY/BREVO_SENDER_EMAIL in $VOTSTAY_ENV"
    fi
  fi
fi

[ "$STATUS" = FAILED ] && exit 1 || exit 0
