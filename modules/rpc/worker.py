import os
import sys
import time
import asyncio
import threading
from typing import Optional, Dict, Any
import discord

from core.logger import log_event
from core.config import UPLOAD_FOLDER, UPLOAD_PATH_MAP, KNOWN_ASSET_ICONS

class DiscordRPCWorker:
    def __init__(self):
        self.client = None
        self.loop = None
        self.thread = None
        self._active_loop = None
        self._active_client = None
        self._run_id = 0
        self.status = 'stopped'
        self.error_message = None
        self.user_tag = None
        self.user_id = None
        self.start_timestamp = None
        self.current_config = None
        self._managed_app = None
        self._last_name_edit_time = 0
        self._last_icon_edit_time = 0
        self._asset_cache = {}
        self._name_edit_cooldown = 30
        self._lock = threading.Lock()

    def get_status_data(self):
        with self._lock:
            elapsed = 0
            if self.start_timestamp and self.status == 'running':
                elapsed = int(time.time() - self.start_timestamp)
            return {
                'status': self.status,
                'error_message': self.error_message,
                'user_tag': self.user_tag,
                'user_id': self.user_id,
                'elapsed_seconds': elapsed,
                'config': self.current_config
            }

    def _get_live_userbot(self, token: str):
        try:
            from apps.user_discord.core import runtime
            if runtime.is_live(token):
                return runtime.get_live(token)
        except Exception:
            pass
        return None

    def start(self, config):
        self.stop()
        token = (config.get('token') or '').strip()

        # Nếu UserBot đang chạy sẵn trên token này -> dùng luôn phiên Gateway live của UserBot!
        live_bot = self._get_live_userbot(token)
        if live_bot and getattr(live_bot, 'loop', None) and live_bot.loop.is_running() and not live_bot.is_closed():
            with self._lock:
                self._run_id += 1
                self.status = 'connecting'
                self.error_message = None
                self.current_config = config
                self.start_timestamp = time.time()
                self._active_client = live_bot
                self._active_loop = live_bot.loop
                self.client = live_bot
                self.loop = live_bot.loop
                self.user_tag = str(live_bot.user) if live_bot.user else None
                self.user_id = str(live_bot.user.id) if live_bot.user else None
            try:
                fut = asyncio.run_coroutine_threadsafe(self._apply_presence(config), live_bot.loop)
                fut.result(timeout=12.0)
                with self._lock:
                    self.status = 'running'
                return True
            except Exception as e:
                log_event(f'Cảnh báo áp dụng RPC qua UserBot live ({e}), chuyển sang client riêng...', 'warning')

        with self._lock:
            self._run_id += 1
            current_run_id = self._run_id
            self.status = 'connecting'
            self.error_message = None
            self.current_config = config
            self.start_timestamp = time.time()
            self._ready_event = threading.Event()
            self.thread = threading.Thread(target=self._run_thread, args=(config, current_run_id), daemon=True)
            self.thread.start()
        return True

    def wait_ready(self, timeout: float = 12.0) -> bool:
        ev = getattr(self, '_ready_event', None)
        if ev:
            ev.wait(timeout=timeout)
        return self.status == 'running'

    def update_presence(self, config):
        with self._lock:
            loop = self._active_loop
            client = self._active_client
            if self.status != 'running' or not client or client.is_closed() or not loop:
                self.start(config)
                return True
            self.current_config = config
            future = asyncio.run_coroutine_threadsafe(self._apply_presence(config), loop)
        future.result(timeout=6.0)
        return True

    async def _apply_presence(self, config):
        activity = await self._build_activity(config)
        status_choice = config.get('userStatus', 'online')
        discord_status = getattr(discord.Status, status_choice, discord.Status.online)
        if self.client and not self.client.is_closed():
            try:
                await self.client.change_presence(status=discord_status, activity=activity)
            except Exception as err:
                log_event(f'Cảnh báo phát RPC đầy đủ ({err}), chuyển sang chế độ tương thích...', 'warning')
                fallback_act = discord.Activity(
                    type=activity.type,
                    name=activity.name,
                    details=getattr(activity, 'details', None),
                    state=getattr(activity, 'state', None),
                    timestamps=getattr(activity, 'timestamps', None)
                )
                await self.client.change_presence(status=discord_status, activity=fallback_act)
            log_event(f'Đã cập nhật trạng thái Rich Presence ({discord_status.value}) thành công.', 'success')

    def stop(self):
        with self._lock:
            if self.status == 'stopped' and (not self.thread or not self.thread.is_alive()):
                return True
            self.status = 'stopping'

        loop = None
        client = None
        thread = None
        with self._lock:
            loop = self._active_loop
            client = self._active_client
            thread = self.thread

        if loop and client and not client.is_closed() and loop.is_running():
            is_live_bot = bool(self.current_config and self._get_live_userbot((self.current_config.get('token') or '').strip()) is client)
            try:
                if is_live_bot:
                    async def _clear_only():
                        try:
                            await client.change_presence(activity=None)
                        except Exception:
                            pass
                    asyncio.run_coroutine_threadsafe(_clear_only(), loop).result(timeout=4.0)
                else:
                    fut = asyncio.run_coroutine_threadsafe(self._safe_close_client(client, loop), loop)
                    fut.result(timeout=3.0)
            except Exception:
                pass

        if loop and loop.is_running() and not (self.current_config and self._get_live_userbot((self.current_config.get('token') or '').strip()) is client):
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass

        if thread and thread.is_alive() and threading.current_thread() != thread:
            thread.join(timeout=4.0)

        with self._lock:
            self.status = 'stopped'
            self.user_tag = None
            self.user_id = None
            self.start_timestamp = None
            self._active_loop = None
            self._active_client = None
            self.client = None
            self.loop = None
            self.thread = None

        log_event('Đã dừng và ngắt kết nối an toàn với Discord Gateway.', 'warning')
        return True

    async def _safe_close_client(self, client, loop):
        try:
            if client and not client.is_closed():
                try:
                    await client.change_presence(activity=None)
                except BaseException:
                    pass
                await client.close()
        except BaseException:
            pass
        finally:
            try:
                tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task(loop) and not t.done()]
                for t in tasks:
                    t.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            except BaseException:
                pass

    async def _get_or_create_managed_app(self, desired_name: str, preferred_app_id: Optional[str] = None):
        tag_prefix = '[RPC Master]'
        try:
            my_apps = await self.client.applications()
            if preferred_app_id:
                clean_pref = str(preferred_app_id).strip()
                for app in my_apps:
                    if str(app.id) == clean_pref:
                        log_event(f'Sử dụng chính xác ứng dụng theo App ID: {app.name} ({app.id})', 'info')
                        self._managed_app = app
                        return app
            if desired_name:
                for app in my_apps:
                    if app.name.lower() == desired_name.lower():
                        log_event(f"Tìm thấy ứng dụng trùng tên '{desired_name}': {app.name} ({app.id})", 'info')
                        self._managed_app = app
                        return app
            for app in my_apps:
                desc = getattr(app, 'description', '') or ''
                if tag_prefix in desc or app.name == 'DiscordRPC Master':
                    log_event(f'Tìm thấy ứng dụng đã quản lý: {app.name} ({app.id})', 'info')
                    self._managed_app = app
                    return app
            if my_apps:
                app = my_apps[0]
                log_event(f'Tự động sử dụng ứng dụng có sẵn trên tài khoản: {app.name} ({app.id})', 'info')
                self._managed_app = app
                return app
        except Exception as e:
            log_event(f'Lỗi khi duyệt danh sách ứng dụng: {e}', 'warning')
        app_name = desired_name if desired_name else 'DiscordRPC Master'
        try:
            log_event(f"Đang tự động tạo Application mới '{app_name}' trên Discord Developer Portal...", 'info')
            new_app = await self.client.create_application(app_name)
            try:
                await new_app.edit(description='[RPC Master] Tự động quản lý Rich Presence bởi Discord RPC Master')
            except Exception:
                pass
            self._managed_app = new_app
            log_event(f'Tạo thành công Application: {new_app.name} ({new_app.id})', 'success')
            return new_app
        except Exception as e:
            if 'captcha' in str(e).lower():
                log_event('Discord yêu cầu xác thực Captcha khi tạo ứng dụng qua script. Vui lòng mở Developer Portal tạo 1 app bất kỳ.', 'warning')
            else:
                log_event(f'Không thể tự tạo Application: {e}', 'warning')
            return None

    async def _sync_app_name(self, app, desired_name: str):
        if not app or not desired_name:
            return
        if getattr(app, 'name', None) == desired_name:
            return
        now = time.time()
        elapsed = now - self._last_name_edit_time
        if elapsed < self._name_edit_cooldown:
            remain = int(self._name_edit_cooldown - elapsed)
            log_event(f"Tránh Rate Limit: Chờ {remain}s trước khi đổi tên trên Developer Portal (Discord vẫn hiển thị đúng '{desired_name}').", 'info')
            return
        try:
            log_event(f"Đang đổi tên Application từ '{app.name}' sang '{desired_name}'...", 'info')
            await app.edit(name=desired_name)
            self._last_name_edit_time = now
            log_event(f"Đã đổi tên Application thành '{desired_name}' thành công.", 'success')
        except Exception as e:
            log_event(f'Cảnh báo khi đổi tên Application: {e}', 'warning')

    async def _resolve_or_upload_asset(self, app, img_val: str, prefix: str) -> Optional[str]:
        if not img_val:
            img_val = ''
        img_val = img_val.strip()
        lower_val = img_val.lower()

        if prefix == 's' and not img_val:
            return None

        if lower_val in ('', 'bot', 'app', 'bot_avatar', 'app_icon', 'developer_portal', 'portal', 'default'):
            if prefix == 's':
                return None
            if app:
                try:
                    bot = getattr(app, 'bot', None)
                    if not bot and hasattr(app, 'fetch_bot'):
                        bot = await app.fetch_bot()
                    if bot and bot.avatar:
                        avatar_url = str(bot.avatar.url)
                        log_event(f'Sử dụng Avatar Anime từ Bot Icon của Developer Portal: {avatar_url}', 'success')
                        return avatar_url
                    if getattr(app, 'icon', None):
                        icon_url = str(app.icon.url)
                        log_event(f'Sử dụng ảnh từ App Icon của Developer Portal: {icon_url}', 'info')
                        return icon_url
                except Exception as e:
                    log_event(f'Lỗi lấy avatar Developer Portal: {e}', 'warning')
            if not img_val:
                return None
        if any((k in img_val for k in ('discordapp.com/attachments/', 'discordapp.net/attachments/', 'discordapp.com/avatars/', 'discordapp.com/app-icons/', 'discordapp.com/app-assets/', 'mp:'))):
            return img_val
        if lower_val in KNOWN_ASSET_ICONS:
            return KNOWN_ASSET_ICONS[lower_val]
        local_filepath = UPLOAD_PATH_MAP.get(img_val)
        if not local_filepath:
            if '/static/uploads/' in img_val or '/uploads/' in img_val:
                fname = img_val.split('/')[-1].split('?')[0]
                candidate = os.path.join(UPLOAD_FOLDER, fname)
                if os.path.exists(candidate):
                    local_filepath = candidate
            elif not img_val.startswith(('http://', 'https://')):
                candidate = os.path.join(UPLOAD_FOLDER, img_val)
                if os.path.exists(candidate):
                    local_filepath = candidate
        file_bytes = None
        if local_filepath and os.path.exists(local_filepath):
            try:
                with open(local_filepath, 'rb') as f:
                    file_bytes = f.read()
            except Exception as e:
                print(f'[RPC Worker] Không thể đọc file cục bộ: {e}')
        if app and file_bytes:
            try:
                print(f"[RPC Worker] Đang cập nhật App Icon cho '{app.name}' trên Developer Portal...")
                await app.edit(icon=file_bytes)
                if getattr(app, 'icon', None):
                    icon_url = str(app.icon.url)
                    print(f'[RPC Worker] Đã cập nhật thành công App Icon: {icon_url}')
                    return icon_url
            except Exception as icon_err:
                print(f'[RPC Worker] Lưu ý cập nhật App Icon: {icon_err}')
        if app and prefix == 'l':
            try:
                bot = getattr(app, 'bot', None)
                if not bot and hasattr(app, 'fetch_bot'):
                    bot = await app.fetch_bot()
                if bot and bot.avatar:
                    return str(bot.avatar.url)
                if getattr(app, 'icon', None):
                    return str(app.icon.url)
            except Exception:
                pass
        if prefix == 'l':
            return KNOWN_ASSET_ICONS.get('vscode')
        return None

    async def _build_activity(self, config):
        raw_type = str(config.get('activityType', 'playing')).strip().lower()
        stream_url = config.get('streamUrl', '').strip()
        activity_name = config.get('activityName', 'DIPRE STUDIO v5.0').strip() or 'DIPRE STUDIO v5.0'
        details = config.get('details', '').strip()
        state = config.get('state', '').strip()
        large_image = config.get('largeImage', '').strip()
        large_text = config.get('largeText', '').strip()
        small_image = config.get('smallImage', '').strip()
        small_text = config.get('smallText', '').strip()
        has_timestamp = config.get('hasTimestamp', True)
        btn1_label = config.get('btn1Label', '').strip()
        btn1_url = config.get('btn1Url', '').strip()
        btn2_label = config.get('btn2Label', '').strip()
        btn2_url = config.get('btn2Url', '').strip()
        app_id_str = str(config.get('appId', '') or '').strip()
        auto_app = config.get('autoApp', True)
        type_mapping = {
            'playing': discord.ActivityType.playing,
            'streaming': discord.ActivityType.streaming,
            'listening': discord.ActivityType.listening,
            'listening to': discord.ActivityType.listening,
            'watching': discord.ActivityType.watching,
            'competing': discord.ActivityType.competing,
            'competing in': discord.ActivityType.competing,
        }
        act_type = type_mapping.get(raw_type, discord.ActivityType.playing)
        timestamps = None
        if has_timestamp and self.start_timestamp:
            timestamps = {'start': int(self.start_timestamp * 1000)}

        app_id = None
        managed_app = None
        if self.client and (not self.client.is_closed()):
            managed_app = await self._get_or_create_managed_app(activity_name, app_id_str)
            if managed_app:
                app_id = managed_app.id
                if auto_app:
                    await self._sync_app_name(managed_app, activity_name)
        if not managed_app:
            if app_id_str and app_id_str not in ('1054366629930778644', 'None', ''):
                try:
                    app_id = int(app_id_str)
                except ValueError:
                    app_id = None

        final_large = await self._resolve_or_upload_asset(managed_app, large_image, 'l') if managed_app else (large_image if large_image.startswith(('http://', 'https://', 'mp:')) else None)
        final_small = await self._resolve_or_upload_asset(managed_app, small_image, 's') if managed_app else (small_image if small_image.startswith(('http://', 'https://', 'mp:')) else None)

        # Discord không chấp nhận file .svg hoặc URL https chưa proxy qua external-assets
        def _is_valid_discord_asset(val: Optional[str]) -> bool:
            if not val:
                return False
            if val.startswith(('mp:', 'spotify:')):
                return True
            if any(k in val for k in ('discordapp.com/app-assets/', 'discordapp.com/app-icons/', 'discordapp.com/avatars/', 'discordapp.com/attachments/', 'discordapp.net/attachments/')):
                return True
            return False

        if app_id and self.client and hasattr(self.client, 'proxy_external_application_assets'):
            urls_to_proxy = []
            for img in (final_large, final_small):
                if img and img.startswith(('http://', 'https://')) and not img.lower().split('?')[0].endswith('.svg') and (not _is_valid_discord_asset(img)):
                    urls_to_proxy.append(img)
            if urls_to_proxy:
                try:
                    proxied_list = await self.client.proxy_external_application_assets(app_id, *urls_to_proxy)
                    for orig, proxied in zip(urls_to_proxy, proxied_list):
                        if orig == final_large:
                            final_large = proxied
                        if orig == final_small:
                            final_small = proxied
                except Exception:
                    pass

        if not _is_valid_discord_asset(final_large):
            final_large = None
        if not _is_valid_discord_asset(final_small):
            final_small = None

        activity_assets = None
        if final_large or final_small or large_text or small_text:
            if final_large or final_small:
                activity_assets = discord.ActivityAssets(
                    large_image=final_large if final_large else None,
                    large_text=large_text if large_text else None,
                    small_image=final_small if final_small else None,
                    small_text=small_text if small_text else None
                )

        buttons = []
        if app_id:
            if btn1_label and btn1_url and btn1_url.startswith(('http://', 'https://')):
                buttons.append(discord.ActivityButton(label=btn1_label[:32], url=btn1_url))
            if btn2_label and btn2_url and btn2_url.startswith(('http://', 'https://')):
                buttons.append(discord.ActivityButton(label=btn2_label[:32], url=btn2_url))

        return discord.Activity(
            type=act_type,
            name=activity_name,
            url=stream_url if act_type == discord.ActivityType.streaming and stream_url else None,
            details=details if details else None,
            state=state if state else None,
            timestamps=timestamps,
            assets=activity_assets,
            buttons=buttons if buttons else None,
            application_id=app_id
        )

    def _run_thread(self, config, run_id):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = discord.Client(chunk_guilds_at_startup=False)

        with self._lock:
            if self._run_id != run_id:
                loop.close()
                return
            self._active_loop = loop
            self._active_client = client
            self.loop = loop
            self.client = client

        token = config.get('token', '').strip()

        @client.event
        async def on_ready():
            try:
                with self._lock:
                    if self._run_id != run_id:
                        return
                    self.user_tag = str(client.user)
                    self.user_id = str(client.user.id)
                log_event(f'Đã đăng nhập tài khoản Discord: {self.user_tag} ({self.user_id})', 'success')
                log_event(f"Đang đồng bộ cấu hình và hình ảnh cho '{config.get('activityName', 'Visual Studio Code')}'...", 'info')
                activity = await self._build_activity(config)
                status_choice = config.get('userStatus', 'online')
                discord_status = getattr(discord.Status, status_choice, discord.Status.online)
                try:
                    await client.change_presence(status=discord_status, activity=activity)
                except Exception as pres_err:
                    log_event(f'Cảnh báo phát RPC ({pres_err}), thử phát không kèm buttons/assets...', 'warning')
                    fallback_act = discord.Activity(
                        type=activity.type,
                        name=activity.name,
                        details=getattr(activity, 'details', None),
                        state=getattr(activity, 'state', None),
                        timestamps=getattr(activity, 'timestamps', None)
                    )
                    await client.change_presence(status=discord_status, activity=fallback_act)
                with self._lock:
                    if self._run_id == run_id:
                        self.status = 'running'
                ev = getattr(self, '_ready_event', None)
                if ev:
                    ev.set()
                log_event(f'Đã phát trạng thái Rich Presence ({discord_status.value}) thành công!', 'success')
            except Exception as e:
                with self._lock:
                    if self._run_id == run_id:
                        self.status = 'error'
                        self.error_message = f'Lỗi khi phát trạng thái: {e}'
                ev = getattr(self, '_ready_event', None)
                if ev:
                    ev.set()
                log_event(f'Lỗi nghiêm trọng khi phát trạng thái: {e}', 'error')
                import traceback
                traceback.print_exc()

        try:
            log_event('Đang kết nối tới Discord Gateway qua User Token...', 'info')
            loop.run_until_complete(client.start(token))
        except discord.errors.LoginFailure:
            with self._lock:
                if self._run_id == run_id:
                    self.status = 'error'
                    self.error_message = 'Discord User Token không hợp lệ hoặc đã bị khóa!'
            ev = getattr(self, '_ready_event', None)
            if ev:
                ev.set()
            log_event('Lỗi LoginFailure: Discord User Token không hợp lệ!', 'error')
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        except Exception as e:
            with self._lock:
                if self._run_id == run_id and self.status not in ('stopped', 'stopping'):
                    self.status = 'error'
                    self.error_message = str(e)
            ev = getattr(self, '_ready_event', None)
            if ev:
                ev.set()
            if self._run_id == run_id and self.status not in ('stopped', 'stopping'):
                log_event(f'Ngoại lệ kết nối Gateway: {e}', 'error')
        finally:
            ev = getattr(self, '_ready_event', None)
            if ev:
                ev.set()
            try:
                if not client.is_closed():
                    loop.run_until_complete(self._safe_close_client(client, loop))
                tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
                for t in tasks:
                    t.cancel()
                if tasks:
                    loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
            except BaseException:
                pass
            finally:
                try:
                    loop.close()
                except BaseException:
                    pass

            with self._lock:
                if self._run_id == run_id:
                    if self.status != 'error':
                        self.status = 'stopped'
                    self.user_tag = None
                    self.user_id = None
                    self.start_timestamp = None
                    if self._active_loop is loop:
                        self._active_loop = None
                    if self._active_client is client:
                        self._active_client = None
                    if self.client is client:
                        self.client = None
                    if self.loop is loop:
                        self.loop = None

