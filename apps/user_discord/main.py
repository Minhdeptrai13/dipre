import sys
import os

class _SafeStream:
    """Bọc an toàn chống crash WinError 31 trên Windows Server 2012 / cmd cổ."""
    def __init__(self, original):
        self._orig = original

    def write(self, s):
        try:
            return self._orig.write(s)
        except (PermissionError, OSError):
            try:
                # Nếu văng WinError 31 do ký tự Unicode/emoji trên Windows cũ, lọc sang ASCII an toàn
                clean_s = str(s).encode("ascii", errors="replace").decode("ascii")
                return self._orig.write(clean_s)
            except Exception:
                pass
            return len(s)

    def flush(self):
        try:
            return self._orig.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._orig, name)


def _init_console():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream:
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
            if sys.platform == "win32":
                setattr(sys, stream_name, _SafeStream(stream))

_init_console()
print("[USER_DISCORD] [START] Dang bat dau khoi chay tien trinh user discord...", flush=True)
import asyncio
import json
import datetime
import time
import unicodedata
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

CURRENT_DIR = Path(__file__).resolve().parent
BASE_DIR = CURRENT_DIR
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

for p in [str(PROJECT_ROOT), str(CURRENT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

def _ensure_dependencies():
    try:
        import discord
        from discord.ext import commands
    except ModuleNotFoundError as error:
        print(
            f"[USER_DISCORD] Thiếu dependency trong interpreter {sys.executable}: {error}",
            flush=True,
        )
        raise

_ensure_dependencies()

import discord
from discord.ext import commands

# Tự động nạp thư viện âm thanh Opus trên Windows để phát Voice mượt mà, không bị văng/drop
if not discord.opus.is_loaded():
    possible_opus_paths = [
        CURRENT_DIR / ".venv" / "Lib" / "site-packages" / "discord" / "bin" / "libopus-0.x64.dll",
        PROJECT_ROOT / "apps" / "user_discord" / ".venv" / "Lib" / "site-packages" / "discord" / "bin" / "libopus-0.x64.dll",
        PROJECT_ROOT / "apps" / "discord_bot" / ".venv" / "Lib" / "site-packages" / "discord" / "bin" / "libopus-0.x64.dll",
    ]
    for opp in possible_opus_paths:
        if opp.exists():
            try:
                discord.opus.load_opus(str(opp))
                print(f"[USER_DISCORD] Loaded Opus Voice Engine: {opp.name}", flush=True)
                break
            except Exception as e:
                print(f"[USER_DISCORD] Failed to load Opus from {opp}: {e}", flush=True)

CONFIG_PATH = CURRENT_DIR / "config.json"

# Bo thong ke dung chung: moi bot dong gop 1 phan, in BANG TONG QUAN 1 lan duy nhat
REGISTER_BOTS = []
READY_COUNTER = []
REPORT_DONE = []


class RollingMessageLogLimiter:
    def __init__(self, label: str, limit: int = 20, window_seconds: float = 5.0):
        self.label = label
        self.limit = limit
        self.window_seconds = window_seconds
        self.timestamps = deque()
        self.suppressed = 0
        self.last_summary = time.monotonic()

    def should_log(self) -> bool:
        now = time.monotonic()
        while self.timestamps and now - self.timestamps[0] >= self.window_seconds:
            self.timestamps.popleft()
        if len(self.timestamps) < self.limit:
            self.timestamps.append(now)
            return True

        self.suppressed += 1
        if now - self.last_summary >= self.window_seconds:
            print(f"[{self.label}] Suppressed {self.suppressed} message logs due to high traffic.", flush=True)
            self.suppressed = 0
            self.last_summary = now
        return False


def REGISTER_BOT(info: dict) -> None:
    REGISTER_BOTS.append(info)


def load_account_config():
    """Nạp cấu hình tài khoản theo cơ chế bảo mật mới:
    Ưu tiên 1: SQLite Database của Dipre (an toàn, bảo mật, F5 không mất).
    Ưu tiên 2: Biến môi trường Environment Variables (chuẩn Vercel / Railway / Docker / Cloud).
    Ưu tiên 3: File config.json cục bộ (nếu có, KHÔNG tự động tạo file rỗng để tránh lộ token khi push git).
    """
    cfg = {"accounts": []}

    # 1. Nạp từ SQLite Database (nếu đang chạy trong Dipre)
    try:
        from core.database import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT username, discord_token, bot_prefix, bot_enabled FROM users WHERE discord_token != ""')
            main_rows = cursor.fetchall()
            for r in main_rows:
                t = str(r['discord_token']).strip()
                if t:
                    cfg["accounts"].append({
                        "name": r['username'] or "Main_Account",
                        "prefix": r['bot_prefix'] or os.environ.get("BOT_PREFIX", "m"),
                        "token": t,
                        "status": "unlock" if r['bot_enabled'] else "standby"
                    })

            cursor.execute('SELECT discord_username, token, bot_prefix, bot_enabled FROM discord_accounts WHERE token != ""')
            sub_rows = cursor.fetchall()
            for r in sub_rows:
                t = str(r['token']).strip()
                if t and not any(a.get("token") == t for a in cfg["accounts"]):
                    cfg["accounts"].append({
                        "name": r['discord_username'] or "Sub_Account",
                        "prefix": r['bot_prefix'] or os.environ.get("BOT_PREFIX", "m"),
                        "token": t,
                        "status": "unlock" if r['bot_enabled'] else "standby"
                    })
    except Exception:
        pass

    # 2. Nạp từ Environment Variables (chuẩn Cloud / Vercel)
    env_token = os.environ.get("DISCORD_TOKEN") or os.environ.get("USER_DISCORD_TOKEN") or ""
    if env_token.strip() and not any(a.get("token") == env_token.strip() for a in cfg["accounts"]):
        cfg["accounts"].append({
            "name": "Cloud_Primary",
            "prefix": os.environ.get("BOT_PREFIX", "m"),
            "token": env_token.strip(),
            "status": "unlock"
        })

    env_accounts_json = os.environ.get("DISCORD_BOT_ACCOUNTS", "").strip()
    if env_accounts_json:
        try:
            parsed_env = json.loads(env_accounts_json)
            if isinstance(parsed_env, list):
                for item in parsed_env:
                    if isinstance(item, dict) and item.get("token"):
                        t = item["token"].strip()
                        if not any(a.get("token") == t for a in cfg["accounts"]):
                            cfg["accounts"].append(item)
        except Exception:
            pass

    # 3. Nạp từ file config.json cục bộ (chỉ đọc nếu file đã tồn tại, KHÔNG TỰ TẠO MỚI)
    if CONFIG_PATH.exists():
        try:
            from apps.shared.token_crypto import decrypt
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                file_cfg = json.load(f)
            if isinstance(file_cfg, dict):
                for acc in file_cfg.get("accounts", []):
                    if isinstance(acc, dict) and acc.get("token"):
                        t = decrypt(acc["token"]).strip()
                        if t and not any(a.get("token") == t for a in cfg["accounts"]):
                            acc_copy = dict(acc)
                            acc_copy["token"] = t
                            cfg["accounts"].append(acc_copy)
                if "captcha" in file_cfg and "captcha" not in cfg:
                    cfg["captcha"] = file_cfg["captcha"]
        except Exception as e:
            pass

    return cfg


def get_visual_width(text: str) -> int:
    """Tính độ rộng hiển thị thực tế của chuỗi có ký tự dấu / CJK / emoji."""
    width = 0
    for ch in text:
        east_asian = unicodedata.east_asian_width(ch)
        if east_asian in ('F', 'W'):
            width += 2
        elif unicodedata.combining(ch):
            continue
        else:
            width += 1
    return width


def pad_to_width(text: str, target_width: int) -> str:
    """Căn lề chuỗi có tính đến ký tự rộng (Fullwidth/East Asian)."""
    current_width = get_visual_width(text)
    if current_width >= target_width:
        return text
    return text + " " * (target_width - current_width)


def format_message_box(message: discord.Message, log_reason: str = "") -> str:
    """Đóng khung hộp tin nhắn nhận được với viền bo góc sắc nét."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    server_name = message.guild.name if message.guild else "Direct Message (DM)"
    channel_name = message.channel.name if hasattr(message.channel, "name") else "Private"
    author_info = f"{message.author} (ID: {message.author.id})"

    embed_texts = []
    if message.embeds:
        for emb in message.embeds:
            if emb.title:
                embed_texts.append(f"Title: {emb.title}")
            if emb.description:
                desc = emb.description.replace("\n", " ").strip()
                embed_texts.append(f"Desc: {desc}")
            if emb.fields:
                f_list = [f"{f.name}: {f.value}" for f in emb.fields[:2]]
                embed_texts.append(f"Fields: {'; '.join(f_list)}")

    media_sources = []
    if message.attachments:
        for idx, att in enumerate(message.attachments, start=1):
            media_sources.append(f"[src Attachment #{idx} ({att.filename})]: {att.url}")

    if hasattr(message, "stickers") and message.stickers:
        for idx, s in enumerate(message.stickers, start=1):
            media_sources.append(f"[src Sticker #{idx} ({s.name})]: {s.url}")

    if message.embeds:
        for idx, emb in enumerate(message.embeds, start=1):
            banner_url = (emb.image.url if emb.image else None) or (emb.thumbnail.url if emb.thumbnail else None) or emb.url
            if banner_url:
                media_sources.append(f"[src Embed/Banner #{idx}]: {banner_url}")

    text_content = message.content.replace("\n", " ").strip() if message.content else ""
    if text_content and embed_texts:
        content = f"{text_content} | " + " | ".join(embed_texts)
    elif text_content:
        content = text_content
    elif embed_texts:
        content = " | ".join(embed_texts)
    elif media_sources:
        content = f"(Đính kèm {len(media_sources)} media/file - xem [src] bên dưới)"
    else:
        content = "(Không có nội dung chữ)"

    lines = [
        f"Noi dung: {content}",
        f"Nguoi gui: {author_info}",
        f"Server: {server_name} | Kenh: {channel_name}",
    ]
    lines.extend(media_sources)

    box_inner_width = 76
    for line in lines:
        w = get_visual_width(line)
        if w > box_inner_width:
            box_inner_width = min(w, 140)

    header_tag = f" [USER_DISCORD {now_str}] LOG {log_reason} " if log_reason else f" [USER_DISCORD {now_str}] LOG "
    dashes_needed = box_inner_width - get_visual_width(header_tag)
    left_dashes = max(2, dashes_needed // 2)
    right_dashes = max(2, dashes_needed - left_dashes)

    top_border = f"╭{'─' * left_dashes}{header_tag}{'─' * right_dashes}╮"
    bottom_border = f"╰{'─' * (box_inner_width + 2)}╯"

    box_lines = [top_border]
    for line in lines:
        while get_visual_width(line) > box_inner_width:
            cut_idx = len(line)
            while cut_idx > 0 and get_visual_width(line[:cut_idx]) > box_inner_width:
                cut_idx -= 1
            segment = line[:cut_idx]
            padded = pad_to_width(segment, box_inner_width)
            box_lines.append(f"│ {padded} │")
            line = line[cut_idx:]
        padded = pad_to_width(line, box_inner_width)
        box_lines.append(f"│ {padded} │")
    box_lines.append(bottom_border)

    return "\n".join(box_lines)


# ─────────────────────────────────────────────────────────────────────────────
# BANG THONG KE KHI KHOI DONG (gom tat ca bot ve mot lan, khong log tung dong)
# ─────────────────────────────────────────────────────────────────────────────
C_RESET = "\x1b[0m"
C_CYAN = "\x1b[96m"
C_GREEN = "\x1b[92m"
C_YELLOW = "\x1b[93m"
C_RED = "\x1b[91m"
C_DIM = "\x1b[90m"
C_BOLD = "\x1b[1m"


def _enable_utf8_console() -> bool:
    """Bat VT + UTF-8 tren Windows. Tra True neu terminal chap nhan (van an toan neu False)."""
    if os.name != "nt":
        return False
    try:
        import ctypes

        k = ctypes.windll.kernel32
        handle = k.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if not k.SetConsoleMode(handle, mode.value | 0x0004):   # bat Virtual Terminal
            return False
        k.SetConsoleOutputCP(65001)
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        return True
    except Exception:
        return False


def _can_print(text: str) -> bool:
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        text.encode(enc, errors="strict")
        return True
    except Exception:
        return False


_enable_utf8_console()
# Chi dung hinh dep (khung + emoji + tieng Viet co dau) khi terminal doc duoc
# (dat UD_ASCII=1 neu terminal khong ho tro Unicode)
_UNICODE_OK = not os.environ.get("UD_ASCII") and _can_print("█░─│┌┐└┘·🤖✅⚠đ")
_COLOR_OK = not os.environ.get("NO_COLOR") and _can_print("\x1b[96m")

CH_FULL = "█" if _UNICODE_OK else "#"
CH_EMPTY = "░" if _UNICODE_OK else "."
V_LINE = "│" if _UNICODE_OK else "|"
V_TL, V_BL = ("┌", "└") if _UNICODE_OK else ("+", "+")
V_DASH = "─" if _UNICODE_OK else "-"
V_DOT = "·" if _UNICODE_OK else "-"


def _T(vi: str, en: str) -> str:
    """Chon chuoi theo kha nang hien thi cua terminal."""
    return vi if _UNICODE_OK else en


def _S(value) -> str:
    """Chuan hoa chuoi lau vao bang (bo ky tu terminal khong doc duoc o che do ASCII)."""
    s = str(value)
    if _UNICODE_OK:
        return s
    cleaned = "".join(ch for ch in s if _can_print(ch))
    return cleaned or "?"


def _c(text: str, color: str) -> str:
    return f"{color}{text}{C_RESET}" if _COLOR_OK else text


def _p(text: str = "") -> None:
    """print an toan: terminal khong doc duoc ky tu dac biet -> rut gon ASCII."""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        out = "".join(ch if _can_print(ch) else "?" for ch in text)
        try:
            print(out, flush=True)
        except Exception:
            print(ascii(text), flush=True)


def _bar(label: str, count: int, total: int, width: int = 22, color: str = C_GREEN) -> str:
    filled = int(width * (count / total)) if total else 0
    return (f"{label} {_c(CH_FULL * filled, color)}{_c(CH_EMPTY * (width - filled), C_DIM)}"
            f" {count}/{total}")


def _w(text: str) -> int:
    """Do rong hien thi, bo qua ma mau ANSI."""
    out, i = 0, 0
    while i < len(text):
        if text[i] == "\x1b":
            while i < len(text) and text[i] != "m":
                i += 1
            i += 1
            continue
        out += 0 if unicodedata.combining(text[i]) else 1
        i += 1
    return out


def _row(left: str, right: str = "", width: int = 78) -> str:
    return "  " + left + (" " * max(1, width - _w(left) - _w(right))) + right


def print_startup_report(infos: list) -> None:
    """In BANG THONG KE 1 LAN duy nhat sau khi TAT CA bot da san sang."""
    total = len(infos)
    if not total:
        return

    secs = ["utils", "core", "modules"]
    counts = {s: sum(len(i["sections"].get(s, [])) for i in infos) for s in secs}
    failed = sum(len(i.get("failed", [])) for i in infos)
    cogs = sum(i.get("total_cogs", 0) for i in infos)
    help_up = sum(i.get("help_updated", 0) for i in infos)
    loud = sum(1 for i in infos if i.get("lavalink"))
    ext_all = sum(counts.values())
    ready_bots = [i for i in infos if not i.get("failed")]
    ready_count = len(ready_bots)
    bot_tag = "🤖" if _UNICODE_OK else "[BOT]"

    _p()
    _p(_c(CH_FULL * 78, C_CYAN))
    if ready_count == total:
        status_sub = _T(f"{total} bot đã sẵn sàng", f"{total} bot(s) ready")
    else:
        status_sub = _T(f"{ready_count}/{total} bot đã sẵn sàng ({total - ready_count} lỗi)", f"{ready_count}/{total} bot(s) ready ({total - ready_count} error)")
    _p(_c("  " + _T("BÁO CÁO KHỞI ĐỘNG HỆ THỐNG SELFBOT", "SELFBOT STARTUP REPORT")
           + f"  {V_DOT}  {status_sub}", C_BOLD + C_CYAN))
    _p()
    _p(_row(_c(_T("Số bot đang chạy", "Bots running"), C_BOLD),
            _c(f"{ready_count}/{total}", C_GREEN if ready_count == total else C_YELLOW)))
    _p(_row(_c(_T("Extension đã nạp / bot", "Extensions per bot"), C_BOLD),
            _c(f"{ext_all}   ({_T('mỗi bot nạp riêng bản sao của nó', 'each bot loads its own copy')})", C_DIM)))
    _p()
    _p(_row(_bar("Modules", counts["modules"], ext_all or 1, 22, C_CYAN)))
    _p(_row(_bar("Core   ", counts["core"], ext_all or 1, 22, C_GREEN)))
    _p(_row(_bar("Utils  ", counts["utils"], ext_all or 1, 22, C_YELLOW)))
    _p()
    _p(_row(_c(_T("Tổng lệnh (cog) đã đăng ký", "Total commands (cogs)"), C_BOLD), _c(str(cogs), C_CYAN)))
    _p(_row(_c(_T("Lệnh help đã chèn prefix thật", "Help texts patched w/ real prefix"), C_BOLD),
            _c(str(help_up), C_CYAN)))
    _p(_row(_c(_T("Lavalink SSL sẵn sàng", "Lavalink SSL ready"), C_BOLD),
            _c(f"{loud}/{total}", C_GREEN if loud == total else C_YELLOW)))
    _p(_row(_c(_T("Lỗi nạp extension", "Load errors"), C_BOLD),
            _c(_T("không có", "none"), C_GREEN) if not failed else _c(f"{failed} loi", C_RED)))
    _p()

    for info in sorted(infos, key=lambda x: x.get("bot_no", 0)):
        no = info.get("bot_no", "?")
        head = f"  {V_TL}{V_DASH * 2} {bot_tag} BOT {no} "
        _p(_c(head + V_DASH * max(2, 74 - _w(head)), C_CYAN))
        bar = f"  {V_LINE} "

        if info.get("failed"):
            err_text = ", ".join(info["failed"])
            _p(_c(bar, C_CYAN) + _row(_c(_T("Trạng thái   ", "Status       "), C_RED), f"Lỗi đăng nhập ({err_text})"))
            _p(_c(f"  {V_BL}" + V_DASH * 75, C_CYAN))
            continue

        pfx = info.get("prefix") if info.get("prefix") is not None else ""
        forms = "   ".join(f"'{p}'" for p in (info.get("prefixes") or [pfx]))
        _p(_c(bar, C_CYAN) + _row(_c(_T("Tên Discord  ", "Username     "), C_DIM), _S(info.get("username") or "?")))
        _p(_c(bar, C_CYAN) + _row(_c(_T("User ID      ", "User ID      "), C_DIM), _S(info.get("uid") or "?")))
        _p(_c(bar, C_CYAN) + _row(_c(_T("Account      ", "Account      "), C_DIM), _S(info.get("account") or "?")))
        _p(_c(bar, C_CYAN) + _row(_c(_T("Token        ", "Token        "), C_DIM), _S(info.get("token_masked") or "?")))
        pfx_show = f"'{pfx}' (none)" if pfx == "" else f"`{pfx}`"
        _p(_c(bar, C_CYAN) + _row(_c(_T("Prefix       ", "Prefix       "), C_DIM),
                                  f"{_c(pfx_show, C_GREEN)}   {forms}"))
        _p(_c(bar, C_CYAN) + _row(_c(_T("Nguồn prefix ", "Prefix from  "), C_DIM), _S(info.get("source") or "?")))
        secs_txt = "   ".join(f"{s} {len(info['sections'].get(s, []))}"
                              for s in secs if info["sections"].get(s))
        n_ext = sum(len(v) for v in info["sections"].values())
        _p(_c(bar, C_CYAN) + _row(_c(_T("Extensions   ", "Extensions   "), C_DIM), f"{n_ext}   ({secs_txt})"))
        ext_list = ", ".join(e.rsplit(".", 1)[-1] for s in secs for e in info["sections"].get(s, []))
        if ext_list:
            items = [e.rsplit(".", 1)[-1] for s in secs for e in info["sections"].get(s, [])]
            line, cont = "", "               "
            for idx, item in enumerate(items):
                piece = item + (", " if idx < len(items) - 1 else "")
                if _w(cont + line + piece) > 76 and line:
                    _p(_c(bar, C_CYAN) + cont + line.rstrip())
                    line = ""
                line += piece
            if line:
                _p(_c(bar, C_CYAN) + cont + line.rstrip())
        _p(_c(f"  {V_BL}" + V_DASH * 75, C_CYAN))

    first_item = next((i for i in sorted(infos, key=lambda x: x.get("bot_no", 0)) if not i.get("failed")), None)
    first = (first_item.get("prefix") if first_item and first_item.get("prefix") is not None else "")
    _p()
    if ready_count == total:
        _p(_c("  " + _T("✅  Tất cả bot đã sẵn sàng.", "OK  All bots are ready."), C_GREEN)
           + "  " + _T(f"Gõ `{first}prefix` để xem prefix của bot đang nhắn, "
                      f"`{first}prefix list` để xem bảng từng account.",
                      f"Type `{first}prefix` to see this bot's prefix, "
                      f"`{first}prefix list` for the per-account table."))
    _p()


async def run_single_selfbot(token: str, prefix: str, name: str = "", bot_no: int = 1, total: int = 1, bot_id: str = "", bot_uid: Any = None):
    p = str(prefix) if prefix is not None else ""
    base_prefixes = [p]
    if p and not p.endswith(" "):
        base_prefixes.append(f"{p} ")

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
        max_messages=250,
        help_command=None,
    )
    bot._own_bot_id = bot_id
    bot._own_bot_uid = bot_uid
    bot._message_log_limiter = RollingMessageLogLimiter(f"USER_DISCORD:{name or bot_no}")
    # Gan danh tinh RIENG cua bot nay (prefix + token + ten account) thang len object
    # bot -> khi chay nhieu account dong thoi, khong the doc nham prefix cua nhau.
    try:
        from apps.user_discord.utils.prefix import bind
        bind(bot, prefix=p, name=name, token=token)
    except Exception as bind_err:
        print(f"[USER_DISCORD] prefix bind warning: {bind_err}", flush=True)

    # Cho phép Admin và các thành viên được cấp quyền dùng lệnh bot
    bot._skip_check = lambda x, y: False

    # Đăng ký vào runtime -> core/genesis có thể spawn/stop bot khác KHÔNG cần restart
    try:
        from apps.user_discord.core import runtime as _runtime
        _runtime.register(token, bot, prefix=p, name=name)
    except Exception:
        pass

    @bot.event
    async def on_connect():
        pass

    @bot.event
    async def on_ready():
        if getattr(bot, "_booted_once", False):
            return
        bot._booted_once = True
        loaded = {"utils": [], "core": [], "modules": []}
        failed: list = []
        lavalink_ok = False

        # Khởi tạo kết nối tới các Node Lavalink V4 SSL Engine
        try:
            from apps.user_discord.utils.lavalink_voice import LavalinkManager
            lavalink_mgr = LavalinkManager.get_instance(bot)
            await lavalink_mgr.initialize()
            lavalink_ok = True
        except Exception:
            lavalink_ok = False

        # Nạp extension từ utils, core, modules (KHÔNG log từng dòng - gom vào bảng thống kê)
        sections = ["utils", "core", "modules"]
        for sec in sections:
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
                    except Exception as err:
                        # File util thuan (khong phai cog -> khong co setup()) -> bo qua
                        if type(err).__name__ == "NoEntryPointError":
                            continue
                        cause = err.__cause__ or err
                        if isinstance(cause, ModuleNotFoundError) and getattr(cause, "name", None):
                            missing_pkg = cause.name.split(".")[0]
                            try:
                                import subprocess
                                subprocess.check_call(
                                    [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", missing_pkg]
                                )
                                await bot.load_extension(ext_name)
                                loaded.setdefault(sec, []).append(ext_name)
                                continue
                            except Exception:
                                pass
                        try:
                            rel_local = os.path.relpath(os.path.join(root, file), str(BASE_DIR))
                            local_ext = rel_local.replace(os.sep, ".")[:-3]
                            await bot.load_extension(local_ext)
                            loaded.setdefault(sec, []).append(local_ext)
                        except Exception as e2:
                            failed.append(f"{ext_name}: {type(e2).__name__}")

        # Thay "(prefix)" trong help/brief bang prefix THAT cua chinh bot nay
        ident, help_updated = {}, 0
        try:
            from apps.user_discord.utils.prefix import apply_help, identity
            help_updated = apply_help(bot)
            ident = identity(bot)
        except Exception:
            ident = {}

        # Áp dụng các alias đã tùy chỉnh (thay thế triệt để các lệnh cũ)
        try:
            from apps.user_discord.core.alias import apply_bot_saved_aliases
            apply_bot_saved_aliases(bot)
        except Exception:
            pass

        # Đóng góp số liệu vào bảng thống kê chung
        try:
            REGISTER_BOT({
                "bot_no": bot_no,
                "name": name,
                "username": str(bot.user) if bot.user else "?",
                "uid": bot.user.id if bot.user else None,
                "account": ident.get("account", name or "?"),
                "token_masked": ident.get("token_masked", "?"),
                "prefix": ident.get("prefix", p),
                "prefixes": ident.get("prefixes", base_prefixes),
                "source": ident.get("source", "?"),
                "sections": loaded,
                "failed": failed,
                "help_updated": help_updated,
                "lavalink": lavalink_ok,
                "total_cogs": len(bot.cogs),
            })
        except Exception as reg_err:
            pass

        READY_COUNTER.append(bot_no)
        if len(READY_COUNTER) >= total and not REPORT_DONE:
            REPORT_DONE.append(True)
            print_startup_report(sorted(REGISTER_BOTS, key=lambda x: x.get("bot_no", 0)))

    @bot.event
    async def on_message(message: discord.Message):
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
                    from apps.user_discord.utils.autorep import autoreact
                except ImportError:
                    from utils.autorep import autoreact  # type: ignore
                try:
                    await autoreact(message)
                except Exception:
                    pass
        except Exception:
            pass
        # Loc log chong tran: chi log TAG / SV-ON / BOT.
        try:
            try:
                from apps.user_discord.utils.message_log import should_log_message
            except ImportError:
                from utils.message_log import should_log_message
            try:
                from apps.user_discord.core.bot_sys import is_bot_active as _is_on
                _checker = lambda _gid: _is_on(bot, _gid)
            except Exception:
                _checker = None
            _ok, _reason = should_log_message(bot, message, bot_on_checker=_checker)
            if _ok and bot._message_log_limiter.should_log():
                try:
                    box_log = format_message_box(message, _reason)
                    print(box_log, flush=True)
                except Exception:
                    pass
        except Exception:
            pass

        if message.guild:
            guild_id = message.guild.id
            is_staff = False
            author_id = message.author.id

            if author_id == bot.user.id:
                is_staff = True
            else:
                try:
                    from apps.user_discord.core.bot_sys import is_staff as sys_is_staff
                    is_staff = sys_is_staff(bot, author_id)
                except Exception:
                    pass
                if not is_staff and hasattr(bot, "is_staff") and callable(bot.is_staff):
                    try:
                        is_staff = bot.is_staff(author_id)
                    except Exception:
                        pass

            try:
                from apps.user_discord.core.bot_sys import is_bot_active, is_internal_bot
                bot_active = is_bot_active(bot, guild_id)
                if not bot_active and not is_staff:
                    # Server đang BOT OFF:
                    # TUYỆT ĐỐI CHỈ BOT NỘI BỘ TRONG HỆ THỐNG GENESIS mới có ngoại lệ gửi lệnh reset sang bot chính.
                    # Mọi người dùng bên ngoài khác -> CÚT HẾT, DROP 100%, CÂM NÍN TUYỆT ĐỐI!
                    if not is_internal_bot(author_id):
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
            # Nếu người gửi là Bot (tài khoản Bot Discord) nhưng nằm trong hệ thống internal shard
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


    bid_str = f" ({bot_id})" if bot_id else ""
    uid_str = f" [UID: {bot_uid}]" if bot_uid else ""
    disp_name = f"'{name or f'Bot-{bot_no}'}'{bid_str}{uid_str}"

    err_msg = ""
    try:
        await bot.start(token)
    except discord.errors.LoginFailure as exc:
        err_msg = f"Lỗi token/LoginFailure ({exc})"
    except discord.errors.HTTPException as exc:
        if getattr(exc, "status", None) == 401:
            err_msg = "401 Unauthorized (Token không hợp lệ/hết hạn)"
        else:
            err_msg = f"Lỗi HTTP ({exc})"
    except Exception as exc:
        err_msg = f"Lỗi {type(exc).__name__} ({exc})"
    finally:
        if err_msg:
            try:
                from apps.user_discord.utils.prefix import identity
                ident = identity(bot)
            except Exception:
                ident = {}

            REGISTER_BOT({
                "bot_no": bot_no,
                "name": name,
                "username": f"[LỖI: {err_msg[:25]}]",
                "uid": bot_uid or None,
                "account": ident.get("account", name or f"Account-{bot_no}"),
                "token_masked": (token[:8] + "..." + token[-6:]) if len(token) > 16 else "***",
                "prefix": ident.get("prefix", p),
                "prefixes": ident.get("prefixes", base_prefixes),
                "source": ident.get("source", "config.json"),
                "sections": {},
                "failed": [err_msg],
                "help_updated": 0,
                "lavalink": False,
                "total_cogs": 0,
            })
            READY_COUNTER.append(bot_no)
            if len(READY_COUNTER) >= total and not REPORT_DONE:
                REPORT_DONE.append(True)
                print_startup_report(sorted(REGISTER_BOTS, key=lambda x: x.get("bot_no", 0)))

        try:
            from apps.user_discord.core import runtime as _runtime
            _runtime.LIVE.pop(token.strip(), None)
        except Exception:
            pass


async def main():
    cfg = load_account_config()
    targets = []
    default_prefix = cfg.get("prefix", "m")

    accounts = cfg.get("accounts", [])
    for acc in accounts:
        if isinstance(acc, dict) and acc.get("token"):
            if str(acc.get("status", "")).lower() == "lock":
                continue
            t = str(acc["token"]).strip()
            if t and not any(item["token"] == t for item in targets):
                targets.append({
                    "token": t,
                    "prefix": acc.get("prefix", default_prefix),
                    "name": acc.get("name", f"Account-{len(targets) + 1}"),
                    "bot_id": acc.get("bot_id", ""),
                    "uid": acc.get("uid", None),
                })

    tokens = cfg.get("tokens", [])
    for t in tokens:
        t_str = str(t).strip()
        if t_str and not any(item["token"] == t_str for item in targets):
            targets.append({
                "token": t_str,
                "prefix": default_prefix,
                "name": f"Account-{len(targets) + 1}",
                "bot_id": "",
                "uid": None,
            })

    single_t = str(cfg.get("token", "") or os.environ.get("USER_DISCORD_TOKEN", "")).strip()
    if single_t and not any(item["token"] == single_t for item in targets):
        targets.append({
            "token": single_t,
            "prefix": default_prefix,
            "name": "Primary",
            "bot_id": "",
            "uid": None,
        })

    if not targets:
        print("[USER_DISCORD ⚠️] Chưa cấu hình Token nào trong apps/user_discord/config.json!", flush=True)
        return

    tasks = [
        run_single_selfbot(
            acc["token"],
            acc["prefix"],
            acc.get("name", ""),
            bot_no=i,
            total=len(targets),
            bot_id=acc.get("bot_id", ""),
            bot_uid=acc.get("uid", None),
        )
        for i, acc in enumerate(targets, start=1)
    ]
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
