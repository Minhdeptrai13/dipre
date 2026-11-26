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
    """Xử lý hội thoại Ask DIPRE (Scoped RAG + Rate-Safe Guard + 3x3 Tier/Reasoning routing)."""
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
    system_prompt = build_dipre_web_system_prompt(
        rag_context=rag_context,
        workspace_hint=workspace_hint,
        username=str(username),
        reasoning_level=reasoning_level,
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
