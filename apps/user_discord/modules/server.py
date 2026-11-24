# -*- coding: utf-8 -*-
"""
server.py - Module trung tâm điều khiển & quản trị máy chủ Discord (Server Manager).
Hỗ trợ đổi tên, icon, banner, quản lý role, kênh (channels), setting và hiển thị thẻ Info đồ họa.
Phân quyền: Admin (admins) và Admin cấp cao (admintris).
"""
from __future__ import annotations

import asyncio
import io
import os
import random
import re
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
    from apps.user_discord.core.alias import alias_declare
except ImportError:
    from core.bot_sys import require_permission
    from utils.autorep import autorep
    from utils.menu_catalog import menu_entry
    from utils.prefix import get_prefix
    try:
        from core.alias import alias_declare
    except ImportError:
        def alias_declare(*args, **kwargs):
            return lambda f: f


def _parse_color(val: str) -> Optional[discord.Color]:
    """Phân tích mã màu hex (vd: #ff0000, ff0000, red, blue...)."""
    v = val.strip().lstrip("#")
    if len(v) == 6:
        try:
            return discord.Color(int(v, 16))
        except ValueError:
            pass
    named = {
        "red": discord.Color.red(),
        "green": discord.Color.green(),
        "blue": discord.Color.blue(),
        "gold": discord.Color.gold(),
        "purple": discord.Color.purple(),
        "magenta": discord.Color.magenta(),
        "cyan": discord.Color.teal(),
        "yellow": discord.Color.yellow(),
    }
    return named.get(v.lower())


class ServerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.font_bold = str(SHARED_FONTS_DIR / "BeVietnamPro-Bold.ttf")
        self.font_reg = str(SHARED_FONTS_DIR / "BeVietnamPro-Regular.ttf")

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return getattr(self.bot, "_own_prefix", None) or ""

    # ── KIỂM TRA QUYỀN HẠN CỦA BOT ───────────────────────────────────────
    @staticmethod
    def _check_bot_perms(guild: discord.Guild, **perms) -> Tuple[bool, List[str]]:
        me = guild.me
        if not me:
            return False, ["Bot không hiện diện trong máy chủ"]
        my_perms = me.guild_permissions
        missing = [p for p, required in perms.items() if required and not getattr(my_perms, p, False)]
        return len(missing) == 0, missing

    # ── TẢI ẢNH BUFFER TỪ URL HOẶC ĐÍNH KÈM ──────────────────────────────
    @staticmethod
    async def _fetch_image_bytes(message: discord.Message, url: Optional[str] = None) -> Optional[bytes]:
        if message.attachments:
            att = message.attachments[0]
            if att.content_type and att.content_type.startswith("image/"):
                try:
                    return await att.read()
                except Exception:
                    pass
        if url:
            clean_url = url.strip("<> ")
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(clean_url, timeout=aiohttp.ClientTimeout(total=8.0)) as r:
                        if r.status == 200:
                            return await r.read()
            except Exception:
                pass
        return None

    # ── VẼ THẺ THÔNG TIN SERVER (SERVER INFO CARD) ───────────────────────
    async def render_server_info_card(self, guild: discord.Guild) -> io.BytesIO:
        """Thẻ thông tin server — LIQUID GLASS ngang. Lỗi -> bản cũ."""
        try:
            try:
                from apps.user_discord.utils import glass as G
            except ImportError:
                from utils import glass as G
            icon = await G.fetch_image(str(guild.icon.url)) if guild.icon else None
            info = {
                "pfx": self._pfx(),
                "name": guild.name or "Server",
                "id": guild.id,
                "created": guild.created_at.strftime("%d/%m/%Y") if guild.created_at else "?",
                "members": guild.member_count or len(guild.members),
                "text": len(guild.text_channels),
                "voice": len(guild.voice_channels),
                "roles": len(guild.roles),
                "tier": guild.premium_tier or 0,
                "boosts": guild.premium_subscription_count or 0,
            }
            return await asyncio.to_thread(self._draw_server_glass, G, info, icon)
        except Exception as e:
            print(f"[server] liquid glass lỗi, dùng bản cũ: {type(e).__name__}: {e}")
            return await self._render_server_info_card_legacy(guild)

    @staticmethod
    def _draw_server_glass(G, info: Dict[str, Any], icon) -> io.BytesIO:
        p = f"{info['pfx']}server"
        pad, gap, head_h, stat_h = 24, 16, 108, 80
        LW = 1180
        row_h = 52
        sec_h = G.GlassCanvas.section_height(4, row_h)
        LH = pad + head_h + gap + stat_h + gap + sec_h + pad
        cv = G.GlassCanvas(LW, LH)

        # ── header: icon + tên + id ──
        cv.glass((pad, pad, LW - pad, pad + head_h), 24, blur=24)
        isz = 72
        cv.circle_image(icon, pad + 20, pad + (head_h - isz) / 2, isz, ring=G.G_BLUE, ring_w=3,
                        letter=info["name"][:1])
        f_b = cv.font("b", 11)
        tier_txt = f"BOOST LV {info['tier']}" if info["tier"] else "CHƯA BOOST"
        tier_w = cv.tlen(tier_txt, cv.font("b", 12)) + 46
        tx = pad + 20 + isz + 18
        tmax = LW - pad - 20 - tier_w - 12 - tx
        f_t = cv.font("modak", 24)
        name = cv.fit(G.clean_text(info["name"]) or "Server", f_t, tmax - 80)
        tw = cv.text(tx, pad + head_h / 2 - 14, name, f_t, G.C_TEXT, vcenter=True)
        cv.pill(tx + tw + 14, pad + head_h / 2 - 24, "ADMIN", f_b, G.G_AMBER, h=20, padx=10)
        cv.text(tx, pad + head_h / 2 + 16, f"ID: {info['id']}   •   Tạo ngày {info['created']}",
                cv.font("r", 12.5), G.C_MUTED, vcenter=True)
        cv.glass_pill(LW - pad - 20, pad + head_h / 2 - 15, tier_txt, cv.font("b", 12), G.G_PURPLE,
                      align="r", dot=(244, 194, 255))

        # ── 4 ô thống kê ──
        sy = pad + head_h + gap
        stats = [
            ("THÀNH VIÊN", f"{info['members']:,} người", "👥", "M", (96, 165, 250)),
            ("KÊNH", f"{info['text']} text  •  {info['voice']} voice", "💬", "K", (52, 211, 153)),
            ("VAI TRÒ", f"{info['roles']} roles", "🛡", "R", (167, 139, 250)),
            ("NITRO BOOST", f"{info['boosts']} boosts", "🚀", "B", (244, 114, 182)),
        ]
        tw_ = (LW - 2 * pad - 3 * gap) / 4
        for i, (lbl, val, sym, fb, col) in enumerate(stats):
            x1 = pad + i * (tw_ + gap)
            cv.glass((x1, sy, x1 + tw_, sy + stat_h), 20, blur=22, tint=(12, 16, 28, 50))
            cv.chip((x1 + 16, sy + 20, x1 + 56, sy + 60), sym, fb, col, r=12, size=19)
            vx = x1 + 70
            cv.text(vx, sy + 30, lbl, cv.font("b", 10.5), col, vcenter=True)
            cv.text(vx, sy + 52, cv.fit(val, cv.font("b", 14), x1 + tw_ - 14 - vx), cv.font("b", 14),
                    G.C_TEXT, vcenter=True)

        # ── 3 cột lệnh ──
        top = sy + stat_h + gap
        cw = (LW - 2 * pad - 2 * gap) / 3
        cols = [
            ("MÁY CHỦ", "Thông tin • tên • icon", G.G_BLUE, [
                (f"{p} info", "Hiện thẻ thông tin này"),
                (f"{p} name <tên mới>", "Đổi tên máy chủ"),
                (f"{p} icon <link/ảnh>", "Đổi icon (đính kèm ảnh / link)"),
                (f"{p} icon clear", "Xoá icon máy chủ"),
            ]),
            ("ROLE", "Tạo • xoá • trao • gỡ", G.G_PURPLE, [
                (f"{p} role create <tên> [màu]", "Tạo role mới (mã màu hex)"),
                (f"{p} role delete <tên/id>", "Xoá role"),
                (f"{p} role give @user <role>", "Trao role cho thành viên"),
                (f"{p} role remove @user <role>", "Gỡ role khỏi thành viên"),
            ]),
            ("KÊNH", "Tạo • xoá • đổi tên • slowmode", G.G_GREEN, [
                (f"{p} channel create <text|voice> <tên>", "Tạo kênh mới"),
                (f"{p} channel delete [id/tên]", "Xoá kênh (trống = kênh này)"),
                (f"{p} channel rename <tên mới>", "Đổi tên kênh hiện tại"),
                (f"{p} channel slowmode <giây>", "Đặt chế độ chậm"),
            ]),
        ]
        for i, (title, sub, grad, rows) in enumerate(cols):
            x1 = pad + i * (cw + gap)
            cv.section(x1, top, x1 + cw, title, sub, grad, rows, row_h=row_h)
        return cv.finalize()

    async def _render_server_info_card_legacy(self, guild: discord.Guild) -> io.BytesIO:
        w, h = 640, 480
        pfx = self._pfx()

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
                    dim = Image.new("RGBA", (w, h), (10, 12, 18, 205))
                    base_img = Image.alpha_composite(base_img, dim)
                except Exception:
                    pass

        draw = ImageDraw.Draw(base_img)
        draw.rounded_rectangle([16, 16, w - 16, h - 16], radius=20, fill=(20, 25, 35, 225), outline=(55, 70, 100, 180), width=1)

        f_title = ImageFont.truetype(self.font_bold, 20)
        f_sub = ImageFont.truetype(self.font_reg, 12)
        f_bold = ImageFont.truetype(self.font_bold, 13)
        f_text = ImageFont.truetype(self.font_reg, 13)
        f_badge = ImageFont.truetype(self.font_bold, 11)

        # Avatar server
        icon_size = 72
        ix, iy = 36, 36
        loaded_icon = None
        if guild.icon:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(str(guild.icon.url), timeout=aiohttp.ClientTimeout(total=3.0)) as r:
                        if r.status == 200:
                            raw_b = await r.read()
                            with Image.open(io.BytesIO(raw_b)) as im:
                                loaded_icon = im.convert("RGBA")
            except Exception:
                loaded_icon = None

        if loaded_icon:
            try:
                c_icon = ImageOps.fit(loaded_icon, (icon_size, icon_size), method=Image.Resampling.BILINEAR)
                mask = Image.new("L", (icon_size, icon_size), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, icon_size, icon_size), fill=255)
                base_img.paste(c_icon, (ix, iy), mask)
                draw.ellipse([ix, iy, ix + icon_size, iy + icon_size], outline=(96, 165, 250), width=2)
            except Exception:
                loaded_icon = None

        if not loaded_icon:
            draw.ellipse([ix, iy, ix + icon_size, iy + icon_size], fill=(45, 60, 85), outline=(96, 165, 250), width=2)
            initial = guild.name[0].upper() if guild.name else "G"
            fw = int(draw.textlength(initial, font=f_title))
            draw.text((ix + (icon_size - fw) // 2, iy + 22), initial, font=f_title, fill=(255, 255, 255))

        # Header Title
        tx = ix + icon_size + 16
        g_name = guild.name
        while draw.textlength(g_name, font=f_title) > (w - tx - 40) and len(g_name) > 3:
            g_name = g_name[:-2] + "…"
        draw.text((tx, iy + 6), g_name, font=f_title, fill=(255, 255, 255))
        draw.text((tx, iy + 34), f"ID: {guild.id} • Tạo ngày: {guild.created_at.strftime('%d/%m/%Y')}", font=f_sub, fill=(148, 163, 184))

        # Đường kẻ
        draw.line([36, 126, w - 36, 126], fill=(50, 65, 90, 160), width=1)

        # 4 Hộp Thống kê (Grid 2x2)
        total_members = guild.member_count or len(guild.members)
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        roles_count = len(guild.roles)
        boost_tier = f"Level {guild.premium_tier}" if guild.premium_tier else "Chưa boost"

        stats = [
            ("👥 THÀNH VIÊN", f"{total_members:,} người", (96, 165, 250)),
            ("💬 KÊNH CHAT / VOICE", f"{text_channels} text • {voice_channels} voice", (52, 211, 153)),
            ("🛡️ VAI TRÒ (ROLES)", f"{roles_count} roles", (167, 139, 250)),
            ("🚀 NITRO BOOST", f"{boost_tier} ({guild.premium_subscription_count} boosts)", (244, 114, 182)),
        ]

        bx, by = 36, 142
        box_w = (w - 72 - 16) // 2
        box_h = 60

        for idx, (label, val, col) in enumerate(stats):
            r = idx // 2
            c = idx % 2
            cx = bx + c * (box_w + 16)
            cy = by + r * (box_h + 12)
            draw.rounded_rectangle([cx, cy, cx + box_w, cy + box_h], radius=10, fill=(28, 35, 48, 190), outline=(48, 62, 88, 120), width=1)
            draw.text((cx + 12, cy + 10), label, font=f_badge, fill=col)
            draw.text((cx + 12, cy + 28), val, font=f_bold, fill=(240, 245, 255))

        # Bảng lệnh hỗ trợ
        qy = by + (box_h * 2) + 24
        draw.line([36, qy, w - 36, qy], fill=(50, 65, 90, 160), width=1)
        draw.text((36, qy + 12), "🛠️ CÁC LỆNH ĐIỀU KHIỂN MÁY CHỦ NHANH:", font=f_bold, fill=(251, 191, 36))

        cmds_quick = [
            f"`{pfx}server name <tên>`: Đổi tên server",
            f"`{pfx}server icon <link/ảnh>`: Đổi icon",
            f"`{pfx}server role create/delete`: Quản lý role",
            f"`{pfx}server channel create/delete`: Quản lý kênh",
        ]
        for i, cq in enumerate(cmds_quick):
            col_idx = i % 2
            row_idx = i // 2
            px = 36 + col_idx * (box_w + 16)
            py = qy + 36 + row_idx * 24
            draw.text((px, py), cq, font=f_text, fill=(203, 213, 225))

        buf = io.BytesIO()
        base_img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    # ── NHÓM LỆNH: (prefix)server ────────────────────────────────────────
    @menu_entry("SYSTEM & SECURITY", "server", "Quản lý & điều khiển server toàn diện (Role/Kênh/Tên)",
                badge="ADMIN", icon_sym="🛡️", icon_color=(251, 191, 36), order=6)
    @alias_declare("server", main="server", subs=["guild"])
    @commands.group(name="server", aliases=["guild"], invoke_without_command=True)
    @require_permission("admin")
    async def server_cmd(self, ctx: commands.Context, *, sub: Optional[str] = None):
        """Quản trị máy chủ: (prefix)server <info|name|icon|banner|role|channel>"""
        if not ctx.guild:
            await autorep(ctx.message, content="❌ Lệnh này chỉ hoạt động bên trong **Máy chủ (Guild)**.", auto_delete_delay=20)
            return

        if not sub or sub.strip().lower() in ("info", "card"):
            # Gửi thẻ ảnh thông tin server
            try:
                buf = await self.render_server_info_card(ctx.guild)
                file = discord.File(buf, filename="server_info.png")
                await autorep(ctx.message, content="", file=file, auto_delete_delay=45)
            except Exception as e:
                await autorep(ctx.message, content=f"❌ Lỗi vẽ thẻ thông tin server: {e}", auto_delete_delay=25)
            return

        # Nếu gõ lệnh con không nằm trong group: hướng dẫn
        await autorep(
            ctx.message,
            content=f"❓ Lệnh không hợp lệ. Gõ `{self._pfx()}server info` để xem bảng điều khiển hoặc `{self._pfx()}help server`.",
            auto_delete_delay=20,
        )

    # ── 1. ĐỔI TÊN SERVER ────────────────────────────────────────────────
    @server_cmd.command(name="name", aliases=["rename", "setname"])
    @require_permission("admin")
    async def server_rename(self, ctx: commands.Context, *, new_name: str):
        """Đổi tên máy chủ: (prefix)server name <tên mới>"""
        if not ctx.guild:
            return
        ok, missing = self._check_bot_perms(ctx.guild, manage_guild=True)
        if not ok:
            await autorep(ctx.message, content="⛔ **Bot thiếu quyền:** Yêu cầu quyền `Quản lý máy chủ (Manage Server)`.", auto_delete_delay=25)
            return

        old_name = ctx.guild.name
        try:
            await ctx.guild.edit(name=new_name.strip())
            await autorep(
                ctx.message,
                content=f"✅ Đã đổi tên máy chủ thành công!\n• Cũ: **{old_name}**\n• Mới: **{new_name.strip()}**",
                auto_delete_delay=30,
            )
        except Exception as e:
            await autorep(ctx.message, content=f"❌ Không thể đổi tên server: {type(e).__name__} ({e})", auto_delete_delay=25)

    # ── 2. ĐỔI ICON SERVER ───────────────────────────────────────────────
    @server_cmd.command(name="icon", aliases=["seticon"])
    @require_permission("admin")
    async def server_icon(self, ctx: commands.Context, *, url: Optional[str] = None):
        """Đổi avatar máy chủ: (prefix)server icon <link/ảnh đính kèm/clear>"""
        if not ctx.guild:
            return
        ok, missing = self._check_bot_perms(ctx.guild, manage_guild=True)
        if not ok:
            await autorep(ctx.message, content="⛔ **Bot thiếu quyền:** Yêu cầu quyền `Quản lý máy chủ (Manage Server)`.", auto_delete_delay=25)
            return

        if url and url.strip().lower() in ("clear", "xoa", "xóa", "remove"):
            try:
                await ctx.guild.edit(icon=None)
                await autorep(ctx.message, content="✅ Đã xóa icon máy chủ.", auto_delete_delay=25)
            except Exception as e:
                await autorep(ctx.message, content=f"❌ Lỗi khi xóa icon: {e}", auto_delete_delay=25)
            return

        data = await self._fetch_image_bytes(ctx.message, url)
        if not data:
            await autorep(ctx.message, content="❌ Vui lòng đính kèm một file ảnh hoặc cung cấp link ảnh hợp lệ.", auto_delete_delay=20)
            return

        try:
            await ctx.guild.edit(icon=data)
            await autorep(ctx.message, content=f"✅ Đã cập nhật icon mới cho máy chủ **{ctx.guild.name}** thành công!", auto_delete_delay=30)
        except Exception as e:
            await autorep(ctx.message, content=f"❌ Không thể đổi icon: {type(e).__name__} ({e})", auto_delete_delay=25)

    # ── 3. QUẢN LÝ ROLE ──────────────────────────────────────────────────
    @server_cmd.group(name="role", invoke_without_command=True)
    @require_permission("admin")
    async def server_role(self, ctx: commands.Context, *, subcmd: Optional[str] = None):
        """Quản lý Role: (prefix)server role <create|delete|color|give|remove>"""
        p = self._pfx()
        guide = (
            "🛡️ **QUẢN LÝ VAI TRÒ (ROLE MANAGER)**\n"
            f"• `{p}server role create <tên> [màu_hex]`: Tạo role mới\n"
            f"• `{p}server role delete <tên/id>`: Xóa role\n"
            f"• `{p}server role color <tên/id> <màu_hex>`: Đổi màu role\n"
            f"• `{p}server role give <@user> <tên/id role>`: Trao role cho thành viên\n"
            f"• `{p}server role remove <@user> <tên/id role>`: Gỡ role khỏi thành viên"
        )
        await autorep(ctx.message, content=guide, auto_delete_delay=30)

    @server_role.command(name="create")
    @require_permission("admin")
    async def role_create(self, ctx: commands.Context, name: str, color_str: Optional[str] = None):
        """Tạo role: (prefix)server role create <tên> [mã_màu]"""
        if not ctx.guild:
            return
        ok, missing = self._check_bot_perms(ctx.guild, manage_roles=True)
        if not ok:
            await autorep(ctx.message, content="⛔ **Bot thiếu quyền:** Yêu cầu quyền `Quản lý vai trò (Manage Roles)`.", auto_delete_delay=25)
            return

        col = _parse_color(color_str) if color_str else discord.Color.default()
        try:
            r = await ctx.guild.create_role(name=name, color=col or discord.Color.default(), reason=f"Tạo bởi {ctx.author}")
            await autorep(ctx.message, content=f"✅ Đã tạo vai trò mới: **{r.name}** (`{r.id}`)", auto_delete_delay=25)
        except Exception as e:
            await autorep(ctx.message, content=f"❌ Không thể tạo role: {type(e).__name__} ({e})", auto_delete_delay=25)

    @server_role.command(name="delete")
    @require_permission("admin")
    async def role_delete(self, ctx: commands.Context, *, role_target: str):
        """Xóa role: (prefix)server role delete <tên/id>"""
        if not ctx.guild:
            return
        ok, missing = self._check_bot_perms(ctx.guild, manage_roles=True)
        if not ok:
            await autorep(ctx.message, content="⛔ **Bot thiếu quyền:** Yêu cầu quyền `Quản lý vai trò (Manage Roles)`.", auto_delete_delay=25)
            return

        target_role = self._find_role(ctx.guild, role_target)
        if not target_role:
            await autorep(ctx.message, content=f"❌ Không tìm thấy role nào khớp với `{role_target}`.", auto_delete_delay=20)
            return

        me = ctx.guild.me
        if me and target_role >= me.top_role:
            await autorep(ctx.message, content=f"⛔ Vai trò **{target_role.name}** cao hơn hoặc ngang bằng vai trò cao nhất của bot. Không thể xóa!", auto_delete_delay=25)
            return

        try:
            r_name = target_role.name
            await target_role.delete(reason=f"Xóa bởi {ctx.author}")
            await autorep(ctx.message, content=f"✅ Đã xóa vai trò **{r_name}** thành công.", auto_delete_delay=25)
        except Exception as e:
            await autorep(ctx.message, content=f"❌ Không thể xóa role: {type(e).__name__} ({e})", auto_delete_delay=25)

    @server_role.command(name="give")
    @require_permission("admin")
    async def role_give(self, ctx: commands.Context, member: discord.Member, *, role_target: str):
        """Trao role: (prefix)server role give <@user> <tên/id role>"""
        if not ctx.guild:
            return
        ok, missing = self._check_bot_perms(ctx.guild, manage_roles=True)
        if not ok:
            await autorep(ctx.message, content="⛔ **Bot thiếu quyền:** Yêu cầu quyền `Quản lý vai trò (Manage Roles)`.", auto_delete_delay=25)
            return

        target_role = self._find_role(ctx.guild, role_target)
        if not target_role:
            await autorep(ctx.message, content=f"❌ Không tìm thấy role `{role_target}`.", auto_delete_delay=20)
            return

        me = ctx.guild.me
        if me and target_role >= me.top_role:
            await autorep(ctx.message, content=f"⛔ Vai trò **{target_role.name}** nằm trên quyền quản lý của bot.", auto_delete_delay=25)
            return

        try:
            await member.add_roles(target_role, reason=f"Trao bởi {ctx.author}")
            await autorep(ctx.message, content=f"✅ Đã trao vai trò **{target_role.name}** cho {member.mention}.", auto_delete_delay=25)
        except Exception as e:
            await autorep(ctx.message, content=f"❌ Lỗi khi trao role: {type(e).__name__} ({e})", auto_delete_delay=25)

    @server_role.command(name="remove")
    @require_permission("admin")
    async def role_remove(self, ctx: commands.Context, member: discord.Member, *, role_target: str):
        """Gỡ role: (prefix)server role remove <@user> <tên/id role>"""
        if not ctx.guild:
            return
        ok, missing = self._check_bot_perms(ctx.guild, manage_roles=True)
        if not ok:
            await autorep(ctx.message, content="⛔ **Bot thiếu quyền:** Yêu cầu quyền `Quản lý vai trò (Manage Roles)`.", auto_delete_delay=25)
            return

        target_role = self._find_role(ctx.guild, role_target)
        if not target_role:
            await autorep(ctx.message, content=f"❌ Không tìm thấy role `{role_target}`.", auto_delete_delay=20)
            return

        try:
            await member.remove_roles(target_role, reason=f"Gỡ bởi {ctx.author}")
            await autorep(ctx.message, content=f"✅ Đã gỡ vai trò **{target_role.name}** khỏi {member.mention}.", auto_delete_delay=25)
        except Exception as e:
            await autorep(ctx.message, content=f"❌ Lỗi khi gỡ role: {type(e).__name__} ({e})", auto_delete_delay=25)

    # ── 4. QUẢN LÝ KÊNH (CHANNELS) ───────────────────────────────────────
    @server_cmd.group(name="channel", aliases=["chan"], invoke_without_command=True)
    @require_permission("admin")
    async def server_channel(self, ctx: commands.Context):
        """Quản lý Kênh: (prefix)server channel <create|delete|rename|slowmode>"""
        p = self._pfx()
        guide = (
            "💬 **QUẢN LÝ KÊNH (CHANNEL MANAGER)**\n"
            f"• `{p}server channel create <text|voice> <tên>`: Tạo kênh chat hoặc voice\n"
            f"• `{p}server channel delete [tên/id/kênh hiện tại]`: Xóa kênh\n"
            f"• `{p}server channel rename <tên mới>`: Đổi tên kênh hiện tại\n"
            f"• `{p}server channel slowmode <số giây>`: Đặt chế độ chậm cho kênh"
        )
        await autorep(ctx.message, content=guide, auto_delete_delay=30)

    @server_channel.command(name="create")
    @require_permission("admin")
    async def channel_create(self, ctx: commands.Context, ctype: str, *, name: str):
        """Tạo kênh: (prefix)server channel create <text|voice> <tên>"""
        if not ctx.guild:
            return
        ok, missing = self._check_bot_perms(ctx.guild, manage_channels=True)
        if not ok:
            await autorep(ctx.message, content="⛔ **Bot thiếu quyền:** Yêu cầu quyền `Quản lý kênh (Manage Channels)`.", auto_delete_delay=25)
            return

        t = ctype.strip().lower()
        try:
            if t in ("voice", "vc", "thoai"):
                ch = await ctx.guild.create_voice_channel(name=name, reason=f"Tạo bởi {ctx.author}")
                await autorep(ctx.message, content=f"✅ Đã tạo kênh Voice: **{ch.name}** (`{ch.id}`)", auto_delete_delay=25)
            else:
                ch = await ctx.guild.create_text_channel(name=name, reason=f"Tạo bởi {ctx.author}")
                await autorep(ctx.message, content=f"✅ Đã tạo kênh Text: {ch.mention} (`{ch.id}`)", auto_delete_delay=25)
        except Exception as e:
            await autorep(ctx.message, content=f"❌ Không thể tạo kênh: {type(e).__name__} ({e})", auto_delete_delay=25)

    @server_channel.command(name="delete")
    @require_permission("admin")
    async def channel_delete(self, ctx: commands.Context, *, channel_target: Optional[str] = None):
        """Xóa kênh: (prefix)server channel delete [id/tên/kênh hiện tại]"""
        if not ctx.guild:
            return
        ok, missing = self._check_bot_perms(ctx.guild, manage_channels=True)
        if not ok:
            await autorep(ctx.message, content="⛔ **Bot thiếu quyền:** Yêu cầu quyền `Quản lý kênh (Manage Channels)`.", auto_delete_delay=25)
            return

        target_ch = None
        if not channel_target:
            target_ch = ctx.channel
        elif channel_target.isdigit():
            target_ch = ctx.guild.get_channel(int(channel_target))
        else:
            low = channel_target.lower().lstrip("#")
            for c in ctx.guild.channels:
                if c.name.lower() == low:
                    target_ch = c
                    break

        if not target_ch:
            await autorep(ctx.message, content=f"❌ Không tìm thấy kênh `{channel_target}`.", auto_delete_delay=20)
            return

        try:
            c_name = target_ch.name
            await target_ch.delete(reason=f"Xóa bởi {ctx.author}")
            # Nếu xóa kênh khác kênh hiện tại thì rep báo
            if target_ch.id != ctx.channel.id:
                await autorep(ctx.message, content=f"✅ Đã xóa kênh **#{c_name}** thành công.", auto_delete_delay=25)
        except Exception as e:
            await autorep(ctx.message, content=f"❌ Lỗi khi xóa kênh: {type(e).__name__} ({e})", auto_delete_delay=25)

    @server_channel.command(name="rename")
    @require_permission("admin")
    async def channel_rename(self, ctx: commands.Context, *, new_name: str):
        """Đổi tên kênh hiện tại: (prefix)server channel rename <tên mới>"""
        if not ctx.guild:
            return
        ok, missing = self._check_bot_perms(ctx.guild, manage_channels=True)
        if not ok:
            await autorep(ctx.message, content="⛔ **Bot thiếu quyền:** Yêu cầu quyền `Quản lý kênh (Manage Channels)`.", auto_delete_delay=25)
            return

        old_n = ctx.channel.name
        try:
            await ctx.channel.edit(name=new_name.strip(), reason=f"Đổi bởi {ctx.author}")
            await autorep(ctx.message, content=f"✅ Đã đổi tên kênh từ **#{old_n}** ➔ **#{new_name.strip()}**", auto_delete_delay=25)
        except Exception as e:
            await autorep(ctx.message, content=f"❌ Không thể đổi tên kênh: {type(e).__name__} ({e})", auto_delete_delay=25)

    @server_channel.command(name="slowmode", aliases=["slow"])
    @require_permission("admin")
    async def channel_slowmode(self, ctx: commands.Context, seconds: int):
        """Đặt chế độ chậm cho kênh: (prefix)server channel slowmode <giây>"""
        if not ctx.guild:
            return
        ok, missing = self._check_bot_perms(ctx.guild, manage_channels=True)
        if not ok:
            await autorep(ctx.message, content="⛔ **Bot thiếu quyền:** Yêu cầu quyền `Quản lý kênh (Manage Channels)`.", auto_delete_delay=25)
            return

        if not isinstance(ctx.channel, discord.TextChannel):
            await autorep(ctx.message, content="❌ Slowmode chỉ áp dụng cho kênh Text Channel.", auto_delete_delay=20)
            return

        sec = max(0, min(seconds, 21600))
        try:
            await ctx.channel.edit(slowmode_delay=sec, reason=f"Slowmode chỉnh bởi {ctx.author}")
            if sec == 0:
                await autorep(ctx.message, content=f"✅ Đã tắt Slowmode cho kênh {ctx.channel.mention}.", auto_delete_delay=25)
            else:
                await autorep(ctx.message, content=f"⏱️ Đã đặt Slowmode **{sec} giây** cho kênh {ctx.channel.mention}.", auto_delete_delay=25)
        except Exception as e:
            await autorep(ctx.message, content=f"❌ Không thể đổi slowmode: {type(e).__name__} ({e})", auto_delete_delay=25)

    # ── HELPER TÌM ROLE ──────────────────────────────────────────────────
    @staticmethod
    def _find_role(guild: discord.Guild, query: str) -> Optional[discord.Role]:
        q = query.strip()
        # Tìm theo mention <@&ID>
        if q.startswith("<@&") and q.endswith(">"):
            raw_id = "".join(ch for ch in q if ch.isdigit())
            if raw_id:
                return guild.get_role(int(raw_id))
        if q.isdigit():
            r = guild.get_role(int(q))
            if r:
                return r
        low = q.lower()
        for r in guild.roles:
            if r.name.lower() == low:
                return r
        for r in guild.roles:
            if low in r.name.lower() and not r.is_default():
                return r
        return None


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerCog(bot))
