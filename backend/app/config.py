"""
Centralised configuration — reads from environment / .env file.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── PostgreSQL ──
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "ims"
    POSTGRES_USER: str = "ims_user"
    POSTGRES_PASSWORD: str = "ims_secret"

    # ── MongoDB ──
    MONGODB_HOST: str = "localhost"
    MONGODB_PORT: int = 27017
    MONGODB_USER: str = "ims_user"
    MONGODB_PASSWORD: str = "ims_secret"
    MONGODB_DB: str = "ims"

    # ── Redis ──
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # ── Rate Limiter ──
    RATE_LIMIT_MAX: int = 10000
    RATE_LIMIT_WINDOW: int = 60

    # ── Debouncer ──
    DEBOUNCE_WINDOW_SECONDS: int = 60

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def mongodb_dsn(self) -> str:
        return (
            f"mongodb://{self.MONGODB_USER}:{self.MONGODB_PASSWORD}"
            f"@{self.MONGODB_HOST}:{self.MONGODB_PORT}"
        )

    @property
    def redis_dsn(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
