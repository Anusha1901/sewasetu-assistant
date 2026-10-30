"""Explicit first import into an empty private schema; never run automatically."""
import io
from pathlib import Path

import services


def initialize():
    root = Path(services.BASE_DIR)
    with services.transaction() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(870706)')
        cur.execute('CREATE SCHEMA IF NOT EXISTS sewasetu')
        cur.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')")
        roles = ['PUBLIC'] + [r[0] for r in cur.fetchall()]
        # These role names are fixed by the above whitelist, never supplied by a caller.
        grantees = ','.join(roles)
        cur.execute('REVOKE ALL ON SCHEMA sewasetu FROM ' + grantees)
        cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='sewasetu'")
        if cur.fetchone()[0]:
            raise RuntimeError('Refusing to import into a nonempty schema')
        cur.execute((root / 'schema.sql').read_text())
        seed = root / 'hosting/seed.sql'
        # COPY blocks are streamed through the PostgreSQL protocol, not SQL interpolation.
        with seed.open(encoding='utf-8') as source:
            sql = []
            for line in source:
                if line.startswith('COPY '):
                    if sql:
                        statement = ''.join(sql)
                        if any(line.strip() and not line.lstrip().startswith('--') for line in statement.splitlines()):
                            cur.execute(statement)
                        sql = []
                    data = io.StringIO()
                    for row in source:
                        if row.rstrip('\r\n') == '\\.':
                            break
                        data.write(row)
                    data.seek(0)
                    cur.copy_expert(line.strip(), data)
                else:
                    sql.append(line)
            if sql:
                statement = ''.join(sql)
                if any(line.strip() and not line.lstrip().startswith('--') for line in statement.splitlines()):
                    cur.execute(statement)
        for path in sorted((root / 'migrations').glob('*.sql')):
            cur.execute('\n'.join(line for line in path.read_text().splitlines()
                                  if line.strip().upper() not in ('BEGIN;', 'COMMIT;')))
        cur.execute('SELECT count(*) FROM applications')
        if cur.fetchone()[0] != 100000:
            raise RuntimeError('Seed count did not match 100000')
        # Defense in depth if an administrator ever exposes this schema through PostgREST.
        cur.execute('REVOKE ALL ON ALL TABLES IN SCHEMA sewasetu FROM ' + grantees)
        cur.execute('REVOKE ALL ON ALL SEQUENCES IN SCHEMA sewasetu FROM ' + grantees)
    print('Imported original seed into private schema: 100000 applications. No credentials printed.')
