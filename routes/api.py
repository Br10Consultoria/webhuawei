"""
API endpoints otimizados para sistema de monitoramento NE8000.
Implementa cache inteligente, rate limiting, validação robusta e tratamento de erros.
"""

import logging
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple, Union

from flask import Blueprint, current_app, jsonify, request, session

from routes.auth import login_required
from services.background_service import background_service, get_background_service_status
from services.router import (
    RouterConnection, 
    log_interface_action_optimized as log_interface_action,
    router_cache,
    test_router_connection_optimized as test_router_connection,
    get_cache_statistics,
    clear_router_cache,
    get_interfaces_optimized
)

# =============================================================================
# CONSTANTES E CONFIGURAÇÕES
# =============================================================================

# Rate limiting - requisições por minuto por endpoint
RATE_LIMITS = {
    'command_execution': 10,    # Comandos críticos
    'data_retrieval': 30,       # Busca de dados
    'diagnostics': 5,           # Diagnósticos
    'cache_operations': 3,      # Operações de cache
}

# Timeouts para operações
OPERATION_TIMEOUTS = {
    'command_execution': 30,    # Execução de comandos
    'data_retrieval': 10,       # Busca de dados
    'diagnostics': 15,          # Diagnósticos
    'file_operations': 5,       # Operações de arquivo
}

# Mensagens de erro padronizadas
ERROR_MESSAGES = {
    'invalid_command': 'Comando inválido ou não fornecido',
    'router_offline': 'Router offline - dados podem estar desatualizados',
    'cache_miss': 'Dados não disponíveis no cache',
    'permission_denied': 'Operação não permitida',
    'timeout': 'Operação excedeu o tempo limite',
    'rate_limit': 'Muitas requisições - tente novamente em alguns segundos',
    'invalid_interface': 'Interface inválida ou não encontrada',
    'config_error': 'Erro de configuração do sistema',
}

# =============================================================================
# BLUEPRINT E UTILITÁRIOS
# =============================================================================

api_bp = Blueprint('api', __name__)

# Cache para rate limiting
rate_limit_cache = {}
online_history = []
peak_users = 0


# =============================================================================
# DECORADORES PARA OTIMIZAÇÃO
# =============================================================================

def rate_limit(category: str, per_minute: int = None):
    """
    Decorator para rate limiting de endpoints.
    
    Args:
        category: Categoria do rate limit
        per_minute: Número máximo de requisições por minuto
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not per_minute:
                limit = RATE_LIMITS.get(category, 30)
            else:
                limit = per_minute
            
            # Identificar cliente (IP + usuário)
            client_id = f"{request.remote_addr}_{session.get('username', 'anonymous')}"
            cache_key = f"rate_limit_{category}_{client_id}"
            
            now = datetime.now()
            
            # Verificar rate limit
            if cache_key in rate_limit_cache:
                requests, window_start = rate_limit_cache[cache_key]
                
                # Resetar janela se passou de 1 minuto
                if (now - window_start).total_seconds() > 60:
                    rate_limit_cache[cache_key] = (1, now)
                elif requests >= limit:
                    return jsonify({
                        'success': False,
                        'error': ERROR_MESSAGES['rate_limit'],
                        'retry_after': int(60 - (now - window_start).total_seconds())
                    }), 429
                else:
                    rate_limit_cache[cache_key] = (requests + 1, window_start)
            else:
                rate_limit_cache[cache_key] = (1, now)
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def with_error_handling(operation_timeout: int = None):
    """
    Decorator para tratamento robusto de erros.
    
    Args:
        operation_timeout: Timeout para a operação em segundos
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                if operation_timeout:
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(func, *args, **kwargs)
                        try:
                            result = future.result(timeout=operation_timeout)
                            return result
                        except FutureTimeoutError:
                            current_app.logger.warning(
                                f"{func.__name__} excedeu timeout de {operation_timeout}s"
                            )
                            return jsonify({
                                'success': False,
                                'error': ERROR_MESSAGES['timeout'],
                                'timeout_seconds': operation_timeout
                            }), 408
                else:
                    return func(*args, **kwargs)
                    
            except Exception as e:
                execution_time = time.time() - start_time
                current_app.logger.error(
                    f"Erro em {func.__name__}: {str(e)} (tempo: {execution_time:.2f}s)"
                )
                
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'execution_time': round(execution_time, 2),
                    'timestamp': datetime.now().isoformat()
                }), 500
                
        return wrapper
    return decorator


