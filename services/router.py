"""
Serviço de conexão com router NE8000 otimizado para performance e confiabilidade.
Implementa pool de conexões, cache inteligente e retry logic avançado.
"""

import json
import logging
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import wraps
from queue import Queue, Empty
from typing import Dict, List, Optional, Union, Any, Tuple

import paramiko
import redis
import telnetlib

# =============================================================================
# CONSTANTES DE CONFIGURAÇÃO
# =============================================================================

# Timeouts otimizados para equipamentos de rede
TIMEOUTS = {
    'connection': 8,           # Conexão inicial
    'command': 12,             # Execução de comando
    'auth': 15,                # Autenticação
    'banner': 10,              # Banner SSH
    'read_prompt': 8,          # Leitura de prompt
}

# Configurações de retry
RETRY_CONFIG = {
    'max_attempts': 3,
    'base_delay': 1.5,
    'max_delay': 8.0,
    'backoff_multiplier': 2.0,
}

# Cache TTLs (em segundos)
CACHE_TTLS = {
    'interfaces': 45,
    'pppoe_stats': 20,
    'system_metrics': 60,
    'traffic_data': 30,
    'connection_test': 15,
}

# Pool de conexões
CONNECTION_POOL_CONFIG = {
    'max_connections': 5,
    'idle_timeout': 300,       # 5 minutos
    'max_age': 1800,          # 30 minutos
}

# Comandos otimizados por categoria
OPTIMIZED_COMMANDS = {
    'interfaces': [
        "display interface brief | no-more",
        "display interface statistics | no-more"
    ],
    'pppoe': [
        "display access-user online | no-more",
        "display access-user statistics | no-more"
    ],
    'system': [
        "display cpu-usage | no-more",
        "display memory-usage | no-more",
        "display device | no-more"
    ],
    'version': ["display version | no-more"],
}


# =============================================================================
# DECORADORES E UTILITÁRIOS
# =============================================================================

def retry_on_failure(max_attempts: int = None, delay: float = None):
    """
    Decorator para retry automático com backoff exponencial.
    
    Args:
        max_attempts: Número máximo de tentativas
        delay: Delay base entre tentativas
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = max_attempts or RETRY_CONFIG['max_attempts']
            base_delay = delay or RETRY_CONFIG['base_delay']
            
            last_exception = None
            
            for attempt in range(attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt == attempts - 1:
                        break
                    
                    # Calcular delay com backoff exponencial
                    retry_delay = min(
                        base_delay * (RETRY_CONFIG['backoff_multiplier'] ** attempt),
                        RETRY_CONFIG['max_delay']
                    )
                    
                    logging.warning(
                        f"{func.__name__} falhou (tentativa {attempt + 1}/{attempts}): {e}. "
                        f"Tentando novamente em {retry_delay:.1f}s..."
                    )
                    
                    time.sleep(retry_delay)
            
            # Se chegou aqui, todas as tentativas falharam
            logging.error(f"{func.__name__} falhou após {attempts} tentativas: {last_exception}")
            raise last_exception
        
        return wrapper
    return decorator


def with_timeout(timeout_seconds: float):
    """Decorator para aplicar timeout em funções."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(func, *args, **kwargs)
                try:
                    return future.result(timeout=timeout_seconds)
                except FutureTimeoutError:
                    raise TimeoutError(f"{func.__name__} excedeu timeout de {timeout_seconds}s")
        return wrapper
    return decorator


