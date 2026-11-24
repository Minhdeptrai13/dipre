# -*- coding: utf-8 -*-
"""
core/alias.py - Quản lý Alias (Bí danh) Chính & Phụ cho các lệnh nhóm trong Core & Modules.

ĐẶC ĐIỂM QUAN TRỌNG:
1. ĐỔI LÀ THAY THẾ TRIỆT ĐỂ (REPLACE), KHÔNG PHẢI CHỈ THÊM:
   • Khi đổi (ví dụ: đổi `menu` thành `help`), tên cũ `menu` (và các alias cũ) sẽ bị
     XÓA HOÀN TOÀN khỏi bot.all_commands -> gõ `(prefix)menu` bot SẼ KHÔNG TRẢ LỜI.
   • Chỉ có alias mới (chính/phụ) được đăng ký và hoạt động.
   • Khi dùng `(prefix)alis reset`, bot mới khôi phục lại tên mặc định ban đầu.
2. KHAI BÁO VỚI ALIAS CHÍNH VÀ PHỤ:
   • Cung cấp decorator `@alias_declare(canonical, main, subs)` cho các hàm trong Core/Modules.
   • Hệ thống tự động nhận diện canonical command, alias chính (main) và danh sách alias phụ (subs).
3. LƯU TRỮ TRONG SETTING.JSON:
   • Bảng mặc định (default) và bảng hiện tại (current) được lưu tại `data/<uid>_setting.json`.
4. PHÂN QUYỀN:
   • Chỉ Admin cấp cao (admintris / bot owner / creator) mới có quyền đổi và reset.
5. LỆNH KHÔNG CẦN PREFIX "prefix":
   • Phản hồi prefix khi người dùng chat "prefix" nếu bot đang ON hoặc người gửi là Admin.
"""

from __future__ import annotations

import asyncio
import copy
import io
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

import discord
from discord.ext import commands

try:
    from apps.user_discord.utils.menu_catalog import menu_entry
except ImportError:
    from utils.menu_catalog import menu_entry

try:
    from apps.user_discord.utils.autorep import autorep
except ImportError:
    from utils.autorep import autorep

try:
    from apps.user_discord.utils.prefix import get_prefix, fmt
except ImportError:
    from utils.prefix import get_prefix, fmt

BASE_DIR = Path(__file__).resolve().parent.parent  # apps/user_discord
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def alias_declare(canonical: str, main: str = "", subs: Optional[List[str]] = None):
    """
    Decorator dùng để khai báo thông tin Alias Mặc Định (Chính & Phụ)
    trực tiếp trên các hàm lệnh ở core & modules.
    
    Ví dụ:
        @alias_declare("menu", main="menu", subs=["helpme", "ds"])
        @commands.command(name="menu")
        async def cmd_menu(self, ctx):
            ...
    """
    def decorator(func_or_cmd):
        c_name = canonical or getattr(func_or_cmd, "__name__", "")
        m_name = main or c_name
        s_list = list(subs or [])
        # Gán metadata lên function hoặc Command
        func_or_cmd._alias_canonical = c_name
        func_or_cmd._alias_default_main = m_name
        func_or_cmd._alias_default_subs = s_list
        if hasattr(func_or_cmd, "callback"):
            func_or_cmd.callback._alias_canonical = c_name
            func_or_cmd.callback._alias_default_main = m_name
            func_or_cmd.callback._alias_default_subs = s_list
        return func_or_cmd
    return decorator


# Bảng danh mục mặc định chuẩn cho tất cả nhóm lệnh / module
DEFAULT_GROUP_CATALOG: Dict[str, Dict[str, Any]] = {
    "menu": {
        "title": "Menu Bảng Lệnh",
        "desc": "Bảng hiển thị toàn bộ chức năng và danh mục lệnh",
        "main": "menu",
        "subs": ["helpme", "ds"],
    },
    "bot": {
        "title": "Bot Control",
        "desc": "Quản trị & điều khiển hệ thống bot (on/off, cam, ban, admin)",
        "main": "bot",
        "subs": [],
    },
    "gene": {
        "title": "Genesis Hub",
        "desc": "Quản lý khởi tạo, gia hạn, QR Login và reset bot",
        "main": "gene",
        "subs": ["genesis", "gen"],
    },
    "server": {
        "title": "Server Management",
        "desc": "Quản lý máy chủ, kênh, icon, đổi tên server",
        "main": "server",
        "subs": ["guild"],
    },
    "info": {
        "title": "Info Tra cứu",
        "desc": "Tra cứu thông tin tài khoản user, server, banner",
        "main": "info",
        "subs": ["information"],
    },
    "voice": {
        "title": "Voice Room",
        "desc": "Treo voice 24/7, mic, deaf, camera trong phòng thoại",
        "main": "voice",
        "subs": ["v247"],
    },
    "youtube": {
        "title": "YouTube Player",
        "desc": "Phát nhạc / âm thanh YouTube chất lượng cao",
        "main": "youtube",
        "subs": ["yt"],
    },
    "tiktok": {
        "title": "TikTok Audio",
        "desc": "Phát nhạc TikTok vào voice và tra cứu video",
        "main": "tiktok",
        "subs": ["tt"],
    },
    "soundcloud": {
        "title": "SoundCloud Stream",
        "desc": "Phát nhạc SoundCloud trực tiếp trong voice",
        "main": "soundcloud",
        "subs": ["scl"],
    },
    "rpc": {
        "title": "Activity / RPC",
        "desc": "Tùy biến trạng thái hoạt động Rich Presence",
        "main": "rpc",
        "subs": ["activity", "presence", "act"],
    },
    "afk": {
        "title": "Treo máy AFK",
        "desc": "Chế độ tự động phản hồi tin nhắn khi đi vắng",
        "main": "afk",
        "subs": [],
    },
    "del": {
        "title": "Xóa tin nhắn",
        "desc": "Xóa nhanh tin nhắn hàng loạt an toàn",
        "main": "del",
        "subs": ["delete", "xoa", "clean", "purge"],
    },
    "quest": {
        "title": "Auto Quest",
        "desc": "Tự động nhận và hoàn thành nhiệm vụ Discord",
        "main": "quest",
        "subs": ["autoquest", "nv"],
    },
    "join": {
        "title": "Tự động tham gia",
        "desc": "Gia nhập máy chủ bằng link mời nhanh",
        "main": "join",
        "subs": [],
    },
    "read": {
        "title": "Đọc tin nhắn",
        "desc": "Đánh dấu đã đọc tất cả kênh và server",
        "main": "read",
        "subs": [],
    },
    "prefix": {
        "title": "Đầu lệnh Prefix",
        "desc": "Xem và đổi đầu lệnh riêng của tài khoản bot",
        "main": "prefix",
        "subs": ["pfx", "dau-lenh", "dau_lenh"],
    },
    "alias": {
        "title": "Quản lý Alias",
        "desc": "Quản lý bí danh chính & phụ cho mọi lệnh nhóm",
        "main": "alias",
        "subs": ["alis", "aliss", "aliases"],
    },
}


