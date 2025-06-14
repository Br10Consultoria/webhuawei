from flask import Flask, jsonify
from dotenv import load_dotenv
from datetime import timedelta
import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler

# Adicionar o diretório raiz ao path para imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Carrega variáveis de ambiente
load_dotenv()

def create_app(*args, **kwargs):
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')
    
    # Configurações necessárias para gerar URLs corretamente
    app.config['SERVER_NAME'] = None  # Permite gerar URLs sem SERVER_NAME
    app.config['APPLICATION_ROOT'] = '/'
    app.config['PREFERRED_URL_SCHEME'] = 'http'
    
    # Configuração da sessão - expira em 30 minutos
    app.permanent_session_lifetime = timedelta(minutes=30)

    # Configuração do LOG com rotação por dia (30 dias)
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    handler = TimedRotatingFileHandler(
        filename=os.path.join(log_dir, 'app.log'),
        when='D',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    # Blueprints - imports corrigidos
    try:
        from routes.auth import auth_bp
        app.register_blueprint(auth_bp)
    except ImportError as e:
        app.logger.warning(f"Não foi possível importar auth_bp: {e}")
    
    try:
        from routes.pppoe import pppoe_bp
        app.register_blueprint(pppoe_bp)
    except ImportError as e:
        app.logger.warning(f"Não foi possível importar pppoe_bp: {e}")
    
    try:
        from routes.interface import interface_bp
        app.register_blueprint(interface_bp)
    except ImportError as e:
        app.logger.warning(f"Não foi possível importar interface_bp: {e}")
    
    try:
        from routes.logs import logs_bp
        app.register_blueprint(logs_bp)
    except ImportError as e:
        app.logger.warning(f"Não foi possível importar logs_bp: {e}")
    
    try:
        from routes.main import main_bp
        app.register_blueprint(main_bp)
    except ImportError as e:
        app.logger.warning(f"Não foi possível importar main_bp: {e}")
    
    try:
        from routes.api import api_bp
        app.register_blueprint(api_bp)
    except ImportError as e:
        app.logger.warning(f"Não foi possível importar api_bp: {e}")
    
    try:
        from routes.terminal import terminal_bp
        app.register_blueprint(terminal_bp)
    except ImportError as e:
        app.logger.warning(f"Não foi possível importar terminal_bp: {e}")

    @app.route('/health')
    def health_check():
        return jsonify({"status": "healthy"}), 200

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000)