# -*- coding: utf-8 -*-
"""GENESIS - HA TANG KHAI BAO & QUAN LY BOT CON (PRIME / SHARD).

Mo hinh "SO QUYEN" (ledger)
---------------------------
Moi account trong config.json duoc gan them cac truong:
    role       : "prime" (ban the chinh) | "shard" (bot phu)
    status     : "unlock" (hoat dong) | "lock" (bi khoa - go lenh khong chay)
    time_user  : "infinity" (vo han) hoac chuoi thoi han (10s, 5m, 2h, 1d...)
    expire_at  : moc het han (epoch giay) hoac null neu vo han
    bot_id     : ma do genesis sinh ra (vd G001) de go lenh
    owner_ids  : danh sach nguoi da tao/so huu bot nay
    uid        : Discord user id cua bot (dien sau khi bot phu dang nhap)

Quy tac
-------
* Prime = bot chinh -> toan quyen genesis (create/start/lock/unlock/stop/remove/list).
* Shard = bot phu  -> KHONG duoc dung bat ky lenh genesis nao; khi status=lock
  hoac het han thi bi chan MOI lenh. Tat ca deu la "checks-only" -> khong can restart.
* Bot phu van online binh thuong tu config.json (main.py khoi dong); genesis chi
  quyet dinh "duoc phep dung lenh hay khong".
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import types
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord.ext import commands

try:  # khi chay trong package apps.user_discord
    from apps.user_discord.core.bot_sys import require_permission, notice_no_permission
    from apps.user_discord.utils.prefix import token_of, identity, fmt, get_prefix
    from apps.user_discord.utils.menu_catalog import menu_entry
    from apps.user_discord.core.alias import alias_declare
    from apps.user_discord.utils.autorep import autorep
except ImportError:  # fallback khi chay truc tiep / doi sys.path
    from core.bot_sys import require_permission, notice_no_permission
    from utils.prefix import token_of, identity, fmt, get_prefix
    from utils.menu_catalog import menu_entry
    try:
        from core.alias import alias_declare
    except ImportError:
        def alias_declare(*args, **kwargs):
            return lambda f: f
    try:
        from utils.autorep import autorep
    except ImportError:
        autorep = None

BASE_DIR = Path(__file__).resolve().parent.parent          # apps/user_discord
CONFIG_PATH = BASE_DIR / "config.json"
DATA_DIR = BASE_DIR / "data"
PROJECT_ROOT = BASE_DIR.parents[1]                         # goc du an (botdis)

# ── RESET / SHUTDOWN (gop tu core/restart.py cu) ──────────────────────────
SHUTDOWN_DELAY = 3        # doi truoc khi tat/restart (nguoi dung doc thong bao)
COOLDOWN = 10             # khoang cach toi thieu giua 2 lan reset (tranh bam)
_LAST_RESET: Dict[str, float] = {}   # key: "*ALL*" hoac bot_id
_RESETTING: set = set()              # dang reset (chan re-entrant)
_QR_ACTIVE: set = set()              # dang chay phien `gene qrlogin` (chan trung phien)


def _spawn_task(coro):
    """Tao task tren loop dang chay (KHONG dung bot.loop)."""
    try:
        return asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _flush_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass

_LOG_PATTERNS = ("*.log", "log-*.txt", "*.log.*")


def _wipe_old_logs_impl() -> int:
    """Xoa file log cu truoc khi reset THAT (tra ve so file da xoa).

    Quet file log trong: PROJECT_ROOT / <root>/data / BASE_DIR / DATA_DIR va
    MOI app con (apps/<app>, apps/<app>/data, apps/<app>/logs, apps/<app>/log).
    Chi xoa *.log / log-*.txt / *.log.* — KHONG dung .bak / .json / code / .venv.
    Khong raise: file dang bi giu (Windows) thi bo qua.
    """
    removed = 0
    seen: set = set()

    def _kill(path) -> None:
        nonlocal removed
        try:
            if not path.is_file():
                return
        except Exception:
            return
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        if key in seen:
            return
        seen.add(key)
        try:
            path.unlink()
            removed += 1
        except Exception:
            pass

    def _scan(dirpath) -> None:
        try:
            if not dirpath.is_dir():
                return
        except Exception:
            return
        for pat in _LOG_PATTERNS:
            try:
                for p in dirpath.glob(pat):
                    _kill(p)
            except Exception:
                continue

    try:
        roots = [PROJECT_ROOT, PROJECT_ROOT / "data", BASE_DIR, DATA_DIR]
        for root in roots:
            _scan(root)
            for sub in ("logs", "log"):
                _scan(root / sub)

        # Log cua TUNG app con (apps/discord_bot/data/bot.log, ...)
        try:
            apps_dir = PROJECT_ROOT / "apps"
            if apps_dir.is_dir():
                for app in apps_dir.glob("*"):
                    try:
                        if not app.is_dir() or app.name.startswith("."):
                            continue
                    except Exception:
                        continue
                    _scan(app)
                    for sub in ("data", "logs", "log"):
                        _scan(app / sub)
        except Exception:
            pass
    except Exception:
        pass
    _log(f"[GENESIS] Da xoa {removed} file log cu truoc reset.")
    return removed


def _wipe_pycache_impl() -> int:
    """Xóa tất cả thư mục __pycache__ và file *.pyc để đảm bảo nạp 100% code mới từ ổ đĩa."""
    removed = 0
    try:
        import shutil
        roots = [PROJECT_ROOT, BASE_DIR]
        apps_dir = PROJECT_ROOT / "apps"
        if apps_dir.is_dir():
            roots.append(apps_dir)
        for r in roots:
            if not r.exists():
                continue
            for p in list(r.rglob("__pycache__")):
                try:
                    if p.is_dir():
                        shutil.rmtree(str(p), ignore_errors=True)
                        removed += 1
                except Exception:
                    pass
            for f in list(r.rglob("*.pyc")):
                try:
                    if f.is_file():
                        f.unlink(missing_ok=True)
                        removed += 1
                except Exception:
                    pass
    except Exception:
        pass
    _log(f"[GENESIS] Da xoa {removed} file/thu muc __pycache__ truoc reset.")
    return removed


def _purge_sys_modules_impl() -> int:
    """Xóa các module của user_discord ra khỏi sys.modules để nạp lại code mới nhất."""
    import importlib
    try:
        importlib.invalidate_caches()
    except Exception:
        pass
    purged = 0
    prefixes = (
        "apps.user_discord",
        "modules.",
        "utils.",
        "core.",
    )
    for mod_name in list(sys.modules.keys()):
        if any(mod_name.startswith(p) for p in prefixes):
            if not mod_name.startswith("discord") and not mod_name.startswith("aiohttp"):
                del sys.modules[mod_name]
                purged += 1
    _log(f"[GENESIS] Da lam moi {purged} module trong sys.modules RAM.")
    return purged


async def _purge_channel_logs(bot_obj, channel, keep_ids: set = None, limit: int = 30) -> int:
    """Xoa (best-effort) tin nhan reset/log CU cua CHINH bot trong kenh hien tai.

    Chi xoa tin do CHINH `bot_obj.user` gui VA co noi dung log-like
    (DAANG RESET / DA RESET / CHON BOT / SO GENESIS) — giu lai tin trong
    `keep_ids` (thong bao moi vua gui). Tra ve so tin da xoa. Khong raise.
    """
    keep_ids = keep_ids or set()
    me_id = None
    try:
        me_id = getattr(getattr(bot_obj, "user", None), "id", None)
    except Exception:
        me_id = None
    try:
        hist = []
        async for m in channel.history(limit=limit):
            hist.append(m)
    except Exception:
        return 0
    n = 0
    for m in hist:
        try:
            if m.id in keep_ids:
                continue
            try:
                if me_id and getattr(getattr(m, "author", None), "id", None) != me_id:
                    continue
            except Exception:
                continue
            content = str(getattr(m, "content", "") or "")
            if not any(k in content for k in (
                "ĐANG RESET", "ĐÃ RESET", "RESET XONG", "RESET TOÀN BỘ",
                "CHỌN BOT ĐỂ RESET", "SỔ GENESIS",
            )):
                continue
            try:
                await m.delete()
                n += 1
            except Exception:
                continue
        except Exception:
            continue
    return n


ROLE_PRIME = "prime"
ROLE_SHARD = "shard"
STATUS_LOCK = "lock"
STATUS_UNLOCK = "unlock"
TIME_INFINITY = "infinity"

# Cache noi dung config.json theo mtime (giong prefix.py) -> checks chay nhanh.
_cfg_state: Dict[str, Any] = {"key": None, "data": {"accounts": []}}

_UNIT_SECONDS = {
    "s": 1, "sec": 1, "giay": 1,
    "m": 60, "min": 60, "phut": 60,
    "h": 3600, "gio": 3600,
    "d": 86400, "ngay": 86400,
    "w": 604800, "tuan": 604800,
}


async def _wipe_bot_logs(bot, channel, limit: int = 100) -> Dict[str, Any]:
    """Xóa log/tin nhắn cũ của bot trong kênh (reset thật + sạch kênh)."""
    import asyncio as _aio
    out = {"xoa": 0, "sot": 0}
    try:
        me = getattr(bot, "user", None)
        me_id = getattr(me, "id", None)
    except Exception:
        me, me_id = None, None
    markers = ("gene_pick", "gene_list", "ĐANG RESET", "RESET XONG",
               "CHỌN BOT", "SỔ GENESIS", "HỆ THỐNG")
    try:
        msgs = []
        async for m in channel.history(limit=max(1, min(int(limit or 100), 100))):
            msgs.append(m)
    except Exception:
        return out
    me_msgs = []
    for m in msgs:
        try:
            au = getattr(m, "author", None)
            is_me = (me_id is not None and getattr(au, "id", None) == me_id)
            if not is_me and me is not None:
                try:
                    is_me = (au == me)
                except Exception:
                    pass
            txt = str(getattr(m, "content", "") or "")
            has_file = bool(getattr(m, "attachments", None))
            is_marker = any(k in txt for k in markers) or (
                has_file and any(k in txt for k in ("🧬", "♻️", "✅", "❌")))
            if is_me or is_marker:
                me_msgs.append(m)
        except Exception:
            continue
    try:
        if len(me_msgs) >= 2:
            try:
                await channel.delete_messages(me_msgs[:100])
                out["xoa"] += len(me_msgs[:100])
                me_msgs = me_msgs[100:]
            except Exception:
                pass
    except Exception:
        pass
    for m in me_msgs:
        try:
            await m.delete()
            out["xoa"] += 1
            await _aio.sleep(0.25)
        except Exception:
            out["sot"] += 1
    return out


def _log(msg: str) -> None:
    """Log ASCII-thuan (console Windows cp1252 de UnicodeEncodeError)."""
    try:
        print(msg, flush=True)
    except Exception:
        try:
            print(str(msg).encode("ascii", "ignore").decode("ascii"), flush=True)
        except Exception:
            pass


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _wipe_old_logs() -> int:
    """Xoa file log cu truoc khi reset (reset THAT + sach log)."""
    return _wipe_old_logs_impl()


# ─────────────────────────────────────────────────────────────────────────────
# DOC / GHI config.json (nguon su that duy nhat cua "so genesis")
# ─────────────────────────────────────────────────────────────────────────────
def _read_config() -> Dict[str, Any]:
    """Doc config.json (cache theo mtime). Luon tra ve dict co key 'accounts'."""
    if not CONFIG_PATH.exists():
        return {"accounts": []}
    try:
        key: Any = (str(CONFIG_PATH), CONFIG_PATH.stat().st_mtime_ns)
    except OSError:
        key = (str(CONFIG_PATH), None)
    if _cfg_state["key"] != key:
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {"accounts": []}
        except Exception:
            data = {"accounts": []}
        data.setdefault("accounts", [])
        try:
            from apps.shared.token_crypto import decrypt
            for acc in data.get("accounts", []):
                if isinstance(acc, dict) and "token" in acc:
                    acc["token"] = decrypt(acc["token"])
            if "tokens" in data and isinstance(data["tokens"], list):
                data["tokens"] = [decrypt(t) for t in data["tokens"]]
            if "token" in data:
                data["token"] = decrypt(data["token"])
        except Exception:
            pass
        _cfg_state["key"] = key
        _cfg_state["data"] = data
    return _cfg_state["data"]


def _write_config(cfg: Dict[str, Any]) -> bool:
    """Ghi config.json (co backup .json.bak), xong xoa cache de doc lai."""
    try:
        try:
            CONFIG_PATH.with_suffix(".json.bak").write_text(
                CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8"
            )
        except Exception:
            pass

        # Ma hoa token truoc khi ghi xuong disk
        cfg_to_write = json.loads(json.dumps(cfg))
        try:
            from apps.shared.token_crypto import encrypt_config
            encrypt_config(cfg_to_write)
        except Exception:
            pass

        CONFIG_PATH.write_text(
            json.dumps(cfg_to_write, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _cfg_state["key"] = None
        return True
    except Exception as exc:
        _log(f"[GENESIS] Loi ghi config.json: {type(exc).__name__}")
        return False


def _accounts(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Chi lay account hop le (dict) va giu tham chieu doc/ghi truc tiep vao cfg."""
    return [a for a in cfg.get("accounts", []) if isinstance(a, dict)]


def entry_for_token(cfg: Dict[str, Any], token: str) -> Optional[Dict[str, Any]]:
    token = _norm(token)
    if not token:
        return None
    try:
        from apps.shared.token_crypto import decrypt
        tok_plain = decrypt(token)
    except Exception:
        tok_plain = token
    for acc in _accounts(cfg):
        acc_tok = acc.get("token")
        try:
            from apps.shared.token_crypto import decrypt
            acc_plain = decrypt(acc_tok)
        except Exception:
            acc_plain = acc_tok
        if _norm(acc_plain) == token or _norm(acc_plain) == tok_plain:
            return acc
    return None


def _uid_from_token(token: str) -> Optional[int]:
    """Doc Discord user id tu segment dau tien cua token (base64) - loi ve null."""
    try:
        import base64
        head = _norm(token).split(".")[0]
        if not head:
            return None
        pad = "=" * (-len(head) % 4)
        raw = base64.b64decode(head + pad).decode("utf-8", "ignore")
        return int(raw) if raw.isdigit() else None
    except Exception:
        return None


def _prime_prefix() -> str:
    """Doc prefix cua bot chinh (prime) tu config.json — dung cho shard chuyen lenh."""
    for acc in _accounts(_read_config()):
        if role_of(acc) == ROLE_PRIME:
            return _norm(acc.get("prefix")) or ""
    return ""


def self_entry(bot: commands.Bot) -> Optional[Dict[str, Any]]:
    """Tim entry genesis cua DUNG bot dang chay (uu tien token, roi ten account)."""
    cfg = _read_config()
    try:
        tok = token_of(bot)
    except Exception:
        tok = ""
    if tok:
        hit = entry_for_token(cfg, tok)
        if hit is not None:
            return hit
    try:
        name = _norm(identity(bot).get("name"))
    except Exception:
        name = _norm(getattr(getattr(bot, "user", None), "name", ""))
    if name:
        for acc in _accounts(cfg):
            if _norm(acc.get("name")).lower() == name.lower():
                return acc
    return None


def role_of(entry: Optional[Dict[str, Any]]) -> str:
    """Khong co trong so -> coi nhu bot chinh (tuong thich nguoc)."""
    if not entry:
        return ROLE_PRIME
    return _norm(entry.get("role")).lower() or ROLE_PRIME


def status_of(entry: Optional[Dict[str, Any]]) -> str:
    if not entry:
        return STATUS_UNLOCK
    return _norm(entry.get("status")).lower() or STATUS_UNLOCK


def is_expired(entry: Optional[Dict[str, Any]]) -> bool:
    if not entry:
        return False
    if _norm(entry.get("time_user")).lower() in ("", TIME_INFINITY):
        return False
    exp = entry.get("expire_at")
    try:
        return exp is not None and float(exp) <= time.time()
    except Exception:
        return False


def is_locked(entry: Optional[Dict[str, Any]]) -> bool:
    """Bi khoa = status 'lock' HOAC da het han thoi gian su dung."""
    return status_of(entry) == STATUS_LOCK or is_expired(entry)


def is_bot_locked(bot: commands.Bot) -> bool:
    """Public helper (de bot_sys goi): bot dang chay co bi khoa khong?"""
    entry = self_entry(bot)
    if entry is None or role_of(entry) == ROLE_PRIME:
        return False
    return is_locked(entry)


# ─────────────────────────────────────────────────────────────────────────────
# THOI GIAN / MA BOT / CHUAN HOA SO
# ─────────────────────────────────────────────────────────────────────────────
def parse_duration(text: str) -> Tuple[Optional[int], str]:
    """Parse '<so><don_vi>' -> (seconds | None, nhan). None = vo han.

    Don vi ho tro: s (giay), m (phut), h (gio), d (ngay), w (tuan).
    Tu khoa 'inf'/'infinity'/'vo han'/rong -> vo han.
    """
    t = _norm(text).lower()
    if t in ("", "inf", "infinite", "infinity", "vo", "vohan", "vo_han", "∞"):
        return None, TIME_INFINITY
    if t.isdigit():
        return int(t), f"{int(t)}s"
    num, unit = "", ""
    for ch in t:
        if ch.isdigit():
            num += ch
        else:
            unit += ch
    mult = _UNIT_SECONDS.get(unit.strip())
    if not num or not mult:
        return None, TIME_INFINITY
    return int(num) * mult, f"{int(num)}{unit.strip()}"


def humanize(seconds: int) -> str:
    """Doi so giay thanh chuoi ngan gon nhat (toi da 2 don vi)."""
    if seconds <= 0:
        return "0s"
    parts: List[str] = []
    for label, size in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= size:
            value, seconds = divmod(seconds, size)
            parts.append(f"{value}{label}")
    return " ".join(parts[:2])


def remaining_text(entry: Optional[Dict[str, Any]]) -> str:
    if not entry:
        return "∞ vô hạn"
    if _norm(entry.get("time_user")).lower() in ("", TIME_INFINITY) or entry.get("expire_at") is None:
        return "∞ vô hạn"
    try:
        left = int(float(entry["expire_at"]) - time.time())
    except Exception:
        return "∞ vô hạn"
    return "⛔ đã hết hạn" if left <= 0 else humanize(left)


def _new_bot_id(cfg: Dict[str, Any]) -> str:
    used = {_norm(a.get("bot_id")).upper() for a in _accounts(cfg)}
    i = 1
    while f"G{i:03d}" in used:
        i += 1
    return f"G{i:03d}"


