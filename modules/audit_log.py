"""
Módulo de Audit Log — Registra todas as ações dos usuários com IP, hora e detalhes.
Grava em arquivo JSON Lines (.jsonl) e mantém os últimos N registros em memória.
"""
import os
import json
import logging
from datetime import datetime
from collections import deque
from typing import Optional
from fastapi import Request

logger = logging.getLogger(__name__)

# Caminho do arquivo de log
_requested_dir = os.getenv("AUDIT_LOG_DIR", "logs")
try:
    os.makedirs(_requested_dir, exist_ok=True)
    _test_file = os.path.join(_requested_dir, ".write_test")
    with open(_test_file, "w") as _f:
        _f.write("ok")
    os.remove(_test_file)
    LOG_DIR = _requested_dir
except Exception:
    LOG_DIR = "/tmp/ne8000_logs"
    os.makedirs(LOG_DIR, exist_ok=True)
    logger.warning(f"Sem permissao em {_requested_dir}, usando {LOG_DIR}")
LOG_FILE = os.path.join(LOG_DIR, "audit.jsonl")

# Buffer em memória (últimos 500 eventos)
_memory_buffer: deque = deque(maxlen=500)

# Tipos de eventos
class AuditEvent:
    LOGIN_SUCCESS   = "LOGIN_SUCCESS"
    LOGIN_FAILURE   = "LOGIN_FAILURE"
    LOGOUT          = "LOGOUT"
    PPPOE_QUERY     = "PPPOE_QUERY"
    PPPOE_DISCONNECT = "PPPOE_DISCONNECT"
    IFACE_COUNT     = "IFACE_COUNT"
    IFACE_LIST      = "IFACE_LIST"
    CACHE_REFRESH   = "CACHE_REFRESH"
    RECONNECT       = "RECONNECT"
    SETUP_2FA_VIEW  = "SETUP_2FA_VIEW"


def _ensure_log_dir():
    """Garantir que o diretório de logs existe."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except Exception as e:
        logger.warning(f"Não foi possível criar diretório de logs: {e}")


def get_client_ip(request: Request) -> str:
    """Extrair IP real do cliente, considerando proxies."""
    # Tentar X-Forwarded-For primeiro (nginx/docker proxy)
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    # X-Real-IP
    xri = request.headers.get("X-Real-IP", "")
    if xri:
        return xri.strip()
    # IP direto
    if request.client:
        return request.client.host
    return "unknown"


def record(
    event_type: str,
    request: Optional[Request] = None,
    web_user: str = "",
    detail: str = "",
    success: bool = True,
    extra: Optional[dict] = None
):
    """
    Registrar um evento de auditoria.

    Args:
        event_type: Tipo do evento (use AuditEvent.*)
        request: Objeto Request do FastAPI (para extrair IP e path)
        web_user: Usuário logado no sistema web
        detail: Descrição do que foi feito (ex: username PPPoE consultado)
        success: Se a operação foi bem-sucedida
        extra: Dados adicionais opcionais
    """
    now = datetime.now()
    entry = {
        "timestamp": now.isoformat(timespec="seconds"),
        "date": now.strftime("%d/%m/%Y"),
        "time": now.strftime("%H:%M:%S"),
        "event": event_type,
        "web_user": web_user or "—",
        "ip": get_client_ip(request) if request else "—",
        "path": str(request.url.path) if request else "—",
        "detail": detail or "—",
        "success": success,
    }
    if extra:
        entry["extra"] = extra

    # Guardar em memória
    _memory_buffer.append(entry)

    # Gravar em arquivo
    try:
        _ensure_log_dir()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"Erro ao gravar audit log: {e}")

    # Log estruturado no console
    status_icon = "✅" if success else "❌"
    logger.info(
        f"[AUDIT] {status_icon} {event_type} | "
        f"user={entry['web_user']} ip={entry['ip']} | {detail}"
    )


def get_recent(limit: int = 200) -> list:
    """Retornar os eventos mais recentes do buffer em memória."""
    events = list(_memory_buffer)
    events.reverse()  # mais recente primeiro
    return events[:limit]


def get_from_file(limit: int = 500) -> list:
    """Ler eventos do arquivo de log (mais recentes primeiro)."""
    try:
        if not os.path.exists(LOG_FILE):
            return []
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        events = []
        for line in reversed(lines):
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
            if len(events) >= limit:
                break
        return events
    except Exception as e:
        logger.warning(f"Erro ao ler audit log: {e}")
        return []


def get_stats() -> dict:
    """Retornar estatísticas dos eventos de auditoria."""
    events = get_from_file(limit=10000)
    stats = {
        "total": len(events),
        "logins_ok": sum(1 for e in events if e.get("event") == AuditEvent.LOGIN_SUCCESS),
        "logins_fail": sum(1 for e in events if e.get("event") == AuditEvent.LOGIN_FAILURE),
        "pppoe_queries": sum(1 for e in events if e.get("event") == AuditEvent.PPPOE_QUERY),
        "disconnects": sum(1 for e in events if e.get("event") == AuditEvent.PPPOE_DISCONNECT),
    }
    return stats
