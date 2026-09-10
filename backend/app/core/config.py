from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BTB League API"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./btb-local.db"
    local_create_schema: bool = True
    secret_key: str = "change-me"
    access_token_minutes: int = 720
    sleeper_base_url: str = "https://api.sleeper.app/v1"
    sleeper_league_id: str = ""
    season_year: int = 2026
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_display_name: str = "Bootstrap Admin"
    bootstrap_admin_password: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
