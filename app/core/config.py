"""
Configuration management system.
"""
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Application settings
    APP_NAME: str = "Computer Use Session Backend"
    DEBUG: bool = Field(default=False, env="DEBUG")
    BASE_DIR: Path = Path(__file__).parent.parent

    # API settings
    API_V1_STR: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = Field(
        default=["*"],
        env="ALLOWED_ORIGINS",
    )

    # Database settings
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:comp_use_password@localhost:5432/postgres",
        env="DATABASE_URL",
    )

    # Anthropic API settings
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    DEFAULT_MODEL: str = Field(
        default="claude-sonnet-4-5-20250929", env="DEFAULT_MODEL"
    )

    # Authentication settings
    REQUIRE_API_KEY: bool = Field(default=False, env="REQUIRE_API_KEY")

    # VNC settings
    VNC_HOST: str = Field(default="localhost", env="VNC_HOST")
    VNC_PORT: int = Field(default=5900, env="VNC_PORT")
    VNC_PASSWORD: Optional[str] = Field(default=None, env="VNC_PASSWORD")

    # Session settings
    MAX_SESSIONS: int = Field(default=10, env="MAX_SESSIONS")
    SESSION_TIMEOUT_MINUTES: int = Field(default=60, env="SESSION_TIMEOUT_MINUTES")

    # Logging settings
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
