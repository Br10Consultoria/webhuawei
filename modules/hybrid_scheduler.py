"""
Scheduler híbrido para coleta SNMP otimizada
Coleta PPPoE + Tráfego de Interfaces em paralelo
"""

import asyncio
import logging
import threading
import time
import json
from datetime import datetime
from typing import Dict, Optional
import os

logger = logging.getLogger(__name__)

# Estado global do scheduler
_scheduler_running = False
_scheduler_thread = None
_scheduler_stats = {
    "started_at": None,
    "collections": 0,
    "errors": 0,
    "last_collection": None,
    "status": "stopped"
}

def get_scheduler_stats() -> Dict:
    """Obter estatísticas do scheduler"""
    return _scheduler_stats.copy()

async def collect_hybrid_data():
    """Executar coleta híbrida de dados"""
    global _scheduler_stats
    
    try:
        # Verificar se os coletores estão disponíveis
        try:
            from modules.huawei_hybrid_collector import get_hybrid_collector
            from modules.interface_traffic_collector import get_interface_traffic_collector
            
            pppoe_collector = get_hybrid_collector()
            traffic_collector = get_interface_traffic_collector()
            
        except ImportError as e:
            logger.warning(f"⚠️  Coletores não disponíveis: {e}")
            return False
        
        # Executar coletas em paralelo
        logger.info("🔄 Executando coleta híbrida...")
        
        pppoe_task = asyncio.create_task(pppoe_collector.collect_all_data())
        traffic_task = asyncio.create_task(traffic_collector.collect_all_interfaces())
        
        # Aguardar ambas as coletas
        await asyncio.gather(pppoe_task, traffic_task, return_exceptions=True)
        
        _scheduler_stats["collections"] += 1
        _scheduler_stats["last_collection"] = datetime.now().isoformat()
        
        logger.info("✅ Coleta híbrida concluída")
        return True
        
    except Exception as e:
        _scheduler_stats["errors"] += 1
        logger.error(f"❌ Erro na coleta híbrida: {e}")
        return False

def scheduler_loop():
    """Loop principal do scheduler (roda em thread separada)"""
    global _scheduler_running, _scheduler_stats
    
    logger.info("🚀 Scheduler híbrido iniciado")
    _scheduler_stats["status"] = "running"
    
    interval = int(os.getenv("HYBRID_COLLECTION_INTERVAL", "30"))
    
    while _scheduler_running:
        try:
            # Executar coleta usando asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(collect_hybrid_data())
            loop.close()
            
            # Aguardar próximo ciclo
            time.sleep(interval)
            
        except Exception as e:
            logger.error(f"❌ Erro no loop do scheduler: {e}")
            time.sleep(5)  # Aguardar antes de tentar novamente

def start_hybrid_collection():
    """Iniciar coleta híbrida em background"""
    global _scheduler_running, _scheduler_thread, _scheduler_stats
    
    if _scheduler_running:
        logger.warning("⚠️  Scheduler já está rodando")
        return
    
    _scheduler_running = True
    _scheduler_stats["started_at"] = datetime.now().isoformat()
    _scheduler_stats["status"] = "starting"
    
    # Iniciar thread do scheduler
    _scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    _scheduler_thread.start()
    
    logger.info("✅ Coleta híbrida iniciada em background")

def stop_hybrid_collection():
    """Parar coleta híbrida"""
    global _scheduler_running, _scheduler_stats
    
    if not _scheduler_running:
        logger.warning("⚠️  Scheduler não está rodando")
        return
    
    _scheduler_running = False
    _scheduler_stats["status"] = "stopped"
    
    logger.info("🛑 Coleta híbrida parada")