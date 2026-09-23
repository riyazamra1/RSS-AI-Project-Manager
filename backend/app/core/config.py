from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql://rss_manager:rss_manager@localhost:5432/rss_project_manager"
    api_prefix: str = "/api/v1"
    rss_core_url: str = ""
    rss_core_api_token: str = ""
    ray_poll_seconds: int = 5
    ray_poll_timeout_seconds: int = 900
    auto_chat_scheduler_enabled: bool = True
    auto_chat_poll_seconds: int = 30
    auto_chat_batch_size: int = 10
    auto_chat_retry_seconds: int = 60
    session_days: int = 30
    oauth_state_minutes: int = 10
    oauth_redirect_base_url: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    github_oauth_client_id: str = ""
    github_oauth_client_secret: str = ""
    worker_token: str = ""
    ray_execute_tasks: bool = True
    require_https_integrations: bool = True
    max_ray_payload_bytes: int = 262144
    max_ray_response_bytes: int = 1048576
    github_discovery_enabled: bool = False
    github_allowed_repositories: str = "riyazamra1/RSS-AI-Project-Manager"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
