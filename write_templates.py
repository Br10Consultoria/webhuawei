#!/usr/bin/env python3.11
"""Script para sobrescrever todos os templates com o novo visual profissional."""
import os

TEMPLATES_DIR = "/home/ubuntu/webhuawei/templates"

# ============================================================
# LOGIN.HTML
# ============================================================
LOGIN_HTML = """\
{% extends "base.html" %}
{% block title %}Login — NE8000 Manager{% endblock %}
{% block content %}
<div class="w-full max-w-md">
    <div class="bg-white rounded-2xl shadow-2xl overflow-hidden">
        <div class="bg-gradient-to-r from-blue-700 to-blue-900 px-8 py-8 text-center">
            <div class="w-16 h-16 bg-white/10 rounded-2xl mx-auto flex items-center justify-center mb-4">
                <i class="fas fa-network-wired text-white text-2xl"></i>
            </div>
            <h1 class="text-white text-xl font-bold">NE8000 Network Manager</h1>
            <p class="text-blue-200 text-sm mt-1">Huawei BNG — Painel de Gerenciamento</p>
        </div>
        <div class="px-8 py-7">
            {% if error %}
            <div class="mb-5 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-red-700 text-sm">
                <i class="fas fa-circle-xmark flex-shrink-0"></i><span>{{ error }}</span>
            </div>
            {% endif %}
            <form method="POST" action="/login" id="loginForm" class="space-y-4">
                <div>
                    <label class="block text-xs font-semibold text-slate-600 mb-1.5 uppercase tracking-wide">Usuario</label>
                    <div class="relative">
                        <i class="fas fa-user absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm"></i>
                        <input type="text" name="username" id="username" required autocomplete="username"
                               value="{% if prefill_user %}{{ prefill_user }}{% endif %}"
                               class="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
                               placeholder="Digite seu usuario">
                    </div>
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-600 mb-1.5 uppercase tracking-wide">Senha</label>
                    <div class="relative">
                        <i class="fas fa-lock absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm"></i>
                        <input type="password" name="password" id="password" required autocomplete="current-password"
                               class="w-full pl-10 pr-10 py-2.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition"
                               placeholder="Digite sua senha">
                        <button type="button" onclick="togglePwd()" class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                            <i class="fas fa-eye text-sm" id="eyeIcon"></i>
                        </button>
                    </div>
                </div>
                {% if totp_enabled %}
                <div id="totpSection" {% if not show_totp %}class="hidden"{% endif %}>
                    <label class="block text-xs font-semibold text-slate-600 mb-1.5 uppercase tracking-wide">
                        <i class="fas fa-shield-halved text-blue-500 mr-1"></i>Codigo 2FA
                    </label>
                    <div class="relative">
                        <i class="fas fa-key absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm"></i>
                        <input type="text" name="totp_token" id="totp_token"
                               inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code"
                               class="w-full pl-10 pr-4 py-2.5 border border-blue-200 rounded-lg text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition font-mono tracking-widest text-center text-lg"
                               placeholder="000000">
                    </div>
                    <p class="text-xs text-slate-500 mt-1.5">Abra o Google Authenticator / Authy e insira o codigo de 6 digitos.</p>
                </div>
                {% endif %}
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white py-2.5 rounded-lg font-semibold text-sm transition flex items-center justify-center gap-2 mt-1">
                    <i class="fas fa-right-to-bracket"></i> Entrar
                </button>
            </form>
            <div class="mt-5 pt-4 border-t border-slate-100 text-center space-y-1">
                <p class="text-xs text-slate-400"><i class="fas fa-lock text-slate-300 mr-1"></i>Acesso restrito — credenciais via variaveis de ambiente</p>
                {% if totp_enabled %}<p class="text-xs text-blue-500"><i class="fas fa-shield-halved mr-1"></i>Autenticacao de dois fatores ativada</p>{% endif %}
            </div>
        </div>
    </div>
</div>
<script>
document.addEventListener('DOMContentLoaded', function() {
    {% if totp_enabled and not show_totp %}
    const form = document.getElementById('loginForm');
    const totpSection = document.getElementById('totpSection');
    if (form && totpSection) {
        form.addEventListener('submit', function(e) {
            if (totpSection.classList.contains('hidden')) {
                e.preventDefault();
                totpSection.classList.remove('hidden');
                const t = document.getElementById('totp_token');
                if (t) t.focus();
                return false;
            }
        });
    }
    {% endif %}
    const t = document.getElementById('totp_token');
    const u = document.getElementById('username');
    if (t && !t.closest('.hidden')) { t.focus(); }
    else if (u) { u.focus(); }
});
function togglePwd() {
    const p = document.getElementById('password'), i = document.getElementById('eyeIcon');
    if (!p) return;
    if (p.type === 'password') { p.type = 'text'; i.className = 'fas fa-eye-slash text-sm'; }
    else { p.type = 'password'; i.className = 'fas fa-eye text-sm'; }
}
</script>
{% endblock %}
"""