# =============================================================================
# POOL DE CONEXÕES
# =============================================================================

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
    
    def mark_used(self):
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
    
    def _start_cleanup_thread(self):
        """Inicia thread de limpeza do pool."""
        if not self._cleanup_thread or not self._cleanup_thread.is_alive():
            self._running = True
            self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
            self._cleanup_thread.start()
    
    def _cleanup_loop(self):
        """Loop de limpeza de conexões expiradas."""
        while self._running:
            try:
                self._cleanup_expired_connections()
                time.sleep(30)  # Verificar a cada 30 segundos
            except Exception as e:
                logging.warning(f"Erro na limpeza do pool de conexões: {e}")
    
    def _cleanup_expired_connections(self):
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
            
            # Marcar como usada e retornar
            conn_info.mark_used()
            yield conn_info
            
        except Exception as e:
            if conn_info:
                conn_info.is_healthy = False
            raise
        
        finally:
            # Retornar conexão para o pool se ainda estiver saudável
            if conn_info and conn_info.is_healthy and not conn_info.is_expired():
                try:
                    with self._lock:
                        self._pool.put_nowait(conn_info)
                except:
                    # Pool cheio, fechar conexão
                    self._close_connection(conn_info)
            elif conn_info:
                self._close_connection(conn_info)
    
    def _create_new_connection(self, router_connection: 'RouterConnection') -> ConnectionInfo:
        """Cria nova conexão para o pool."""
        if router_connection.protocol == 'ssh':
            connection = self._create_ssh_connection(router_connection)
            return ConnectionInfo(connection, 'ssh')
        else:
            connection = self._create_telnet_connection(router_connection)
            return ConnectionInfo(connection, 'telnet')
    
    def _create_ssh_connection(self, router_conn: 'RouterConnection') -> paramiko.SSHClient:
        """Cria conexão SSH otimizada."""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        ssh.connect(
            hostname=router_conn.host,
            port=router_conn.ssh_port,
            username=router_conn.username,
            password=router_conn.password,
            timeout=TIMEOUTS['connection'],
            banner_timeout=TIMEOUTS['banner'],
            auth_timeout=TIMEOUTS['auth'],
            look_for_keys=False,
            allow_agent=False,
            compress=True,  # Ativar compressão para melhor performance
            gss_auth=False,
            gss_kex=False,
        )
        
        return ssh
    
    def _create_telnet_connection(self, router_conn: 'RouterConnection') -> telnetlib.Telnet:
        """Cria conexão Telnet otimizada."""
        tn = telnetlib.Telnet(
            host=router_conn.host,
            port=router_conn.telnet_port,
            timeout=TIMEOUTS['connection']
        )
        
        # Autenticação
        tn.read_until(b"Username:", timeout=TIMEOUTS['auth'])
        tn.write(router_conn.username.encode('ascii') + b"\n")
        
        tn.read_until(b"Password:", timeout=TIMEOUTS['auth'])
        tn.write(router_conn.password.encode('ascii') + b"\n")
        
        return tn
    
    def _test_connection_health(self, conn_info: ConnectionInfo) -> bool:
        """Testa se a conexão ainda está funcional."""
        try:
            if conn_info.protocol == 'ssh':
                # Para SSH, verificar se o transporte ainda está ativo
                transport = conn_info.connection.get_transport()
                return transport is not None and transport.is_active()
            else:
                # Para Telnet, a conexão é sempre considerada saudável se não expirou
                return True
        except:
            return False
    
    def _close_connection(self, conn_info: ConnectionInfo):
        """Fecha uma conexão de forma segura."""
        try:
            if conn_info.protocol == 'ssh':
                conn_info.connection.close()
            else:
                conn_info.connection.close()
        except:
            pass
    
    def shutdown(self):
        """Encerra o pool de conexões."""
        self._running = False
        
        # Fechar todas as conexões
        with self._lock:
            while not self._pool.empty():
                try:
                    conn_info = self._pool.get_nowait()
                    self._close_connection(conn_info)
                except Empty:
                    break


# =============================================================================
# CACHE INTELIGENTE
# =============================================================================

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
    
    def _initialize_redis(self):
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
    
    def set(self, key: str, data: Any, ttl_seconds: int = 30):
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
    
    def _cleanup_memory_cache(self):
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
    
    def clear(self, pattern: str = None):
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


# =============================================================================
# CONEXÃO PRINCIPAL COM O ROUTER
# =============================================================================

