from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


BASE_DIR = Path(__file__).resolve().parents[2]


def _normalize_config_file_path(config_file: str | Path) -> Path:
    candidate = Path(config_file)
    if candidate.is_absolute():
        return candidate
    return (BASE_DIR / candidate).resolve()


def _config_path_from_env() -> Path:
    return _normalize_config_file_path(os.getenv("APP_CONFIG_FILE", BASE_DIR / "config" / "config.yaml"))


@dataclass
class AppConfig:
    name: str = "Herbal Vision"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


@dataclass
class ModelConfig:
    path: str = "./models/best.pt"
    device: str = "cpu"
    conf: float = 0.25
    iou: float = 0.45
    imgsz: int = 512
    allow_upload: bool = False
    allow_unsafe_serialized_uploads: bool = False


@dataclass
class RuntimeConfig:
    cpu_threads: int = 2
    max_upload_size_mb: int = 256
    max_batch_files: int = 10
    save_result: bool = True


@dataclass
class CameraConfig:
    default_fps_limit: int = 6
    reconnect_interval: int = 5
    read_timeout: int = 10


@dataclass
class AIConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout_seconds: int = 30


@dataclass
class AuthConfig:
    default_username: str = "admin"
    default_password: str = ""
    session_ttl_minutes: int = 1440
    auth_file: str = "./config/auth.json"
    cookie_name: str = "hv_session"
    min_password_length: int = 8
    max_login_failures: int = 5
    lockout_minutes: int = 15


@dataclass
class PathConfig:
    upload_dir: str = "./uploads"
    output_dir: str = "./outputs"
    watch_dir: str = "./watch"
    log_dir: str = "./logs"
    frontend_dir: str = "./frontend"


