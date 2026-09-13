import json
from flask import Blueprint, request, jsonify, session
from core.database import get_db
from core.supabase_client import get_supabase
from modules.auth.helpers import login_required
from core.registry import registry, SubModule

template_bp = Blueprint('template', __name__)

@template_bp.route('/api/templates', methods=['GET'])
def get_templates():
    """Lấy danh sách các template RPC công khai từ Diễn đàn (Supabase / SQLite)"""
    sort_by = request.args.get('sort', 'newest')  # newest, popular, uses
    tag = request.args.get('tag', '').strip().lower()
    search = request.args.get('search', '').strip().lower()
    
    supabase = get_supabase()
    if supabase:
        try:
            query = supabase.table('rpc_templates').select('*').eq('is_public', True)
            if tag:
                query = query.contains('tags', [tag])
            if search:
                query = query.ilike('title', f'%{search}%')
            
            if sort_by == 'popular':
                query = query.order('likes_count', desc=True)
            elif sort_by == 'uses':
                query = query.order('uses_count', desc=True)
            else:
                query = query.order('created_at', desc=True)
                
            res = query.limit(50).execute()
            return jsonify({'success': True, 'templates': res.data or [], 'source': 'supabase'})
        except Exception as e:
            print(f"[Supabase Templates] Error: {e}, falling back to SQLite")

    # SQLite fallback
    with get_db() as conn:
        cursor = conn.cursor()
        sql = 'SELECT * FROM rpc_templates WHERE is_public = 1'
        params = []
        
        if search:
            sql += ' AND (LOWER(title) LIKE ? OR LOWER(description) LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%'])
            
        if sort_by == 'popular':
            sql += ' ORDER BY likes_count DESC'
        elif sort_by == 'uses':
            sql += ' ORDER BY uses_count DESC'
        else:
            sql += ' ORDER BY created_at DESC'
            
        sql += ' LIMIT 50'
        cursor.execute(sql, params)
        rows = [dict(r) for r in cursor.fetchall()]
        
        for r in rows:
            try:
                r['tags'] = json.loads(r['tags']) if isinstance(r['tags'], str) else r['tags']
                r['rpc_config'] = json.loads(r['rpc_config']) if isinstance(r['rpc_config'], str) else r['rpc_config']
            except Exception:
                pass
                
        # Filter tag in-memory for SQLite if requested
        if tag:
            rows = [r for r in rows if tag in [t.lower() for t in r.get('tags', [])]]
            
        return jsonify({'success': True, 'templates': rows, 'source': 'sqlite'})


@template_bp.route('/api/templates/create', methods=['POST'])
@login_required
def create_template():
    """Tạo hoặc chia sẻ một mẫu RPC mới lên diễn đàn hoặc lưu vào kho cá nhân"""
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    if not title:
        return jsonify({'success': False, 'message': 'Vui lòng nhập tiêu đề template'}), 400
        
    description = data.get('description', '').strip()
    tags = data.get('tags', [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',') if t.strip()]
        
    rpc_config = data.get('rpc_config', {})
    preview_image_url = data.get('preview_image_url', '').strip()
    is_public = 1 if data.get('is_public', True) else 0
    
    user_id = session['user_id']
    username = session.get('username', 'Anonymous')
    
    supabase = get_supabase()
    if supabase:
        try:
            insert_data = {
                'title': title,
                'description': description,
                'tags': tags,
                'rpc_config': rpc_config,
                'preview_image_url': preview_image_url,
                'is_public': bool(is_public),
                'likes_count': 0,
                'uses_count': 0
            }
            res = supabase.table('rpc_templates').insert(insert_data).execute()
            if res.data:
                return jsonify({'success': True, 'template': res.data[0], 'message': 'Đã tạo template thành công trên Supabase!'})
        except Exception as e:
            print(f"[Supabase Create Template] Error: {e}, falling back to SQLite")

    # SQLite
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO rpc_templates (author_id, author_name, title, description, tags, rpc_config, preview_image_url, is_public)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, title, description, json.dumps(tags, ensure_ascii=False), json.dumps(rpc_config, ensure_ascii=False), preview_image_url, is_public))
        template_id = cursor.lastrowid
        conn.commit()
        
    return jsonify({'success': True, 'id': template_id, 'message': 'Đã lưu template thành công!'})


