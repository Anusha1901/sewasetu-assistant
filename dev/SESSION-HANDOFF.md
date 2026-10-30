# Session handoff — 30 October 2026

## Current work: Stage 5 free Render/Supabase preparation

The user approved Stage 5 and chose Render Free after reviewing hosting constraints.
They created private GitHub repo `Anusha1901/sewasetu-assistant`, a Render account,
and Supabase project `ipbcvfrdeeqvbhysscdi` with private `age-proofs` bucket; actual
region was selected automatically. No remote secrets have been entered yet.
See `dev/STAGE5-PREPARATION.md` and `deploy/RENDER.md` for exact current status.
All original 247 checks plus 24 hosting checks passed locally (271 total).
The dev stack remains running with preserved volumes. Latest counts for persistence:
STAGE1_EXPECTED_APPLICATIONS=27, STAGE1_EXPECTED_CLIENTS=43, STAGE1_EXPECTED_DEEMED=9703.

Next user action: run `python deploy/setup_render.py` from project root; enter the
Supabase Session pooler URI (5432) and legacy service_role key in hidden local prompts.
It creates ignored deploy/secrets/render.env and render-officer.json. Never print them
or ask the user to paste keys/passwords into chat. Do not import/reset Supabase until
ready; initialization refuses nonempty schema. Public deployment and external AI-client
tests are still outstanding. GitHub CLI auth works outside the restricted environment;
the connector cannot access the private repository. Source had no original Git history.
No scheme/deadline or original cron/script changes were made; evaluator dates unconfirmed.

## Historical Stage 4 handoff (superseded counts below)

Stages 1–4 are complete locally. Stop here and wait for the user's next-stage approval.
The Officer MCP and Citizen MCP are implemented; the evaluation dashboard is not built.

The isolated `sewasetu-stage1-dev` stack is RUNNING (app, db, scheduler, smsgw).
The user authorized restarting it for Stage 4. All database/uploads/logs remain in the
same dedicated development volumes. Do not delete/reset them or modify the seed.

Latest report: `dev/STAGE4.md` (full file inventory, authentication design, test evidence
and deployment/evaluation risks). Previous reports remain historical evidence.
Latest result: **247 checks passed, zero final failures**, including the original 188.

Endpoints:
- http://localhost:8000/mcp/citizen — five citizen tools.
- http://localhost:8000/mcp/officer — four officer tools.
- http://localhost:8000/ — existing web portal.

Both MCPs use the existing OAuth server and shared business services. Both enforce
CITIZEN_MCP_BLOCKS (default Sonari,Rajapara). Officer decisions require inspection,
a proposal with reason, and explicit token-bound confirmation. Changes use shared
atomic pending-only decision/audit logic; terminal states cannot be overwritten.
Citizen tool/preparation/upload modules are unchanged; shared auth/gateway interfaces
were extended for officer compatibility. No paid AI model integration was introduced.

Seed, scheme configuration, deemed-approval script and crontab are unchanged.
Deadline: **31 October 2026, 23:59 IST**. Never modify it without explicit user approval.

Development credentials remain in ignored `dev/.env.local`; officer username `admin`.
Never print or commit the credential file. Migrations 001, 002 and 003 are already applied.

From the nested project directory, PowerShell:

```powershell
docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml up -d
docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml ps
docker compose --env-file dev/.env.local -p sewasetu-stage1-dev -f dev/compose.yml stop
```

Docker executable if PATH is stale:
`C:\Users\anush\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe`.
Docker Desktop must run Linux containers; Docker access may require execution outside
this task's sandbox. For builds, add that directory to the command's PATH for the
credential helper. Existing Dockerfiles still build the combined ASGI/Flask listener.

Retained test snapshot: 24 Stage One synthetic applications, three Stage Three cases,
12 Stage Four cases, 34 OAuth clients. Two Stage Four cases exercised the actual unchanged
15-day job, so deemed-approved application and audit counts are both 9702. Use
STAGE1_EXPECTED_APPLICATIONS=24, STAGE1_EXPECTED_CLIENTS=34 and
STAGE1_EXPECTED_DEEMED=9702 for the original persistence script. Additional workflow
runs increase these values. Test-created pending cases are withdrawn at script exit.

Remaining before public deployment/evaluation: HTTPS hosting/correct PUBLIC_BASE_URL,
manual external-client account testing, named staff accounts and credential management,
authorized SMS simulation or real SMS, upload-browser continuity, retention cleanup,
legacy security considerations, and evaluation dates after the unchanged deadline.
Do not start the dashboard or any further stage without the user's approval.
