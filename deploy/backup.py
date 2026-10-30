"""Private, coordinated DB/uploads/log backup. Briefly stops app and scheduler.

Keep an encrypted/off-VM copy; local volumes/backups alone do not survive VM loss.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess


def backup(env_file, project, destination):
    root = Path(__file__).resolve().parents[1]
    command = ['docker', 'compose', '--env-file', str(env_file.resolve()), '-p', project,
               '-f', str(root/'deploy/compose.yml')]
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.chmod(destination, 0o700)
    subprocess.run(command+['stop', 'app', 'scheduler'], check=True)
    try:
        jobs = [('database.dump', ['exec','-T','db','pg_dump','-U','sewasetu','-d','sewasetu','-Fc']),
                ('uploads.tar.gz', ['run','--rm','--no-deps','-T','--entrypoint','tar','app','-C','/var/sewasetu/uploads','-czf','-','.']),
                ('logs.tar.gz', ['run','--rm','--no-deps','-T','--entrypoint','tar','app','-C','/var/log/sewasetu','-czf','-','.'])]
        hashes = {}
        for name, arguments in jobs:
            path = destination/name
            with path.open('wb') as out:
                subprocess.run(command+arguments, stdout=out, check=True)
            os.chmod(path, 0o600)
            digest = hashlib.sha256()
            with path.open('rb') as source:
                for chunk in iter(lambda: source.read(1024*1024), b''):
                    digest.update(chunk)
            hashes[name] = digest.hexdigest()
        (destination/'sha256.json').write_text(json.dumps(hashes, indent=2)+'\n')
        os.chmod(destination/'sha256.json', 0o600)
        print('Backup completed at '+str(destination)+'. Contains private data: do not commit or share publicly.')
    finally:
        subprocess.run(command+['up','-d','app','scheduler'], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=Path(__file__).parent/'secrets/.env')
    parser.add_argument('--project', default='sewasetu-eval')
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    path = args.destination or Path(__file__).parent/'backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup(args.env_file, args.project, path)
