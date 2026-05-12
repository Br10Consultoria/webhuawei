"""
Sistema Híbrido de Monitoramento NE8000 - PPPoE + Tráfego de Interfaces
Coleta direta via SNMP + Sistema original SSH
"""

from datetime import datetime
from fastapi import Request, Form
from fastapi.responses import HTMLResponse

# Importar módulos locais originais
from modules.config import setup_logging, load_environment, create_app, CACHE_TIMEOUTS
from modules.ssh_connection import get_ssh_connection
from modules.cache_manager import get_cache
from modules.web_routes import (
    login_page, login_post, logout,
    dashboard, pppoe_page, bandwidth_graph_page, pppoe_history_page,
    interfaces_pppoe_page, interfaces_traffic_page, setup_2fa_page
)
from modules import audit_log as _audit_log
from modules.api_routes import (
    get_online_total, pppoe_query, pppoe_disconnect,
    get_connection_status, reconnect, bandwidth_data, pppoe_history, pppoe_by_interface,
    pppoe_interfaces_real, pppoe_users_by_interface, discover_physical_interfaces,
    get_ip_pool_usage
)

# Importar módulos híbridos (novos)
try:
    from modules.hybrid_scheduler import start_hybrid_collection, stop_hybrid_collection
    from modules.hybrid_api_routes import (
        dashboard_summary, dashboard_charts_data,
        pppoe_detailed_interfaces, network_interfaces_traffic,
        system_status
    )
    HYBRID_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Módulos híbridos não disponíveis: {e}")
    HYBRID_AVAILABLE = False

# Configurar sistema
load_environment()
logger = setup_logging()
app = create_app()

logger.info("🚀 Iniciando NE8000 Sistema Híbrido")
logger.info("📦 Módulos carregados: ssh_connection, pppoe_parser, cache_manager")
if HYBRID_AVAILABLE:
    logger.info("🔧 Módulos híbridos: DISPONÍVEIS")
else:
    logger.warning("⚠️  Módulos híbridos: NÃO DISPONÍVEIS")

# ============================================================================
# EVENTOS DE STARTUP/SHUTDOWN (apenas se híbrido disponível)
# ============================================================================

if HYBRID_AVAILABLE:
    @app.on_event("startup")
    async def startup_event():
        """🚀 Inicialização do sistema híbrido"""
        logger.info("🚀 Iniciando sistema híbrido...")
        try:
            start_hybrid_collection()
            logger.info("📡 Coleta híbrida iniciada (PPPoE + Tráfego)")
        except Exception as e:
            logger.error(f"❌ Erro ao iniciar coleta híbrida: {e}")

    @app.on_event("shutdown") 
    async def shutdown_event():
        """🛑 Encerramento do sistema"""
        logger.info("🛑 Encerrando sistema híbrido...")
        try:
            stop_hybrid_collection()
        except Exception as e:
            logger.error(f"❌ Erro ao parar coleta híbrida: {e}")

# ============================================================================
# ROTAS WEB (HTML) - SISTEMA ORIGINAL
# ============================================================================

@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
async def route_login_page(request: Request, error: str = None):
    """Página de login"""
    return await login_page(request, error)

@app.post("/login")
async def route_login_post(request: Request, username: str = Form(...), password: str = Form(...), totp_token: str = Form(default="")):
    """Processar login com suporte a 2FA"""
    return await login_post(request, username, password, totp_token)

@app.get("/setup-2fa", response_class=HTMLResponse)
async def route_setup_2fa(request: Request):
    """Página de configuração do 2FA"""
    return await setup_2fa_page(request)

@app.get("/logout")
async def route_logout(request: Request):
    """Logout"""
    return await logout(request)

@app.get("/dashboard", response_class=HTMLResponse)
async def route_dashboard(request: Request):
    """Dashboard principal original"""
    return await dashboard(request)

@app.get("/pppoe", response_class=HTMLResponse)
async def route_pppoe_page(request: Request):
    """Página PPPoE original"""
    return await pppoe_page(request)

@app.get("/bandwidth_graph/{username}", response_class=HTMLResponse)
async def route_bandwidth_graph_page(request: Request, username: str):
    """Página de gráfico de banda"""
    return await bandwidth_graph_page(request, username)

