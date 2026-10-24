# MarineEdge HTTP API

For integrators, scripts and AI agents. Every route lives once in `backend/app/routes.py`; the production server (FastAPI) and the development server (`app/devserver.py`) both dispatch to it. This page describes version **1.0.0**, which `GET /api/health` reports.

## Basics

- Base URL: `https://<your server>/api`. On a laptop with `make dev`: `http://localhost:8080/api`.
- JSON in and out, UTF-8. Every response carries `Cache-Control: no-store`.
- **Units:** times are epoch **milliseconds, UTC**; distances in nautical miles (nm), speeds in knots (kn), draught in metres.
- **Ships are identified by IMO number** (7 digits). Names, flags and MMSI numbers change and are history on the IMO.
- **Errors** come back as an HTTP status plus `{"detail": "…", "code": "…", "field": "…"}`. `detail` is a sentence a person can read, `code` is for programs (may be null), and `field` names the input that was wrong (may be null).

## Signing in

| Caller | How it authenticates | Extra header on POST, PUT, PATCH, DELETE |
|---|---|---|
| People, through the app | The `me_session` cookie set by sign-in: HttpOnly, SameSite=Lax, Secure behind HTTPS, valid 90 days and extended while in use | `X-MarineEdge: 1`, which a form on another site can't send (CSRF protection) |
| Scripts, scheduled jobs, agents | An API token from `API_TOKENS` in the server's `.env` (`name:token[:admin]`, comma-separated), sent as `Authorization: Bearer <token>` or `X-API-Key: <token>` | none |

A session token can also be sent as a Bearer token; then no extra header is needed. Roles are `admin` and `analyst`. Each route below is marked **public**, **user** (any signed-in person or token) or **admin**.

```bash
# a script with an API token
curl -s -H "Authorization: Bearer $MARINEEDGE_TOKEN" "https://tracker.example.com/api/vessels/search?q=silver"
curl -s -H "Authorization: Bearer $MARINEEDGE_TOKEN" "https://tracker.example.com/api/vessels/9000013/analysis?track=0"
```

Never put a token in a URL, a prompt, a test or a commit; keep it in the environment.

**Rate limits** (per server process): sign-in 10 tries per email and 30 per IP address in 15 minutes; sign-up 10 per IP per hour; forgot-password 5 per email and 10 per IP per hour; reset 10 per email and 20 per IP per hour; password change 10 per account per hour. Over the limit: `429`, code `rate_limited`.

### Error codes

| Status | `code` | When |
|---|---|---|
| 400 | `bad_email`, `bad_name`, `weak_password`, `bad_reset`, `bad_role`, `bad_status`, `bad_invite`, or none | Invalid input; `field` says which |
| 401 | `signin` | Not signed in, or the token is unknown |
| 401 | `bad_credentials` | Wrong email or password |
| 402 | `credits` | The paid provider's credits are used up |
| 403 | `csrf` | A cookie request changed something without `X-MarineEdge: 1` |
| 403 | `admin` | The route is for admins |
| 403 | `disabled`, `bad_password`, `bad_setup_code`, `invite_email` | Account turned off; current password wrong; server admin password wrong; invite made for another email |
| 404 | `unknown_imo` | The server has no data for that IMO yet |
| 404 | `not_found` | The session, invite or person no longer exists |
| 405 | — | Wrong method for the path |
| 409 | `exists`, `last_admin` | Email already has an account; the last admin can't be demoted or removed |
| 429 | `rate_limited` | Too many attempts |
| 500 | `server` | Unexpected; logged on the server |
| 502 | `provider` | The AIS provider failed (keys are scrubbed from the message) |

## Accounts — public

| Method and path | Body | Returns |
|---|---|---|
| `GET /health` | — | `{ok, version, provider, auth: "accounts"}` |
| `GET /auth/state` | — | `{setup, inviteOnly, email, minPassword, signedIn}`. `setup: true` means the server has no account yet. `email` says whether email delivery is configured |
| `POST /auth/signup` | `{name, email, password, invite?, setupCode?}` | `{user}` and the session cookie. The first account needs `setupCode` (the server admin password) and becomes an admin; everyone else needs an `invite` code |
| `POST /auth/login` | `{email, password}` | `{user}` and the session cookie |
| `POST /auth/logout` | — | 204, clears the cookie |
| `POST /auth/forgot` | `{email}` | `{ok: true, email}`. It answers the same way whether or not the account exists. With email set up, it sends a 6-digit code (valid 30 minutes) and a link |
| `POST /auth/reset` | `{password, email, code}` or `{password, token}` | `{user}` and a new session cookie. All the person's other sessions end |
| `GET /auth/invite/{code}` | — | `{valid, email, role, expires, invitedBy}` |
| `GET /auth/reset/{token}` | — | `{valid, email, name}` |

A server updated from the earlier token sign-in also accepts, once, `POST /auth/login` with any email and the server admin password: that creates the owner account and keeps what was saved under the old sign-in.

## The signed-in person — user