@dataclass
class Settings:
    app: AppConfig
    model: ModelConfig
    runtime: RuntimeConfig
    camera: CameraConfig
    ai: AIConfig
    auth: AuthConfig
    path: PathConfig
    config_file: Path

    @staticmethod
    def _resolve_path(value: str) -> Path:
        candidate = Path(value)
        return candidate if candidate.is_absolute() else (BASE_DIR / candidate).resolve()

    @property
    def model_path(self) -> Path:
        return self._resolve_path(self.model.path)

    @property
    def models_dir(self) -> Path:
        return self.model_path.parent

    @property
    def upload_dir(self) -> Path:
        return self._resolve_path(self.path.upload_dir)

    @property
    def upload_images_dir(self) -> Path:
        return self.upload_dir / "images"

    @property
    def upload_videos_dir(self) -> Path:
        return self.upload_dir / "videos"

    @property
    def output_dir(self) -> Path:
        return self._resolve_path(self.path.output_dir)

    @property
    def output_images_dir(self) -> Path:
        return self.output_dir / "images"

    @property
    def output_videos_dir(self) -> Path:
        return self.output_dir / "videos"

    @property
    def output_comparisons_dir(self) -> Path:
        return self.output_dir / "comparisons"

    @property
    def watch_dir(self) -> Path:
        return self._resolve_path(self.path.watch_dir)

    @property
    def log_dir(self) -> Path:
        return self._resolve_path(self.path.log_dir)

    @property
    def auth_file(self) -> Path:
        return self._resolve_path(self.auth.auth_file)

    @property
    def frontend_dir(self) -> Path:
        return self._resolve_path(self.path.frontend_dir)

    def ensure_directories(self) -> None:
        for directory in (
            self.models_dir,
            self.upload_dir,
            self.upload_images_dir,
            self.upload_videos_dir,
            self.output_dir,
            self.output_images_dir,
            self.output_videos_dir,
            self.output_comparisons_dir,
            self.watch_dir,
            self.log_dir,
            self.auth_file.parent,
            self.frontend_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "app": self.app.__dict__.copy(),
            "model": self.model.__dict__.copy(),
            "runtime": self.runtime.__dict__.copy(),
            "camera": self.camera.__dict__.copy(),
            "ai": self.ai.__dict__.copy(),
            "auth": self.auth.__dict__.copy(),
            "path": self.path.__dict__.copy(),
        }

    def _runtime_env_overrides(self) -> dict[str, Any]:
        return {
            "ai": {
                "base_url": os.getenv("AI_BASE_URL", "").strip(),
                "api_key": os.getenv("AI_API_KEY", "").strip(),
                "model": os.getenv("AI_MODEL", "").strip(),
            }
        }

    def to_persisted_config_dict(self) -> dict[str, Any]:
        config = self.to_config_dict()
        runtime_env = self._runtime_env_overrides()
        ai_runtime = runtime_env.get("ai", {})
        ai_config = dict(config.get("ai", {}))
        for key in ("base_url", "api_key", "model"):
            if ai_runtime.get(key):
                ai_config[key] = ai_runtime[key]
        config["ai"] = ai_config
        return config

    def save(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with self.config_file.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(self.to_persisted_config_dict(), handle, ensure_ascii=False, sort_keys=False)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml_config(config_file: Path) -> dict[str, Any]:
    if not config_file.exists():
        return {}
    with config_file.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _env_override(config: dict[str, Any]) -> dict[str, Any]:
    mapping: dict[str, tuple[str, str, Any]] = {
        "APP_NAME": ("app", "name", str),
        "APP_HOST": ("app", "host", str),
        "APP_PORT": ("app", "port", int),
        "APP_DEBUG": ("app", "debug", lambda raw: raw.lower() == "true"),
        "MODEL_PATH": ("model", "path", str),
        "DEVICE": ("model", "device", str),
        "MODEL_CONF": ("model", "conf", float),
        "MODEL_IOU": ("model", "iou", float),
        "MODEL_IMGSZ": ("model", "imgsz", int),
        "ALLOW_MODEL_UPLOAD": ("model", "allow_upload", lambda raw: raw.lower() == "true"),
        "ALLOW_UNSAFE_MODEL_UPLOADS": ("model", "allow_unsafe_serialized_uploads", lambda raw: raw.lower() == "true"),
        "CPU_THREADS": ("runtime", "cpu_threads", int),
        "MAX_UPLOAD_SIZE_MB": ("runtime", "max_upload_size_mb", int),
        "MAX_BATCH_FILES": ("runtime", "max_batch_files", int),
        "SAVE_RESULT": ("runtime", "save_result", lambda raw: raw.lower() == "true"),
        "CAMERA_DEFAULT_FPS_LIMIT": ("camera", "default_fps_limit", int),
        "CAMERA_RECONNECT_INTERVAL": ("camera", "reconnect_interval", int),
        "CAMERA_READ_TIMEOUT": ("camera", "read_timeout", int),
        "AI_BASE_URL": ("ai", "base_url", str),
        "AI_API_KEY": ("ai", "api_key", str),
        "AI_MODEL": ("ai", "model", str),
        "AI_TIMEOUT_SECONDS": ("ai", "timeout_seconds", int),
        "AUTH_DEFAULT_USERNAME": ("auth", "default_username", str),
        "AUTH_DEFAULT_PASSWORD": ("auth", "default_password", str),
        "AUTH_SESSION_TTL_MINUTES": ("auth", "session_ttl_minutes", int),
        "AUTH_FILE": ("auth", "auth_file", str),
        "AUTH_COOKIE_NAME": ("auth", "cookie_name", str),
        "AUTH_MIN_PASSWORD_LENGTH": ("auth", "min_password_length", int),
        "AUTH_MAX_LOGIN_FAILURES": ("auth", "max_login_failures", int),
        "AUTH_LOCKOUT_MINUTES": ("auth", "lockout_minutes", int),
        "UPLOAD_DIR": ("path", "upload_dir", str),
        "OUTPUT_DIR": ("path", "output_dir", str),
        "WATCH_DIR": ("path", "watch_dir", str),
        "LOG_DIR": ("path", "log_dir", str),
        "FRONTEND_DIR": ("path", "frontend_dir", str),
    }

    updated = dict(config)
    for env_key, (section, field, caster) in mapping.items():
        raw = os.getenv(env_key)
        if raw is None:
            continue
        section_data = dict(updated.get(section, {}))
        section_data[field] = caster(raw)
        updated[section] = section_data
    return updated


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    config_file = _config_path_from_env()
    defaults = {
        "app": AppConfig().__dict__,
        "model": ModelConfig().__dict__,
        "runtime": RuntimeConfig().__dict__,
        "camera": CameraConfig().__dict__,
        "ai": AIConfig().__dict__,
        "auth": AuthConfig().__dict__,
        "path": PathConfig().__dict__,
    }
    yaml_config = _load_yaml_config(config_file)
    if "llm" in yaml_config and "ai" not in yaml_config:
        yaml_config["ai"] = yaml_config.pop("llm")
    merged = _env_override(_deep_merge(defaults, yaml_config))
    settings = Settings(
        app=AppConfig(**merged.get("app", {})),
        model=ModelConfig(**merged.get("model", {})),
        runtime=RuntimeConfig(**merged.get("runtime", {})),
        camera=CameraConfig(**merged.get("camera", {})),
        ai=AIConfig(**merged.get("ai", {})),
        auth=AuthConfig(**merged.get("auth", {})),
        path=PathConfig(**merged.get("path", {})),
        config_file=config_file,
    )
    settings.ensure_directories()
    return settings
