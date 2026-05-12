# NE8000 Monitor — Gerenciamento PPPoE via Web

Sistema web para gerenciamento de usuários PPPoE no roteador **Huawei NE8000**, com conexão via **SSH** ou **Telnet**, exibição de dados completos da sessão (IPv4, IPv6, uptime, MAC, VLAN, DNS, tráfego em tempo real) e opção de desconexão de usuário.

## Funcionalidades

- Consulta individual de usuário PPPoE com todos os campos do `display access-user verbose`
- Exibição de IPv4, IPv6 (NDRA Prefix, PD Prefix, Link Local, DUID, DNS)
- Uptime formatado (dias, horas, minutos e segundos)
- Velocidade em tempo real (inbound/outbound em kbyte/min e MB/min)
- Desconexão de usuário via sequência AAA (`system-view → aaa → cut access-user username <user> radius`)
- Suporte a conexão via **SSH** (Paramiko) ou **Telnet** (telnetlib)
- Dashboard com total de usuários online
- Cache Redis para performance
- Interface web responsiva (FastAPI + Jinja2 + TailwindCSS)

## Instalação com Docker (recomendado)

### Pré-requisitos

- Docker 20.10+
- Docker Compose 2.0+
- Acesso SSH ou Telnet ao roteador Huawei NE8000

### 1. Clone o repositório

```bash
git clone https://github.com/Br10Consultoria/webhuawei.git
cd webhuawei
```

### 2. Configure as variáveis de ambiente

```bash
cp .env.example .env
nano .env
```

Edite os campos obrigatórios:

```bash
# Autenticação da interface web
WEB_USERNAME=admin
WEB_PASSWORD=sua-senha-segura
SECRET_KEY=chave-secreta-aleatoria-longa

# Conexão com o roteador NE8000
ROUTER_HOST=10.0.0.1          # IP do roteador
ROUTER_PROTOCOL=ssh            # ssh ou telnet
ROUTER_SSH_PORT=22             # porta SSH (se usar SSH)
ROUTER_TELNET_PORT=23          # porta Telnet (se usar Telnet)
ROUTER_USERNAME=admin          # usuário do roteador
ROUTER_PASSWORD=senha-router   # senha do roteador
```

### 3. Inicie os serviços

```bash
docker-compose up --build -d

# Verificar status
docker-compose ps

# Acompanhar logs
docker-compose logs -f app
```

### 4. Acesse a aplicação

- **Login**: http://localhost:8000
- **PPPoE Management**: http://localhost:8000/pppoe
- **Dashboard**: http://localhost:8000/dashboard
- **Health Check**: http://localhost:8000/health

## Instalação Local (sem Docker)

```bash
# Instalar dependências
pip install -r requirements.txt

# Instalar Redis
sudo apt-get install redis-server   # Ubuntu/Debian
# ou
brew install redis                   # macOS

# Copiar e editar .env
cp .env.example .env
nano .env

# Executar
python simple_main_v2_complete.py
```

## Variáveis de Ambiente

| Variável | Descrição | Padrão |
|---|---|---|
| `WEB_USERNAME` | Usuário de login na interface web | `admin` |
| `WEB_PASSWORD` | Senha de login na interface web | — |
| `SECRET_KEY` | Chave secreta para sessões | — |
| `ROUTER_HOST` | IP ou hostname do NE8000 | `192.168.1.1` |
| `ROUTER_PROTOCOL` | Protocolo: `ssh` ou `telnet` | `ssh` |
| `ROUTER_SSH_PORT` | Porta SSH | `22` |
| `ROUTER_TELNET_PORT` | Porta Telnet | `23` |
| `ROUTER_USERNAME` | Usuário do roteador | `admin` |
| `ROUTER_PASSWORD` | Senha do roteador | — |
| `REDIS_HOST` | Host do Redis | `redis` |
| `REDIS_PORT` | Porta do Redis | `6379` |

## Comando de Desconexão

A desconexão de usuário PPPoE executa a seguinte sequência no NE8000:

```
system-view
aaa
cut access-user username <usuario> radius
quit
quit
```

## API Endpoints

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/online_total` | Total de usuários PPPoE online |
| `POST` | `/api/pppoe_query` | Consultar usuário (campo: `username`) |
| `POST` | `/api/pppoe_disconnect` | Desconectar usuário (campo: `username`) |
| `GET` | `/api/connection_status` | Status da conexão com o roteador |
| `POST` | `/api/reconnect` | Reconectar ao roteador |
| `GET` | `/health` | Health check da aplicação |

## Estrutura do Projeto

```
webhuawei/
├── modules/
│   ├── ssh_connection.py      # Conexão SSH/Telnet com NE8000
│   ├── pppoe_parser.py        # Parser do output do NE8000
│   ├── api_routes.py          # Rotas da API REST
│   ├── web_routes.py          # Rotas HTML
│   ├── cache_manager.py       # Cache Redis
│   └── config.py              # Configuração da aplicação
├── templates/
│   ├── base.html              # Template base
│   ├── login.html             # Página de login
│   ├── pppoe.html             # Gerenciamento PPPoE
│   └── ...
├── simple_main_v2_complete.py # Ponto de entrada
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Troubleshooting

**Erro de conexão com o roteador:**
```bash
# Testar conectividade
docker-compose exec app ping <IP_DO_ROTEADOR>

# Testar porta SSH
docker-compose exec app nc -zv <IP_DO_ROTEADOR> 22

# Testar porta Telnet
docker-compose exec app nc -zv <IP_DO_ROTEADOR> 23

# Ver logs
docker-compose logs app | grep -i "erro\|error\|connect"
```

**Redis não conecta:**
```bash
docker-compose ps redis
docker-compose exec app python -c "import redis; r=redis.Redis(host='redis'); print(r.ping())"
```

**Reconstruir após alterações:**
```bash
docker-compose down
docker-compose up --build -d
```