class RouterConnection:
    """Conexão otimizada com router NE8000."""
    
    def __init__(self):
        # Configurações de conexão
        self.host = os.getenv('ROUTER_HOST')
        self.username = os.getenv('ROUTER_USERNAME')
        self.password = os.getenv('ROUTER_PASSWORD')
        self.enable_password = os.getenv('ROUTER_ENABLE_PASSWORD')
        self.protocol = os.getenv('ROUTER_PROTOCOL', 'ssh').lower()
        self.ssh_port = int(os.getenv('ROUTER_SSH_PORT', 22))
        self.telnet_port = int(os.getenv('ROUTER_TELNET_PORT', 23))
        
        # Validar configuração
        if not all([self.host, self.username, self.password]):
            raise ValueError("Configurações de router incompletas (HOST, USERNAME, PASSWORD)")
        
        self.connection_pool = ConnectionPool()
        
        logging.info(f"RouterConnection inicializada: {self.protocol}://{self.username}@{self.host}")
    
    @retry_on_failure()
    @with_timeout(TIMEOUTS['command'] * 2)
    def execute_commands(self, commands: List[str]) -> List[str]:
        """
        Executa comandos no router usando pool de conexões.
        
        Args:
            commands: Lista de comandos para executar
            
        Returns:
            Lista com resultados dos comandos
        """
        if not commands:
            return []
        
        # Otimizar comandos (adicionar | no-more se necessário)
        optimized_commands = self._optimize_commands(commands)
        
        try:
            with self.connection_pool.get_connection(self) as conn_info:
                if conn_info.protocol == 'ssh':
                    return self._execute_ssh_commands(conn_info.connection, optimized_commands)
                else:
                    return self._execute_telnet_commands(conn_info.connection, optimized_commands)
        
        except Exception as e:
            logging.error(f"Erro ao executar comandos {commands}: {e}")
            return [f"Error: {str(e)}"]
    
    def _optimize_commands(self, commands: List[str]) -> List[str]:
        """
        Otimiza comandos para melhor performance.
        
        Args:
            commands: Comandos originais
            
        Returns:
            Comandos otimizados
        """
        optimized = []
        
        for cmd in commands:
            cmd = cmd.strip()
            if not cmd:
                continue
            
            # Adicionar | no-more para comandos display se não tiver
            if (cmd.startswith('display') and 
                '| no-more' not in cmd and 
                '|' not in cmd):
                cmd += ' | no-more'
            
            optimized.append(cmd)
        
        return optimized
    
    def _execute_ssh_commands(self, ssh_client: paramiko.SSHClient, commands: List[str]) -> List[str]:
        """Executa comandos via SSH com shell interativo."""
        shell = None
        
        try:
            # Criar shell interativo
            shell = ssh_client.invoke_shell(width=120, height=40)
            shell.settimeout(TIMEOUTS['command'])
            
            # Aguardar prompt inicial
            self._wait_for_prompt(shell, timeout=TIMEOUTS['auth'])
            
            results = []
            
            for command in commands:
                logging.debug(f"Executando SSH: {command}")
                
                # Enviar comando
                shell.send(command.encode() + b'\n')
                
                # Aguardar e ler resposta
                output = self._read_command_output(shell, command)
                results.append(output)
                
                logging.debug(f"SSH comando OK: {len(output)} chars")
            
            return results
            
        except Exception as e:
            logging.error(f"Erro na execução SSH: {e}")
            raise
        
        finally:
            if shell:
                try:
                    shell.close()
                except:
                    pass
    
    def _execute_telnet_commands(self, telnet_conn: telnetlib.Telnet, commands: List[str]) -> List[str]:
        """Executa comandos via Telnet."""
        results = []
        
        try:
            for command in commands:
                logging.debug(f"Executando Telnet: {command}")
                
                # Enviar comando
                telnet_conn.write(command.encode('ascii') + b'\n')
                
                # Ler resposta até próximo prompt
                output = telnet_conn.read_until(b'>', timeout=TIMEOUTS['command'])
                clean_output = output.decode('utf-8', errors='ignore')
                
                # Limpar output
                clean_output = self._clean_telnet_output(clean_output, command)
                results.append(clean_output)
                
                logging.debug(f"Telnet comando OK: {len(clean_output)} chars")
            
            return results
            
        except Exception as e:
            logging.error(f"Erro na execução Telnet: {e}")
            raise
    
    def _wait_for_prompt(self, shell: paramiko.Channel, timeout: float = 10):
        """Aguarda prompt do router."""
        start_time = time.time()
        buffer = b''
        
        prompt_indicators = [b'>', b'#', b']', b'<', b'$']
        
        while time.time() - start_time < timeout:
            if shell.recv_ready():
                chunk = shell.recv(1024)
                buffer += chunk
                
                # Verificar se encontrou prompt
                for indicator in prompt_indicators:
                    if indicator in chunk:
                        return buffer.decode('utf-8', errors='ignore')
            
            time.sleep(0.1)
        
        raise TimeoutError(f"Timeout aguardando prompt após {timeout}s")
    
    def _read_command_output(self, shell: paramiko.Channel, command: str, timeout: float = None) -> str:
        """Lê saída de comando até próximo prompt."""
        timeout = timeout or TIMEOUTS['command']
        start_time = time.time()
        output = b''
        
        prompt_indicators = [b'>', b'#', b']', b'<']
        
        while time.time() - start_time < timeout:
            if shell.recv_ready():
                chunk = shell.recv(4096)
                output += chunk
                
                # Verificar se terminou (encontrou prompt)
                for indicator in prompt_indicators:
                    if chunk.endswith(indicator) or chunk.endswith(indicator + b' '):
                        return self._clean_ssh_output(output.decode('utf-8', errors='ignore'), command)
            
            time.sleep(0.1)
        
        # Timeout - retornar o que foi coletado
        logging.warning(f"Timeout lendo comando '{command}' - retornando output parcial")
        return self._clean_ssh_output(output.decode('utf-8', errors='ignore'), command)
    
    def _clean_ssh_output(self, output: str, command: str) -> str:
        """Limpa output SSH removendo comando e prompts."""
        lines = output.split('\n')
        cleaned_lines = []
        
        skip_command = True
        
        for line in lines:
            line = line.strip()
            
            # Pular linha com o comando digitado
            if skip_command and command.strip() in line:
                skip_command = False
                continue
            
            # Pular prompts e linhas vazias
            if (line.endswith('>') or line.endswith('#') or 
                line.endswith(']') or line.endswith('<') or
                not line):
                continue
            
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()
    
    def _clean_telnet_output(self, output: str, command: str) -> str:
        """Limpa output Telnet."""
        lines = output.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            
            # Pular comando digitado e prompts
            if (command.strip() in line or 
                line.endswith('>') or 
                not line):
                continue
            
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()
    
    @retry_on_failure(max_attempts=2)
    def test_connection(self) -> bool:
        """
        Testa conectividade básica com o router.
        
        Returns:
            True se conectividade OK, False caso contrário
        """
        try:
            result = self.execute_commands(["display version"])
            
            if result and len(result) > 0 and not "Error:" in str(result[0]):
                logging.info("Teste de conectividade: SUCESSO")
                return True
            else:
                logging.warning(f"Teste de conectividade falhou: {result}")
                return False
                
        except Exception as e:
            logging.error(f"Erro no teste de conectividade: {e}")
            return False
    
    def get_optimized_commands_for_category(self, category: str) -> List[str]:
        """
        Retorna comandos otimizados para uma categoria.
        
        Args:
            category: Categoria de comandos ('interfaces', 'pppoe', 'system', etc.)
            
        Returns:
            Lista de comandos otimizados
        """
        return OPTIMIZED_COMMANDS.get(category, [])
    
    def shutdown(self):
        """Encerra conexão e limpa recursos."""
        if hasattr(self, 'connection_pool'):
            self.connection_pool.shutdown()


