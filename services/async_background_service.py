"""
Serviço de background assíncrono para coleta contínua de dados
Versão otimizada com WebSocket broadcasting
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from services.async_router import AsyncRouterConnection
from services.async_cache import AsyncCache
from api.websocket import websocket_manager
from core.config import settings

logger = logging.getLogger(__name__)

class AsyncBackgroundService:
    """Serviço de background assíncrono para monitoramento contínuo"""
    
    def __init__(self):
        self.is_running = False
        self.router = AsyncRouterConnection()
        self.cache = AsyncCache()
        
        # Tasks de coleta
        self.collection_tasks: List[asyncio.Task] = []
        
        # Controle de intervalos
        self.intervals = {
            "interfaces": settings.BG_UPDATE_INTERVAL_INTERFACES,
            "pppoe_stats": settings.BG_UPDATE_INTERVAL_PPPOE,
            "system_metrics": settings.BG_UPDATE_INTERVAL_SYSTEM,
            "traffic_data": settings.BG_UPDATE_INTERVAL_TRAFFIC
        }
        
        # Última atualização
        self.last_update: Optional[datetime] = None
        self.last_updates = {key: datetime.min for key in self.intervals.keys()}
        
        # Estatísticas
        self.stats = {
            "collections": 0,
            "errors": 0,
            "start_time": None
        }
    
    async def start(self):
        """Inicia o serviço de background"""
        if self.is_running:
            logger.warning("⚠️ Serviço de background já está rodando")
            return
        
        try:
            # Inicializar dependências
            await self.cache.connect()
            await self.router.initialize()
            
            self.is_running = True
            self.stats["start_time"] = datetime.now()
            
            # Iniciar tasks de coleta
            await self._start_collection_tasks()
            
            logger.info("🚀 Serviço de background assíncrono iniciado")
            
        except Exception as e:
            logger.error(f"❌ Erro ao iniciar serviço de background: {e}")
            self.is_running = False
            raise
    
    async def stop(self):
        """Para o serviço de background"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # Cancelar todas as tasks
        for task in self.collection_tasks:
            if not task.done():
                task.cancel()
        
        # Aguardar cancelamento
        if self.collection_tasks:
            await asyncio.gather(*self.collection_tasks, return_exceptions=True)
        
        # Fechar conexões
        await self.router.disconnect()
        
        logger.info("🛑 Serviço de background parado")
    
    async def _start_collection_tasks(self):
        """Inicia as tasks de coleta de dados"""
        # Task principal de controle
        self.collection_tasks.append(
            asyncio.create_task(self._main_collection_loop())
        )
        
        # Task de limpeza de cache
        self.collection_tasks.append(
            asyncio.create_task(self._cache_cleanup_loop())
        )
        
        # Task de broadcast de status
        self.collection_tasks.append(
            asyncio.create_task(self._status_broadcast_loop())
        )
    
    async def _main_collection_loop(self):
        """Loop principal de coleta de dados"""
        logger.info("🔄 Iniciando loop de coleta de dados")
        
        # Coleta inicial
        await self._initial_data_collection()
        
        while self.is_running:
            try:
                current_time = datetime.now()
                
                # Verificar quais dados precisam ser atualizados
                update_tasks = []
                
                for data_type, interval in self.intervals.items():
                    last_update = self.last_updates[data_type]
                    if (current_time - last_update).total_seconds() >= interval:
                        update_tasks.append(self._collect_data_type(data_type))
                        self.last_updates[data_type] = current_time
                
                # Executar coletas em paralelo
                if update_tasks:
                    results = await asyncio.gather(*update_tasks, return_exceptions=True)
                    
                    # Contar sucessos/erros
                    for result in results:
                        if isinstance(result, Exception):
                            self.stats["errors"] += 1
                            logger.error(f"Erro na coleta: {result}")
                        else:
                            self.stats["collections"] += 1
                    
                    self.last_update = current_time
                
                # Aguardar antes da próxima verificação
                await asyncio.sleep(5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Erro no loop principal: {e}")
                await asyncio.sleep(10)
        
        logger.info("🔄 Loop de coleta finalizado")
    
    async def _initial_data_collection(self):
        """Coleta inicial de dados para popular o cache"""
        logger.info("📊 Executando coleta inicial de dados...")
        
        try:
            # Verificar se router está acessível
            if not self.router.is_connected():
                await self.router.connect()
            
            if not self.router.is_connected():
                logger.warning("⚠️ Router não acessível - usando dados de fallback")
                await self._set_fallback_data()
                return
            
            # Coletar todos os tipos de dados em paralelo
            tasks = [
                self._collect_data_type(data_type)
                for data_type in self.intervals.keys()
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            successful = sum(1 for r in results if not isinstance(r, Exception))
            logger.info(f"✅ Coleta inicial concluída: {successful}/{len(tasks)} sucessos")
            
        except Exception as e:
            logger.error(f"❌ Erro na coleta inicial: {e}")
            await self._set_fallback_data()
    
    async def _collect_data_type(self, data_type: str):
        """Coleta um tipo específico de dados"""
        try:
            logger.debug(f"📊 Coletando {data_type}...")
            
            if data_type == "interfaces":
                data = await self.router.get_interfaces()
                await self.cache.set("interfaces", data, settings.CACHE_TTL_INTERFACES)
                
                # Broadcast via WebSocket
                await websocket_manager.send_router_data({
                    "type": "interfaces_update",
                    "data": data
                })
                
            elif data_type == "pppoe_stats":
                data = await self.router.get_pppoe_stats()
                await self.cache.set("pppoe_stats", data, settings.CACHE_TTL_PPPOE_STATS)
                
                # Broadcast via WebSocket
                await websocket_manager.send_router_data({
                    "type": "pppoe_update",
                    "data": data
                })
                
            elif data_type == "system_metrics":
                data = await self.router.get_system_metrics()
                await self.cache.set("system_metrics", data, settings.CACHE_TTL_SYSTEM_METRICS)
                
                # Broadcast via WebSocket
                await websocket_manager.send_router_data({
                    "type": "system_metrics_update",
                    "data": data
                })
                
            elif data_type == "traffic_data":
                data = await self.router.get_traffic_data()
                await self.cache.set("traffic_data", data, settings.CACHE_TTL_TRAFFIC_DATA)
                
                # Broadcast via WebSocket
                await websocket_manager.send_router_data({
                    "type": "traffic_update",
                    "data": data
                })
            
            logger.debug(f"✅ {data_type} coletado com sucesso")
            
        except Exception as e:
            logger.error(f"❌ Erro ao coletar {data_type}: {e}")
            raise
    
    async def _set_fallback_data(self):
        """Define dados de fallback quando router não está acessível"""
        fallback_data = {
            "interfaces": [],
            "pppoe_stats": {"active": 0, "peak": 0},
            "system_metrics": {"cpu": 0, "memory": 0, "uptime": "Unknown"},
            "traffic_data": {"total_in": 0, "total_out": 0, "interfaces": []}
        }
        
        for key, data in fallback_data.items():
            await self.cache.set(key, data, 300)  # Cache por 5 minutos
        
        logger.info("📝 Dados de fallback definidos")
    
    async def _cache_cleanup_loop(self):
        """Loop de limpeza do cache"""
        while self.is_running:
            try:
                await asyncio.sleep(300)  # A cada 5 minutos
                
                # Limpar cache expirado
                # (implementação específica depende do cache usado)
                
                logger.debug("🧹 Limpeza de cache executada")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro na limpeza de cache: {e}")
    
    async def _status_broadcast_loop(self):
        """Loop de broadcast de status do sistema"""
        while self.is_running:
            try:
                await asyncio.sleep(30)  # A cada 30 segundos
                
                # Broadcast status do sistema
                status = {
                    "background_service": {
                        "running": self.is_running,
                        "last_update": self.last_update.isoformat() if self.last_update else None,
                        "collections": self.stats["collections"],
                        "errors": self.stats["errors"],
                        "uptime": str(datetime.now() - self.stats["start_time"]) if self.stats["start_time"] else None
                    },
                    "router": {
                        "connected": self.router.is_connected()
                    },
                    "cache": await self.cache.get_stats()
                }
                
                await websocket_manager.send_system_status(status)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Erro no broadcast de status: {e}")
    
    def get_status(self) -> Dict:
        """Obtém status atual do serviço"""
        uptime = None
        if self.stats["start_time"]:
            uptime = str(datetime.now() - self.stats["start_time"])
        
        return {
            "running": self.is_running,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "collections": self.stats["collections"],
            "errors": self.stats["errors"],
            "uptime": uptime,
            "router_connected": self.router.is_connected(),
            "active_tasks": len([t for t in self.collection_tasks if not t.done()]),
            "intervals": self.intervals
        } 