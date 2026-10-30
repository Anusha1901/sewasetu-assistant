# Stage 6 — public evaluation dashboard

Status: implementation and local checks complete; public deployment verification pending.
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

## Verification to date

- 107 unit/integration cases passed, including 20 new dashboard contract/privacy tests.
- 38 headless-browser checks passed locally at 1440px desktop, 768px tablet, 390px mobile.
  Search, combined filters, empty state, expected/actual expansion, source expansion,
  keyboard skip link, layout overflow and absence of third-party requests were checked.
- Desktop/mobile screenshots visually inspected; no clipping or horizontal overflow.
- Existing local officer protocol suite: 39 passed; portal suite: 76 passed; citizen MCP
  suite: 45 passed. Automatic OAuth, adapter and persistence checks are recorded below
  when completed. Stage 5 source artifacts are frozen; new logs use stage6-* names.
- Production Docker build passed. No dependency changes.

## Public deployment

Pending operator Manual Deploy → Deploy latest commit on the existing Render Free service.
No new hosting resources, credentials or paid plan changes are required. Final public
verification will compare the served export byte-for-byte with the reviewed artifact,
test privacy headers and read-only behavior, render three viewport sizes, rerun public
OAuth/MCP discovery probes, and call both configured MCP resources.

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
