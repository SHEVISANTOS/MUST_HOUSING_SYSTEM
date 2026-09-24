# Deploy Notes — Tenancy Contract Status & Availability Timeline

Notes for deploying the tenancy/contract feature (models, approval hook,
renewal, daily status sync, and the tenant/landlord/seeker UI built across
this feature's steps 1–7).

## 1. `CRON_SECRET` environment variable

The daily status sync (`update_tenancy_statuses`) runs via a Vercel Cron
job hitting `/bookings/tasks/update-tenancy-statuses/` (see the `crons`
entry in `vercel.json`, scheduled for 03:00 UTC daily).

That endpoint is protected by a shared secret: it only accepts requests
carrying `Authorization: Bearer <CRON_SECRET>`, and **fails closed** — if
`CRON_SECRET` isn't set, every request is rejected (401), including from
Vercel Cron itself.

**Before this will run in production**, set `CRON_SECRET` as an environment
variable on the Vercel project (Project → Settings → Environment Variables).
Vercel automatically attaches it as the `Authorization: Bearer` header on
every call it makes to a `crons` path — this is Vercel's own documented
convention, nothing custom was built for it. Use a long random value, e.g.:

    python -c "import secrets; print(secrets.token_urlsafe(32))"

Without this set, tenancy statuses will simply never auto-advance
(`upcoming → active → ending_soon → ended`) and bookings won't get
auto-marked `COMPLETED` on their natural end date. Nothing breaks — the
site keeps working, since every status shown to users is computed live
from today's date (`Tenancy.display_status`) regardless of whether the
cron has run. It's a tidiness/reporting job, not a correctness dependency,
with one exception: **Booking → `COMPLETED`** on natural end only happens
via this job, so a booking will stay `CONFIRMED`/`PAID` indefinitely past
its end date until the cron (or the management command) actually runs.

## 2. Migrations 0006 and 0007

- `0006_tenancy.py` — creates the `Tenancy` table + its indexes. Standard
  schema migration, nothing special.
- `0007_backfill_tenancies.py` — a **data migration**: it creates `Tenancy`
  rows for every pre-existing `CONFIRMED`/`PAID` `Booking` that doesn't
  already have one, so tenants/landlords who were already mid-lease before
  this feature shipped show up correctly instead of looking unoccupied.

Both run automatically as part of the existing build — `vercel.json`'s
`buildCommand` already runs `python manage.py migrate` on every deploy, so
**no manual step is required**. If you ever need to run it by hand (e.g.
against a copy of the DB locally):

    python manage.py migrate bookings

The backfill is defensive: it skips (with a printed warning, not a crash)
any legacy booking with missing or nonsensical dates (`end_date <=
start_date`), and it does **not** try to reconcile pre-existing overlapping
bookings for the same property — those can only have existed because there
was no overlap check before this feature. `0007`'s reverse migration is a
no-op by design (removing the backfilled rows on rollback isn't safe once
they may have accrued real renewal/termination history).

## 3. Running `update_tenancy_statuses` manually

Locally, or via any environment with shell access to the deployment:

    python manage.py update_tenancy_statuses

Safe to run repeatedly — it's a no-op for rows that are already up to date,
and prints a one-line summary (`Tenancy statuses updated: N. Bookings
marked COMPLETED: M.`).

To trigger the same logic over HTTP (e.g. to test the cron path, or as a
manual override without shell access) — same auth as Vercel Cron uses:

    curl -H "Authorization: Bearer <CRON_SECRET>" \
      https://<your-domain>/bookings/tasks/update-tenancy-statuses/

## 4. Deferred follow-ups (not built — scoped out during this feature)

- **Notification system with 30/7/0-day reminders.** No `Notification`
  model or email backend exists in this project. What *was* built covers
  the same need passively: every status badge/progress bar is computed
  live from `Tenancy.display_status`, so a tenant/landlord sees accurate
  "ending soon" info the moment they load a page — there's just nothing
  that proactively pushes it to them (email, SMS, in-app inbox) ahead of
  that. Building real reminders needs: an `EMAIL_BACKEND` configured in
  `settings.py` (none exists today), and/or a persisted `Notification`
  model with read/unread state and a bell-icon UI.
- **"Notify me when available"** (seeker-facing, on an occupied listing).
  Depends on the same notification infrastructure above — deferred for the
  same reason.
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
