from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str

    @field_validator("database_url")
    @classmethod
    def _use_asyncpg_driver(cls, v: str) -> str:
        # Render/Heroku/Aiven hand out postgres:// or postgresql:// URLs; async SQLAlchemy needs the asyncpg driver
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        # asyncpg rejects libpq's sslmode= query param; its equivalent is ssl=
        if "+asyncpg" in v and "sslmode=" in v:
            v = v.replace("sslmode=", "ssl=")
        return v
    app_base_url: str
    # NOTE: also key material — owner wallet keys are derived from it, so rotating
    # this orphans every provisioned wallet. Back it up like a private key.
    secret_key: str

    bmoni_base_url: str = "https://embedded-dev.bmoni.com"
    bmoni_api_key: str = ""
    # sandbox-only BVN; real ones are rejected outside production
    bmoni_test_bvn: str = "22222222222"
    bmoni_webhook_secret: str = ""

    class Config:
        env_file = ".env"
        # ignore unrecognised vars rather than refusing to boot over them — a
        # stale leftover in the environment shouldn't take the whole app down
        extra = "ignore"


settings = Settings()
