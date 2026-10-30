# Sewa Setu — Old Age Pension Portal

Department of Social Welfare, Government of Purvanchal. Maintained in-house.

## Running

On a fresh checkout, copy `app/config/app.ini.example` to `app/config/app.ini`.
The real INI and private environment files are intentionally excluded from Git.
For the free hosted deployment, follow [the Render/Supabase instructions](deploy/RENDER.md).

```
ADMIN_PASSWORD=pick-something docker compose up --build
```

- Portal: http://localhost:8000
- Status portal: http://localhost:8000/status (mobile number + password; the
  password is the applicant's date of birth as DDMMYYYY)
- Departmental login: http://localhost:8000/admin (user `admin`, password from
  `ADMIN_PASSWORD`)
- SMS gateway console (simulated telecom): http://localhost:8000/__gateway/ —
  OTPs and notifications appear here once "delivered" (1–4 s carrier latency).
  The gateway's inbox is also readable as JSON at
  `/__gateway/api/messages?to=<mobile>`.
- Database: Postgres, loaded from `seed/seed.sql` on first boot (~100k applications).

## Deploying on a server

Set `PUBLIC_BASE_URL` to the address people will use (for example
`https://sewasetu.example.in`). It is stamped into sign-in tokens and the discovery documents
described below, so a wrong value means other applications cannot find the sign-in page. Put
the portal behind HTTPS; some applications refuse to sign in over plain HTTP.

```
PUBLIC_BASE_URL=https://sewasetu.example.in SECRET_KEY=replace-with-a-random-secret-of-at-least-32-characters ADMIN_PASSWORD=pick-something-private docker compose up --build -d
```

## What the portal does

Citizen flow: mobile → OTP → personal details → address → bank details →
age-proof upload → preview and declaration → application number. A nightly
job (`scripts/deemed_approval.py`, via cron in the `scheduler` container)
deems approved any application still pending after the 15-day statutory SLA.

Rules enforced at submission, in `validate_application()` in `app/app.py`:
applicant is 60 years of age or above; required fields and an age-proof
document are present; the scheme window is open; and the mobile number holds
no other active (pending / approved / deemed-approved) application. A pending
application can be withdrawn from the status portal, after which the same
mobile may apply again.

Departmental users see a dashboard, list and filter applications, approve or
reject pending ones, and see the audit trail per application.

## Layout

```
app/          Flask application, templates, config, nightly job
seed/         seed.sql — production data snapshot
smsgw/        simulated SMS gateway
```

## Letting other applications act for a citizen or an officer

Sewa Setu is also an **OAuth 2.1 authorization server**. A third-party application can act
for a citizen (scope `citizen`) or for a block officer (scope `officer`) once that person
signs in on the portal and approves it. Citizens sign in by mobile and OTP, officers with the
departmental login. The application never handles the OTP or the password.

