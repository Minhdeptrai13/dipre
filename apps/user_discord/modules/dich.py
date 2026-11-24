# -*- coding: utf-8 -*-
"""
MODULE: dich (Universal Translation System)
- Lệnh: (prefix)dich, (prefix)trans, (prefix)dịch
- Cú pháp:
  • (prefix)dich set <ngôn ngữ> : Cài đặt ngôn ngữ mục tiêu (mặc định: vi).
  • (prefix)dich list : Xem danh sách các mã ngôn ngữ hỗ trợ dạng ảnh Liquid Glass.
  • (prefix)dich <văn bản> : Dịch văn bản (hoặc reply tin nhắn rồi gõ dich).
  • (prefix)dich on/off/status : Bật/tắt tự động dịch tin nhắn ngoại ngữ trong server.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord.ext import commands
import requests

try:
    from apps.user_discord.core.bot_sys import require_permission
    from apps.user_discord.core.alias import alias_declare
    from apps.user_discord.utils.prefix import fmt, get_prefix
    from apps.user_discord.utils.menu_catalog import menu_entry
    from apps.user_discord.utils.media_card import async_help_card
    from apps.user_discord.utils.autorep import autorep
    from apps.user_discord.utils.autodelet import autodelet
    from apps.user_discord.utils import glass as G
except ImportError:
    from core.bot_sys import require_permission
    from core.alias import alias_declare
    from utils.prefix import fmt, get_prefix
    from utils.menu_catalog import menu_entry
    from utils.media_card import async_help_card
    from utils.autorep import autorep
    from utils.autodelet import autodelet
    try:
        from utils import glass as G
    except ImportError:
        G = None

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_DIR / "translate_settings.json"

LANGUAGES = {
    "vi": "Tiếng Việt (Vietnamese)",
    "en": "Tiếng Anh (English)",
    "ja": "Tiếng Nhật (Japanese)",
    "ko": "Tiếng Hàn (Korean)",
    "zh": "Tiếng Trung (Chinese)",
    "fr": "Tiếng Pháp (French)",
    "de": "Tiếng Đức (German)",
    "ru": "Tiếng Nga (Russian)",
    "es": "Tiếng Tây Ban Nha (Spanish)",
    "th": "Tiếng Thái (Thai)",
    "lo": "Tiếng Lào (Lao)",
    "id": "Tiếng Indonesia (Indonesian)",
    "it": "Tiếng Ý (Italian)",
    "pt": "Tiếng Bồ Đào Nha (Portuguese)",
    "ar": "Tiếng Ả Rập (Arabic)",
    "hi": "Tiếng Hindi (Indian)",
}


class DichModule(commands.Cog, name="DichModule"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings: Dict[str, Any] = self._load_settings()

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return "!"

    def _load_settings(self) -> Dict[str, Any]:
        default = {
            "default_lang": "vi",
            "guild_langs": {},
            "active_guilds": {}
        }
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                for k, v in default.items():
                    if k not in data:
                        data[k] = v
                return data
            except Exception:
                return default
        return default

    def _save_settings(self):
        try:
            SETTINGS_FILE.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _get_target_lang(self, guild_id: Optional[int]) -> str:
        if guild_id:
            gl = self.settings.get("guild_langs", {}).get(str(guild_id))
            if gl:
                return gl.lower()
        return self.settings.get("default_lang", "vi").lower()

    def _set_target_lang(self, guild_id: Optional[int], lang_code: str):
        lang_code = lang_code.lower()
        if guild_id:
            if "guild_langs" not in self.settings:
                self.settings["guild_langs"] = {}
            self.settings["guild_langs"][str(guild_id)] = lang_code
        else:
            self.settings["default_lang"] = lang_code
        self._save_settings()

    def _is_auto_on(self, guild_id: Optional[int]) -> bool:
        if not guild_id:
            return False
        return bool(self.settings.get("active_guilds", {}).get(str(guild_id), False))

    def _set_auto(self, guild_id: int, is_on: bool):
        if "active_guilds" not in self.settings:
            self.settings["active_guilds"] = {}
        self.settings["active_guilds"][str(guild_id)] = is_on
        self._save_settings()

    def _check_admin(self, user_id: int) -> bool:
        bot_uid = self.bot.user.id if self.bot.user else 0
        cfg_owners = set()
        cfg_path = None
        for p in [BASE_DIR / "config.json", BASE_DIR.parent / "config.json"]:
            if p.exists():
                cfg_path = p
                break
        try:
            if cfg_path:
                cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
                for acc in cfg_data.get("accounts", []):
                    if isinstance(acc, dict) and acc.get("uid") == bot_uid:
                        for oid in list(acc.get("owner_ids") or []) + [acc.get("created_by")]:
                            if oid and str(oid).isdigit():
                                cfg_owners.add(int(oid))
        except Exception:
            pass

        setting_file = DATA_DIR / f"{bot_uid}_setting.json"
        this_conf: Dict[str, Any] = {}
        if setting_file.exists():
            try:
                this_conf = json.loads(setting_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        admin_list = set(cfg_owners)
        for x in this_conf.get("admintris", []) + this_conf.get("admins", []):
            if str(x).isdigit():
                admin_list.add(int(x))

        return user_id in admin_list

    # ── HÀM DỊCH THUẬT GOOGLE CHROME VỚI FALLBACK MYMEMORY ───────────────────
    def _translate_sync(self, text: str, target_lang: str) -> Tuple[bool, str, str]:
        """Trả về (thành_công, văn_bản_dịch, ngôn_ngữ_nguồn)"""
        # Engine 1: Google Chrome Translate
        try:
            q = urllib.parse.quote(text)
            url = f"https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=auto&tl={target_lang}&q={q}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            r = requests.get(url, headers=headers, timeout=7)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    translated = data[0][0] if isinstance(data[0], list) else str(data[0])
                    src_lang = data[0][1] if isinstance(data[0], list) and len(data[0]) > 1 else "auto"
                    return True, translated, src_lang
        except Exception:
            pass

        # Engine 2: MyMemory Translate
        try:
            q = urllib.parse.quote(text)
            url = f"https://api.mymemory.translated.net/get?q={q}&langpair=autodetect|{target_lang}"
            r = requests.get(url, timeout=7)
            if r.status_code == 200:
                data = r.json()
                translated = data.get("responseData", {}).get("translatedText")
                if translated and not translated.startswith("MYMEMORY WARNING"):
                    return True, translated, "auto"
        except Exception:
            pass

        return False, text, "unknown"

    # ── RENDER BẢNG DANH SÁCH NGÔN NGỮ LIQUID GLASS ────────────────────────
    def _render_lang_list_card(self) -> io.BytesIO:
        try:
            from apps.user_discord.utils import glass as G
        except ImportError:
            from utils import glass as G

        LW, LH = 1000, 520
        pad = 20
        head_h = 70
        gap = 14
        cv = G.GlassCanvas(LW, LH, scale=2, out=1.3)

        pfx = self._pfx()
        cv.header(
            pad, pad, LW - pad, head_h,
            "DANH SACH MA NGON NGU HO TRO",
            f"Prefix {pfx}   •   Cu phap: {pfx}dich set <ma>   •   {len(LANGUAGES)} Ngon Ngu",
            tag="TRANSLATE",
            right_reserve=140
        )

        top = pad + head_h + gap
        bottom = LH - pad
        panel_box = (pad, top, LW - pad, bottom)
        cv.glass(panel_box, 18, blur=20, tint=(14, 18, 30, 95), highlight=35)

        items = list(LANGUAGES.items())
        cols = 2
        col_w = (LW - 2 * pad - 40) / cols
        row_h = 38
        start_y = top + 18

        f_code = cv.font("b", 12.5)
        f_name = cv.font("r", 12)

        for idx, (code, name) in enumerate(items):
            c_idx = idx // 8
            r_idx = idx % 8
            if c_idx >= cols:
                break
            x1 = pad + 20 + c_idx * (col_w + 20)
            x2 = x1 + col_w
            y1 = start_y + r_idx * row_h
            y2 = y1 + 32

            cv.glass((x1, y1, x2, y2), 8, blur=4, tint=(18, 24, 40, 75))
            cv.pill(x1 + 8, y1 + 5, code.upper(), f_code, ((14, 165, 233), (2, 132, 199)), h=22, padx=10)
            cv.text(x1 + 65, y1 + 16, name, f_name, G.C_TEXT, vcenter=True)

        return cv.finalize()

    # ── RENDER THẺ BÁO CÁO STATUS LIQUID GLASS ─────────────────────────────
    def _render_status_card(self, ctx: commands.Context) -> io.BytesIO:
        try:
            from apps.user_discord.utils import glass as G
        except ImportError:
            from utils import glass as G

        active_map = self.settings.get("active_guilds", {})
        on_guilds = []
        for gid_str, is_on in active_map.items():
            if is_on:
                try:
                    g = self.bot.get_guild(int(gid_str))
                    if g:
                        on_guilds.append({
                            "name": g.name,
                            "id": str(g.id),
                            "members": g.member_count or len(g.members),
                            "lang": self._get_target_lang(g.id)
                        })
                    else:
                        on_guilds.append({"name": f"Server {gid_str}", "id": gid_str, "members": 0, "lang": "vi"})
                except Exception:
                    pass

        cur_guild = ctx.guild
        cur_guild_id = cur_guild.id if cur_guild else None
        cur_on = self._is_auto_on(cur_guild_id)
        cur_lang = self._get_target_lang(cur_guild_id)
        pfx = self._pfx()

        LW, LH = 1040, 540
        pad = 20
        head_h = 70
        gap = 14
        left_w = 340
        cv = G.GlassCanvas(LW, LH, scale=2, out=1.35)

        st_text = "🟢 AUTO DICH BAT" if cur_on else "🔴 AUTO DICH TAT"
        st_pill_col = G.G_ON if cur_on else G.G_OFF
        st_dot = (167, 255, 214) if cur_on else (255, 170, 170)

        cv.header(
            pad, pad, LW - pad, head_h,
            "TRANSLATION MONITOR SYSTEM",
            f"Prefix {pfx}   •   Dich Den: {cur_lang.upper()} ({LANGUAGES.get(cur_lang, cur_lang)})   •   {len(on_guilds)} Active",
            tag="TRANS MONITOR",
            right_reserve=180
        )
        cv.glass_pill(LW - pad - 16, pad + head_h / 2 - 15, st_text, cv.font("b", 12), st_pill_col, align="r", dot=st_dot)

        top = pad + head_h + gap
        bottom = LH - pad
        lx1, lx2 = pad, pad + left_w

        # Hộp Server hiện tại
        p_h = 140
        cv.glass((lx1, top, lx2, top + p_h), 20, blur=24, tint=(14, 18, 30, 95))
        cv.text(lx1 + 18, top + 18, "MAY CHU HIEN TAI", cv.font("b", 11), G.C_DIM, vcenter=True)
        if cur_guild:
            cv.text(lx1 + 18, top + 46, cv.fit(cur_guild.name, cv.font("b", 16), left_w - 36), cv.font("b", 16), G.C_GOLD, vcenter=True)
            cv.text(lx1 + 18, top + 72, f"ID: {cur_guild.id}   •   Ngon ngu: {cur_lang.upper()}", cv.font("r", 11.5), G.C_MUTED, vcenter=True)
            cur_badge = "🟢 DANG BAT TU DONG" if cur_on else "🔴 DANG TAT TU DONG"
            cv.pill(lx1 + 18, top + 96, cur_badge, cv.font("b", 10.5), grad=G.G_GREEN if cur_on else G.G_RED, h=22)
        else:
            cv.text(lx1 + 18, top + 46, "Tin Nhan Rieng (DM)", cv.font("b", 16), G.C_GOLD, vcenter=True)
            cv.pill(lx1 + 18, top + 96, "⚪ KHONG HO TRO AUTO", cv.font("b", 10.5), grad=G.G_GRAY, h=22)

        # Hộp Thống kê
        s_y1 = top + p_h + gap
        s_h = 130
        cv.glass((lx1, s_y1, lx2, s_y1 + s_h), 20, blur=24, tint=(14, 18, 30, 95))
        cv.text(lx1 + 18, s_y1 + 18, "CAI DAT MAC DINH HE THONG", cv.font("b", 11), G.C_DIM, vcenter=True)
        def_l = self.settings.get("default_lang", "vi")
        cv.text(lx1 + 18, s_y1 + 46, f"Ngon Ngu: {def_l.upper()} ({LANGUAGES.get(def_l, def_l)})", cv.font("b", 14), G.C_TEXT, vcenter=True)
        cv.text(lx1 + 18, s_y1 + 72, f"Tong so server bat: {len(on_guilds)}/{len(self.bot.guilds)}", cv.font("r", 12), G.C_MUTED, vcenter=True)
        cv.text(lx1 + 18, s_y1 + 96, f"Doi ngon ngu: {pfx}dich set <ma>", cv.font("r", 11), (56, 189, 248), vcenter=True)

        # Cột Phải: Danh sách Server Active
        rx1, rx2 = lx2 + gap, LW - pad
        cv.glass((rx1, top, rx2, bottom), 20, blur=24, tint=(14, 18, 30, 95))
        cv.text(rx1 + 20, top + 18, "DANH SACH MAY CHU BAT AUTO DICH", cv.font("b", 12), G.C_DIM, vcenter=True)

        if on_guilds:
            row_h = 58
            for i, ginfo in enumerate(on_guilds[:5]):
                ry1 = top + 42 + i * row_h
                ry2 = ry1 + row_h - 6
                cv.glass((rx1 + 14, ry1, rx2 - 14, ry2), 12, blur=12, tint=(18, 24, 40, 85))
                cv.circle_image(None, rx1 + 22, ry1 + 8, 36, ring=G.G_GREEN, letter=ginfo['name'][:1].upper(), fill=(28, 42, 58))
                tx = rx1 + 68
                cv.text(tx, ry1 + 16, cv.fit(ginfo['name'], cv.font("b", 13.5), rx2 - tx - 110), cv.font("b", 13.5), G.C_TEXT, vcenter=True)
                cv.text(tx, ry1 + 36, f"ID: {ginfo['id']}   •   Dich sang: {ginfo.get('lang', 'vi').upper()}", cv.font("r", 10.5), G.C_MUTED, vcenter=True)
                cv.pill(rx2 - 30, ry1 + 15, "ACTIVE", cv.font("b", 10), grad=G.G_GREEN, h=22, align="r")
        else:
            cv.text((rx1 + rx2) / 2, (top + bottom) / 2 - 10, "Chua co may chu nao bat Auto Dich", cv.font("b", 15), G.C_MUTED, align="c", vcenter=True)
            cv.text((rx1 + rx2) / 2, (top + bottom) / 2 + 18, f"Go {pfx}dich on de bat tinh nang nay tai server!", cv.font("r", 12), G.C_DIM, align="c", vcenter=True)

        return cv.finalize()

    # ── LỆNH CHÍNH (PREFIX)DICH / TRANS / DỊCH ──────────────────────────────
    @menu_entry("AI & TIỆN ÍCH", "dich", "Dich thuat da ngon ngu thong minh Realtime",
                badge="HOT", icon_sym="🌐", icon_color=(14, 165, 233), order=2)
    @alias_declare("dich", ["trans", "dịch"])
    @commands.command(
        name="dich",
        aliases=["trans", "dịch"],
        help="Dich thuat da ngon ngu thong minh & ho tro tu dong."
    )
    async def cmd_dich(self, ctx: commands.Context, *, arg: Optional[str] = None):
        p = self._pfx()
        target_lang = self._get_target_lang(ctx.guild.id if ctx.guild else None)

        # 1. Nếu không có arg: kiểm tra nếu đang reply tin nhắn -> dịch tin nhắn đó
        if not arg:
            ref = ctx.message.reference
            if ref and ref.message_id:
                try:
                    ref_msg = await ctx.channel.fetch_message(ref.message_id)
                    if ref_msg and ref_msg.content:
                        arg = ref_msg.content.strip()
                except Exception:
                    pass

        # 2. Nếu vẫn không có arg -> Xuất Help Card ảnh
        if not arg:
            card_buf = None
            try:
                card_buf = await async_help_card("dich", p)
            except Exception:
                card_buf = None

            if card_buf:
                try:
                    file = discord.File(card_buf, filename="dich_guide.png")
                    sent = await autorep(ctx.message, content=f"🌐 **UNIVERSAL TRANSLATION SYSTEM** (`{p}dich`)", file=file)
                    autodelet(sent, delay=45)
                    return
                except Exception:
                    pass

            guide = (
                f"🌐 **HỆ THỐNG DỊCH THUẬT ĐA NGÔN NGỮ** 🌐\n\n"
                f"• `{p}dich <văn bản>` : Dịch văn bản sang `{target_lang.upper()}` (hoặc reply tin nhắn rồi gõ `{p}dich`).\n"
                f"• `{p}dich set <mã>` : Cài đặt ngôn ngữ mục tiêu (ví dụ: `{p}dich set en`, `{p}dich set vi`).\n"
                f"• `{p}dich list` : Xem bảng danh sách các mã ngôn ngữ hỗ trợ.\n"
                f"• `{p}dich on/off` : Bật/tắt tự động dịch tin nhắn ngoại ngữ trong server.\n"
                f"• `{p}dich status` : Xem báo cáo trạng thái hệ thống bằng thẻ Liquid Glass."
            )
            sent = await autorep(ctx.message, guide)
            autodelet(sent, delay=45)
            return

        parts = arg.strip().split(maxsplit=1)
        sub = parts[0].lower()
        sub_arg = parts[1].strip() if len(parts) > 1 else ""

        if sub in ["set", "cai"]:
            return await self.dich_set(ctx, sub_arg)
        elif sub in ["list", "danhsach", "ma"]:
            return await self.dich_list(ctx)
        elif sub in ["on", "bat"]:
            return await self.dich_on(ctx)
        elif sub in ["off", "tat"]:
            return await self.dich_off(ctx)
        elif sub in ["status", "stt"]:
            return await self.dich_status(ctx)

        # Dịch văn bản trực tiếp
        text_to_trans = arg.strip()
        waiting = await autorep(ctx.message, f"⏳ Đang dịch sang `{target_lang.upper()}`...")
        autodelet(waiting, delay=10)

        loop = asyncio.get_event_loop()
        success, translated, src_lang = await loop.run_in_executor(None, self._translate_sync, text_to_trans, target_lang)

        if success:
            dst_name = LANGUAGES.get(target_lang, target_lang.upper())
            src_name = LANGUAGES.get(src_lang.lower(), src_lang.upper())
            resp_txt = (
                f"🌐 **BẢN DỊCH** `[{src_name} ➔ {dst_name}]`:\n"
                f"💬 **Nội dung:** {translated}"
            )
            sent = await autorep(ctx.message, resp_txt)
            autodelet(sent, delay=90)
        else:
            sent = await autorep(ctx.message, f"❌ Không thể dịch văn bản này (Lỗi mạng hoặc dịch vụ bận).")
            autodelet(sent, delay=15)

    async def dich_set(self, ctx: commands.Context, lang_code: str):
        p = self._pfx()
        if not lang_code:
            cur = self._get_target_lang(ctx.guild.id if ctx.guild else None)
            sent = await autorep(ctx.message, f"⚠️ Hãy nhập mã ngôn ngữ! Ví dụ: `{p}dich set en` (Hiện tại: `{cur.upper()}`). Gõ `{p}dich list` để xem mã.")
            autodelet(sent, delay=15)
            return

        code = lang_code.lower().strip()
        if code not in LANGUAGES and len(code) not in [2, 5]:
            sent = await autorep(ctx.message, f"❌ Mã ngôn ngữ `{code}` không hợp lệ! Gõ `{p}dich list` để xem các mã được hỗ trợ.")
            autodelet(sent, delay=15)
            return

        gid = ctx.guild.id if ctx.guild else None
        self._set_target_lang(gid, code)
        full_name = LANGUAGES.get(code, code.upper())
        sent = await autorep(
            ctx.message,
            f"✅ **Đã cài đặt ngôn ngữ dịch mặc định:** `{code.upper()}` ({full_name})!"
        )
        autodelet(sent, delay=25)

    async def dich_list(self, ctx: commands.Context):
        p = self._pfx()
        loop = asyncio.get_event_loop()
        buf = None
        try:
            buf = await loop.run_in_executor(None, self._render_lang_list_card)
        except Exception:
            buf = None

        if buf:
            try:
                file = discord.File(buf, filename="dich_lang_list.png")
                sent = await autorep(ctx.message, content=f"📋 **DANH SÁCH MÃ NGÔN NGỮ HỖ TRỢ** (`{p}dich list`)", file=file)
                autodelet(sent, delay=60)
                return
            except Exception:
                pass

        # Text fallback
        rows = [f"• `{k.upper()}`: {v}" for k, v in LANGUAGES.items()]
        txt = "📋 **DANH SÁCH MÃ NGÔN NGỮ HỖ TRỢ**:\n" + "\n".join(rows)
        sent = await autorep(ctx.message, txt)
        autodelet(sent, delay=60)

    async def dich_on(self, ctx: commands.Context):
        if not ctx.guild:
            sent = await autorep(ctx.message, "Không thể bật Auto Dịch trong tin nhắn riêng.")
            autodelet(sent, delay=15)
            return

        if not self._check_admin(ctx.author.id):
            sent = await autorep(ctx.message, "⛔ Lệnh này yêu cầu quyền **Admin trở lên** của bot!")
            autodelet(sent, delay=15)
            return

        target_lang = self._get_target_lang(ctx.guild.id)
        self._set_auto(ctx.guild.id, True)
        sent = await autorep(
            ctx.message,
            f"🎉 **Đã BẬT Tự Động Dịch tại máy chủ:** `{ctx.guild.name}`!\n"
            f"👉 Mọi tin nhắn ngoại ngữ trong server sẽ tự động được dịch sang `{target_lang.upper()}` ({LANGUAGES.get(target_lang, target_lang)})."
        )
        autodelet(sent, delay=30)

    async def dich_off(self, ctx: commands.Context):
        if not ctx.guild:
            sent = await autorep(ctx.message, "Không thể tắt Auto Dịch trong tin nhắn riêng.")
            autodelet(sent, delay=15)
            return

        if not self._check_admin(ctx.author.id):
            sent = await autorep(ctx.message, "⛔ Lệnh này yêu cầu quyền **Admin trở lên** của bot!")
            autodelet(sent, delay=15)
            return

        self._set_auto(ctx.guild.id, False)
        sent = await autorep(ctx.message, f"💤 **Đã TẮT Tự Động Dịch tại máy chủ:** `{ctx.guild.name}`.")
        autodelet(sent, delay=30)

    async def dich_status(self, ctx: commands.Context):
        p = self._pfx()
        loop = asyncio.get_event_loop()
        buf = None
        try:
            buf = await loop.run_in_executor(None, self._render_status_card, ctx)
        except Exception:
            buf = None

        if buf:
            try:
                file = discord.File(buf, filename="dich_status.png")
                sent = await autorep(ctx.message, content=f"🤖 **BÁO CÁO HỆ THỐNG DỊCH THUẬT** (`{p}dich status`)", file=file)
                autodelet(sent, delay=45)
                return
            except Exception:
                pass

        # Text fallback
        cur_on = self._is_auto_on(ctx.guild.id if ctx.guild else None)
        cur_lang = self._get_target_lang(ctx.guild.id if ctx.guild else None)
        txt = (
            f"🤖 **TRẠNG THÁI HỆ THỐNG DỊCH THUẬT**:\n"
            f"• Trạng thái server này: `{'🟢 BẬT' if cur_on else '🔴 TẮT'}`\n"
            f"• Ngôn ngữ dịch sang: `{cur_lang.upper()}` ({LANGUAGES.get(cur_lang, cur_lang)})\n"
            f"• Đổi ngôn ngữ: `{p}dich set <mã>` | Xem mã: `{p}dich list`"
        )
        sent = await autorep(ctx.message, txt)
        autodelet(sent, delay=45)

    # ── LISTENER TỰ ĐỘNG DỊCH KHI BẬT DICH ON ───────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not self._is_auto_on(message.guild.id):
            return

        p = self._pfx()
        content = message.content.strip()
        if not content or content.startswith(p) or len(content) < 4:
            return
        if content.startswith("http://") or content.startswith("https://"):
            return

        target_lang = self._get_target_lang(message.guild.id)

        # Chạy dịch nền
        loop = asyncio.get_event_loop()
        success, translated, src_lang = await loop.run_in_executor(None, self._translate_sync, content, target_lang)

        # Chỉ gửi nếu dịch thành công và ngôn ngữ nguồn khác ngôn ngữ đích
        if success and src_lang.lower() != target_lang.lower() and translated.strip().lower() != content.lower():
            src_name = LANGUAGES.get(src_lang.lower(), src_lang.upper())
            dst_name = LANGUAGES.get(target_lang, target_lang.upper())
            resp_txt = f"🌐 `[{src_name} ➔ {dst_name}]` {translated}"
            sent = await autorep(message, resp_txt)
            autodelet(sent, delay=60)


async def setup(bot: commands.Bot):
    await bot.add_cog(DichModule(bot))
