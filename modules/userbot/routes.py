import os
import sys
from flask import Blueprint, request, jsonify, session

from core.database import get_db, track_feature_use
from core.logger import userbot_log, USERBOT_LOG_BUFFER, USERBOT_LOG_LOCK
from core.registry import registry, SubModule
from modules.auth.helpers import login_required
from modules.userbot.worker import userbot_worker

userbot_bp = Blueprint('userbot', __name__)

COMMANDS_CATALOG = [
    {
        'category': 'AI & Trí Tuệ Nhân Tạo',
        'icon': 'bot',
        'description': 'Tích hợp ChatGPT, Gemini và mô hình AI trực tiếp trong tin nhắn chat',
        'commands': [
            {'name': 'ai <câu hỏi>', 'desc': 'Trò chuyện và hỏi đáp thông minh với AI'},
            {'name': 'ask <nội dung>', 'desc': 'Hỏi nhanh AI xử lý dữ liệu'},
            {'name': 'dich <text>', 'desc': 'Dịch thuật đa ngôn ngữ bằng AI Google/DeepL'}
        ]
    },
    {
        'category': 'Media & Tải Video Mạng Xã Hội',
        'icon': 'download',
        'description': 'Tải video, nhạc không logo từ TikTok, YouTube, Facebook, SoundCloud, v.v.',
        'commands': [
            {'name': 'tiktok <link>', 'desc': 'Tải video TikTok không dính watermark/logo'},
            {'name': 'yt <link|tên>', 'desc': 'Tìm kiếm và tải video/nhạc YouTube cực nét'},
            {'name': 'fb <link>', 'desc': 'Tải video Facebook HD / Reels siêu tốc'},
            {'name': 'scl <link|tên>', 'desc': 'Nghe và tải bài hát SoundCloud chất lượng cao'},
            {'name': 'x <link>', 'desc': 'Tải video từ Twitter / X'},
            {'name': 'ig <link>', 'desc': 'Tải bài viết hoặc Reels Instagram'},
            {'name': 'threads <link>', 'desc': 'Tải video bài viết từ Threads'},
            {'name': 'extract <reply video>', 'desc': 'Tách âm thanh MP3 từ video'}
        ]
    },
    {
        'category': 'Voice 24/7 & Lavalink Engine',
        'icon': 'mic',
        'description': 'Treo phòng thoại 24/7, phát nhạc lossless qua Lavalink SSL',
        'commands': [
            {'name': 'join <channel_id>', 'desc': 'Treo tài khoản vào phòng Voice 24/7 không rớt'},
            {'name': 'leave', 'desc': 'Rời phòng thoại hiện tại'},
            {'name': 'play <bài hát>', 'desc': 'Phát nhạc vào phòng voice qua Lavalink Engine'}
        ]
    },
    {
        'category': 'Auto Quest & Tự Động Hóa',
        'icon': 'award',
        'description': 'Tự động hoàn thành Discord Quests nhận vật phẩm, Nitro avatar decoration',
        'commands': [
            {'name': 'quest list', 'desc': 'Xem danh sách nhiệm vụ Discord Quests có sẵn'},
            {'name': 'quest auto', 'desc': 'Tự động cày hoàn thành toàn bộ Quests nhận quà'}
        ]
    },
    {
        'category': 'AFK & Trả Lời Tự Động',
        'icon': 'clock',
        'description': 'Tự động phản hồi khi có người tag hoặc nhắn tin lúc bạn vắng mặt',
        'commands': [
            {'name': 'afk [lý do]', 'desc': 'Bật chế độ AFK tự động trả lời khi được nhắc tên'},
            {'name': 'unafk', 'desc': 'Tắt chế độ AFK'}
        ]
    },
    {
        'category': 'Quản Lý & Tiện Ích Discord',
        'icon': 'settings',
        'description': 'Kiểm tra thông tin tài khoản, server, crypto, thời tiết, xóa tin nhắn',
        'commands': [
            {'name': 'menu', 'desc': 'Mở menu giao diện tương tác đẹp mắt (Glass theme)'},
            {'name': 'prefix [mới]', 'desc': 'Xem hoặc đổi tiền tố lệnh cho tài khoản'},
            {'name': 'info [user]', 'desc': 'Xem chi tiết avatar, banner, decoration tài khoản'},
            {'name': 'server', 'desc': 'Xem thống kê server Discord hiện tại'},
            {'name': 'del <số lượng>', 'desc': 'Xóa nhanh số lượng tin nhắn đã gửi'},
            {'name': 'crypto [btc/eth]', 'desc': 'Tra cứu tỷ giá tiền điện tử thời gian thực'},
            {'name': 'weather <địa điểm>', 'desc': 'Dự báo thời tiết địa phương chi tiết'},
            {'name': 'mail gen', 'desc': 'Tạo email tạm thời và nhận mã OTP'}
        ]
    }
]

