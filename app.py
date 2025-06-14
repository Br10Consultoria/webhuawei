"""
Aplicação Flask principal com configuração de logging, CORS e serviços de background.
Esta aplicação gerencia rotas principais e APIs, além de executar serviços em background.
"""

import atexit
import logging
import os
import signal
import sys
from datetime import datetime, timedelta
from typing import Callable, Optional

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

# =============================================================================
# CONSTANTES
# =============================================================================

DEFAULT_SECRET_KEY: str = 'your-secret-key-here'
DEFAULT_PORT: int = 5000
LOG_FILENAME: str = 'app.log'
LOG_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Mensagens de log padronizadas
LOG_MESSAGES = {
    'starting_background_service': "Inicializando Router Background Service...",
    'background_service_started': "Router Background Service inicializado com sucesso",
    'stopping_background_service': "Parando Router Background Service...",
    'background_service_stopped': "Router Background Service parado com sucesso",
    'background_service_start_error': "Erro ao inicializar Background Service: {}",
    'background_service_stop_error': "Erro ao parar Background Service: {}",
    'signal_received': "Recebido sinal {}, parando aplicação...",
    'app_starting': "Iniciando aplicação na porta {}, debug={}",
    'app_interrupted': "Aplicação interrompida pelo usuário",
    'internal_error': "Erro interno: {}",
    'request_log': "{} {} - {}"
}

# =============================================================================
# CONFIGURAÇÃO DE LOGGING
# =============================================================================

def setup_logging() -> None:
    """Configura o sistema de logging da aplicação."""
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(LOG_FILENAME),
            logging.StreamHandler(sys.stdout)
        ]
    )


# =============================================================================
# CRIAÇÃO E CONFIGURAÇÃO DA APLICAÇÃO FLASK
# =============================================================================

def create_app() -> Flask:
    """
    Factory function para criar e configurar a aplicação Flask.
    
    Returns:
        Flask: Instância configurada da aplicação Flask
    """
    flask_app = Flask(__name__)
    flask_app.secret_key = os.environ.get('SECRET_KEY', DEFAULT_SECRET_KEY)
    
    # Configuração CORS
    CORS(flask_app)
    
    return flask_app


def register_blueprints(flask_app: Flask) -> None:
    """
    Registra todos os blueprints da aplicação.
    
    Args:
        flask_app: Instância da aplicação Flask
    """
    try:
        from routes.main import main_bp
        from routes.api import api_bp
        
        flask_app.register_blueprint(main_bp)
        flask_app.register_blueprint(api_bp)
        
    except ImportError as e:
        logging.error(f"Erro ao importar blueprints: {e}")
        raise


# =============================================================================
# GERENCIAMENTO DE SERVIÇOS DE BACKGROUND
# =============================================================================

def initialize_background_service() -> None:
    """
    Inicializa o serviço de background com tratamento de exceções.
    
    Raises:
        Exception: Re-levanta exceções após logging para permitir tratamento upstream
    """
    try:
        from services.background_service import start_background_service
        
        logging.info(LOG_MESSAGES['starting_background_service'])
        start_background_service()
        logging.info(LOG_MESSAGES['background_service_started'])
        
    except ImportError as e:
        error_msg = f"Falha ao importar background service: {e}"
        logging.error(error_msg)
        raise
    except Exception as e:
        logging.error(LOG_MESSAGES['background_service_start_error'].format(e))
        raise


def shutdown_background_service() -> None:
    """
    Para o serviço de background graciosamente com tratamento de exceções.
    """
    try:
        from services.background_service import stop_background_service
        
        logging.info(LOG_MESSAGES['stopping_background_service'])
        stop_background_service()
        logging.info(LOG_MESSAGES['background_service_stopped'])
        
    except ImportError as e:
        logging.warning(f"Background service não disponível para shutdown: {e}")
    except Exception as e:
        logging.error(LOG_MESSAGES['background_service_stop_error'].format(e))


# =============================================================================
# HANDLERS DE SINAL E SHUTDOWN
# =============================================================================

def create_signal_handler() -> Callable[[int, Optional[object]], None]:
    """
    Cria um handler para sinais de sistema.
    
    Returns:
        Função handler para sinais
    """
    def signal_handler(signum: int, frame: Optional[object]) -> None:
        logging.info(LOG_MESSAGES['signal_received'].format(signum))
        shutdown_background_service()
        sys.exit(0)
    
    return signal_handler


def register_shutdown_handlers() -> None:
    """Registra handlers para shutdown gracioso da aplicação."""
    atexit.register(shutdown_background_service)
    
    signal_handler = create_signal_handler()
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


# =============================================================================
# MIDDLEWARE E HANDLERS DE ERRO
# =============================================================================

def setup_middleware(flask_app: Flask) -> None:
    """
    Configura middleware da aplicação.
    
    Args:
        flask_app: Instância da aplicação Flask
    """
    @flask_app.before_first_request
    def startup() -> None:
        """Executa inicializações na primeira requisição."""
        initialize_background_service()
    
    @flask_app.after_request
    def log_request(response):
        """Loga requisições HTTP (exceto arquivos estáticos)."""
        if request.endpoint and not request.endpoint.startswith('static'):
            logging.info(
                LOG_MESSAGES['request_log'].format(
                    request.method, 
                    request.url, 
                    response.status_code
                )
            )
        return response


def setup_error_handlers(flask_app: Flask) -> None:
    """
    Configura handlers de erro personalizados.
    
    Args:
        flask_app: Instância da aplicação Flask
    """
    @flask_app.errorhandler(500)
    def internal_error(error):
        """Handler para erros internos do servidor."""
        logging.error(LOG_MESSAGES['internal_error'].format(error))
        return render_template('error.html', error="Erro interno do servidor"), 500

    @flask_app.errorhandler(404)
    def not_found(error):
        """Handler para páginas não encontradas."""
        return render_template('error.html', error="Página não encontrada"), 404


# =============================================================================
# FUNÇÃO PRINCIPAL E EXECUÇÃO
# =============================================================================

def get_app_config() -> tuple[int, bool]:
    """
    Obtém configurações da aplicação a partir de variáveis de ambiente.
    
    Returns:
        Tupla contendo (porta, modo_debug)
    """
    port = int(os.environ.get('PORT', DEFAULT_PORT))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    return port, debug


def run_application() -> None:
    """
    Executa a aplicação Flask com tratamento de exceções.
    """
    port, debug = get_app_config()
    
    logging.info(LOG_MESSAGES['app_starting'].format(port, debug))
    
    # Inicializar background service se ainda não foi inicializado
    if not hasattr(app, '_background_service_initialized'):
        try:
            initialize_background_service()
            app._background_service_initialized = True
        except Exception as e:
            logging.error(f"Falha crítica na inicialização do background service: {e}")
            # Continua execução mesmo com falha no background service
    
    try:
        app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
    except KeyboardInterrupt:
        logging.info(LOG_MESSAGES['app_interrupted'])
    except Exception as e:
        logging.error(f"Erro durante execução da aplicação: {e}")
        raise
    finally:
        shutdown_background_service()


# =============================================================================
# INICIALIZAÇÃO DA APLICAÇÃO
# =============================================================================

# Configurar logging
setup_logging()

# Criar aplicação Flask
app = create_app()

# Configurar aplicação
register_blueprints(app)
setup_middleware(app)
setup_error_handlers(app)

# Registrar handlers de shutdown
register_shutdown_handlers()


# =============================================================================
# PONTO DE ENTRADA
# =============================================================================

if __name__ == '__main__':
    run_application() 