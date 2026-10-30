# Stage 4: Officer MCP Server

Completed locally on **28 October 2026**. The existing isolated development stack is
running. No evaluation dashboard, additional database/service or paid AI model integration
was introduced. Stop here and await the user's next-stage approval.

Officer endpoint: **http://localhost:8000/mcp/officer**.
Citizen endpoint remains **http://localhost:8000/mcp/citizen**.

## Tools and scope

| Tool | Implemented behavior |
| --- | --- |
| `get_queue_summary` | Status totals, pending counts by permitted block, oldest pending dates and overdue counts; officer identity and browser sign-out link |
| `list_applications` | Oldest-first queue, maximum 20 rows, cursor pagination, status/block/mobile/application-number filters; masked mobile, no bank account |
| `get_application` | A permitted case's details, masked identifiers, bounded audit, proof/acknowledgment browser links, and a short-lived case review token |
| `decide_application` | Exact decision/reason proposal followed by explicit, token-bound confirmation; shared atomic decision service |

Both servers read the same `CITIZEN_MCP_BLOCKS` setting, default **Sonari,Rajapara**.
Summary queries, lists, detail reads, browser downloads and decision updates enforce that
allowlist. User-supplied filters cannot broaden it. The setting is checked again when
confirming an earlier review. The existing web administrator retains its original global
portal access; these restrictions apply to agent channels.

## Shared business logic

The officer adapter does not implement another approve/reject writer. It calls the
Stage 2 `services.decide_application` function. That function now accepts optional
`blocks` and `cur` keywords, so agent scope, audit and confirmation consumption can
participate in one transaction. Default arguments preserve existing web behavior.

`get_officer_application` similarly supports optional block filtering, an existing cursor
and a row lock. Added shared query functions are `officer_queue_summary` and
`list_officer_applications`. Existing citizen and web callers retain their interfaces.

Final decisions still use `UPDATE ... WHERE status='PENDING'`, with an additional block
guard for agent callers. Competing requests serialize on the case row; exactly one
decision wins. The winner's authenticated actor, reason and audit commit together with
the confirmation's consumption. Audit failure rolls everything back. Withdrawn, rejected,
approved and deemed-approved cases cannot be overwritten.

The seed, scheme configuration, original deemed-approval script and crontab are
byte-for-byte unchanged. The deadline remains **31 October 2026, 23:59 IST**; the statutory
job still uses **15 days**. Its original behavior was exercised against synthetic overdue
cases during live tests, without modifying the job or eligibility rules.

## Authentication and resource isolation

- The officer resource has its own official SDK FastMCP instance, tool registry,
  Streamable HTTP session manager, verifier and protected-resource metadata at
  `/.well-known/oauth-protected-resource/mcp/officer`.
- Gateway dispatch keeps the two SDK authentication middleware stacks separate.
  Citizen tool/business/upload modules are unchanged. The shared session/JWT verifier
  was generalized with role/resource parameters while preserving citizen defaults.
- Clients discover the existing OAuth server, register, use PKCE S256 and request exactly
  scope `officer` with resource `<PUBLIC_BASE_URL>/mcp/officer`.
- Departmental credentials are entered only on portal browser pages. Tokens require
  RS256 verification, matching key/issuer/audience, officer role/scope/subject, access
  token kind, expiry, client binding, session ID and absolute session end.
- Officer sign-ins keep the existing 30-minute access token and eight-hour absolute
  session. Refresh rotates without extending it. OAuth revocation, connected-application
  revocation and the finish-sign-in action invalidate subsequent MCP access immediately.
- Citizen tokens, wrong-audience tokens, expired/revoked sessions and long-lived program
  tokens are rejected. Legacy officer tokens without the MCP session reference must be
  replaced through a fresh OAuth connection.
- No tool has an officer identity argument. Identity is taken from the verified token.
  Tests confirmed a forged `officer_username` argument cannot change the audit actor.

