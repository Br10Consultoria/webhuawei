from flask import Blueprint, render_template, current_app
from routes.auth import login_required
import os

logs_bp = Blueprint('logs', __name__)

@logs_bp.route('/logs')
@login_required
def logs():
    log_entries = []
    log_file_path = 'logs/app.log'
    if os.path.exists(log_file_path):
        with open(log_file_path, 'r') as f:
            lines = f.readlines()[-1000:]
            for line in lines:
                parts = line.split(' - ', 2)
                if len(parts) == 3:
                    log_entries.append({
                        'timestamp': parts[0],
                        'level': parts[1],
                        'message': parts[2].strip()
                    })
    return render_template('logs.html', logs=log_entries) 