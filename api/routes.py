"""
Rotas da API FastAPI - Migração completa do Flask
Implementa endpoints assíncronos com WebSocket broadcasting
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.websocket import websocket_manager
from core.config import settings
from services.async_router import AsyncRouterConnection
from services.async_cache import AsyncCache
from services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# =============================================================================
# ROUTER E DEPENDÊNCIAS
# =============================================================================

router = APIRouter()

# Instâncias globais
async_router = AsyncRouterConnection()
cache = AsyncCache()
rate_limiter = RateLimiter()

# =============================================================================
# MODELOS PYDANTIC
# =============================================================================

class CommandRequest(BaseModel):
    command: str
    timeout: Optional[int] = 30

class InterfaceCommandRequest(BaseModel):
    command: str
    action: str
    interface: str
    timeout: Optional[int] = 30

class RouterConnectRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None

# =============================================================================
# DEPENDÊNCIAS
# =============================================================================

async def get_router_connection():
    """Dependência para obter conexão com router"""
    if not async_router.is_connected():
        await async_router.connect()
    return async_router

# =============================================================================
# DECORADORES DE RATE LIMITING
# =============================================================================

async def check_rate_limit(endpoint: str, limit: int = 30):
    """Verifica rate limiting"""
    client_id = "default"  # Implementar identificação de cliente real
    
    if not await rate_limiter.is_allowed(client_id, endpoint, limit):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later."
        )

# =============================================================================
# ROTAS PRINCIPAIS DE DADOS
# =============================================================================

@router.get("/online_total")
async def get_online_total():
    """Obtém total de usuários online"""
    await check_rate_limit("data_retrieval", settings.RATE_LIMIT_DATA)
    
    try:
        # Tentar cache primeiro
        cached_data = await cache.get("pppoe_stats")
        if cached_data:
            return {
                "success": True,
                "online_total": cached_data.get("active", 0),
                "peak_users": cached_data.get("peak", 0),
                "cached": True,
                "timestamp": datetime.now().isoformat()
            }
        
        # Buscar dados frescos
        router_conn = await get_router_connection()
        stats = await router_conn.get_pppoe_stats()
        
        # Broadcast via WebSocket
        await websocket_manager.send_router_data({
            "type": "online_total",
            "data": stats
        })
        
        return {
            "success": True,
            "online_total": stats.get("active", 0),
            "peak_users": stats.get("peak", 0),
            "cached": False,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter total online: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/system_metrics")
async def get_system_metrics():
    """Obtém métricas do sistema"""
    await check_rate_limit("data_retrieval", settings.RATE_LIMIT_DATA)
    
    try:
        router_conn = await get_router_connection()
        metrics = await router_conn.get_system_metrics()
        
        # Broadcast via WebSocket
        await websocket_manager.send_router_data({
            "type": "system_metrics",
            "data": metrics
        })
        
        return {
            "success": True,
            "data": metrics,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter métricas: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/interfaces_status")
async def get_interfaces_status():
    """Obtém status das interfaces"""
    await check_rate_limit("data_retrieval", settings.RATE_LIMIT_DATA)
    
    try:
        router_conn = await get_router_connection()
        interfaces = await router_conn.get_interfaces()
        
        # Broadcast via WebSocket
        await websocket_manager.send_router_data({
            "type": "interfaces_status",
            "data": interfaces
        })
        
        return {
            "success": True,
            "interfaces": interfaces,
            "total": len(interfaces),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter interfaces: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/network_traffic")
async def get_network_traffic():
    """Obtém dados de tráfego de rede"""
    await check_rate_limit("data_retrieval", settings.RATE_LIMIT_DATA)
    
    try:
        router_conn = await get_router_connection()
        traffic_data = await router_conn.get_traffic_data()
        
        # Broadcast via WebSocket
        await websocket_manager.send_router_data({
            "type": "network_traffic",
            "data": traffic_data
        })
        
        return {
            "success": True,
            "traffic": traffic_data,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter tráfego: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pppoe_stats")
async def get_pppoe_stats():
    """Obtém estatísticas PPPoE detalhadas"""
    await check_rate_limit("data_retrieval", settings.RATE_LIMIT_DATA)
    
    try:
        router_conn = await get_router_connection()
        stats = await router_conn.get_pppoe_stats_detailed()
        
        # Broadcast via WebSocket
        await websocket_manager.send_router_data({
            "type": "pppoe_stats",
            "data": stats
        })
        
        return {
            "success": True,
            "stats": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter stats PPPoE: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# ROTAS DE COMANDO
# =============================================================================

@router.post("/execute_command")
async def execute_command(
    request: CommandRequest,
    background_tasks: BackgroundTasks
):
    """Executa comando no router"""
    await check_rate_limit("command_execution", settings.RATE_LIMIT_COMMANDS)
    
    try:
        router_conn = await get_router_connection()
        
        # Executar comando
        result = await router_conn.execute_command(
            request.command,
            timeout=request.timeout
        )
        
        # Log da ação em background
        background_tasks.add_task(
            log_command_execution,
            request.command,
            True,
            result
        )
        
        # Broadcast resultado via WebSocket
        await websocket_manager.send_router_data({
            "type": "command_result",
            "command": request.command,
            "result": result
        })
        
        return {
            "success": True,
            "command": request.command,
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao executar comando: {e}")
        
        # Log da falha em background
        background_tasks.add_task(
            log_command_execution,
            request.command,
            False,
            str(e)
        )
        
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/interface_command")
async def interface_command(
    request: InterfaceCommandRequest,
    background_tasks: BackgroundTasks
):
    """Executa comando em interface específica"""
    await check_rate_limit("command_execution", settings.RATE_LIMIT_COMMANDS)
    
    try:
        router_conn = await get_router_connection()
        
        # Montar comando específico da interface
        full_command = f"interface {request.interface}\n{request.command}"
        
        result = await router_conn.execute_command(
            full_command,
            timeout=request.timeout
        )
        
        # Log da ação em background
        background_tasks.add_task(
            log_interface_action,
            request.action,
            request.interface,
            "system",  # Implementar usuário real
            True,
            result
        )
        
        # Broadcast resultado via WebSocket
        await websocket_manager.send_router_data({
            "type": "interface_command_result",
            "interface": request.interface,
            "action": request.action,
            "result": result
        })
        
        return {
            "success": True,
            "interface": request.interface,
            "action": request.action,
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao executar comando de interface: {e}")
        
        # Log da falha em background
        background_tasks.add_task(
            log_interface_action,
            request.action,
            request.interface,
            "system",
            False,
            str(e)
        )
        
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# ROTAS DE CONEXÃO E DIAGNÓSTICO
# =============================================================================

@router.post("/router_connect")
async def router_connect(request: RouterConnectRequest = None):
    """Conecta ao router"""
    await check_rate_limit("diagnostics", settings.RATE_LIMIT_DIAGNOSTICS)
    
    try:
        # Usar configurações do request ou padrão
        config = {}
        if request:
            if request.host:
                config['host'] = request.host
            if request.port:
                config['port'] = request.port
            if request.username:
                config['username'] = request.username
            if request.password:
                config['password'] = request.password
        
        # Conectar
        success = await async_router.connect(config)
        
        if success:
            # Broadcast conexão via WebSocket
            await websocket_manager.send_system_status({
                "router_connected": True,
                "connection_time": datetime.now().isoformat()
            })
            
            return {
                "success": True,
                "message": "Conectado ao router com sucesso",
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Falha na conexão")
            
    except Exception as e:
        logger.error(f"Erro ao conectar router: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/router_disconnect")
async def router_disconnect():
    """Desconecta do router"""
    try:
        await async_router.disconnect()
        
        # Broadcast desconexão via WebSocket
        await websocket_manager.send_system_status({
            "router_connected": False,
            "disconnection_time": datetime.now().isoformat()
        })
        
        return {
            "success": True,
            "message": "Desconectado do router",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao desconectar router: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/router_status")
async def get_router_status():
    """Obtém status da conexão com router"""
    try:
        is_connected = async_router.is_connected()
        connection_info = await async_router.get_connection_info()
        
        return {
            "success": True,
            "connected": is_connected,
            "connection_info": connection_info,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter status do router: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/router_diagnostics")
async def router_diagnostics():
    """Executa diagnósticos do router"""
    await check_rate_limit("diagnostics", settings.RATE_LIMIT_DIAGNOSTICS)
    
    try:
        router_conn = await get_router_connection()
        diagnostics = await router_conn.run_diagnostics()
        
        return {
            "success": True,
            "diagnostics": diagnostics,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro nos diagnósticos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# ROTAS DE CACHE E SISTEMA
# =============================================================================

@router.post("/force_cache_refresh")
async def force_cache_refresh():
    """Força atualização do cache"""
    try:
        await cache.clear()
        
        # Recarregar dados principais
        router_conn = await get_router_connection()
        
        # Executar coletas em paralelo
        tasks = [
            router_conn.get_interfaces(),
            router_conn.get_pppoe_stats(),
            router_conn.get_system_metrics()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            "success": True,
            "message": "Cache atualizado com sucesso",
            "data_collected": len([r for r in results if not isinstance(r, Exception)]),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao atualizar cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clear_cache")
async def clear_cache():
    """Limpa o cache"""
    try:
        await cache.clear()
        
        return {
            "success": True,
            "message": "Cache limpo com sucesso",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao limpar cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cache_statistics")
async def get_cache_statistics():
    """Obtém estatísticas do cache"""
    try:
        stats = await cache.get_stats()
        
        return {
            "success": True,
            "cache_stats": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas do cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/websocket_stats")
async def get_websocket_stats():
    """Obtém estatísticas das conexões WebSocket"""
    try:
        stats = websocket_manager.get_connection_stats()
        
        return {
            "success": True,
            "websocket_stats": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas WebSocket: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

async def log_command_execution(command: str, success: bool, result: str):
    """Log de execução de comando"""
    logger.info(f"Comando executado: {command} | Sucesso: {success} | Resultado: {result[:100]}...")

async def log_interface_action(action: str, interface: str, user: str, success: bool, details: str):
    """Log de ação em interface"""
    logger.info(f"Ação na interface: {action} | Interface: {interface} | Usuário: {user} | Sucesso: {success}")

@router.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()} 