# ============================================================
# SETUP_2FA.HTML
# ============================================================
SETUP_2FA_HTML = """\
{% extends "base.html" %}
{% block title %}Configurar 2FA — NE8000 Manager{% endblock %}
{% block page_title %}Autenticacao de Dois Fatores (2FA){% endblock %}
{% block content %}
<div class="max-w-2xl mx-auto space-y-6">
    <!-- Status card -->
    <div class="card p-5 flex items-center gap-4">
        <div class="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 {% if totp_enabled %}bg-green-100{% else %}bg-slate-100{% endif %}">
            <i class="fas fa-shield-halved text-xl {% if totp_enabled %}text-green-600{% else %}text-slate-400{% endif %}"></i>
        </div>
        <div class="flex-1">
            <div class="font-semibold text-slate-800">Status do 2FA</div>
            <div class="text-sm {% if totp_enabled %}text-green-600{% else %}text-slate-500{% endif %}">
                {% if totp_enabled %}Autenticacao de dois fatores esta ATIVADA{% else %}Autenticacao de dois fatores esta DESATIVADA{% endif %}
            </div>
        </div>
        <span class="{% if totp_enabled %}badge-online{% else %}badge-offline{% endif %}">
            {% if totp_enabled %}ATIVO{% else %}INATIVO{% endif %}
        </span>
    </div>

    <!-- QR Code card -->
    <div class="card p-6">
        <h2 class="section-title mb-1">Configurar Aplicativo Autenticador</h2>
        <p class="text-sm text-slate-500 mb-5">Escaneie o QR Code abaixo com o Google Authenticator, Authy ou qualquer app TOTP compativel.</p>

        <div class="flex flex-col md:flex-row gap-6 items-start">
            <div class="flex-shrink-0 bg-white border-2 border-slate-200 rounded-xl p-3 mx-auto md:mx-0">
                <img src="data:image/png;base64,{{ qr_b64 }}" alt="QR Code 2FA" class="w-44 h-44">
            </div>
            <div class="flex-1 space-y-4">
                <div>
                    <div class="field-label mb-1">Conta / Emissor</div>
                    <div class="field-value">{{ web_user }} @ {{ issuer }}</div>
                </div>
                <div>
                    <div class="field-label mb-1">Chave Secreta (entrada manual)</div>
                    <div class="flex items-center gap-2">
                        <code class="field-value bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm tracking-widest select-all flex-1">{{ secret }}</code>
                        <button onclick="copySecret()" class="btn-secondary text-xs px-3 py-2">
                            <i class="fas fa-copy"></i>
                        </button>
                    </div>
                </div>
                <div class="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
                    <i class="fas fa-triangle-exclamation mr-1"></i>
                    <strong>Importante:</strong> Guarde a chave secreta em local seguro. Ela nao pode ser recuperada depois.
                </div>
            </div>
        </div>
    </div>

    <!-- Instructions -->
    <div class="card p-6">
        <h2 class="section-title mb-4">Como ativar o 2FA</h2>
        <ol class="space-y-3 text-sm text-slate-700">
            <li class="flex gap-3">
                <span class="w-6 h-6 bg-blue-600 text-white rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0">1</span>
                <span>Instale o <strong>Google Authenticator</strong> ou <strong>Authy</strong> no seu celular.</span>
            </li>
            <li class="flex gap-3">
                <span class="w-6 h-6 bg-blue-600 text-white rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0">2</span>
                <span>Escaneie o QR Code acima ou insira a chave secreta manualmente no aplicativo.</span>
            </li>
            <li class="flex gap-3">
                <span class="w-6 h-6 bg-blue-600 text-white rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0">3</span>
                <span>No arquivo <code class="bg-slate-100 px-1 rounded">.env</code>, defina <code class="bg-slate-100 px-1 rounded">TOTP_ENABLED=true</code> e <code class="bg-slate-100 px-1 rounded">TOTP_SECRET={{ secret }}</code>.</span>
            </li>
            <li class="flex gap-3">
                <span class="w-6 h-6 bg-blue-600 text-white rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0">4</span>
                <span>Reinicie o servico. No proximo login, o campo de codigo 2FA sera exibido automaticamente.</span>
            </li>
        </ol>
    </div>

    <!-- .env snippet -->
    <div class="card p-6">
        <h2 class="section-title mb-3">Configuracao no .env</h2>
        <pre class="bg-slate-900 text-green-400 rounded-xl p-4 text-xs overflow-x-auto font-mono leading-relaxed">TOTP_ENABLED=true
TOTP_SECRET={{ secret }}
TOTP_ISSUER={{ issuer }}</pre>
    </div>
</div>
<script>
function copySecret() {
    navigator.clipboard.writeText('{{ secret }}').then(() => {
        showMessage('Chave secreta copiada!', 'success');
    });
}
</script>
{% endblock %}
"""