@app.get("/pppoe_history/{username}", response_class=HTMLResponse)
async def route_pppoe_history_page(request: Request, username: str):
    """Página de histórico PPPoE"""
    return await pppoe_history_page(request, username)

@app.get("/interfaces/pppoe", response_class=HTMLResponse)
async def route_interfaces_pppoe_page(request: Request):
    """Página de interfaces PPPoE detalhadas"""
    return await interfaces_pppoe_page(request)

@app.get("/interfaces/traffic", response_class=HTMLResponse) 
async def route_interfaces_traffic_page(request: Request):
    """Página de tráfego de interfaces"""
    return await interfaces_traffic_page(request)

# ============================================================================
# ROTAS WEB (HTML) - SISTEMA HÍBRIDO
# ============================================================================

if HYBRID_AVAILABLE:
    @app.get("/hybrid", response_class=HTMLResponse)
    async def route_hybrid_dashboard(request: Request):
        """Página: Dashboard híbrido principal"""
        from fastapi.templating import Jinja2Templates
        templates = Jinja2Templates(directory="templates")
        return templates.TemplateResponse("hybrid_dashboard.html", {"request": request})

# ============================================================================
# ROTAS API (JSON) - SISTEMA ORIGINAL
# ============================================================================

@app.get("/api/online_total")
async def route_get_online_total():
    """API: Obter total de usuários PPPoE online"""
    return await get_online_total()

@app.post("/api/pppoe_query")
async def route_pppoe_query(request: Request, username: str = Form(...)):
    """API: Consultar usuário PPPoE específico"""
    return await pppoe_query(username, request=request)

@app.post("/api/pppoe_disconnect")
async def route_pppoe_disconnect(request: Request, username: str = Form(...)):
    """API: Desconectar usuário PPPoE"""
    return await pppoe_disconnect(username, request=request)

@app.get("/api/connection_status")
async def route_get_connection_status():
    """API: Status da conexão SSH"""
    return await get_connection_status()

@app.post("/api/reconnect")
async def route_reconnect():
    """API: Reconectar SSH"""
    return await reconnect()

@app.get("/api/bandwidth_data/{username}")
async def route_bandwidth_data(username: str):
    """API: Obter dados de banda do usuário"""
    return await bandwidth_data(username)

@app.get("/api/pppoe_history/{username}")
async def route_pppoe_history(username: str):
    """API: Obter histórico PPPoE do usuário"""
    return await pppoe_history(username)

@app.get("/api/pppoe_by_interface")
async def route_pppoe_by_interface():
    """API: Obter estatísticas PPPoE por interface"""
    return await pppoe_by_interface()

@app.get("/api/pppoe_interfaces_real")
async def route_pppoe_interfaces_real(slot: int = 0, interface: str = "", vlan: int = 0):
    """API: Contagem real de PPPoE por interface/VLAN via SSH"""
    from modules.api_routes import pppoe_interfaces_real
    return await pppoe_interfaces_real(slot=slot, interface=interface, vlan=vlan)

@app.get("/api/pppoe_users_by_interface")
async def route_pppoe_users_by_interface(slot: int = 0, interface: str = ""):
    """API: Lista de usuários PPPoE por interface via SSH"""
    from modules.api_routes import pppoe_users_by_interface
    return await pppoe_users_by_interface(slot=slot, interface=interface)

@app.get("/api/discover_interfaces")
async def route_discover_interfaces(slot: int = 0):
    """API: Descoberta automatica de interfaces fisicas GE com contagem PPPoE"""
    return await discover_physical_interfaces(slot=slot)

@app.get("/api/ip_pool_usage")
async def route_ip_pool_usage():
    """API: Uso de pools de IP (display ip-pool pool-usage)"""
    return await get_ip_pool_usage()

# ============================================================================
# ROTAS API (JSON) - SISTEMA HÍBRIDOO
# ============================================================================

