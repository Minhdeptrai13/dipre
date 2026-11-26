import json
import re
from flask import Blueprint, request, jsonify, session

from core.ai_engine import (
    DIPRE_TIERS,
    REASONING_LEVELS,
    DIPRE_RAG_CHUNKS,
    normalize_tier,
    normalize_reasoning_level,
    retrieve_rag_context,
    build_dipre_web_system_prompt,
    web_ai_guard,
    call_dipre_ai,
)
from core.discord_guard import discord_guard
from core.database import track_feature_use
from modules.auth.helpers import login_required

ai_bp = Blueprint('ask_dipre', __name__)


def _collect_live_telemetry() -> str:
    """Thu thập trạng thái live an toàn của các worker (tuyệt đối không lộ token)."""
    parts = []
    try:
        from modules.rpc.worker import rpc_worker
        rpc_st = rpc_worker.get_status_data()
        active_rpc = rpc_st.get('active_count', len(rpc_st.get('sessions', []))) if isinstance(rpc_st, dict) else 0
        parts.append(f"- Presence RPC Worker: {active_rpc} phiên đang chạy")
    except Exception:
        parts.append("- Presence RPC Worker: chưa rõ")

    try:
        from modules.voice.routes import voice_worker
        v_run = bool(getattr(voice_worker, 'is_running', False))
        v_conf = bool(getattr(voice_worker, 'confirmed', False))
        v_err = getattr(voice_worker, 'last_error', '') or ''
        v_ch = getattr(voice_worker, 'channel_name', '') or ''
        parts.append(f"- Voice AFK 24/7: {'Đang chạy' if v_run else 'Đang tắt'} (confirmed={v_conf}{', kênh=' + v_ch if v_ch else ''}{', err=' + v_err if v_err else ''})")
    except Exception:
        pass

    try:
        from modules.sniper.worker import sniper_worker
        sn = sniper_worker.get_status()
        if isinstance(sn, dict):
            parts.append(f"- Sniper Radar: {'Đang chạy' if sn.get('running') else 'Đang tắt'} (detected={sn.get('detected', 0)}, claimed={sn.get('claimed', 0)})")
    except Exception:
        pass

    parts.append(f"- Anti-Ban Shield (DiscordAntiBanGuard): {'ĐANG BẬT' if discord_guard.enabled else 'ĐANG TẮT'} (giới hạn {discord_guard.max_writes_per_min} write/phút)")
    return "\n".join(parts)


@ai_bp.route('/api/ai/meta', methods=['GET'])
@login_required
def api_ai_meta():
    """Trả về thông tin 3 bậc model DIPRE + 3 mức suy luận + trạng thái RAG / Guard."""
    tiers = []
    for k in ('flash', 'standard', 'pro'):
        t = DIPRE_TIERS[k]
        tiers.append({
            'id': t['id'],
            'name': t['name'],
            'badge': t['badge'],
            'label': t['name'],
            'tagline': t['tagline'],
        })
    levels = []
    for k in ('low', 'medium', 'high'):
        lv = REASONING_LEVELS[k]
        levels.append({
            'id': lv['id'],
            'label': lv['label'],
            'desc': lv['desc'],
        })
    return jsonify({
        'ok': True,
        'tiers': tiers,
        'reasoning_levels': levels,
        'rag_sources': [c['title'] for c in DIPRE_RAG_CHUNKS],
        'guard_enabled': bool(discord_guard.enabled),
    })


