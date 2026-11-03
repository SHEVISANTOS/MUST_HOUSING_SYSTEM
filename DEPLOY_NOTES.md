# Deploy Notes

## Ubuntu Server Deployment (Gunicorn + Nginx + systemd)

The only deployment target (Vercel and Neon were retired 2026-11-03):
Gunicorn behind Nginx, managed by systemd, with a local Postgres database
and local-disk media storage. Config files referenced below live in `deploy/` and `scripts/deploy_ubuntu.sh`.

This assumes Ubuntu 22.04+, a non-root user with `sudo`, and that you're
deploying from a git clone of this repo. Paths below assume the app lives at
`/srv/must_housing`, run as the `santos` user, and that nginx listens on
**port 8080** rather than 80/443 - adjust `deploy/vot-house-finding.service`,
`deploy/vot-tenancy-sync.service` and `deploy/nginx_vot_house_finding.conf`
if you use a different path/user/port.

If this server already hosts another app (e.g. its own nginx site on
80/443, like this deployment does alongside "VOT Stays"), do **not** touch
that app's nginx config, systemd services, firewall rules for 80/443, or
database - everything below is scoped to this app only, using its own port
(8080), its own systemd unit names (`vot-house-finding*`), and its own
Postgres database/user.

### 1. System packages

Skip anything already installed (check with e.g. `nginx -v`, `psql --version`):

    sudo apt update
    sudo apt install -y python3-venv python3-pip postgresql postgresql-contrib \
        nginx git build-essential libpq-dev

### 2. Get the code onto the server

    sudo mkdir -p /srv/must_housing
    sudo chown "$USER":www-data /srv/must_housing
    git clone <your-repo-url> /srv/must_housing
    cd /srv/must_housing

### 3. Local Postgres database

    sudo -u postgres psql -c "CREATE USER vot_user WITH PASSWORD 'choose-a-strong-password';"
    sudo -u postgres psql -c "CREATE DATABASE vot_house_finding OWNER vot_user;"

### 4. Python environment

    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

### 5. Configure `.env`

Create `/srv/must_housing/.env` (git-ignored, never committed - see
`.env.example` for the full list of variables):

    DJANGO_SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_urlsafe(50))">
    DJANGO_DEBUG=False
    DATABASE_URL=postgresql://vot_user:choose-a-strong-password@localhost:5432/vot_house_finding

    # No domain yet - allow the server's bare IP. Add a domain here too once
    # one is pointed at this server (both can be listed, comma-separated).
    DJANGO_ALLOWED_HOSTS=<your-server-ip>
    CSRF_TRUSTED_ORIGINS=<your-server-ip>

`DJANGO_ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` are additive on top of the
hardcoded local-network defaults in `config/settings.py`.

### 6. Migrate, collect static, create an admin user

    python manage.py migrate
    python manage.py collectstatic --noinput
    python manage.py createsuperuser

### 7. Gunicorn as a systemd service

    sudo cp deploy/vot-house-finding.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now vot-house-finding
    sudo systemctl status vot-house-finding

Edit the `User=`/paths in `/etc/systemd/system/vot-house-finding.service`
first if your user or install path differs from the defaults above.

### 8. Daily tenancy status sync

Run the `update_tenancy_statuses` management command daily on a timer:

    sudo cp deploy/vot-tenancy-sync.service deploy/vot-tenancy-sync.timer /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now vot-tenancy-sync.timer
    sudo systemctl list-timers vot-tenancy-sync.timer

### 9. Nginx

This only adds a new site on port 8080 - it does not touch whatever's
already in `sites-enabled` for other apps on this server (no `default` site
removal, no edits to existing site files):

    sudo cp deploy/nginx_vot_house_finding.conf /etc/nginx/sites-available/vot-house-finding
    sudo ln -s /etc/nginx/sites-available/vot-house-finding /etc/nginx/sites-enabled/
    sudo nginx -t && sudo systemctl reload nginx

### 10. Firewall

If `ufw` is already managing this server's firewall (check with
`sudo ufw status`), just add the new port - don't re-run `ufw enable` or
touch existing rules:

    sudo ufw allow 8080/tcp

### 11. Verify

Visit `http://<your-server-ip>:8080/` - you should see the property listing
page. `/admin/` should log in with the superuser created in step 6.

