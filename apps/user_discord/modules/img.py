# -*- coding: utf-8 -*-
"""
MODULE: img (Image Processing Studio & Utilities)
- Lệnh chính: (prefix)img, (prefix)image, (prefix)anh
- Nhóm lệnh đa năng với các tham số đằng sau:
  • (prefix)img : Xem bảng hướng dẫn Liquid Glass Studio.
  • (prefix)img qr <link | văn bản> : Tạo mã QR Liquid Glass sắc nét.
  • (prefix)img avt [@user | uid] : Lấy avatar gốc phân giải tối đa (1024/2048px).
  • (prefix)img banner [@user | uid] : Lấy ảnh bìa profile / banner server HD.
  • (prefix)img resize <WxH> : Đổi kích thước ảnh (VD: 800x600, 1920x1080).
  • (prefix)img blur [1-30] : Làm mờ ảnh nghệ thuật (Gaussian Blur).
  • (prefix)img gray : Chuyển ảnh sang đen trắng nghệ thuật (Grayscale).
  • (prefix)img invert : Đảo màu âm bản (Negative / Invert).
  • (prefix)img circle : Cắt ảnh hình tròn bo viền dạ quang trong suốt.
  • (prefix)img info : Xem thông số chi tiết của ảnh (kích thước, định dạng, dung lượng).
* Tất cả lệnh xử lý ảnh đều hỗ trợ: reply ảnh, đính kèm ảnh hoặc dán link ảnh!
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple, Union

import discord
from discord.ext import commands
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps
import requests
import qrcode

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


class ImageModule(commands.Cog, name="Image"):
    """Module xử lý ảnh, tạo QR và trích xuất Avatar/Banner dạng Studio chuyên nghiệp."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return "."

    # ── TÌM ẢNH TỪ CONTEXT (ATTACHMENT, REPLY HOẶC URL) ────────────────────
    async def _resolve_image(self, ctx: commands.Context, arg_url: Optional[str] = None) -> Optional[Tuple[bytes, str]]:
        """Trả về (image_bytes, filename) từ attachment, reply hoặc URL."""
        # 1. Attachment trong tin nhắn hiện tại
        if ctx.message.attachments:
            att = ctx.message.attachments[0]
            if any(att.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"]):
                data = await att.read()
                return data, att.filename

        # 2. Reply tin nhắn
        if ctx.message.reference and ctx.message.reference.message_id:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if ref_msg.attachments:
                    for att in ref_msg.attachments:
                        if any(att.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"]):
                            data = await att.read()
                            return data, att.filename
                if ref_msg.content:
                    links = re.findall(r'https?://[^\s]+', ref_msg.content)
                    for l in links:
                        if any(l.lower().split("?")[0].endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]):
                            loop = asyncio.get_running_loop()
                            res = await loop.run_in_executor(None, self.session.get, l)
                            if res.status_code == 200:
                                fn = l.split("/")[-1].split("?")[0] or "image.png"
                                return res.content, fn
            except Exception:
                pass

        # 3. URL trong tham số
        if arg_url:
            links = re.findall(r'https?://[^\s]+', arg_url)
            if links:
                target_url = links[0]
                loop = asyncio.get_running_loop()
                try:
                    res = await loop.run_in_executor(None, self.session.get, target_url)
                    if res.status_code == 200:
                        fn = target_url.split("/")[-1].split("?")[0] or "image.png"
                        return res.content, fn
                except Exception:
                    pass

        return None

    # ── NHÓM LỆNH CHÍNH (PREFIX)IMG / IMAGE / ANH ──────────────────────────
    @menu_entry("AI & TIỆN ÍCH", "img", "Bo cong cu xu ly anh, tao QR va Avatar HD",
                badge="HOT", icon_sym="🖼️", icon_color=(236, 72, 153), order=6)
    @alias_declare("img", ["image", "anh"])
    @commands.group(
        name="img",
        aliases=["image", "anh"],
        invoke_without_command=True,
        help="Bo cong cu xu ly anh, tao ma QR va trich xuat Avatar/Banner HD."
    )
    async def cmd_img(self, ctx: commands.Context, *, extra: Optional[str] = None):
        """Mở bảng hướng dẫn Liquid Glass Studio nếu không có lệnh con."""
        pfx = self._pfx()
        card_buf = await async_help_card("img", pfx)
        if card_buf:
            card_file = discord.File(card_buf, filename="img_studio_guide.png")
            await autorep(
                ctx.message,
                content="🖼️ **BỘ CÔNG CỤ XỬ LÝ ẢNH & TIỆN ÍCH (IMG STUDIO)**",
                file=card_file,
                auto_delete_delay=60
            )
        else:
            msg = await autorep(
                ctx.message,
                f"🖼️ **HƯỚNG DẪN SỬ DỤNG NHÓM LỆNH IMG**\n"
                f"• `{pfx}img qr <link|chữ>` : Tạo mã QR Liquid Glass\n"
                f"• `{pfx}img avt [@user]` : Tải Avatar HD 2048px\n"
                f"• `{pfx}img banner [@user]` : Tải Banner Profile HD\n"
                f"• `{pfx}img resize <WxH>` : Đổi kích thước ảnh (VD: 800x600)\n"
                f"• `{pfx}img blur [1-30]` : Làm mờ ảnh nghệ thuật\n"
                f"• `{pfx}img gray` : Chuyển ảnh sang đen trắng\n"
                f"• `{pfx}img invert` : Đảo màu âm bản\n"
                f"• `{pfx}img circle` : Cắt tròn bo viền trong suốt\n"
                f"• `{pfx}img info` : Đọc thông số chi tiết ảnh"
            )
            autodelet(msg, delay=30)

    # ── LỆNH CON 1: TẠO MÃ QR (IMG QR) ─────────────────────────────────────
    @cmd_img.command(name="qr")
    async def sub_qr(self, ctx: commands.Context, *, content: Optional[str] = None):
        """Tạo mã QR Liquid Glass: (prefix)img qr <link | nội dung>"""
        pfx = self._pfx()
        if not content:
            # Kiểm tra nếu reply tin nhắn có text
            if ctx.message.reference and ctx.message.reference.message_id:
                try:
                    ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                    content = ref_msg.content
                except Exception:
                    pass

        if not content:
            msg = await autorep(ctx.message, f"❌ Cú pháp: `{pfx}img qr <link hoặc nội dung chữ>`")
            autodelet(msg, delay=15)
            return

        waiting = await autorep(ctx.message, "⏳ Đang kết xuất mã QR Liquid Glass...")
        autodelet(waiting, delay=10)

        loop = asyncio.get_running_loop()

        def _generate_qr_card():
            if G is None:
                raise RuntimeError("Liquid Glass không khả dụng.")

            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=2,
            )
            qr.add_data(content)
            qr.make(fit=True)
            qr_raw = qr.make_image(fill_color=(15, 23, 42), back_color=(255, 255, 255)).convert("RGBA")

            LW, LH = 860, 520
            pad = 20
            head_h = 70
            gap = 14
            cv = G.GlassCanvas(LW, LH, scale=2, out=1.35)

            cv.header(
                pad, pad, LW - pad, head_h,
                "QR CODE GENERATOR - HD MATRIX",
                f"Prefix {pfx}   •   Độ phân giải cao   •   Quét tức thì bằng Camera",
                tag="QR STUDIO",
                right_reserve=160
            )
            cv.pill(LW - pad - 16, pad + head_h / 2 - 14, "SCAN READY", cv.font("b", 12), G.G_GREEN, h=24, align="r")

            top = pad + head_h + gap
            bottom = LH - pad

            # Khối trái: Khung chứa QR
            qr_size = bottom - top
            cv.glass((pad, top, pad + qr_size, bottom), 16, blur=20, tint=(255, 255, 255, 220))
            # Dán mã QR vào giữa khung
            qr_scaled = qr_raw.resize((qr_size - 24, qr_size - 24), Image.Resampling.LANCZOS)
            cv.img(qr_scaled, pad + 12, top + 12)

            # Khối phải: Thông tin nội dung QR
            right_x1 = pad + qr_size + gap
            right_x2 = LW - pad
            cv.glass((right_x1, top, right_x2, bottom), 16, blur=20, tint=(16, 20, 34, 95))
            cv.grad((right_x1 + 4, top + 14, right_x1 + 8, bottom - 14), 2, (14, 165, 233), (99, 102, 241))

            cv.text(right_x1 + 24, top + 34, "NỘI DUNG MÃ QR", cv.font("b", 18), G.C_TEXT, vcenter=True)
            cv.pill(right_x1 + 24, top + 64, "DỮ LIỆU ĐÃ MÃ HÓA", cv.font("b", 11), G.G_BRAND, h=22, padx=10)

            # Preview nội dung text
            clean_display = content if len(content) <= 120 else content[:117] + "..."
            cv.text(right_x1 + 24, top + 110, "Giá trị quét được:", cv.font("r", 12), G.C_MUTED, vcenter=True)
            cv.text(right_x1 + 24, top + 138, cv.fit(clean_display, cv.font("r", 13), right_x2 - right_x1 - 40), cv.font("r", 13), G.C_GOLD, vcenter=True)

            # Capsule chỉ số
            info_top = top + 190
            cv.glass((right_x1 + 20, info_top, right_x2 - 20, bottom - 20), 12, blur=12, tint=(24, 28, 44, 90))
            cv.text(right_x1 + 36, info_top + 28, "Độ dài chuỗi:", cv.font("r", 12), G.C_MUTED, vcenter=True)
            cv.text(right_x2 - 36, info_top + 28, f"{len(content)} ký tự", cv.font("b", 13), G.C_TEXT, align="r", vcenter=True)
            cv.text(right_x1 + 36, info_top + 60, "Chuẩn mã hóa:", cv.font("r", 12), G.C_MUTED, vcenter=True)
            cv.text(right_x2 - 36, info_top + 60, "ISO/IEC 18004", cv.font("b", 13), (56, 189, 248), align="r", vcenter=True)

            return cv.finalize()

        try:
            buf = await loop.run_in_executor(None, _generate_qr_card)
            file = discord.File(buf, filename="qr_glass.png")
            sent = await autorep(
                ctx.message,
                content=f"📱 **MÃ QR LIQUID GLASS ĐÃ SẴN SÀNG QUÉT**\n🔗 Nội dung: `{content[:80]}`",
                file=file,
                auto_delete_delay=60
            )
            autodelet(sent, delay=60)
        except Exception as e:
            msg = await autorep(ctx.message, f"❌ Lỗi tạo mã QR: {str(e)[:100]}")
            autodelet(msg, delay=20)

    # ── LỆNH CON 2: TRÍCH XUẤT AVATAR HD (IMG AVT) ─────────────────────────
    @cmd_img.command(name="avt", aliases=["avatar", "pfp"])
    async def sub_avatar(self, ctx: commands.Context, *, target: Optional[str] = None):
        """Lấy Avatar HD 2048px của người dùng: (prefix)img avt [@user | uid]"""
        user = ctx.author
        if target:
            # Kiểm tra mention
            if ctx.message.mentions:
                user = ctx.message.mentions[0]
            else:
                target_clean = re.sub(r"[<@!>]", "", target.strip())
                if target_clean.isdigit():
                    try:
                        user = await self.bot.fetch_user(int(target_clean))
                    except Exception:
                        pass
                else:
                    # Tìm trong guild
                    if ctx.guild:
                        m = discord.utils.find(lambda x: x.name.lower() == target.lower() or (x.nick and x.nick.lower() == target.lower()), ctx.guild.members)
                        if m:
                            user = m

        avt_asset = user.avatar or user.default_avatar
        avt_url = avt_asset.replace(size=2048, static_format="png").url

        caption = (
            f"🖼️ **AVATAR FULL HD 2048PX — {user.display_name}** (@{user.name})\n"
            f"🔗 [Link ảnh gốc]({avt_url})"
        )
        sent = await autorep(ctx.message, content=caption, auto_delete_delay=60)
        autodelet(sent, delay=60)

    # ── LỆNH CON 3: TRÍCH XUẤT BANNER HD (IMG BANNER) ───────────────────────
    @cmd_img.command(name="banner", aliases=["bn"])
    async def sub_banner(self, ctx: commands.Context, *, target: Optional[str] = None):
        """Lấy Banner Profile hoặc Server Banner: (prefix)img banner [@user | uid]"""
        user = None
        if target:
            if ctx.message.mentions:
                target_user = ctx.message.mentions[0]
            else:
                target_clean = re.sub(r"[<@!>]", "", target.strip())
                if target_clean.isdigit():
                    try:
                        target_user = await self.bot.fetch_user(int(target_clean))
                    except Exception:
                        target_user = None
                else:
                    target_user = None
            if target_user:
                try:
                    user = await self.bot.fetch_user(target_user.id)
                except Exception:
                    user = target_user
        else:
            try:
                user = await self.bot.fetch_user(ctx.author.id)
            except Exception:
                user = ctx.author

        if user and user.banner:
            banner_url = user.banner.replace(size=2048, static_format="png").url
            caption = (
                f"🎨 **BANNER PROFILE — {user.display_name}** (@{user.name})\n"
                f"🔗 [Link banner gốc]({banner_url})"
            )
            sent = await autorep(ctx.message, content=caption, auto_delete_delay=60)
            autodelet(sent, delay=60)
            return

        # Nếu user không có banner, kiểm tra nếu trong server và server có banner
        if ctx.guild and ctx.guild.banner:
            guild_banner_url = ctx.guild.banner.replace(size=2048, static_format="png").url
            caption = (
                f"🏰 **SERVER BANNER — {ctx.guild.name}**\n"
                f"🔗 [Link banner server]({guild_banner_url})"
            )
            sent = await autorep(ctx.message, content=caption, auto_delete_delay=60)
            autodelet(sent, delay=60)
            return

        msg = await autorep(ctx.message, f"❌ Người dùng **{user.name if user else 'này'}** không cài đặt ảnh bìa (Banner).")
        autodelet(msg, delay=15)

    # ── LỆNH CON 4: RESIZE ẢNH (IMG RESIZE) ────────────────────────────────
    @cmd_img.command(name="resize", aliases=["scale"])
    async def sub_resize(self, ctx: commands.Context, dimension: str, *, url_opt: Optional[str] = None):
        """Đổi kích thước ảnh: (prefix)img resize <WxH> [reply/file/url]"""
        pfx = self._pfx()
        # Parse kích thước WxH
        match = re.match(r"^(\d+)[xX*](\d+)$", dimension.strip())
        if not match:
            msg = await autorep(ctx.message, f"❌ Cú pháp: `{pfx}img resize <rộng>x<cao>` (Ví dụ: `{pfx}img resize 800x600`)")
            autodelet(msg, delay=15)
            return

        nw, nh = int(match.group(1)), int(match.group(2))
        if nw < 10 or nw > 4000 or nh < 10 or nh > 4000:
            msg = await autorep(ctx.message, "❌ Kích thước phải nằm trong khoảng từ 10px đến 4000px.")
            autodelet(msg, delay=15)
            return

        resolved = await self._resolve_image(ctx, url_opt)
        if not resolved:
            msg = await autorep(ctx.message, "❌ Vui lòng reply vào ảnh, đính kèm file ảnh hoặc dán link ảnh để resize.")
            autodelet(msg, delay=15)
            return

        img_bytes, fn = resolved
        loop = asyncio.get_running_loop()

        def _do_resize():
            with Image.open(io.BytesIO(img_bytes)) as im:
                out = im.resize((nw, nh), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                fmt = "PNG" if im.format == "PNG" or im.mode == "RGBA" else "JPEG"
                out.save(buf, format=fmt, quality=95)
                buf.seek(0)
                return buf, fmt.lower()

        try:
            buf, fmt_name = await loop.run_in_executor(None, _do_resize)
            file = discord.File(buf, filename=f"resized_{nw}x{nh}.{fmt_name}")
            sent = await autorep(
                ctx.message,
                content=f"📐 **ĐÃ RESIZE ẢNH THÀNH CÔNG:** `{nw}x{nh}px`",
                file=file,
                auto_delete_delay=60
            )
            autodelet(sent, delay=60)
        except Exception as e:
            msg = await autorep(ctx.message, f"❌ Lỗi xử lý ảnh: {str(e)[:100]}")
            autodelet(msg, delay=15)

    # ── LỆNH CON 5: LÀM MỜ ẢNH (IMG BLUR) ──────────────────────────────────
    @cmd_img.command(name="blur")
    async def sub_blur(self, ctx: commands.Context, radius: Optional[int] = 6, *, url_opt: Optional[str] = None):
        """Làm mờ ảnh nghệ thuật: (prefix)img blur [1-30]"""
        radius = max(1, min(radius, 50))
        resolved = await self._resolve_image(ctx, url_opt)
        if not resolved:
            msg = await autorep(ctx.message, "❌ Vui lòng reply vào ảnh, đính kèm file ảnh hoặc dán link ảnh để làm mờ.")
            autodelet(msg, delay=15)
            return

        img_bytes, fn = resolved
        loop = asyncio.get_running_loop()

        def _do_blur():
            with Image.open(io.BytesIO(img_bytes)) as im:
                out = im.filter(ImageFilter.GaussianBlur(radius=radius))
                buf = io.BytesIO()
                fmt = "PNG" if im.mode == "RGBA" else "JPEG"
                out.save(buf, format=fmt, quality=92)
                buf.seek(0)
                return buf, fmt.lower()

        try:
            buf, fmt_name = await loop.run_in_executor(None, _do_blur)
            file = discord.File(buf, filename=f"blur_r{radius}.{fmt_name}")
            sent = await autorep(
                ctx.message,
                content=f"🌫️ **ĐÃ LÀM MỜ ẢNH NGHỆ THUẬT (Radius: {radius}px)**",
                file=file,
                auto_delete_delay=60
            )
            autodelet(sent, delay=60)
        except Exception as e:
            msg = await autorep(ctx.message, f"❌ Lỗi làm mờ: {str(e)[:100]}")
            autodelet(msg, delay=15)

    # ── LỆNH CON 6: ĐEN TRẮNG (IMG GRAY) ───────────────────────────────────
    @cmd_img.command(name="gray", aliases=["bw", "grayscale"])
    async def sub_gray(self, ctx: commands.Context, *, url_opt: Optional[str] = None):
        """Chuyển ảnh sang đen trắng nghệ thuật: (prefix)img gray"""
        resolved = await self._resolve_image(ctx, url_opt)
        if not resolved:
            msg = await autorep(ctx.message, "❌ Vui lòng reply vào ảnh, đính kèm file ảnh hoặc dán link ảnh.")
            autodelet(msg, delay=15)
            return

        img_bytes, fn = resolved
        loop = asyncio.get_running_loop()

        def _do_gray():
            with Image.open(io.BytesIO(img_bytes)) as im:
                out = ImageOps.grayscale(im)
                buf = io.BytesIO()
                out.save(buf, format="JPEG", quality=92)
                buf.seek(0)
                return buf

        try:
            buf = await loop.run_in_executor(None, _do_gray)
            file = discord.File(buf, filename="grayscale_art.jpg")
            sent = await autorep(
                ctx.message,
                content="🖤 **ĐÃ CHUYỂN ẢNH SANG ĐEN TRẮNG NGHỆ THUẬT (GRAYSCALE)**",
                file=file,
                auto_delete_delay=60
            )
            autodelet(sent, delay=60)
        except Exception as e:
            msg = await autorep(ctx.message, f"❌ Lỗi: {str(e)[:100]}")
            autodelet(msg, delay=15)

    # ── LỆNH CON 7: ĐẢO MÀU ÂM BẢN (IMG INVERT) ────────────────────────────
    @cmd_img.command(name="invert", aliases=["negative"])
    async def sub_invert(self, ctx: commands.Context, *, url_opt: Optional[str] = None):
        """Đảo ngược màu sắc âm bản: (prefix)img invert"""
        resolved = await self._resolve_image(ctx, url_opt)
        if not resolved:
            msg = await autorep(ctx.message, "❌ Vui lòng reply vào ảnh, đính kèm file ảnh hoặc dán link ảnh.")
            autodelet(msg, delay=15)
            return

        img_bytes, fn = resolved
        loop = asyncio.get_running_loop()

        def _do_invert():
            with Image.open(io.BytesIO(img_bytes)) as im:
                rgb = im.convert("RGB")
                out = ImageOps.invert(rgb)
                buf = io.BytesIO()
                out.save(buf, format="JPEG", quality=92)
                buf.seek(0)
                return buf

        try:
            buf = await loop.run_in_executor(None, _do_invert)
            file = discord.File(buf, filename="inverted_negative.jpg")
            sent = await autorep(
                ctx.message,
                content="🎭 **ĐÃ ĐẢO MÀU SẮC ÂM BẢN (INVERT / NEGATIVE)**",
                file=file,
                auto_delete_delay=60
            )
            autodelet(sent, delay=60)
        except Exception as e:
            msg = await autorep(ctx.message, f"❌ Lỗi: {str(e)[:100]}")
            autodelet(msg, delay=15)

    # ── LỆNH CON 8: CẮT HÌNH TRÒN TRONG SUỐT (IMG CIRCLE) ──────────────────
    @cmd_img.command(name="circle", aliases=["tron"])
    async def sub_circle(self, ctx: commands.Context, *, url_opt: Optional[str] = None):
        """Cắt ảnh thành hình tròn trong suốt: (prefix)img circle"""
        resolved = await self._resolve_image(ctx, url_opt)
        if not resolved:
            msg = await autorep(ctx.message, "❌ Vui lòng reply vào ảnh, đính kèm file ảnh hoặc dán link ảnh.")
            autodelet(msg, delay=15)
            return

        img_bytes, fn = resolved
        loop = asyncio.get_running_loop()

        def _do_circle():
            with Image.open(io.BytesIO(img_bytes)) as im:
                # Crop vuông trung tâm
                w, h = im.size
                side = min(w, h)
                x1 = (w - side) // 2
                y1 = (h - side) // 2
                sq = im.crop((x1, y1, x1 + side, y1 + side)).convert("RGBA")

                # Mask tròn antialiased x2
                mask_scale = side * 2
                mask = Image.new("L", (mask_scale, mask_scale), 0)
                d = ImageDraw.Draw(mask)
                d.ellipse((0, 0, mask_scale, mask_scale), fill=255)
                mask = mask.resize((side, side), Image.Resampling.LANCZOS)

                out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
                out.paste(sq, (0, 0), mask=mask)

                buf = io.BytesIO()
                out.save(buf, format="PNG")
                buf.seek(0)
                return buf

        try:
            buf = await loop.run_in_executor(None, _do_circle)
            file = discord.File(buf, filename="circle_crop.png")
            sent = await autorep(
                ctx.message,
                content="⭕ **ĐÃ CẮT ẢNH HÌNH TRÒN TRONG SUỐT HOÀN HẢO**",
                file=file,
                auto_delete_delay=60
            )
            autodelet(sent, delay=60)
        except Exception as e:
            msg = await autorep(ctx.message, f"❌ Lỗi cắt tròn: {str(e)[:100]}")
            autodelet(msg, delay=15)

    # ── LỆNH CON 9: THÔNG SỐ ẢNH (IMG INFO) ────────────────────────────────
    @cmd_img.command(name="info")
    async def sub_info(self, ctx: commands.Context, *, url_opt: Optional[str] = None):
        """Xem thông số kỹ thuật chi tiết của ảnh: (prefix)img info"""
        resolved = await self._resolve_image(ctx, url_opt)
        if not resolved:
            msg = await autorep(ctx.message, "❌ Vui lòng reply vào ảnh, đính kèm file ảnh hoặc dán link ảnh.")
            autodelet(msg, delay=15)
            return

        img_bytes, fn = resolved

        try:
            with Image.open(io.BytesIO(img_bytes)) as im:
                w, h = im.size
                fmt_name = im.format or "UNKNOWN"
                mode = im.mode
                size_kb = len(img_bytes) / 1024
                size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.2f} MB"
                aspect = f"{w / math.gcd(w, h):.0f}:{h / math.gcd(w, h):.0f}" if hasattr(math, "gcd") else f"{w}:{h}"

                caption = (
                    f"🔍 **THÔNG SỐ KỸ THUẬT ẢNH**\n"
                    f"• Tên file: **{fn}**\n"
                    f"• Kích thước: **{w} x {h} px** (Tỉ lệ: `{aspect}`)\n"
                    f"• Định dạng: **{fmt_name}**   |   Color Mode: **{mode}**\n"
                    f"• Dung lượng: **{size_str}**"
                )
                sent = await autorep(ctx.message, content=caption, auto_delete_delay=60)
                autodelet(sent, delay=60)
        except Exception as e:
            msg = await autorep(ctx.message, f"❌ Không thể đọc thông số ảnh: {str(e)[:100]}")
            autodelet(msg, delay=15)


async def setup(bot: commands.Bot):
    await bot.add_cog(ImageModule(bot))
