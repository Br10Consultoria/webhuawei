"""
APIs especializadas para dados híbridos
Otimizadas para performance máxima
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
import redis
from modules.hybrid_scheduler import get_scheduler_stats

logger = logging.getLogger(__name__)

# Cliente Redis global para APIs
_redis_client = None

def get_redis_client() -> redis.Redis:
    """Obter cliente Redis otimizado"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )
    return _redis_client

# ============================================================================
# APIS PARA DASHBOARD (DADOS RÁPIDOS)
# ============================================================================

async def dashboard_summary():
    """🏠 Dashboard - resumo ultra-rápido"""
    try:
        redis_client = get_redis_client()
        
        # Buscar dados essenciais em paralelo
        pipeline = redis_client.pipeline()
        pipeline.get("huawei:summary")                # PPPoE summary
        pipeline.get("network:traffic_summary")       # Traffic summary
        
        results = pipeline.execute()
        
        pppoe_data = json.loads(results[0]) if results[0] else {}
        traffic_data = json.loads(results[1]) if results[1] else {}
        
        # Combinar dados para dashboard
        return {
            "success": True,
            "source": "redis_optimized",
            "dashboard": {
                "pppoe": {
                    "total_users": pppoe_data.get("totals", {}).get("pppoe_online", 0),
                    "active_interfaces": pppoe_data.get("summary", {}).get("active_interfaces", 0),
                    "collection_time": pppoe_data.get("collection_time", 0)
                },
                "network": {
                    "total_interfaces": traffic_data.get("summary", {}).get("total_interfaces", 0),
                    "active_interfaces": traffic_data.get("summary", {}).get("active_interfaces", 0),
                    "total_in_mbps": traffic_data.get("summary", {}).get("total_in_mbps", 0),
                    "total_out_mbps": traffic_data.get("summary", {}).get("total_out_mbps", 0),
                    "collection_time": traffic_data.get("collection_time", 0)
                },
                "timestamp": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Erro no dashboard summary: {e}")
        return {"success": False, "error": str(e)}

async def dashboard_charts_data():
    """📈 Dados para gráficos do dashboard"""
    try:
        redis_client = get_redis_client()
        
        # Buscar históricos
        pppoe_history = redis_client.lrange("huawei:history", 0, 119)  # Últimas 2h (a cada 30s)
        traffic_history = redis_client.lrange("network:traffic_history", 0, 119)  # Últimas 2h (a cada 60s)
        
        # Processar dados para gráficos
        pppoe_chart = []
        for record in reversed(pppoe_history):  # Ordem cronológica
            try:
                data = json.loads(record)
                pppoe_chart.append({
                    "time": data["timestamp"],
                    "users": data["total_users"]
                })
            except:
                continue
        
        traffic_chart = []
        for record in reversed(traffic_history):
            try:
                data = json.loads(record)
                traffic_chart.append({
                    "time": data["timestamp"],
                    "in_mbps": data["total_in_mbps"],
                    "out_mbps": data["total_out_mbps"]
                })
            except:
                continue
        
        return {
            "success": True,
            "charts": {
                "pppoe_users": pppoe_chart[-60:],    # Última hora
                "network_traffic": traffic_chart[-60:] # Última hora
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Erro nos dados de gráficos: {e}")
        return {"success": False, "error": str(e)}

# ============================================================================
# APIS PARA CONSULTAS DETALHADAS
# ============================================================================

async def pppoe_detailed_interfaces():
    """🔍 PPPoE - interfaces detalhadas"""
    try:
        redis_client = get_redis_client()
        data = redis_client.get("huawei:interfaces")
        
        if not data:
            return {"success": False, "error": "Dados PPPoE não disponíveis"}
        
        interfaces = json.loads(data)
        
        # Converter para lista ordenada por usuários
        interface_list = sorted(
            [{"snmp_index": k, **v} for k, v in interfaces.items()],
            key=lambda x: x.get("quantity", 0),
            reverse=True
        )
        
        return {
            "success": True,
            "source": "redis_detailed",
            "total_interfaces": len(interface_list),
            "interfaces": interface_list[:50]  # Top 50
        }
        
    except Exception as e:
        logger.error(f"❌ Erro nas interfaces PPPoE detalhadas: {e}")
        return {"success": False, "error": str(e)}

async def network_interfaces_traffic():
    """📡 Tráfego de interfaces de rede"""
    try:
        redis_client = get_redis_client()
        data = redis_client.get("network:interfaces")
        
        if not data:
            return {"success": False, "error": "Dados de tráfego não disponíveis"}
        
        interfaces_data = json.loads(data)
        interfaces = interfaces_data.get("interfaces", {})
        
        # Converter para lista ordenada por tráfego
        interface_list = []
        for snmp_index, iface in interfaces.items():
            total_mbps = (iface.get("in_bps", 0) + iface.get("out_bps", 0)) / 1_000_000
            interface_list.append({
                "snmp_index": snmp_index,
                "name": iface.get("name", ""),
                "status": iface.get("status", "unknown"),
                "in_mbps": round(iface.get("in_bps", 0) / 1_000_000, 2),
                "out_mbps": round(iface.get("out_bps", 0) / 1_000_000, 2),
                "total_mbps": round(total_mbps, 2),
                "last_update": iface.get("last_update", "")
            })
        
        # Ordenar por tráfego total
        interface_list.sort(key=lambda x: x["total_mbps"], reverse=True)
        
        return {
            "success": True,
            "source": "redis_traffic",
            "summary": interfaces_data.get("summary", {}),
            "interfaces": interface_list[:30]  # Top 30
        }
        
    except Exception as e:
        logger.error(f"❌ Erro no tráfego de interfaces: {e}")
        return {"success": False, "error": str(e)}

# ============================================================================
# APIS DE SISTEMA E MONITORAMENTO
# ============================================================================

async def system_status():
    """⚡ Status completo do sistema híbrido"""
    try:
        redis_client = get_redis_client()
        
        # Verificar conectividade Redis
        redis_ping = redis_client.ping()
        
        # Obter stats do scheduler
        scheduler_stats = get_scheduler_stats()
        
        # Verificar idade dos dados
        pppoe_data = redis_client.get("huawei:summary")
        traffic_data = redis_client.get("network:traffic_summary")
        
        pppoe_age = 0
        traffic_age = 0
        
        if pppoe_data:
            pppoe_ts = json.loads(pppoe_data).get("timestamp")
            if pppoe_ts:
                pppoe_age = (datetime.now() - datetime.fromisoformat(pppoe_ts)).total_seconds()
        
        if traffic_data:
            traffic_ts = json.loads(traffic_data).get("timestamp")
            if traffic_ts:
                traffic_age = (datetime.now() - datetime.fromisoformat(traffic_ts)).total_seconds()
        
        # Determinar status geral
        overall_status = "healthy"
        if pppoe_age > 120 or traffic_age > 180:  # Dados antigos
            overall_status = "degraded"
        if pppoe_age > 300 or traffic_age > 600:  # Dados muito antigos
            overall_status = "unhealthy"
        
        return {
            "success": True,
            "status": overall_status,
            "components": {
                "redis": "connected" if redis_ping else "disconnected",
                "scheduler": "running" if scheduler_stats["running"] else "stopped",
                "pppoe_collector": "active" if pppoe_age < 120 else "stale",
                "traffic_collector": "active" if traffic_age < 180 else "stale"
            },
            "data_age": {
                "pppoe_seconds": pppoe_age,
                "traffic_seconds": traffic_age
            },
            "scheduler_stats": scheduler_stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Erro no status do sistema: {e}")
        return {"success": False, "error": str(e)} 