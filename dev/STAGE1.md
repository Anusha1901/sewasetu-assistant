# Stage 1: local baseline and isolation

Status on 27 October 2026: STAGE 1 BASELINE VERIFIED; awaiting Stage 2 approval.

Docker Desktop has been installed by the user. No MCP work has begun.
The original application, configuration, Dockerfiles, Compose file, and seed are unchanged.

## Completed live verification

The isolated `sewasetu-stage1-dev` deployment is running at http://localhost:8000/.
Docker Desktop 4.97.0, Engine 29.9.2, Compose v5.6.1; Linux containers.
Application runtime: Python 3.11.18, Flask 2.2.5, Werkzeug 3.1.9, Gunicorn 20.1.0,
psycopg2-binary 2.9.9, PyJWT 2.9.0. No dependency modifications were needed.

**Results: 76 main HTTP/database checks and 15 post-restart checks passed (91 total).**
Tests used real HTTP routes and read-only SQL assertions against the development database.
All synthetic application writes used the ordinary portal flow, including CAPTCHA and OTP.
These are automated HTTP checks, not a visual/browser accessibility review or a security audit.

| Area | Observed result |
| --- | --- |
| Startup | Original images built; all four services running; Postgres healthy; Compose config validation passed |
| Database | Seed imported 100000 applications, 100000 accounts, 199300 audit rows; SELECT 1 passed |
| Citizen portal | Home, about, application, status and login pages returned 200 |
| Citizen flow | CAPTCHA, invalid/valid OTP, details, actual synthetic PDF upload, preview, submission and database audit passed |
| Validation | Missing proof shown in preview; underage, invalid block/bank submissions rejected without inserts; duplicate active submission rejected |
| Follow-up | DOB login, own-case read and PDF acknowledgment passed; another citizen's record/PDF denied |
| Withdrawal | Pending withdrawal persisted with audit |
| Officer | Anonymous access redirected; wrong password rejected; login, dashboard, queue, mobile search and case detail passed |
| Decisions | Approval/rejection persisted with admin actor and exact test reason in audit |
| OAuth | Discovery/JWKS, registration, citizen OTP and officer password login, consent, state, PKCE exchange passed |
| Tokens | RS256 signature, issuer/audience, role/scope/subject, access lifetime bounds, code single use, refresh rotation and revocation passed |
| Session bounds | Refresh preserved the original session end; no multi-hour wall-clock expiry wait was performed |
| Scheduler | Exactly 700 overdue cases deemed approved at startup; 0 further updates on restart; no additional audit duplication on this delayed restart |
| Persistence | Database records, 6 synthetic proof files, 12 synthetic audit rows and OAuth clients survived full-stack stop/start |
| Host access | Windows request to http://localhost:8000/ returned 200 outside the sandbox |
| Source integrity | All 38 original-file SHA-256 checksums still match; seed file unchanged; Docker inspection confirms read-only seed/schema mounts |

Sanitized evidence: `stage1-results.jsonl`, `stage1-persistence-results.jsonl`.
The initial attempt is retained in `stage1-first-attempt.jsonl`: its citizen OAuth check
failed because the test helper selected an old delivered OTP while a newer one was queued.
The helper was corrected to wait for the newest message; the complete rerun passed.
This was a test-harness issue, not an application fix.

Six synthetic applications remain in development volumes (IDs 100011 through 100016):
two APPROVED, two REJECTED, two WITHDRAWN. The database now contains 100006 applications,
100006 portal accounts and 200012 audit records. Final status counts: APPROVED 82902,
DEEMED_APPROVED 9700, REJECTED 7002, WITHDRAWN 402, PENDING 0.
Three development OAuth clients remain. Test proofs are clearly marked synthetic.
The gateway's earlier inbox was cleared on restart, consistent with its in-memory design.

### Errors encountered and changes made