### 12. Redeploying after future changes

    /srv/must_housing/scripts/deploy_ubuntu.sh

Pulls the latest code, reinstalls dependencies, migrates, collects static
files, and restarts Gunicorn. Requires passwordless (or prompted) `sudo` for
the `systemctl restart` step.

### 13. Nightly backup (local Postgres + local media)

A local database has no managed point-in-time recovery -
`deploy/backup/must-housing-backup.sh` is the only backup this data gets.
It `pg_dump`s the local database and tars `media/`, writing timestamped,
checksummed files to `/var/backups/must_housing/` with a 7-day retention (`BACKUP_KEEP_DAYS`). Optional off-site copy via
`BACKUP_S3_URI` (same convention as `VOT-Stay/deploy/backup/backup.sh`).

    sudo cp deploy/must-housing-backup.service deploy/must-housing-backup.timer /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now must-housing-backup.timer
    sudo systemctl list-timers must-housing-backup.timer

To test it immediately rather than waiting for 02:45:

    sudo systemctl start must-housing-backup.service
    sudo journalctl -u must-housing-backup -n 20 --no-pager

### 14. Health monitoring + email alerts

`deploy/monitor/must-housing-monitor.sh` runs every 3 hours: checks
`nginx`/`postgresql`/`must-housing` are active, hits `/healthz` (confirms
the DB is actually reachable, not just that Gunicorn accepted the TCP
connection), checks the TLS cert isn't expiring within 14 days, and checks
a DB backup exists from the last 2 days. On any problem it emails
`shevijeremiah@gmail.com` via Brevo, **reusing VOT-Stay's existing Brevo
API key** (`/home/santos/VOT-Stay/.env`) rather than provisioning a second
account - same convention `votstay-sshdigest.sh` already uses. Deduped so
a standing issue re-alerts once/day instead of every run.

This is monitor-and-alert only - unlike `votstay-autoupdate.sh`, it does
**not** auto-pull code or auto-restart anything; deploys here stay a
manual step (`scripts/deploy_ubuntu.sh` or the manual sequence in step 12).

    sudo cp deploy/must-housing-monitor.service deploy/must-housing-monitor.timer /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now must-housing-monitor.timer

To test it immediately:

    sudo systemctl start must-housing-monitor.service
    sudo journalctl -u must-housing-monitor -n 40 --no-pager

**Naming note:** this server's actual live systemd service is named
`must-housing` (not `vot-house-finding` as the rest of this doc assumes) -
a holdover from before the project was renamed from "MUST Housing System"
to "VOT House Finding". The backup/monitor units above were written to
match what's actually running. If you're deploying fresh to a new server
following steps 1-12 above, swap `must-housing` for `vot-house-finding` in
`deploy/must-housing-backup.service`, `deploy/must-housing-monitor.service`
and the `SERVICE=` line in `deploy/monitor/must-housing-monitor.sh`.

### Adding HTTPS later (once a domain is pointed at this server)

Pick a domain/subdomain distinct from whatever other apps on this server
already answer to (e.g. `housing.yourdomain.com`), point its DNS A record
at the server, then switch `deploy/nginx_vot_house_finding.conf` from
`listen 8080;`/`server_name _;` to `listen 80;`/`server_name housing.yourdomain.com;`,
reload nginx, and run certbot:

    sudo apt install -y certbot python3-certbot-nginx
    sudo certbot --nginx -d housing.yourdomain.com

Certbot edits the Nginx config in place to add the TLS block and redirect.
Afterwards, add the `https://housing.yourdomain.com` origin to
`CSRF_TRUSTED_ORIGINS` in `.env` and restart the service.

## Media storage (local disk only)

User uploads (property photos, payment proofs, profile pictures) are stored
on local disk under `MEDIA_ROOT` (`media/`) via `FileSystemStorage`, served
by nginx's `location /media/` block. Cloudflare R2 support was removed
(2026-11-03); any leftover `R2_*` env vars are ignored.

Uploads go through `config/uploads.py`: JPG/PNG/WEBP only, max 10 MB, saved
under a random UUID filename (`RandomName`) rather than the original name.

## Tenancy Contract Status & Availability Timeline

