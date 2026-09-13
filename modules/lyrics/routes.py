import os
import uuid
import threading
import requests
from flask import Blueprint, request, jsonify, session

from core.config import UPLOAD_FOLDER
from core.database import get_db, track_feature_use
from core.logger import log_event, quest_log
from core.registry import registry, SubModule
from modules.auth.helpers import login_required
from modules.lyrics.worker import lyric_worker

lyrics_bp = Blueprint('lyrics', __name__)

ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'm4a', 'ogg', 'flac', 'webm'}
_STT_MODEL = None
_STT_MODEL_LOCK = threading.Lock()

def _get_stt_model():
    """Lazy-load faster-whisper model (chỉ tải 1 lần, dùng chung cho cả app)."""
    global _STT_MODEL
    with _STT_MODEL_LOCK:
        if _STT_MODEL is None:
            from faster_whisper import WhisperModel
            model_size = os.environ.get('STT_MODEL_SIZE', 'base')
            _STT_MODEL = WhisperModel(model_size, device='cpu', compute_type='int8')
        return _STT_MODEL

def _format_lrc_timestamp(seconds: float) -> str:
    seconds = max(0, seconds)
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f'[{m:02d}:{s:02d}]'

@lyrics_bp.route('/api/lyrics/search', methods=['GET'])
@login_required
def api_lyrics_search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'success': False, 'message': 'Vui lòng nhập tên bài hát'}), 400
    try:
        results = []
        nct_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Referer': 'https://www.nhaccuatui.com/'
        }

        nct_cover_map = {}
        try:
            nct_url = f"https://www.nhaccuatui.com/ajax/search?q={requests.utils.quote(q)}"
            nr = requests.get(nct_url, headers=nct_headers, timeout=4, verify=False)
            if nr.status_code == 200:
                ndata = nr.json().get('data', {})
                for p in ndata.get('playlist', []) + ndata.get('song', []) + ndata.get('video', []):
                    img = p.get('img') or p.get('avatar') or p.get('thumb')
                    name = p.get('name') or p.get('title')
                    if img and name:
                        nct_cover_map[name.lower().strip()] = img
        except Exception:
            pass

        zing_cover_map = {}
        try:
            zr = requests.get(f"https://ac.mp3.zing.vn/complete?type=song&num=10&query={requests.utils.quote(q)}", timeout=3, verify=False)
            if zr.status_code == 200:
                for grp in zr.json().get('data', []):
                    for s in grp.get('song', []):
                        sname = s.get('name', '').lower().strip()
                        sthumb = s.get('thumb')
                        if sthumb:
                            zing_cover_map[sname] = f"https://photo-resize-zmp3.zmdcdn.me/w320_r1x1_jpeg/{sthumb}"
        except Exception:
            pass

        url = f"https://lrclib.net/api/search?q={requests.utils.quote(q)}"
        r = requests.get(url, headers={"User-Agent": "DIPRE-Discord/1.0"}, timeout=6)
        if r.status_code == 200:
            tracks = r.json()
            selected_tracks = tracks[:10]

            for t in selected_tracks:
                track_name = t.get('trackName') or ''
                artist_name = t.get('artistName') or ''
                t_lower = track_name.lower().strip()

                cover_url = ''
                for k, img in nct_cover_map.items():
                    if k in t_lower or t_lower in k:
                        cover_url = img
                        break

                if not cover_url:
                    for k, img in zing_cover_map.items():
                        if k in t_lower or t_lower in k:
                            cover_url = img
                            break

                if not cover_url:
                    if nct_cover_map:
                        cover_url = list(nct_cover_map.values())[0]
                    else:
                        cover_url = 'https://image-cdn.nct.vn/playlist/2023/01/03/6/2/1/4/1672730677680.jpg'

                results.append({
                    'id': t.get('id'),
                    'name': track_name,
                    'artist': artist_name,
                    'album': t.get('albumName') or 'NhacCuaTui Synced',
                    'duration': t.get('duration') or 0,
                    'cover': cover_url,
                    'has_synced': bool(t.get('syncedLyrics'))
                })

            return jsonify({'success': True, 'tracks': results})
        return jsonify({'success': True, 'tracks': []})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@lyrics_bp.route('/api/lyrics/song', methods=['GET'])
