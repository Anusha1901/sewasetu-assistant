"""Generate private VM configuration; does not provision or publish anything."""
import argparse
import configparser
import json
import os
from pathlib import Path
import re
import secrets
import subprocess


def generate(root, domain, email, out_dir, bind='0.0.0.0', http_port=80, https_port=443):
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', domain) or '..' in domain:
        raise ValueError('Use a lowercase bare DNS hostname, without scheme, path or port.')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise ValueError('Supply your real certificate contact email.')
    if bind not in ('0.0.0.0', '127.0.0.1') or not all(1 <= p <= 65535 for p in (http_port, https_port)):
        raise ValueError('Invalid bind address or port.')
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ValueError('Output directory is nonempty. Refusing to overwrite existing secrets.')
    admin_password, sms_password = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    image = 'caddy:2-alpine'
    # Password goes over stdin, never a command argument, log or repository file.
    hashed = subprocess.run(['docker', 'run', '--rm', '-i', image, 'caddy', 'hash-password'],
                            input=sms_password+'\n', text=True, capture_output=True, check=True)
    match = re.search(r'\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}', hashed.stdout)
    if not match:
        raise RuntimeError('Caddy did not return a bcrypt hash.')
    cfg = configparser.ConfigParser()
    cfg.read(root / 'app/config/app.ini')
    pension = dict(cfg['pension'])
    db_password = secrets.token_urlsafe(32)
    secret = secrets.token_hex(32)
    cfg['database'].update(host='db', port='5432', name='sewasetu', user='sewasetu', password=db_password)
    cfg['app']['secret_key'] = secret
    assert dict(cfg['pension']) == pension  # Never change the scheme window/rules.
    out_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(out_dir, 0o700)
    suffix = '' if https_port == 443 else ':' + str(https_port)
    env = dict(PUBLIC_DOMAIN=domain, PUBLIC_BASE_URL='https://'+domain+suffix, ACME_EMAIL=email,
               ADMIN_USERNAME='assessor', ADMIN_PASSWORD=admin_password, SECRET_KEY=secret,
               EVAL_SMS_USERNAME='assessor_sms', EVAL_SMS_PASSWORD_HASH=match.group(),
               CITIZEN_MCP_BLOCKS='Sonari,Rajapara', CITIZEN_MCP_ALLOWED_ORIGINS='',
               OFFICER_MCP_ALLOWED_ORIGINS='', EDGE_BIND_IP=bind, HTTP_PORT=str(http_port),
               HTTPS_PORT=str(https_port), MCP_WORKERS='2', CADDY_IMAGE=image,
               SECRETS_DIR=out_dir.resolve().as_posix())
    # Single quotes keep bcrypt dollar signs literal during Compose interpolation.
    (out_dir/'.env').write_text(''.join(k+"='"+v+"'\n" for k,v in env.items()))
    with (out_dir/'app.ini').open('w') as f:
        cfg.write(f)
    (out_dir/'db_password').write_text(db_password)
    (out_dir/'credentials.json').write_text(json.dumps({'officer_username': 'assessor',
        'officer_password': admin_password, 'sms_username': 'assessor_sms', 'sms_password': sms_password}, indent=2)+'\n')
    for file in out_dir.iterdir():
        os.chmod(file, 0o600)
    print('Private configuration created in '+str(out_dir)+'. No credentials printed.')
    return env


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', required=True)
    parser.add_argument('--email', required=True)
    parser.add_argument('--out-dir', type=Path, default=Path(__file__).parent/'secrets')
    parser.add_argument('--bind', default='0.0.0.0', choices=['0.0.0.0', '127.0.0.1'])
    parser.add_argument('--http-port', type=int, default=80)
    parser.add_argument('--https-port', type=int, default=443)
    args = parser.parse_args()
    generate(Path(__file__).resolve().parents[1], args.domain, args.email, args.out_dir,
             args.bind, args.http_port, args.https_port)