# =============================================================================
# INSTÂNCIAS GLOBAIS
# =============================================================================

# Cache global otimizado
router_cache = SmartCache()

# =============================================================================
# FUNÇÕES DE ALTO NÍVEL OTIMIZADAS
# =============================================================================

@retry_on_failure()
def get_interfaces_optimized() -> List[Dict[str, Any]]:
    """
    Obtém lista de interfaces do router de forma otimizada.
    
    Returns:
        Lista de interfaces com suas informações
    """
    cache_key = 'router_interfaces'
    
    # Verificar cache primeiro
    cached_data = router_cache.get(cache_key)
    if cached_data:
        logging.debug("Interfaces obtidas do cache")
        return cached_data
    
    # Se não tem cache, buscar do router
    router = RouterConnection()
    
    try:
        # Usar comandos otimizados
        commands = router.get_optimized_commands_for_category('interfaces')
        results = router.execute_commands(commands)
        
        if results and not any("Error:" in str(r) for r in results):
            interfaces = parse_interface_output_optimized(results[0])
            
            # Adicionar informações de utilização se disponível
            if len(results) > 1 and results[1]:
                add_utilization_data(interfaces, results[1])
            
            # Cache com TTL apropriado
            router_cache.set(cache_key, interfaces, CACHE_TTLS['interfaces'])
            
            logging.info(f"Interfaces atualizadas: {len(interfaces)} encontradas")
            return interfaces
        
    except Exception as e:
        logging.error(f"Erro ao obter interfaces: {e}")
    
    # Retornar lista vazia em caso de erro
    return []


