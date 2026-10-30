"""Compile an allowlisted PUBLIC snapshot, never publish raw logs or database exports."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'app/evaluation/evidence.json'
ARCHIVE = ROOT / 'dev/evidence/stage5'


def build():
    baseline = json.loads((ARCHIVE / 'stage5-final-summary.json').read_text())
    sources, checks = [], []
    for filename, expected in baseline['counts'].items():
        unit = filename == 'unit_and_integration'
        filename = 'stage5-final-unit-integration.txt' if unit else filename
        raw = (ARCHIVE / filename).read_bytes()
        text = raw.decode('utf-8-sig')
        source_id = 'suite-' + str(len(sources) + 1)
        scope = 'LOCAL' if unit or filename.startswith(('stage5-final-main', 'stage5-final-citizen', 'stage5-final-officer', 'stage5-final-persistence', 'stage5-final-hosted')) else 'LIVE'
        if filename == 'stage5-final-public-probe-results.jsonl':
            scope = 'LIVE'
        if unit:
            names = sorted(set(re.findall(r'test_\w+ \([\w.]+\)', text)))
            assert len(names) == expected and re.search(r'Ran 87 tests', text) and '\nOK' in text and 'FAILED' not in text and 'skipped=' not in text
            records = [{'check': name, 'passed': True} for name in names]
        else:
            records = []
            for line in text.splitlines():
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict) and isinstance(record.get('passed'), bool):
                    records.append({'check': record['check'], 'passed': record['passed']})
            assert len(records) == expected and all(r['passed'] for r in records), filename
        sources.append({'id': source_id, 'name': filename, 'scope': scope,
                        'sha256': hashlib.sha256(raw).hexdigest(), 'count': len(records)})
        for index, record in enumerate(records, 1):
            checks.append({'id': source_id + '-' + str(index), 'source_id': source_id,
                           'scope': scope, 'name': record['check'], 'status': 'PASS' if record['passed'] else 'FAIL'})
    assert len(checks) == baseline['total_passed'] == 376
    assert sum(c['scope'] == 'LOCAL' for c in checks) == 275
    assert sum(c['scope'] == 'LIVE' for c in checks) == 101

    def refs(*fragments):
        result = []
        for fragment in fragments:
            found = [c['id'] for c in checks if fragment.casefold() in c['name'].casefold()]
            assert found, 'Missing evidence: ' + fragment
            result.extend(found)
        return list(dict.fromkeys(result))

    definitions = [
        ('submission', 'Citizen application submission', 'Citizen', 'LIVE', 'A verified citizen can prepare, upload, accept the current declaration and submit once.', 'Public SDK submission returned PENDING; SQL checked the authenticated owner and persisted case. Codex separately completed the Kamala workflow.', ['Rejection synthetic case submitted through public MCP', 'MCP submission persisted']),
        ('approval', 'Officer approval and actor attribution', 'Officer', 'LOCAL', 'Inspection and an exact confirmed reason produce one authenticated officer audit.', 'Local protocol checks passed. The real Codex approval of Kamala is separately documented below with database corroboration.', ['approval uses authenticated officer', 'approval reason and actor persisted']),
        ('rejection', 'Officer rejection with a mandatory reason', 'Officer', 'LIVE', 'A blank reason is refused; confirmed rejection records the exact reason and authenticated actor.', 'Public rejection succeeded, the preview left the case pending, and the citizen saw REJECTED with the same reason.', ['requires nonblank reason on public server', 'rejection audit records exact reason', 'citizen sees rejected status']),
        ('withdrawal', 'Citizen withdrawal', 'Citizen', 'LIVE', 'Only the owner can withdraw a pending case after confirmation.', 'Public withdrawal changed the case to WITHDRAWN and recorded the authenticated citizen. A repeated withdrawal was rejected.', ['public withdrawal requires explicit confirmation', 'public citizen withdrawal succeeds', 'withdrawal audit uses authenticated citizen']),
        ('eligibility', 'Age, details and bank validation', 'Citizen', 'LOCAL', 'Underage applicants and malformed required details cannot submit.', 'Local web, shared-service and MCP checks rejected underage, invalid DOB, bank and block inputs. No claim of a live natural-language eligibility interview.', ['underage submission rejected', 'invalid bank submission rejected', 'invalid application returns errors']),
        ('documents', 'Private proof and declaration binding', 'Citizen', 'MIXED', 'Missing proof prevents readiness; uploads require the OAuth browser, valid content and the current accepted revision.', 'Public proof/readiness checks passed. Local checks rejected copied links, CSRF failures, invalid PDFs, stale previews and non-boolean declarations.', ['missing proof prevents submission readiness', 'upload link alone is not identity', 'upload CSRF rejected', 'stale document preview rejected', 'declaration must be a real boolean']),
        ('blocks', 'Supported and unsupported blocks', 'Security', 'MIXED', 'Agent operations are restricted to Sonari and Rajapara; filters cannot expand scope.', 'Public officer access to an unsupported block was denied. Local citizen preparation/submission for unsupported blocks was refused.', ['unsupported officer block remains denied', 'unsupported block rejected in preparation', 'unsupported block rejected on submit']),
        ('oauth', 'OAuth discovery, PKCE and tool separation', 'Security', 'MIXED', 'The two resources expose separate tools and require appropriate OAuth identities.', 'Public SDK clients discovered five citizen tools and four officer tools. Both cross-role token attempts were rejected; local automatic discovery/PKCE checks passed.', ['citizen SDK discovers five tools', 'officer SDK discovers four tools', 'citizen token cannot access officer MCP', 'officer token cannot access citizen MCP', 'official SDK automatic resource/AS discovery']),
        ('expiry', 'Expired and revoked sessions', 'Security', 'LIVE', 'Expired or revoked grants cannot access protected tools or refresh access.', 'Dedicated public test sessions were expired at the server and denied; real OAuth revocation also denied access and refresh for both roles. User Codex sessions were untouched.', ['expired server session rejects protected tools', 'expired session cannot refresh', 'revoked access cannot reach protected tools', 'revoked refresh token cannot mint new access']),
        ('ownership', 'Citizen ownership boundaries', 'Security', 'LIVE', 'Knowing another application ID must not grant authority over it.', 'The public synthetic identity could not withdraw the other citizen test case. Cross-role checks also denied access.', ['synthetic identity cannot withdraw another citizen case']),
        ('shared', 'Shared-session isolation and sign-out', 'Security', 'LOCAL', 'Drafts belong to the sign-in session; ending it immediately blocks further access.', 'Local tests covered separate sessions for the same mobile, sign-out and immediate access/refresh revocation. This is protocol isolation, not a kiosk usability study.', ['test_same_mobile_different_session_cannot_read_draft', 'signed-out access token immediately rejected', 'signed-out refresh rejected']),
        ('idempotency', 'Duplicate submissions and idempotency', 'Citizen', 'MIXED', 'Retries of the same accepted draft return the same case; active duplicates are blocked.', 'Public retry after rejection returned the original application. Local concurrent submission and database-constraint checks passed.', ['submission retry remains idempotent after rejection', 'test_concurrent_submissions', 'test_direct_database_duplicate_protection']),
        ('competition', 'Competing officer decisions', 'Officer', 'LIVE', 'Two confirmations on one pending case produce exactly one decision and audit.', 'Two independently authenticated public SDK clients raced opposite decisions. REJECTED won; exactly one matching audit was verified.', ['two independent officer clients have exactly one winner', 'competing decisions produce exactly one decision audit', 'race outcome is stored without overwrite']),
        ('terminal', 'Terminal decisions cannot be overwritten', 'Officer', 'LOCAL', 'Approved, rejected, withdrawn and deemed-approved cases are terminal.', 'Local decision, replay, withdrawal-race and statutory-approval guards passed; the earlier Codex decision replay was also denied.', ['replayed decision cannot overwrite', 'withdrawn case cannot be decided', 'deemed approval cannot be overwritten']),
        ('scheduler', '15-day scheduler and repeat-run audit safety', 'Reliability', 'MIXED', 'Only overdue pending cases transition; immediate repeat/race must not duplicate audit or notification.', 'Two fixed GitHub runs succeeded with unchanged hosted counts. Disposable-schema regressions reproduced then fixed duplicate audits and retained the original cutoff.', ['fixed GitHub scheduler run', 'scheduler reruns do not add duplicate audit entries', 'test_immediate_repeat_does_not_duplicate_audit_or_notification', 'test_recent_pending_case_keeps_original_fifteen_day_cutoff']),
        ('persistence', 'Hosted restart persistence', 'Reliability', 'LIVE', 'Restarting the web service preserves records, private PDF bytes, audits and simulated messages.', 'After the operator restarted Render, synthetic case and document/audit hashes matched the baseline and a fresh SDK called a protected tool.', ['application records and exact private documents persist', 'persistent global audit_count unchanged', 'persistent global simulated_message_count unchanged', 'reconnected client calls protected officer tool']),
        ('cold', 'External MCP reconnect after idle', 'Reliability', 'LIVE', 'An OAuth-authenticated external MCP client can reconnect after the free host is idle.', 'After 988.6 seconds of quiet, first response took 24.634 seconds; full protected SDK reconnect took 25.844 seconds, first attempt successful. This is behavioral evidence, not Render lifecycle telemetry.', ['cold reconnect waits at least sixteen minutes', 'external MCP client connects on first post-idle attempt']),
        ('public', 'Public HTTPS, discovery and SMS privacy', 'Security', 'LIVE', 'Public endpoints advertise the canonical issuer; protected MCP and SMS routes require authentication.', 'All eight public deployment probes passed, including both resource metadata checks and denial of unauthenticated SMS-inbox access.', ['portal TLS and homepage', 'canonical OAuth issuer', 'SMS inbox is not public']),
        ('deadline', 'Application deadline boundary', 'Citizen', 'LOCAL', 'After the configured cutoff, submissions fail while follow-up remains possible.', 'Local tests patched only their test clock to verify the exact deadline and post-deadline behavior. Production clock and configuration were not changed.', ['test_deadline_exactly_preserved', 'test_deadline_rejects_submission_but_not_followup']),
    ]
    scenarios = [{'id': a, 'title': b, 'category': c, 'scope': d, 'expected': e, 'actual': f,
                  'status': 'PASS', 'check_ids': refs(*g)} for a,b,c,d,e,f,g in definitions]
    for ident, title, category, expected, actual in [
        ('claude', 'Evaluator’s Claude Code client', 'Security', 'Repeat the workflow in the evaluator’s own client and small model.', 'NOT TESTED: Codex and the official Python SDK were used. Claude Code compatibility has not been directly verified.'),
        ('language', 'Multilingual or in-person kiosk usability', 'Citizen', 'Observe elderly applicants, shared-phone helpers and informal local-language requests.', 'NOT TESTED: no field study, natural-language local-language run or physical kiosk accessibility study was performed.'),
        ('wallclock', 'Full-duration expiry and 30-day availability', 'Reliability', 'Observe a full two/eight-hour session and an uninterrupted 30-day deployment.', 'NOT TESTED: expiry used dedicated server-side test fixtures; availability evidence is a restart and one measured post-idle reconnect, not a 30-day guarantee.'),
    ]:
        scenarios.append({'id':ident,'title':title,'category':category,'scope':'NOT TESTED',
                          'expected':expected,'actual':actual,'status':'NOT TESTED','check_ids':[]})

    # These fields are explicit synthetic examples from the actual Stage 5 run.
    cases = [
        {'id':100011,'number':'SSP26495722','name':'Kamala Devi (Synthetic Test)','age':70,'village':'Synthetic Sonari Village','block':'Sonari','status':'APPROVED','mode':'Real Codex + human operator','voice':'Short English instructions and explicit confirmations typed by the operator; not a field interview.','goal':'Submit, review and follow up through separate citizen and officer assistants.','database_expectation':'One case, one SUBMIT audit and one confirmed APPROVED audit.','actual':'Verified through both MCP resources and read-only Supabase assertions.'},
        {'id':100012,'number':'SSP26545674','name':'Stage Five Rejection Synthetic Applicant','age':76,'village':'Synthetic Test Village','block':'Rajapara','status':'REJECTED','mode':'Scripted public SDK','voice':'Deterministic English tool inputs; no AI conversation claimed.','goal':'Reject fictional proof with a recorded reason.','database_expectation':'REJECTED, exactly one decision audit with authenticated actor and exact reason.','actual':'Public MCP and SQL assertions passed.'},
        {'id':100013,'number':'SSP26669481','name':'Stage Five Withdrawal Synthetic Applicant','age':76,'village':'Synthetic Test Village','block':'Rajapara','status':'WITHDRAWN','mode':'Scripted public SDK','voice':'Deterministic English tool inputs; no AI conversation claimed.','goal':'Withdraw a pending case only after confirmation.','database_expectation':'WITHDRAWN and one owner-attributed withdrawal audit.','actual':'Public MCP and SQL assertions passed.'},
        {'id':100014,'number':'SSP26635026','name':'Stage Five Competing Decisions Synthetic Applicant','age':76,'village':'Synthetic Test Village','block':'Rajapara','status':'REJECTED','mode':'Scripted public SDK','voice':'Two independent officer clients, not two invented chat transcripts.','goal':'Race opposing confirmations on one pending case.','database_expectation':'One winning terminal decision and exactly one corresponding audit.','actual':'REJECTED won; exactly one decision audit verified.'},
    ]
    private_snapshot = json.loads((ARCHIVE / 'synthetic-case-assertions.json').read_text())
    verified = {r['id']: r for r in private_snapshot['cases']}
    for case in cases:
        actual = verified[case['id']]
        assert (case['number'], case['status']) == (actual['application_no'], actual['status'])
        assert actual['audit_count'] == 2
    corroboration = []
    for filename in ['stage5-real-citizen-results.jsonl', 'stage5-real-officer-results.jsonl']:
        raw = (ARCHIVE / filename).read_bytes()
        for line in raw.decode('utf-8-sig').splitlines():
            r = json.loads(line)
            assert r['passed'] is True
            corroboration.append({'name':r['check'],'status':'PASS','source':filename})
        sources.append({'id':'corroboration-' + str(len(sources)), 'name':filename,
                        'scope':'CODEX DATABASE CHECK', 'sha256':hashlib.sha256(raw).hexdigest(), 'count':0})
    payload = {'schema_version':1,'recorded_on':'2026-10-30','timestamp_note':'Date-level snapshot. Per-check timestamps were not recorded; none are invented.',
        'deployment_url':'https://sewasetu-assistant-wgcq.onrender.com',
        'baseline':{'stage':5,'passed':376,'failed':0,'local':275,'live':101,
                    'count_note':'87 unittest cases plus scenario assertions. The manual Codex conversation and its eight database corroboration checks are not added again.'},
        'sources':sources,'checks':checks,'scenarios':scenarios,'cases':cases,'corroboration':corroboration,
        'conversation':[
            {'kind':'Operator — verbatim excerpt','text':'Uploaded the PDF, please check the updated preview.'},
            {'kind':'Tool result — summary','text':'prepare_application returned revision 2, age proof present, ready to submit and no errors.'},
            {'kind':'Operator — verbatim excerpt','text':'I accept the declaration for this test application. Submit revision 2.'},
            {'kind':'Tool result — summary','text':'submit_application returned SSP26495722, PENDING. Owner-filtered follow-up and database assertions agreed.'},
            {'kind':'Operator — verbatim excerpt','text':'approve it , with a reason that sounds good'},
            {'kind':'Decision preview — summary','text':'The assistant proposed APPROVED with a reason explicitly limited to a synthetic evaluation, not genuine eligibility or payment. The MCP required confirmation.'},
            {'kind':'Operator — verbatim excerpt','text':'Confirm this approval and reason.'},
            {'kind':'Tool result — summary','text':'The officer MCP recorded APPROVED using the authenticated actor; citizen follow-up showed the same status and reason. Exactly one decision audit was verified.'},
        ],
        'conversation_note':'Selected operator excerpts from the actual Codex session, paired with labeled tool summaries. This is not a complete transcript or a conversation generated for the SDK fixtures. Login, OTPs, credentials, private links and tokens are omitted.',
        'learnings':[
            {'title':'Repeats must audit only this run’s changes','text':'Two scheduler regressions initially produced duplicate audits. UPDATE RETURNING now drives audit insertion in the same transaction; repeat and concurrent runs produce one audit.'},
            {'title':'Test isolation needs its own guard','text':'A test cleanup mistake reset local synthetic fixtures. Owned-mock cleanup and a current-schema guard fixed it; the local seed was restored. Hosted data was unaffected.'},
            {'title':'A free host needs patient clients','text':'A measured first post-idle reconnect took 25.844 seconds. Allow 60–120 seconds for client startup and retries; this is not an uptime guarantee.'},
        ]}
    validate(payload)
    return payload


def validate(data):
    text = json.dumps(data)
    for pattern in [r'-----BEGIN .*PRIVATE KEY',r'eyJ[\w-]{15,}\.[\w-]{20,}\.[\w-]{20,}',
                    r'gh[pousr]_[A-Za-z0-9]{30,}',r'sb_secret_[\w-]{20,}',
                    r'https?://[^\s"]+/(?:citizen|officer)/(?:upload|proof|ack|finish)/[\w-]+',
                    r'(?:postgresql|postgres)://',r'"(?:mobile|bank_account|access_token|refresh_token|password|doc_path)"\s*:']:
        assert not re.search(pattern,text), 'Unsafe public evidence'
    assert all(c['status'] in ('PASS','FAIL') for c in data['checks'])
    ids = {c['id'] for c in data['checks']}
    assert all(set(s['check_ids']) <= ids for s in data['scenarios'])


if __name__ == '__main__':
    payload = build()
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_bytes((json.dumps(payload,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print('Compiled public evidence: 376 recorded checks; no raw logs, credentials or private records.')
