"""
Pool de conexões e classe de conexão principal para router NE8000.
"""

import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from queue import Empty, Queue
from typing import Any, List

import paramiko
import telnetlib

from .utils import (
    CONNECTION_POOL_CONFIG, 
    TIMEOUTS, 
    clean_command_output, 
    optimize_commands,
    retry_on_failure,
    with_timeout
)


class ConnectionInfo:
    """Informações sobre uma conexão no pool."""
    
    def __init__(self, connection: Any, protocol: str):
        self.connection = connection
        self.protocol = protocol
        self.created_at = datetime.now()
        self.last_used = datetime.now()
        self.is_healthy = True
        self.usage_count = 0
    
    def is_expired(self) -> bool:
        """Verifica se a conexão expirou."""
        now = datetime.now()
        idle_time = (now - self.last_used).total_seconds()
        age = (now - self.created_at).total_seconds()
        
        return (idle_time > CONNECTION_POOL_CONFIG['idle_timeout'] or 
                age > CONNECTION_POOL_CONFIG['max_age'])
    
    def mark_used(self) -> None:
        """Marca a conexão como usada."""
        self.last_used = datetime.now()
        self.usage_count += 1


class ConnectionPool:
    """Pool de conexões reutilizáveis para o router."""
    
    def __init__(self):
        self._pool: Queue[ConnectionInfo] = Queue(maxsize=CONNECTION_POOL_CONFIG['max_connections'])
        self._lock = threading.RLock()
        self._cleanup_thread = None
        self._running = False
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self) -> None:
        """Inicia thread de limpeza do pool."""
        if not self._cleanup_thread or not self._cleanup_thread.is_alive():
            self._running = True
            self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
            self._cleanup_thread.start()
    
    def _cleanup_loop(self) -> None:
        """Loop de limpeza de conexões expiradas."""
        while self._running:
            try:
                self._cleanup_expired_connections()
                time.sleep(30)  # Verificar a cada 30 segundos
            except Exception as e:
                logging.warning(f"Erro na limpeza do pool de conexões: {e}")
    
    def _cleanup_expired_connections(self) -> None:
        """Remove conexões expiradas do pool."""
        with self._lock:
            active_connections = []
            
            while not self._pool.empty():
                try:
                    conn_info = self._pool.get_nowait()
                    
                    if not conn_info.is_expired() and conn_info.is_healthy:
                        active_connections.append(conn_info)
                    else:
                        self._close_connection(conn_info)
                        logging.debug(f"Conexão {conn_info.protocol} removida do pool (expirada/não saudável)")
                
                except Empty:
                    break
            
            # Recolocar conexões ativas no pool
            for conn_info in active_connections:
                try:
                    self._pool.put_nowait(conn_info)
                except:
                    self._close_connection(conn_info)
    
    @contextmanager
    def get_connection(self, router_connection: 'RouterConnection'):
        """
        Context manager para obter conexão do pool.
        
        Args:
            router_connection: Instância de RouterConnection para criar nova conexão se necessário
        
        Yields:
            ConnectionInfo: Informações da conexão
        """
        conn_info = None
        
        try:
            # Tentar obter conexão existente do pool
            with self._lock:
                try:
                    conn_info = self._pool.get_nowait()
                    
                    # Verificar se a conexão ainda é válida
                    if conn_info.is_expired() or not self._test_connection_health(conn_info):
                        self._close_connection(conn_info)
                        conn_info = None
                
                except Empty:
                    pass
            
            # Se não há conexão válida, criar nova
            if conn_info is None:
                conn_info = self._create_new_connection(router_connection)
            
            # Mar 