Notes for deploying the tenancy/contract feature (models, approval hook,
renewal, daily status sync, and the tenant/landlord/seeker UI built across
this feature's steps 1–7).

## 1. Migrations 0006 and 0007

- `0006_tenancy.py` — creates the `Tenancy` table + its indexes. Standard
  schema migration, nothing special.
- `0007_backfill_tenancies.py` — a **data migration**: it creates `Tenancy`
  rows for every pre-existing `CONFIRMED`/`PAID` `Booking` that doesn't
  already have one, so tenants/landlords who were already mid-lease before
  this feature shipped show up correctly instead of looking unoccupied.

Both are applied by the `migrate` step of every deploy
(`scripts/deploy_ubuntu.sh`). If you ever need to run it by hand (e.g.
against a copy of the DB locally):

    python manage.py migrate bookings

The backfill is defensive: it skips (with a printed warning, not a crash)
any legacy booking with missing or nonsensical dates (`end_date <=
start_date`), and it does **not** try to reconcile pre-existing overlapping
bookings for the same property — those can only have existed because there
was no overlap check before this feature. `0007`'s reverse migration is a
no-op by design (removing the backfilled rows on rollback isn't safe once
they may have accrued real renewal/termination history).

## 2. Running `update_tenancy_statuses`

The server's crontab runs this daily at 03:00. To run it by hand:

    python manage.py update_tenancy_statuses

Safe to run repeatedly — it's a no-op for rows that are already up to date,
and prints a one-line summary (`Tenancy statuses updated: N. Bookings
marked COMPLETED: M.`).

If it stops running, nothing visibly breaks (every status shown to users is
computed live from `Tenancy.display_status`), with one exception: a
Booking only becomes `COMPLETED` on its natural end date via this job, so
it would stay `CONFIRMED`/`PAID` past its end date until the job runs.

## 3. Deferred follow-ups (not built — scoped out during this feature)

- **30/7/0-day tenancy reminders.** In-app notifications exist
  (`apps/notifications`, bell icon) for booking/payment/verification
  events, but nothing yet creates a notification ahead of a tenancy ending,
  and there's no email/SMS delivery (no `EMAIL_BACKEND` configured).
- **"Notify me when available"** (seeker-facing, on an occupied listing).
  Could now build on `apps/notifications`; not built yet.
- **`INSTALLED_APPS` (`'bookings'`) vs `AppConfig.name` (`'apps.bookings'`)
  mismatch.** Documented in detail in `config/settings.py` right at the
  `sys.path.insert(...)` line, and in `apps/bookings/apps.py`'s `ready()`.
  This already caused one real failure during this feature (a relative
  import in `ready()` tried to load `Booking` a second time under a
  different module identity) and was worked around locally with absolute
  imports — but the underlying inconsistency is still there for all 4 apps
  and could bite the same way again. Proper fix is one of: drop the
  `sys.path` hack and use `apps.X` everywhere, or rename every
  `AppConfig.name` to match its short `INSTALLED_APPS` entry. Either way
  it touches all 4 apps, so it wasn't done as a side effect of this feature.
- **A `Unit`/`Room` model.** This feature was built against the current
  reality that `Property` *is* the bookable unit — there's no multi-room
  breakdown per listing. The spec's "3 of 5 rooms occupied" style seeker
  messaging was scoped out for that reason; every badge/timeline here is
  binary (this property is occupied-until-X or free). Introducing a real
  `Unit` model would be a separate, larger feature — it'd change what
  `Booking`/`Tenancy` point at (property vs. unit), which is a much bigger
  change than what's additive/minimal here.
- **Whether tenants should be able to cancel mid-contract.** Worth calling
  out explicitly: there is currently **no tenant-facing view to cancel an
  already-approved booking** at all (only `reject_booking`, landlord-only
  and PENDING-only, and the landlord's own `terminate_tenancy`). The
  cancellation signal (`apps/bookings/signals.py`) is already written to
  handle it correctly whenever such a path exists — it terminates the
  `Tenancy` and frees the property automatically off any `Booking` save
  with `status='CANCELLED'`, regardless of which view sets that. Adding a
  tenant-facing "cancel my booking" action is mostly a UI/policy decision
  (should it require landlord approval? a notice period? a fee?) rather
  than a technical one — the plumbing is already there.
