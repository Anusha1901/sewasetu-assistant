"""Archive only assertion names/outcomes, never raw MCP responses or credentials."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dev/evidence/stage6'
OUT.mkdir(exist_ok=True)
FILES = {
    'main': 76, 'citizen': 45, 'officer': 39, 'citizen-oauth': 3,
    'persistence': 15, 'hosted-adapter': 10, 'local-browser': 38,
    'reproducibility': 1, 'public-dashboard': 20, 'public-browser': 38,
    'public-mcp-probe': 8, 'real-client': 2,
}
sources = []
for name, expected in FILES.items():
    source = ROOT / ('dev/stage6-' + name + '-results.jsonl')
    raw = source.read_bytes()
    records = [json.loads(line) for line in raw.decode('utf-8-sig').splitlines() if line.startswith('{')]
    checks = [{'check': r['check'], 'passed': r['passed']} for r in records if 'check' in r]
    assert len(checks) == expected and all(r['passed'] is True for r in checks), name
    sources.append({'source': source.name, 'sha256': hashlib.sha256(raw).hexdigest(), 'checks': checks})
raw = (ROOT / 'dev/stage6-unit-integration.txt').read_bytes()
unit = raw.decode('utf-8-sig')
cases = [match.group(1) for line in unit.splitlines()
         if (match := re.fullmatch(r'(test_\S+ \(.+\)) \.\.\. ok', line))]
assert len(cases) == 107 and re.search(r'^OK\s*$', unit, re.M) and 'skipped' not in unit
sources.append({'source': 'stage6-unit-integration.txt', 'sha256': hashlib.sha256(raw).hexdigest(),
                'checks': [{'check': case, 'passed': True} for case in cases]})
payload = {'date': '2026-10-30', 'total_passed': sum(len(s['checks']) for s in sources),
           'failed': 0, 'note': 'Stage 6 rerun assertions; not added to the historical Stage 5 public snapshot.',
           'sources': sources}
text = json.dumps(payload, ensure_ascii=False, indent=2) + '\n'
for pattern in [r'eyJ[a-zA-Z0-9_-]{15,}\.', r'(?:postgres|postgresql)://',
                r'/(?:officer|citizen)/finish/', r'\b[6-9]\d{9}\b']:
    assert not re.search(pattern, text), 'Unsafe archive content'
(OUT / 'results.json').write_bytes(text.encode('utf-8'))
print(json.dumps({'passed': payload['total_passed'], 'failed': 0}))
