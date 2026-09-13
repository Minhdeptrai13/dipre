import os
import uuid
import sqlite3
import json
import requests
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from core.database import get_db
from core.security import clear_failed_attempts, record_failed_attempt, get_client_ip
from core.config import CLOUDFLARE_TURNSTILE_SITE_KEY
from core.registry import registry, SubModule
from modules.auth.helpers import login_required
from modules.captcha.routes import verify_turnstile
from modules.account.discord_effects import resolve_profile_effect
from modules.account.services import fetch_discord_profile

auth_bp = Blueprint('auth', __name__)

DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '')
DISCORD_CLIENT_SECRET = os.environ.get('DISCORD_CLIENT_SECRET', '')

def get_discord_redirect_uri():
    uri = os.environ.get('DISCORD_REDIRECT_URI') or url_for('auth_discord_callback', _external=True)
    if uri.startswith('http://') and ('onrender.com' in uri or request.headers.get('X-Forwarded-Proto') == 'https'):
        uri = 'https://' + uri[7:]
    return uri

GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')

def get_google_redirect_uri():
    uri = os.environ.get('GOOGLE_REDIRECT_URI') or url_for('auth_google_callback', _external=True)
    if uri.startswith('http://') and ('onrender.com' in uri or request.headers.get('X-Forwarded-Proto') == 'https'):
        uri = 'https://' + uri[7:]
    return uri

def get_avatar_info(username: str, avatar_url: str = '', auth_provider: str = 'local') -> dict:
    """Tự động sinh cấu trúc Avatar: nếu có link ảnh thì dùng ảnh, nếu chưa có thì tạo Initials + Gradient kiểu Zalo"""
    if avatar_url and avatar_url.strip():
        return {
            'type': 'image',
            'url': avatar_url.strip(),
            'initials': '',
            'gradient': ''
        }
    
    # Tính toán Initials Zalo-style (1 hoặc 2 chữ cái đầu)
    clean_name = (username or 'User').strip()
    words = [w for w in clean_name.replace('_', ' ').replace('-', ' ').split() if w]
    if len(words) >= 2:
        initials = (words[0][0] + words[-1][0]).upper()
    elif len(words) == 1 and len(words[0]) >= 2:
        initials = words[0][:2].upper()
    elif len(words) == 1:
        initials = words[0][0].upper()
    else:
        initials = 'D'
    
    # Bảng màu Luxury Cyber Gradient
    gradients = [
        'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)', # Indigo Purple
        'linear-gradient(135deg, #0284c7 0%, #2563eb 100%)', # Sky Blue
        'linear-gradient(135deg, #059669 0%, #0d9488 100%)', # Emerald Teal
        'linear-gradient(135deg, #e11d48 0%, #be123c 100%)', # Rose Crimson
        'linear-gradient(135deg, #9333ea 0%, #c026d3 100%)', # Violet Fuchsia
        'linear-gradient(135deg, #d97706 0%, #c2410c 100%)', # Amber Orange
        'linear-gradient(135deg, #5865f2 0%, #7289da 100%)', # Discord Blurple
    ]
    color_idx = abs(hash(clean_name)) % len(gradients)
    return {
        'type': 'initials',
        'url': '',
        'initials': initials,
        'gradient': gradients[color_idx]
    }

