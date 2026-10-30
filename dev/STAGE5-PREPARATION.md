# Stage 5 preparation — 30 October 2026

Stage 5 is **not complete**. Render/Supabase accounts and a private age-proofs bucket
were created by the user. No deployment, Supabase import, remote credential validation,
or real external AI-assistant conversation has been performed by this work yet.

## Local result

**271 checks passed, zero final failures:**

| Suite | Passed |
| --- | ---: |
| Unit and isolated-schema integration tests | 83 |
| Original portal, OAuth, SMS and DB workflow | 76 |
| Restart persistence and duplicate checks | 15 |
| Citizen MCP workflow | 45 |
| Citizen SDK automatic OAuth client | 3 |
| Officer SDK OAuth and MCP workflow | 39 |
| Hosted seed/private-schema/persistent-SMS rehearsal | 10 |
| Total | 271 |

This includes all previous 247 checks and 24 new checks. The first unit invocation
omitted RUN_DB_TESTS and skipped DB cases; the corrected final invocation explicitly
enabled it and ran all 83 tests with no skips. Both original and hosted Docker images
build. Source integrity checks confirm original seed, scheme INI, approval script,
and crontab bytes remain unchanged. Generated test logs remain ignored local artifacts.

The hosted-adapter rehearsal created a uniquely named disposable local database,
imported all 100000 original applications into schema sewasetu, checked PUBLIC has no
schema privileges, refused a repeat seed import, persisted SMS through module reload,
and removed only that disposable test database. It did not contact Supabase.
The document REST tests mock the provider: actual Supabase upload/download and private
bucket behavior still require live testing with the backend key.

The isolated development stack remains running. Latest retained fixture snapshot:
27 Stage One applications, 4 Stage Three applications, 18 Stage Four applications,
43 OAuth clients, 9703 deemed applications and matching deemed audit rows. All synthetic
pending cases were finalized/withdrawn by the workflow cleanup. Development uploads
and audit data survived a full stack stop/start.

## Files and behavior

- `app/documents.py`: bounded private Supabase REST storage with local default, random
  object names, no public URLs, strict references, closed failure behavior, private bucket check.
- `app/runtime_db.py`: optional TLS-required hosted DSN and private search_path;
  services.get_db retains original INI behavior without DATABASE_URL.
- `app/app.py`, `citizen.py`, `citizen_web.py`, `officer.py`, `officer_web.py`: route
  document operations through storage, retaining caller authorization, ownership,
  confirmation, validation and content-hash checks. Existing MCP transport/tool logic untouched.
- `app/gateway.py`: readiness route prepared earlier in Stage 5.
- `app/migrations/004_simulated_sms.sql`, `smsgw/app.py`: opt-in persistent SMS adapter;
  original in-memory default remains for development. Hosted simulator is loopback-only.
- `deploy/render.Dockerfile`, `render_start.py`, `initialize_hosted.py`, `render.yaml`:
  one hosted web listener plus loopback SMS, explicit empty-schema seed import, reusable migrations,
  and no automatic reseeding. The original deemed-approval script runs unchanged in scheduler mode.
- `.github/workflows/deemed-approval.yml`: opt-in single scheduler, 02:00 IST; no paid Render cron.
- `deploy/setup_render.py`: hidden local credential entry, ignored private output, no chat secrets.
- `deploy/RENDER.md`, README: step-by-step setup and limits.
- `app/config/app.ini.example`, `.gitignore`, `.dockerignore`: sanitized sample instead of
  publishing original private INI; exclude secrets, backup files, tokens, logs and dev Docker context.
- `app/tests/test_hosted.py`, `dev/verify_hosted_adapters.py`: 24 additional checks.
- Existing generic VM preparation under deploy/ remains an alternative, not provisioned.

## Git and remaining work

The source directory had no Git history at the beginning of this preparation. A new
repository was initialized; earlier stage history cannot be reconstructed honestly.
User's target repository was verified private and empty through authenticated GitHub CLI.
The GitHub connector could not access it, but the CLI connection works. Private environment
and INI files are ignored. The staged-file audit found no private files or credential patterns.
Only synthetic/local development credentials appear in examples and Compose defaults.

Next: user runs the hidden-input helper with Session pooler URI (5432) and legacy
service_role key, then assistant imports into the empty evaluation schema, validates the
real private bucket, and guides the user through Render environment settings and deployment.
Only after public startup: HTTPS/OAuth probes, cold-start checks, real external AI clients,
actual Supabase DB/audit verification, remote document/SMS restart checks, and scheduler run.

Deadline remains **31 October 2026 at 23:59 IST**. The user supplied a project reference
but has not confirmed evaluator dates. Do not extend the deadline without approval.
Render cold starts, free quotas, Supabase inactivity pausing, GitHub scheduled-job delays,
ephemeral file logs, orphan object cleanup and single-worker memory usage remain risks.
No evaluation dashboard, paid model integration, purchased domain, or paid hosting was added.