@userbot_bp.route('/api/userbot/status', methods=['GET'])
@login_required
def api_userbot_status():
    """Lấy danh sách tài khoản cùng trạng thái UserBot (luôn lưu trữ và phản ánh đúng DB)"""
    user_id = session['user_id']
    username = session.get('username') or f"User_{user_id}"

    accounts_data = []
    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Tài khoản chính trong bảng users
        cursor.execute('''
            SELECT id, username, discord_token, discord_id, discord_username, discord_avatar, 
                   avatar_decoration, banner, bot_enabled, bot_prefix, bot_status
            FROM users WHERE id = ?
        ''', (user_id,))
        u = cursor.fetchone()

        if u:
            main_token = u['discord_token'] or ''
            has_token = bool(main_token and len(main_token) > 20)
            is_alive = userbot_worker.is_running(main_token) if has_token else False
            db_enabled = int(u['bot_enabled'] or 0)
            # Trạng thái logic: Nếu db_enabled=1 thì luôn lưu là đã bật (F5 không mất)
            effective_running = is_alive or (db_enabled == 1)

            details = userbot_worker.get_bot_details(main_token) if is_alive else {}
            accounts_data.append({
                'account_id': 'main',
                'account_type': 'main',
                'label': f"{u['discord_username'] or u['username']} (Tài khoản chính)",
                'username': u['discord_username'] or u['username'],
                'discord_id': u['discord_id'] or '',
                'discord_avatar': u['discord_avatar'] or '',
                'avatar_decoration': u['avatar_decoration'] or '',
                'banner': u['banner'] or '',
                'has_token': has_token,
                'bot_enabled': db_enabled,
                'bot_prefix': '' if u['bot_prefix'] is None else str(u['bot_prefix']),
                'is_running': effective_running,
                'status': 'running' if effective_running else (u['bot_status'] or 'stopped'),
                'details': details
            })

        # 2. Tài khoản phụ trong bảng discord_accounts
        cursor.execute('''
            SELECT id, user_id, token, discord_id, discord_username, discord_avatar, 
                   avatar_decoration, banner, is_active, bot_enabled, bot_prefix, bot_status
            FROM discord_accounts 
            WHERE user_id = ?
            ORDER BY is_active DESC, id DESC
        ''', (user_id,))
        sub_rows = cursor.fetchall()

        for s in sub_rows:
            sub_token = s['token'] or ''
            has_token = bool(sub_token and len(sub_token) > 20)
            is_alive = userbot_worker.is_running(sub_token) if has_token else False
            db_enabled = int(s['bot_enabled'] or 0)
            effective_running = is_alive or (db_enabled == 1)
            details = userbot_worker.get_bot_details(sub_token) if is_alive else {}

            accounts_data.append({
                'account_id': s['id'],
                'account_type': 'sub',
                'label': f"{s['discord_username'] or f'Acc #{s['id']}'} (Phụ)",
                'username': s['discord_username'] or f"Account #{s['id']}",
                'discord_id': s['discord_id'] or '',
                'discord_avatar': s['discord_avatar'] or '',
                'avatar_decoration': s['avatar_decoration'] or '',
                'banner': s['banner'] or '',
                'has_token': has_token,
                'bot_enabled': db_enabled,
                'bot_prefix': '' if s['bot_prefix'] is None else str(s['bot_prefix']),
                'is_running': effective_running,
                'status': 'running' if effective_running else (s['bot_status'] or 'stopped'),
                'is_active': s['is_active'] == 1,
                'details': details
            })

    total_running = sum(1 for a in accounts_data if a['is_running'])
    return jsonify({
        'success': True,
        'username': username,
        'bot_display_name': f"{username}'s Bot",
        'accounts': accounts_data,
        'total_running': total_running,
        'commands_catalog': COMMANDS_CATALOG
    })

@userbot_bp.route('/api/userbot/start', methods=['POST'])
@login_required
def api_userbot_start():
    """Kích hoạt chạy bot cho một tài khoản cụ thể và lưu vĩnh viễn vào DB"""
    user_id = session['user_id']
    data = request.get_json() or {}
    account_id = data.get('account_id', 'main')
    prefix = str(data.get('prefix', '')).strip() or 'm'

    with get_db() as conn:
        cursor = conn.cursor()
        token = ''
        name = ''
        if str(account_id) == 'main':
            cursor.execute('SELECT username, discord_token, discord_username FROM users WHERE id = ?', (user_id,))
            u = cursor.fetchone()
            if u:
                token = u['discord_token']
                name = u['discord_username'] or u['username']
        else:
            cursor.execute('SELECT token, discord_username FROM discord_accounts WHERE id = ? AND user_id = ?', (account_id, user_id))
            s = cursor.fetchone()
            if s:
                token = s['token']
                name = s['discord_username'] or f"Sub-{account_id}"

    if not token or len(token) < 20:
        return jsonify({'success': False, 'message': 'Tài khoản chưa có Discord Token hợp lệ. Hãy nạp Token trước!'}), 400

    track_feature_use(user_id, 'userbot')
    res = userbot_worker.start_bot(user_id, account_id, token, prefix=prefix, name=name)
    return jsonify(res)