@auth_bp.route('/')
@login_required
def index():
    user_id = session['user_id']
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT username, discord_token, discord_id, discord_username, discord_avatar, avatar_url, google_avatar, auth_provider, profile_effect, avatar_decoration, banner, badges, custom_status, bio FROM users WHERE id = ?', (user_id,))
        u = cursor.fetchone()
        cursor.execute('SELECT avatar_decoration, banner, profile_effect, discord_username, discord_avatar, custom_status FROM discord_accounts WHERE user_id = ? AND is_active = 1 LIMIT 1', (user_id,))
        acc = cursor.fetchone()
        cursor.execute('SELECT COUNT(*) as cnt FROM discord_accounts WHERE user_id = ?', (user_id,))
        acc_cnt_row = cursor.fetchone()
        sub_count = acc_cnt_row['cnt'] if acc_cnt_row else 0
    
    username = u['username'] if u else session.get('username', 'User')
    has_token = bool((u and u['discord_token'] and len(u['discord_token']) > 20) or acc)
    d_name = (acc['discord_username'] if (acc and acc['discord_username']) else (u['discord_username'] if (u and u['discord_username']) else None))
    d_avatar = (acc['discord_avatar'] if (acc and acc['discord_avatar']) else (u['discord_avatar'] if (u and u['discord_avatar']) else None))
    auth_prov = (u['auth_provider'] if u and u['auth_provider'] else 'local')
    
    raw_avatar = (u['avatar_url'] or u['google_avatar'] or u['discord_avatar'] or '').strip() if u else ''
    avatar_info = get_avatar_info(username, raw_avatar, auth_prov)
    
    avatar_decoration = (acc['avatar_decoration'] if (acc and acc['avatar_decoration']) else (u['avatar_decoration'] if (u and u['avatar_decoration']) else None))
    banner = (acc['banner'] if (acc and acc['banner']) else (u['banner'] if (u and u['banner']) else None))
    profile_effect = (acc['profile_effect'] if (acc and acc['profile_effect']) else (u['profile_effect'] if (u and u['profile_effect']) else None))
    custom_status = (acc['custom_status'] if (acc and acc['custom_status']) else (u['custom_status'] if (u and u['custom_status']) else 'nắng biển?'))
    bio = (u['bio'] if (u and u['bio']) else '')
    
    # Lấy badges list
    badges_list = []
    if u and u['badges']:
        try:
            badges_list = json.loads(u['badges']) if isinstance(u['badges'], str) else u['badges']
        except Exception:
            badges_list = []

    # Nếu chưa có profile_effect hoặc avatar_decoration mà có discord_id, thử sync realtime
    d_id = u['discord_id'] if u else None
    showcase_token = os.environ.get('DISCORD_SHOWCASE_TOKEN', '')
    if d_id and showcase_token and (not profile_effect or not avatar_decoration):
        try:
            p_live = fetch_discord_profile(showcase_token, d_id)
            if p_live:
                if not profile_effect and p_live.get('profile_effect'):
                    profile_effect = p_live['profile_effect']
                if not avatar_decoration and p_live.get('decoration'):
                    avatar_decoration = p_live['decoration']
                if not banner and p_live.get('banner'):
                    banner = p_live['banner']
                if not badges_list and p_live.get('badges'):
                    badges_list = p_live['badges']
                if not bio and p_live.get('bio'):
                    bio = p_live['bio']
                # Cập nhật ngược lại vào DB
                with get_db() as conn:
                    c = conn.cursor()
                    c.execute('UPDATE users SET profile_effect = ?, avatar_decoration = ?, banner = ?, badges = ?, bio = ? WHERE id = ?',
                              (profile_effect or '', avatar_decoration or '', banner or '', json.dumps(badges_list, ensure_ascii=False), bio, user_id))
                    conn.commit()
        except Exception:
            pass

    profile_effect_data = resolve_profile_effect(profile_effect) if profile_effect else None

    return render_template('index.html',
                           username=username,
                           has_token=has_token,
                           discord_username=d_name,
                           discord_avatar=d_avatar,
                           auth_provider=auth_prov,
                           avatar_url=raw_avatar,
                           avatar_info=avatar_info,
                           avatar_decoration=avatar_decoration,
                           banner=banner,
                           profile_effect=profile_effect,
                           profile_effect_data=profile_effect_data,
                           badges=badges_list,
                           custom_status=custom_status,
                           bio=bio,
                           sub_accounts_count=sub_count)

