"""
Configurações da aplicação FastAPI usando Pydantic Settings
"""

import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Configurações principais da aplicação"""
    
    # Aplicação
    APP_NAME: str = "NE8000 Network Monitor"
    VERSION: str = "2.0.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    
    # Servidor
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8000, env="PORT")
    
    # Segurança
    SECRET_KEY: str = Field(default="your-secret-key-change-in-production", env="SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080", "*"],
        env="ALLOWED_ORIGINS"
    )
    
    # Router NE8000
    ROUTER_HOST: str = Field(default="192.168.1.1", env="ROUTER_HOST")
    ROUTER_PORT: int = Field(default=22, env="ROUTER_PORT")
    ROUTER_USERNAME: str = Field(default="admin", env="ROUTER_USERNAME")
    ROUTER_PASSWORD: str = Field(default="", env="ROUTER_PASSWORD")
    ROUTER_PROTOCOL: str = Field(default="ssh", env="ROUTER_PROTOCOL")  # ssh or telnet
    
    # Redis
    REDIS_HOST: str = Field(default="localhost", env="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, env="REDIS_PORT")
    REDIS_DB: int = Field(default=0, env="REDIS_DB")
    REDIS_PASSWORD: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    
    # Cache TTLs (seconds)
    CACHE_TTL_INTERFACES: int = 45
    CACHE_TTL_PPPOE_STATS: int = 20
    CACHE_TTL_SYSTEM_METRICS: int = 60
    CACHE_TTL_TRAFFIC_DATA: int = 30
    
    # Background Service
    BG_UPDATE_INTERVAL_INTERFACES: int = 30
    BG_UPDATE_INTERVAL_PPPOE: int = 15
    BG_UPDATE_INTERVAL_SYSTEM: int = 45
    BG_UPDATE_INTERVAL_TRAFFIC: int = 20
    
    # Timeouts
    ROUTER_CONNECTION_TIMEOUT: int = 8
    ROUTER_COMMAND_TIMEOUT: int = 12
    ROUTER_AUTH_TIMEOUT: int = 15
    
    # Rate Limiting (requests per minute)
    RATE_LIMIT_COMMANDS: int = 10
    RATE_LIMIT_DATA: int = 30
    RATE_LIMIT_DIAGNOSTICS: int = 5
    
    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30
    WS_MAX_CONNECTIONS: int = 100
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FILE: str = Field(default="logs/fastapi.log", env="LOG_FILE")
    LOG_ROTATION: str = "10 MB"
    LOG_RETENTION: str = "30 days"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Instância global das configurações
settings = Settings()


def get_database_url() -> str:
    """Constrói URL do Redis"""
    auth = f":{settings.REDIS_PASSWORD}@" if settings.REDIS_PASSWORD else ""
    return f"redis://{auth}{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"


def get_router_config() -> dict:
    """Retorna configuração do router"""
    return {
        "host": settings.ROUTER_HOST,
        "port": settings.ROUTER_PORT,
        "username": settings.ROUTER_USERNAME,
        "password": settings.ROUTER_PASSWORD,
        "protocol": settings.ROUTER_PROTOCOL,
        "timeouts": {
            "connection": settings.ROUTER_CONNECTION_TIMEOUT,
            "command": settings.ROUTER_COMMAND_TIMEOUT,
            "auth": settings.ROUTER_AUTH_TIMEOUT,
        }
    } 