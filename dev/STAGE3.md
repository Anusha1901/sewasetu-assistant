# Stage 3: Citizen MCP Server

Completed locally on 27 October 2026. The application is running in the existing isolated
`sewasetu-stage1-dev` Compose project. No officer MCP, evaluation dashboard, AI model API,
additional database or additional container/service was introduced.

Citizen endpoint: **http://localhost:8000/mcp/citizen** (Streamable HTTP).
Portal: **http://localhost:8000/**.

## Implemented tools

| Tool | Behavior |
| --- | --- |
| `get_scheme_info` | Configured deadline, age/SLA, supported blocks, document requirements, masked identity and browser finish-sign-in link |
| `prepare_application` | Accepts partial details, creates/updates a session-owned preparation, calls shared validation, returns preview/errors/revision and an upload link |
| `submit_application` | Requires the current revision and an explicit boolean declaration acceptance; calls the shared submission function and records acceptance atomically |
| `get_my_applications` | At most 20 own cases in supported blocks, status/reason, masked bank information and authorized acknowledgment links; cursor pagination |
| `withdraw_application` | Requires explicit confirmation, checks ownership/block, invokes the existing pending-only withdrawal service |

The SDK advertises exactly these five tools. No tool accepts a mobile as identity, OTP,
password, document filesystem path or arbitrary document URL. Details are a typed,
bounded object; unknown fields such as `details.mobile` are rejected. Application IDs
and preparation IDs are always checked against the verified identity/session.

## Shared services and duplicate protection

Eligibility, normalization, deadline checks, active-application checks, submission,
withdrawal and audit insertion remain in `services.py`. `submit_application` now accepts
an optional caller-owned database cursor, so the citizen preparation's completion and
the actual application/account/audit commit in one transaction. Its existing standalone
transaction interface is preserved for the web portal.

A preparation row is locked during submission. A retry of the same preparation/revision
returns its original application number. A different preparation for the same mobile
still meets the existing unique active-mobile constraint. Changes to details or uploaded
proof increment the revision; stale preview acceptance is rejected. Declaration acceptance
is recorded with its timestamp and application ID. Notifications are sent after commit.
`list_citizen_applications` is the added shared owner-filtered history query.

The original seed, `app/config/app.ini`, deemed-approval script and crontab retain their
original SHA-256 hashes. Minimum age 60, deadline 31 October 2026 at 23:59 IST and 15-day
deemed approval are unchanged. No runtime deadline override or clock change was added.

## Blocks

Before implementation PostgreSQL returned Sonari **16608** rows and Rajapara **16751**
rows, including retained development fixtures. The default agent allowlist is
`CITIZEN_MCP_BLOCKS=Sonari,Rajapara`. The server verifies configured names against both
the portal's block list and existing database data at startup. Empty/unknown/absent
block configurations fail startup. The ordinary portal retains all six blocks.

Agent preparation, submission, upload, status listing, acknowledgment and withdrawal
are restricted to the configured subset. A changed allowlist is checked again when a
previously prepared application is submitted.

## OAuth, authorization and shared devices

The official Python MCP SDK, pinned to **1.26.0**, supplies Streamable HTTP and bearer
middleware. The existing Flask OAuth server continues issuing the credentials.

1. An unauthenticated MCP request receives HTTP 401 and `WWW-Authenticate` pointing to
   `/.well-known/oauth-protected-resource/mcp/citizen`.
2. Resource metadata identifies the exact resource URL and the existing authorization
   server. The issuer spelling is kept exact, avoiding an added root slash.
3. The client discovers the existing OAuth metadata, dynamically registers, requests
   scope `citizen` and the exact citizen MCP resource, and opens portal login/consent.
4. The citizen enters the OTP on the portal browser page. The assistant never receives it.
5. Every MCP request verifies RS256 signature, key ID, issuer, exact audience, expiry,
   citizen role/scope/subject, token kind, client binding, session ID and absolute end.

Citizen MCP grants have a persistent session ID (`sid`) and use the same 20-minute access
token / two-hour absolute session design. Refresh rotates within that session. The SDK
transport is stateless across requests; it does not retain a shared user identity in
process memory. Drafts are isolated by subject **and sign-in session**, including separate
sign-ins for the same mobile. User data is in Postgres, not browser draft cookies.

Revocation, the existing Connected applications action, and the new finish-sign-in
browser action revoke the associated citizen session. Subsequent requests with an old
access token fail immediately. In-flight operations already authorized are not canceled.
Legacy non-MCP JWTs retain their original expiry behavior.

OAuth login requests are bound to the browser that initiated them. Successful citizen
OAuth login replaces prior portal/admin/form identity in that browser. OAuth OTP use is
consumed atomically; verification attempts are bounded per authorization request. A send
limit applies to outstanding OTPs. This is not a comprehensive rate-limiting rewrite of
the legacy portal.

