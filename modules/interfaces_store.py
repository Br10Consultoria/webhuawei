"""
interfaces_store.py — Persistência de interfaces e VLANs em arquivo JSON no servidor.
Os dados ficam em /app/data/interfaces.json (dentro do container Docker).
"""
import json
import os
import logging
from threading import Lock
from datetime import datetime

logger = logging.getLogger(__name__)

# Diretório de dados — usa /app/data dentro do Docker, ou ./data localmente
_DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
_DATA_FILE = os.path.join(_DATA_DIR, "interfaces.json")
_lock = Lock()


def _ensure_dir():
    """Garante que o diretório de dados existe."""
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
    except Exception as e:
        logger.warning(f"interfaces_store: não foi possível criar {_DATA_DIR}: {e}")


def load_interfaces() -> list:
    """Carrega a lista de interfaces do arquivo JSON."""
    _ensure_dir()
    try:
        if os.path.exists(_DATA_FILE):
            with _lock:
                with open(_DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"interfaces_store: erro ao carregar {_DATA_FILE}: {e}")
    return []


def save_interfaces(interfaces: list) -> bool:
    """Salva a lista de interfaces no arquivo JSON."""
    _ensure_dir()
    try:
        with _lock:
            with open(_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(interfaces, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"interfaces_store: erro ao salvar {_DATA_FILE}: {e}")
        return False


def add_interface(name: str, slot: int = 0, desc: str = "") -> dict:
    """Adiciona uma interface física. Retorna {'success': bool, 'message': str}."""
    interfaces = load_interfaces()
    if any(i["name"] == name for i in interfaces):
        return {"success": False, "message": f"Interface {name} já cadastrada."}
    interfaces.append({
        "name": name,
        "slot": slot,
        "desc": desc,
        "vlans": [],
        "created_at": datetime.now().isoformat()
    })
    if save_interfaces(interfaces):
        return {"success": True, "message": f"Interface {name} adicionada.", "interfaces": interfaces}
    return {"success": False, "message": "Erro ao salvar dados no servidor."}


def remove_interface(name: str) -> dict:
    """Remove uma interface física pelo nome."""
    interfaces = load_interfaces()
    before = len(interfaces)
    interfaces = [i for i in interfaces if i["name"] != name]
    if len(interfaces) == before:
        return {"success": False, "message": f"Interface {name} não encontrada."}
    if save_interfaces(interfaces):
        return {"success": True, "message": f"Interface {name} removida.", "interfaces": interfaces}
    return {"success": False, "message": "Erro ao salvar dados no servidor."}


def add_vlans(iface_name: str, vlan_ids: list, desc: str = "") -> dict:
    """Adiciona múltiplas VLANs a uma interface. Retorna {'success': bool, 'added': [...], 'skipped': [...]}."""
    interfaces = load_interfaces()
    iface = next((i for i in interfaces if i["name"] == iface_name), None)
    if not iface:
        return {"success": False, "message": f"Interface {iface_name} não encontrada."}

    existing_ids = {v["id"] for v in iface.get("vlans", [])}
    added = []
    skipped = []

    for vid in vlan_ids:
        if vid in existing_ids:
            skipped.append(vid)
        else:
            iface["vlans"].append({"id": vid, "desc": desc})
            existing_ids.add(vid)
            added.append(vid)

    # Ordenar VLANs por ID
    iface["vlans"].sort(key=lambda v: v["id"])

    if save_interfaces(interfaces):
        return {
            "success": True,
            "message": f"{len(added)} VLAN(s) adicionada(s), {len(skipped)} ignorada(s).",
            "added": added,
            "skipped": skipped,
            "interfaces": interfaces
        }
    return {"success": False, "message": "Erro ao salvar dados no servidor."}


def remove_vlan(iface_name: str, vlan_id: int) -> dict:
    """Remove uma VLAN de uma interface."""
    interfaces = load_interfaces()
    iface = next((i for i in interfaces if i["name"] == iface_name), None)
    if not iface:
        return {"success": False, "message": f"Interface {iface_name} não encontrada."}

    before = len(iface["vlans"])
    iface["vlans"] = [v for v in iface["vlans"] if v["id"] != vlan_id]
    if len(iface["vlans"]) == before:
        return {"success": False, "message": f"VLAN {vlan_id} não encontrada em {iface_name}."}

    if save_interfaces(interfaces):
        return {"success": True, "message": f"VLAN {vlan_id} removida de {iface_name}.", "interfaces": interfaces}
    return {"success": False, "message": "Erro ao salvar dados no servidor."}
