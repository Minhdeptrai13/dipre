# -*- coding: utf-8 -*-
"""MODULE: del (Delete / Purge Messages) - Hệ thống xoá tin nhắn siêu tốc cho Selfbot.

Hỗ trợ:
1. Reply tin nhắn + (prefix)del: Xoá ngay tin nhắn được reply.
2. (prefix)del <số>: Xoá N tin nhắn gần nhất (tự động lọc tin của bản thân nếu không có quyền Admin server).
3. (prefix)del all: Dọn sạch toàn bộ tin nhắn của bản thân trong kênh / DM hiện tại.
4. (prefix)del: Gửi bảng hướng dẫn Glassmorphism siêu đẹp.
"""
from __future__ import annotations

import asyncio
import io
import time
from typing import Optional

import discord
from discord.ext import commands

try:
    from apps.user_discord.core.bot_sys import require_permission
    from apps.user_discord.core.alias import alias_declare
    from apps.user_discord.utils.prefix import fmt, get_prefix
    from apps.user_discord.utils.menu_catalog import menu_entry
    from apps.user_discord.utils.media_card import async_help_card
    from apps.user_discord.utils.autorep import autorep
except ImportError:
    from core.bot_sys import require_permission
    from core.alias import alias_declare
    from utils.prefix import fmt, get_prefix
    from utils.menu_catalog import menu_entry
    from utils.media_card import async_help_card
    from utils.autorep import autorep


