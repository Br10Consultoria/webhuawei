"""
Coletor de tráfego de interfaces usando IF-MIB padrão
Baseado no template Interfaces SNMP
"""

import asyncio
import logging
import redis
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import os

# IMPORTS PARA PYSNMP v7.x
from pysnmp.hlapi.v1arch.asyncio import *
from pysnmp.hlapi.v1arch.asyncio import get_cmd, bulk_cmd, SnmpDispatcher, CommunityData, UdpTransportTarget, ObjectType, ObjectIdentity

logger = logging.getLogger(__name__)

@dataclass
class InterfaceTrafficConfig:
    """Configuração para coleta de tráfego de interfaces"""
    host: str
    port: int = 161
    community: str = "public"
    
    # OIDs IF-MIB padrão (do template interfaces)
    interface_discovery_oid: str = "1.3.6.1.2.1.2.2.1"
    
    # Discovery OIDs específicos
    if_oper_status_oid: str = "1.3.6.1.2.1.2.2.1.8"     # ifOperStatus
    if_admin_status_oid: str = "1.3.6.1.2.1.2.2.1.7"    # ifAdminStatus
    if_alias_oid: str = "1.3.6.1.2.1.31.1.1.1.18"       # ifAlias
    if_name_oid: str = "1.3.6.1.2.1.31.1.1.1.1"         # ifName
    if_descr_oid: str = "1.3.6.1.2.1.2.2.1.2"           # ifDescr
    if_type_oid: str = "1.3.6.1.2.1.2.2.1.3"            # ifType
    
    # Traffic OIDs (High Capacity - 64 bits)
    if_hc_in_octets_oid: str = "1.3.6.1.2.1.31.1.1.1.6"  # ifHCInOctets
    if_hc_out_octets_oid: str = "1.3.6.1.2.1.31.1.1.1.10" # ifHCOutOctets
    
    # Filtros para interfaces relevantes
    interface_name_filter: str = r"GigabitEthernet.*|Virtual-Template.*|Loopback.*"
    exclude_loopback: bool = True
    
    @classmethod
    def from_env(cls):
        return cls(
            host=os.getenv("HUAWEI_SNMP_HOST", "192.168.1.1"),
            port=int(os.getenv("HUAWEI_SNMP_PORT", "161")),
            community=os.getenv("HUAWEI_SNMP_COMMUNITY", "public"),
            interface_name_filter=os.getenv("INTERFACE_NAME_FILTER", r"GigabitEthernet.*|Virtual-Template.*"),
            exclude_loopback=os.getenv("EXCLUDE_LOOPBACK", "true").lower() == "true"
        )

@dataclass
class NetworkInterface:
    """Estrutura de dados para interface de rede"""
    snmp_index: str
    name: str
    description: str
    alias: str
    if_type: int
    admin_status: int
    oper_status: int
    in_octets: int = 0
    out_octets: int = 0
    in_bps: float = 0.0
    out_bps: float = 0.0
    last_update: str = ""
    status: str = "unknown"

