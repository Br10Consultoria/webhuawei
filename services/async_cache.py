"""
Serviço de cache assíncrono usando Redis
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional, Dict

import aioredis
from core.config import settings, get_database_url

logger = logging.getLogger(__name__)

class AsyncCache:
    """Cache assíncrono com Redis"""
    
    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self.memory_cache: Dict[str, Dict] = {}
        self.connected = False
    
    async def connect(self):
        """Conecta ao Redis"""
        try:
            self.redis = aioredis.from_url(
                get_database_url(),
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5
            )
            
            # Testar conexão
            await self.redis.ping()
            self.connected = True
            logger.info("✅ Conectado ao Redis")
            
        except Exception as e:
            logger.warning(f"⚠️ Falha na conexão Redis: {e}. Usando cache em memória.")
            self.connected = False
    
    async def get(self, key: str) -> Optional[Any]:
        """Obtém valor do cache"""
        try:
            # Tentar Redis primeiro
            if self.connected and self.redis:
                data = await self.redis.get(key)
                if data:
                    return json.loads(data)
            
            # Fallback para cache em memória
            if key in self.memory_cache:
                entry = self.memory_cache[key]
                if datetime.now() < entry['expires']:
                    return entry['data']
                else:
                    del self.memory_cache[key]
            
            return None
            
        except Exception as e:
            logger.error(f"Erro ao obter do cache: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 60):
        """Define valor no cache"""
        try:
            # Serializar dados
            data = json.dumps(value, default=str)
            
            # Tentar Redis
            if self.connected and self.redis:
                await self.redis.setex(key, ttl, data)
            
            # Cache em memória como backup
            self.memory_cache[key] = {
                'data': value,
                'expires': datetime.now() + timedelta(seconds=ttl)
            }
            
        except Exception as e:
            logger.error(f"Erro ao definir cache: {e}")
    
    async def clear(self, pattern: str = None):
        """Limpa o cache"""
        try:
            if self.connected and self.redis:
                if pattern:
                    keys = await self.redis.keys(pattern)
                    if keys:
                        await self.redis.delete(*keys)
                else:
                    await self.redis.flushdb()
            
            # Limpar cache em memória
            if pattern:
                keys_to_remove = [k for k in self.memory_cache.keys() if pattern in k]
                for key in keys_to_remove:
                    del self.memory_cache[key]
            else:
                self.memory_cache.clear()
                
        except Exception as e:
            logger.error(f"Erro ao limpar cache: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Obtém estatísticas do cache"""
        stats = {
            "redis_connected": self.connected,
            "memory_cache_keys": len(self.memory_cache),
            "redis_keys": 0
        }
        
        try:
            if self.connected and self.redis:
                info = await self.redis.info()
                stats["redis_keys"] = info.get("db0", {}).get("keys", 0)
                stats["redis_memory"] = info.get("used_memory_human", "Unknown")
        except:
            pass
        
        return stats 