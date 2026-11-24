# -*- coding: utf-8 -*-
"""
MODULE: vps (Cloud Linux VPS Manager - Zero Browser RAM)
- vps: Huong dan chi tiet cach dung.
- vps create <ten>: Khoi tao may ao Linux ca nhan (moi acc chi duoc tao 1 VPS).
- vps list: Xem lai link truy cap va lay lai ma PIN bao mat.
- vps delete: Huy phien VPS hien tai de tao cai moi.
"""
from __future__ import annotations
import asyncio
import time
from typing import Optional

import discord
from discord.ext import commands

try:
    from apps.user_discord.core.bot_sys import require_permission
    from apps.user_discord.core.alias import alias_declare
    from apps.user_discord.utils.prefix import fmt, get_prefix
    from apps.user_discord.utils.autorep import autorep
    from apps.user_discord.utils.autodelet import autodelet
    from apps.user_discord.utils.media_card import async_help_card
    from apps.user_discord.utils.menu_catalog import menu_entry
    from apps.user_discord.core.vps_manager import VPSManager
except ImportError:
    from core.bot_sys import require_permission
    from core.alias import alias_declare
    from utils.prefix import fmt, get_prefix
    from utils.autorep import autorep
    from utils.autodelet import autodelet
    from utils.media_card import async_help_card
    from utils.menu_catalog import menu_entry
    from core.vps_manager import VPSManager


class VPS(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.mgr = VPSManager.get_instance()

    @menu_entry("SYSTEM & SECURITY", "vps", "Khởi tạo Cloud Linux VPS miễn phí",
                icon_sym="💻", icon_color=(14, 165, 233), order=20)
    @commands.group(name="vps", invoke_without_command=True)
    async def vps_cmd(self, ctx: commands.Context, *, sub: Optional[str] = None):

        """Lenh chinh huong dan su dung VPS."""
        p = get_prefix(ctx)
        
        card_file = None
        try:
            card_buf = await async_help_card("vps", p)
            if card_buf:
                card_file = discord.File(card_buf, filename="vps_guide.png")
        except Exception as e:
            print(f"[vps] async_help_card error: {e}")

        text = (
            "🚀 **HỆ THỐNG MÁY ẢO LINUX CÁ NHÂN (FREE CLOUD VPS)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "✨ *Mỗi tài khoản được cấp tối đa 1 máy ảo Linux (Ubuntu 22.04) chạy độc lập.*\n\n"
            f"📌 **CÁC LỆNH ĐIỀU KHIỂN:**\n"
            f"• `{p}vps create <tên>` : Khởi tạo máy ảo mới (tên do bạn tự đặt)\n"
            f"• `{p}vps list` : Lấy lại Link Web Portal & Mã PIN bí mật\n"
            f"• `{p}vps delete` : Hủy VPS hiện tại để giải phóng / tạo lại\n\n"
            "🛡️ *Giao diện Web GUI bo góc bảo mật: Truy cập link, nhập mã PIN là vào thẳng Linux Terminal!*"
        )
        if card_file:
            await autorep(ctx, text, file=card_file, auto_delete_delay=60)
        else:
            await autorep(ctx, text, auto_delete_delay=60)


    @vps_cmd.command(name="create")
    async def vps_create(self, ctx: commands.Context, *, vps_name: Optional[str] = None):
        """Khoi tao may ao moi."""
        p = get_prefix(ctx)
        uid = ctx.author.id

        # 1. Kiem tra xem da co session chua
        existing = self.mgr.get_session(uid)
        if existing:
            await autorep(
                ctx,
                f"⚠️ Bạn đã có 1 VPS đang hoạt động: **{existing.vps_name}**\n"
                f"• Dùng `{p}vps list` để xem lại Link & Mã PIN.\n"
                f"• Dùng `{p}vps delete` nếu muốn xóa để tạo máy mới.",
                auto_delete_delay=30
            )
            return

        name = (vps_name or f"node-{str(uid)[-4:]}").strip().replace(" ", "-")[:20]

        wait_msg = await autorep(
            ctx,
            f"⏳ Đang kết nối hạ tầng đám mây để khởi tạo máy ảo **{name}**... (mất ~12-15s)",
            auto_delete_delay=20
        )

        try:
            # Khoi tao qua pure REST stream API (Zero Browser RAM)
            sess = await self.mgr.spawn_vps(uid, name)

            text = (
                "🎉 **MÁY ẢO LINUX ĐÃ KHỞI TẠO THÀNH CÔNG!**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏷️ **Tên máy:** `{sess.vps_name}`\n"
                f"🔑 **MÃ PIN MỞ KHÓA:** `{sess.pin_code}`\n"
                f"⏳ **Thời gian phiên:** ~60 Phút (Có Auto Keep-Alive)\n\n"
                f"🌐 **LINK TRUY CẬP WEB GUI:**\n"
                f"👉 [Bấm vào đây để mở máy chủ]({sess.portal_url})\n\n"
                "⚠️ *Mở link trên Safari/Chrome, nhập đúng mã PIN ở trên là vào thẳng Linux Terminal!*"
            )

            await autorep(ctx, text, auto_delete_delay=180)

        except Exception as ex:
            await autorep(
                ctx,
                f"❌ Lỗi khởi tạo máy ảo: `{ex}`. Vui lòng thử lại sau!",
                auto_delete_delay=30
            )

    @vps_cmd.command(name="list")
    async def vps_list(self, ctx: commands.Context):
        """Lay lai link va xem ma PIN."""
        p = get_prefix(ctx)
        uid = ctx.author.id
        sess = self.mgr.get_session(uid)

        if not sess:
            await autorep(
                ctx,
                f"📭 Bạn chưa có máy ảo nào đang chạy! Gõ `{p}vps create <tên>` để tạo ngay.",
                auto_delete_delay=30
            )
            return

        text = (
            "📋 **THÔNG TIN MÁY ẢO CỦA BẠN**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ **Tên máy:** `{sess.vps_name}`\n"
            f"🔑 **Mã PIN bảo mật:** `{sess.pin_code}`\n"
            f"⏳ **Thời gian còn lại:** `{sess.time_left_str()}`\n"
            f"🌐 **Link truy cập:** [Vào Web GUI Máy Chủ]({sess.portal_url})\n\n"
            f"💡 *Gõ `{p}vps delete` nếu muốn xóa máy này.*"
        )
        await autorep(ctx, text, auto_delete_delay=120)

    @vps_cmd.command(name="delete", aliases=["del", "remove", "rm"])
    async def vps_delete(self, ctx: commands.Context):
        """Huy may ao hien tai."""
        p = get_prefix(ctx)
        uid = ctx.author.id
        ok = self.mgr.delete_session(uid)

        if ok:
            await autorep(
                ctx,
                f"🗑️ Đã hủy máy ảo thành công! Bạn có thể gõ `{p}vps create <tên>` để tạo máy mới.",
                auto_delete_delay=30
            )
        else:
            await autorep(
                ctx,
                "⚠️ Bạn không có máy ảo nào đang chạy để xóa.",
                auto_delete_delay=20
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(VPS(bot))