def ensure_ledger(cfg: Dict[str, Any]) -> bool:
    """Bo sung field con thieu trong 'so'. Tra True neu co sua doi (can ghi lai).

    * prime = account dau tien CO token (neu chua ai duoc danh role 'prime').
    * status mac dinh 'unlock' (de account cu khong bi khoa bat ngo).
    * bot tao moi qua `gene create` se duoc dat status 'lock' rieng.
    """
    changed = False
    accts = _accounts(cfg)
    if not accts:
        return False
    prime_set = any(_norm(a.get("role")).lower() == ROLE_PRIME for a in accts)
    first_tok_idx = next((i for i, a in enumerate(accts) if _norm(a.get("token"))), 0)

    for idx, acc in enumerate(accts):
        if not _norm(acc.get("role")):
            if not prime_set and idx == first_tok_idx:
                acc["role"] = ROLE_PRIME
                prime_set = True
            else:
                acc["role"] = ROLE_SHARD
            changed = True
        if not _norm(acc.get("status")):
            acc["status"] = STATUS_UNLOCK
            changed = True
        if not _norm(acc.get("time_user")):
            acc["time_user"] = TIME_INFINITY
            acc["expire_at"] = None
            changed = True
        if "expire_at" not in acc:
            acc["expire_at"] = None
            changed = True
        if not _norm(acc.get("bot_id")):
            acc["bot_id"] = _new_bot_id(cfg)
            changed = True
        if not isinstance(acc.get("owner_ids"), list):
            acc["owner_ids"] = []
            changed = True
    return changed


# ─────────────────────────────────────────────────────────────────────────────
# DECORATOR: chi bot chinh (prime) duoc dung
# ─────────────────────────────────────────────────────────────────────────────
def _prime_only():
    """Check: bot DANG CHAY phai la bot chinh (prime) moi cho chay lenh."""
    async def predicate(ctx: commands.Context) -> bool:
        cog = getattr(ctx, "cog", None)
        is_prime = getattr(cog, "_is_prime_bot", None)
        return bool(callable(is_prime) and is_prime())
    return commands.check(predicate)


