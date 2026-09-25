from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional

from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama

class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    provider: Literal["groq", "openai", "google", "ollama"] = "groq"
    api_key: str = ""
    model: str
    base_url: Optional[str] = None
    max_retries: int = 6
    requests_per_minute: float = 0
    vision_images: bool = True
    data_dir: str = "data"
    sqlite_path: str | None = None
    cors_origins: str = "http://localhost:8501"

config = Config()


def _rate_limiter(config: Config) -> InMemoryRateLimiter | None:
    # One limiter per client; every agent shares the client, so this paces the whole turn.
    if config.requests_per_minute <= 0:
        return None
    return InMemoryRateLimiter(
        requests_per_second=config.requests_per_minute / 60,
        check_every_n_seconds=0.2,
        max_bucket_size=2,
    )


def get_client(config: Config) -> ChatGroq | ChatOpenAI | ChatGoogleGenerativeAI | ChatOllama:
    base_url = config.base_url or None
    rate_limiter = _rate_limiter(config)
    if config.provider == "groq":
        return ChatGroq(
            api_key=config.api_key,
            base_url=base_url,
            model=config.model,
            max_retries=config.max_retries,
            rate_limiter=rate_limiter,
        )
    elif config.provider == "openai":
        return ChatOpenAI(
            api_key=config.api_key or "unused",
            base_url=base_url,
            model=config.model,
            max_retries=config.max_retries,
            rate_limiter=rate_limiter,
        )
    elif config.provider == "google":
        return ChatGoogleGenerativeAI(
            api_key=config.api_key,
            base_url=base_url,
            model=config.model,
            max_retries=config.max_retries,
            rate_limiter=rate_limiter,
        )
    elif config.provider == "ollama":
        return ChatOllama(
            model=config.model,
            # base_url=base_url,
        )
    else:
        raise ValueError(f"Invalid provider: {config.provider}")
