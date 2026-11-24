# -*- coding: utf-8 -*-
"""
read.py - Module đánh dấu đã đọc (Ack Notifications) cho toàn bộ hoặc từng máy chủ.
Hỗ trợ vẽ lưới danh sách Server co giãn động (dù hàng chục hay hàng trăm server vẫn hiển thị sắc nét).
Phân quyền: Admin & Admin cấp cao (admintris).
"""
from __future__ import annotations

import asyncio
import io
import math
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from apps.shared.paths import SHARED_BACKGROUNDS_DIR, SHARED_FONTS_DIR
try:
    from apps.user_discord.core.bot_sys import require_permission
    from apps.user_discord.utils.autorep import autorep
    from apps.user_discord.utils.menu_catalog import menu_entry
    from apps.user_discord.utils.prefix import get_prefix
    from apps.user_discord.utils.media_card import async_help_card
    from apps.user_discord.core.alias import alias_declare
except ImportError:
    from core.bot_sys import require_permission
    from utils.autorep import autorep
    from utils.menu_catalog import menu_entry
    from utils.prefix import get_prefix
    try:
        from utils.media_card import async_help_card
    except ImportError:
        async_help_card = None
    try:
        from core.alias import alias_declare
    except ImportError:
        def alias_declare(*args, **kwargs):
            return lambda f: f

# Cache icon server trong bộ nhớ RAM để vẽ tức thì
_ICON_CACHE: Dict[str, bytes] = {}


class ReadCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.font_bold = str(SHARED_FONTS_DIR / "BeVietnamPro-Bold.ttf")
        self.font_reg = str(SHARED_FONTS_DIR / "BeVietnamPro-Regular.ttf")

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return getattr(self.bot, "_own_prefix", None) or ""

    # ── TẢI ICON SERVER BẤT ĐỒNG BỘ ──────────────────────────────────────
    async def _fetch_guild_icon(self, session: aiohttp.ClientSession, guild: discord.Guild) -> Optional[Image.Image]:
        """Tải avatar/icon của server hoặc fallback vẽ icon chữ cái."""
        icon_url = str(guild.icon.url) if guild.icon else None
        if icon_url:
            if icon_url in _ICON_CACHE:
                try:
                    with Image.open(io.BytesIO(_ICON_CACHE[icon_url])) as im:
                        return im.convert("RGBA")
                except Exception:
                    pass
            try:
                async with session.get(icon_url, timeout=aiohttp.ClientTimeout(total=2.0)) as resp:
                    if resp.status == 200:
                        raw = await resp.read()
                        _ICON_CACHE[icon_url] = raw
                        with Image.open(io.BytesIO(raw)) as im:
                            return im.convert("RGBA")
            except Exception:
                pass
        return None

    # ── VẼ LƯỚI SERVER CO GIÃN ĐỘNG (DYNAMIC GRID CANVAS) ────────────────
    async def render_guilds_matrix_card(self, guilds: List[discord.Guild], invoker: discord.User) -> io.BytesIO:
        """Lưới server LIQUID GLASS co giãn (2/3/4 cột). Lỗi -> bản cũ."""
        try:
            async with aiohttp.ClientSession() as session:
                icons = await asyncio.gather(*[self._fetch_guild_icon(session, g) for g in guilds],
                                             return_exceptions=True)
            icons = [i if isinstance(i, Image.Image) else None for i in icons]
            rows = [(g.name or "Server", g.id, len(g.channels)) for g in guilds]
            return await asyncio.to_thread(self._draw_matrix_glass, rows, icons, self._pfx())
        except Exception as e:
            print(f"[read] liquid glass lỗi, dùng bản cũ: {type(e).__name__}: {e}")
            return await self._render_guilds_matrix_card_legacy(guilds, invoker)

    @staticmethod
    def _draw_matrix_glass(rows: List[Tuple[str, int, int]], icons: List[Optional[Image.Image]], p: str) -> io.BytesIO:
        try:
            from apps.user_discord.utils import glass as G
        except ImportError:
            from utils import glass as G
        total = len(rows)
        if total <= 8:
            cols, LW = 2, 900
        elif total <= 30:
            cols, LW = 3, 1120
        else:
            cols, LW = 4, 1260
        # nhiều server -> giảm độ phân giải vẽ (vẫn supersample) cho nhẹ RAM/CPU
        if total <= 30:
            scale, out = 4, 2.0
        elif total <= 80:
            scale, out = 3, 1.5
        else:
            scale, out = 2, 1.5
        pad, gap, head_h, foot_h = 24, 16, 78, 70
        cell_h, gx, gy, inner = 58, 10, 10, 12
        nrows = max(1, math.ceil(total / cols))
        grid_h = nrows * cell_h + (nrows - 1) * gy
        body_h = grid_h + inner * 2
        LH = pad + head_h + gap + body_h + gap + foot_h + pad
        cv = G.GlassCanvas(LW, LH, scale=scale, out=out)

        f_st = cv.font("b", 12)
        st_text = f"{total} SERVER"
        st_w = cv.tlen(st_text, f_st) + 46
        cv.header(pad, pad, LW - pad, head_h, "DANH SÁCH MÁY CHỦ  •  ĐÁNH DẤU ĐÃ ĐỌC",
                  f"Đang có mặt tại {total} máy chủ  •  nhập số 1..{max(1, total)} hoặc 'all'",
                  tag="READ", tag_grad=G.G_GREEN, right_reserve=st_w + 8)
        cv.glass_pill(LW - pad - 20, pad + head_h / 2 - 15, st_text, f_st, G.G_BLUE, align="r",
                      dot=(147, 197, 253))

        top = pad + head_h + gap
        cv.glass((pad, top, LW - pad, top + body_h), 22, blur=24, tint=(12, 16, 28, 50))
        col_w = (LW - 2 * pad - 2 * inner - (cols - 1) * gx) / cols
        f_idx = cv.font("b", 12)
        f_name = cv.font("b", 12.5)
        f_meta = cv.font("r", 10.5)
        if not rows:
            cv.text(LW / 2, top + body_h / 2, "Không có máy chủ nào", f_name, G.C_DIM, align="c", vcenter=True)
        for i, (name, gid, nch) in enumerate(rows):
            r, c = divmod(i, cols)
            x1 = pad + inner + c * (col_w + gx)
            y1 = top + inner + r * (cell_h + gy)
            x2, y2 = x1 + col_w, y1 + cell_h
            cv.glass((x1, y1, x2, y2), 14, blur=6, tint=(255, 255, 255, 16), magnify=1.0, saturate=1.1,
                     highlight=34, rim=(120, 26), shadow=True, shadow_opacity=50)
            num = str(i + 1)
            nw = max(30, cv.tlen(num, f_idx) + 14)
            nb = (x1 + 10, y1 + (cell_h - 26) / 2, x1 + 10 + nw, y1 + (cell_h + 26) / 2)
            cv.glass(nb, 9, blur=4, tint_grad=((59, 130, 246), (37, 99, 235), 150), magnify=1.0,
                     saturate=1.0, highlight=55, rim=(200, 60), shadow=False)
            cv.text((nb[0] + nb[2]) / 2, (nb[1] + nb[3]) / 2, num, f_idx, (255, 255, 255), align="c",
                    vcenter=True, shadow=False)
            isz = 36
            ix = nb[2] + 10
            cv.circle_image(icons[i] if i < len(icons) else None, ix, y1 + (cell_h - isz) / 2, isz,
                            ring=G.G_BLUE, ring_w=1.5, letter=G.clean_text(name)[:1] or "S",
                            fill=(56, 80, 115))
            tx = ix + isz + 10
            tmax = x2 - 10 - tx
            cv.text(tx, y1 + 21, cv.fit(G.clean_text(name) or "Server", f_name, tmax), f_name, G.C_TEXT,
                    vcenter=True)
            cv.text(tx, y1 + 39, cv.fit(f"{nch} kênh  •  {gid}", f_meta, tmax), f_meta, G.C_DIM, vcenter=True)

        fy1 = top + body_h + gap
        cv.bar(pad, fy1, LW - pad, fy1 + foot_h)
        cv.chip((pad + 16, fy1 + 15, pad + 56, fy1 + foot_h - 15), "✉", "R", (52, 211, 153), r=12, size=18)
        tx = pad + 72
        fb, fr = cv.font("b", 12.5), cv.font("r", 12)
        y_c = (253, 224, 71)
        cv.rich(tx, fy1 + 24, [("Gõ  ", fr, G.C_MUTED), (f"1…{max(1, total)}", fb, y_c),
                               ("  để đọc 1 server   •   ", fr, G.C_MUTED), ("all", fb, y_c),
                               ("  đọc tất cả   •   ", fr, G.C_MUTED), ("c", fb, y_c), ("  huỷ", fr, G.C_MUTED)],
                vcenter=True)
        cv.rich(tx, fy1 + 47, [("Lệnh nhanh:  ", fr, G.C_DIM), (f"{p}read <id server>", fb, G.C_TEXT),
                               ("   •   ", fr, G.C_DIM), (f"{p}read all", fb, G.C_TEXT),
                               ("   —  tự huỷ sau 45 giây", fr, G.C_DIM)], vcenter=True)
        return cv.finalize()

    async def _render_guilds_matrix_card_legacy(self, guilds: List[discord.Guild], invoker: discord.User) -> io.BytesIO:
        """
        Bản cũ — fallback.
        """
        total = len(guilds)
        # Quyết định số cột dựa trên tổng số server
        if total <= 8:
            cols = 2
            card_w = 720
            cell_h = 56
        elif total <= 30:
            cols = 3
            card_w = 980
            cell_h = 54
        else:
            cols = 4
            card_w = 1200
            cell_h = 52

        rows = math.ceil(total / cols) if total > 0 else 1
        header_h = 100
        footer_h = 75
        pad_x = 24
        pad_y = 16
        gap_x = 12
        gap_y = 10

        grid_h = rows * cell_h + (rows - 1) * gap_y
        card_h = header_h + grid_h + footer_h + (pad_y * 2)

        # 1. Background kính mờ
        base_img = Image.new("RGBA", (card_w, card_h), (14, 17, 24, 255))
        valid_exts = (".png", ".jpg", ".jpeg", ".webp")
        if SHARED_BACKGROUNDS_DIR.exists():
            bg_files = [f for f in os.listdir(SHARED_BACKGROUNDS_DIR) if f.lower().endswith(valid_exts)]
            if bg_files:
                try:
                    chosen = SHARED_BACKGROUNDS_DIR / random.choice(bg_files)
                    with Image.open(chosen) as rbg:
                        raw = rbg.convert("RGBA")
                    raw = ImageOps.fit(raw, (card_w, card_h), method=Image.Resampling.BILINEAR)
                    sw, sh = max(card_w // 8, 40), max(card_h // 8, 40)
                    blur_img = raw.resize((sw, sh), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(2))
                    base_img = blur_img.resize((card_w, card_h), Image.Resampling.BICUBIC)
                    dim = Image.new("RGBA", (card_w, card_h), (10, 13, 20, 210))
                    base_img = Image.alpha_composite(base_img, dim)
                except Exception:
                    pass

        draw = ImageDraw.Draw(base_img)

        # Khung viền vi tinh
        draw.rounded_rectangle([12, 12, card_w - 12, card_h - 12], radius=20, fill=(20, 25, 36, 220), outline=(50, 65, 95, 180), width=1)

        # Fonts
        f_title = ImageFont.truetype(self.font_bold, 22)
        f_sub = ImageFont.truetype(self.font_reg, 13)
        f_idx = ImageFont.truetype(self.font_bold, 13)
        f_name = ImageFont.truetype(self.font_bold, 12)
        f_meta = ImageFont.truetype(self.font_reg, 11)
        f_badge = ImageFont.truetype(self.font_bold, 12)

        # Header
        draw.text((pad_x + 12, pad_y + 16), "📬 DANH SÁCH MÁY CHỦ — ĐÁNH DẤU ĐÃ ĐỌC", font=f_title, fill=(255, 255, 255))
        draw.text((pad_x + 12, pad_y + 48), f"Tài khoản hiện có mặt tại {total} máy chủ • Nhập số 1..{total} hoặc 'all' để xóa thông báo", font=f_sub, fill=(148, 163, 184))

        # Badge đếm tổng số
        b_text = f"🌐 {total} SERVER"
        bw = int(draw.textlength(b_text, font=f_badge)) + 18
        bx = card_w - pad_x - 12 - bw
        draw.rounded_rectangle([bx, pad_y + 22, bx + bw, pad_y + 50], radius=14, fill=(59, 130, 246, 220))
        draw.text((bx + 9, pad_y + 28), b_text, font=f_badge, fill=(255, 255, 255))

        draw.line([pad_x + 12, pad_y + 78, card_w - pad_x - 12, pad_y + 78], fill=(60, 75, 105, 150), width=1)

        # Tính toán kích thước cell
        col_w = int((card_w - (pad_x * 2) - ((cols - 1) * gap_x)) / cols)
        start_y = pad_y + header_h

        # Tải song song tất cả icon qua session HTTP
        async with aiohttp.ClientSession() as session:
            tasks = [self._fetch_guild_icon(session, g) for g in guilds]
            icons = await asyncio.gather(*tasks, return_exceptions=True)

        # Vẽ từng cell server
        for idx, guild in enumerate(guilds, 1):
            r = (idx - 1) // cols
            c = (idx - 1) % cols
            x = pad_x + c * (col_w + gap_x)
            y = start_y + r * (cell_h + gap_y)

            # Cell Card
            draw.rounded_rectangle([x, y, x + col_w, y + cell_h], radius=10, fill=(26, 32, 45, 190), outline=(48, 62, 90, 130), width=1)

            # Huy hiệu số thứ tự (#1, #2, ...)
            num_str = f"{idx}"
            nw = max(int(draw.textlength(num_str, font=f_idx)) + 10, 24)
            draw.rounded_rectangle([x + 6, y + (cell_h - 22) // 2, x + 6 + nw, y + (cell_h + 22) // 2], radius=6, fill=(40, 52, 75, 210))
            draw.text((x + 6 + (nw - int(draw.textlength(num_str, font=f_idx))) // 2, y + (cell_h - 22) // 2 + 2), num_str, font=f_idx, fill=(147, 197, 253))

            # Avatar tròn (Icon server)
            icon_size = 36
            ix = x + nw + 12
            iy = y + (cell_h - icon_size) // 2

            loaded_icon = icons[idx - 1] if isinstance(icons[idx - 1], Image.Image) else None
            if loaded_icon:
                try:
                    c_icon = ImageOps.fit(loaded_icon, (icon_size, icon_size), method=Image.Resampling.BILINEAR)
                    mask = Image.new("L", (icon_size, icon_size), 0)
                    ImageDraw.Draw(mask).ellipse((0, 0, icon_size, icon_size), fill=255)
                    base_img.paste(c_icon, (ix, iy), mask)
                    draw.ellipse([ix, iy, ix + icon_size, iy + icon_size], outline=(96, 165, 250, 180), width=1)
                except Exception:
                    loaded_icon = None

            if not loaded_icon:
                # Fallback: vẽ vòng tròn màu kèm chữ cái đầu
                h_val = sum(ord(ch) for ch in guild.name) % 360
                # Màu pastel ngẫu nhiên theo tên
                color_bg = (56, 80, 115)
                draw.ellipse([ix, iy, ix + icon_size, iy + icon_size], fill=color_bg, outline=(120, 150, 200, 180), width=1)
                initial = guild.name[0].upper() if guild.name else "G"
                fw = int(draw.textlength(initial, font=f_idx))
                draw.text((ix + (icon_size - fw) // 2, iy + 8), initial, font=f_idx, fill=(240, 245, 255))

            # Tên server & thông tin
            tx = ix + icon_size + 10
            max_name_w = col_w - (tx - x) - 8

            g_name = guild.name
            while draw.textlength(g_name, font=f_name) > max_name_w and len(g_name) > 3:
                g_name = g_name[:-2] + "…"

            draw.text((tx, y + 8), g_name, font=f_name, fill=(248, 250, 252))

            channel_count = len(guild.channels)
            meta_txt = f"{channel_count} kênh • {guild.id}"
            while draw.textlength(meta_txt, font=f_meta) > max_name_w and len(meta_txt) > 6:
                meta_txt = meta_txt[:-2] + "…"
            draw.text((tx, y + 28), meta_txt, font=f_meta, fill=(148, 163, 184))

        # Footer hướng dẫn
        foot_y = card_h - footer_h - pad_y + 10
        draw.line([pad_x + 12, foot_y, card_w - pad_x - 12, foot_y], fill=(60, 75, 105, 150), width=1)
        p = self._pfx()
        draw.text((pad_x + 14, foot_y + 12), f"➡️ Gõ số 1…{total} để đánh dấu đã đọc 1 server • Gõ 'all' để đánh dấu TẤT CẢ ({total} server) • 'c' để hủy", font=f_name, fill=(255, 255, 255))
        draw.text((pad_x + 14, foot_y + 34), f"• Lệnh nhanh: `{p}read <id_server>` hoặc `{p}read all` — Tự động chờ lựa chọn trong 45 giây.", font=f_sub, fill=(251, 191, 36))

        buf = io.BytesIO()
        base_img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    # ── NHÓM LỆNH: (prefix)read & bread ───────────────────────────────────
    @menu_entry("AUTOMATION & QUEST", "read", "Đánh dấu đã đọc & dọn sạch chấm đỏ thông báo",
                badge="UTIL", icon_sym="✉️", icon_color=(52, 211, 153), order=2)
    @alias_declare("read", main="read", subs=["bread"])
    @commands.group(name="read", aliases=["bread"], invoke_without_command=True)
    @require_permission("admin")
    async def read_cmd(self, ctx: commands.Context, *, target: Optional[str] = None):
        """Đánh dấu đã đọc tin nhắn: (prefix)read [all|list|group|user|sv|id]"""
        p = self._pfx()
        # 1. Nếu gõ trần (không truyền tham số) -> Gửi Card Ảnh Hướng Dẫn Liquid Glass
        if not target or not target.strip():
            card_buf = None
            try:
                if async_help_card:
                    card_buf = await async_help_card("read", p)
            except Exception:
                card_buf = None

            if card_buf:
                try:
                    file = discord.File(card_buf, filename="read_guide.png")
                    await autorep(
                        ctx.message,
                        content=f"✉️ **HƯỚNG DẪN ĐÁNH DẤU ĐÃ ĐỌC THÔNG BÁO** (`{p}read`)",
                        file=file,
                        auto_delete_delay=35,
                    )
                    return
                except Exception:
                    pass

            # Fallback nếu card ảnh lỗi: mở lưới danh sách
            await self._handle_read_list_interactive(ctx)
            return

        clean = target.strip().lower()
        parts = clean.split()
        sub = parts[0]

        # 2. Xử lý các nhánh subcmd
        if sub in ("list", "sv", "servers", "guilds", "grid"):
            await self._handle_read_list_interactive(ctx)
            return

        if sub in ("all", "tatca", "tất cả", "het"):
            force = len(parts) > 1 and parts[1] in ("force", "f", "ep", "all")
            await self._handle_read_all(ctx, force=force)
            return

        if sub in ("group", "groups", "nhom", "gr"):
            if len(parts) > 1 and parts[1] in ("list", "ds", "danhsach"):
                await self._handle_group_list(ctx)
            else:
                await self._handle_read_groups(ctx)
            return

        if sub in ("user", "users", "dm", "dms", "inbox"):
            if len(parts) > 1 and parts[1] in ("list", "ds", "danhsach"):
                await self._handle_dm_list(ctx)
            else:
                await self._handle_read_dms(ctx)
            return

        # Coi target là ID server hoặc tên server
        await self._handle_read_target(ctx, target.strip())

    @read_cmd.command(name="list", aliases=["sv", "servers", "guilds"])
    @require_permission("admin")
    async def read_list(self, ctx: commands.Context):
        """Xem ảnh lưới danh sách máy chủ kèm số 1..N để chọn đọc."""
        await self._handle_read_list_interactive(ctx)

    @read_cmd.command(name="all")
    @require_permission("admin")
    async def read_all(self, ctx: commands.Context, mode: Optional[str] = None):
        """Đánh dấu đã đọc TẤT CẢ tin nhắn trên toàn bộ máy chủ: (prefix)read all [force]"""
        force = bool(mode and mode.strip().lower() in ("force", "f", "ep", "all"))
        await self._handle_read_all(ctx, force=force)

    @read_cmd.command(name="group", aliases=["groups", "nhom"])
    @require_permission("admin")
    async def read_group(self, ctx: commands.Context, sub: Optional[str] = None):
        """Đánh dấu đã đọc toàn bộ tin nhắn trong các Nhóm chat riêng (Group DMs): (prefix)read group [list]"""
        if sub and sub.strip().lower() in ("list", "ds", "danhsach"):
            await self._handle_group_list(ctx)
        else:
            await self._handle_read_groups(ctx)

    @read_cmd.command(name="user", aliases=["users", "dm", "dms", "inbox"])
    @require_permission("admin")
    async def read_user(self, ctx: commands.Context, sub: Optional[str] = None):
        """Đánh dấu đã đọc toàn bộ tin nhắn riêng cá nhân (DMs): (prefix)read user [list]"""
        if sub and sub.strip().lower() in ("list", "ds", "danhsach"):
            await self._handle_dm_list(ctx)
        else:
            await self._handle_read_dms(ctx)

    @staticmethod
    def _guild_has_red_dot(guild: discord.Guild) -> bool:
        """Cờ chấm đỏ tự tính từ read-state cache và cấu hình mute hiện tại."""
        channels = list(getattr(guild, "channels", ()) or ())
        channels.extend(getattr(guild, "threads", ()) or ())
        seen_ids = set()
        guild_settings = getattr(guild, "notification_settings", None)
        guild_muted = bool(getattr(guild_settings, "muted", False))

        for channel in channels:
            channel_id = getattr(channel, "id", None)
            if channel_id in seen_ids:
                continue
            seen_ids.add(channel_id)
            try:
                read_state = channel.read_state
                if int(getattr(read_state, "badge_count", 0) or 0) > 0:
                    return True

                channel_settings = getattr(channel, "notification_settings", None)
                channel_muted = bool(getattr(channel_settings, "muted", False))
                category = getattr(channel, "category", None)
                category_settings = getattr(category, "notification_settings", None)
                category_muted = bool(getattr(category_settings, "muted", False))
                if guild_muted or channel_muted or category_muted:
                    continue

                last_message_id = int(getattr(channel, "last_message_id", 0) or 0)
                last_acked_id = int(getattr(read_state, "last_acked_id", 0) or 0)
                if last_message_id > last_acked_id:
                    return True
            except Exception:
                continue
        return False

    # ── ĐÁNH DẤU ĐÃ ĐỌC TẤT CẢ SERVER ────────────────────────────────────
    async def _handle_read_all(self, ctx: commands.Context, force: bool = False) -> None:
        guilds = list(self.bot.guilds)
        total = len(guilds)
        if total == 0:
            await autorep(ctx.message, content="⚠️ Tài khoản hiện chưa tham gia máy chủ nào.", auto_delete_delay=20)
            return

        if force:
            target_guilds = guilds
        else:
            target_guilds = [guild for guild in guilds if self._guild_has_red_dot(guild)]

        unread_total = len(target_guilds)
        if unread_total == 0:
            p = self._pfx()
            await autorep(
                ctx.message,
                content=(
                    f"✅ **ĐÃ QUÉT {total} MÁY CHỦ:** Không có thông báo hoặc chấm đỏ chưa đọc nào!\n"
                    f"💡 *Nếu bạn muốn ép đánh dấu đã đọc toàn bộ cả {total} máy chủ, hãy gõ:* `{p}read all force`"
                ),
                auto_delete_delay=25,
            )
            return

        desc_type = "tất cả máy chủ" if force else "máy chủ có thông báo chưa đọc"
        wait_msg = await autorep(
            ctx.message,
            content=f"⏳ Đang đánh dấu đã đọc trên **{unread_total}**/**{total}** {desc_type}...",
            auto_delete_delay=None,
        )

        success_guilds: List[discord.Guild] = []
        failed_guilds: List[discord.Guild] = []

        for g in target_guilds:
            try:
                if hasattr(g, "ack"):
                    await g.ack()
                else:
                    await self.bot.http.ack_guild(g.id)
                success_guilds.append(g)
                await asyncio.sleep(0.12)  # Delay nhẹ nhàng tránh bị rate-limit
            except Exception:
                failed_guilds.append(g)

        # Lập danh sách tên các máy chủ đã đánh dấu đọc
        items = []
        for idx, g in enumerate(success_guilds, 1):
            chans = len(g.channels)
            items.append(f"{idx}. 🏰 **{g.name}** (`{g.id}`) — *{chans} kênh*")

        if len(items) <= 15:
            list_str = "\n".join(items) if items else "*Không có máy chủ nào*"
        else:
            list_str = "\n".join(items[:15]) + f"\n*...và còn {len(items) - 15} máy chủ khác đã được đọc thành công.*"

        failed_note = ""
        if failed_guilds:
            failed_note = f"\n⚠️ **Thất bại ({len(failed_guilds)}):** " + ", ".join(f"`{g.name}`" for g in failed_guilds[:5])

        res_txt = (
            f"🎉 **ĐÃ ĐÁNH DẤU ĐÃ ĐỌC TOÀN BỘ XONG!**\n\n"
            f"📊 **Thống kê:**\n"
            f"• Tổng số máy chủ đã quét: **{total}**\n"
            f"• Đã đánh dấu thành công: **{len(success_guilds)}** / **{unread_total}** máy chủ\n"
            f"• Bỏ qua / thất bại: **{len(failed_guilds)}** máy chủ{failed_note}\n\n"
            f"📋 **DANH SÁCH MÁY CHỦ ĐÃ ĐÁNH DẤU ĐỌC:**\n"
            f"{list_str}"
        )

        # Tạo card ảnh nếu số lượng server vừa phải (1..20)
        card_file = None
        if 1 <= len(success_guilds) <= 20:
            try:
                buf = await self.render_guilds_matrix_card(success_guilds, ctx.author)
                if buf:
                    card_file = discord.File(buf, filename="read_success_servers.png")
            except Exception:
                card_file = None

        if wait_msg:
            try:
                await wait_msg.delete()
            except Exception:
                pass

        if card_file:
            await autorep(ctx.message, content=res_txt, file=card_file, auto_delete_delay=60)
        else:
            await autorep(ctx.message, content=res_txt, auto_delete_delay=45)

    # ── ĐÁNH DẤU ĐÃ ĐỌC MỘT SERVER THEO ID HOẶC TÊN ──────────────────────
    async def _handle_read_target(self, ctx: commands.Context, target_str: str) -> None:
        target_guild: Optional[discord.Guild] = None

        if target_str.isdigit():
            target_guild = self.bot.get_guild(int(target_str))

        if not target_guild:
            low = target_str.lower()
            for g in self.bot.guilds:
                if g.name.lower() == low or low in g.name.lower():
                    target_guild = g
                    break

        if not target_guild:
            await autorep(
                ctx.message,
                content=f"❌ Không tìm thấy máy chủ nào khớp với `{target_str}` mà bot đang tham gia.",
                auto_delete_delay=20,
            )
            return

        try:
            if hasattr(target_guild, "ack"):
                await target_guild.ack()
            else:
                await self.bot.http.ack_guild(target_guild.id)
            await autorep(
                ctx.message,
                content=f"✅ Đã đánh dấu đã đọc toàn bộ tin nhắn tại máy chủ: **{target_guild.name}** (`{target_guild.id}`).",
                auto_delete_delay=25,
            )
        except Exception as e:
            await autorep(
                ctx.message,
                content=f"❌ Lỗi khi đánh dấu đã đọc tại **{target_guild.name}**: {type(e).__name__} ({e})",
                auto_delete_delay=25,
            )

    # ── GỬI ẢNH MATRIX VÀ CHỜ CHỌN SỐ ───────────────────────────────────
    async def _handle_read_list_interactive(self, ctx: commands.Context) -> None:
        guilds = sorted(list(self.bot.guilds), key=lambda x: len(x.channels), reverse=True)
        total = len(guilds)
        if total == 0:
            await autorep(ctx.message, content="⚠️ Tài khoản hiện chưa tham gia máy chủ nào.", auto_delete_delay=20)
            return

        # 1. Render ảnh lưới toàn diện
        wait_render = await autorep(ctx.message, content="⏳ Đang tải và vẽ lưới danh sách máy chủ...", auto_delete_delay=None)
        try:
            buf = await self.render_guilds_matrix_card(guilds, ctx.author)
            card_file = discord.File(buf, filename="guilds_read_matrix.png")
        except Exception as exc:
            card_file = None

        if wait_render:
            try:
                await wait_render.delete()
            except Exception:
                pass

        card_msg = await autorep(
            ctx.message,
            content=f"📬 **BẢNG MÁY CHỦ ({total} GUILDS)** — Nhập số `1`…`{total}`, hoặc `all` để đọc hết, `c` để hủy:",
            file=card_file,
            auto_delete_delay=60,
        )

        def check(m: discord.Message) -> bool:
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

        try:
            choice_msg = await self.bot.wait_for("message", check=check, timeout=45.0)
            choice = choice_msg.content.strip().lower()

            if choice in ("c", "cancel", "huy", "hủy"):
                await autorep(ctx.message, content="Đã hủy thao tác.", auto_delete_delay=15)
                return

            if choice in ("all", "tatca", "tất cả", "het"):
                await self._handle_read_all(ctx)
                return

            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= total:
                    picked_guild = guilds[idx - 1]
                    await self._handle_read_target(ctx, str(picked_guild.id))
                    return
                else:
                    await autorep(ctx.message, content=f"❌ Số lựa chọn phải từ `1` đến `{total}`.", auto_delete_delay=15)
                    return

            # Nếu gõ tên
            await self._handle_read_target(ctx, choice)
        except asyncio.TimeoutError:
            pass

    # ── ĐỌC VÀ QUẢN LÝ NHÓM CHAT (GROUP DMS) ─────────────────────────────
    async def _handle_read_groups(self, ctx: commands.Context) -> None:
        """Đánh dấu đã đọc tất cả tin nhắn trong các Group DMs."""
        groups = [c for c in self.bot.private_channels if isinstance(c, discord.GroupChannel)]
        if not groups:
            await autorep(ctx.message, content="ℹ️ Tài khoản hiện không tham gia Nhóm chat riêng (Group DM) nào.", auto_delete_delay=20)
            return

        wait_msg = await autorep(ctx.message, content=f"⏳ Đang đánh dấu đã đọc trên **{len(groups)}** nhóm chat...", auto_delete_delay=None)
        success: List[discord.GroupChannel] = []
        failed: List[discord.GroupChannel] = []

        for grp in groups:
            try:
                if hasattr(grp, "ack"):
                    await grp.ack()
                elif hasattr(grp, "last_message_id") and grp.last_message_id:
                    await self.bot.http.ack_message(grp.id, grp.last_message_id)
                success.append(grp)
                await asyncio.sleep(0.1)
            except Exception:
                failed.append(grp)

        if wait_msg:
            try:
                await wait_msg.delete()
            except Exception:
                pass

        names = [f"• 👥 **{g.name or 'Nhóm không tên'}** (`{g.id}`)" for g in success[:10]]
        more = f"\n*...và {len(success) - 10} nhóm khác*" if len(success) > 10 else ""
        list_str = "\n".join(names) if names else "*Không có nhóm nào*"

        res = (
            f"🎉 **ĐÃ ĐÁNH DẤU ĐÃ ĐỌC NHÓM CHAT (GROUP DMS) XONG!**\n\n"
            f"📊 **Kết quả:** Đã đọc **{len(success)}** / **{len(groups)}** nhóm\n\n"
            f"📋 **DANH SÁCH NHÓM ĐÃ ĐỌC:**\n{list_str}{more}"
        )
        await autorep(ctx.message, content=res, auto_delete_delay=40)

    async def _handle_group_list(self, ctx: commands.Context) -> None:
        """Hiển thị danh sách các Group DMs."""
        groups = [c for c in self.bot.private_channels if isinstance(c, discord.GroupChannel)]
        if not groups:
            await autorep(ctx.message, content="ℹ️ Tài khoản hiện không có Nhóm chat riêng (Group DM) nào.", auto_delete_delay=20)
            return

        lines = []
        for i, grp in enumerate(groups[:25], 1):
            name = grp.name or "Nhóm không tên"
            mem_count = len(getattr(grp, "recipients", [])) + 1
            lines.append(f"{i}. 👥 **{name}** (`{grp.id}`) — *{mem_count} thành viên*")

        more = f"\n*...và còn {len(groups) - 25} nhóm khác.*" if len(groups) > 25 else ""
        content = (
            f"👥 **DANH SÁCH NHÓM CHAT RIÊNG ({len(groups)} GROUPS)**\n\n"
            f"{chr(10).join(lines)}{more}\n\n"
            f"💡 *Gõ `{self._pfx()}read group` để đánh dấu đã đọc tất cả nhóm này.*"
        )
        await autorep(ctx.message, content=content, auto_delete_delay=50)

    # ── ĐỌC VÀ QUẢN LÝ TIN NHẮN RIÊNG (DMS) ──────────────────────────────
    async def _handle_read_dms(self, ctx: commands.Context) -> None:
        """Đánh dấu đã đọc tất cả tin nhắn riêng cá nhân (DMs)."""
        dms = [c for c in self.bot.private_channels if isinstance(c, discord.DMChannel)]
        if not dms:
            await autorep(ctx.message, content="ℹ️ Tài khoản hiện không có cuộc trò chuyện riêng (DM) nào.", auto_delete_delay=20)
            return

        wait_msg = await autorep(ctx.message, content=f"⏳ Đang đánh dấu đã đọc trên **{len(dms)}** cuộc trò chuyện riêng...", auto_delete_delay=None)
        success: List[discord.DMChannel] = []
        failed: List[discord.DMChannel] = []

        for ch in dms:
            try:
                if hasattr(ch, "ack"):
                    await ch.ack()
                elif hasattr(ch, "last_message_id") and ch.last_message_id:
                    await self.bot.http.ack_message(ch.id, ch.last_message_id)
                success.append(ch)
                await asyncio.sleep(0.1)
            except Exception:
                failed.append(ch)

        if wait_msg:
            try:
                await wait_msg.delete()
            except Exception:
                pass

        user_names = []
        for ch in success[:10]:
            recipient = getattr(ch, "recipient", None)
            u_name = str(recipient) if recipient else f"ID: {ch.id}"
            user_names.append(f"• 👤 **{u_name}** (`{ch.id}`)")

        more = f"\n*...và {len(success) - 10} cuộc trò chuyện khác*" if len(success) > 10 else ""
        list_str = "\n".join(user_names) if user_names else "*Không có cuộc trò chuyện nào*"

        res = (
            f"🎉 **ĐÃ ĐÁNH DẤU ĐÃ ĐỌC TIN NHẮN RIÊNG (DMS) XONG!**\n\n"
            f"📊 **Kết quả:** Đã đọc **{len(success)}** / **{len(dms)}** cuộc trò chuyện cá nhân\n\n"
            f"📋 **DANH SÁCH NGƯỜI DÙNG ĐÃ ĐỌC:**\n{list_str}{more}"
        )
        await autorep(ctx.message, content=res, auto_delete_delay=40)

    async def _handle_dm_list(self, ctx: commands.Context) -> None:
        """Hiển thị danh sách các cuộc trò chuyện riêng (DMs)."""
        dms = [c for c in self.bot.private_channels if isinstance(c, discord.DMChannel)]
        if not dms:
            await autorep(ctx.message, content="ℹ️ Tài khoản hiện không có cuộc trò chuyện riêng (DM) nào.", auto_delete_delay=20)
            return

        lines = []
        for i, ch in enumerate(dms[:25], 1):
            recipient = getattr(ch, "recipient", None)
            u_name = f"{recipient.name}#{recipient.discriminator}" if (recipient and getattr(recipient, "discriminator", "0") != "0") else (getattr(recipient, "name", "Người dùng") if recipient else f"ID: {ch.id}")
            lines.append(f"{i}. 👤 **{u_name}** (`{ch.id}`)")

        more = f"\n*...và còn {len(dms) - 25} người khác.*" if len(dms) > 25 else ""
        content = (
            f"👤 **DANH SÁCH TIN NHẮN RIÊNG ({len(dms)} USERS)**\n\n"
            f"{chr(10).join(lines)}{more}\n\n"
            f"💡 *Gõ `{self._pfx()}read user` để đánh dấu đã đọc tất cả tin nhắn riêng này.*"
        )
        await autorep(ctx.message, content=content, auto_delete_delay=50)


async def setup(bot: commands.Bot):
    await bot.add_cog(ReadCog(bot))
