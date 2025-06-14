from .pppoe import pppoe_bp
from .interface import interface_bp
from .logs import logs_bp
from .main import main_bp
from .auth import auth_bp
from .api import api_bp
from .terminal import terminal_bp

def register_blueprints(app):
    app.register_blueprint(pppoe_bp)
    app.register_blueprint(interface_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(terminal_bp)