- Docker's new per-user binary directory was absent from this session's PATH, causing
  `docker-credential-desktop` lookup failure during the first pull. Adding that directory
  to the build command's PATH resolved it; no machine-wide PATH changes were made.
- Docker API and Windows localhost access needed out-of-sandbox execution; both worked
  after permission was granted. These were execution-environment restrictions.
- No app, gateway, database initialization, or dependency startup errors reproduced.
- Added only development test scripts, sanitized results, this report, `.gitignore`, and
  an ignored `.env.local` with generated development-only credentials. No original files changed.
- No clock, deadline, eligibility, schema or OAuth behavior was altered.

## Initial environment evidence (before Docker installation)

- `docker` and `docker-compose` were not found in PATH.
- Docker executable and Docker Desktop were absent from the standard Program Files locations.
- An out-of-sandbox WSL check reported no installed distributions. This alone does not
  prevent Docker Desktop: it can provision its own WSL environment.
- No Docker service was found by the service-name query.
- Host Python is 3.13.6; the Dockerfiles use Python 3.11. Host Python is not a substitute
  for verifying the prescribed container environment.
- No containers were started and no database writes or migrations were performed.

Completed offline checks: the development YAML parses; all referenced build directories
contain Dockerfiles; all project Python files parse successfully; the full seed scan
matches the counts below; the seed hash matches the initial pre-change reading. Checksums
were recorded for all 38 original files. YAML parsing is not Docker Compose validation,
and Python syntax parsing is not dependency/import or service verification.

## Safe development deployment

`dev/compose.yml` is a standalone development configuration, not an override of the original.
It builds the original app and gateway Dockerfiles without editing them. Always use the
explicit project name and file below; do not use bare `docker compose up` for this baseline.

- Dedicated project: `sewasetu-stage1-dev`.
- Dedicated volumes: `sewasetu-stage1-dev_pgdata`, `sewasetu-stage1-dev_uploads`,
  `sewasetu-stage1-dev_applogs`. No external or production volumes are referenced.
- Schema and seed initialization files are mounted read-only.
- Only localhost port 8000 is published; Postgres and the SMS gateway have no host ports.
- Admin password and Flask session secret must be supplied through the shell.
- The database health check uses TCP so it waits for Postgres's normal server after
  first-boot initialization, rather than its temporary initialization socket.
- The app and scheduler wait for database health. The scheduler's startup execution and
  nightly cron are preserved, including all original eligibility and deadline rules.
- Scheduler dependency on the SMS gateway reduces first-start notification failures;
  it is startup ordering, not an SMS-readiness guarantee.

From the project directory in PowerShell, after Docker Desktop is running Linux containers:

```powershell
docker version
docker compose version
$env:ADMIN_PASSWORD = Read-Host 'Choose a local development admin password'
$env:SECRET_KEY = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
docker compose -p sewasetu-stage1-dev -f dev/compose.yml config --quiet
docker compose -p sewasetu-stage1-dev -f dev/compose.yml up --build -d
docker compose -p sewasetu-stage1-dev -f dev/compose.yml ps
docker compose -p sewasetu-stage1-dev -f dev/compose.yml logs --tail 100 db app smsgw scheduler
```

Keep the shell open: later Compose commands need the same environment variables.
Do not paste resolved Compose output, passwords, cookies, OTPs, or tokens into reports.
The development gateway intentionally exposes simulated SMS messages locally.

Stopping without removing development data:

```powershell
docker compose -p sewasetu-stage1-dev -f dev/compose.yml down
```

For a fresh test database, use another explicit development project name, such as
`sewasetu-stage1-run2`, consistently in every command. Stop the earlier project's app first
to free port 8000. Each new project imports the read-only seed into new volumes. Retaining
old volumes avoids destructive reset commands; cleanup can be requested separately.

## Seed baseline

SHA-256 of `seed/seed.sql`:

`8F5A4A87C5C1FB1E06A327DCB5D7389501F459B2FA577377A7EF1544A00BBF4B`

