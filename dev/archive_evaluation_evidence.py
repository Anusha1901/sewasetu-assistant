"""Archive only reviewed, synthetic test assertions in the private submission repo."""
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
archive = root / 'dev/evidence/stage5'
summary = json.loads((root / 'dev/stage5-final-summary.json').read_text())
names = [('stage5-final-unit-integration.txt' if n == 'unit_and_integration' else n) for n in summary['counts']]
names += ['stage5-real-citizen-results.jsonl', 'stage5-real-officer-results.jsonl', 'stage5-final-summary.json']
archive.mkdir(parents=True, exist_ok=True)
for name in names:
    raw = (root / 'dev' / name).read_bytes()
    text = raw.decode('utf-8-sig')
    for pattern in [r'eyJ[\w-]{15,}\.[\w-]{20,}\.[\w-]{20,}',r'-----BEGIN .*PRIVATE KEY',
                    r'(?:postgresql|postgres)://',r'\b\d{10}\b',
                    r'https?://[^\s"]+/(?:citizen|officer)/(?:upload|proof|ack|finish)/[\w-]+']:
        assert not re.search(pattern, text), 'Private material in source artifact: ' + name
    (archive / name).write_bytes(raw)
private = json.loads((root / 'deploy/secrets/stage5-evidence/before-restart.json').read_text())
safe = {'recorded_on':'2026-10-30','derivation':'Allowlisted fields from the verified Stage 5 synthetic-case persistence snapshot.',
        'cases': [{k:r[k] for k in ['id','application_no','status','audit_count']} for r in private['cases']]}
assert {r['id'] for r in safe['cases']} == {100011,100012,100013,100014}
(archive / 'synthetic-case-assertions.json').write_text(json.dumps(safe,indent=2)+'\n',encoding='utf-8')
print('Archived reviewed test assertions and synthetic-only case outcomes; no credentials, private links or documents.')