class DeleteCog(commands.Cog, name="Delete"):
    """Quản lý xoá và dọn dẹp tin nhắn siêu tốc."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return getattr(self.bot, "_own_prefix", None) or ""

    async def _reply(self, ctx: commands.Context, text: str, delay: Optional[int] = 5):
        """Phản hồi tự huỷ nhanh không làm rác kênh chat."""
        try:
            text = fmt(self.bot, text)
        except Exception:
            pass
        try:
            return await autorep(ctx.message, content=text, auto_delete_delay=delay)
        except Exception:
            try:
                return await ctx.send(text, delete_after=delay)
            except Exception:
                pass

    @menu_entry("UTILITY & CLEANER", "del", "Xoá tin nhắn (reply / số lượng / all)",
                badge="HOT", icon_sym="🗑️", icon_color=(239, 68, 68), order=1)
    @alias_declare("del", main="del", subs=["delete", "xoa", "clean", "purge"])
    @commands.command(name="del", aliases=["delete", "xoa", "clean", "purge"])
    @require_permission("user")
    async def cmd_del(self, ctx: commands.Context, amount: str = None):
        """Xoá tin nhắn siêu tốc:
        • Reply tin nhắn + (prefix)del: xoá ngay tin được reply.
        • (prefix)del <số>: xoá số lượng tin nhắn chỉ định.
        • (prefix)del all: xoá sạch tin nhắn của chính mình trong kênh / DM.
        """
        p = self._pfx()

        # ── TRƯỜNG HỢP 1: REPLY TIN NHẮN (Xoá ngay tin được trích dẫn) ─────────
        if ctx.message.reference and ctx.message.reference.message_id:
            ref_id = ctx.message.reference.message_id
            target_msg = None
            try:
                target_msg = await ctx.channel.fetch_message(ref_id)
            except Exception:
                pass

            if target_msg:
                # Xoá tin nhắn gọi lệnh trước
                try:
                    await ctx.message.delete()
                except Exception:
                    pass

                # Nếu là tin của chính mình -> xoá luôn vô điều kiện
                if target_msg.author.id == self.bot.user.id:
                    try:
                        await target_msg.delete()
                        return
                    except Exception as e:
                        await self._reply(ctx, f"❌ Lỗi xoá tin nhắn: {e}", delay=5)
                        return

                # Nếu là tin của người khác -> cần quyền Manage Messages
                can_delete_others = False
                if ctx.guild and hasattr(ctx.channel, "permissions_for"):
                    perms = ctx.channel.permissions_for(ctx.guild.me)
                    can_delete_others = perms.manage_messages or perms.administrator

                if can_delete_others:
                    try:
                        await target_msg.delete()
                        return
                    except Exception as e:
                        await self._reply(ctx, f"❌ Không thể xoá tin nhắn người khác: {e}", delay=5)
                        return
                else:
                    await self._reply(ctx, "⚠️ Bạn không có quyền quản lý tin nhắn của người khác trong kênh này.", delay=6)
                    return

        # ── TRƯỜNG HỢP 2: GÕ LỆNH TRỐNG HOẶC HELP -> GỬI BẢNG HƯỚNG DẪN ẢNH GLASSMORPHISM ─
        if not amount or amount.strip().lower() in ("help", "hd", "menu", "card"):
            card_buf = None
            try:
                card_buf = await async_help_card("del", p)
            except Exception:
                card_buf = None

            if card_buf:
                try:
                    file = discord.File(card_buf, filename="del_guide.png")
                    return await autorep(
                        ctx.message,
                        content=f"🗑️ **HƯỚNG DẪN SỬ DỤNG LỆNH XOÁ TIN NHẮN** (`{p}del`)",
                        file=file,
                        auto_delete_delay=35,
                    )
                except Exception:
                    pass

            # Fallback văn bản nếu không render được ảnh
            guide_text = (
                f"🗑️ **HỆ THỐNG XOÁ TIN NHẮN (`{p}del`)**\n\n"
                f"👉 **1. Xoá nhanh 1 tin nhắn:**\n"
                f"   • *Reply* tin nhắn bất kỳ + gõ `{p}del`\n\n"
                f"👉 **2. Xoá theo số lượng:**\n"
                f"   • Gõ `{p}del <số>` (Ví dụ: `{p}del 10` hoặc `{p}del 30`)\n\n"
                f"👉 **3. Xoá toàn bộ tin nhắn bản thân:**\n"
                f"   • Gõ `{p}del all` hoặc `{p}del me` (Dọn dẹp DM / Kênh chat)"
            )
            return await self._reply(ctx, guide_text, delay=30)

        # ── TRƯỜNG HỢP 3: XOÁ TOÀN BỘ TIN CỦA CHÍNH MÌNH (del all / del me) ───
        target_mode = amount.strip().lower()
        if target_mode in ("all", "me", "tatca", "het", "sach"):
            # Xoá tin nhắn gọi lệnh
            try:
                await ctx.message.delete()
            except Exception:
                pass

            notify = await self._reply(ctx, "⏳ Đang quét và dọn dẹp toàn bộ tin nhắn của bạn...", delay=15)
            deleted_count = 0
            scanned = 0

            try:
                async for msg in ctx.channel.history(limit=300):
                    scanned += 1
                    if msg.author.id == self.bot.user.id:
                        try:
                            await msg.delete()
                            deleted_count += 1
                            await asyncio.sleep(0.28)  # Tránh rate-limit 429
                        except Exception:
                            pass
            except Exception as exc:
                await self._reply(ctx, f"⚠️ Quá trình quét gián đoạn: {exc}", delay=6)

            try:
                if notify:
                    await notify.delete()
            except Exception:
                pass

            await self._reply(
                ctx,
                f"✅ **ĐÃ DỌN DẸP XONG**\n"
                f"• Đã xoá thành công: **{deleted_count}** tin nhắn của bạn.\n"
                f"• Quét tổng cộng: {scanned} tin nhắn gần nhất.",
                delay=6,
            )
            return

        # ── TRƯỜNG HỢP 4: XOÁ THEO SỐ LƯỢNG (del <số>) ────────────────────────
        if target_mode.isdigit():
            count = int(target_mode)
            if count <= 0:
                await self._reply(ctx, "❌ Số lượng tin nhắn cần xoá phải lớn hơn 0.", delay=5)
                return

            if count > 100:
                await self._reply(ctx, "⚠️ Mỗi lần chỉ nên xoá tối đa 100 tin nhắn để tránh bị Discord hạn chế.", delay=6)
                count = 100

            # Xoá tin gọi lệnh
            try:
                await ctx.message.delete()
            except Exception:
                pass

            # Kiểm tra xem có quyền xoá tin nhắn của người khác trong guild không
            can_manage = False
            if ctx.guild and hasattr(ctx.channel, "permissions_for"):
                perms = ctx.channel.permissions_for(ctx.guild.me)
                can_manage = perms.manage_messages or perms.administrator

            deleted_count = 0
            try:
                # Quét lịch sử
                async for msg in ctx.channel.history(limit=count + 15):
                    if deleted_count >= count:
                        break
                    # Nếu có quyền manage_messages -> xoá bất kỳ tin nào
                    # Nếu không có quyền (hoặc DM) -> chỉ xoá tin của chính mình
                    if can_manage or msg.author.id == self.bot.user.id:
                        try:
                            await msg.delete()
                            deleted_count += 1
                            await asyncio.sleep(0.25)
                        except Exception:
                            continue
            except Exception as exc:
                await self._reply(ctx, f"⚠️ Lỗi khi xoá: {exc}", delay=5)

            await self._reply(ctx, f"✅ Đã xoá thành công **{deleted_count}** tin nhắn.", delay=5)
            return

        # ── TRƯỜNG HỢP 5: XOÁ CHỈ TIN NHẮN CỦA BOT (del bot) ─────────────────
        if target_mode in ("bot", "bots"):
            try:
                await ctx.message.delete()
            except Exception:
                pass

            can_manage = False
            if ctx.guild and hasattr(ctx.channel, "permissions_for"):
                perms = ctx.channel.permissions_for(ctx.guild.me)
                can_manage = perms.manage_messages or perms.administrator

            deleted_count = 0
            try:
                async for msg in ctx.channel.history(limit=100):
                    if deleted_count >= 50:
                        break
                    # Nếu là tin của bot khác thì cần quyền, nếu của chính bot này thì xoá luôn
                    is_my_bot = msg.author.id == self.bot.user.id
                    is_other_bot = getattr(msg.author, "bot", False)
                    if is_my_bot or (can_manage and is_other_bot):
                        try:
                            await msg.delete()
                            deleted_count += 1
                            await asyncio.sleep(0.25)
                        except Exception:
                            continue
            except Exception as exc:
                pass

            await self._reply(ctx, f"🤖 Đã xoá **{deleted_count}** tin nhắn của bot.", delay=5)
            return

        await self._reply(ctx, f"❌ Cú pháp không hợp lệ. Gõ `{p}del` để xem bảng hướng dẫn.", delay=6)


async def setup(bot: commands.Bot):
    await bot.add_cog(DeleteCog(bot))
