"""
Sistema de autenticação otimizado com segurança aprimorada.
Implementa proteção contra ataques, rate limiting e logging de segurança.
"""

import hashlib
import hmac
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Dict, Optional, Tuple

from flask import (
    Blueprint, 
    current_app, 
    flash, 
    redirect, 
    render_template, 
    request, 
    session, 
    url_for
)

# =============================================================================
# CONSTANTES DE SEGURANÇA
# =============================================================================

# Configurações de sessão
SESSION_CONFIG = {
    'max_age_minutes': 60,          # Sessão expira em 60 minutos
    'inactivity_timeout_minutes': 30, # Timeout por inatividade
    'max_sessions_per_user': 3,     # Máximo de sessões simultâneas
    'session_renewal_threshold': 10, # Renovar sessão quando restam 10 min
}

# Configurações de rate limiting para login
LOGIN_RATE_LIMIT = {
    'max_attempts_per_ip': 5,       # Máximo 5 tentativas por IP
    'max_attempts_per_user': 3,     # Máximo 3 tentativas por usuário
    'lockout_duration_minutes': 15, # Bloqueio por 15 minutos
    'cleanup_interval_minutes': 30, # Limpeza de dados antigos
}

# Configurações de senha
PASSWORD_CONFIG = {
    'min_length': 8,
    'require_complexity': True,     # Letras, números e símbolos
    'max_login_time_seconds': 5,    # Máximo 5s para validar login
}

# Mensagens de erro padronizadas
ERROR_MESSAGES = {
    'login_required': 'Por favor, faça login para acessar esta página.',
    'session_expired': 'Sua sessão expirou. Faça login novamente.',
    'session_expired_inactivity': 'Sua sessão expirou por inatividade. Faça login novamente.',
    'invalid_credentials': 'Credenciais inválidas.',
    'account_locked': 'Conta temporariamente bloqueada devido a múltiplas tentativas de login. Tente novamente em {} minutos.',
    'ip_blocked': 'IP temporariamente bloqueado devido a múltiplas tentativas de login. Tente novamente em {} minutos.',
    'missing_fields': 'Por favor, preencha todos os campos.',
    'config_error': 'Erro de configuração do servidor. Contate o administrador.',
    'too_many_sessions': 'Muitas sessões ativas. Faça logout de outras sessões primeiro.',
    'weak_password': 'Senha não atende aos critérios de segurança.',
}

# =============================================================================
# BLUEPRINT E CACHE DE SEGURANÇA
# =============================================================================

auth_bp = Blueprint('auth', __name__)

# Cache thread-safe para rate limiting e sessões
import threading

_security_lock = threading.RLock()
_failed_login_attempts = {}  # {ip: {count: int, last_attempt: datetime, locked_until: datetime}}
_user_login_attempts = {}    # {username: {count: int, last_attempt: datetime, locked_until: datetime}}
_active_sessions = {}        # {username: [{session_id: str, ip: str, created: datetime, last_activity: datetime}]}


# =============================================================================
# UTILITÁRIOS DE SEGURANÇA
# =============================================================================

def _get_client_ip() -> str:
    """Obtém IP real do cliente considerando proxies."""
    # Verificar headers de proxy
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        # Pegar o primeiro IP da lista
        return forwarded_for.split(',')[0].strip()
    
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip.strip()
    
    return request.remote_addr or 'unknown'


def _generate_session_id() -> str:
    """Gera ID de sessão seguro."""
    return secrets.token_urlsafe(32)


def _hash_password(password: str, salt: str = None) -> Tuple[str, str]:
    """
    Gera hash seguro da senha.
    
    Args:
        password: Senha em texto plano
        salt: Salt opcional (se não fornecido, será gerado)
        
    Returns:
        Tupla (hash, salt)
    """
    if salt is None:
        salt = secrets.token_hex(16)
    
    # Usar PBKDF2 com SHA-256
    password_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # 100k iterações
    )
    
    return password_hash.hex(), salt


def _verify_password(password: str, password_hash: str, salt: str) -> bool:
    """
    Verifica senha usando timing-safe comparison.
    
    Args:
        password: Senha em texto plano
        password_hash: Hash armazenado
        salt: Salt usado no hash
        
    Returns:
        True se senha for válida
    """
    computed_hash, _ = _hash_password(password, salt)
    return hmac.compare_digest(password_hash, computed_hash)


