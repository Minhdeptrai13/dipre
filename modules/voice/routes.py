import asyncio
import re
import threading
import time
import discord
import requests
from flask import Blueprint, request, jsonify, session

from core.logger import log_event
from core.database import get_db, track_feature_use
from core.registry import registry, SubModule
from modules.auth.helpers import login_required

voice_bp = Blueprint('voice', __name__)


def _resolve_voice_token(user_id: int, account_id=None):
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
    return token, acc_name


def _parse_voice_targets(guild_raw: str, channel_raw: str):
    """Hỗ trợ nhập ID thuần hoặc dán thẳng link Discord https://discord.com/channels/<guild>/<channel>"""
    g_str = str(guild_raw or '').strip()
    c_str = str(channel_raw or '').strip()

    for txt in (c_str, g_str):
        m = re.search(r'/channels/(\d+)/(\d+)', txt)
        if m:
            return m.group(1), m.group(2)

    g_digits = re.sub(r'\D', '', g_str)
    c_digits = re.sub(r'\D', '', c_str)
    return g_digits, c_digits


def _inspect_voice_channel(token: str, guild_id: str, channel_id: str):
    """Kiểm tra thật trên Discord REST API xem Channel ID có phải phòng Voice không & lấy tên thật của Guild/Channel"""
    headers = {
        'Authorization': token,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    if not channel_id:
        return None, None, None, 'Vui lòng nhập Channel ID hoặc dán Link phòng Voice Discord!'

    res = requests.get(f'https://discord.com/api/v9/channels/{channel_id}', headers=headers, timeout=8)
    if res.status_code == 401:
        return None, None, None, 'Discord Token không hợp lệ hoặc đã hết hạn!'
    if res.status_code == 403:
        return None, None, None, 'Tài khoản không có quyền truy cập phòng Voice này (403 Forbidden)!'
    if res.status_code == 404:
        return None, None, None, f'Không tìm thấy kênh #{channel_id} trên Discord (sai ID hoặc bị đảo Guild/Channel ID)!'
    if res.status_code != 200:
        return None, None, None, f'Discord API báo lỗi HTTP {res.status_code}'

    ch_data = res.json()
    ch_type = ch_data.get('type')
    # type 2 = Guild Voice, type 13 = Stage Voice, type 1/3 = DM/Group Call
    if ch_type not in (2, 13, 1, 3):
        return None, None, None, f'Kênh #{ch_data.get("name", channel_id)} là kênh Chat/Khác (type={ch_type}), không phải phòng Voice!'

    real_gid = str(ch_data.get('guild_id') or guild_id or '')
    ch_name = ch_data.get('name') or f'Phòng #{channel_id[-6:]}'
    guild_name = f'Server {real_gid}' if real_gid else 'Direct Call'

    if real_gid:
        try:
            rg = requests.get(f'https://discord.com/api/v9/guilds/{real_gid}', headers=headers, timeout=6)
            if rg.status_code == 200:
                guild_name = rg.json().get('name') or guild_name
        except Exception:
            pass

    return real_gid, ch_name, guild_name, None


class VoiceAFKWorker:
    """Engine Treo Voice 24/7 thực tế dùng discord.py-self Gateway Opcode 4 + Auto-Keeper."""

    def __init__(self):
        self.is_running = False
        self.confirmed = False
        self.last_error = ''
        self.token = ''
        self.guild_id = ''
        self.channel_id = ''
        self.channel_name = ''
        self.guild_name = ''
        self.self_mute = True
        self.self_deaf = True
        self.thread = None
        self.loop = None
        self.client = None
        self.connected_at = 0
        self._run_id = 0
        self._lock = threading.Lock()
        self._used_live_bot = False
        self._join_event = None

    def _get_live_userbot(self, token: str):
        try:
            from apps.user_discord.core import runtime
            if runtime.is_live(token):
                return runtime.get_live(token)
        except Exception:
            pass
        return None

    def start(self, token: str, guild_id: str, channel_id: str, self_mute: bool = True, self_deaf: bool = True, channel_name: str = '', guild_name: str = ''):
        self.stop()
        join_ev = threading.Event()
        with self._lock:
            self._run_id += 1
            run_id = self._run_id
            self.token = token.strip()
            self.guild_id = str(guild_id).strip()
            self.channel_id = str(channel_id).strip()
            self.channel_name = channel_name or f'#{self.channel_id[-6:]}'
            self.guild_name = guild_name or self.guild_id
            self.self_mute = bool(self_mute)
            self.self_deaf = bool(self_deaf)
            self.is_running = True
            self.confirmed = False
            self.last_error = ''
            self.connected_at = time.time()
            self._used_live_bot = False
            self._join_event = join_ev

        # Nếu UserBot đang chạy sẵn trên token này -> dùng luôn WebSocket live của nó để vào Voice tức thì!
        live_bot = self._get_live_userbot(self.token)
        if live_bot and getattr(live_bot, 'loop', None) and live_bot.loop.is_running() and not live_bot.is_closed():
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    self._join_on_client(live_bot, int(self.guild_id) if self.guild_id else None, int(self.channel_id), self.self_mute, self.self_deaf),
                    live_bot.loop
                )
                ok = fut.result(timeout=8.0)
                if ok:
                    with self._lock:
                        self._used_live_bot = True
                        self.confirmed = True
                        self.client = live_bot
                        self.loop = live_bot.loop
                    join_ev.set()
                    log_event(f'Treo Voice 24/7 (UserBot Live): Đã vào #{self.channel_name} ({self.guild_name})!', 'success')
                    return True
            except Exception as e:
                log_event(f'Chuyển sang luồng Gateway Voice riêng: {e}', 'info')

        self.thread = threading.Thread(target=self._run_thread, args=(run_id, join_ev), daemon=True)
        self.thread.start()

        # Đợi tối đa 12s để Discord xác nhận vào phòng thật sự
        join_ev.wait(timeout=12.0)
        return self.confirmed or (self.is_running and not self.last_error)

    async def _join_on_client(self, client, gid, ch_id: int, mute: bool, deaf: bool) -> bool:
        try:
            if gid:
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
                            if gid:
                                g = client.get_guild(int(gid))
                                if g:
                                    await g.change_voice_state(channel=None)
                                    return
                            if hasattr(client, 'ws') and client.ws:
                                await client.ws.voice_state(int(gid) if gid else None, None)
                        except Exception:
                            pass
                    asyncio.run_coroutine_threadsafe(_leave_live(), loop).result(timeout=4.0)
                else:
                    async def _close_standalone():
                        try:
                            if not client.is_closed():
                                if hasattr(client, 'ws') and client.ws:
                                    try:
                                        await client.ws.voice_state(int(gid) if gid else None, None)
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

    def _run_thread(self, run_id: int, join_ev: threading.Event):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = discord.Client(chunk_guilds_at_startup=False)

        with self._lock:
            if self._run_id != run_id or not self.is_running:
                loop.close()
                join_ev.set()
                return
            self.loop = loop
            self.client = client

        token = self.token
        gid = int(self.guild_id) if self.guild_id else None
        ch_id = int(self.channel_id)

        async def _keeper():
            await client.wait_until_ready()
            while self.is_running and self._run_id == run_id and not client.is_closed():
                await asyncio.sleep(30.0)
                try:
                    if gid:
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
                join_ev.set()
                return
            log_event(f'Voice Gateway READY ({client.user}) — đang gửi lệnh vào #{self.channel_name}...', 'info')
            ok = await self._join_on_client(client, gid, ch_id, self.self_mute, self.self_deaf)
            if ok:
                # Đợi tối đa 3s để xác nhận VOICE_STATE_UPDATE, hoặc xác nhận đã gửi Opcode 4 thành công
                await asyncio.sleep(1.2)
                with self._lock:
                    if self._run_id == run_id:
                        self.confirmed = True
                log_event(f'Treo Voice 24/7: Đã kết nối vào #{self.channel_name} ({self.guild_name})', 'success')
                loop.create_task(_keeper())
            else:
                with self._lock:
                    if self._run_id == run_id:
                        self.is_running = False
                        self.confirmed = False
            join_ev.set()

        @client.event
        async def on_voice_state_update(member, before, after):
            if client.user and member.id == client.user.id:
                if after and after.channel and after.channel.id == ch_id:
                    with self._lock:
                        self.confirmed = True
                    join_ev.set()
                elif self.is_running and self._run_id == run_id and after.channel is None:
                    await asyncio.sleep(2.5)
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
            join_ev.set()
            log_event(f'Lỗi Treo Voice Gateway: {e}', 'error')
        finally:
            join_ev.set()
            try:
                if not client.is_closed():
                    loop.run_until_complete(client.close())
                loop.close()
            except Exception:
                pass


