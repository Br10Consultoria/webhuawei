"""
Módulo de gerenciamento de cache em memória
"""

import time
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class MemoryCache:
    """Cache simples em memória com TTL"""
    
    def __init__(self):
        self.cache: Dict[str, Any] = {}
        self.timestamps: Dict[str, float] = {}
        logger.debug("Cache inicializado")
    
    def get(self, key: str, ttl_seconds: int = 30) -> Optional[Any]:
        """
        Obter dados do cache com TTL
        
        Args:
            key: Chave do cache
            ttl_seconds: Tempo de vida em segundos
            
        Returns:
            Dados do cache ou None se expirado/inexistente
        """
        if key in self.cache:
            timestamp = self.timestamps.get(key, 0)
            if time.time() - timestamp < ttl_seconds:
                logger.debug(f"Cache hit: {key}")
                return self.cache[key]
            else:
                # Cache expirado, remover
                self.remove(key)
                logger.debug(f"Cache expired: {key}")
        
        logger.debug(f"Cache miss: {key}")
        return None
    
    def set(self, key: str, data: Any) -> None:
        """
        Armazenar dados no cache
        
        Args:
            key: Chave do cache
            data: Dados a serem armazenados
        """
        self.cache[key] = data
        self.timestamps[key] = time.time()
        logger.debug(f"Cache set: {key}")
    
    def remove(self, key: str) -> None:
        """
        Remover item do cache
        
        Args:
            key: Chave do cache
        """
        self.cache.pop(key, None)
        self.timestamps.pop(key, None)
        logger.debug(f"Cache removed: {key}")
    
    def clear(self) -> None:
        """Limpar todo o cache"""
        self.cache.clear()
        self.timestamps.clear()
        logger.info("Cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Obter estatísticas do cache
        
        Returns:
            Estatísticas do cache
        """
        current_time = time.time()
        active_items = 0
        expired_items = 0
        
        for key, timestamp in self.timestamps.items():
            if current_time - timestamp < 300:  # 5 minutos
                active_items += 1
            else:
                expired_items += 1
        
        return {
            "total_items": len(self.cache),
            "active_items": active_items,
            "expired_items": expired_items,
            "memory_usage_mb": self._estimate_memory_usage()
        }
    
    def cleanup_expired(self, max_age_seconds: int = 300) -> int:
        """
        Limpar itens expirados do cache
        
        Args:
            max_age_seconds: Idade máxima em segundos
            
        Returns:
            Número de itens removidos
        """
        current_time = time.time()
        expired_keys = []
        
        for key, timestamp in self.timestamps.items():
            if current_time - timestamp > max_age_seconds:
                expired_keys.append(key)
        
        for key in expired_keys:
            self.remove(key)
        
        if expired_keys:
            logger.info(f"Cleanup: removidos {len(expired_keys)} itens expirados")
        
        return len(expired_keys)
    
    def _estimate_memory_usage(self) -> float:
        """
        Estimar uso de memória em MB (aproximado)
        
        Returns:
            Uso estimado de memória em MB
        """
        try:
            import sys
            total_size = 0
            for key, value in self.cache.items():
                total_size += sys.getsizeof(key) + sys.getsizeof(value)
            return round(total_size / (1024 * 1024), 2)
        except:
            return 0.0

# Instância global do cache
_cache_instance: Optional[MemoryCache] = None

def get_cache() -> MemoryCache:
    """Obter instância global do cache (singleton)"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = MemoryCache()
    return _cache_instance

# Funções de conveniência para compatibilidade
def get_cached_data(key: str, ttl_seconds: int = 30) -> Optional[Any]:
    """Obter dados do cache (função compatível)"""
    return get_cache().get(key, ttl_seconds)

def set_cached_data(key: str, data: Any) -> None:
    """Armazenar dados no cache (função compatível)"""
    get_cache().set(key, data) 