class MultiDiscordRPCWorker:
    """Quản lý chạy đồng thời nhiều tài khoản Discord Rich Presence (Đa Token song song)"""
    def __init__(self):
        self.workers: Dict[str, DiscordRPCWorker] = {}
        self._lock = threading.Lock()
        self.current_config = None

    def start_accounts(self, configs_list: list):
        """Khởi động đồng loạt nhiều tài khoản cùng lúc không dừng lẫn nhau"""
        with self._lock:
            if configs_list:
                self.current_config = configs_list[0]

            active_tokens = {c.get('token') for c in configs_list if c.get('token')}
            
            for tok in list(self.workers.keys()):
                if tok not in active_tokens:
                    try:
                        self.workers[tok].stop()
                    except Exception:
                        pass
                    del self.workers[tok]

            started_workers = []
            for cfg in configs_list:
                tok = cfg.get('token')
                if not tok:
                    continue
                if tok not in self.workers:
                    w = DiscordRPCWorker()
                    self.workers[tok] = w
                    w.start(cfg)
                    started_workers.append(w)
                else:
                    self.workers[tok].update_presence(cfg)

        for w in started_workers:
            w.wait_ready(timeout=12.0)

    def start(self, config):
        """Hỗ trợ tương thích ngược: chạy 1 config duy nhất"""
        self.start_accounts([config])

    def update_presence(self, config):
        with self._lock:
            self.current_config = config
            for w in self.workers.values():
                w.update_presence(config)

    def stop(self):
        """Dừng tất cả các worker đang chạy"""
        with self._lock:
            for w in self.workers.values():
                try:
                    w.stop()
                except Exception:
                    pass
            self.workers.clear()

    def get_status_data(self):
        with self._lock:
            if not self.workers:
                return {'status': 'stopped', 'workers_count': 0}
            running = [w for w in self.workers.values() if w.status == 'running']
            first_w = next(iter(self.workers.values()))
            res = first_w.get_status_data()
            res['workers_count'] = len(self.workers)
            res['running_count'] = len(running)
            res['status'] = 'running' if running else ('connecting' if any(w.status == 'connecting' for w in self.workers.values()) else 'stopped')
            return res

rpc_worker = MultiDiscordRPCWorker()
