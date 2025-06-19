"""
Módulo de conexão SSH otimizado para NE8000
"""

import logging
import os
import time
import paramiko
from typing import Optional

logger = logging.getLogger(__name__)

class SimpleSSHConnection:
    """Conexão SSH simplificada e funcional"""
    
    def __init__(self):
        self.host = os.getenv("ROUTER_HOST", "192.168.1.1")
        self.port = int(os.getenv("ROUTER_SSH_PORT", "22"))
        self.username = os.getenv("ROUTER_USERNAME", "admin")
        self.password = os.getenv("ROUTER_PASSWORD", "")
        self.ssh_client = None
        self.shell = None
        self.connected = False
        
    def connect(self) -> bool:
        """Conectar ao router via SSH"""
        try:
            logger.info(f"Conectando a {self.host}:{self.port}")
            
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.ssh_client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=10,
                look_for_keys=False,
                allow_agent=False
            )
            
            self.shell = self.ssh_client.invoke_shell()
            self.shell.settimeout(10)
            
            # Aguardar prompt inicial
            time.sleep(2)
            if self.shell.recv_ready():
                self.shell.recv(4096)
            
            self.connected = True
            logger.info("✅ SSH conectado com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro na conexão SSH: {e}")
            self.disconnect()
            return False
    
    def execute_command(self, command: str) -> str:
        """Executar comando no router"""
        if not self.connected:
            if not self.connect():
                raise Exception("Falha na conexão SSH")
        
        try:
            # Limpar buffer
            while self.shell.recv_ready():
                self.shell.recv(4096)
            
            # Enviar comando
            if not command.endswith(' | no-more'):
                command += ' | no-more'
            
            self.shell.send(command.encode() + b'\n')
            time.sleep(1.5)  # Aumentar timeout para comandos mais complexos
            
            # Ler resposta
            output = ""
            start_time = time.time()
            while time.time() - start_time < 12:  # Aumentar timeout
                if self.shell.recv_ready():
                    chunk = self.shell.recv(4096).decode('utf-8', errors='ignore')
                    output += chunk
                    if '>' in chunk or ']' in chunk:
                        break
                else:
                    time.sleep(0.1)
            
            # Limpar output
            lines = output.split('\n')
            cleaned_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.endswith('>') and not line.endswith(']'):
                    if command.replace(' | no-more', '') not in line:
                        cleaned_lines.append(line)
            
            result = '\n'.join(cleaned_lines)
            logger.info(f"Comando executado: {command[:50]}...")
            return result
            
        except Exception as e:
            logger.error(f"Erro ao executar comando: {e}")
            self.disconnect()
            raise
    
    def execute_command_with_confirmation(self, command: str, confirmation: str = "Y") -> str:
        """Executar comando que requer confirmação [Y/N]"""
        if not self.connected:
            if not self.connect():
                raise Exception("Falha na conexão SSH")
        
        try:
            # Limpar buffer
            while self.shell.recv_ready():
                self.shell.recv(4096)
            
            # Enviar comando inicial
            self.shell.send(command.encode() + b'\n')
            time.sleep(2)  # Aguardar prompt de confirmação
            
            # Ler primeira resposta (deve conter a pergunta [Y/N])
            output = ""
            start_time = time.time()
            while time.time() - start_time < 8:
                if self.shell.recv_ready():
                    chunk = self.shell.recv(4096).decode('utf-8', errors='ignore')
                    output += chunk
                    if '[Y/N]' in chunk or '[y/n]' in chunk:
                        break
                else:
                    time.sleep(0.1)
            
            # Se encontrou prompt de confirmação, enviar resposta
            if '[Y/N]' in output.upper() or '[y/n]' in output.upper():
                logger.info(f"📝 Enviando confirmação: {confirmation}")
                self.shell.send(confirmation.encode() + b'\n')
                time.sleep(2)  # Aguardar execução
                
                # Ler resposta final
                while time.time() - start_time < 12:
                    if self.shell.recv_ready():
                        chunk = self.shell.recv(4096).decode('utf-8', errors='ignore')
                        output += chunk
                        if '>' in chunk or ']' in chunk:
                            break
                    else:
                        time.sleep(0.1)
            
            # Limpar output
            lines = output.split('\n')
            cleaned_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.endswith('>') and not line.endswith(']'):
                    if command not in line:
                        cleaned_lines.append(line)
            
            result = '\n'.join(cleaned_lines)
            logger.info(f"Comando com confirmação executado: {command[:50]}...")
            return result
            
        except Exception as e:
            logger.error(f"Erro ao executar comando com confirmação: {e}")
            self.disconnect()
            raise

    def execute_aaa_disconnect_sequence(self, username: str) -> str:
        """Executar sequência de comandos AAA para desconectar usuário"""
        if not self.connected:
            if not self.connect():
                raise Exception("Falha na conexão SSH")
        
        try:
            # Limpar buffer
            while self.shell.recv_ready():
                self.shell.recv(4096)
            
            full_output = ""
            
            # Comando 1: system-view
            logger.info("📝 Executando comando 1/3: system-view")
            self.shell.send(b'system-view\n')
            time.sleep(1.5)  # Reduzir timeout
            
            output = ""
            start_time = time.time()
            while time.time() - start_time < 8:
                if self.shell.recv_ready():
                    chunk = self.shell.recv(4096).decode('utf-8', errors='ignore')
                    output += chunk
                    if '[~' in chunk and ']' in chunk:  # system-view prompt
                        break
                else:
                    time.sleep(0.1)
            
            full_output += f"=== system-view ===\n{output}\n"
            
            # Comando 2: aaa
            logger.info("📝 Executando comando 2/3: aaa")
            self.shell.send(b'aaa\n')
            time.sleep(1.5)  # Reduzir timeout
            
            output = ""
            start_time = time.time()
            while time.time() - start_time < 8:
                if self.shell.recv_ready():
                    chunk = self.shell.recv(4096).decode('utf-8', errors='ignore')
                    output += chunk
                    if '-aaa]' in chunk:  # aaa module prompt
                        break
                else:
                    time.sleep(0.1)
            
            full_output += f"=== aaa ===\n{output}\n"
            
            # Comando 3: cut access-user (execução direta)
            logger.info(f"📝 Executando comando 3/3: cut access-user username {username} all")
            self.shell.send(f'cut access-user username {username} all\n'.encode())
            time.sleep(1.5)
            
            output = ""
            start_time = time.time()
            
            while time.time() - start_time < 10:
                if self.shell.recv_ready():
                    chunk = self.shell.recv(4096).decode('utf-8', errors='ignore')
                    output += chunk
                    
                    # Verificar se comando foi executado com sucesso
                    if 'user has been cut off' in chunk.lower():
                        logger.info("✅ Usuário desconectado - mensagem: 'user has been cut off'")
                        time.sleep(0.5)  # Aguardar prompt final
                        break
                    
                    # Verificar se retornou ao prompt AAA após execução
                    elif '-aaa]' in chunk:
                        break
                        
                    # Verificar erros específicos
                    elif 'error:' in chunk.lower() or 'invalid' in chunk.lower():
                        logger.warning(f"⚠️ Erro detectado: {chunk.strip()}")
                        break
                else:
                    time.sleep(0.1)
            
            full_output += f"=== cut access-user ===\n{output}\n"
            
            # Sair do modo de configuração
            logger.info("📝 Saindo do modo de configuração...")
            self.shell.send(b'quit\n')  # Sair do AAA
            time.sleep(1)
            self.shell.send(b'quit\n')  # Sair do system-view
            time.sleep(1)
            
            # Limpar resposta final
            if self.shell.recv_ready():
                final_chunk = self.shell.recv(4096).decode('utf-8', errors='ignore')
                full_output += f"=== quit ===\n{final_chunk}"
            
            # Processar resultado
            if 'user has been cut off' in full_output.lower():
                logger.info(f"✅ Usuário {username} desconectado com sucesso")
                return full_output
            elif 'error' in full_output.lower():
                logger.error(f"❌ Erro ao desconectar usuário {username}")
                raise Exception(f"Erro na desconexão: {full_output}")
            else:
                logger.warning(f"⚠️ Resultado incerto para desconexão de {username}")
                return full_output
            
        except Exception as e:
            logger.error(f"❌ Erro na sequência AAA: {e}")
            # Tentar sair do modo de configuração em caso de erro
            try:
                logger.info("🔧 Tentando sair do modo de configuração após erro...")
                self.shell.send(b'quit\nquit\n')
                time.sleep(2)
                # Limpar buffer após quit
                while self.shell.recv_ready():
                    self.shell.recv(4096)
            except:
                logger.warning("⚠️ Falha ao sair do modo de configuração")
                pass
            raise

    def disconnect(self):
        """Desconectar SSH"""
        self.connected = False
        if self.shell:
            self.shell.close()
        if self.ssh_client:
            self.ssh_client.close()
        logger.info("SSH desconectado")

# Instância global singleton
_ssh_connection: Optional[SimpleSSHConnection] = None

def get_ssh_connection() -> SimpleSSHConnection:
    """Obter conexão SSH global (singleton)"""
    global _ssh_connection
    if _ssh_connection is None:
        _ssh_connection = SimpleSSHConnection()
    return _ssh_connection 