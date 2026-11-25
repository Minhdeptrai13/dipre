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
    """Chức năng hữu hạn (hết hạn 14/12): Gọi đúng chuỗi Discord API (user-offer, promotions, trials, entitlements, settings-proto)"""
    import base64
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
        # 1. Kích hoạt User Offer Trigger giống hệt Discord Store (POST /users/@me/billing/user-offer)
        if action in ('claim_nitro', 'both'):
            try:
                r_offer = requests.post(
                    'https://discord.com/api/v9/users/@me/billing/user-offer',
                    headers=headers,
                    json={'allow_triggers': True},
                    timeout=8
                )
                logs.append(f"Kích hoạt User Offer Trigger: HTTP {r_offer.status_code}")
                if r_offer.status_code == 200 and r_offer.text:
                    offer_json = r_offer.json()
                    if offer_json.get('user_trial_offer'):
                        ut = offer_json['user_trial_offer']
                        trials_found.append({'id': ut.get('id'), 'expires_at': ut.get('expires_at', '')})
                        logs.append(f"Phát hiện User Trial Offer: ID {ut.get('id')}")
            except Exception as oe:
                logs.append(f"User Offer check: {oe}")

            # 2. Quét danh sách Promotions đang chạy trên Discord Store (GET /promotions?locale=vi&platform=0)
            try:
                r_store_promo = requests.get(
                    'https://discord.com/api/v9/promotions?locale=vi&platform=0',
                    headers=headers,
                    timeout=8
                )
                if r_store_promo.status_code == 200 and isinstance(r_store_promo.json(), list):
                    for pr in r_store_promo.json():
                        title = pr.get('outbound_title') or pr.get('outbound_promo_page') or pr.get('inbound_header_text') or pr.get('outbound_redemption_page_link') or pr.get('id')
                        if len(str(title)) > 60:
                            title = str(title)[:60] + '...'
                        end_d = str(pr.get('end_date') or '')[:10]
                        logs.append(f"Store Promo: {title} (Hết hạn: {end_d})")
                        promos_found.append({'title': title, 'end_date': end_d, 'id': pr.get('id')})
            except Exception:
                pass

            # 3. Kiểm tra trạng thái Nitro thật của acc (@me, subscriptions, nitro-affinity, storefront/promotions)
            try:
                r_me = requests.get('https://discord.com/api/v9/users/@me', headers=headers, timeout=8)
                if r_me.status_code == 200:
                    me_j = r_me.json()
                    pt = me_j.get('premium_type', 0)
                    pt_map = {0: 'Chưa có Nitro', 1: 'Nitro Classic', 2: 'Nitro Boost', 3: 'Nitro Basic'}
                    logs.append(f"Tài khoản {me_j.get('username')}: {pt_map.get(pt, f'Type {pt}')}")

                r_sub = requests.get('https://discord.com/api/v9/users/@me/billing/subscriptions?sync_level=2&with_gift_subscription=true', headers=headers, timeout=8)
                if r_sub.status_code == 200 and isinstance(r_sub.json(), list):
                    subs_list = r_sub.json()
                    if subs_list:
                        for s in subs_list:
                            logs.append(f"Subscription: status={s.get('status')}, hết hạn={str(s.get('current_period_end', ''))[:10]}")
                    else:
                        logs.append("Subscriptions: 0 gói trả phí trực tiếp (có thể đang dùng Nitro Trial / Gift).")

                r_sf = requests.get('https://discord.com/api/v9/storefront/promotions?application_ids=1096190356233670716', headers=headers, timeout=8)
                if r_sf.status_code == 200 and r_sf.text:
                    sf_data = r_sf.json()
                    if isinstance(sf_data, list) and sf_data:
                        logs.append(f"Storefront Promotions: {len(sf_data)} ưu đãi khả dụng.")
            except Exception as te:
                logs.append(f"Billing check note: {te}")

            # 4. Quét Code Outbound Promotions & Toàn bộ Entitlements (không lọc type để thấy cả Nitro Trial/Vice City)
            r_promo = requests.get('https://discord.com/api/v9/users/@me/outbound-promotions/codes', headers=headers, timeout=8)
            if r_promo.status_code == 200 and isinstance(r_promo.json(), list):
                for c in r_promo.json():
                    code_val = c.get('code')
                    promo_title = (c.get('promotion') or {}).get('outbound_title', 'Discord Promo')
                    if code_val:
                        promos_found.append({'title': promo_title, 'code': code_val})
                        logs.append(f"Code Promo khả dụng: {promo_title} -> {code_val}")

            r_ent = requests.get(
                'https://discord.com/api/v9/users/@me/entitlements?exclude_ended=true',
                headers=headers,
                timeout=8
            )
            if r_ent.status_code == 200 and isinstance(r_ent.json(), list):
                ents = r_ent.json()
                logs.append(f"Đang sở hữu {len(ents)} quyền lợi (Entitlements) đang hoạt động trên acc.")

        # 5. Áp dụng Theme qua PreloadedUserSettings Protobuf (/users/@me/settings-proto/1)
        if action in ('theme', 'both'):
            theme_applied = False
            try:
                from discord_protos import PreloadedUserSettings
                r_get_proto = requests.get('https://discord.com/api/v9/users/@me/settings-proto/1', headers=headers, timeout=8)
                if r_get_proto.status_code == 200:
                    b64_cur = r_get_proto.json().get('settings', '')
                    proto = PreloadedUserSettings()
                    if b64_cur:
                        proto.ParseFromString(base64.b64decode(b64_cur))
                    # Theme enum: 0=UNSET, 1=DARK, 2=LIGHT
                    proto.appearance.theme = 1
                    proto.appearance.client_theme_settings.background_gradient_preset_id.value = 18
                    new_b64 = base64.b64encode(proto.SerializeToString()).decode('ascii')
                    r_patch_proto = requests.patch(
                        'https://discord.com/api/v9/users/@me/settings-proto/1',
                        headers=headers,
                        json={'settings': new_b64},
                        timeout=8
                    )
                    if r_patch_proto.status_code == 200:
                        theme_applied = True
                        logs.append("Đã đồng bộ Client Theme Gradient lên Discord qua Protobuf (/settings-proto/1)!")
                    else:
                        logs.append(f"Cập nhật Client Theme Protobuf: HTTP {r_patch_proto.status_code} (Discord có thể giới hạn theo gói Nitro)")
            except Exception as pe:
                logs.append(f"Protobuf Theme note: {pe}")

            if not theme_applied:
                r_set = requests.patch(
                    'https://discord.com/api/v9/users/@me/settings',
                    headers=headers,
                    json={'theme': 'dark'},
                    timeout=8
                )
                if r_set.status_code == 200:
                    logs.append("Đã đồng bộ Dark Base Theme cho Discord.")

        if not logs:
            logs.append("Đã quét xong ưu đãi hữu hạn (hết hạn 14/12) trên Discord API.")

        track_feature_use(user_id, 'auto_quest')
        log_event(f'Vice City & Nitro Promo Scan ({acc_name}): {len(trials_found)} trials, {len(promos_found)} promos', 'success')
        return jsonify({
            'success': True,
            'message': f'Đã quét ưu đãi Vice City & Nitro (14/12) cho {acc_name}: tìm thấy {len(trials_found)} Trial, {len(promos_found)} Promo.',
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