@login_required
def api_lyrics_song():
    q = request.args.get('q', '').strip()
    song_id = request.args.get('id')
    try:
        if song_id:
            url = f"https://lrclib.net/api/get/{song_id}"
            r = requests.get(url, headers={"User-Agent": "DIPRE-Discord/1.0"}, timeout=6)
            if r.status_code == 200:
                t = r.json()
                synced = t.get('syncedLyrics') or ''
                parsed = lyric_worker.parse_lrc(synced)
                return jsonify({
                    'success': True,
                    'track': {
                        'name': t.get('trackName'),
                        'artist': t.get('artistName'),
                        'duration': t.get('duration'),
                        'lyrics': [{'t': p[0], 'l': p[1]} for p in parsed]
                    }
                })
        elif q:
            ok, name, parsed = lyric_worker.fetch_nct_lyrics(q)
            if ok:
                return jsonify({
                    'success': True,
                    'track': {
                        'name': name,
                        'lyrics': [{'t': p[0], 'l': p[1]} for p in parsed]
                    }
                })
        return jsonify({'success': False, 'message': 'Không tìm thấy bài hát hoặc lời bài hát'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@lyrics_bp.route('/api/lyrics/sync', methods=['POST'])
@login_required
def api_lyrics_sync():
    user_id = session['user_id']
    data = request.get_json() or {}
    
    tokens_to_use = []
    
    # 1. Nếu client truyền trực tiếp danh sách tokens
    if isinstance(data.get('tokens'), list):
        tokens_to_use = [t.strip() for t in data['tokens'] if t and isinstance(t, str) and len(t.strip()) > 20]
        
    # 2. Nếu client truyền account_ids
    if not tokens_to_use and isinstance(data.get('account_ids'), list):
        ids = data['account_ids']
        with get_db() as conn:
            cursor = conn.cursor()
            if 'main' in ids or -1 in ids:
                cursor.execute('SELECT discord_token FROM users WHERE id = ?', (user_id,))
                u_row = cursor.fetchone()
                if u_row and u_row['discord_token']:
                    tokens_to_use.append(u_row['discord_token'])
            
            sub_ids = [int(i) for i in ids if str(i).isdigit() and int(i) > 0]
            if sub_ids:
                placeholders = ','.join('?' for _ in sub_ids)
                cursor.execute(f'SELECT token FROM discord_accounts WHERE user_id = ? AND id IN ({placeholders})', [user_id] + sub_ids)
                for r in cursor.fetchall():
                    if r['token'] and len(r['token']) > 20:
                        tokens_to_use.append(r['token'])

    # 3. Fallback: lấy token active của user
    if not tokens_to_use:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT discord_token FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            tok = (row['discord_token'] if row else '') or session.get('discord_token', '')
            if tok and len(tok) > 20:
                tokens_to_use.append(tok)

    if not tokens_to_use:
        return jsonify({'success': False, 'message': 'Không tìm thấy Discord Token nào để chạy đồng bộ!'}), 400

    song_name = data.get('song', '').strip()
    emoji = data.get('emoji', '🎵').strip()
    
    if song_name:
        ok, title, lyrics = lyric_worker.fetch_nct_lyrics(song_name)
        if not ok:
            return jsonify({'success': False, 'message': title}), 400
        track_feature_use(user_id, 'status_lyric')
        lyric_worker.start_lyric_stream(user_id, tokens_to_use, lyrics, emoji=emoji)
        return jsonify({
            'success': True,
            'message': f'Đang phát: {title} ({len(lyrics)} câu) trên {len(tokens_to_use)} tài khoản Discord!',
            'accounts_count': len(tokens_to_use)
        })

    text = (data.get('text') or data.get('status') or '').strip()
    if text:
        track_feature_use(user_id, 'status_custom')
        success_count = 0
        for t in tokens_to_use:
            ok, _ = lyric_worker.update_lyric(t, text, emoji=emoji)
            if ok:
                success_count += 1
        return jsonify({'success': True, 'message': f'Đã cập nhật trạng thái trên {success_count}/{len(tokens_to_use)} tài khoản!'})
    return jsonify({'success': False, 'message': 'Nội dung câu hát trống'}), 400

@lyrics_bp.route('/api/status/custom', methods=['POST'])
@login_required
def api_status_custom():
    """Đổi Custom Status trực tiếp của Discord token"""
    user_id = session['user_id']
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT discord_token FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
    token = (row['discord_token'] if row else '') or session.get('discord_token', '')
    if not token:
        return jsonify({'success': False, 'message': 'Tài khoản chưa liên kết Discord Token!'}), 400

    data = request.get_json() or {}
    text = data.get('text', '').strip()
    emoji = data.get('emoji', '').strip()

    ok, msg = lyric_worker.update_lyric(token, text, emoji=emoji)
    if ok:
        track_feature_use(user_id, 'status_custom')
        log_event(f'Đã đổi Custom Status cho tài khoản: "{text}"', 'success')
        return jsonify({'success': True, 'message': 'Đã cập nhật trạng thái tùy chỉnh thành công!'})
    return jsonify({'success': False, 'message': msg}), 400

@lyrics_bp.route('/api/lyrics/clear', methods=['POST'])
@login_required
def api_lyrics_clear():
    user_id = session['user_id']
    data = request.get_json() or {}
    lyric_worker.stop_lyric_stream(user_id)
    
    tokens_to_clear = []
    if isinstance(data.get('tokens'), list):
        tokens_to_clear = [t.strip() for t in data['tokens'] if t and len(t.strip()) > 20]
    
    if not tokens_to_clear:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT discord_token FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            tok = (row['discord_token'] if row else '') or session.get('discord_token', '')
            if tok:
                tokens_to_clear.append(tok)
            cursor.execute('SELECT token FROM discord_accounts WHERE user_id = ?', (user_id,))
            for r in cursor.fetchall():
                if r['token'] and len(r['token']) > 20:
                    tokens_to_clear.append(r['token'])

    success_cnt = 0
    for tok in set(tokens_to_clear):
        ok, _ = lyric_worker.clear_lyric(tok)
        if ok:
            success_cnt += 1
            
    return jsonify({'success': True, 'message': f'Đã xóa Status trên {success_cnt} tài khoản Discord!'})

@lyrics_bp.route('/api/lyrics/transcribe', methods=['POST'])
@login_required
def api_lyrics_transcribe():
    """Nhận file âm thanh, dùng faster-whisper để tự động nhận diện lời bài hát -> LRC."""
    if 'audio' not in request.files:
        return jsonify({'success': False, 'message': 'Không tìm thấy file âm thanh'}), 400
    file = request.files['audio']
    if not file or file.filename == '':
        return jsonify({'success': False, 'message': 'Chưa chọn file âm thanh nào'}), 400
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        return jsonify({'success': False, 'message': 'Định dạng không hỗ trợ (mp3, wav, m4a, ogg, flac)'}), 400

    tmp_name = f'{uuid.uuid4().hex}.{ext}'
    tmp_path = os.path.join(UPLOAD_FOLDER, tmp_name)
    file.save(tmp_path)
    try:
        try:
            model = _get_stt_model()
        except ImportError:
            return jsonify({
                'success': False,
                'message': 'Chưa cài thư viện nhận diện giọng nói. Chạy: pip install faster-whisper'
            }), 500

        segments, _info = model.transcribe(tmp_path, task='transcribe', vad_filter=True)
        lines = []
        count = 0
        for seg in segments:
            text = (seg.text or '').strip()
            if not text:
                continue
            lines.append(f'{_format_lrc_timestamp(seg.start)} {text}')
            count += 1

        if not lines:
            return jsonify({'success': False, 'message': 'Không nhận diện được lời bài hát nào từ file này.'}), 200

        lrc_text = '\n'.join(lines)
        quest_log(f'🎤 STT: đã tạo {count} dòng lời từ file {file.filename}', 'info')
        return jsonify({'success': True, 'lrc': lrc_text, 'segments': count})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi khi nhận diện: {e}'}), 500
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

# Đăng ký tiểu mục Lyric Sync vào Mục Lớn Status trong Core Registry
registry.register_module(SubModule(
    key='lyric_sync',
    category_key='status',
    title='Discord Lyric Sync & Speech-To-Text Engine',
    blueprint=lyrics_bp,
    worker=lyric_worker,
    cleanup_handler=lambda: lyric_worker.stop_all()
))
