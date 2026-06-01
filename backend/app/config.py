from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./falltracker.db"
    SECRET_KEY: str = "change-me-to-a-random-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    REDIS_URL: str = "redis://localhost:6379/0"
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-chat"

    class Config:
        env_file = ".env"

settings = Settings()
