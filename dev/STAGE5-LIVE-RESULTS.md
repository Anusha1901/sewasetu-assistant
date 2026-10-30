# Stage 5 live client results — 30 October 2026

Deployment: https://sewasetu-assistant-wgcq.onrender.com
Citizen: /mcp/citizen. Officer: /mcp/officer. Both remain Streamable HTTP.
Private source: Anusha1901/sewasetu-assistant. No paid model API integration.

## Real Codex citizen workflow: passed

The user added the custom Streamable HTTP server, completed browser OAuth with a
synthetic mobile ending 0000, and restarted Codex so tools appeared. The assistant
then invoked the actual configured MCP tools, rather than simulating a conversation
through shell HTTP calls:

1. get_scheme_info returned current rules, open application window, Sonari/Rajapara.
2. get_my_applications returned an empty owner-filtered history.
3. prepare_application created a draft for Kamala Devi (Synthetic Test), born
   01/01/1956, Sonari, with fictional address and bank details. It correctly reported
   missing age proof, revision 1, ready_to_submit=false.
4. The user uploaded the clearly marked synthetic PDF in the authenticated browser.
5. prepare_application returned revision 2, has_age_proof=true, no errors and ready=true.
6. The assistant displayed the exact preview and full declaration; the user explicitly
   accepted and requested submission of revision 2.
7. submit_application returned application **SSP26495722**, id **100011**, PENDING.
8. get_my_applications returned the same case. Read-only Supabase checks confirmed
   ownership/block, exactly one submission audit, stored declaration/revision, one active
   case and the uploaded private PDF.

## Real Codex officer workflow: passed

The user separately connected and authenticated the officer resource as assessor.
get_queue_summary returned one pending case in Sonari and zero in Rajapara.
list_applications found SSP26495722. get_application returned masked mobile/bank,
audit, private browser proof link and a session-bound review token. The user was
shown the document link and explicitly told it was synthetic, not genuine age evidence.

The user requested approval with a drafted reason. decide_application with confirmed=false
returned confirmation_required and a preview. The assistant displayed this exact reason:

> Approved solely for the controlled synthetic evaluation to verify the MCP decision and audit workflow. The uploaded document is synthetic; this decision does not establish real-world eligibility or authorize an actual pension payment.

Only after the user said "Confirm this approval and reason" did the assistant call
decide_application with confirmed=true and the returned confirmation token. The server
returned APPROVED, decided_by=assessor. Citizen get_my_applications immediately returned
APPROVED and the same reason. Read-only Supabase checks confirmed one decision audit
with actor admin:assessor, exact reason, decision timestamp, and one active application.
This is an explicitly fictional evaluation record, not verified real-world eligibility.

## Additional live safeguards

- Repeating submit_application with the previously accepted draft/revision returned
  the same id/number and already_submitted=true.
- Replaying the already-consumed officer review/confirmation was rejected as review_required.
- Officer list_applications for Dhemaji Pathar returned unsupported_block, without records.
- Both public resources rejected deliberately invalid bearer tokens with HTTP 401.
- Eight earlier public probes passed: HTTPS portal, DB readiness, canonical OAuth metadata,
  both authentication challenges and resource metadata, and denied unauthenticated SMS inbox.

## Scheduler

The first scheduled-job verification hit its 15-minute limit after decisions/audit committed
while delivering the 700 initial overdue notifications. Aggregate DB checks: 9700 deemed
applications, 9700 deemed audits, zero overdue pending. A targeted idempotent recovery
queued the 41 missing simulated notifications; no application/audit rows changed in recovery.
The workflow limit was increased to 30 minutes. Rerun **41024650173 passed**.
Daily workflow is enabled at 02:00 IST. GitHub timing is best effort, not an exact-time SLA.

## Final verification

The remaining public rejection/withdrawal, expired/revoked sessions, competing decisions,
hosted restart, post-idle reconnect and scheduler repeat checks are now complete.
See STAGE5.md for the final 376-check report, fixes and operational limitations.
Stage 5 is complete. No evaluation dashboard has been built; await Stage 6 approval.
Application deadline remains 31 October 2026 at 23:59 IST. User has not confirmed evaluator dates.