Full-export scan (file analysis, not a query against running Postgres):

| Table | Rows |
| --- | ---: |
| applications | 100000 |
| portal_users | 100000 |
| audit_log | 199300 |

| Application status | Rows |
| --- | ---: |
| APPROVED | 82900 |
| DEEMED_APPROVED | 9000 |
| REJECTED | 7000 |
| WITHDRAWN | 400 |
| PENDING | 700 |

Every seeded document path is empty. All 700 seeded pending applications were submitted
between 16 and 30 September 2026. On 27 October, all are overdue. The original scheduler
will update the development database at startup. This is expected behavior, not seed-file
corruption; the read-only SQL source remains unchanged. New test applications must be
created through the real portal for pending-case decisions and document tests.

## Verification checklist originally prepared

The checklist below was prepared before Docker was available. See the completed results
above for coverage and limits. Full wall-clock session expiry is not claimed as tested.

| Area | Check and evidence |
| --- | --- |
| Startup | Image builds, all four services run, seed import completes, no worker tracebacks |
| Database | `SELECT 1`; table counts; status counts; scheduler changes and audit rows |
| Public portal | GET `/`, `/about`, `/apply`, `/status` render successfully |
| Officer login | Anonymous dashboard access redirects; wrong credentials rejected; configured login succeeds |
| Officer dashboard | Dashboard, pending list, search and case detail load against Postgres |
| SMS | Trigger OTP through `/apply`; poll `/__gateway/api/messages?to=<test mobile>` until delivered; verify console |
| Citizen application | OTP, personal/address/bank fields, actual proof upload, declaration, application number |
| Citizen follow-up | DOB login, application ownership, acknowledgment PDF and pending withdrawal |
| Validation | Underage, missing proof, invalid bank/block rejected; duplicate active application blocked |
| Officer decision | Fresh pending cases approved/rejected; status, reason, actor and audit persisted |
| OAuth discovery | GET `/.well-known/oauth-authorization-server`; issuer/URLs match localhost base |
| OAuth keys | GET `/.well-known/jwks.json`; valid RSA public key |
| OAuth citizen | Register loopback client; PKCE login/OTP/consent/code exchange; verify JWT signature/claims |
| OAuth officer | Same flow with departmental login; officer role/scope/subject |
| OAuth lifecycle | Refresh rotation, old refresh rejection, revocation and absolute expiry behavior |
| Persistence | Restart services; test records/uploads remain; source-file checksums still match |

Example database inspection (after the stack is running):

```powershell
docker compose -p sewasetu-stage1-dev -f dev/compose.yml exec -T db psql -U sewasetu -d sewasetu -c 'SELECT 1;'
docker compose -p sewasetu-stage1-dev -f dev/compose.yml exec -T db psql -U sewasetu -d sewasetu -c 'SELECT status, count(*) FROM applications GROUP BY status ORDER BY status;'
```

## Startup and dependency risks

Resolved prerequisite issue: Docker was initially unavailable; build/start and live tests
have now completed successfully.

Earlier dependency concern did not reproduce: both images built and ran with Flask 2.2.5
and Werkzeug 3.1.9. The broad Flask 2.2-era compatibility concern did not justify a change
to this specific app. Transitive dependencies remain unpinned; no pins were changed.

Reference: https://github.com/pallets/werkzeug/issues/2789

Other source-level risks to check at runtime:

- Original Compose uses startup ordering rather than database readiness; the development
  file adds readiness without altering the original file.
- No explicit container timezone is configured. Eligibility/deadline use Asia/Kolkata in
  the app; scheduler/audit timestamps use host-local naive time. No clock changes were made.
- App SMS failures are logged but do not fail application creation; verify delivery separately.
- The scheduler may spend time sending hundreds of first-start messages after committing.
- Seeded missing documents must not be mistaken for a broken upload volume.

## Confirmed scheme configuration