class AliasCog(commands.Cog, name="Alias"):
    """Cog quản lý thay thế bí danh chính và phụ cho các nhóm lệnh."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._prefix_trigger_cooldown: Dict[int, float] = {}

    def _pfx(self) -> str:
        return get_prefix(self.bot)

    def _get_setting_path(self) -> Optional[Path]:
        if not self.bot.user:
            return None
        return DATA_DIR / f"{self.bot.user.id}_setting.json"

    def is_high_admin(self, uid: int) -> bool:
        """Kiểm tra quyền Admin cấp cao (admintris / bot owner / creator)."""
        if self.bot.user and uid == self.bot.user.id:
            return True
        try:
            from apps.user_discord.core.bot_sys import SelfBotSystem
            bs = self.bot.get_cog("SelfBotSystem")
            if bs and hasattr(bs, "is_mod") and bs.is_mod(uid):
                return True
        except Exception:
            pass
        p = self._get_setting_path()
        if p and p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                mod_list = data.get("admintris", data.get("moderator", []))
                if any(int(x) == int(uid) for x in mod_list if str(x).isdigit()):
                    return True
            except Exception:
                pass
        return False

    def is_staff_user(self, uid: int) -> bool:
        """Kiểm tra quyền Staff (Admin thường hoặc Admin cấp cao)."""
        if self.is_high_admin(uid):
            return True
        try:
            from apps.user_discord.core.bot_sys import SelfBotSystem
            bs = self.bot.get_cog("SelfBotSystem")
            if bs and hasattr(bs, "is_staff") and bs.is_staff(uid):
                return True
        except Exception:
            pass
        return False

    def load_alias_config(self) -> Dict[str, Dict[str, Any]]:
        """Đọc bảng alias từ setting.json, tự động tạo mới nếu file hoặc mục aliases chưa có."""
        p = self._get_setting_path()
        data = {}
        file_existed = False
        if p and p.exists():
            file_existed = True
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                data = {}

        aliases_sec = data.get("aliases")
        updated = not file_existed
        if not isinstance(aliases_sec, dict):
            aliases_sec = {
                "default": copy.deepcopy(DEFAULT_GROUP_CATALOG),
                "current": copy.deepcopy(DEFAULT_GROUP_CATALOG),
            }
            data["aliases"] = aliases_sec
            updated = True
        else:
            if "default" not in aliases_sec or not isinstance(aliases_sec["default"], dict):
                aliases_sec["default"] = copy.deepcopy(DEFAULT_GROUP_CATALOG)
                updated = True
            if "current" not in aliases_sec or not isinstance(aliases_sec["current"], dict):
                aliases_sec["current"] = copy.deepcopy(aliases_sec["default"])
                updated = True

            # Bổ sung các nhóm mới nếu bảng mặc định chưa có
            for k, def_item in DEFAULT_GROUP_CATALOG.items():
                if k not in aliases_sec["default"]:
                    aliases_sec["default"][k] = copy.deepcopy(def_item)
                    updated = True
                if k not in aliases_sec["current"]:
                    aliases_sec["current"][k] = copy.deepcopy(def_item)
                    updated = True

        if updated:
            try:
                p.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass

        return aliases_sec

    def save_alias_config(self, aliases_sec: Dict[str, Dict[str, Any]]) -> bool:
        """Lưu lại bảng alias vào setting.json."""
        p = self._get_setting_path()
        if not p:
            return False
        try:
            data = {}
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            data["aliases"] = aliases_sec
            p.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception as e:
            print(f"[ALIAS] Lỗi ghi config: {e}", flush=True)
            return False

    def find_command_by_canonical(self, canonical_key: str) -> Optional[commands.Command]:
        """Tìm đối tượng Command gốc theo canonical key."""
        canonical_clean = canonical_key.strip().lower()

        # 1. Tìm qua thuộc tính _alias_canonical đã gắn trên command hoặc callback
        for cmd in self.bot.commands:
            if getattr(cmd, "_alias_canonical", None) == canonical_clean:
                return cmd
            cb = getattr(cmd, "callback", None)
            if cb and getattr(cb, "_alias_canonical", None) == canonical_clean:
                return cmd

        # 2. Tìm theo tên hoặc alias mặc định trong DEFAULT_GROUP_CATALOG
        def_item = DEFAULT_GROUP_CATALOG.get(canonical_clean)
        default_names = set([canonical_clean])
        if def_item:
            default_names.add(def_item.get("main", canonical_clean))
            default_names.update(def_item.get("subs", []))

        for name in default_names:
            cmd = self.bot.get_command(name)
            if cmd:
                return cmd
            if name in self.bot.all_commands:
                return self.bot.all_commands[name]

        # 3. Duyệt toàn bộ bot.commands
        for cmd in self.bot.commands:
            if cmd.name == canonical_clean or canonical_clean in cmd.aliases:
                return cmd

        return None

    def apply_single_command_aliases(
        self,
        canonical_key: str,
        current_main: str,
        current_subs: List[str],
    ) -> bool:
        """
        THAY THẾ TRIỆT ĐỂ BÍ DANH CHO LỆNH:
        • Xóa sạch toàn bộ tên/alias mặc định gốc và các alias cũ khỏi bot.all_commands.
        • Đăng ký DUY NHẤT `current_main` (alias chính) và `current_subs` (alias phụ).
        • Gõ tên cũ (ví dụ `menu` khi đã đổi sang `help`) bot SẼ KHÔNG TRẢ LỜI.
        """
        cmd = self.find_command_by_canonical(canonical_key)
        if not cmd:
            return False

        # Đánh dấu canonical key vĩnh viễn lên command
        cmd._alias_canonical = canonical_key

        cfg = self.load_alias_config()
        def_item = cfg.get("default", {}).get(canonical_key) or DEFAULT_GROUP_CATALOG.get(canonical_key, {})
        default_main = def_item.get("main", canonical_key)
        default_subs = def_item.get("subs", [])

        # Tập hợp tất cả các key cần dọn dẹp (tên mặc định + các alias cũ đã đăng ký)
        old_keys_to_clean: Set[str] = set()
        old_keys_to_clean.add(default_main)
        old_keys_to_clean.add(canonical_key)
        old_keys_to_clean.update(default_subs)
        old_keys_to_clean.update(getattr(cmd, "_prev_applied_keys", set()))
        old_keys_to_clean.update(getattr(cmd, "_custom_applied_aliases", set()))
        if hasattr(cmd, "aliases"):
            old_keys_to_clean.update(cmd.aliases)

        # 1. GỠ BỎ TOÀN BỘ TÊN CŨ KHỎI bot.all_commands
        for old_k in old_keys_to_clean:
            if old_k in self.bot.all_commands and self.bot.all_commands[old_k] == cmd:
                del self.bot.all_commands[old_k]

        # 2. XÁC ĐỊNH BỘ BÍ DANH MỚI
        main_clean = str(current_main).strip().lower()
        subs_clean = [str(s).strip().lower() for s in current_subs if str(s).strip().lower() and str(s).strip().lower() != main_clean]

        # Cập nhật cmd.name và cmd.aliases
        cmd.name = main_clean
        cmd.aliases = subs_clean

        # 3. ĐĂNG KÝ DUY NHẤT CÁC TÊN MỚI VÀO bot.all_commands
        self.bot.all_commands[main_clean] = cmd
        for s in subs_clean:
            self.bot.all_commands[s] = cmd

        # Lưu lại tập hợp key đang hoạt động để dọn dẹp cho lần đổi kế tiếp
        active_keys = set([main_clean] + subs_clean)
        cmd._prev_applied_keys = active_keys
        cmd._custom_applied_aliases = active_keys
        return True

    def apply_all_aliases(self) -> int:
        """Áp dụng toàn bộ alias từ bảng current vào Discord.py runtime."""
        cfg = self.load_alias_config()
        current_map = cfg.get("current", {})
        default_map = cfg.get("default", {})

        count = 0
        for cmd_key, info in current_map.items():
            if not isinstance(info, dict):
                continue
            main_alias = info.get("main") or cmd_key
            subs = info.get("subs") or []
            if self.apply_single_command_aliases(cmd_key, main_alias, subs):
                count += 1
        return count

    @commands.Cog.listener()
    async def on_ready(self):
        """Khi bot sẵn sàng, áp dụng ngay các alias đã lưu."""
        self.apply_all_aliases()

    # ── Trigger không cần prefix: "prefix" ───────────────────────────────────
    @staticmethod
    def _normalize_prefix_query(raw_text: str) -> str:
        """Chuẩn hóa mọi font chữ nghệ thuật (Unicode Math Bold, Italic, Gothic...),
        in đậm (**), in nghiêng (*), code block (`), gạch chân (__), dấu tiếng Việt
        về dạng chữ latin thường để phát hiện từ 'prefix' chính xác 100%."""
        if not raw_text:
            return ""
        import unicodedata
        # 1. NFKD decomposition tách font và ký hiệu Unicode về dạng ký tự Latin gốc
        norm = unicodedata.normalize("NFKD", raw_text)
        # 2. Loại bỏ toàn bộ combining marks (dấu thanh, accent)
        norm = "".join(c for c in norm if not unicodedata.combining(c))
        # 3. Chuyển đổi đ/Đ
        norm = norm.replace("đ", "d").replace("Đ", "d")
        # 4. Thay toàn bộ ký tự Markdown Discord và dấu câu thành khoảng trắng
        norm = re.sub(r"[*_~|`>#:\^!?,.\-/\@\\()\[\]{}\"\']", " ", norm)
        return norm.lower()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Lắng nghe tin nhắn không cần prefix. Bất kỳ tin nhắn nào chứa từ 'prefix'
        (ở mọi font chữ, in đậm, in nghiêng, trần trụi hay trong câu) đều được nhận diện
        NẾU bot đang ON (trong server/DM) HOẶC người gửi là Admin / Admin cấp cao."""
        # Tránh vòng lặp nếu tin nhắn chính là tin nhắn phản hồi của bot
        if self.bot.user and message.author.id == self.bot.user.id:
            if "BotIdentity:" in message.content:
                return

        cleaned = self._normalize_prefix_query(message.content).strip()
        words = cleaned.split()
        if not words:
            return

        first_word = words[0]
        is_pfx_query = False
        if first_word in ("prefix", "pfx"):
            if len(words) > 1 and words[1] in ("set", "list", "doi", "change", "none", "off", "no"):
                return
            is_pfx_query = True
        elif first_word == "dau" and len(words) >= 2 and words[1] == "lenh":
            is_pfx_query = True

        if not is_pfx_query:
            return

        # NẾU tin nhắn này đã bắt đầu bằng prefix của chính bot này HOẶC bot này có prefix rỗng (""),
        # thì lệnh command `cmd_prefix` của discord.py sẽ tự dispatch xử lý,
        # Cog này KHÔNG phản hồi thêm trong on_message để TRÁNH BỊ REP 2 LẦN!
        cur_pfx = self._pfx()
        if cur_pfx == "" or message.content.strip().startswith(cur_pfx):
            return

        # ── KIỂM TRA ĐIỀU KIỆN CỦA RIÊNG TỪNG BOT (ISOLATED PER BOT) ────────
        bot_uid = self.bot.user.id if self.bot.user else 0
        if not bot_uid:
            return

        # 1. Đọc file setting riêng của CHÍNH bot này
        setting_file = DATA_DIR / f"{bot_uid}_setting.json"
        this_conf: Dict[str, Any] = {}
        if setting_file.exists():
            try:
                this_conf = json.loads(setting_file.read_text(encoding="utf-8"))
            except Exception:
                this_conf = {}

        # 2. Kiểm tra bot này có đang ON tại đây không? (Mặc định trong server là OFF / False)
        if message.guild:
            guild_active_map = this_conf.get("guild_active", {})
            bot_on_here = bool(guild_active_map.get(str(message.guild.id), False))
        else:
            bot_on_here = bool(this_conf.get("dm_active", True))

        # 3. Kiểm tra người gửi có phải là Admin / Admin cấp cao của CHÍNH BOT NÀY không?
        sender_id = message.author.id
        is_owner_this_bot = (sender_id == bot_uid)
        
        # Đọc thêm owner_ids & created_by từ config.json của RIÊNG BOT NÀY
        cfg_owners = set()
        try:
            cfg_path = next(
                (p for p in (BASE_DIR / "config.json", BASE_DIR / "data" / "config.json") if p.exists()),
                None,
            )
            if cfg_path:
                cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
                for acc in cfg_data.get("accounts", []):
                    if isinstance(acc, dict) and acc.get("uid") == bot_uid:
                        for oid in list(acc.get("owner_ids") or []) + [acc.get("created_by")]:
                            if oid:
                                try:
                                    cfg_owners.add(int(oid))
                                except Exception:
                                    pass
        except Exception:
            pass

        # Danh sách admintris (Admin cấp cao) của riêng bot này:
        # Gồm: Chính chủ bot_uid, owner_ids/created_by trong config.json, và admintris trong setting.json
        this_mod_list = set(cfg_owners)
        for x in this_conf.get("admintris", this_conf.get("moderator", [])):
            try:
                if str(x).isdigit():
                    this_mod_list.add(int(x))
            except Exception:
                pass

        is_high_admin_this_bot = is_owner_this_bot or (sender_id in this_mod_list)

        # Danh sách admins (Admin thường) của riêng bot này
        this_admin_list = set(this_mod_list)
        for x in this_conf.get("admins", this_conf.get("admin", [])):
            try:
                if str(x).isdigit():
                    this_admin_list.add(int(x))
            except Exception:
                pass

        is_admin_this_bot = is_high_admin_this_bot or (sender_id in this_admin_list)

        # 4. Kiểm tra người gửi có bị CHÍNH BOT NÀY cấm (CAM) không?
        cam_map = this_conf.get("cam_list", {})
        if str(sender_id) in cam_map and not is_high_admin_this_bot:
            return  # Bị bot này CAM -> Im lặng hoàn toàn

        # 5. ĐIỀU KIỆN TIÊN QUYẾT:
        # - Nếu là Admin cấp cao / Admin của BOT NÀY: Luôn rep (bất kể bot ON hay OFF).
        # - Nếu là Thành viên thường đối với BOT NÀY: CHỈ rep khi bot này đang ON tại server đó!
        #   (Nếu bot này đang OFF và người gửi không phải admin của nó -> CÂM MIỆNG 100%!)
        if not bot_on_here and not is_admin_this_bot:
            return

        # Cooldown per channel (3s) để tránh lặp rep
        chan_id = message.channel.id
        now = time.time()
        last_t = self._prefix_trigger_cooldown.get(chan_id, 0)
        if now - last_t < 3.0:
            return
        self._prefix_trigger_cooldown[chan_id] = now

        pfx = self._pfx()
        pfx_display = f"`{pfx}`" if pfx else "*(Không dùng prefix / No prefix)*"
        bot_name = self.bot.user.name if self.bot.user else "Bot"
        bot_uid = self.bot.user.id if self.bot.user else 0

        tier_txt = "Admin cấp cao (admintris)" if is_high_admin_this_bot else (
            "Admin" if is_admin_this_bot else "Thành viên"
        )

        latency_ms = int(self.bot.latency * 1000) if (self.bot.latency and self.bot.latency > 0) else 15
        pfx_clean = pfx if pfx else "None"
        status_txt = "Đang bật" if bot_on_here else "Đang tắt (Admin Only)"

        rep_text = (
            f"```\n"
            f"BotIdentity:\n"
            f"  tên           {bot_name} ({bot_uid})\n"
            f"  prefix        {pfx_clean}\n"
            f"  quyền         {tier_txt}\n"
            f"  trạng thái    {status_txt} ({latency_ms}ms)\n\n"
            f"Gõ {pfx}menu để xem toàn bộ danh sách lệnh.\n"
            f"```"
        )
        try:
            await autorep(message, content=rep_text, auto_delete_delay=30)
        except Exception:
            pass

    # ── Command Group: alias (alis, aliss, aliases) ──────────────────────────
    @menu_entry("HỆ THỐNG", "alias", "Quản lý bí danh chính và phụ cho các nhóm lệnh",
                badge="CORE", icon_sym="🏷️", icon_color=(236, 72, 153), order=3)
    @alias_declare("alias", main="alias", subs=["alis", "aliss", "aliases"])
    @commands.group(name="alias", aliases=["alis", "aliss", "aliases"], invoke_without_command=True)
    async def cmd_alias(self, ctx: commands.Context):
        """Bảng hướng dẫn lệnh tùy chỉnh Bí danh (Alias) chính và phụ."""
        p = self._pfx()

        card_file = None
        try:
            from apps.user_discord.utils.media_card import async_help_card
            buf = await async_help_card("alias", p)
            if buf:
                card_file = discord.File(buf, filename="alias_guide.png")
        except Exception as e:
            pass

        if card_file:
            await autorep(
                ctx.message,
                content=f"🏷️ **HỆ THỐNG QUẢN LÝ BÍ DANH LỆNH (ALIAS SYSTEM)**",
                file=card_file,
                auto_delete_delay=60,
            )
            return

        msg = (
            f"🏷️ **HỆ THỐNG QUẢN LÝ BÍ DANH LỆNH (ALIAS SYSTEM)**\n\n"
            f"👑 *Quyền hạn: Chỉ Admin cấp cao (admintris) mới có quyền đổi.* \n"
            f"⚠️ *Lưu ý: Đổi là thay thế hoàn toàn — tên cũ sẽ không trả lời nữa cho đến khi reset!*\n\n"
            f"📌 **Cú pháp khả dụng:**\n"
            f"• `{p}alis set main <lệnh> to <tên_mới>`: Đổi bí danh chính\n"
            f"  *Ví dụ:* `{p}alis set main menu to help` (lệnh `menu` sẽ được gọi bằng `help`)\n"
            f"• `{p}alis set sub <lệnh> to <phụ_1, phụ_2...>`: Đổi danh sách bí danh phụ\n"
            f"  *Ví dụ:* `{p}alis set sub server to sv, guild`\n"
            f"• `{p}alis reset main [lệnh|all]`: Khôi phục riêng bí danh chính về mặc định gốc\n"
            f"• `{p}alis reset sub [lệnh|all]`: Khôi phục riêng danh sách bí danh phụ về mặc định gốc\n"
            f"• `{p}alis reset [lệnh|all]`: Khôi phục cả chính & phụ về mặc định ban đầu\n"
            f"• `{p}alis list`: Xem thẻ ảnh Liquid Glass danh mục bí danh & toàn bộ tham số\n"
            f"• `{p}alis`: Xem lại bảng hướng dẫn điều khiển bí danh dạng ảnh này"
        )
        await autorep(ctx, msg, auto_delete_delay=45)

    # ── Subcommand Group: alis set (CHÍNH THỨC) ──────────────────────────────
    @cmd_alias.group(name="set", invoke_without_command=True)
    async def sub_set_group(self, ctx: commands.Context, *, raw_args: Optional[str] = None):
        """Đổi bí danh chính hoặc phụ:
        • (prefix)alis set main <lệnh> to <tên_mới>
        • (prefix)alis set sub <lệnh> to <phụ_1, phụ_2...>
        """
        if not self.is_high_admin(ctx.author.id):
            return await autorep(
                ctx,
                "❌ **Từ chối:** Chỉ **Admin cấp cao (admintris)** của bot mới có quyền thay đổi Alias!",
                auto_delete_delay=15,
            )
        p = self._pfx()
        if not raw_args:
            return await autorep(
                ctx,
                f"📌 **Cú pháp đổi Alias:**\n"
                f"• `{p}alis set main <lệnh> to <tên_mới>`: Đổi bí danh chính\n"
                f"  *Ví dụ:* `{p}alis set main menu to help`\n"
                f"• `{p}alis set sub <lệnh> to <phụ_1, phụ_2...>`: Đổi danh sách bí danh phụ\n"
                f"  *Ví dụ:* `{p}alis set sub server to sv, guild`",
                auto_delete_delay=20,
            )

        args_str = raw_args.strip()
        parts = args_str.split(None, 1)
        sub_type = parts[0].lower() if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        if sub_type == "main":
            return await self._handle_main_set(ctx, rest)
        elif sub_type in ("sub", "subs"):
            return await self._handle_sub_set(ctx, rest)
        else:
            return await self._handle_main_set(ctx, args_str)

    @sub_set_group.command(name="main")
    async def sub_set_main_cmd(self, ctx: commands.Context, *, raw_args: str = None):
        """Đổi bí danh chính: (prefix)alis set main <lệnh> to <tên_mới>"""
        await self._handle_main_set(ctx, raw_args)

    @sub_set_group.command(name="sub", aliases=["subs"])
    async def sub_set_sub_cmd(self, ctx: commands.Context, *, raw_args: str = None):
        """Đổi bí danh phụ: (prefix)alis set sub <lệnh> to <phụ_1, phụ_2...>"""
        await self._handle_sub_set(ctx, raw_args)

    # ── Tương thích ngược: alis main set & alis sub set ──────────────────────
    @cmd_alias.group(name="main", invoke_without_command=True)
    async def sub_main_group(self, ctx: commands.Context, *, raw_args: Optional[str] = None):
        if raw_args:
            args_str = raw_args.strip()
            if args_str.lower().startswith("set "):
                return await self._handle_main_set(ctx, args_str[4:].strip())
            return await self._handle_main_set(ctx, args_str)
        p = self._pfx()
        await autorep(
            ctx,
            f"📌 **Cú pháp đổi Alias CHÍNH:** `{p}alis set main <lệnh> to <tên_mới>`\n"
            f"*Ví dụ:* `{p}alis set main menu to help`",
            auto_delete_delay=20,
        )

    @sub_main_group.command(name="set")
    async def sub_main_set(self, ctx: commands.Context, *, raw_args: str = None):
        await self._handle_main_set(ctx, raw_args)

    @cmd_alias.group(name="sub", aliases=["subs"], invoke_without_command=True)
    async def sub_sub_group(self, ctx: commands.Context, *, raw_args: Optional[str] = None):
        if raw_args:
            args_str = raw_args.strip()
            if args_str.lower().startswith("set "):
                return await self._handle_sub_set(ctx, args_str[4:].strip())
            return await self._handle_sub_set(ctx, args_str)
        p = self._pfx()
        await autorep(
            ctx,
            f"📌 **Cú pháp đổi Alias PHỤ:** `{p}alis set sub <lệnh> to <phụ_1, phụ_2...>`\n"
            f"*Ví dụ:* `{p}alis set sub server to sv, guild`",
            auto_delete_delay=20,
        )

    @sub_sub_group.command(name="set")
    async def sub_sub_set(self, ctx: commands.Context, *, raw_args: str = None):
        await self._handle_sub_set(ctx, raw_args)

    async def _handle_main_set(self, ctx: commands.Context, raw_args: Optional[str]):
        if not self.is_high_admin(ctx.author.id):
            return await autorep(
                ctx,
                "❌ **Từ chối:** Chỉ **Admin cấp cao (admintris)** của bot mới có quyền thay đổi Alias!",
                auto_delete_delay=15,
            )
        p = self._pfx()
        if not raw_args:
            return await autorep(
                ctx,
                f"⚠️ **Thiếu tham số!** Cú pháp: `{p}alis set main <lệnh> to <tên_mới>`\n"
                f"*Ví dụ:* `{p}alis set main menu to help`",
                auto_delete_delay=20,
            )
        args_str = raw_args.strip()
        if " to " in args_str:
            target, new_main = args_str.split(" to ", 1)
        elif "->" in args_str:
            target, new_main = args_str.split("->", 1)
        elif ":" in args_str:
            target, new_main = args_str.split(":", 1)
        else:
            tokens = args_str.split()
            if len(tokens) >= 2:
                target = tokens[0]
                new_main = tokens[1]
            else:
                return await autorep(
                    ctx,
                    f"⚠️ Cú pháp chưa đúng! Ví dụ: `{p}alis set main menu to help`",
                    auto_delete_delay=20,
                )
        cfg = self.load_alias_config()
        return await self._apply_custom_alias(ctx, cfg, target.strip().lower(), new_main=new_main.strip().lower())

    async def _handle_sub_set(self, ctx: commands.Context, raw_args: Optional[str]):
        if not self.is_high_admin(ctx.author.id):
            return await autorep(
                ctx,
                "❌ **Từ chối:** Chỉ **Admin cấp cao (admintris)** của bot mới có quyền thay đổi Alias!",
                auto_delete_delay=15,
            )
        p = self._pfx()
        if not raw_args:
            return await autorep(
                ctx,
                f"⚠️ **Thiếu tham số!** Cú pháp: `{p}alis set sub <lệnh> to <phụ_1, phụ_2...>`\n"
                f"*Ví dụ:* `{p}alis set sub server to sv, guild`",
                auto_delete_delay=20,
            )
        args_str = raw_args.strip()
        if " to " in args_str:
            target, subs_raw = args_str.split(" to ", 1)
        elif "->" in args_str:
            target, subs_raw = args_str.split("->", 1)
        elif ":" in args_str:
            target, subs_raw = args_str.split(":", 1)
        else:
            tokens = args_str.split()
            if len(tokens) >= 2:
                target = tokens[0]
                subs_raw = " ".join(tokens[1:])
            else:
                return await autorep(
                    ctx,
                    f"⚠️ Cú pháp chưa đúng! Ví dụ: `{p}alis set sub server to sv, guild`",
                    auto_delete_delay=20,
                )
        subs = [s.strip().lower() for s in subs_raw.replace(",", " ").split() if s.strip()]
        cfg = self.load_alias_config()
        return await self._apply_custom_alias(ctx, cfg, target.strip().lower(), new_subs=subs)

    async def _apply_custom_alias(
        self,
        ctx: commands.Context,
        cfg: Dict[str, Dict[str, Any]],
        target: str,
        new_main: Optional[str] = None,
        new_subs: Optional[List[str]] = None,
    ):
        """Lưu và áp dụng alias cho mục tiêu target (thay thế hoàn toàn)."""
        current_map = cfg["current"]
        default_map = cfg["default"]

        matched_key = None
        for k in current_map.keys():
            if k == target or target == current_map[k].get("main") or target in current_map[k].get("subs", []):
                matched_key = k
                break
            if target in (f"modules.{k}", f"core.{k}", f"{k}.py"):
                matched_key = k
                break

        if not matched_key:
            cmd_obj = self.find_command_by_canonical(target)
            if cmd_obj:
                matched_key = getattr(cmd_obj, "_alias_canonical", cmd_obj.name)
                if matched_key not in current_map:
                    current_map[matched_key] = {
                        "title": matched_key.title(),
                        "desc": getattr(cmd_obj, "help", "") or "Lệnh hệ thống",
                        "main": matched_key,
                        "subs": list(cmd_obj.aliases),
                    }
                    default_map[matched_key] = copy.deepcopy(current_map[matched_key])

        if not matched_key:
            avail = ", ".join(f"`{k}`" for k in sorted(current_map.keys()))
            return await autorep(
                ctx,
                f"❌ Không tìm thấy nhóm lệnh nào khớp với `{target}`!\n"
                f"📋 Các nhóm lệnh hợp lệ: {avail}",
                auto_delete_delay=25,
            )

        entry = current_map[matched_key]
        old_main = entry.get("main", matched_key)

        if new_main is not None:
            entry["main"] = new_main
        if new_subs is not None:
            entry["subs"] = new_subs

        # Lưu file config
        self.save_alias_config(cfg)

        # CẬP NHẬT TỨC THÌ (XÓA TÊN CŨ, GÁN TÊN MỚI)
        ok = self.apply_single_command_aliases(matched_key, entry["main"], entry.get("subs", []))

        subs_str = ", ".join(f"`{s}`" for s in entry.get("subs", [])) if entry.get("subs") else "*Không có*"
        p = self._pfx()
        msg = (
            f"✅ **ĐÃ THAY ĐỔI BÍ DANH (ALIAS) THÀNH CÔNG!**\n\n"
            f"🏷️ **Nhóm lệnh:** `{matched_key}`\n"
            f"⭐ **Alias CHÍNH MỚI:** `{entry['main']}`\n"
            f"🔹 **Alias PHỤ MỚI:** {subs_str}\n\n"
            f"🚫 **Lưu ý:** Lệnh cũ `{p}{old_main}` đã bị TẮT (bot sẽ không trả lời `{p}{old_main}`).\n"
            f"⚡ **Hãy dùng:** `{p}{entry['main']}`."
        )
        await autorep(ctx, msg, auto_delete_delay=30)

    # ── Subcommand Group: alis reset ─────────────────────────────────────────
    @cmd_alias.group(name="reset", aliases=["default", "clear"], invoke_without_command=True)
    async def sub_reset(self, ctx: commands.Context, target: Optional[str] = None, *, extra: Optional[str] = None):
        """Khôi phục bí danh về mặc định gốc:
        • (prefix)alis reset main [lệnh|all] -> Khôi phục riêng bí danh chính
        • (prefix)alis reset sub [lệnh|all]  -> Khôi phục riêng bí danh phụ
        • (prefix)alis reset [lệnh|all]     -> Khôi phục cả chính & phụ
        """
        if not self.is_high_admin(ctx.author.id):
            return await autorep(
                ctx,
                "❌ **Từ chối:** Chỉ **Admin cấp cao (admintris)** mới có quyền reset Alias!",
                auto_delete_delay=15,
            )

        if target and target.lower() == "main":
            return await self._handle_reset_main(ctx, extra)
        if target and target.lower() in ("sub", "subs"):
            return await self._handle_reset_sub(ctx, extra)

        return await self._handle_reset_full(ctx, target)

    @sub_reset.command(name="main")
    async def sub_reset_main_cmd(self, ctx: commands.Context, target: Optional[str] = None):
        """Khôi phục riêng bí danh CHÍNH: (prefix)alis reset main [lệnh|all]"""
        await self._handle_reset_main(ctx, target)

    @sub_reset.command(name="sub", aliases=["subs"])
    async def sub_reset_sub_cmd(self, ctx: commands.Context, target: Optional[str] = None):
        """Khôi phục riêng danh sách bí danh PHỤ: (prefix)alis reset sub [lệnh|all]"""
        await self._handle_reset_sub(ctx, target)

    async def _handle_reset_main(self, ctx: commands.Context, target: Optional[str]):
        """Chỉ khôi phục bí danh CHÍNH (giữ nguyên phụ)."""
        if not self.is_high_admin(ctx.author.id):
            return await autorep(
                ctx,
                "❌ **Từ chối:** Chỉ **Admin cấp cao (admintris)** mới có quyền reset Alias!",
                auto_delete_delay=15,
            )
        cfg = self.load_alias_config()
        default_map = cfg["default"]
        current_map = cfg["current"]

        if not target or target.lower() in ("all", "toanbo", "tatca"):
            for k, def_val in default_map.items():
                if k in current_map:
                    current_map[k]["main"] = def_val["main"]
            self.save_alias_config(cfg)
            self.apply_all_aliases()
            return await autorep(
                ctx,
                "🔄 **ĐÃ KHÔI PHỤC TOÀN BỘ BÍ DANH CHÍNH (MAIN) VỀ MẶC ĐỊNH GỐC!**\n"
                "Danh sách bí danh phụ (sub) vẫn được giữ nguyên.",
                auto_delete_delay=30,
            )

        target_clean = target.strip().lower()
        matched_key = None
        for k in default_map.keys():
            if k == target_clean or default_map[k].get("main") == target_clean or target_clean in (f"modules.{k}", f"core.{k}"):
                matched_key = k
                break

        if not matched_key:
            return await autorep(
                ctx,
                f"❌ Không tìm thấy nhóm lệnh mặc định nào tên `{target}`!\n"
                f"*(Lưu ý: hãy nhập đúng tên lệnh gốc mặc định, ví dụ `menu`, `server`, `info`)*",
                auto_delete_delay=20,
            )

        current_map[matched_key]["main"] = default_map[matched_key]["main"]
        self.save_alias_config(cfg)
        self.apply_single_command_aliases(
            matched_key,
            current_map[matched_key]["main"],
            current_map[matched_key].get("subs", []),
        )

        main_def = current_map[matched_key]["main"]
        await autorep(
            ctx,
            f"🔄 **Đã khôi phục Bí Danh CHÍNH của lệnh `{matched_key}` về mặc định:** `{main_def}`!\n"
            f"*(Bí danh phụ hiện tại vẫn được giữ nguyên)*",
            auto_delete_delay=25,
        )

    async def _handle_reset_sub(self, ctx: commands.Context, target: Optional[str]):
        """Chỉ khôi phục danh sách bí danh PHỤ (giữ nguyên chính)."""
        if not self.is_high_admin(ctx.author.id):
            return await autorep(
                ctx,
                "❌ **Từ chối:** Chỉ **Admin cấp cao (admintris)** mới có quyền reset Alias!",
                auto_delete_delay=15,
            )
        cfg = self.load_alias_config()
        default_map = cfg["default"]
        current_map = cfg["current"]

        if not target or target.lower() in ("all", "toanbo", "tatca"):
            for k, def_val in default_map.items():
                if k in current_map:
                    current_map[k]["subs"] = list(def_val.get("subs", []))
            self.save_alias_config(cfg)
            self.apply_all_aliases()
            return await autorep(
                ctx,
                "🔄 **ĐÃ KHÔI PHỤC TOÀN BỘ BÍ DANH PHỤ (SUB) VỀ MẶC ĐỊNH GỐC!**\n"
                "Bí danh chính (main) hiện tại vẫn được giữ nguyên.",
                auto_delete_delay=30,
            )

        target_clean = target.strip().lower()
        matched_key = None
        for k in default_map.keys():
            if k == target_clean or default_map[k].get("main") == target_clean or target_clean in (f"modules.{k}", f"core.{k}"):
                matched_key = k
                break

        if not matched_key:
            return await autorep(
                ctx,
                f"❌ Không tìm thấy nhóm lệnh mặc định nào tên `{target}`!\n"
                f"*(Lưu ý: hãy nhập đúng tên lệnh gốc mặc định, ví dụ `menu`, `server`, `info`)*",
                auto_delete_delay=20,
            )

        current_map[matched_key]["subs"] = list(default_map[matched_key].get("subs", []))
        self.save_alias_config(cfg)
        self.apply_single_command_aliases(
            matched_key,
            current_map[matched_key]["main"],
            current_map[matched_key].get("subs", []),
        )

        subs_def = ", ".join(f"`{s}`" for s in current_map[matched_key].get("subs", [])) or "*Không có*"
        await autorep(
            ctx,
            f"🔄 **Đã khôi phục Bí Danh PHỤ của lệnh `{matched_key}` về mặc định:** {subs_def}!\n"
            f"*(Bí danh chính hiện tại vẫn là `{current_map[matched_key]['main']}`)*",
            auto_delete_delay=25,
        )

    async def _handle_reset_full(self, ctx: commands.Context, target: Optional[str]):
        """Khôi phục cả bí danh CHÍNH và PHỤ về mặc định."""
        cfg = self.load_alias_config()
        default_map = cfg["default"]
        current_map = cfg["current"]

        if not target or target.lower() in ("all", "toanbo", "tatca"):
            cfg["current"] = copy.deepcopy(default_map)
            self.save_alias_config(cfg)
            self.apply_all_aliases()
            return await autorep(
                ctx,
                "🔄 **ĐÃ KHÔI PHỤC TOÀN BỘ ALIAS (CHÍNH & PHỤ) VỀ BẢNG MẶC ĐỊNH GỐC!**\n"
                "Tất cả các tên lệnh cũ ban đầu đã được mở lại bình thường.",
                auto_delete_delay=30,
            )

        target_clean = target.strip().lower()
        matched_key = None
        for k in default_map.keys():
            if k == target_clean or default_map[k].get("main") == target_clean or target_clean in (f"modules.{k}", f"core.{k}"):
                matched_key = k
                break

        if not matched_key:
            return await autorep(
                ctx,
                f"❌ Không tìm thấy nhóm lệnh `{target}` trong bảng mặc định!",
                auto_delete_delay=20,
            )

        current_map[matched_key] = copy.deepcopy(default_map[matched_key])
        self.save_alias_config(cfg)
        self.apply_single_command_aliases(
            matched_key,
            current_map[matched_key]["main"],
            current_map[matched_key].get("subs", []),
        )

        main_def = current_map[matched_key]["main"]
        subs_def = ", ".join(f"`{s}`" for s in current_map[matched_key].get("subs", [])) or "*Không có*"
        await autorep(
            ctx,
            f"🔄 **Đã khôi phục TOÀN BỘ lệnh `{matched_key}` về mặc định!**\n"
            f"• Tên/Alias chính: `{main_def}`\n"
            f"• Alias phụ: {subs_def}",
            auto_delete_delay=25,
        )

    # ── Subcommand: alis list ────────────────────────────────────────────────
    @cmd_alias.command(name="list", aliases=["show", "all", "ls"])
    async def sub_list(self, ctx: commands.Context):
        """Xem danh sách bí danh: bảng mặc định và bảng hiện tại kèm Card ảnh."""
        cfg = self.load_alias_config()
        def_map = cfg.get("default", {})
        cur_map = cfg.get("current", {})

        p = self._pfx()

        lines_def = []
        lines_cur = []

        all_keys = sorted(set(list(def_map.keys()) + list(cur_map.keys())))
        for k in all_keys:
            d_item = def_map.get(k, {})
            c_item = cur_map.get(k, {})

            d_main = d_item.get("main", k)
            d_subs = ", ".join(d_item.get("subs", [])) if d_item.get("subs") else "—"

            c_main = c_item.get("main", k)
            c_subs = ", ".join(c_item.get("subs", [])) if c_item.get("subs") else "—"

            is_modified = (c_main != d_main) or (set(c_item.get("subs", [])) != set(d_item.get("subs", [])))
            mod_mark = "⚡ " if is_modified else "• "

            lines_def.append(f"• `{k}`: Chính: **{d_main}** | Phụ: {d_subs}")
            lines_cur.append(f"{mod_mark}`{k}`: Chính: **{c_main}** | Phụ: {c_subs}")

        text_summary = (
            f"🏷️ **DANH SÁCH BÍ DANH LỆNH (ALIAS CATALOG)**\n"
            f"👑 *Quyền hạn: Admin cấp cao* | *Đổi lệnh:* `{p}alis set <lệnh> to <alias>`\n"
            f"⚠️ *Đổi là thay thế hoàn toàn — tên cũ sẽ không trả lời.*\n\n"
            f"📋 **BẢNG MẶC ĐỊNH (DEFAULT):**\n" + "\n".join(lines_def[:8]) + "\n"
            f"*(...và {max(0, len(lines_def) - 8)} nhóm lệnh khác)*\n\n"
            f"⚡ **BẢNG HIỆN TẠI (CURRENT):**\n" + "\n".join(lines_cur[:8]) + "\n"
            f"*(Dấu ⚡ đánh dấu các lệnh đã được thay thế)*"
        )

        card_file = None
        try:
            buf = await self.render_alias_card(def_map, cur_map)
            if buf:
                card_file = discord.File(buf, filename="alias_list.png")
        except Exception as e:
            print(f"[ALIAS] Lỗi vẽ ảnh alias card: {e}", flush=True)

        if card_file:
            await autorep(ctx.message, content=text_summary, file=card_file, auto_delete_delay=60)
        else:
            await autorep(ctx, text_summary, auto_delete_delay=60)

    # ── Liquid Glass Card: Alias List ────────────────────────────────────────
    async def render_alias_card(
        self,
        default_map: Dict[str, Dict[str, Any]],
        current_map: Dict[str, Dict[str, Any]],
    ) -> Optional[io.BytesIO]:
        """Tạo card ảnh Liquid Glass cao cấp hiển thị toàn bộ tham số và lệnh bí danh."""
        try:
            from apps.user_discord.utils import glass as G
        except Exception:
            try:
                from utils import glass as G
            except Exception:
                return None

        pad = 24
        W = 1200
        keys = sorted(set(list(default_map.keys()) + list(current_map.keys())))
        num_items = len(keys)
        col1_keys = keys[:(num_items + 1) // 2]
        col2_keys = keys[(num_items + 1) // 2:]
        max_rows = max(len(col1_keys), len(col2_keys))

        header_h = 88
        row_h = 56
        row_gap = 8
        footer_h = 76
        H = pad + header_h + 16 + max_rows * (row_h + row_gap) + 16 + footer_h + pad

        cv = G.GlassCanvas(W, H)

        # 1. Header Card
        p = self._pfx()
        cv.glass((pad, pad, W - pad, pad + header_h), 20, blur=24, tint=(15, 23, 42, 180), rim=(236, 120))
        cv.dots(pad + 18, pad + 24)
        f_title = cv.font("b", 22)
        f_sub = cv.font("r", 12.5)
        bot_lbl = self.bot.user.name if getattr(self.bot, "user", None) else "Selfbot"
        cv.text(pad + 20, pad + 54, "🏷️ BẢNG BÍ DANH LỆNH HỆ THỐNG (ALIAS CATALOG)", f_title, G.C_TEXT, vcenter=True)
        cv.text(pad + 20, pad + 74, f"Bot: {bot_lbl} • Prefix: '{p}' • Đổi là thay thế hoàn toàn — tên cũ sẽ không trả lời nữa", f_sub, G.C_MUTED, vcenter=True)

        # 2. Hai cột lệnh chi tiết
        col_w = (W - 2 * pad - 18) / 2
        start_y = pad + header_h + 16

        for col_idx, col_items in enumerate([col1_keys, col2_keys]):
            cx1 = pad + col_idx * (col_w + 18)
            cx2 = cx1 + col_w
            for r_idx, k in enumerate(col_items):
                ry1 = start_y + r_idx * (row_h + row_gap)
                ry2 = ry1 + row_h

                d_item = default_map.get(k, {})
                c_item = current_map.get(k, {})

                d_main = d_item.get("main", k)
                d_subs = ", ".join(d_item.get("subs", [])) if d_item.get("subs") else "none"

                c_main = c_item.get("main", k)
                c_subs = ", ".join(c_item.get("subs", [])) if c_item.get("subs") else "none"

                is_mod = (c_main != d_main) or (set(c_item.get("subs", [])) != set(d_item.get("subs", [])))

                # Hộp dòng kính
                tint = (40, 20, 60, 160) if is_mod else (15, 23, 42, 140)
                rim = (236, 140) if is_mod else (100, 60)
                cv.glass((cx1, ry1, cx2, ry2), 14, blur=18, tint=tint, rim=rim)

                # Tag badge nhóm lệnh
                badge_grad = G.G_PURPLE if is_mod else G.G_BLUE
                pill_str = f"/{k}"
                pw = cv.tlen(pill_str, cv.font("b", 12)) + 20
                cv.pill(cx1 + 12, ry1 + 10, pill_str, cv.font("b", 12), badge_grad, h=22, padx=10)

                # Bí danh chính
                main_color = (244, 114, 182) if is_mod else (52, 211, 153)
                lead = "⚡ ĐÃ ĐỔI: " if is_mod else "CHÍNH: "
                cv.rich(cx1 + 12 + pw + 12, ry1 + 21, [
                    (lead, cv.font("b", 11), G.C_MUTED),
                    (c_main, cv.font("b", 12.5), main_color)
                ], vcenter=True)

                # Tham số lệnh & bí danh phụ
                param_desc = f"Phụ: {c_subs}  •  Gốc: {d_main} (alis set {k} to <mới>)"
                fit_desc = cv.fit(param_desc, cv.font("r", 10.5), col_w - 24)
                cv.text(cx1 + 14, ry1 + 42, fit_desc, cv.font("r", 10.5), G.C_MUTED, vcenter=True)

        # 3. Footer hướng dẫn toàn bộ cú pháp & tham số
        fy1 = start_y + max_rows * (row_h + row_gap) + 16
        fy2 = fy1 + footer_h
        cv.glass((pad, fy1, W - pad, fy2), 18, blur=22, tint=(12, 16, 28, 180), rim=(251, 120))
        cv.text(pad + 20, fy1 + 20, "📌 CÚ PHÁP & THAM SỐ ĐIỀU KHIỂN BÍ DANH (ALIAS):", cv.font("b", 12), G.C_GOLD, vcenter=True)
        guide_p1 = f"• Đổi CHÍNH: {p}alis main set <lệnh> to <alias_chính>  • Đổi PHỤ: {p}alis sub set <lệnh> to <phụ_1, phụ_2...>"
        guide_p2 = f"• Xem bảng: {p}alis list  • Khôi phục gốc: {p}alis reset [lệnh | all]  • Lưu ý: Đổi là thay thế toàn bộ!"
        cv.text(pad + 20, fy1 + 42, guide_p1, cv.font("r", 11.5), G.C_TEXT, vcenter=True)
        cv.text(pad + 20, fy1 + 60, guide_p2, cv.font("r", 11.5), G.C_MUTED, vcenter=True)

        return cv.finalize()


def apply_bot_saved_aliases(bot: commands.Bot) -> int:
    """Hàm tiện ích toàn cục để áp dụng alias cho bot instance."""
    cog = bot.get_cog("Alias")
    if cog and hasattr(cog, "apply_all_aliases"):
        return cog.apply_all_aliases()
    return 0


async def setup(bot: commands.Bot):
    """Đăng ký Cog Alias vào hệ thống selfbot."""
    cog = AliasCog(bot)
    await bot.add_cog(cog)
    if bot.user:
        cog.apply_all_aliases()
