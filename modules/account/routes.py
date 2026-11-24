import uuid
import requests
from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash

from core.database import get_db
from core.logger import log_event
from core.security import clear_failed_attempts, get_client_ip
from core.registry import registry, SubModule
from modules.auth.helpers import login_required
from modules.account.services import fetch_discord_profile

account_bp = Blueprint('account', __name__)

@account_bp.route('/api/account/quick_oauth', methods=['POST'])
def api_account_quick_oauth():
    """Hỗ trợ đăng nhập nhanh bằng tài khoản Discord / Google"""
    data = request.get_json() or {}
    provider = data.get('provider')
    username = data.get('username', '').strip()
    
    if not username:
        username = 'User_' + uuid.uuid4().hex[:6]

    with get_db() as conn:
        cursor = conn.cursor()
        if provider == 'discord':
            cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()
            if not user:
                pwd_dummy = generate_password_hash(uuid.uuid4().hex)
                cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, pwd_dummy))
                user_id = cursor.lastrowid
            else:
                user_id = user['id']
            conn.commit()

            session['user_id'] = user_id
            session['username'] = username
            clear_failed_attempts(get_client_ip())
            log_event(f'Đăng nhập tài khoản qua Discord OAuth2: {username}', 'success')
            return jsonify({'success': True, 'message': f'Chào mừng {username}!'})

        elif provider == 'google':
            email = data.get('email', '').strip()
            cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()
            if not user:
                pwd_dummy = generate_password_hash(uuid.uuid4().hex)
                cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, pwd_dummy))
                user_id = cursor.lastrowid
            else:
                user_id = user['id']
            conn.commit()

            session['user_id'] = user_id
            session['username'] = username
            clear_failed_attempts(get_client_ip())
            log_event(f'Đăng nhập tài khoản qua Google OAuth2: {username} ({email})', 'success')
            return jsonify({'success': True, 'message': f'Chào mừng {username}!'})

        else:
            return jsonify({'success': False, 'message': 'Phương thức đăng nhập không hợp lệ'}), 400

@account_bp.route('/api/account/info', methods=['GET'])
@login_required
def api_account_info():
    user_id = session['user_id']
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT username, discord_token, discord_id, discord_username, discord_avatar, auth_provider, avatar_url, google_avatar, profile_effect, avatar_decoration, banner FROM users WHERE id = ?', (user_id,))
        u = cursor.fetchone()
        if not u:
            username = session.get('username') or f'User_{user_id}'
            cursor.execute('INSERT OR IGNORE INTO users (id, username, password_hash) VALUES (?, ?, ?)', (user_id, username, 'autogen'))
            conn.commit()
            cursor.execute('SELECT username, discord_token, discord_id, discord_username, discord_avatar, auth_provider, avatar_url, google_avatar, profile_effect, avatar_decoration, banner FROM users WHERE id = ?', (user_id,))
            u = cursor.fetchone()
        
        main_discord_id = (u['discord_id'] if u else '') or ''
        if main_discord_id:
            cursor.execute('''
                SELECT * FROM discord_accounts 
                WHERE user_id = ? AND discord_id != ?
                ORDER BY is_active DESC, id DESC
            ''', (user_id, str(main_discord_id)))
        else:
            cursor.execute('''
                SELECT * FROM discord_accounts 
                WHERE user_id = ?
                ORDER BY is_active DESC, id DESC
            ''', (user_id,))
        accounts = [dict(r) for r in cursor.fetchall()]

    u_dict = dict(u) if u else {}
    token = u_dict.get('discord_token') or ''
    has_token = bool(token and len(token) > 20) or bool(accounts)
    masked = (token[:10] + '...' + token[-6:]) if (token and len(token) > 20) else ''

    active_acc = next((a for a in accounts if a.get('is_active') == 1), None) or (accounts[0] if accounts else None)

    return jsonify({
        'success': True,
        'username': u_dict.get('username') or session.get('username', 'User'),
        'auth_provider': u_dict.get('auth_provider') or 'local',
        'avatar_url': u_dict.get('avatar_url') or u_dict.get('google_avatar') or '',
        'google_avatar': u_dict.get('google_avatar') or '',
        'has_token': has_token,
        'discord_id': u_dict.get('discord_id') or (active_acc['discord_id'] if active_acc else ''),
        'discord_username': u_dict.get('discord_username') or (active_acc['discord_username'] if active_acc else ''),
        'discord_avatar': u_dict.get('discord_avatar') or (active_acc['discord_avatar'] if active_acc else ''),
        'avatar_decoration': u_dict.get('avatar_decoration') or (active_acc.get('avatar_decoration') if active_acc else ''),
        'banner': u_dict.get('banner') or (active_acc.get('banner') if active_acc else ''),
        'profile_effect': u_dict.get('profile_effect') or (active_acc.get('profile_effect') if active_acc else ''),
        'masked_token': masked,
        'accounts': accounts
    })