@ai_bp.route('/api/ai/chat', methods=['POST'])
@login_required
def api_ai_chat():
    """Xử lý hội thoại Ask DIPRE (Scoped RAG + Live Telemetry + Rate-Safe Guard + 3x3 routing)."""
    user_id = session.get('user_id', 'anon')
    username = session.get('discord_username') or session.get('username') or 'Operator'

    allowed, guard_msg, retry_after = web_ai_guard.check_and_consume(str(user_id))
    if not allowed:
        return jsonify({
            'ok': False,
            'error': guard_msg,
            'retry_after': retry_after,
            'rate_limited': True,
        }), 429

    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'ok': False, 'error': 'Vui lòng nhập nội dung câu hỏi.'}), 400
    if len(message) > 3000:
        return jsonify({'ok': False, 'error': 'Tin nhắn quá dài (tối đa 3000 ký tự).'}), 400

    tier = normalize_tier(data.get('tier'))
    reasoning_level = normalize_reasoning_level(data.get('reasoning_level'))
    workspace_hint = (data.get('workspace') or '').strip()[:32]
    raw_history = data.get('history') or []

    rag_context, rag_topics = retrieve_rag_context(message, workspace_hint=workspace_hint)
    live_telemetry = _collect_live_telemetry()
    system_prompt = build_dipre_web_system_prompt(
        rag_context=rag_context,
        workspace_hint=workspace_hint,
        username=str(username),
        reasoning_level=reasoning_level,
        live_telemetry=live_telemetry,
    )

    messages = [{'role': 'system', 'content': system_prompt}]
    if isinstance(raw_history, list):
        for item in raw_history[-10:]:
            if not isinstance(item, dict):
                continue
            r = item.get('role')
            c = (item.get('content') or '').strip()
            if r in ('user', 'assistant') and c:
                messages.append({'role': r, 'content': c[:2500]})

    messages.append({'role': 'user', 'content': message})

    res = call_dipre_ai(messages, tier=tier, reasoning_level=reasoning_level)
    if not res['ok']:
        return jsonify({
            'ok': False,
            'error': f"Ask DIPRE tạm thời quá tải ({res['error']}). Vui lòng thử lại sau vài giây.",
            'tier': res['tier'],
            'reasoning_level': res['reasoning_level'],
            'latency_ms': res['latency_ms'],
        }), 502

    try:
        track_feature_use(user_id, 'ai')
    except Exception:
        pass

    return jsonify({
        'ok': True,
        'reply': res['text'],
        'tier': res['tier'],
        'tier_name': res['tier_name'],
        'reasoning_level': res['reasoning_level'],
        'reasoning_label': res['reasoning_label'],
        'latency_ms': res['latency_ms'],
        'rag_topics': rag_topics,
        'guard_enabled': bool(discord_guard.enabled),
    })


@ai_bp.route('/api/ai/inbox-assist', methods=['POST'])
@login_required
def api_ai_inbox_assist():
    """Tóm tắt đoạn hội thoại DM/Group trong Vault & Inbox và gợi ý 3 câu trả lời nhanh."""
    user_id = session.get('user_id', 'anon')
    username = session.get('discord_username') or session.get('username') or 'Operator'

    allowed, guard_msg, retry_after = web_ai_guard.check_and_consume(str(user_id))
    if not allowed:
        return jsonify({
            'ok': False,
            'error': guard_msg,
            'retry_after': retry_after,
            'rate_limited': True,
        }), 429

    data = request.get_json(silent=True) or {}
    thread_name = (data.get('thread_name') or 'Hội thoại').strip()[:80]
    raw_msgs = data.get('messages') or []
    if not isinstance(raw_msgs, list) or not raw_msgs:
        return jsonify({'ok': False, 'error': 'Chưa có tin nhắn nào trong hội thoại để phân tích.'}), 400

    transcript_lines = []
    for m in raw_msgs[-15:]:
        if not isinstance(m, dict):
            continue
        author = str(m.get('author_name') or m.get('author') or 'User')[:32]
        content = str(m.get('content') or '').strip()[:300]
        if content:
            transcript_lines.append(f"{author}: {content}")

    if not transcript_lines:
        return jsonify({'ok': False, 'error': 'Hội thoại chỉ có ảnh/embed, chưa có nội dung chữ để tóm tắt.'}), 400

    sys_prompt = (
        f"Bạn là Ask DIPRE hỗ trợ trả lời tin nhắn Discord cho {username}.\n"
        "Hãy đọc đoạn chat sau và trả về DUY NHẤT 1 JSON hợp lệ (không bọc markdown thừa nếu không cần) theo đúng cấu trúc:\n"
        '{"summary": "Tóm tắt ngắn gọn 1-2 câu nội dung chính bằng tiếng Việt", "suggestions": ["Câu trả lời gợi ý 1 (tự nhiên, ngắn gọn)", "Câu trả lời gợi ý 2", "Câu trả lời gợi ý 3"]}'
    )
    user_prompt = f"Hội thoại với: {thread_name}\n\n" + "\n".join(transcript_lines)

    res = call_dipre_ai(
        [{'role': 'system', 'content': sys_prompt}, {'role': 'user', 'content': user_prompt}],
        tier='flash',
        reasoning_level='low',
    )
    if not res['ok']:
        return jsonify({'ok': False, 'error': f"Ask DIPRE tạm bận ({res['error']})."}), 502

    raw_txt = res['text'].strip()
    summary = raw_txt
    suggestions = []
    try:
        m_json = re.search(r'\{[\s\S]*\}', raw_txt)
        if m_json:
            parsed = json.loads(m_json.group(0))
            if isinstance(parsed, dict):
                summary = str(parsed.get('summary') or '').strip() or summary
                sug = parsed.get('suggestions') or []
                if isinstance(sug, list):
                    suggestions = [str(s).strip() for s in sug if str(s).strip()][:3]
    except Exception:
        pass

    return jsonify({
        'ok': True,
        'summary': summary,
        'suggestions': suggestions,
        'latency_ms': res['latency_ms'],
    })
