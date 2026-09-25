from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional

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
    data_dir: str = "data"
    sqlite_path: str | None = None
    cors_origins: str = "http://localhost:8501"

config = Config()

def get_client(config: Config) -> ChatGroq | ChatOpenAI | ChatGoogleGenerativeAI | ChatOllama:
    base_url = config.base_url or None
    if config.provider == "groq":
        return ChatGroq(
            api_key=config.api_key,
            base_url=base_url,
            model=config.model
        )
    elif config.provider == "openai":
        return ChatOpenAI(
            api_key=config.api_key or "unused",
            base_url=base_url,
            model=config.model
        )
    elif config.provider == "google":
        return ChatGoogleGenerativeAI(
            api_key=config.api_key,
            base_url=base_url,
            model=config.model
        )
    elif config.provider == "ollama":
        return ChatOllama(
            model=config.model,
            base_url=base_url,
        )
    else:
        raise ValueError(f"Invalid provider: {config.provider}")