@retry_on_failure()
def get_pppoe_stats_optimized() -> Dict[str, Any]:
    """
    Obtém estatísticas PPPoE otimizadas.
    
    Returns:
        Dicionário com estatísticas PPPoE
    """
    cache_key = 'pppoe_stats'
    
    # Verificar cache
    cached_data = router_cache.get(cache_key)
    if cached_data:
        logging.debug("Estatísticas PPPoE obtidas do cache")
        return cached_data
    
    # Buscar do router
    router = RouterConnection()
    
    try:
        commands = router.get_optimized_commands_for_category('pppoe')
        results = router.execute_commands(commands)
        
        if results and not any("Error:" in str(r) for r in results):
            stats = parse_pppoe_stats_optimized(results)
            
            # Cache com TTL menor (dados mais dinâmicos)
            router_cache.set(cache_key, stats, CACHE_TTLS['pppoe_stats'])
            
            logging.info(f"PPPoE stats atualizadas: {stats.get('active', 0)} sessões ativas")
            return stats
    
    except Exception as e:
        logging.error(f"Erro ao obter estatísticas PPPoE: {e}")
    
    # Retornar dados padrão em caso de erro
    return {
        'total': 0,
        'active': 0,
        'peak': 0,
        'authenticated': 0,
        'last_update': datetime.now().isoformat(),
        'error': 'Dados não disponíveis'
    }


@retry_on_failure()
def get_system_metrics_optimized() -> Dict[str, Any]:
    """
    Obtém métricas do sistema otimizadas.
    
    Returns:
        Dicionário com métricas do sistema
    """
    cache_key = 'system_metrics'
    
    # Verificar cache
    cached_data = router_cache.get(cache_key)
    if cached_data:
        logging.debug("Métricas do sistema obtidas do cache")
        return cached_data
    
    # Buscar do router
    router = RouterConnection()
    
    try:
        commands = router.get_optimized_commands_for_category('system')
        results = router.execute_commands(commands)
        
        if results and not any("Error:" in str(r) for r in results):
            metrics = parse_system_metrics_optimized(results)
            
            # Cache com TTL maior (dados menos dinâmicos)
            router_cache.set(cache_key, metrics, CACHE_TTLS['system_metrics'])
            
            logging.info(f"Métricas sistema atualizadas: CPU {metrics.get('cpu', 0)}%")
            return metrics
    
    except Exception as e:
        logging.error(f"Erro ao obter métricas do sistema: {e}")
    
    # Retornar dados padrão
    return {
        'cpu': 0,
        'memory': 0,
        'uptime': 'Desconhecido',
        'version': 'Desconhecido',
        'model': 'NE8000',
        'temperature': 0,
        'last_update': datetime.now().isoformat(),
        'error': 'Dados não disponíveis'
    }


# =============================================================================
# FUNÇÕES DE PARSING OTIMIZADAS
# =============================================================================

