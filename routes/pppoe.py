from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from services.router import RouterConnection
from routes.auth import login_required

pppoe_bp = Blueprint('pppoe', __name__)

@pppoe_bp.route('/pppoe', methods=['GET', 'POST'])
@login_required
def pppoe_management():
    username = ''
    terminal_output = ''
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if not username:
            flash('Informe o nome de usuário PPPoE.', 'warning')
            return redirect(url_for('pppoe.pppoe_management'))
        commands = [
            f"display ppp username {username}",
            f"display access-user username {username}",
            f"display aaa online-fail-record username {username}",
            f"display aaa offline-record username {username}"
        ]
        router = RouterConnection()
        results = router.execute_commands(commands)
        terminal_output = '\n'.join(results)
        current_app.logger.info(f"Consulta PPPoE para {username} executada com sucesso.")
    return render_template('pppoe.html', username=username, terminal_output=terminal_output)

@pppoe_bp.route('/pppoe/disconnect', methods=['POST'])
@login_required
def pppoe_disconnect():
    username = request.form.get('username', '').strip()
    if not username:
        flash('Usuário inválido para desconectar.', 'error')
        return redirect(url_for('pppoe.pppoe_management'))
    command = f"undo access-user username {username}"
    router = RouterConnection()
    result = router.execute_commands([command])
    output = result[0] if result else 'Nenhuma saída retornada'
    current_app.logger.warning(f"Usuário {username} desconectado manualmente.")
    flash(f'Usuário {username} foi desconectado.', 'success')
    return render_template('pppoe.html', username=username, terminal_output=output) 