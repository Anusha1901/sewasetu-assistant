"""Collect hosting credentials privately on this computer, never in chat or Git."""
from getpass import getpass
import json
import os
from pathlib import Path
import secrets
from urllib.parse import quote, urlparse


def main():
    folder = Path(__file__).resolve().parent / 'secrets'
    target = folder / 'render.env'
    if target.exists():
        raise SystemExit('Private render.env already exists; refusing to overwrite it.')
    print('Copy the Supabase Connect → Session pooler URI (port 5432). Input is hidden.')
    uri = getpass('Session pooler connection URI: ').strip()
    if '[YOUR-PASSWORD]' in uri:
        password = getpass('Supabase database password: ')
        uri = uri.replace('[YOUR-PASSWORD]', quote(password, safe=''))
    parsed = urlparse(uri)
    if (parsed.scheme not in ('postgres', 'postgresql') or not parsed.password
            or parsed.port != 5432 or not (parsed.hostname or '').endswith('.pooler.supabase.com')
            or parsed.username != 'postgres.ipbcvfrdeeqvbhysscdi'):
        raise SystemExit('Use this project’s Session pooler URI on port 5432, with a password.')
    key = getpass('Supabase legacy service_role key (backend only): ').strip()
    if not key.startswith('eyJ') or key.count('.') != 2:
        raise SystemExit('Use the legacy service_role JWT from Supabase API Keys, not the anon key.')
    try:
        import base64
        body = key.split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
        if claims.get('role') != 'service_role' or claims.get('ref') != 'ipbcvfrdeeqvbhysscdi':
            raise ValueError()
    except Exception:
        raise SystemExit('That is not this project’s service_role key.') from None
    password = secrets.token_urlsafe(32)
    env = dict(DATABASE_URL=uri, DATABASE_SCHEMA='sewasetu',
               SUPABASE_URL='https://ipbcvfrdeeqvbhysscdi.supabase.co',
               SUPABASE_SERVICE_ROLE_KEY=key, SUPABASE_STORAGE_BUCKET='age-proofs',
               DOCUMENT_STORAGE='supabase', SECRET_KEY=secrets.token_hex(32),
               ADMIN_USERNAME='assessor', ADMIN_PASSWORD=password,
               ENABLE_LOCAL_SMS_CONSOLE='0', CITIZEN_MCP_BLOCKS='Sonari,Rajapara',
               PUBLIC_BASE_URL='https://replace-me.onrender.com')
    if any('\n' in value or '\r' in value for value in env.values()):
        raise SystemExit('Multiline credentials are not supported.')
    folder.mkdir(mode=0o700, exist_ok=True)
    os.chmod(folder, 0o700)
    target.write_text(''.join(k + '=' + v + '\n' for k, v in env.items()), encoding='utf-8')
    os.chmod(target, 0o600)
    creds = folder / 'render-officer.json'
    creds.write_text(json.dumps({'username': 'assessor', 'password': password}, indent=2), encoding='utf-8')
    os.chmod(creds, 0o600)
    print('Saved private render.env and render-officer.json in deploy/secrets. No secrets printed.')
    print('Do not upload these files to GitHub. Tell the assistant only that setup completed.')


if __name__ == '__main__':
    main()
