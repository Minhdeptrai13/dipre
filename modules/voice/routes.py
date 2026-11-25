import asyncio
import threading
import time
import discord
from flask import Blueprint, request, jsonify, session

from core.logger import log_event
from core.database import get_db, track_feature_use
from core.registry import registry, SubModule
from modules.auth.helpers import login_required

voice_bp = Blueprint('voice', __name__)


class VoiceAFKWorker:
    """Engine Treo Voice 24/7 thực tế dùng discord.py-self Gateway Opcode 4 + Auto-Keeper."""

    def __init__(self):
        self.is_running = False
        self.confirmed = False
        self.last_error = ''
        self.token = ''
        self.guild_id = ''
        self.channel_id = ''
        self.self_mute = True
        self.self_deaf = True
        self.thread = None
        self.loop = None
        self.client = None
        self.connected_at = 0
        self._run_id = 0
        self._lock = threading.Lock()
        self._used_live_bot = False

    def _get_live_userbot(self, token: str):
        try:
            from apps.user_discord.core import runtime
            if runtime.is_live(token):
                return runtime.get_live(token)
        except Exception:
            pass
        return None

    def start(self, token: str, guild_id: str, channel_id: str, self_mute: bool = True, self_deaf: bool = True):
        self.stop()
        with self._lock:
            self._run_id += 1
            run_id = self._run_id
            self.token = token.strip()
            self.guild_id = str(guild_id).strip()
            self.channel_id = str(channel_id).strip()
            self.self_mute = bool(self_mute)
            self.self_deaf = bool(self_deaf)
            self.is_running = True
            self.confirmed = False
            self.last_error = ''
            self.connected_at = time.time()
            self._used_live_bot = False

        # Nếu UserBot đang chạy sẵn trên token này -> dùng luôn WebSocket live của nó để vào Voice tức thì!
        live_bot = self._get_live_userbot(self.token)
        if live_bot and getattr(live_bot, 'loop', None) and live_bot.loop.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    self._join_on_client(live_bot, int(self.guild_id), int(self.channel_id), self.self_mute, self.self_deaf),
                    live_bot.loop
                )
                ok = fut.result(timeout=8.0)
                if ok:
                    with self._lock:
                        self._used_live_bot = True
                        self.confirmed = True
                        self.client = live_bot
                        self.loop = live_bot.loop
                    log_event(f'Treo Voice 24/7 (UserBot Live): Đã vào kênh {self.channel_id}!', 'success')
                    return
            except Exception as e:
                log_event(f'Chuyển sang luồng Gateway Voice riêng: {e}', 'info')

        self.thread = threading.Thread(target=self._run_thread, args=(run_id,), daemon=True)
        self.thread.start()

    async def _join_on_client(self, client, gid: int, ch_id: int, mute: bool, deaf: bool) -> bool:
        try:
            guild = client.get_guild(gid)
            channel = client.get_channel(ch_id) or (guild.get_channel(ch_id) if guild else None)
            if guild and channel:
                await guild.change_voice_state(channel=channel, self_mute=mute, self_deaf=deaf, self_video=False)
                return True
            if hasattr(client, 'ws') and client.ws:
                await client.ws.voice_state(gid, ch_id, self_mute=mute, self_deaf=deaf, self_video=False)
                return True
        except Exception as e:
            self.last_error = str(e)
            log_event(f'Lỗi gửi Opcode 4 Voice State: {e}', 'error')
        return False

    def stop(self):
        with self._lock:
            self._run_id += 1
            was_running = self.is_running
            self.is_running = False
            self.confirmed = False
            client = self.client
            loop = self.loop
            used_live = self._used_live_bot
            gid = self.guild_id

        if was_running and client and loop and loop.is_running():
            try:
                if used_live:
                    async def _leave_live():
                        try:
                            g = client.get_guild(int(gid))
                            if g:
                                await g.change_voice_state(channel=None)
                            elif hasattr(client, 'ws') and client.ws:
                                await client.ws.voice_state(int(gid), None)
                        except Exception:
                            pass
                    asyncio.run_coroutine_threadsafe(_leave_live(), loop).result(timeout=4.0)
                else:
                    async def _close_standalone():
                        try:
                            if not client.is_closed():
                                if gid and hasattr(client, 'ws') and client.ws:
                                    try:
                                        await client.ws.voice_state(int(gid), None)
                                    except Exception:
                                        pass
                                await client.close()
                        except Exception:
                            pass
                    asyncio.run_coroutine_threadsafe(_close_standalone(), loop).result(timeout=4.0)
            except Exception:
                pass

        with self._lock:
            self.client = None
            self.loop = None
            self._used_live_bot = False
            self.connected_at = 0

    def _run_thread(self, run_id: int):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = discord.Client()

        with self._lock:
            if self._run_id != run_id or not self.is_running:
                loop.close()
                return
            self.loop = loop
            self.client = client

        token = self.token
        gid = int(self.guild_id)
        ch_id = int(self.channel_id)

        async def _keeper():
            await client.wait_until_ready()
            while self.is_running and self._run_id == run_id and not client.is_closed():
                await asyncio.sleep(30.0)
                try:
                    g = client.get_guild(gid)
                    me = g.me if g else None
                    in_target = bool(me and me.voice and me.voice.channel and me.voice.channel.id == ch_id)
                    if not in_target:
                        await self._join_on_client(client, gid, ch_id, self.self_mute, self.self_deaf)
                except Exception:
                    pass

        @client.event
        async def on_ready():
            if self._run_id != run_id or not self.is_running:
                return
            log_event(f'Voice Gateway READY ({client.user}) — đang kết nối vào phòng #{ch_id}...', 'info')
            ok = await self._join_on_client(client, gid, ch_id, self.self_mute, self.self_deaf)
            if ok:
                with self._lock:
                    if self._run_id == run_id:
                        self.confirmed = True
                log_event(f'Treo Voice 24/7: Đã kết nối vào phòng voice ({ch_id})', 'success')
                loop.create_task(_keeper())
            else:
                with self._lock:
                    if self._run_id == run_id:
                        self.is_running = False
                        self.confirmed = False

        @client.event
        async def on_voice_state_update(member, before, after):
            if client.user and member.id == client.user.id:
                if after and after.channel and after.channel.id == ch_id:
                    with self._lock:
                        self.confirmed = True
                elif self.is_running and self._run_id == run_id and after.channel is None:
                    # Auto-keeper: bị kick hoặc mất kết nối -> tự join lại sau 2s
                    await asyncio.sleep(2.0)
                    if self.is_running and self._run_id == run_id:
                        await self._join_on_client(client, gid, ch_id, self.self_mute, self.self_deaf)

        try:
            loop.run_until_complete(client.start(token))
        except Exception as e:
            with self._lock:
                if self._run_id == run_id:
                    self.last_error = str(e)
                    self.is_running = False
                    self.confirmed = False
            log_event(f'Lỗi Treo Voice Gateway: {e}', 'error')
        finally:
            try:
                if not client.is_closed():
                    loop.run_until_complete(client.close())
                loop.close()
            except Exception:
                pass


