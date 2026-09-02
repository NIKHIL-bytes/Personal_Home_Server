"""
Server-rendered page shells. Dynamic content within each page is loaded
client-side via the JSON APIs in the other routers (keeps the backend simple
and avoids re-rendering large HTML fragments on every interaction).
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import APP_NAME, BASE_DIR
from app.dependencies import CurrentUser, get_optional_user

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app/templates"))


def _ctx(request: Request, user: CurrentUser, **extra):
    return {"app_name": APP_NAME, "user": user, **extra}


def _render(request: Request, name: str, context: dict):
    return templates.TemplateResponse(
        request=request,
        name=name,
        context=context,
    )


@router.get("/login")
def login_page(request: Request, user: CurrentUser | None = Depends(get_optional_user)):
    if user:
        return RedirectResponse(url="/")
    return _render(
        request,
        "login.html",
        {"app_name": APP_NAME},
    )


@router.get("/")
def dashboard_page(request: Request, user: CurrentUser | None = Depends(get_optional_user)):
    if not user:
        return RedirectResponse(url="/login")
    return _render(
        request,
        "dashboard.html",
        _ctx(request, user, active="dashboard"),
    )


@router.get("/files")
def files_page(request: Request, user: CurrentUser | None = Depends(get_optional_user)):
    if not user:
        return RedirectResponse(url="/login")
    return _render(
        request,
        "files.html",
        _ctx(request, user, active="files"),
    )


@router.get("/shared")
def shared_page(request: Request, user: CurrentUser | None = Depends(get_optional_user)):
    if not user:
        return RedirectResponse(url="/login")
    return _render(
        request,
        "shared.html",
        _ctx(request, user, active="shared"),
    )


@router.get("/media")
def media_page(request: Request, user: CurrentUser | None = Depends(get_optional_user)):
    if not user:
        return RedirectResponse(url="/login")
    return _render(
        request,
        "media.html",
        _ctx(request, user, active="media"),
    )


@router.get("/admin")
def admin_page(request: Request, user: CurrentUser | None = Depends(get_optional_user)):
    if not user:
        return RedirectResponse(url="/login")
    if not user.is_admin:
        return RedirectResponse(url="/")
    return _render(
        request,
        "admin.html",
        _ctx(request, user, active="admin"),
    )


@router.get("/profile")
def profile_page(request: Request, user: CurrentUser | None = Depends(get_optional_user)):
    if not user:
        return RedirectResponse(url="/login")
    return _render(
        request,
        "profile.html",
        _ctx(request, user, active="profile"),
    )
