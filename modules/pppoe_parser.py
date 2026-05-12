"""
Módulo de parsing PPPoE otimizado para Huawei NE8000
Extrai todos os campos relevantes do output de 'display access-user username <user> verbose'
"""

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def format_online_time(time_str: str) -> str:
    """
    Converte tempo no formato H:MM:SS ou HH:MM:SS para texto legível em português.
    Exemplo: "61:18:02" → "2 dias, 13 horas, 18 minutos e 2 segundos"
    """
    try:
        if not time_str or time_str.strip() in ("-", ""):
            return "-"

        parts = time_str.strip().split(":")
        if len(parts) != 3:
            return time_str

        total_hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])

        days = total_hours // 24
        hours = total_hours % 24

        result_parts = []
        if days > 0:
            result_parts.append(f"{days} {'dia' if days == 1 else 'dias'}")
        if hours > 0:
            result_parts.append(f"{hours} {'hora' if hours == 1 else 'horas'}")
        if minutes > 0:
            result_parts.append(f"{minutes} {'minuto' if minutes == 1 else 'minutos'}")
        if seconds > 0:
            result_parts.append(f"{seconds} {'segundo' if seconds == 1 else 'segundos'}")

        if not result_parts:
            return "0 segundos"
        if len(result_parts) == 1:
            return result_parts[0]
        if len(result_parts) == 2:
            return f"{result_parts[0]} e {result_parts[1]}"
        return f"{', '.join(result_parts[:-1])} e {result_parts[-1]}"

    except (ValueError, IndexError):
        return time_str


def _extract(line: str) -> str:
    """Extrai o valor após ':' em uma linha do output Huawei."""
    match = re.search(r":\s*(.+)", line)
    return match.group(1).strip() if match else "-"


