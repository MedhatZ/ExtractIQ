from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"
    mock_ai: bool = True
    fetch_timeout_seconds: float = 10.0
    openai_timeout_seconds: float = 60.0
    allowed_content_max_bytes: int = 500_000
    max_text_chars: int = 12_000
    max_redirects: int = 5
    host: str = "127.0.0.1"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
