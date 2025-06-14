"""
Serviço de background otimizado para coleta contínua de dados do router NE8000.
Implementa coleta assíncrona, recuperação de falhas e otimização de recursos.
"""

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from .router import (
    RouterConnection, 
    get_interfaces_optimized, 
    get_pppoe_stats_optimized,
    get_system_metrics_optimized,
    router_cache
)

# =============================================================================
# CONSTANTES DE CONFIGURAÇÃO
# =============================================================================

# Intervalos de atualização otimizados (em segundos)
UPDATE_INTERVALS = {
    'pppoe_stats': 10,          # Mais frequente - dados críticos
    'network_traffic': 15,       # Dados de tráfego
    'interfaces': 20,            # Interfaces
    'system_metrics': 30,        # Métricas de sistema
    'connection_health': 60,     # Health checks
}

# Configurações de retry para falhas
RETRY_CONFIG = {
    'max_consecutive_failures': 5,
    'failure_backoff_multiplier': 1.5,
    'max_backoff_seconds': 300, # 5 minutos
    'recovery_check_interval': 60,
}

# Configurações de threading
THREADING_CONFIG = {
    'max_workers': 4,
    'collection_timeout': 45,
    'startup_timeout': 30,
}

# Thresholds para alertas

class RouterBackgroundService:
    def __init__(self):
        self.router = RouterConnection()
        self.running = False
        self.thread = None
        
        # Configurações do serviço
        self.update_intervals = {
            'interfaces': 30,      # Interfaces a cada 30s
            'pppoe_stats': 15,     # PPPoE stats a cada 15s
            'system_metrics': 45,  # Métricas sistema a cada 45s
            'traffic_data': 20,    # Dados de tráfego a cada 20s
        }
        
        # Controle de última atualização
        self.last_updates = {
            'interfaces': datetime.min,
            'pppoe_stats': datetime.min,
            'system_metrics': datetime.min,
            'traffic_data': datetime.min,
        }
        
        logging.info("Router Background Service inicializado")
    
    def start(self):
        """Inicia o serviço em background"""
        if self.running:
            logging.warning("Background service já está rodando")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_service, daemon=True)
        self.thread.start()
        logging.info("Router Background Service iniciado")
    
    def stop(self):
        """Para o serviço"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logging.info("Router Background Service parado")
    
    def _run_service(self):
        """Loop principal do serviço"""
        logging.info("Iniciando loop do background service")
        
        # Fazer coleta inicial
        self._initial_data_collection()
        
        while self.running:
            try:
                current_time = datetime.now()
                
                # Verificar quais dados precisam ser atualizados
                for data_type, interval in self.update_intervals.items():
                    if (current_time - self.last_updates[data_type]).total_seconds() >= interval:
                        self._update_data_type(data_type)
                        self.last_updates[data_type] = current_time
                
                # Aguardar antes da próxima verificação
                time.sleep(5)  # Verificar a cada 5 segundos
                
            except Exception as e:
                logging.error(f"Erro no background service: {e}")
                time.sleep(10)  # Aguardar mais tempo se houver erro
    
    def _initial_data_collection(self):
        """Coleta inicial de dados para popular o cache rapidamente"""
        logging.info("Realizando coleta inicial de dados...")
        
        # Tentar conectar primeiro
        if not self.router.test_connection():
            logging.warning("Router não acessível - pulando coleta inicial")
            self._set_fallback_data()
            return
        
        # Coletar todos os tipos de dados
        for data_type in self.update_intervals.keys():
            try:
                self._update_data_type(data_type)
                time.sleep(2)  # Pequeno delay entre coletas
            except Exception as e:
                logging.error(f"Erro na coleta inicial de {data_type}: {e}")
        
        logging.info("Coleta inicial de dados concluída")
    
    def _update_data_type(self, data_type):
        """Atualiza um tipo específico de dados"""
        try:
            if data_type == 'interfaces':
                self._update_interfaces()
            elif data_type == 'pppoe_stats':
                self._update_pppoe_stats()
            elif data_type == 'system_metrics':
                self._update_system_metrics()
            elif data_type == 'traffic_data':
                self._update_traffic_data()
            
            logging.debug(f"Dados {data_type} atualizados com sucesso")
            
        except Exception as e:
            logging.error(f"Erro ao atualizar {data_type}: {e}")
    
    def _update_interfaces(self):
        """Atualiza dados das interfaces"""
        try:
            commands = [
                "display interface brief",
                "display interface | include utilization"
            ]
            
            results = self.router.execute_commands(commands)
            
            if results and not any("Error:" in str(r) for r in results):
                # Parse interfaces do primeiro resultado
                interfaces = get_interfaces_optimized(results[0])
                
                # Parse utilização do segundo resultado se disponível
                if len(results) > 1 and results[1]:
                    self._parse_interface_utilization(interfaces, results[1])
                
                # Armazenar no cache com TTL longo
                router_cache.set('router_interfaces', interfaces, 300)  # 5 minutos
                router_cache.set('interfaces_last_update', datetime.now().isoformat(), 300)
                
                logging.info(f"Interfaces atualizadas: {len(interfaces)} encontradas")
            else:
                logging.warning("Falha ao obter dados de interfaces")
                
        except Exception as e:
            logging.error(f"Erro ao atualizar interfaces: {e}")
    
    def _update_pppoe_stats(self):
        """Atualiza estatísticas PPPoE"""
        try:
            commands = [
                "display access-user online-total",
                "display access-user statistics"
            ]
            
            results = self.router.execute_commands(commands)
            
            if results and not any("Error:" in str(r) for r in results):
                stats = get_pppoe_stats_optimized(results)
                
                router_cache.set('pppoe_stats', stats, 180)  # 3 minutos
                router_cache.set('pppoe_last_update', datetime.now().isoformat(), 180)
                
                logging.info(f"PPPoE stats atualizadas: {stats['active']} sessões ativas")
            else:
                logging.warning("Falha ao obter estatísticas PPPoE")
                
        except Exception as e:
            logging.error(f"Erro ao atualizar PPPoE stats: {e}")
    
    def _update_system_metrics(self):
        """Atualiza métricas do sistema"""
        try:
            commands = [
                "display cpu-usage",
                "display memory-usage",
                "display device",
                "display version"
            ]
            
            results = self.router.execute_commands(commands)
            
            if results and not any("Error:" in str(r) for r in results):
                metrics = get_system_metrics_optimized(results)
                
                router_cache.set('system_metrics', metrics, 240)  # 4 minutos
                router_cache.set('system_last_update', datetime.now().isoformat(), 240)
                
                logging.info(f"Métricas sistema atualizadas: CPU {metrics['cpu']}%, RAM {metrics['memory']}%")
            else:
                logging.warning("Falha ao obter métricas do sistema")
                
        except Exception as e:
            logging.error(f"Erro ao atualizar métricas do sistema: {e}")
    
    def _update_traffic_data(self):
        """Atualiza dados de tráfego de rede"""
        try:
            commands = [
                "display interface brief | include utilization",
                "display traffic-policy statistics"
            ]
            
            results = self.router.execute_commands(commands)
            
            if results:
                traffic_data = self._parse_traffic_data(results)
                
                router_cache.set('network_traffic', traffic_data, 120)  # 2 minutos
                router_cache.set('traffic_last_update', datetime.now().isoformat(), 120)
                
                logging.info("Dados de tráfego atualizados")
                
        except Exception as e:
            logging.error(f"Erro ao atualizar dados de tráfego: {e}")
    
    def _parse_interface_utilization(self, interfaces, utilization_output):
        """Parse da utilização das interfaces"""
        lines = utilization_output.split('\n')
        for line in lines:
            if 'utilization' in line.lower():
                for interface in interfaces:
                    if interface['name'] in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if 'in:' in part.lower() and i + 1 < len(parts):
                                interface['in_util'] = parts[i + 1]
                            elif 'out:' in part.lower() and i + 1 < len(parts):
                                interface['out_util'] = parts[i + 1]
    
    def _parse_traffic_data(self, results):
        """Parse dos dados de tráfego"""
        traffic_data = {
            'inbound': 0.0,
            'outbound': 0.0,
            'total': 0.0,
            'peak_in': 0.0,
            'peak_out': 0.0
        }
        
        # Parse real traffic data from results
        for result in results:
            if result and 'utilization' in result.lower():
                lines = result.split('\n')
                total_in = 0
                total_out = 0
                count = 0
                
                for line in lines:
                    if 'in:' in line.lower() and 'out:' in line.lower():
                        try:
                            parts = line.split()
                            for i, part in enumerate(parts):
                                if 'in:' in part.lower() and i + 1 < len(parts):
                                    in_val = float(parts[i + 1].replace('%', '').replace('Mbps', ''))
                                    total_in += in_val
                                elif 'out:' in part.lower() and i + 1 < len(parts):
                                    out_val = float(parts[i + 1].replace('%', '').replace('Mbps', ''))
                                    total_out += out_val
                            count += 1
                        except:
                            pass
                
                if count > 0:
                    traffic_data['inbound'] = total_in / count
                    traffic_data['outbound'] = total_out / count
                    traffic_data['total'] = traffic_data['inbound'] + traffic_data['outbound']
        
        return traffic_data
    
    def _set_fallback_data(self):
        """Define dados de fallback quando router não está acessível"""
        logging.info("Definindo dados de fallback...")
        
        # Dados vazios mas estruturados
        fallback_data = {
            'router_interfaces': [],
            'pppoe_stats': {'total': 0, 'active': 0, 'peak': 0, 'max_users': 0},
            'system_metrics': {
                'cpu': 0, 'memory': 0, 'uptime': 'Unknown',
                'version': 'Unknown', 'serial': 'Unknown',
                'temperature': 0, 'power_status': 'Normal', 'model': 'NE8000'
            },
            'network_traffic': {
                'inbound': 0.0, 'outbound': 0.0, 'total': 0.0,
                'peak_in': 0.0, 'peak_out': 0.0
            }
        }
        
        # Armazenar no cache com TTL menor para tentar novamente em breve
        for key, data in fallback_data.items():
            router_cache.set(key, data, 60)
        
        # Marcar como offline
        router_cache.set('router_status', {'online': False, 'last_error': 'Connection failed'}, 60)
    
    def get_service_status(self):
        """Retorna status do serviço"""
        return {
            'running': self.running,
            'last_updates': self.last_updates,
            'update_intervals': self.update_intervals,
            'thread_alive': self.thread.is_alive() if self.thread else False
        }

# Instância global do serviço
background_service = RouterBackgroundService()

# Função para inicializar o serviço
def start_background_service():
    """Inicializa o serviço de background"""
    background_service.start()

def stop_background_service():
    """Para o serviço de background"""
    background_service.stop()

def get_background_service_status():
    """Retorna status do serviço de background"""
    return background_service.get_service_status() 