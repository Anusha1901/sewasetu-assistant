# Stage 2: shared business operations

Completed 27 October 2026. No MCP server or new service/infrastructure was added.
The isolated development portal remains running at http://localhost:8000/.

## Application changes

| File | Change |
| --- | --- |
| `app/services.py` (new) | Flask-independent validation, transaction handling, submission, citizen/officer reads, withdrawal, decisions, audit functions and configuration |
| `app/app.py` | Routes call the shared functions; authentication, templates, redirects, flash messages, SMS after submission and PDF generation remain in the web adapter |
| `app/schema.sql` | Unique application-number index and partial unique active-mobile index for new databases |
| `app/migrations/001_application_uniqueness.sql` (new) | Explicit transactional upgrade for existing databases; applied only to isolated development database |
| `app/templates/admin_view.html` | Approval/rejection reason fields required, maximum 500 characters |
| `app/tests/test_services.py` (new) | stdlib unit tests and real Postgres integration/concurrency tests |

Development-only changes: `dev/verify_stage1_persistence.py` now accepts expected record
and client counts through environment variables, retaining the original default values
and all 15 assertions. Added this report and sanitized Stage 2 results:
`stage2-unit-integration.txt`, `stage2-regression-main.jsonl`,
`stage2-regression-persistence.jsonl`.

Original application/configuration checksum comparison shows only `app/app.py`,
`app/schema.sql`, and `app/templates/admin_view.html` changed among the original files.
`seed/seed.sql`, `app/config/app.ini`, OAuth, Dockerfiles, dependencies, original Compose,
the scheduler script and crontab are byte-for-byte unchanged. The Stage 1 report and its
checksums remain historical evidence of the original baseline.

## Shared interfaces

- `validate_application(data, doc_path)`: original errors and normalized values.
- `parse_dob`, `age_on`, `sanitize`, `now_ist`: original rule helpers.
- `submit_application(mobile, data, doc_path)`: validates after acquiring the mobile lock,
  rejects active duplicates, creates application/account/audit, commits or rolls back,
  returns `(id, application_no)`.
- `active_application(cur, mobile)`, `create_application(cur, mobile, cleaned)`:
  low-level transaction helpers. New adapters must use `submit_application`, not call
  the insert helper directly. Existing imports from `app` remain available for compatibility.
- `get_latest_application_id(mobile)`, `get_citizen_application(id, mobile)`:
  status-portal retrieval; ownership is enforced in the citizen detail query.
- `get_officer_application(id, officer_username)`, `get_audit(id)`:
  internal officer/detail reads; callers must authenticate and authorize access first.
- `withdraw_pending_application(id, mobile)`: owner- and pending-guarded update plus audit.
- `decide_application(id, status, officer_username, reason)`: pending-only decision,
  constrained to APPROVED/REJECTED, with required reason and authenticated actor.
- `write_audit(cur, id, action, actor, note)`, `transaction()`: shared audit and transaction
  lifecycle. Connections and cursors are always closed, including on failure.

The functions have no Flask/session dependencies. They are internal Python APIs, not an
authentication mechanism: web routes authenticate first; future MCP adapters must verify
JWTs and derive the mobile/officer identity from verified claims. Never expose a freely
caller-selected mobile, officer username, or unrestricted `get_audit` as an agent interface.
Block allowlist enforcement is still a Stage 3 decision.

## Database protection and decisions

- `uq_app_application_no` prevents duplicate application numbers across all writers.
- `uq_app_active_mobile` permits at most one PENDING/APPROVED/DEEMED_APPROVED application
  per mobile, while preserving rejected/withdrawn history and reapplication.
- A transaction-scoped Postgres advisory lock serializes cooperative submissions for
  the same mobile. The unique index remains the cross-writer backstop.
- Random application-number collisions retry within savepoints (up to 20 attempts).
  No partial application, status account, or audit survives a failed attempt.
- Portal-account creation uses ON CONFLICT DO NOTHING, preserving an existing password.
- Decisions and withdrawals retain conditional pending-only updates. Exactly one
  competing mutation wins. Its audit commits in the same transaction; failed audit
  insertion rolls the mutation back.
- Officer identity comes from `session['admin_user']`, not a posted actor. Reasons are
  retained exactly as submitted after checking that they are nonblank and at most 500
  characters. Actor length is bounded by the existing audit-column capacity.

**Intentional behavior tightening requested in Stage 2:** blank decision notes previously
worked. Both approval and rejection now require a reason in the UI and service. Invalid
reasons leave the application pending and show an error. Other tested web behavior and
all existing eligibility rules remain unchanged.

### Existing database upgrade

From the project folder (isolated development example):

```powershell
Get-Content -Raw app/migrations/001_application_uniqueness.sql | docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml exec -T db psql -v ON_ERROR_STOP=1 -U sewasetu -d sewasetu
```

