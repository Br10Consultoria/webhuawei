from flask import Blueprint, render_template, jsonify, current_app, request
from services.router import get_interfaces
from routes.auth import login_required
import redis
import os
import json

interface_bp = Blueprint('interface', __name__)

@interface_bp.route('/interfaces', methods=['GET', 'POST'])
@login_required
def interfaces():
    interfaces = get_interfaces()
    interface_name = ''
    terminal_output = ''
    
    if request.method == 'POST':
        interface_name = request.form.get('interface', '').strip()
        if interface_name:
            from services.router import RouterConnection
            router = RouterConnection()
            commands = [f"display interface {interface_name}"]
            results = router.execute_commands(commands)
            terminal_output = '\n'.join(results) if results else 'No output'
    
    return render_template('interfaces.html', 
                         interfaces=interfaces, 
                         interface=interface_name,
                         terminal_output=terminal_output)

@interface_bp.route('/api/refresh_interfaces', methods=['POST'])
@login_required
def refresh_interfaces():
    try:
        redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'redis'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=0,
            decode_responses=True
        )
        redis_client.delete('router_interfaces')
        interfaces = get_interfaces()
        return jsonify({'success': True, 'message': 'Interfaces refreshed successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500 