def parse_interface_output_optimized(output: str) -> List[Dict[str, Any]]:
    """
    Faz parsing otimizado da saída de interfaces.
    
    Args:
        output: Saída do comando display interface brief
        
    Returns:
        Lista de interfaces parseadas
    """
    interfaces = []
    
    if not output or "Error:" in output:
        return interfaces
    
    lines = output.split('\n')
    
    for line in lines:
        line = line.strip()
        
        # Pular linhas vazias ou cabeçalhos
        if not line or 'Interface' in line or '------' in line:
            continue
        
        # Parse básico de interface (adaptar conforme formato do NE8000)
        parts = line.split()
        
        if len(parts) >= 3:
            interface = {
                'name': parts[0],
                'status': parts[1] if len(parts) > 1 else 'Unknown',
                'protocol': parts[2] if len(parts) > 2 else 'Unknown',
                'ip_address': parts[3] if len(parts) > 3 else '',
                'description': ' '.join(parts[4:]) if len(parts) > 4 else '',
                'utilization_in': 0,
                'utilization_out': 0,
                'last_update': datetime.now().isoformat(),
            }
            
            interfaces.append(interface)
    
    return interfaces


def add_utilization_data(interfaces: List[Dict[str, Any]], utilization_output: str):
    """
    Adiciona dados de utilização às interfaces.
    
    Args:
        interfaces: Lista de interfaces para atualizar
        utilization_output: Saída do comando de utilização
    """
    if not utilization_output:
        return
    
    # Parse de utilização (adaptar conforme formato específico do NE8000)
    lines = utilization_output.split('\n')
    
    for line in lines:
        if 'utilization' in line.lower():
            # Implementar parsing específico baseado no formato real
            pass


def parse_pppoe_stats_optimized(results: List[str]) -> Dict[str, Any]:
    """
    Parse otimizado das estatísticas PPPoE.
    
    Args:
        results: Lista de resultados dos comandos PPPoE
        
    Returns:
        Dicionário com estatísticas parseadas
    """
    stats = {
        'total': 0,
        'active': 0,
        'peak': 0,
        'authenticated': 0,
        'last_update': datetime.now().isoformat(),
    }
    
    for result in results:
        if not result or "Error:" in result:
            continue
        
        lines = result.split('\n')
        
        for line in lines:
            line = line.strip().lower()
            
            # Adaptar parsing conforme formato real do NE8000
            if 'total' in line and 'user' in line:
                # Extrair número total
                parts = line.split()
                for part in parts:
                    if part.isdigit():
                        stats['total'] = int(part)
                        break
            
            elif 'active' in line and 'session' in line:
                # Extrair sessões ativas
                parts = line.split()
                for part in parts:
                    if part.isdigit():
                        stats['active'] = int(part)
                        break
    
    return stats


def parse_system_metrics_optimized(results: List[str]) -> Dict[str, Any]:
    """
    Parse otimizado das métricas do sistema.
    
    Args:
        results: Lista de resultados dos comandos de sistema
        
    Returns:
        Dicionário com métricas parseadas
    """
    metrics = {
        'cpu': 0,
        'memory': 0,
        'uptime': 'Desconhecido',
        'version': 'Desconhecido',
        'model': 'NE8000',
        'temperature': 0,
        'last_update': datetime.now().isoformat(),
    }
    
    for i, result in enumerate(results):
        if not result or "Error:" in result:
            continue
        
        lines = result.split('\n')
        
        if i == 0:  # CPU usage
            for line in lines:
                if 'cpu' in line.lower() and '%' in line:
                    # Extrair percentual de CPU
                    parts = line.split()
                    for part in parts:
                        if '%' in part:
                            try:
                                metrics['cpu'] = float(part.replace('%', ''))
                                break
                            except ValueError:
                                pass
        
        elif i == 1:  # Memory usage
            for line in lines:
                if 'memory' in line.lower() and '%' in line:
                    # Extrair percentual de memória
                    parts = line.split()
                    for part in parts:
                        if '%' in part:
                            try:
                                metrics['memory'] = float(part.replace('%', ''))
                                break
                            except ValueError:
                                pass
    
    return metrics


# =============================================================================
# FUNÇÕES DE UTILIDADE
# =============================================================================

