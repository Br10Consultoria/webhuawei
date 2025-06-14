"""
Sistema de conexão e cache para router NE8000 - Versão Modular.
"""

# Importar todas as funcionalidades dos módulos
from .cache import router_cache, SmartCache
from .connection import RouterConnection, ConnectionPool
from .commands import (
    get_interfaces_optimized,
    get_pppoe_stats_optimized, 
    get_system_metrics_optimized,
    test_router_connection_optimized,
    parse_interface_output_optimized,
    parse_pppoe_stats_optimized,
    parse_system_metrics_optimized,
    execute_router_commands
)
from .utils import (
    log_interface_action_optimized,
    get_optimized_commands_for_category,
    CACHE_TTLS,
    TIMEOUTS,
    RETRY_CONFIG,
    CONNECTION_POOL_CONFIG,
    OPTIMIZED_COMMANDS
)

# =============================================================================
# FUNÇÕES DE COMPATIBILIDADE (Aliases)
# =============================================================================

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
# FUNÇÕES UTILITÁRIAS EXPORTADAS
# =============================================================================

def get_cache_statistics():
    """
    Obtém estatísticas do cache.
    
    Returns:
        Dicionário com estatísticas do cache
    """
    return router_cache.get_stats()


def clear_router_cache(pattern=None):
    """
    Limpa o cache do router.
    
    Args:
        pattern: Padrão de chaves para limpar (opcional)
    """
    router_cache.clear(pattern)
    import logging
    logging.info(f"Cache limpo {f'(padrão: {pattern})' if pattern else '(completo)'}")


# =============================================================================
# EXPORTS PRINCIPAIS
# =============================================================================

__all__ = [
    # Classes principais
    'RouterConnection',
    'SmartCache',
    'ConnectionPool',
    
    # Cache global
    'router_cache',
    
    # Funções otimizadas
    'get_interfaces_optimized',
    'get_pppoe_stats_optimized', 
    'get_system_metrics_optimized',
    'test_router_connection_optimized',
    'log_interface_action_optimized',
    
    # Funções de parsing
    'parse_interface_output_optimized',
    'parse_pppoe_stats_optimized',
    'parse_system_metrics_optimized',
    
    # Funções de compatibilidade
    'get_interfaces',
    'get_pppoe_stats',
    'get_system_metrics', 
    'test_router_connection',
    'log_interface_action',
    'parse_interface_output',
    'execute_router_commands',
    
    # Funções utilitárias
    'get_cache_statistics',
    'clear_router_cache',
    'get_optimized_commands_for_category',
    
    # Constantes
    'CACHE_TTLS',
    'TIMEOUTS',
    'RETRY_CONFIG',
    'CONNECTION_POOL_CONFIG',
    'OPTIMIZED_COMMANDS',
] 