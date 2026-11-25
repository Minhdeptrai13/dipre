from flask import Blueprint, request, jsonify, session

from core.database import get_db, track_feature_use
from core.discord_guard import discord_guard
from core.logger import log_event
from core.registry import registry, SubModule
from modules.auth.helpers import login_required
from modules.sniper.worker import sniper_worker

sniper_bp = Blueprint('sniper', __name__)


def _resolve_sniper_token(user_id: int, account_id=None):
    with get_db() as conn:
        cursor = conn.cursor()
        token = ''
        acc_name = ''
        if account_id and str(account_id) != 'main':
            cursor.execute('SELECT token, discord_username FROM discord_accounts WHERE id = ? AND user_id = ?', (account_id, user_id))
            r = cursor.fetchone()
            if r:
                token = r['token']
                acc_name = r['discord_username'] or f'Sub-{account_id}'
        if not token:
            cursor.execute('SELECT token, discord_username FROM discord_accounts WHERE user_id = ? AND is_active = 1 LIMIT 1', (user_id,))
            acc_r = cursor.fetchone()
            if acc_r and acc_r['token']:
                token = acc_r['token']
                acc_name = acc_r['discord_username'] or 'Main'
        if not token:
            cursor.execute('SELECT discord_token, discord_username FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                token = row['discord_token'] or ''
                acc_name = row['discord_username'] or session.get('username', 'Main')
            if not token:
                token = session.get('discord_token', '')
    return token, acc_name


@sniper_bp.route('/api/sniper/start', methods=['POST'])
@login_required
def api_sniper_start():
    user_id = session.get('user_id')
    data = request.get_json() or {}
    account_id = data.get('account_id')
    token, acc_name = _resolve_sniper_token(user_id, account_id)

    if not token or len(token) < 20:
        return jsonify({'success': False, 'message': 'Chưa có Discord User Token hợp lệ cho tài khoản này!'}), 400

    ok, msg = sniper_worker.start(token, acc_name=acc_name, cfg=data)
    if ok:
        track_feature_use(user_id, 'nitro_sniper')
        log_event(f'Bật Sniper Radar + Anti-Ban Shield cho {acc_name}', 'success')
        return jsonify({'success': True, 'message': msg, 'status': sniper_worker.get_status()})
    return jsonify({'success': False, 'message': msg, 'status': sniper_worker.get_status()}), 400


@sniper_bp.route('/api/sniper/stop', methods=['POST'])
@login_required
def api_sniper_stop():
    sniper_worker.stop()
    log_event(f'Tài khoản {session.get("username")} đã dừng Sniper Radar', 'info')
    return jsonify({'success': True, 'message': 'Đã dừng Nitro & Vanity Sniper', 'status': sniper_worker.get_status()})


@sniper_bp.route('/api/sniper/config', methods=['POST'])
@login_required
def api_sniper_config():
    data = request.get_json() or {}
    sniper_worker.update_config(data)
    return jsonify({'success': True, 'message': 'Đã cập nhật cấu hình Sniper', 'status': sniper_worker.get_status()})


@sniper_bp.route('/api/sniper/status', methods=['GET'])
@login_required
def api_sniper_status():
    return jsonify({'success': True, 'status': sniper_worker.get_status()})


@sniper_bp.route('/api/sniper/logs', methods=['GET', 'DELETE'])
@login_required
def api_sniper_logs():
    if request.method == 'DELETE':
        sniper_worker.clear_logs()
        return jsonify({'success': True, 'message': 'Đã xóa nhật ký Sniper'})
    return jsonify({'success': True, 'logs': sniper_worker.get_status()['logs']})


@sniper_bp.route('/api/sniper/webhook', methods=['POST'])
@login_required
def api_sniper_webhook():
    data = request.get_json() or {}
    ok, msg = sniper_worker.test_webhook(data.get('webhook_url', ''))
    return jsonify({'success': ok, 'message': msg}), (200 if ok else 400)


@sniper_bp.route('/api/security/antiban', methods=['GET', 'POST'])
@login_required
def api_security_antiban():
    if request.method == 'POST':
        data = request.get_json() or {}
        if 'enabled' in data:
            discord_guard.set_enabled(bool(data['enabled']))
        else:
            discord_guard.set_enabled(not discord_guard.enabled)
    return jsonify({'success': True, 'anti_ban': discord_guard.get_status()})


registry.register_module(SubModule(
    key='nitro_sniper',
    category_key='script',
    title='Real Nitro/Vanity Sniper & Anti-Ban Shield',
    blueprint=sniper_bp,
    cleanup_handler=lambda: sniper_worker.stop()
))
