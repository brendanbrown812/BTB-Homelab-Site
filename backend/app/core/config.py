from functools import lru_cache
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BTB League API"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./btb-local.db"
    local_create_schema: bool = True
    secret_key: str = "change-me"
    access_token_minutes: int = 60 * 24 * 30
    sleeper_base_url: str = "https://api.sleeper.app/v1"
    sleeper_league_id: str = ""
    notion_base_url: str = "https://api.notion.com"
    notion_api_version: str = "2026-03-11"
    notion_api_token: SecretStr = SecretStr("")
    notion_game_history_data_source_id: str = ""
    notion_game_history_database_id: str = ""
    notion_timeout_seconds: float = 20.0
    task_poll_seconds: int = 30
    task_lease_seconds: int = 15 * 60
    task_retry_minutes: int = 15
    season_year: int = 2026
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_display_name: str = "Bootstrap Admin"
    bootstrap_admin_password: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    public_site_url: str = "http://localhost:3000"
    discord_poll_webhook_url: str = ""
    discord_poll_role_id: str = ""

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
