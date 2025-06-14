"""
Serviço de Rate Limiting para APIs
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, DefaultDict
from collections import defaultdict

logger = logging.getLogger(__name__)

class RateLimiter:
    """Rate limiter em memória com sliding window"""
    
    def __init__(self):
        # Armazena timestamps de requisições por cliente/endpoint
        self.requests: DefaultDict[str, list] = defaultdict(list)
        self.cleanup_task = None
        self._start_cleanup()
    
    def _start_cleanup(self):
        """Inicia task de limpeza periódica"""
        if not self.cleanup_task or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def _cleanup_loop(self):
        """Loop de limpeza de dados antigos"""
        while True:
            try:
                await asyncio.sleep(60)  # Limpar a cada minuto
                await self._cleanup_old_requests()
            except Exception as e:
                logger.error(f"Erro na limpeza do rate limiter: {e}")
    
    async def _cleanup_old_requests(self):
        """Remove requisições antigas"""
        cutoff = datetime.now() - timedelta(minutes=10)
        
        for key in list(self.requests.keys()):
            # Filtrar apenas requisições dos últimos 10 minutos
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if req_time > cutoff
            ]
            
            # Remover chaves vazias
            if not self.requests[key]:
                del self.requests[key]
    
    async def is_allowed(self, client_id: str, endpoint: str, limit: int, window_minutes: int = 1) -> bool:
        """
        Verifica se a requisição é permitida
        
        Args:
            client_id: Identificador do cliente
            endpoint: Nome do endpoint
            limit: Número máximo de requisições
            window_minutes: Janela de tempo em minutos
        """
        now = datetime.now()
        key = f"{client_id}:{endpoint}"
        
        # Obter requisições dentro da janela de tempo
        window_start = now - timedelta(minutes=window_minutes)
        recent_requests = [
            req_time for req_time in self.requests[key]
            if req_time > window_start
        ]
        
        # Verificar se excede o limite
        if len(recent_requests) >= limit:
            logger.warning(f"Rate limit excedido para {key}: {len(recent_requests)}/{limit}")
            return False
        
        # Adicionar requisição atual
        self.requests[key].append(now)
        
        return True
    
    def get_stats(self) -> Dict:
        """Obtém estatísticas do rate limiter"""
        total_clients = len(self.requests)
        total_requests = sum(len(reqs) for reqs in self.requests.values())
        
        return {
            "total_clients": total_clients,
            "total_tracked_requests": total_requests,
            "active_keys": list(self.requests.keys())[:10]  # Apenas os 10 primeiros
        } 