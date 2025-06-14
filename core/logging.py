"""
Configuração de logging estruturado para FastAPI
"""

import logging
import sys
from pathlib import Path
from loguru import logger
from core.config import settings


def setup_logging():
    """Configura o sistema de logging da aplicação"""
    
    # Remover handlers padrão do loguru
    logger.remove()
    
    # Criar diretório de logs se não existir
    log_path = Path(settings.LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Formato de log
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    # Handler para console
    logger.add(
        sys.stdout,
        format=log_format,
        level=settings.LOG_LEVEL,
        colorize=True,
        backtrace=True,
        diagnose=True
    )
    
    # Handler para arquivo
    logger.add(
        settings.LOG_FILE,
        format=log_format,
        level=settings.LOG_LEVEL,
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        compression="zip",
        backtrace=True,
        diagnose=True,
        enqueue=True  # Thread-safe
    )
    
    # Configurar logging padrão do Python para usar loguru
    class InterceptHandler(logging.Handler):
        def emit(self, record):
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno
            
            frame, depth = logging.currentframe(), 2
            while frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1
            
            logger.opt(depth=depth, exception=record.exc_info).log(
                level, record.getMessage()
            )
    
    # Interceptar logs do uvicorn
    logging.getLogger("uvicorn").handlers = [InterceptHandler()]
    logging.getLogger("uvicorn.access").handlers = [InterceptHandler()]
    logging.getLogger("fastapi").handlers = [InterceptHandler()]
    
    # Configurar nível global
    logging.getLogger().setLevel(getattr(logging, settings.LOG_LEVEL))
    
    logger.info("🔧 Sistema de logging configurado")


def get_logger(name: str = None):
    """Obtém um logger configurado"""
    if name:
        return logger.bind(module=name)
    return logger 