At shared devices, tools display the verified mobile's last four digits, explain the
portal's one-active-application-per-mobile limitation, and return a finish-sign-in link.
Finishing revokes that assistant grant and clears the browser portal session. To act for
another mobile, reconnect and complete a fresh OTP login. People sharing one mobile still
share the portal's mobile-based identity; this does not introduce person-level accounts.

Signing-key initialization now takes a Postgres advisory lock so all workers select one
key on a fresh database. A real concurrent initialization test covers this startup case.

## Browser proof and acknowledgment flow

- Preparation returns a random 256-bit upload capability. Only its SHA-256 hash is
  stored in the database. It expires after 15 minutes or the session end, whichever is first.
- The link also requires the browser identity proved during citizen OAuth login. A copied
  link without the correct browser cookie is denied. If a different browser/profile was
  used, reconnect the assistant and open the link in the same OAuth browser.
- Upload forms use CSRF tokens and a bounded multipart body before parsing. Files must
  be nonempty and no larger than 5 MB. Extension and actual file content must match.
- JPEG/PNG files are parsed and verified with Pillow, with a pixel-count bound. PDF files
  are parsed with pypdf, unencrypted, at most 100 pages, and checked for selected active
  content. Ordinary page-opening destinations are accepted.
- Storage names are server-generated; uploaded filenames cannot choose paths. Files are
  stored privately under the existing uploads volume. Tool responses do not expose paths.
- Successful upload consumes its link and increments the preparation revision. The assistant
  must refresh the preview before submitting. Submitted preparations cannot accept new uploads.
- Acknowledgments use separate expiring owner/session-bound links and are sent as PDF
  attachments. They call the portal's existing acknowledgment generator.
- Browser handoffs use no-store, no-referrer, nosniff and a restrictive CSP.

File checks do not establish document authenticity and are not antivirus scanning. Expiry
prevents access; expired unsubmitted preparation rows/files are not yet physically purged.
Retention/cleanup, including replaced proofs, remains a decision before public operation.

## Serving and deployment

`gateway.py` serves the SDK's routes with the existing Flask app mounted as the WSGI
fallback. Docker starts `uvicorn gateway:app` with four workers on port 8000. There is no
HTTP proxy loop or forwarding of citizen bearer tokens to another resource server.
Blocking database work runs in worker threads. All workers share the existing Postgres
and upload volume.

Transport Host/Origin checks remain enabled. `PUBLIC_BASE_URL` determines the canonical
issuer/resource and allowed public host. `CITIZEN_MCP_ALLOWED_ORIGINS` can add trusted
browser-client origins; native/server clients without Origin headers work normally.
Use an origin such as `https://client.example`, without a path.

Public configuration requires HTTPS, a private random SECRET_KEY of at least 32 characters,
and a nondefault ADMIN_PASSWORD. Startup also refuses the local anonymous SMS-console
flag for a public issuer. Do not rely on the localhost defaults on a public VM.

The gateway console is officer-authenticated by default. The isolated development file
explicitly enables anonymous simulated inbox access **only in its localhost-bound setup**
to preserve the original tests. This flag is not forwarded by the original deployment
Compose file. Neither SDK tools nor browser handoff responses expose OTPs/passwords.

### Database migration and local commands

Migration 001 from Stage 2 and new migration 002 must be applied explicitly to an existing
database before this version starts. Fresh databases receive the same definitions in
schema.sql. Migration 002 adds sessions, preparations, hashed handoff capabilities and
the refresh-token session reference to the same portal database. It does not modify
applications, seed content, eligibility or deadlines.

```powershell
Get-Content -Raw app/migrations/002_citizen_agent.sql | docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml exec -T db psql -v ON_ERROR_STOP=1 -U sewasetu -d sewasetu
docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml up --build -d
```

Credentials remain in ignored `dev/.env.local`. No password, OTP, bearer token, refresh
token or signing key was written into the test result files. HTTP access logging is
disabled for the listener to avoid recording capability paths.

## Verification

**188 final suite checks passed; zero final failures.** The original **119** are included,
not replaced: 28 original unit/integration tests plus 76 original workflow checks plus
15 original persistence checks. There are 21 added unit/integration tests and 48 added
client-protocol checks.

| Suite | Passed | Evidence |
| --- | ---: | --- |
| Unit + real Postgres integration tests | 49 | `stage3-unit-integration.txt` |
| Existing portal/OAuth workflows | 76 | `stage3-regression-main.jsonl` |
| Existing full-stack restart/persistence checks | 15 | `stage3-regression-persistence.jsonl` |
| Real OAuth + browser upload + official Streamable HTTP client | 45 | `stage3-mcp-results.jsonl` |
| Official SDK automatic discovery/DCR/PKCE, refresh and revocation | 3 | `stage3-oauth-client-results.jsonl` |