- Application deadline: **31 October 2026, 23:59 Asia/Kolkata (IST)**.
- Minimum age: **60**; statutory processing SLA: **15 days**.
- Blocks: **Sonari, Rajapara, Dhemaji Pathar, Borgaon, Namti, Khelua**.
- No block subset has been selected or enforced for MCP in this stage.

## Exact shared-function candidates

All line references below refer to unchanged original source.

| Existing function | Location | Intended treatment in a later stage |
| --- | --- | --- |
| `now_ist` | app/app.py:22 | Shared scheme clock |
| `get_db` | app/app.py:71 | Shared database access |
| `sanitize` | app/app.py:81 | Shared normalization |
| `send_sms` | app/app.py:93 | Shared notification helper |
| `deadline_remaining` | app/app.py:101 | Shared scheme-window display |
| `new_application_no` | app/app.py:108 | Shared number generation; concurrency improvement later |
| `write_audit` | app/app.py:112 | Shared audit operation |
| `parse_dob` | app/app.py:125 | Shared DOB parsing |
| `age_on` | app/app.py:132 | Shared age calculation |
| `validate_application` | app/app.py:136 | Mandatory shared submission validator |
| `active_application` | app/app.py:180 | Shared duplicate lookup; not inside validator |
| `create_application` | app/app.py:188 | Shared insertion/account/audit transaction work; caller commits |
| `generate_acknowledgment` | app/app.py:407 | Shared PDF generation behind ownership checks |
| `verify_token` | app/oauth.py:124 | Existing JWT verification primitive; additional role/scope enforcement needed later |

The following are routes, not directly reusable services. Extract only their business work
later, leaving session checks, flashes, redirects and templates in the web layer:

- `handle_submission` (app/app.py:373): validate, active check, insert, commit, notify.
- `view_application` (472): ownership-filtered read.
- `withdraw_application` (490): ownership- and pending-guarded update plus audit.
- `upload` (333): file validation/storage; strengthen ownership and naming later.
- `admin_dashboard` (579): aggregate queue queries.
- `admin_list` (598): filtered/paginated search queries.
- `admin_view` (622): detail and audit queries.
- `_admin_decide` (642): conditional decision update and audit.

Keep existing OAuth login, consent, registration and token routes as the authorization
server. Do not expose OTP/password helpers as MCP tools. The scheduler `main()` remains
the existing background workflow rather than an officer tool.

## Files added in this stage

- `dev/compose.yml`: isolated local deployment configuration.
- `dev/STAGE1.md`: findings, run instructions and pending verification checklist.
- `dev/original-sha256.json`: checksums of original handout files, excluding this dev folder.
- `dev/.gitignore`, ignored `dev/.env.local`: development-only credentials.
- `dev/verify_stage1.py`: main HTTP/database verification script.
- `dev/verify_stage1_persistence.py`: post-restart snapshot and duplicate checks.
- `dev/stage1-results.jsonl`, `dev/stage1-persistence-results.jsonl`: passing evidence.
- `dev/stage1-first-attempt.jsonl`: initial test-helper failure retained for transparency.

## Operating the verified stack

The per-user Docker binary is currently at:
`C:\Users\anush\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe`.
Use a new terminal if the installer-updated PATH is not yet visible.
Credentials are in ignored `dev/.env.local`; they were not printed into test results.
Officer username: `admin`. Use the local file's ADMIN_PASSWORD value to sign in.

From the project directory:

```powershell
docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml ps
docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml up -d
docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml stop
```

To run the main verification again (creates three additional synthetic applications):

```powershell
Get-Content -Raw dev/verify_stage1.py | docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml exec -T app python -
```

The persistence script intentionally asserts this recorded six-application baseline;
additional main-script runs require updating its expected counts. Do not run these
development scripts against a production deployment.

Stage 1 baseline is complete. Do not proceed to MCP implementation without the user's
next-stage approval. Existing security/design limitations from the architecture review
remain; passing the baseline tests does not establish production readiness.
