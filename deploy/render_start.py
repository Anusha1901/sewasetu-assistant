"""Single free Render service, or an ephemeral scheduler container; no portal logic."""
import configparser
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def configure():
    # This writes only the disposable container's configuration. Source INI is untouched.
    from psycopg2.extensions import parse_dsn
    from documents import _settings, remote
    url = os.environ.get('DATABASE_URL', '')
    if not url or os.environ.get('DATABASE_SCHEMA', 'sewasetu') != 'sewasetu':
        raise RuntimeError('Hosted DATABASE_URL and the private sewasetu schema are required')
    fields = parse_dsn(url)
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(ROOT / 'config/app.ini')
    for ini, dsn in [('host', 'host'), ('port', 'port'), ('name', 'dbname'), ('user', 'user'), ('password', 'password')]:
        cfg['database'][ini] = fields.get(dsn, '5432' if ini == 'port' else '').replace('%', '%%')
    cfg['app']['sms_gateway_url'] = 'http://127.0.0.1:8025'
    cfg['app']['secret_key'] = os.environ.get('SECRET_KEY', '')
    with (ROOT / 'config/app.ini').open('w') as out:
        cfg.write(out)
    os.chmod(ROOT / 'config/app.ini', 0o600)
    os.environ.update(SMS_GATEWAY_URL='http://127.0.0.1:8025', PERSISTENT_SMS='1',
                      PGSSLMODE='require', PGOPTIONS='-c search_path=sewasetu -c timezone=Asia/Kolkata')
    if remote():
        _settings()


def run(mode='web'):
    configure()
    if mode == 'initialize':
        import initialize_hosted
        initialize_hosted.initialize()
        return 0
    if mode == 'web':
        import documents
        if not documents.remote():
            raise RuntimeError('Render requires persistent private document storage')
        documents.verify_private_bucket()
    # Explicit migration step is repeatable; never seed automatically on a restart.
    subprocess.run([sys.executable, str(ROOT / 'scripts/apply_migrations.py')], check=True)
    children = []

    def stop(*_):
        for child in children:
            if child.poll() is None:
                child.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        children.append(subprocess.Popen([sys.executable, '-m', 'gunicorn', 'simulator.app:app',
                                         '--bind', '127.0.0.1:8025', '--workers', '1', '--threads', '2'], cwd=ROOT))
        import requests
        for _ in range(50):
            if children[0].poll() is not None:
                raise RuntimeError('Private SMS simulator failed to start')
            try:
                requests.get('http://127.0.0.1:8025/', timeout=2).raise_for_status()
                break
            except requests.RequestException:
                time.sleep(.2)
        else:
            raise RuntimeError('Private SMS simulator did not become ready')
        if mode == 'scheduler':
            # Exact original 15-day selection, decisions, audit and notifications.
            return subprocess.call([sys.executable, str(ROOT / 'scripts/deemed_approval.py')], cwd=ROOT)
        children.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'gateway:app', '--host', '0.0.0.0',
                                         '--port', os.environ.get('PORT', '10000'), '--workers', '1',
                                         '--proxy-headers', '--forwarded-allow-ips', '*', '--no-access-log'], cwd=ROOT))
        while all(child.poll() is None for child in children):
            time.sleep(.5)
        return next((child.returncode or 1 for child in children if child.poll() is not None), 1)
    finally:
        stop()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'web'
    if mode not in ('web', 'scheduler', 'initialize'):
        raise SystemExit('Choose web, scheduler or initialize')
    try:
        raise SystemExit(run(mode))
    except Exception:
        # Connection errors can contain credentials/hosts; never dump exceptions into build logs.
        print('Hosted startup failed. Check private configuration and database initialization.', file=sys.stderr)
        raise SystemExit(1)