| Method and path | Body | Returns |
|---|---|---|
| `GET /me` | — | `{user, watchlist, push: {configured, publicKey}, unread, server: {version, source, liveKey, mock, recorder}}`. `recorder` is filled for admins only |
| `PATCH /me` | `{name?, email?, currentPassword?, prefs?}` | `{user}`. Changing the email needs `currentPassword`. `prefs` keys: `theme`, `region`, `timeLocal`, `pushMin` (`high` or `medium`), `introSeen` |
| `POST /me/password` | `{current, password}` | `{ok}`. Other sessions are signed out |
| `GET /me/sessions` | — | Signed-in devices, the current one marked |
| `DELETE /me/sessions/{id}` | — | 204 |
| `POST /me/sessions/revoke-others` | — | `{signedOut: n}` |
| `PUT /me/watchlist` | `{imos: [7-digit numbers]}`, up to 500 | `{watchlist}` |
| `GET /me/watching` | — | `[{imo, name, level, headline, checked, last: {t, lat, lon, sog}}]` |

`user` is `{id, name, email, role, status, created, lastSeen, lastLogin, prefs, initials, color}`.

## Regions, search and ships — user

| Method and path | Query or body | Returns |
|---|---|---|
| `GET /regions` | — | `[{id, name, bbox}]`; ids `blacksea`, `hormuz`, `iran`, `oman`, `uae`; `bbox` is `[minLon, minLat, maxLon, maxLat]` |
| `GET /regions/{id}/overview` | — | `{region, name, bbox, now, counts: {inRange, checked, high, sanctioned}, newest, recorder, source, highest: [live row…], sweep}`. Calling it may start the free background check of ships in range |
| `GET /regions/{id}/vessels` | — | Live rows: every ship heard in the box in the last 6 hours |
| `GET /vessels/search` | `q`: name, former name, IMO or MMSI, at least 2 characters | `[{imo, name, mmsi, flag, type, sub, dwt, built, exNames, matchedFormer, verdict}]`. `verdict` is the last check (`{level, label, headline, checked}`) or null |
| `GET /vessels/{imo}` | — | The ship's particulars (the `vessel` object below) |
| `GET /vessels/{imo}/analysis` | `refresh=1` re-runs it now; `track=0` leaves out the positions | The analysis (below) plus `watching`, `history: {available, provider, bought}`, `sanctionsChecked` (when the lists were last downloaded) and `sanctionsLists` (which lists the server holds) |
| `GET /vessels/{imo}/report.pdf` | — | The PDF report (`application/pdf`) |
| `GET /vessels/{imo}/report.html` | — | The same report as HTML |
| `GET /vessels/{imo}/crosscheck` | — | Global Fishing Watch events for the last 12 months (port visits, loitering, encounters, AIS off). A second opinion, licensed for non-commercial use; `{configured: false}` without a token |
| `POST /vessels/{imo}/history` | — | **admin.** Buys the missing part of the last 12 months from the paid provider (Datalastic) and re-runs the analysis: `{ok, bought, credits, verdict}` or `{ok, already: true}`. Positions are cached for good and never bought twice |

A **live row** is `{imo, name, mmsi, type, sub, flag, lat, lon, sog, cog, t, nav, level, headline, checked, sanctioned, destination?}`. `level` is the last verdict level, forced to `high` when the IMO is on a sanctions list held by the server. Only verdicts written under the rules and zones in force count: after an update to the rules, or an admin's change to a threshold or a zone, `level` and `checked` are null until the ship is checked again.

### The analysis object

```text
vessel       imo, name, mmsi, callsign, flag, type, sub, dwt, gt, loa, beam, built, builder,
             draughtLoaded, draughtBallast, region, exNames[], history[{field, from, to, t}],
             sanctions[{list, programme, t}], regOwner, benOwner, ism, operator, classSoc, pi, speed
track        [{t, lat, lon, sog, cog, draught, nav, src, jump?}]    nav: 0 under way, 1 at anchor, 5 moored
                                                                    src: T terrestrial, S satellite
portCalls    [{port: {id, name, c, b: [lon, lat], zone, pseudo}, anchorage, arrive, depart, lat, lon,
               i0, i1, draughtIn, draughtOut, anchHours}]
voyages      [{n, color, from, to, i0, i1, depart, arrive, nm, draughtOut, draughtIn, current, flags[ids], darkH}]
flags        [{id, key, rule, severity, title, lines[], t0, t1, lat, lon, story: {title, text},
               vesselLevel, hours, voyage, partnerImo, meta, evidence: {before[], after[]}}]
sev          {high, medium, info}                                   counts by severity
status       {state: underway|anchored|moored|unknown, destination, eta, since, port, lastPort, nextPort}
stats        {raw, dup, bad, clean, portCalls, voyages, flags, ms, source, historySince?}
last         the latest position
verdict      {level: high|review|clear|insufficient, label, sentence, detail, meta,
              tiles[{value, label, risk}], historyDays, historyFrom, findings, headline}
positions    number of positions after cleaning
```

