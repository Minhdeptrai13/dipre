"""
DIPRE AI Core Engine — Keyless Kilo Gateway + Scoped DIPRE RAG + Rate-Limit Guard.
Rebranded completely under DIPRE tiers (DIPRE Flash / DIPRE Pro) with zero third-party model leakage.
"""
import json
import ssl
import time
import threading
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional, Tuple

KILO_GATEWAY_URL = "https://api.kilo.ai/api/gateway/chat/completions"

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

DIPRE_TIERS: Dict[str, Dict[str, Any]] = {
    "flash": {
        "id": "flash",
        "name": "DIPRE Flash",
        "badge": "FLASH",
        "tagline": "Phản hồi siêu tốc (~3-6s) cho hỏi đáp nhanh, lệnh UserBot & tinh chỉnh cấu hình.",
        "candidates": [
            {
                "model_id": "baidu/ernie-5.5-flash-preview:free",
                "max_tokens": 1800,
                "temperature": 0.45,
                "reasoning": {"effort": "low"},
                "timeout": 20.0,
            },
            {
                "model_id": "particle-ai/particle-1:free",
                "max_tokens": 2048,
                "temperature": 0.45,
                "reasoning": None,  # Do NOT send reasoning.effort (avoids 429 on particle-1)
                "timeout": 22.0,
            },
            {
                "model_id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
                "max_tokens": 2048,
                "temperature": 0.45,
                "reasoning": None,
                "timeout": 26.0,
            },
        ],
    },
    "pro": {
        "id": "pro",
        "name": "DIPRE Pro",
        "badge": "PRO",
        "tagline": "Suy luận chuyên sâu (~9-16s) cho kiến trúc RPC, Anti-Ban, gỡ lỗi & JSON cấu hình.",
        "candidates": [
            {
                "model_id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
                "max_tokens": 2200,
                "temperature": 0.35,
                "reasoning": None,
                "timeout": 28.0,
            },
            {
                "model_id": "nvidia/nemotron-3-ultra-550b-a55b:free",
                "max_tokens": 2400,
                "temperature": 0.35,
                "reasoning": {"effort": "low"},
                "timeout": 34.0,
            },
            {
                "model_id": "baidu/ernie-5.5-flash-preview:free",
                "max_tokens": 2000,
                "temperature": 0.35,
                "reasoning": {"effort": "low"},
                "timeout": 22.0,
            },
        ],
    },
}

