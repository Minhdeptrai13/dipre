# -*- coding: utf-8 -*-
"""
MODULE: war (War Arena - Auto Spam Sớ & Poll Trừng Phạt Kẻ Phá Hoại)
- Lệnh chính: war (alias: var).
- war: Mở bảng hướng dẫn Liquid Glass đồ họa xịn sò.
- war reo <@tag|uid> [delay] [số_lượng]: Spam tag chửi liên thanh bằng sớ từ data/war_txt.
- war poll <@tag|uid> [delay] [số_lượng]: Spam tạo khảo sát Poll tag đối phương liên tục.
- war off / stop: Dừng toàn bộ tiến trình war đang chạy.
"""
from __future__ import annotations

import asyncio
import datetime
import os
import random
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

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
except ImportError:
    from core.bot_sys import require_permission
    from core.alias import alias_declare
    from utils.prefix import fmt, get_prefix
    from utils.autorep import autorep
    from utils.autodelet import autodelet
    from utils.media_card import async_help_card
    from utils.menu_catalog import menu_entry

BASE_DIR = Path(__file__).resolve().parent.parent
WAR_TXT_DIR = BASE_DIR / "data" / "war_txt"

# Cache danh sách câu chửi
_WAR_LINES: List[str] = []
_LAST_LOAD_TIME = 0.0

# Quản lý tác vụ ngầm đang chạy: channel_id -> set of asyncio.Task
_ACTIVE_WAR_TASKS: Dict[int, Set[asyncio.Task]] = {}


def _load_war_lines() -> List[str]:
    """Tải và làm sạch toàn bộ câu chửi từ các file trong data/war_txt."""
    global _WAR_LINES, _LAST_LOAD_TIME
    now = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0
    if _WAR_LINES and (now - _LAST_LOAD_TIME < 60.0):
        return _WAR_LINES

    lines: List[str] = []
    if WAR_TXT_DIR.exists():
        for txt_file in WAR_TXT_DIR.glob("*.txt"):
            try:
                content = txt_file.read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines():
                    clean = line.strip()
                    if clean and len(clean) > 2:
                        lines.append(clean)
            except Exception:
                pass

    if not lines:
        lines = [
            "sủa tiếp đi con chó rách",
            "cay cắn lưỡi chưa em",
            "gõ chậm thế con trai",
            "sồn hăng lên tí nữa xem nào",
            "bố mày đứng đây chờ mày sủa này",
        ]

    random.shuffle(lines)
    _WAR_LINES = lines
    _LAST_LOAD_TIME = now
    return _WAR_LINES


def _parse_target_id(target_str: str) -> Optional[int]:
    """Bóc User ID từ tag @user hoặc UID thuần."""
    if not target_str:
        return None
    target_str = str(target_str).strip()
    match = re.search(r"<@!?(\d+)>", target_str)
    if match:
        return int(match.group(1))
    digits = re.sub(r"\D", "", target_str)
    if digits and len(digits) >= 15:
        return int(digits)
    return None


