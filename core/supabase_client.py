import os
from typing import Optional

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').strip()
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', os.environ.get('SUPABASE_ANON_KEY', '')).strip()

_supabase_client = None

def get_supabase():
    """
    Trả về Supabase Client nếu đã cấu hình SUPABASE_URL và SUPABASE_KEY trong .env.
    Nếu chưa cấu hình, trả về None (hệ thống sẽ dùng SQLite cục bộ làm fallback mượt mà).
    """
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    try:
        from supabase import create_client, Client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return _supabase_client
    except Exception as e:
        print(f"[Supabase] Không thể khởi tạo Supabase client: {e}")
        return None

def is_supabase_enabled() -> bool:
    """Kiểm tra xem Supabase đã sẵn sàng sử dụng hay chưa"""
    return bool(SUPABASE_URL and SUPABASE_KEY)