# ============================================================
# SIMPLE_DASHBOARD.HTML
# ============================================================
DASHBOARD_HTML = """\
{% extends "base.html" %}
{% block title %}Dashboard — NE8000 Manager{% endblock %}
{% block page_title %}Dashboard{% endblock %}
{% block content %}
<!-- Stats row -->
<div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
    <div class="card p-5">
        <div class="flex items-center justify-between mb-3">
            <span class="text-xs font-semibold text-slate-500 uppercase tracking-wide">Usuarios Online</span>
            <div class="w-9 h-9 bg-blue-100 rounded-lg flex items-center justify-center">
                <i class="fas fa-users text-blue-600 text-sm"></i>
            </div>
        </div>
        <div class="text-3xl font-extrabold text-slate-800" id="totalOnline">—</div>
        <div class="text-xs text-slate-400 mt-1">PPPoE ativos no BNG</div>
    </div>
    <div class="card p-5">
        <div class="flex items-center justify-between mb-3">
            <span class="text-xs font-semibold text-slate-500 uppercase tracking-wide">Conexao</span>
            <div class="w-9 h-9 bg-green-100 rounded-lg flex items-center justify-center">
                <i class="fas fa-plug text-green-600 text-sm"></i>
            </div>
        </div>
        <div class="text-xl font-bold text-slate-800" id="connStatus">—</div>
        <div class="text-xs text-slate-400 mt-1" id="connHost">Verificando...</div>
    </div>
    <div class="card p-5">
        <div class="flex items-center justify-between mb-3">
            <span class="text-xs font-semibold text-slate-500 uppercase tracking-wide">Protocolo</span>
            <div class="w-9 h-9 bg-purple-100 rounded-lg flex items-center justify-center">
                <i class="fas fa-terminal text-purple-600 text-sm"></i>
            </div>
        </div>
        <div class="text-xl font-bold text-slate-800 uppercase" id="connProto">—</div>
        <div class="text-xs text-slate-400 mt-1">SSH ou Telnet</div>
    </div>
    <div class="card p-5">
        <div class="flex items-center justify-between mb-3">
            <span class="text-xs font-semibold text-slate-500 uppercase tracking-wide">Ultima Atualizacao</span>
            <div class="w-9 h-9 bg-amber-100 rounded-lg flex items-center justify-center">
                <i class="fas fa-clock text-amber-600 text-sm"></i>
            </div>
        </div>
        <div class="text-sm font-bold text-slate-800" id="lastUpdate">—</div>
        <div class="text-xs text-slate-400 mt-1">Atualiza a cada 60s</div>
    </div>
</div>

<!-- Quick actions -->
<div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
    <div class="card p-5">
        <h3 class="section-title mb-3">Acoes Rapidas</h3>
        <div class="space-y-2">
            <a href="/pppoe" class="flex items-center gap-3 p-3 rounded-lg bg-slate-50 hover:bg-blue-50 hover:text-blue-700 transition text-sm font-medium text-slate-700 border border-transparent hover:border-blue-200">
                <i class="fas fa-search w-4 text-center"></i> Consultar usuario PPPoE
            </a>
            <a href="/interfaces/pppoe" class="flex items-center gap-3 p-3 rounded-lg bg-slate-50 hover:bg-blue-50 hover:text-blue-700 transition text-sm font-medium text-slate-700 border border-transparent hover:border-blue-200">
                <i class="fas fa-ethernet w-4 text-center"></i> Ver interfaces PPPoE
            </a>
            <button onclick="forceRefresh()" class="w-full flex items-center gap-3 p-3 rounded-lg bg-slate-50 hover:bg-amber-50 hover:text-amber-700 transition text-sm font-medium text-slate-700 border border-transparent hover:border-amber-200">
                <i class="fas fa-rotate-right w-4 text-center"></i> Forcar atualizacao do cache
            </button>
        </div>
    </div>
    <div class="card p-5">
        <h3 class="section-title mb-3">Status do Sistema</h3>
        <div id="healthInfo" class="space-y-2 text-sm text-slate-600">
            <div class="flex items-center gap-2"><i class="fas fa-spinner fa-spin text-slate-400"></i> Carregando...</div>
        </div>
    </div>
</div>

<script>
async function loadDashboard() {
    try {
        const [statusRes, totalRes] = await Promise.all([
            fetch('/api/connection_status'),
            fetch('/api/online_total')
        ]);
        const status = await statusRes.json();
        const total = await totalRes.json();

        document.getElementById('connStatus').textContent = status.connected ? 'Conectado' : 'Desconectado';
        document.getElementById('connStatus').style.color = status.connected ? '#16a34a' : '#dc2626';
        document.getElementById('connHost').textContent = status.host || '—';
        document.getElementById('connProto').textContent = (status.protocol || 'SSH').toUpperCase();
        document.getElementById('totalOnline').textContent = total.total ?? total.active ?? '—';
        document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString('pt-BR');
    } catch(e) {
        document.getElementById('connStatus').textContent = 'Erro';
    }
}

async function loadHealth() {
    try {
        const r = await fetch('/health');
        const d = await r.json();
        const el = document.getElementById('healthInfo');
        const items = [
            {icon: d.ssh_connected ? 'fa-check text-green-500' : 'fa-xmark text-red-500', label: 'Conexao SSH/Telnet', val: d.ssh_connected ? 'OK' : 'Falha'},
            {icon: 'fa-database text-blue-500', label: 'Itens em cache', val: d.cache_active_items ?? '—'},
            {icon: 'fa-code-branch text-purple-500', label: 'Versao', val: d.version ?? '—'},
        ];
        el.innerHTML = items.map(i => `<div class="flex items-center justify-between py-1 border-b border-slate-100 last:border-0"><span class="flex items-center gap-2"><i class="fas ${i.icon} w-4"></i>${i.label}</span><span class="font-semibold text-slate-800">${i.val}</span></div>`).join('');
    } catch(e) {}
}

async function forceRefresh() {
    try {
        const r = await fetch('/api/force_cache_refresh', {method:'POST'});
        const d = await r.json();
        showMessage(d.success ? 'Cache limpo! Proxima consulta sera em tempo real.' : 'Erro: ' + d.error, d.success ? 'success' : 'error');
        if (d.success) loadDashboard();
    } catch(e) { showMessage('Erro ao forcar refresh', 'error'); }
}

loadDashboard();
loadHealth();
setInterval(loadDashboard, 60000);
</script>
{% endblock %}
"""

