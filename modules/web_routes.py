"""
Módulo de rotas Web - Páginas simplificadas (apenas login e PPPoE)
"""

import logging
import os
from fastapi import Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")

def get_template_context(request: Request, **kwargs):
    """Criar contexto padrão para templates"""
    logged_in = False
    try:
        if hasattr(request, 'session') and request.session:
            logged_in = request.session.get("logged_in", False)
    except:
        logged_in = False
    
    context = {
        "request": request,
        "session": {"logged_in": logged_in}
    }
    context.update(kwargs)
    return context

def check_auth_redirect(request: Request):
    """Verificar se precisa redirecionar para login"""
    try:
        if not hasattr(request, 'session') or not request.session.get("logged_in"):
            return RedirectResponse(url="/login", status_code=302)
    except:
        return RedirectResponse(url="/login", status_code=302)
    return None

# Rotas de autenticação
async def login_page(request: Request, error: str = None):
    """Página de login"""
    context = get_template_context(request, error=error)
    return templates.TemplateResponse("login.html", context)

async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    """Processar login"""
    web_user = os.getenv("WEB_USERNAME", "admin")
    web_pass = os.getenv("WEB_PASSWORD", "admin")
    
    if username == web_user and password == web_pass:
        request.session["logged_in"] = True
        return RedirectResponse(url="/dashboard", status_code=302)
    else:
        context = get_template_context(request, error="Credenciais inválidas")
        return templates.TemplateResponse("login.html", context)

async def logout(request: Request):
    """Processar logout"""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)

# Rotas principais
async def dashboard(request: Request):
    """Dashboard principal"""
    auth_redirect = check_auth_redirect(request)
    if auth_redirect:
        return auth_redirect
    context = get_template_context(request)
    return templates.TemplateResponse("simple_dashboard.html", context)

async def pppoe_page(request: Request):
    """Página PPPoE"""
    auth_redirect = check_auth_redirect(request)
    if auth_redirect:
        return auth_redirect
    context = get_template_context(request)
    return templates.TemplateResponse("pppoe.html", context)

async def bandwidth_graph_page(request: Request, username: str):
    """Página de gráfico de banda para usuário específico"""
    auth_redirect = check_auth_redirect(request)
    if auth_redirect:
        return auth_redirect
    context = get_template_context(request, username=username)
    return templates.TemplateResponse("bandwidth_graph.html", context)

async def pppoe_history_page(request: Request, username: str):
    """Página de histórico PPPoE para usuário específico"""
    auth_redirect = check_auth_redirect(request)
    if auth_redirect:
        return auth_redirect
    context = get_template_context(request, username=username)
    return templates.TemplateResponse("pppoe_history.html", context)

async def interfaces_pppoe_page(request: Request):
    """Página de interfaces PPPoE detalhadas"""
    auth_redirect = check_auth_redirect(request)
    if auth_redirect:
        return auth_redirect
    context = get_template_context(request)
    return templates.TemplateResponse("interfaces_pppoe.html", context)

async def interfaces_traffic_page(request: Request):
    """Página de tráfego de interfaces"""
    auth_redirect = check_auth_redirect(request)
    if auth_redirect:
        return auth_redirect
    context = get_template_context(request)
    return templates.TemplateResponse("interfaces_traffic.html", context) 