class War(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return getattr(self.bot, "_own_prefix", "!") or "!"

    @menu_entry("AUTOMATION & QUEST", "war", "Auto spam sớ chửi & poll trừng phạt",
                icon_sym="⚔️", icon_color=(239, 68, 68), order=30)
    @commands.group(name="war", aliases=["var"], invoke_without_command=True)
    @require_permission("admin")
    async def cmd_war(self, ctx: commands.Context, *, sub: Optional[str] = None):
        """Bảng hướng dẫn War / Var đồ họa Liquid Glass."""
        p = self._pfx()

        card_file = None
        try:
            card_buf = await async_help_card("war", p)
            if card_buf:
                card_file = discord.File(card_buf, filename="war_guide.png")
        except Exception as e:
            print(f"[war] async_help_card error: {e}")

        text = (
            "⚔️ **HỆ THỐNG CHIẾN TRƯỜNG WAR & VAR DISCORD**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• `{p}war reo <@tag|UID> [delay] [số_lượng]` : Spam tag réo tên dồn dập bằng sớ chửi\n"
            f"• `{p}war poll <@tag|UID> [delay] [số_lượng]` : Spam tạo bình chọn Poll tag đối phương\n"
            f"• `{p}war off` (hoặc `{p}war stop`) : Dừng ngay lập tức toàn bộ tiến trình War\n\n"
            "💡 *Mẹo: Không điền [số_lượng] thì bot sẽ chạy vô hạn (infinity) cho tới khi gõ `war off`.*"
        )
        if card_file:
            await autorep(ctx, content=None, file=card_file, auto_delete_delay=60)
        else:
            await autorep(ctx, text, auto_delete_delay=60)


    @cmd_war.command(name="reo", aliases=["r", "spam", "chui"])
    @require_permission("admin")
    async def war_reo(
        self,
        ctx: commands.Context,
        target: str,
        delay: Optional[float] = 1.8,
        count: Optional[Union[int, str]] = None,
    ):
        """Spam tin nhắn tag đối phương liên thanh kèm sớ chửi."""
        p = self._pfx()
        target_uid = _parse_target_id(target)
        if not target_uid:
            await autorep(
                ctx,
                f"❌ Vui lòng tag hoặc nhập UID hợp lệ của đối phương! Ví dụ: `{p}war reo @user 1.8`",
                auto_delete_delay=15,
            )
            return

        # Chuẩn hóa delay (tối thiểu 0.8s để chống 429 quá gắt)
        actual_delay = max(0.8, float(delay or 1.8))

        # Chuẩn hóa số lượng
        actual_count: Optional[int] = None
        if count is not None:
            c_str = str(count).lower().strip()
            if c_str not in ("inf", "infinity", "vohan", "vo_han", "all", "*"):
                try:
                    actual_count = max(1, int(c_str))
                except Exception:
                    actual_count = None

        channel_id = ctx.channel.id
        tag_str = f"<@{target_uid}>"
        pool = _load_war_lines()

        # Thông báo bắt đầu ngắn gọn, tự xóa
        await autorep(ctx, f"M chết r con {tag_str}", auto_delete_delay=10)

        async def _reo_worker():
            idx = 0
            sent = 0
            lines = list(pool)
            random.shuffle(lines)

            while True:
                if actual_count is not None and sent >= actual_count:
                    break

                if idx >= len(lines):
                    lines = list(pool)
                    random.shuffle(lines)
                    idx = 0

                slogan = lines[idx]
                idx += 1

                # Đổi kiểu tag trước / sau để đa dạng
                if sent % 2 == 0:
                    msg_text = f"{tag_str} {slogan}"
                else:
                    msg_text = f"{slogan} {tag_str}"

                # Fake typing tạo hiệu ứng đang gõ sớ chửi cực chân thật
                typing_pre = min(0.4, actual_delay * 0.2)
                try:
                    await ctx.channel.trigger_typing()
                    if typing_pre > 0.05:
                        await asyncio.sleep(typing_pre)
                except Exception:
                    pass

                try:
                    await ctx.channel.send(msg_text)
                    sent += 1
                except discord.HTTPException as err:
                    if err.status == 429:
                        retry_after = getattr(err, "retry_after", 3.0)
                        await asyncio.sleep(retry_after)
                    else:
                        await asyncio.sleep(2.0)
                except Exception:
                    break

                remaining_sleep = max(0.1, actual_delay - typing_pre)
                await asyncio.sleep(remaining_sleep)

            # Kết thúc
            try:
                await ctx.channel.send("tha m đó")
            except Exception:
                pass

        task = asyncio.create_task(_reo_worker())
        tasks_set = _ACTIVE_WAR_TASKS.setdefault(channel_id, set())
        tasks_set.add(task)
        task.add_done_callback(lambda t: tasks_set.discard(t))

    @cmd_war.command(name="poll", aliases=["p", "binhchon", "vote"])
    @require_permission("admin")
    async def war_poll(
        self,
        ctx: commands.Context,
        target: str,
        delay: Optional[float] = 2.5,
        count: Optional[Union[int, str]] = None,
    ):
        """Spam tạo bình chọn Poll tag đối phương liên tục."""
        p = self._pfx()
        target_uid = _parse_target_id(target)
        if not target_uid:
            await autorep(
                ctx,
                f"❌ Vui lòng tag hoặc nhập UID hợp lệ của đối phương! Ví dụ: `{p}war poll @user 2.5`",
                auto_delete_delay=15,
            )
            return

        if not hasattr(discord, "Poll"):
            await autorep(
                ctx,
                "⚠️ Phiên bản discord.py hiện tại chưa hỗ trợ API Poll!",
                auto_delete_delay=15,
            )
            return

        actual_delay = max(1.5, float(delay or 2.5))

        actual_count: Optional[int] = None
        if count is not None:
            c_str = str(count).lower().strip()
            if c_str not in ("inf", "infinity", "vohan", "vo_han", "all", "*"):
                try:
                    actual_count = max(1, int(c_str))
                except Exception:
                    actual_count = None

        channel_id = ctx.channel.id
        tag_str = f"<@{target_uid}>"
        pool = _load_war_lines()

        # Lấy tên hiển thị của đối phương vì Poll của Discord không hỗ trợ render mention <@id>
        target_name = target.lstrip("@<>&!")
        if ctx.guild:
            m = ctx.guild.get_member(target_uid)
            if m:
                target_name = m.display_name
        if target_name == target.lstrip("@<>&!"):
            try:
                u = ctx.bot.get_user(target_uid) or await ctx.bot.fetch_user(target_uid)
                if u:
                    target_name = getattr(u, "display_name", u.name)
            except Exception:
                pass

        # Thông báo bắt đầu cực gọn, tự xóa
        await autorep(ctx, f"M chết r con {tag_str}", auto_delete_delay=10)

        async def _poll_worker():
            idx = 0
            sent = 0
            lines = list(pool)
            random.shuffle(lines)

            # Danh sách câu trả lời trêu ngươi
            ans_pairs = [
                ("Sủa tiếp đi con 🐶", "Cay cắn lưỡi rồi à 🌶️"),
                ("Dạ con xin thua bố 😭", "Mặt dày cào phím tiếp 🤡"),
                ("Đột quỵ tại chỗ ⚡", "Trốn vào xó khóc huhu 👶"),
                ("Câm họng đéo dám gõ 🤐", "Gõ chậm như rùa bò 🐢"),
            ]

            while True:
                if actual_count is not None and sent >= actual_count:
                    break

                if idx >= len(lines):
                    lines = list(pool)
                    random.shuffle(lines)
                    idx = 0

                slogan = lines[idx]
                idx += 1

                # Discord giới hạn độ dài câu hỏi poll tối đa 300 ký tự
                short_slogan = slogan[:200].strip()
                question = f"{target_name} {short_slogan}"
                if len(question) > 295:
                    question = question[:290] + "..."

                pair = random.choice(ans_pairs)
                poll = discord.Poll(question, datetime.timedelta(hours=1))
                poll.add_answer(text=pair[0])
                poll.add_answer(text=pair[1])

                # Fake typing trước khi quăng Poll
                typing_pre = min(0.5, actual_delay * 0.2)
                try:
                    await ctx.channel.trigger_typing()
                    if typing_pre > 0.05:
                        await asyncio.sleep(typing_pre)
                except Exception:
                    pass

                try:
                    await ctx.channel.send(poll=poll)
                    sent += 1
                except discord.HTTPException as err:
                    if err.status == 429:
                        retry_after = getattr(err, "retry_after", 3.5)
                        await asyncio.sleep(retry_after)
                    else:
                        await asyncio.sleep(2.5)
                except Exception:
                    break

                remaining_sleep = max(0.1, actual_delay - typing_pre)
                await asyncio.sleep(remaining_sleep)

            try:
                await ctx.channel.send("tha m đó")
            except Exception:
                pass

        task = asyncio.create_task(_poll_worker())
        tasks_set = _ACTIVE_WAR_TASKS.setdefault(channel_id, set())
        tasks_set.add(task)
        task.add_done_callback(lambda t: tasks_set.discard(t))

    @cmd_war.command(name="off", aliases=["stop", "cancel", "huy", "dung"])
    @require_permission("admin")
    async def war_off(self, ctx: commands.Context):
        """Dừng ngay lập tức toàn bộ các tác vụ war / spam đang chạy."""
        channel_id = ctx.channel.id
        stopped_count = 0

        # Dừng các task ở channel hiện tại
        tasks = list(_ACTIVE_WAR_TASKS.get(channel_id, set()))
        for t in tasks:
            if not t.done():
                t.cancel()
                stopped_count += 1
        _ACTIVE_WAR_TASKS.pop(channel_id, None)

        # Nếu không có task ở channel này, kiểm tra và dọn toàn bộ các channel khác nếu có
        if stopped_count == 0:
            for ch_id, t_set in list(_ACTIVE_WAR_TASKS.items()):
                for t in list(t_set):
                    if not t.done():
                        t.cancel()
                        stopped_count += 1
            _ACTIVE_WAR_TASKS.clear()

        if stopped_count > 0:
            await autorep(
                ctx,
                f"🛑 **ĐÃ DỪNG TOÀN BỘ TIẾN TRÌNH WAR!** (Đã hủy {stopped_count} tác vụ spam)",
                auto_delete_delay=20,
            )
        else:
            await autorep(
                ctx,
                "⚠️ Hiện tại không có tiến trình War nào đang chạy ở kênh này.",
                auto_delete_delay=15,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(War(bot))
