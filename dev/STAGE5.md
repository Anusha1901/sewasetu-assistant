# Stage 5 final verification — 30 October 2026

**Stage 5 complete. Stop and wait for approval before implementing the evaluation dashboard.**

Portal: https://sewasetu-assistant-wgcq.onrender.com

- Citizen Streamable HTTP: /mcp/citizen
- Officer Streamable HTTP: /mcp/officer
- Render Free, Frankfurt; Supabase Free, Paris; private age-proofs bucket.
- Private repository: https://github.com/Anusha1901/sewasetu-assistant
- No paid hosting, domain, or model API was provisioned.

## Results

| Scenario | Result and evidence |
| --- | --- |
| Real Codex citizen-to-officer workflow | Passed earlier: synthetic Kamala case SSP26495722 submitted after the user's declaration acceptance, approved only after exact decision/reason preview and user confirmation, visible in citizen follow-up and Supabase audit. |
| Public rejection | Passed: SSP26545674 / id 100012 rejected through official SDK over public Streamable HTTP. Blank reasons were rejected for BOTH decision types. Preview did not mutate the case; confirmed rejection recorded exact reason and authenticated admin:assessor audit. Citizen history returned that reason. |
| Citizen withdrawal | Passed: SSP26669481 / id 100013 required confirmation, then became WITHDRAWN with applicant audit. A second withdrawal was rejected. |
| Expired sessions | Passed for both citizen and officer: real OAuth authorization-code/PKCE sessions were created for dedicated test clients, then ONLY those session rows were advanced to expiry. Existing access tokens received 401 and refresh received 400. User's Codex sessions were untouched. No forged access tokens were used. |
| Revoked sessions | Passed for both roles using the real /oauth/revoke endpoint. Revoked access received 401 and refresh received 400. |
| Competing decisions | Passed: two separately authenticated officer SDK clients inspected and previewed opposite decisions on pending SSP26635026 / id 100014, then sent confirmations concurrently. Exactly one succeeded (REJECTED), with exactly one matching decision audit. |
| Authorization boundaries | Passed: citizen token rejected by officer MCP and vice versa; other-citizen withdrawal rejected; unsupported block denied. Synthetic data only. |
| Hosted restart persistence | Passed after the user selected Render Restart service and reported Live. Four synthetic case records, exact private PDF hashes, exact audit hashes/counts, global application/audit/deemed counts and simulated SMS count matched the before-restart baseline. A fresh authenticated SDK connection listed four officer tools and called the protected queue tool. |
| Render post-idle reconnect | Passed on first attempt after a measured 988.6-second (16m29s) quiet window. First response HTTP 200 application/json at 24.634 seconds; full authenticated official-SDK reconnect/discovery/tool call at 25.844 seconds. Existing Codex citizen/officer tools also worked afterward. |
| Scheduler | Two fixed GitHub runs succeeded: 41030375367 and 41030731190. Comparing the saved hosted baseline confirmed no additional application decisions or audit rows. The newly approved-row repeat/concurrency path is additionally covered by isolated DB regressions below. |
| Public deployment probes | Eight passed after restart and cold reconnect: HTTPS homepage, DB readiness, correct AS metadata, both MCP challenges, both resource metadata checks, and protected SMS inbox. |
| Automated regression | All 275 local tests/checks passed, including all original 247. All 100000 local seed rows remained after the corrected tests. |

The controlled public test harness performs ordinary browser OAuth and fetches only its
synthetic citizens' delivered OTPs through an assessor-authenticated simulator session.
Passwords, OTPs, tokens, browser cookies and capability URLs are not printed or committed.
Applications and decisions use public MCP tools; SQL is used for verification and tightly
scoped synthetic session-expiry fixtures, never to bypass application/decision logic.
This automated SDK harness complements the real Codex conversation; it is not represented
as an additional human/AI conversation.

## Final automated count

| Suite | Passed |
| --- | ---: |
| Unit and disposable-schema integration | 87 |
| Existing web portal, OAuth, SMS, DB | 76 |
| Citizen MCP workflow | 45 |
| Officer MCP workflow | 39 |
| Automatic citizen SDK OAuth discovery | 3 |
| Local restart persistence | 15 |
| Hosted adapter rehearsal in disposable local DB | 10 |
| **Local regression subtotal** | **275** |
| Public synthetic workflows/security | 79 |
| Hosted restart persistence | 6 |
| Hosted fresh SDK reconnect | 2 |
| Quiet-window/cold SDK reconnect | 2 |
| Public HTTPS/discovery/privacy probes | 8 |
| Fixed scheduler success/idempotency | 4 |
| **Live automated subtotal** | **101** |
| **Total** | **376** |

