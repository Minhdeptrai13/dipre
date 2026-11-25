import time
import requests
from flask import Blueprint, request, jsonify, session

from core.database import get_db, track_feature_use
from core.logger import log_event, quest_log, QUEST_LOG_BUFFER, QUEST_LOG_LOCK
from core.registry import registry, SubModule
from modules.auth.helpers import login_required
from modules.quest.helpers import make_discord_headers, parse_discord_quest_item
from modules.quest.runner import get_user_quest_runner, stop_all_quest_runners

quest_bp = Blueprint('quest', __name__)

@quest_bp.route('/api/quests', methods=['GET'])
@login_required
def api_quests():
    user_id = session['user_id']
    account_id = request.args.get('account_id')
    with get_db() as conn:
        cursor = conn.cursor()
        token = ''
        if account_id and str(account_id) != 'main':
            cursor.execute('SELECT token FROM discord_accounts WHERE id = ? AND user_id = ?', (account_id, user_id))
            r = cursor.fetchone()
            if r:
                token = r['token']
        if not token:
            cursor.execute('SELECT discord_token FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            token = (row['discord_token'] if row else '') or session.get('discord_token', '')
    
    quests = []
    if token:
        try:
            headers = make_discord_headers(token)
            res = requests.get('https://discord.com/api/v9/quests/@me', headers=headers, timeout=10)
            if res.status_code == 200:
                raw = res.json()
                raw_quests = []
                if isinstance(raw, dict):
                    raw_quests = raw.get('quests', [])
                elif isinstance(raw, list):
                    raw_quests = raw
                for q in raw_quests:
                    quests.append(parse_discord_quest_item(q))
        except Exception as e:
            log_event(f'Lỗi tải Quests Discord từ API: {e}', 'warn')

    runner = get_user_quest_runner(user_id)
    return jsonify({
        'success': True,
        'quests': quests,
        'worker_status': runner.get_status()
    })

@quest_bp.route('/api/quests/enroll_all', methods=['POST'])
@login_required
def api_quests_enroll_all():
    user_id = session['user_id']
    data = request.get_json() or {}
    account_id = data.get('account_id')

    with get_db() as conn:
        cursor = conn.cursor()
        token = ''
        if account_id and str(account_id) != 'main':
            cursor.execute('SELECT token FROM discord_accounts WHERE id = ? AND user_id = ?', (account_id, user_id))
            r = cursor.fetchone()
            if r:
                token = r['token']
        if not token:
            cursor.execute('SELECT discord_token FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            token = (row['discord_token'] if row else '') or session.get('discord_token', '')

    if not token or len(token) < 20:
        return jsonify({'success': False, 'message': 'Vui lòng liên kết Discord Token trước!'}), 400

    runner = get_user_quest_runner(user_id)
    count = 0
    try:
        headers = make_discord_headers(token)
        res = requests.get('https://discord.com/api/v9/quests/@me', headers=headers, timeout=8)
        if res.status_code == 200:
            raw = res.json()
            raw_quests = raw.get('quests', []) if isinstance(raw, dict) else raw
            for q in raw_quests:
                p = parse_discord_quest_item(q)
                if not p['completable']:
                    continue
                if not p['enrolled'] and not p['completed']:
                    if runner.enroll(token, p['id']):
                        count += 1
                        time.sleep(1.5)
        log_event(f'Đã tự động nhận {count} nhiệm vụ Discord mới!', 'success')
        return jsonify({'success': True, 'count': count, 'message': f'Đã nhận thành công {count} nhiệm vụ mới!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi nhận nhiệm vụ: {str(e)}'}), 500

@quest_bp.route('/api/quests/start', methods=['POST'])
@login_required
def api_quests_start():
    user_id = session['user_id']
    data = request.get_json() or {}
    account_id = data.get('account_id')

    with get_db() as conn:
        cursor = conn.cursor()
        token = ''
        if account_id and str(account_id) != 'main':
            cursor.execute('SELECT token FROM discord_accounts WHERE id = ? AND user_id = ?', (account_id, user_id))
            r = cursor.fetchone()
            if r:
                token = r['token']
        if not token:
            cursor.execute('SELECT discord_token FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            token = (row['discord_token'] if row else '') or session.get('discord_token', '')

    if not token or len(token) < 20:
        return jsonify({'success': False, 'message': 'Vui lòng liên kết Discord Token trước khi cày Quest!'}), 400

    runner = get_user_quest_runner(user_id)
    track_feature_use(user_id, 'auto_quest')

    if data.get('auto', False) or data.get('quest_id') == 'auto':
        runner.start_auto(token)
        return jsonify({'success': True, 'message': 'Đã khởi động chế độ Tự Động Quét & Cày Tất Cả Nhiệm Vụ!'})

    quest_id = data.get('quest_id', 'quest_discord_desktop')
    quest_name = data.get('quest_name', 'Nhiệm Vụ Discord')
    task_type = data.get('task_type', 'PLAY_ON_DESKTOP')
    target_seconds = int(data.get('target_seconds', 45))

    runner.start(token, quest_id, quest_name, task_type=task_type, target_seconds=target_seconds)
    return jsonify({'success': True, 'message': f'Đã bắt đầu chạy Auto Quest cho {quest_name}!'})

@quest_bp.route('/api/quests/stop', methods=['POST'])
@login_required
def api_quests_stop():
    user_id = session['user_id']
    runner = get_user_quest_runner(user_id)
    runner.stop()
    return jsonify({'success': True, 'message': 'Đã dừng tiến trình Auto Quest'})

@quest_bp.route('/api/quests/status', methods=['GET'])
@login_required
def api_quests_status():
    user_id = session['user_id']
    runner = get_user_quest_runner(user_id)
    return jsonify({'success': True, 'status': runner.get_status()})

@quest_bp.route('/api/quests/logs', methods=['GET', 'DELETE'])
@login_required
def api_quests_logs():
    if request.method == 'DELETE':
        with QUEST_LOG_LOCK:
            QUEST_LOG_BUFFER.clear()
        quest_log('Đã xóa nhật ký Quest Console.', 'info')
        return jsonify({'success': True, 'message': 'Đã xóa nhật ký'})
    with QUEST_LOG_LOCK:
        logs_copy = list(QUEST_LOG_BUFFER)
    return jsonify({'success': True, 'logs': logs_copy})

@quest_bp.route('/api/hypesquad/claim', methods=['POST'])
@login_required
def api_hypesquad_claim():
    user_id = session['user_id']
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT discord_token FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
    token = (row['discord_token'] if row else '') or session.get('discord_token', '')
    if not token:
        return jsonify({'success': False, 'message': 'Vui lòng liên kết Discord Token trước!'}), 400

    data = request.get_json() or {}
    house_id = int(data.get('house_id', 1))
    houses = {1: 'Bravery (Tím)', 2: 'Brilliance (Cam)', 3: 'Balance (Xanh Lá)'}
    house_name = houses.get(house_id, 'Bravery')

    try:
        headers = make_discord_headers(token)
        res = requests.post('https://discord.com/api/v9/hypesquad/online', headers=headers, json={'house_id': house_id}, timeout=8)
        if res.status_code == 204:
            log_event(f'Nhận thành công huy hiệu HypeSquad {house_name} cho tài khoản {session.get("username")}', 'success')
            return jsonify({'success': True, 'message': f'Chúc mừng! Đã nhận thành công huy hiệu HypeSquad {house_name}!'})
        elif res.status_code == 429:
            retry = res.headers.get('Retry-After', '60')
            return jsonify({'success': False, 'message': f'Discord Rate Limited. Vui lòng thử lại sau {retry}s'}), 429
        else:
            return jsonify({'success': False, 'message': f'Không thể nhận huy hiệu (Mã lỗi {res.status_code})'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi kết nối: {str(e)}'}), 500

@quest_bp.route('/api/automation/vice_city_promo', methods=['POST'])
@login_required
def api_vice_city_promo():
    """Chức năng hữu hạn (hết hạn 14/12): Quét & nhận Nitro Trial/Promo miễn phí + kích hoạt diện mạo Vice City"""
    user_id = session['user_id']
    data = request.get_json() or {}
    account_id = data.get('account_id')
    action = str(data.get('action', 'both')).strip().lower()

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

    if not token or len(token) < 20:
        return jsonify({'success': False, 'message': 'Vui lòng liên kết Discord Token trước!'}), 400

    headers = make_discord_headers(token)
    logs = []
    claimed_items = []
    trials_found = []
    promos_found = []

    try:
        # 1. Kiểm tra các gói Nitro Free Trial khả dụng trên tài khoản
        if action in ('claim_nitro', 'both'):
            r_trials = requests.get('https://discord.com/api/v9/users/@me/billing/trials', headers=headers, timeout=8)
            if r_trials.status_code == 200:
                trials = r_trials.json() if isinstance(r_trials.json(), list) else []
                for tr in trials:
                    tid = tr.get('id')
                    offer = tr.get('trial_offer') or {}
                    expires_at = tr.get('expires_at') or ''
                    trials_found.append({'id': tid, 'expires_at': expires_at})
                    logs.append(f"Tìm thấy Nitro Free Trial ID {tid} (Hạn: {expires_at[:10] if expires_at else '14/12'})")
                    # Thử redeem trial nếu API cho phép không cần thẻ
                    if tid:
                        r_red = requests.post(f'https://discord.com/api/v9/users/@me/billing/trials/{tid}/redeem', headers=headers, json={}, timeout=8)
                        if r_red.status_code in (200, 201, 204):
                            claimed_items.append(f"Nitro Trial {tid}")
                            logs.append(f"ĐÃ CLAIM THÀNH CÔNG Nitro Trial {tid}!")
                        else:
                            logs.append(f"Trial {tid}: Discord yêu cầu xác minh/phương thức thanh toán hoặc đã hết lượt (HTTP {r_red.status_code})")
            else:
                logs.append(f"Quét Nitro Trials: HTTP {r_trials.status_code}")

            # 2. Quét Outbound Promotions & Claimed Gifts / Rewards khả dụng
            r_promo = requests.get('https://discord.com/api/v9/users/@me/outbound-promotions/codes', headers=headers, timeout=8)
            if r_promo.status_code == 200:
                codes = r_promo.json() if isinstance(r_promo.json(), list) else []
                for c in codes:
                    code_val = c.get('code')
                    promo_title = (c.get('promotion') or {}).get('outbound_title', 'Discord Promo')
                    if code_val:
                        promos_found.append({'title': promo_title, 'code': code_val})
                        logs.append(f"Code Promo khả dụng: {promo_title} -> {code_val}")

            r_gifts = requests.get('https://discord.com/api/v9/users/@me/entitlements/gifts', headers=headers, timeout=8)
            if r_gifts.status_code == 200 and isinstance(r_gifts.json(), list):
                for g in r_gifts.json():
                    logs.append(f"Gift Inventory: {g.get('sku_id')} (Còn {g.get('remaining_uses', 0)} lượt)")

        # 3. Quét & kích hoạt giao diện Vice City Theme (Khả dụng tới 14/12 cho mọi user & 21/02 cho Nitro)
        if action in ('theme', 'both'):
            r_set = requests.patch(
                'https://discord.com/api/v9/users/@me/settings',
                headers=headers,
                json={'theme': 'dark'},
                timeout=8
            )
            if r_set.status_code == 200:
                logs.append("Đã đồng bộ nền Dark Base chuẩn bị áp dụng diện mạo Vice City (hạn 14/12).")
            else:
                logs.append(f"Cập nhật theme cơ bản: HTTP {r_set.status_code}")

        if not logs:
            logs.append("Đã quét xong ưu đãi hữu hạn (hết hạn 14/12) trên Discord API.")

        track_feature_use(user_id, 'auto_quest')
        log_event(f'Vice City & Nitro Promo Scan ({acc_name}): {len(trials_found)} trials, {len(promos_found)} promos', 'success')
        return jsonify({
            'success': True,
            'message': f'Đã quét ưu đãi Vice City & Nitro (14/12) cho {acc_name}: tìm thấy {len(trials_found)} Trial, {len(promos_found)} Code.',
            'logs': logs,
            'trials': trials_found,
            'promos': promos_found,
            'claimed': claimed_items
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi kết nối Discord Promo API: {str(e)}'}), 500

registry.register_module(SubModule(
    key='auto_quest',
    category_key='script',
    title='Discord Auto Quest Runner & HypeSquad claimer',
    blueprint=quest_bp,
    cleanup_handler=stop_all_quest_runners
))
