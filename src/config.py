import os
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env
load_dotenv()

# Router credentials and connection settings
ROUTER_HOST = os.getenv('ROUTER_HOST')
ROUTER_USERNAME = os.getenv('ROUTER_USERNAME')
ROUTER_PASSWORD = os.getenv('ROUTER_PASSWORD')
ROUTER_ENABLE_PASSWORD = os.getenv('ROUTER_ENABLE_PASSWORD')
ROUTER_PROTOCOL = os.getenv('ROUTER_PROTOCOL', 'ssh').lower()
ROUTER_SSH_PORT = int(os.getenv('ROUTER_SSH_PORT', '22'))
ROUTER_TELNET_PORT = int(os.getenv('ROUTER_TELNET_PORT', '23'))

# Web application credentials
WEB_USERNAME = os.getenv('WEB_USERNAME')
WEB_PASSWORD = os.getenv('WEB_PASSWORD')

# Flask secret key
APP_SECRET_KEY = os.getenv('FLASK_SECRET_KEY')

# Validação de variáveis obrigatórias
required_vars = [
    'ROUTER_HOST',
    'ROUTER_USERNAME',
    'ROUTER_PASSWORD',
    'WEB_USERNAME',
    'WEB_PASSWORD',
    'FLASK_SECRET_KEY'
]

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Validação do protocolo
if ROUTER_PROTOCOL not in ['ssh', 'telnet']:
    raise ValueError("ROUTER_PROTOCOL must be either 'ssh' or 'telnet'")