def _validate_password_strength(password: str) -> bool:
    """
    Valida força da senha.
    
    Args:
        password: Senha para validar
        
    Returns:
        True se senha atender aos critérios
    """
    if len(password) < PASSWORD_CONFIG['min_length']:
        return False
    
    if PASSWORD_CONFIG['require_complexity']:
        has_letter = any(c.isalpha() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_symbol = any(not c.isalnum() for c in password)
        
        return has_letter and has_digit and has_symbol
    
    return True


def _is_ip_blocked(ip: str) -> Tuple[bool, int]:
    """
    Verifica se IP está bloqueado.
    
    Args:
        ip: Endereço IP
        
    Returns:
        Tupla (is_blocked, minutes_remaining)
    """
    with _security_lock:
        if ip not in _failed_login_attempts:
            return False, 0
        
        attempt_data = _failed_login_attempts[ip]
        locked_until = attempt_data.get('locked_until')
        
        if locked_until and datetime.now() < locked_until:
            minutes_remaining = int((locked_until - datetime.now()).total_seconds() / 60) + 1
            return True, minutes_remaining
        
        return False, 0


def _is_user_blocked(username: str) -> Tuple[bool, int]:
    """
    Verifica se usuário está bloqueado.
    
    Args:
        username: Nome do usuário
        
    Returns:
        Tupla (is_blocked, minutes_remaining)
    """
    with _security_lock:
        if username not in _user_login_attempts:
            return False, 0
        
        attempt_data = _user_login_attempts[username]
        locked_until = attempt_data.get('locked_until')
        
        if locked_until and datetime.now() < locked_until:
            minutes_remaining = int((locked_until - datetime.now()).total_seconds() / 60) + 1
            return True, minutes_remaining
        
        return False, 0


def _record_failed_login(ip: str, username: str) -> None:
    """
    Registra tentativa de login falhada.
    
    Args:
        ip: Endereço IP
        username: Nome do usuário
    """
    with _security_lock:
        current_time = datetime.now()
        
        # Registrar falha por IP
        if ip not in _failed_login_attempts:
            _failed_login_attempts[ip] = {'count': 0, 'last_attempt': current_time}
        
        _failed_login_attempts[ip]['count'] += 1
        _failed_login_attempts[ip]['last_attempt'] = current_time
        
        # Bloquear IP se exceder limite
        if _failed_login_attempts[ip]['count'] >= LOGIN_RATE_LIMIT['max_attempts_per_ip']:
            lockout_duration = timedelta(minutes=LOGIN_RATE_LIMIT['lockout_duration_minutes'])
            _failed_login_attempts[ip]['locked_until'] = current_time + lockout_duration
        
        # Registrar falha por usuário
        if username not in _user_login_attempts:
            _user_login_attempts[username] = {'count': 0, 'last_attempt': current_time}
        
        _user_login_attempts[username]['count'] += 1
        _user_login_attempts[username]['last_attempt'] = current_time
        
        # Bloquear usuário se exceder limite
        if _user_login_attempts[username]['count'] >= LOGIN_RATE_LIMIT['max_attempts_per_user']:
            lockout_duration = timedelta(minutes=LOGIN_RATE_LIMIT['lockout_duration_minutes'])
            _user_login_attempts[username]['locked_until'] = current_time + lockout_duration


def _reset_login_attempts(ip: str, username: str) -> None:
    """
    Reseta contadores de tentativas de login após sucesso.
    
    Args:
        ip: Endereço IP
        username: Nome do usuário
    """
    with _security_lock:
        if ip in _failed_login_attempts:
            del _failed_login_attempts[ip]
        
        if username in _user_login_attempts:
            del _user_login_attempts[username]


def _cleanup_old_attempts() -> None:
    """Remove tentativas antigas de login."""
    with _security_lock:
        current_time = datetime.now()
        cleanup_threshold = current_time - timedelta(minutes=LOGIN_RATE_LIMIT['cleanup_interval_minutes'])
        
        # Limpar tentativas por IP
        expired_ips = []
        for ip, data in _failed_login_attempts.items():
            if data['last_attempt'] < cleanup_threshold:
                expired_ips.append(ip)
        
        for ip in expired_ips:
            del _failed_login_attempts[ip]
        
        # Limpar tentativas por usuário
        expired_users = []
        for username, data in _user_login_attempts.items():
            if data['last_attempt'] < cleanup_threshold:
                expired_users.append(username)
        
        for username in expired_users:
            del _user_login_attempts[username]


def _manage_user_sessions(username: str, session_id: str, ip: str) -> bool:
    """
    Gerencia sessões ativas do usuário.
    
    Args:
        username: Nome do usuário
        session_id: ID da sessão
        ip: Endereço IP
        
    Returns:
        True se sessão foi aceita, False se rejeitada
    """
    with _security_lock:
        current_time = datetime.now()
        
        if username not in _active_sessions:
            _active_sessions[username] = []
        
        user_sessions = _active_sessions[username]
        
        # Remover sessões expiradas
        session_timeout = timedelta(minutes=SESSION_CONFIG['max_age_minutes'])
        active_sessions = []
        
        for sess in user_sessions:
            if current_time - sess['last_activity'] < session_timeout:
                active_sessions.append(sess)
        
        _active_sessions[username] = active_sessions
        
        # Verificar limite de sessões
        if len(active_sessions) >= SESSION_CONFIG['max_sessions_per_user']:
            return False
        
        # Adicionar nova sessão
        new_session = {
            'session_id': session_id,
            'ip': ip,
            'created': current_time,
            'last_activity': current_time
        }
        
        _active_sessions[username].append(new_session)
        return True


def _update_session_activity(username: str, session_id: str) -> None:
    """
    Atualiza atividade da sessão.
    
    Args:
        username: Nome do usuário
        session_id: ID da sessão
    """
    with _security_lock:
        if username in _active_sessions:
            for sess in _active_sessions[username]:
                if sess['session_id'] == session_id:
                    sess['last_activity'] = datetime.now()
                    break


def _remove_user_session(username: str, session_id: str) -> None:
    """
    Remove sessão específica do usuário.
    
    Args:
        username: Nome do usuário
        session_id: ID da sessão
    """
    with _security_lock:
        if username in _active_sessions:
            _active_sessions[username] = [
                sess for sess in _active_sessions[username]
                if sess['session_id'] != session_id
            ]


# =============================================================================
# DECORADOR DE AUTENTICAÇÃO OTIMIZADO
# =============================================================================

def login_required(f):
    """
    Decorator otimizado para verificação de autenticação.
    
    Args:
        f: Função a ser decorada
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Verificar se usuário está logado
        if not session.get('logged_in'):
            flash(ERROR_MESSAGES['login_required'], 'warning')
            return redirect(url_for('auth.login'))
        
        username = session.get('username')
        session_id = session.get('session_id')
        
        if not username or not session_id:
            session.clear()
            flash(ERROR_MESSAGES['session_expired'], 'warning')
            return redirect(url_for('auth.login'))
        
        # Verificar expiração da sessão
        last_activity = session.get('last_activity')
        if last_activity:
            try:
                last_activity = datetime.fromisoformat(last_activity)
                current_time = datetime.now()
                
                # Verificar timeout de inatividade
                inactivity_timeout = timedelta(minutes=SESSION_CONFIG['inactivity_timeout_minutes'])
                if current_time - last_activity > inactivity_timeout:
                    _remove_user_session(username, session_id)
                    session.clear()
                    flash(ERROR_MESSAGES['session_expired_inactivity'], 'warning')
                    return redirect(url_for('auth.login'))
                
                # Verificar expiração total da sessão
                session_created = session.get('created_at')
                if session_created:
                    session_created = datetime.fromisoformat(session_created)
                    max_age = timedelta(minutes=SESSION_CONFIG['max_age_minutes'])
                    
                    if current_time - session_created > max_age:
                        _remove_user_session(username, session_id)
                        session.clear()
                        flash(ERROR_MESSAGES['session_expired'], 'warning')
                        return redirect(url_for('auth.login'))
                
                # Renovar sessão se próxima do vencimento
                time_remaining = max_age - (current_time - session_created)
                renewal_threshold = timedelta(minutes=SESSION_CONFIG['session_renewal_threshold'])
                
                if time_remaining < renewal_threshold:
                    session['created_at'] = current_time.isoformat()
                    current_app.logger.info(f"Sessão renovada para usuário: {username}")
            
            except ValueError:
                # Formato de data inválido
                session.clear()
                flash(ERROR_MESSAGES['session_expired'], 'warning')
                return redirect(url_for('auth.login'))
        
        # Atualizar atividade da sessão
        current_time = datetime.now()
        session['last_activity'] = current_time.isoformat()
        _update_session_activity(username, session_id)
        
        # Limpar tentativas antigas periodicamente
        _cleanup_old_attempts()
        
        return f(*args, **kwargs)
    
    return decorated_function


# =============================================================================
# ROTAS DE AUTENTICAÇÃO
# =============================================================================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Endpoint de login com segurança aprimorada."""
    # Se já está logado, redirecionar
    if session.get('logged_in'):
        return redirect(url_for('main.index'))
    
    if request.method == 'GET':
        return render_template('login.html')
    
    # POST - Processar login
    start_time = time.time()
    
    try:
        # Obter dados do formulário
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        client_ip = _get_client_ip()
        
        # Validações básicas
        if not username or not password:
            flash(ERROR_MESSAGES['missing_fields'], 'error')
            return render_template('login.html')
        
        # Verificar se IP está bloqueado
        ip_blocked, ip_minutes = _is_ip_blocked(client_ip)
        if ip_blocked:
            current_app.logger.warning(f"Login bloqueado por IP: {client_ip}")
            flash(ERROR_MESSAGES['ip_blocked'].format(ip_minutes), 'error')
            return render_template('login.html')
        
        # Verificar se usuário está bloqueado
        user_blocked, user_minutes = _is_user_blocked(username)
        if user_blocked:
            current_app.logger.warning(f"Login bloqueado para usuário: {username}")
            flash(ERROR_MESSAGES['account_locked'].format(user_minutes), 'error')
            return render_template('login.html')
        
        # Obter credenciais esperadas
        expected_username = os.getenv('WEB_USERNAME')
        expected_password = os.getenv('WEB_PASSWORD')
        
        if not expected_username or not expected_password:
            current_app.logger.error("Credenciais não configuradas nas variáveis de ambiente")
            flash(ERROR_MESSAGES['config_error'], 'error')
            return render_template('login.html')
        
        # Limitar tempo de processamento (mitigar timing attacks)
        min_processing_time = 0.5  # Mínimo 500ms
        
        # Validar credenciais
        credentials_valid = (
            hmac.compare_digest(username, expected_username) and
            hmac.compare_digest(password, expected_password)
        )
        
        # Aguardar tempo mínimo de processamento
        elapsed_time = time.time() - start_time
        if elapsed_time < min_processing_time:
            time.sleep(min_processing_time - elapsed_time)
        
        if not credentials_valid:
            # Registrar falha de login
            _record_failed_login(client_ip, username)
            
            current_app.logger.warning(
                f"Tentativa de login falhada - Usuario: {username}, IP: {client_ip}, "
                f"User-Agent: {request.headers.get('User-Agent', 'unknown')}"
            )
            
            flash(ERROR_MESSAGES['invalid_credentials'], 'error')
            return render_template('login.html')
        
        # Login bem-sucedido
        session_id = _generate_session_id()
        
        # Verificar limite de sessões
        if not _manage_user_sessions(username, session_id, client_ip):
            current_app.logger.warning(f"Muitas sessões ativas para usuário: {username}")
            flash(ERROR_MESSAGES['too_many_sessions'], 'error')
            return render_template('login.html')
        
        # Configurar sessão
        current_time = datetime.now()
        session.permanent = True
        session['logged_in'] = True
        session['username'] = username
        session['session_id'] = session_id
        session['created_at'] = current_time.isoformat()
        session['last_activity'] = current_time.isoformat()
        session['login_ip'] = client_ip
        
        # Resetar contadores de falha
        _reset_login_attempts(client_ip, username)
        
        # Log de sucesso
        current_app.logger.info(
            f"Login bem-sucedido - Usuario: {username}, IP: {client_ip}, "
            f"Session ID: {session_id[:8]}..."
        )
        
        flash('Login realizado com sucesso!', 'success')
        
        # Redirecionar para página solicitada ou dashboard
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        
        return redirect(url_for('main.index'))
    
    except Exception as e:
        current_app.logger.error(f"Erro no processo de login: {e}")
        flash('Erro interno no processo de login. Tente novamente.', 'error')
        return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    """Endpoint de logout com limpeza de sessão."""
    try:
        username = session.get('username')
        session_id = session.get('session_id')
        
        if username and session_id:
            # Remover sessão do cache
            _remove_user_session(username, session_id)
            
            current_app.logger.info(f"Logout realizado - Usuario: {username}, Session: {session_id[:8]}...")
        
        # Limpar sessão
        session.clear()
        
        flash('Logout realizado com sucesso', 'success')
        return redirect(url_for('auth.login'))
    
    except Exception as e:
        current_app.logger.error(f"Erro no logout: {e}")
        session.clear()
        return redirect(url_for('auth.login'))


@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Endpoint para alteração de senha."""
    if request.method == 'GET':
        return render_template('change_password.html')
    
    try:
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        # Validações
        if not all([current_password, new_password, confirm_password]):
            flash('Por favor, preencha todos os campos.', 'error')
            return render_template('change_password.html')
        
        if new_password != confirm_password:
            flash('Nova senha e confirmação não coincidem.', 'error')
            return render_template('change_password.html')
        
        if not _validate_password_strength(new_password):
            flash(ERROR_MESSAGES['weak_password'], 'error')
            return render_template('change_password.html')
        
        # Verificar senha atual
        expected_password = os.getenv('WEB_PASSWORD')
        if not hmac.compare_digest(current_password, expected_password):
            flash('Senha atual incorreta.', 'error')
            return render_template('change_password.html')
        
        # Nota: Em um sistema real, aqui atualizaríamos a senha no banco de dados
        # Por enquanto, apenas log da solicitação
        username = session.get('username')
        current_app.logger.info(f"Solicitação de alteração de senha - Usuario: {username}")
        
        flash('Funcionalidade de alteração de senha não implementada nesta versão.', 'info')
        return render_template('change_password.html')
    
    except Exception as e:
        current_app.logger.error(f"Erro na alteração de senha: {e}")
        flash('Erro interno. Tente novamente.', 'error')
        return render_template('change_password.html')


@auth_bp.route('/sessions')
@login_required
def list_sessions():
    """Lista sessões ativas do usuário."""
    try:
        username = session.get('username')
        current_session_id = session.get('session_id')
        
        with _security_lock:
            user_sessions = _active_sessions.get(username, [])
            
            # Preparar dados das sessões para exibição
            sessions_data = []
            for sess in user_sessions:
                is_current = sess['session_id'] == current_session_id
                
                sessions_data.append({
                    'session_id': sess['session_id'][:8] + '...',  # Mascarar ID
                    'ip': sess['ip'],
                    'created': sess['created'].strftime('%d/%m/%Y %H:%M:%S'),
                    'last_activity': sess['last_activity'].strftime('%d/%m/%Y %H:%M:%S'),
                    'is_current': is_current
                })
        
        return render_template('sessions.html', sessions=sessions_data)
    
    except Exception as e:
        current_app.logger.error(f"Erro ao listar sessões: {e}")
        flash('Erro ao carregar sessões.', 'error')
        return redirect(url_for('main.index'))


@auth_bp.route('/security_log')
@login_required
def security_log():
    """Exibe log de segurança (apenas para administradores)."""
    try:
        # Em um sistema real, verificaria permissões de administrador aqui
        
        # Obter dados de segurança
        with _security_lock:
            security_data = {
                'failed_ip_attempts': dict(_failed_login_attempts),
                'failed_user_attempts': dict(_user_login_attempts),
                'active_sessions_count': sum(len(sessions) for sessions in _active_sessions.values()),
                'total_active_users': len(_active_sessions),
            }
        
        return render_template('security_log.html', data=security_data)
    
    except Exception as e:
        current_app.logger.error(f"Erro ao carregar log de segurança: {e}")
        flash('Erro ao carregar log de segurança.', 'error')
        return redirect(url_for('main.index'))


# =============================================================================
# FUNÇÕES DE INICIALIZAÇÃO
# =============================================================================

def init_security_cleanup():
    """Inicializa thread de limpeza de segurança."""
    def cleanup_thread():
        while True:
            try:
                time.sleep(LOGIN_RATE_LIMIT['cleanup_interval_minutes'] * 60)
                _cleanup_old_attempts()
            except Exception as e:
                current_app.logger.error(f"Erro na limpeza de segurança: {e}")
    
    import threading
    thread = threading.Thread(target=cleanup_thread, daemon=True)
    thread.start()


# Inicializar limpeza ao importar o módulo
try:
    init_security_cleanup()
except:
    pass  # Silenciar erros de inicialização 