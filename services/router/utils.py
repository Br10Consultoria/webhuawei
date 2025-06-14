"""
Utilitários e decoradores para o sistema de router NE8000.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

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
# DECORADORES UTILITÁRIOS
# =============================================================================

def retry_on_failure(max_attempts: int = None, delay: float = None):
    """
    Decorator para retry automático com backoff exponencial.
    
    Args:
        max_attempts: Número máximo de tentativas
        delay: Delay base entre tentativas
    """
    def decorator(func: Callable) -> Callable:
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
    def decorator(func: Callable) -> Callable:
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
# FUNÇÕES UTILITÁRIAS
# =============================================================================

def optimize_commands(commands: List[str]) -> List[str]:
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


def format_commands_with_target(commands: List[str], target: str) -> List[str]:
    """
    Formata comandos substituindo placeholders de target.
    
    Args:
        commands: Lista de comandos com placeholders
        target: Valor para substituir {target}
        
    Returns:
        Comandos formatados
    """
    formatted_commands = []
    for cmd in commands:
        if '{target}' in cmd:
            formatted_cmd = cmd.format(target=target)
        else:
            formatted_cmd = cmd
        formatted_commands.append(formatted_cmd)
    
    return formatted_commands


def clean_command_output(output: str, command: str, protocol: str = 'ssh') -> str:
    """
    Limpa output de comando removendo prompts e comandos digitados.
    
    Args:
        output: Output bruto do comando
        command: Comando executado
        protocol: Protocolo usado (ssh/telnet)
        
    Returns:
        Output limpo
    """
    if protocol == 'ssh':
        return _clean_ssh_output(output, command)
    else:
        return _clean_telnet_output(output, command)


def _clean_ssh_output(output: str, command: str) -> str:
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


def _clean_telnet_output(output: str, command: str) -> str:
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


def get_optimized_commands_for_category(category: str) -> List[str]:
    """
    Retorna comandos otimizados para uma categoria.
    
    Args:
        category: Categoria de comandos
        
    Returns:
        Lista de comandos otimizados
    """
    return OPTIMIZED_COMMANDS.get(category, [])


def log_interface_action_optimized(
    action: str, 
    interface: str, 
    user: str, 
    success: bool, 
    details: str = ""
) -> None:
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