@userbot_bp.route('/api/userbot/stop', methods=['POST'])
@login_required
def api_userbot_stop():
    """Tắt UserBot cho một tài khoản cụ thể và lưu trạng thái tắt vào DB"""
    user_id = session['user_id']
    data = request.get_json() or {}
    account_id = data.get('account_id', 'main')

    with get_db() as conn:
        cursor = conn.cursor()
        token = ''
        if str(account_id) == 'main':
            cursor.execute('SELECT discord_token FROM users WHERE id = ?', (user_id,))
            u = cursor.fetchone()
            if u:
                token = u['discord_token']
        else:
            cursor.execute('SELECT token FROM discord_accounts WHERE id = ? AND user_id = ?', (account_id, user_id))
            s = cursor.fetchone()
            if s:
                token = s['token']

    res = userbot_worker.stop_bot(user_id, account_id, token)
    return jsonify(res)

@userbot_bp.route('/api/userbot/toggle', methods=['POST'])
@login_required
def api_userbot_toggle():
    """Toggle 1-click Bật / Tắt UserBot cho tài khoản"""
    user_id = session['user_id']
    data = request.get_json() or {}
    account_id = data.get('account_id', 'main')
    prefix = str(data.get('prefix', '')).strip()

    with get_db() as conn:
        cursor = conn.cursor()
        token = ''
        name = ''
        bot_enabled = 0
        saved_prefix = 'm'
        if str(account_id) == 'main':
            cursor.execute('SELECT username, discord_token, discord_username, bot_enabled, bot_prefix FROM users WHERE id = ?', (user_id,))
            u = cursor.fetchone()
            if u:
                token = u['discord_token']
                name = u['discord_username'] or u['username']
                bot_enabled = int(u['bot_enabled'] or 0)
                saved_prefix = u['bot_prefix'] or 'm'
        else:
            cursor.execute('SELECT token, discord_username, bot_enabled, bot_prefix FROM discord_accounts WHERE id = ? AND user_id = ?', (account_id, user_id))
            s = cursor.fetchone()
            if s:
                token = s['token']
                name = s['discord_username'] or f"Sub-{account_id}"
                bot_enabled = int(s['bot_enabled'] or 0)
                saved_prefix = s['bot_prefix'] or 'm'

    if not token or len(token) < 20:
        return jsonify({'success': False, 'message': 'Chưa nạp Discord Token cho tài khoản này!'}), 400

    use_prefix = prefix if prefix else saved_prefix
    is_live = userbot_worker.is_running(token)

    # Nếu đang chạy -> tắt
    if is_live or bot_enabled == 1:
        res = userbot_worker.stop_bot(user_id, account_id, token)
        res['action'] = 'stopped'
        res['is_running'] = False
        return jsonify(res)
    else:
        track_feature_use(user_id, 'userbot')
        res = userbot_worker.start_bot(user_id, account_id, token, prefix=use_prefix, name=name)
        res['action'] = 'started'
        res['is_running'] = res.get('success', False)
        return jsonify(res)

@userbot_bp.route('/api/userbot/set_prefix', methods=['POST'])
@login_required
def api_userbot_set_prefix():
    """Cập nhật tiền tố (prefix) cho bot"""
    user_id = session['user_id']
    data = request.get_json() or {}
    account_id = data.get('account_id', 'main')
    prefix = str(data.get('prefix', 'm')).strip() or 'm'

    with get_db() as conn:
        cursor = conn.cursor()
        if str(account_id) == 'main':
            cursor.execute('UPDATE users SET bot_prefix = ? WHERE id = ?', (prefix, user_id))
        else:
            cursor.execute('UPDATE discord_accounts SET bot_prefix = ? WHERE id = ? AND user_id = ?', (prefix, account_id, user_id))
        conn.commit()

    return jsonify({'success': True, 'message': f'Đã đổi prefix thành: {prefix}', 'prefix': prefix})

@userbot_bp.route('/api/userbot/logs', methods=['GET'])
@login_required
def api_userbot_logs():
    """Lấy danh sách log hoạt động thời gian thực của bot"""
    with USERBOT_LOG_LOCK:
        logs_copy = list(USERBOT_LOG_BUFFER)
    return jsonify({'success': True, 'logs': logs_copy})

@userbot_bp.route('/api/userbot/commands', methods=['GET'])
def api_userbot_commands():
    """Xem danh mục toàn bộ lệnh và cogs của bot"""
    return jsonify({'success': True, 'catalog': COMMANDS_CATALOG})
