# -*- coding: utf-8 -*-
"""RUNTIME - Quan ly vong doi selfbot trong CUNG mot process.

Muc dich
--------
* main.py: dang ky cac bot khoi dong tu config.json vao so LIVE.
* core/genesis.py: spawn (bat bot len NGAY) / shutdown (tat bot) theo lenh
  `gene start` / `gene stop` -> KHONG can restart ca he thong.

Moi bot duoc spawn se:
  - bind prefix rieng (utils/prefix.py) => dung lenh bang prefix cua chinh no.
  - nap day du utils/core/modules (giong main.py) => co du moi lenh.
  - co listener on_message rieng -> process_commands.

Khoa so: LIVE[token] = {"bot": Bot, "task": Task|None, "prefix": str, "name": str}
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from discord.ext import commands

try:
    from apps.user_discord.utils.prefix import bind, apply_help
except ImportError:  # fallback khi sys.path khac
    from utils.prefix import bind, apply_help

BASE_DIR = Path(__file__).resolve().parent.parent          # apps/user_discord
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# token -> {bot, task, prefix, name}
LIVE: Dict[str, Dict[str, Any]] = {}


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except Exception:
        try:
            print(str(msg).encode("ascii", "ignore").decode("ascii"), flush=True)
        except Exception:
            pass


def _tok(token: Any) -> str:
    return "" if token is None else str(token).strip()


def is_live(token: Any) -> bool:
    """Bot cua token nay dang chay (va chua dong) khong?"""
    t = _tok(token)
    if not t:
        return False
    ent = LIVE.get(t)
    bot = ent.get("bot") if ent else None
    try:
        return bool(bot and not bot.is_closed())
    except Exception:
        return False


def get_live(token: Any) -> Optional[Any]:
    ent = LIVE.get(_tok(token)) or {}
    return ent.get("bot")


def find_live_bot(token: Optional[str] = None, uid: Optional[Any] = None, bot_id: Optional[str] = None) -> Optional[commands.Bot]:
    """Tìm bot đang chạy trong tiến trình: hỗ trợ tìm theo token (raw hoặc mã hoá), UID hoặc bot_id."""
    if token:
        t = _tok(token)
        b = get_live(t)
        if b:
            return b
        try:
            from apps.shared.token_crypto import decrypt
            dec_t = decrypt(t)
            if dec_t and dec_t != t:
                b = get_live(dec_t)
                if b:
                    return b
        except Exception:
            pass

    uid_int = None
    if uid:
        try:
            uid_int = int(str(uid).strip())
        except Exception:
            uid_int = None

    for item in LIVE.values():
        cand = item.get("bot")
        if not cand:
            continue
        if uid_int is not None:
            c_uid = getattr(getattr(cand, "user", None), "id", None) or getattr(cand, "_own_bot_uid", None)
            if c_uid and int(c_uid) == uid_int:
                return cand
        if bot_id:
            c_bid = getattr(cand, "_own_bot_id", None)
            if c_bid and str(c_bid).upper() == str(bot_id).upper():
                return cand
    return None


def register(token: Any, bot: Any, prefix: str = "", name: str = "") -> None:
    """Dang ky bot da chay (do main.py khoi dong) vao so LIVE."""
    t = _tok(token)
    if t:
        LIVE[t] = {"bot": bot, "task": None, "prefix": prefix, "name": name}


def build_bot(token: str, prefix: str, name: str = "") -> commands.Bot:
    """Tao doi tuong Bot + bind prefix rieng (chua ket noi)."""
    p = str(prefix).strip() if prefix is not None else ""
    base_prefixes = [p] + ([] if (not p or p.endswith(" ")) else [f"{p} "])

    def _prefix_callable(b, msg):
        try:
            from apps.user_discord.utils.prefix import get_prefixes
            return get_prefixes(b)
        except Exception:
            try:
                from utils.prefix import get_prefixes
                return get_prefixes(b)
            except Exception:
                return base_prefixes

    bot = commands.Bot(
        command_prefix=_prefix_callable,
        self_bot=True,
        chunk_guilds_at_startup=False,
    )
    try:
        bind(bot, prefix=p, name=name, token=token)
    except Exception as exc:
        _log(f"[RUNTIME] prefix bind warning: {type(exc).__name__}")
    bot._skip_check = lambda x, y: False
    return bot


async def _load_extensions(bot: commands.Bot) -> Dict[str, list]:
    """Nap toan bo utils/core/modules cho bot (giong main.py)."""
    loaded: Dict[str, list] = {"utils": [], "core": [], "modules": []}
    for sec in ("utils", "core", "modules"):
        sec_dir = BASE_DIR / sec
        if not sec_dir.exists():
            continue
        init_file = sec_dir / "__init__.py"
        if not init_file.exists():
            try:
                init_file.write_text("", encoding="utf-8")
            except Exception:
                pass
        for root, _, files in os.walk(str(sec_dir)):
            for file in sorted(files):
                if not file.endswith(".py") or file.startswith("__"):
                    continue
                rel = os.path.relpath(os.path.join(root, file), str(PROJECT_ROOT))
                ext_name = rel.replace(os.sep, ".")[:-3]
                try:
                    await bot.load_extension(ext_name)
                    loaded.setdefault(sec, []).append(ext_name)
                except Exception:
                    try:
                        rel_local = os.path.relpath(os.path.join(root, file), str(BASE_DIR))
                        local_ext = rel_local.replace(os.sep, ".")[:-3]
                        await bot.load_extension(local_ext)
                        loaded.setdefault(sec, []).append(local_ext)
                    except Exception:
                        pass
    return loaded


async def spawn(token: str, prefix: str, name: str = "", timeout: float = 30.0) -> Tuple[bool, Any, str]:
    """Bat bot len ngay (login + nap lenh + prefix rieng). Tra (ok, bot|None, msg)."""
    t = _tok(token)
    if not t:
        return False, None, "token trống"
    if is_live(t):
        return True, get_live(t), "đã chạy sẵn"

    bot = build_bot(t, prefix, name)
    state: Dict[str, Any] = {"loaded": False, "error": None}
    ready = asyncio.Event()

    @bot.event
    async def on_ready():
        if state["loaded"]:
            return
        state["loaded"] = True
        try:
            from apps.user_discord.utils.lavalink_voice import LavalinkManager
            await LavalinkManager.get_instance(bot).initialize()
        except Exception:
            pass
        try:
            await _load_extensions(bot)
        except Exception:
            pass
        try:
            apply_help(bot)
        except Exception:
            pass
        try:
            from apps.user_discord.core.alias import apply_bot_saved_aliases
            apply_bot_saved_aliases(bot)
        except Exception:
            pass
        ready.set()
        _log(f"[RUNTIME] Bot '{name or '?'}' ({bot.user}) da ONLINE (prefix rieng).")

    @bot.event
    async def on_message(message):
        if not message.author:
            return
        # Bot CHINH (prime) gui lenh cho bot PHU: chi rep khi prime la
        # Admin/Admin cap cao CUA BOT NAY — khong thi cam nín (khong icon, khong rep).
        try:
            try:
                from apps.user_discord.core.bot_sys import prime_reply_allowed as _gate
            except ImportError:
                from core.bot_sys import prime_reply_allowed as _gate  # type: ignore
            if not _gate(bot, message.author.id):
                return
        except Exception:
            pass
        # Tha icon CHI KHI tin la LENH HOP LE + duoc phep tra loi
        # (Staff hoac bot ON) — khong tha cho tin thuong chi do bat ky prefix nao.
        try:
            try:
                from apps.user_discord.core.bot_sys import should_autoreact as _allow_react
            except ImportError:
                from core.bot_sys import should_autoreact as _allow_react  # type: ignore
            if _allow_react(bot, message):
                try:
                    try:
                        from apps.user_discord.utils.autorep import autoreact as _react
                    except ImportError:
                        from utils.autorep import autoreact as _react  # type: ignore
                    await _react(message)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            try:
                from apps.user_discord.utils.message_log import should_log_message
            except ImportError:
                from utils.message_log import should_log_message
            from apps.user_discord.core.bot_sys import is_bot_active as _is_on
            _ok, _ = should_log_message(bot, message, bot_on_checker=lambda _gid: _is_on(bot, _gid))
            if _ok:
                try:
                    from apps.user_discord.main import (
                        RollingMessageLogLimiter as _Limiter,
                        format_message_box as _fmt,
                    )
                    _lim = getattr(bot, "_message_log_limiter", None)
                    if _lim is None:
                        _lim = _Limiter("USER_DISCORD:RUNTIME")
                        bot._message_log_limiter = _lim
                    if _lim.should_log():
                        print(_fmt(message, _), flush=True)
                except Exception:
                    pass
        except Exception:
            pass
        if message.guild:
            try:
                from apps.user_discord.core.bot_sys import is_bot_active, is_staff as sys_is_staff
                active = is_bot_active(bot, message.guild.id)
                staff = (message.author.id == bot.user.id) or sys_is_staff(bot, message.author.id)
                if not staff and hasattr(bot, "is_staff") and callable(bot.is_staff):
                    try:
                        staff = bot.is_staff(message.author.id)
                    except Exception:
                        pass
                from apps.user_discord.core.bot_sys import is_internal_bot
                if not active and not staff:


                    # Server đang BOT OFF:
                    # TUYỆT ĐỐI CHỈ BOT NỘI BỘ TRONG HỆ THỐNG GENESIS mới có ngoại lệ gửi lệnh reset sang bot chính.
                    # Mọi người dùng bên ngoài khác -> CÚT HẾT, DROP 100%, CÂM NÍN TUYỆT ĐỐI!
                    if not is_internal_bot(message.author.id):
                        return

                    is_sys_exempt = False
                    try:
                        content_clean = message.content.strip().lower()
                        from apps.user_discord.utils.prefix import get_prefixes
                        for p in get_prefixes(bot):
                            p_c = p.rstrip().lower()
                            pfx_matches = [p_c, f"{p_c} "] if p_c else [""]
                            for pm in pfx_matches:
                                if content_clean.startswith(pm):
                                    after_pfx = content_clean[len(pm):].strip()
                                    parts = after_pfx.split()
                                    if parts:
                                        head = parts[0]
                                        if head in ("reset", "rs", "restart", "reboot"):
                                            is_sys_exempt = True
                                            break
                                        if head in ("gene", "genesis", "gen") and len(parts) > 1 and parts[1] in ("reset", "rs", "restart", "reboot"):
                                            is_sys_exempt = True
                                            break
                            if is_sys_exempt:
                                break
                    except Exception:
                        pass

                    if not is_sys_exempt:
                        return
            except Exception:
                pass
        else:
            # DM: Mặc định là BOT ON (dm_active=True).
            # Người khác nhắn tin riêng (DM) vẫn dùng được lệnh bình thường.
            # Nếu chủ bot tắt DM (bot off trong DM) thì chỉ Staff / bot nội bộ mới dùng được.
            try:
                from apps.user_discord.core.bot_sys import (
                    is_dm_active, is_internal_bot as _dm_internal, is_staff as _dm_staff,
                )
                _dm_uid = message.author.id
                _is_staff_user = (_dm_uid == bot.user.id) or _dm_staff(bot, _dm_uid) or _dm_internal(_dm_uid)
                if not is_dm_active(bot) and not _is_staff_user:
                    return
            except Exception:
                pass

        if getattr(message.author, "bot", False):
            try:
                from apps.user_discord.core.bot_sys import is_internal_bot
                if is_internal_bot(message.author.id):
                    ctx = await bot.get_context(message)
                    await bot.invoke(ctx)
                    return
            except Exception:
                pass

        # ── KIỂM TRA RATE LIMIT CHỐNG SPAM (CHỈ STAFF / BOT NỘI BỘ ĐƯỢC MIỄN TRỪ) ──
        try:
            from apps.user_discord.utils.rate_limit import is_rate_limited
            if is_rate_limited(bot, message):
                return
        except Exception:
            pass

        await bot.process_commands(message)


    async def _runner():
        try:
            await bot.start(t)
        except Exception as exc:
            state["error"] = type(exc).__name__
            _log(f"[RUNTIME] Bot '{name or '?'}' start loi: {type(exc).__name__}")
            ready.set()

    task = asyncio.create_task(_runner(), name=f"selfbot-{(name or t)[:12]}")
    LIVE[t] = {"bot": bot, "task": task, "prefix": prefix, "name": name}

    try:
        await asyncio.wait_for(ready.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass

    if state["error"]:
        await shutdown(t)
        return False, None, f"lỗi đăng nhập ({state['error']})"
    if not state["loaded"]:
        return True, bot, "đang khởi động (chưa xác nhận online)"
    return True, bot, f"online: {bot.user}"


async def shutdown(token: str) -> bool:
    """Tat bot (dong ket noi + huy task). Tra True neu co bot de tat."""
    t = _tok(token)
    ent = LIVE.pop(t, None)
    if not ent:
        return False
    bot, task = ent.get("bot"), ent.get("task")
    try:
        if bot is not None and not bot.is_closed():
            await bot.close()
    except Exception:
        pass
    if task is not None and not task.done():
        task.cancel()
    _log(f"[RUNTIME] Da tat bot '{ent.get('name') or t[:8]}'.")
    return True


# ── Extension loader hook cho main.py (load MỌI file .py trong core/ làm extension) ──
async def setup(bot):
    """Không làm gì — runtime là module quản lý vòng đời (register/spawn/shutdown), không có cog."""
    pass