`OFFICER_MCP_ALLOWED_ORIGINS` optionally adds trusted browser-client origins. Host and
Origin protection remain enabled. No-origin native/server clients work without extra
origin configuration. Citizen origin settings and policies remain independent.

## Explicit confirmation and sensitive records

1. `get_application` returns a random, hashed-at-rest review token tied to the officer's
   session, the case and its snapshot. The snapshot includes the available proof digest.
2. `decide_application` with `confirmed=false` returns the exact applicant/application,
   block, decision and reason. It issues a separate confirmation token without modifying
   the application.
3. The assistant shows that preview and obtains the officer's explicit confirmation.
4. A second call supplies the same decision/reason, `confirmed=true` and the confirmation
   token. A strict boolean is required. Changed arguments, stale cases/proofs, expired
   reviews, different sessions, consumed tokens or nonpending status are rejected.

Reviews/confirmation expire within ten minutes or the access-token end, whichever is
earlier. A new proposal invalidates the old confirmation token. After an expired review,
inspect the case again. This is a delegated-client confirmation contract; it cannot
independently prove what a human said to the client.

List responses omit bank accounts and mask mobile numbers. Detail responses mask bank
and mobile numbers, including applicant identities embedded in audit actor fields.
At most 50 audit entries are returned. Audit notes remain records, not instructions;
the server instructs clients not to follow embedded instructions or decide in bulk.

Proof/acknowledgment links expire within 15 minutes and require the browser identity
proved during officer OAuth login, a live associated session and the current block
permission. A copied link alone is insufficient. Proofs must resolve to an allowed
document type inside the existing upload directory, without symlink/path escape, and
must still match the issued digest. Downloads are attachments, with no-store,
no-referrer, nosniff and restrictive CSP headers. Filesystem paths are not returned.
The legacy acknowledgment PDF can contain full bank details, but its handoff is restricted
to the authorized officer browser rather than being put directly into tool responses.

## Database and operating commands

Migration **003_officer_agent.sql** adds review/confirmation and officer handoff tables
to the existing portal database. It is applied to the isolated development database.
Fresh schema.sql contains the same definitions. Existing deployments must apply it
after migrations 001 and 002 before running this version.

```powershell
Get-Content -Raw app/migrations/003_officer_agent.sql | docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml exec -T db psql -v ON_ERROR_STOP=1 -U sewasetu -d sewasetu
docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml up --build -d
```

Officer username is `admin` in development; the generated password remains in ignored
`dev/.env.local`. No credentials, OTPs or bearer/refresh tokens are in the evidence files.

## Test results

**247 suite checks passed; zero final failures.** This includes the existing **188**
checks and adds 20 officer unit/integration tests plus 39 live officer client checks.

| Suite | Passed | Evidence |
| --- | ---: | --- |
| Existing and officer unit/Postgres integration tests | 69 | `stage4-unit-integration.txt` |
| Existing portal/OAuth workflows | 76 | `stage4-regression-main.jsonl` |
| Existing restart/persistence checks | 15 | `stage4-regression-persistence.jsonl` |
| Citizen MCP workflows | 45 | `stage4-citizen-results.jsonl` |
| Citizen automatic OAuth discovery/refresh/revocation | 3 | `stage4-citizen-oauth-results.jsonl` |
| Officer automatic OAuth + live MCP workflows | 39 | `stage4-mcp-results.jsonl` |

The officer tests cover summaries, masked case inspection, pagination, permitted-block
enforcement, approval/rejection reasons, confirmation binding, expired tokens/reviews,
session ownership/revocation, competing decisions, withdrawal races, terminal states,
proof/browser authorization and audit-failure rollback. Live protocol tests use the
official SDK's automatic discovery, DCR and PKCE flow with automated browser credential
entry, then read the actual database and existing web portal. They include an actual run
of the unchanged statutory job and denial of a later rejection of its deemed approval.
No AI model API was called. Manual ChatGPT/Claude account UI testing and a public HTTPS
deployment are not claimed.

