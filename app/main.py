"""
FastAPI application entry point.
No business logic here - just app wiring, middleware, and router registration.
Run with: uvicorn app.main:app --host 127.0.0.1 --port 8000
"""
import logging
import secrets
import hmac
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import APP_ENV, APP_NAME, BASE_DIR, COOKIE_SECURE
from app.database import init_db
from app.routers import admin, auth, files, media, pages, shared, system

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "logs" / "app.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("home_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting up", APP_NAME)
    yield


app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, lifespan=lifespan)

CSRF_COOKIE_NAME = "hs_csrf"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    if (
        APP_ENV != "test"
        and request.url.path.startswith("/api/")
        and request.method in UNSAFE_METHODS
    ):
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        header_token = request.headers.get("X-CSRF-Token")

        if (
            not cookie_token
            or not header_token
            or not hmac.compare_digest(cookie_token, header_token)
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF validation failed"},
            )

    response = await call_next(request)

    if not request.cookies.get(CSRF_COOKIE_NAME):
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=secrets.token_urlsafe(32),
            httponly=False,
            secure=COOKIE_SECURE,
            samesite="lax",
            max_age=60 * 60 * 24 * 30,
            path="/",
        )

    return response


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app/static")), name="static")

app.include_router(auth.router)
app.include_router(files.router)
app.include_router(shared.router)
app.include_router(media.router)
app.include_router(admin.router)
app.include_router(system.router)
app.include_router(pages.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # API requests get JSON; page loads get a friendly error page.
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return HTMLResponse(
        status_code=exc.status_code,
        content=f"<h1>{exc.status_code}</h1><p>{exc.detail}</p><a href='/'>Go home</a>",
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    ref_id = uuid.uuid4().hex[:8].upper()
    logger.exception("Unhandled error [ref=%s] on %s", ref_id, request.url.path)
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=500, content={"detail": f"Something went wrong. Reference ID: {ref_id}"})
    return HTMLResponse(
        status_code=500,
        content=f"<h1>Something went wrong</h1><p>Reference ID: {ref_id}</p><a href='/'>Go home</a>",
    )
