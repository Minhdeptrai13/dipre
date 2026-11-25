import json
import uuid
import requests
from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash

from core.database import get_db
from core.discord_guard import discord_guard
from core.logger import log_event
from core.security import clear_failed_attempts, get_client_ip
from core.registry import registry, SubModule
from modules.auth.helpers import login_required
from modules.account.services import fetch_discord_profile
from modules.account.discord_effects import resolve_profile_effect

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
                'profile_effect_data': resolve_profile_effect(r['profile_effect']) if r['profile_effect'] else None,
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
                'profile_effect_data': resolve_profile_effect(u_row['profile_effect']) if u_row['profile_effect'] else None,
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


def _resolve_active_token(user_id, account_id=None):
    with get_db() as conn:
        cursor = conn.cursor()
        if account_id and str(account_id) != 'main':
            cursor.execute('SELECT token FROM discord_accounts WHERE id = ? AND user_id = ?', (account_id, user_id))
            r = cursor.fetchone()
            if r and r['token']:
                return r['token']
        cursor.execute('SELECT token FROM discord_accounts WHERE user_id = ? AND is_active = 1 LIMIT 1', (user_id,))
        acc_r = cursor.fetchone()
        if acc_r and acc_r['token']:
            return acc_r['token']
        cursor.execute('SELECT discord_token FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        if row and row['discord_token']:
            return row['discord_token']
    return session.get('discord_token', '')

def _snowflake_to_time_str(snowflake_id) -> str:
    try:
        import datetime
        ms = (int(snowflake_id) >> 22) + 1420070400000
        dt = datetime.datetime.fromtimestamp(ms / 1000.0)
        return dt.strftime('%H:%M %d/%m')
    except Exception:
        return ''

@account_bp.route('/api/discord/inbox', methods=['GET'])
@login_required
def api_discord_inbox():
    """Đọc 100% thật danh sách DM, Nhóm chat (Group DM) và Server từ Discord API"""
    user_id = session['user_id']
    account_id = request.args.get('account_id')
    token = _resolve_active_token(user_id, account_id)
    if not token:
        return jsonify({'success': False, 'message': 'Chưa liên kết token Discord'}), 400
    try:
        headers = {
            'Authorization': token,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        res = requests.get('https://discord.com/api/v9/users/@me/channels', headers=headers, timeout=10)
        if res.status_code != 200:
            return jsonify({'success': False, 'message': f'Lỗi Discord API ({res.status_code})'}), 400

        channels = res.json() if isinstance(res.json(), list) else []
        # Sắp xếp mới nhất lên đầu theo last_message_id (snowflake)
        channels.sort(key=lambda ch: int(ch.get('last_message_id') or 0), reverse=True)

        formatted = []
        for ch in channels[:40]:
            ch_type = ch.get('type')  # 1 = DM, 3 = Group DM
            recipients = ch.get('recipients', [])
            if ch_type == 3:
                name = ch.get('name') or (', '.join([r.get('global_name') or r.get('username', '') for r in recipients[:3]]) or 'Nhóm Chat')
                item_type = 'group'
                icon_hash = ch.get('icon')
                avatar = f"https://cdn.discordapp.com/channel-icons/{ch.get('id')}/{icon_hash}.png?size=64" if icon_hash else ''
            else:
                name = ', '.join([r.get('global_name') or r.get('username', '') for r in recipients]) if recipients else 'Direct Message'
                item_type = 'dm'
                avatar = ''
                if recipients:
                    r0 = recipients[0]
                    av_hash = r0.get('avatar')
                    avatar = f"https://cdn.discordapp.com/avatars/{r0['id']}/{av_hash}.png?size=64" if av_hash else "https://cdn.discordapp.com/embed/avatars/0.png"

            last_msg_id = ch.get('last_message_id')
            formatted.append({
                'id': ch.get('id'),
                'channel_id': ch.get('id'),
                'name': name or ('Nhóm' if item_type == 'group' else 'DM'),
                'avatar': avatar,
                'last_message_id': last_msg_id,
                'last_time': _snowflake_to_time_str(last_msg_id) if last_msg_id else 'Trống',
                'type': item_type,
                'raw_type': ch_type,
                'recipients_count': len(recipients) + (1 if ch_type == 3 else 0),
                'unread': bool(last_msg_id)
            })

        # Lấy thêm danh sách Servers (Guilds) thực tế để phục vụ nút Read All Guilds (như read.py)
        guilds_list = []
        try:
            g_res = requests.get('https://discord.com/api/v9/users/@me/guilds', headers=headers, timeout=8)
            if g_res.status_code == 200 and isinstance(g_res.json(), list):
                for g in g_res.json():
                    gid = g.get('id')
                    gicon = g.get('icon')
                    guilds_list.append({
                        'id': gid,
                        'name': g.get('name', 'Server'),
                        'icon': f"https://cdn.discordapp.com/icons/{gid}/{gicon}.png?size=64" if gicon else ''
                    })
        except Exception:
            pass

        return jsonify({
            'success': True,
            'channels': formatted,
            'conversations': formatted,
            'guilds': guilds_list,
            'guilds_count': len(guilds_list)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@account_bp.route('/api/discord/ack_channel', methods=['POST'])
@login_required
def api_discord_ack_channel():
    """Đánh dấu đã đọc 1 kênh DM hoặc Group DM cụ thể"""
    user_id = session['user_id']
    data = request.get_json() or {}
    channel_id = str(data.get('channel_id', '')).strip()
    message_id = str(data.get('message_id', '')).strip()
    account_id = data.get('account_id')
    token = _resolve_active_token(user_id, account_id)
    if not token or not channel_id:
        return jsonify({'success': False, 'message': 'Thiếu token hoặc channel_id'}), 400
    headers = {
        'Authorization': token,
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        if not message_id:
            r_ch = requests.get(f'https://discord.com/api/v9/channels/{channel_id}', headers=headers, timeout=6)
            if r_ch.status_code == 200:
                message_id = str(r_ch.json().get('last_message_id') or '')
        if message_id:
            r = requests.post(f'https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}/ack', headers=headers, json={'token': None}, timeout=6)
            return jsonify({'success': r.status_code in (200, 204), 'status_code': r.status_code})
        return jsonify({'success': True, 'message': 'Kênh chưa có tin nhắn'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@account_bp.route('/api/discord/read_all', methods=['POST'])
@login_required
def api_discord_read_all():
    """Đánh dấu đã đọc toàn bộ DM, Nhóm (Group DM) và/hoặc Server (tham khảo logic read.py của userdis)"""
    import time
    user_id = session['user_id']
    data = request.get_json() or {}
    scope = str(data.get('scope', 'all')).strip().lower()  # 'dms', 'groups', 'dm_group', 'guilds', 'all'
    account_id = data.get('account_id')
    token = _resolve_active_token(user_id, account_id)

    if not token:
        return jsonify({'success': False, 'message': 'Chưa liên kết token Discord'}), 400

    headers = {
        'Authorization': token,
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    read_dms = 0
    read_groups = 0
    read_guilds = 0
    failed = 0

    try:
        # 1. Đánh dấu đã đọc DM & Group DM (channels)
        if scope in ('dms', 'groups', 'dm_group', 'all'):
            r_ch = requests.get('https://discord.com/api/v9/users/@me/channels', headers=headers, timeout=10)
            if r_ch.status_code == 200 and isinstance(r_ch.json(), list):
                for ch in r_ch.json():
                    ch_type = ch.get('type')
                    last_id = ch.get('last_message_id')
                    if not last_id:
                        continue
                    if scope == 'dms' and ch_type != 1:
                        continue
                    if scope == 'groups' and ch_type != 3:
                        continue
                    if scope in ('dm_group', 'all') and ch_type not in (1, 3):
                        continue
                    try:
                        allowed, reason = discord_guard.wait_if_needed(token, action='ack')
                        if not allowed:
                            return jsonify({
                                'success': True,
                                'message': f'Anti-Ban Shield đã tạm dừng Read All ({reason}) — đã đọc {read_dms} DM, {read_groups} Nhóm.',
                                'read_dms': read_dms, 'read_groups': read_groups, 'read_guilds': read_guilds, 'failed': failed, 'anti_ban_paused': True
                            })
                        r_ack = requests.post(
                            f"https://discord.com/api/v9/channels/{ch['id']}/messages/{last_id}/ack",
                            headers=headers,
                            json={'token': None},
                            timeout=6
                        )
                        discord_guard.record_response(token, r_ack.status_code, r_ack.headers, r_ack.text)
                        if r_ack.status_code in (200, 204):
                            if ch_type == 3:
                                read_groups += 1
                            else:
                                read_dms += 1
                        else:
                            failed += 1
                            if r_ack.status_code == 429:
                                break
                    except Exception:
                        failed += 1

        # 2. Đánh dấu đã đọc toàn bộ Server (Guilds Ack - giống read.py ack_guild)
        if scope in ('guilds', 'all'):
            r_g = requests.get('https://discord.com/api/v9/users/@me/guilds', headers=headers, timeout=10)
            if r_g.status_code == 200 and isinstance(r_g.json(), list):
                for g in r_g.json():
                    gid = g.get('id')
                    if not gid:
                        continue
                    try:
                        allowed, reason = discord_guard.wait_if_needed(token, action='ack')
                        if not allowed:
                            return jsonify({
                                'success': True,
                                'message': f'Anti-Ban Shield đã tạm dừng Read All ({reason}) — đã đọc {read_guilds} Server.',
                                'read_dms': read_dms, 'read_groups': read_groups, 'read_guilds': read_guilds, 'failed': failed, 'anti_ban_paused': True
                            })
                        r_ack_g = requests.post(
                            f'https://discord.com/api/v9/guilds/{gid}/ack',
                            headers=headers,
                            json={},
                            timeout=6
                        )
                        discord_guard.record_response(token, r_ack_g.status_code, r_ack_g.headers, r_ack_g.text)
                        if r_ack_g.status_code in (200, 204):
                            read_guilds += 1
                        else:
                            failed += 1
                            if r_ack_g.status_code == 429:
                                break
                    except Exception:
                        failed += 1

        msg_parts = []
        if read_dms:
            msg_parts.append(f'{read_dms} DM')
        if read_groups:
            msg_parts.append(f'{read_groups} Nhóm')
        if read_guilds:
            msg_parts.append(f'{read_guilds} Server')
        summary = ', '.join(msg_parts) if msg_parts else '0 mục cần đánh dấu'

        log_event(f'Read All ({scope}): Đã đánh dấu đã đọc {summary} (Lỗi: {failed})', 'success')
        return jsonify({
            'success': True,
            'message': f'Đã đánh dấu đã đọc: {summary}!',
            'read_dms': read_dms,
            'read_groups': read_groups,
            'read_guilds': read_guilds,
            'failed': failed
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi Read All: {str(e)}'}), 500

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