- `flags[].key` is stable across re-analysis (rule plus start time); notes and links attach to it. `flags[].id` is positional and changes.
- `flags[].rule` is one of `Sanctions hit`, `Call at a sensitive port`, `AIS gap`, `Draught change at sea`, `Possible ship-to-ship transfer`, `Position jump`, `Identity change`. `severity` is `high`, `medium` or `info`; info items (for example a quiet period outside receiver coverage) are shown but never counted.
- `verdict.sentence`, `verdict.detail` and every `story` are written by fixed rules in `backend/app/verdict.py`, so the app, the PDF and the notifications say the same thing. [METHODOLOGY.md](METHODOLOGY.md) explains how each is chosen.

## Team notes — user

| Method and path | Body | Returns |
|---|---|---|
| `GET /vessels/{imo}/notes` | — | `[{id, imo, scope, text, created, updated, author, mine, canEdit, canDelete}]` |
| `POST /vessels/{imo}/notes` | `{scope, text}`; scope is `ship`, `voyage:<n>` or `flag:<key>`; text up to 4,000 characters | The note |
| `PATCH /notes/{id}` | `{text}` | The note; only its author may edit |
| `DELETE /notes/{id}` | — | 204; the author or an admin |

## Alerts and notifications — user

| Method and path | Body or query | Returns |
|---|---|---|
| `GET /alerts` | `days` (1–90, default 30) | `{items: [{imo, rule, t0, severity, title, detail, created_at, unread}], seen, watching}`; only ships the person watches |
| `POST /alerts/seen` | — | `{ok}`; marks everything up to now as read |
| `POST /push/subscribe` | A Web Push subscription `{endpoint, keys}` | `{ok, configured}` |
| `DELETE /push/subscribe` | `{endpoint}` | `{ok}` |
| `POST /push/test` | — | `{sent}` |

The 30-minute job re-checks every watched ship and stores each new finding as an alert. It pushes the ones at or above the level each watcher chose (High only, or High and Medium); the notification opens the finding (`#/ship/<imo>/finding/<key>`).

## Reference data — user

| Method and path | Returns |
|---|---|
| `GET /geo/zones` | The sensitive zones as GeoJSON, each with `id, name, short, basis, enabled` |
| `GET /geo/ports` | `[{id, name, country, lon, lat, zone, major}]` |
| `GET /rules` | `{rules, overrides}`: the thresholds in force, and which an admin changed |
| `GET /maps` | `{installed, url, attribution}` for the detailed map tiles |

## Administration — admin

| Method and path | Body | What it does |
|---|---|---|
| `GET /admin/config` | — | Everything the admin pages show: provider and masked keys, recorder status, recorded-feed statistics, sanctions status, update gate result, disk, database size, email, maps, zones, push, sweep, version |
| `POST /admin/provider` | `{provider, api_key?}` | Switch the main source: `aisstream`, `datalastic` or `kpler` (`mock` only on a development machine) |
| `POST /admin/key` | `{name, api_key}` | Save or clear (`null`) a key: `aisstream`, `datalastic`, `kpler`, `gfw` |
| `POST /admin/test` | — | One cheap call to the main source: `{ok, provider, matches, sample, credits_used, ms}` or `{ok: false, error}` |
| `POST /admin/first-pull` | `{imos: [up to 10]}` | The acceptance checks for a first paid pull, per ship |
| `GET /admin/team` | — | `{users, invites}` |
| `POST /admin/invites` | `{email?, role}` | `{id, code, link, email, role, expires, emailed}`; the link works once, for 7 days |
| `DELETE /admin/invites/{id}` | — | Revoke an invite |
| `PATCH /admin/users/{id}` | `{role?, status?}` | Change role (`admin`, `analyst`) or turn an account off (`disabled`) or on (`active`) |
| `DELETE /admin/users/{id}` | — | Remove a person; their notes stay, signed "Former member" |
| `POST /admin/users/{id}/reset-link` | — | A password reset link valid 24 hours, for when email isn't set up |
| `GET /admin/email` · `PUT /admin/email` | SMTP settings; `{clear: true}` removes them | Read or save outgoing email (the password comes back masked) |
| `POST /admin/email/test` | `{to?}` | Send a test email |
| `PUT /admin/rules` | `{overrides: {group: {key: number}}}` | Change thresholds (numbers only, 0 to 100,000); stored on the server |
| `DELETE /admin/rules` | — | Back to the defaults in `config/rules.yaml` |
| `POST /admin/zones/{id}` | `{enabled}` | Switch a sensitive zone on or off |
| `GET /admin/maps` · `POST /admin/maps/download` · `DELETE /admin/maps` | `{maxzoom?}` | Status, download or remove the detailed OpenStreetMap extract |
| `POST /jobs/sanctions` | — | Download the OFAC, EU and UK lists now (needs the database) |
| `POST /jobs/refresh` | — | Re-check watched ships now (the 30-minute job) |
| `POST /jobs/sweep` | `{seconds?}` | Check ships in range on the recorded feed for up to `seconds` (default 30); free |

## Changing the API

Add the route once in `backend/app/routes.py` with its auth level, keep JSON shapes in `backend/app/service.py` (or `routes.py`), add a test in `backend/tests/test_routes.py`, call it from `frontend/public/js/api.js`, and update this page.
