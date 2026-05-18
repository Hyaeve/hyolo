from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.core.config import get_settings
from backend.services.auth_service import auth_service


router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangeCredentialsRequest(BaseModel):
    current_password: str
    new_username: str
    new_password: str


def _should_set_secure_cookie(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto:
        return forwarded_proto.split(",", 1)[0].strip().lower() == "https"
    return request.url.scheme.lower() == "https"


def _set_session_cookie(response: JSONResponse, request: Request, cookie_name: str, token: str, max_age: int) -> None:
    response.set_cookie(
        key=cookie_name,
        value=token,
        httponly=True,
        samesite="strict",
        max_age=max_age,
        secure=_should_set_secure_cookie(request),
        path="/",
    )


@router.post("/api/auth/login")
def login(payload: LoginRequest, request: Request) -> JSONResponse:
    settings = get_settings()
    username = payload.username.strip()
    client_host = request.client.host if request.client else "unknown"
    identity = f"{client_host}:{username.lower()}"
    allowed, retry_after = auth_service.check_login_allowed(identity)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"too many login attempts, retry after {retry_after} seconds")

    if not auth_service.authenticate(username, payload.password):
        auth_service.record_login_failure(identity)
        raise HTTPException(status_code=401, detail="invalid username or password")

    auth_service.record_login_success(identity)
    token = auth_service.create_session(username)
    response = JSONResponse(
        {
            "success": True,
            "username": username,
            "must_change_password": auth_service.must_change_password(),
        }
    )
    _set_session_cookie(response, request, settings.auth.cookie_name, token, settings.auth.session_ttl_minutes * 60)
    return response


@router.post("/api/auth/logout")
def logout(request: Request) -> Response:
    settings = get_settings()
    token = request.cookies.get(settings.auth.cookie_name)
    auth_service.revoke_session(token)
    response = JSONResponse({"success": True})
    response.delete_cookie(settings.auth.cookie_name, path="/")
    return response


@router.get("/api/auth/status")
def status(request: Request) -> dict:
    settings = get_settings()
    token = request.cookies.get(settings.auth.cookie_name)
    authenticated = auth_service.validate_session(token)
    profile = auth_service.profile() if authenticated else {"username": None, "must_change_password": False}
    return {
        "authenticated": authenticated,
        "username": profile["username"] if authenticated else None,
        "must_change_password": bool(profile["must_change_password"]) if authenticated else False,
    }


@router.post("/api/auth/change-credentials")
def change_credentials(payload: ChangeCredentialsRequest, request: Request) -> JSONResponse:
    settings = get_settings()
    token = request.cookies.get(settings.auth.cookie_name)
    if not auth_service.validate_session(token):
        raise HTTPException(status_code=401, detail="unauthorized")

    try:
        updated = auth_service.change_credentials(
            current_password=payload.current_password,
            new_username=payload.new_username,
            new_password=payload.new_password,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    new_token = auth_service.create_session(updated["username"])
    response = JSONResponse({"success": True, "username": updated["username"]})
    _set_session_cookie(response, request, settings.auth.cookie_name, new_token, settings.auth.session_ttl_minutes * 60)
    return response