Final failures: **0**. Counts are parsed from the retained logs; see stage5-final-summary.json.
This counts 87 unittest cases plus scenario assertions in the existing verification scripts,
using the same convention as prior 247/271-check reports. Repeated diagnostic runs and the
earlier manually driven Codex workflow are not added again to inflate the count.

## Bugs discovered and fixed

### Statutory audit duplication

The original job conditionally updated pending overdue applications, but inserted audit
rows for every RTPS-AUTO decision from the preceding minute. Immediate repeats and
competing runs reproduced **two audit entries for one decision**. Both regression tests
failed before the fix.

Fix: app/scripts/deemed_approval.py now returns id with application number/mobile from
the conditional UPDATE and audits exactly those returned rows in the same transaction.
Notifications also use only those transitioned rows. Repeat/concurrency tests now produce
one audit and one notification. A recent pending case remains untouched. The 15-day cutoff,
eligibility rules, deadline, decision status and notification wording are unchanged.
The fix is active in GitHub Actions (runs build current main); Render portal logic was not
changed. The source was pushed with [skip render] to avoid disrupting the measured idle test.

### Test harness isolation cleanup

An overly broad patch.stopall() in the new scheduler regression class removed the temporary
schema connection override. This reset the isolated local application's synthetic fixtures.
Hosted Supabase records and original seed/configuration files were never affected.

Fix: clean up only the two mocks owned by that test. Add a guard in the shared test fixture
setup that refuses TRUNCATE unless current_schema() equals that class's temporary schema;
a dedicated regression verifies refusal. The local seed was restored transactionally from
the unchanged seed file, then the full regression and persistence suites were rerun.
Earlier local synthetic application/audit history was reset and rebuilt; it was not recovered.
Existing local OAuth clients and upload files were retained. A pre-restore snapshot of the
already affected DB is kept privately in deploy/backups, not committed.

An initial restore correctly rolled back on a dependent-table constraint; the successful
restore explicitly reset the dependent synthetic preparation tables as well. The final local
state contains the full original 100000 seed applications plus 10 regenerated test cases.

The earlier initial scheduler notification timeout and 41-message recovery are described
in STAGE5-LIVE-RESULTS.md. The 30-minute workflow limit remains in place.

## Preserved invariants

- Minimum age 60; pension amount 250 rupees/month.
- Deadline **31 October 2026, 23:59 Asia/Kolkata**; no extension or bypass.
- Pending applications older than the original 15-day cutoff get deemed approval.
- Same configurable Sonari/Rajapara agent allowlist and citizen/officer boundaries.
- Original scheme INI, crontab and seed file still match initial SHA-256 hashes.
- One deliberately changed production file this final test stage: the scheduler's audit
  targeting bug fix. Other changes are tests, ignored-output patterns and documentation.
- Both MCP endpoints remain Streamable HTTP, not legacy SSE.

## Remaining operational limitations

- Render Free sleeps and can restart; this test measured a 25.8-second authenticated cold
  reconnect, not an uptime guarantee. Give external clients 60–120 seconds for startup and
  tool calls and support retries. Some clients' short defaults may fail on a cold service.
- The measured idle interval plus increased response time is post-idle behavioral evidence;
  direct Render instance lifecycle telemetry was unavailable because browser automation
  stopped when it could not verify the active URL. The restart action was performed by the
  user and verified independently through state/hash comparisons and reconnection.
- Free quotas and Supabase inactivity pausing still apply. Monitor accounts for the entire
  evaluation period; no 30-day uninterrupted availability promise can be made.
- GitHub scheduled jobs can be delayed/dropped and consume private-repository Actions
  minutes. Keep failure notifications enabled and monitor runs; no exact-time SLA.
- SMS is simulated. Its protected inbox is for authorized assessors, not real delivery.
- PostgreSQL holds audit records; local application log files remain ephemeral on Render.
  Free hosting does not replace independent private backups or a retention policy.
- Abandoned uploads can leave private orphan objects; quota/retention cleanup remains
  operational work. No referenced document was deleted in these tests.
- New applications after the unchanged deadline must fail. Evaluator dates after that
  point remain a business decision requiring explicit user approval to change the deadline.

## State left for evaluation

Hosted records: 100004 applications, 200008 audit rows, 9700 deemed applications and
matching deemed audits. Four retained, clearly synthetic cases: APPROVED 100011,
REJECTED 100012, WITHDRAWN 100013, REJECTED 100014. No synthetic case is left pending.
Expired/revoked dedicated test OAuth sessions remain unusable; user Codex sessions work.
Local stack remains running with preserved volumes after its final persistence check.
Private test sessions/snapshots stay under ignored deploy/secrets/stage5-evidence.

**No dashboard was built. Await explicit Stage 6 approval.**
