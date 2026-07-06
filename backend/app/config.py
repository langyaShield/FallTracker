from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./falltracker.db"
    SECRET_KEY: str = "change-me-to-a-random-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    REDIS_URL: str = "redis://localhost:6379/0"
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-chat"
    # 固定 API KEY 认证（供 Hermes 等 MCP 客户端使用，无需动态登录获取 JWT）
    MCP_API_KEY: str = ""
    MCP_API_USER_ID: int = 1
    CORS_ORIGINS: str = "*"  # Comma-separated origins, e.g. "http://localhost:5173,http://localhost:3000"

    class Config:
        import os
        _local_env = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        env_file = _local_env if os.path.isfile(_local_env) else "/app/backend/.env"

    @property
    def cors_origins_list(self) -> List[str]:
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

settings = Settings()
