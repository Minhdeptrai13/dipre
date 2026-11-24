# -*- coding: utf-8 -*-
"""
join.py - Module quản lý gia nhập & tự động tham gia máy chủ Discord (Auto-Join).
Phân quyền: Chỉ Admin cấp cao (admintris) mới có quyền sử dụng.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from apps.shared.paths import SHARED_BACKGROUNDS_DIR, SHARED_FONTS_DIR
try:
    from apps.user_discord.core.bot_sys import get_system, require_permission
    from apps.user_discord.core.alias import alias_declare
    from apps.user_discord.utils.autorep import autorep
    from apps.user_discord.utils.menu_catalog import menu_entry
    from apps.user_discord.utils.prefix import get_prefix
except ImportError:
    from core.bot_sys import get_system, require_permission
    from core.alias import alias_declare
    from utils.autorep import autorep
    from utils.menu_catalog import menu_entry
    from utils.prefix import get_prefix

# Regex bóc tách mã code mời Discord từ link hoặc văn bản
INVITE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com/invite)/([a-zA-Z0-9\-]+)",
    re.IGNORECASE,
)

# Chống spam join lặp lại trong thời gian ngắn (cooldown theo guild_id hoặc code)
_RECENT_JOINS: Dict[str, float] = {}


class JoinCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.font_bold = str(SHARED_FONTS_DIR / "BeVietnamPro-Bold.ttf")
        self.font_reg = str(SHARED_FONTS_DIR / "BeVietnamPro-Regular.ttf")

    def _get_setting_path(self) -> Optional[Path]:
        uid = getattr(getattr(self.bot, "user", None), "id", None)
        if not uid:
            return None
        return Path("apps/user_discord/data") / f"{uid}_setting.json"

    def _load_settings(self) -> Dict[str, Any]:
        p = self._get_setting_path()
        if not p or not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_settings(self, data: Dict[str, Any]) -> None:
        p = self._get_setting_path()
        if not p:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def is_auto_join_enabled(self, guild_id: int) -> bool:
        """Kiểm tra server này có đang bật chế độ Auto-Join không."""
        data = self._load_settings()
        aj_map = data.get("auto_join", {})
        return bool(aj_map.get(str(guild_id), False))

    def set_auto_join(self, guild_id: int, enabled: bool) -> None:
        """Bật hoặc tắt chế độ Auto-Join cho server."""
        data = self._load_settings()
        aj_map = data.setdefault("auto_join", {})
        aj_map[str(guild_id)] = enabled
        self._save_settings(data)

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return getattr(self.bot, "_own_prefix", None) or ""

    # ── VẼ ẢNH HƯỚNG DẪN ──────────────────────────────────────────────────
    async def render_guide_card(self, invoker: discord.User, guild: Optional[discord.Guild] = None) -> io.BytesIO:
        """Thẻ hướng dẫn (prefix)join — LIQUID GLASS ngang. Lỗi -> bản cũ."""
        try:
            pfx = self._pfx()
            is_on = self.is_auto_join_enabled(guild.id) if guild else False
            g_name = guild.name if guild else None
            return await asyncio.to_thread(self._draw_guide_glass, pfx, is_on, g_name)
        except Exception as e:
            print(f"[join] liquid glass lỗi, dùng bản cũ: {type(e).__name__}: {e}")
            return await self._render_guide_card_legacy(invoker, guild)

    @staticmethod
    def _draw_guide_glass(pfx: str, is_on: bool, g_name: Optional[str]) -> io.BytesIO:
        try:
            from apps.user_discord.utils import glass as G
        except ImportError:
            from utils import glass as G
        pad, gap, head_h, foot_h = 24, 16, 78, 70
        LW = 980
        row_h = 54
        sec_h = G.GlassCanvas.section_height(2, row_h)
        LH = pad + head_h + gap + sec_h + gap + foot_h + pad
        cv = G.GlassCanvas(LW, LH)

        f_st = cv.font("b", 12)
        st_text = f"AUTO-JOIN: {'BẬT' if is_on else 'TẮT'}" if g_name else "AUTO-JOIN: DM"
        st_w = cv.tlen(st_text, f_st) + 46
        cv.header(pad, pad, LW - pad, head_h, "HỆ THỐNG GIA NHẬP MÁY CHỦ",
                  "Join thủ công & tự động bắt link mời", tag="ROOT", tag_grad=G.G_RED,
                  right_reserve=st_w + 8)
        cv.glass_pill(LW - pad - 20, pad + head_h / 2 - 15, st_text, f_st,
                      G.G_ON if is_on else G.G_OFF, align="r",
                      dot=(167, 255, 214) if is_on else (255, 170, 170))

        top = pad + head_h + gap
        col_w = (LW - 2 * pad - gap) / 2
        x1 = pad
        cv.section(x1, top, x1 + col_w, "GIA NHẬP", "Join ngay bằng link / mã mời", G.G_BLUE, [
            (f"{pfx}join <link mời>", "Gia nhập máy chủ Discord ngay lập tức", "JOIN"),
            (f"{pfx}join status", "Xem trạng thái Auto-Join của server này", "STATUS"),
        ], row_h=row_h)
        x1 = pad + col_w + gap
        cv.section(x1, top, x1 + col_w, "AUTO-JOIN", "Tự join khi thấy link mời", G.G_GREEN, [
            (f"{pfx}join on", "Bật tự join (bắt cả link do bot gửi)", "ON"),
            (f"{pfx}join off", "Tắt tự động join tại server này", "OFF"),
        ], row_h=row_h)

        fy1 = top + sec_h + gap
        cv.bar(pad, fy1, LW - pad, fy1 + foot_h)
        cv.chip((pad + 16, fy1 + 15, pad + 56, fy1 + foot_h - 15), "🚀", "J", (96, 165, 250), r=12, size=18)
        f_l = cv.font("b", 12.5)
        f_r = cv.font("r", 12)
        tx = pad + 72
        tmax = LW - pad - 20 - tx
        cv.rich(tx, fy1 + 24, [("Máy chủ hiện tại:  ", f_r, G.C_MUTED),
                               (cv.fit(G.clean_text(g_name) if g_name else "Tin nhắn riêng (DM)", f_l, tmax - 130),
                                f_l, G.C_TEXT)], vcenter=True)
        cv.text(tx, fy1 + 47, "Quyền hạn: chỉ Admin cấp cao (admintris) mới điều khiển được.", f_r, G.C_GOLD,
                vcenter=True)
        return cv.finalize()

    async def _render_guide_card_legacy(self, invoker: discord.User, guild: Optional[discord.Guild] = None) -> io.BytesIO:
        """Bản cũ — fallback."""
        w, h = 580, 480
        pfx = self._pfx()
        is_on = self.is_auto_join_enabled(guild.id) if guild else False

        # 1. Ảnh nền bokeh mờ
        base_img = Image.new("RGBA", (w, h), (14, 16, 22, 255))
        valid_exts = (".png", ".jpg", ".jpeg", ".webp")
        if SHARED_BACKGROUNDS_DIR.exists():
            bg_files = [f for f in os.listdir(SHARED_BACKGROUNDS_DIR) if f.lower().endswith(valid_exts)]
            if bg_files:
                try:
                    chosen = SHARED_BACKGROUNDS_DIR / random.choice(bg_files)
                    with Image.open(chosen) as rbg:
                        raw = rbg.convert("RGBA")
                    raw = ImageOps.fit(raw, (w, h), method=Image.Resampling.BILINEAR)
                    sw, sh = max(w // 8, 40), max(h // 8, 40)
                    blur_img = raw.resize((sw, sh), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(2))
                    base_img = blur_img.resize((w, h), Image.Resampling.BICUBIC)
                    dim = Image.new("RGBA", (w, h), (10, 12, 18, 200))
                    base_img = Image.alpha_composite(base_img, dim)
                except Exception:
                    pass

        draw = ImageDraw.Draw(base_img)

        # 2. Outer frosted panel
        draw.rounded_rectangle([18, 18, w - 18, h - 18], radius=20, fill=(20, 24, 32, 225), outline=(60, 75, 105, 180), width=1)

        # Fonts
        f_title = ImageFont.truetype(self.font_bold, 22)
        f_sub = ImageFont.truetype(self.font_bold, 13)
        f_text = ImageFont.truetype(self.font_reg, 13)
        f_cmd = ImageFont.truetype(self.font_bold, 14)
        f_badge = ImageFont.truetype(self.font_bold, 11)

        # Header Title
        draw.text((40, 36), "🚀 HỆ THỐNG GIA NHẬP MÁY CHỦ", font=f_title, fill=(255, 255, 255))
        draw.text((40, 66), "Join thủ công & tự động lắng nghe link mời tham gia", font=f_sub, fill=(140, 165, 210))

        # Status badge của Guild hiện tại
        badge_y = 38
        badge_text = "🟢 AUTO-JOIN: BẬT" if is_on else "🔴 AUTO-JOIN: TẮT"
        badge_bg = (34, 197, 94, 220) if is_on else (239, 68, 68, 220)
        bw = int(draw.textlength(badge_text, font=f_badge)) + 16
        bx = w - 40 - bw
        draw.rounded_rectangle([bx, badge_y, bx + bw, badge_y + 24], radius=12, fill=badge_bg)
        draw.text((bx + 8, badge_y + 4), badge_text, font=f_badge, fill=(255, 255, 255))

        # Đường kẻ chia
        draw.line([40, 95, w - 40, 95], fill=(50, 65, 90, 150), width=1)

        # Danh sách lệnh
        commands_list = [
            (f"{pfx}join <link_mời>", "Gia nhập máy chủ Discord ngay lập tức", "ADMINTRIS"),
            (f"{pfx}join on", "Bật chế độ tự động join khi có người gửi link", "AUTO-JOIN"),
            (f"{pfx}join off", "Tắt chế độ tự động join tại server này", "TẮT"),
            (f"{pfx}join status", "Xem trạng thái Auto-Join của server hiện tại", "STATUS"),
        ]

        curr_y = 110
        for cmd_txt, desc, b_label in commands_list:
            # Box lệnh
            draw.rounded_rectangle([38, curr_y, w - 38, curr_y + 54], radius=12, fill=(28, 34, 46, 180), outline=(48, 60, 85, 120), width=1)
            # Dot phát sáng
            draw.ellipse([54, curr_y + 22, 62, curr_y + 30], fill=(96, 165, 250))
            # Cú pháp lệnh
            draw.text((74, curr_y + 10), cmd_txt, font=f_cmd, fill=(240, 245, 255))
            # Diễn giải
            draw.text((74, curr_y + 30), desc, font=f_text, fill=(148, 163, 184))
            # Tag badge
            tw = int(draw.textlength(b_label, font=f_badge)) + 12
            draw.rounded_rectangle([w - 52 - tw, curr_y + 14, w - 52, curr_y + 36], radius=8, fill=(40, 50, 70, 200))
            draw.text((w - 46 - tw, curr_y + 19), b_label, font=f_badge, fill=(186, 230, 253))
            curr_y += 64

        # Footer note
        draw.line([40, curr_y + 10, w - 40, curr_y + 10], fill=(50, 65, 90, 150), width=1)
        draw.text((40, curr_y + 22), f"• Máy chủ hiện tại: {guild.name if guild else 'Tin nhắn riêng (DM)'}", font=f_text, fill=(160, 175, 200))
        draw.text((40, curr_y + 42), "• Quyền hạn: Chỉ Admin cấp cao (admintris) mới có quyền điều khiển.", font=f_sub, fill=(251, 191, 36))

        buf = io.BytesIO()
        base_img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    # ── NHÓM LỆNH: (prefix)join ──────────────────────────────────────────
    @menu_entry("SYSTEM & SECURITY", "join", "Gia nhập & tự động tham gia máy chủ Discord",
                badge="ROOT", icon_sym="🚀", icon_color=(96, 165, 250), order=4)
    @alias_declare("join", main="join", subs=[])
    @commands.group(name="join", invoke_without_command=True)
    @require_permission("mod")
    async def join_cmd(self, ctx: commands.Context, *, target: Optional[str] = None):
        """Lệnh gia nhập server: (prefix)join <link|on|off|status>"""
        if not target:
            buf = await self.render_guide_card(ctx.author, guild=ctx.guild)
            file = discord.File(buf, filename="join_guide.png")
            await autorep(ctx.message, content="", file=file, auto_delete_delay=30)
            return

        target_clean = target.strip()
        sub = target_clean.lower()

        # Xử lý các subcmd tiện lợi: on / off / status
        if sub in ("on", "bat", "bật"):
            await self._handle_auto_join_switch(ctx, True)
            return
        if sub in ("off", "tat", "tắt"):
            await self._handle_auto_join_switch(ctx, False)
            return
        if sub in ("status", "st", "tt"):
            await self._handle_auto_join_status(ctx)
            return

        # Còn lại: coi target_clean là link hoặc mã mời
        await self._do_join_invite(ctx, target_clean)

    @join_cmd.command(name="on")
    @require_permission("mod")
    async def join_on(self, ctx: commands.Context):
        """Bật tính năng Auto-Join khi ai đó gửi link mời ở server này."""
        await self._handle_auto_join_switch(ctx, True)

    @join_cmd.command(name="off")
    @require_permission("mod")
    async def join_off(self, ctx: commands.Context):
        """Tắt tính năng Auto-Join ở server này."""
        await self._handle_auto_join_switch(ctx, False)

    @join_cmd.command(name="status")
    @require_permission("mod")
    async def join_status(self, ctx: commands.Context):
        """Xem trạng thái Auto-Join của server hiện tại."""
        await self._handle_auto_join_status(ctx)

    async def _handle_auto_join_switch(self, ctx: commands.Context, state: bool) -> None:
        if not ctx.guild:
            await autorep(ctx.message, content="❌ Lệnh này chỉ sử dụng được trong **Máy chủ (Guild)**.", auto_delete_delay=20)
            return
        self.set_auto_join(ctx.guild.id, state)
        st_text = "🟢 **BẬT (ON)**" if state else "🔴 **TẮT (OFF)**"
        msg = (
            f"✅ Đã chuyển trạng thái Auto-Join tại **{ctx.guild.name}** thành: {st_text}\n"
            + ("• Bot sẽ tự động tham gia các máy chủ khi phát hiện link mời trong server này." if state else "• Bot sẽ bỏ qua các link mời được gửi trong server này.")
        )
        await autorep(ctx.message, content=msg, auto_delete_delay=25)

    async def _handle_auto_join_status(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await autorep(ctx.message, content="❌ Lệnh này chỉ sử dụng được trong **Máy chủ (Guild)**.", auto_delete_delay=20)
            return
        is_on = self.is_auto_join_enabled(ctx.guild.id)
        st_text = "🟢 **ĐANG BẬT (ON)**" if is_on else "🔴 **ĐANG TẮT (OFF)**"
        msg = (
            f"📍 **TRẠNG THÁI AUTO-JOIN MÁY CHỦ**\n"
            f"• Server: **{ctx.guild.name}** (`{ctx.guild.id}`)\n"
            f"• Chế độ: {st_text}\n"
            f"• Cú pháp: `{self._pfx()}join on` để bật • `{self._pfx()}join off` để tắt."
        )
        await autorep(ctx.message, content=msg, auto_delete_delay=25)

    # ── LOGIC GIA NHẬP LINK MỜI ──────────────────────────────────────────
    async def _do_join_invite(self, ctx: commands.Context, invite_input: str) -> None:
        """Xử lý phân tích và gia nhập server từ chuỗi link hoặc code."""
        code = self._extract_code(invite_input)
        if not code:
            await autorep(ctx.message, content=f"❌ Không tìm thấy mã mời hợp lệ từ: `{invite_input}`", auto_delete_delay=20)
            return

        # Kiểm tra xem bot đã ở trong server đó chưa
        try:
            invite = await self.bot.fetch_invite(code)
        except discord.NotFound:
            await autorep(ctx.message, content=f"❌ **Mã mời không tồn tại hoặc đã hết hạn:** `{code}`", auto_delete_delay=25)
            return
        except Exception as e:
            await autorep(ctx.message, content=f"❌ Không thể kiểm tra mã mời `{code}`: {type(e).__name__} ({e})", auto_delete_delay=25)
            return

        g_id = invite.guild.id if invite.guild else None
        g_name = invite.guild.name if invite.guild else "Không rõ"
        members = invite.approximate_member_count or "N/A"

        if g_id and self.bot.get_guild(g_id):
            await autorep(
                ctx.message,
                content=f"⚠️ Tài khoản bot **đã có mặt sẵn** trong máy chủ: **{g_name}** (`{g_id}`).",
                auto_delete_delay=25,
            )
            return

        # Bắt đầu gia nhập
        load_msg = await autorep(ctx.message, content=f"⏳ Đang tiến hành gia nhập **{g_name}** (`{code}`)...", auto_delete_delay=None)
        try:
            res = await self.bot.accept_invite(code)
            succ_guild = self.bot.get_guild(g_id) if g_id else None
            succ_name = succ_guild.name if succ_guild else g_name
            final_text = (
                f"🎉 **GIA NHẬP MÁY CHỦ THÀNH CÔNG!**\n"
                f"• Máy chủ: **{succ_name}** (`{g_id or '?'}`)\n"
                f"• Thành viên: **{members}** người\n"
                f"• Mã mời: `{code}`"
            )
            if load_msg:
                try:
                    await load_msg.edit(content=final_text)
                    return
                except Exception:
                    pass
            await autorep(ctx.message, content=final_text, auto_delete_delay=35)
        except discord.HTTPException as http_err:
            err_code = getattr(http_err, "code", None)
            err_msg = str(http_err)
            if err_code == 30001 or "Maximum number of guilds" in err_msg:
                detail = "Tài khoản đã đạt giới hạn tối đa 100/200 máy chủ (Full Server)."
            elif err_code == 50036 or "banned" in err_msg.lower():
                detail = "Tài khoản đang bị CẤM (Banned) tại máy chủ này."
            elif "captcha" in err_msg.lower() or "checkpoint" in err_msg.lower():
                detail = "Discord yêu cầu giải mã Captcha / Checkpoint để gia nhập."
            else:
                detail = f"Lỗi Discord HTTP: {err_msg}"

            fail_txt = f"❌ **Không thể gia nhập {g_name}:** {detail}"
            if load_msg:
                try:
                    await load_msg.edit(content=fail_txt)
                    return
                except Exception:
                    pass
            await autorep(ctx.message, content=fail_txt, auto_delete_delay=30)
        except Exception as exc:
            fail_txt = f"❌ Lỗi khi gia nhập `{code}`: {type(exc).__name__} ({exc})"
            if load_msg:
                try:
                    await load_msg.edit(content=fail_txt)
                    return
                except Exception:
                    pass
            await autorep(ctx.message, content=fail_txt, auto_delete_delay=30)

    @staticmethod
    def _extract_code(text: str) -> Optional[str]:
        m = INVITE_REGEX.search(text)
        if m:
            return m.group(1)
        cleaned = text.strip()
        if "/" not in cleaned and " " not in cleaned and len(cleaned) >= 2:
            return cleaned
        return None

    # ── LISTENER: TỰ ĐỘNG BẮT LINK MỜI (AUTO-JOIN) ──────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or not message.author:
            return

        # Kiểm tra xem server hiện tại có bật chế độ Auto-Join không
        if not self.is_auto_join_enabled(message.guild.id):
            return

        # Tìm kiếm link mời trong tin nhắn
        content = message.content or ""
        matches = INVITE_REGEX.findall(content)
        if not matches:
            return

        now = time.time()
        for code in set(matches):
            code_key = code.lower()
            last_tried = _RECENT_JOINS.get(code_key, 0)
            if now - last_tried < 60:
                continue  # Bỏ qua mã mời này nếu đã thử trong vòng 60s
            _RECENT_JOINS[code_key] = now

            # Thử lấy thông tin invite
            try:
                invite = await self.bot.fetch_invite(code)
                g_id = invite.guild.id if invite.guild else None
                g_name = invite.guild.name if invite.guild else "Không rõ"
                if g_id and self.bot.get_guild(g_id):
                    continue  # Đã có mặt trong server rồi thì bỏ qua

                # Thực hiện accept invite
                await self.bot.accept_invite(code)
                author_desc = "chính bạn (bot)" if message.author.id == self.bot.user.id else message.author.mention
                notice = (
                    f"📥 **[AUTO-JOIN]** Đã tự động tham gia máy chủ: **{g_name}**\n"
                    f"• Nguồn link: `{code}` từ {author_desc} trong #{message.channel.name}"
                )
                await autorep(message, content=notice, auto_delete_delay=30)
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(JoinCog(bot))