@auth_bp.route('/api/live/status')
@login_required
def api_live_status():
    """API realtime trả về trạng thái người dùng & hệ thống không delay"""
    user_id = session.get('user_id')
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT username, discord_token, discord_username, discord_avatar, avatar_url, auth_provider, avatar_decoration, banner, profile_effect, badges, custom_status, bio FROM users WHERE id = ?', (user_id,))
        u = cursor.fetchone()
        cursor.execute('SELECT avatar_decoration, banner, profile_effect, discord_username, discord_avatar, custom_status FROM discord_accounts WHERE user_id = ? AND is_active = 1 LIMIT 1', (user_id,))
        acc = cursor.fetchone()
    if not u:
        return jsonify({'status': 'unauthorized'}), 401
    
    raw_avatar = (u['avatar_url'] or u['discord_avatar'] or '').strip()
    avatar_info = get_avatar_info(u['username'], raw_avatar, u['auth_provider'] or 'local')
    has_token = bool((u['discord_token'] and len(u['discord_token']) > 20) or acc)

    avatar_decoration = (acc['avatar_decoration'] if (acc and acc['avatar_decoration']) else (u['avatar_decoration'] if u['avatar_decoration'] else ''))
    banner = (acc['banner'] if (acc and acc['banner']) else (u['banner'] if u['banner'] else ''))
    profile_effect = (acc['profile_effect'] if (acc and acc['profile_effect']) else (u['profile_effect'] if u['profile_effect'] else ''))
    custom_status = (acc['custom_status'] if (acc and acc['custom_status']) else (u['custom_status'] if u['custom_status'] else 'nắng biển?'))
    bio = u['bio'] or ''

    badges_list = []
    if u['badges']:
        try:
            badges_list = json.loads(u['badges']) if isinstance(u['badges'], str) else u['badges']
        except Exception:
            badges_list = []

    profile_effect_data = resolve_profile_effect(profile_effect) if profile_effect else None
    
    return jsonify({
        'status': 'ok',
        'user': {
            'id': user_id,
            'username': u['username'],
            'auth_provider': u['auth_provider'] or 'local',
            'has_token': has_token,
            'discord_username': (acc['discord_username'] if acc and acc['discord_username'] else u['discord_username']) or '',
            'avatar': avatar_info,
            'avatar_decoration': avatar_decoration,
            'banner': banner,
            'profile_effect': profile_effect,
            'profile_effect_data': profile_effect_data,
            'badges': badges_list,
            'custom_status': custom_status,
            'bio': bio
        }
    })

@auth_bp.route('/api/user/profile/update', methods=['POST'])
@login_required
def api_user_profile_update():
    """Cập nhật tên và avatar của tài khoản DIPRE Studio độc lập không ảnh hưởng OAuth2"""
    user_id = session['user_id']
    data = request.get_json() or {}
    new_username = data.get('username', '').strip()
    new_avatar_url = data.get('avatar_url', '').strip()

    if not new_username:
        return jsonify({'success': False, 'message': 'Tên tài khoản không được để trống'}), 400

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE username = ? AND id != ?', (new_username, user_id))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': 'Tên tài khoản này đã được sử dụng bởi người khác'}), 400
        
        cursor.execute('UPDATE users SET username = ?, avatar_url = ? WHERE id = ?',
                       (new_username, new_avatar_url, user_id))
        conn.commit()

    session['username'] = new_username
    return jsonify({
        'success': True,
        'message': 'Đã cập nhật hồ sơ DIPRE thành công!',
        'username': new_username,
        'avatar_url': new_avatar_url
    })

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        cf_token = request.form.get('cf-turnstile-response') or request.form.get('turnstile_token')
        client_ip = get_client_ip()
        is_verified = session.get('captcha_verified', False) or (cf_token and verify_turnstile(cf_token, client_ip))
        
        if not is_verified:
            flash('Vui lòng hoàn thành xác thực Cloudflare Turnstile trước khi đăng nhập.', 'error')
            return redirect(url_for('login'))
        session['captcha_verified'] = False
        session['slide_verified'] = False

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            flash('Vui lòng nhập đầy đủ tên tài khoản và mật khẩu.', 'error')
            return redirect(url_for('login'))
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()
        if user and check_password_hash(user['password_hash'], password):
            clear_failed_attempts(get_client_ip())
            session['user_id'] = user['id']
            session['username'] = user['username']
            if user['discord_token']:
                session['discord_token'] = user['discord_token']
                session['discord_username'] = user['discord_username']
                session['discord_avatar'] = user['discord_avatar']
            flash(f'Chào mừng trở lại, {username}!', 'success')
            return redirect(url_for('index'))
        else:
            record_failed_attempt(get_client_ip())
            flash('Tên đăng nhập hoặc mật khẩu không chính xác.', 'error')
            return redirect(url_for('login'))
            
    # Lấy thông tin Showcase Profile trực tiếp từ Discord API nếu có Token
    showcase_token = (
        os.environ.get('DISCORD_SHOWCASE_TOKEN') or 
        os.environ.get('DISCORD_TOKEN') or 
        os.environ.get('DISCORD_BOT_TOKEN') or ''
    ).strip()
    
    # Nếu chưa có trong .env, thử tìm token đầu tiên trong database để tự động fetch
    if not showcase_token:
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT token FROM discord_accounts WHERE token IS NOT NULL AND length(token) > 20 LIMIT 1')
                t_row = cursor.fetchone()
                if t_row and t_row['token']:
                    showcase_token = t_row['token']
                else:
                    cursor.execute('SELECT discord_token FROM users WHERE discord_token IS NOT NULL AND length(discord_token) > 20 LIMIT 1')
                    u_row = cursor.fetchone()
                    if u_row and u_row['discord_token']:
                        showcase_token = u_row['discord_token']
        except Exception:
            pass

    showcase_profile = None
    if showcase_token:
        try:
            from modules.account.services import fetch_discord_profile
            # Target ID của Minh: 1412818296033775707
            showcase_profile = fetch_discord_profile(showcase_token, target_user_id='1412818296033775707')
        except Exception as e:
            print(f"[SHOWCASE ERROR] Failed to fetch Discord profile: {e}")

    return render_template('login.html', 
                           turnstile_site_key=CLOUDFLARE_TURNSTILE_SITE_KEY,
                           showcase=showcase_profile)

