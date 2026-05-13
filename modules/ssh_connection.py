"""
Módulo de conexão SSH/Telnet otimizado para Huawei NE8000
Suporta SSH (via Paramiko) e Telnet (via telnetlib)
"""

import logging
import os
import time
import telnetlib
import paramiko
from typing import Optional

logger = logging.getLogger(__name__)


class SimpleSSHConnection:
    """Conexão SSH/Telnet para Huawei NE8000"""

    def __init__(self):
        self.host = os.getenv("ROUTER_HOST", "192.168.1.1")
        self.protocol = os.getenv("ROUTER_PROTOCOL", "ssh").lower()
        self.port = int(
            os.getenv("ROUTER_SSH_PORT", "22")
            if self.protocol == "ssh"
            else os.getenv("ROUTER_TELNET_PORT", "23")
        )
        self.username = os.getenv("ROUTER_USERNAME", "admin")
        self.password = os.getenv("ROUTER_PASSWORD", "")

        # SSH
        self.ssh_client: Optional[paramiko.SSHClient] = None
        self.shell = None

        # Telnet
        self.telnet_client: Optional[telnetlib.Telnet] = None

        self.connected = False

    # ------------------------------------------------------------------
    # Conexão
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Conectar ao roteador via SSH ou Telnet"""
        if self.protocol == "telnet":
            return self._connect_telnet()
        return self._connect_ssh()

    def _connect_ssh(self) -> bool:
        """Conectar via SSH usando Paramiko"""
        try:
            logger.info(f"Conectando via SSH a {self.host}:{self.port}")
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh_client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=15,
                look_for_keys=False,
                allow_agent=False,
            )
            self.shell = self.ssh_client.invoke_shell(width=200, height=50)
            self.shell.settimeout(15)
            time.sleep(2)
            if self.shell.recv_ready():
                self.shell.recv(8192)
            self.connected = True
            logger.info("✅ SSH conectado com sucesso")
            return True
        except Exception as e:
            logger.error(f"❌ Erro na conexão SSH: {e}")
            self.disconnect()
            return False

    def _connect_telnet(self) -> bool:
        """Conectar via Telnet"""
        try:
            logger.info(f"Conectando via Telnet a {self.host}:{self.port}")
            self.telnet_client = telnetlib.Telnet(self.host, self.port, timeout=15)

            # Aguardar prompt de login
            self.telnet_client.read_until(b"Username:", timeout=10)
            self.telnet_client.write(self.username.encode("ascii") + b"\n")

            self.telnet_client.read_until(b"Password:", timeout=10)
            self.telnet_client.write(self.password.encode("ascii") + b"\n")

            # Aguardar prompt do equipamento (> ou ])
            time.sleep(2)
            banner = self.telnet_client.read_very_eager().decode("utf-8", errors="ignore")
            if ">" in banner or "]" in banner or self.host in banner:
                self.connected = True
                logger.info("✅ Telnet conectado com sucesso")
                return True
            else:
                logger.error(f"❌ Prompt não reconhecido após login Telnet: {banner[:200]}")
                self.disconnect()
                return False
        except Exception as e:
            logger.error(f"❌ Erro na conexão Telnet: {e}")
            self.disconnect()
            return False

    # ------------------------------------------------------------------
    # Execução de comandos
    # ------------------------------------------------------------------

    def _is_alive(self) -> bool:
        """Verificar se a conexão SSH/Telnet ainda está ativa"""
        try:
            if self.protocol == "ssh":
                if self.shell is None:
                    return False
                transport = self.shell.get_transport() if hasattr(self.shell, 'get_transport') else None
                if transport is None:
                    # shell é um Channel do paramiko
                    t = self.ssh_client.get_transport() if self.ssh_client else None
                    return t is not None and t.is_active()
                return transport.is_active()
            elif self.protocol == "telnet":
                if self.telnet_client is None:
                    return False
                # Telnet: tentar enviar NOP (sequência vazia)
                self.telnet_client.write(b"")
                return True
        except Exception:
            return False

    def _ensure_connected(self) -> None:
        """Garantir que a conexão está ativa; reconectar se necessário"""
        if not self.connected or not self._is_alive():
            logger.warning("🔄 Conexão perdida — reconectando automaticamente...")
            self.disconnect()
            if not self.connect():
                raise Exception("Falha ao reconectar com o roteador")
            logger.info("✅ Reconectado com sucesso")

    def execute_command(self, command: str) -> str:
        """Executar comando no roteador (SSH ou Telnet) com reconexão automática"""
        self._ensure_connected()
        if self.protocol == "telnet":
            return self._execute_telnet(command)
        return self._execute_ssh(command)

    def _execute_ssh(self, command: str) -> str:
        """Executar comando via SSH"""
        try:
            # Limpar buffer
            while self.shell.recv_ready():
                self.shell.recv(8192)

            # Adicionar | no-more para evitar paginação
            cmd = command if command.endswith(" | no-more") else command + " | no-more"
            self.shell.send(cmd.encode() + b"\n")
            time.sleep(2)

            output = ""
            start = time.time()
            while time.time() - start < 15:
                if self.shell.recv_ready():
                    chunk = self.shell.recv(8192).decode("utf-8", errors="ignore")
                    output += chunk
                    # Verificar se chegou ao prompt ou à pergunta [Y/N]
                    if "[Y/N]" in chunk or "[y/n]" in chunk:
                        self.shell.send(b"Y\n")
                        time.sleep(2)
                    elif ">" in chunk or "]" in chunk:
                        # Aguardar um pouco mais para garantir que todo o output chegou
                        time.sleep(0.3)
                        if self.shell.recv_ready():
                            output += self.shell.recv(8192).decode("utf-8", errors="ignore")
                        break
                else:
                    time.sleep(0.1)

            return self._clean_output(output, command)
        except Exception as e:
            logger.error(f"Erro ao executar comando SSH: {e}")
            self.disconnect()
            raise

    def _execute_telnet(self, command: str) -> str:
        """Executar comando via Telnet"""
        try:
            cmd = command if command.endswith(" | no-more") else command + " | no-more"
            self.telnet_client.write(cmd.encode("ascii") + b"\n")
            time.sleep(2)

            output = ""
            start = time.time()
            while time.time() - start < 15:
                try:
                    chunk = self.telnet_client.read_very_eager().decode("utf-8", errors="ignore")
                    if chunk:
                        output += chunk
                        if "[Y/N]" in chunk or "[y/n]" in chunk:
                            self.telnet_client.write(b"Y\n")
                            time.sleep(2)
                        elif ">" in chunk or "]" in chunk:
                            time.sleep(0.3)
                            extra = self.telnet_client.read_very_eager().decode("utf-8", errors="ignore")
                            output += extra
                            break
                    else:
                        time.sleep(0.1)
                except EOFError:
                    logger.warning("Conexão Telnet encerrada pelo servidor")
                    self.connected = False
                    break

            return self._clean_output(output, command)
        except Exception as e:
            logger.error(f"Erro ao executar comando Telnet: {e}")
            self.disconnect()
            raise

    def _clean_output(self, output: str, command: str) -> str:
        """Limpar output removendo prompts e eco do comando"""
        lines = output.split("\n")
        cleaned = []
        cmd_clean = command.replace(" | no-more", "").strip()
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            # Remover eco do comando
            if cmd_clean in line_stripped:
                continue
            # Remover prompts finais (mas manter linhas intermediárias com > ou ])
            if line_stripped.endswith(">") or line_stripped.endswith("]"):
                continue
            cleaned.append(line_stripped)
        return "\n".join(cleaned)

    # ------------------------------------------------------------------
    # Sequência de desconexão de usuário AAA
    # ------------------------------------------------------------------

    def execute_aaa_disconnect_sequence(self, username: str) -> str:
        """
        Executar sequência AAA para desconectar usuário PPPoE.
        Comando correto para NE8000:
            system-view → aaa → cut access-user username <user> radius
        """
        if not self.connected:
            if not self.connect():
                raise Exception("Falha na conexão com o roteador")

        try:
            if self.protocol == "telnet":
                return self._aaa_disconnect_telnet(username)
            return self._aaa_disconnect_ssh(username)
        except Exception as e:
            logger.error(f"❌ Erro na sequência AAA: {e}")
            # Tentar retornar ao modo de usuário
            try:
                self._send_raw(b"quit\nquit\nreturn\n")
                time.sleep(2)
                self._flush_buffer()
            except Exception:
                pass
            raise

    def _send_raw(self, data: bytes):
        """Enviar bytes brutos para SSH ou Telnet"""
        if self.protocol == "telnet" and self.telnet_client:
            self.telnet_client.write(data)
        elif self.shell:
            self.shell.send(data)

    def _flush_buffer(self):
        """Limpar buffer de leitura"""
        try:
            if self.protocol == "telnet" and self.telnet_client:
                self.telnet_client.read_very_eager()
            elif self.shell and self.shell.recv_ready():
                self.shell.recv(8192)
        except Exception:
            pass

    def _read_until_prompt(self, expected: list, timeout: int = 10) -> str:
        """Ler output até encontrar um dos prompts esperados"""
        output = ""
        start = time.time()
        while time.time() - start < timeout:
            try:
                if self.protocol == "telnet" and self.telnet_client:
                    chunk = self.telnet_client.read_very_eager().decode("utf-8", errors="ignore")
                elif self.shell and self.shell.recv_ready():
                    chunk = self.shell.recv(8192).decode("utf-8", errors="ignore")
                else:
                    chunk = ""

                if chunk:
                    output += chunk
                    for prompt in expected:
                        if prompt in output:
                            return output
                time.sleep(0.2)
            except Exception:
                break
        return output

    def _aaa_disconnect_ssh(self, username: str) -> str:
        """Sequência AAA via SSH"""
        full_output = ""
        self._flush_buffer()

        # 1) system-view
        logger.info("📝 [1/3] system-view")
        self.shell.send(b"system-view\n")
        out = self._read_until_prompt(["[~", "[-"], timeout=8)
        full_output += f"=== system-view ===\n{out}\n"

        # 2) aaa
        logger.info("📝 [2/3] aaa")
        self.shell.send(b"aaa\n")
        out = self._read_until_prompt(["-aaa]"], timeout=8)
        full_output += f"=== aaa ===\n{out}\n"

        # 3) cut access-user username <user> radius
        cmd = f"cut access-user username {username} radius\n"
        logger.info(f"📝 [3/3] {cmd.strip()}")
        self.shell.send(cmd.encode())
        out = self._read_until_prompt(["cut off", "aaa]", "Error", "error"], timeout=12)
        full_output += f"=== cut access-user ===\n{out}\n"

        # Sair do modo de configuração
        self.shell.send(b"quit\n")
        time.sleep(1)
        self.shell.send(b"quit\n")
        time.sleep(1)
        self._flush_buffer()

        return full_output

    def _aaa_disconnect_telnet(self, username: str) -> str:
        """Sequência AAA via Telnet"""
        full_output = ""
        self._flush_buffer()

        # 1) system-view
        logger.info("📝 [1/3] system-view")
        self.telnet_client.write(b"system-view\n")
        out = self._read_until_prompt(["[~", "[-"], timeout=8)
        full_output += f"=== system-view ===\n{out}\n"

        # 2) aaa
        logger.info("📝 [2/3] aaa")
        self.telnet_client.write(b"aaa\n")
        out = self._read_until_prompt(["-aaa]"], timeout=8)
        full_output += f"=== aaa ===\n{out}\n"

        # 3) cut access-user username <user> radius
        cmd = f"cut access-user username {username} radius\n"
        logger.info(f"📝 [3/3] {cmd.strip()}")
        self.telnet_client.write(cmd.encode("ascii"))
        out = self._read_until_prompt(["cut off", "aaa]", "Error", "error"], timeout=12)
        full_output += f"=== cut access-user ===\n{out}\n"

        # Sair do modo de configuração
        self.telnet_client.write(b"quit\n")
        time.sleep(1)
        self.telnet_client.write(b"quit\n")
        time.sleep(1)
        self._flush_buffer()

        return full_output

    # ------------------------------------------------------------------
    # Desconexão
    # ------------------------------------------------------------------

    def disconnect(self):
        """Desconectar SSH/Telnet"""
        self.connected = False
        if self.shell:
            try:
                self.shell.close()
            except Exception:
                pass
            self.shell = None
        if self.ssh_client:
            try:
                self.ssh_client.close()
            except Exception:
                pass
            self.ssh_client = None
        if self.telnet_client:
            try:
                self.telnet_client.close()
            except Exception:
                pass
            self.telnet_client = None
        logger.info("Conexão encerrada")


# Instância global singleton
_ssh_connection: Optional[SimpleSSHConnection] = None


def get_ssh_connection() -> SimpleSSHConnection:
    """Obter conexão global (singleton)"""
    global _ssh_connection
    if _ssh_connection is None:
        _ssh_connection = SimpleSSHConnection()
    return _ssh_connection
