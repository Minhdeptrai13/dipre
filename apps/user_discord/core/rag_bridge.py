# -*- coding: utf-8 -*-
"""
Safe UserBot Data RAG Bridge (`apps/user_discord/core/rag_bridge.py`).

Nhiệm vụ:
- Làm cầu nối CHỈ-ĐỌC theo Allowlist giữa dữ liệu người dùng thực tế trong `apps/user_discord/data/`
  và trí nhớ ngữ cảnh của AI trong UserBot (`modules/ai.py`).
- Cung cấp ánh xạ rõ ràng: mỗi trường dữ liệu nằm ở file nào và liên kết với module/lệnh nào.
- BẢO MẬT TUYỆT ĐỐI: CẤM đọc hoặc trả ra `config.json`, `.env`, token, API keys, mật khẩu,
  hoặc nội dung hội thoại riêng tư `ai_memory.json`.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Các file bị CẤM TUYỆT ĐỐI qua cầu nối RAG
BLOCKED_SENSITIVE_FILES = {
    "config.json",
    ".env",
    "ai_memory.json",
    "app.db",
    "database.db",
    "users.db",
    "discord_rpg.db",
}

# Bản đồ liên kết giữa Data Field / File <-> Module phụ trách <-> Lệnh điều khiển
DATA_MODULE_LINKS: List[Dict[str, Any]] = [
    {
        "topic": "ban",
        "keywords": ["ban", "cấm", "khóa", "trục xuất", "banlist", "unban", "punish", "phạt"],
        "file_pattern": "data/<bot_uid>_setting.json (ban_list, temp_punishments)",
        "module": "core/bot_sys.py (System Admin & Moderation)",
        "commands": "bot ban @user [time], bot unban @user, bot banlist",
    },
    {
        "topic": "moderation",
        "keywords": ["mute", "câm", "voice", "cam", "camera", "block", "chặn", "skip", "bad", "tục", "chửi", "lọc"],
        "file_pattern": "data/<bot_uid>_setting.json (mute_voice_list, cam_list, block_list, skip_list, bad_words)",
        "module": "core/bot_sys.py & modules/voice.py",
        "commands": "bot mute/unmute/mutelist, bot cam/uncam, bot block/unblock, bot skip, bot badword",
    },
    {
        "topic": "permissions",
        "keywords": ["admin", "admintris", "mod", "quyền", "server", "guild", "active", "bật", "tắt", "bot"],
        "file_pattern": "data/<bot_uid>_setting.json (admintris, admins, settings/guild_active)",
        "module": "core/bot_sys.py & core/alias.py",
        "commands": "bot on, bot off, bot status, bot addadmin, alias",
    },
    {
        "topic": "ai",
        "keywords": ["ai", "model", "flash", "standard", "pro", "think", "suy nghĩ", "tư duy", "memory", "nhớ"],
        "file_pattern": "data/ai_settings.json (current_model, reasoning_level, active_guilds)",
        "module": "modules/ai.py (AICog)",
        "commands": "ai <hỏi>, ai model [flash|standard|pro], ai think [low|medium|high], ai on/off, ai status, ai clear",
    },
    {
        "topic": "afk",
        "keywords": ["afk", "treo", "vắng", "bận", "ngủ"],
        "file_pattern": "data/<bot_uid>_afk.json",
        "module": "modules/afk.py (AFKCog)",
        "commands": "afk [lý do], unafk",
    },
    {
        "topic": "voice",
        "keywords": ["voice", "join", "phòng", "thoại", "nhạc", "play", "lavalink"],
        "file_pattern": "data/<bot_uid>_voice.json",
        "module": "modules/join.py & modules/voice.py",
        "commands": "join <channel_id>, leave, play <bài hát>",
    },
    {
        "topic": "prefix_alias",
        "keywords": ["prefix", "tiền tố", "alias", "viết tắt", "lệnh", "menu", "module", "data", "file"],
        "file_pattern": "data/<bot_uid>_prefix.json & data/<bot_uid>_setting.json (aliases)",
        "module": "utils/prefix.py, core/alias.py, modules/menu.py",
        "commands": "prefix [mới], alias, menu",
    },
    {
        "topic": "translate",
        "keywords": ["dịch", "dich", "translate", "ngôn ngữ"],
        "file_pattern": "data/translate_settings.json",
        "module": "modules/dich.py",
        "commands": "dich <text>",
    },
]


def _safe_read_json(path: Path) -> Dict[str, Any]:
    """Chỉ đọc JSON nằm trong DATA_DIR và không thuộc danh sách file nhạy cảm."""
    try:
        resolved = path.resolve()
        if resolved.name.lower() in BLOCKED_SENSITIVE_FILES:
            return {}
        data_root = DATA_DIR.resolve()
        if data_root not in resolved.parents:
            return {}
        if not resolved.exists() or not resolved.is_file():
            return {}
        raw = json.loads(resolved.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _resolve_display_name(uid_str: str, fallback_name: str = "", bot: Any = None, guild: Any = None) -> str:
    """Ưu tiên lấy tên hiển thị thật từ Guild/Bot cache thay cho chuỗi ID khô."""
    try:
        uid_int = int(str(uid_str).strip())
    except Exception:
        return fallback_name or str(uid_str)

    if guild is not None:
        try:
            m = guild.get_member(uid_int)
            if m:
                return getattr(m, "display_name", None) or getattr(m, "name", None) or fallback_name or str(uid_int)
        except Exception:
            pass
    if bot is not None:
        try:
            u = bot.get_user(uid_int)
            if u:
                return getattr(u, "display_name", None) or getattr(u, "name", None) or fallback_name or str(uid_int)
        except Exception:
            pass
    return fallback_name or f"User_{uid_str}"


def _format_punish_list(
    items: Dict[str, Any],
    temps: List[Dict[str, Any]],
    ptype: str,
    bot: Any = None,
    guild: Any = None,
) -> str:
    if not isinstance(items, dict) or not items:
        return "Trống (0 người)"
    now = time.time()
    out = []
    for uid_str, stored_name in list(items.items())[:25]:
        exp = None
        for p in temps or []:
            if isinstance(p, dict) and str(p.get("uid")) == str(uid_str) and p.get("type") == ptype:
                exp = p.get("expire")
                break
        if isinstance(exp, (int, float)):
            rem = int(exp - now)
            dur = f"còn {rem}s" if rem > 0 else "hết hạn/chờ dọn"
        else:
            dur = "Vĩnh viễn"
        disp = _resolve_display_name(str(uid_str), str(stored_name or ""), bot=bot, guild=guild)
        out.append(f"{disp} — tag: <@{uid_str}>, avatar_cmd: [[AVATAR:{uid_str}]] ({dur})")
    extra = f" ...(+{len(items) - 25} nữa)" if len(items) > 25 else ""
    return " | ".join(out) + extra


def _format_uid_list(uids: List[Any], bot: Any = None, guild: Any = None) -> str:
    if not uids:
        return "Trống"
    out = []
    for u in uids[:20]:
        us = str(u).strip()
        if not us:
            continue
        disp = _resolve_display_name(us, "", bot=bot, guild=guild)
        out.append(f"{disp} (<@{us}>, avt: [[AVATAR:{us}]])")
    return ", ".join(out) or "Trống"


def detect_query_topics(query: str) -> List[str]:
    q = (query or "").lower()
    matched = []
    for item in DATA_MODULE_LINKS:
        if any(kw in q for kw in item["keywords"]):
            matched.append(item["topic"])
    if any(w in q for w in ("avatar", "avt", "ảnh", "mặt", "profile", "tag", "mention")):
        matched.append("avatar_lookup")
    if any(w in q for w in ("config.json", "token", "password", "mật khẩu", "api key", "secret")):
        matched.append("blocked_secret")
    return matched


def build_userbot_rag_context(
    bot_uid: int,
    guild_id: Optional[int] = None,
    guild_name: Optional[str] = None,
    query: str = "",
    bot: Any = None,
    guild: Any = None,
) -> str:
    """
    Trích xuất ngữ cảnh dữ liệu sống (đã lọc an toàn) của UserBot + ánh xạ module + tên/tag/avatar.
    """
    topics = detect_query_topics(query)
    setting = _safe_read_json(DATA_DIR / f"{bot_uid}_setting.json") if bot_uid else {}
    ai_cfg = _safe_read_json(DATA_DIR / "ai_settings.json")
    afk_cfg = _safe_read_json(DATA_DIR / f"{bot_uid}_afk.json") if bot_uid else {}
    voice_cfg = _safe_read_json(DATA_DIR / f"{bot_uid}_voice.json") if bot_uid else {}
    prefix_cfg = _safe_read_json(DATA_DIR / f"{bot_uid}_prefix.json") if bot_uid else {}
    trans_cfg = _safe_read_json(DATA_DIR / "translate_settings.json")

    temps = setting.get("temp_punishments") if isinstance(setting.get("temp_punishments"), list) else []
    ban_list = setting.get("ban_list") if isinstance(setting.get("ban_list"), dict) else {}
    mute_list = setting.get("mute_voice_list") if isinstance(setting.get("mute_voice_list"), dict) else {}
    cam_list = setting.get("cam_list") if isinstance(setting.get("cam_list"), dict) else {}
    block_list = setting.get("block_list") if isinstance(setting.get("block_list"), dict) else {}
    skip_list = setting.get("skip_list") if isinstance(setting.get("skip_list"), dict) else {}
    bad_words = setting.get("bad_words") if isinstance(setting.get("bad_words"), list) else []
    admintris = setting.get("admintris") if isinstance(setting.get("admintris"), list) else []
    admins = setting.get("admins") if isinstance(setting.get("admins"), list) else []
    guild_settings = setting.get("settings") if isinstance(setting.get("settings"), dict) else {}
    if not guild_settings and isinstance(setting.get("guild_active"), dict):
        guild_settings = {k: {"bot_active": v} for k, v in setting.get("guild_active", {}).items()}

    # Xác định trạng thái server hiện tại
    cur_gid_str = str(guild_id) if guild_id else ""
    cur_bot_on = None
    if cur_gid_str and cur_gid_str in guild_settings:
        val = guild_settings[cur_gid_str]
        cur_bot_on = val.get("bot_active") if isinstance(val, dict) else bool(val)
    elif cur_gid_str and isinstance(setting.get("guild_active"), dict):
        cur_bot_on = bool(setting.get("guild_active", {}).get(cur_gid_str, False))

    ai_guilds = ai_cfg.get("active_guilds") if isinstance(ai_cfg.get("active_guilds"), dict) else {}
    cur_ai_on = bool(ai_guilds.get(cur_gid_str, False)) if cur_gid_str else True

    lines: List[str] = []

    # 1. Tổng quan dữ liệu sống của UserBot hiện tại (luôn có nhưng rất gọn)
    lines.append(
        f"[SNAPSHOT DỮ LIỆU USERBOT (UID `{bot_uid}`) — CHỈ ĐỌC QUA BRIDGE AN TOÀN]\n"
        f"- File chính: `data/{bot_uid}_setting.json` (liên kết `core/bot_sys.py`)\n"
        f"- Ban: {len(ban_list)} người | Mute Voice: {len(mute_list)} | Cam: {len(cam_list)} | Block: {len(block_list)} | Skip: {len(skip_list)}\n"
        f"- Quyền quản trị: {len(admintris)} Admintris, {len(admins)} Admins | Từ cấm (bad_words): {len(bad_words)}\n"
        f"- AI Config (`data/ai_settings.json` ↔ `modules/ai.py`): Model `{ai_cfg.get('current_model', 'standard')}`, Tư duy `{ai_cfg.get('reasoning_level', 'medium')}`, {sum(1 for v in ai_guilds.values() if v)} server bật AI auto-rep\n"
        f"- Server hiện tại: {guild_name or 'DM'} (`{cur_gid_str or 'DM'}`) — Bot Active: {cur_bot_on}, AI Auto-Rep: {cur_ai_on}"
    )

    # 2. Chi tiết theo chủ đề người dùng đang hỏi
    if not topics or "ban" in topics:
        lines.append(
            f"[CHI TIẾT DANH SÁCH BAN (`data/{bot_uid}_setting.json` → `ban_list`, `temp_punishments` | Module: `core/bot_sys.py` | Lệnh: `bot ban`, `bot unban`, `bot banlist`)]\n"
            f"- Danh sách đang bị ban ({len(ban_list)}): {_format_punish_list(ban_list, temps, 'ban', bot=bot, guild=guild)}"
        )

    if "moderation" in topics:
        lines.append(
            f"[CHI TIẾT MUTE / CAM / BLOCK / SKIP / BADWORDS (`data/{bot_uid}_setting.json` | Module: `core/bot_sys.py` & `modules/voice.py`)]\n"
            f"- Mute Voice ({len(mute_list)}): {_format_punish_list(mute_list, temps, 'mute', bot=bot, guild=guild)}\n"
            f"- Block ({len(block_list)}): {_format_punish_list(block_list, temps, 'block', bot=bot, guild=guild)}\n"
            f"- Cam ({len(cam_list)}): {_format_punish_list(cam_list, temps, 'cam', bot=bot, guild=guild)} | Skip ({len(skip_list)}): {_format_punish_list(skip_list, temps, 'skip', bot=bot, guild=guild)}\n"
            f"- Bad words ({len(bad_words)}): {', '.join(map(str, bad_words[:15])) if bad_words else 'Trống'}"
        )

    if "permissions" in topics:
        active_gids = [
            gid for gid, v in guild_settings.items()
            if (v.get("bot_active") if isinstance(v, dict) else bool(v))
        ]
        lines.append(
            f"[CHI TIẾT QUYỀN & SERVER (`data/{bot_uid}_setting.json` | Module: `core/bot_sys.py`, `core/alias.py`)]\n"
            f"- Admintris: {_format_uid_list(admintris, bot=bot, guild=guild)}\n"
            f"- Admins: {_format_uid_list(admins, bot=bot, guild=guild)}\n"
            f"- Server IDs đang bật bot ({len(active_gids)}): {', '.join(active_gids[:12]) or 'Chưa bật server nào'}"
        )

    # 2b. Resolve các UID được mention/nhắc trực tiếp trong câu hỏi để AI xem tên/avt/trạng thái
    mentioned_uids = list(dict.fromkeys(re.findall(r"(?<!\d)(\d{17,20})(?!\d)", query or "")))[:5]
    if mentioned_uids:
        m_lines = []
        for muid in mentioned_uids:
            disp = _resolve_display_name(muid, "", bot=bot, guild=guild)
            flags = []
            if muid in ban_list:
                flags.append("ĐANG BỊ BAN")
            if muid in mute_list:
                flags.append("MUTE VOICE")
            if muid in block_list:
                flags.append("BLOCK")
            if any(str(x) == muid for x in admintris):
                flags.append("ADMINTRIS")
            elif any(str(x) == muid for x in admins):
                flags.append("ADMIN")
            st = ", ".join(flags) if flags else "Bình thường"
            m_lines.append(f"• {disp} — tag: <@{muid}>, avatar_cmd: [[AVATAR:{muid}]] | Trạng thái: {st}")
        lines.append("[NGƯỜI DÙNG ĐƯỢC NHẮC TRONG CÂU HỎI]\n" + "\n".join(m_lines))

    if "afk" in topics:
        afk_summary = json.dumps(afk_cfg, ensure_ascii=False)[:350] if afk_cfg else "Chưa bật AFK hoặc chưa có file `<uid>_afk.json`"
        lines.append(f"[DỮ LIỆU AFK (`data/{bot_uid}_afk.json` ↔ `modules/afk.py` | Lệnh: `afk`, `unafk`)]: {afk_summary}")

    if "voice" in topics:
        voice_summary = json.dumps(voice_cfg, ensure_ascii=False)[:350] if voice_cfg else "Chưa lưu cấu hình treo voice (`<uid>_voice.json`)"
        lines.append(f"[DỮ LIỆU VOICE (`data/{bot_uid}_voice.json` ↔ `modules/join.py`, `modules/voice.py`)]: {voice_summary}")

    if "translate" in topics:
        tr_summary = json.dumps(trans_cfg, ensure_ascii=False)[:300] if trans_cfg else "Mặc định (`translate_settings.json` trống)"
        lines.append(f"[DỮ LIỆU DỊCH (`data/translate_settings.json` ↔ `modules/dich.py`)]: {tr_summary}")

    if "prefix_alias" in topics or not topics:
        px_str = prefix_cfg.get("prefix") if isinstance(prefix_cfg, dict) else None
        link_rows = "\n".join(
            f"  • {item['file_pattern']} ↔ `{item['module']}` (lệnh: `{item['commands']}`)"
            for item in DATA_MODULE_LINKS
        )
        lines.append(
            f"[LIÊN KẾT DATA ↔ MODULE TRONG USERBOT (prefix file: `{px_str or 'mặc định'}`)]\n"
            f"{link_rows}"
        )

    if "blocked_secret" in topics:
        lines.append(
            "[CẢNH BÁO BẢO MẬT BRIDGE]: Người dùng đang hỏi tới file/thông tin nhạy cảm (`config.json`, token, API key, mật khẩu). "
            "Cầu nối đã KHÓA quyền truy cập `config.json` và mọi bí mật. Hãy từ chối khéo và giải thích rằng vì bảo mật, AI chỉ đọc được dữ liệu vận hành trong `data/*_setting.json` qua Bridge an toàn."
        )

    return "\n\n".join(lines)