Temporary integration schemas were removed. Test fixtures use shared submission services
and clearly synthetic proofs; all remaining pending fixtures are withdrawn on test exit.
Original seed rows/file are not rewritten. The current retained baseline contains 24
Stage One synthetic applications, three Stage Three cases, 12 Stage Four cases, and 34
OAuth test clients. Two Stage Four cases were deliberately made overdue, increasing
deemed-approved applications/audits from 9700 to 9702. The persistence suite used those
exact snapshot counts. The known legacy recent-audit scheduler edge case did not
reproduce in the final delayed-restart check; the job was not changed.

Compatibility updates to development assertions:

- The old Stage 3 assertion that the officer endpoint was absent now checks that it
  rejects unauthenticated requests. All other citizen checks remain the same.
- The persistence script accepts `STAGE1_EXPECTED_DEEMED` for deliberate statutory test
  fixtures, retaining the original default 9700 and all original assertions.

Docker Desktop was initially stopped; it was started and the saved volumes resumed.
The floating Python base image refreshed during build, but no project dependency pins
were changed in Stage 4, and all suites passed with the resulting images. Existing
Starlette/Pydantic deprecation warnings remain nonblocking.

Commands:

```powershell
docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml exec -T -e RUN_DB_TESTS=1 app python -m unittest discover -s tests -v
Get-Content -Raw dev/verify_stage4.py | docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml exec -T app python -
```

The live workflow creates synthetic applications and OAuth clients. Do not run it against
production; additional runs require new expected persistence counts.

## File inventory

New application files:

- `app/officer_auth.py`
- `app/officer.py`
- `app/officer_mcp.py`
- `app/officer_web.py`
- `app/templates/officer_handoff.html`
- `app/migrations/003_officer_agent.sql`
- `app/tests/test_officer.py`

Modified application/deployment files:

- `app/citizen_auth.py`: reusable role/audience-aware JWT and session helpers; citizen wrappers preserved.
- `app/oauth.py`: issue persistent officer MCP sessions and establish the officer browser identity.
- `app/services.py`: optional scoped/caller-owned officer reads/decisions and shared queue queries.
- `app/gateway.py`: independent endpoint dispatch, metadata and both transport lifespans.
- `app/schema.sql`: migration 003 definitions.
- `docker-compose.yml`, `dev/compose.yml`: optional officer browser-origin configuration.
- `README.md`: officer connection, migration and confirmation instructions.

New/updated development files: `verify_stage4.py`, the six evidence files above,
`STAGE4.md`, the session handoff, `stage3-source-sha256.json` (pre-change integrity
snapshot), and the two regression-script compatibility updates described above.
Citizen tool, preparation and upload modules remain byte-for-byte unchanged.

## Deployment and evaluation risks

- Both endpoints are still localhost-only. External assistants need public HTTPS,
  reachable networking and the correct stable PUBLIC_BASE_URL. Use the exact canonical
  endpoint and an OAuth-capable Streamable HTTP client. Automatic SDK connection has
  passed locally; arbitrary external client versions have not all been tested.
- The portal still has one environment-configured departmental account, not a staff
  account directory or individual block assignments. Audit identity is the authenticated
  username; real departments need named accounts and credential management before
  relying on per-person accountability. All current officers share the configured agent
  block subset. The ordinary admin web portal retains its prior wider access.
- Proof links require the OAuth browser/profile. Its legacy browser session can expire
  earlier than the eight-hour officer API session; re-authenticate when necessary.
- Public citizen login still depends on authorized simulated SMS access or a real SMS
  provider. Do not make the global inbox public to bypass that issue.
- The unchanged **31 October 2026, 23:59 IST** deadline will block new applications after
  that date. Evaluation dates and any authorized extension remain unresolved. Existing
  case review and decisions continue after closing.
- Expired draft/review/link/proof retention, legacy portal hardening, immutable legacy
  proof storage and the previously identified scheduler audit edge case remain separate
  preproduction considerations. Passing these tests is not a full security audit.
- The evaluation dashboard and persona evaluation deliverables are still not implemented.

Do not begin the next stage without user approval.
