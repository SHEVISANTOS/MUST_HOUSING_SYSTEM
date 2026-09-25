# Deploy Notes

## Media storage (Cloudflare R2)

Property image uploads used plain local-disk storage (`FileSystemStorage`),
which doesn't persist on Vercel's ephemeral filesystem - images uploaded in
production were never actually retrievable afterwards. Fixed by adding
optional Cloudflare R2 support (S3-compatible, via `django-storages`) in
`config/settings.py`. It's **opt-in via environment variables** - with none
of the `R2_*` vars set, the app falls back to local disk exactly as before
(fine for local dev).

**One-time setup in the Cloudflare dashboard:**
1. R2 → Create bucket (lowercase name, no spaces, e.g. `vot-house-finding-media`).
2. Open the bucket → Settings → **Public Access** → allow it. This gives you
   a public `pub-xxxxxxxx.r2.dev` URL - required so generated image URLs are
   plain, permanent public links rather than short-lived signed ones
   (`querystring_auth` is set to `False` in settings.py on that assumption).
   A custom domain works the same way if you'd rather use one.
3. R2 → Manage API Tokens → create a token with **Object Read & Write**,
   scoped to this bucket if possible. Copy the Access Key ID and Secret
   Access Key immediately - R2 only shows the secret once.
4. Your Account ID is in the R2 dashboard sidebar (also visible in the S3
   API endpoint URL Cloudflare shows you: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`).

**Set these as environment variables** (both locally in `.env` and on the
Vercel project, same pattern as `DATABASE_URL`/`CRON_SECRET`):

    R2_ACCOUNT_ID=<your account id>
    R2_ACCESS_KEY_ID=<from the API token>
    R2_SECRET_ACCESS_KEY=<from the API token>
    R2_BUCKET_NAME=<the bucket name you chose>
    R2_PUBLIC_URL=<the pub-xxxxxxxx.r2.dev host, or your custom domain - no scheme>

Once all five are set, `config/settings.py` automatically switches
`STORAGES["default"]` to R2; leaving any of them blank keeps local disk
storage active. Static files (CSS/JS/whitenoise) are untouched by this -
only media uploads move to R2.

## Tenancy Contract Status & Availability Timeline

Notes for deploying the tenancy/contract feature (models, approval hook,
renewal, daily status sync, and the tenant/landlord/seeker UI built across
this feature's steps 1–7).

## 0. ⚠️ Required Vercel env vars (`.env` is no longer committed)

`config/settings.py` calls `load_dotenv()`, which loads a `.env` file *if
one is present in the working directory*. Until a recent security fix,
`.env` was committed to this repo — so every Vercel deploy cloned it along
with the code, and `load_dotenv()` quietly sourced production's real
`DATABASE_URL` (and `DJANGO_DEBUG=True`) from that committed file. Now that
`.env` is correctly git-ignored, a fresh clone has nothing for
`load_dotenv()` to load, and the build **fails outright**
(`django.core.exceptions.ImproperlyConfigured: settings.DATABASES is
improperly configured`) unless these are set as real environment variables
in the Vercel project (Project → Settings → Environment Variables,
Production scope):

- **`DATABASE_URL`** — required, no fallback. Use the Neon connection
  string (the *rotated* one, if the password exposure was already
  remediated — it should be).
- **`DJANGO_SECRET_KEY`** — has a fallback (`fallback-dev-key-replace-in-
  vercel`), so it won't crash the build, but that fallback is a public,
  hardcoded value. If this isn't already set, generate and set a real one:
  `python -c "import secrets; print(secrets.token_urlsafe(50))"`.
- **`CRON_SECRET`** — see §1 below; not required for the build to succeed,
  but required for the daily status sync to actually run.
- `DJANGO_DEBUG` — no action needed. It now correctly falls back to
  `False` since the committed `.env` (which had it as `True`) is gone.

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