voice_worker = VoiceAFKWorker()


@voice_bp.route('/api/voice/channels', methods=['GET'])
@login_required
def api_voice_channels():
    """Lấy danh sách Server & Phòng Voice thật từ Discord của tài khoản đang chọn"""
    user_id = session.get('user_id')
    account_id = request.args.get('account_id')
    token, acc_name = _resolve_voice_token(user_id, account_id)
    if not token:
        return jsonify({'success': False, 'message': 'Chưa có token Discord'}), 400

    headers = {
        'Authorization': token,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        rg = requests.get('https://discord.com/api/v9/users/@me/guilds', headers=headers, timeout=8)
        if rg.status_code != 200:
            return jsonify({'success': False, 'message': f'Lỗi tải Server ({rg.status_code})'}), 400
        guilds = rg.json() if isinstance(rg.json(), list) else []
        results = []
        # Nếu truyền guild_id cụ thể thì load channels của guild đó, không thì load top 8 guilds
        target_gid = request.args.get('guild_id', '').strip()
        scan_guilds = [g for g in guilds if str(g.get('id')) == target_gid] if target_gid else guilds[:8]
        for g in scan_guilds:
            gid = str(g.get('id'))
            gname = g.get('name', 'Server')
            try:
                rc = requests.get(f'https://discord.com/api/v9/guilds/{gid}/channels', headers=headers, timeout=5)
                if rc.status_code == 200 and isinstance(rc.json(), list):
                    v_chans = [
                        {'id': str(c['id']), 'name': c.get('name', 'Voice'), 'type': c.get('type')}
                        for c in rc.json() if c.get('type') in (2, 13)
                    ]
                    if v_chans:
                        results.append({'guild_id': gid, 'guild_name': gname, 'channels': v_chans})
            except Exception:
                pass
        return jsonify({'success': True, 'guilds': results, 'account_name': acc_name})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@voice_bp.route('/api/voice/start', methods=['POST'])
@login_required
def api_voice_start():
    user_id = session.get('user_id')
    data = request.get_json() or {}
    guild_raw = data.get('guild_id', '')
    channel_raw = data.get('channel_id', '')
    account_id = data.get('account_id')
    self_mute = bool(data.get('self_mute', True))
    self_deaf = bool(data.get('self_deaf', True))

    token, acc_name = _resolve_voice_token(user_id, account_id)
    if not token or len(token) < 20:
        return jsonify({'success': False, 'message': 'Chưa có Discord User Token hợp lệ cho tài khoản này!'}), 400

    parsed_gid, parsed_cid = _parse_voice_targets(guild_raw, channel_raw)
    if not parsed_cid:
        return jsonify({'success': False, 'message': 'Vui lòng nhập Channel ID hoặc dán link phòng Voice Discord!'}), 400

    # Đọc thông tin thật của phòng Voice từ Discord API để tránh sai ID / nhầm kênh chữ
    real_gid, ch_name, guild_name, err_msg = _inspect_voice_channel(token, parsed_gid, parsed_cid)
    if err_msg:
        return jsonify({'success': False, 'message': err_msg}), 400

    ok = voice_worker.start(token, real_gid, parsed_cid, self_mute, self_deaf, channel_name=ch_name, guild_name=guild_name)
    if not ok or voice_worker.last_error:
        return jsonify({
            'success': False,
            'message': voice_worker.last_error or 'Không thể kết nối vào phòng Voice trên Discord Gateway!'
        }), 400

    track_feature_use(user_id, 'voice_afk')
    log_event(f'Tài khoản {acc_name} ĐÃ VÀO phòng Voice #{ch_name} ({guild_name})', 'success')
    return jsonify({
        'success': True,
        'confirmed': voice_worker.confirmed,
        'guild_id': real_gid,
        'channel_id': parsed_cid,
        'channel_name': ch_name,
        'guild_name': guild_name,
        'message': f'Đã vào Treo Voice 24/7 tại #{ch_name} ({guild_name}) cho {acc_name}!',
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
        'channel_name': voice_worker.channel_name,
        'guild_name': voice_worker.guild_name,
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