# ─────────────────────────────────────────────────────────────────────────────
# COG GENESIS
# ─────────────────────────────────────────────────────────────────────────────
class GenesisCog(commands.Cog):
    """Quan ly bot con theo mo hinh so quyen (prime/shard).

    * Prime (bot chinh): toan quyen gene.
    * Shard (bot phu): khong dung duoc lenh gene; bi khoa thi cam moi lenh.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── helpers ──────────────────────────────────────────────────────────
    async def _reply(self, ctx: commands.Context, text: str, delay: Optional[int] = 30):
        """Rep theo chuan user_discord (autorep) + tu thay prefix cua bot nay."""
        try:
            text = fmt(self.bot, text)
        except Exception:
            pass
        try:
            from apps.user_discord.utils.autorep import autorep
        except ImportError:
            try:
                from utils.autorep import autorep
            except ImportError:
                return await ctx.send(text)
        return await autorep(ctx.message, content=text, auto_delete_delay=delay)

    async def _reply_with_file(self, ctx: commands.Context, text: str, file: Optional[discord.File] = None, delay: Optional[int] = 60):
        """Rep kèm file ảnh theo chuẩn autorep + autodelet."""
        try:
            text = fmt(self.bot, text)
        except Exception:
            pass
        try:
            from apps.user_discord.utils.autorep import autorep
        except ImportError:
            try:
                from utils.autorep import autorep
            except ImportError:
                return await ctx.send(text, file=file)
        return await autorep(ctx.message, content=text, file=file, auto_delete_delay=delay)

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return getattr(self.bot, "_own_prefix", None) or ""

    def _self(self) -> Optional[Dict[str, Any]]:
        return self_entry(self.bot)

    def _is_prime_bot(self) -> bool:
        """True neu bot DANG CHAY la bot chinh (prime)."""
        return role_of(self._self()) == ROLE_PRIME

    @staticmethod
    def _is_gene_command(cmd) -> bool:
        node = cmd
        while node is not None:
            if getattr(node, "name", "") in ("gene", "genesis", "gen"):
                return True
            node = getattr(node, "parent", None)
        return False

    async def _global_gate(self, ctx: commands.Context) -> bool:
        """Check toan cuc: bot phu (shard) bi khoa -> cam moi lenh; shard cam lenh gene tru reset/update/create."""
        entry = self._self()
        if entry is None or role_of(entry) == ROLE_PRIME:
            return True
        if is_locked(entry):
            return False
        if ctx.command is not None and self._is_gene_command(ctx.command):
            # NGOAI LE: Lenh reset, update, create, qrlogin, prefix, help thi bot phu duoc phep chay
            # de admin cap cao hoac bot chinh quan ly!
            cmd_name = getattr(ctx.command, "name", "")
            if cmd_name in (
                "reset", "rs", "restart", "reboot",
                "update", "upd", "settoken", "token",
                "create", "add", "new",
                "qrlogin", "qr",
                "prefix", "setprefix", "pfx", "doiprefix",
                "gene", "genesis", "gen"
            ):
                return True

            # Bot PHU khong dung duoc cac lenh gene khac -> BAO TO
            try:
                pfx = _prime_prefix() or ""
                await notice_no_permission(
                    self.bot,
                    ctx,
                    "Bot phụ (shard) **không có quyền duyệt hoặc quản trị** lệnh gene này — chỉ Bot chính (Prime) và Admin cấp cao bot chính mới có quyền.\n"
                    f"• Hãy dùng **prefix của BOT CHÍNH**: `{pfx}gene ...`",
                )
            except Exception:
                pass
            return False
        return True

    @staticmethod
    def _live_uid(acc: Dict[str, Any]) -> Optional[int]:
        """UID THAT cua bot dang chay (`runtime.LIVE` -> `bot.user.id`).

        Nguon dang tin nhat: config.json co the ghi `uid` sai/trong, token co the
        bi sua tay — nhung bot nao DANG chay thi `bot.user.id` luon la uid that.
        """
        tok = _norm(acc.get("token"))
        if not tok:
            return None
        try:
            try:
                from apps.user_discord.core import runtime as _runtime
            except ImportError:
                from core import runtime as _runtime
            bot = _runtime.get_live(tok)
            uid = getattr(getattr(bot, "user", None), "id", None)
            return int(uid) if uid else None
        except Exception:
            return None

    @staticmethod
    def _entry_uids(acc: Dict[str, Any]) -> set:
        """Tap MOI uid co the la cua bot nay — 3 nguon, thieu 1 van nhan ra bot:

        1. `uid` ghi trong config.json (so genesis);
        2. uid GIAI MA TU TOKEN (base64 segment dau) — luon co du bot chua login;
        3. uid cua bot DANG CHAY (`bot.user.id`) — uid that.
        """
        uids: set = set()
        try:
            u = int(acc.get("uid") or 0)
            if u:
                uids.add(u)
        except Exception:
            pass
        token_uid = _uid_from_token(_norm(acc.get("token")))
        if token_uid:
            uids.add(token_uid)
        live_uid = GenesisCog._live_uid(acc)
        if live_uid:
            uids.add(live_uid)
        return uids

    @staticmethod
    def _uid_report(acc: Dict[str, Any]) -> Dict[str, Any]:
        """CHECK cheo: account nay giu uid gi trong so, token giai ma ra uid gi,
        bot dang chay uid gi — va co LECH nhau khong."""
        try:
            acc_uid = int(acc.get("uid") or 0) or None
        except Exception:
            acc_uid = None
        token_uid = _uid_from_token(_norm(acc.get("token")))
        live_uid = GenesisCog._live_uid(acc)
        found = sorted({u for u in (acc_uid, token_uid, live_uid) if u})
        others = {u for u in (token_uid, live_uid) if u}
        return {
            "acc_uid": acc_uid,
            "token_uid": token_uid,
            "live_uid": live_uid,
            "uids": found,
            "any_uid": found[0] if found else None,
            "mismatch": bool(acc_uid and others and acc_uid not in others),
            "stale": (not acc_uid) and bool(others),
        }

    @staticmethod
    def _uid_compare_text(acc: Dict[str, Any]) -> str:
        """Mô tả UID ngắn gọn, tinh tế: nếu khớp nhau thì chỉ in 1 UID duy nhất, chỉ cảnh báo khi lệch."""
        rep = GenesisCog._uid_report(acc)
        uid_val = rep.get("acc_uid") or rep.get("token_uid") or rep.get("live_uid")
        if rep.get("mismatch"):
            return f"`{rep.get('acc_uid') or 'trống'}` (⚠️ Token: `{rep.get('token_uid')}`)"
        if rep.get("stale"):
            return f"`{rep.get('token_uid')}` (⚠️ chưa lưu sổ)"
        return f"`{uid_val}`" if uid_val else "`trống`"

    def _resolve(self, raw: str) -> Optional[Dict[str, Any]]:
        """Tim entry theo: @mention | uid (trong so HOAC giai ma tu token HOAC uid
        bot dang chay) | ma bot (G00x) | ten bot | dau token."""
        raw = _norm(raw)
        if not raw:
            return None
        cfg = _read_config()
        uid = 0
        if raw.startswith("<@") and raw.endswith(">"):
            uid = int("".join(ch for ch in raw if ch.isdigit()) or 0)
        elif raw.isdigit():
            uid = int(raw)
        else:
            guessed = _uid_from_token(raw)
            if guessed:
                uid = guessed
        low = raw.lower()

        # 1. Uu tien UID: so sanh CA 3 nguon (uid trong so | uid giai ma tu token |
        #    uid cua bot dang chay) -> tag la uid nao cua bot cung nhan ra
        if uid:
            for acc in _accounts(cfg):
                if uid in self._entry_uids(acc):
                    return acc

        # 2. Ma bot / ten bot
        for acc in _accounts(cfg):
            if _norm(acc.get("bot_id")).lower() == low:
                return acc
            if _norm(acc.get("name")).lower() == low:
                return acc

        # 3. Token (khop chinh xac hoac dau token)
        for acc in _accounts(cfg):
            tok = _norm(acc.get("token")).lower()
            if tok and (tok == low or tok.startswith(low)):
                return acc
        return None

    def _user_admin_bots(self, uid: int) -> List[Dict[str, Any]]:
        """Danh sach BOT PHU ma `uid` la admin cap cao (admintris / nguoi tao)."""
        out: List[Dict[str, Any]] = []
        try:
            for acc in _accounts(_read_config()):
                if role_of(acc) == ROLE_PRIME:
                    continue
                try:
                    if uid in self._target_admin_ids(acc):
                        out.append(acc)
                except Exception:
                    continue
        except Exception:
            return []
        return out

    def _sync_owners(self, uid: int, owners: List[Any]) -> None:
        """Ghi owner_ids (nguoi tao) vao data/<uid>_setting.json cua bot phu."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            path = DATA_DIR / f"{uid}_setting.json"
            data: Dict[str, Any] = {}
            if path.exists():
                try:
                    loaded = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        data = loaded
                except Exception:
                    data = {}
            changed = False
            targets = list(owners) + [uid]
            for key in ("admintris", "admins"):
                lst = data.get(key)
                if not isinstance(lst, list):
                    lst = []
                    data[key] = lst
                    changed = True
                for oid in targets:
                    try:
                        oid = int(oid)
                    except Exception:
                        continue
                    if oid not in lst:
                        lst.append(oid)
                        changed = True
            if changed:
                path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            _log(f"[GENESIS] sync owners loi: {type(exc).__name__}")

    # ── vong doi ─────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            cfg = _read_config()
            if ensure_ledger(cfg):
                _write_config(cfg)
            me = self.bot.user
            if me is None:
                return
            cfg = _read_config()
            entry = self_entry(self.bot)
            if entry is None:
                return
            if int(entry.get("uid") or 0) != me.id:
                entry["uid"] = me.id
                _write_config(cfg)
            if role_of(entry) == ROLE_SHARD:
                # sync ca owner_ids (nguoi so huu) lan created_by (nguoi tao)
                owners = list(entry.get("owner_ids") or [])
                cb = entry.get("created_by")
                if cb and cb not in owners:
                    owners.append(cb)
                self._sync_owners(me.id, owners)
            _log(f"[GENESIS] {me} -> role={role_of(entry)} status={status_of(entry)} locked={is_locked(entry)}")
        except Exception as exc:
            _log(f"[GENESIS] on_ready loi: {type(exc).__name__}")

    # ── NHOM LENH: gene ──────────────────────────────────────────────────
    @menu_entry("SYSTEM & SECURITY", "gene", "Quản lý bot chính / phụ (Genesis)",
                badge="ROOT", icon_sym="🧬", icon_color=(167, 139, 250), order=3)
    @alias_declare("gene", main="gene", subs=["genesis", "gen"])
    @commands.group(name="gene", aliases=("genesis", "gen"), invoke_without_command=True)
    @require_permission("user")
    async def gene(self, ctx: commands.Context):
        """Genesis - quan ly bot con (prime/shard): (prefix)gene <create|qrlogin|start|reset|list|lock|unlock|stop|remove>"""
        await self._help(ctx)

    async def _help(self, ctx: commands.Context):
        p = self._pfx()
        prime_p = _prime_prefix() or "!"

        # 1. Uu tien gui bang huong dan dang ANH (giong scl / yt / tt) - Day du cho ca chinh va phu
        try:
            from apps.user_discord.utils.media_card import async_help_card
        except ImportError:
            try:
                from utils.media_card import async_help_card
            except ImportError:
                async_help_card = None
        card_file = None
        if async_help_card is not None:
            try:
                buf = await async_help_card("genesis", p)
                if buf:
                    card_file = discord.File(buf, filename="gene_guide.png")
            except Exception:
                card_file = None
        if card_file is not None:
            try:
                from apps.user_discord.utils.autorep import autorep
            except ImportError:
                from utils.autorep import autorep
            await autorep(
                ctx.message,
                content="🧬 **HƯỚNG DẪN SỬ DỤNG LỆNH GENESIS**",
                file=card_file,
                auto_delete_delay=60,
            )
            return

        # 2. Fallback: bang text neu khong render duoc anh
        await self._reply(
            ctx,
            "🧬 **GENESIS — QUẢN LÝ BOT CON**\n"
            f"• `{p}gene create <token> <tên> <prefix>` — đăng ký bot phụ (chờ duyệt, status `lock` — cần gửi bot chính)\n"
            f"• `{p}gene qrlogin` — QUÉT QR bằng Discord mobile để lấy acc → chọn **tạo bot** hoặc **nhận token qua DM** (chính/phụ đều dùng được)\n"
            f"• `{p}gene prefix [bot] <prefix_mới>` — ĐỔI PREFIX (bot phụ tự đổi được cho chính mình, bot chính đổi cho mọi bot)\n"
            f"• `{p}gene unlock <@bot|id>` — duyệt & mở khoá (BẮT BUỘC trước khi start — bot chính)\n"
            f"• `{p}gene start <@bot|id> <time>` — KHỞI ĐỘNG bot ngay + gán thời gian (bot chính)\n"
            f"• `{p}gene list` — xem danh sách bot (avatar / role / thời gian / trạng thái — bot chính)\n"
            f"• `{p}gene lock <@bot|id>` — khoá bot phụ lại (chặn lệnh, vẫn online — bot chính)\n"
            f"• `{p}gene stop <@bot|id>` — tắt hẳn bot phụ (shutdown — bot chính)\n"
            f"• `{p}gene reset [G00x|id|tên]` — RESET: bot chính reset cả hệ thống/riêng bot; bot phụ tự reset chính mình\n"
            f"• `{p}gene update <@bot|id> <token>` — CẬP NHẬT token mới (tự reload & nạp lại)\n"
            f"• `{p}gene reload <tên> [bot]` — nạp lại extension (không tag = bot chính)\n"
            f"• `{p}gene status` — trạng thái hệ thống | `{p}gene shutdown` — tắt toàn bộ\n"
            f"• `{p}gene remove [@bot|id]` — xoá khỏi config.json; bỏ trống để chọn bằng ảnh (bot chính)\n\n"
            f"💡 *Menu lệnh giống nhau trên cả bot chính & bot phụ. Một số quyền quản trị/tạo bot cần gửi qua **BOT CHÍNH** (`{prime_p}gene ...`).*",
            delay=50,
        )

    # ── gene create ──────────────────────────────────────────────────────
    @gene.command(name="create", aliases=("add", "new"))
    @require_permission("user")
    async def gene_create(self, ctx: commands.Context, token_arg: str = None, *, spec: str = ""):
        """Đăng ký bot phụ vào config.json (trạng thái khoá, chờ duyệt).
        Có thể gõ: (prefix)gene create <token> <tên bot> <prefix>
        Hoặc gõ không tham số: bot sẽ hỏi từng bước và tự động xoá token để bảo mật!
        """
        p = self._pfx()

        # Nếu đang ở BOT PHỤ -> Nhắc người dùng gửi lệnh này qua BOT CHÍNH!
        if not self._is_prime_bot():
            prime_p = _prime_prefix() or "!"
            entry = self_entry(self.bot)
            bot_name = _norm(entry.get('name')) if entry else (getattr(self.bot.user, 'name', 'Bot Phụ'))
            await self._reply(
                ctx,
                f"⚠️ **CẦN GỬI LỆNH TẠO BOT CHO BOT CHÍNH**\n"
                f"• Bạn đang dùng lệnh trên **Bot Phụ** (`{bot_name}`).\n"
                f"• Để đăng ký / tạo bot mới vào hệ thống, vui lòng gửi lệnh này cho **BOT CHÍNH**:\n"
                f"👉 `{prime_p}gene create`\n\n"
                f"💡 *(Nếu muốn quét QR đăng nhập lấy token thì bạn có thể dùng ngay tại đây: `{p}gene qrlogin`)*",
                delay=35,
            )
            return
        author_id = ctx.author.id
        is_prime_admin = self._is_prime_admin(author_id)
        user_admin_bots = self._user_admin_bots(author_id)

        token = token_arg.strip() if token_arg else ""

        # Nếu người dùng gửi thẳng token trong câu lệnh -> xoá ngay tin nhắn gốc để chống lộ
        if token:
            try:
                await ctx.message.delete()
            except Exception:
                pass

        name, prefix = "", None
        if token and spec:
            parts = spec.split()
            if len(parts) >= 2:
                prefix = parts[-1]
                name = " ".join(parts[:-1]).strip()
            elif len(parts) == 1:
                name = parts[0].strip()

        # Nếu chưa có token -> yêu cầu gửi Token trước
        if not token:
            prompt_step1 = (
                "🔐 **ĐĂNG KÝ BOT PHỤ MỚI**\n"
                "• Hãy gửi chuỗi **Token Discord** trong vòng 60 giây (gõ `c` để huỷ).\n"
                "🛡️ **CƠ CHẾ BẢO MẬT**: Bot sẽ **tự động xoá ngay lập tức** tin nhắn chứa token của bạn!"
            )
            await self._reply(ctx, prompt_step1, delay=60)

            def check_tok(m: discord.Message) -> bool:
                return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

            try:
                tok_msg = await self.bot.wait_for("message", check=check_tok, timeout=60.0)
            except asyncio.TimeoutError:
                await self._reply(ctx, "⌛ Hết thời gian gửi token. Đã huỷ tạo bot.", delay=20)
                return

            try:
                await tok_msg.delete()
            except Exception:
                pass

            tok_txt = tok_msg.content.strip()
            if tok_txt.lower() in ("c", "cancel", "huy", "hủy"):
                await self._reply(ctx, "Đã huỷ tạo bot.", delay=15)
                return
            token = tok_txt

        if not token:
            await self._reply(ctx, f"❌ Thiếu token. Hãy thử lại: `{p}gene create`", delay=20)
            return

        # Tự động lấy tên tài khoản Discord nếu chưa có tên
        if not name:
            disc_name = await self._fetch_token_username(token)
            name = disc_name or "BotPhu"

        # Nếu chưa chỉ định prefix -> hỏi người dùng có chắc không dùng prefix không hoặc chọn prefix
        if prefix is None:
            prime_p = _prime_prefix() or "!"
            prompt_pfx = (
                f"🧬 **CẤU HÌNH PREFIX CHO BOT** **{name}**\n"
                f"• Bạn có chắc muốn để **KHÔNG PREFIX** (trống) không?\n"
                f"• Gõ **`k`** (hoặc `none`): Xác nhận **Không dùng prefix** (chạy lệnh trực tiếp / tag bot).\n"
                f"• Gõ **`d`**: Dùng prefix mặc định `{prime_p}`.\n"
                f"• Hoặc **gửi ký tự prefix** bạn muốn đặt (Ví dụ: `,` hoặc `.` hoặc `?`) trong 30 giây (gõ `c` để huỷ):"
            )
            await self._reply(ctx, prompt_pfx, delay=40)

            def check_pfx(m: discord.Message) -> bool:
                return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

            try:
                pfx_msg = await self.bot.wait_for("message", check=check_pfx, timeout=30.0)
                pfx_val = pfx_msg.content.strip()
                if pfx_val.lower() in ("c", "cancel", "huy", "hủy"):
                    await self._reply(ctx, "Đã huỷ tạo bot.", delay=15)
                    return
                if pfx_val.lower() in ("k", "khong", "không", "none", "trong", "trống", "no", "yes", "co", "có"):
                    prefix = ""
                elif pfx_val.lower() in ("d", "default", "mac dinh", "mặc định"):
                    prefix = prime_p
                else:
                    prefix = pfx_val
            except asyncio.TimeoutError:
                prefix = prime_p

        prefix = prefix if prefix is not None else (_prime_prefix() or "")

        cfg = _read_config()
        if entry_for_token(cfg, token) is not None:
            await self._reply(ctx, "⚠️ Token này đã tồn tại trong hệ thống.", delay=25)
            return
        if any(_norm(a.get("name")).lower() == name.lower() for a in _accounts(cfg)):
            await self._reply(ctx, f"⚠️ Tên bot **{name}** đã được dùng, chọn tên khác.", delay=25)
            return

        new_id = _new_bot_id(cfg)
        cfg.setdefault("accounts", []).append({
            "name": name,
            "token": token,
            "prefix": prefix,
            "role": ROLE_SHARD,
            "status": STATUS_LOCK,
            "time_user": TIME_INFINITY,
            "expire_at": None,
            "bot_id": new_id,
            "owner_ids": [ctx.author.id],
            "created_by": ctx.author.id,
            "created_at": time.time(),
        })
        if not _write_config(cfg):
            await self._reply(ctx, "❌ Không ghi được config.json.", delay=25)
            return

        try:
            guess_uid = _uid_from_token(token)
            if guess_uid and (DATA_DIR / f"{guess_uid}_setting.json").exists():
                self._sync_owners(guess_uid, [ctx.author.id])
        except Exception:
            pass

        _log(f"[GENESIS] Dang ky bot phu '{name}' ({new_id}) boi {ctx.author} ({ctx.author.id})")
        if is_prime_admin:
            admin_hint = (
                f"➡️ **Admin cấp cao bot chính**: Dùng mã `{new_id}` để DUYỆT: `{p}gene unlock {new_id}`\n"
                f"➡️ Rồi khởi động: `{p}gene start {new_id} <time>` (hoặc `infinity`) — bot lên NGAY."
            )
        else:
            admin_hint = (
                "🔒 **Bot đang ở trạng thái khoá (lock) chờ duyệt**.\n"
                f"• Chỉ **Admin cấp cao bot chính** mới có quyền duyệt bot.\n"
                f"• Hãy báo Admin cấp cao bot chính duyệt với mã `{new_id}`:\n"
                f"  `{p}gene unlock {new_id}` và `{p}gene start {new_id} <time>`"
            )
        await self._reply(
            ctx,
            "🧬 **ĐÃ ĐĂNG KÝ BOT PHỤ THÀNH CÔNG (chờ duyệt)**\n"
            f"• Mã bot: `{new_id}`\n"
            f"• Tên: **{name}** | Prefix: `{prefix}`\n"
            "• Role: `shard` | Status: `lock` 🔒\n"
            f"• Người tạo: <@{ctx.author.id}>\n"
            "🛡️ _(Tin nhắn chứa token đã được tự động xoá an toàn)_\n\n"
            f"{admin_hint}",
            delay=60,
        )

    # ── gene qrlogin ─────────────────────────────────────────────────────
    @gene.command(name="qrlogin", aliases=("qr",))
    @require_permission("user")
    async def gene_qrlogin(self, ctx: commands.Context):
        """Quét QR bằng Discord mobile để lấy acc → chọn: tạo bot (CHỈ create, không start) hoặc nhận token qua DM:
        (prefix)gene qrlogin"""
        p = self._pfx()
        if ctx.author.id in _QR_ACTIVE:
            await self._reply(
                ctx,
                "⏳ Bạn đang có phiên **QR LOGIN** đang chờ — đợi phiên trước kết thúc đã nhé.",
                delay=20,
            )
            return

        try:
            try:
                from apps.user_discord.core.qr_login import (
                    RemoteAuthError, build_qr_url, render_qr_png, style_qr_card, run_remote_auth,
                )
            except ImportError:
                from core.qr_login import (
                    RemoteAuthError, build_qr_url, render_qr_png, style_qr_card, run_remote_auth,
                )
        except Exception as exc:
            await self._reply(
                ctx, f"❌ Không nạp được module QR LOGIN: `{type(exc).__name__}: {exc}`", delay=25)
            return

        _QR_ACTIVE.add(ctx.author.id)
        try:
            author_avatar: Optional[bytes] = None
            try:
                if hasattr(ctx.author, "display_avatar") and ctx.author.display_avatar:
                    author_avatar = await ctx.author.display_avatar.read()
                elif hasattr(ctx.author, "avatar") and ctx.author.avatar:
                    author_avatar = await ctx.author.avatar.read()
            except Exception:
                author_avatar = None

            author_name = getattr(ctx.author, "display_name", None) or getattr(ctx.author, "name", "User")

            async def _on_fingerprint(fp: Any):
                # Gateway tra fingerprint / hoac VPS Chromium tra anh PNG -> ve QR va gui ngay ra kenh
                if isinstance(fp, (bytes, bytearray)):
                    raw_bytes = fp
                elif hasattr(fp, "read"):
                    raw_bytes = fp.read()
                else:
                    raw_bytes = render_qr_png(build_qr_url(str(fp))).getvalue()

                # Trang trí mã QR bằng PIL với avatar người dùng lệnh và chữ QR bên dưới
                buf = style_qr_card(
                    raw_bytes,
                    avatar_bytes=author_avatar,
                    username=author_name,
                    discord_tag="discord.com/login",
                )
                await self._reply_with_file(
                    ctx,
                    "📱 **QR LOGIN — QUÉT BẰNG DISCORD MOBILE**\n"
                    "• Mở app Discord (đã đăng nhập **acc cần lấy**) → Quét mã → bấm **Approve / OK**\n"
                    "• Mã tự hết hạn sau ~2 phút hoặc ngay khi bạn quét xong.\n"
                    "⚠️ **Chỉ dùng với acc của chính bạn** — bot sẽ lấy token của acc quét mã này.",
                    file=discord.File(buf, filename="qrlogin.png"),
                    delay=180,
                )

            # Cấu hình giải captcha (hybrid): AI Gemini Flash -> 2captcha/capsolver -> retry free
            captcha_cfg: Dict[str, str] = {}
            try:
                _c = (_read_config() or {}).get("captcha")
                if isinstance(_c, dict):
                    captcha_cfg = {
                        "provider": str(_c.get("provider") or "").strip(),
                        "api_key": str(_c.get("api_key") or "").strip(),
                        "gemini_key": str(
                            _c.get("gemini_key") or _c.get("gemini_api_key") or "").strip(),
                        "nopecha_key": str(_c.get("nopecha_key") or "").strip(),
                    }
            except Exception:
                captcha_cfg = {}
            try:
                import os as _os
                if not captcha_cfg.get("gemini_key"):
                    _g = (_os.environ.get("GEMINI_API_KEY")
                          or _os.environ.get("GOOGLE_API_KEY") or "").strip()
                    if _g:
                        captcha_cfg["gemini_key"] = _g
                if not captcha_cfg.get("nopecha_key"):
                    _n = (_os.environ.get("NOPECHA_API_KEY") or "").strip()
                    if _n:
                        captcha_cfg["nopecha_key"] = _n
                if not captcha_cfg.get("api_key"):
                    _env_key = (_os.environ.get("CAPTCHA_API_KEY") or "").strip()
                    if _env_key:
                        captcha_cfg["provider"] = (
                            _os.environ.get("CAPTCHA_PROVIDER") or "2captcha").strip()
                        captcha_cfg["api_key"] = _env_key
            except Exception:
                pass

            async def _on_notice(text: str):
                try:
                    await self._reply(ctx, text, delay=45)
                except Exception:
                    pass

            try:
                result = await run_remote_auth(
                    on_fingerprint=_on_fingerprint,
                    timeout=600.0,
                    captcha=captcha_cfg or None,
                    on_notice=_on_notice,
                )
            except RemoteAuthError as exc:
                kind = getattr(exc, "kind", "connection")
                msg = getattr(exc, "message", str(exc))
                text = {
                    "cancel": "🚫 Bạn đã **huỷ quét mã** trên điện thoại. Phiên kết thúc.",
                    "timeout": f"⌛ Mã QR **hết hạn** / quét không kịp. Thử lại: `{p}gene qrlogin`",
                    "captcha": f"⛔ Discord bắt **captcha**: {msg}\n• AI: bot đã thử giải bằng Gemini Flash (nếu có key) — chưa qua thì thử lại sau ít phút.\n• API key: thêm vào `config.json` mục `captcha` (`provider` + `api_key`) hoặc env `CAPTCHA_API_KEY` để fallback 2Captcha/CapSolver.\n• Gemini key: `config.json` mục `captcha.gemini_key` hoặc env `GEMINI_API_KEY` + cài `playwright`/`hcaptcha-challenger`.",
                    "qr": f"❌ Lỗi tạo/gửi mã QR: {msg}",
                    "missing_lib": f"❌ {msg}",
                }.get(kind, f"❌ Lỗi kết nối QR LOGIN: {msg}")
                await self._reply(ctx, text, delay=30)
                return
            except Exception as exc:
                await self._reply(
                    ctx, f"❌ Lỗi QR LOGIN: `{type(exc).__name__}: {exc}`", delay=30)
                return

            # ── Đã có token (không in ra kênh ở bất kỳ nhánh nào) ──
            if result.username:
                acc = f"**{result.username}** (`{result.user_id}`)"
            else:
                uid = None
                try:
                    uid = _uid_from_token(result.token)
                except Exception:
                    uid = None
                acc = f"`{uid}`" if uid else "*(không rõ)*"

            await self._reply(
                ctx,
                "✅ **QUÉT THÀNH CÔNG — ĐÃ LẤY ĐƯỢC ACC**\n"
                f"• Account: {acc}\n"
                "• Trả lời **`1`** hoặc **`2`** trong 60 giây (gõ `c` để huỷ):\n"
                "  `1` — **TẠO BOT**: đăng ký bot phụ vào config — *chỉ create, KHÔNG start*\n"
                "  `2` — **GỬI RIÊNG**: bot gửi token acc qua DM cho bạn",
                delay=90,
            )

            def _check(m: discord.Message) -> bool:
                return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

            try:
                ans = await self.bot.wait_for("message", check=_check, timeout=60.0)
            except asyncio.TimeoutError:
                await self._reply(
                    ctx,
                    "⌛ Hết thời gian chọn — phiên kết thúc (token **không** được lưu lại).",
                    delay=25,
                )
                return

            choice = ans.content.strip().lower()
            if choice in ("c", "cancel", "huy", "hủy"):
                await self._reply(ctx, "Đã huỷ — token **không** được lưu lại.", delay=20)
                return

            if choice in ("1", "tao", "tạo", "create", "bot"):
                raw_name = getattr(result, "username", None) or getattr(result, "name", None)
                if not raw_name:
                    raw_name = await self._fetch_token_username(result.token) or "QRBot"
                prime_p = _prime_prefix() or "!"
                prompt_qr_pfx = (
                    f"🧬 **TẠO BOT TỪ ACC QR: {raw_name}**\n"
                    "• Bạn có chắc muốn để **KHÔNG PREFIX** (trống) không?\n"
                    "• Gõ **`k`**: Không dùng prefix (chạy lệnh trực tiếp / mention tag bot).\n"
                    f"• Gõ **`d`**: Dùng prefix mặc định `{prime_p}`.\n"
                    "• Hoặc **gửi ký tự prefix** bạn muốn đặt (Ví dụ: `,` hoặc `.` | gõ `c` để huỷ) trong 30 giây:"
                )
                await self._reply(ctx, prompt_qr_pfx, delay=40)
                try:
                    spec_msg = await self.bot.wait_for("message", check=_check, timeout=30.0)
                    spec_txt = spec_msg.content.strip()
                    if spec_txt.lower() in ("c", "cancel", "huy", "hủy"):
                        await self._reply(ctx, "Đã huỷ tạo bot (token không lưu).", delay=15)
                        return
                    if spec_txt.lower() in ("k", "khong", "không", "none", "trong", "trống", "no", "yes"):
                        chosen_pfx = ""
                    elif spec_txt.lower() in ("d", "default", "mac dinh"):
                        chosen_pfx = prime_p
                    else:
                        chosen_pfx = spec_txt
                except asyncio.TimeoutError:
                    chosen_pfx = prime_p

                try:
                    await self.gene_create.callback(
                        self, ctx, result.token, spec=f"{raw_name} {chosen_pfx}"
                    )
                except Exception as exc:
                    await self._reply(
                        ctx,
                        f"❌ Lỗi khi đăng ký bot: `{type(exc).__name__}: {exc}`",
                        delay=25,
                    )
                return

            if choice in ("2", "dm", "gui", "gửi", "rieng", "riêng"):
                dm_text = (
                    "🔐 **ACC TỪ QR LOGIN**\n"
                    f"• Account: {acc}\n"
                    f"• Token: ||{result.token}||\n"
                    "⚠️ Ai có token này = **chiếm quyền acc**. Không chia sẻ cho bất kỳ ai!"
                )
                try:
                    await ctx.author.send(dm_text)
                except Exception:
                    await self._reply(
                        ctx,
                        "❌ Không gửi được **DM** (hãy mở Tin nhắn riêng với bot). "
                        "Vì bảo mật, token **không** được gửi ra kênh.",
                        delay=30,
                    )
                    return
                await self._reply(
                    ctx,
                    "📬 **Đã gửi token acc qua DM** — kiểm tra hộp thư của bạn. "
                    "(Token không xuất hiện trong kênh)",
                    delay=30,
                )
                return

            await self._reply(
                ctx, "❌ Lựa chọn không hợp lệ — đã huỷ (token không lưu).", delay=20)
        finally:
            _QR_ACTIVE.discard(ctx.author.id)

    # ── gene start ───────────────────────────────────────────────────────
    @gene.command(name="start", aliases=("bat", "run"))
    @require_permission("user")
    async def gene_start(self, ctx: commands.Context, target: str = None, time_arg: str = "infinity"):
        """Gán thời gian sử dụng cho bot phụ (prime). Bot PHẢI được unlock trước:
        (prefix)gene unlock <@bot|id>  ->  (prefix)gene start <@bot|id> <time|infinity>
        """
        p = self._pfx()
        if not self._is_prime_bot():
            await self._reply(
                ctx,
                "⛔ **BOT PHỤ KHÔNG CÓ QUYỀN DUYỆT / KÍCH HOẠT BOT**\n"
                f"• Lệnh này chỉ dành riêng cho **Bot chính (Prime)**.\n"
                f"• Vui lòng dùng prefix của bot chính: `{_prime_prefix() or '!'}gene start ...`",
                delay=30,
            )
            return

        if not self._is_prime_admin(ctx.author.id):
            await self._reply(
                ctx,
                "⛔ **BẠN KHÔNG CÓ QUYỀN DUYỆT / KÍCH HOẠT BOT**\n"
                "• Lệnh này chỉ dành riêng cho **Admin cấp cao của bot chính** (Prime Admin).\n"
                "• Bot phụ và người dùng thông thường không có quyền thực hiện.",
                delay=30,
            )
            return

        if not target:
            await self._reply(ctx, f"❌ Cú pháp: `{p}gene start <@bot|id> <time|infinity>`", delay=25)
            return
        entry = self._resolve(target)
        if entry is None:
            await self._reply(ctx, f"❓ Không tìm thấy bot `{target}` trong sổ genesis.", delay=25)
            return
        name, bid = _norm(entry.get("name")), _norm(entry.get("bot_id"))
        # BAT BUOC phai unlock truoc - start KHONG tu mo khoa
        if status_of(entry) == STATUS_LOCK:
            await self._reply(
                ctx,
                f"🔒 Bot **{name}** (`{bid}`) đang bị **KHOÁ**.\n"
                f"➡️ Duyệt/mở khoá trước: `{p}gene unlock {bid}`\n"
                f"➡️ Rồi mới gán thời gian: `{p}gene start {bid} <time>`",
                delay=40,
            )
            return
        sec, label = parse_duration(time_arg)
        token = _norm(entry.get("token"))
        if not token:
            await self._reply(ctx, f"❌ Bot **{name}** (`{bid}`) chưa có token — không thể khởi động.", delay=30)
            return

        # 1. Gán thời gian sử dụng
        entry["time_user"] = label
        entry["expire_at"] = (time.time() + sec) if sec else None
        _write_config(_read_config())

        # 2. KHỞI ĐỘNG THẬT: login + nạp lệnh + prefix riêng, KHÔNG cần restart
        try:
            from apps.user_discord.core import runtime as _runtime
        except ImportError:
            from core import runtime as _runtime

        if _runtime.is_live(token):
            await self._reply(
                ctx,
                "✅ **BOT ĐANG ONLINE SẴN**\n"
                f"• Bot: **{name}** (`{bid}`)\n"
                f"• Thời gian: **{'∞ vô hạn' if label == TIME_INFINITY else label}**",
                delay=40,
            )
            return

        await self._reply(ctx, f"⏳ Đang khởi động bot **{name}** (`{bid}`)...", delay=15)
        spawn_pfx = _norm(entry.get("prefix")) if entry.get("prefix") is not None else ""
        ok, bot, msg = await _runtime.spawn(token, spawn_pfx, name)
        _log(f"[GENESIS] START '{name}' ({bid}) time={label} ok={ok} msg={msg} boi {ctx.author}")
        if ok:
            pfx_str = f"'{spawn_pfx}' (none)" if spawn_pfx == "" else f"`{spawn_pfx}`"
            await self._reply(
                ctx,
                "🚀 **ĐÃ KHỞI ĐỘNG BOT PHỤ**\n"
                f"• Bot: **{name}** (`{bid}`)\n"
                f"• Trạng thái: {msg}\n"
                f"• Prefix riêng: {pfx_str} | Thời gian: **{'∞ vô hạn' if label == TIME_INFINITY else label}**",
                delay=60,
            )
        else:
            await self._reply(
                ctx,
                f"❌ Không khởi động được bot **{name}** (`{bid}`): {msg}\n"
                "• Kiểm tra lại token (có thể sai / hết hạn).",
                delay=45,
            )

    @staticmethod
    async def _fetch_token_username(token: str) -> Optional[str]:
        """Tự động lấy tên hiển thị hoặc username từ Discord API bằng token."""
        if not token:
            return None
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.get("https://discord.com/api/v10/users/@me", headers={"Authorization": token}, timeout=aiohttp.ClientTimeout(total=4)) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data.get("global_name") or data.get("username")
        except Exception:
            pass
        return None

    # ── gene extend (gia hạn thêm thời gian sử dụng) ──────────────────────
    @gene.command(name="extend", aliases=("renew", "addtime", "giahan"))
    @require_permission("user")
    async def gene_extend(self, ctx: commands.Context, target: str = None, time_arg: str = None):
        """Gia hạn thêm thời gian sử dụng cho bot phụ (cộng dồn thời gian):
        (prefix)gene extend <@bot|id> <thời gian> (Ví dụ: 7d, 30d, 12h, 1d)
        """
        p = self._pfx()
        if not self._is_prime_bot():
            await self._reply(ctx, "⛔ Chỉ **Bot chính (Prime)** mới có quyền gia hạn thời gian bot phụ.", delay=25)
            return

        if not self._is_prime_admin(ctx.author.id):
            await self._reply(ctx, "⛔ Bạn không có quyền gia hạn bot (cần quyền Prime Admin).", delay=25)
            return

        if not target or not time_arg:
            await self._reply(ctx, f"❌ Cú pháp: `{p}gene extend <@bot|id> <thời gian>`\n💡 Ví dụ: `{p}gene extend G002 7d` (cộng thêm 7 ngày)", delay=25)
            return

        entry = self._resolve(target)
        if entry is None:
            await self._reply(ctx, f"❓ Không tìm thấy bot `{target}` trong sổ genesis.", delay=25)
            return

        name, bid = _norm(entry.get("name")), _norm(entry.get("bot_id"))
        sec, label = parse_duration(time_arg)
        if not sec:
            await self._reply(ctx, "❌ Định dạng thời gian không hợp lệ. Ví dụ: `7d` (7 ngày), `30d`, `12h`.", delay=25)
            return

        now = time.time()
        cur_exp = entry.get("expire_at")
        if cur_exp and cur_exp > now:
            new_exp = cur_exp + sec
        else:
            new_exp = now + sec

        entry["expire_at"] = new_exp
        entry["time_user"] = remaining_text(entry)
        _write_config(_read_config())
        _log(f"[GENESIS] EXTEND '{name}' ({bid}) +{label} boi {ctx.author}")

        await self._reply(
            ctx,
            "🎉 **GIA HẠN BOT THÀNH CÔNG**\n"
            f"• Bot: **{name}** (`{bid}`)\n"
            f"• Đã cộng thêm: **+{label}**\n"
            f"• Thời hạn mới: **{remaining_text(entry)}** (mốc: <t:{int(new_exp)}:F>)",
            delay=50,
        )

    # ── gene info (thẻ thông tin đồ họa Liquid Glass) ────────────────────
    @gene.command(name="info", aliases=("botinfo", "bi"))
    @require_permission("user")
    async def gene_info(self, ctx: commands.Context, target: str = None):
        """Xem thẻ thông tin đồ hoạ Liquid Glass đầy đủ của bot:
        (prefix)gene info [bot_id|@bot]
        """
        p = self._pfx()
        if not target:
            entry = self_entry(self.bot)
            if not entry:
                entry = next((a for a in _accounts(_read_config()) if role_of(a) == ROLE_PRIME), None)
        else:
            entry = self._resolve(target)

        if not entry:
            await self._reply(ctx, f"❌ Không tìm thấy bot `{target}` trong hệ thống.", delay=25)
            return

        try:
            buf = await self._render_gene_info_card(entry)
            file = discord.File(buf, filename="gene_bot_info.png")
            await self._reply_with_file(
                ctx,
                text=f"🧬 **THÔNG TIN BOT {entry.get('name', 'Bot')}** (`{entry.get('bot_id', '--')}`)",
                file=file,
                delay=60,
            )
        except Exception as e:
            print(f"[gene info] Lỗi vẽ card: {e}", flush=True)
            txt = (
                f"🧬 **THÔNG TIN BOT {_norm(entry.get('name'))}**\n"
                f"• Mã bot: `{entry.get('bot_id')}` | Role: `{role_of(entry).upper()}`\n"
                f"• Trạng thái: `{status_of(entry).upper()}` | Prefix: `{entry.get('prefix')}`\n"
                f"• Hạn dùng: **{remaining_text(entry)}**"
            )
            await self._reply(ctx, txt, delay=40)

    async def _render_gene_info_card(self, entry: Dict[str, Any]) -> io.BytesIO:
        try:
            from apps.user_discord.utils import glass as G
        except ImportError:
            from utils import glass as G

        import datetime

        name = _norm(entry.get("name")) or "Bot"
        bot_id = _norm(entry.get("bot_id")) or "G001"
        role = role_of(entry).upper()
        status = status_of(entry).upper()
        pfx = _norm(entry.get("prefix"))
        time_rem = remaining_text(entry)

        # ── Xử lý các mốc thời gian ──
        tu = _norm(entry.get("time_user")) or "Vô hạn"
        if tu.lower() in ("infinity", "inf", "vo_han", "vohan", "∞"):
            package_str = "Vĩnh viễn (∞)"
        else:
            package_str = tu

        exp_val = entry.get("expire_at")
        if exp_val and str(exp_val).lower() not in ("none", "null", ""):
            try:
                dt = datetime.datetime.fromtimestamp(float(exp_val))
                expire_str = dt.strftime("%d/%m/%Y %H:%M")
            except Exception:
                expire_str = "Không xác định"
        else:
            expire_str = "Vô hạn (Không hết hạn)"

        token = _norm(entry.get("token"))
        uid_val = self._uid_report(entry).get("any_uid") or _norm(entry.get("uid")) or "?"
        owner_ids = entry.get("owner_ids", [])
        owner_str = f"<@{owner_ids[0]}>" if owner_ids else f"<@{entry.get('created_by', '?')}>"

        is_live = False
        guild_count = 0
        ping_ms = 0
        avatar_img = None
        try:
            from apps.user_discord.core import runtime as _runtime
            live_bot = _runtime.get_live(token) if token else None
            if live_bot:
                is_live = True
                guild_count = len(getattr(live_bot, "guilds", []))
                ping_ms = int(getattr(live_bot, "latency", 0) * 1000)
                if live_bot.user and live_bot.user.display_avatar:
                    avatar_img = await G.fetch_image(str(live_bot.user.display_avatar.url))
        except Exception:
            pass

        if avatar_img is None and token:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as s:
                    av_data = await self._probe_token(s, token)
                    if av_data.get("avatar_url"):
                        avatar_img = await G.fetch_image(av_data["avatar_url"])
            except Exception:
                pass

        if is_expired(entry):
            license_lbl = "HẾT HẠN"
            license_col = (239, 68, 68)
        elif is_locked(entry):
            license_lbl = "BỊ KHOÁ"
            license_col = (245, 158, 11)
        elif is_live:
            license_lbl = "HOẠT ĐỘNG"
            license_col = (34, 197, 94)
        else:
            license_lbl = "SẴN SÀNG"
            license_col = (59, 130, 246)

        masked_token = (token[:10] + "..." + token[-6:]) if len(token) >= 20 else ("(Ẩn)" if token else "Chưa cấu hình")

        info = {
            "name": name,
            "bot_id": bot_id,
            "role": role,
            "status": status,
            "is_live": is_live,
            "pfx": pfx,
            "package": package_str,
            "time_rem": time_rem,
            "expire_at": expire_str,
            "license_lbl": license_lbl,
            "license_col": license_col,
            "uid": uid_val,
            "owners": owner_str,
            "token_masked": masked_token,
            "guilds": guild_count,
            "ping": ping_ms,
        }
        return await asyncio.to_thread(self._draw_gene_info_glass, G, info, avatar_img)

    @staticmethod
    def _draw_gene_info_glass(G, info: Dict[str, Any], avatar_img) -> io.BytesIO:
        pad, gap, head_h = 24, 14, 108
        stat_h1 = 78
        stat_h2 = 78
        bh = 196
        LW = 1180
        LH = pad + head_h + gap + stat_h1 + gap + stat_h2 + gap + bh + pad
        cv = G.GlassCanvas(LW, LH)

        # ── 1. HEADER: Avatar + Tên + Vai trò + ID + Live status pill ──
        cv.glass((pad, pad, LW - pad, pad + head_h), 24, blur=24)
        isz = 72
        ring_col = G.G_GREEN if info["is_live"] else (G.G_OFF if info["status"] == "LOCK" else G.G_PURPLE)
        cv.circle_image(avatar_img, pad + 20, pad + (head_h - isz) / 2, isz, ring=ring_col, ring_w=3, letter=info["name"][:1])

        tx = pad + 20 + isz + 18
        f_t = cv.font("modak", 24)
        tmax = LW - pad - 20 - 220 - tx
        name_fit = cv.fit(G.clean_text(info["name"]) or "Bot", f_t, tmax)
        tw = cv.text(tx, pad + head_h / 2 - 14, name_fit, f_t, G.C_TEXT, vcenter=True)
        role_pill_grad = G.G_AMBER if info["role"] == "PRIME" else G.G_BLUE
        cv.pill(tx + tw + 14, pad + head_h / 2 - 24, info["role"], cv.font("b", 11), role_pill_grad, h=20, padx=10)
        cv.text(tx, pad + head_h / 2 + 16, f"Bot ID: {info['bot_id']}   •   Discord UID: {info['uid']}", cv.font("r", 12.5), G.C_MUTED, vcenter=True)

        st_text = f"LIVE • {info['ping']}ms" if info["is_live"] else ("LOCKED" if info["status"] == "LOCK" else "STOPPED")
        st_grad = G.G_ON if info["is_live"] else (G.G_OFF if info["status"] == "LOCK" else G.G_SLATE)
        st_dot = (167, 255, 214) if info["is_live"] else (255, 170, 170)
        cv.glass_pill(LW - pad - 20, pad + head_h / 2 - 15, st_text, cv.font("b", 12), st_grad, align="r", dot=st_dot)

        # ── 2. HÀNG THỐNG KÊ 1: CHRONO & TIME METRICS (Thời gian & Cấp phép) ──
        sy1 = pad + head_h + gap
        time_stats = [
            ("GÓI CẤP PHÉP", info["package"], "⏱️", "P", (96, 165, 250)),
            ("THỜI GIAN CÒN LẠI", info["time_rem"], "⏳", "R", (52, 211, 153)),
            ("MỐC HẾT HẠN", info["expire_at"], "📅", "E", (167, 139, 250)),
            ("TRẠNG THÁI HẠN", info["license_lbl"], "🛡️", "S", info["license_col"]),
        ]
        tw_ = (LW - 2 * pad - 3 * gap) / 4
        for i, (lbl, val, sym, fb, col) in enumerate(time_stats):
            x1 = pad + i * (tw_ + gap)
            cv.glass((x1, sy1, x1 + tw_, sy1 + stat_h1), 18, blur=22, tint=(12, 16, 28, 50))
            cv.chip((x1 + 14, sy1 + 18, x1 + 52, sy1 + 58), sym, fb, col, r=11, size=18)
            vx = x1 + 64
            cv.text(vx, sy1 + 28, lbl, cv.font("b", 10), col, vcenter=True)
            cv.text(vx, sy1 + 50, cv.fit(val, cv.font("b", 13), x1 + tw_ - 12 - vx), cv.font("b", 13), G.C_TEXT, vcenter=True)

        # ── 3. HÀNG THỐNG KÊ 2: SYSTEM & HARDWARE (Hạ tầng kỹ thuật) ──
        sy2 = sy1 + stat_h1 + gap
        pfx_label = f"'{info['pfx']}'" if info['pfx'] else "(None / Trống)"
        sys_stats = [
            ("TIỀN TỐ (PREFIX)", pfx_label, "⌨️", "X", (251, 191, 36)),
            ("SỐ LƯỢNG MÁY CHỦ", f"{info['guilds']} servers", "🏰", "G", (34, 211, 238)),
            ("ĐỘ TRỄ GATEWAY", f"{info['ping']} ms" if info["is_live"] else "N/A", "⚡", "D", (74, 222, 128)),
            ("PHÂN QUYỀN HỆ THỐNG", f"{info['role']} / {info['status']}", "🧬", "R", (244, 114, 182)),
        ]
        for i, (lbl, val, sym, fb, col) in enumerate(sys_stats):
            x1 = pad + i * (tw_ + gap)
            cv.glass((x1, sy2, x1 + tw_, sy2 + stat_h2), 18, blur=22, tint=(12, 16, 28, 50))
            cv.chip((x1 + 14, sy2 + 18, x1 + 52, sy2 + 58), sym, fb, col, r=11, size=18)
            vx = x1 + 64
            cv.text(vx, sy2 + 28, lbl, cv.font("b", 10), col, vcenter=True)
            cv.text(vx, sy2 + 50, cv.fit(val, cv.font("b", 13), x1 + tw_ - 12 - vx), cv.font("b", 13), G.C_TEXT, vcenter=True)

        # ── 4. PANEL CHI TIẾT ĐÁY + QR CODE PROFILE DISCORD BOT ──
        by = sy2 + stat_h2 + gap
        cv.glass((pad, by, LW - pad, by + bh), 22, blur=24, tint=(14, 18, 30, 80))
        cv.text(pad + 24, by + 26, "CHI TIẾT VẬN HÀNH & KẾT NỐI HỆ THỐNG", cv.font("b", 13), G.C_GOLD, vcenter=True)

        # ── QR Code mở profile Bot trên Discord ──
        qr_box_w = 148
        qr_x2 = LW - pad - 20
        qr_x1 = qr_x2 - qr_box_w
        qr_y1 = by + 16
        qr_y2 = by + bh - 16

        cv.glass((qr_x1, qr_y1, qr_x2, qr_y2), 16, blur=18, tint=(255, 255, 255, 30), rim=(255, 90))
        try:
            import qrcode
            from PIL import Image, ImageOps
            qr = qrcode.QRCode(box_size=4, border=1)
            target_qr_url = f"https://discord.com/users/{info['uid']}" if (info["uid"] and str(info["uid"]) != "?") else "https://discord.com"
            qr.add_data(target_qr_url)
            qr.make(fit=True)
            qr_raw = qr.make_image(fill_color=(15, 23, 42), back_color=(255, 255, 255)).convert("RGBA")
            q_sz = int(cv.s(112))
            qr_fitted = qr_raw.resize((q_sz, q_sz), Image.Resampling.NEAREST)
            q_x = int(cv.s(qr_x1 + (qr_box_w - 112) / 2))
            q_y = int(cv.s(qr_y1 + 10))
            white_bg = Image.new("RGBA", (q_sz + 4, q_sz + 4), (255, 255, 255, 255))
            cv.c.paste(white_bg, (q_x - 2, q_y - 2))
            cv.c.paste(qr_fitted, (q_x, q_y))
            cv.text((qr_x1 + qr_x2) / 2, qr_y2 - 13, "QUÉT PROFILE BOT", cv.font("b", 10), G.C_GOLD, align="c", vcenter=True)
        except Exception as _ge:
            print(f"[geneinfo QR error]: {_ge}", flush=True)
            cv.text((qr_x1 + qr_x2) / 2, (qr_y1 + qr_y2) / 2, "GENESIS QR", cv.font("b", 11), G.C_MUTED, align="c", vcenter=True)

        # ── Thông tin bên trái ──
        text_max_w = qr_x1 - (pad + 24) - 24
        pfx_desc = f"Lệnh gọi: '{info['pfx']}' (đổi: (prefix)gene prefix <mới>)" if info['pfx'] else "Không có prefix (gọi trực tiếp / không tiền tố)"
        detail_lines = [
            ("Chủ sở hữu / Tạo bởi: ", f"{info['owners']}"),
            ("Cấu hình tiền tố: ", pfx_desc),
            ("Thời hạn sử dụng: ", f"{info['package']} • Còn lại: {info['time_rem']} • Hết hạn: {info['expire_at']}"),
            ("Gia hạn & Cập nhật: ", f"(prefix)gene extend {info['bot_id']} <time>  hoặc  (prefix)gene update {info['bot_id']} <token>"),
            ("Mã Token bảo mật: ", f"`{info['token_masked']}` | Mã bot: {info['bot_id']}"),
        ]
        dy = by + 52
        for title_l, val_l in detail_lines:
            val_fit = cv.fit(val_l, cv.font("b", 12), text_max_w - cv.tlen(title_l, cv.font("r", 12)))
            cv.rich(pad + 24, dy, [(title_l, cv.font("r", 12), G.C_MUTED), (val_fit, cv.font("b", 12), G.C_TEXT)], vcenter=True)
            dy += 26

        return cv.finalize()

    def _resolve_target_strict(self, raw: str) -> Optional[Dict[str, Any]]:
        """Chỉ tìm bot theo: @mention | Discord UID (trong sổ/từ token/live) | Mã bot (G00x).
        TUYỆT ĐỐI KHÔNG tìm theo tên chuỗi thường để tránh nhầm lẫn với prefix như 'none', '!', '.'...
        """
        raw = _norm(raw)
        if not raw:
            return None
        cfg = _read_config()
        uid = 0
        if raw.startswith("<@") and raw.endswith(">"):
            uid = int("".join(ch for ch in raw if ch.isdigit()) or 0)
        elif raw.isdigit() and len(raw) >= 15:
            uid = int(raw)
        else:
            guessed = _uid_from_token(raw)
            if guessed:
                uid = guessed

        if uid:
            for acc in _accounts(cfg):
                if uid in self._entry_uids(acc):
                    return acc

        # Mã bot G00x (bắt buộc định dạng G + chữ số, vd: G001, G004)
        low = raw.lower()
        if low.startswith("g") and len(low) >= 2 and low[1:].isdigit():
            for acc in _accounts(cfg):
                if _norm(acc.get("bot_id")).lower() == low:
                    return acc

        return None

    # ── gene prefix ──────────────────────────────────────────────────────
    @gene.command(name="prefix", aliases=("setprefix", "pfx", "doiprefix"))
    @require_permission("user")
    async def gene_prefix(self, ctx: commands.Context, arg1: str = None, *, arg2: str = ""):
        """Đổi prefix cho bot (dùng được ngay không cần restart):
        • Đổi cho chính bot này: (prefix)gene prefix <prefix_mới>  (Gõ 'none' để không dùng prefix)
        • Đổi cho bot chỉ định: (prefix)gene prefix <@bot|UID|Mã_G00x> <prefix_mới>
        """
        p = self._pfx()
        author = ctx.author.id

        # 0. Tránh bị spam / cấm
        try:
            from apps.user_discord.core.bot_sys import is_cammed
            if is_cammed(self.bot, author):
                return
        except Exception:
            pass

        try:
            from apps.user_discord.utils.prefix import set_prefix, get_prefix as u_get_pfx
        except ImportError:
            from utils.prefix import set_prefix, get_prefix as u_get_pfx

        try:
            from apps.user_discord.core import runtime as _runtime
        except ImportError:
            from core import runtime as _runtime

        # 1. Không truyền tham số nào -> hiển thị prefix hiện tại & hướng dẫn
        if not arg1 and not arg2:
            cur = u_get_pfx(self.bot)
            cur_lbl = f"`{cur}`" if cur else "Không dùng prefix (No Prefix)"
            await self._reply(
                ctx,
                f"📌 **PREFIX HIỆN TẠI CỦA BOT NÀY**: **{cur_lbl}**\n"
                f"• Đổi cho chính bot này: `{p}gene prefix <prefix_mới>` (Gõ `none` nếu không muốn dùng tiền tố)\n"
                f"• Đổi cho bot khác: `{p}gene prefix <@bot|UID|G00x> <prefix_mới>` *(Chỉ dùng tag, UID hoặc mã bot)*",
                delay=30,
            )
            return

        target_entry = None
        new_prefix_raw = ""

        # 2. Phân tích tham số: 2 tham số hay 1 tham số
        if arg1 and arg2:
            # Dạng: gene prefix <target> <new_prefix>
            target_entry = self._resolve_target_strict(arg1)
            if not target_entry:
                await self._reply(
                    ctx,
                    f"❌ **Không tìm thấy bot có định danh `{arg1}`!**\n"
                    f"💡 Lưu ý: Hệ thống chỉ nhận diện bằng **@tag**, **Discord UID** (17-20 số) hoặc **Mã bot (G00x)** — không dùng tên.",
                    delay=25,
                )
                return
            new_prefix_raw = arg2.strip()
        elif arg1 and not arg2:
            # Kiểm tra xem arg1 có phải là target (tag/uid/bot_id) hay chính là prefix mới
            target_cand = self._resolve_target_strict(arg1)
            if target_cand:
                # User chỉ gõ target mà quên gõ prefix mới -> hướng dẫn
                bot_lbl = _norm(target_cand.get("name")) or target_cand.get("bot_id")
                await self._reply(
                    ctx,
                    f"💡 Bạn đã chọn bot **{bot_lbl}** (`{target_cand.get('bot_id')}`). Vui lòng nhập thêm prefix mới:\n"
                    f"👉 `{p}gene prefix {arg1} <prefix_mới>` (hoặc gõ `none` để không dùng prefix).",
                    delay=25,
                )
                return
            else:
                # arg1 không phải là target bot -> ĐÂY CHÍNH LÀ PREFIX MỚI CHO BOT HIỆN TẠI
                target_entry = self_entry(self.bot)
                if not target_entry:
                    cfg_init = _read_config()
                    target_entry = next((a for a in _accounts(cfg_init) if role_of(a) == ROLE_PRIME), None)
                new_prefix_raw = arg1.strip()

        if not target_entry:
            await self._reply(ctx, "❌ Không tìm thấy thông tin bot cần đổi prefix trong sổ Genesis.", delay=25)
            return

        # 3. Kiểm tra quyền hạn
        is_current_bot = (target_entry.get("bot_id") == getattr(self_entry(self.bot), "get", lambda k: None)("bot_id")) or (
            getattr(getattr(self.bot, "user", None), "id", None) in self._entry_uids(target_entry)
        )
        if not self._is_prime_admin(author) and author not in self._target_admin_ids(target_entry):
            await self._reply(
                ctx,
                f"⛔ **TỪ CHỐI — BẠN KHÔNG CÓ QUYỀN ĐỔI PREFIX CHO BOT NÀY**\n"
                f"• Chỉ **Admin cấp cao của bot này** hoặc **Admin cấp cao Bot chính** mới có quyền đổi.",
                delay=25,
            )
            return

        # 4. Chuẩn hoá prefix mới
        is_none = new_prefix_raw.lower() in ("none", "no", "off", "empty", "trong", "null")
        new_prefix = "" if is_none else new_prefix_raw

        # 5. Áp dụng ngay cho bot runtime trong tiến trình
        applied_runtime = False
        if is_current_bot:
            ok, msg = set_prefix(self.bot, new_prefix, persist=True)
            applied_runtime = True
        else:
            # Tìm bot phụ đang LIVE
            tok = _norm(target_entry.get("token"))
            live_bot = _runtime.find_live_bot(token=tok, uid=target_entry.get("uid"), bot_id=target_entry.get("bot_id"))
            if live_bot:
                ok, msg = set_prefix(live_bot, new_prefix, persist=True)
                applied_runtime = True

        # 6. Đồng bộ lưu vĩnh viễn vào config.json
        cfg = _read_config()
        for a in _accounts(cfg):
            if _norm(a.get("bot_id")) == _norm(target_entry.get("bot_id")) or _norm(a.get("token")) == _norm(target_entry.get("token")):
                a["prefix"] = new_prefix
                break
        _write_config(cfg)

        _log(f"[GENESIS] PREFIX bot {_norm(target_entry.get('name'))} ({target_entry.get('bot_id')}) doi thanh {new_prefix!r} boi {ctx.author} ({author})")
        pfx_lbl = f"`{new_prefix}`" if new_prefix else "Không dùng prefix (No Prefix)"
        sample_call = f"`{new_prefix}menu`" if new_prefix else "`menu`"

        status_note = "Đã áp dụng tức thì cho bot đang chạy!" if applied_runtime else "Đã lưu vào cấu hình (sẽ áp dụng khi bot online)."
        await self._reply(
            ctx,
            f"✅ **ĐÃ ĐỔI PREFIX BOT THÀNH CÔNG**\n"
            f"• Bot: **{_norm(target_entry.get('name'))}** (`{target_entry.get('bot_id')}` • UID: `{target_entry.get('uid') or '?'}`)\n"
            f"• Prefix mới: **{pfx_lbl}**\n"
            f"• Ví dụ gọi lệnh: {sample_call}\n"
            f"• Trạng thái: {status_note}",
            delay=35,
        )
        return

    # ── gene lock ────────────────────────────────────────────────────────
    @gene.command(name="lock", aliases=("khoa",))
    @require_permission("user")
    async def gene_lock(self, ctx: commands.Context, target: str = None):
        """Khoá bot phụ - chặn mọi lệnh nhưng bot vẫn online (prime): (prefix)gene lock <@bot|id>"""
        p = self._pfx()
        if not self._is_prime_bot():
            await self._reply(
                ctx,
                "⛔ **BOT PHỤ KHÔNG CÓ QUYỀN KHÓA BOT**\n"
                f"• Lệnh này chỉ dành riêng cho **Bot chính (Prime)**.\n"
                f"• Vui lòng dùng prefix của bot chính: `{_prime_prefix() or '!'}gene lock ...`",
                delay=30,
            )
            return

        if not self._is_prime_admin(ctx.author.id):
            await self._reply(
                ctx,
                "⛔ **BẠN KHÔNG CÓ QUYỀN KHÓA BOT**\n"
                "• Lệnh này chỉ dành riêng cho **Admin cấp cao của bot chính** (Prime Admin).\n"
                "• Bot phụ và người dùng thông thường không có quyền thực hiện.",
                delay=30,
            )
            return

        entry = self._resolve(target) if target else None
        if entry is None:
            await self._reply(ctx, f"❌ Cú pháp: `{p}gene lock <@bot|id>`", delay=25)
            return
        name, bid = _norm(entry.get("name")), _norm(entry.get("bot_id"))
        if role_of(entry) == ROLE_PRIME or (_norm(entry.get("token")) and _norm(entry.get("token")) == _norm(token_of(self.bot))):
            await self._reply(ctx, "❌ Không thể khoá **bot chính (prime)**.", delay=25)
            return
        entry["status"] = STATUS_LOCK
        entry["expire_at"] = None
        _write_config(_read_config())
        _log(f"[GENESIS] LOCK '{name}' ({bid}) boi {ctx.author}")
        await self._reply(ctx, f"🔒 Đã **KHOÁ** bot **{name}** (`{bid}`).", delay=45)

    # ── gene unlock ──────────────────────────────────────────────────────
    @gene.command(name="unlock", aliases=("mokhoa",))
    @require_permission("user")
    async def gene_unlock(self, ctx: commands.Context, target: str = None):
        """Mở khoá / duyệt bot phụ, giữ nguyên mốc thời gian cũ (prime): (prefix)gene unlock <@bot|id>"""
        p = self._pfx()
        if not self._is_prime_bot():
            await self._reply(
                ctx,
                "⛔ **BOT PHỤ KHÔNG CÓ QUYỀN DUYỆT / MỞ KHÓA BOT**\n"
                f"• Lệnh này chỉ dành riêng cho **Bot chính (Prime)**.\n"
                f"• Vui lòng dùng prefix của bot chính: `{_prime_prefix() or '!'}gene unlock ...`",
                delay=30,
            )
            return

        if not self._is_prime_admin(ctx.author.id):
            await self._reply(
                ctx,
                "⛔ **BẠN KHÔNG CÓ QUYỀN DUYỆT / MỞ KHÓA BOT**\n"
                "• Quyền duyệt và mở khoá bot chỉ dành riêng cho **Admin cấp cao của bot chính** (Prime Admin).\n"
                "• Bot phụ và người dùng thông thường không có quyền duyệt bot.",
                delay=30,
            )
            return

        entry = self._resolve(target) if target else None
        if entry is None:
            await self._reply(ctx, f"❌ Cú pháp: `{p}gene unlock <@bot|id>`", delay=25)
            return
        entry["status"] = STATUS_UNLOCK
        _write_config(_read_config())
        _log(f"[GENESIS] UNLOCK '{_norm(entry.get('name'))}' ({_norm(entry.get('bot_id'))}) boi {ctx.author}")
        await self._reply(ctx, f"🔓 Đã **MỞ KHOÁ** bot **{_norm(entry.get('name'))}** (`{_norm(entry.get('bot_id'))}`).", delay=45)

    # ── gene stop ────────────────────────────────────────────────────────
    @gene.command(name="stop", aliases=("dung",))
    @require_permission("user")
    async def gene_stop(self, ctx: commands.Context, target: str = None):
        """Tắt (shutdown) bot phụ và đưa về khoá (prime): (prefix)gene stop <@bot|id>"""
        p = self._pfx()
        if not self._is_prime_bot():
            await self._reply(
                ctx,
                "⛔ **BOT PHỤ KHÔNG CÓ QUYỀN DỪNG BOT**\n"
                f"• Lệnh này chỉ dành riêng cho **Bot chính (Prime)**.\n"
                f"• Vui lòng dùng prefix của bot chính: `{_prime_prefix() or '!'}gene stop ...`",
                delay=30,
            )
            return

        if not self._is_prime_admin(ctx.author.id):
            await self._reply(
                ctx,
                "⛔ **BẠN KHÔNG CÓ QUYỀN DỪNG BOT**\n"
                "• Lệnh này chỉ dành riêng cho **Admin cấp cao của bot chính** (Prime Admin).\n"
                "• Bot phụ và người dùng thông thường không có quyền thực hiện.",
                delay=30,
            )
            return
        entry = self._resolve(target) if target else None
        if entry is None:
            await self._reply(ctx, f"❌ Cú pháp: `{p}gene stop <@bot|id>`", delay=25)
            return
        name, bid = _norm(entry.get("name")), _norm(entry.get("bot_id"))
        token = _norm(entry.get("token"))
        if role_of(entry) == ROLE_PRIME or (token and token == _norm(token_of(self.bot))):
            await self._reply(ctx, "❌ Không thể dừng **bot chính (prime)**.", delay=25)
            return
        entry["status"] = STATUS_LOCK
        entry["expire_at"] = None
        _write_config(_read_config())
        stopped = False
        if token:
            try:
                from apps.user_discord.core import runtime as _runtime
            except ImportError:
                from core import runtime as _runtime
            stopped = await _runtime.shutdown(token)
        _log(f"[GENESIS] STOP '{name}' ({bid}) stopped={stopped} boi {ctx.author}")
        await self._reply(
            ctx,
            f"⏹️ Đã **DỪNG** bot **{name}** (`{bid}`).\n"
            f"• Tiến trình: {'đã tắt' if stopped else 'không đang chạy'}\n"
            "• Trạng thái: `lock` 🔒",
            delay=45,
        )

    # ── gene update (cập nhật token mới) ─────────────────────────────────
    @gene.command(name="update", aliases=("upd", "settoken", "token"))
    @require_permission("user")
    async def gene_update(self, ctx: commands.Context, target_arg: str = None, new_token_arg: str = None):
        """Cập nhật token mới cho bot.
        Hỗ trợ:
        - Gõ trực tiếp: (prefix)gene update <@bot|uid|bot_id> <token_mới> (tự xoá tin nhắn gốc để chống lộ)
        - Gõ không tham số: bot gửi ảnh danh sách bot để chọn (Lần 1) -> yêu cầu gửi token và tự xoá ngay (Lần 2).
        - Admin bot chính hoặc Admin cấp cao bot phụ đều dùng được!
        """
        p = self._pfx()
        author_id = ctx.author.id
        is_prime_admin = self._is_prime_admin(author_id)
        user_admin_bots = self._user_admin_bots(author_id)

        # Kiểm tra quyền tối thiểu
        if not is_prime_admin and not user_admin_bots:
            await self._reply(
                ctx,
                "⛔ **BẠN KHÔNG CÓ QUYỀN QUẢN LÝ BOT**\n"
                "• Lệnh này chỉ dành cho **Admin cấp cao của bot chính** hoặc **Admin cấp cao của bot phụ**.",
                delay=30,
            )
            return

        # Nếu người dùng gửi thẳng token trong câu lệnh -> xoá ngay tin nhắn gốc để bảo mật
        if new_token_arg:
            try:
                await ctx.message.delete()
            except Exception:
                pass

        target = target_arg.strip() if target_arg else ""
        new_token = new_token_arg.strip() if new_token_arg else ""

        entry = None
        if target:
            entry = self._resolve(target)
            if entry is None:
                guess_uid = _uid_from_token(target)
                if guess_uid:
                    entry = self._resolve(str(guess_uid))

        # ── LẦN 1: Nếu chưa có target -> gửi ẢNH danh sách bot để người dùng chọn ──
        if entry is None:
            # Lọc danh sách bot mà người gọi có quyền
            if is_prime_admin:
                candidates = _accounts(_read_config())
            else:
                candidates = user_admin_bots

            if not candidates:
                await self._reply(ctx, "📭 Không có bot nào trong danh sách quản lý của bạn.", delay=25)
                return

            card_file = await self._reset_card_file(
                candidates,
                title="🔑 CHỌN BOT ĐỂ CẬP NHẬT TOKEN",
                tip=f"Gửi số 1…{len(candidates)}, mã bot hoặc @tag trong 45 giây.",
                filename="gene_update_pick.png",
            )
            prompt = (
                "🔑 **CHỌN BOT CẦN CẬP NHẬT TOKEN** (Lần 1/2)\n"
                f"• Hãy gửi số thứ tự `1`…`{len(candidates)}`, mã bot (`G00x`) hoặc `@tag` bot trong 45 giây (gõ `c` để huỷ)."
            )
            if card_file is None:
                prompt += "\n" + "\n".join(
                    f"`{idx}.` **{_norm(acc.get('name')) or 'Bot'}** (`{_norm(acc.get('bot_id')) or '--'}`)"
                    for idx, acc in enumerate(candidates, 1)
                )

            await self._reply_with_file(ctx, prompt, file=card_file, delay=60)

            def check_choice(m: discord.Message) -> bool:
                return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

            try:
                choice_msg = await self.bot.wait_for("message", check=check_choice, timeout=45.0)
            except asyncio.TimeoutError:
                await self._reply(ctx, "⌛ Hết thời gian chọn bot. Lệnh cập nhật token đã huỷ.", delay=20)
                return

            choice = choice_msg.content.strip().lower()
            if choice in ("c", "cancel", "huy", "hủy"):
                await self._reply(ctx, "Đã huỷ cập nhật token.", delay=15)
                return

            if choice.isdigit() and 1 <= int(choice) <= len(candidates):
                entry = candidates[int(choice) - 1]
            else:
                entry = self._resolve(choice)
                if entry is None:
                    guess_u = _uid_from_token(choice)
                    if guess_u:
                        entry = self._resolve(str(guess_u))

            if entry is None:
                await self._reply(ctx, f"❌ Lựa chọn `{choice}` không khớp bot nào. Hãy thử lại: `{p}gene update`", delay=20)
                return

        # Kiểm tra quyền riêng trên entry đã chọn: nếu không phải prime admin thì phải là admin bot này
        if not is_prime_admin and author_id not in self._target_admin_ids(entry):
            await self._reply(ctx, f"⛔ Bạn không phải admin cấp cao của bot **{_norm(entry.get('name'))}**.", delay=25)
            return

        name, bid = _norm(entry.get("name")), _norm(entry.get("bot_id"))
        old_token = _norm(entry.get("token"))

        # ── LẦN 2: Yêu cầu gửi TOKEN mới + TỰ XOÁ TIN NHẮN NGAY LẬP TỨC ──
        if not new_token:
            prompt_step2 = (
                f"🔐 **GỬI TOKEN MỚI CHO BOT** **{name}** (`{bid}`) (Lần 2/2)\n"
                "• Hãy gửi chuỗi Token Discord mới trong vòng 60 giây (gõ `c` để huỷ).\n"
                "🛡️ **CƠ CHẾ BẢO MẬT**: Bot sẽ **tự động xoá ngay lập tức** tin nhắn chứa token của bạn!\n"
                "_(Khuyên dùng: Nếu ở server mà bot KHÔNG có quyền Quản lý tin nhắn (Manage Messages), bot sẽ không thể tự xoá tin nhắn của bạn. Tốt nhất nên sang server khác nơi bot có quyền Admin hoặc nhắn riêng DM cho bot!)_"
            )
            await self._reply(ctx, prompt_step2, delay=60)

            def check_token_msg(m: discord.Message) -> bool:
                return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

            try:
                tok_msg = await self.bot.wait_for("message", check=check_token_msg, timeout=60.0)
            except asyncio.TimeoutError:
                await self._reply(ctx, f"⌛ Hết thời gian gửi token cho bot **{name}**. Đã huỷ.", delay=20)
                return

            # XÓA NGAY LẬP TỨC tin nhắn của người dùng để chống lộ token!
            try:
                await tok_msg.delete()
            except Exception:
                pass

            tok_txt = tok_msg.content.strip()
            if tok_txt.lower() in ("c", "cancel", "huy", "hủy"):
                await self._reply(ctx, "Đã huỷ cập nhật token.", delay=15)
                return

            new_token = tok_txt

        if not new_token:
            await self._reply(ctx, "❌ Token không hợp lệ.", delay=20)
            return

        # Ghi nhận UID giải mã từ token mới
        new_uid = _uid_from_token(new_token)
        cfg = _read_config()

        # Tìm đúng entry trong config để cập nhật
        target_entry = None
        for a in _accounts(cfg):
            if _norm(a.get("bot_id")) == bid or (bid and _norm(a.get("bot_id")).lower() == bid.lower()):
                target_entry = a
                break
            if _norm(a.get("token")) == old_token:
                target_entry = a
                break

        if target_entry is None:
            target_entry = entry

        target_entry["token"] = new_token
        if new_uid:
            target_entry["uid"] = new_uid

        if not _write_config(cfg):
            await self._reply(ctx, "❌ Không thể ghi cập nhật vào config.json.", delay=25)
            return

        _log(f"[GENESIS] UPDATE TOKEN cho bot '{name}' ({bid}) boi {ctx.author} ({ctx.author.id})")

        # Runtime reload: tắt bot cũ (nếu đang chạy)
        try:
            from apps.user_discord.core import runtime as _runtime
        except ImportError:
            from core import runtime as _runtime

        if old_token:
            await _runtime.shutdown(old_token)

        masked_tok = (new_token[:8] + "..." + new_token[-6:]) if len(new_token) > 16 else "***"
        if status_of(target_entry) == STATUS_LOCK:
            st_text = f"🔒 Bot đang ở trạng thái `lock`. Hãy mở khoá và khởi động: `{p}gene unlock {bid}` -> `{p}gene start {bid} <time|infinity>`"
        else:
            st_text = f"➡️ Hãy khởi động bot bằng lệnh: `{p}gene start {bid} <time|infinity>`"

        await self._reply(
            ctx,
            "🧬 **ĐÃ CẬP NHẬT TOKEN THÀNH CÔNG**\n"
            f"• Bot: **{name}** (`{bid}`)\n"
            f"• UID: `{new_uid or target_entry.get('uid') or 'chưa xác định'}`\n"
            f"• Token mới: `{masked_tok}`\n"
            "🛡️ _(Tin nhắn chứa token đã được tự động xoá an toàn)_\n"
            f"• {st_text}",
            delay=60,
        )

    # ── helpers cho gene list (probe token + avatar) ─────────────────────
    async def _probe_token(self, session, token: str) -> Dict[str, Any]:
        """Kiểm tra token qua API /users/@me -> state + avatar_url + uid."""
        try:
            async with session.get(
                "https://discord.com/api/v10/users/@me",
                headers={"Authorization": token},
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    uid = str(data.get("id") or "")
                    av = data.get("avatar")
                    if uid and av:
                        url = f"https://cdn.discordapp.com/avatars/{uid}/{av}.png?size=512"
                    elif uid:
                        url = f"https://cdn.discordapp.com/embed/avatars/{(int(uid) >> 22) % 6}.png"
                    else:
                        url = None
                    return {"state": "login", "uid": uid or None, "avatar_url": url}
                return {"state": "bad_token", "uid": None, "avatar_url": None}
        except Exception:
            return {"state": "error", "uid": None, "avatar_url": None}

    async def _fetch_av(self, session, url: str) -> Optional[bytes]:
        try:
            async with session.get(url) as r:
                if r.status == 200:
                    return await r.read()
        except Exception:
            pass
        return None

    def _row_static(self, acc: Dict[str, Any], state: str = None, avatar_bytes=None) -> Dict[str, Any]:
        token = _norm(acc.get("token"))
        locked = is_locked(acc)
        is_shard = (role_of(acc) == ROLE_SHARD)
        try:
            from apps.user_discord.core import runtime as _runtime
            is_live = _runtime.is_live(token)
        except Exception:
            is_live = False

        if not state:
            if not token:
                calc_state = "no_token"
            elif locked:
                calc_state = "locked"
            elif is_shard and not is_live:
                calc_state = "stopped"
            else:
                calc_state = "login"
        else:
            calc_state = state

        return {
            "name": _norm(acc.get("name")) or "?",
            "bot_id": _norm(acc.get("bot_id")) or "--",
            "uid": _norm(acc.get("uid")) or None,
            # uid ghi trong so (giu rieng de CHECK voi uid THAT lay tu Discord)
            "uid_cfg": _norm(acc.get("uid")) or None,
            "prefix": _norm(acc.get("prefix")) or None,
            "role": role_of(acc),
            "status": status_of(acc),
            "locked": locked,
            "time": remaining_text(acc),
            "state": calc_state,
            "avatar_bytes": avatar_bytes,
        }

    async def _row_for(self, session, acc: Dict[str, Any]) -> Dict[str, Any]:
        token = _norm(acc.get("token"))
        row = self._row_static(acc, state="no_token")
        if not token:
            return row
        probe = await self._probe_token(session, token)
        if probe.get("uid"):
            row["uid"] = probe["uid"]
        if probe.get("avatar_url"):
            row["avatar_bytes"] = await self._fetch_av(session, probe["avatar_url"])

        locked = is_locked(acc)
        is_shard = (role_of(acc) == ROLE_SHARD)
        try:
            from apps.user_discord.core import runtime as _runtime
            is_live = _runtime.is_live(token)
        except Exception:
            is_live = False

        if probe["state"] != "login":
            row["state"] = probe["state"]
        elif locked:
            row["state"] = "locked"
        elif is_shard and not is_live:
            row["state"] = "stopped"
        else:
            row["state"] = "login"
        return row

    async def _collect_rows(self, accts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Dựng dữ liệu từng dòng: có token -> thử login lấy avatar; không token -> báo thiếu."""
        rows: List[Dict[str, Any]] = []
        try:
            import aiohttp
        except ImportError:
            aiohttp = None
        if aiohttp is not None:
            try:
                timeout = aiohttp.ClientTimeout(total=8)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    for acc in accts:
                        rows.append(await self._row_for(session, acc))
                return rows
            except Exception:
                rows = []
        for acc in accts:
            rows.append(self._row_static(acc))
        return rows

    # ── gene list ────────────────────────────────────────────────────────
    @gene.command(name="list", aliases=("ls", "all"))
    @require_permission("user")
    async def gene_list(self, ctx: commands.Context):
        """Xem danh sách bot dạng ẢNH: avatar / role / thời gian / trạng thái (prime): (prefix)gene list"""
        if not self._is_prime_bot():
            await self._reply(
                ctx,
                "⛔ **BOT PHỤ KHÔNG CÓ QUYỀN XEM SỔ GENESIS**\n"
                f"• Lệnh này chỉ dành riêng cho **Bot chính (Prime)**.\n"
                f"• Vui lòng dùng prefix của bot chính: `{_prime_prefix() or '!'}gene list`",
                delay=30,
            )
            return

        if not self._is_prime_admin(ctx.author.id):
            await self._reply(
                ctx,
                "⛔ **BẠN KHÔNG CÓ QUYỀN XEM SỔ GENESIS**\n"
                "• Sổ danh sách bot chỉ dành riêng cho **Admin cấp cao của bot chính** (Prime Admin).\n"
                "• Bot phụ và người dùng thông thường không có quyền xem.",
                delay=30,
            )
            return

        accts = _accounts(_read_config())
        if not accts:
            await self._reply(ctx, "📭 Sổ genesis trống — chưa có bot nào.", delay=30)
            return
        rows = await self._collect_rows(accts)

        # 1. Ưu tiên gửi ẢNH (avatar thật của từng bot)
        card_file = None
        try:
            try:
                from apps.user_discord.utils.media_card import async_genesis_list_card
            except ImportError:
                from utils.media_card import async_genesis_list_card
            buf = await async_genesis_list_card(rows, self._pfx())
            if buf:
                card_file = discord.File(buf, filename="gene_list.png")
        except Exception:
            card_file = None
        if card_file is not None:
            try:
                from apps.user_discord.utils.autorep import autorep
            except ImportError:
                from utils.autorep import autorep
            await autorep(ctx.message, content="🧬 **SỔ GENESIS — DANH SÁCH BOT**", file=card_file, auto_delete_delay=60)
            return

        # 2. Fallback: bảng text nếu không render được ảnh
        stt_map = {
            "login": "🟢 login", "locked": "🔒 locked", "stopped": "⏹️ stopped",
            "no_token": "⚪ chưa có token", "bad_token": "🔴 token lỗi", "error": "🟠 lỗi kết nối"
        }
        lines = []
        for r in rows:
            icon = "👑" if r["role"] == ROLE_PRIME else "🔷"
            state = "🔒 locked" if r["locked"] else "🔓 active"
            lines.append(
                f"{icon} `{r['bot_id']}` **{r['name']}** (uid: `{r['uid'] or 'chưa login'}`)\n"
                f"     • prefix: `{r.get('prefix') or '-'}` | role: `{r['role']}` | "
                f"status: `{r['status']}` {state} | {stt_map.get(r['state'], r['state'])} | thời gian: **{r['time']}**"
            )
        await self._reply(ctx, "🧬 **SỔ GENESIS — DANH SÁCH BOT**\n\n" + "\n".join(lines), delay=60)

    # ── gene remove ──────────────────────────────────────────────────────
    @gene.command(name="remove", aliases=("del", "delete", "xoa"))
    @require_permission("user")
    async def gene_remove(self, ctx: commands.Context, target: str = None):
        """Xoá bot khỏi config.json; bỏ trống để chọn từ ảnh danh sách bot."""
        p = self._pfx()
        if not self._is_prime_bot():
            await self._reply(
                ctx,
                "⛔ **BOT PHỤ KHÔNG CÓ QUYỀN XOÁ BOT**\n"
                f"• Lệnh này chỉ dành riêng cho **Bot chính (Prime)**.\n"
                f"• Vui lòng dùng prefix của bot chính: `{_prime_prefix() or '!'}gene remove ...`",
                delay=30,
            )
            return

        if not self._is_prime_admin(ctx.author.id):
            await self._reply(
                ctx,
                "⛔ **BẠN KHÔNG CÓ QUYỀN XOÁ BOT**\n"
                "• Lệnh xoá bot chỉ dành riêng cho **Admin cấp cao của bot chính** (Prime Admin).\n"
                "• Bot phụ và người dùng thông thường không có quyền thực hiện.",
                delay=30,
            )
            return
        entry = self._resolve(target) if target else None
        if target and entry is None:
            await self._reply(ctx, f"❌ Không tìm thấy bot `{target}` trong sổ Genesis.", delay=25)
            return

        if entry is None:
            candidates = [acc for acc in _accounts(_read_config()) if role_of(acc) == ROLE_SHARD]
            if not candidates:
                await self._reply(ctx, "📭 Không có bot phụ nào để xoá.", delay=25)
                return

            card_file = await self._reset_card_file(
                candidates,
                title="🗑️ CHỌN BOT ĐỂ XÓA",
                tip=f"Gửi số 1…{len(candidates)} trong 45 giây để xác nhận chọn bot.",
                filename="gene_remove.png",
            )
            prompt = f"🗑️ **CHỌN BOT ĐỂ XÓA** — Gửi số `1`…`{len(candidates)}` trong 45 giây, hoặc `c` để hủy."
            if card_file is None:
                prompt += "\n" + "\n".join(
                    f"`{idx}.` **{_norm(acc.get('name')) or 'Bot'}** (`{_norm(acc.get('bot_id')) or '--'}`)"
                    for idx, acc in enumerate(candidates, 1)
                )
            await self._reply_with_file(ctx, prompt, file=card_file, delay=60)

            def check_choice(message: discord.Message) -> bool:
                return message.author.id == ctx.author.id and message.channel.id == ctx.channel.id

            try:
                choice_msg = await self.bot.wait_for("message", check=check_choice, timeout=45.0)
            except asyncio.TimeoutError:
                await self._reply(ctx, "⌛ Hết thời gian chọn bot. Lệnh xoá đã được huỷ.", delay=20)
                return

            choice = choice_msg.content.strip().lower()
            if choice in ("c", "cancel", "huy", "hủy"):
                await self._reply(ctx, "Đã huỷ thao tác xoá bot.", delay=15)
                return
            if not choice.isdigit() or not (1 <= int(choice) <= len(candidates)):
                await self._reply(ctx, f"❌ Hãy gửi số từ `1` đến `{len(candidates)}` hoặc `c` để huỷ.", delay=20)
                return
            entry = candidates[int(choice) - 1]

        if role_of(entry) == ROLE_PRIME:
            await self._reply(ctx, "❌ Không thể xoá **bot chính (prime)** khỏi sổ.", delay=25)
            return
        name, bid = _norm(entry.get("name")), _norm(entry.get("bot_id"))
        cfg = _read_config()
        try:
            cfg.get("accounts", []).remove(entry)
        except ValueError:
            await self._reply(ctx, "❓ Bản ghi không còn trong sổ.", delay=25)
            return
        if not _write_config(cfg):
            await self._reply(ctx, "❌ Không ghi được config.json.", delay=25)
            return

        # ── Xóa triệt để file setting.json và các file cấu hình của bot này ──
        removed_files: List[str] = []
        possible_identifiers = set()
        for k in ("uid", "bot_id", "id"):
            val = entry.get(k)
            if val is not None and str(val).strip():
                possible_identifiers.add(str(val).strip())

        for ident in possible_identifiers:
            for candidate in (
                DATA_DIR / f"{ident}_setting.json",
                DATA_DIR / f"setting_{ident}.json",
                DATA_DIR / f"{ident}_prefix.json",
                DATA_DIR / f"{ident}_afk.json",
                DATA_DIR / f"{ident}_voice.json",
            ):
                if candidate.exists():
                    try:
                        candidate.unlink()
                        removed_files.append(candidate.name)
                    except Exception as e:
                        _log(f"[GENESIS] Loi khi xoa file {candidate}: {e}")

        clean_note = f" và dọn dẹp sạch file cài đặt `{', '.join(removed_files)}`" if removed_files else ""
        _log(f"[GENESIS] REMOVE '{name}' ({bid}) boi {ctx.author} ({ctx.author.id}) - Removed files: {removed_files}")
        await self._reply(ctx, f"🗑️ Đã **XOÁ** bot **{name}** (`{bid}`) khỏi config.json{clean_note}.", delay=45)

    # ════════════════════════════════════════════════════════════════════
    # RESET / RELOAD / SHUTDOWN / STATUS  (gộp từ core/restart.py cũ)
    # ════════════════════════════════════════════════════════════════════
    def _is_prime_admin(self, uid: int) -> bool:
        """Admin cấp cao (admintris) của BOT CHÍNH (Prime Bot).
        Người dùng thông thường và bot phụ tuyệt đối KHÔNG có quyền này.
        """
        try:
            u_int = int(uid)
        except Exception:
            return False
        try:
            cfg = _read_config()
            accounts = _accounts(cfg)
            prime_acc = next((a for a in accounts if role_of(a) == ROLE_PRIME), accounts[0] if accounts else None)
            if not prime_acc:
                return False

            # 1. Creator / Owner của BOT CHÍNH (Prime)
            prime_owners = list(prime_acc.get("owner_ids") or [])
            if prime_acc.get("created_by"):
                prime_owners.append(prime_acc.get("created_by"))
            for o in prime_owners:
                try:
                    if int(o) == u_int:
                        return True
                except Exception:
                    pass

            # 2. UID của chính Prime Bot
            p_uids = self._entry_uids(prime_acc)
            if u_int in p_uids:
                return True

            # 3. Admintris / Moderator trong file setting của Prime Bot
            for p_u in p_uids:
                p_setting = DATA_DIR / f"{p_u}_setting.json"
                if p_setting.exists():
                    try:
                        s_data = json.loads(p_setting.read_text(encoding="utf-8"))
                        for adm in s_data.get("admintris", s_data.get("moderator", [])):
                            try:
                                if int(adm) == u_int:
                                    return True
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            pass
        return False

    def _target_admin_ids(self, entry: Dict[str, Any]) -> set:
        """UID duoc quyen reset entry nay: MOI uid cua bot do + admintris setting + nguoi tao.

        Doc file setting theo CA 3 nguon uid (so / token / dang chay): uid trong so
        co the cu/sai trong khi file that (`<uid-that>_setting.json`) moi chua admintris.
        """
        ids: set = set()
        if not isinstance(entry, dict):
            return ids
        for uid in self._entry_uids(entry):
            ids.add(uid)
            try:
                path = DATA_DIR / f"{uid}_setting.json"
                if path.exists():
                    data = json.loads(path.read_text(encoding="utf-8"))
                    for x in (data.get("admintris") or []):
                        try:
                            ids.add(int(x))
                        except Exception:
                            continue
            except Exception:
                pass
        for x in list(entry.get("owner_ids") or []) + [entry.get("created_by")]:
            try:
                ids.add(int(x))
            except Exception:
                continue
        return ids

    async def _deny_reset(self, ctx: commands.Context, target: str = None) -> None:
        # CÂM NÍN TUYỆT ĐỐI: Người lạ hoặc không đủ quyền gọi lệnh reset -> im lặng hoàn toàn,
        # không gửi bất kỳ tin nhắn phản hồi nào để bảo mật selfbot tuyệt đối!
        return


    @staticmethod
    def _ctx_of(msg) -> Any:
        """Boc 1 Message thanh ctx toi thieu de `_reply` (autorep) dung duoc."""
        return types.SimpleNamespace(
            message=msg,
            author=getattr(msg, "author", None),
            channel=getattr(msg, "channel", None),
            guild=getattr(msg, "guild", None),
            send=getattr(getattr(msg, "channel", None), "send", None),
        )

    async def _reply_target_not_found(self, ctx: commands.Context, target: str) -> None:
        """Khong tim thay tag -> noi RO da doi chieu nhung gi + goi y bot cua nguoi goi.

        Doi chieu gom: `uid` trong so • `uid` GIAI MA TU TOKEN • ma bot (`G00x`)
        • ten bot • dau token — va cho biet nguoi goi co phai admintris bot nao khong.
        """
        p = self._pfx()
        author = ctx.author.id
        lines = [
            f"❓ **KHÔNG TÌM THẤY BOT** `{_norm(target)}` **TRONG SỔ GENESIS**",
            "• Đã đối chiếu: `uid` trong sổ • `uid` **giải mã từ token** • `uid` **bot đang chạy** "
            "• mã bot (`G00x`) • tên bot • đầu token — **không khớp bot nào**.",
        ]

        mine = self._user_admin_bots(author)
        if mine:
            listing = []
            for acc in mine[:10]:
                listing.append(
                    f"    ↳ `{_norm(acc.get('bot_id'))}` • **{_norm(acc.get('name'))}** — "
                    f"{self._uid_compare_text(acc)}"
                )
            extra = f" _(+{len(mine) - 10} bot nữa)_" if len(mine) > 10 else ""
            lines.append(
                f"• Bạn là **admin cấp cao (admintris)** của **{len(mine)}** bot phụ:{extra}\n"
                + "\n".join(listing)
            )
            if len(mine) == 1:
                lines.append(f"➡️ Thử lại: `{p}gene reset {_norm(mine[0].get('bot_id'))}`")
            else:
                lines.append(
                    f"➡️ Gõ `{p}gene reset` (**không tag**) để bot gửi **ảnh danh sách bot của bạn** "
                    f"rồi chọn `1`…`{len(mine)}` hoặc `all`."
                )
        else:
            lines.append("• Bạn **KHÔNG** phải admin cấp cao của bot phụ nào trong sổ.")

        if self._is_prime_admin(author):
            shards = [a for a in _accounts(_read_config()) if role_of(a) != ROLE_PRIME]
            if shards:
                allb = "\n".join(
                    f"    ↳ `{_norm(a.get('bot_id'))}` **{_norm(a.get('name'))}** — "
                    f"{self._uid_compare_text(a)}"
                    for a in shards[:12]
                )
                lines.append(f"• Danh sách bot phụ trong sổ genesis:\n{allb}")
            else:
                lines.append("• Sổ hiện **chưa có bot phụ** nào.")
            lines.append(f"➡️ `{p}gene list` — xem toàn bộ sổ genesis.")

        await self._reply(ctx, "\n".join(lines), delay=60)

    async def _send_pick_card(self, ctx: commands.Context, rows, title: str, menu: str,
                              footer: str, filename: str = "gene_pick.png",
                              delay: int = 60) -> None:
        """Gửi ẢNH danh sách bot để chọn + text menu đánh số (dùng chung reset).

        ẢNH chỉ vẽ 1 DÒNG tiêu đề (nhiều dòng/emoji -> ô vuông), còn text gửi kèm
        đầy đủ `title` + `menu` (đánh số 1..n) + `footer` (hướng dẫn gõ số / all / c).
        """
        p = self._pfx()
        card_file = None
        try:
            try:
                from apps.user_discord.utils.media_card import async_genesis_list_card
            except ImportError:
                from utils.media_card import async_genesis_list_card
            # Card chọn bot: tiêu đề 1 dòng + tip riêng cho reset (kẻo nhầm với gene list)
            _tip = (f"{p}gene reset 1 / 2 / all — gõ số để reset 1 bot, all để reset hết, "
                    f"c để hủy.")
            buf = await async_genesis_list_card(rows, p, title=title, tip=_tip)
            if buf:
                card_file = discord.File(buf, filename=filename)
        except Exception:
            card_file = None
        text = "\n".join([x for x in (title, menu, footer) if x])
        try:
            text = fmt(self.bot, text)
        except Exception:
            pass
        try:
            try:
                from apps.user_discord.utils.autorep import autorep
            except ImportError:
                from utils.autorep import autorep
            await autorep(ctx.message, content=text, file=card_file,
                          auto_delete_delay=delay)
            return
        except Exception:
            pass
        await self._reply(ctx, text, delay=delay)

    async def _reset_card_file(self, entries: List[Dict[str, Any]], title: str,
                               tip: str = "", filename: str = "gene_reset.png") -> Any:
        """Dung ANH (discord.File) cho mot buoc reset — giao dien giong `gene list`.

        - Anh liet ke TUNG bot se bi reset: avatar that + role + status + thoi gian.
        - `title`: tieu de card (vd "♻️ ĐANG RESET TOÀN BỘ HỆ THỐNG").
        - `tip`: dong goi y chan card (log cu da xoa, so bot...).
        Tra ve `discord.File` hoac `None` (khong render duoc -> chi gui text).
        """
        try:
            rows = await self._collect_rows(list(entries or []))
            for idx, row in enumerate(rows, 1):
                row["name"] = f"{idx}. {row.get('name') or '?'}"
            try:
                from apps.user_discord.utils.media_card import async_genesis_list_card
            except ImportError:
                from utils.media_card import async_genesis_list_card
            buf = await async_genesis_list_card(
                rows, self._pfx(), title=title, tip=tip or None)
            if buf:
                return discord.File(buf, filename=filename or "gene_reset.png")
        except Exception:
            return None
        return None

    async def _reply_with_file(self, ctx: commands.Context, text: str, file: Any = None,
                               filename: str = None, delay: Optional[int] = 30) -> None:
        """Reply KEM ANH (nguon: `_reset_card_file` / `_send_pick_card`).

        `filename` chi de DOI TEN file hien thi tren Discord (neu truyen vao).
        Luon dam bao TEXT duoc gui: neu gui kem anh loi -> tu dong gui lai text.
        """
        try:
            text = fmt(self.bot, text)
        except Exception:
            pass
        if file is not None and filename:
            try:
                file.filename = filename
            except Exception:
                pass
        autorep = None
        try:
            from apps.user_discord.utils.autorep import autorep
        except ImportError:
            try:
                from utils.autorep import autorep
            except ImportError:
                autorep = None
        if autorep is not None:
            try:
                return await autorep(ctx.message, content=text, file=file,
                                     auto_delete_delay=delay)
            except Exception:
                pass
        try:
            if file is not None:
                try:
                    return await ctx.send(text, file=file)
                except Exception:
                    pass
            return await ctx.send(text)
        except Exception:
            return None

    async def _ask_choice_reset(self, ctx: commands.Context, mine: List[Dict[str, Any]],
                                title: str = None, all_label: str = None,
                                on_all=None) -> None:
        """Gui ANH danh sach bot + yeu cau chon:
        `1`..`n` = reset 1 bot | `all` = reset het | `c` = huy (cho 45s).

        - `mine`: danh sach entry de chon (giữ nguyên thứ tự hiển thị 1..n).
        - `on_all`: callback khi user gõ `all` (mặc định = reset lần lượt từng bot
          trong `mine`); prime-admin truyền vào để `all` = reset toàn hệ thống.
        """
        p = self._pfx()
        rows = await self._collect_rows(mine)
        # Đánh số hiển thị TRÊN ẢNH (không sửa entry gốc): "1. Tên"
        for idx, row in enumerate(rows, 1):
            row["name"] = f"{idx}. {row.get('name') or '?'}"

        def _line(idx: int, a: Dict[str, Any]) -> str:
            icon = "👑" if role_of(a) == ROLE_PRIME else "🔷"
            if ctx.guild:
                # Ở server công cộng: CHE SẠCH TOÀN BỘ UID & THÔNG TIN SHARD CHỐNG LỘ SELFBOT!
                return f"{icon} `{idx}` • **{_norm(a.get('name'))}**"
            state = "🔒 locked" if is_locked(a) else "🔓 active"
            return (
                f"{icon} `{idx}` • **{_norm(a.get('name'))}** (`{_norm(a.get('bot_id'))}`)\n"
                f"      ↳ {self._uid_compare_text(a)}\n"
                f"      ↳ {state} • {remaining_text(a)}"
            )


        menu = "\n".join(_line(idx, a) for idx, a in enumerate(mine, 1))
        if title is None:
            title = (
                "🧬 **CHỌN BOT ĐỂ RESET**\n"
                f"• Bạn là **admin cấp cao (admintris)** của **{len(mine)}** bot phụ:"
            )
        if all_label is None:
            all_label = "reset **tất cả** bot của bạn"
        footer = (
            f"➡️ Gõ `1`…`{len(mine)}` để reset **1 bot**, hoặc `all` để {all_label}, `c` để hủy.\n"
            "• ⏳ Bot chờ lựa chọn trong **45s**."
        )
        await self._send_pick_card(ctx, rows, title, menu, footer,
                                   filename="gene_pick.png", delay=60)

        def check(m) -> bool:
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

        try:
            choice = await self.bot.wait_for("message", check=check, timeout=45.0)
        except asyncio.TimeoutError:
            await self._reply(ctx, "⌛ Hết thời gian chọn bot — gõ lại lệnh khi cần.", delay=20)
            return
        except Exception:
            return

        val = _norm(getattr(choice, "content", "")).lower()
        cctx = self._ctx_of(choice)
        if val in ("c", "cancel", "huy", "hủy", "0"):
            await self._reply(cctx, "❌ Đã hủy reset.", delay=15)
            return
        if val in ("all", "tatca", "tat_ca", "tất cả", "het", "hết"):
            if on_all is not None:
                await on_all(cctx)
                return
            targets = list(mine)
        elif val.isdigit() and 1 <= int(val) <= len(mine):
            targets = [mine[int(val) - 1]]
            # Chon dung bot CHINH (prime) -> reset TOAN BO he thong (cung process)
            try:
                _tok_self = _norm(token_of(self.bot))
                _t = _norm(targets[0].get("token"))
                if role_of(targets[0]) == ROLE_PRIME or (_t and _t == _tok_self):
                    await self._reset_all(cctx)
                    return
            except Exception:
                pass
        else:
            await self._reply(
                cctx,
                f"❌ Lựa chọn không hợp lệ — gõ `1`…`{len(mine)}` hoặc `all` (hoặc `c` để hủy).",
                delay=25,
            )
            return

        if len(targets) > 1:
            await self._reply(
                cctx,
                f"♻️ Reset **{len(targets)}** bot — lần lượt từng bot, các bot khác không bị ảnh hưởng.",
                delay=30,
            )
        for entry in targets:
            await self._do_reset_one(cctx, entry)

    def _wipe_reset_logs(self) -> str:
        """XÓA LOG CŨ trước reset thật (log chat/nhạc/lavalink...).

        Wrapper gọi _wipe_old_logs_impl (quét PROJECT_ROOT/data/BASE_DIR/DATA_DIR
        + thư mục logs/log, chỉ xóa *.log / log-*.txt / *.log.* — giữ lại
        setting.json / config / code / venv). Trả về text tóm tắt.
        """
        try:
            wiped = _wipe_old_logs_impl()
        except Exception:
            wiped = 0
        return f"đã xóa {wiped} file log cũ" if wiped else "không có file log cũ nào"

    async def _handle_reset(self, ctx: commands.Context, target: str = None) -> None:
        """gene reset [tag]: khong tag = CHỌN BOT QUA ẢNH; co tag = reset RIÊNG 1 bot."""
        p = self._pfx()
        author = ctx.author.id

        # 0. Bi CAM -> CAN NHIN tuyet doi, khong rep gi (require_permission("user")
        # cung da chan truoc day la hang rao chong lap)
        try:
            from apps.user_discord.core.bot_sys import is_cammed
        except ImportError:
            from core.bot_sys import is_cammed
        try:
            if is_cammed(self.bot, author):
                return
        except Exception:
            pass

        # 1. Khong tag -> GỬI ẢNH 2 BOT (prime + shard mà bạn quản trị) rồi chọn:
        #    gõ `1` / `2` = reset riêng 1 bot | `all` = reset TOÀN BỘ hệ thống.
        #    * admin cấp cao bot CHÍNH (+ có/không bot phụ) -> ảnh gồm prime + shard
        #    * admin cấp cao bot PHỤ (không phải prime)    -> ảnh bot phụ của họ
        if not target:
            is_prime = self._is_prime_admin(author)
            mine = self._user_admin_bots(author)
            if is_prime:
                # Acc chính: ảnh gồm BOT CHÍNH + BOT PHỤ mình làm admintris
                # (ví dụ 1 = bot chính, 2 = bot phụ — hoặc all = cả hệ thống)
                cfg = _read_config()
                prime_entry = None
                try:
                    tok_self = _norm(token_of(self.bot))
                    for acc in _accounts(cfg):
                        if role_of(acc) == ROLE_PRIME or (
                            tok_self and _norm(acc.get("token")) == tok_self
                        ):
                            prime_entry = acc
                            break
                except Exception:
                    prime_entry = None
                picks: List[Dict[str, Any]] = []
                if prime_entry is not None:
                    picks.append(prime_entry)
                for acc in (mine or []):
                    if all(acc is not q for q in picks):
                        picks.append(acc)
                if not picks:
                    await self._deny_reset(ctx)
                    return
                if len(picks) == 1 and role_of(picks[0]) == ROLE_PRIME:
                    # Chỉ có đúng bot chính -> reset toàn hệ thống luôn
                    await self._reset_all(ctx)
                    return
                await self._ask_choice_reset(
                    ctx,
                    picks,
                    title=(
                        "🧬 **CHỌN BOT ĐỂ RESET**\n"
                        "• Bạn là **admin cấp cao của BOT CHÍNH** (và cả bot phụ):\n"
                        "• `1` = **bot chính** (reset toàn hệ thống) • `2`,`3`… = **bot phụ** "
                        "• `all` = tất cả"
                    ),
                    all_label="reset **TOÀN BỘ hệ thống** (prime + shard)",
                    on_all=lambda cctx: self._reset_all(cctx),
                )
                return
            if not mine:
                await self._deny_reset(ctx)
                return
            if len(mine) == 1:
                entry = mine[0]
                await self._reply(
                    ctx,
                    "🧬 Bạn là **admin cấp cao** của **1** bot phụ — reset bot này:\n"
                    f"• Bot: **{_norm(entry.get('name'))}** (`{_norm(entry.get('bot_id'))}`)",
                    delay=25,
                )
                await self._do_reset_one(ctx, entry)
                return
            await self._ask_choice_reset(ctx, mine)
            return

        # 2. Co tag -> neu la 'all' thi reset toan bo he thong
        if str(target).lower().strip() in ("all", "tatca", "*"):
            if not self._is_prime_admin(author):
                await self._deny_reset(ctx, target)
                return
            await self._reset_all(ctx)
            return

        entry = self._resolve(target)
        if entry is None:
            await self._reply_target_not_found(ctx, target)
            return

        # 3. Target la bot chinh (prime) -> reset CA HE THONG
        tok_self = _norm(token_of(self.bot))
        if role_of(entry) == ROLE_PRIME or (_norm(entry.get("token")) and _norm(entry.get("token")) == tok_self):
            if not self._is_prime_admin(author):
                await self._deny_reset(ctx, target)
                return
            await self._reset_all(ctx)
            return

        # 4. Target la bot phu -> admin prime HOAC chinh bot do HOAC admin cap cao cua no
        if not self._is_prime_admin(author) and author not in self._target_admin_ids(entry):
            await self._deny_reset(ctx, target)
            return

        name, bid = _norm(entry.get("name")), _norm(entry.get("bot_id"))
        token = _norm(entry.get("token"))
        if not token:
            await self._reply(ctx, f"❌ Bot **{name}** (`{bid}`) chưa có token — không reset được.", delay=30)
            return
        await self._do_reset_one(ctx, entry)

    async def _do_reset_one(self, ctx: commands.Context, entry: Dict[str, Any]) -> None:
        """Reset RIENG 1 bot phu: shutdown (neu dang chay) + spawn lai — khong anh huong bot khac."""
        try:
            from apps.user_discord.core import runtime as _runtime
        except ImportError:
            from core import runtime as _runtime

        name, bid = _norm(entry.get("name")), _norm(entry.get("bot_id"))
        token = _norm(entry.get("token"))
        key = bid or token[:8]

        if key in _RESETTING:
            await self._reply(ctx, f"⏳ Bot **{name}** (`{bid}`) đang reset — đợi chút…", delay=20)
            return
        now = time.time()
        wait = COOLDOWN - (now - _LAST_RESET.get(key, 0.0))
        if 0 < wait <= COOLDOWN:
            await self._reply(ctx, f"⏳ Vừa reset xong, đợi thêm **{wait:.0f}s** nữa.", delay=20)
            return

        live = _runtime.is_live(token)
        if not live and status_of(entry) == STATUS_LOCK:
            await self._reply(
                ctx,
                f"🔒 Bot **{name}** (`{bid}`) đang **KHOÁ & OFFLINE**.\n"
                f"➡️ Mở khoá trước: `{self._pfx()}gene unlock {bid}` rồi `{self._pfx()}gene start {bid} <time>`.",
                delay=40,
            )
            return

        _RESETTING.add(key)
        _LAST_RESET[key] = now
        try:
            # BOT CHÍNH thông báo ngắn gọn trước khi reset
            notice = await self._reply(
                ctx,
                f"♻️ **ĐANG RESET BOT** `{bid}` — **{name}**\n"
                f"• UID: {self._uid_compare_text(entry)} • Yêu cầu: {ctx.author.name}\n"
                f"• Thao tác: {'Tắt ➔ Khởi động lại' if live else 'Khởi động bot'}",
                delay=None,
            )
            keep_ids: set = set()
            try:
                if notice is not None and getattr(notice, "id", None):
                    keep_ids.add(notice.id)
            except Exception:
                pass
            if live:
                await _runtime.shutdown(token)
                await asyncio.sleep(1.5)
            # RESET THẬT: xóa log cũ + dọn cache pycache + purge sys.modules để nạp code mới nhất từ ổ đĩa
            try:
                wipe_txt = self._wipe_reset_logs()
            except Exception:
                wipe_txt = "không xóa được log cũ"
            try:
                pyc_n = _wipe_pycache_impl()
            except Exception:
                pyc_n = 0
            try:
                mod_n = _purge_sys_modules_impl()
            except Exception:
                mod_n = 0
            purged = 0
            try:
                purged = await _purge_channel_logs(self.bot, ctx.channel, keep_ids=keep_ids)
            except Exception:
                purged = 0
            pfx = _norm(entry.get("prefix")) if entry.get("prefix") is not None else ""
            ok, _b, msg = await _runtime.spawn(token, pfx, name)
            rep = self._uid_report(entry)
            _log(
                f"[GENESIS] RESET-ONE '{name}' ({bid}) ok={ok} msg={msg} "
                f"uid(so={rep['acc_uid']} token={rep['token_uid']} live={rep['live_uid']}) "
                f"bởi {ctx.author} ({ctx.author.id})"
            )
            if ok:
                img_file = await self._reset_card_file(
                    [entry], "✅ ĐÃ RESET & NÂNG CẤP XONG",
                    f"{wipe_txt} • {pyc_n} pycache • {mod_n} modules nạp mới • đã dọn {purged} log",
                )
                await self._reply_with_file(
                    ctx,
                    f"✅ **ĐÃ KHỞI ĐỘNG XONG** `{bid}` — **{name}**\n"
                    f"• UID: {self._uid_compare_text(entry)} • Prefix: `{pfx}`\n"
                    f"• 🔄 Nâng cấp: Nạp lại 100% code mới từ ổ đĩa ({mod_n} modules, {pyc_n} pycache cleared)\n"
                    f"• 🧹 Dọn dẹp: {wipe_txt} ({purged} tin log)\n"
                    f"• Trạng thái: {msg}",
                    file=img_file,
                    filename="gene_reset_done.png",
                    delay=45,
                )
            else:
                await self._reply(ctx, f"❌ Reset bot **{name}** (`{bid}`) thất bại: {msg}", delay=45)
        finally:
            _RESETTING.discard(key)

    async def _reset_all(self, ctx: commands.Context) -> None:
        """Reset TOAN BO he thong: Dọn sạch pycache/log -> nạp code mới nhất -> khởi động lại tiến trình."""
        key = "*ALL*"
        if key in _RESETTING:
            await self._reply(ctx, "⚠️ Hệ thống đang khởi động lại, vui lòng đợi…", delay=25)
            return
        now = time.time()
        wait = COOLDOWN - (now - _LAST_RESET.get(key, 0.0))
        if 0 < wait <= COOLDOWN:
            await self._reply(ctx, f"⏳ Vừa khởi động lại xong, đợi thêm **{wait:.0f}s** nữa.", delay=25)
            return
        _RESETTING.add(key)
        _LAST_RESET[key] = now

        me = getattr(self.bot, "user", None)
        pyc_n = _wipe_pycache_impl()
        mod_n = _purge_sys_modules_impl()
        wipe_txt = self._wipe_reset_logs()

        # Chụp ẢNH reset trước khi restart thật (giao diện như gene list).
        start_img = await self._reset_card_file(
            _accounts(_read_config()), "♻️ ĐANG RESET & NÂNG CẤP TOÀN BỘ HỆ THỐNG",
            "Nạp lại 100% code mới • xóa pycache • làm mới RAM",
        )
        msg_lines = [
            f"♻️ **ĐANG RESET TOÀN BỘ HỆ THỐNG ĐỂ NÂNG CẤP & CẬP NHẬT CODE**",
            f"• Yêu cầu bởi: {ctx.author} (`{ctx.author.id}`)",
            f"• Bot chính: {me.name if me else '?'} | prefix `{self._pfx()}`",
            f"• 🔄 Nâng cấp: Đã dọn dẹp `{pyc_n}` pycache & `{mod_n}` modules để nạp code mới nhất từ đĩa",
            f"• 🧹 Log cũ: {wipe_txt}",
            f"• MỌI bot trong process (prime + shard) sẽ khởi động lại trong **{SHUTDOWN_DELAY}s**.",
            f"• Lệnh trong lúc này sẽ không phản hồi."
        ]
        notice = await self._reply_with_file(
            ctx,
            "\n".join(msg_lines),
            file=start_img,
            filename="gene_reset_all.png",
            delay=None,
        )
        keep_ids: set = set()
        try:
            if notice is not None and getattr(notice, "id", None):
                keep_ids.add(notice.id)
        except Exception:
            pass
        try:
            purged = await _purge_channel_logs(self.bot, ctx.channel, keep_ids=keep_ids)
        except Exception:
            purged = 0
        if purged:
            _log(f"[GENESIS] Da don {purged} tin log cu trong kenh truoc full reset.")
        _log(f"[GENESIS] FULL RESET (UPGRADE) boi {ctx.author} ({ctx.author.id}) - restart sau {SHUTDOWN_DELAY}s")
        _spawn_task(self._run_full_reset())

    async def _run_full_reset(self) -> None:
        await asyncio.sleep(SHUTDOWN_DELAY)
        try:
            from apps.user_discord.core import runtime as _runtime
        except ImportError:
            from core import runtime as _runtime

        # 1. Dung runner (AutoQuest/thread) tren MOI bot
        try:
            for _tok, ent in list(_runtime.LIVE.items()):
                b2 = ent.get("bot")
                if b2 is None:
                    continue
                for cog in getattr(b2, "cogs", {}).values():
                    r = getattr(cog, "runner", None)
                    if r is not None and hasattr(r, "stop"):
                        try:
                            r.stop()
                        except Exception:
                            pass
        except Exception:
            pass

        # 2. Dong cac bot shard truoc, prime (self.bot) cuoi cung
        try:
            self_tok = _norm(token_of(self.bot))
            for tok in list(_runtime.LIVE.keys()):
                if tok == self_tok:
                    continue
                try:
                    await _runtime.shutdown(tok)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            for cog in self.bot.cogs.values():
                r = getattr(cog, "runner", None)
                if r is not None and hasattr(r, "stop"):
                    try:
                        r.stop()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            await self.bot.close()
        except Exception:
            pass

        # 3. Thay the tien trinh = chinh no (tu dong nap lai TAT CA extension + bot voi code moi)
        _log("[GENESIS] Dang thay the tien trinh (full reset de ap dung code moi)...")
        _flush_stdout()
        try:
            # Thử execv thay thế tiến trình trên Linux/Docker Pterodactyl
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as exc:
            _log(f"[GENESIS] execv loi ({exc}) - thu subprocess / exit code 42.")
            try:
                import subprocess
                subprocess.Popen([sys.executable] + sys.argv, cwd=str(PROJECT_ROOT))
                os._exit(0)
            except Exception:
                pass
            # Thoát với code 42 để supervisor (main.py root hoặc docker) tự khởi động lại ngay
            os._exit(42)

    async def _run_shutdown(self) -> None:
        """Tat HE THONG: dong tat ca bot -> os._exit(0) (khong khoi dong lai)."""
        await asyncio.sleep(SHUTDOWN_DELAY)
        try:
            from apps.user_discord.core import runtime as _runtime
        except ImportError:
            from core import runtime as _runtime
        try:
            for _tok, ent in list(_runtime.LIVE.items()):
                b2 = ent.get("bot")
                if b2 is None:
                    continue
                for cog in getattr(b2, "cogs", {}).values():
                    r = getattr(cog, "runner", None)
                    if r is not None and hasattr(r, "stop"):
                        try:
                            r.stop()
                        except Exception:
                            pass
            for tok in list(_runtime.LIVE.keys()):
                try:
                    await _runtime.shutdown(tok)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            await self.bot.close()
        except Exception:
            pass
        _log("[GENESIS] Da tat he thong (shutdown).")
        _flush_stdout()
        os._exit(0)

    # ── gene reset ─────────────────────────────────────────────────────
    @gene.command(name="reset", aliases=("rs", "restart", "reboot"))
    @require_permission("user")
    async def gene_reset(self, ctx: commands.Context, target: str = None):
        """Reset bot:
        • Bot chính: chạy trực tiếp logic reset hệ thống / bot phụ.
        • Bot phụ: tự động chuyển lệnh sang bot chính để reset chính nó.
        (prefix)gene reset [G00x|id|tên]"""
        if self._is_prime_bot():
            await self._handle_reset(ctx, target)
        else:
            await self.reset_top(ctx, target)

    # ── gene reload ────────────────────────────────────────────────────
    @gene.command(name="reload", aliases=("reloadcog", "nap_lai"))
    @require_permission("user")
    @_prime_only()
    async def gene_reload(self, ctx: commands.Context, name: str = None, target: str = None):
        """Nạp lại 1 extension: (prefix)gene reload <tên> [bot] — không tag = bot chính."""
        p = self._pfx()
        author = ctx.author.id
        target_bot = self.bot
        where = "bot chính (prime)"

        if target:
            entry = self._resolve(target)
            if entry is None:
                await self._reply_target_not_found(ctx, target)
                return
            if not self._is_prime_admin(author) and author not in self._target_admin_ids(entry):
                await self._deny_reset(ctx, target)
                return
            tok = _norm(entry.get("token"))
            try:
                from apps.user_discord.core import runtime as _runtime
            except ImportError:
                from core import runtime as _runtime
            target_bot = _runtime.get_live(tok) if tok else None
            if target_bot is None:
                await self._reply(
                    ctx,
                    f"❌ Bot **{_norm(entry.get('name'))}** (`{_norm(entry.get('bot_id'))}`) chưa online — không reload được.",
                    delay=30,
                )
                return
            where = f"bot **{_norm(entry.get('name'))}** (`{_norm(entry.get('bot_id'))}`)"
        elif not self._is_prime_admin(author):
            await self._deny_reset(ctx)
            return

        current = sorted(target_bot.extensions.keys())
        if not name:
            pretty = ", ".join(f"`{e.rsplit('.', 1)[-1]}`" for e in current) or "(chưa có)"
            await self._reply(
                ctx,
                f"♻️ **NẠP LẠI EXTENSION** — {where}\n"
                f"• Cú pháp: `{p}gene reload <tên> [bot]`, ví dụ `{p}gene reload prefix`\n"
                f"• Đang chạy ({len(current)}): {pretty}\n"
                f"• Muốn sạch hoàn toàn thì dùng `{p}gene reset`.",
                delay=60,
            )
            return

        key = name.strip()
        full = None
        for ext in current:
            if ext == key or ext.rsplit(".", 1)[-1] == key:
                full = ext
                break
        if not full:
            for sec in ("utils", "core", "modules"):
                if (BASE_DIR / sec / f"{key}.py").exists():
                    full = f"apps.user_discord.{sec}.{key}"
                    break
        if not full:
            await self._reply(ctx, f"❌ Không tìm thấy extension tên **{key}**.", delay=30)
            return

        try:
            if full in target_bot.extensions:
                await target_bot.reload_extension(full)
                mode = "nạp lại"
            else:
                await target_bot.load_extension(full)
                mode = "nạp mới"
        except commands.ExtensionError as exc:
            await self._reply(ctx, f"❌ Lỗi khi {mode} `{full}`: {exc}", delay=30)
            return
        except Exception as exc:
            await self._reply(ctx, f"❌ Lỗi khi {mode} `{full}`: {type(exc).__name__}: {exc}", delay=30)
            return

        updated = 0
        try:
            from apps.user_discord.utils.prefix import apply_help
            updated = apply_help(target_bot)
        except Exception:
            pass
        _log(f"[GENESIS] RELOAD {mode} {full} tren {where} boi {ctx.author} ({ctx.author.id})")
        await self._reply(
            ctx,
            f"✅ **ĐÃ {mode.upper()} THÀNH CÔNG** — {where}\n"
            f"• Extension: `{full}`\n"
            f"• Tổng extension đang chạy: **{len(target_bot.extensions)}**\n"
            f"• Lệnh help đã cập nhật prefix: **{updated}**",
            delay=30,
        )

    # ── gene shutdown ──────────────────────────────────────────────────
    @gene.command(name="shutdown", aliases=("tatbot", "off_bot"))
    @require_permission("user")
    @_prime_only()
    async def gene_shutdown(self, ctx: commands.Context):
        """Tắt TOÀN BỘ hệ thống, không khởi động lại (CHỈ admin cấp cao bot chính): (prefix)gene shutdown"""
        if not self._is_prime_admin(ctx.author.id):
            await self._deny_reset(ctx)
            return
        await self._reply(
            ctx,
            f"🛑 **ĐANG TẮT TOÀN BỘ HỆ THỐNG**\n"
            f"• Yêu cầu bởi: {ctx.author} (Admin cấp cao)\n"
            f"• Tắt trong **{SHUTDOWN_DELAY}s** — MỌI bot (prime + shard) sẽ offline.\n"
            f"• Khởi động lại bằng cách chạy lại bot thủ công.",
            delay=None,
        )
        _log(f"[GENESIS] SHUTDOWN boi {ctx.author} ({ctx.author.id})")
        _spawn_task(self._run_shutdown())

    # ── gene status ────────────────────────────────────────────────────
    @gene.command(name="status", aliases=("botstatus", "status_bot", "trangthai"))
    @require_permission("user")
    @_prime_only()
    async def gene_status(self, ctx: commands.Context):
        """Xem trạng thái hệ thống (CHỈ admin cấp cao bot chính): (prefix)gene status"""
        if not self._is_prime_admin(ctx.author.id):
            await self._deny_reset(ctx)
            return
        me = getattr(self.bot, "user", None)
        secs = {"utils": 0, "core": 0, "modules": 0}
        for ext in sorted(self.bot.extensions.keys()):
            parts = ext.split(".")
            if len(parts) >= 4 and parts[2] in secs:
                secs[parts[2]] += 1
        uptime = time.time() - getattr(self.bot, "_ud_started_at", time.time())
        mins, secs_left = divmod(int(uptime), 60)
        try:
            ping_ms = f"{round(self.bot.latency * 1000)}ms"
        except Exception:
            ping_ms = "?ms"
        live_n = 1
        try:
            try:
                from apps.user_discord.core import runtime as _runtime
            except ImportError:
                from core import runtime as _runtime
            live_n = len(_runtime.LIVE)
        except Exception:
            pass
        await self._reply(
            ctx,
            f"📊 **TRẠNG THÁI HỆ THỐNG SELFBOT**\n"
            f"• Bot: **{me.name if me else '?'}** (UID `{me.id if me else '?'}`)\n"
            f"• Thời gian chạy: **{mins}p {secs_left}s**\n"
            f"• Bot đang chạy trong process: **{live_n}** (prime + shard)\n"
            f"• Extension: **{len(self.bot.extensions)}** "
            f"(utils {secs['utils']}, core {secs['core']}, modules {secs['modules']})\n"
            f"• Cog đang chạy: **{len(self.bot.cogs)}** | Ping: **{ping_ms}**\n"
            f"• Dùng `{self._pfx()}gene reset` để khởi động lại TOÀN BỘ hệ thống.",
            delay=45,
        )

    # ── (prefix)reset — top-level: prime chay truc tiep; shard chuyen lenh sang bot chinh ──
    @commands.command(name="reset", aliases=("rs", "restart", "reboot", "khoi_dong_lai"))
    @require_permission("admintris")
    async def reset_top(self, ctx: commands.Context, target: str = None):
        """Reset bot. Bot chính: chạy thẳng (không tag = cả hệ thống). Bot phụ: tự chuyển
        lệnh sang PREFIX BOT CHÍNH để reset riêng mình — admin cấp cao bot phụ cũng dùng cách này:
        (prefix)reset [G00x|id|tên]"""
        # Bot CHINH -> chay truc tiep logic reset
        if self._is_prime_bot():
            await self._handle_reset(ctx, target)
            return

        # Bot PHU (shard): khong reset truc tiep — chuyen lenh sang prefix bot chinh
        entry = self_entry(self.bot)
        if entry is None:
            return
        # Chi admin cap cao CUA BOT NAY (shard) moi duoc phep chuyen lenh
        if not self._is_prime_admin(ctx.author.id) and ctx.author.id not in self._target_admin_ids(entry):
            return

        prime_pfx = _prime_prefix()
        if not prime_pfx:
            await self._reply(ctx, "❌ Không tìm thấy bot chính (prime) trong config.json.", delay=30)
            return
        tgt = target or _norm(entry.get("bot_id"))
        if not tgt:
            await self._reply(
                ctx,
                f"❌ Không xác định được mã bot — thử `{prime_pfx}gene reset <tag>` từ prefix bot chính.",
                delay=30,
            )
            return
        fwd = f"{prime_pfx}gene reset {tgt}"
        _log(f"[GENESIS] SHARD forward reset -> {fwd!r} boi {ctx.author} ({ctx.author.id})")
        await self._reply(ctx, f"➡️ Chuyển lệnh sang **BOT CHÍNH**: `{fwd}`", delay=20)
        try:
            await ctx.send(fwd)
        except Exception as exc:
            await self._reply(ctx, f"❌ Không gửi được lệnh tới bot chính: {type(exc).__name__}", delay=30)


async def setup(bot: commands.Bot):
    """Nap cog + gan check toan cuc (bot phu bi khoa -> cam moi lenh)."""
    if not hasattr(bot, "_ud_started_at"):
        bot._ud_started_at = time.time()
    cog = GenesisCog(bot)
    await bot.add_cog(cog)
    try:
        bot.add_check(cog._global_gate)
    except Exception:
        pass

