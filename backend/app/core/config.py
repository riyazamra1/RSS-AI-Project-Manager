from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://rss_manager:rss_manager@localhost:5432/rss_project_manager"
    api_prefix: str = "/api/v1"
    rss_core_url: str = ""
    rss_core_api_token: str = ""
    ray_poll_seconds: int = 5
    ray_poll_timeout_seconds: int = 900

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
