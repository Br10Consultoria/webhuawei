"""
Gerenciador de WebSocket para comunicação em tempo real
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set
from fastapi import WebSocket, WebSocketDisconnect
from core.config import settings

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Gerenciador centralizado de conexões WebSocket"""
    
    def __init__(self):
        # Conexões ativas por canal
        self.connections: Dict[str, Set[WebSocket]] = {
            "default": set(),
            "router_data": set(),
            "system_status": set(),
            "alerts": set()
        }
        
        # Metadados das conexões
        self.connection_metadata: Dict[WebSocket, Dict] = {}
        
        # Lock para operações thread-safe
        self._lock = asyncio.Lock()
        
        # Task de heartbeat
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._start_heartbeat()
    
    def _start_heartbeat(self):
        """Inicia o heartbeat para manter conexões vivas"""
        if not self._heartbeat_task or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    async def _heartbeat_loop(self):
        """Loop de heartbeat para verificar conexões"""
        while True:
            try:
                await asyncio.sleep(settings.WS_HEARTBEAT_INTERVAL)
                await self._send_heartbeat()
            except Exception as e:
                logger.error(f"Erro no heartbeat: {e}")
    
    async def _send_heartbeat(self):
        """Envia heartbeat para todas as conexões"""
        if not any(self.connections.values()):
            return
        
        heartbeat_data = {
            "type": "heartbeat",
            "timestamp": datetime.now().isoformat(),
            "server_time": datetime.now().strftime("%H:%M:%S")
        }
        
        await self.broadcast_to_all(heartbeat_data)
    
    async def connect(self, websocket: WebSocket, channel: str = "default"):
        """Conecta um WebSocket a um canal específico"""
        await websocket.accept()
        
        async with self._lock:
            # Verificar limite de conexões
            total_connections = sum(len(conns) for conns in self.connections.values())
            if total_connections >= settings.WS_MAX_CONNECTIONS:
                await websocket.close(code=1008, reason="Too many connections")
                return False
            
            # Adicionar ao canal
            if channel not in self.connections:
                self.connections[channel] = set()
            
            self.connections[channel].add(websocket)
            
            # Armazenar metadados
            self.connection_metadata[websocket] = {
                "channel": channel,
                "connected_at": datetime.now(),
                "last_activity": datetime.now(),
                "client_info": websocket.client if websocket.client else None
            }
            
            logger.info(f"WebSocket conectado ao canal '{channel}'. Total: {len(self.connections[channel])}")
            
            # Enviar mensagem de boas-vindas
            await self._send_welcome_message(websocket, channel)
            
            return True
    
    async def disconnect(self, websocket: WebSocket, channel: str = None):
        """Desconecta um WebSocket"""
        async with self._lock:
            # Se canal não especificado, encontrar o canal da conexão
            if not channel and websocket in self.connection_metadata:
                channel = self.connection_metadata[websocket]["channel"]
            
            # Remover da lista de conexões
            if channel and channel in self.connections:
                self.connections[channel].discard(websocket)
                logger.info(f"WebSocket desconectado do canal '{channel}'. Restantes: {len(self.connections[channel])}")
            
            # Remover metadados
            self.connection_metadata.pop(websocket, None)
            
            # Fechar conexão se ainda estiver aberta
            try:
                if websocket.client_state.value == 1:  # CONNECTED
                    await websocket.close()
            except Exception as e:
                logger.debug(f"Erro ao fechar WebSocket: {e}")
    
    async def disconnect_all(self):
        """Desconecta todos os WebSockets"""
        async with self._lock:
            for channel, connections in self.connections.items():
                for websocket in connections.copy():
                    await self.disconnect(websocket, channel)
            
            # Cancelar heartbeat
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
            
            logger.info("Todas as conexões WebSocket foram fechadas")
    
    async def _send_welcome_message(self, websocket: WebSocket, channel: str):
        """Envia mensagem de boas-vindas para nova conexão"""
        welcome_data = {
            "type": "welcome",
            "channel": channel,
            "timestamp": datetime.now().isoformat(),
            "message": f"Conectado ao canal {channel}",
            "server_info": {
                "version": settings.VERSION,
                "heartbeat_interval": settings.WS_HEARTBEAT_INTERVAL
            }
        }
        
        await self._send_safe(websocket, welcome_data)
    
    async def _send_safe(self, websocket: WebSocket, data: dict):
        """Envia dados para um WebSocket com tratamento de erro"""
        try:
            await websocket.send_json(data)
            
            # Atualizar última atividade
            if websocket in self.connection_metadata:
                self.connection_metadata[websocket]["last_activity"] = datetime.now()
                
        except WebSocketDisconnect:
            await self.disconnect(websocket)
        except Exception as e:
            logger.error(f"Erro ao enviar dados via WebSocket: {e}")
            await self.disconnect(websocket)
    
    async def send_to_channel(self, channel: str, data: dict):
        """Envia dados para todas as conexões de um canal"""
        if channel not in self.connections:
            return
        
        connections = self.connections[channel].copy()
        if not connections:
            return
        
        # Adicionar metadados
        data.update({
            "channel": channel,
            "timestamp": datetime.now().isoformat()
        })
        
        # Enviar para todas as conexões do canal
        tasks = []
        for websocket in connections:
            tasks.append(self._send_safe(websocket, data))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def broadcast_to_all(self, data: dict):
        """Envia dados para todas as conexões ativas"""
        tasks = []
        for channel in self.connections:
            if self.connections[channel]:
                tasks.append(self.send_to_channel(channel, data.copy()))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def send_router_data(self, data: dict):
        """Envia dados específicos do router"""
        router_data = {
            "type": "router_data",
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        await self.send_to_channel("router_data", router_data)
    
    async def send_system_status(self, status: dict):
        """Envia status do sistema"""
        status_data = {
            "type": "system_status",
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        await self.send_to_channel("system_status", status_data)
    
    async def send_alert(self, alert: dict):
        """Envia alerta"""
        alert_data = {
            "type": "alert",
            "alert": alert,
            "timestamp": datetime.now().isoformat()
        }
        await self.send_to_channel("alerts", alert_data)
    
    def get_connection_count(self, channel: str = None) -> int:
        """Retorna número de conexões ativas"""
        if channel:
            return len(self.connections.get(channel, set()))
        return sum(len(conns) for conns in self.connections.values())
    
    def get_connection_stats(self) -> dict:
        """Retorna estatísticas das conexões"""
        stats = {
            "total_connections": self.get_connection_count(),
            "channels": {},
            "oldest_connection": None,
            "newest_connection": None
        }
        
        # Estatísticas por canal
        for channel, connections in self.connections.items():
            stats["channels"][channel] = len(connections)
        
        # Conexão mais antiga e mais nova
        if self.connection_metadata:
            connect_times = [meta["connected_at"] for meta in self.connection_metadata.values()]
            stats["oldest_connection"] = min(connect_times).isoformat()
            stats["newest_connection"] = max(connect_times).isoformat()
        
        return stats


# Instância global do gerenciador
websocket_manager = WebSocketManager() 