from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    PROJECT_NAME: str = "Task Management API"
    SECRET_KEY: str = "YOUR_SUPER_SECRET_KEY_CHANGE_IN_PRODUCTION"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 години

    POSTGRES_USER: str = os.environ.get('POSTGRES_USER')
    POSTGRES_PASSWORD: str = os.environ.get('POSTGRES_PASSWORD')
    POSTGRES_SERVER: str = os.environ.get('POSTGRES_SERVER')
    POSTGRES_PORT: int = os.environ.get('POSTGRES_PORT')
    POSTGRES_DB: str = os.environ.get('POSTGRES_DB')

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()