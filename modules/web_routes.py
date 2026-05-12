"""
Módulo de rotas Web — Login, 2FA TOTP, páginas principais
"""
import logging
import os
import pyotp
import qrcode
import io
import base64
from fastapi import Request, Form
from . import audit_log
from .audit_log import AuditEvent, record as audit_record
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")


def get_template_context(request: Request, **kwargs):
    logged_in = False
    username = ""
    try:
        if hasattr(request, 'session') and request.session:
            logged_in = request.session.get("logged_in", False)
            username = request.session.get("username", "")
    except Exception:
        logged_in = False
    context = {"request": request, "session": {"logged_in": logged_in, "username": username}}
    context.update(kwargs)
    return context


def check_auth_redirect(request: Request):
    try:
        if not hasattr(request, 'session') or not request.session.get("logged_in"):
            return RedirectResponse(url="/login", status_code=302)
    except Exception:
        return RedirectResponse(url="/login", status_code=302)
    return None


def _get_totp_secret() -> str:
    secret = os.getenv("TOTP_SECRET", "")
    if not secret:
        secret = pyotp.random_base32()
        logger.warning(f"TOTP_SECRET nao configurado. Segredo gerado: {secret}")
        logger.warning("Adicione TOTP_SECRET ao .env para persistir o 2FA!")
    return secret


def _is_2fa_enabled() -> bool:
    return os.getenv("TOTP_ENABLED", "false").lower() in ("true", "1", "yes")


def _verify_totp(token: str) -> bool:
    try:
        secret = _get_totp_secret()
        totp = pyotp.TOTP(secret)
        return totp.verify(token, valid_window=1)
    except Exception as e:
        logger.error(f"Erro ao verificar TOTP: {e}")
        return False


async def login_page(request: Request, error: str = None):
    try:
        if request.session.get("logged_in"):
            return RedirectResponse(url="/dashboard", status_code=302)
    except Exception:
        pass
    context = get_template_context(request, error=error, totp_enabled=_is_2fa_enabled())
    return templates.TemplateResponse("login.html", context)


async def login_post(request: Request, username: str = Form(...), password: str = Form(...), totp_token: str = Form(default="")):
    web_user = os.getenv("WEB_USERNAME", "admin")
    web_pass = os.getenv("WEB_PASSWORD", "admin")

    if username != web_user or password != web_pass:
        audit_record(AuditEvent.LOGIN_FAILURE, request=request, web_user=username, detail="Senha ou usuario incorretos", success=False)
        context = get_template_context(request, error="Usuário ou senha incorretos.", totp_enabled=_is_2fa_enabled())
        return templates.TemplateResponse("login.html", context)

    if _is_2fa_enabled():
        if not totp_token or not totp_token.strip():
            context = get_template_context(request, error="Código 2FA obrigatório.", totp_enabled=True, show_totp=True, prefill_user=username)
            return templates.TemplateResponse("login.html", context)
        if not _verify_totp(totp_token.strip()):
            audit_record(AuditEvent.LOGIN_FAILURE, request=request, web_user=username, detail="Codigo 2FA invalido ou expirado", success=False)
            context = get_template_context(request, error="Código 2FA inválido ou expirado.", totp_enabled=True, show_totp=True, prefill_user=username)
            return templates.TemplateResponse("login.html", context)

    request.session["logged_in"] = True
    request.session["username"] = username
    logger.info(f"Login bem-sucedido: {username}")
    audit_record(AuditEvent.LOGIN_SUCCESS, request=request, web_user=username, detail=f"Login bem-sucedido", success=True)
    return RedirectResponse(url="/dashboard", status_code=302)


async def logout(request: Request):
    username = request.session.get("username", "")
    audit_record(AuditEvent.LOGOUT, request=request, web_user=username, detail="Logout", success=True)
    request.session.clear()
    logger.info(f"Logout: {username}")
    return RedirectResponse(url="/login", status_code=302)


async def setup_2fa_page(request: Request):
    auth_redirect = check_auth_redirect(request)
    if auth_redirect:
        return auth_redirect

    secret = _get_totp_secret()
    web_user = os.getenv("WEB_USERNAME", "admin")
    issuer = os.getenv("TOTP_ISSUER", "NE8000 Monitor")

    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=web_user, issuer_name=issuer)

    qr = qrcode.QRCode(version=1, box_size=6, border=4)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    audit_record(AuditEvent.SETUP_2FA_VIEW, request=request,
        web_user=request.session.get("username",""), detail="Visualizou pagina de configuracao 2FA", success=True)
    context = get_template_context(request, secret=secret, qr_b64=qr_b64,
        provisioning_uri=provisioning_uri, totp_enabled=_is_2fa_enabled(),
        issuer=issuer, web_user=web_user)
    return templates.TemplateResponse("setup_2fa.html", context)


async def dashboard(request: Request):
    auth_redirect = check_auth_redirect(request)
    if auth_redirect:
        return auth_redirect
    context = get_template_context(request)
    return templates.TemplateResponse("simple_dashboard.html", context)


async def pppoe_page(request: Request):
    auth_redirect = check_auth_redirect(request)
    if auth_redirect:
        return auth_redirect
    context = get_template_context(request)
    return templates.TemplateResponse("pppoe.html", context)


async def interfaces_pppoe_page(request: Request):
    auth_redirect = check_auth_redirect(request)
    if auth_redirect:
        return auth_redirect
    context = get_template_context(request)
    return templates.TemplateResponse("interfaces_pppoe.html", context)


async def interfaces_traffic_page(request: Request):
    auth_redirect = check_auth_redirect(request)
    if auth_redirect:
        return auth_redirect
    return RedirectResponse(url="/interfaces/pppoe", status_code=302)


async def bandwidth_graph_page(request: Request, username: str):
    auth_redirect = check_auth_redirect(request)
    if auth_redirect:
        return auth_redirect
    context = get_template_context(request, username=username)
    return templates.TemplateResponse("bandwidth_graph.html", context)


async def pppoe_history_page(request: Request, username: str):
    auth_redirect = check_auth_redirect(request)
    if auth_redirect:
        return auth_redirect
    context = get_template_context(request, username=username)
    return templates.TemplateResponse("pppoe_history.html", context)
