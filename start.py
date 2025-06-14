#!/usr/bin/env python3
"""
Script de inicialização do NE8000 FastAPI Monitor
"""

import asyncio
import os
import sys
import subprocess
import time
from pathlib import Path

def check_python_version():
    """Verifica se a versão do Python é compatível"""
    if sys.version_info < (3.8, 0):
        print("❌ Python 3.8+ é necessário")
        print(f"Versão atual: {sys.version}")
        sys.exit(1)
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} detectado")

def check_dependencies():
    """Verifica se as dependências estão instaladas"""
    print("🔍 Verificando dependências...")
    
    required_packages = [
        "fastapi",
        "uvicorn",
        "redis",
        "paramiko",
        "aioredis",
        "pydantic",
        "loguru"
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            missing.append(package)
            print(f"  ❌ {package}")
    
    if missing:
        print(f"\n❌ Dependências ausentes: {', '.join(missing)}")
        print("💡 Execute: pip install -r requirements.txt")
        return False
    
    print("✅ Todas as dependências estão instaladas")
    return True

def check_env_file():
    """Verifica se o arquivo .env existe"""
    env_file = Path(".env")
    if not env_file.exists():
        print("⚠️  Arquivo .env não encontrado")
        print("💡 Criando .env padrão...")
        
        default_env = """# Configurações do servidor
HOST=0.0.0.0
PORT=8000
DEBUG=false

# Router NE8000
ROUTER_HOST=192.168.1.1
ROUTER_PORT=22
ROUTER_USERNAME=admin
ROUTER_PASSWORD=
ROUTER_PROTOCOL=ssh

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/fastapi.log
"""
        env_file.write_text(default_env)
        print("✅ Arquivo .env criado")
        print("⚠️  Configure as credenciais do router no .env")
    else:
        print("✅ Arquivo .env encontrado")

def create_directories():
    """Cria diretórios necessários"""
    directories = ["logs", "static", "templates"]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"✅ Diretório {directory}/ verificado")

def check_redis():
    """Verifica se o Redis está acessível"""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, socket_timeout=3)
        r.ping()
        print("✅ Redis conectado")
        return True
    except Exception as e:
        print(f"⚠️  Redis não acessível: {e}")
        print("💡 Inicie o Redis ou use Docker: docker run -d -p 6379:6379 redis:alpine")
        return False

def start_server(dev_mode=False, port=8000, host="0.0.0.0"):
    """Inicia o servidor FastAPI"""
    print(f"\n🚀 Iniciando servidor FastAPI...")
    print(f"📍 Endereço: http://{host}:{port}")
    print(f"📋 Documentação: http://{host}:{port}/docs")
    print(f"🔌 WebSocket: ws://{host}:{port}/ws/monitor")
    
    cmd = [
        "uvicorn", 
        "main:app",
        "--host", host,
        "--port", str(port)
    ]
    
    if dev_mode:
        cmd.extend(["--reload", "--log-level", "debug"])
        print("🔧 Modo desenvolvimento ativado")
    else:
        cmd.extend(["--workers", "1"])
    
    print("=" * 60)
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n👋 Servidor parado pelo usuário")
    except Exception as e:
        print(f"❌ Erro ao iniciar servidor: {e}")

def main():
    """Função principal"""
    print("🎯 NE8000 FastAPI Monitor - Inicialização")
    print("=" * 50)
    
    # Verificações
    check_python_version()
    
    if not check_dependencies():
        sys.exit(1)
    
    check_env_file()
    create_directories()
    
    # Redis é opcional mas recomendado
    redis_ok = check_redis()
    if not redis_ok:
        print("⚠️  Continuando sem Redis (cache em memória será usado)")
    
    print("\n✅ Verificações concluídas!")
    
    # Argumentos de linha de comando
    dev_mode = "--dev" in sys.argv or "--reload" in sys.argv
    
    # Porta customizada
    port = 8000
    if "--port" in sys.argv:
        try:
            port_idx = sys.argv.index("--port")
            port = int(sys.argv[port_idx + 1])
        except (IndexError, ValueError):
            print("⚠️  Porta inválida, usando 8000")
    
    # Host customizado
    host = "0.0.0.0"
    if "--host" in sys.argv:
        try:
            host_idx = sys.argv.index("--host")
            host = sys.argv[host_idx + 1]
        except IndexError:
            print("⚠️  Host inválido, usando 0.0.0.0")
    
    # Aguardar um pouco para o usuário ver as verificações
    time.sleep(1)
    
    # Iniciar servidor
    start_server(dev_mode=dev_mode, port=port, host=host)

if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print("""
🎯 NE8000 FastAPI Monitor - Script de Inicialização

Uso:
    python start.py [opções]

Opções:
    --dev, --reload    Modo desenvolvimento com reload automático
    --port PORT        Porta do servidor (padrão: 8000)
    --host HOST        Host do servidor (padrão: 0.0.0.0)
    --help, -h         Mostrar esta ajuda

Exemplos:
    python start.py                    # Modo produção na porta 8000
    python start.py --dev              # Modo desenvolvimento
    python start.py --port 9000        # Porta customizada
    python start.py --dev --port 9000  # Dev mode na porta 9000

Acesso:
    Web Interface: http://localhost:8000
    API Docs: http://localhost:8000/docs
    WebSocket: ws://localhost:8000/ws/monitor
        """)
        sys.exit(0)
    
    main() 