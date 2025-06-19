"""
Coletor híbrido principal para dados PPPoE Huawei
Combina dados totais + detalhados de forma otimizada
"""

import asyncio
import logging
import redis
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import os
# IMPORTS PARA PYSNMP v7.x
from pysnmp.hlapi.v1arch.asyncio import *
from pysnmp.hlapi.v1arch.asyncio import get_cmd, bulk_cmd, SnmpDispatcher, CommunityData, UdpTransportTarget, ObjectType, ObjectIdentity

logger = logging.getLogger(__name__)

@dataclass
class HuaweiHybridConfig:
    """Configuração para coleta híbrida Huawei"""
    host: str
    port: int = 161
    community: str = "public"
    
    # OIDs Template 1 (Discovery - Detalhados por interface)
    detail_name_oid: str = "1.3.6.1.4.1.2011.5.25.40.1.1.13.1.3"
    detail_quant_oid: str = "1.3.6.1.4.1.2011.5.25.40.1.1.13.1.4"
    
    # OIDs Template 2 (Totais - Dashboard)
    total_pppoe_oid: str = "1.3.6.1.4.1.2011.5.2.1.14.1.2.0"       # Total PPPoE
    total_dualstack_oid: str = "1.3.6.1.4.1.2011.5.2.1.14.1.17.0"  # DualStack
    total_ipv4_oid: str = "1.3.6.1.4.1.2011.5.2.1.14.1.15.0"       # IPv4
    
    @classmethod
    def from_env(cls):
        return cls(
            host=os.getenv("HUAWEI_SNMP_HOST", "192.168.1.1"),
            port=int(os.getenv("HUAWEI_SNMP_PORT", "161")),
            community=os.getenv("HUAWEI_SNMP_COMMUNITY", "public")
        )