@auth_bp.route('/register', methods=['POST'])
def register():
    cf_token = request.form.get('cf-turnstile-response') or request.form.get('turnstile_token')
    client_ip = get_client_ip()
    is_verified = session.get('captcha_verified', False) or (cf_token and verify_turnstile(cf_token, client_ip))
    
    if not is_verified:
        flash('Vui lòng hoàn thành xác thực Cloudflare Turnstile trước khi đăng ký.', 'error')
        return redirect(url_for('login'))
    session['slide_verified'] = False
    session['captcha_verified'] = False

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()
    if not username or not password:
        flash('Vui lòng điền đầy đủ các thông tin đăng ký.', 'error')
        return redirect(url_for('login'))
    if len(username) < 3:
        flash('Tên đăng nhập phải có tối thiểu 3 ký tự.', 'error')
        return redirect(url_for('login'))
    if password != confirm_password:
        flash('Mật khẩu xác nhận không khớp.', 'error')
        return redirect(url_for('login'))
    password_hash = generate_password_hash(password)
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO users (username, password_hash, auth_provider, avatar_url) VALUES (?, ?, ?, ?)', (username, password_hash, 'local', ''))
            conn.commit()
            clear_failed_attempts(get_client_ip())
        flash('Tạo tài khoản thành công! Hãy đăng nhập ngay bây giờ.', 'success')
    except sqlite3.IntegrityError:
        record_failed_attempt(get_client_ip())
        flash('Tên đăng nhập này đã được sử dụng. Vui lòng chọn tên khác.', 'error')
    return redirect(url_for('login'))

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Đã đăng xuất thành công.', 'info')
    return redirect(url_for('login'))

@auth_bp.route('/auth/discord')
def auth_discord_redirect():
    redirect_uri = get_discord_redirect_uri()
    discord_auth_url = (
        f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={requests.utils.quote(redirect_uri)}&response_type=code&scope=identify%20email"
    )
    return redirect(discord_auth_url)

