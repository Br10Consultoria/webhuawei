"""
Execução de comandos e parsing de dados do router NE8000.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List

from .cache import router_cache
from .connection import RouterConnection
from .utils import (
    CACHE_TTLS, 
    format_commands_with_target,
    get_optimized_commands_for_category,
    retry_on_failure
)


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
        commands = get_optimized_commands_for_category('interfaces')
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
        commands = get_optimized_commands_for_category('pppoe')
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
        commands = get_optimized_commands_for_category('system')
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


def add_utilization_data(interfaces: List[Dict[str, Any]], utilization_output: str) -> None:
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
# FUNÇÃO DE COMPATIBILIDADE
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
        # Formatar comandos com target
        formatted_commands = format_commands_with_target(commands, target)
        
        # Executar comandos usando a nova classe RouterConnection
        router = RouterConnection()
        results = router.execute_commands(formatted_commands)
        
        return results
        
    except Exception as e:
        logging.error(f"Erro na execução de comandos para target {target}: {e}")
        return [f"Error: {str(e)}"] 