class HuaweiHybridCollector:
    """Coletor que combina dados totais E detalhados de PPPoE"""
    
    def __init__(self, config: HuaweiHybridConfig, redis_client: redis.Redis):
        self.config = config
        self.redis = redis_client
        
    async def collect_all_data(self) -> Dict:
        """🎯 Coletar AMBOS os tipos de dados em paralelo"""
        try:
            start_time = datetime.now()
            
            # Executar ambas as coletas em paralelo para máxima eficiência
            total_task = self.collect_total_metrics()
            detail_task = self.collect_detailed_interfaces()
            
            total_data, detail_data = await asyncio.gather(
                total_task, detail_task, return_exceptions=True
            )
            
            # Verificar erros
            if isinstance(total_data, Exception):
                logger.error(f"❌ Erro na coleta total: {total_data}")
                total_data = {}
            
            if isinstance(detail_data, Exception):
                logger.error(f"❌ Erro na coleta detalhada: {detail_data}")
                detail_data = {}
            
            # Combinar dados
            combined_data = {
                "timestamp": datetime.now().isoformat(),
                "collection_time": (datetime.now() - start_time).total_seconds(),
                
                # Dados TOTAIS (para dashboard)
                "totals": {
                    "pppoe_online": total_data.get("pppoe_online", 0),
                    "pppoe_dualstack": total_data.get("pppoe_dualstack", 0),
                    "pppoe_ipv4": total_data.get("pppoe_ipv4", 0),
                    "last_update": datetime.now().isoformat()
                },
                
                # Dados DETALHADOS (para consultas específicas)
                "interfaces": detail_data.get("interfaces", {}),
                "interface_summary": {
                    "total_interfaces": len(detail_data.get("interfaces", {})),
                    "active_interfaces": len([
                        i for i in detail_data.get("interfaces", {}).values() 
                        if i.get("quantity", 0) > 0
                    ]),
                    "total_users_detailed": sum([
                        i.get("quantity", 0) 
                        for i in detail_data.get("interfaces", {}).values()
                    ])
                }
            }
            
            # Salvar no Redis com diferentes estratégias
            await self.save_to_redis(combined_data)
            
            logger.info(f"✅ Coleta híbrida PPPoE: Total={combined_data['totals']['pppoe_online']}, "
                       f"Detalhado={combined_data['interface_summary']['total_users_detailed']}, "
                       f"Interfaces={combined_data['interface_summary']['total_interfaces']}")
            
            return {"success": True, **combined_data}
            
        except Exception as e:
            logger.error(f"❌ Erro na coleta híbrida: {e}")
            return {"success": False, "error": str(e)}
    
    async def collect_total_metrics(self) -> Dict:
        """📊 Coletar métricas totais (Template 2 - rápido)"""
        try:
            logger.debug("📊 Coletando métricas totais PPPoE...")
            
            # Coletar todos os OIDs totais em paralelo
            tasks = [
                self._snmp_get(self.config.total_pppoe_oid),
                self._snmp_get(self.config.total_dualstack_oid),
                self._snmp_get(self.config.total_ipv4_oid)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            return {
                "pppoe_online": int(results[0]) if not isinstance(results[0], Exception) and results[0] else 0,
                "pppoe_dualstack": int(results[1]) if not isinstance(results[1], Exception) and results[1] else 0,
                "pppoe_ipv4": int(results[2]) if not isinstance(results[2], Exception) and results[2] else 0
            }
            
        except Exception as e:
            logger.error(f"❌ Erro na coleta total: {e}")
            return {}
    
    async def collect_detailed_interfaces(self) -> Dict:
        """🔍 Coletar dados detalhados por interface (Template 1)"""
        try:
            logger.debug("🔍 Coletando dados detalhados por interface...")
            
            # Discovery das interfaces em paralelo
            names_task = self._snmp_walk(self.config.detail_name_oid)
            quantities_task = self._snmp_walk(self.config.detail_quant_oid)
            
            names, quantities = await asyncio.gather(names_task, quantities_task)
            
            interfaces = {}
            
            for oid, name in names.items():
                snmp_index = oid.split('.')[-1]
                quantity_oid = f"{self.config.detail_quant_oid}.{snmp_index}"
                quantity = int(quantities.get(quantity_oid, 0))
                
                interfaces[snmp_index] = {
                    "snmp_index": snmp_index,
                    "name": str(name),
                    "quantity": quantity,
                    "status": "active" if quantity > 0 else "inactive",
                    "last_update": datetime.now().isoformat()
                }
            
            return {"interfaces": interfaces}
            
        except Exception as e:
            logger.error(f"❌ Erro na coleta detalhada: {e}")
            return {}
    
    async def save_to_redis(self, data: Dict):
        """💾 Salvar dados no Redis com estratégias otimizadas"""
        try:
            # TTLs otimizados por tipo de uso
            ttl_dashboard = int(os.getenv("REDIS_TTL_DASHBOARD", "60"))
            ttl_details = int(os.getenv("REDIS_TTL_DETAILS", "300"))
            
            # 1. Dados TOTAIS (TTL curto - para dashboard)
            totals_key = "huawei:totals"
            self.redis.setex(totals_key, ttl_dashboard, json.dumps(data["totals"]))
            
            # 2. Dados DETALHADOS (TTL médio - para consultas)
            details_key = "huawei:interfaces"
            self.redis.setex(details_key, ttl_details, json.dumps(data["interfaces"]))
            
            # 3. RESUMO GERAL (TTL curto - para dashboard)
            summary_key = "huawei:summary"
            summary_data = {
                "timestamp": data["timestamp"],
                "collection_time": data["collection_time"],
                "totals": data["totals"],
                "summary": data["interface_summary"]
            }
            self.redis.setex(summary_key, ttl_dashboard, json.dumps(summary_data))
            
            # 4. HISTÓRICO (manter 24h)
            history_key = "huawei:history"
            history_point = {
                "timestamp": data["timestamp"],
                "total_users": data["totals"]["pppoe_online"],
                "active_interfaces": data["interface_summary"]["active_interfaces"],
                "detailed_total": data["interface_summary"]["total_users_detailed"]
            }
            
            self.redis.lpush(history_key, json.dumps(history_point))
            self.redis.ltrim(history_key, 0, 2879)  # 24h a cada 30s
            
        except Exception as e:
            logger.error(f"❌ Erro ao salvar no Redis: {e}")
    
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
_hybrid_collector = None

def get_hybrid_collector() -> HuaweiHybridCollector:
    """Obter coletor híbrido"""
    global _hybrid_collector
    if _hybrid_collector is None:
        config = HuaweiHybridConfig.from_env()
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            decode_responses=True
        )
        _hybrid_collector = HuaweiHybridCollector(config, redis_client)
    return _hybrid_collector