# Render Free + Supabase Free evaluation deployment

Status: locally prepared and tested; not publicly deployed or tested with an external AI assistant.
The portal and both MCP resources keep Streamable HTTP. No paid model API is used.
Keep the GitHub repository private: the supplied seed contains personal records.

## Account choices

- One Render Free web service runs Uvicorn (one worker) and an internal SMS simulator.
- Existing Supabase project `ipbcvfrdeeqvbhysscdi` provides PostgreSQL and private `age-proofs` storage.
- Portal tables live in the **sewasetu** schema, outside Supabase's default exposed API schemas.
  Initialization revokes PUBLIC/anon/authenticated schema and table privileges. Do not expose this
  schema through the Supabase Data API or grant anonymous access to it.
- OAuth stays in the existing portal; do not configure Supabase Auth for this application.
- Documents are uploaded/downloaded by the backend after the existing browser/actor checks.
  No public bucket, public object URLs, or service-role key in browser JavaScript.
- Simulated SMS is persisted in PostgreSQL; its HTTP service binds only to 127.0.0.1:8025.
  Assessors read messages through the existing officer-authenticated `/__gateway/` proxy.

The free plans have quotas and no availability promise. Render sleeps after 15 minutes idle;
first requests may wait roughly a minute. Supabase may pause an inactive free project after
one week. Watch both dashboards and preserve separate encrypted backups. Do not use a paid
Render database, disk, background worker, cron service, or a custom purchased domain.

## 1. Enter secrets locally

From the project root in PowerShell, run `python deploy/setup_render.py`.

In Supabase, click **Connect**, choose **Session pooler**, and copy the PostgreSQL URI on
**port 5432**. Use the session pooler, not the transaction pooler on port 6543: the application
uses transaction locks and the scheduler requires predictable connection state. It is also
the IPv4-compatible choice. The helper hides your input and substitutes the separately
entered database password if the URI contains `[YOUR-PASSWORD]`.

Find **Settings → API Keys → Legacy API Keys → service_role**. Enter that key only in the
hidden local prompt. Never use the anon/publishable key, paste a backend key into chat, or
put a key in GitHub source. The helper checks the role and project reference, but this is
only a format check; it does not authenticate the key with Supabase.

Output: ignored `deploy/secrets/render.env` and `deploy/secrets/render-officer.json`.
They contain credentials. Windows file permissions depend on the user's profile/drive ACL;
the POSIX mode settings in Python are not a replacement for Windows ACL protection.

## 2. Import once, explicitly

After the assistant reviews the local preparation, build the deployment image:

```powershell
docker build -f deploy/render.Dockerfile -t sewasetu-render-local .
docker run --rm --env-file deploy/secrets/render.env sewasetu-render-local python /app/hosting/render_start.py initialize
```

This is an explicit write to the evaluation Supabase project. Run it only when ready to
initialize that project. The importer creates a private schema and loads the original seed,
then applies migrations in one transaction. It requires an empty schema and refuses a repeat
import rather than clearing records. It never seeds on ordinary application startup.
It does not copy local development test records, local keys, or local OTPs to Supabase.

## 3. Create the Render service

Once code is pushed to the private repository:

1. New → Web Service → connect `Anusha1901/sewasetu-assistant`.
2. Branch `main`; runtime **Docker**; repository root directory unchanged.
3. Dockerfile path `./deploy/render.Dockerfile`; Docker context repository root (`.`).
4. Name `sewasetu-evaluation` (or an available name), select **Free**.
5. Prefer the region closest to the Supabase project's actual region.
6. Use **Add from .env** to enter the contents of the local private `render.env` directly
   into Render's secret environment settings. Do not commit that file.
7. Replace `PUBLIC_BASE_URL` with the service's actual `https://<name>.onrender.com` URL,
   without a trailing slash. Never leave `replace-me.onrender.com` configured.
8. Set health-check path `/healthz`. Turn automatic deployment off during evaluation.
9. Deploy only after the database import and secret settings are complete.

