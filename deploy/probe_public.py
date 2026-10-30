"""External, read-only TLS/discovery probe. Does not claim to test an AI conversation."""
import argparse
import json
from urllib.parse import urlparse
import requests


def probe(base, ca=True):
    if urlparse(base).scheme != 'https':
        raise ValueError('A public HTTPS URL is required.')
    checks = []
    def check(name, passed):
        checks.append({'check': name, 'passed': bool(passed)})
        print(json.dumps(checks[-1]), flush=True)
        assert passed, name
    session = requests.Session()
    session.verify = ca
    check('portal TLS and homepage', session.get(base+'/', timeout=30).status_code == 200)
    check('database readiness', session.get(base+'/healthz', timeout=30).json() == {'status':'ok'})
    metadata = session.get(base+'/.well-known/oauth-authorization-server', timeout=30).json()
    check('canonical OAuth issuer and redirect discovery', metadata['issuer'] == base and metadata['authorization_endpoint'] == base+'/oauth/authorize' and metadata['code_challenge_methods_supported'] == ['S256'])
    for role in ('citizen','officer'):
        url = base+'/mcp/'+role
        response = session.post(url, headers={'Accept':'application/json, text/event-stream'},
                                json={'jsonrpc':'2.0','id':1,'method':'tools/list'}, timeout=30)
        check(role+' denies missing credentials and advertises discovery', response.status_code == 401 and 'resource_metadata=' in response.headers.get('WWW-Authenticate',''))
        resource = session.get(base+'/.well-known/oauth-protected-resource/mcp/'+role, timeout=30).json()
        check(role+' canonical resource scope issuer', resource['resource'] == url and resource['scopes_supported'] == [role] and resource['authorization_servers'] == [base])
    check('SMS inbox is not public', session.get(base+'/__gateway/api/messages', timeout=30).status_code in (401,403))
    return checks


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--ca-file', help='Only for local rehearsal using the exported local CA; omit for public certificates.')
    args=parser.parse_args()
    probe(args.base_url.rstrip('/'), args.ca_file or True)