# Scoped Knowledge Base (RAG Chunks) cho DIPRE Studio v5.0 & UserBot Core
DIPRE_RAG_CHUNKS: List[Dict[str, Any]] = [
    {
        "id": "overview_arch",
        "title": "Kiến trúc DIPRE Studio v5.0",
        "keywords": ["dipre", "tổng quan", "overview", "studio", "tab", "workspace", "bắt đầu", "hướng dẫn", "tính năng"],
        "content": (
            "DIPRE Studio v5.0 gồm 6 Workspace chính: "
            "(1) Tổng Quan (phím 1): telemetry gateway, ping, trạng thái tài khoản, hoạt động gần đây; "
            "(2) Presence Studio (phím 2): Custom Rich Presence RPC, YouTube/Music Sync, Custom Status & Rotator; "
            "(3) UserBot Core (phím 3): bật/tắt UserBot, prefix lệnh, danh bạ 34 Cogs; "
            "(4) Voice & Audio (phím 4): treo Voice AFK 24/7, mute/deaf, auto-reconnect, soundboard; "
            "(5) Automation (phím 5): Auto Quest Completer, Nitro & Vanity Sniper Radar, Anti-Ban Shield; "
            "(6) Vault & Inbox (phím 6): quản lý đa Token Discord và đọc DM/Group Inbox thực tế."
        ),
    },
    {
        "id": "presence_rpc",
        "title": "Presence Studio (RPC & Custom Status)",
        "keywords": ["presence", "rpc", "status", "rich presence", "youtube", "game", "playing", "streaming", "button", "ảnh", "asset", "rotator", "lyric"],
        "content": (
            "Presence Studio (`/api/rpc/*`): hỗ trợ set Custom Rich Presence (Application ID, Type: Playing/Streaming/Listening/Watching/Competing, "
            "Details, State, Large/Small Image URL hoặc Asset Key, tối đa 2 nút bấm URL, Timestamp đếm giờ) và YouTube Rich Presence Sync. "
            "Ngoài ra có Custom Status & Rotator đổi dòng trạng thái + emoji theo chu kỳ (giữ chu kỳ >= 15-30s để tránh rate limit Discord)."
        ),
    },
    {
        "id": "voice_farm",
        "title": "Voice & Audio 24/7",
        "keywords": ["voice", "thoại", "afk", "treo", "kênh", "channel", "mute", "deaf", "mic", "tai nghe", "lavalink", "nhạc", "farm"],
        "content": (
            "Voice & Audio (`/api/voice/channels`, `/api/voice/start`, `/api/voice/stop`): cho phép kết nối WebSocket Voice Gateway treo kênh thoại 24/7, "
            "tùy chọn Self-Mute / Self-Deaf, chọn tài khoản chính hoặc phụ. Khuyến nghị bật Anti-Ban Guard để tự giãn cách khi reconnect, "
            "không nhảy kênh liên tục dưới 10-15 giây."
        ),
    },
    {
        "id": "quest_auto",
        "title": "Auto Quest Completer",
        "keywords": ["quest", "nhiệm vụ", "auto quest", "decor", "orbs", "reward", "quà"],
        "content": (
            "Auto Quest (`/api/quest/*`): tự động quét danh sách Discord Quests đang mở trên tài khoản, mô phỏng heartbeat tiến độ hợp lệ "
            "(Play game / Watch video / Stream) theo đúng nhịp server Discord yêu cầu, hạn chế gửi heartbeat dồn dập."
        ),
    },
    {
        "id": "sniper_antiban",
        "title": "Sniper Radar & Anti-Ban Guard",
        "keywords": ["sniper", "nitro", "vanity", "gift", "anti-ban", "antiban", "ban", "rate limit", "ratelimit", "429", "bảo vệ", "an toàn", "guard", "delay", "token"],
        "content": (
            "Sniper Radar (`/api/sniper/*`) & Anti-Ban Shield (`core/discord_guard.py`): "
            "Mọi thao tác ghi/redeem/react qua Discord REST đều đi qua `DiscordAntiBanGuard`: "
            "giới hạn tối đa 16 write requests/phút mỗi token (30 read/phút), min spacing >= 0.4s, tự chèn jitter ngẫu nhiên (0.18s–0.65s). "
            "Nếu Discord trả HTTP 429 (`Retry-After`), 401/403 hoặc yêu cầu Captcha/Verify, Circuit Breaker tự động khóa cooldown ngay lập tức "
            "(15s+ hoặc 45-60s khi 429 lặp lại) để cứu tài khoản khỏi bị ban/khóa."
        ),
    },
    {
        "id": "userbot_cogs",
        "title": "UserBot Core & Hệ thống Lệnh",
        "keywords": ["userbot", "bot", "lệnh", "command", "prefix", "cogs", "ai", "model", "flash", "pro", "clear", "tiktok", "yt", "afk", "menu"],
        "content": (
            "UserBot Core (`/api/userbot/*`, `apps/user_discord/modules/ai.py`): hỗ trợ quản lý qua Web hoặc gõ trực tiếp trong Discord với prefix riêng (mặc định `!`). "
            "Nhóm lệnh AI trong UserBot: `<prefix>ai <câu hỏi>`, `<prefix>ai model` (xem bảng bậc AI), `<prefix>ai model flash` hoặc `pro` (Admin cấp cao đổi bậc), "
            "`<prefix>ai clear` (xoá trí nhớ kênh), `<prefix>ai on/off` (bật/tắt tự rep khi tag @bot), `<prefix>ai status`. "
            "Các tiện ích khác: `tiktok`, `yt`, `fb`, `scl` (tải media), `join`/`leave`/`play` (Voice & Lavalink), `quest`, `afk`, `info`, `server`, `crypto`, `weather`, `mail gen`."
        ),
    },
    {
        "id": "vault_inbox",
        "title": "Vault Đa Token & Live Inbox",
        "keywords": ["vault", "inbox", "dm", "tin nhắn", "tài khoản", "multi", "switch", "đăng nhập", "qr", "oauth"],
        "content": (
            "Vault & Inbox: nạp và chuyển đổi nhanh giữa tài khoản chính và các tài khoản phụ (lưu bảo mật phiên), "
            "đọc luồng Direct Message / Group DM trực tiếp mà không mở tab Discord riêng."
        ),
    },
]


def normalize_tier(tier: Optional[str]) -> str:
    t = (tier or "flash").strip().lower()
    if t in ("pro", "deep", "reasoning", "ultra", "nano", "nemotron"):
        return "pro"
    return "flash"


def retrieve_rag_context(query: str, workspace_hint: str = "") -> Tuple[str, List[str]]:
    """Tìm các mảnh kiến thức DIPRE liên quan nhất tới câu hỏi + workspace hiện tại."""
    q = f"{query or ''} {workspace_hint or ''}".lower()
    scored: List[Tuple[int, Dict[str, Any]]] = []
    for chunk in DIPRE_RAG_CHUNKS:
        score = 0
        for kw in chunk["keywords"]:
            if kw in q:
                score += 2 if len(kw) > 4 else 1
        if workspace_hint and chunk["id"].startswith(workspace_hint.lower()[:4]):
            score += 2
        scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [c for s, c in scored[:4] if s > 0]
    if not selected:
        selected = DIPRE_RAG_CHUNKS[:3]

    context_lines = [f"- [{c['title']}]: {c['content']}" for c in selected]
    topics = [c["title"] for c in selected]
    return "\n".join(context_lines), topics