# ============================================================
# PPPOE.HTML
# ============================================================
PPPOE_HTML = """\
{% extends "base.html" %}
{% block title %}Consulta PPPoE — NE8000 Manager{% endblock %}
{% block page_title %}Consulta de Usuario PPPoE{% endblock %}
{% block content %}
<!-- Search bar -->
<div class="card p-5 mb-5">
    <form id="pppoeForm" class="flex gap-3" onsubmit="queryUser(event)">
        <div class="flex-1 relative">
            <i class="fas fa-user absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm"></i>
            <input type="text" id="usernameInput" name="username" required
                   class="input-field pl-10" placeholder="Digite o username do cliente PPPoE (ex: jose)">
        </div>
        <button type="submit" class="btn-primary flex-shrink-0">
            <i class="fas fa-search"></i> Consultar
        </button>
    </form>
</div>

<!-- Loading -->
<div id="loadingDiv" class="hidden card p-8 text-center">
    <i class="fas fa-spinner fa-spin text-blue-500 text-2xl mb-3"></i>
    <div class="text-slate-600 font-medium">Consultando roteador...</div>
    <div class="text-slate-400 text-sm mt-1">Aguarde, executando comando no NE8000</div>
</div>

<!-- Result -->
<div id="resultDiv" class="hidden space-y-4">
    <!-- Status header -->
    <div class="card p-5 flex items-center gap-4">
        <div class="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0" id="statusIcon">
            <i class="fas fa-user text-xl" id="statusIconI"></i>
        </div>
        <div class="flex-1">
            <div class="flex items-center gap-3 flex-wrap">
                <span class="text-lg font-bold text-slate-800" id="resUsername">—</span>
                <span id="statusBadge" class="badge-offline">OFFLINE</span>
            </div>
            <div class="text-sm text-slate-500 mt-0.5" id="resMessage">—</div>
        </div>
        <div class="flex gap-2">
            <button onclick="copyRaw()" class="btn-secondary text-xs px-3 py-2" title="Copiar output raw">
                <i class="fas fa-copy"></i>
            </button>
            <button id="disconnectBtn" onclick="confirmDisconnect()" class="btn-danger hidden text-xs px-3 py-2">
                <i class="fas fa-plug-circle-xmark"></i> Desconectar
            </button>
        </div>
    </div>

    <!-- Info grid -->
    <div id="infoGrid" class="hidden grid grid-cols-1 lg:grid-cols-2 gap-4">
        <!-- Sessao -->
        <div class="card p-5">
            <h3 class="section-title mb-4 flex items-center gap-2"><i class="fas fa-id-card text-blue-500"></i> Sessao</h3>
            <div class="space-y-2.5" id="sessionFields"></div>
        </div>
        <!-- IPv4 -->
        <div class="card p-5">
            <h3 class="section-title mb-4 flex items-center gap-2"><i class="fas fa-globe text-green-500"></i> IPv4</h3>
            <div class="space-y-2.5" id="ipv4Fields"></div>
        </div>
        <!-- IPv6 -->
        <div class="card p-5" id="ipv6Card">
            <h3 class="section-title mb-4 flex items-center gap-2"><i class="fas fa-globe text-purple-500"></i> IPv6</h3>
            <div class="space-y-2.5" id="ipv6Fields"></div>
        </div>
        <!-- Trafego -->
        <div class="card p-5">
            <h3 class="section-title mb-4 flex items-center gap-2"><i class="fas fa-chart-line text-amber-500"></i> Trafego e AAA</h3>
            <div class="space-y-2.5" id="trafficFields"></div>
        </div>
    </div>

    <!-- Raw output -->
    <div class="card">
        <button onclick="toggleRaw()" class="w-full flex items-center justify-between p-4 text-sm font-semibold text-slate-600 hover:text-slate-800 transition">
            <span><i class="fas fa-terminal mr-2 text-slate-400"></i>Output Raw do Roteador</span>
            <i class="fas fa-chevron-down text-slate-400" id="rawChevron"></i>
        </button>
        <div id="rawOutput" class="hidden border-t border-slate-100">
            <pre class="bg-slate-900 text-green-400 p-4 text-xs overflow-x-auto font-mono leading-relaxed rounded-b-xl" id="rawPre"></pre>
        </div>
    </div>
</div>

<!-- Disconnect modal -->
<div id="disconnectModal" class="hidden fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
        <div class="flex items-center gap-3 mb-4">
            <div class="w-10 h-10 bg-red-100 rounded-xl flex items-center justify-center">
                <i class="fas fa-plug-circle-xmark text-red-600"></i>
            </div>
            <div>
                <div class="font-bold text-slate-800">Confirmar Desconexao</div>
                <div class="text-sm text-slate-500">Esta acao nao pode ser desfeita</div>
            </div>
        </div>
        <p class="text-sm text-slate-600 mb-5">
            Deseja desconectar o usuario <strong id="modalUsername" class="text-red-600">—</strong> do BNG?<br>
            <span class="text-xs text-slate-400">Sera executado: <code>cut access-user username &lt;user&gt; radius</code></span>
        </p>
        <div class="flex gap-3">
            <button onclick="closeModal()" class="btn-secondary flex-1">Cancelar</button>
            <button onclick="doDisconnect()" class="btn-danger flex-1">
                <i class="fas fa-plug-circle-xmark"></i> Desconectar
            </button>
        </div>
    </div>
</div>

<script>
let currentUsername = '';
let rawData = '';

function field(label, value, mono=false) {
    if (!value || value === 'N/A' || value === '' || value === 'None') return '';
    return `<div class="flex items-start justify-between gap-2 py-1.5 border-b border-slate-50 last:border-0">
        <span class="field-label flex-shrink-0 w-36">${label}</span>
        <span class="field-value text-right ${mono?'font-mono':''} break-all">${value}</span>
    </div>`;
}

async function queryUser(e) {
    e.preventDefault();
    const username = document.getElementById('usernameInput').value.trim();
    if (!username) return;
    currentUsername = username;

    document.getElementById('loadingDiv').classList.remove('hidden');
    document.getElementById('resultDiv').classList.add('hidden');

    const fd = new FormData();
    fd.append('username', username);

    try {
        const r = await fetch('/api/pppoe_query', {method:'POST', body:fd});
        const d = await r.json();
        renderResult(d);
    } catch(err) {
        showMessage('Erro ao consultar: ' + err.message, 'error');
    } finally {
        document.getElementById('loadingDiv').classList.add('hidden');
    }
}

function renderResult(d) {
    document.getElementById('resultDiv').classList.remove('hidden');
    document.getElementById('resUsername').textContent = d.username || currentUsername;
    document.getElementById('resMessage').textContent = d.formatted_message || '';
    rawData = d.raw_output || '';
    document.getElementById('rawPre').textContent = rawData;

    const isOnline = d.status === 'ONLINE';
    const badge = document.getElementById('statusBadge');
    const icon = document.getElementById('statusIcon');
    const iconI = document.getElementById('statusIconI');
    const discBtn = document.getElementById('disconnectBtn');
    const infoGrid = document.getElementById('infoGrid');

    badge.textContent = d.status || 'OFFLINE';
    badge.className = isOnline ? 'badge-online' : 'badge-offline';
    icon.className = 'w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 ' + (isOnline ? 'bg-green-100' : 'bg-red-100');
    iconI.className = 'fas fa-user text-xl ' + (isOnline ? 'text-green-600' : 'text-red-600');
    discBtn.classList.toggle('hidden', !isOnline);

    if (isOnline && d.user_data) {
        infoGrid.classList.remove('hidden');
        const u = d.user_data;

        document.getElementById('sessionFields').innerHTML = [
            field('Interface', u.interface),
            field('MAC', u.mac, true),
            field('VLAN', u.vlan),
            field('Dominio', u.domain),
            field('Tipo de Acesso', u.access_type),
            field('MTU', u.mtu),
            field('Inicio Sessao', u.access_start_time),
            field('Inicio Accounting', u.accounting_start_time),
            field('Uptime', `<span class="text-green-700 font-bold">${u.online_time_formatted || u.online_time || '—'}</span>`, false),
        ].join('');

        document.getElementById('ipv4Fields').innerHTML = [
            field('Endereco IP', u.ip_address, true),
            field('Mascara', u.ip_mask, true),
            field('Gateway', u.gateway, true),
            field('DNS Primario', u.primary_dns, true),
            field('DNS Secundario', u.secondary_dns, true),
        ].join('');

        const ipv6html = [
            field('Link Local', u.link_local, true),
            field('NDRA Prefix', u.ndra_prefix, true),
            field('PD Prefix', u.pd_prefix, true),
            field('DNS IPv6 Pri', u.ipv6_primary_dns, true),
            field('DNS IPv6 Sec', u.ipv6_secondary_dns, true),
            field('DUID', u.duid, true),
            field('Lease', u.lease),
            field('Remain Lease', u.remain_lease),
        ].join('');
        document.getElementById('ipv6Fields').innerHTML = ipv6html || '<div class="text-sm text-slate-400">Sem dados IPv6</div>';

        document.getElementById('trafficFields').innerHTML = [
            field('Velocidade Total', u.total_speed),
            field('Inbound', u.inbound_speed),
            field('Outbound', u.outbound_speed),
            field('CIR Inbound', u.cir_inbound),
            field('CIR Outbound', u.cir_outbound),
            field('Servidor RADIUS', u.radius_server),
            field('Auth Result', u.auth_result),
            field('Session ID', u.accounting_session_id, true),
        ].join('');
    } else {
        infoGrid.classList.add('hidden');
    }
}

function toggleRaw() {
    const raw = document.getElementById('rawOutput');
    const chev = document.getElementById('rawChevron');
    raw.classList.toggle('hidden');
    chev.className = raw.classList.contains('hidden') ? 'fas fa-chevron-down text-slate-400' : 'fas fa-chevron-up text-slate-400';
}

function copyRaw() {
    navigator.clipboard.writeText(rawData).then(() => showMessage('Output copiado!', 'success'));
}

function confirmDisconnect() {
    document.getElementById('modalUsername').textContent = currentUsername;
    document.getElementById('disconnectModal').classList.remove('hidden');
}

function closeModal() {
    document.getElementById('disconnectModal').classList.add('hidden');
}

async function doDisconnect() {
    closeModal();
    const fd = new FormData();
    fd.append('username', currentUsername);
    try {
        const r = await fetch('/api/pppoe_disconnect', {method:'POST', body:fd});
        const d = await r.json();
        if (d.success) {
            showMessage('Usuario ' + currentUsername + ' desconectado com sucesso!', 'success');
            setTimeout(() => queryUser({preventDefault:()=>{}}), 2000);
        } else {
            showMessage('Erro ao desconectar: ' + (d.error || d.message), 'error');
        }
    } catch(err) {
        showMessage('Erro: ' + err.message, 'error');
    }
}

// Fechar modal clicando fora
document.getElementById('disconnectModal').addEventListener('click', function(e) {
    if (e.target === this) closeModal();
});
</script>
{% endblock %}
"""

