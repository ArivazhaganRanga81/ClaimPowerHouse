from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CPH_", env_file=".env", extra="ignore")

    env: str = "development"
    data_root: Path = Path("data/runtime")
    database_url: str = "sqlite:///./data/runtime/db/claim_powerhouse.db"
    chroma_path: Path = Path("data/runtime/chroma")
    web_root: Path = Path("apps/web/dist")
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_model_path: Path | None = None
    llm_provider: str = "stub"
    llm_model: str = "gpt-5-mini"
    llm_api_key: str | None = None
    session_secret: str = "development-only-secret"
    sidecar_token: str | None = None
    allowed_origins: str = "http://localhost:5173"
    auto_seed: bool = True
    demo_mode: bool = True
    max_parallel_agents: int = Field(default=3, ge=1, le=8)

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    def ensure_directories(self) -> None:
        for path in (
            self.data_root,
            self.data_root / "db",
            self.chroma_path,
            self.data_root / "documents",
            self.data_root / "backups",
            self.data_root / "logs",
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
