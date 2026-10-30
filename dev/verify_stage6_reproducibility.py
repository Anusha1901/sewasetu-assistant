"""Prove the public snapshot rebuilds from only committed, reviewed artifacts."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

root = Path(__file__).resolve().parents[1]
isolated = root / 'tmp' / ('stage6-reproduce-' + uuid.uuid4().hex)
(isolated / 'dev').mkdir(parents=True)
(isolated / 'app').mkdir()
shutil.copyfile(root / 'dev/build_evaluation_evidence.py', isolated / 'dev/build_evaluation_evidence.py')
shutil.copytree(root / 'dev/evidence', isolated / 'dev/evidence')
subprocess.run([sys.executable, str(isolated / 'dev/build_evaluation_evidence.py')], check=True, stdout=subprocess.DEVNULL)
same = (isolated / 'app/evaluation/evidence.json').read_bytes() == (root / 'app/evaluation/evidence.json').read_bytes()
print(json.dumps({'check':'public snapshot reproduces byte-exactly without credentials or private snapshots','passed':same}))
assert same
