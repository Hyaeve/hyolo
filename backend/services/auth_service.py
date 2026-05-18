from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
import time
from typing import Any

from backend.core.config import Settings


logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self) -> None:
        self._settings: Settings | None = None
        self._lock = threading.RLock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._failed_attempts: dict[str, dict[str, float | int]] = {}

    def initialize(self, settings: Settings) -> None:
        with self._lock:
            self._settings = settings
            self._ensure_store()

    def authenticate(self, username: str, password: str) -> bool:
        credentials = self._load_credentials()
        if credentials["username"] != username:
            return False
        return self._verify_password(password, credentials["salt"], credentials["password_hash"])

    def create_session(self, username: str) -> str:
        ttl_seconds = self._require_settings().auth.session_ttl_minutes * 60
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = {
                "username": username,
                "expires_at": time.time() + ttl_seconds,
            }
        return token

    def validate_session(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock:
            session = self._sessions.get(token)
            if not session:
                return False
            if session["expires_at"] < time.time():
                self._sessions.pop(token, None)
                return False
            return True

    def get_session_username(self, token: str | None) -> str | None:
        if not self.validate_session(token):
            return None
        with self._lock:
            session = self._sessions.get(token)
            return session["username"] if session else None

    def revoke_session(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def revoke_all_sessions(self) -> None:
        with self._lock:
            self._sessions.clear()

    def check_login_allowed(self, identity: str) -> tuple[bool, int]:
        if not identity:
            return True, 0

        now = time.time()
        with self._lock:
            state = self._failed_attempts.get(identity)
            if not state:
                return True, 0

            locked_until = float(state.get("locked_until", 0) or 0)
            if locked_until <= now:
                self._failed_attempts.pop(identity, None)
                return True, 0

            return False, max(1, int(locked_until - now))

    def record_login_failure(self, identity: str) -> int:
        if not identity:
            return 0

        settings = self._require_settings()
        now = time.time()
        max_failures = max(1, settings.auth.max_login_failures)
        lockout_seconds = max(1, settings.auth.lockout_minutes) * 60

        with self._lock:
            state = self._failed_attempts.get(identity, {"count": 0, "locked_until": 0.0})
            if float(state.get("locked_until", 0) or 0) <= now:
                state = {"count": 0, "locked_until": 0.0}

            state["count"] = int(state.get("count", 0)) + 1
            if int(state["count"]) >= max_failures:
                state["locked_until"] = now + lockout_seconds
            self._failed_attempts[identity] = state

            return max(0, int(float(state.get("locked_until", 0) or 0) - now))

    def record_login_success(self, identity: str) -> None:
        if not identity:
            return

        with self._lock:
            self._failed_attempts.pop(identity, None)

    def profile(self) -> dict[str, Any]:
        credentials = self._load_credentials()
        return {
            "username": credentials["username"],
            "must_change_password": credentials["must_change_password"],
        }

    def must_change_password(self) -> bool:
        credentials = self._load_credentials()
        return bool(credentials["must_change_password"])

    def change_credentials(self, current_password: str, new_username: str, new_password: str) -> dict[str, Any]:
        settings = self._require_settings()
        if not new_username.strip():
            raise RuntimeError("username cannot be empty")
        if len(new_password) < settings.auth.min_password_length:
            raise RuntimeError(f"new password must be at least {settings.auth.min_password_length} characters")

        credentials = self._load_credentials()
        if not self._verify_password(current_password, credentials["salt"], credentials["password_hash"]):
            raise RuntimeError("current password is incorrect")

        salt = secrets.token_hex(16)
        password_hash = self._hash_password(new_password, salt)
        updated = {
            "username": new_username.strip(),
            "salt": salt,
            "password_hash": password_hash,
            "updated_at": int(time.time()),
            "must_change_password": False,
            "bootstrap_password": False,
        }

        with settings.auth_file.open("w", encoding="utf-8") as handle:
            json.dump(updated, handle, ensure_ascii=False, indent=2)

        self.revoke_all_sessions()
        return {"username": updated["username"]}

    def _ensure_store(self) -> None:
        settings = self._require_settings()
        settings.auth_file.parent.mkdir(parents=True, exist_ok=True)
        if settings.auth_file.exists():
            return

        username = settings.auth.default_username.strip() or "admin"
        configured_password = settings.auth.default_password.strip()
        generated_password = ""
        if not configured_password or configured_password.lower() == "password":
            generated_password = secrets.token_urlsafe(18)
            configured_password = generated_password

        salt = secrets.token_hex(16)
        payload = {
            "username": username,
            "salt": salt,
            "password_hash": self._hash_password(configured_password, salt),
            "updated_at": int(time.time()),
            "must_change_password": True,
            "bootstrap_password": True,
        }
        with settings.auth_file.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

        if generated_password:
            logger.warning(
                "security bootstrap credentials generated; username=%s password=%s ; please log in and change password immediately",
                username,
                generated_password,
            )
        else:
            logger.warning(
                "security bootstrap credentials initialized for username=%s ; please change password immediately after first login",
                username,
            )

    def _load_credentials(self) -> dict[str, Any]:
        settings = self._require_settings()
        self._ensure_store()
        with settings.auth_file.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return {
            "username": payload.get("username", settings.auth.default_username),
            "salt": payload["salt"],
            "password_hash": payload["password_hash"],
            "must_change_password": bool(payload.get("must_change_password", False)),
        }

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            200000,
        ).hex()

    def _verify_password(self, password: str, salt: str, expected_hash: str) -> bool:
        actual_hash = self._hash_password(password, salt)
        return secrets.compare_digest(actual_hash, expected_hash)

    def _require_settings(self) -> Settings:
        if self._settings is None:
            raise RuntimeError("settings not initialized")
        return self._settings


auth_service = AuthService()