The Docker entrypoint reads Render's PORT. HTTPS is provided by Render; no Caddy or custom
domain is required. Render must be the only public ingress because Uvicorn trusts proxy
forwarding headers. The startup check rejects a public age-proof bucket. Persistent database
state, unchanged SECRET_KEY and unchanged public hostname keep OAuth sessions across restarts.
The deployment copies only a sample INI; private config is generated inside the disposable
container. Original local INI, seed, pension deadline, eligibility and cron script stay unchanged.

The root `render.yaml` is an alternative Blueprint for the same single Free service. Manual
setup makes it easier to set the actual public hostname before the first successful startup.
The Blueprint's deployment trigger is quoted 'off' so YAML readers do not parse it as false.

## 4. Enable automatic approval

The `.github/workflows/deemed-approval.yml` workflow runs the original script at 02:00 IST
using an ephemeral container with the same database and persistent internal SMS simulator.
The original 15-day cutoff, status changes, reasons and audit logic are not duplicated.

In the private repository:

1. Settings → Secrets and variables → Actions → add repository secret **DATABASE_URL**,
   using exactly the private session-pooler URI from the local render.env.
2. Add repository variable **ENABLE_PENSION_SCHEDULER** = **true** only after seed import.
3. Actions → Statutory deemed approval → Run workflow, and inspect the result.
4. Enable failure notifications and check scheduled runs throughout evaluation. Scheduled
   GitHub workflows may run late or be dropped; this is not an exact-time service guarantee.
   If a run fails, repair and rerun the same job; do not reset the deadline or patch statuses.

The workflow is disabled by default until the variable is set. Free private-repository Actions
minutes must remain available; do not enable paid overages. It builds its own image from the
private checkout and never uploads database dumps, OTPs, or credentials as workflow artifacts.
Run only one scheduler; do not also enable a second cron container against this hosted database.

## 5. Verify before submission

- Portal `/`, readiness `/healthz`, OAuth AS discovery and both protected-resource metadata.
- `/mcp/citizen` and `/mcp/officer` return an OAuth challenge without valid tokens.
- `/__gateway/` and its message API deny unauthenticated requests.
- Officer sign-in and SMS-console access use a separate browser profile from citizen OAuth.
  The assistant must never receive the assessor's password or an OTP.
- Real external client: discovery, OAuth/PKCE, upload, declaration, submit, status, case
  inspection, exact-reason decision preview/confirmation, then verify DB and audit records.
- Restart/redeploy and repeat status, private document and SMS checks.
- Let Render sleep, then test a fresh external-client connection. Opening `/healthz` first
  can warm it for supervised testing but does not fix an evaluator's unattended cold start.
- Test invalid tokens, expired links, disallowed blocks, duplicates and competing decisions.

Public URLs are the actual Render base plus `/mcp/citizen` and `/mcp/officer`.
`deploy/probe_public.py --base-url <url>` provides read-only HTTPS discovery/security checks;
inspect its usage if arguments change. Passing that probe is not real AI-client evaluation.

## Deadline and remaining limits

The scheme closes **31 October 2026, 23:59 Asia/Kolkata**. New applications after that date
must fail under current rules, independently of hosting. Status, withdrawal when pending,
officer decisions and automatic approval continue. Obtain evaluator dates; no deployment
script extends or bypasses this deadline. The evaluation dashboard is not implemented yet.

Supabase storage writes and PostgreSQL draft updates cannot be a distributed atomic
transaction. Failed/abandoned uploads may leave private orphan objects, consuming quota;
never delete referenced documents during evaluation. Object responses are bounded to 5 MB
and storage failures stop operations rather than silently accepting a missing proof.
Audit records and SMS persist in PostgreSQL; local application/cron log files are ephemeral.
The Render service's single-worker memory usage and real cold-start client behavior still
need measurement on the actual free host. Back up evaluation records before changing providers.

References: https://render.com/docs/free, https://supabase.com/pricing,
https://supabase.com/docs/guides/database/connecting-to-postgres,
https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
