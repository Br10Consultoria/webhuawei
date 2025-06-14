"""
FastAPI Application Principal - Sistema de Monitoramento NE8000
Migração completa de Flask para FastAPI com WebSockets para monitoramento em tempo real
"""

import asyncio
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api.routes import router as api_router
from api.websocket import websocket_manager
from core.config import settings
from core.logging import setup_logging
from services.async_background_service import AsyncBackgroundService
from services.async_router import AsyncRouterConnection

# =============================================================================
# CONFIGURAÇÃO DE LOGGING
# =============================================================================

setup_logging()
logger = logging.getLogger(__name__)

# =============================================================================
# SERVIÇO DE BACKGROUND GLOBAL
# =============================================================================

background_service: Optional[AsyncBackgroundService] = None

# =============================================================================
# LIFESPAN EVENTS
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação FastAPI"""
    global background_service
    
    logger.info("🚀 Iniciando aplicação FastAPI NE8000 Monitor")
    
    # Startup
    try:
        # Inicializar serviço de background
        background_service = AsyncBackgroundService()
        await background_service.start()
        logger.info("✅ Serviço de background iniciado com sucesso")
        
        # Inicializar conexão com router
        router_connection = AsyncRouterConnection()
        await router_connection.initialize()
        logger.info("✅ Conexão com router inicializada")
        
    except Exception as e:
        logger.error(f"❌ Erro na inicialização: {e}")
        # Continua execução mesmo com falhas
    
    yield
    
    # Shutdown
    logger.info("🔄 Parando aplicação...")
    
    if background_service:
        await background_service.stop()
        logger.info("✅ Serviço de background parado")
    
    # Fechar conexões WebSocket
    await websocket_manager.disconnect_all()
    logger.info("✅ Conexões WebSocket fechadas")
    
    logger.info("👋 Aplicação parada graciosamente")

# =============================================================================
# CRIAÇÃO DA APLICAÇÃO FASTAPI
# =============================================================================

app = FastAPI(
    title="NE8000 Network Monitor",
    description="Sistema de monitoramento de rede em tempo real com WebSockets",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# =============================================================================
# CONFIGURAÇÃO DE MIDDLEWARE
# =============================================================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# =============================================================================
# ARQUIVOS ESTÁTICOS E TEMPLATES
# =============================================================================

# Servir arquivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates Jinja2
templates = Jinja2Templates(directory="templates")

# =============================================================================
# ROTAS PRINCIPAIS
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Página principal do dashboard"""
    return templates.TemplateResponse("dashboard.html", {"request": {}})

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "background_service": background_service.is_running if background_service else False
    }

# =============================================================================
# WEBSOCKET ENDPOINTS
# =============================================================================

@app.websocket("/ws/monitor")
async def websocket_monitor(websocket: WebSocket):
    """WebSocket principal para monitoramento em tempo real"""
    await websocket_manager.connect(websocket)
    
    try:
        while True:
            # Receber mensagens do cliente
            data = await websocket.receive_text()
            logger.debug(f"WebSocket recebeu: {data}")
            
            # Processar comandos específicos se necessário
            if data == "ping":
                await websocket.send_text("pong")
            elif data == "get_status":
                status = await get_system_status()
                await websocket.send_json(status)
                
    except WebSocketDisconnect:
        logger.info("Cliente WebSocket desconectado")
    except Exception as e:
        logger.error(f"Erro no WebSocket: {e}")
    finally:
        await websocket_manager.disconnect(websocket)

@app.websocket("/ws/router")
async def websocket_router_data(websocket: WebSocket):
    """WebSocket específico para dados do router"""
    await websocket_manager.connect(websocket, channel="router_data")
    
    try:
        while True:
            await asyncio.sleep(1)  # Manter conexão viva
            
    except WebSocketDisconnect:
        logger.info("Cliente WebSocket router desconectado")
    except Exception as e:
        logger.error(f"Erro no WebSocket router: {e}")
    finally:
        await websocket_manager.disconnect(websocket, channel="router_data")

# =============================================================================
# INCLUIR ROTAS DA API
# =============================================================================

app.include_router(api_router, prefix="/api", tags=["api"])

# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

async def get_system_status() -> Dict:
    """Obtém status geral do sistema"""
    return {
        "timestamp": datetime.now().isoformat(),
        "background_service": {
            "running": background_service.is_running if background_service else False,
            "last_update": background_service.last_update.isoformat() if background_service and background_service.last_update else None
        },
        "websocket_connections": websocket_manager.get_connection_count(),
        "router_status": "connected"  # Implementar verificação real
    }

# =============================================================================
# HANDLERS DE SINAL
# =============================================================================

def signal_handler(signum, frame):
    """Handler para sinais de sistema"""
    logger.info(f"Recebido sinal {signum}, parando aplicação...")
    sys.exit(0)

# Registrar handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# =============================================================================
# EXECUÇÃO PRINCIPAL
# =============================================================================

if __name__ == "__main__":
    logger.info("🚀 Iniciando servidor FastAPI...")
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if not settings.DEBUG else "debug",
        access_log=True,
        server_header=False,
        date_header=False
    ) 