Coverage includes success, invalid details, unsupported blocks, missing/invalid/expired
proof, CSRF, link ownership, stale previews, strict declaration acceptance, repeated and
concurrent submissions, wrong identity/role/scope/audience/issuer, token/session expiry,
revocation/sign-out, status privacy and confirmed withdrawal. The officer endpoint was
confirmed absent. No model API was used: protocol tests use a real official SDK client;
browser interactions are automated HTTP sessions simulating the human login/upload.
This is not a claim of a manual Claude/ChatGPT account UI test or public deployment.

All integration schemas were removed. Additional post-restart spot checks confirmed both
MCP-created proof files/declaration records survived, and the default nonlocal SMS-inbox
guard rejects anonymous requests. The retained fixtures now include 21 Stage One synthetic
applications, two Stage Three synthetic applications (withdrawn), and 23 OAuth test clients.
The persistence suite used exact expected snapshot counts 21 and 23.

Issues found and corrected during implementation:

- MCP SDK 1.26.0 required PyJWT >=2.10.1; upgraded the old 2.9.0 pin to 2.10.1.
- The first PDF filter rejected standard FPDF page-opening destinations; corrected and tested.
- A new key-initialization test initially imported the legacy OAuth module before the
  Flask app, triggering its pre-existing circular import pattern; corrected the test
  import order. The production gateway already loads the app first.
- Starlette WSGI deprecation and Pydantic settings forward-reference warnings remain
  nonblocking with the installed versions. They did not prevent startup or any test.

Run tests:

```powershell
docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml exec -T -e RUN_DB_TESTS=1 app python -m unittest discover -s tests -v
Get-Content -Raw dev/verify_stage3.py | docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml exec -T app python -
Get-Content -Raw dev/verify_stage3_oauth_client.py | docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml exec -T app python -
```

Workflow scripts create fresh development citizens/clients. Update exact expected snapshot
counts before rerunning the original persistence test. Never run development fixtures
against production.

## File inventory

New application files:

- `app/citizen.py`
- `app/citizen_auth.py`
- `app/citizen_mcp.py`
- `app/citizen_web.py`
- `app/gateway.py`
- `app/templates/citizen_handoff.html`
- `app/migrations/002_citizen_agent.sql`
- `app/tests/test_citizen.py`

Modified application/deployment files:

- `app/services.py`: optional shared transaction and owned history retrieval.
- `app/app.py`: default SMS-console authorization guard.
- `app/oauth.py`: browser binding, citizen session claims/revocation, bounded/consumed OTPs,
  refresh client/resource binding and serialized key initialization.
- `app/schema.sql`: definitions corresponding to migration 002.
- `app/requirements.txt`: SDK, ASGI server and PDF parser dependencies; PyJWT update.
- `app/Dockerfile`: ASGI listener command; existing source/database architecture retained.
- `app/tests/test_services.py`: TRUNCATE CASCADE only inside temporary test schemas to
  accommodate the new foreign keys; original assertions retained.
- `docker-compose.yml`, `dev/compose.yml`: citizen settings and secret forwarding; the
  development file retains explicit localhost SMS simulation access.
- `README.md`: connection, migration and deployment instructions.

New development files: this report, `verify_stage3.py`, `verify_stage3_oauth_client.py`
and the five sanitized evidence files in the test table.

## External connection blockers and decisions before Stage 4

1. **Local-only deployment:** remote ChatGPT/Claude cannot reach this machine's localhost.
   Deploy under a public HTTPS origin with correct DNS/network access and PUBLIC_BASE_URL.
2. **Client support:** use a client supporting OAuth and Streamable HTTP. Stdio-only clients
   need an appropriate bridge. Automatic SDK discovery/registration has passed locally.
3. **Browser continuity:** uploads require the OAuth browser/profile. An assistant's isolated
   browser or another profile will be denied; reconnect using the browser used for upload.
4. **SMS simulation:** no real SMS provider exists. Public evaluator citizen login needs
   authorized access to the officer-protected simulator console or a real SMS integration.
   Do not solve this by publicly exposing every citizen's OTP.
5. **Deadline:** after 31 October 2026 at 23:59 IST, new submissions fail by design. Evaluation
   dates/policy still need organizer clarification. No deadline change is authorized or made.
6. **Legacy security and retention:** existing DOB-password/reset, legacy OTP behavior and
   other portal/OAuth hardening concerns from earlier reviews remain. Configure secrets,
   review expired-draft/proof retention and consider a broader security review before public use.

No officer-server or dashboard work has begun. Stop here and wait for Stage 4 approval.
