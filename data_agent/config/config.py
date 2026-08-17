import os

from dotenv import load_dotenv

load_dotenv()


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


_PLACEHOLDER_VALUES = {
    "your_moonshot_api_key_here",
    "your_tavily_api_key_here",
    "your_jwt_secret_key_here",
    "change_me",
    "changeme",
}
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _optional_env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    if not value or value.lower() in _PLACEHOLDER_VALUES:
        return None
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ConfigurationError(
        f"{name} must be one of: "
        f"{', '.join(sorted(_TRUE_VALUES | _FALSE_VALUES))}"
    )


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc


def _env_positive_int(name: str, default: int) -> int:
    value = _env_int(name, default)
    if value <= 0:
        raise ConfigurationError(f"{name} must be a positive integer")
    return value


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc


def _env_origins(name: str, default: str) -> tuple[str, ...]:
    raw_value = os.environ.get(name, default)
    origins = tuple(
        dict.fromkeys(
            origin.strip().rstrip("/")
            for origin in raw_value.split(",")
            if origin.strip()
        )
    )
    if not origins:
        raise ConfigurationError(f"{name} must contain at least one origin")
    if "*" in origins:
        raise ConfigurationError(
            f"{name} cannot contain '*' when credentials are enabled"
        )
    if any("://" not in origin for origin in origins):
        raise ConfigurationError(
            f"{name} entries must be absolute origins"
        )
    return origins


