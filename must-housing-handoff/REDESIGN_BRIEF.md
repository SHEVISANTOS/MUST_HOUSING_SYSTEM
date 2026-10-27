# MUST Housing redesign: implementation brief for Claude Code

Read this file fully before changing anything. Work one phase at a time. After each phase:
run migrations, run the tests, check every changed page at 360px and 1280px, list the files you
changed with a one-line reason, then STOP and wait for approval.

## Rules
- Minimal, targeted edits. Do not rename or restructure working code unless a step says so.
- Keep all existing URLs working. Keep Bootstrap loaded until no template uses it.
- New CSS goes only in `static/css/tokens.css` and `static/css/components.css` (classes prefixed `vh-`).
- Icons: inline the sprite from `static/icons/sprite.svg` once in `base.html`, then
  `<svg class="vh-icon" aria-hidden="true"><use href="#i-NAME"></use></svg>`. No emoji as icons.
- Accessibility: real buttons/links, visible labels, `aria-invalid` + `aria-describedby` on errors,
  44px touch targets, inputs 16px, visible focus ring.
- Money: always `TZS {{ value|floatformat:0|intcomma }}`.
- Never commit secrets. Never print `.env` values.

## Design tokens (from tokens.css)
forest-700 #176B52 (primary) · forest-800 #11533F (hover) · leaf-100 #D9EFE4 (selected)
ink-900 #172A25 (text) · ink-600 #4D5C57 (secondary) · line-200 #DCE4DC · paper-50 #F7F8F3 (page)
clay-600 #B8432F (danger). Status pairs: success #11533F/#D9EFE4, warning #7A5200/#FFF4D6,
info #1D4F7A/#E3EEF9, danger #9C3422/#FBE4DF, neutral #3F4B47/#EEF1EE.
Fonts: Manrope 700/800 (headings, prices), DM Sans 400-700 (text).

## Navigation
- Visitor/tenant: top bar on desktop; bottom tab bar on phones
  (Visitor: Search, Saved, Messages, Sign in. Tenant: Search, Saved, My home, Messages, Account).
- Landlord: green sidebar on desktop (Overview, Properties, Requests, Tenants, Payments, Messages,
  "Add property" button); bottom tabs on phones (Overview, Properties, Requests, Messages, Payments).
- Admin: dark ink sidebar (Overview, Verification, Reports, Users, Properties, Bookings & payments, Exports).
- `/` shows search to visitors; signed-in dashboard moves to `/home/`.
- Breadcrumbs show page titles, never URL names.

## Phase 0: security (do first, alone)
1. `apps/users/forms.py`: `role` choices = TENANT and LANDLORD only. Add a test that posting
   `role=ADMIN` to register fails.
2. `templates/properties/detail.html`: remove the hard-coded Google Maps key; read it from settings
   (`GOOGLE_MAPS_API_KEY` from env) or switch the map to Leaflet + OpenStreetMap. Tell me to rotate the old key.

## Phase 1: look + search (~15 dev-days)
1. Copy `css/`, `icons/` into `static/`; load tokens.css + components.css in base.html after Bootstrap.
2. Build the shells (consumer top bar + tab bar; landlord/admin sidebar) in base.html using `vh-` classes.
3. Search (`properties/list.html` + `property_list` view): search bar, quick chips (Near MUST,
   budget, Available now, type), sort (Recommended, Lowest price, Nearest, Newest), 20 per page,
   search also over `location`, filters in a bottom sheet on phones / side sheet on tablet.
4. Listing card: use `templates/_listing_card.html` (photo first, availability badge from
   `get_current_tenancy`, price largest).
5. Listing detail: gallery, 4 key facts, description, amenities, availability bar, approximate map
   until approved, landlord card, similar places; sticky price + "Request to book" bar on phones,
   sticky side card on desktop.
6. Migrations: `Property.status` (draft/in_review/live/paused/let, backfill from `is_available`),
   `min_months`, `max_months`, `months_per_payment`, `distance_to_campus_km` (computed from lat/lng
   on save; MUST main gate coordinates in settings). Add landlord Edit and Pause for a property.

## Phase 2: book + pay (~15 dev-days)
1. Booking: 3 steps (move-in date + months stepper with live total → review + optional note → sent
   with "what happens next"). Replace the move-out date input; compute move-out from months.
   Inline conflict message using `Tenancy.available_from` with a "Use {date}" button.
2. `Booking.note`, `Booking.expires_at` (created + 48h), `Booking.decline_reason`; approving one
   request auto-declines overlapping PENDING ones with a message.
3. Pay screen: amount + due date, method choice, landlord number with Copy, transaction code,
   optional screenshot, status timeline (Submitted → Landlord checks → Receipt).
   `Payment.rejection_reason` for "Not received" → tenant can fix the code.
4. `SavedProperty` model + heart button + Saved page.
5. Sign-up: role cards, phone required + SMS code verification (ask me which SMS gateway first).

## Phase 3: messaging (~10 dev-days)
`Conversation(property, tenant, landlord, booking nullable)` + `Message(conversation, sender, body,
created_at, read_at)`. Inbox, thread with listing context, quick replies, unread counts.
Landlord phone and exact address shown only after a booking is CONFIRMED.

## Phase 4: workspaces (~10 dev-days)
5-step add/edit property wizard with autosave (Basics, Photos, Location, Rent & availability,
Review). Landlord overview "Needs your attention" queue. Admin verification + reports queue.
Restyle the standalone login page with the same tokens.

## Copy rules
Short, plain, second person. "Request to book" (not "Book now"), "Ask a question",
"I have paid", "Approve / Decline", "Yes, I received it / Not received". Every empty or error
state says what happened and offers one next step.
