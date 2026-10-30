# Stage 6 — public evaluation dashboard

Status: COMPLETE, 30 October 2026. Stop here pending approval for final submission assets.
Target URL: https://sewasetu-assistant-wgcq.onrender.com/eval-dashboard

## Assignment-first scope

Reviewed BRIEF.md, README.md, the supplied Director transcript, and Stage 1–5 reports.
The brief specifically asks for invented citizens, conversations, expected database
outcomes, what passed, and lessons, evaluated through real MCP clients. This dashboard
therefore presents the actual operator-guided Codex case separately from scripted SDK
fixtures and local regressions. It does not manufacture conversations for scripted cases,
retroactively invent field-study personas, or label local checks as live public tests.

## Implementation

- `app/evaluation_dashboard.py`: read-only Flask Blueprint, registered in the existing app.
  GET/HEAD `/eval-dashboard` and `/eval-dashboard/evidence.json`. No DB queries, credential
  reads, browser session access, case lookup API, state-changing endpoints or new service.
- `app/templates/eval_dashboard.html`: standalone responsive page with summary metrics,
  both Streamable HTTP endpoints, workflow, Sonari/Rajapara boundary, scenario search/scope
  filters, expected/actual outcomes, assertions, synthetic case profiles, selected real
  conversation excerpts, lessons and explicit limitations/NOT TESTED sections.
- `app/static/eval-dashboard.css` and `.js`: self-hosted styles and progressive enhancement;
  no paid dependencies, external fonts, analytics, third-party requests or polling.
- `app/evaluation/evidence.json`: reviewed historical Stage 5 snapshot used by HTML and
  byte-exact JSON export. Displayed SHA-256 matches the exported file.
- `dev/build_evaluation_evidence.py`: deterministic compiler validates source results,
  counts, assertion references, privacy patterns and saved synthetic DB outcomes.
  Canonical UTF-8/LF output preserves the displayed digest across Windows and Linux.
- `dev/verify_stage6_reproducibility.py`: rebuilds from only the compiler and committed
  evidence in an isolated directory, without deployment credentials or private snapshots.
- `dev/archive_stage6_results.py` and `dev/evidence/stage6/results.json`: reviewed Stage 6
  assertion outcomes and source digests, excluding raw MCP responses or private links.
- `dev/evidence/stage5/`: reviewed raw assertion artifacts plus a narrow four-case DB
  attestation. Kept in the PRIVATE repo so evaluators can reproduce the snapshot without
  accessing live credentials. `.gitattributes` preserves checksummed bytes across platforms.
- `dev/archive_evaluation_evidence.py`: initial allowlist archive with credential, phone,
  private-link and database-DSN checks. Never copies private session files or documents.
- Portal footer links to evaluation results. Existing portal layout and functionality
  otherwise preserved. No MCP, OAuth, scheduler, eligibility or deadline code was changed.

## Evidence and provenance

The historical baseline remains **376 checks: 275 LOCAL and 101 LIVE**, all from Stage 5.
Twenty dashboard unit tests and new browser/deployment checks are Stage 6 verification;
they are not silently added to or relabeled as the historical Stage 5 baseline.

There are 22 scenario entries: 19 evidence-backed outcomes and three explicitly NOT TESTED
areas. A scenario is not another independent check count; it references recorded assertions.
Eight read-only DB assertions corroborate the real Codex run but are not counted twice.

Cases are allowlisted synthetic IDs 100011–100014. Kamala (70, Sonari) is the actual Codex
operator-guided case. The rejection, withdrawal and competing-decision fixtures (76,
Rajapara) reused one dedicated synthetic identity sequentially; this is stated explicitly.
Each card includes its actual test name, village, interaction type, goal and database
expectation. No invented SDK chat is displayed. Selected user quotes are actual excerpts;
tool summaries are labeled as summaries, not presented as verbatim agent utterances.

Only the date 2026-10-30 is asserted for the snapshot. Per-assertion timestamps were not
recorded and are not invented. The cold-start numbers are actual measurements, with the
limitation that direct Render instance lifecycle telemetry was unavailable.

## Privacy and security

Only synthetic case fields and reviewed assertion names are public. No phone numbers,
bank details, passwords, OTPs, access/refresh tokens, private document/capability links,
raw snapshots, signing keys or database DSNs are included. Source artifacts are outside
the Flask static directory and excluded from the production Docker context by dev/.