class InterfaceTrafficCollector:
    """Coletor de tráfego de interfaces usando IF-MIB"""
    
    def __init__(self, config: InterfaceTrafficConfig, redis_client: redis.Redis):
        self.config = config
        self.redis = redis_client
        self.previous_data = {}  # Para calcular delta de tráfego
        
    async def discover_interfaces(self) -> Dict[str, NetworkInterface]:
        """🔍 Descobrir interfaces de rede (replica template Zabbix)"""
        try:
            logger.info("🔍 Descobrindo interfaces de rede...")
            
            # Coletar todos os dados de discovery em paralelo
            discovery_tasks = [
                self._snmp_walk(self.config.if_oper_status_oid),
                self._snmp_walk(self.config.if_admin_status_oid),
                self._snmp_walk(self.config.if_alias_oid),
                self._snmp_walk(self.config.if_name_oid),
                self._snmp_walk(self.config.if_descr_oid),
                self._snmp_walk(self.config.if_type_oid)
            ]
            
            results = await asyncio.gather(*discovery_tasks, return_exceptions=True)
            
            oper_status_data = results[0] if not isinstance(results[0], Exception) else {}
            admin_status_data = results[1] if not isinstance(results[1], Exception) else {}
            alias_data = results[2] if not isinstance(results[2], Exception) else {}
            name_data = results[3] if not isinstance(results[3], Exception) else {}
            descr_data = results[4] if not isinstance(results[4], Exception) else {}
            type_data = results[5] if not isinstance(results[5], Exception) else {}
            
            interfaces = {}
            
            # Processar interfaces descobertas
            for oid, oper_status in oper_status_data.items():
                snmp_index = oid.split('.')[-1]
                
                # Obter dados de outras tabelas
                name = name_data.get(f"{self.config.if_name_oid}.{snmp_index}", f"Interface{snmp_index}")
                description = descr_data.get(f"{self.config.if_descr_oid}.{snmp_index}", "")
                alias = alias_data.get(f"{self.config.if_alias_oid}.{snmp_index}", "")
                admin_status = int(admin_status_data.get(f"{self.config.if_admin_status_oid}.{snmp_index}", 0))
                if_type = int(type_data.get(f"{self.config.if_type_oid}.{snmp_index}", 0))
                
                # Aplicar filtros (replica lógica do template Zabbix)
                if not self._should_include_interface(name, description, alias, int(oper_status), admin_status):
                    continue
                
                interface = NetworkInterface(
                    snmp_index=snmp_index,
                    name=name,
                    description=description,
                    alias=alias,
                    if_type=if_type,
                    admin_status=admin_status,
                    oper_status=int(oper_status),
                    last_update=datetime.now().isoformat(),
                    status=self._get_interface_status(int(oper_status), admin_status)
                )
                
                interfaces[snmp_index] = interface
                
                logger.debug(f"📡 Interface: {name} ({description}) - Status: {interface.status}")
            
            logger.info(f"✅ Descobertas {len(interfaces)} interfaces relevantes")
            return interfaces
            
        except Exception as e:
            logger.error(f"❌ Erro na descoberta de interfaces: {e}")
            return {}
    
    async def collect_traffic_data(self, interfaces: Dict[str, NetworkInterface]) -> Dict[str, NetworkInterface]:
        """📊 Coletar dados de tráfego para interfaces"""
        try:
            logger.debug("📊 Coletando dados de tráfego...")
            
            if not interfaces:
                return {}
            
            # Coletar dados de tráfego para todas as interfaces
            in_octets_tasks = []
            out_octets_tasks = []
            
            for snmp_index in interfaces.keys():
                in_octets_tasks.append(self._snmp_get(f"{self.config.if_hc_in_octets_oid}.{snmp_index}"))
                out_octets_tasks.append(self._snmp_get(f"{self.config.if_hc_out_octets_oid}.{snmp_index}"))
            
            # Executar todas as coletas em paralelo
            in_results = await asyncio.gather(*in_octets_tasks, return_exceptions=True)
            out_results = await asyncio.gather(*out_octets_tasks, return_exceptions=True)
            
            # Processar resultados
            current_time = datetime.now()
            updated_interfaces = {}
            
            for i, (snmp_index, interface) in enumerate(interfaces.items()):
                # Obter valores de tráfego
                in_octets = int(in_results[i]) if not isinstance(in_results[i], Exception) and in_results[i] else 0
                out_octets = int(out_results[i]) if not isinstance(out_results[i], Exception) and out_results[i] else 0
                
                # Calcular BPS (bits per second) baseado em dados anteriores
                in_bps, out_bps = self._calculate_bps(snmp_index, in_octets, out_octets, current_time)
                
                # Atualizar interface
                interface.in_octets = in_octets
                interface.out_octets = out_octets
                interface.in_bps = in_bps
                interface.out_bps = out_bps
                interface.last_update = current_time.isoformat()
                
                updated_interfaces[snmp_index] = interface
            
            return updated_interfaces
            
        except Exception as e:
            logger.error(f"❌ Erro na coleta de tráfego: {e}")
            return interfaces
    
    async def collect_all_interfaces(self) -> Dict:
        """🎯 Coletar todos os dados de interfaces"""
        try:
            start_time = datetime.now()
            
            # Descobrir interfaces
            interfaces = await self.discover_interfaces()
            
            if not interfaces:
                return {"success": False, "error": "Nenhuma interface descoberta"}
            
            # Coletar dados de tráfego
            interfaces_with_traffic = await self.collect_traffic_data(interfaces)
            
            # Calcular estatísticas
            total_interfaces = len(interfaces_with_traffic)
            active_interfaces = len([i for i in interfaces_with_traffic.values() if i.status == "up"])
            total_in_bps = sum([i.in_bps for i in interfaces_with_traffic.values()])
            total_out_bps = sum([i.out_bps for i in interfaces_with_traffic.values()])
            
            result = {
                "timestamp": datetime.now().isoformat(),
                "collection_time": (datetime.now() - start_time).total_seconds(),
                "summary": {
                    "total_interfaces": total_interfaces,
                    "active_interfaces": active_interfaces,
                    "inactive_interfaces": total_interfaces - active_interfaces,
                    "total_in_bps": total_in_bps,
                    "total_out_bps": total_out_bps,
                    "total_in_mbps": round(total_in_bps / 1_000_000, 2),
                    "total_out_mbps": round(total_out_bps / 1_000_000, 2)
                },
                "interfaces": {k: asdict(v) for k, v in interfaces_with_traffic.items()}
            }
            
            # Salvar no Redis
            await self.save_to_redis(result)
            
            logger.info(f"✅ Coleta de interfaces: {total_interfaces} interfaces, "
                       f"{active_interfaces} ativas, "
                       f"IN: {result['summary']['total_in_mbps']}Mbps, "
                       f"OUT: {result['summary']['total_out_mbps']}Mbps")
            
            return {"success": True, **result}
            
        except Exception as e:
            logger.error(f"❌ Erro na coleta completa de interfaces: {e}")
            return {"success": False, "error": str(e)}
    
    def _should_include_interface(self, name: str, description: str, alias: str, 
                                 oper_status: int, admin_status: int) -> bool:
        """🔍 Filtrar interfaces relevantes (replica lógica do template)"""
        import re
        
        # Excluir loopbacks se configurado
        if self.config.exclude_loopback:
            loopback_patterns = [
                r"^Software Loopback Interface",
                r"^NULL[0-9.]*$",
                r"^[Ll]o[0-9.]*$",
                r"^[Ss]ystem$",
                r"^Nu[0-9.]*$",
                r"^veth[0-9a-z]+$",
                r"docker[0-9]+",
                r"br-[a-z0-9]{12}"
            ]
            
            for pattern in loopback_patterns:
                if re.match(pattern, name, re.IGNORECASE):
                    return False
        
        # Incluir apenas interfaces que passam no filtro de nome
        if not re.search(self.config.interface_name_filter, name, re.IGNORECASE):
            return False
        
        # Excluir interfaces com status administrativo down (2)
        if admin_status == 2:
            return False
        
        # Excluir interfaces notPresent (6)
        if oper_status == 6:
            return False
        
        return True
    
    def _get_interface_status(self, oper_status: int, admin_status: int) -> str:
        """📊 Determinar status da interface"""
        if admin_status == 2:
            return "admin_down"
        elif oper_status == 1:
            return "up"
        elif oper_status == 2:
            return "down"
        elif oper_status == 5:
            return "dormant"
        elif oper_status == 6:
            return "not_present"
        else:
            return "unknown"
    
    def _calculate_bps(self, snmp_index: str, current_in: int, current_out: int, 
                      current_time: datetime) -> Tuple[float, float]:
        """📈 Calcular bits per second baseado em dados anteriores"""
        try:
            key = f"traffic_{snmp_index}"
            
            if key not in self.previous_data:
                # Primeira coleta - salvar dados e retornar 0
                self.previous_data[key] = {
                    "in_octets": current_in,
                    "out_octets": current_out,
                    "timestamp": current_time
                }
                return 0.0, 0.0
            
            # Calcular delta
            prev_data = self.previous_data[key]
            time_delta = (current_time - prev_data["timestamp"]).total_seconds()
            
            if time_delta <= 0:
                return 0.0, 0.0
            
            # Calcular bytes por segundo e converter para bits
            in_delta = current_in - prev_data["in_octets"]
            out_delta = current_out - prev_data["out_octets"]
            
            # Tratar rollover de contadores (contadores SNMP podem dar rollover)
            if in_delta < 0:
                in_delta += 2**64  # Assumir contador de 64 bits
            if out_delta < 0:
                out_delta += 2**64
            
            in_bps = (in_delta / time_delta) * 8  # bytes para bits
            out_bps = (out_delta / time_delta) * 8
            
            # Atualizar dados anteriores
            self.previous_data[key] = {
                "in_octets": current_in,
                "out_octets": current_out,
                "timestamp": current_time
            }
            
            return in_bps, out_bps
            
        except Exception as e:
            logger.error(f"❌ Erro no cálculo BPS para interface {snmp_index}: {e}")
            return 0.0, 0.0
    
    async def save_to_redis(self, data: Dict):
        """💾 Salvar dados de interfaces no Redis"""
        try:
            # 1. Dados completos de interfaces (TTL médio)
            interfaces_key = "network:interfaces"
            self.redis.setex(interfaces_key, 300, json.dumps(data))  # 5min
            
            # 2. Resumo de tráfego (TTL curto - para dashboard)
            summary_key = "network:traffic_summary"
            summary_data = {
                "timestamp": data["timestamp"],
                "collection_time": data["collection_time"],
                "summary": data["summary"]
            }
            self.redis.setex(summary_key, 60, json.dumps(summary_data))  # 1min
            
            # 3. Histórico de tráfego (manter 24h)
            history_key = "network:traffic_history"
            history_point = {
                "timestamp": data["timestamp"],
                "total_in_mbps": data["summary"]["total_in_mbps"],
                "total_out_mbps": data["summary"]["total_out_mbps"],
                "active_interfaces": data["summary"]["active_interfaces"]
            }
            
            self.redis.lpush(history_key, json.dumps(history_point))
            self.redis.ltrim(history_key, 0, 1439)  # 24h a cada minuto
            
            # 4. Dados por interface específica (para consultas detalhadas)
            for snmp_index, interface in data["interfaces"].items():
                iface_key = f"network:interface:{snmp_index}"
                self.redis.setex(iface_key, 600, json.dumps(interface))  # 10min
            
        except Exception as e:
            logger.error(f"❌ Erro ao salvar dados de interface no Redis: {e}")
    
    async def _snmp_get(self, oid: str) -> Optional[str]:
        """SNMP GET otimizado para pysnmp v7.x"""
        try:
            # Usar SnmpDispatcher ao invés de SnmpEngine
            dispatcher = SnmpDispatcher()
            transport_target = await UdpTransportTarget.create((self.config.host, self.config.port))
            
            errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
                dispatcher,
                CommunityData(self.config.community),
                transport_target,
                ObjectType(ObjectIdentity(oid))
            )
            
            dispatcher.close()
            
            if errorIndication or errorStatus:
                return None
            
            return str(varBinds[0][1])
            
        except Exception as e:
            logger.debug(f"❌ SNMP GET {oid}: {e}")
            return None
    
    async def _snmp_walk(self, oid: str) -> Dict[str, str]:
        """SNMP WALK otimizado para pysnmp v7.x"""
        try:
            results = {}
            
            # Usar SnmpDispatcher ao invés de SnmpEngine
            dispatcher = SnmpDispatcher()
            transport_target = await UdpTransportTarget.create((self.config.host, self.config.port))
            
            # Usar bulk_cmd para maior compatibilidade
            errorIndication, errorStatus, errorIndex, varBindTable = await bulk_cmd(
                dispatcher,
                CommunityData(self.config.community),
                transport_target,
                0, 50,  # nonRepeaters, maxRepetitions
                ObjectType(ObjectIdentity(oid))
            )
            
            dispatcher.close()
            
            if errorIndication or errorStatus:
                logger.error(f"❌ SNMP BULK error: {errorIndication or errorStatus}")
                return {}
            
            # Processar resultados do bulk_cmd
            for varBindTableRow in varBindTable:
                for varBind in varBindTableRow:
                    oid_str = str(varBind[0])
                    value_str = str(varBind[1])
                    
                    # Verificar se ainda estamos dentro da árvore OID desejada
                    if not oid_str.startswith(oid):
                        break
                        
                    results[oid_str] = value_str
                    
                    # Limitar número de resultados para performance
                    max_interfaces = int(os.getenv("MAX_INTERFACES_DISCOVERY", "100"))
                    if len(results) >= max_interfaces:
                        break
                        
                if len(results) >= max_interfaces:
                    break
            
            return results
            
        except Exception as e:
            logger.error(f"❌ SNMP WALK {oid}: {e}")
            return {}

# Instância global
_interface_collector = None

def get_interface_traffic_collector() -> InterfaceTrafficCollector:
    """Obter coletor de tráfego de interfaces"""
    global _interface_collector
    if _interface_collector is None:
        config = InterfaceTrafficConfig.from_env()
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            decode_responses=True
        )
        _interface_collector = InterfaceTrafficCollector(config, redis_client)
    return _interface_collector 