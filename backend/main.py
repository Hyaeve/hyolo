from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.api.auth_api import router as auth_router
from backend.api.camera_api import router as camera_router
from backend.api.compare_api import router as compare_router
from backend.api.detect_api import router as detect_router
from backend.api.log_api import router as log_router
from backend.api.model_api import router as model_router
from backend.api.settings_api import router as settings_router
from backend.api.status_api import router as status_router
from backend.api.watch_api import router as watch_router
from backend.core.config import get_settings
from backend.core.logger import configure_logging
from backend.services.auth_service import auth_service
from backend.services.camera_service import camera_service
from backend.services.model_service import model_service
from backend.services.watch_service import watch_service


settings = get_settings()
configure_logging(settings.log_dir)

app = FastAPI(title=settings.app.name, version="3.2.0")
app.include_router(auth_router)
app.include_router(status_router)
app.include_router(model_router)
app.include_router(settings_router)
app.include_router(detect_router)
app.include_router(camera_router)
app.include_router(compare_router)
app.include_router(log_router)
app.include_router(watch_router)

app.mount("/assets", StaticFiles(directory=str(settings.frontend_dir / "assets")), name="assets")
app.mount("/outputs", StaticFiles(directory=str(settings.output_dir)), name="outputs")


def _frontend_cache_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }


PUBLIC_PATHS = {
    "/login",
    "/api/auth/login",
    "/api/auth/status",
}
PUBLIC_PREFIXES = ("/assets",)
PASSWORD_CHANGE_ALLOWED_API_PATHS = {
    "/api/auth/status",
    "/api/auth/logout",
    "/api/auth/change-credentials",
}


@app.middleware("http")
async def require_auth(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS":
        return await call_next(request)

    if path in PUBLIC_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
        return await call_next(request)

    token = request.cookies.get(settings.auth.cookie_name)
    if auth_service.validate_session(token):
        if path.startswith("/api/") and auth_service.must_change_password() and path not in PASSWORD_CHANGE_ALLOWED_API_PATHS:
            return JSONResponse(status_code=403, content={"detail": "password change required before using protected APIs"})
        return await call_next(request)

    if path.startswith("/api/"):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    return RedirectResponse(url="/login", status_code=303)


@app.on_event("startup")
def on_startup() -> None:
    settings.ensure_directories()
    auth_service.initialize(settings)
    model_service.initialize(settings)
    camera_service.initialize(settings)
    watch_service.initialize(settings)


@app.on_event("shutdown")
def on_shutdown() -> None:
    camera_service.stop_all()
    watch_service.stop()


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(Path(settings.frontend_dir) / "index.html", headers=_frontend_cache_headers())


@app.get("/login", include_in_schema=False)
def login_page() -> FileResponse:
    return FileResponse(Path(settings.frontend_dir) / "login.html", headers=_frontend_cache_headers())