def validate_request_data(required_fields: List[str]):
    """
    Decorator para validação de dados de requisição.
    
    Args:
        required_fields: Lista de campos obrigatórios
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not request.is_json:
                return jsonify({
                    'success': False,
                    'error': 'Content-Type deve ser application/json'
                }), 400
            
            data = request.get_json()
            if not data:
                return jsonify({
                    'success': False,
                    'error': 'Dados JSON não fornecidos'
                }), 400
            
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                return jsonify({
                    'success': False,
                    'error': f'Campos obrigatórios ausentes: {", ".join(missing_fields)}'
                }), 400
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


# =============================================================================
# ENDPOINTS DE DADOS - OTIMIZADOS PARA CACHE
# =============================================================================

@api_bp.route('/api/online_total')
@login_required
@rate_limit('data_retrieval')
@with_error_handling(OPERATION_TIMEOUTS['data_retrieval'])
def get_online_total():
    """Endpoint otimizado para total de usuários online com histórico."""
    global peak_users, online_history
    
    # Obter dados do cache do background service
    pppoe_stats = router_cache.get('pppoe_stats')
    
    if pppoe_stats:
        current_total = pppoe_stats.get('total', 0)
        current_active = pppoe_stats.get('active', 0)
        
        # Atualizar pico de usuários
        peak_users = max(peak_users, current_total)
        
        # Manter histórico (últimas 288 entradas = 24h com amostragem de 5 min)
        online_history.append({
            'timestamp': datetime.now().isoformat(),
            'total': current_total,
            'active': current_active
        })
        
        # Limitar tamanho do histórico
        if len(online_history) > 288:
            online_history = online_history[-288:]
        
        return jsonify({
            'success': True,
            'data': {
                'total': current_total,
                'active': current_active,
                'peak': max(peak_users, pppoe_stats.get('peak', 0)),
                'history': online_history[-50:],  # Últimas 50 entradas para o gráfico
                'last_update': router_cache.get('pppoe_last_update'),
                'cached': True,
                'history_size': len(online_history)
            }
        })
    
    # Fallback se não há dados no cache
    return jsonify({
        'success': True,
        'data': {
            'total': 0,
            'active': 0,
            'peak': peak_users,
            'history': online_history[-50:],
            'last_update': None,
            'cached': False,
            'message': 'Aguardando dados do background service'
        }
    })


@api_bp.route('/api/system_metrics')
@login_required
@rate_limit('data_retrieval')
@with_error_handling(OPERATION_TIMEOUTS['data_retrieval'])
def get_system_metrics():
    """Endpoint otimizado para métricas do sistema."""
    # Obter dados do cache
    metrics = router_cache.get('system_metrics')
    
    if metrics:
        return jsonify({
            'success': True,
            'data': {
                **metrics,
                'last_update': router_cache.get('system_last_update'),
                'cached': True
            }
        })
    
    # Dados padrão se cache vazio
    return jsonify({
        'success': True,
        'data': {
            'cpu': 0,
            'memory': 0,
            'uptime': 'Desconhecido',
            'version': 'Desconhecido',
            'serial': 'Desconhecido',
            'temperature': 0,
            'power_status': 'Desconhecido',
            'model': 'NE8000',
            'last_update': None,
            'cached': False,
            'message': 'Aguardando coleta de dados'
        }
    })


@api_bp.route('/api/network_traffic')
@login_required
@rate_limit('data_retrieval')
@with_error_handling(OPERATION_TIMEOUTS['data_retrieval'])
def get_network_traffic():
    """Endpoint otimizado para dados de tráfego de rede."""
    traffic_data = router_cache.get('network_traffic')
    
    if traffic_data:
        return jsonify({
            'success': True,
            'data': {
                'inbound': round(traffic_data.get('inbound', 0), 2),
                'outbound': round(traffic_data.get('outbound', 0), 2),
                'total': round(traffic_data.get('total', 0), 2),
                'peak_in': round(traffic_data.get('peak_in', 0), 2),
                'peak_out': round(traffic_data.get('peak_out', 0), 2),
                'utilization_percent': round(traffic_data.get('utilization_percent', 0), 1),
                'max_bandwidth': traffic_data.get('max_bandwidth', 1000),
                'timestamp': datetime.now().isoformat(),
                'last_update': router_cache.get('traffic_last_update'),
                'cached': True
            }
        })
    
    # Dados padrão
    return jsonify({
        'success': True,
        'data': {
            'inbound': 0,
            'outbound': 0,
            'total': 0,
            'peak_in': 0,
            'peak_out': 0,
            'utilization_percent': 0,
            'max_bandwidth': 1000,
            'timestamp': datetime.now().isoformat(),
            'last_update': None,
            'cached': False,
            'message': 'Aguardando coleta de dados'
        }
    })


@api_bp.route('/api/interfaces_status')
@login_required
@rate_limit('data_retrieval')
@with_error_handling(OPERATION_TIMEOUTS['data_retrieval'])
def get_interfaces_status():
    """Retorna status das interfaces com tratamento robusto."""
    try:
        # Buscar dados
        interfaces_data = get_interfaces_optimized()
        
        # Validar e normalizar dados
        if not interfaces_data:
            interfaces_data = []
        
        # Garantir que é sempre uma lista
        if not isinstance(interfaces_data, list):
            current_app.logger.warning(f"interfaces_data não é lista: {type(interfaces_data)}")
            interfaces_data = []
        
        return jsonify({
            'success': True,
            'data': interfaces_data,
            'count': len(interfaces_data),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        current_app.logger.error(f"Erro ao buscar interfaces: {e}")
        return jsonify({
            'success': False,
            'error': f"Falha ao buscar interfaces: {str(e)}",
            'data': [],  # Array vazio para evitar erro no frontend
            'count': 0
        }), 500


@api_bp.route('/api/pppoe_stats')
@login_required
@rate_limit('data_retrieval')
@with_error_handling(OPERATION_TIMEOUTS['data_retrieval'])
def get_pppoe_stats():
    """Endpoint otimizado para estatísticas PPPoE."""
    stats = router_cache.get('pppoe_stats')
    
    if stats:
        return jsonify({
            'success': True,
            'data': {
                **stats,
                'last_update': router_cache.get('pppoe_last_update'),
                'cached': True
            }
        })
    
    # Dados padrão
    return jsonify({
        'success': True,
        'data': {
            'total': 0,
            'active': 0,
            'peak': 0,
            'authenticated': 0,
            'max_users': 0,
            'last_update': None,
            'cached': False,
            'message': 'Aguardando estatísticas PPPoE'
        }
    })


# =============================================================================
# ENDPOINTS DE COMANDO - ALTA SEGURANÇA
# =============================================================================

@api_bp.route('/api/execute_command', methods=['POST'])
@login_required
@rate_limit('command_execution')
@validate_request_data(['command'])
@with_error_handling(OPERATION_TIMEOUTS['command_execution'])
def execute_command():
    """Endpoint para execução segura de comandos."""
    data = request.get_json()
    command = data.get('command', '').strip()
    
    # Validações de segurança
    if not command:
        return jsonify({
            'success': False,
            'error': ERROR_MESSAGES['invalid_command']
        }), 400
    
    # Lista de comandos permitidos (whitelist)
    allowed_commands = [
        'display version',
        'display interface brief',
        'display cpu-usage',
        'display memory-usage',
        'display device',
        'display access-user online',
        'display access-user statistics',
        'display traffic-policy statistics'
    ]
    
    # Verificar se comando está na whitelist
    command_allowed = False
    for allowed in allowed_commands:
        if command.lower().startswith(allowed.lower()):
            command_allowed = True
            break
    
    if not command_allowed:
        current_app.logger.warning(
            f"Comando não permitido: {command} - Usuário: {session.get('username', 'unknown')}"
        )
        return jsonify({
            'success': False,
            'error': 'Comando não permitido por política de segurança'
        }), 403
    
    # Log da execução
    user = session.get('username', 'unknown')
    current_app.logger.info(f"Executando comando: {command} - Usuário: {user}")
    
    # Executar comando
    start_time = time.time()
    
    try:
        router = RouterConnection()
        results = router.execute_commands([command])
        
        execution_time = time.time() - start_time
        
        if results and not any("Error:" in str(r) for r in results):
            output = '\n'.join(results).strip()
            
            current_app.logger.info(f"Comando executado com sucesso em {execution_time:.2f}s")
            
            return jsonify({
                'success': True,
                'data': {
                    'output': output,
                    'command': command,
                    'execution_time': round(execution_time, 2),
                    'timestamp': datetime.now().isoformat(),
                    'user': user
                }
            })
        else:
            error_output = '\n'.join(results) if results else 'Nenhuma resposta'
            current_app.logger.error(f"Erro na execução do comando: {error_output}")
            
            return jsonify({
                'success': False,
                'error': error_output,
                'execution_time': round(execution_time, 2)
            }), 500
    
    except Exception as e:
        execution_time = time.time() - start_time
        current_app.logger.error(f"Exceção na execução do comando: {e}")
        
        return jsonify({
            'success': False,
            'error': str(e),
            'execution_time': round(execution_time, 2)
        }), 500


@api_bp.route('/api/interface_command', methods=['POST'])
@login_required
@rate_limit('command_execution')
@validate_request_data(['command', 'action', 'interface'])
@with_error_handling(OPERATION_TIMEOUTS['command_execution'])
def interface_command():
    """Endpoint para comandos específicos de interface."""
    data = request.get_json()
    command = data.get('command', '').strip()
    action = data.get('action', '').strip()
    interface = data.get('interface', '').strip()
    
    # Validações
    if not all([command, action, interface]):
        return jsonify({
            'success': False,
            'error': 'Comando, ação e interface são obrigatórios'
        }), 400
    
    # Ações permitidas
    allowed_actions = ['activate', 'deactivate', 'shutdown', 'undo_shutdown', 'reset', 'show']
    
    if action not in allowed_actions:
        return jsonify({
            'success': False,
            'error': f'Ação não permitida: {action}'
        }), 403
    
    # Validar nome da interface
    if not interface.replace('/', '').replace('-', '').replace('_', '').isalnum():
        return jsonify({
            'success': False,
            'error': ERROR_MESSAGES['invalid_interface']
        }), 400
    
    # Log da ação
    user = session.get('username', 'unknown')
    current_app.logger.info(f"Interface {action}: {interface} - Usuário: {user}")
    
    try:
        router = RouterConnection()
        
        # Preparar comandos baseados na ação
        if action in ['activate', 'deactivate', 'shutdown', 'undo_shutdown']:
            # Comandos de configuração
            config_commands = [
                'system-view',
                f'interface {interface}',
                command,
                'quit',
                'quit'
            ]
            results = router.execute_commands(config_commands)
        else:
            # Comandos de consulta
            results = router.execute_commands([command])
        
        # Processar resultado
        if results and not any("Error:" in str(r) for r in results):
            output = '\n'.join(results).strip()
            
            # Log de sucesso
            log_interface_action(action, interface, user, True, "Comando executado com sucesso")
            
            current_app.logger.info(f"Interface {action} em {interface}: SUCESSO")
            
            return jsonify({
                'success': True,
                'data': {
                    'output': output,
                    'action': action,
                    'interface': interface,
                    'timestamp': datetime.now().isoformat()
                }
            })
        else:
            error_output = '\n'.join(results) if results else 'Nenhuma resposta'
            
            # Log de falha
            log_interface_action(action, interface, user, False, error_output[:200])
            
            current_app.logger.error(f"Interface {action} em {interface}: FALHA - {error_output}")
            
            return jsonify({
                'success': False,
                'error': error_output
            }), 500
    
    except Exception as e:
        # Log de exceção
        log_interface_action(action, interface, user, False, str(e))
        
        current_app.logger.error(f"Exceção em interface {action}: {e}")
        
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# ENDPOINTS DE CONECTIVIDADE E DIAGNÓSTICO
# =============================================================================

@api_bp.route('/api/router_connect', methods=['POST'])
@login_required
@rate_limit('diagnostics')
@with_error_handling(OPERATION_TIMEOUTS['diagnostics'])
def router_connect():
    """Endpoint para testar conectividade com o router."""
    try:
        router = RouterConnection()
        
        # Testar conectividade
        is_connected = router.test_connection()
        
        if is_connected:
            return jsonify({
                'success': True,
                'data': {
                    'connected': True,
                    'message': 'Conexão estabelecida com sucesso',
                    'router_info': 'NE8000 Connected',
                    'timestamp': datetime.now().isoformat()
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Falha na conectividade com o router',
                'data': {
                    'connected': False,
                    'timestamp': datetime.now().isoformat()
                }
            }), 503
    
    except Exception as e:
        current_app.logger.error(f"Erro no teste de conectividade: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'data': {
                'connected': False,
                'timestamp': datetime.now().isoformat()
            }
        }), 500


@api_bp.route('/api/router_disconnect', methods=['POST'])
@login_required
@rate_limit('diagnostics')
def router_disconnect():
    """Endpoint para simular desconexão (sem estado persistente)."""
    return jsonify({
        'success': True,
        'data': {
            'message': 'Desconectado com sucesso',
            'timestamp': datetime.now().isoformat()
        }
    })


@api_bp.route('/api/router_status')
@login_required
@rate_limit('data_retrieval')
@with_error_handling(OPERATION_TIMEOUTS['data_retrieval'])
def get_router_status():
    """Endpoint para verificar status do router."""
    try:
        # Testar conectividade
        connection_result = test_router_connection()
        is_connected = connection_result.get('success', False)
        
        # Obter informações do cache
        cache_info = {
            'interfaces_available': router_cache.get('router_interfaces') is not None,
            'pppoe_available': router_cache.get('pppoe_stats') is not None,
            'system_available': router_cache.get('system_metrics') is not None,
            'last_interfaces_update': router_cache.get('interfaces_last_update'),
            'last_pppoe_update': router_cache.get('pppoe_last_update'),
            'last_system_update': router_cache.get('system_last_update'),
        }
        
        return jsonify({
            'success': True,
            'data': {
                'connected': is_connected,
                'status': 'online' if is_connected else 'offline',
                'message': 'Router conectado' if is_connected else 'Router offline - usando dados em cache',
                'response_time_ms': connection_result.get('response_time_ms', 0),
                'protocol': connection_result.get('protocol', 'unknown'),
                'cache_info': cache_info,
                'last_check': datetime.now().isoformat()
            }
        })
    
    except Exception as e:
        current_app.logger.error(f"Erro ao verificar status do router: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'data': {
                'connected': False,
                'status': 'error',
                'last_check': datetime.now().isoformat()
            }
        }), 500


@api_bp.route('/api/router_diagnostics')
@login_required
@rate_limit('diagnostics')
@with_error_handling(OPERATION_TIMEOUTS['diagnostics'])
def router_diagnostics():
    """Endpoint avançado de diagnóstico."""
    diagnostics = {
        'timestamp': datetime.now().isoformat(),
        'config_check': {},
        'connectivity_check': {},
        'authentication_check': {},
        'performance_check': {},
        'recommendations': [],
        'overall_status': 'unknown'
    }
    
    try:
        # 1. Verificar configurações
        config = {
            'router_host': os.getenv('ROUTER_HOST', 'NOT_SET'),
            'router_username': os.getenv('ROUTER_USERNAME', 'NOT_SET'),
            'router_password': 'SET' if os.getenv('ROUTER_PASSWORD') else 'NOT_SET',
            'router_protocol': os.getenv('ROUTER_PROTOCOL', 'ssh'),
            'ssh_port': int(os.getenv('ROUTER_SSH_PORT', 22)),
            'telnet_port': int(os.getenv('ROUTER_TELNET_PORT', 23))
        }
        
        diagnostics['config_check'] = config
        
        # Validar configurações críticas
        if config['router_host'] == 'NOT_SET':
            diagnostics['recommendations'].append('⚠️ ROUTER_HOST não configurado')
            diagnostics['overall_status'] = 'config_error'
            return jsonify(diagnostics)
        
        if config['router_password'] == 'NOT_SET':
            diagnostics['recommendations'].append('⚠️ ROUTER_PASSWORD não configurado')
        
        # 2. Teste de conectividade de rede
        connectivity_results = {}
        
        try:
            # Teste de ping/conectividade básica
            ssh_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            ssh_socket.settimeout(5)
            ssh_start = time.time()
            ssh_result = ssh_socket.connect_ex((config['router_host'], config['ssh_port']))
            ssh_time = time.time() - ssh_start
            ssh_socket.close()
            
            telnet_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            telnet_socket.settimeout(5)
            telnet_start = time.time()
            telnet_result = telnet_socket.connect_ex((config['router_host'], config['telnet_port']))
            telnet_time = time.time() - telnet_start
            telnet_socket.close()
            
            connectivity_results = {
                'host_reachable': ssh_result == 0 or telnet_result == 0,
                'ssh_port_open': ssh_result == 0,
                'telnet_port_open': telnet_result == 0,
                'ssh_response_time_ms': round(ssh_time * 1000, 2),
                'telnet_response_time_ms': round(telnet_time * 1000, 2)
            }
            
        except Exception as e:
            connectivity_results = {
                'host_reachable': False,
                'ssh_port_open': False,
                'telnet_port_open': False,
                'error': str(e)
            }
        
        diagnostics['connectivity_check'] = connectivity_results
        
        # 3. Teste de autenticação
        auth_results = {}
        
        try:
            router = RouterConnection()
            auth_start = time.time()
            auth_success = router.test_connection()
            auth_time = time.time() - auth_start
            
            auth_results = {
                'authentication_successful': auth_success,
                'response_time_ms': round(auth_time * 1000, 2),
                'protocol_used': config['router_protocol']
            }
            
        except Exception as e:
            auth_results = {
                'authentication_successful': False,
                'error': str(e),
                'protocol_used': config['router_protocol']
            }
        
        diagnostics['authentication_check'] = auth_results
        
        # 4. Teste de performance
        performance_results = {
            'cache_stats': get_cache_statistics(),
            'background_service_status': get_background_service_status()
        }
        
        diagnostics['performance_check'] = performance_results
        
        # 5. Gerar recomendações
        recommendations = []
        
        if not connectivity_results.get('host_reachable', False):
            recommendations.append('🔴 Host não alcançável - verificar rede e firewall')
            diagnostics['overall_status'] = 'network_error'
        
        elif not connectivity_results.get('ssh_port_open', False):
            recommendations.append('🟡 Porta SSH não acessível - verificar configuração SSH')
        
        if not auth_results.get('authentication_successful', False):
            recommendations.extend([
                '🔴 Falha na autenticação - verificar credenciais',
                '💡 Testar conexão manual via SSH',
                '💡 Verificar algoritmos de criptografia suportados'
            ])
            if diagnostics['overall_status'] == 'unknown':
                diagnostics['overall_status'] = 'auth_error'
        
        # Recomendações de performance
        cache_stats = performance_results['cache_stats']
        if cache_stats.get('hit_rate_percent', 0) < 50:
            recommendations.append('🟡 Taxa de hit do cache baixa - considerar ajustar TTLs')
        
        if not performance_results['background_service_status'].get('running', False):
            recommendations.append('🔴 Serviço de background não está rodando')
        
        # Recomendações de conectividade
        ssh_time = connectivity_results.get('ssh_response_time_ms', 0)
        if ssh_time > 2000:
            recommendations.append('🟡 Latência alta para SSH - verificar rede')
        
        if not recommendations:
            recommendations.append('✅ Todos os testes passaram - sistema funcionando normalmente')
            diagnostics['overall_status'] = 'healthy'
        
        diagnostics['recommendations'] = recommendations
        
        return jsonify({
            'success': True,
            'data': diagnostics
        })
        
    except Exception as e:
        current_app.logger.error(f"Erro no diagnóstico: {e}")
        diagnostics['overall_status'] = 'diagnostic_error'
        diagnostics['error'] = str(e)
        
        return jsonify({
            'success': False,
            'error': str(e),
            'data': diagnostics
        }), 500


# =============================================================================
# ENDPOINTS DE ADMINISTRAÇÃO E CACHE
# =============================================================================

@api_bp.route('/api/background_service_status')
@login_required
@rate_limit('data_retrieval')
def get_background_service_status_endpoint():
    """Endpoint para status do serviço de background."""
    try:
        service_status = get_background_service_status()
        cache_stats = get_cache_statistics()
        
        # Informações detalhadas do cache
        cache_info = {
            'statistics': cache_stats,
            'data_availability': {
                'interfaces': router_cache.get('router_interfaces') is not None,
                'pppoe_stats': router_cache.get('pppoe_stats') is not None,
                'system_metrics': router_cache.get('system_metrics') is not None,
                'network_traffic': router_cache.get('network_traffic') is not None,
            },
            'last_updates': {
                'interfaces': router_cache.get('interfaces_last_update'),
                'pppoe': router_cache.get('pppoe_last_update'),
                'system': router_cache.get('system_last_update'),
                'traffic': router_cache.get('traffic_last_update'),
            }
        }
        
        return jsonify({
            'success': True,
            'data': {
                'service': service_status,
                'cache': cache_info,
                'timestamp': datetime.now().isoformat()
            }
        })
    
    except Exception as e:
        current_app.logger.error(f"Erro ao obter status do background service: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@api_bp.route('/api/force_cache_refresh', methods=['POST'])
@login_required
@rate_limit('cache_operations')
@with_error_handling(OPERATION_TIMEOUTS['data_retrieval'])
def force_cache_refresh():
    """Endpoint para forçar refresh do cache."""
    try:
        # Limpar cache atual
        clear_router_cache()
        
        # Forçar coleta de dados no background service
        if background_service and background_service.running:
            # Executar coleta inicial em thread separada para não bloquear
            import threading
            thread = threading.Thread(
                target=background_service._initial_data_collection,
                daemon=True
            )
            thread.start()
            
            return jsonify({
                'success': True,
                'data': {
                    'message': 'Cache refresh iniciado com sucesso',
                    'timestamp': datetime.now().isoformat(),
                    'background_service_running': True
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Background service não está rodando',
                'data': {
                    'timestamp': datetime.now().isoformat(),
                    'background_service_running': False
                }
            }), 503
    
    except Exception as e:
        current_app.logger.error(f"Erro ao forçar refresh do cache: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@api_bp.route('/api/clear_cache', methods=['POST'])
@login_required
@rate_limit('cache_operations')
def clear_cache():
    """Endpoint para limpar cache completamente."""
    try:
        data = request.get_json() or {}
        pattern = data.get('pattern')  # Padrão opcional para limpeza seletiva
        
        clear_router_cache(pattern)
        
        return jsonify({
            'success': True,
            'data': {
                'message': f'Cache limpo com sucesso{f" (padrão: {pattern})" if pattern else ""}',
                'timestamp': datetime.now().isoformat(),
                'pattern': pattern
            }
        })
    
    except Exception as e:
        current_app.logger.error(f"Erro ao limpar cache: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


# =============================================================================
# ENDPOINTS DE LOGS E AUDITORIA
# =============================================================================

@api_bp.route('/api/interface_logs')
@login_required
@rate_limit('data_retrieval')
@with_error_handling(OPERATION_TIMEOUTS['file_operations'])
def get_interface_logs():
    """Endpoint para obter logs de ações em interfaces."""
    try:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
        log_file = os.path.join(log_dir, 'interface_actions.log')
        
        logs = []
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
                # Pegar as últimas 200 linhas e formatar
                for line in lines[-200:]:
                    line = line.strip()
                    if line:
                        logs.append({
                            'timestamp': datetime.now().isoformat(),  # Seria melhor parsear do log
                            'message': line,
                            'raw': line
                        })
        
        return jsonify({
            'success': True,
            'data': {
                'logs': logs,
                'count': len(logs),
                'log_file': log_file,
                'last_read': datetime.now().isoformat()
            }
        })
    
    except Exception as e:
        current_app.logger.error(f"Erro ao ler logs de interface: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@api_bp.route('/api/system_logs')
@login_required
@rate_limit('data_retrieval')
@with_error_handling(OPERATION_TIMEOUTS['file_operations'])
def get_system_logs():
    """Endpoint para obter logs do sistema."""
    try:
        log_files = ['app.log', 'error.log', 'access.log']
        logs_data = {}
        
        for log_filename in log_files:
            log_path = os.path.join('logs', log_filename)
            
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    # Últimas 50 linhas de cada arquivo
                    logs_data[log_filename] = [line.strip() for line in lines[-50:] if line.strip()]
            else:
                logs_data[log_filename] = []
        
        return jsonify({
            'success': True,
            'data': {
                'logs': logs_data,
                'files_checked': log_files,
                'timestamp': datetime.now().isoformat()
            }
        })
    
    except Exception as e:
        current_app.logger.error(f"Erro ao ler logs do sistema: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


# =============================================================================
# ENDPOINTS DE ESTATÍSTICAS E MÉTRICAS
# =============================================================================

@api_bp.route('/api/cache_statistics')
@login_required
@rate_limit('data_retrieval')
def get_cache_statistics_endpoint():
    """Endpoint para estatísticas detalhadas do cache."""
    try:
        cache_stats = get_cache_statistics()
        
        return jsonify({
            'success': True,
            'data': {
                'statistics': cache_stats,
                'timestamp': datetime.now().isoformat()
            }
        })
    
    except Exception as e:
        current_app.logger.error(f"Erro ao obter estatísticas do cache: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@api_bp.route('/api/performance_metrics')
@login_required
@rate_limit('data_retrieval')
def get_performance_metrics():
    """Endpoint para métricas de performance da aplicação."""
    try:
        # Limpar cache de rate limiting antigo
        now = datetime.now()
        expired_keys = []
        
        for key, (requests, window_start) in rate_limit_cache.items():
            if (now - window_start).total_seconds() > 60:
                expired_keys.append(key)
        
        for key in expired_keys:
            del rate_limit_cache[key]
        
        # Coletar métricas
        metrics = {
            'cache': get_cache_statistics(),
            'rate_limiting': {
                'active_clients': len(rate_limit_cache),
                'total_requests_last_minute': sum(req[0] for req in rate_limit_cache.values())
            },
            'background_service': get_background_service_status(),
            'memory_usage': {
                'online_history_size': len(online_history),
                'rate_limit_cache_size': len(rate_limit_cache)
            }
        }
        
        return jsonify({
            'success': True,
            'data': {
                'metrics': metrics,
                'timestamp': datetime.now().isoformat()
            }
        })
    
    except Exception as e:
        current_app.logger.error(f"Erro ao obter métricas de performance: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


# =============================================================================
# HEALTH CHECK
# =============================================================================

@api_bp.route('/api/health')
def health_check():
    """Endpoint de health check para monitoramento."""
    try:
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'components': {
                'cache': 'healthy',
                'background_service': 'unknown',
                'router_connection': 'unknown'
            }
        }
        
        # Verificar cache
        try:
            cache_stats = get_cache_statistics()
            health_status['components']['cache'] = 'healthy' if cache_stats else 'unhealthy'
        except:
            health_status['components']['cache'] = 'unhealthy'
        
        # Verificar background service
        try:
            bg_status = get_background_service_status()
            health_status['components']['background_service'] = 'healthy' if bg_status.get('running') else 'unhealthy'
        except:
            health_status['components']['background_service'] = 'unhealthy'
        
        # Status geral
        unhealthy_components = [k for k, v in health_status['components'].items() if v == 'unhealthy']
        
        if unhealthy_components:
            health_status['status'] = 'degraded'
            health_status['issues'] = unhealthy_components
        
        return jsonify(health_status)
    
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500