class Config:
    """Application configuration parsed from environment variables."""

    def __init__(self) -> None:
        self.MOONSHOT_API_KEY = _optional_env("MOONSHOT_API_KEY")
        self.TAVILY_API_KEY = _optional_env("TAVILY_API_KEY")

        self.MODEL_NAME = os.environ.get(
            "MODEL_NAME", "kimi-k2-turbo-preview"
        ).strip()
        self.MODEL_BASE_URL = os.environ.get(
            "MODEL_BASE_URL", "https://api.moonshot.cn/v1"
        ).strip()
        self.MODEL_TEMPERATURE = _env_float("MODEL_TEMPERATURE", 0.3)

        self.FASTAPI_HOST = os.environ.get("FASTAPI_HOST", "0.0.0.0").strip()
        self.FASTAPI_PORT = _env_int("FASTAPI_PORT", 8000)
        self.NEXT_PUBLIC_REST_API_URL = os.environ.get(
            "NEXT_PUBLIC_REST_API_URL", "http://localhost:8000"
        ).strip().rstrip("/")

        self.DATABASE_URL = os.environ.get(
            "DATABASE_URL",
            "mysql+pymysql://root:test@localhost:3306/mydb",
        ).strip()
        self.REDIS_URL = os.environ.get(
            "REDIS_URL", "redis://localhost:6379/0"
        ).strip()
        self.REDIS_SOCKET_TIMEOUT_SECONDS = _env_float(
            "REDIS_SOCKET_TIMEOUT_SECONDS", 1.0
        )

        self.FILE_STORAGE_ROOT = os.environ.get(
            "FILE_STORAGE_ROOT", "var/managed_files"
        ).strip()
        if not self.FILE_STORAGE_ROOT:
            raise ConfigurationError("FILE_STORAGE_ROOT cannot be empty")
        self.FILE_UPLOAD_MAX_BYTES = _env_positive_int(
            "FILE_UPLOAD_MAX_BYTES", 5 * 1024 * 1024
        )
        self.FILE_UPLOAD_BATCH_MAX_BYTES = _env_positive_int(
            "FILE_UPLOAD_BATCH_MAX_BYTES", 10 * 1024 * 1024
        )
        self.FILE_UPLOAD_REQUEST_MAX_BYTES = _env_positive_int(
            "FILE_UPLOAD_REQUEST_MAX_BYTES", 11 * 1024 * 1024
        )
        self.FILE_UPLOAD_BATCH_MAX_COUNT = _env_positive_int(
            "FILE_UPLOAD_BATCH_MAX_COUNT", 5
        )
        self.FILE_USER_QUOTA_BYTES = _env_positive_int(
            "FILE_USER_QUOTA_BYTES", 100 * 1024 * 1024
        )
        self.FILE_USER_MAX_COUNT = _env_positive_int(
            "FILE_USER_MAX_COUNT", 100
        )
        self.FILE_RETENTION_HOURS = _env_positive_int(
            "FILE_RETENTION_HOURS", 7 * 24
        )
        self.FILE_ANALYSIS_MAX_CHARS = _env_positive_int(
            "FILE_ANALYSIS_MAX_CHARS", 20000
        )
        if self.FILE_UPLOAD_BATCH_MAX_BYTES < self.FILE_UPLOAD_MAX_BYTES:
            raise ConfigurationError(
                "FILE_UPLOAD_BATCH_MAX_BYTES must be >= "
                "FILE_UPLOAD_MAX_BYTES"
            )
        if (
            self.FILE_UPLOAD_REQUEST_MAX_BYTES
            < self.FILE_UPLOAD_BATCH_MAX_BYTES
        ):
            raise ConfigurationError(
                "FILE_UPLOAD_REQUEST_MAX_BYTES must be >= "
                "FILE_UPLOAD_BATCH_MAX_BYTES"
            )
        if self.FILE_USER_QUOTA_BYTES < self.FILE_UPLOAD_BATCH_MAX_BYTES:
            raise ConfigurationError(
                "FILE_USER_QUOTA_BYTES must be >= "
                "FILE_UPLOAD_BATCH_MAX_BYTES"
            )
        if self.FILE_USER_MAX_COUNT < self.FILE_UPLOAD_BATCH_MAX_COUNT:
            raise ConfigurationError(
                "FILE_USER_MAX_COUNT must be >= "
                "FILE_UPLOAD_BATCH_MAX_COUNT"
            )

        self.ENABLE_CODE_EXECUTION = _env_bool(
            "ENABLE_CODE_EXECUTION", default=False
        )
        jwt_secret = _optional_env("JWT_SECRET_KEY")
        self.JWT_SECRET_KEY = (
            jwt_secret if jwt_secret and len(jwt_secret) >= 32 else None
        )
        self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = _env_positive_int(
            "JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 30
        )
        self.CORS_ALLOWED_ORIGINS = _env_origins(
            "CORS_ALLOWED_ORIGINS", "http://localhost:3000"
        )
        self.SERVICE_NAME = os.environ.get(
            "SERVICE_NAME", "deep-data-agent"
        ).strip()
        self.LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
        self.LOG_FILE_PATH = os.environ.get(
            "LOG_FILE_PATH", "deep_data_agent.log"
        ).strip()
        self.LOG_MAX_BYTES = _env_positive_int(
            "LOG_MAX_BYTES", 10 * 1024 * 1024
        )
        self.LOG_BACKUP_COUNT = _env_positive_int(
            "LOG_BACKUP_COUNT", 3
        )

        self.RATE_LIMIT_ENABLED = _env_bool(
            "RATE_LIMIT_ENABLED", default=True
        )
        self.TRUSTED_PROXY_COUNT = _env_int("TRUSTED_PROXY_COUNT", 0)
        if self.TRUSTED_PROXY_COUNT < 0:
            raise ConfigurationError(
                "TRUSTED_PROXY_COUNT must be >= 0"
            )
        self.RATE_LIMIT_AUTH_MAX_REQUESTS = _env_positive_int(
            "RATE_LIMIT_AUTH_MAX_REQUESTS", 10
        )
        self.RATE_LIMIT_AUTH_WINDOW_SECONDS = _env_positive_int(
            "RATE_LIMIT_AUTH_WINDOW_SECONDS", 60
        )
        self.RATE_LIMIT_QUERY_MAX_REQUESTS = _env_positive_int(
            "RATE_LIMIT_QUERY_MAX_REQUESTS", 20
        )
        self.RATE_LIMIT_QUERY_WINDOW_SECONDS = _env_positive_int(
            "RATE_LIMIT_QUERY_WINDOW_SECONDS", 60
        )
        self.RATE_LIMIT_SESSION_MAX_REQUESTS = _env_positive_int(
            "RATE_LIMIT_SESSION_MAX_REQUESTS", 60
        )
        self.RATE_LIMIT_SESSION_WINDOW_SECONDS = _env_positive_int(
            "RATE_LIMIT_SESSION_WINDOW_SECONDS", 60
        )
        self.RATE_LIMIT_DEFAULT_MAX_REQUESTS = _env_positive_int(
            "RATE_LIMIT_DEFAULT_MAX_REQUESTS", 120
        )
        self.RATE_LIMIT_DEFAULT_WINDOW_SECONDS = _env_positive_int(
            "RATE_LIMIT_DEFAULT_WINDOW_SECONDS", 60
        )

    def require_model_api_key(self) -> str:
        """Return the model API key or raise a stable configuration error."""
        missing = [
            name
            for name, value in (
                ("MOONSHOT_API_KEY", self.MOONSHOT_API_KEY),
                ("MODEL_NAME", self.MODEL_NAME),
                ("MODEL_BASE_URL", self.MODEL_BASE_URL),
            )
            if not value
        ]
        if missing:
            raise ConfigurationError(
                "Missing required model configuration: " + ", ".join(missing)
            )
        return self.MOONSHOT_API_KEY

    def require_search_api_key(self) -> str:
        """Return the search API key or raise a stable configuration error."""
        if not self.TAVILY_API_KEY:
            raise ConfigurationError(
                "TAVILY_API_KEY is required for internet search"
            )
        return self.TAVILY_API_KEY

    def require_jwt_secret_key(self) -> str:
        """Return the JWT secret or raise a stable configuration error."""
        if not self.JWT_SECRET_KEY:
            raise ConfigurationError(
                "JWT_SECRET_KEY must be at least 32 characters and must not "
                "be a placeholder"
            )
        return self.JWT_SECRET_KEY

    @property
    def sensitive_values(self) -> tuple[str, ...]:
        """Values that must be removed from diagnostic output."""
        return tuple(
            value
            for value in (
                self.MOONSHOT_API_KEY,
                self.TAVILY_API_KEY,
                self.JWT_SECRET_KEY,
                self.DATABASE_URL,
                self.REDIS_URL,
            )
            if value
        )


config = Config()