def test_router_connection_optimized() -> Dict[str, Any]:
    """
    Testa conexão com o router de forma otimizada.
    
    Returns:
        Dicionário com resultado do teste
    """
    start_time = time.time()
    
    try:
        router = RouterConnection()
        success = router.test_connection()
        
        response_time = int((time.time() - start_time) * 1000)
        
        return {
            'success': success,
            'response_time_ms': response_time,
            'timestamp': datetime.now().isoformat(),
            'protocol': router.protocol,
            'host': router.host,
        }
    
    except Exception as e:
        response_time = int((time.time() - start_time) * 1000)
        
        return {
            'success': False,
            'error': str(e),
            'response_time_ms': response_time,
            'timestamp': datetime.now().isoformat(),
        }


def log_interface_action_optimized(
    action: str, 
    interface: str, 
    user: str, 
    success: bool, 
    details: str = ""
):
    """
    Log otimizado de ações em interfaces.
    
    Args:
        action: Ação realizada
        interface: Nome da interface
        user: Usuário que executou a ação
        success: Se a ação foi bem-sucedida
        details: Detalhes adicionais
    """
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'action': action,
        'interface': interface,
        'user': user,
        'success': success,
        'details': details,
    }
    
    # Log estruturado
    if success:
        logging.info(f"Interface action: {action} on {interface} by {user} - SUCCESS")
    else:
        logging.warning(f"Interface action: {action} on {interface} by {user} - FAILED: {details}")
    
    # Aqui poderia salvar em banco de dados para auditoria
    # Por enquanto, apenas log


def get_cache_statistics() -> Dict[str, Any]:
    """
    Obtém estatísticas do cache.
    
    Returns:
        Dicionário com estatísticas do cache
    """
    return router_cache.get_stats()


def clear_router_cache(pattern: str = None):
    """
    Limpa o cache do router.
    
    Args:
        pattern: Padrão de chaves para limpar (opcional)
    """
    router_cache.clear(pattern)
    logging.info(f"Cache limpo {f'(padrão: {pattern})' if pattern else '(completo)'}")


# =============================================================================
# COMPATIBILIDADE COM CÓDIGO EXISTENTE
# =============================================================================

# Aliases para manter compatibilidade
def get_interfaces():
    """Alias de compatibilidade para get_interfaces_optimized."""
    return get_interfaces_optimized()


def get_pppoe_stats():
    """Alias de compatibilidade para get_pppoe_stats_optimized."""
    return get_pppoe_stats_optimized()


def get_system_metrics():
    """Alias de compatibilidade para get_system_metrics_optimized."""
    return get_system_metrics_optimized()


def test_router_connection():
    """Alias de compatibilidade para test_router_connection_optimized."""
    return test_router_connection_optimized()


def log_interface_action(action, interface, user, success, details=""):
    """Alias de compatibilidade para log_interface_action_optimized."""
    return log_interface_action_optimized(action, interface, user, success, details)


def parse_interface_output(output):
    """Alias de compatibilidade para parse_interface_output_optimized."""
    return parse_interface_output_optimized(output)


# =============================================================================
# FUNÇÕES DE COMPATIBILIDADE ADICIONAL
# =============================================================================

def execute_router_commands(target: str, commands: List[str]) -> List[str]:
    """
    Função de compatibilidade para execute_router_commands.
    
    Args:
        target: Target para substituir nos comandos (placeholder {target})
        commands: Lista de comandos com placeholders
        
    Returns:
        Lista de resultados dos comandos
    """
    try:
        # Substituir placeholder {target} nos comandos
        formatted_commands = []
        for cmd in commands:
            if '{target}' in cmd:
                formatted_cmd = cmd.format(target=target)
            else:
                formatted_cmd = cmd
            formatted_commands.append(formatted_cmd)
        
        # Executar comandos usando a nova classe RouterConnection
        router = RouterConnection()
        results = router.execute_commands(formatted_commands)
        
        return results
        
    except Exception as e:
        logging.error(f"Erro na execução de comandos para target {target}: {e}")
        return [f"Error: {str(e)}"]
