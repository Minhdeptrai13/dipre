import discord
from discord.ext import commands, tasks
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageEnhance
from collections import defaultdict, deque
from pathlib import Path
import json
import asyncio
import os
import time
import io
import datetime
from datetime import timedelta
import aiohttp
import random
from typing import Union, Optional, Tuple, List, Dict, Any

try:  # khai báo mục menu GUI - (prefix)menu
    from apps.user_discord.utils.menu_catalog import menu_entry
except ImportError:  # fallback khi chay truc tiep / doi sys.path
    from utils.menu_catalog import menu_entry

BASE_DIR = Path(__file__).resolve().parent.parent  # c:\Users\BinhMinh\Downloads\Code\botdis\apps\user_discord
DATA_DIR = BASE_DIR / "data"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
FONTS_DIR = PROJECT_ROOT / "fonts"
BACKGROUNDS_DIR = PROJECT_ROOT / "backgrounds"

DATA_DIR.mkdir(parents=True, exist_ok=True)
FONTS_DIR.mkdir(parents=True, exist_ok=True)
BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)


class SelfBotSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.uid = None
        self.config_path = None
        self.nuke_counter = defaultdict(lambda: defaultdict(int))
        self.spam_tracker = defaultdict(lambda: deque(maxlen=25))
        self.spam_violations = defaultdict(int)

    @property
    def current_uid(self) -> Optional[int]:
        if self.bot.user:
            return self.bot.user.id
        return self.uid

    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_for_user()

    async def init_for_user(self):
        """Khởi tạo config (uid)_setting.json tại apps/user_discord/data và đưa uid token lên admintris & admins."""
        if not self.bot.user:
            return
        self.uid = self.bot.user.id
        self.config_path = DATA_DIR / f"{self.uid}_setting.json"
        
        is_first_time = not self.config_path.exists()
        data, updated = self.ensure_config()
        if is_first_time:
            print(f"[USER_DISCORD] [INIT] Tạo mới cấu hình {self.config_path.name} | UID {self.uid} -> admintris & admins.", flush=True)
        elif updated:
            print(f"[USER_DISCORD] [UPDATE] Bổ sung UID {self.uid} vào admintris/admins trong {self.config_path.name}.", flush=True)

        try:
            if not self.clean_temp_punishments.is_running():
                self.clean_temp_punishments.start()
        except Exception:
            pass

    def _creator_ids(self) -> list:
        """ID NGƯỜI TẠO bot này (created_by + owner_ids trong config.json).

        Dùng để đưa người tạo (acc chính) lên admintris/admins khi khởi tạo
        setting json — ai tạo bot = admin cap cao cua bot do.
        """
        ids: list = []
        try:
            cfg_path = next(
                (p for p in (BASE_DIR / "config.json", BASE_DIR / "data" / "config.json") if p.exists()),
                None,
            )
            if cfg_path is None:
                return ids
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            accounts = [a for a in cfg.get("accounts", []) if isinstance(a, dict)]
            try:
                from apps.user_discord.utils.prefix import token_of
            except ImportError:
                from utils.prefix import token_of
            tok = ""
            try:
                tok = str(token_of(self.bot) or "").strip()
            except Exception:
                tok = ""
            me = getattr(self.bot, "user", None)
            entry = None
            # 1. Khop theo token chinh cua bot nay (chinh xac nhat)
            if tok:
                try:
                    from apps.shared.token_crypto import decrypt
                except Exception:
                    decrypt = lambda x: x
                entry = next(
                    (a for a in accounts if str(a.get("token") or "").strip() == tok or str(decrypt(a.get("token")) or "").strip() == tok),
                    None,
                )
            # 2. Khop theo uid da luu trong entry
            if entry is None and me is not None:
                entry = next(
                    (a for a in accounts if str(a.get("uid") or "") == str(me.id)),
                    None,
                )
            # 3. Khop theo ten account
            if entry is None and me is not None:
                me_name = str(getattr(me, "name", "") or "").strip().lower()
                if me_name:
                    entry = next(
                        (a for a in accounts
                         if str(a.get("name") or "").strip().lower() == me_name),
                        None,
                    )
            if not isinstance(entry, dict):
                return ids
            for raw in list(entry.get("owner_ids") or []) + [entry.get("created_by")]:
                try:
                    v = int(raw)
                except Exception:
                    continue
                if v and v not in ids:
                    ids.append(v)
        except Exception:
            return ids
        return ids

    def ensure_config(self) -> dict:
        defaults = {
            "admintris": [self.uid] if self.uid else [],
            "admins": [self.uid] if self.uid else [],
            "ban_list": {},
            "mute_voice_list": {},
            "cam_list": {},
            "block_list": {},
            "skip_list": {},
            "bad_words": [],
            "settings": {},
            "temp_punishments": [],
            "aliases": {},
        }
        data = {}
        file_existed = self.config_path and self.config_path.exists()
        if file_existed:
            try:
                with self.config_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        updated = not file_existed
        for k, v in defaults.items():
            if k not in data:
                data[k] = v
                updated = True

        # Tự động đồng bộ UID token vào admintris (cấp cao) và admins (admin thường)
        if self.uid:
            if "admintris" not in data or not isinstance(data["admintris"], list):
                data["admintris"] = [self.uid]
                updated = True
            elif self.uid not in data["admintris"]:
                data["admintris"].append(self.uid)
                updated = True

            if "admins" not in data or not isinstance(data["admins"], list):
                data["admins"] = [self.uid]
                updated = True
            elif self.uid not in data["admins"]:
                data["admins"].append(self.uid)
                updated = True

        # Dong bo ID NGUOI TAO bot (created_by / owner_ids trong config.json)
        # len admintris & admins -> ai tao bot se la admin cap cao cua bot do.
        for oid in self._creator_ids():
            for key in ("admintris", "admins"):
                lst = data.get(key)
                if not isinstance(lst, list):
                    lst = []
                    data[key] = lst
                    updated = True
                if oid not in lst:
                    lst.append(oid)
                    updated = True

        if updated or not self.config_path.exists():
            self.save_config(data)
        return data, updated

    def _system_root_admins(self) -> set:
        """Lấy tất cả UID là Admin cấp cao tối cao của hệ thống:
        - Owner / Creator của mọi bot trong config.json (đặc biệt là Prime bot)
        - UID của chính Prime bot
        - Toàn bộ admintris trong file setting của Prime bot.
        """
        roots = set()
        try:
            cfg_path = next(
                (p for p in (BASE_DIR / "config.json", BASE_DIR / "data" / "config.json") if p.exists()),
                None,
            )
            if cfg_path:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                accounts = [a for a in cfg.get("accounts", []) if isinstance(a, dict)]
                prime_acc = next((a for a in accounts if a.get("role") == "prime"), accounts[0] if accounts else None)
                if prime_acc:
                    # Chỉ owner / creator của BOT CHÍNH (Prime) mới là root admin tối cao
                    for oid in list(prime_acc.get("owner_ids") or []) + [prime_acc.get("created_by")]:
                        try:
                            if oid:
                                roots.add(int(oid))
                        except Exception:
                            pass
                    p_uid = prime_acc.get("uid")
                    if p_uid:
                        try:
                            roots.add(int(p_uid))
                            p_setting = DATA_DIR / f"{p_uid}_setting.json"
                            if p_setting.exists():
                                p_data = json.loads(p_setting.read_text(encoding="utf-8"))
                                for adm in p_data.get("admintris", p_data.get("moderator", [])):
                                    try:
                                        roots.add(int(adm))
                                    except Exception:
                                        pass
                        except Exception:
                            pass
        except Exception:
            pass
        return roots

    def _system_root_staff(self) -> set:
        """Lấy tất cả UID là Staff (Admin cấp cao hoặc Admin thường của Prime bot / Creator)."""
        staff = set(self._system_root_admins())
        try:
            cfg_path = next(
                (p for p in (BASE_DIR / "config.json", BASE_DIR / "data" / "config.json") if p.exists()),
                None,
            )
            if cfg_path:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                accounts = [a for a in cfg.get("accounts", []) if isinstance(a, dict)]
                prime_acc = next((a for a in accounts if a.get("role") == "prime"), accounts[0] if accounts else None)
                if prime_acc:
                    p_uid = prime_acc.get("uid")
                    if p_uid:
                        try:
                            staff.add(int(p_uid))
                            p_setting = DATA_DIR / f"{p_uid}_setting.json"
                            if p_setting.exists():
                                p_data = json.loads(p_setting.read_text(encoding="utf-8"))
                                for adm in p_data.get("admins", p_data.get("admin", [])):
                                    try:
                                        staff.add(int(adm))
                                    except Exception:
                                        pass
                        except Exception:
                            pass
        except Exception:
            pass
        return staff

    def load_config(self) -> dict:
        """Đọc file cấu hình tại apps/user_discord/data/(uid)_setting.json, tự phục hồi nếu file bị xóa."""
        # Tự động gán config_path theo bot.user nếu chưa khởi tạo
        if not self.config_path or not self.uid:
            c_uid = self.current_uid
            if c_uid:
                self.uid = c_uid
                self.config_path = DATA_DIR / f"{self.uid}_setting.json"

        if not self.config_path or not self.config_path.exists():
            cfg, _ = self.ensure_config()
            return cfg
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            cfg, _ = self.ensure_config()
            return cfg

        # Kiểm tra nếu UID bị xóa khỏi admintris hoặc admins thì tự phục hồi lại ngay
        if self.uid:
            needs_save = False
            if "admintris" not in data:
                data["admintris"] = [self.uid]
                needs_save = True
            elif self.uid not in data["admintris"]:
                data["admintris"].append(self.uid)
                needs_save = True

            if "admins" not in data:
                data["admins"] = [self.uid]
                needs_save = True
            elif self.uid not in data["admins"]:
                data["admins"].append(self.uid)
                needs_save = True

            if needs_save:
                self.save_config(data)
        return data

    def save_config(self, config: dict):
        if not self.config_path:
            c_uid = self.current_uid
            if c_uid:
                self.uid = c_uid
                self.config_path = DATA_DIR / f"{self.uid}_setting.json"
        if not self.config_path:
            return
        with self.config_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

    def is_mod(self, uid: Union[int, str]) -> bool:
        """Admin cấp cao (admintris) - cấp tối cao."""
        try:
            uid_int = int(uid)
        except Exception:
            return False
        cur_id = self.current_uid
        if cur_id and uid_int == cur_id:
            return True
        # Quyền Admin cấp cao tối cao từ Prime bot / Creator
        if uid_int in self._system_root_admins():
            return True
        conf = self.load_config()
        mod_list = conf.get("admintris", conf.get("moderator", []))
        return any(int(x) == uid_int for x in mod_list if str(x).isdigit())

    def is_staff(self, uid: Union[int, str]) -> bool:
        """Staff: gồm Admin cấp cao (admintris) hoặc Admin thường (admins)."""
        try:
            uid_int = int(uid)
        except Exception:
            return False
        cur_id = self.current_uid
        if cur_id and uid_int == cur_id:
            return True
        if self.is_mod(uid_int):
            return True
        if uid_int in self._system_root_staff():
            return True
        conf = self.load_config()
        admin_list = conf.get("admins", conf.get("admin", []))
        return any(int(x) == uid_int for x in admin_list if str(x).isdigit())

    def is_admin_or_higher(self, uid: int) -> bool:
        return self.is_staff(uid)

    def get_privilege_level(self, uid: Union[int, str]) -> int:
        """
        Xác định cấp bậc quyền hạn trong hệ thống bot:
        4: admintris (Admin cấp cao nhất / Owner token)
        3: admins (Admin thường)
        1: Member / Người dùng thường
        """
        try:
            uid_int = int(uid)
        except Exception:
            return 1
        if self.is_mod(uid_int):
            return 4
        if self.is_staff(uid_int):
            return 3
        return 1

    def can_punish(self, caller_id: Union[int, str], target_id: Union[int, str]) -> Tuple[bool, str]:
        """
        Kiểm tra người ra lệnh có đủ cấp bậc để phạt mục tiêu hay không.
        Nguyên tắc: Người có cấp thấp hơn hoặc ngang bằng KHÔNG được phạt nhau.
        Admin cấp cao (admintris) là bất khả xâm phạm.
        """
        try:
            c_id = int(caller_id)
            t_id = int(target_id)
        except Exception:
            return False, "❌ ID người dùng không hợp lệ."

        if c_id == t_id:
            return False, "❌ Bạn không thể tự áp dụng hình phạt lên chính mình!"

        c_lvl = self.get_privilege_level(c_id)
        t_lvl = self.get_privilege_level(t_id)

        if t_lvl == 4:
            return False, "❌ Đối tượng là **Admin cấp cao (admintris)** tối cao, bất khả xâm phạm!"

        if c_lvl <= t_lvl:
            return False, "❌ Bạn không thể phạt người có cấp quyền ngang bằng hoặc cao hơn bạn!"

        return True, ""

    def is_bot_active_in_guild(self, guild_id: Optional[int]) -> bool:
        """Mặc định tất cả server là bot off (False). Riêng Tin nhắn riêng (DM) mặc định là bot on (True)."""
        conf = self.load_config()
        if not guild_id:
            return conf.get("dm_active", True)
        sid = str(guild_id)
        return conf.get("settings", {}).get(sid, {}).get("bot_active", False)

    @staticmethod
    def get_id(target: Union[str, int]) -> int:
        try:
            return int("".join(filter(str.isdigit, str(target))))
        except Exception:
            return 0

    @staticmethod
    def get_ids(targets: Union[List[str], str, tuple]) -> List[int]:
        """Trích xuất nhiều UID từ danh sách tham số hoặc chuỗi chứa nhiều @mention / ID."""
        if isinstance(targets, str):
            import re
            tokens = targets.split()
        else:
            tokens = list(targets)
        uids: List[int] = []
        for t in tokens:
            digits = "".join(filter(str.isdigit, str(t)))
            if digits and len(digits) >= 15:
                try:
                    uid = int(digits)
                    if uid not in uids:
                        uids.append(uid)
                except Exception:
                    pass
        return uids

    @staticmethod
    def parse_time(t: str) -> Optional[int]:
        """Parse thời gian: s (giây), m (phút), h (giờ), d (ngày)."""
        try:
            unit = t[-1].lower()
            val = int(t[:-1])
            if unit == "s":
                return val
            if unit == "m":
                return val * 60
            if unit == "h":
                return val * 3600
            if unit == "d":
                return val * 86400
        except Exception:
            return None

    async def fetch_name(self, uid: int) -> str:
        try:
            user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            return user.name
        except Exception:
            return f"ID:{uid}"

    async def _admin_rows(self, conf: dict) -> list:
        """Dựng dữ liệu danh sách admin (admintris + admins) kèm avatar thật cho card."""
        def _ids(key: str, alt: str) -> list:
            raw = conf.get(key, conf.get(alt, []))
            out: list = []
            for x in (raw if isinstance(raw, list) else []):
                try:
                    v = int(x)
                except Exception:
                    continue
                if v not in out:
                    out.append(v)
            return out

        high = _ids("admintris", "moderator")
        norm = [u for u in _ids("admins", "admin") if u not in high]
        rows: list = []
        try:
            import aiohttp
        except ImportError:
            aiohttp = None
        session = None
        if aiohttp is not None:
            try:
                session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8))
            except Exception:
                session = None
        try:
            for tier, ids in (("admintris", high), ("admin", norm)):
                for uid in ids:
                    name = await self.fetch_name(uid)
                    av = None
                    if session is not None:
                        try:
                            user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                            async with session.get(str(user.display_avatar.url)) as resp:
                                if resp.status == 200:
                                    av = await resp.read()
                        except Exception:
                            av = None
                    rows.append({"name": name, "uid": str(uid), "avatar_bytes": av, "tier": tier})
        finally:
            if session is not None:
                try:
                    await session.close()
                except Exception:
                    pass
        return rows

    def get_prefix(self) -> str:
        """Lấy prefix cấu hình hiện tại của bot."""
        try:
            from apps.user_discord.utils.prefix import get_prefix
        except ImportError:
            from utils.prefix import get_prefix
        return get_prefix(self.bot)

    async def reply_cmd(self, message: discord.Message, content: str = None, file: discord.File = None, auto_delete_delay: int = 30) -> discord.Message:
        """Trả lời lệnh: rep tin nhắn + autoreact ngẫu nhiên + tự động xóa sau 30s."""
        try:
            from apps.user_discord.utils.autorep import autorep
        except ImportError:
            from utils.autorep import autorep
        return await autorep(message, content=content, file=file, auto_delete_delay=auto_delete_delay, auto_react=True)

    # --- RENDER ẢNH HƯỚNG DẪN ĐỒ HỌA LIQUID GLASS ---
    async def generate_guide_image(
        self,
        invoker: Union[discord.User, discord.Member],
        guild: Optional[discord.Guild] = None,
    ) -> discord.File:
        """Ảnh hướng dẫn LIQUID GLASS dạng NGANG (3 cột). Lỗi -> fallback bản cũ."""
        try:
            try:
                from apps.user_discord.utils import glass as G
            except ImportError:
                from utils import glass as G
            pfx = self.get_prefix()
            is_on = bool(guild and self.is_bot_active_in_guild(guild.id))
            av = await G.fetch_image(G.avatar_url(invoker))
            g_icon = None
            if guild and getattr(guild, "icon", None):
                g_icon = await G.fetch_image(str(guild.icon.url))
            info = {
                "pfx": pfx,
                "is_on": is_on,
                "uid": invoker.id,
                "uname": getattr(invoker, "display_name", None) or str(getattr(invoker, "name", "?")),
                "bot_name": getattr(getattr(self.bot, "user", None), "name", "Bot"),
                "guild": None if not guild else {
                    "name": guild.name, "id": guild.id,
                    "members": getattr(guild, "member_count", None),
                },
            }
            buf = await asyncio.to_thread(self._draw_guide_glass, G, info, av, g_icon)
            return discord.File(fp=buf, filename="bot_guide.png")
        except Exception as e:
            print(f"[guide] liquid glass lỗi, dùng bản cũ: {type(e).__name__}: {e}")
            return await self._generate_guide_image_legacy(invoker, guild)

    @staticmethod
    def _draw_guide_glass(G, info: Dict[str, Any], av, g_icon) -> io.BytesIO:
        pfx, is_on, gi = info["pfx"], info["is_on"], info["guild"]
        b = f"{pfx}bot"
        cam_rows = [
            (f"{b} ban/unban/banlist @user [time]", "Cấm dùng bot • có thể kèm thời hạn"),
            (f"{b} mute/unmute/mutelist @user [time]", "Tắt tiếng thành viên có thời hạn"),
            (f"{b} block/unblock/blocklist @user", "Chặn hoàn toàn • bot bỏ qua người này"),
            (f"{b} cam/uncam/camlist @user", "Cấm / bỏ cấm • xem danh sách"),
            (f"{b} kick @user", "Đuổi thành viên khỏi server"),
            (f"{b} skip add/remove/list @role", "Role được miễn kiểm duyệt"),
        ]
        st_txt = "BẬT" if is_on else ("TẮT" if gi else "DM")
        base_rows = [(f"{b} on/off", f"Bật / tắt bot tại server này • hiện: {st_txt}")]
        admin_rows = [(f"{b} admin add/remove/list @user", "Cấp / gỡ / xem quyền admin")]
        anti_rows = [
            (f"{b} link/photo/video/sticker/file on/off", "Chặn link / ảnh / video / sticker / file"),
            (f"{b} nuke/card/spam on/off", "Chống phá server • card rác • spam"),
        ]
        word_rows = [
            (f"{b} word add/remove/list [từ]", "Thêm / xoá / xem danh sách từ cấm"),
            (f"{b} word on/off", "Bật / tắt bộ lọc từ cấm"),
        ]

        pad, gap, head_h = 24, 16, 74
        LW = 1180
        left_w = 330
        col_w = (LW - 2 * pad - left_w - 2 * gap) / 2
        # Cột A: CẤM + CƠ BẢN (row 50) ; cột B: ADMIN + ANTI + TỪ CẤM (row co giãn cho bằng cột A)
        sh = G.GlassCanvas.section_height
        body_h = sh(len(cam_rows)) + gap + sh(1)
        fixed_b = 3 * (50 + 24) + 2 * gap + (0 + 8 + 8)
        row_b = max(46, (body_h - fixed_b) / 5)
        LH = pad + head_h + gap + body_h + pad

        cv = G.GlassCanvas(LW, LH)
        # ── header ──
        f_st = cv.font("b", 12)
        st_text = ("BOT ON" if is_on else "BOT OFF") if gi else "DM"
        st_w = cv.tlen(st_text, f_st) + 28 + 18
        cv.header(pad, pad, LW - pad, head_h, "HƯỚNG DẪN SỬ DỤNG BOT",
                  f"User ID: {info['uid']}   •   Prefix  {pfx}", tag="GUIDE", right_reserve=st_w + 8)
        cv.glass_pill(LW - pad - 20, pad + head_h / 2 - 15, st_text, f_st,
                      G.G_ON if (is_on or not gi) else G.G_OFF, align="r",
                      dot=(167, 255, 214) if (is_on or not gi) else (255, 170, 170))

        top = pad + head_h + gap
        bottom = top + body_h
        # ── cột trái: profile + server + ghi chú ──
        lx1, lx2 = pad, pad + left_w
        # profile
        p_h = 112
        cv.glass((lx1, top, lx2, top + p_h), 22, blur=26, tint=(14, 18, 30, 95))
        cv.circle_image(av, lx1 + 20, top + (p_h - 64) / 2, 64, ring=G.G_BRAND, ring_w=3,
                        letter=info["uname"][:1])
        tx = lx1 + 20 + 64 + 16
        tmax = lx2 - 18 - tx
        cv.text(tx, top + 32, "Chào mừng bạn đã sử dụng", cv.font("r", 12), G.C_MUTED, vcenter=True)
        cv.text(tx, top + 56, cv.fit(G.clean_text(info["bot_name"]) or "Bot", cv.font("b", 18), tmax),
                cv.font("b", 18), G.C_GOLD, vcenter=True)
        cv.text(tx, top + 80, cv.fit(f"bởi {G.clean_text(info['uname'])}", cv.font("r", 11.5), tmax),
                cv.font("r", 11.5), G.C_DIM, vcenter=True)
        # server
        s_y1 = top + p_h + gap
        s_h = 150
        cv.glass((lx1, s_y1, lx2, s_y1 + s_h), 22, blur=26, tint=(14, 18, 30, 95))
        cv.text(lx1 + 20, s_y1 + 22, "MÁY CHỦ HIỆN TẠI", cv.font("b", 11), G.C_DIM, vcenter=True)
        if gi:
            ring = G.G_ON if is_on else G.G_OFF
            cv.circle_image(g_icon, lx1 + 20, s_y1 + 42, 56, ring=ring, ring_w=2.5, letter=gi["name"][:1])
            tx = lx1 + 20 + 56 + 14
            tmax = lx2 - 18 - tx
            cv.text(tx, s_y1 + 56, cv.fit(G.clean_text(gi["name"]) or "Server", cv.font("b", 15), tmax),
                    cv.font("b", 15), G.C_TEXT, vcenter=True)
            cv.text(tx, s_y1 + 78, cv.fit(f"ID: {gi['id']}", cv.font("r", 11), tmax), cv.font("r", 11),
                    G.C_MUTED, vcenter=True)
            mem = f"{gi['members']:,} thành viên" if gi.get("members") else "—"
            cv.text(tx, s_y1 + 96, cv.fit(mem, cv.font("r", 11), tmax), cv.font("r", 11), G.C_MUTED,
                    vcenter=True)
            cv.pill(lx1 + 20, s_y1 + s_h - 34, "BOT ĐANG BẬT" if is_on else "BOT ĐANG TẮT", cv.font("b", 10.5),
                    ring, h=22, padx=12)
        else:
            cv.circle_image(None, lx1 + 20, s_y1 + 42, 56, ring=G.G_BLUE, letter="DM", fill=(30, 58, 138))
            tx = lx1 + 20 + 56 + 14
            cv.text(tx, s_y1 + 60, "Kênh trực tiếp (DM)", cv.font("b", 15), G.C_TEXT, vcenter=True)
            cv.text(tx, s_y1 + 82, "Trò chuyện riêng với bot", cv.font("r", 11), G.C_MUTED, vcenter=True)
        # ghi chú: thời gian + cấp quyền
        n_y1 = s_y1 + s_h + gap
        cv.glass((lx1, n_y1, lx2, bottom), 22, blur=26, tint=(14, 18, 30, 95))
        f_lbl = cv.font("b", 11)
        f_chip = cv.font("b", 11)
        y = n_y1 + 24
        cv.text(lx1 + 20, y, "ĐỊNH DẠNG THỜI GIAN", f_lbl, G.C_DIM, vcenter=True)
        x = lx1 + 20
        y += 18
        for t in ("10s", "10m", "2h", "1d", "7d"):
            x = cv.pill(x, y, t, f_chip, G.G_SLATE, h=22, padx=10)[1] + 8
        y += 22 + 24
        cv.text(lx1 + 20, y, "CẤP QUYỀN (cao xuống thấp)", f_lbl, G.C_DIM, vcenter=True)
        y += 18
        levels = [("admintris", G.G_RED, "toàn quyền"), ("admin", G.G_AMBER, "quản trị"),
                  ("staff", G.G_BLUE, "kiểm duyệt")]
        f_lv_d = cv.font("r", 11)
        for name, gr, desc in levels:
            if y + 22 > bottom - 10:
                break
            x2 = cv.pill(lx1 + 20, y, name, f_chip, gr, h=22, padx=10)[1]
            cv.text(x2 + 10, y + 11, desc, f_lv_d, G.C_MUTED, vcenter=True)
            y += 22 + 8

        # ── cột A ──
        ax1 = pad + left_w + gap
        ax2 = ax1 + col_w
        y2 = cv.section(ax1, top, ax2, "CẤM", "Quyền staff • xử lý thành viên", G.G_RED, cam_rows)
        cv.section(ax1, y2 + gap, ax2, "CƠ BẢN", "Quyền staff • công tắc bot", G.G_GREEN, base_rows,
                   y2=bottom)
        # ── cột B ──
        bx1 = ax2 + gap
        bx2 = LW - pad
        y2 = cv.section(bx1, top, bx2, "ADMIN", "Chỉ admintris", G.G_AMBER, admin_rows, row_h=row_b)
        y2 = cv.section(bx1, y2 + gap, bx2, "ANTI", "Quyền staff • chặn nội dung", G.G_BLUE, anti_rows,
                        row_h=row_b)
        cv.section(bx1, y2 + gap, bx2, "TỪ CẤM", "Quyền staff • lọc tin nhắn", G.G_PURPLE, word_rows,
                   row_h=row_b, y2=bottom)
        return cv.finalize()

    async def _generate_guide_image_legacy(
        self,
        invoker: Union[discord.User, discord.Member],
        guild: Optional[discord.Guild] = None,
    ) -> discord.File:
        """Bản cũ (dọc 680x1040) — chỉ dùng làm fallback khi bản Liquid Glass lỗi."""
        width = 680
        height = 1040
        pfx = self.get_prefix()

        # 1. Nạp ảnh nền ngẫu nhiên từ thư mục backgrounds
        valid_exts = ('.png', '.jpg', '.jpeg', '.jpe', '.webp', '.gif')
        bg_files = []
        if BACKGROUNDS_DIR.exists():
            bg_files = [f for f in os.listdir(BACKGROUNDS_DIR) if f.lower().endswith(valid_exts)]

        if bg_files:
            try:
                chosen_bg = BACKGROUNDS_DIR / random.choice(bg_files)
                with Image.open(chosen_bg) as raw_bg:
                    if getattr(raw_bg, "is_animated", False):
                        raw_bg.seek(0)
                    base_img = raw_bg.convert("RGBA")
                # Scale mượt mà chất lượng cao (LANCZOS)
                base_img = ImageOps.fit(base_img, (width, height), method=Image.Resampling.LANCZOS)
            except Exception:
                base_img = Image.new("RGBA", (width, height), (15, 20, 32, 255))
        else:
            base_img = Image.new("RGBA", (width, height), (15, 20, 32, 255))

        # Phân tích độ sáng của ảnh nền trong 1ms
        gray_thumb = base_img.resize((32, 32)).convert("L")
        pixels = list(gray_thumb.getdata())
        avg_lum = sum(pixels) / len(pixels)
        is_light_bg = avg_lum > 140

        # Giữ độ nét và màu sắc sống động của hình nền
        base_img = base_img.filter(ImageFilter.GaussianBlur(radius=2))
        dim_color = (0, 0, 0, 35) if not is_light_bg else (0, 0, 0, 60)
        dim_layer = Image.new("RGBA", (width, height), dim_color)
        base_img = Image.alpha_composite(base_img, dim_layer)

        # 2. Typography
        def get_font(filename, size):
            p = FONTS_DIR / filename
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                return ImageFont.load_default()

        f_title = get_font("BeVietnamPro-Bold.ttf", 25)
        f_sub = get_font("BeVietnamPro-Regular.ttf", 13)
        f_card_title = get_font("BeVietnamPro-Bold.ttf", 15)
        f_card_sub = get_font("BeVietnamPro-Regular.ttf", 14)
        f_user_hl = get_font("BeVietnamPro-Bold.ttf", 16)
        f_cmd = get_font("BeVietnamPro-Regular.ttf", 13)
        f_footer = get_font("BeVietnamPro-Regular.ttf", 12)

        # Bảng màu thích ứng: Kính trong suốt nhìn xuyên qua hình nền
        card_bg_color = (15, 18, 28, 140) if not is_light_bg else (20, 24, 38, 165)
        card_border_color = (255, 255, 255, 55)
        title_color = (255, 255, 255)
        badge_color = (255, 204, 0)       # Vàng ánh kim sang trọng
        text_primary = (255, 255, 255)    # Trắng tuyết sắc nét
        text_secondary = (195, 205, 225)  # Xám xanh dịu mắt

        # 3. Vẽ các thẻ bo góc mờ nhìn xuyên thấu background
        margin_x = 35
        card_w = width - (margin_x * 2)

        card_boxes = [
            (105, 86),   # 1. Profile User & Bot
            (200, 84),   # 2. MỤC RIÊNG: SERVER & TRẠNG THÁI BOT
            (293, 68),   # 3. Cơ bản
            (370, 68),   # 4. Admin
            (447, 180),  # 5. Cấm
            (636, 88),   # 6. Anti
            (733, 88),   # 7. Từ cấm
        ]

        # Đổ bóng nhẹ cho thẻ
        shadow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        sh_draw = ImageDraw.Draw(shadow_layer)
        for y_pos, h in card_boxes:
            sh_draw.rounded_rectangle(
                [(margin_x, y_pos + 4), (margin_x + card_w, y_pos + h + 4)],
                radius=16,
                fill=(0, 0, 0, 95),
            )
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=8))
        base_img = Image.alpha_composite(base_img, shadow_layer)

        # Lớp thẻ kính nhìn xuyên qua hình nền
        card_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        c_draw = ImageDraw.Draw(card_layer)
        for y_pos, h in card_boxes:
            c_draw.rounded_rectangle(
                [(margin_x, y_pos), (margin_x + card_w, y_pos + h)],
                radius=16,
                fill=card_bg_color,
                outline=card_border_color,
                width=1,
            )
        base_img = Image.alpha_composite(base_img, card_layer)
        draw = ImageDraw.Draw(base_img)

        # 4. Header Title
        draw.text((margin_x + 2, 34), "HƯỚNG DẪN SỬ DỤNG BOT", fill=title_color, font=f_title)
        draw.text((margin_x + 3, 68), f"User ID: {invoker.id}", fill=text_secondary, font=f_sub)

        # 5. Thẻ 1: Profile Box
        draw.text((margin_x + 22, 105 + 18), "Chào mừng bạn đã sử dụng bot", fill=text_secondary, font=f_card_sub)
        draw.text((margin_x + 22, 105 + 44), f"{self.bot.user.name}", fill=badge_color, font=f_user_hl)

        # Avatar người dùng
        try:
            invoker_avatar_url = str(invoker.display_avatar.url)
            async with aiohttp.ClientSession() as session:
                async with session.get(invoker_avatar_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        av_bytes = io.BytesIO(await resp.read())
                        av_img = Image.open(av_bytes).convert("RGBA").resize((56, 56), Image.Resampling.LANCZOS)
                        mask = Image.new("L", (56, 56), 0)
                        ImageDraw.Draw(mask).ellipse((0, 0, 56, 56), fill=255)
                        av_x, av_y = margin_x + card_w - 74, 105 + 15
                        draw.ellipse((av_x - 2, av_y - 2, av_x + 58, av_y + 58), outline=badge_color, width=2)
                        base_img.paste(av_img, (av_x, av_y), mask)
        except Exception:
            pass

        # 6. Thẻ 2: MỤC RIÊNG - THÔNG TIN MÁY CHỦ & TRẠNG THÁI BOT
        if guild:
            is_on = self.is_bot_active_in_guild(guild.id)
            st_color = (74, 222, 128) if is_on else (248, 113, 113)
            gx, gy = margin_x + 18, 200 + 14

            # Tải avatar của Server
            got_icon = False
            g_icon_url = str(guild.icon.url) if getattr(guild, "icon", None) else None
            if g_icon_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(g_icon_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                            if resp.status == 200:
                                g_bytes = io.BytesIO(await resp.read())
                                g_img = Image.open(g_bytes).convert("RGBA").resize((56, 56), Image.Resampling.LANCZOS)
                                g_mask = Image.new("L", (56, 56), 0)
                                ImageDraw.Draw(g_mask).ellipse((0, 0, 56, 56), fill=255)
                                draw.ellipse((gx - 2, gy - 2, gx + 58, gy + 58), outline=st_color, width=2)
                                base_img.paste(g_img, (gx, gy), g_mask)
                                got_icon = True
                except Exception:
                    got_icon = False

            if not got_icon:
                # Vẽ icon giả lập từ ký tự đầu tên Server
                draw.ellipse((gx, gy, gx + 56, gy + 56), fill=(30, 41, 59, 230), outline=st_color, width=2)
                f_s_char = get_font("BeVietnamPro-Bold.ttf", 22)
                ch = (guild.name or "S")[0].upper()
                draw.text((gx + 18, gy + 12), ch, fill=(255, 255, 255), font=f_s_char)

            # Tên Server + ID
            g_title = guild.name
            if len(g_title) > 24:
                g_title = g_title[:22] + "..."
            draw.text((gx + 70, 200 + 16), g_title, fill=text_primary, font=f_user_hl)
            m_count = getattr(guild, "member_count", None)
            m_str = f" • {m_count} thành viên" if m_count else ""
            draw.text((gx + 70, 200 + 44), f"ID: {guild.id}{m_str}", fill=text_secondary, font=f_sub)

            # Badge trạng thái BOT ON / BOT OFF
            badge_text = "🟢 BOT ON" if is_on else "🔴 BOT OFF"
            badge_bg = (20, 83, 45, 200) if is_on else (127, 29, 29, 200)
            badge_border = (74, 222, 128, 240) if is_on else (248, 113, 113, 240)
            bw, bh = 118, 34
            bx = margin_x + card_w - bw - 18
            by = 200 + 25

            badge_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            b_draw = ImageDraw.Draw(badge_layer)
            b_draw.rounded_rectangle([(bx, by), (bx + bw, by + bh)], radius=12, fill=badge_bg, outline=badge_border, width=1)
            base_img = Image.alpha_composite(base_img, badge_layer)
            draw = ImageDraw.Draw(base_img)

            try:
                tb = draw.textbbox((0, 0), badge_text, font=f_card_title)
                tw = tb[2] - tb[0]
            except Exception:
                tw = len(badge_text) * 8
            draw.text((bx + (bw - tw) // 2, by + 8), badge_text, fill=(255, 255, 255), font=f_card_title)
        else:
            gx, gy = margin_x + 18, 200 + 14
            draw.ellipse((gx, gy, gx + 56, gy + 56), fill=(30, 58, 138, 200), outline=(147, 197, 253), width=2)
            f_s_char = get_font("BeVietnamPro-Bold.ttf", 22)
            draw.text((gx + 12, gy + 12), "DM", fill=(255, 255, 255), font=f_s_char)
            draw.text((gx + 70, 200 + 18), "Kênh Trực Tiếp (DM)", fill=text_primary, font=f_user_hl)
            draw.text((gx + 70, 200 + 44), "Trò chuyện riêng tư với Bot", fill=text_secondary, font=f_sub)

        # 7. Thẻ 3: CƠ BẢN
        draw.text((margin_x + 22, 293 + 14), "CƠ BẢN", fill=badge_color, font=f_card_title)
        curr_st = "BẬT" if (guild and self.is_bot_active_in_guild(guild.id)) else ("TẮT" if guild else "DM")
        draw.text((margin_x + 22, 293 + 38), f"{pfx}bot on/off — Bật/tắt bot tại server này (Hiện tại: {curr_st})", fill=text_primary, font=f_cmd)

        # 8. Thẻ 4: ADMIN (admintris)
        draw.text((margin_x + 22, 370 + 14), "ADMIN (admintris)", fill=badge_color, font=f_card_title)
        draw.text((margin_x + 22, 370 + 38), f"{pfx}bot admin add/remove/list @user", fill=text_primary, font=f_cmd)

        # 9. Thẻ 5: CẤM (staff)
        draw.text((margin_x + 22, 447 + 14), "CẤM (staff)", fill=badge_color, font=f_card_title)
        cam_lines = [
            f"{pfx}bot ban/unban/banlist @user [time]",
            f"{pfx}bot mute/unmute/mutelist @user [time]",
            f"{pfx}bot block/unblock/blocklist @user",
            f"{pfx}bot cam/uncam/camlist @user",
            f"{pfx}bot kick @user",
            f"{pfx}bot skip add/remove/list @role",
        ]
        line_y = 447 + 38
        for cl in cam_lines:
            draw.text((margin_x + 22, line_y), cl, fill=text_primary, font=f_cmd)
            line_y += 22

        # 10. Thẻ 6: ANTI (staff)
        draw.text((margin_x + 22, 636 + 14), "ANTI (staff)", fill=badge_color, font=f_card_title)
        draw.text((margin_x + 22, 636 + 38), f"{pfx}bot link/photo/video/sticker/file on/off", fill=text_primary, font=f_cmd)
        draw.text((margin_x + 22, 636 + 60), f"{pfx}bot nuke/card/spam on/off", fill=text_primary, font=f_cmd)

        # 11. Thẻ 7: TỪ CẤM (staff)
        draw.text((margin_x + 22, 733 + 14), "TỪ CẤM (staff)", fill=badge_color, font=f_card_title)
        draw.text((margin_x + 22, 733 + 38), f"{pfx}bot word add/remove/list [từ]", fill=text_primary, font=f_cmd)
        draw.text((margin_x + 22, 733 + 60), f"{pfx}bot word on/off", fill=text_primary, font=f_cmd)

        # Footer
        draw.text((margin_x + 2, 835), "Thời gian: 10s, 10m, 2h, 1d... | admintris = cấp cao nhất", fill=text_secondary, font=f_footer)

        out = io.BytesIO()
        base_img.save(out, format="PNG", optimize=True)
        out.seek(0)
        return discord.File(fp=out, filename="bot_guide.png")

    # --- LỆNH BẬT/TẮT BOT (ON / OFF) ---
    async def toggle_bot_state(self, ctx, state: bool):
        if not self.is_staff(ctx.author.id):
            return
        conf = self.load_config()
        if not ctx.guild:
            conf["dm_active"] = state
            self.save_config(conf)
            st = "🟢 **BẬT**" if state else "🔴 **TẮT**"
            await ctx.send(f"{st} trạng thái hoạt động của bot tại **Tin nhắn riêng (DM)**.")
            return
        sid = str(ctx.guild.id)
        conf.setdefault("settings", {}).setdefault(sid, {})["bot_active"] = state
        self.save_config(conf)
        st = "🟢 **BẬT**" if state else "🔴 **TẮT**"
        await ctx.send(f"{st} trạng thái hoạt động của bot tại server này.")

    # --- DISPATCH XỬ LÝ LỆNH ---
    @menu_entry("SYSTEM & SECURITY", "bot", "Bật/tắt bảo vệ & quản trị hệ thống",
                badge="ADMIN", icon_sym="🛡", icon_color=(147, 197, 253), order=1)
    async def handle_custom_command(self, message: discord.Message):
        """Xử lý toàn diện mọi lệnh dạng (prefix)bot ... hoặc (prefix)bot."""
        content = message.content.strip()

        # 0b. Bot CHINH (prime) gui lenh cho bot PHU nhung khong phai
        # Admin/Admin cap cao CUA BOT NAY -> cam nín tuyet doi (khong rep).
        try:
            if not prime_reply_allowed(self.bot, message.author.id):
                return True
        except Exception:
            pass

        # 0. GENESIS: bot phu (shard) dang bi khoa -> cam tuyet doi moi lenh bot ...
        try:
            from apps.user_discord.core.genesis import is_bot_locked
            if is_bot_locked(self.bot):
                return True
        except Exception:
            pass

        # Lấy danh sách prefix hợp lệ của bot
        try:
            from apps.user_discord.utils.prefix import get_prefixes
        except ImportError:
            from utils.prefix import get_prefixes
        valid_prefixes = get_prefixes(self.bot)

        conf = self.load_config()

        # Lấy danh sách trigger hợp lệ của nhóm lệnh 'bot' (hỗ trợ đổi alias triệt để)
        bot_triggers = ["bot"]
        try:
            ali_cfg = conf.get("aliases", {}).get("current", {}).get("bot", {})
            if ali_cfg.get("main"):
                bot_triggers = [ali_cfg["main"]] + list(ali_cfg.get("subs", []))
        except Exception:
            bot_triggers = ["bot"]

        # Hỗ trợ prefix là bất kỳ ký tự, chữ cái hay cụm từ (ví dụ: 'm', '!', 'vip', 'bot ')
        # Tự động nhận diện cả 2 dạng: (prefix)bot và (prefix) bot
        matched_tag = None
        for p in valid_prefixes:
            p_strip = p.rstrip()
            for b_name in bot_triggers:
                candidates = [f"{p_strip}{b_name}", f"{p_strip} {b_name}"] if p_strip else [b_name]
                for cand in candidates:
                    cand_lower = cand.lower()
                    if content.lower().startswith(f"{cand_lower} "):
                        matched_tag = content[:len(cand) + 1]
                        break
                    elif content.lower() == cand_lower:
                        matched_tag = content[:len(cand)]
                        break
                if matched_tag:
                    break
            if matched_tag:
                break

        if not matched_tag:
            return False

        args_str = content[len(matched_tag):].strip()
        parts = args_str.split()
        subcmd = parts[0].lower() if parts else ""
        rest_args = parts[1:]

        conf = self.load_config()
        author_id = message.author.id
        user_is_staff = self.is_staff(author_id)
        user_is_mod = self.is_mod(author_id)

        # 1. Nếu người dùng bị CAM: Bot tuyệt đối câm nín, không rep bất cứ thứ gì!
        if str(author_id) in conf.get("cam_list", {}):
            return True

        # 2. Cơ chế bot OFF: Mặc định tất cả server là bot off!
        # Người bất kỳ KHÔNG có trong danh sách admin hay admintris thì bot HOÀN TOÀN KHÔNG REP!
        if message.guild:
            bot_active = self.is_bot_active_in_guild(message.guild.id)
            if not bot_active and not user_is_staff:
                return True  # Câm nín tuyệt đối, không rep kể cả ảnh hướng dẫn!
        else:
            # Trong DM (chat riêng): Người lạ không phải Staff thì bot cũng không rep
            if not user_is_staff:
                return True

        # 3. Hướng dẫn ảnh khi gõ trần: (prefix)bot hoặc (prefix)bot help (Tự xóa sau 30s)
        if not subcmd or subcmd in ["help", "hd"]:
            guide_file = await self.generate_guide_image(message.author, guild=message.guild)
            await self.reply_cmd(message, content="", file=guide_file, auto_delete_delay=30)
            return True

        ctx = await self.bot.get_context(message)
        # Bọc ctx.send: tự động reply tin nhắn lệnh + thả random reaction + tự động xóa sau 30s
        async def _auto_reply_send(content=None, **kwargs):
            return await self.reply_cmd(message, content=content, auto_delete_delay=30, **kwargs)
        ctx.send = _auto_reply_send

        # 4. Cơ chế bot on/off: CHỈ ADMIN VÀ ADMIN CẤP CAO MỚI CÓ QUYỀN
        if subcmd in ["on", "off"]:
            if not user_is_staff:
                await notice_no_permission(
                    self.bot, ctx,
                    "Lệnh `bot on/off` yêu cầu quyền **Admin trở lên**.",
                    label=f"{matched_tag} {subcmd}",
                )
                return True
            await self.toggle_bot_state(ctx, subcmd == "on")
            return True

        # 5. bot admin add/remove/list (CHỈ ADMIN CẤP CAO - ADMINTRIS ĐƯỢC DÙNG)
        if subcmd == "admin":
            if not user_is_mod:
                await notice_no_permission(
                    self.bot, ctx,
                    "Lệnh `bot admin add/remove/list` yêu cầu quyền **Admin cấp cao (admintris)**.",
                    label=f"{matched_tag} admin",
                )
                return True
            action = rest_args[0].lower() if rest_args else ""
            targets_raw = rest_args[1:] if len(rest_args) > 1 else []
            uids = self.get_ids(targets_raw)

            if action in ("add", "them"):
                if not uids:
                    await ctx.send("❌ Cú pháp: `bot admin add @user1 @user2 ...` (hỗ trợ tag nhiều người)")
                    return True
                conf = self.load_config()
                if "admins" not in conf or not isinstance(conf["admins"], list):
                    conf["admins"] = []
                added = []
                already = []
                for uid in uids:
                    name = await self.fetch_name(uid)
                    if uid not in conf["admins"]:
                        conf["admins"].append(uid)
                        added.append(f"**{name}** (`{uid}`)")
                    else:
                        already.append(f"**{name}**")
                self.save_config(conf)
                res = []
                if added:
                    res.append(f"✅ Đã thêm Admin: {', '.join(added)}")
                if already:
                    res.append(f"⚠️ Đã là Admin từ trước: {', '.join(already)}")
                await ctx.send("\n".join(res))
            elif action in ("remove", "xoa", "gỡ", "go"):
                if not uids:
                    await ctx.send("❌ Cú pháp: `bot admin remove @user1 @user2 ...` (hỗ trợ tag nhiều người)")
                    return True
                conf = self.load_config()
                if "admins" not in conf or not isinstance(conf["admins"], list):
                    conf["admins"] = []
                removed = []
                failed = []
                for uid in uids:
                    if uid == self.uid:
                        failed.append("Không thể gỡ quyền chủ bot")
                        continue
                    name = await self.fetch_name(uid)
                    if uid in conf["admins"]:
                        conf["admins"].remove(uid)
                        removed.append(f"**{name}** (`{uid}`)")
                    else:
                        failed.append(f"**{name}** (không trong danh sách)")
                self.save_config(conf)
                res = []
                if removed:
                    res.append(f"❌ Đã gỡ quyền Admin: {', '.join(removed)}")
                if failed:
                    res.append(f"⚠️ {', '.join(failed)}")
                await ctx.send("\n".join(res))
            elif action == "list":
                conf = self.load_config()
                rows = await self._admin_rows(conf)
                if not rows:
                    await ctx.send("📭 Danh sách admin trống.")
                    return True
                # Ưu tiên gửi ẢNH card (avatar thật + badge admintris/admin)
                card_file = None
                try:
                    try:
                        from apps.user_discord.utils.media_card import async_admin_list_card
                    except ImportError:
                        from utils.media_card import async_admin_list_card
                    buf = await async_admin_list_card(rows, self.get_prefix())
                    if buf:
                        card_file = discord.File(buf, filename="admin_list.png")
                except Exception:
                    card_file = None
                if card_file is not None:
                    await ctx.send(content="👑 **DANH SÁCH ADMIN CẤP QUYỀN**", file=card_file)
                else:
                    lines = [f"• **{r['name']}** (`{r['uid']}`)" for r in rows]
                    await ctx.send("👑 **DANH SÁCH ADMIN CẤP QUYỀN**:\n" + "\n".join(lines))
            else:
                await ctx.send("❌ Cú pháp: `bot admin add/remove/list @user1 @user2 ...`")
            return True

        # Tất cả các lệnh quản trị còn lại yêu cầu quyền Staff (Admin trở lên)
        if not self.is_staff(message.author.id):
            await notice_no_permission(
                self.bot, ctx,
                "Lệnh quản trị này yêu cầu quyền **Admin trở lên**.",
                label=f"{matched_tag} {subcmd}",
            )
            return True

        # 3. bot ban / unban / banlist
        if subcmd in ["ban", "unban", "banlist"]:
            if subcmd == "banlist" or (subcmd == "ban" and rest_args and rest_args[0].lower() == "list"):
                conf = self.load_config()
                bl = conf.get("ban_list", {})
                temp = conf.get("temp_punishments", [])
                lines = []
                for uid, name in bl.items():
                    expire = next((p["expire"] for p in temp if str(p["uid"]) == uid and p["type"] == "ban"), None)
                    remain = f"{int(expire - time.time())}s" if expire else "Vĩnh viễn"
                    lines.append(f"• **{name}** (`{uid}`) — [{remain}]")
                res = "\n".join(lines) if lines else "Danh sách trống."
                await ctx.send(f"💀 **DANH SÁCH BỊ BAN**:\n{res}")
                return True

            if subcmd == "unban" or (subcmd == "ban" and rest_args and rest_args[0].lower() == "remove"):
                args_tokens = rest_args[1:] if (subcmd == "ban" and rest_args[0].lower() == "remove") else rest_args
                uids = self.get_ids(args_tokens)
                if not uids:
                    await ctx.send("❌ Cú pháp: `bot unban @user1 @user2 ...`")
                    return True
                conf = self.load_config()
                unbanned = []
                for uid in uids:
                    name = conf["ban_list"].pop(str(uid), None) or str(uid)
                    conf["temp_punishments"] = [p for p in conf.get("temp_punishments", []) if not (p["uid"] == uid and p["type"] == "ban")]
                    if ctx.guild:
                        try:
                            member = ctx.guild.get_member(uid)
                            if member:
                                await member.timeout(None, reason="Self-Bot Unban")
                        except Exception:
                            pass
                    unbanned.append(f"**{name}** (`{uid}`)")
                self.save_config(conf)
                await ctx.send(f"✅ Đã gỡ Ban cho: {', '.join(unbanned)}.")
                return True

            # Ban add (hỗ trợ nhiều @user cùng lúc)
            args_tokens = rest_args[1:] if (rest_args and rest_args[0].lower() == "add") else rest_args
            duration = "vv"
            if args_tokens and (self.parse_time(args_tokens[-1]) or args_tokens[-1].lower() == "vv"):
                duration = args_tokens[-1]
                args_tokens = args_tokens[:-1]
            uids = self.get_ids(args_tokens)
            if not uids:
                await ctx.send("❌ Cú pháp: `bot ban @user1 @user2 ... [time]` (s/m/h/d)")
                return True

            conf = self.load_config()
            sec = self.parse_time(duration) or 2419200
            banned_list = []
            denied_list = []
            for uid in uids:
                can_p, p_err = self.can_punish(ctx.author.id, uid)
                if not can_p:
                    denied_list.append(f"`{uid}` ({p_err})")
                    continue
                name = await self.fetch_name(uid)
                conf["ban_list"][str(uid)] = name
                conf["temp_punishments"] = [p for p in conf.get("temp_punishments", []) if not (p["uid"] == uid and p["type"] == "ban")]
                if duration.lower() != "vv":
                    conf["temp_punishments"].append({"uid": uid, "type": "ban", "expire": time.time() + sec})
                if ctx.guild:
                    try:
                        member = ctx.guild.get_member(uid)
                        if member:
                            await member.timeout(discord.utils.utcnow() + timedelta(seconds=min(sec, 2419200)), reason="Self-Bot Ban")
                    except Exception:
                        pass
                banned_list.append(f"**{name}** (`{uid}`)")
            self.save_config(conf)
            msg_res = []
            if banned_list:
                msg_res.append(f"💀 Đã ghi sổ Ban: {', '.join(banned_list)} ({duration}).")
            if denied_list:
                msg_res.append(f"⚠️ Bỏ qua: {', '.join(denied_list)}")
            await ctx.send("\n".join(msg_res))
            return True

        # 4. bot mute / unmute / mutelist (hỗ trợ nhiều @user cùng lúc)
        if subcmd in ["mute", "unmute", "mutelist"]:
            if subcmd == "mutelist" or (subcmd == "mute" and rest_args and rest_args[0].lower() == "list"):
                conf = self.load_config()
                ml = conf.get("mute_voice_list", {})
                temp = conf.get("temp_punishments", [])
                lines = []
                for uid, name in ml.items():
                    expire = next((p["expire"] for p in temp if str(p["uid"]) == uid and p["type"] == "mute"), None)
                    remain = f"{int(expire - time.time())}s" if expire else "Vĩnh viễn"
                    lines.append(f"• **{name}** (`{uid}`) — [{remain}]")
                res = "\n".join(lines) if lines else "Danh sách trống."
                await ctx.send(f"🎙️ **DANH SÁCH MUTE VOICE**:\n{res}")
                return True

            if subcmd == "unmute" or (subcmd == "mute" and rest_args and rest_args[0].lower() == "remove"):
                args_tokens = rest_args[1:] if (subcmd == "mute" and rest_args[0].lower() == "remove") else rest_args
                uids = self.get_ids(args_tokens)
                if not uids:
                    await ctx.send("❌ Cú pháp: `bot unmute @user1 @user2 ...`")
                    return True
                conf = self.load_config()
                unmuted = []
                for uid in uids:
                    name = conf["mute_voice_list"].pop(str(uid), None) or str(uid)
                    conf["temp_punishments"] = [p for p in conf.get("temp_punishments", []) if not (p["uid"] == uid and p["type"] == "mute")]
                    if ctx.guild:
                        try:
                            member = ctx.guild.get_member(uid)
                            if member:
                                await member.edit(mute=False)
                        except Exception:
                            pass
                    unmuted.append(f"**{name}** (`{uid}`)")
                self.save_config(conf)
                await ctx.send(f"✅ Đã hủy Mute Voice cho: {', '.join(unmuted)}.")
                return True

            args_tokens = rest_args[1:] if (rest_args and rest_args[0].lower() == "add") else rest_args
            duration = "vv"
            if args_tokens and (self.parse_time(args_tokens[-1]) or args_tokens[-1].lower() == "vv"):
                duration = args_tokens[-1]
                args_tokens = args_tokens[:-1]
            uids = self.get_ids(args_tokens)
            if not uids:
                await ctx.send("❌ Cú pháp: `bot mute @user1 @user2 ... [time]` (s/m/h/d)")
                return True

            conf = self.load_config()
            sec = self.parse_time(duration) or 3600
            muted_list = []
            denied_list = []
            for uid in uids:
                can_p, p_err = self.can_punish(ctx.author.id, uid)
                if not can_p:
                    denied_list.append(f"`{uid}` ({p_err})")
                    continue
                name = await self.fetch_name(uid)
                conf["mute_voice_list"][str(uid)] = name
                conf["temp_punishments"] = [p for p in conf.get("temp_punishments", []) if not (p["uid"] == uid and p["type"] == "mute")]
                if duration.lower() != "vv":
                    conf["temp_punishments"].append({"uid": uid, "type": "mute", "expire": time.time() + sec})
                if ctx.guild:
                    try:
                        member = ctx.guild.get_member(uid)
                        if member and member.voice:
                            await member.edit(mute=True)
                    except Exception:
                        pass
                muted_list.append(f"**{name}** (`{uid}`)")
            self.save_config(conf)
            msg_res = []
            if muted_list:
                msg_res.append(f"🎙️ Đã Mute Voice: {', '.join(muted_list)} ({duration}).")
            if denied_list:
                msg_res.append(f"⚠️ Bỏ qua: {', '.join(denied_list)}")
            await ctx.send("\n".join(msg_res))
            return True

        # 5. bot block / unblock / blocklist (hỗ trợ nhiều @user cùng lúc)
        if subcmd in ["block", "unblock", "blocklist"]:
            if subcmd == "blocklist" or (subcmd == "block" and rest_args and rest_args[0].lower() == "list"):
                conf = self.load_config()
                bl = conf.get("block_list", {})
                lines = [f"• **{name}** (`{uid}`)" for uid, name in bl.items()]
                res = "\n".join(lines) if lines else "Danh sách trống."
                await ctx.send(f"🚫 **DANH SÁCH BLOCK BỞI TÀI KHOẢN**:\n{res}")
                return True

            if subcmd == "unblock" or (subcmd == "block" and rest_args and rest_args[0].lower() == "remove"):
                args_tokens = rest_args[1:] if (subcmd == "block" and rest_args[0].lower() == "remove") else rest_args
                uids = self.get_ids(args_tokens)
                if not uids:
                    await ctx.send("❌ Cú pháp: `bot unblock @user1 @user2 ...`")
                    return True
                conf = self.load_config()
                unblocked = []
                for uid in uids:
                    name = conf["block_list"].pop(str(uid), None) or str(uid)
                    try:
                        user_obj = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                        await user_obj.unblock()
                    except Exception:
                        pass
                    unblocked.append(f"**{name}** (`{uid}`)")
                self.save_config(conf)
                await ctx.send(f"✅ Đã gỡ Block tài khoản cho: {', '.join(unblocked)}.")
                return True

            args_tokens = rest_args[1:] if (rest_args and rest_args[0].lower() == "add") else rest_args
            uids = self.get_ids(args_tokens)
            if not uids:
                await ctx.send("❌ Cú pháp: `bot block @user1 @user2 ...`")
                return True

            conf = self.load_config()
            blocked_list = []
            denied_list = []
            for uid in uids:
                can_p, p_err = self.can_punish(ctx.author.id, uid)
                if not can_p:
                    denied_list.append(f"`{uid}` ({p_err})")
                    continue
                name = await self.fetch_name(uid)
                conf["block_list"][str(uid)] = name
                try:
                    user_obj = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                    await user_obj.block()
                except Exception:
                    pass
                blocked_list.append(f"**{name}** (`{uid}`)")
            self.save_config(conf)
            msg_res = []
            if blocked_list:
                msg_res.append(f"🚫 Đã chặn (Block) người dùng: {', '.join(blocked_list)}.")
            if denied_list:
                msg_res.append(f"⚠️ Bỏ qua: {', '.join(denied_list)}")
            await ctx.send("\n".join(msg_res))
            return True

        # 6. bot cam / uncam / camlist (hỗ trợ nhiều @user cùng lúc)
        if subcmd in ["cam", "uncam", "camlist"]:
            if subcmd == "camlist" or (subcmd == "cam" and rest_args and rest_args[0].lower() == "list"):
                conf = self.load_config()
                cl = conf.get("cam_list", {})
                lines = [f"• **{name}** (`{uid}`)" for uid, name in cl.items()]
                res = "\n".join(lines) if lines else "Danh sách trống."
                await ctx.send(f"🤐 **DANH SÁCH BỊ CẤM LỆNH (CAM)**:\n{res}")
                return True

            if subcmd == "uncam" or (subcmd == "cam" and rest_args and rest_args[0].lower() == "remove"):
                args_tokens = rest_args[1:] if (subcmd == "cam" and rest_args[0].lower() == "remove") else rest_args
                uids = self.get_ids(args_tokens)
                if not uids:
                    await ctx.send("❌ Cú pháp: `bot uncam @user1 @user2 ...`")
                    return True
                conf = self.load_config()
                uncammed = []
                for uid in uids:
                    if str(uid) in conf["cam_list"]:
                        name = conf["cam_list"].pop(str(uid))
                        uncammed.append(f"**{name}** (`{uid}`)")
                self.save_config(conf)
                if uncammed:
                    await ctx.send(f"🔊 Đã mở lại quyền dùng Bot cho: {', '.join(uncammed)}.")
                else:
                    await ctx.send("❓ Các mục tiêu này hiện không bị tước quyền.")
                return True

            args_tokens = rest_args[1:] if (rest_args and rest_args[0].lower() == "add") else rest_args
            uids = self.get_ids(args_tokens)
            if not uids:
                await ctx.send("❌ Cú pháp: `bot cam @user1 @user2 ...`")
                return True

            conf = self.load_config()
            cammed_list = []
            denied_list = []
            for uid in uids:
                can_p, p_err = self.can_punish(ctx.author.id, uid)
                if not can_p:
                    denied_list.append(f"`{uid}` ({p_err})")
                    continue
                name = await self.fetch_name(uid)
                conf["cam_list"][str(uid)] = name
                cammed_list.append(f"**{name}** (`{uid}`)")
            self.save_config(conf)
            msg_res = []
            if cammed_list:
                msg_res.append(f"🤐 Đã tước quyền sử dụng Bot của: {', '.join(cammed_list)}.")
            if denied_list:
                msg_res.append(f"⚠️ Bỏ qua: {', '.join(denied_list)}")
            await ctx.send("\n".join(msg_res))
            return True

        # 7. bot kick (hỗ trợ nhiều @user cùng lúc)
        if subcmd == "kick":
            uids = self.get_ids(rest_args)
            if not uids or not ctx.guild:
                await ctx.send("❌ Cú pháp: `bot kick @user1 @user2 ...`")
                return True

            me = ctx.guild.me
            if not me.guild_permissions.kick_members:
                await ctx.send("❌ Tài khoản Bot không đủ quyền Kick members trên server này!")
                return True

            kicked_list = []
            failed_list = []
            for uid in uids:
                can_p, p_err = self.can_punish(ctx.author.id, uid)
                if not can_p:
                    failed_list.append(f"`{uid}` ({p_err})")
                    continue
                member = ctx.guild.get_member(uid)
                if not member:
                    failed_list.append(f"`{uid}` (không trong server)")
                    continue
                if member.top_role >= me.top_role:
                    failed_list.append(f"`{member.name}` (role cao hơn bot)")
                    continue
                try:
                    await member.kick(reason="Tự động kick bởi Self-Bot")
                    kicked_list.append(f"**{member.name}** (`{uid}`)")
                except Exception as e:
                    failed_list.append(f"`{member.name}` (lỗi: {e})")

            res_lines = []
            if kicked_list:
                res_lines.append(f"👞 Đã kick khỏi server: {', '.join(kicked_list)}")
            if failed_list:
                res_lines.append(f"⚠️ Bỏ qua: {', '.join(failed_list)}")
            await ctx.send("\n".join(res_lines))
            return True

        # 8. bot skip add/remove/list @role
        if subcmd == "skip":
            action = rest_args[0].lower() if rest_args else ""
            if action == "add" and len(rest_args) > 1:
                rid = self.get_id(rest_args[1])
                role = ctx.guild.get_role(rid) if ctx.guild else None
                rname = role.name if role else f"Role-{rid}"
                conf = self.load_config()
                conf["skip_list"][str(rid)] = rname
                self.save_config(conf)
                await ctx.send(f"✅ Đã thêm Role **{rname}** vào danh sách miễn trừ Anti.")
            elif action == "remove" and len(rest_args) > 1:
                rid = str(self.get_id(rest_args[1]))
                conf = self.load_config()
                if rid in conf["skip_list"]:
                    name = conf["skip_list"].pop(rid)
                    self.save_config(conf)
                    await ctx.send(f"❌ Đã xóa Role **{name}** khỏi danh sách miễn trừ Anti.")
                else:
                    await ctx.send("❓ Role này chưa có trong danh sách.")
            elif action == "list":
                conf = self.load_config()
                sl = conf.get("skip_list", {})
                lines = [f"• **{name}** (`{rid}`)" for rid, name in sl.items()]
                res = "\n".join(lines) if lines else "Danh sách trống."
                await ctx.send(f"🛡️ **DANH SÁCH ROLE MIỄN TRỪ ANTI**:\n{res}")
            else:
                await ctx.send("❌ Cú pháp: `bot skip add/remove/list @role`")
            return True

        # 9. Anti toggle commands
        anti_keys = {
            "link": "anti_link",
            "photo": "anti_photo",
            "video": "anti_video",
            "sticker": "anti_sticker",
            "file": "anti_file",
            "nuke": "anti_nuke",
            "card": "anti_card",
            "spam": "anti_spam",
        }
        if subcmd in anti_keys:
            status = rest_args[0].lower() if rest_args else ""
            if status not in ["on", "off"]:
                await ctx.send(f"❌ Cú pháp: `bot {subcmd} on/off`")
                return True
            val = status == "on"
            sid = str(ctx.guild.id) if ctx.guild else "dm"
            conf = self.load_config()
            conf.setdefault("settings", {}).setdefault(sid, {})[anti_keys[subcmd]] = val
            self.save_config(conf)
            st_text = "🟢 BẬT" if val else "🔴 TẮT"
            await ctx.send(f"{st_text} chế độ **{subcmd.upper()}** cho server này.")
            return True

        # 10. bot word add/remove/list / on / off
        if subcmd == "word":
            action = rest_args[0].lower() if rest_args else ""
            if action in ["on", "off"]:
                val = action == "on"
                sid = str(ctx.guild.id) if ctx.guild else "dm"
                conf = self.load_config()
                conf.setdefault("settings", {}).setdefault(sid, {})["anti_word"] = val
                self.save_config(conf)
                st_text = "🟢 BẬT" if val else "🔴 TẮT"
                await ctx.send(f"{st_text} chế độ lọc **TỪ CẤM** cho server này.")
            elif action == "add" and len(rest_args) > 1:
                word = " ".join(rest_args[1:]).lower().strip()
                conf = self.load_config()
                conf.setdefault("bad_words", [])
                if word not in conf["bad_words"]:
                    conf["bad_words"].append(word)
                    self.save_config(conf)
                    await ctx.send(f"✅ Đã thêm từ cấm: **'{word}'**")
                else:
                    await ctx.send(f"⚠️ Từ **'{word}'** đã có trong danh sách.")
            elif action == "remove" and len(rest_args) > 1:
                word = " ".join(rest_args[1:]).lower().strip()
                conf = self.load_config()
                if word in conf.get("bad_words", []):
                    conf["bad_words"].remove(word)
                    self.save_config(conf)
                    await ctx.send(f"❌ Đã gỡ từ cấm: **'{word}'**")
                else:
                    await ctx.send("❓ Từ này không tồn tại trong danh sách.")
            elif action == "list":
                conf = self.load_config()
                words = conf.get("bad_words", [])
                res = ", ".join([f"`{w}`" for w in words]) if words else "Trống."
                await ctx.send(f"🚫 **DANH SÁCH TỪ BỊ CHẶN**:\n{res}")
            else:
                await ctx.send("❌ Cú pháp: `bot word on/off` hoặc `bot word add/remove/list [từ]`")
            return True

        return False

    # --- TASKS ---
    @tasks.loop(seconds=15)
    async def clean_temp_punishments(self):
        conf = self.load_config()
        now = time.time()
        temp = conf.get("temp_punishments", [])
        expired = [p for p in temp if p.get("expire") and p["expire"] <= now]
        if not expired:
            return

        remaining = [p for p in temp if not (p.get("expire") and p["expire"] <= now)]
        conf["temp_punishments"] = remaining

        for p in expired:
            uid = p.get("uid")
            p_type = p.get("type")
            if p_type == "ban":
                conf.get("ban_list", {}).pop(str(uid), None)
            elif p_type == "mute":
                conf.get("mute_voice_list", {}).pop(str(uid), None)

        self.save_config(conf)

    # --- EVENT LISTENERS ---
    @commands.Cog.listener()
    async def on_ready(self):
        await self.init_for_user()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.author:
            return

        # Kiểm tra và xử lý lệnh bot trước
        handled = await self.handle_custom_command(message)
        if handled:
            return

        # Bỏ qua tin nhắn do chính bot gửi
        if message.author.id == self.bot.user.id or not message.guild:
            return

        conf = self.load_config()
        sid = str(message.guild.id)
        uid_str = str(message.author.id)

        # Kiểm tra xem bot có được bật tại server này không
        if not self.is_bot_active_in_guild(message.guild.id):
            return

        # Staff hoàn toàn miễn trừ kiểm tra vi phạm
        if self.is_staff(message.author.id):
            return

        # 1. Chặn người dùng trong danh sách CAM dùng lệnh bot
        if uid_str in conf.get("cam_list", {}):
            if message.content.strip().lower().startswith(("bot", "!bot", ",bot")):
                return

        # 2. Xóa tin nhắn nếu trong danh sách Ban
        if uid_str in conf.get("ban_list", {}):
            try:
                await message.delete()
                return
            except Exception:
                pass

        # 3. Ngoại lệ Role (Skip Anti)
        if hasattr(message.author, "roles"):
            user_roles = [str(r.id) for r in message.author.roles]
            if any(rid in conf.get("skip_list", {}) for rid in user_roles):
                return

        # 4. Anti Checks
        sset = conf.get("settings", {}).get(sid, {})
        to_delete = False

        if sset.get("anti_word"):
            msg_lower = message.content.lower()
            if any(bad.lower() in msg_lower for bad in conf.get("bad_words", [])):
                to_delete = True

        if not to_delete and sset.get("anti_sticker") and message.stickers:
            to_delete = True

        if not to_delete and sset.get("anti_link") and ("http://" in message.content.lower() or "https://" in message.content.lower()):
            to_delete = True

        if not to_delete and sset.get("anti_card"):
            if "discord.gg/" in message.content.lower() or "discord.com/invite/" in message.content.lower():
                to_delete = True

        if not to_delete and message.attachments:
            for att in message.attachments:
                fname = att.filename.lower()
                is_img = any(fname.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"])
                is_vid = any(fname.endswith(ext) for ext in [".mp4", ".mov", ".webm", ".mkv"])
                if sset.get("anti_photo") and is_img:
                    to_delete = True
                    break
                elif sset.get("anti_video") and is_vid:
                    to_delete = True
                    break
                elif sset.get("anti_file") and not is_img and not is_vid:
                    to_delete = True
                    break

        if not to_delete and sset.get("anti_spam"):
            now_ts = time.time()
            tracker = self.spam_tracker[message.author.id]
            tracker.append(now_ts)
            recent_count = sum(1 for ts in tracker if now_ts - ts <= 2.0)
            if recent_count >= 5:
                to_delete = True
                try:
                    await message.guild.ban(message.author, reason="Anti-Spam Triggered (>5 tin trong 2s)")
                except Exception:
                    pass

        if to_delete:
            try:
                await message.delete()
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot or self.is_staff(member.id):
            return
        conf = self.load_config()
        if str(member.id) in conf.get("mute_voice_list", {}) and after.channel and not after.mute:
            try:
                await member.edit(mute=True, reason="Mute Voice còn hiệu lực")
            except Exception:
                pass


# ==============================================================================
# 🧩 PUBLIC SYSTEM API (CHO PHÉP CÁC MODULE KHÁC DỄ DÀNG IMPORT & TÁI SỬ DỤNG)
# ==============================================================================

def get_system(bot: commands.Bot) -> Optional[Any]:
    """Lấy instance SelfBotSystem đang gắn trên bot."""
    if not bot:
        return None
    cog = bot.get_cog("SelfBotSystem")
    if cog is not None:
        return cog
    return None


def is_mod(bot: commands.Bot, user_id: int) -> bool:
    """Kiểm tra có phải Admin cấp cao (admintris / moderator) không."""
    sys = get_system(bot)
    if sys:
        return sys.is_mod(user_id)
    if hasattr(bot, "is_mod") and callable(bot.is_mod):
        try:
            return bot.is_mod(user_id)
        except Exception:
            pass
    return False


def is_admin(bot: commands.Bot, user_id: int) -> bool:
    """Kiểm tra có phải Admin (hoặc Admin cấp cao) không."""
    sys = get_system(bot)
    if sys:
        conf = sys.load_config()
        return user_id in conf.get("admins", conf.get("admin", [])) or sys.is_mod(user_id)
    return is_staff(bot, user_id)


def is_staff(bot: commands.Bot, user_id: int) -> bool:
    """Kiểm tra có phải Staff (Admin hoặc Admin cấp cao) không."""
    sys = get_system(bot)
    if sys:
        return sys.is_staff(user_id)
    if hasattr(bot, "is_staff") and callable(bot.is_staff):
        try:
            return bot.is_staff(user_id)
        except Exception:
            pass
    return False


def is_bot_active(bot: commands.Bot, guild_id: Optional[int]) -> bool:
    """Kiểm tra server này đang ON hay OFF bot (Mặc định mọi server là OFF)."""
    sys = get_system(bot)
    if sys:
        return sys.is_bot_active_in_guild(guild_id)
    if hasattr(bot, "is_bot_active") and callable(bot.is_bot_active):
        try:
            return bot.is_bot_active(guild_id)
        except Exception:
            pass
    return False


def is_dm_active(bot: commands.Bot) -> bool:
    """Kiểm tra tin nhắn riêng (DM) đang ON hay OFF bot (Mặc định là ON: True)."""
    sys = get_system(bot)
    if sys:
        conf = sys.load_config()
        return conf.get("dm_active", True)
    return True


def is_cammed(bot: commands.Bot, user_id: int) -> bool:
    """Kiểm tra người dùng có bị tước quyền dùng bot (CAM) không."""
    sys = get_system(bot)
    if not sys:
        return False
    conf = sys.load_config()
    return str(user_id) in conf.get("cam_list", {})


def get_all_shard_uids() -> set:
    """Lấy danh sách UID của tất cả bot (prime + shard) trong sổ genesis và runtime."""
    uids: set = set()
    try:
        from apps.user_discord.core.genesis import _read_config, _accounts, _uid_from_token
        cfg = _read_config()
        for acc in _accounts(cfg):
            u = acc.get("uid")
            if u:
                try:
                    uids.add(int(u))
                except Exception:
                    pass
            tok = acc.get("token")
            if tok:
                tu = _uid_from_token(tok)
                if tu:
                    uids.add(tu)
    except Exception:
        pass
    try:
        from apps.user_discord.core import runtime as _runtime
        for bot in _runtime.LIVE.values():
            uid = getattr(getattr(bot, "user", None), "id", None)
            if uid:
                uids.add(int(uid))
    except Exception:
        pass
    return uids


def is_internal_bot(user_id: Union[int, str]) -> bool:
    """True nếu user_id là một trong các bot shard/prime trong hệ thống."""
    try:
        return int(user_id) in get_all_shard_uids()
    except Exception:
        return False


def is_prime_uid(user_id: Union[int, str]) -> bool:
    """True neu user_id la uid cua BOT CHINH (prime) trong so genesis."""
    try:
        uid = int(user_id)
    except Exception:
        return False
    try:
        from apps.user_discord.core.genesis import (
            _read_config, _accounts, role_of, _uid_from_token, ROLE_PRIME,
        )
    except ImportError:
        from core.genesis import (  # type: ignore
            _read_config, _accounts, role_of, _uid_from_token, ROLE_PRIME,
        )
    try:
        for acc in _accounts(_read_config()):
            if role_of(acc) != ROLE_PRIME:
                continue
            raw = acc.get("uid")
            if raw is not None:
                try:
                    if int(raw) == uid:
                        return True
                except Exception:
                    pass
            tok = acc.get("token")
            if tok:
                try:
                    if _uid_from_token(tok) == uid:
                        return True
                except Exception:
                    pass
    except Exception:
        return False
    return False


def _cmd_head_after_prefix(bot, content: str) -> Optional[str]:
    """Tach ten lenh (head) dau tien ngay sau prefix cua BOT NAY. None neu khong co prefix."""
    try:
        try:
            from apps.user_discord.utils.prefix import get_prefixes
        except ImportError:
            from utils.prefix import get_prefixes  # type: ignore
        for p in sorted(get_prefixes(bot), key=len, reverse=True):
            pc = str(p or "")
            if pc and content.startswith(pc):
                parts = content[len(pc):].split()
                if parts:
                    return parts[0]
    except Exception:
        return None
    return None


def _is_reset_exempt_msg(bot, content: str) -> bool:
    """Lenh reset / gene reset van duoc phep khi bot OFF (cung process_commands)."""
    try:
        try:
            from apps.user_discord.utils.prefix import get_prefixes
        except ImportError:
            from utils.prefix import get_prefixes  # type: ignore
        c = str(content or "").strip().lower()
        for p in get_prefixes(bot):
            p_c = str(p or "").rstrip().lower()
            for pm in ([p_c, f"{p_c} "] if p_c else [""]):
                if c.startswith(pm):
                    parts = c[len(pm):].strip().split()
                    if parts and parts[0] in ("reset", "rs", "restart", "reboot"):
                        return True
                    if (len(parts) > 1 and parts[0] in ("gene", "genesis", "gen")
                            and parts[1] in ("reset", "rs", "restart", "reboot")):
                        return True
        return False
    except Exception:
        return False


def should_autoreact(bot, message) -> bool:
    """Chi duoc tha emoji vao tin nhan khi TAT CA dieu kien sau dung:

    1. Tin nhan la LENH HOP LE cua bot nay (co prefix + ten lenh dang ky/alias
       hoac lenh custom "(prefix)bot ...") — khong chi do bat ky tin bat dau
       bang prefix (prefix 1 ki tu nhu m/n/b khac gi tin thuong -> van de
       tha emoji lung tung -> bi cho la selfbot).
    2. Duoc phep TRA LOI: khong bi CAM, khong phai bot ngoai he thong, va
       (Staff [Admin/Admin cap cao] HOAC bot ON o server do) — cung dieu kien
       voi process_commands; ngoai tru lenh reset (mien triu bot OFF).
    3. DM: chi Staff hoac bot trong he thong (khong co khai niem bot ON/OFF).
    """
    try:
        content = str(getattr(message, "content", "") or "")
        if not content:
            return False
        author = getattr(message, "author", None)
        if author is None:
            return False
        uid = getattr(author, "id", None)
        if uid is None:
            return False

        # Bot ngoai he thong (hoac khong xac dinh duoc) -> bo qua.
        if getattr(author, "bot", False):
            try:
                if not is_internal_bot(uid):
                    return False
            except Exception:
                return False

        # 1. Phai la LENH HOP LE.
        head = _cmd_head_after_prefix(bot, content)
        if not head:
            return False
        if head.lower() != "bot":  # lenh custom (prefix)bot ... (handle_custom_command)
            try:
                cmd = bot.get_command(head)
            except Exception:
                cmd = None
            if cmd is None:
                return False

        # 2. Khong bi CAM.
        try:
            if is_cammed(bot, uid):
                return False
        except Exception:
            pass

        guild = getattr(message, "guild", None)

        # 3. DM: Cho phep neu DM dang ON hoac nguoi gui la Staff / bot trong he thong.
        if guild is None:
            try:
                if is_staff(bot, uid) or is_internal_bot(uid):
                    return True
                return is_dm_active(bot)
            except Exception:
                return True

        # 4. Minh (chinh bot) -> van tha.
        try:
            me = getattr(bot, "user", None)
            if me is not None and int(uid) == int(me.id):
                return True
        except Exception:
            pass

        # 5. Staff -> duoc tha ca khi bot OFF.
        try:
            if is_staff(bot, uid):
                return True
        except Exception:
            return False

        # 6. Nguoi thuong -> chi khi bot ON o server nay.
        try:
            if is_bot_active(bot, getattr(guild, "id", None)):
                return True
        except Exception:
            return False

        # 7. Ngoai lech lenh reset (duoc phep khi bot OFF).
        return _is_reset_exempt_msg(bot, content)
    except Exception:
        return False


def prime_reply_allowed(bot, author_id: Union[int, str]) -> bool:
    """Bot PHU (shard) chi xu ly / rep lenh gui tu BOT CHINH (prime) khi
    prime la **Admin hoac Admin cap cao CUA BOT PHU**. Khong thi -> cam nín
    tuyet doi (khong icon, khong rep, khong xu ly lenh).

    Giu hanh vi cu (True) cho cac truong hop:
      * khong phai tin internal (nguoi thuong) -> quyen van do check lenh cu;
      * chinh minh / bot chinh (prime) nhan tin shard (forward reset...);
      * tin khong phai tu prime (shard gui shard...);
      * he thong SelfBotSystem chua nap xong -> khong cheo duyet.
    """
    try:
        uid = int(author_id)
    except Exception:
        return True
    try:
        if not is_internal_bot(uid):
            return True
    except Exception:
        return True
    try:
        self_uid = getattr(getattr(bot, "user", None), "id", None)
        if self_uid is not None and int(self_uid) == uid:
            return True
    except Exception:
        pass
    try:
        if get_system(bot) is None:
            return True  # cog chua san sang -> khong cheo duyet
    except Exception:
        return True
    try:
        try:
            from apps.user_discord.core.genesis import self_entry, role_of, ROLE_PRIME
        except ImportError:
            from core.genesis import self_entry, role_of, ROLE_PRIME  # type: ignore
        if role_of(self_entry(bot)) == ROLE_PRIME:
            return True  # minh la bot chinh -> van xu ly shard nhu cu
    except Exception:
        return True
    try:
        if not is_prime_uid(uid):
            return True  # khong phai bot chinh gui -> giu logic cu
    except Exception:
        return True
    try:
        return bool(is_staff(bot, uid))
    except Exception:
        return False  # khong cham duoc quyen -> chan (khong rep)


def can_notice(bot, user_id, guild=None, is_reset_exempt: bool = False) -> bool:
    """Bot duoc phep gui thong bao (bao gom loi quyen) o ngu canh nay khong?

    Dieu kien CA 2:
      1. Nguoi goi khong bi CAM (bi cam -> can nhin tuyet doi).
      2. O guild: bot ON o sv nay HOAC nguoi goi la Staff (Admin tro len) HOAC lenh reset duoc mien tru.
         O DM: cho phep (khong co khai niem bot ON/OFF).
    """
    try:
        if is_cammed(bot, user_id):
            return False
    except Exception:
        return False
    if guild is None or is_reset_exempt:
        return True
    gid = getattr(guild, "id", guild)
    try:
        if is_bot_active(bot, gid):
            return True
    except Exception:
        return False
    try:
        return bool(is_staff(bot, user_id))
    except Exception:
        return False


async def notice_no_permission(bot, ctx, reason: str, label: str = None, is_reset_exempt: bool = False) -> None:
    """Gui '⛔ BAN KHONG DU QUYEN' + LY DO — chi khi du dieu kien cho phep rep
    (khong CAM va khong phai nguoi thuong o sv bot OFF)."""
    try:
        uid = ctx.author.id
        guild = getattr(ctx, "guild", None)
    except Exception:
        return
    if not can_notice(bot, uid, guild, is_reset_exempt=is_reset_exempt):
        return
    cmd = label or getattr(getattr(ctx, "command", None), "qualified_name", None) or "?"
    msg = (
        "⛔ **BẠN KHÔNG ĐỦ QUYỀN**\n"
        f"• {reason}\n"
        f"• Lệnh: `{cmd}`\n"
        f"• Người gọi: {ctx.author} (`{uid}`)"
    )
    try:
        from apps.user_discord.utils.autorep import autorep
    except ImportError:
        try:
            from utils.autorep import autorep
        except ImportError:
            autorep = None
    if autorep is not None:
        try:
            await autorep(getattr(ctx, "message", None), content=msg, auto_delete_delay=30)
            return
        except Exception:
            pass
    try:
        await ctx.send(msg)
    except Exception:
        pass


def check_permission(
    bot: commands.Bot,
    user_id: int,
    guild_id: Optional[int] = None,
    required_level: str = "user",
    is_reset_exempt: bool = False,
) -> tuple[bool, str]:
    """
    Hàm kiểm tra toàn diện quyền thực thi lệnh:
    - required_level:
        * 'user'   : Lệnh thông thường (Chỉ chạy khi bot ON, trừ khi người dùng là Staff thì chạy được cả khi bot OFF).
        * 'staff'  : Yêu cầu Admin hoặc Admin cấp cao (Chạy được mọi lúc kể cả bot OFF).
        * 'admin'  : Yêu cầu Admin hoặc Admin cấp cao.
        * 'mod'    : Yêu cầu Admin cấp cao (admintris).
    Trả về: (allowed: bool, reason: str)
    """
    sys = get_system(bot)
    if not sys:
        return False, "Hệ thống SelfBot chưa sẵn sàng."

    # 1. Bị CAM (tước quyền): luôn luôn bị từ chối
    if is_cammed(bot, user_id):
        return False, "Người dùng đang bị tước quyền sử dụng bot (CAM)."

    user_is_mod = is_mod(bot, user_id)
    user_is_staff = is_staff(bot, user_id)
    bot_active = is_bot_active(bot, guild_id)

    # 2. Xử lý trạng thái Bot OFF:
    # Nếu bot đang OFF, chỉ có Staff (Admin / Mod) mới được bot phản hồi.
    # RIÊNG VỚI LỆNH GENE RESET: CHỈ bot phụ trong hệ thống Genesis mới được miễn trừ!
    # Người ngoài không bao giờ được miễn trừ khi bot OFF.
    if guild_id:
        if not bot_active and not user_is_staff:
            if not (is_reset_exempt and is_internal_bot(user_id)):
                return False, "Bot đang tắt tại server này (Bot OFF)."
    else:
        dm_on = is_dm_active(bot)
        if not dm_on and not user_is_staff:
            if not (is_reset_exempt and is_internal_bot(user_id)):
                return False, "Bot đang tắt tại tin nhắn riêng (DM OFF)."


    # 3. Kiểm tra theo cấp độ quyền
    req = required_level.lower()
    if req in ("mod", "admintris"):
        if not user_is_mod:
            return False, "Yêu cầu quyền Admin cấp cao (admintris)."
        return True, "OK"

    if req in ("admin", "staff"):
        if not user_is_staff:
            return False, "Yêu cầu quyền Admin trở lên."
        return True, "OK"

    # req == 'user'
    return True, "OK"


def require_permission(level: str = "user"):
    """
    Decorator dùng trực tiếp cho các lệnh @commands.command() trong bất kỳ module nào:
    Ví dụ:
        from apps.user_discord.core.bot_sys import require_permission

        @commands.command()
        @require_permission("staff")
        async def my_command(self, ctx):
            ...
    """
    async def predicate(ctx: commands.Context) -> bool:
        cmd_name = (getattr(ctx.command, "qualified_name", "") or getattr(ctx.command, "name", "")).lower()
        is_reset_call = any(k in cmd_name for k in ("reset", "rs", "restart", "reboot"))
        if not is_reset_call and any(g in cmd_name for g in ("gene", "genesis", "gen")):
            content_clean = ctx.message.content.strip().lower()
            if any(k in content_clean for k in ("reset", "rs", "restart", "reboot")):
                is_reset_call = True

        allowed, reason = check_permission(
            ctx.bot,
            ctx.author.id,
            ctx.guild.id if ctx.guild else None,
            required_level=level,
            is_reset_exempt=is_reset_call,
        )
        if allowed:
            return True
        # Thieu cap quyen -> BAO RO "khong du quyen" (dieu kien rep nam trong notice).
        # CAM / Bot OFF / loi he thong -> CAN NHIN tuyet doi (khong rep).
        if (reason or "").startswith("Yêu cầu quyền"):
            await notice_no_permission(ctx.bot, ctx, reason, is_reset_exempt=is_reset_call)
        return False

    return commands.check(predicate)


async def setup(bot: commands.Bot):
    cog = SelfBotSystem(bot)
    await bot.add_cog(cog)
    if bot.user:
        await cog.init_for_user()

    # Gắn shortcut tiện dụng trực tiếp lên bot instance
    bot.is_mod = lambda uid: cog.is_mod(uid)
    bot.is_staff = lambda uid: cog.is_staff(uid)
    bot.is_bot_active = lambda gid: cog.is_bot_active_in_guild(gid)
    bot.check_permission = lambda uid, gid=None, req="user": check_permission(bot, uid, gid, req)