if HYBRID_AVAILABLE:
    @app.get("/api/hybrid/dashboard")
    async def route_dashboard_summary():
        """🏠 API: Dashboard híbrido ultra-rápido"""
        return await dashboard_summary()

    @app.get("/api/hybrid/charts")
    async def route_dashboard_charts():
        """📈 API: Dados para gráficos do dashboard"""
        return await dashboard_charts_data()

    @app.get("/api/hybrid/pppoe/interfaces")
    async def route_pppoe_detailed():
        """🔍 API: Interfaces PPPoE detalhadas"""
        return await pppoe_detailed_interfaces()

    @app.get("/api/hybrid/network/traffic")
    async def route_network_traffic():
        """📡 API: Tráfego de interfaces de rede"""
        return await network_interfaces_traffic()

    @app.get("/api/hybrid/status")
    async def route_system_status():
        """⚡ API: Status completo do sistema híbrido"""
        return await system_status()

# ============================================================================
# ROTAS DE SISTEMA
# ============================================================================

@app.get("/api/cache_stats")
async def route_cache_stats():
    """API: Estatísticas do cache"""
    try:
        cache = get_cache()
        stats = cache.get_stats()
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            **stats
        }
    except Exception as e:
        logger.error(f"Erro ao obter stats do cache: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/cache_cleanup")
