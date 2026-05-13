"""
Módulo de métricas do servidor host.
Coleta CPU, memória, disco e uptime via psutil.
Não depende de conexão SSH — lê o próprio sistema operacional.
"""
import logging
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Momento de início do processo (para calcular uptime do processo)
_process_start = time.time()


def _format_uptime(seconds: float) -> str:
    """Formata segundos em string legível: '5 dias, 3h 22min'"""
    td = timedelta(seconds=int(seconds))
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days} dia{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}min")
    if not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def _format_bytes(b: int) -> str:
    """Formata bytes em GB com 1 casa decimal"""
    return f"{b / (1024 ** 3):.1f} GB"


def get_server_metrics() -> dict:
    """
    Retorna métricas do servidor host:
    - CPU: percentual de uso (média 1s)
    - Memória: total, usado, livre, percentual
    - Disco: total, usado, livre, percentual (partição raiz /)
    - Uptime do sistema operacional
    - Uptime do processo Python (aplicação)
    - Load average (1, 5, 15 min) — Linux only
    """
    try:
        import psutil

        # ── CPU ──────────────────────────────────────────────────────────────
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count   = psutil.cpu_count(logical=True)
        cpu_count_p = psutil.cpu_count(logical=False) or cpu_count

        # ── Memória RAM ───────────────────────────────────────────────────────
        mem = psutil.virtual_memory()

        # ── Swap ─────────────────────────────────────────────────────────────
        swap = psutil.swap_memory()

        # ── Disco ─────────────────────────────────────────────────────────────
        disk = psutil.disk_usage("/")

        # ── Uptime do sistema ─────────────────────────────────────────────────
        boot_time    = psutil.boot_time()
        sys_uptime_s = time.time() - boot_time
        sys_uptime   = _format_uptime(sys_uptime_s)
        boot_dt      = datetime.fromtimestamp(boot_time).strftime("%d/%m/%Y %H:%M")

        # ── Uptime do processo (aplicação) ────────────────────────────────────
        app_uptime_s = time.time() - _process_start
        app_uptime   = _format_uptime(app_uptime_s)

        # ── Load average ──────────────────────────────────────────────────────
        try:
            load1, load5, load15 = psutil.getloadavg()
        except Exception:
            load1 = load5 = load15 = 0.0

        # ── Rede (bytes enviados/recebidos desde o boot) ───────────────────────
        try:
            net = psutil.net_io_counters()
            net_sent = _format_bytes(net.bytes_sent)
            net_recv = _format_bytes(net.bytes_recv)
        except Exception:
            net_sent = net_recv = "—"

        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "cpu": {
                "percent":       round(cpu_percent, 1),
                "cores_logical": cpu_count,
                "cores_physical": cpu_count_p,
                "load_1":        round(load1, 2),
                "load_5":        round(load5, 2),
                "load_15":       round(load15, 2),
                "status":        "critical" if cpu_percent >= 90 else "warning" if cpu_percent >= 70 else "ok",
            },
            "memory": {
                "total":        _format_bytes(mem.total),
                "used":         _format_bytes(mem.used),
                "available":    _format_bytes(mem.available),
                "percent":      round(mem.percent, 1),
                "total_bytes":  mem.total,
                "used_bytes":   mem.used,
                "status":       "critical" if mem.percent >= 90 else "warning" if mem.percent >= 75 else "ok",
            },
            "swap": {
                "total":   _format_bytes(swap.total) if swap.total else "—",
                "used":    _format_bytes(swap.used),
                "percent": round(swap.percent, 1) if swap.total else 0,
            },
            "disk": {
                "total":       _format_bytes(disk.total),
                "used":        _format_bytes(disk.used),
                "free":        _format_bytes(disk.free),
                "percent":     round(disk.percent, 1),
                "total_bytes": disk.total,
                "used_bytes":  disk.used,
                "status":      "critical" if disk.percent >= 90 else "warning" if disk.percent >= 75 else "ok",
            },
            "uptime": {
                "system":        sys_uptime,
                "system_seconds": int(sys_uptime_s),
                "boot_time":     boot_dt,
                "app":           app_uptime,
                "app_seconds":   int(app_uptime_s),
            },
            "network": {
                "sent": net_sent,
                "recv": net_recv,
            },
        }

    except ImportError:
        logger.warning("psutil não instalado — métricas do servidor indisponíveis")
        return {
            "success": False,
            "error": "psutil não instalado. Adicione 'psutil' ao requirements.txt e reconstrua o container.",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Erro ao coletar métricas do servidor: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
