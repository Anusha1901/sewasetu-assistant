"""Private age-proof storage. Authorization belongs to the existing caller routes."""
import os
import re
import secrets
from pathlib import Path

import requests

MAX_FILE = 5 * 1024 * 1024
MIMES = {'.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}


class StorageUnavailable(RuntimeError):
    pass


def remote():
    backend = os.environ.get('DOCUMENT_STORAGE', 'local')
    if backend not in ('local', 'supabase'):
        raise StorageUnavailable('Unknown document storage backend')
    return backend == 'supabase'


def _settings():
    base = os.environ.get('SUPABASE_URL', '').rstrip('/')
    bucket = os.environ.get('SUPABASE_STORAGE_BUCKET', 'age-proofs')
    key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
    if (not re.fullmatch(r'https://[a-z0-9]+\.supabase\.co', base)
            or not re.fullmatch(r'[a-z0-9-]{1,63}', bucket) or not key):
        raise StorageUnavailable('Private document storage is not configured')
    return base, bucket, {'apikey': key, 'Authorization': 'Bearer ' + key}


def _object(reference):
    _, bucket, _ = _settings()
    match = re.fullmatch(r'supabase://' + re.escape(bucket) + r'/(proofs/[a-f0-9]{48}\.(?:pdf|jpg|jpeg|png))', str(reference))
    if not match:
        raise StorageUnavailable('Invalid private document reference')
    return match[1]


def _request(method, path, **kwargs):
    base, _, headers = _settings()
    headers.update(kwargs.pop('headers', {}))
    try:
        response = requests.request(method, base + '/storage/v1/' + path,
                                    headers=headers, timeout=(5, 25), allow_redirects=False, **kwargs)
    except requests.RequestException:
        raise StorageUnavailable('Private document storage is temporarily unavailable') from None
    if not 200 <= response.status_code < 300:
        response.close()
        raise StorageUnavailable('Private document storage could not complete the request')
    return response


def save(content, suffix, *, local_path=None):
    if not content or len(content) > MAX_FILE or suffix.lower() not in MIMES:
        raise ValueError('Invalid document size or extension')
    if remote():
        _, bucket, _ = _settings()
        name = 'proofs/' + secrets.token_hex(24) + suffix.lower()
        response = _request('POST', 'object/' + bucket + '/' + name, data=content,
                            headers={'Content-Type': MIMES[suffix.lower()], 'x-upsert': 'false'})
        response.close()
        return 'supabase://' + bucket + '/' + name
    path = Path(local_path)
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    with path.open('xb') as out:
        out.write(content)
    os.chmod(path, 0o600)
    return str(path)


def read(reference):
    if str(reference).startswith('supabase://'):
        name = _object(reference)
        _, bucket, _ = _settings()
        response = _request('GET', 'object/authenticated/' + bucket + '/' + name, stream=True)
        try:
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > MAX_FILE:
                    raise StorageUnavailable('Stored document exceeds the allowed size')
            if not content:
                raise StorageUnavailable('Stored document is empty')
            return bytes(content)
        except requests.RequestException:
            raise StorageUnavailable('Private document download failed') from None
        finally:
            response.close()
    return Path(reference).read_bytes()


def exists(reference):
    if str(reference).startswith('supabase://'):
        # Do not silently turn a storage outage into a missing-document submission.
        read(reference)
        return True
    return bool(reference) and Path(reference).is_file()


def verify_private_bucket():
    _, bucket, _ = _settings()
    response = _request('GET', 'bucket/' + bucket)
    try:
        details = response.json()
        if details.get('id') != bucket or details.get('public') is not False:
            raise StorageUnavailable('Age-proof bucket must be private')
    finally:
        response.close()


def delete(reference):
    if str(reference).startswith('supabase://'):
        name = _object(reference)
        _, bucket, _ = _settings()
        response = _request('DELETE', 'object/' + bucket, json={'prefixes': [name]})
        response.close()
    else:
        Path(reference).unlink(missing_ok=True)
