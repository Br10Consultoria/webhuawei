"""
Serviço de conexão assíncrona com router NE8000
Versão otimizada para FastAPI com concurrent connections e timeout handling
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
import asyncssh
import aioredis
from concurrent.futures import ThreadPoolExecutor
import paramiko
import telnetlib
from contextlib import asynccontextmanager

from core.config import settings, get_router_config

logger = logging.getLogger(__name__)

# =============================================================================
# ASYNC ROUTER CONNECTION
# =============================================================================

class AsyncRouterConnection:
    """Conexão assíncrona com router NE8000"""
    
    def __init__(self):
        self.config = get_router_config()
        self.connected = False
        self.connection = None
        self.connection_time = None
        self.last_activity = None
        
        # Pool de threads para operações síncronas
        self.thread_pool = ThreadPoolExecutor(max_workers=3)
        
        # Cache interno para comandos
        self._command_cache = {}
        self._cache_expiry = {}
        
    async def initialize(self):
        """Inicializa a conexão assíncrona"""
        try:
            await self.connect()
            logger.info("✅ Conexão assíncrona com router inicializada")
        except Exception as e:
            logger.warning(f"⚠️ Falha na inicialização da conexão: {e}")
    
    async def connect(self, custom_config: Dict = None) -> bool:
        """Conecta ao router de forma assíncrona"""
        try:
            # Usar configuração customizada se fornecida
            config = custom_config or self.config
            
            if config["protocol"] == "ssh":
                success = await self._connect_ssh(config)
            else:
                success = await self._connect_telnet(config)
            
            if success:
                self.connected = True
                self.connection_time = datetime.now()
                self.last_activity = datetime.now()
                logger.info(f"🔗 Conectado ao router {config['host']}:{config['port']}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Erro na conexão: {e}")
            self.connected = False
            return False
    
    async def _connect_ssh(self, config: Dict) -> bool:
        """Conecta via SSH assíncrono"""
        try:
            # Usar asyncssh para conexão assíncrona
            self.connection = await asyncio.wait_for(
                asyncssh.connect(
                    config["host"],
                    port=config["port"],
                    username=config["username"],
                    password=config["password"],
                    known_hosts=None,
                    server_host_key_algs=['ssh-rsa', 'rsa-sha2-256', 'rsa-sha2-512']
                ),
                timeout=config["timeouts"]["connection"]
            )
            
            # Testar conexão com comando simples
            result = await self._execute_ssh_command("display version | include uptime")
            return "uptime" in result.lower() or len(result) > 0
            
        except asyncio.TimeoutError:
            logger.error("🕐 Timeout na conexão SSH")
            return False
        except Exception as e:
            logger.error(f"❌ Erro SSH: {e}")
            return False
    
    async def _connect_telnet(self, config: Dict) -> bool:
        """Conecta via Telnet (executado em thread)"""
        try:
            # Executar conexão telnet em thread separada
            loop = asyncio.get_event_loop()
            self.connection = await loop.run_in_executor(
                self.thread_pool,
                self._sync_telnet_connect,
                config
            )
            
            return self.connection is not None
            
        except Exception as e:
            logger.error(f"❌ Erro Telnet: {e}")
            return False
    
    def _sync_telnet_connect(self, config: Dict):
        """Conexão telnet síncrona (para thread)"""
        try:
            tn = telnetlib.Telnet(
                config["host"],
                config["port"],
                timeout=config["timeouts"]["connection"]
            )
            
            # Autenticação
            tn.read_until(b"Username:", timeout=5)
            tn.write(config["username"].encode('ascii') + b"\n")
            
            tn.read_until(b"Password:", timeout=5)
            tn.write(config["password"].encode('ascii') + b"\n")
            
            # Aguardar prompt
            tn.read_until(b">", timeout=5)
            
            return tn
            
        except Exception as e:
            logger.error(f"Erro na conexão telnet síncrona: {e}")
            return None
    
    async def disconnect(self):
        """Desconecta do router"""
        try:
            if self.connection:
                if hasattr(self.connection, 'close'):
                    await self.connection.close()
                else:
                    # Para conexões telnet
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        self.thread_pool,
                        self.connection.close
                    )
                
                self.connection = None
            
            self.connected = False
            logger.info("🔌 Desconectado do router")
            
        except Exception as e:
            logger.error(f"Erro ao desconectar: {e}")
    
    def is_connected(self) -> bool:
        """Verifica se está conectado"""
        if not self.connected:
            return False
        
        # Verificar timeout de conexão
        if self.connection_time:
            elapsed = datetime.now() - self.connection_time
            if elapsed > timedelta(minutes=30):  # Timeout de 30 minutos
                asyncio.create_task(self.disconnect())
                return False
        
        return True
    
    async def get_connection_info(self) -> Dict:
        """Obtém informações da conexão"""
        return {
            "connected": self.is_connected(),
            "connection_time": self.connection_time.isoformat() if self.connection_time else None,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "protocol": self.config["protocol"],
            "host": self.config["host"],
            "port": self.config["port"]
        }
    
    async def execute_command(self, command: str, timeout: int = 30) -> str:
        """Executa comando no router"""
        if not self.is_connected():
            await self.connect()
        
        try:
            # Verificar cache primeiro
            cache_key = f"cmd:{command}"
            if cache_key in self._command_cache:
                expiry = self._cache_expiry.get(cache_key)
                if expiry and datetime.now() < expiry:
                    logger.debug(f"🗃️ Comando em cache: {command[:50]}...")
                    return self._command_cache[cache_key]
            
            # Executar comando
            if self.config["protocol"] == "ssh":
                result = await self._execute_ssh_command(command, timeout)
            else:
                result = await self._execute_telnet_command(command, timeout)
            
            # Atualizar cache para comandos de leitura
            if any(cmd in command.lower() for cmd in ["display", "show", "get"]):
                self._command_cache[cache_key] = result
                self._cache_expiry[cache_key] = datetime.now() + timedelta(seconds=30)
            
            self.last_activity = datetime.now()
            return result
            
        except Exception as e:
            logger.error(f"❌ Erro ao executar comando '{command}': {e}")
            raise
    
    async def _execute_ssh_command(self, command: str, timeout: int = 30) -> str:
        """Executa comando via SSH"""
        try:
            # Executar comando com timeout
            result = await asyncio.wait_for(
                self.connection.run(command),
                timeout=timeout
            )
            
            return result.stdout.strip()
            
        except asyncio.TimeoutError:
            raise TimeoutError(f"Comando '{command}' excedeu timeout de {timeout}s")
        except Exception as e:
            raise Exception(f"Erro SSH no comando '{command}': {e}")
    
    async def _execute_telnet_command(self, command: str, timeout: int = 30) -> str:
        """Executa comando via Telnet"""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.thread_pool,
                self._sync_telnet_command,
                command,
                timeout
            )
            
            return result
            
        except Exception as e:
            raise Exception(f"Erro Telnet no comando '{command}': {e}")
    
    def _sync_telnet_command(self, command: str, timeout: int) -> str:
        """Executa comando telnet síncrono"""
        try:
            # Enviar comando
            self.connection.write(command.encode('ascii') + b"\n")
            
            # Ler resposta até próximo prompt
            response = self.connection.read_until(b">", timeout=timeout)
            
            # Decodificar e limpar resposta
            result = response.decode('ascii', errors='ignore')
            
            # Remover eco do comando e prompt
            lines = result.split('\n')
            if lines and command in lines[0]:
                lines = lines[1:]  # Remover eco
            if lines and lines[-1].endswith('>'):
                lines = lines[:-1]  # Remover prompt
            
            return '\n'.join(lines).strip()
            
        except Exception as e:
            raise Exception(f"Erro na execução telnet: {e}")
    
    # =============================================================================
    # MÉTODOS DE DADOS ESPECÍFICOS
    # =============================================================================
    
    async def get_interfaces(self) -> List[Dict[str, Any]]:
        """Obtém lista de interfaces"""
        try:
            command = "display interface brief | no-more"
            result = await self.execute_command(command)
            
            return self._parse_interfaces(result)
            
        except Exception as e:
            logger.error(f"Erro ao obter interfaces: {e}")
            return []
    
    async def get_pppoe_stats(self) -> Dict[str, Any]:
        """Obtém estatísticas PPPoE básicas"""
        try:
            command = "display access-user online-total | no-more"
            result = await self.execute_command(command)
            
            return self._parse_pppoe_stats(result)
            
        except Exception as e:
            logger.error(f"Erro ao obter stats PPPoE: {e}")
            return {"active": 0, "peak": 0}
    
    async def get_pppoe_stats_detailed(self) -> Dict[str, Any]:
        """Obtém estatísticas PPPoE detalhadas"""
        try:
            commands = [
                "display access-user online-total | no-more",
                "display access-user statistics | no-more"
            ]
            
            # Executar comandos em paralelo
            tasks = [self.execute_command(cmd) for cmd in commands]
            results = await asyncio.gather(*tasks)
            
            return self._parse_pppoe_detailed(results)
            
        except Exception as e:
            logger.error(f"Erro ao obter stats PPPoE detalhadas: {e}")
            return {"active": 0, "peak": 0, "total_sessions": 0}
    
    async def get_system_metrics(self) -> Dict[str, Any]:
        """Obtém métricas do sistema"""
        try:
            commands = [
                "display cpu-usage | no-more",
                "display memory-usage | no-more",
                "display device | no-more"
            ]
            
            # Executar comandos em paralelo
            tasks = [self.execute_command(cmd) for cmd in commands]
            results = await asyncio.gather(*tasks)
            
            return self._parse_system_metrics(results)
            
        except Exception as e:
            logger.error(f"Erro ao obter métricas do sistema: {e}")
            return {"cpu": 0, "memory": 0, "uptime": "Unknown"}
    
    async def get_traffic_data(self) -> Dict[str, Any]:
        """Obtém dados de tráfego"""
        try:
            command = "display interface statistics | no-more"
            result = await self.execute_command(command)
            
            return self._parse_traffic_data(result)
            
        except Exception as e:
            logger.error(f"Erro ao obter dados de tráfego: {e}")
            return {"total_in": 0, "total_out": 0, "interfaces": []}
    
    async def run_diagnostics(self) -> Dict[str, Any]:
        """Executa diagnósticos básicos"""
        try:
            diagnostics = {
                "connection": self.is_connected(),
                "timestamp": datetime.now().isoformat(),
                "tests": {}
            }
            
            if self.is_connected():
                # Teste de comando básico
                try:
                    result = await self.execute_command("display version | include uptime", timeout=10)
                    diagnostics["tests"]["basic_command"] = {
                        "success": True,
                        "response_time": "< 10s",
                        "data": result[:100] + "..." if len(result) > 100 else result
                    }
                except Exception as e:
                    diagnostics["tests"]["basic_command"] = {
                        "success": False,
                        "error": str(e)
                    }
                
                # Teste de interfaces
                try:
                    interfaces = await self.get_interfaces()
                    diagnostics["tests"]["interfaces"] = {
                        "success": True,
                        "count": len(interfaces)
                    }
                except Exception as e:
                    diagnostics["tests"]["interfaces"] = {
                        "success": False,
                        "error": str(e)
                    }
            
            return diagnostics
            
        except Exception as e:
            logger.error(f"Erro nos diagnósticos: {e}")
            return {"connection": False, "error": str(e)}
    
    # =============================================================================
    # MÉTODOS DE PARSING
    # =============================================================================
    
    def _parse_interfaces(self, output: str) -> List[Dict[str, Any]]:
        """Parse da saída de interfaces"""
        interfaces = []
        
        for line in output.split('\n'):
            line = line.strip()
            if not line or line.startswith('Interface') or line.startswith('---'):
                continue
            
            # Parse básico - implementar conforme formato real do NE8000
            parts = line.split()
            if len(parts) >= 3:
                interfaces.append({
                    "name": parts[0],
                    "status": parts[1] if len(parts) > 1 else "Unknown",
                    "protocol": parts[2] if len(parts) > 2 else "Unknown",
                    "description": " ".join(parts[3:]) if len(parts) > 3 else ""
                })
        
        return interfaces
    
    def _parse_pppoe_stats(self, output: str) -> Dict[str, Any]:
        """Parse das estatísticas PPPoE"""
        stats = {"active": 0, "peak": 0}
        
        # Implementar parsing específico do NE8000
        for line in output.split('\n'):
            if 'online' in line.lower() or 'active' in line.lower():
                # Extrair números da linha
                numbers = [int(s) for s in line.split() if s.isdigit()]
                if numbers:
                    stats["active"] = numbers[0]
                    if len(numbers) > 1:
                        stats["peak"] = numbers[1]
                break
        
        return stats
    
    def _parse_pppoe_detailed(self, results: List[str]) -> Dict[str, Any]:
        """Parse detalhado das estatísticas PPPoE"""
        stats = self._parse_pppoe_stats(results[0])
        
        # Adicionar dados do segundo comando se disponível
        if len(results) > 1:
            stats["total_sessions"] = stats["active"]  # Implementar parsing real
        
        return stats
    
    def _parse_system_metrics(self, results: List[str]) -> Dict[str, Any]:
        """Parse das métricas do sistema"""
        metrics = {
            "cpu": 0,
            "memory": 0,
            "uptime": "Unknown",
            "temperature": None
        }
        
        # Parse CPU
        if results[0]:
            for line in results[0].split('\n'):
                if 'cpu' in line.lower() and '%' in line:
                    numbers = [float(s.replace('%', '')) for s in line.split() if '%' in s]
                    if numbers:
                        metrics["cpu"] = numbers[0]
                    break
        
        # Parse Memory
        if results[1]:
            for line in results[1].split('\n'):
                if 'memory' in line.lower() and '%' in line:
                    numbers = [float(s.replace('%', '')) for s in line.split() if '%' in s]
                    if numbers:
                        metrics["memory"] = numbers[0]
                    break
        
        return metrics
    
    def _parse_traffic_data(self, output: str) -> Dict[str, Any]:
        """Parse dos dados de tráfego"""
        traffic = {
            "total_in": 0,
            "total_out": 0,
            "interfaces": []
        }
        
        # Implementar parsing específico do formato do NE8000
        # Por enquanto, retorno básico
        
        return traffic
    
    async def __aenter__(self):
        """Context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        await self.disconnect() 