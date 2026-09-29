"""API docs (Swagger UI, ReDoc, openapi.json), optionally behind a single
shared password — no username — so docs can be shared with partner developers
without making the schema public.

- API_DOCS_ENABLED=false -> all three paths 404.
- API_DOCS_PASSWORD unset -> docs are open.
- API_DOCS_PASSWORD set   -> a password page; success sets a signed cookie
  valid for 12 h. Changing the password invalidates every existing cookie.
Wrong attempts are rate-limited per client IP (via Redis) against brute force.
"""
import hashlib
import hmac
import html

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.core.config import settings
from app.core.redis import redis_client

router = APIRouter(include_in_schema=False)

_COOKIE = "docs_session"
_COOKIE_MAX_AGE_S = 12 * 3600
_MAX_FAILED_ATTEMPTS = 10
_FAILED_WINDOW_S = 15 * 60


def _expected_cookie() -> str:
    # Derived from both the server secret and the password: unforgeable, and
    # rotating the password logs everyone out.
    return hmac.new(
        settings.jwt_secret.encode(), f"docs:{settings.api_docs_password}".encode(), hashlib.sha256
    ).hexdigest()


def _authorized(request: Request) -> bool:
    if not settings.api_docs_password:
        return True
    return hmac.compare_digest(request.cookies.get(_COOKIE, ""), _expected_cookie())


def _gate(request: Request, next_path: str):
    """None if the request may see the docs, otherwise the response to send."""
    if not settings.api_docs_enabled:
        raise HTTPException(404)
    if _authorized(request):
        return None
    return RedirectResponse(f"/docs/login?next={next_path}", status_code=303)


def _client_ip(request: Request) -> str:
    return request.headers.get(settings.client_ip_header) or (request.client.host if request.client else "?")


_LOGIN_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>API docs</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ margin:0; min-height:100vh; display:grid; place-items:center; font:16px system-ui,sans-serif;
         background:Canvas; color:CanvasText; }}
  form {{ width:min(320px, calc(100vw - 32px)); display:grid; gap:12px; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  input, button {{ font:inherit; padding:10px 12px; border-radius:8px; border:1px solid #8886; }}
  button {{ cursor:pointer; background:#2563eb; color:#fff; border:0; }}
  .err {{ color:#dc2626; font-size:14px; margin:0; }}
</style></head>
<body><form method="post" action="/docs/login">
  <h1>API documentation</h1>
  <input type="password" name="password" placeholder="Password" autofocus required autocomplete="current-password">
  <input type="hidden" name="next" value="{next}">
  {error}
  <button type="submit">View docs</button>
</form></body></html>"""


def _safe_next(next_path: str) -> str:
    # Only our own docs paths — never an open redirect to another site.
    return next_path if next_path in ("/docs", "/redoc") else "/docs"


@router.get("/docs/login")
async def login_page(next: str = "/docs"):
    if not settings.api_docs_enabled:
        raise HTTPException(404)
    return HTMLResponse(_LOGIN_PAGE.format(next=html.escape(_safe_next(next)), error=""))


@router.post("/docs/login")
async def login(request: Request, password: str = Form(...), next: str = Form("/docs")):
    if not settings.api_docs_enabled:
        raise HTTPException(404)
    target = _safe_next(next)
    key = f"docs_login_failed:{_client_ip(request)}"
    failed = int(await redis_client.get(key) or 0)
    if failed >= _MAX_FAILED_ATTEMPTS:
        return HTMLResponse(
            _LOGIN_PAGE.format(next=html.escape(target),
                               error='<p class="err">Too many attempts. Try again in 15 minutes.</p>'),
            status_code=429,
        )

    if not settings.api_docs_password or not hmac.compare_digest(
        password.encode(), settings.api_docs_password.encode()
    ):
        async with redis_client.pipeline(transaction=True) as pipe:
            await pipe.incr(key).expire(key, _FAILED_WINDOW_S).execute()
        return HTMLResponse(
            _LOGIN_PAGE.format(next=html.escape(target), error='<p class="err">Wrong password.</p>'),
            status_code=401,
        )

    await redis_client.delete(key)
    resp = RedirectResponse(target, status_code=303)
    resp.set_cookie(
        _COOKIE, _expected_cookie(), max_age=_COOKIE_MAX_AGE_S,
        httponly=True, secure=request.url.scheme == "https" or "cf-connecting-ip" in request.headers,
        samesite="lax",
    )
    return resp


@router.get("/docs")
async def swagger_ui(request: Request):
    if (denied := _gate(request, "/docs")) is not None:
        return denied
    return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{request.app.title} — docs")


@router.get("/redoc")
async def redoc(request: Request):
    if (denied := _gate(request, "/redoc")) is not None:
        return denied
    return get_redoc_html(openapi_url="/openapi.json", title=f"{request.app.title} — docs")


@router.get("/openapi.json")
async def openapi_schema(request: Request):
    if not settings.api_docs_enabled:
        raise HTTPException(404)
    if not _authorized(request):
        raise HTTPException(401, "Docs password required")
    return JSONResponse(request.app.openapi())
