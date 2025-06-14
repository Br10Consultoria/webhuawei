from flask import Blueprint, render_template, request, jsonify, current_app
from routes.auth import login_required
from services.router import RouterConnection

terminal_bp = Blueprint('terminal', __name__)

@terminal_bp.route('/terminal')
@login_required
def terminal():
    return render_template('terminal.html')

@terminal_bp.route('/api/execute_terminal_command', methods=['POST'])
@login_required
def execute_terminal_command():
    try:
        data = request.json
        command = data.get('command', '').strip()
        
        if not command:
            return jsonify({
                'success': False,
                'error': 'Comando não fornecido'
            }), 400
        
        router = RouterConnection()
        results = router.execute_commands([command])
        
        output = '\n'.join(results) if results else 'No output'
        
        # Verificar se houve erro
        if any("Error:" in str(r) for r in results):
            return jsonify({
                'success': False,
                'error': output
            })
        
        return jsonify({
            'success': True,
            'output': output
        })
    except Exception as e:
        current_app.logger.error(f"Error executing terminal command: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500 