# ============================================================
# INTERFACES_PPPOE.HTML
# ============================================================
INTERFACES_HTML = """\
{% extends "base.html" %}
{% block title %}Interfaces PPPoE — NE8000 Manager{% endblock %}
{% block page_title %}Interfaces PPPoE por Slot / Interface / VLAN{% endblock %}
{% block content %}
<!-- Query form -->
<div class="card p-5 mb-5">
    <h3 class="section-title mb-4">Consultar Usuarios por Interface</h3>
    <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
        <div>
            <label class="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Slot</label>
            <input type="number" id="slotInput" value="0" min="0" max="9"
                   class="input-field" placeholder="0">
        </div>
        <div class="md:col-span-2">
            <label class="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">Interface (ex: GE0/1/0)</label>
            <input type="text" id="ifaceInput" value="GE0/1/0"
                   class="input-field" placeholder="GE0/1/0">
        </div>
        <div>
            <label class="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">VLAN (0 = todas)</label>
            <input type="number" id="vlanInput" value="0" min="0" max="4094"
                   class="input-field" placeholder="0">
        </div>
    </div>
    <div class="flex gap-3 mt-4">
        <button onclick="queryCount()" class="btn-primary">
            <i class="fas fa-calculator"></i> Contar Usuarios
        </button>
        <button onclick="queryUsers()" class="btn-secondary">
            <i class="fas fa-list"></i> Listar Usuarios
        </button>
    </div>
    <div class="mt-3 text-xs text-slate-400">
        <i class="fas fa-terminal mr-1"></i>
        <span id="cmdPreview">display access-user slot 0 | include GE0/1/0 | exclude PPPoE | count</span>
    </div>
</div>

<!-- Count result -->
<div id="countResult" class="hidden card p-5 mb-4">
    <div class="flex items-center gap-4">
        <div class="w-14 h-14 bg-blue-100 rounded-xl flex items-center justify-center flex-shrink-0">
            <i class="fas fa-users text-blue-600 text-xl"></i>
        </div>
        <div>
            <div class="text-3xl font-extrabold text-slate-800" id="countNumber">—</div>
            <div class="text-sm text-slate-500" id="countLabel">usuarios encontrados</div>
            <div class="text-xs text-slate-400 font-mono mt-0.5" id="countCmd">—</div>
        </div>
    </div>
</div>

<!-- Users table -->
<div id="usersResult" class="hidden card">
    <div class="p-4 border-b border-slate-100 flex items-center justify-between">
        <span class="section-title">Usuarios na Interface</span>
        <span class="text-sm text-slate-500" id="usersCount">—</span>
    </div>
    <div class="overflow-x-auto">
        <table class="w-full text-sm">
            <thead class="bg-slate-50 border-b border-slate-100">
                <tr>
                    <th class="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">#</th>
                    <th class="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Dados</th>
                </tr>
            </thead>
            <tbody id="usersTableBody" class="divide-y divide-slate-50"></tbody>
        </table>
    </div>
    <!-- Raw output -->
    <div class="border-t border-slate-100">
        <button onclick="toggleRawIface()" class="w-full flex items-center justify-between p-4 text-sm font-semibold text-slate-600 hover:text-slate-800 transition">
            <span><i class="fas fa-terminal mr-2 text-slate-400"></i>Output Raw</span>
            <i class="fas fa-chevron-down text-slate-400" id="rawIfaceChevron"></i>
        </button>
        <div id="rawIfaceOutput" class="hidden border-t border-slate-100">
            <pre class="bg-slate-900 text-green-400 p-4 text-xs overflow-x-auto font-mono leading-relaxed rounded-b-xl" id="rawIfacePre"></pre>
        </div>
    </div>
</div>

<!-- Loading -->
<div id="ifaceLoading" class="hidden card p-8 text-center">
    <i class="fas fa-spinner fa-spin text-blue-500 text-2xl mb-3"></i>
    <div class="text-slate-600 font-medium">Consultando roteador...</div>
</div>

<script>
function getParams() {
    return {
        slot: parseInt(document.getElementById('slotInput').value) || 0,
        iface: document.getElementById('ifaceInput').value.trim() || 'GE0/1/0',
        vlan: parseInt(document.getElementById('vlanInput').value) || 0
    };
}

function updateCmdPreview() {
    const {slot, iface, vlan} = getParams();
    let cmd = vlan > 0
        ? `display access-user slot ${slot} | include ${iface}.${vlan} | exclude PPPoE | count`
        : `display access-user slot ${slot} | include ${iface} | exclude PPPoE | count`;
    document.getElementById('cmdPreview').textContent = cmd;
}

['slotInput','ifaceInput','vlanInput'].forEach(id => {
    document.getElementById(id).addEventListener('input', updateCmdPreview);
});

function showLoading(show) {
    document.getElementById('ifaceLoading').classList.toggle('hidden', !show);
}

async function queryCount() {
    const {slot, iface, vlan} = getParams();
    showLoading(true);
    document.getElementById('countResult').classList.add('hidden');
    try {
        const url = `/api/pppoe_interfaces_real?slot=${slot}&interface=${encodeURIComponent(iface)}&vlan=${vlan}`;
        const r = await fetch(url);
        const d = await r.json();
        showLoading(false);
        if (d.success) {
            document.getElementById('countResult').classList.remove('hidden');
            document.getElementById('countNumber').textContent = d.count;
            document.getElementById('countLabel').textContent = `usuario(s) na interface ${iface}${vlan>0?'.'+vlan:''}`;
            document.getElementById('countCmd').textContent = d.command;
        } else {
            showMessage('Erro: ' + d.error, 'error');
        }
    } catch(e) {
        showLoading(false);
        showMessage('Erro de conexao: ' + e.message, 'error');
    }
}

async function queryUsers() {
    const {slot, iface} = getParams();
    showLoading(true);
    document.getElementById('usersResult').classList.add('hidden');
    try {
        const url = `/api/pppoe_users_by_interface?slot=${slot}&interface=${encodeURIComponent(iface)}`;
        const r = await fetch(url);
        const d = await r.json();
        showLoading(false);
        if (d.success) {
            document.getElementById('usersResult').classList.remove('hidden');
            document.getElementById('usersCount').textContent = d.count + ' usuario(s)';
            document.getElementById('rawIfacePre').textContent = d.raw_output || '';
            const tbody = document.getElementById('usersTableBody');
            if (d.users && d.users.length > 0) {
                tbody.innerHTML = d.users.map((u, i) =>
                    `<tr class="hover:bg-slate-50"><td class="px-4 py-2.5 text-slate-400 text-xs">${i+1}</td><td class="px-4 py-2.5 font-mono text-xs text-slate-700">${u.raw}</td></tr>`
                ).join('');
            } else {
                tbody.innerHTML = '<tr><td colspan="2" class="px-4 py-6 text-center text-slate-400">Nenhum usuario encontrado</td></tr>';
            }
        } else {
            showMessage('Erro: ' + d.error, 'error');
        }
    } catch(e) {
        showLoading(false);
        showMessage('Erro de conexao: ' + e.message, 'error');
    }
}

function toggleRawIface() {
    const raw = document.getElementById('rawIfaceOutput');
    const chev = document.getElementById('rawIfaceChevron');
    raw.classList.toggle('hidden');
    chev.className = raw.classList.contains('hidden') ? 'fas fa-chevron-down text-slate-400' : 'fas fa-chevron-up text-slate-400';
}
</script>
{% endblock %}
"""

files = {
    'login.html': LOGIN_HTML,
    'setup_2fa.html': SETUP_2FA_HTML,
    'simple_dashboard.html': DASHBOARD_HTML,
    'pppoe.html': PPPOE_HTML,
    'interfaces_pppoe.html': INTERFACES_HTML,
}

for fname, content in files.items():
    path = os.path.join(TEMPLATES_DIR, fname)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"OK: {fname} ({len(content)} chars)")

print("\nAll templates written successfully!")
