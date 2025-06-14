from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from routes.auth import login_required
from services.router import execute_router_commands

main_bp = Blueprint('main', __name__)

command_history = []
online_total_history = []
peak_users = 0

@main_bp.route('/')
@login_required
def index():
    return render_template('index.html')



@main_bp.route('/command_history')
@login_required
def command_history_view():
    return render_template('command_history.html', commands=command_history)

@main_bp.route('/diagnostics')
@login_required
def diagnostics():
    return render_template('diagnostics.html')

@main_bp.route('/statistics')
@login_required
def statistics():
    command_counts = {}
    response_times = []
    for cmd in command_history:
        if cmd['command'] not in command_counts:
            command_counts[cmd['command']] = 0
        command_counts[cmd['command']] += 1
        response_times.append({
            'timestamp': cmd['timestamp'],
            'response_time': cmd['response_time']
        })
    return render_template('statistics.html', command_counts=command_counts, response_times=response_times)

@main_bp.route('/query', methods=['POST'])
@login_required
def query():
    query_type = request.form.get('query_type')
    target = request.form.get('target')
    if not target:
        flash('Please provide a username or interface')
        return redirect(url_for('main.index'))
    current_app.logger.info(f"Query - Type: {query_type}, Target: {target}, IP: {request.remote_addr}")
    commands = []
    if query_type == 'username':
        commands = [
            "display ppp username {target}",
            "display access-user username {target}",
            "display aaa online-fail-record username {target}",
            "display aaa offline-record username {target}"
        ]
    elif query_type == 'interface':
        commands = [
            "display access-user interface {target}",
            "display access-user online-total | no-more"
        ]
    results = execute_router_commands(target, commands)
    return render_template('results.html', results=results, query_type=query_type, target=target) 