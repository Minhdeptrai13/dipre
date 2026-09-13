import json
import threading
import time
try:
    import websocket
except ImportError:
    websocket = None
from flask import Blueprint, request, jsonify, session

from core.logger import log_event
from core.database import get_db, track_feature_use
from core.registry import registry, SubModule
from modules.auth.helpers import login_required

voice_bp = Blueprint('voice', __name__)

class VoiceAFKWorker:
    def __init__(self):
        self.is_running = False
        self.token = ''
        self.guild_id = ''
        self.channel_id = ''
        self.self_mute = True
        self.self_deaf = True
        self.ws = None
        self.thread = None
        self.connected_at = 0

    def start(self, token, guild_id, channel_id, self_mute=True, self_deaf=True):
        self.stop()
        self.token = token
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.self_mute = self_mute
        self.self_deaf = self_deaf
        self.is_running = True
        self.connected_at = time.time()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False
        if self.ws:
            try:
                leave_payload = {
                    'op': 4,
                    'd': {
                        'guild_id': self.guild_id,
                        'channel_id': None,
                        'self_mute': False,
                        'self_deaf': False
                    }
                }
                self.ws.send(json.dumps(leave_payload))
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        self.connected_at = 0

    def _run_loop(self):
        while self.is_running:
            try:
                ws_url = 'wss://gateway.discord.gg/?v=9&encoding=json'
                self.ws = websocket.WebSocketApp(
                    ws_url,
                    on_message=self._on_message,
                    on_open=self._on_open,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                self.ws.run_forever()
            except Exception:
                time.sleep(5)

    def _on_open(self, ws):
        identify = {
            'op': 2,
            'd': {
                'token': self.token,
                'properties': {
                    'os': 'Windows',
                    'browser': 'Chrome',
                    'device': 'desktop'
                }
            }
        }
        ws.send(json.dumps(identify))

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            op = data.get('op')
            t = data.get('t')

            if op == 10:
                interval = data['d']['heartbeat_interval'] / 1000.0
                threading.Thread(target=self._heartbeat, args=(ws, interval), daemon=True).start()

            if t == 'READY':
                join_payload = {
                    'op': 4,
                    'd': {
                        'guild_id': self.guild_id,
                        'channel_id': self.channel_id,
                        'self_mute': self.self_mute,
                        'self_deaf': self.self_deaf
                    }
                }
                ws.send(json.dumps(join_payload))
                log_event(f'Treo Voice 24/7: Đã kết nối vào phòng voice ({self.channel_id})', 'success')
        except Exception:
            pass

    def _heartbeat(self, ws, interval):
        while self.is_running and ws.sock and ws.sock.connected:
            try:
                ws.send(json.dumps({'op': 1, 'd': None}))
            except Exception:
                break
            time.sleep(interval)

    def _on_error(self, ws, error):
        pass

    def _on_close(self, ws, close_status_code, close_msg):
        pass

voice_worker = VoiceAFKWorker()

@voice_bp.route('/api/voice/start', methods=['POST'])
@login_required
def api_voice_start():
    user_id = session.get('user_id')
    data = request.get_json() or {}
    guild_id = data.get('guild_id', '').strip()
    channel_id = data.get('channel_id', '').strip()
    self_mute = bool(data.get('self_mute', True))
    self_deaf = bool(data.get('self_deaf', True))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT discord_token FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
    token = (row['discord_token'] if row else '') or session.get('discord_token', '')

    if not token:
        return jsonify({'success': False, 'message': 'Chưa kết nnối tài khoản Discord token'}), 400
    if not guild_id or not channel_id:
        return jsonify({'success': False, 'message': 'Vui lòng điền đầy đủ Guild ID (Server) và Channel ID (Phòng Voice)'}), 400

    voice_worker.start(token, guild_id, channel_id, self_mute, self_deaf)
    track_feature_use(user_id, 'voice_afk')
    log_event(f'Tài khoản {session.get("username")} đã kích hoạt Treo Voice 24/7 trên kênh {channel_id}', 'success')
    return jsonify({'success': True, 'message': 'Đã khởi động treo voice 24/7 thành công!'})

@voice_bp.route('/api/voice/stop', methods=['POST'])
@login_required
def api_voice_stop():
    voice_worker.stop()
    log_event(f'Tài khoản {session.get("username")} đã ngắt kết nnối Treo Voice 24/7', 'info')
    return jsonify({'success': True, 'message': 'Đã ngầt kết nối Treo Voice'})

@voice_bp.route('/api/voice/status', methods=['GET'])
@login_required
def api_voice_status():
    elapsed = int(time.time() - voice_worker.connected_at) if voice_worker.is_running and voice_worker.connected_at else 0
    return jsonify({
        'success': True,
        'is_running': voice_worker.is_running,
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
    blueprint=voice_bp
))