The export has a constant bundled file path; query parameters cannot choose a file or
case. HTML autoescapes all evidence strings. Restrictive CSP blocks external scripts,
connections, framing, form submission and base-URL changes; nosniff/no-referrer are set.
The page sets no authentication cookie and never reads the user's existing identity.
No background traffic keeps Render artificially awake. Source digests identify evidence
files; they are not a signature or third-party attestation.

## Final verification

- 107 unit/integration cases passed, including 20 new dashboard contract/privacy tests.
- 38 headless-browser checks passed locally at 1440px desktop, 768px tablet, 390px mobile.
  Search, combined filters, empty state, expected/actual expansion, source expansion,
  keyboard skip link, layout overflow and absence of third-party requests were checked.
- Desktop/mobile screenshots visually inspected; no clipping or horizontal overflow.
- Existing local officer protocol suite: 39 passed; portal suite: 76 passed; citizen MCP
  suite: 45 passed; automatic SDK OAuth: 3 passed; hosted adapters: 10 passed;
  post-restart local persistence and duplicate protection: 15 passed.
- Independent evidence reproduction: 1 passed.
- Public dashboard HTTP, privacy and evidence checks: 20 passed.
- Public headless-browser checks: 38 passed at the same three viewport sizes; desktop
  and mobile screenshots visually inspected. No clipping, overflow or third-party requests.
- Public portal/OAuth/resource discovery/MCP authentication-boundary probes: 8 passed.
- Real authenticated Codex citizen get_scheme_info and officer get_queue_summary: 2
  passed after deployment. Only outcome booleans were archived, never session-finish URLs.
- **402 final checks passed, zero final failures**: 295 local regression assertions,
  38 local browser checks, 1 reproducibility assertion, 20 public dashboard checks,
  38 public browser checks, 8 public probes, 2 real-client checks. The repeated 20-case
  release-only suite is not counted again. The final 107-case unittest run enabled
  RUN_DB_TESTS=1, passed with no skips. Stage 5 logs and public 376-check snapshot are frozen.
- Production Docker build passed. No dependency changes.

## Public deployment

Operator manually deployed commit 53a093e on the existing Render Free service and
confirmed Live. Public verification completed against:

- https://sewasetu-assistant-wgcq.onrender.com/eval-dashboard — HTTP 200 without login.
- https://sewasetu-assistant-wgcq.onrender.com/eval-dashboard/evidence.json — reviewed,
  sanitized snapshot; exact served bytes match the displayed SHA-256 and local bundle.
- https://sewasetu-assistant-wgcq.onrender.com/mcp/citizen — authenticated real-client
  scheme lookup works; unauthenticated calls denied with OAuth discovery advertised.
- https://sewasetu-assistant-wgcq.onrender.com/mcp/officer — authenticated real-client
  permitted queue works; unauthenticated calls denied with OAuth discovery advertised.

No new resources, credentials, paid plans or public DB administration endpoints.
Production code changes are limited to dashboard files, Blueprint registration and the
portal footer link. MCP/OAuth/shared-services/scheduler behavior was not changed.
Compiler line-ending and documentation follow-ups do not alter the deployed runtime.

Local restart retained six Stage One synthetic applications and their proofs/audits,
70 OAuth clients, and 9702 deemed approvals with 9702 matching audits. All 100000 seed
rows remain. Stage 6 did not submit or decide any new public application. Stage 5's
hosted restart, scheduler execution and cold-start evidence is historical evidence, not
misrepresented as a new Stage 6 repeat of those scenarios.

Tests live in app/tests/test_evaluation.py and dev/verify_stage6_{public,reproducibility}.py,
dev/verify_stage6_browser.cjs. Archived sanitized results: dev/evidence/stage6/results.json.
Browser screenshots are local ignored artifacts under output/stage6/.

## Limitations and remaining submission tasks

- NOT TESTED: evaluator's Claude Code/small-model client; multilingual or in-person kiosk
  usability; full-duration session-expiry observation and uninterrupted 30-day uptime.
- Codex was operator-guided; this is not an elderly-applicant field study. The synthetic
  proof explicitly states that it is not genuine age evidence; approval is evaluation-only.
- Snapshot evidence is historical, not continuous monitoring or a guarantee of security.
- Deadline stays 31 October 2026, 23:59 IST; after closing, new submissions must fail.
- Free Render cold starts, Supabase quotas/pausing, simulated SMS and best-effort GitHub
  scheduling remain. No deadline extension or new paid infrastructure was introduced.
- Final submission assets remain a separate, approval-gated stage: private evaluator repo
  invitation, officer credentials through a private channel, repo ZIP including .git,
  three-minute face/screen Loom, and one-page three-decisions design note. No assets or
  invitations were sent during this stage.
