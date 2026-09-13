import sqlite3
from core.config import DB_PATH

def get_db():
    """Mở kết nối SQLite với row_factory và chế độ WAL mode tối ưu tốc độ ghi"""
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn

def init_db():
    """Khởi tạo cấu trúc bảng và tự động migrate schema"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                discord_token TEXT DEFAULT '',
                discord_id TEXT DEFAULT '',
                discord_username TEXT DEFAULT '',
                discord_avatar TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                config TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS discord_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL,
                discord_id TEXT DEFAULT '',
                discord_username TEXT DEFAULT '',
                discord_avatar TEXT DEFAULT '',
                avatar_decoration TEXT DEFAULT '',
                banner TEXT DEFAULT '',
                custom_status TEXT DEFAULT '',
                profile_effect TEXT DEFAULT '',
                is_active INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feature_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                feature_name TEXT NOT NULL,
                use_count INTEGER DEFAULT 1,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        
        # Tự động migrate các cột cho bảng users
        cursor.execute("PRAGMA table_info(users)")
        cols = [r['name'] for r in cursor.fetchall()]
        for col_name in ['discord_token', 'discord_id', 'discord_username', 'discord_avatar', 'config', 'auth_provider', 'avatar_url', 'google_avatar', 'profile_effect']:
            if col_name not in cols:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} TEXT DEFAULT ''")
                except Exception:
                    pass

        # Tự động migrate các cột cho bảng discord_accounts
        cursor.execute("PRAGMA table_info(discord_accounts)")
        d_cols = [r['name'] for r in cursor.fetchall()]
        for col_name in ['avatar_decoration', 'banner', 'custom_status', 'profile_effect', 'is_active']:
            if col_name not in d_cols:
                try:
                    cursor.execute(f"ALTER TABLE discord_accounts ADD COLUMN {col_name} TEXT DEFAULT ''")
                except Exception:
                    pass

        # Tự động migrate token của user vào discord_accounts nếu chưa có
        cursor.execute("SELECT id, discord_token, discord_id, discord_username, discord_avatar FROM users WHERE discord_token != '' AND discord_token IS NOT NULL")
        for u in cursor.fetchall():
            cursor.execute("SELECT id FROM discord_accounts WHERE user_id = ? AND token = ?", (u['id'], u['discord_token']))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO discord_accounts (user_id, token, discord_id, discord_username, discord_avatar, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                ''', (u['id'], u['discord_token'], u['discord_id'], u['discord_username'], u['discord_avatar']))
        conn.commit()

def track_feature_use(user_id: int, feature_name: str):
    """Ghi nhận lượt sử dụng tính năng của người dùng để làm thống kê Dashboard"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, use_count FROM feature_usage WHERE user_id = ? AND feature_name = ?', (user_id, feature_name))
            row = cursor.fetchone()
            if row:
                cursor.execute('UPDATE feature_usage SET use_count = use_count + 1, last_used = CURRENT_TIMESTAMP WHERE id = ?', (row['id'],))
            else:
                cursor.execute('INSERT INTO feature_usage (user_id, feature_name, use_count) VALUES (?, ?, 1)', (user_id, feature_name))
            conn.commit()
    except Exception:
        pass

def get_dashboard_stats(user_id: int) -> dict:
    """Lấy dữ liệu thống kê tổng hợp cho Dashboard của tài khoản"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Đếm số lượng tài khoản Discord token đã lưu
        cursor.execute('SELECT COUNT(*) as total FROM discord_accounts WHERE user_id = ?', (user_id,))
        token_count = cursor.fetchone()['total']

        # Lấy tài khoản Discord đang active
        cursor.execute('SELECT * FROM discord_accounts WHERE user_id = ? AND is_active = 1', (user_id,))
        active_acc = cursor.fetchone()

        # Thống kê tính năng thường dùng
        cursor.execute('SELECT feature_name, use_count FROM feature_usage WHERE user_id = ? ORDER BY use_count DESC LIMIT 5', (user_id,))
        top_features = [dict(r) for r in cursor.fetchall()]

        # Tính tổng số lượt chạy tính năng
        cursor.execute('SELECT SUM(use_count) as total_runs FROM feature_usage WHERE user_id = ?', (user_id,))
        row_sum = cursor.fetchone()
        total_runs = row_sum['total_runs'] if row_sum and row_sum['total_runs'] else 0

    most_used = top_features[0]['feature_name'] if top_features else 'Custom RPC'
    feature_labels = {
        'rpc_custom': 'Custom RPC',
        'rpc_youtube': 'YouTube RPC',
        'rpc_soundcloud': 'SoundCloud RPC',
        'rpc_spotify': 'Spotify RPC',
        'status_custom': 'Custom Status',
        'status_lyric': 'Lyric Status',
        'voice_afk': 'Treo Voice 24/7',
        'auto_quest': 'Auto Quest'
    }

    return {
        'total_tokens': token_count,
        'active_account': dict(active_acc) if active_acc else None,
        'most_used_feature': feature_labels.get(most_used, most_used),
        'total_runs': total_runs,
        'top_features': [{'name': feature_labels.get(f['feature_name'], f['feature_name']), 'count': f['use_count']} for f in top_features]
    }

