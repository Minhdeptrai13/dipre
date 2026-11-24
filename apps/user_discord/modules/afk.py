# -*- coding: utf-8 -*-
"""MODULE: afk (AFK Auto-Responder & Notification Tracker) - Tự động phản hồi & thống kê tin nhắn khi vắng mặt.

Quy trình:
1. Bật AFK: (prefix)afk [tin nhắn phản hồi]
   - Thiết lập câu trả lời tự động do bạn tự quyết định (mặc định: 'Hiện tại tôi đang bận (AFK)...')
   - Bắt đầu ghi nhận thời gian và nhật ký các lần được Tag hoặc Inbox riêng (DM).
2. Khi ai đó Tag hoặc Inbox riêng (DM):
   - Tự động trả lời đúng nội dung bạn đã thiết lập (kèm cơ chế chống spam 45s/người).
   - Lưu lại ai đã nhắn, nội dung gì, ở đâu, lúc mấy giờ.
3. Tắt AFK: (prefix)afk off HOẶC khi bạn nhắn bất kỳ tin nhắn bình thường nào:
   - Tự động huỷ chế độ AFK.
   - Xuất bảng báo cáo thống kê chi tiết: thời gian đã AFK, số lần được tag, số lần nhận tin nhắn riêng, danh sách chi tiết.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

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

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_AFK_MSG = "Hiện tại tôi đang vắng mặt (AFK), có việc gì hãy để lại tin nhắn tôi sẽ phản hồi sau."


def _format_duration(seconds: float) -> str:
    """Format thời lượng giây thành chuỗi đọc dễ hiểu."""
    s = int(seconds)
    if s < 60:
        return f"{s} giây"
    m = s // 60
    rem_s = s % 60
    if m < 60:
        return f"{m} phút {rem_s}s" if rem_s else f"{m} phút"
    h = m // 60
    rem_m = m % 60
    if h < 24:
        return f"{h} giờ {rem_m}p" if rem_m else f"{h} giờ"
    d = h // 24
    rem_h = h % 24
    return f"{d} ngày {rem_h}h"


class AFKCog(commands.Cog, name="AFK"):
    """Tự động trả lời khi được Tag / DM và thống kê tin nhắn khi quay trở lại."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._user_cooldowns: Dict[int, float] = {}  # user_id -> last_reply_timestamp

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return getattr(self.bot, "_own_prefix", None) or ""

    def _db_path(self) -> Optional[Path]:
        uid = getattr(getattr(self.bot, "user", None), "id", None)
        if not uid:
            return None
        return DATA_DIR / f"{uid}_afk.json"

    def _load_afk(self) -> Dict[str, Any]:
        path = self._db_path()
        if not path or not path.exists():
            return {"is_afk": False, "start_time": 0, "message": "", "mentions": [], "dms": []}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"is_afk": False, "start_time": 0, "message": "", "mentions": [], "dms": []}

    def _save_afk(self, data: Dict[str, Any]) -> None:
        path = self._db_path()
        if not path:
            return
        try:
            path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[AFK] Lỗi ghi file afk: {e}", flush=True)

    def _is_owner(self, uid: int) -> bool:
        return bool(self.bot.user and uid == self.bot.user.id)

    async def _reply(self, ctx: commands.Context, text: str, delay: Optional[int] = 10):
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

    async def _finish_afk_and_report(self, channel: discord.abc.Messageable, afk_data: Dict[str, Any]):
        """Tắt AFK và gửi báo cáo thống kê chi tiết."""
        start_time = afk_data.get("start_time", time.time())
        duration_str = _format_duration(time.time() - start_time)

        mentions: List[Dict[str, Any]] = afk_data.get("mentions", [])
        dms: List[Dict[str, Any]] = afk_data.get("dms", [])

        total_mentions = len(mentions)
        total_dms = len(dms)

        # Đếm số người duy nhất
        unique_mentioners = {m.get("author_name") for m in mentions if m.get("author_name")}
        unique_dmers = {d.get("author_name") for d in dms if d.get("author_name")}

        lines = [
            "✨ **CHÀO MỪNG BẠN ĐÃ QUAY TRỞ LẠI! CHẾ ĐỘ AFK ĐÃ TẮT**",
            f"⏱️ **Thời gian vắng mặt:** `{duration_str}`",
            f"📊 **Tổng quan tin nhắn nhận được:**",
            f"   • **Tag / Mention:** `{total_mentions}` lần (từ `{len(unique_mentioners)}` người)",
            f"   • **Tin nhắn riêng (DM):** `{total_dms}` lần (từ `{len(unique_dmers)}` người)",
        ]

        # Liệt kê chi tiết các tin nhắn gần nhất
        if total_mentions > 0 or total_dms > 0:
            lines.append("\n📬 **DANH SÁCH CHI TIẾT TIN NHẮN ĐÃ GHI NHẬN:**")

            if total_mentions > 0:
                lines.append("\n🏷️ **Tin nhắn được Tag trong Server:**")
                for idx, m in enumerate(mentions[-5:], 1):
                    sender = m.get("author_name", "Ai đó")
                    guild_name = m.get("guild_name", "Server")
                    channel_name = m.get("channel_name", "Kênh")
                    content = m.get("content", "")
                    if len(content) > 50:
                        content = content[:47] + "..."
                    t_ago = _format_duration(time.time() - m.get("time", time.time()))
                    lines.append(f"   `{idx}.` **{sender}** (`{guild_name}` #{channel_name}) [{t_ago} trước]: *\"{content}\"*")
                if total_mentions > 5:
                    lines.append(f"   *(... và {total_mentions - 5} lần tag khác)*")

            if total_dms > 0:
                lines.append("\n💬 **Tin nhắn riêng (Inbox / DM):**")
                for idx, d in enumerate(dms[-5:], 1):
                    sender = d.get("author_name", "Ai đó")
                    content = d.get("content", "")
                    if len(content) > 50:
                        content = content[:47] + "..."
                    t_ago = _format_duration(time.time() - d.get("time", time.time()))
                    lines.append(f"   `{idx}.` **{sender}** [{t_ago} trước]: *\"{content}\"*")
                if total_dms > 5:
                    lines.append(f"   *(... và {total_dms - 5} tin nhắn riêng khác)*")
        else:
            lines.append("\n🎉 *Trong suốt thời gian bạn vắng mặt, không có ai tag hoặc inbox riêng.*")

        # Đặt lại trạng thái trong DB
        self._save_afk({"is_afk": False, "start_time": 0, "message": "", "mentions": [], "dms": []})

        report_content = "\n".join(lines)
        try:
            await channel.send(report_content)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Bắt sự kiện để tự động trả lời khi được Tag/DM hoặc tự động tắt AFK khi chủ bot nhắn tin."""
        if not self.bot.user:
            return

        # ── 1. NẾU CHỦ BOT NHẮN TIN -> TỰ ĐỘNG TẮT AFK & GỬI BÁO CÁO ───────────
        if message.author.id == self.bot.user.id:
            content = message.content.strip()
            p = self._pfx()

            # Bỏ qua nếu tin nhắn này chính là lệnh bật AFK mới
            if content.lower().startswith((f"{p}afk", f"{p}afk ")):
                # Nếu là lệnh afk off thì để command xử lý
                return

            afk_data = self._load_afk()
            if afk_data.get("is_afk"):
                # Người dùng đã nhắn tin bình thường -> Tự động kết thúc AFK và xuất báo cáo!
                await self._finish_afk_and_report(message.channel, afk_data)
            return

        # Bỏ qua tin nhắn từ Bot khác
        if message.author.bot:
            return

        # ── 2. NẾU BOT ĐANG AFK VÀ CÓ NGƯỜI TAG HOẶC INBOX RIÊNG ─────────────
        afk_data = self._load_afk()
        if not afk_data.get("is_afk"):
            return

        is_dm = isinstance(message.channel, discord.DMChannel)

        # Kiểm tra xem có phải tin nhắn được Mention hoặc Reply vào bot không
        is_mentioned = False
        if not is_dm:
            if self.bot.user in message.mentions:
                is_mentioned = True
            elif message.reference and message.reference.resolved:
                resolved = message.reference.resolved
                if isinstance(resolved, discord.Message) and resolved.author.id == self.bot.user.id:
                    is_mentioned = True

        if not is_dm and not is_mentioned:
            return

        sender_id = message.author.id
        now = time.time()

        # ── GHI NHẬN VÀO NHẬT KÝ THỐNG KÊ ──
        if is_dm:
            afk_data.setdefault("dms", []).append({
                "author_name": str(message.author.name),
                "author_id": sender_id,
                "content": message.content,
                "time": now,
            })
        else:
            afk_data.setdefault("mentions", []).append({
                "author_name": str(message.author.name),
                "author_id": sender_id,
                "guild_name": message.guild.name if message.guild else "Server",
                "channel_name": getattr(message.channel, "name", "kênh"),
                "content": message.content,
                "time": now,
            })
        self._save_afk(afk_data)

        # ── TỰ ĐỘNG PHẢN HỒI (KÈM ANTI-SPAM COOLDOWN 45s) ──
        last_rep = self._user_cooldowns.get(sender_id, 0)
        if now - last_rep < 45.0:
            return  # Đang trong cooldown chống spam, chỉ ghi nhận log mà không spam chat

        self._user_cooldowns[sender_id] = now
        reply_reason = afk_data.get("message") or DEFAULT_AFK_MSG
        duration_so_far = _format_duration(now - afk_data.get("start_time", now))

        reply_text = (
            f"💤 **[TỰ ĐỘNG PHẢN HỒI AFK]**\n"
            f"• **Lời nhắn:** {reply_reason}\n"
            f"• *Đã vắng mặt từ `{duration_so_far}` trước.*"
        )

        try:
            if is_dm:
                await message.channel.send(reply_text)
            else:
                # Trong server: reply tin nhắn và tự xoá sau 25 giây để không làm rác đoạn chat
                await autorep(message, content=reply_text, auto_delete_delay=25)
        except Exception:
            pass

    # ── NHÓM LỆNH: afk ───────────────────────────────────────────────────
    @menu_entry("AUTOMATION & QUEST", "afk", "Tự trả lời khi AFK & thống kê tag/ib",
                badge="HOT", icon_sym="💤", icon_color=(59, 130, 246), order=2)
    @alias_declare("afk", main="afk", subs=[])
    @commands.group(name="afk", invoke_without_command=True)
    @require_permission("user")
    async def cmd_afk(self, ctx: commands.Context, *, reason: str = None):
        """Bật / Tắt chế độ AFK tự động:
        • (prefix)afk [tin nhắn] : Bật AFK với câu trả lời tự động tùy chọn.
        • (prefix)afk off        : Tắt chế độ AFK và xuất bảng thống kê.
        """
        p = self._pfx()

        if not self._is_owner(ctx.author.id):
            return await self._reply(ctx, "⛔ Lệnh AFK này chỉ dành cho chính chủ tài khoản tự quản lý bản thân.", delay=6)

        # Nếu gõ `afk off`
        if reason and reason.strip().lower() in ("off", "tat", "stop", "end"):
            afk_data = self._load_afk()
            if not afk_data.get("is_afk"):
                return await self._reply(ctx, "ℹ️ Bạn hiện tại chưa bật chế độ AFK.", delay=5)
            return await self._finish_afk_and_report(ctx.channel, afk_data)

        afk_data = self._load_afk()

        # Nếu đang AFK mà gõ lại lệnh không tham số -> Hiển thị tình trạng
        if reason is None and afk_data.get("is_afk"):
            start_t = afk_data.get("start_time", time.time())
            cur_dur = _format_duration(time.time() - start_t)
            m_cnt = len(afk_data.get("mentions", []))
            d_cnt = len(afk_data.get("dms", []))
            return await self._reply(
                ctx,
                f"💤 **BẠN ĐANG TRONG CHẾ ĐỘ AFK**\n"
                f"• **Thời gian:** `{cur_dur}`\n"
                f"• **Lời nhắn phản hồi:** *\"{afk_data.get('message')}\"*\n"
                f"• **Đã ghi nhận:** `{m_cnt}` lần Tag • `{d_cnt}` lần Inbox riêng.\n\n"
                f"👉 Gõ `{p}afk off` hoặc nhắn tin bất kỳ để tắt AFK và nhận báo cáo.",
                delay=15,
            )

        # Nếu chưa AFK và gõ trống -> Hiển thị bảng hướng dẫn hoặc bật mặc định
        if reason is None:
            # Gửi Card đồ hoạ Glassmorphism
            card_buf = None
            try:
                card_buf = await async_help_card("afk", p)
            except Exception:
                card_buf = None

            if card_buf:
                try:
                    file = discord.File(card_buf, filename="afk_guide.png")
                    return await autorep(
                        ctx.message,
                        content=f"💤 **HỆ THỐNG AFK TỰ ĐỘNG PHẢN HỒI** (`{p}afk`)",
                        file=file,
                        auto_delete_delay=35,
                    )
                except Exception:
                    pass

            reason = DEFAULT_AFK_MSG

        # ── TIẾN HÀNH BẬT CHẾ ĐỘ AFK ──
        reply_message = reason.strip()
        new_data = {
            "is_afk": True,
            "start_time": time.time(),
            "message": reply_message,
            "mentions": [],
            "dms": [],
        }
        self._save_afk(new_data)
        self._user_cooldowns.clear()

        await self._reply(
            ctx,
            f"💤 **ĐÃ BẬT CHẾ ĐỘ AFK THÀNH CÔNG**\n"
            f"• **Tin nhắn tự trả lời:** *\"{reply_message}\"*\n"
            f"• **Cơ chế:** Khi có người Tag hoặc Inbox riêng (DM), bot sẽ tự động phản hồi lại họ và lưu lại nhật ký.\n"
            f"• **Cách tắt:** Nhắn tin bất kỳ hoặc gõ `{p}afk off` để nhận bảng thống kê chi tiết.",
            delay=15,
        )

    @cmd_afk.command(name="off", aliases=["tat", "stop", "end"])
    @require_permission("user")
    async def afk_off(self, ctx: commands.Context):
        """Chủ động tắt AFK và xuất bảng thống kê."""
        if not self._is_owner(ctx.author.id):
            return await self._reply(ctx, "⛔ Lệnh này chỉ dành cho chính chủ tài khoản.", delay=6)

        afk_data = self._load_afk()
        if not afk_data.get("is_afk"):
            return await self._reply(ctx, "ℹ️ Bạn hiện tại chưa bật chế độ AFK.", delay=5)
        await self._finish_afk_and_report(ctx.channel, afk_data)

    @cmd_afk.command(name="status", aliases=["stt", "info"])
    @require_permission("user")
    async def afk_status(self, ctx: commands.Context):
        """Xem tình trạng AFK hiện tại."""
        p = self._pfx()
        afk_data = self._load_afk()
        if not afk_data.get("is_afk"):
            return await self._reply(ctx, f"ℹ️ Bạn đang **ONLINE** bình thường (Chế độ AFK đang TẮT). Gõ `{p}afk <lời nhắn>` để bật.", delay=8)

        start_t = afk_data.get("start_time", time.time())
        cur_dur = _format_duration(time.time() - start_t)
        m_cnt = len(afk_data.get("mentions", []))
        d_cnt = len(afk_data.get("dms", []))

        await self._reply(
            ctx,
            f"💤 **TRẠNG THÁI AFK HIỆN TẠI**\n"
            f"• **Đã vắng mặt:** `{cur_dur}`\n"
            f"• **Lời nhắn phản hồi:** *\"{afk_data.get('message')}\"*\n"
            f"• **Số lần được Tag:** `{m_cnt}` lần\n"
            f"• **Số lần Inbox riêng:** `{d_cnt}` lần\n\n"
            f"👉 Nhắn tin bất kỳ hoặc gõ `{p}afk off` để kết thúc.",
            delay=15,
        )

    @cmd_afk.command(name="clear", aliases=["xoa"])
    @require_permission("user")
    async def afk_clear(self, ctx: commands.Context):
        """Xoá sạch nhật ký tin nhắn ghi nhận mà vẫn giữ nguyên chế độ AFK."""
        if not self._is_owner(ctx.author.id):
            return await self._reply(ctx, "⛔ Lệnh này chỉ dành cho chính chủ tài khoản.", delay=6)

        afk_data = self._load_afk()
        afk_data["mentions"] = []
        afk_data["dms"] = []
        self._save_afk(afk_data)
        await self._reply(ctx, "🧹 Đã xoá sạch nhật ký tin nhắn ghi nhận trong đợt AFK này.", delay=6)


async def setup(bot: commands.Bot):
    await bot.add_cog(AFKCog(bot))