@template_bp.route('/api/templates/<int:template_id>/use', methods=['POST'])
def use_template(template_id):
    """Tăng số lượt dùng (uses_count) khi người dùng áp dụng template"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE rpc_templates SET uses_count = uses_count + 1 WHERE id = ?', (template_id,))
        cursor.execute('SELECT * FROM rpc_templates WHERE id = ?', (template_id,))
        row = cursor.fetchone()
        conn.commit()
        
    if not row:
        return jsonify({'success': False, 'message': 'Template không tồn tại'}), 404
        
    tpl = dict(row)
    try:
        tpl['tags'] = json.loads(tpl['tags']) if isinstance(tpl['tags'], str) else tpl['tags']
        tpl['rpc_config'] = json.loads(tpl['rpc_config']) if isinstance(tpl['rpc_config'], str) else tpl['rpc_config']
    except Exception:
        pass
        
    return jsonify({'success': True, 'template': tpl})


@template_bp.route('/api/templates/<int:template_id>/like', methods=['POST'])
@login_required
def toggle_like(template_id):
    """Thích / Bỏ thích một template"""
    user_id = session['user_id']
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM template_favorites WHERE user_id = ? AND template_id = ?', (user_id, template_id))
        liked = cursor.fetchone()
        if liked:
            cursor.execute('DELETE FROM template_favorites WHERE user_id = ? AND template_id = ?', (user_id, template_id))
            cursor.execute('UPDATE rpc_templates SET likes_count = MAX(0, likes_count - 1) WHERE id = ?', (template_id,))
            is_liked = False
        else:
            cursor.execute('INSERT INTO template_favorites (user_id, template_id) VALUES (?, ?)', (user_id, template_id))
            cursor.execute('UPDATE rpc_templates SET likes_count = likes_count + 1 WHERE id = ?', (template_id,))
            is_liked = True
        conn.commit()
        
    return jsonify({'success': True, 'liked': is_liked})


@template_bp.route('/api/portal/apps', methods=['GET'])
@login_required
def get_user_bots():
    """Lấy danh sách các Bot Application được lưu của tài khoản người dùng"""
    user_id = session['user_id']
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM discord_bots WHERE user_id = ? ORDER BY id DESC', (user_id,))
        rows = [dict(r) for r in cursor.fetchall()]
        
    # Mặc định thêm các bot thông dụng nếu chưa có bot nào
    if not rows:
        default_apps = [
            {'app_id': '1118182981329244241', 'bot_name': 'DIPRE Studio RPC', 'bot_avatar_url': 'https://cdn.discordapp.com/app-icons/1118182981329244241/a_123.png'},
            {'app_id': '383226320970055681', 'bot_name': 'Visual Studio Code', 'bot_avatar_url': 'https://cdn.discordapp.com/app-icons/383226320970055681/a_vsc.png'},
            {'app_id': '438122941394649088', 'bot_name': 'Spotify Listening', 'bot_avatar_url': 'https://cdn.discordapp.com/app-icons/438122941394649088/a_spotify.png'}
        ]
        return jsonify({'success': True, 'bots': default_apps, 'is_default': True})
        
    return jsonify({'success': True, 'bots': rows, 'is_default': False})


@template_bp.route('/api/portal/apps/add', methods=['POST'])
@login_required
def add_user_bot():
    """Thêm một Discord Bot / Application ID mới"""
    data = request.get_json() or {}
    app_id = data.get('app_id', '').strip()
    bot_name = data.get('bot_name', '').strip() or 'Custom Bot App'
    bot_avatar_url = data.get('bot_avatar_url', '').strip()
    
    if not app_id or not app_id.isdigit():
        return jsonify({'success': False, 'message': 'Application ID không hợp lệ'}), 400
        
    user_id = session['user_id']
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO discord_bots (user_id, app_id, bot_name, bot_avatar_url)
            VALUES (?, ?, ?, ?)
        ''', (user_id, app_id, bot_name, bot_avatar_url))
        conn.commit()
        
    return jsonify({'success': True, 'message': 'Đã lưu Application Bot thành công!'})


def init_module():
    """Đăng ký blueprint với registry"""
    return SubModule(
        key="theme_rpc_hub",
        category_key="rpc",
        title="Theme RPC Hub & Community Templates",
        blueprint=template_bp
    )

registry.register_module(init_module())
