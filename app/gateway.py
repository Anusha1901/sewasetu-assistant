"""One listener: official MCP transport plus the existing Flask portal."""
from contextlib import asynccontextmanager
import anyio
from starlette.routing import Mount, Route
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.middleware.wsgi import WSGIMiddleware
from starlette.middleware.cors import CORSMiddleware

import app as portal
from citizen_web import web
from citizen_mcp import mcp, origins
from officer_mcp import mcp as officer_mcp, origins as officer_origins
from officer_auth import RESOURCE as OFFICER_RESOURCE
from officer_web import web as officer_web
from citizen_auth import ISSUER, RESOURCE, validate_public_configuration
import os

validate_public_configuration(ISSUER, os.environ.get('SECRET_KEY', ''),
                              os.environ.get('ENABLE_LOCAL_SMS_CONSOLE'), portal.ADMIN_PASSWORD)
from citizen import verify_configured_blocks
import services

portal.app.register_blueprint(web)
portal.app.register_blueprint(officer_web)
portal.app.config.update(SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_HTTPONLY=True,
                         SESSION_COOKIE_SECURE=portal.os.environ.get('PUBLIC_BASE_URL', '').startswith('https://'))
app = mcp.streamable_http_app()


async def resource_metadata(request):
    # Preserve the issuer's exact canonical spelling (URL models add a root slash).
    return JSONResponse({'resource': RESOURCE, 'authorization_servers': [ISSUER],
                         'scopes_supported': ['citizen'], 'bearer_methods_supported': ['header']})


app.router.routes.insert(0, Route('/.well-known/oauth-protected-resource/mcp/citizen', resource_metadata))
# Keep the SDK's auth middleware and its metadata routes; Flask is only the fallback.
app.router.routes.append(Mount('/', app=WSGIMiddleware(portal.app)))


@asynccontextmanager
async def lifespan(application):
    await anyio.to_thread.run_sync(verify_configured_blocks)
    async with mcp.session_manager.run(), officer_mcp.session_manager.run():
        yield


citizen_app = app
officer_app = officer_mcp.streamable_http_app()


async def officer_metadata(request):
    return JSONResponse({'resource': OFFICER_RESOURCE, 'authorization_servers': [ISSUER],
                         'scopes_supported': ['officer'], 'bearer_methods_supported': ['header']})


officer_app.router.routes.insert(0, Route('/.well-known/oauth-protected-resource/mcp/officer', officer_metadata))


async def health(request):
    def check_database():
        with services.transaction() as cur:
            cur.execute('SELECT 1')
            return cur.fetchone() == (1,)
    try:
        ready = await anyio.to_thread.run_sync(check_database)
    except Exception:
        ready = False
    return JSONResponse({'status': 'ok' if ready else 'unavailable'}, status_code=200 if ready else 503)


# Dispatch without merging auth middleware: each resource keeps its own verifier/context.
app = Starlette(routes=[Route('/healthz', health), Route('/mcp/officer', endpoint=officer_app),
                        Route('/.well-known/oauth-protected-resource/mcp/officer', endpoint=officer_app),
                        Mount('/', app=citizen_app)], lifespan=lifespan)
app = CORSMiddleware(app, allow_origins=list(dict.fromkeys(origins + officer_origins)), allow_methods=['GET', 'POST', 'DELETE', 'OPTIONS'],
                     allow_headers=['Authorization', 'Content-Type', 'MCP-Protocol-Version', 'Mcp-Session-Id', 'Accept'],
                     expose_headers=['WWW-Authenticate', 'Mcp-Session-Id'])