- Discovery: `/.well-known/oauth-authorization-server` (RFC 8414)
- Registration: `/oauth/register` (RFC 7591), or a client ID metadata document URL as `client_id`
- Authorization: `/oauth/authorize` (authorization code with PKCE S256; the `resource` the
  application asks for becomes the token's audience, RFC 8707)
- Tokens: `/oauth/token`. Access tokens are RS256 JWTs. A sign-in is a **session with an
  absolute end**: 2 hours for a citizen, 8 hours for an officer, counted from the consent.
  Access tokens are short (20 / 30 minutes) and refresh tokens rotate within the session but
  never extend it; after it ends the person signs in again. Portals are used on shared phones
  and kiosks.
- Sign-out: `/oauth/revoke` (RFC 7009). People can also end any sign-in from the status
  portal (**Connected applications**) or, for officers, the admin dashboard.
- Keys: `/.well-known/jwks.json`

A service that receives one of these tokens verifies it with the JWKS, checks `iss` is this
portal, checks `aud` is its own canonical URL, and reads `scope`, `role` and `sub`
(`citizen:<mobile>` or `officer:<username>`).

Long-lived **program tokens** for unattended use (role officer) are issued by an
administrator at `/admin/tokens`.

## Citizen MCP (Stage 3)

Streamable HTTP endpoint: `http://localhost:8000/mcp/citizen` locally, or
`<PUBLIC_BASE_URL>/mcp/citizen` on deployment. The official MCP SDK and existing Flask
portal share one listener through `uvicorn gateway:app`. The separate Officer MCP is
described below.

The five tools are `get_scheme_info`, `prepare_application`, `submit_application`,
`get_my_applications`, and `withdraw_application`. They use the existing shared pension
services and database. The deadline remains **31 October 2026 at 23:59 IST**.

Use an OAuth-capable Streamable HTTP client. A request without a token receives a
discovery challenge for `/.well-known/oauth-protected-resource/mcp/citizen`. The client
registers with the existing OAuth server, requests scope `citizen` and resource equal to
the exact MCP URL, then opens the portal's citizen OTP/consent pages. Do not enter OTPs
or passwords into the assistant. Officer, program, wrong-audience and expired tokens are
not accepted at this endpoint.

`CITIZEN_MCP_BLOCKS` is a comma-separated allowlist, default `Sonari,Rajapara`. Both were
verified in the seed database; startup rejects unknown or absent blocks. The ordinary
portal continues supporting all six blocks. Optional `CITIZEN_MCP_ALLOWED_ORIGINS` adds
trusted browser-client origins to the default same-origin policy; server-side/native
clients normally send no Origin header and do not need this setting.

The assistant prepares details, supplies an expiring browser upload link, then refreshes
the preview after upload. Open the link **in the browser used for OAuth sign-in**. The
link alone does not establish ownership. Review the exact preview/declaration before
explicitly accepting it. Use the returned finish-sign-in link on a shared phone or kiosk.
Finishing, revoking, or expiring the session immediately disables citizen MCP access.

Existing databases must receive `app/migrations/001_application_uniqueness.sql` and
`app/migrations/002_citizen_agent.sql` before starting this version; initialization SQL
does not rerun on persistent volumes. Fresh databases include both changes in schema.sql.
The development run commands and full verification results are in `dev/STAGE3.md`.

Public startup requires HTTPS `PUBLIC_BASE_URL`, a random private `SECRET_KEY` of at least
32 characters, and a nondefault `ADMIN_PASSWORD`. Keep the issuer URL and MCP audience
stable. The simulated SMS inbox requires officer browser login by default. The isolated
localhost-only development configuration explicitly enables its test console; do not
enable `ENABLE_LOCAL_SMS_CONSOLE=1` on a public deployment. Actual SMS delivery still
uses the provided simulation, so evaluators need authorized access to that console or a
real SMS integration before public citizen login is practical.

## Officer MCP (Stage 4)

Streamable HTTP endpoint: `<PUBLIC_BASE_URL>/mcp/officer` (locally
`http://localhost:8000/mcp/officer`). Its registry contains only `get_queue_summary`,
`list_applications`, `get_application`, and `decide_application`. Connect with an OAuth
client requesting scope `officer` and this exact resource URL. The officer signs in using
departmental credentials on the existing portal consent flow; the assistant never handles
the password. Citizen tokens, program tokens and tokens for other audiences are rejected.

The endpoint has its own resource discovery document at
`/.well-known/oauth-protected-resource/mcp/officer`, verifier, transport manager and tool
registry. Both MCPs use the same `CITIZEN_MCP_BLOCKS` allowlist (default Sonari,Rajapara).
`OFFICER_MCP_ALLOWED_ORIGINS` optionally adds trusted browser-client origins. The existing
departmental web portal retains its original global administrator access.

Officer sign-ins retain 30-minute access tokens and an absolute eight-hour session with
refresh rotation and immediate session revocation. A reconnect is required for old
officer tokens issued without the MCP session reference. The portal still has one
environment-configured departmental account; this does not create individual staff accounts.

Decision flow:

1. Inspect the case with `get_application` and review available proof in the OAuth browser.
2. Call `decide_application` with the review token, decision and reason, `confirmed=false`.
3. Show the exact returned preview to the officer and obtain explicit confirmation.
4. Call again with the same arguments, `confirmed=true` and its `confirmation_token`.

Review/confirmation expires within ten minutes and is bound to the officer sign-in and
case snapshot. Modified reasons/cases, expired sessions, unsupported blocks and terminal
statuses are rejected. The shared decision service records the authenticated officer,
reason and audit atomically. Results mask mobile/bank account numbers; document URLs are
expiring, browser-authenticated attachments. End the sign-in using the returned finish link.

Before starting this version against an existing database, apply migrations 001, 002 and
`app/migrations/003_officer_agent.sql` in order. Fresh schema.sql includes all definitions.
See `dev/STAGE4.md` for full verification, changes and deployment limitations. The
evaluation dashboard is not implemented yet.
