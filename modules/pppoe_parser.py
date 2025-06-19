"""
Módulo de parsing PPPoE otimizado para NE8000 com tratamento de usuários offline
"""

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

def format_online_time(time_str):
    """
    Converte tempo de formato HH:MM:SS para formato legível com dias, horas, minutos e segundos
    
    Args:
        time_str (str): Tempo no formato "HH:MM:SS" (ex: "231:15:55")
    
    Returns:
        str: Tempo formatado (ex: "9 dias, 15 horas, 15 minutos e 55 segundos")
    """
    try:
        # Verifica se o tempo é válido
        if not time_str or time_str == "-" or time_str.strip() == "":
            return "-"
        
        # Separa horas, minutos e segundos
        parts = time_str.split(':')
        if len(parts) != 3:
            return time_str  # Retorna original se formato inválido
        
        total_hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
        
        # Calcula dias e horas restantes
        days = total_hours // 24
        hours = total_hours % 24
        
        # Constrói a string formatada
        result_parts = []
        
        if days > 0:
            if days == 1:
                result_parts.append(f"{days} dia")
            else:
                result_parts.append(f"{days} dias")
        
        if hours > 0:
            if hours == 1:
                result_parts.append(f"{hours} hora")
            else:
                result_parts.append(f"{hours} horas")
        
        if minutes > 0:
            if minutes == 1:
                result_parts.append(f"{minutes} minuto")
            else:
                result_parts.append(f"{minutes} minutos")
        
        if seconds > 0:
            if seconds == 1:
                result_parts.append(f"{seconds} segundo")
            else:
                result_parts.append(f"{seconds} segundos")
        
        # Junta as partes com vírgulas e "e" antes da última
        if len(result_parts) == 0:
            return "0 segundos"
        elif len(result_parts) == 1:
            return result_parts[0]
        elif len(result_parts) == 2:
            return f"{result_parts[0]} e {result_parts[1]}"
        else:
            return f"{', '.join(result_parts[:-1])} e {result_parts[-1]}"
    
    except (ValueError, IndexError):
        return time_str  # Retorna original em caso de erro

