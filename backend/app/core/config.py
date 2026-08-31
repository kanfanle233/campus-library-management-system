"""Runtime configuration for the backend application."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ModuleNotFoundError:  # pragma: no cover - exercised only in minimal installs
    # Keep configuration importable for local diagnostics when the optional
    # pydantic-settings package has not been installed yet. The production
    # dependency provides the normal environment/.env loading behavior.
    from pydantic import BaseModel

    BaseSettings = BaseModel

    def SettingsConfigDict(**kwargs: object) -> dict[str, object]:
        return kwargs


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "backend" / "data" / "library.db"
DEFAULT_DATABASE_URL = f"sqlite+pysqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"


class Settings(BaseSettings):
    """Configuration loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_name: str = Field(default="Library Management System API", validation_alias="APP_NAME")
    app_version: str = Field(default="0.1.0", validation_alias="APP_VERSION")
    database_url: str = Field(
        default=DEFAULT_DATABASE_URL, validation_alias="DATABASE_URL"
    )
    jwt_secret_key: str = Field(default="", validation_alias="JWT_SECRET_KEY")
    jwt_expire_minutes: int = Field(default=30, validation_alias="JWT_EXPIRE_MINUTES", gt=0)
    cors_origins: str = Field(default="", validation_alias="CORS_ORIGINS")
    sqlite_busy_timeout_ms: int = Field(
        default=5_000, validation_alias="SQLITE_BUSY_TIMEOUT_MS", gt=0
    )
    sqlalchemy_echo: bool = Field(default=False, validation_alias="SQLALCHEMY_ECHO")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_path(self) -> Path:
        """Resolve a SQLite URL path for directory creation and diagnostics."""

        # SQLAlchemy accepts both ``sqlite:///`` and the explicit
        # ``sqlite+pysqlite:///`` dialect prefix.  Supporting both here keeps
        # ``init_db`` and a custom test/demo DATABASE_URL pointed at the same
        # file as the engine.
        for prefix in ("sqlite+pysqlite:///", "sqlite:///"):
            if self.database_url.startswith(prefix):
                raw_path = self.database_url[len(prefix) :]
                return Path(raw_path).expanduser().resolve()
        return DEFAULT_DATABASE_PATH


@lru_cache
def get_settings() -> Settings:
    return Settings()


# A single settings object keeps engine construction and application startup
# on the same configuration. Tests can clear ``get_settings``'s cache and
# replace this module attribute before importing the database package.
settings = get_settings()
