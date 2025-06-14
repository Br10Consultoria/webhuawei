"""
Sistema de cache inteligente para dados do router NE8000.
"""

import json
import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import redis

from .utils import CACHE_TTLS


class SmartCache:
    """Cache inteligente com fallback Redis -> Memória -> Nenhum."""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.memory_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'redis_hits': 0,
            'memory_hits': 0,
        }
        self._lock = threading.RLock()
        
        self._initialize_redis()
    
    def _initialize_redis(self) -> None:
        """Inicializa conexão Redis com configurações otimizadas."""
        try:
            self.redis_client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'redis'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                db=int(os.getenv('REDIS_DB', 0)),
                decode_responses=True,
                socket_timeout=2,
                socket_connect_timeout=2,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30,
                max_connections=10,
                retry_on_timeout=True,
            )
            
            # Testar conexão
            self.redis_client.ping()
            logging.info("Cache Redis inicializado com sucesso")
            
        except Exception as e:
            logging.warning(f"Redis não disponível, usando apenas cache em memória: {e}")
            self.redis_client = None
    
    def get(self, key: str) -> Optional[Any]:
        """
        Obtém valor do cache com estratégia hierárquica.
        
        Args:
            key: Chave do cache
            
        Returns:
            Valor cacheado ou None se não encontrado/expirado
        """
        # Tentar Redis primeiro
        if self.redis_client:
            try:
                data = self.redis_client.get(key)
                if data:
                    cached_data = json.loads(data)
                    if self._is_valid_cache_entry(cached_data):
                        self.cache_stats['hits'] += 1
                        self.cache_stats['redis_hits'] += 1
                        return cached_data['data']
            except Exception as e:
                logging.debug(f"Erro ao acessar Redis para chave '{key}': {e}")
        
        # Fallback para cache em memória
        with self._lock:
            if key in self.memory_cache:
                cached_data = self.memory_cache[key]
                if self._is_valid_cache_entry(cached_data):
                    self.cache_stats['hits'] += 1
                    self.cache_stats['memory_hits'] += 1
                    return cached_data['data']
                else:
                    # Remover entrada expirada
                    del self.memory_cache[key]
        
        self.cache_stats['misses'] += 1
        return None
    
    def set(self, key: str, data: Any, ttl_seconds: int = 30) -> None:
        """
        Armazena valor no cache com TTL.
        
        Args:
            key: Chave do cache
            data: Dados para armazenar
            ttl_seconds: Tempo de vida em segundos
        """
        expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
        cached_data = {
            'data': data,
            'expires_at': expires_at.isoformat(),
            'created_at': datetime.now().isoformat(),
        }
        
        # Salvar no Redis
        if self.redis_client:
            try:
                self.redis_client.setex(
                    key, 
                    ttl_seconds, 
                    json.dumps(cached_data, default=str)
                )
            except Exception as e:
                logging.debug(f"Erro ao salvar no Redis para chave '{key}': {e}")
        
        # Salvar no cache em memória como backup
        with self._lock:
            self.memory_cache[key] = cached_data
            self._cleanup_memory_cache()
    
    def _is_valid_cache_entry(self, cached_data: Dict[str, Any]) -> bool:
        """Verifica se entrada do cache ainda é válida."""
        try:
            expires_at = datetime.fromisoformat(cached_data['expires_at'])
            return datetime.now() < expires_at
        except (KeyError, ValueError):
            return False
    
    def _cleanup_memory_cache(self) -> None:
        """Remove entradas expiradas do cache em memória."""
        now = datetime.now()
        expired_keys = []
        
        for key, cached_data in self.memory_cache.items():
            if not self._is_valid_cache_entry(cached_data):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.memory_cache[key]
        
        # Limitar tamanho do cache em memória
        if len(self.memory_cache) > 100:
            # Remover as entradas mais antigas
            sorted_items = sorted(
                self.memory_cache.items(),
                key=lambda x: x[1].get('created_at', ''),
            )
            
            # Manter apenas os 50 mais recentes
            self.memory_cache = dict(sorted_items[-50:])
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache."""
        total_requests = self.cache_stats['hits'] + self.cache_stats['misses']
        hit_rate = (self.cache_stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'total_requests': total_requests,
            'hits': self.cache_stats['hits'],
            'misses': self.cache_stats['misses'],
            'hit_rate_percent': round(hit_rate, 2),
            'redis_available': self.redis_client is not None,
            'redis_hits': self.cache_stats['redis_hits'],
            'memory_hits': self.cache_stats['memory_hits'],
            'memory_cache_size': len(self.memory_cache),
        }
    
    def clear(self, pattern: str = None) -> None:
        """
        Limpa o cache.
        
        Args:
            pattern: Padrão de chaves para limpar (se None, limpa tudo)
        """
        if pattern:
            # Limpeza seletiva
            if self.redis_client:
                try:
                    keys = self.redis_client.keys(pattern)
                    if keys:
                        self.redis_client.delete(*keys)
                except Exception as e:
                    logging.warning(f"Erro ao limpar Redis com padrão '{pattern}': {e}")
            
            with self._lock:
                keys_to_remove = [k for k in self.memory_cache.keys() if pattern in k]
                for key in keys_to_remove:
                    del self.memory_cache[key]
        else:
            # Limpeza total
            if self.redis_client:
                try:
                    self.redis_client.flushdb()
                except Exception as e:
                    logging.warning(f"Erro ao limpar Redis: {e}")
            
            with self._lock:
                self.memory_cache.clear()


# Instância global do cache
router_cache = SmartCache() 