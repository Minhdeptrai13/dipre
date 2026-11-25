import asyncio
import random
import re
import threading
import time
from typing import Dict, Any, List, Optional
import discord
import requests

from core.discord_guard import discord_guard
from core.logger import log_event

GIFT_REGEX = re.compile(r'(?:discord\.gift/|discord\.com/gifts/|discordapp\.com/gifts/)([A-Za-z0-9]{12,26})')


class RealDiscordSniperWorker:
    """
    Sniper Engine THẬT chạy qua Discord Gateway + Anti-Ban Rate-Limit Guard:
    - Auto Nitro Code Sniping: Nghe on_message tìm discord.gift/ và redeem qua Discord API.
    - Auto Giveaway Clicker: Phát hiện tin nhắn giveaway (GiveawayBot/Dyno/Carl-bot) và tự react an toàn.
    - Vanity URL Monitor: Kiểm tra Invite Vanity theo chu kỳ an toàn (anti-429).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.is_running: bool = False
        self.token: str = ''
        self.acc_name: str = ''
        self.nitro_enabled: bool = True
        self.giveaway_enabled: bool = False
        self.vanity_enabled: bool = False
        self.nitro_delay_ms: int = 150
        self.giveaway_delay_sec: int = 4
        self.vanity_codes: List[str] = ['vip', 'dipre', 'gang']
        self.webhook_url: str = ''

        self.logs: List[Dict[str, str]] = []
        self.seen_codes: set = set()
        self.gifts_seen: int = 0
        self.gifts_claimed: int = 0
        self.giveaways_joined: int = 0
        self.vanity_checks: int = 0

        self._run_id: int = 0
        self._client = None
        self._loop = None
        self._used_live_bot: bool = False
        self._live_listener_fn = None
        self._thread: Optional[threading.Thread] = None
        self._vanity_thread: Optional[threading.Thread] = None

    def _push_log(self, msg: str, level: str = 'info'):
        ts = time.strftime('%H:%M:%S')
        with self._lock:
            self.logs.append({'time': ts, 'message': msg, 'level': level})
            if len(self.logs) > 120:
                self.logs = self.logs[-120:]

    def clear_logs(self):
        with self._lock:
            self.logs.clear()
        self._push_log('[CLEARED] Đã làm sạch nhật ký Sniper Radar.', 'info')

    def update_config(self, cfg: Dict[str, Any]):
        with self._lock:
            if 'nitro' in cfg:
                self.nitro_enabled = bool(cfg['nitro'])
            if 'giveaway' in cfg:
                self.giveaway_enabled = bool(cfg['giveaway'])
            if 'vanity' in cfg:
                self.vanity_enabled = bool(cfg['vanity'])
            if 'nitro_delay_ms' in cfg:
                self.nitro_delay_ms = max(50, min(5000, int(cfg['nitro_delay_ms'] or 150)))
            if 'giveaway_delay_sec' in cfg:
                self.giveaway_delay_sec = max(2, min(60, int(cfg['giveaway_delay_sec'] or 4)))
            if 'vanity_codes' in cfg:
                raw = str(cfg['vanity_codes'] or '')
                self.vanity_codes = [c.strip().lower() for c in raw.split(',') if c.strip()][:8]
            if 'webhook_url' in cfg:
                self.webhook_url = str(cfg['webhook_url'] or '').strip()

    def _send_webhook(self, content: str) -> Tuple[bool, int]:
        url = self.webhook_url.strip()
        if not url or not url.startswith(('http://', 'https://')):
            return False, 0
        try:
            r = requests.post(url, json={'content': content}, timeout=6)
            return r.status_code in (200, 204), r.status_code
        except Exception:
            return False, 0

    def test_webhook(self, url: str) -> Tuple[bool, str]:
        clean = str(url or '').strip()
        if not clean.startswith(('http://', 'https://')) or 'discord.com/api/webhooks/' not in clean:
            return False, 'URL Webhook Discord không hợp lệ (phải có dạng https://discord.com/api/webhooks/...)'
        self.webhook_url = clean
        ok, code = self._send_webhook('🛡️ **[DIPRE STUDIO RADAR]** Đã liên kết Webhook thành công! Anti-Ban Shield đang bảo vệ.')
        if ok:
            self._push_log(f'[WEBHOOK] Đã lưu & test thành công (HTTP {code})', 'success')
            return True, f'Đã lưu & gửi Webhook thử nghiệm thành công (HTTP {code})!'
        self._push_log(f'[WEBHOOK] Test thất bại (HTTP {code})', 'warning')
        return False, f'Webhook phản hồi lỗi HTTP {code}'

    def _get_live_userbot(self, token: str):
        try:
            from apps.user_discord.core import runtime
            if runtime.is_live(token):
                return runtime.get_live(token)
        except Exception:
            pass
        return None

    async def _handle_message(self, message: discord.Message):
        if not self.is_running or not message or not message.author:
            return

        # 1. Auto Nitro Gift Code Sniping
        if self.nitro_enabled and message.content:
            codes = GIFT_REGEX.findall(message.content)
            for code in codes:
                with self._lock:
                    if code in self.seen_codes:
                        continue
                    self.seen_codes.add(code)
                    self.gifts_seen += 1

                ch_name = getattr(message.channel, 'name', 'DM')
                g_name = getattr(getattr(message, 'guild', None), 'name', 'Direct Message')
                self._push_log(f'[NITRO] Phát hiện mã discord.gift/{code} tại {g_name} (#{ch_name})', 'warn')

                # Kiểm tra Anti-Ban Shield trước khi claim
                allowed, reason, _ = discord_guard.can_call(self.token, action='redeem')
                if not allowed:
                    self._push_log(f'[ANTI-BAN] Tạm chặn claim {code}: {reason}', 'warn')
                    continue

                delay_s = max(0.05, self.nitro_delay_ms / 1000.0)
                if discord_guard.enabled:
                    delay_s += random.uniform(0.04, 0.18)
                await asyncio.sleep(delay_s)

                def _redeem():
                    headers = {
                        'Authorization': self.token,
                        'Content-Type': 'application/json',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    return requests.post(
                        f'https://discord.com/api/v9/entitlements/gift-codes/{code}/redeem',
                        headers=headers,
                        json={'channel_id': str(message.channel.id), 'payment_source_id': None},
                        timeout=6
                    )

                try:
                    resp = await asyncio.to_thread(_redeem)
                    discord_guard.record_response(self.token, resp.status_code, resp.headers, resp.text)
                    if resp.status_code in (200, 201):
                        with self._lock:
                            self.gifts_claimed += 1
                        self._push_log(f'🎉 [CLAIMED] Nhận thành công Nitro Gift {code}!', 'success')
                        self._send_webhook(f'🎉 **[DIPRE NITRO SNIPER]** Đã claim thành công gift `{code}` tại **{g_name}**!')
                    else:
                        msg_err = ''
                        try:
                            msg_err = resp.json().get('message', '')
                        except Exception:
                            pass
                        self._push_log(f'[NITRO] Mã {code}: HTTP {resp.status_code} ({msg_err or "Đã hết hạn/có người nhận"})', 'info')
                except Exception as ex:
                    self._push_log(f'[NITRO] Lỗi claim {code}: {ex}', 'error')

        # 2. Auto Giveaway Reaction Clicker (an toàn chống spam)
        if self.giveaway_enabled and message.author.bot:
            author_name = str(message.author.name or '').lower()
            is_ga_bot = any(k in author_name for k in ('giveaway', 'dyno', 'carl'))
            has_ga_embed = any('giveaway' in str(getattr(e, 'title', '') or '').lower() or 'prize' in str(getattr(e, 'description', '') or '').lower() for e in (message.embeds or []))
            if is_ga_bot or has_ga_embed:
                wait_ga = float(self.giveaway_delay_sec) + (random.uniform(1.0, 3.5) if discord_guard.enabled else 0.0)
                await asyncio.sleep(wait_ga)
                allowed, reason, _ = discord_guard.can_call(self.token, action='react')
                if not allowed:
                    self._push_log(f'[ANTI-BAN] Bỏ qua Giveaway để tránh rate-limit: {reason}', 'warn')
                    return
                try:
                    await message.add_reaction('🎉')
                    with self._lock:
                        self.giveaways_joined += 1
                    g_name = getattr(getattr(message, 'guild', None), 'name', 'Server')
                    self._push_log(f'[GIVEAWAY] Đã bấm tham gia Giveaway từ {message.author.name} tại {g_name}', 'success')
                    self._send_webhook(f'🎁 **[DIPRE GIVEAWAY]** Đã bấm tham gia Giveaway của `{message.author.name}` tại **{g_name}**')
                except Exception as ge:
                    self._push_log(f'[GIVEAWAY] Không thể react: {ge}', 'warn')

    def _vanity_loop(self, run_id: int):
        idx = 0
        while self.is_running and self._run_id == run_id:
            # Anti-Ban: nghỉ dài tối thiểu 18-30 giây giữa mỗi lần kiểm tra Vanity để không bị khóa IP/Token
            sleep_sec = random.uniform(18.0, 28.0) if discord_guard.enabled else 10.0
            for _ in range(int(sleep_sec)):
                if not self.is_running or self._run_id != run_id:
                    return
                time.sleep(1.0)

            if not self.vanity_enabled or not self.vanity_codes:
                continue

            code = self.vanity_codes[idx % len(self.vanity_codes)]
            idx += 1

            allowed, reason, _ = discord_guard.can_call(self.token, action='read')
            if not allowed:
                self._push_log(f'[ANTI-BAN] Tạm dừng quét Vanity: {reason}', 'warn')
                continue

            try:
                r = requests.get(f'https://discord.com/api/v9/invites/{code}', timeout=6)
                discord_guard.record_response(self.token, r.status_code, r.headers, r.text)
                with self._lock:
                    self.vanity_checks += 1
                if r.status_code == 404:
                    self._push_log(f'🔥 [VANITY] Link discord.gg/{code} ĐANG TRỐNG (AVAILABLE)!', 'success')
                    self._send_webhook(f'🔥 **[VANITY RADAR]** Mã `discord.gg/{code}` vừa được giải phóng (404 Available)!')
                elif r.status_code == 200:
                    gname = (r.json().get('guild') or {}).get('name', 'Server khác')
                    self._push_log(f'[VANITY] "{code}" đang thuộc về: {gname}', 'info')
            except Exception:
                pass

    def start(self, token: str, acc_name: str = 'Main', cfg: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        self.stop()
        if cfg:
            self.update_config(cfg)

        ready_ev = threading.Event()
        with self._lock:
            self._run_id += 1
            run_id = self._run_id
            self.token = token.strip()
            self.acc_name = acc_name
            self.is_running = True
            self._used_live_bot = False

        self._push_log(f'[RADAR] Khởi động Sniper Gateway cho {acc_name} (Anti-Ban Shield: {"ON" if discord_guard.enabled else "OFF"})...', 'warn')

        # Tái sử dụng kết nối UserBot đang chạy nếu có để không tạo 2 Gateway song song
        live_bot = self._get_live_userbot(self.token)
        if live_bot and getattr(live_bot, 'loop', None) and live_bot.loop.is_running() and not live_bot.is_closed():
            async def _listener(msg):
                await self._handle_message(msg)

            def _attach():
                live_bot.add_listener(_listener, 'on_message')

            live_bot.loop.call_soon_threadsafe(_attach)
            with self._lock:
                self._used_live_bot = True
                self._client = live_bot
                self._loop = live_bot.loop
                self._live_listener_fn = _listener

            self._push_log(f'[RADAR] Đã gắn Sniper trực tiếp vào phiên UserBot Live ({live_bot.user})!', 'success')
            self._vanity_thread = threading.Thread(target=self._vanity_loop, args=(run_id,), daemon=True)
            self._vanity_thread.start()
            return True, f'Đã bật Sniper thật (dùng chung Gateway UserBot {live_bot.user})!'

        # Nếu chưa bật UserBot -> tạo Gateway Client nhẹ với chunk_guilds_at_startup=False
        self._thread = threading.Thread(target=self._run_gateway_thread, args=(run_id, ready_ev), daemon=True)
        self._thread.start()
        ready_ev.wait(timeout=10.0)

        if not self.is_running:
            return False, 'Không thể kết nối Sniper tới Discord Gateway (kiểm tra lại Token).'

        self._vanity_thread = threading.Thread(target=self._vanity_loop, args=(run_id,), daemon=True)
        self._vanity_thread.start()
        return True, f'Đã bật Sniper Radar 24/7 cho {acc_name} (Anti-Ban: {"BẬT" if discord_guard.enabled else "TẮT"})!'

    def _run_gateway_thread(self, run_id: int, ready_ev: threading.Event):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = discord.Client(chunk_guilds_at_startup=False)

        with self._lock:
            if self._run_id != run_id or not self.is_running:
                loop.close()
                ready_ev.set()
                return
            self._client = client
            self._loop = loop

        @client.event
        async def on_ready():
            if self._run_id != run_id or not self.is_running:
                ready_ev.set()
                return
            g_cnt = len(getattr(client, 'guilds', []))
            self._push_log(f'[READY] Sniper đã nối Gateway ({client.user}) — đang canh {g_cnt} servers!', 'success')
            ready_ev.set()

        @client.event
        async def on_message(message):
            if self._run_id == run_id and self.is_running:
                await self._handle_message(message)

        try:
            loop.run_until_complete(client.start(self.token))
        except Exception as e:
            with self._lock:
                if self._run_id == run_id:
                    self.is_running = False
            self._push_log(f'[ERROR] Sniper Gateway dừng: {e}', 'error')
            ready_ev.set()
        finally:
            ready_ev.set()
            try:
                if not client.is_closed():
                    loop.run_until_complete(client.close())
                loop.close()
            except Exception:
                pass

    def stop(self):
        with self._lock:
            self._run_id += 1
            was = self.is_running
            self.is_running = False
            client = self._client
            loop = self._loop
            used_live = self._used_live_bot
            listener_fn = self._live_listener_fn
            self._client = None
            self._loop = None
            self._used_live_bot = False
            self._live_listener_fn = None

        if was and client and loop and loop.is_running():
            try:
                if used_live and listener_fn:
                    loop.call_soon_threadsafe(client.remove_listener, listener_fn, 'on_message')
                elif not used_live:
                    asyncio.run_coroutine_threadsafe(client.close(), loop).result(timeout=3.0)
            except Exception:
                pass
        if was:
            self._push_log('[STOP] Đã tắt Gateway Radar Sniper.', 'warn')

    def get_status(self) -> Dict[str, Any]:
        guard = discord_guard.get_status(self.token)
        with self._lock:
            return {
                'is_running': self.is_running,
                'account_name': self.acc_name,
                'nitro': self.nitro_enabled,
                'giveaway': self.giveaway_enabled,
                'vanity': self.vanity_enabled,
                'nitro_delay_ms': self.nitro_delay_ms,
                'giveaway_delay_sec': self.giveaway_delay_sec,
                'vanity_codes': ', '.join(self.vanity_codes),
                'webhook_url': self.webhook_url,
                'gifts_seen': self.gifts_seen,
                'gifts_claimed': self.gifts_claimed,
                'giveaways_joined': self.giveaways_joined,
                'vanity_checks': self.vanity_checks,
                'anti_ban': guard,
                'logs': list(self.logs[-50:]),
            }


sniper_worker = RealDiscordSniperWorker()