@account_bp.route('/api/account/bind_token', methods=['POST'])
@login_required
def api_account_bind_token():
    data = request.get_json() or {}
    token = data.get('token', '').strip()
    if not token:
        return jsonify({'success': False, 'message': 'Vui lòng cung cấp Discord User Token'}), 400
    try:
        profile = fetch_discord_profile(token)
        if not profile:
            return jsonify({'success': False, 'message': 'Token Discord không hợp lệ hoặc đã hết hạn.'}), 400

        user_id = session['user_id']
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            u = cursor.fetchone()
            if not u:
                username = session.get('username') or f'User_{user_id}'
                cursor.execute('INSERT OR IGNORE INTO users (id, username, password_hash) VALUES (?, ?, ?)', (user_id, username, 'autogen'))
                conn.commit()
                cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
                u = cursor.fetchone()

            # Luôn cập nhật đầy đủ profile Discord chính chủ vào users để avatar và hiệu ứng hiển thị ngay lập tức
            cursor.execute('''
                UPDATE users 
                SET discord_token = ?,
                    discord_id = ?,
                    discord_username = ?,
                    discord_avatar = ?,
                    avatar_decoration = ?,
                    banner = ?,
                    profile_effect = ?,
                    bio = ?,
                    badges = ?
                WHERE id = ?
            ''', (
                token,
                profile['id'],
                profile['username'],
                profile['avatar'],
                profile['decoration'],
                profile['banner'],
                profile.get('profile_effect', ''),
                profile.get('bio', ''),
                json.dumps(profile.get('badges', []), ensure_ascii=False),
                user_id
            ))

            # Quản lý tài khoản trong bảng discord_accounts
            cursor.execute('UPDATE discord_accounts SET is_active = 0 WHERE user_id = ?', (user_id,))
            cursor.execute('SELECT id FROM discord_accounts WHERE user_id = ? AND (token = ? OR discord_id = ?)', (user_id, token, profile['id']))
            existing = cursor.fetchone()
            if existing:
                cursor.execute('''
                    UPDATE discord_accounts
                    SET token = ?, discord_id = ?, discord_username = ?, discord_avatar = ?, avatar_decoration = ?, banner = ?, profile_effect = ?, is_active = 1
                    WHERE id = ?
                ''', (token, profile['id'], profile['username'], profile['avatar'], profile['decoration'], profile['banner'], profile.get('profile_effect', ''), existing['id']))
            else:
                cursor.execute('''
                    INSERT INTO discord_accounts (user_id, token, discord_id, discord_username, discord_avatar, avatar_decoration, banner, profile_effect, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                ''', (user_id, token, profile['id'], profile['username'], profile['avatar'], profile['decoration'], profile['banner'], profile.get('profile_effect', '')))
            conn.commit()

        session['discord_token'] = token
        log_event(f'Tài khoản {session.get("username")} đã kết nối Discord thành công: {profile["username"]} ({profile["id"]})', 'success')
        return jsonify({
            'success': True,
            'message': f'Đã liên kết tài khoản Discord thành công: {profile["username"]}!',
            'username': profile['username'],
            'avatar': profile['avatar'],
            'discord_id': profile['id'],
            'discord_username': profile['username'],
            'discord_avatar': profile['avatar'],
            'avatar_decoration': profile['decoration'],
            'banner': profile['banner'],
            'profile_effect': profile.get('profile_effect', ''),
            'badges': profile.get('badges', []),
            'bio': profile.get('bio', '')
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi kết nối xác minh Discord: {str(e)}'}), 500

@account_bp.route('/api/accounts/list', methods=['GET'])
@login_required
def api_accounts_list():
    """Trả về toàn bộ danh sách tài khoản Discord đã nạp trong Vault (cả chính và phụ)"""
    user_id = session['user_id']
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, discord_token, discord_id, discord_username, discord_avatar, avatar_decoration, banner, profile_effect, bio 
            FROM users WHERE id = ?
        ''', (user_id,))
        u_row = cursor.fetchone()

        cursor.execute('''
            SELECT id, token, discord_id, discord_username, discord_avatar, avatar_decoration, banner, profile_effect, is_active, created_at 
            FROM discord_accounts 
            WHERE user_id = ?
            ORDER BY is_active DESC, id DESC
        ''', (user_id,))
        sub_rows = [dict(r) for r in cursor.fetchall()]

    all_accounts = []
    seen_discord_ids = set()

    for r in sub_rows:
        d_id = str(r['discord_id']) if r['discord_id'] else str(r['id'])
        if d_id not in seen_discord_ids:
            seen_discord_ids.add(d_id)
            all_accounts.append({
                'id': str(r['id']),
                'db_id': r['id'],
                'discord_id': r['discord_id'] or '',
                'discord_username': r['discord_username'] or 'Discord User',
                'discord_avatar': r['discord_avatar'] or '',
                'avatar_decoration': r['avatar_decoration'] or '',
                'banner': r['banner'] or '',
                'profile_effect': r['profile_effect'] or '',
                'is_active': 1 if r.get('is_active') == 1 else 0,
                'main': r.get('is_active') == 1 or len(all_accounts) == 0,
                'has_token': bool(r.get('token') and len(r['token']) > 20)
            })

    if u_row and (u_row['discord_token'] or u_row['discord_username']):
        u_did = str(u_row['discord_id']) if u_row['discord_id'] else 'main'
        if u_did not in seen_discord_ids:
            seen_discord_ids.add(u_did)
            all_accounts.insert(0, {
                'id': 'main',
                'db_id': 'main',
                'discord_id': u_row['discord_id'] or '',
                'discord_username': u_row['discord_username'] or 'Discord User',
                'discord_avatar': u_row['discord_avatar'] or '',
                'avatar_decoration': u_row['avatar_decoration'] or '',
                'banner': u_row['banner'] or '',
                'profile_effect': u_row['profile_effect'] or '',
                'is_active': 1 if not any(a.get('is_active') == 1 for a in all_accounts) else 0,
                'main': True,
                'has_token': bool(u_row['discord_token'] and len(u_row['discord_token']) > 20)
            })

    if all_accounts and not any(a.get('main') for a in all_accounts):
        all_accounts[0]['main'] = True

    return jsonify({'success': True, 'accounts': all_accounts})

@account_bp.route('/api/accounts/switch', methods=['POST'])
@login_required
def api_accounts_switch():
    user_id = session['user_id']
    data = request.get_json() or {}
    account_id = data.get('account_id')
    if not account_id:
        return jsonify({'success': False, 'message': 'Thiếu account_id'}), 400
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM discord_accounts WHERE id = ? AND user_id = ?', (account_id, user_id))
        target = cursor.fetchone()
        if not target:
            return jsonify({'success': False, 'message': 'Không tìm thấy tài khoản này'}), 404

        cursor.execute('UPDATE discord_accounts SET is_active = 0 WHERE user_id = ?', (user_id,))
        cursor.execute('UPDATE discord_accounts SET is_active = 1 WHERE id = ?', (account_id,))
        cursor.execute('UPDATE users SET discord_token = ? WHERE id = ?', (target['token'], user_id))
        conn.commit()

    session['discord_token'] = target['token']
    log_event(f'Đã chuyển sang tài khoản Discord phụ: {target["discord_username"]}', 'info')
    return jsonify({
        'success': True,
        'message': f'Đã chuyển sang tài khoản phụ: {target["discord_username"]}',
        'username': target['discord_username'],
        'avatar': target['discord_avatar'],
        'discord_id': target['discord_id'],
        'discord_username': target['discord_username'],
        'discord_avatar': target['discord_avatar'],
        'avatar_decoration': target['avatar_decoration'],
        'banner': target['banner'],
        'profile_effect': target['profile_effect']
    })

@account_bp.route('/api/accounts/delete', methods=['POST'])
@login_required
def api_accounts_delete():
    user_id = session['user_id']
    data = request.get_json() or {}
    account_id = data.get('account_id')
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT is_active FROM discord_accounts WHERE id = ? AND user_id = ?', (account_id, user_id))
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'Không tìm thấy tài khoản'}), 404
        was_active = row['is_active'] == 1
        cursor.execute('DELETE FROM discord_accounts WHERE id = ? AND user_id = ?', (account_id, user_id))
        
        if was_active:
            cursor.execute('SELECT * FROM discord_accounts WHERE user_id = ? ORDER BY id DESC LIMIT 1', (user_id,))
            next_acc = cursor.fetchone()
            if next_acc:
                cursor.execute('UPDATE discord_accounts SET is_active = 1 WHERE id = ?', (next_acc['id'],))
                cursor.execute('UPDATE users SET discord_token = ? WHERE id = ?', (next_acc['token'], user_id))
                session['discord_token'] = next_acc['token']
            else:
                cursor.execute('UPDATE users SET discord_token = "" WHERE id = ?', (user_id,))
                session.pop('discord_token', None)
        conn.commit()
    return jsonify({'success': True, 'message': 'Đã xóa tài khoản khỏi danh sách'})

@account_bp.route('/api/account/unbind_token', methods=['POST'])
@login_required
def api_account_unbind_token():
    user_id = session['user_id']
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT auth_provider FROM users WHERE id = ?', (user_id,))
        u = cursor.fetchone()
        if u and u['auth_provider'] == 'discord':
            cursor.execute('UPDATE users SET discord_token = "" WHERE id = ?', (user_id,))
        else:
            cursor.execute('UPDATE users SET discord_token = "", discord_id = "", discord_username = "", discord_avatar = "" WHERE id = ?', (user_id,))
        cursor.execute('UPDATE discord_accounts SET is_active = 0 WHERE user_id = ?', (user_id,))
        conn.commit()
    session.pop('discord_token', None)
    log_event(f'Đã hủy liên kết Discord Token cho tài khoản {session.get("username")}', 'info')
    return jsonify({'success': True, 'message': 'Đã hủy liên kết token thành công'})


@account_bp.route('/api/discord/inbox', methods=['GET'])
@login_required
def api_discord_inbox():
    """Đọc hòm thư / tin nhắn chưa đọc & kênh gần nhất của token active"""
    user_id = session['user_id']
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT discord_token FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
    token = (row['discord_token'] if row else '') or session.get('discord_token', '')
    if not token:
        return jsonify({'success': False, 'message': 'Chưa liên kết token Discord'}), 400
    try:
        headers = {
            'Authorization': token,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        res = requests.get('https://discord.com/api/v9/users/@me/channels', headers=headers, timeout=8)
        if res.status_code == 200:
            channels = res.json()
            formatted = []
            for ch in channels[:15]:
                recipients = ch.get('recipients', [])
                name = ', '.join([r.get('global_name') or r.get('username', '') for r in recipients]) if recipients else 'Direct Message'
                last_msg_id = ch.get('last_message_id')
                avatar = ''
                if recipients:
                    r0 = recipients[0]
                    av_hash = r0.get('avatar')
                    avatar = f"https://cdn.discordapp.com/avatars/{r0['id']}/{av_hash}.png?size=64" if av_hash else "https://cdn.discordapp.com/embed/avatars/0.png"
                formatted.append({
                    'id': ch.get('id'),
                    'name': name or 'DM',
                    'avatar': avatar,
                    'last_message_id': last_msg_id,
                    'type': ch.get('type')
                })
            return jsonify({'success': True, 'channels': formatted, 'conversations': formatted})
        else:
            return jsonify({'success': False, 'message': f'Lỗi Discord API ({res.status_code})'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@account_bp.route('/api/discord/channel_messages/<channel_id>', methods=['GET'])
@login_required
def api_discord_channel_messages(channel_id):
    """Lấy danh sách tin nhắn của channel/DM cụ thể"""
    user_id = session['user_id']
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT discord_token FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
    token = (row['discord_token'] if row else '') or session.get('discord_token', '')
    if not token:
        return jsonify({'success': False, 'message': 'Chưa liên kết token Discord'}), 400

    try:
        headers = {
            'Authorization': token,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        res = requests.get(f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=25', headers=headers, timeout=8)
        if res.status_code == 200:
            msgs = res.json()
            formatted = []
            for m in reversed(msgs):
                author = m.get('author', {})
                a_id = author.get('id')
                a_av = author.get('avatar')
                av_url = f"https://cdn.discordapp.com/avatars/{a_id}/{a_av}.png?size=64" if (a_id and a_av) else "https://cdn.discordapp.com/embed/avatars/0.png"
                formatted.append({
                    'id': m.get('id'),
                    'content': m.get('content', ''),
                    'author_name': author.get('global_name') or author.get('username', 'User'),
                    'author_id': a_id,
                    'author_avatar': av_url,
                    'timestamp': m.get('timestamp', '')
                })
            return jsonify({'success': True, 'messages': formatted})
        else:
            return jsonify({'success': False, 'message': f'Discord API trả về {res.status_code}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@account_bp.route('/api/discord/send_message', methods=['POST'])
@login_required
def api_discord_send_message():
    """Gửi tin nhắn trực tiếp qua tài khoản Discord đang chọn"""
    user_id = session['user_id']
    data = request.get_json() or {}
    channel_id = data.get('channel_id')
    content = str(data.get('content', '')).strip()
    account_id = data.get('account_id')

    if not channel_id or not content:
        return jsonify({'success': False, 'message': 'Thiếu channel_id hoặc nội dung tin nhắn'}), 400

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

    if not token:
        return jsonify({'success': False, 'message': 'Chưa liên kết token Discord'}), 400

    try:
        headers = {
            'Authorization': token,
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        payload = {'content': content}
        res = requests.post(f'https://discord.com/api/v9/channels/{channel_id}/messages', headers=headers, json=payload, timeout=8)
        if res.status_code in (200, 201):
            return jsonify({'success': True, 'message': 'Đã gửi tin nhắn thành công', 'data': res.json()})
        else:
            return jsonify({'success': False, 'message': f'Lỗi Discord API ({res.status_code}): {res.text}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@account_bp.route('/api/dashboard/stats', methods=['GET'])
@login_required
def api_dashboard_stats():
    """Lấy dữ liệu thống kê tổng hợp phục vụ hiển thị Dashboard Command Center"""
    user_id = session.get('user_id')
    from core.database import get_dashboard_stats
    stats = get_dashboard_stats(user_id)
    return jsonify({'success': True, 'stats': stats})

registry.register_module(SubModule(
    key='multi_account',
    category_key='account',
    title='Multi-Token Account Manager & Inbox',
    blueprint=account_bp
))
