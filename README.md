# Seva Setu Assistant

AI-assisted access to the Seva Setu old-age pension portal, built for the **Build for Bharat** assignment. Citizens can apply and follow up through an AI assistant, while officers can review and decide applications through a separate MCP channel. The existing portal remains the system of record.

## Live Deployment

| Service | Public URL |
| --- | --- |
| Citizen portal | [Open Seva Setu](https://sewasetu-assistant-wgcq.onrender.com/) |
| Citizen MCP | [Citizen endpoint](https://sewasetu-assistant-wgcq.onrender.com/mcp/citizen) |
| Officer MCP | [Officer endpoint](https://sewasetu-assistant-wgcq.onrender.com/mcp/officer) |
| Evaluation dashboard | [View evaluation results](https://sewasetu-assistant-wgcq.onrender.com/eval-dashboard) |

Both MCP endpoints use **Streamable HTTP** and require OAuth authentication. They are protocol endpoints, not ordinary web pages. Render Free may take a short time to wake after inactivity.

## What It Does

### Citizen Workflow

Read official scheme information, prepare an application, upload age proof privately, review the declaration, submit with explicit acceptance, check status, or withdraw a pending application.

### Officer Workflow

View the permitted queue, inspect a case, and approve or reject it with a mandatory reason. Every decision requires a preview and explicit confirmation, with the authenticated officer recorded in the audit trail.

### Shared Rules

The portal and both MCP servers reuse the same business services and PostgreSQL records. Eligibility remains age **60 or above**, pension **₹250 per month**, and automatic approval after the **15-day** statutory period. New submissions close on **31 October 2026 at 23:59 IST**; follow-up and officer processing remain available afterward.

Agent access is limited to **Sonari and Rajapara** through a configurable allowlist. The web portal retains all six blocks.

## Architecture and Security

- **Flask portal + official MCP SDK:** one application deployment with separate citizen and officer tool registries.
- **PostgreSQL:** shared applications, OAuth sessions, and transactional decision/audit records.
- **OAuth with PKCE:** browser-based citizen OTP and officer login; tokens are checked for identity, role, scope, audience, expiry, and revocation.
- **Private document storage:** validated, expiring, ownership-checked upload and viewing flows.
- **Render + Supabase + GitHub Actions:** free-tier hosting, persistent database/documents, protected SMS simulation, and scheduled statutory processing.

Passwords, OTPs, tokens, and private documents must never be shared with the assistant or committed to this repository. Evaluator credentials are provided privately. The SMS gateway is simulated and requires authorized access.

## Evaluation

The public dashboard presents expected versus actual outcomes, synthetic test cases, selected real Codex interactions, database assertions, and source evidence. It distinguishes local regression tests from live public MCP checks and labels untested scenarios explicitly.

The recorded Stage 5 baseline is **376 passing checks**; Stage 6 dashboard and regression verification completed with **402 passing checks**. Detailed results and limitations are documented in the stage reports.

## Repository Guide

| Directory | Contents |
| --- | --- |
| `app/` | Flask portal, MCP servers, shared services, OAuth, migrations, and tests |
| `deploy/` | Hosting configuration and deployment helpers |
| `dev/` | Stage reports, verification scripts, and reviewed evaluation evidence |
| `seed/` | Original assignment-provided database snapshot; handle privately |
| `smsgw/` | Simulated SMS gateway |

For deployment instructions, see [Render and Supabase setup](deploy/RENDER.md). For implementation and verification details, see [Stage 5](dev/STAGE5.md) and [Stage 6](dev/STAGE6.md).