@auth_bp.route('/auth/discord/callback')
def auth_discord_callback():
    code = request.args.get('code')
    if not code:
        flash('Xác thực Discord OAuth2 không thành công.', 'error')
        return redirect(url_for('login'))
    try:
        redirect_uri = get_discord_redirect_uri()
        data = {
            'client_id': DISCORD_CLIENT_ID,
            'client_secret': DISCORD_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        r = requests.post('https://discord.com/api/oauth2/token', data=data, headers=headers, timeout=10)
        tokens = r.json()
        access_token = tokens.get('access_token')
        if not access_token:
            flash('Không thể lấy Discord Access Token qua OAuth2.', 'error')
            return redirect(url_for('login'))

        u_res = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {access_token}'}, timeout=8)
        u_data = u_res.json()
        d_id = str(u_data.get('id'))
        d_username = u_data.get('global_name') or u_data.get('username') or 'Discord User'
        avatar_hash = u_data.get('avatar')
        ext = 'gif' if (avatar_hash and avatar_hash.startswith('a_')) else 'png'
        avatar_url = f"https://cdn.discordapp.com/avatars/{d_id}/{avatar_hash}.{ext}?size=256" if avatar_hash else "https://cdn.discordapp.com/embed/avatars/0.png"

        decor_data = u_data.get('avatar_decoration_data')
        avatar_decoration = f"https://cdn.discordapp.com/avatar-decoration-presets/{decor_data['asset']}.png?size=256&passthrough=true" if (decor_data and decor_data.get('asset')) else ''

        banner_hash = u_data.get('banner')
        b_ext = 'gif' if (banner_hash and banner_hash.startswith('a_')) else 'png'
        banner_url = f"https://cdn.discordapp.com/banners/{d_id}/{banner_hash}.{b_ext}?size=600" if banner_hash else (f"#{u_data.get('accent_color'):06x}" if u_data.get('accent_color') else '')

        profile_effect = ''
        bio = u_data.get('bio', '')
        custom_status = 'nắng biển?'
        badges = []

        showcase_token = os.environ.get('DISCORD_SHOWCASE_TOKEN', '')
        if showcase_token:
            try:
                p_info = fetch_discord_profile(showcase_token, d_id)
                if p_info:
                    if p_info.get('profile_effect'):
                        profile_effect = p_info['profile_effect']
                    if p_info.get('decoration') and not avatar_decoration:
                        avatar_decoration = p_info['decoration']
                    if p_info.get('banner') and not banner_url:
                        banner_url = p_info['banner']
                    if p_info.get('badges'):
                        badges = p_info['badges']
                    if p_info.get('bio'):
                        bio = p_info['bio']
                    if p_info.get('custom_status'):
                        custom_status = p_info['custom_status']
            except Exception:
                pass

        if not badges:
            flags = u_data.get('flags', 0) or u_data.get('public_flags', 0)
            if flags & (1 << 8):
                badges.append({'name': 'HypeSquad Balance', 'icon': 'https://cdn.discordapp.com/badge-icons/3aa41de486fa12454c3761e8e223442e.png?size=64'})
            if flags & (1 << 22):
                badges.append({'name': 'Active Developer', 'icon': 'https://cdn.discordapp.com/badge-icons/6bdc42827b30f498e4a0713f64455d80.png?size=64'})

        badges_json = json.dumps(badges, ensure_ascii=False)

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE discord_id = ? OR username = ?', (d_id, d_username))
            user = cursor.fetchone()
            if not user:
                pwd_dummy = generate_password_hash(uuid.uuid4().hex)
                cursor.execute('''INSERT INTO users (username, password_hash, discord_id, discord_username, discord_avatar, avatar_url, auth_provider, avatar_decoration, banner, profile_effect, badges, bio, custom_status) 
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                               (d_username, pwd_dummy, d_id, d_username, avatar_url, avatar_url, 'discord', avatar_decoration, banner_url, profile_effect, badges_json, bio, custom_status))
                user_id = cursor.lastrowid
            else:
                user_id = user['id']
                cursor.execute('''UPDATE users SET discord_id = ?, discord_username = ?, discord_avatar = ?, avatar_url = ?, auth_provider = ?, avatar_decoration = ?, banner = ?, profile_effect = ?, badges = ?, bio = ?, custom_status = ? 
                                  WHERE id = ?''',
                               (d_id, d_username, avatar_url, avatar_url, 'discord', avatar_decoration, banner_url, profile_effect, badges_json, bio, custom_status, user_id))
            
            # Cập nhật hoặc lưu vào danh sách discord_accounts
            cursor.execute('SELECT id FROM discord_accounts WHERE user_id = ? AND (discord_id = ? OR token = ?)', (user_id, d_id, access_token))
            d_acc = cursor.fetchone()
            if not d_acc:
                cursor.execute('''INSERT INTO discord_accounts (user_id, token, discord_id, discord_username, discord_avatar, avatar_decoration, banner, profile_effect, custom_status, is_active)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)''',
                               (user_id, access_token, d_id, d_username, avatar_url, avatar_decoration, banner_url, profile_effect, custom_status))
            else:
                cursor.execute('''UPDATE discord_accounts SET discord_username = ?, discord_avatar = ?, avatar_decoration = ?, banner = ?, profile_effect = ?, custom_status = ?, is_active = 1
                                  WHERE id = ?''',
                               (d_username, avatar_url, avatar_decoration, banner_url, profile_effect, custom_status, d_acc['id']))
            conn.commit()

        session['user_id'] = user_id
        session['username'] = d_username
        session['discord_username'] = d_username
        session['discord_avatar'] = avatar_url
        session['discord_avatar_decoration'] = avatar_decoration
        session['discord_banner'] = banner_url
        session['discord_profile_effect'] = profile_effect
        clear_failed_attempts(get_client_ip())
        flash(f'Đăng nhập Discord OAuth2 thành công! Chào mừng {d_username}.', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Lỗi xử lý Discord OAuth2: {str(e)}', 'error')
        return redirect(url_for('login'))

@auth_bp.route('/auth/google')
def auth_google_redirect():
    redirect_uri = get_google_redirect_uri()
    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={requests.utils.quote(redirect_uri)}&response_type=code&scope=openid%20profile%20email"
        f"&prompt=select_account"
    )
    return redirect(google_auth_url)

@auth_bp.route('/auth/google/callback')
def auth_google_callback():
    code = request.args.get('code')
    if not code:
        flash('Xác thực Google OAuth2 không thành công.', 'error')
        return redirect(url_for('login'))
    try:
        redirect_uri = get_google_redirect_uri()
        token_data = {
            'code': code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }
        tr = requests.post('https://oauth2.googleapis.com/token', data=token_data, timeout=10)
        tokens = tr.json()
        access_token = tokens.get('access_token')
        if not access_token:
            flash('Không thể lấy Access Token từ Google.', 'error')
            return redirect(url_for('login'))

        u_res = requests.get('https://www.googleapis.com/oauth2/v2/userinfo', headers={'Authorization': f'Bearer {access_token}'}, timeout=8)
        u_data = u_res.json()
        email = u_data.get('email', '').strip()
        name = u_data.get('name') or (email.split('@')[0] if email else 'GoogleUser')
        picture = u_data.get('picture', '').strip()

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE username = ?', (name,))
            user = cursor.fetchone()
            if not user:
                pwd_dummy = generate_password_hash(uuid.uuid4().hex)
                cursor.execute('INSERT INTO users (username, password_hash, avatar_url, google_avatar, auth_provider) VALUES (?, ?, ?, ?, ?)',
                               (name, pwd_dummy, picture, picture, 'google'))
                user_id = cursor.lastrowid
            else:
                user_id = user['id']
                cursor.execute('UPDATE users SET avatar_url = ?, google_avatar = ?, auth_provider = ? WHERE id = ?',
                               (picture, picture, 'google', user_id))
            conn.commit()

        session['user_id'] = user_id
        session['username'] = name
        clear_failed_attempts(get_client_ip())
        flash(f'Đăng nhập Google thành công! Chào mừng {name}.', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Lỗi xử lý Google OAuth2: {str(e)}', 'error')
        return redirect(url_for('login'))

@auth_bp.route('/auth/mock/<provider>')
def auth_oauth2_mock(provider):
    return render_template('oauth_mock.html', provider=provider)

@auth_bp.route('/auth/mock/confirm', methods=['POST'])
def auth_oauth2_mock_confirm():
    provider = request.form.get('provider', 'discord')
    username = request.form.get('username', '').strip() or ('DiscordUser' if provider == 'discord' else 'GoogleUser')
    
    with get_db() as conn:
        cursor = conn.cursor()
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
    flash(f'Đăng nhập thành công qua {provider.capitalize()} OAuth2! Chào mừng {username}.', 'success')
    return redirect(url_for('index'))

def register_auth_endpoints(app):
    """Đăng ký các alias endpoints để tương thích hoàn toàn với url_for('login'), url_for('index'),... trong templates"""
    app.add_url_rule('/', endpoint='index', view_func=index)
    app.add_url_rule('/login', endpoint='login', view_func=login, methods=['GET', 'POST'])
    app.add_url_rule('/register', endpoint='register', view_func=register, methods=['POST'])
    app.add_url_rule('/logout', endpoint='logout', view_func=logout)
    app.add_url_rule('/auth/discord/callback', endpoint='auth_discord_callback', view_func=auth_discord_callback)
    app.add_url_rule('/auth/google/callback', endpoint='auth_google_callback', view_func=auth_google_callback)
    app.add_url_rule('/api/live/status', endpoint='api_live_status', view_func=api_live_status)

# Đăng ký tiểu mục Auth vào Mục Lớn Account & Auth trong Core Registry
registry.register_module(SubModule(
    key='auth',
    category_key='account',
    title='Authentication & OAuth2 Engine',
    blueprint=auth_bp,
    init_handler=register_auth_endpoints
))