def parse_pppoe_output(output: str) -> Dict:
    """Parse do output de contagem total de usuários PPPoE no BNG."""
    try:
        total = 0
        for line in output.split("\n"):
            line = line.strip()
            if "Total users" in line and ":" in line:
                m = re.search(r"Total users\s*:\s*(\d+)", line)
                if m:
                    total = int(m.group(1))
                    break
        return {
            "total": total,
            "active": total,
            "peak": total,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Erro ao fazer parse PPPoE BNG: {e}")
        return {"total": 0, "active": 0, "peak": 0, "error": str(e)}


def parse_pppoe_user_output(output: str, username: str) -> Dict:
    """
    Parse completo do output de 'display access-user username <user> verbose' no NE8000.
    Extrai: IPv4, IPv6, uptime, interface, MAC, VLAN, DNS, velocidade em tempo real, etc.
    """
    user_data: Dict = {
        # Identificação
        "username": username,
        "status": "OFFLINE",
        "domain": "-",
        "access_index": "-",
        # Rede IPv4
        "ip_address": "-",
        "gateway": "-",
        "primary_dns": "-",
        "secondary_dns": "-",
        "netmask": "-",
        # Rede IPv6
        "ipv6_interface_id": "-",
        "ipv6_link_local": "-",
        "ipv6_ndra_prefix": "-",
        "ipv6_pd_prefix": "-",
        "ipv6_duid": "-",
        "ipv6_primary_dns": "-",
        "ipv6_secondary_dns": "-",
        "ipv6_lease": "-",
        "remain_lease": "-",
        "ipv6_mtu": "-",
        "ipv6_authen_type": "-",
        # Sessão
        "interface": "-",
        "mac_address": "-",
        "vlan": "-",
        "access_type": "-",
        "access_slot": "-",
        "online_time": "-",
        "online_time_raw": "-",
        "online_time_formatted": "-",
        "access_start_time": "-",
        "accounting_start_time": "-",
        "accounting_session_id": "-",
        # QoS / Velocidade
        "inbound_cir": "-",
        "outbound_cir": "-",
        "realtime_speed": "-",
        "realtime_speed_kbyte": 0,
        "realtime_speed_mb": 0.0,
        "realtime_speed_inbound": "-",
        "realtime_speed_inbound_kbyte": 0,
        "realtime_speed_inbound_mb": 0.0,
        "realtime_speed_outbound": "-",
        "realtime_speed_outbound_kbyte": 0,
        "realtime_speed_outbound_mb": 0.0,
        # RADIUS
        "radius_server": "-",
        "authen_result": "-",
        # Outros
        "mtu": "-",
        "raw_output": output,
        "formatted_message": "",
    }

    # ---------------------------------------------------------------
    # Verificações de usuário offline / erro
    # ---------------------------------------------------------------
    if not output or not output.strip():
        user_data["formatted_message"] = f"❌ Nenhum dado retornado para {username}"
        logger.info(f"📋 {username}: Output vazio — OFFLINE")
        return user_data

    offline_patterns = [
        "Info: No online user",
        "No online user",
        "User not online",
        "not found",
        "does not exist",
        "No such user",
    ]
    for pat in offline_patterns:
        if pat.lower() in output.lower():
            user_data["status"] = "OFFLINE"
            user_data["formatted_message"] = f"🔴 Usuário {username} está OFFLINE"
            user_data["offline_reason"] = f"Indicador: {pat}"
            logger.info(f"📋 {username}: '{pat}' encontrado — OFFLINE")
            return user_data

    if any(e in output for e in ["Error:", "Failed:", "Access denied", "Authentication failed"]):
        user_data["status"] = "ERROR"
        user_data["formatted_message"] = f"⚠️ Erro no sistema ao consultar {username}"
        user_data["error_details"] = output.strip()
        logger.error(f"📋 {username}: Erro real do sistema")
        return user_data

    # ---------------------------------------------------------------
    # Parsing linha a linha
    # ---------------------------------------------------------------
    has_online_data = False

    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue

        # ---- Indicadores de usuário online ----
        online_triggers = [
            "User access interface",
            "User IP address",
            "Online time",
            "Realtime speed",
            "Access start time",
            "Accounting start time",
        ]
        for trigger in online_triggers:
            if trigger in line:
                user_data["status"] = "ONLINE"
                has_online_data = True
                break

        # ---- Extração de campos ----

        # Identificação
        if "User access index" in line:
            user_data["access_index"] = _extract(line)

        elif "User name" in line and "Domain" not in line:
            val = _extract(line)
            if val and val != "-":
                user_data["username"] = val

        elif "Domain name" in line:
            user_data["domain"] = _extract(line)

        # Rede IPv4
        elif "User IP address" in line:
            user_data["ip_address"] = _extract(line)

        elif "User IP netmask" in line:
            user_data["netmask"] = _extract(line)

        elif "User gateway address" in line:
            user_data["gateway"] = _extract(line)

        elif "User Primary-DNS" in line:
            user_data["primary_dns"] = _extract(line)

        elif "User Secondary-DNS" in line:
            user_data["secondary_dns"] = _extract(line)

        # Rede IPv6
        elif "User Authen IP Type" in line:
            user_data["ipv6_authen_type"] = _extract(line)

        elif "User IPv6 InterfaceID" in line:
            user_data["ipv6_interface_id"] = _extract(line)

        elif "User IPv6 linkLocal address" in line or "User IPv6 link-local" in line:
            user_data["ipv6_link_local"] = _extract(line)

        elif "User IPv6 NDRA Prefix" in line:
            user_data["ipv6_ndra_prefix"] = _extract(line)

        elif "User IPv6 PD Prefix" in line:
            user_data["ipv6_pd_prefix"] = _extract(line)

        elif "IPv6 DUID" in line:
            user_data["ipv6_duid"] = _extract(line)

        elif "User IPv6 Primary-DNS" in line:
            user_data["ipv6_primary_dns"] = _extract(line)

        elif "User IPv6 Secondary-DNS" in line:
            user_data["ipv6_secondary_dns"] = _extract(line)

        elif "User IPv6 lease" in line and "Remain" not in line:
            user_data["ipv6_lease"] = _extract(line)

        elif "Remain IPv6 lease" in line or "Remain lease" in line:
            user_data["remain_lease"] = _extract(line)

        elif "IPv6 MTU" in line:
            user_data["ipv6_mtu"] = _extract(line)

        # Sessão
        elif "User access interface" in line:
            user_data["interface"] = _extract(line)

        elif "User MAC" in line:
            user_data["mac_address"] = _extract(line)

        elif "User access PeVlan" in line or "PeVlan" in line:
            user_data["vlan"] = _extract(line)

        elif "User access type" in line:
            user_data["access_type"] = _extract(line)

        elif "User access slot" in line:
            user_data["access_slot"] = _extract(line)

        elif "Online time" in line:
            # Formato NE8000: "Online time (h:min:sec)       : 61:18:02"
            # Extrair apenas o valor HH:MM:SS após o último ':'
            m = re.search(r"(\d+:\d{2}:\d{2})\s*$", line)
            if m:
                raw = m.group(1).strip()
            else:
                raw = _extract(line)
            user_data["online_time_raw"] = raw
            user_data["online_time"] = raw
            user_data["online_time_formatted"] = format_online_time(raw)

        elif "Access start time" in line:
            user_data["access_start_time"] = _extract(line)

        elif "Accounting start time" in line:
            user_data["accounting_start_time"] = _extract(line)

        elif "Accounting session ID" in line:
            user_data["accounting_session_id"] = _extract(line)

        # QoS
        elif "Inbound cir" in line:
            user_data["inbound_cir"] = _extract(line)

        elif "Outbound cir" in line:
            user_data["outbound_cir"] = _extract(line)

        elif "MTU" in line and "IPv6" not in line:
            user_data["mtu"] = _extract(line)

        # Velocidade em tempo real
        elif "Realtime speed" in line and "inbound" not in line.lower() and "outbound" not in line.lower():
            m = re.search(r":\s*(\d+)\s*kbyte/min", line)
            if m:
                kb = int(m.group(1))
                mb = round(kb / 1024, 2)
                user_data["realtime_speed"] = f"{kb} kbyte/min ({mb} MB/min)"
                user_data["realtime_speed_kbyte"] = kb
                user_data["realtime_speed_mb"] = mb

        elif "Realtime speed inbound" in line:
            m = re.search(r":\s*(\d+)\s*kbyte/min", line)
            if m:
                kb = int(m.group(1))
                mb = round(kb / 1024, 2)
                user_data["realtime_speed_inbound"] = f"{kb} kbyte/min ({mb} MB/min)"
                user_data["realtime_speed_inbound_kbyte"] = kb
                user_data["realtime_speed_inbound_mb"] = mb

        elif "Realtime speed outbound" in line:
            m = re.search(r":\s*(\d+)\s*kbyte/min", line)
            if m:
                kb = int(m.group(1))
                mb = round(kb / 1024, 2)
                user_data["realtime_speed_outbound"] = f"{kb} kbyte/min ({mb} MB/min)"
                user_data["realtime_speed_outbound_kbyte"] = kb
                user_data["realtime_speed_outbound_mb"] = mb

        # RADIUS
        elif "RADIUS-server-template" in line:
            user_data["radius_server"] = _extract(line)

        elif "Authen result" in line:
            user_data["authen_result"] = _extract(line)

    # ---------------------------------------------------------------
    # Mensagem formatada final
    # ---------------------------------------------------------------
    if user_data["status"] == "ONLINE":
        msg = f"🟢 Usuário {user_data['username']} está ONLINE"
        if user_data["interface"] != "-":
            msg += f" | Interface: {user_data['interface']}"
        if user_data["ip_address"] != "-":
            msg += f" | IPv4: {user_data['ip_address']}"
        if user_data["online_time_formatted"] not in ("-", ""):
            msg += f" | Uptime: {user_data['online_time_formatted']}"
        elif user_data["online_time_raw"] not in ("-", ""):
            msg += f" | Uptime: {user_data['online_time_raw']}"
        user_data["formatted_message"] = msg
        logger.info(f"📋 {username}: ONLINE — {msg}")
    else:
        user_data["status"] = "OFFLINE"
        user_data["formatted_message"] = f"🔴 Usuário {username} está OFFLINE"
        logger.info(f"📋 {username}: OFFLINE")

    return user_data


def parse_interfaces_output(output: str) -> List[Dict]:
    """Parse do output de interfaces."""
    try:
        interfaces = []
        for line in output.split("\n"):
            if "GigabitEthernet" in line or "Ethernet" in line:
                parts = line.split()
                if len(parts) >= 3:
                    interfaces.append({
                        "name": parts[0],
                        "status": parts[1] if len(parts) > 1 else "unknown",
                        "protocol": parts[2] if len(parts) > 2 else "unknown",
                    })
        return interfaces
    except Exception as e:
        logger.error(f"Erro ao fazer parse interfaces: {e}")
        return []


def parse_system_output(output: str) -> Dict:
    """Parse do output do sistema (CPU, memória)."""
    try:
        cpu = 0
        memory = 0
        for line in output.split("\n"):
            line = line.strip()
            if any(w in line.lower() for w in ["cpu", "processor"]):
                m = re.search(r"(\d+)%", line)
                if m:
                    cpu = int(m.group(1))
            if any(w in line.lower() for w in ["memory", "ram", "mem"]):
                m = re.search(r"(\d+)%", line)
                if m:
                    memory = int(m.group(1))
        return {"cpu": cpu, "memory": memory, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Erro ao fazer parse sistema: {e}")
        return {"cpu": 0, "memory": 0, "error": str(e)}


def parse_pppoe_interface_output(output: str, interface: str) -> int:
    """Parse do output PPPoE por interface."""
    try:
        for line in output.split("\n"):
            if "Total lines:" in line:
                m = re.search(r"Total lines:\s*(\d+)", line)
                if m:
                    return int(m.group(1))
        return 0
    except Exception as e:
        logger.error(f"Erro ao fazer parse PPPoE interface: {e}")
        return 0


def format_user_status(user_data: Dict) -> str:
    """Formatar status do usuário de forma amigável."""
    username = user_data.get("username", "Unknown")
    status = user_data.get("status", "UNKNOWN")
    if status == "ONLINE":
        return f"🟢 {username} está ONLINE"
    elif status == "OFFLINE":
        return f"🔴 {username} está OFFLINE"
    elif status == "NOT_FOUND":
        return f"❓ {username} não encontrado"
    elif status == "ERROR":
        return f"❌ {username} — erro na consulta"
    return f"⚪ {username} — status desconhecido"