def parse_pppoe_output(output: str) -> Dict:
    """Parse do output PPPoE do BNG Huawei"""
    try:
        total = 0
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if 'Total users' in line and ':' in line:
                match = re.search(r'Total users\s*:\s*(\d+)', line)
                if match:
                    total = int(match.group(1))
                    logger.info(f"Total PPPoE users encontrado: {total}")
                    break
        
        return {
            "total": total,
            "active": total,
            "peak": total,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Erro ao fazer parse PPPoE BNG: {e}")
        return {"total": 0, "active": 0, "peak": 0, "error": str(e)}

def parse_pppoe_user_output(output: str, username: str) -> Dict:
    """
    Parse do output de consulta individual de usuário PPPoE
    MELHORADO para tratar usuários offline e debug detalhado
    """
    try:
        # Log detalhado do output recebido
        logger.debug(f"🔍 Parsing output para usuário {username}:")
        logger.debug(f"Output bruto (primeiras 200 chars): {output[:200]}...")
        
        user_data = {
            "username": username,
            "status": "OFFLINE",  # Default: offline
            "interface": "-",
            "ip_address": "-",
            "gateway": "-",
            "ipv6_interface_id": "-",
            "ipv6_link_local": "-",
            "ipv6_ndra_prefix": "-",
            "ipv6_pd_prefix": "-",
            "ipv6_duid": "-",
            "ipv6_primary_dns": "-",
            "ipv6_secondary_dns": "-",
            "online_time": "-",
            "ipv6_lease": "-",
            "remain_lease": "-",
            "ipv6_mtu": "-",
            "raw_output": output,
            "formatted_message": ""
        }
        
        # Verificar se o usuário não está online
        if not output or output.strip() == "":
            user_data["status"] = "OFFLINE"
            user_data["formatted_message"] = f"❌ Nenhum dado retornado para o usuário {username}"
            logger.info(f"📋 {username}: Sem dados no output - marcando como OFFLINE")
            return user_data
        
        # Verificar mensagem específica de usuário offline
        if "Info: No online user!" in output:
            user_data["status"] = "OFFLINE"
            user_data["formatted_message"] = f"🔴 Usuário {username} está OFFLINE"
            user_data["offline_reason"] = "Usuário não está conectado no momento"
            logger.info(f"📋 {username}: Mensagem 'No online user!' encontrada - OFFLINE")
            return user_data
        
        # Verificar outras mensagens que indicam usuário offline
        offline_indicators = [
            "No online user",
            "User not online",
            "not found",
            "does not exist",
            "No such user"
        ]
        
        for indicator in offline_indicators:
            if indicator.lower() in output.lower():
                user_data["status"] = "OFFLINE"
                user_data["formatted_message"] = f"🔴 Usuário {username} está OFFLINE"
                user_data["offline_reason"] = f"Indicador encontrado: {indicator}"
                logger.info(f"📋 {username}: Indicador '{indicator}' encontrado - OFFLINE")
                return user_data
        
        # Verificar mensagens de erro REAL do sistema (não usuário offline)
        if any(error in output for error in ["Error:", "Failed:", "Access denied", "Authentication failed"]):
            user_data["status"] = "ERROR"
            user_data["formatted_message"] = f"⚠️ Erro no sistema ao consultar usuário {username}"
            user_data["error_details"] = output.strip()
            logger.error(f"📋 {username}: Erro real do sistema encontrado")
            return user_data
        
        lines = output.split('\n')
        has_online_data = False
        found_data_fields = []
        
        logger.debug(f"📋 {username}: Analisando {len(lines)} linhas do output...")
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            
            # Verificar se usuário está online - múltiplos indicadores
            online_indicators = [
                'Online time',
                'User access interface',
                'User IP address',
                'Realtime speed',
                'access interface',
                'IP address'
            ]
            
            for indicator in online_indicators:
                if indicator in line:
                    user_data["status"] = "ONLINE"
                    has_online_data = True
                    found_data_fields.append(f"{indicator} (linha {line_num})")
                    logger.debug(f"📋 {username}: Indicador ONLINE '{indicator}' encontrado na linha {line_num}")
                    break
            
            # Extrair informações específicas
            if 'User access interface' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    user_data["interface"] = match.group(1).strip()
                    logger.debug(f"📋 {username}: Interface extraída: {user_data['interface']}")
            
            elif 'User IP address' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    user_data["ip_address"] = match.group(1).strip()
                    logger.debug(f"📋 {username}: IP extraído: {user_data['ip_address']}")
            
            elif 'User gateway address' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    user_data["gateway"] = match.group(1).strip()
            
            elif 'User IPv6 InterfaceID' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    user_data["ipv6_interface_id"] = match.group(1).strip()
            
            elif 'User IPv6 linkLocal address' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    user_data["ipv6_link_local"] = match.group(1).strip()
            
            elif 'User IPv6 NDRA Prefix' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    user_data["ipv6_ndra_prefix"] = match.group(1).strip()
            
            elif 'User IPv6 PD Prefix' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    user_data["ipv6_pd_prefix"] = match.group(1).strip()
            
            elif 'IPv6 DUID' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    user_data["ipv6_duid"] = match.group(1).strip()
            
            elif 'User IPv6 Primary-DNS' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    user_data["ipv6_primary_dns"] = match.group(1).strip()
            
            elif 'User IPv6 Secondary-DNS' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    user_data["ipv6_secondary_dns"] = match.group(1).strip()
            
            elif 'Online time' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    online_time_value = match.group(1).strip()
                    user_data["online_time"] = online_time_value
                    logger.debug(f"📋 {username}: Tempo online extraído: '{online_time_value}' da linha: '{line}'")
            
            elif 'User IPv6 lease' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    user_data["ipv6_lease"] = match.group(1).strip()
            
            elif 'Remain IPv6 lease' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    user_data["remain_lease"] = match.group(1).strip()
            
            elif 'IPv6 MTU' in line:
                match = re.search(r':\s*(.+)', line)
                if match:
                    user_data["ipv6_mtu"] = match.group(1).strip()
                    
            # Dados de tráfego em tempo real
            elif 'Realtime speed' in line and 'inbound' not in line and 'outbound' not in line:
                match = re.search(r':\s*(\d+)\s*kbyte/min', line)
                if match:
                    kbyte_min = int(match.group(1))
                    # Converter para MB/min
                    mb_min = round(kbyte_min / 1024, 2)
                    user_data["realtime_speed"] = f"{kbyte_min} kbyte/min ({mb_min} MB/min)"
                    user_data["realtime_speed_kbyte"] = kbyte_min
                    user_data["realtime_speed_mb"] = mb_min
                    logger.debug(f"📋 {username}: Velocidade total: {mb_min} MB/min")
            
            elif 'Realtime speed inbound' in line:
                match = re.search(r':\s*(\d+)\s*kbyte/min', line)
                if match:
                    kbyte_min = int(match.group(1))
                    mb_min = round(kbyte_min / 1024, 2)
                    user_data["realtime_speed_inbound"] = f"{kbyte_min} kbyte/min ({mb_min} MB/min)"
                    user_data["realtime_speed_inbound_kbyte"] = kbyte_min
                    user_data["realtime_speed_inbound_mb"] = mb_min
                    logger.debug(f"📋 {username}: Velocidade inbound: {mb_min} MB/min")
            
            elif 'Realtime speed outbound' in line:
                match = re.search(r':\s*(\d+)\s*kbyte/min', line)
                if match:
                    kbyte_min = int(match.group(1))
                    mb_min = round(kbyte_min / 1024, 2)
                    user_data["realtime_speed_outbound"] = f"{kbyte_min} kbyte/min ({mb_min} MB/min)"
                    user_data["realtime_speed_outbound_kbyte"] = kbyte_min
                    user_data["realtime_speed_outbound_mb"] = mb_min
                    logger.debug(f"📋 {username}: Velocidade outbound: {mb_min} MB/min")
        
        # Log do resultado da análise
        if has_online_data:
            logger.info(f"📋 {username}: Dados ONLINE encontrados - campos: {', '.join(found_data_fields)}")
        else:
            logger.info(f"📋 {username}: Nenhum dado ONLINE encontrado - marcando como OFFLINE")
        
        # Criar mensagem formatada baseada no status
        if user_data["status"] == "ONLINE":
            user_data["formatted_message"] = f"🟢 Usuário {username} está ONLINE"
            if user_data["interface"] != "-":
                user_data["formatted_message"] += f" na interface {user_data['interface']}"
            if user_data["ip_address"] != "-":
                user_data["formatted_message"] += f" com IP {user_data['ip_address']}"
            
            # Melhorar formatação do tempo online
            online_time_raw = user_data.get('online_time', '-')
            if online_time_raw and online_time_raw != "-":
                try:
                    formatted_time = format_online_time(online_time_raw)
                    user_data["formatted_message"] += f" (online há {formatted_time})"
                    logger.debug(f"📋 {username}: Tempo original: '{online_time_raw}' -> Formatado: '{formatted_time}'")
                except Exception as e:
                    logger.error(f"📋 {username}: Erro ao formatar tempo online '{online_time_raw}': {e}")
                    user_data["formatted_message"] += f" (online há {online_time_raw})"
            else:
                user_data["formatted_message"] += " (tempo online não disponível)"
        else:
            # Se não encontrou dados de usuário online, garantir que seja OFFLINE
            user_data["status"] = "OFFLINE"
            user_data["formatted_message"] = f"🔴 Usuário {username} está OFFLINE"
        
        # Log final
        logger.info(f"📋 {username}: Status final determinado: {user_data['status']}")
        
        return user_data
        
    except Exception as e:
        logger.error(f"📋 {username}: EXCEÇÃO ao fazer parse - {e}")
        logger.error(f"📋 {username}: Output que causou erro: {output[:500]}...")
        
        # EM CASO DE ERRO, SEMPRE RETORNAR OFFLINE (não ERROR)
        # Isso evita status "desconhecido" no frontend
        return {
            "username": username,
            "status": "OFFLINE",  # Mudança: retorna OFFLINE em vez de ERROR
            "error": str(e),
            "formatted_message": f"🔴 Usuário {username} está OFFLINE (erro no processamento)",
            "raw_output": output,
            "error_details": f"Erro técnico: {str(e)}"
        }

def parse_interfaces_output(output: str) -> List[Dict]:
    """Parse do output de interfaces"""
    try:
        interfaces = []
        lines = output.split('\n')
        
        for line in lines:
            if 'GigabitEthernet' in line or 'Ethernet' in line:
                parts = line.split()
                if len(parts) >= 3:
                    interfaces.append({
                        "name": parts[0],
                        "status": parts[1] if len(parts) > 1 else "unknown",
                        "protocol": parts[2] if len(parts) > 2 else "unknown"
                    })
        
        return interfaces
    except Exception as e:
        logger.error(f"Erro ao fazer parse interfaces: {e}")
        return []

def parse_system_output(output: str) -> Dict:
    """Parse do output do sistema"""
    try:
        cpu = 0
        memory = 0
        
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if any(word in line.lower() for word in ['cpu', 'processor']):
                cpu_match = re.search(r'(\d+)%', line)
                if cpu_match:
                    cpu = int(cpu_match.group(1))
            
            if any(word in line.lower() for word in ['memory', 'ram', 'mem']):
                mem_match = re.search(r'(\d+)%', line)
                if mem_match:
                    memory = int(mem_match.group(1))
        
        return {
            "cpu": cpu,
            "memory": memory,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Erro ao fazer parse sistema: {e}")
        return {"cpu": 0, "memory": 0, "error": str(e)}

def parse_pppoe_interface_output(output: str, interface: str) -> int:
    """Parse do output PPPoE por interface"""
    try:
        lines = output.split('\n')
        for line in lines:
            if 'Total lines:' in line:
                match = re.search(r'Total lines:\s*(\d+)', line)
                if match:
                    count = int(match.group(1))
                    logger.info(f"PPPoE count para {interface}: {count}")
                    return count
        return 0
    except Exception as e:
        logger.error(f"Erro ao fazer parse PPPoE interface: {e}")
        return 0

def format_user_status(user_data: Dict) -> str:
    """
    Formatar status do usuário de forma amigável
    """
    username = user_data.get("username", "Unknown")
    status = user_data.get("status", "UNKNOWN")
    
    if status == "ONLINE":
        return f"🟢 {username} está ONLINE"
    elif status == "OFFLINE":
        return f"🔴 {username} está OFFLINE"
    elif status == "NOT_FOUND":
        return f"❓ {username} não encontrado"
    elif status == "ERROR":
        return f"❌ {username} - erro na consulta"
    else:
        return f"⚪ {username} - status desconhecido"

def get_user_summary(user_data: Dict) -> Dict:
    """
    Gerar resumo do usuário
    """
    return {
        "username": user_data.get("username", "Unknown"),
        "status": user_data.get("status", "UNKNOWN"),
        "formatted_message": user_data.get("formatted_message", ""),
        "interface": user_data.get("interface", "-"),
        "ip_address": user_data.get("ip_address", "-"),
        "online_time": user_data.get("online_time", "-"),
        "is_online": user_data.get("status") == "ONLINE",
        "has_error": user_data.get("status") == "ERROR"
    }

# Teste rápido da função
time_str = "659:48:02"
parts = time_str.split(':')
total_hours = int(parts[0])  # 659
minutes = int(parts[1])      # 48  
seconds = int(parts[2])      # 2

days = total_hours // 24     # 659 ÷ 24 = 27 dias
hours = total_hours % 24     # 659 % 24 = 11 horas

# Resultado: "27 dias, 11 horas, 48 minutos e 2 segundos" 