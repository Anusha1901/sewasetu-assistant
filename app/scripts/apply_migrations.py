"""Idempotent deployment-time migrations using the existing portal configuration."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import services

with services.transaction() as cur:
    cur.execute('SELECT pg_advisory_xact_lock(870705)')
    for path in sorted((Path(services.BASE_DIR) / 'migrations').glob('*.sql')):
        sql = path.read_text()
        # Each supplied migration is an explicit transaction; keep all upgrades atomic
        # and retain the advisory lock by using the surrounding shared transaction.
        sql = '\n'.join(line for line in sql.splitlines() if line.strip().upper() not in ('BEGIN;', 'COMMIT;'))
        cur.execute(sql)
        print('Applied ' + path.name, flush=True)
