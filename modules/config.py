"""
Módulo de configurações centralizadas
"""

import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

def setup_logging():
    """Configurar sistema de logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def load_environment():
    """Carregar variáveis de ambiente"""
    load_dotenv()

def create_app():
    """Criar e configurar aplicação FastAPI"""
    app = FastAPI(title="NE8000 Simple Monitor v2", version="2.0.0")
    
    # Middleware CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Middleware de sessão
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.getenv("SECRET_KEY", "your-secret-key-here-change-this")
    )
    
    # Servir arquivos estáticos
    app.mount("/static", StaticFiles(directory="static"), name="static")
    
    return app

# Configurações do sistema
CACHE_TIMEOUTS = {
    "pppoe_stats": 30,          # 30 segundos
    "interfaces": 60,           # 1 minuto  
    "system_metrics": 45,       # 45 segundos
    "pppoe_user": 30,           # 30 segundos
    "pppoe_interfaces": 60,     # 1 minuto
    "pppoe_user_detailed": 60,  # 1 minuto
}

# Comandos do sistema
SYSTEM_COMMANDS = {
    "pppoe_total": "display access-user slot 0 brief | include Total users",
    "interfaces": "display interface brief", 
    "cpu_usage": "display cpu-usage",
    "memory_usage": "display memory-usage",
    "system_info": "display system",
    "device_info": "display device"
}

# Configurações SSH
SSH_CONFIG = {
    "timeout": 10,
    "command_timeout": 12,
    "shell_timeout": 10,
    "retry_attempts": 3
} 