"""Official SDK auto-discovery/DCR/PKCE flow with a simulated human browser callback."""
import asyncio
import json
import re
import secrets
import time
from urllib.parse import parse_qs, urlparse
import requests
from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientMetadata
from citizen_auth import RESOURCE

BASE = 'http://localhost:8000'


class Storage:
    tokens = None
    client = None

    async def get_tokens(self):
        return self.tokens

    async def set_tokens(self, value):
        self.tokens = value

    async def get_client_info(self):
        return self.client

    async def set_client_info(self, value):
        self.client = value


async def main():
    browser = requests.Session()
    number = '97' + ''.join(str(secrets.randbelow(10)) for _ in range(8))
    callback = None
    async def redirect(url):
        nonlocal callback
        page = browser.get(url, timeout=20)
        login = page.url
        browser.post(login, data={'mobile': number}, timeout=20)
        for _ in range(25):
            msgs = requests.get(BASE + '/__gateway/api/messages', params={'to': number}, timeout=20).json()['messages']
            if msgs and msgs[-1]['delivered']:
                code = re.search(r'\b\d{6}\b', msgs[-1]['text']).group()
                break
            await asyncio.sleep(.3)
        page = browser.post(login, data={'otp': code}, timeout=20)
        response = browser.post(page.url, data={'decision': 'allow'}, allow_redirects=False, timeout=20)
        params = parse_qs(urlparse(response.headers['Location']).query)
        callback = params['code'][0], params['state'][0]

    async def receive_callback():
        return callback

    storage = Storage()
    auth = OAuthClientProvider(server_url=RESOURCE,
        client_metadata=OAuthClientMetadata(client_name='Stage 3 native SDK OAuth',
            redirect_uris=['http://localhost:9878/callback'], grant_types=['authorization_code', 'refresh_token'],
            response_types=['code'], token_endpoint_auth_method='none', scope='citizen'),
        storage=storage, redirect_handler=redirect, callback_handler=receive_callback)
    async with streamablehttp_client(RESOURCE, auth=auth) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool('get_scheme_info', {})
            assert len(tools.tools) == 5 and not result.isError
    assert storage.tokens and storage.client
    print(json.dumps({'check': 'official SDK automatic resource/AS discovery, registration, PKCE and tool call', 'passed': True}), flush=True)
    # Verify rotation keeps the citizen session live, then revocation immediately blocks access.
    refreshed = browser.post(BASE + '/oauth/token', data={'grant_type': 'refresh_token',
        'client_id': storage.client.client_id, 'refresh_token': storage.tokens.refresh_token, 'resource': RESOURCE}, timeout=20)
    assert refreshed.status_code == 200
    newer = refreshed.json()
    async with streamablehttp_client(RESOURCE, headers={'Authorization': 'Bearer ' + newer['access_token']}) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            assert not (await session.call_tool('get_my_applications', {})).isError
    print(json.dumps({'check': 'rotated citizen token retains active MCP session', 'passed': True}), flush=True)
    browser.post(BASE + '/oauth/revoke', data={'token': newer['refresh_token']}, timeout=20)
    response = requests.post(RESOURCE, headers={'Authorization': 'Bearer ' + newer['access_token'],
        'Accept': 'application/json, text/event-stream'}, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, timeout=20)
    assert response.status_code == 401
    print(json.dumps({'check': 'OAuth revocation immediately denies citizen access token', 'passed': True}), flush=True)


asyncio.run(main())