def build_dipre_web_system_prompt(rag_context: str, workspace_hint: str = "", username: str = "User") -> str:
    ws_note = f"Người dùng đang mở tab `{workspace_hint}` trong DIPRE Studio v5.0." if workspace_hint else ""
    return (
        f"Bạn là **DIPRE AI**, trợ lý kỹ thuật độc quyền tích hợp trong **DIPRE Studio v5.0**.\n"
        f"Người dùng hiện tại: {username}. {ws_note}\n\n"
        f"PHẠM VI HOẠT ĐỘNG (RAG IN-SCOPE):\n"
        f"1. Chỉ tập trung hỗ trợ các tính năng, cấu hình, lệnh UserBot, tối ưu an toàn/anti-ban rate-limit, và giải đáp kỹ thuật xoay quanh DIPRE Studio & Discord.\n"
        f"2. TUYỆT ĐỐI KHÔNG tự nhận là mô hình bên thứ ba (không nhắc tên Baidu, Ernie, NVIDIA, Nemotron, Particle, Kilo, OpenRouter, Qwen). Bạn là DIPRE AI.\n"
        f"3. KHÔNG bịa tính năng không có trong hệ thống; ưu tiên hướng dẫn đúng tên tab, nút bấm, cấu hình an toàn để người dùng không bị Discord rate-limit (429) hay khóa tài khoản.\n"
        f"4. Nếu người dùng hỏi ngoài phạm vi DIPRE Studio (ví dụ viết bài văn, giải toán phổ thông, tin tức giải trí...) hoặc yêu cầu vượt CAPTCHA / spam phá hoại, hãy từ chối ngắn gọn và kéo về hỗ trợ các công cụ hợp lệ trong DIPRE Studio.\n"
        f"5. Trả lời bằng tiếng Việt sắc nét, chuẩn kỹ thuật, trình bày Markdown sạch sẽ (danh sách rõ ràng, JSON/code block khi cần).\n\n"
        f"TRI THỨC NỘI BỘ DIPRE (RAG CONTEXT):\n"
        f"{rag_context}"
    )


class WebAIRateGuard:
    """Bảo vệ chống spam / quá tải AI Gateway cho từng user web (Rate-Limit Guard)."""

    def __init__(self, max_per_min: int = 12, min_spacing: float = 1.2):
        self._lock = threading.Lock()
        self._max_per_min = max_per_min
        self._min_spacing = min_spacing
        self._buckets: Dict[str, Dict[str, Any]] = {}

    def check_and_consume(self, user_key: str) -> Tuple[bool, str, float]:
        now = time.time()
        key = str(user_key or "anon")
        with self._lock:
            b = self._buckets.setdefault(key, {"ts": [], "last": 0.0})
            b["ts"] = [t for t in b["ts"] if now - t < 60.0]

            elapsed = now - b["last"]
            if elapsed < self._min_spacing:
                wait = round(self._min_spacing - elapsed, 1)
                return False, f"Rate-Safe Guard: Chậm lại {wait}s giữa các lượt gửi.", wait

            if len(b["ts"]) >= self._max_per_min:
                wait = max(1.0, round(60.0 - (now - b["ts"][0]), 1))
                return False, f"Rate-Safe Guard: Đạt giới hạn {self._max_per_min} câu/phút, thử lại sau {wait}s.", wait

            b["last"] = now
            b["ts"].append(now)
            return True, "", 0.0


web_ai_guard = WebAIRateGuard()


def call_dipre_ai(
    messages: List[Dict[str, str]],
    tier: str = "flash",
    max_tokens_override: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Gọi Kilo Gateway theo bậc DIPRE Flash / DIPRE Pro kèm fallback tự động.
    Trả về dict: {"ok": bool, "text": str, "tier": str, "latency_ms": int, "error": str}
    """
    norm_tier = normalize_tier(tier)
    tier_cfg = DIPRE_TIERS[norm_tier]
    t_start = time.perf_counter()
    last_err = ""

    for cand in tier_cfg["candidates"]:
        payload: Dict[str, Any] = {
            "model": cand["model_id"],
            "messages": messages,
            "max_tokens": max_tokens_override or cand["max_tokens"],
            "temperature": cand["temperature"],
        }
        if cand.get("reasoning") is not None:
            payload["reasoning"] = cand["reasoning"]

        req = urllib.request.Request(
            KILO_GATEWAY_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "DIPRE-Studio/5.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=float(cand.get("timeout", 22.0)), context=_SSL_CTX) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                choices = data.get("choices") or []
                if choices:
                    msg = choices[0].get("message") or {}
                    content = (msg.get("content") or "").strip()
                    if content:
                        latency_ms = int((time.perf_counter() - t_start) * 1000)
                        return {
                            "ok": True,
                            "text": content,
                            "tier": norm_tier,
                            "tier_name": tier_cfg["name"],
                            "latency_ms": latency_ms,
                            "error": "",
                        }
                    last_err = "Empty model output"
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            continue
        except Exception as e:
            last_err = str(e)[:120]
            continue

    latency_ms = int((time.perf_counter() - t_start) * 1000)
    return {
        "ok": False,
        "text": "",
        "tier": norm_tier,
        "tier_name": tier_cfg["name"],
        "latency_ms": latency_ms,
        "error": last_err or "Gateway busy",
    }
