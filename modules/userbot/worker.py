import os
import sys
import time
import asyncio
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List

from core.logger import log_event, userbot_log
from core.database import get_db

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

class UserBotWorker:
    """Quản lý toàn bộ tiến trình và vòng đời các UserBot Discord chạy song song trong Dipre."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UserBotWorker, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self._initialized = True
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._bot_states: Dict[str, Dict[str, Any]] = {}
        self._start_event_loop()

    def _start_event_loop(self):
        """Khởi động luồng nền vĩnh viễn chứa Asyncio Event Loop cho UserBot"""
        def _runner():
            asyncio.set_event_loop(asyncio.new_event_loop())
            self._loop = asyncio.get_event_loop()
            self._loop.run_forever()

        self._thread = threading.Thread(target=_runner, daemon=True, name="UserBot-EventLoop")
        self._thread.start()
        while self._loop is None:
            time.sleep(0.05)
        userbot_log("Luồng điều khiển UserBot Async Engine đã sẵn sàng.", "info")

    def run_coro(self, coro, timeout: float = 35.0):
        """Chạy an toàn một coroutine trong Event Loop của UserBot"""
        if not self._loop or not self._loop.is_running():
            raise RuntimeError("UserBot Event Loop chưa được khởi chạy")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def is_running(self, token: str) -> bool:
        t = (token or "").strip()
        if not t:
            return False
        try:
            from apps.user_discord.core import runtime
            return runtime.is_live(t)
        except Exception:
            return False

    def get_bot_details(self, token: str) -> Dict[str, Any]:
        t = (token or "").strip()
        if not t:
            return {'is_running': False, 'status': 'stopped'}
        try:
            from apps.user_discord.core import runtime
            is_live = runtime.is_live(t)
            if not is_live:
                return {'is_running': False, 'status': 'stopped'}
            bot = runtime.get_live(t)
            if not bot:
                return {'is_running': True, 'status': 'connecting'}

            user = getattr(bot, 'user', None)
            username = str(user) if user else "Discord User"
            uid = str(user.id) if user else ""
            avatar_url = str(user.display_avatar.url) if user and hasattr(user, 'display_avatar') else ""
            guilds_count = len(getattr(bot, 'guilds', []))
            cogs_count = len(getattr(bot, 'cogs', []))
            cached_prefix = getattr(bot, '_saved_prefix', 'm')
            
            return {
                'is_running': True,
                'status': 'running',
                'username': username,
                'user_id': uid,
                'avatar_url': avatar_url,
                'guilds_count': guilds_count,
                'cogs_count': cogs_count,
                'prefix': cached_prefix
            }
        except Exception as e:
            return {'is_running': False, 'status': 'error', 'error': str(e)}

    def start_bot(self, user_id: int, account_id: Any, token: str, prefix: str = "m", name: str = "") -> Dict[str, Any]:
        """Kích hoạt chạy UserBot và lưu vĩnh viễn trạng thái vào cơ sở dữ liệu"""
        token = (token or "").strip()
        if not token:
            return {'success': False, 'message': 'Token không hợp lệ hoặc để trống'}

        prefix = "" if prefix is None else str(prefix).strip()
        if prefix.lower() in ("none", "null", "empty", "không", "khong"):
            prefix = ""
        name = name or f"UserBot-{account_id}"

        # Kiểm tra nếu đang chạy rồi thì chỉ cập nhật prefix nếu cần
        if self.is_running(token):
            self._persist_status(user_id, account_id, enabled=1, prefix=prefix, status='running')
            return {'success': True, 'message': f'Bot {name} đã và đang chạy sẵn!', 'status': 'running'}

        try:
            from apps.user_discord.core import runtime

            userbot_log(f"Đang khởi động UserBot '{name}' với prefix '{prefix}'...", "info")

            async def _do_spawn():
                ok, bot, msg = await runtime.spawn(token, prefix=prefix, name=name, timeout=25.0)
                return ok, bot, msg

            ok, bot, msg = self.run_coro(_do_spawn(), timeout=30.0)
            if ok:
                self._persist_status(user_id, account_id, enabled=1, prefix=prefix, status='running')
                userbot_log(f"UserBot '{name}' đã KÍCH HOẠT THÀNH CÔNG! (Prefix: `{prefix}`)", "success")
                log_event(f"Đã kích hoạt UserBot cho tài khoản {name} (Prefix: {prefix})", "success")
                return {
                    'success': True,
                    'message': f"Đã kích hoạt bot thành công: {msg}",
                    'status': 'running',
                    'prefix': prefix
                }
            else:
                self._persist_status(user_id, account_id, enabled=0, prefix=prefix, status='error')
                userbot_log(f"Khởi động UserBot '{name}' thất bại: {msg}", "error")
                return {'success': False, 'message': f"Lỗi khởi động bot: {msg}", 'status': 'error'}

        except Exception as e:
            self._persist_status(user_id, account_id, enabled=0, prefix=prefix, status='error')
            userbot_log(f"Lỗi ngoại lệ khi chạy UserBot: {e}", "error")
            return {'success': False, 'message': f"Lỗi: {str(e)}", 'status': 'error'}

    def stop_bot(self, user_id: int, account_id: Any, token: str) -> Dict[str, Any]:
        """Tắt UserBot và lưu trạng thái tắt vào cơ sở dữ liệu"""
        token = (token or "").strip()
        if not token:
            self._persist_status(user_id, account_id, enabled=0, status='stopped')
            return {'success': True, 'message': 'Đã cập nhật trạng thái tắt bot'}

        try:
            from apps.user_discord.core import runtime

            async def _do_shutdown():
                return await runtime.shutdown(token)

            self.run_coro(_do_shutdown(), timeout=15.0)
            self._persist_status(user_id, account_id, enabled=0, status='stopped')
            userbot_log(f"Đã TẮT UserBot cho tài khoản (ID: {account_id})", "warning")
            log_event(f"Đã dừng UserBot cho tài khoản (ID: {account_id})", "info")
            return {'success': True, 'message': 'Đã tắt UserBot thành công', 'status': 'stopped'}
        except Exception as e:
            self._persist_status(user_id, account_id, enabled=0, status='stopped')
            userbot_log(f"Cảnh báo khi tắt UserBot: {e}", "warning")
            return {'success': True, 'message': f'Đã tắt bot (Cảnh báo: {str(e)})', 'status': 'stopped'}

    def _persist_status(self, user_id: int, account_id: Any, enabled: int, prefix: Optional[str] = None, status: str = 'stopped'):
        """Ghi trạng thái vào SQLite để F5 hay restart server không bao giờ bị mất"""
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                if str(account_id) == 'main':
                    if prefix is not None:
                        cursor.execute('''
                            UPDATE users 
                            SET bot_enabled = ?, bot_prefix = ?, bot_status = ?, bot_last_started = CURRENT_TIMESTAMP
                            WHERE id = ?
                        ''', (enabled, prefix, status, user_id))
                    else:
                        cursor.execute('''
                            UPDATE users 
                            SET bot_enabled = ?, bot_status = ?
                            WHERE id = ?
                        ''', (enabled, status, user_id))
                else:
                    if prefix is not None:
                        cursor.execute('''
                            UPDATE discord_accounts 
                            SET bot_enabled = ?, bot_prefix = ?, bot_status = ?, bot_last_started = CURRENT_TIMESTAMP
                            WHERE id = ? AND user_id = ?
                        ''', (enabled, prefix, status, account_id, user_id))
                    else:
                        cursor.execute('''
                            UPDATE discord_accounts 
                            SET bot_enabled = ?, bot_status = ?
                            WHERE id = ? AND user_id = ?
                        ''', (enabled, status, account_id, user_id))
                conn.commit()
        except Exception as e:
            userbot_log(f"Lỗi ghi trạng thái bot vào DB: {e}", "warning")

    def auto_start_saved_bots(self):
        """Quét DB và tự động khởi động lại tất cả bot mà người dùng đã bấm Kích hoạt trước đó"""
        userbot_log("Đang kiểm tra và phục hồi trạng thái các UserBot đã lưu từ trước...", "info")
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                # 1. Quét tài khoản chính trong users
                cursor.execute('SELECT id, username, discord_token, bot_enabled, bot_prefix FROM users WHERE bot_enabled = 1 AND discord_token != ""')
                main_users = cursor.fetchall()
                for u in main_users:
                    token = u['discord_token']
                    prefix = '' if u['bot_prefix'] is None else str(u['bot_prefix'])
                    name = u['username'] or f"MainUser-{u['id']}"
                    userbot_log(f"Tự động chạy lại UserBot chính cho {name} (Prefix: '{prefix or 'None'}')...", "info")
                    threading.Thread(
                        target=self.start_bot,
                        args=(u['id'], 'main', token, prefix, name),
                        daemon=True
                    ).start()

                # 2. Quét các tài khoản phụ trong discord_accounts
                cursor.execute('SELECT id, user_id, discord_username, token, bot_enabled, bot_prefix FROM discord_accounts WHERE bot_enabled = 1 AND token != ""')
                sub_accs = cursor.fetchall()
                for a in sub_accs:
                    token = a['token']
                    prefix = '' if a['bot_prefix'] is None else str(a['bot_prefix'])
                    name = a['discord_username'] or f"SubAcc-{a['id']}"
                    userbot_log(f"Tự động chạy lại UserBot phụ cho {name} (Prefix: '{prefix or 'None'}')...", "info")
                    threading.Thread(
                        target=self.start_bot,
                        args=(a['user_id'], a['id'], token, prefix, name),
                        daemon=True
                    ).start()
        except Exception as e:
            userbot_log(f"Lỗi khi auto-start các UserBot đã lưu: {e}", "warning")

    def shutdown_all(self):
        """Tắt tất cả UserBot khi tắt hệ thống máy chủ"""
        userbot_log("Đang ngắt kết nối và giải phóng toàn bộ các UserBot...", "warning")
        try:
            from apps.user_discord.core import runtime
            tokens = list(runtime.LIVE.keys())
            for t in tokens:
                try:
                    async def _shut():
                        await runtime.shutdown(t)
                    self.run_coro(_shut(), timeout=5.0)
                except Exception:
                    pass
        except Exception:
            pass

userbot_worker = UserBotWorker()