voice_worker = VoiceAFKWorker()


@voice_bp.route('/api/voice/start', methods=['POST'])
@login_required
def api_voice_start():
    user_id = session.get('user_id')
    data = request.get_json() or {}
    guild_id = str(data.get('guild_id', '')).strip()
    channel_id = str(data.get('channel_id', '')).strip()
    account_id = data.get('account_id')
    self_mute = bool(data.get('self_mute', True))
    self_deaf = bool(data.get('self_deaf', True))

    if not guild_id.isdigit() or not channel_id.isdigit():
        return jsonify({'success': False, 'message': 'Guild ID và Channel ID phải là chuỗi số ID hợp lệ của Discord!'}), 400

    with get_db() as conn:
        cursor = conn.cursor()
        token = ''
        acc_name = ''
        if account_id and str(account_id) != 'main':
            cursor.execute('SELECT token, discord_username FROM discord_accounts WHERE id = ? AND user_id = ?', (account_id, user_id))
            r = cursor.fetchone()
            if r:
                token = r['token']
                acc_name = r['discord_username'] or f'Sub-{account_id}'
        if not token:
            cursor.execute('SELECT token, discord_username FROM discord_accounts WHERE user_id = ? AND is_active = 1 LIMIT 1', (user_id,))
            acc_r = cursor.fetchone()
            if acc_r and acc_r['token']:
                token = acc_r['token']
                acc_name = acc_r['discord_username'] or 'Main'
        if not token:
            cursor.execute('SELECT discord_token, discord_username FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                token = row['discord_token'] or ''
                acc_name = row['discord_username'] or session.get('username', 'Main')
            if not token:
                token = session.get('discord_token', '')

    if not token or len(token) < 20:
        return jsonify({'success': False, 'message': 'Chưa có Discord User Token hợp lệ cho tài khoản này!'}), 400

    voice_worker.start(token, guild_id, channel_id, self_mute, self_deaf)
    track_feature_use(user_id, 'voice_afk')
    log_event(f'Tài khoản {acc_name} đang kết nối Treo Voice 24/7 tới kênh {channel_id} (Server: {guild_id})', 'success')
    return jsonify({
        'success': True,
        'message': f'Đang kết nối Treo Voice 24/7 vào phòng #{channel_id} cho {acc_name}!',
        'account_name': acc_name
    })


@voice_bp.route('/api/voice/stop', methods=['POST'])
@login_required
def api_voice_stop():
    voice_worker.stop()
    log_event(f'Tài khoản {session.get("username")} đã ngắt kết nối Treo Voice 24/7', 'info')
    return jsonify({'success': True, 'message': 'Đã ngắt kết nối Treo Voice khỏi phòng thoại'})


@voice_bp.route('/api/voice/status', methods=['GET'])
@login_required
def api_voice_status():
    elapsed = int(time.time() - voice_worker.connected_at) if voice_worker.is_running and voice_worker.connected_at else 0
    return jsonify({
        'success': True,
        'is_running': voice_worker.is_running,
        'confirmed': voice_worker.confirmed,
        'last_error': voice_worker.last_error,
        'guild_id': voice_worker.guild_id,
        'channel_id': voice_worker.channel_id,
        'self_mute': voice_worker.self_mute,
        'self_deaf': voice_worker.self_deaf,
        'elapsed_seconds': elapsed
    })


registry.register_module(SubModule(
    key='voice_afk',
    category_key='voice',
    title='24/7 Voice Channel AFK',
    blueprint=voice_bp,
    cleanup_handler=lambda: voice_worker.stop()
))