async def route_cache_cleanup():
    """API: Limpeza do cache"""
    try:
        cache = get_cache()
        removed = cache.cleanup_expired()
        return {
            "success": True,
            "items_removed": removed,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Erro na limpeza do cache: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/system_metrics")
async def route_system_metrics():
    """API: Métricas do sistema (CPU, RAM, etc.)"""
    try:
        import psutil
        return {
            "success": True,
            "cpu": round(psutil.cpu_percent(interval=1), 1),
            "memory": round(psutil.virtual_memory().percent, 1),
            "disk": round(psutil.disk_usage('/').percent, 1),
            "last_update": datetime.now().isoformat(),
            "timestamp": datetime.now().isoformat()
        }
    except ImportError:
        # Fallback case when psutil is not available
        return {
            "success": True,
            "cpu": 0,
            "memory": 0,
            "disk": 0,
            "last_update": datetime.now().isoformat(),
            "timestamp": datetime.now().isoformat(),
            "note": "psutil not available - showing dummy data"
        }
    except Exception as e:
        logger.error(f"Erro ao obter métricas do sistema: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/background_service_status")
async def route_background_service_status():
    """API: Status do serviço de background"""
    try:
        # Check if cache is being updated regularly
        cache = get_cache()
        stats = cache.get_stats()
        
        # Simple heuristic: if cache has recent data, service is likely running
        has_recent_data = stats.get("active_items", 0) > 0
        
        return {
            "success": True,
            "service": {
                "running": has_recent_data,
                "status": "active" if has_recent_data else "inactive",
                "last_check": datetime.now().isoformat()
            },
            "cache_stats": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Erro ao verificar status do serviço: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/force_cache_refresh")
async def route_force_cache_refresh():
    """API: Forçar atualização do cache"""
    try:
        # Clear relevant cache entries to force refresh
        cache = get_cache()
        
        # Remove entries related to PPPoE data
        cache.remove("pppoe_online_total")
        cache.remove("pppoe_interfaces_data")
        
        logger.info("Cache forçadamente limpo - próxima consulta será em tempo real")
        
        return {
            "success": True,
            "message": "Cache limpo com sucesso - dados serão atualizados na próxima consulta",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Erro ao forçar refresh do cache: {e}")
        return {"success": False, "error": str(e)}

@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    """Pagina de logs de auditoria"""
    from fastapi.responses import RedirectResponse as _Redirect
    if not request.session.get("logged_in"):
        return _Redirect(url="/login", status_code=302)
    from fastapi.templating import Jinja2Templates as _Jinja2
    _tpl = _Jinja2(directory="templates")
    context = {"request": request, "page": "logs", "session": request.session, "username": request.session.get("username", "")}
    return _tpl.TemplateResponse("logs.html", context)

@app.get("/api/audit_logs")
async def api_audit_logs(request: Request, limit: int = 300):
    """API: Retornar logs de auditoria recentes"""
    if not request.session.get("logged_in"):
        return {"success": False, "error": "Unauthorized"}
    logs = _audit_log.get_from_file(limit=limit)
    return {"success": True, "logs": logs, "count": len(logs)}

@app.get("/api/audit_stats")
async def api_audit_stats(request: Request):
    """API: Estatisticas dos logs de auditoria"""
    if not request.session.get("logged_in"):
        return {"success": False, "error": "Unauthorized"}
    stats = _audit_log.get_stats()
    return {"success": True, "stats": stats}

@app.get("/health")
async def route_health_check():
    """API: Health check da aplicação"""
    ssh_conn = get_ssh_connection()
    cache_stats = get_cache().get_stats()
    
    modules_loaded = [
        "ssh_connection",
        "pppoe_parser", 
        "cache_manager",
        "api_routes",
        "web_routes",
        "config"
    ]
    
    if HYBRID_AVAILABLE:
        modules_loaded.extend([
            "hybrid_scheduler",
            "hybrid_api_routes",
            "huawei_hybrid_collector",
            "interface_traffic_collector"
        ])
    
    return {
        "status": "ok",
        "version": "2.0.0-hybrid" if HYBRID_AVAILABLE else "2.0.0-basic-pppoe",
        "timestamp": datetime.now().isoformat(),
        "ssh_connected": ssh_conn.connected,
        "hybrid_available": HYBRID_AVAILABLE,
        "cache_active_items": cache_stats["active_items"],
        "cache_total_items": cache_stats["total_items"],
        "modules_loaded": modules_loaded,
        "routes_count": {
            "web_pages": 8 if HYBRID_AVAILABLE else 5,
            "api_endpoints": 13 if HYBRID_AVAILABLE else 8,
            "system_endpoints": 3
        },
        "cache_timeouts": CACHE_TIMEOUTS
    }

@app.get("/api/system_info")
async def route_system_info():
    """API: Informações do sistema"""
    features = {
        "pppoe_query": "Consultar usuários PPPoE pelo username",
        "pppoe_disconnect": "Desconectar usuários PPPoE",
        "connection_management": "Gerenciar conexão SSH",
        "cache_system": "Cache inteligente com TTL"
    }
    
    if HYBRID_AVAILABLE:
        features.update({
            "hybrid_collection": "Coleta SNMP direta para PPPoE e tráfego",
            "real_time_monitoring": "Monitoramento em tempo real",
            "interface_traffic": "Tráfego de interfaces via IF-MIB",
            "redis_cache": "Cache Redis otimizado"
        })
    
    return {
        "success": True,
        "system": {
            "name": "NE8000 Sistema Híbrido" if HYBRID_AVAILABLE else "NE8000 Simple Monitor",
            "version": "2.0.0-hybrid" if HYBRID_AVAILABLE else "2.0.0-basic-pppoe",
            "architecture": "hybrid" if HYBRID_AVAILABLE else "basic",
            "modules": len([
                "ssh_connection", "pppoe_parser", "cache_manager", "api_routes", "web_routes", "config"
            ] + (["hybrid_scheduler", "hybrid_api_routes", "collectors"] if HYBRID_AVAILABLE else [])),
        },
        "features": features,
        "improvements": [
            "✅ Sistema SSH original mantido",
            "✅ Consulta e desconexão de usuários PPPoE",
            "✅ Interface limpa e responsiva",
            "✅ Cache otimizado",
            "✅ Logs estruturados",
        ] + ([
            "✅ Coleta SNMP direta e otimizada",
            "✅ Monitoramento de tráfego de interfaces", 
            "✅ Dashboard híbrido em tempo real",
            "✅ Cache Redis de alta performance"
        ] if HYBRID_AVAILABLE else []),
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("🎯 Sistema carregado!")
    
    total_routes = 16 if HYBRID_AVAILABLE else 11
    system_type = "HÍBRIDO" if HYBRID_AVAILABLE else "BÁSICO"
    
    logger.info(f"📊 Total de rotas: {total_routes}")
    logger.info(f"🔧 Modo: {system_type}")
    
    if HYBRID_AVAILABLE:
        logger.info("🚀 Funcionalidades híbridas: PPPoE + Tráfego + Dashboard avançado")
    else:
        logger.info("📡 Funcionalidades básicas: SSH + PPPoE + Cache")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")