Apply this before running the new application against an existing database. Changing
`schema.sql` does not migrate a persistent Docker volume. The upgrade is repeatable and
does not delete or repair existing rows. It fails transactionally if conflicting data
exists; investigate those rows rather than automatically rewriting them. Regular index
creation temporarily blocks writes, so use a maintenance window for a live deployment.

## Tests and evidence

**All final checks passed: 28 unit/integration tests + the original 91 baseline checks.**
No failures in the final runs.

| Suite | Result | Evidence |
| --- | --- | --- |
| Unit tests | 11 passed | `stage2-unit-integration.txt` |
| PostgreSQL integration tests | 17 passed | `stage2-unit-integration.txt` |
| Original HTTP/database flow checks | 76 passed | `stage2-regression-main.jsonl` |
| Original restart/persistence/duplicate checks | 15 passed | `stage2-regression-persistence.jsonl` |

Integration tests create a unique temporary schema in the development Postgres database,
apply the real schema and indexes, and remove that schema afterwards. No seed or public
development rows are used as unit-test fixtures. Concurrency tests use separate real
connections and synchronized threads. Coverage includes:

- Normalization, required fields, exact age boundary, leap-day age and invalid DOBs.
- Original optional IFSC behavior and original block list.
- Exact configured deadline and rejection just after it.
- Two simultaneous submissions: one application/account/submit audit, one duplicate error.
- Database duplicate rejection even when the high-level submission function is bypassed.
- Application-number collision retries, including simultaneous different-mobile collisions.
- Reapplication after rejection/withdrawal while retaining one portal account.
- Competing officer decisions, and officer approval versus citizen withdrawal.
- Audit failure rolling back submission, decision and withdrawal.
- Wrong-mobile detail/withdrawal denial and citizen attempts at officer web actions.
- Blank reasons rejected and forged actor form fields ignored.
- Migration repeatability.
- Post-deadline submission rejection while status/decisions continue to work.

Test clocks are patched only inside test processes; runtime configuration and actual
container clocks were not changed. Full-duration OAuth expiry and visual accessibility
remain outside this regression suite, as in Stage 1.

Commands:

```powershell
docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml exec -T -e RUN_DB_TESTS=1 app python -m unittest discover -s tests -v
Get-Content -Raw dev/verify_stage1.py | docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml exec -T app python -
```

The main regression script creates three more synthetic applications per run. At this
stage's final snapshot there are 12 retained Stage One synthetic applications and 7 test
OAuth clients from all baseline runs. The 15 persistence checks were run after a full
stop/start with `STAGE1_EXPECTED_APPLICATIONS=12` and `STAGE1_EXPECTED_CLIENTS=7`.
Defaults remain 6 and 3 to preserve the initial Stage 1 snapshot. Counts must reflect
additional runs; assertions are not weakened to merely accept any increasing count.

The original 100000-row source export is unchanged. Public development data now includes
12 synthetic terminal applications; tests of current mutations do not rely on the old
overdue pending seed cases. Scheduler restart reported zero additional approvals.

## Deadline investigation and decisions before Stage 3

The configured deadline remains **31 October 2026 at 23:59 Asia/Kolkata**. The validator
rejects submissions when its IST clock is later than that instant; starting a draft
before closing does not reserve a right to submit later. Existing `/apply` closes at
the exact configured instant, while final validation uses `>`; this pre-existing boundary
behavior is preserved, including the fact that the setting is 23:59:00 rather than the
end of that minute.

After closing, new applications and resubmissions fail through both web and shared
submission. Status retrieval, withdrawal, officer decisions and the 15-day scheduler
are not closed by the application deadline. Tests verify this distinction.

Neither BRIEF.md nor README.md nor the supplied Director transcript identifies evaluation
dates or authorizes changing the scheme window. BRIEF.md requires keeping the deployment
available and permits repeated evaluation. Therefore an evaluator testing after closing
can connect and inspect/decide cases but cannot complete a new pension application under
the unchanged rules. There is no technical workaround consistent with those rules.
Obtain the organizers' evaluation dates and an explicitly approved policy if an extension
is needed. **No deadline change, runtime override, clock shift, or bypass was implemented.**

Other Stage 3 decisions/risks:

- Choose the agent-supported block subset and map officer access to it. Current portal
  authentication still represents one global departmental user.
- Implement MCP authorization and per-request identity checks, document upload ownership,
  session isolation/revocation, and declaration binding in the authorized next stage.
- Existing upload, DOB-password, OTP-rate-limit, CSRF and OAuth limitations from the
  architecture review remain. This extraction is not a security-hardening rewrite.
- Duplicate protection is not full request-key idempotency: retried active submissions
  return the existing-application conflict, not an identical success response. A prepared
  submission/idempotency key can be added with the MCP workflow.
- Future adapters must send notifications after successful submission commit; SMS failures
  must not undo a recorded application. No durable notification queue was introduced.

Stop here: Stage 3 requires the user's approval.
