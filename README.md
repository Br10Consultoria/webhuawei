# 🚀 NE8000 Sistema Híbrido de Monitoramento

Sistema completo de monitoramento para equipamentos Huawei NE8000, combinando coleta via SSH e SNMP para análise de PPPoE e tráfego de interfaces em tempo real.

## 📋 Características

- **🔍 Monitoramento PPPoE**: Consulta de usuários online, desconexão e histórico
- **📊 Análise de Tráfego**: Coleta SNMP de interfaces de rede
- **⚡ Cache Inteligente**: Sistema Redis para performance otimizada
- **🎯 Dashboard Híbrido**: Interface web moderna e responsiva
- **🐳 Docker Ready**: Containerização completa com orquestração

## 🏗️ Arquitetura

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Browser   │────│   FastAPI App   │────│   NE8000 Device │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                │
                       ┌─────────────────┐
                       │   Redis Cache   │
                       └─────────────────┘
```

## 🚀 Instalação Rápida com Docker

### Pré-requisitos
- Docker 20.10+
- Docker Compose 2.0+

### 1. Clone o repositório
```bash
git clone <seu-repositorio>
cd ne80001506
```

### 2. Configure as variáveis de ambiente
```bash
cp .env.example .env
nano .env  # Edite com suas configurações
```

### 3. Inicie os serviços
```bash
# Construir e iniciar
docker-compose up --build -d

# Verificar status
docker-compose ps

# Ver logs
docker-compose logs -f app
```

### 4. Acesse a aplicação
- **Dashboard Principal**: http://localhost:8000
- **Dashboard Híbrido**: http://localhost:8000/hybrid
- **API Health Check**: http://localhost:8000/health

## ⚙️ Configuração

### 📝 Arquivo .env

Edite o arquivo `.env` com suas configurações:

```bash
# ============================================================================
# CONFIGURAÇÕES DE AUTENTICAÇÃO WEB
# ============================================================================
WEB_USERNAME=admin
WEB_PASSWORD=sua-senha-segura
SECRET_KEY=sua-chave-secreta-super-segura

# ============================================================================
# CONFIGURAÇÕES SSH (Sistema Original)
# ============================================================================
SSH_HOST=192.168.1.1
SSH_PORT=22
SSH_USERNAME=admin
SSH_PASSWORD=senha-do-equipamento

# ============================================================================
# CONFIGURAÇÕES SNMP (Sistema Híbrido) 
# ============================================================================
HUAWEI_SNMP_HOST=192.168.1.1
HUAWEI_SNMP_PORT=161
HUAWEI_SNMP_COMMUNITY=public

# ============================================================================
# CONFIGURAÇÕES REDIS (Cache)
# ============================================================================
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_TTL_DASHBOARD=60

# ============================================================================
# CONFIGURAÇÕES DE PERFORMANCE
# ============================================================================
SNMP_TIMEOUT=5
SNMP_RETRIES=3
COLLECTION_INTERVAL=30
DEBUG=False
```

### 🔧 Comandos Úteis

```bash
# Parar os serviços
docker-compose down

# Parar e remover volumes
docker-compose down -v

# Reconstruir apenas a aplicação
docker-compose build app

# Reiniciar apenas a aplicação
docker-compose restart app

# Ver logs específicos
docker-compose logs redis
docker-compose logs app

# Executar comandos no container
docker-compose exec app bash
docker-compose exec redis redis-cli
```

## 📊 API Endpoints

### 🏠 Dashboard
- `GET /` - Login page
- `GET /dashboard` - Dashboard original
- `GET /hybrid` - Dashboard híbrido

### 🔌 API Original
- `GET /api/online_total` - Total de usuários online
- `POST /api/pppoe_query` - Consultar usuário específico
- `POST /api/pppoe_disconnect` - Desconectar usuário
- `GET /api/connection_status` - Status da conexão SSH

### ⚡ API Híbrida
- `GET /api/hybrid/dashboard` - Dados do dashboard híbrido
- `GET /api/hybrid/charts` - Dados para gráficos
- `GET /api/hybrid/pppoe/interfaces` - Interfaces PPPoE detalhadas
- `GET /api/hybrid/network/traffic` - Tráfego de interfaces

### 🏥 Monitoramento
- `GET /health` - Health check
- `GET /api/system_info` - Informações do sistema
- `GET /api/cache_stats` - Estatísticas do cache

## 🛠️ Desenvolvimento

### Instalação Local (sem Docker)

```bash
# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate     # Windows

# Instalar dependências
pip install -r requirements.txt

# Instalar Redis localmente
# Ubuntu/Debian:
sudo apt-get install redis-server

# macOS:
brew install redis

# Windows:
# Baixar do site oficial do Redis

# Executar aplicação
python simple_main_v2_complete.py
```

### 🧪 Estrutura do Projeto

```
ne80001506/
├── 📁 modules/              # Módulos Python
│   ├── api_routes.py        # Rotas API originais
│   ├── cache_manager.py     # Gerenciamento de cache
│   ├── config.py           # Configurações
│   ├── hybrid_api_routes.py # Rotas API híbridas
│   ├── hybrid_scheduler.py  # Agendador híbrido
│   ├── huawei_hybrid_collector.py # Coletor SNMP
│   ├── interface_traffic_collector.py # Coletor de tráfego
│   ├── pppoe_parser.py     # Parser PPPoE
│   ├── ssh_connection.py   # Conexão SSH
│   └── web_routes.py       # Rotas web
├── 📁 static/              # Arquivos estáticos
│   ├── 📁 images/          # Imagens
│   └── 📁 js/              # JavaScript
├── 📁 templates/           # Templates HTML
├── 🐳 Dockerfile           # Imagem Docker
├── 🐳 docker-compose.yml   # Orquestração
├── 📋 requirements.txt     # Dependências Python
├── ⚙️ .env                # Variáveis de ambiente
└── 🚀 simple_main_v2_complete.py # Aplicação principal
```

## 🔒 Segurança

- ✅ Usuário não-root no container
- ✅ Health checks automáticos
- ✅ Variáveis de ambiente para senhas
- ✅ Middleware de sessão seguro
- ✅ CORS configurado adequadamente

## 📈 Monitoramento

### Health Checks
```bash
# Verificar saúde da aplicação
curl http://localhost:8000/health

# Verificar saúde do Redis
docker-compose exec redis redis-cli ping
```

### Logs
```bash
# Logs da aplicação
docker-compose logs -f app

# Logs do Redis
docker-compose logs -f redis

# Logs específicos por tempo
docker-compose logs --since="1h" app
```

## 🐛 Troubleshooting

### Problemas Comuns

**1. Erro de conexão SSH/SNMP**
```bash
# Verificar conectividade
docker-compose exec app ping <IP_DO_EQUIPAMENTO>

# Testar conexão SSH
docker-compose exec app telnet <IP_DO_EQUIPAMENTO> 22

# Verificar logs
docker-compose logs app | grep -i error
```

**2. Redis não conecta**
```bash
# Verificar status do Redis
docker-compose ps redis

# Testar conexão Redis
docker-compose exec app python -c "import redis; r=redis.Redis(host='redis'); print(r.ping())"
```

**3. Aplicação não inicia**
```bash
# Verificar logs de inicialização
docker-compose logs app

# Reconstruir imagem
docker-compose build --no-cache app
```

## 🤝 Contribuição

1. Fork o projeto
2. Crie uma branch (`git checkout -b feature/amazing-feature`)
3. Commit suas mudanças (`git commit -m 'Add amazing feature'`)
4. Push para a branch (`git push origin feature/amazing-feature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.

## 🙋‍♂️ Suporte

- 📧 Email: seu-email@exemplo.com
- 🐛 Issues: [GitHub Issues](https://github.com/seu-usuario/ne80001506/issues)
- 📖 Wiki: [Documentação Completa](https://github.com/seu-usuario/ne80001506/wiki)

---

**Desenvolvido com ❤️ para monitoramento de equipamentos Huawei NE8000** 