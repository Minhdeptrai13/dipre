# -*- coding: utf-8 -*-
"""MODULE: activity (Rich Presence & Status Manager) - Tùy biến trạng thái cho Selfbot.

Hỗ trợ:
1. (prefix)status <online|idle|dnd|inv>: Đổi trạng thái hiển thị.
2. (prefix)play <tên>: Hiển thị đang chơi game.
3. (prefix)stream <tên> [url]: Hiển thị đang phát trực tiếp Twitch/YouTube (Huy hiệu Tím).
4. (prefix)listen <tên>: Hiển thị đang nghe nhạc.
5. (prefix)watch <tên>: Hiển thị đang xem phim/video.
6. (prefix)activity clear: Xoá hoạt động ảo.
7. Tự động lưu cấu hình theo UID vào setting.json và phục hồi khi bot khởi động lại.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

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

DEFAULT_STREAM_URL = "https://www.twitch.tv/discord"


class ActivityCog(commands.Cog, name="Activity"):
    """Quản lý trạng thái Online và Rich Presence của Selfbot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._restored = False

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return getattr(self.bot, "_own_prefix", None) or ""

    def _setting_path(self) -> Optional[Path]:
        uid = getattr(getattr(self.bot, "user", None), "id", None)
        if not uid:
            return None
        return DATA_DIR / f"{uid}_setting.json"

    def _load_presence(self) -> Dict[str, Any]:
        path = self._setting_path()
        if not path or not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("presence", {})
        except Exception:
            return {}

    def _save_presence(self, presence_data: Dict[str, Any]) -> None:
        path = self._setting_path()
        if not path:
            return
        try:
            data = {}
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            data["presence"] = presence_data
            path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[ACTIVITY] Lưu presence lỗi: {e}", flush=True)

    def _is_owner_or_mod(self, uid: int) -> bool:
        """Chỉ chủ token hoặc Admin cấp cao của bot mới có quyền đổi status/activity."""
        if self.bot.user and uid == self.bot.user.id:
            return True
        checker = getattr(self.bot, "is_mod", None)
        if callable(checker):
            try:
                return bool(checker(uid))
            except Exception:
                pass
        return False

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

    def _parse_status(self, raw: str) -> Tuple[Optional[discord.Status], str]:
        r = raw.strip().lower()
        if r in ("online", "on", "truc tuyen", "tructuyen", "1"):
            return discord.Status.online, "🟢 Trực tuyến (Online)"
        if r in ("idle", "afk", "away", "cho", "chờ", "2"):
            return discord.Status.idle, "🟡 Chờ (Idle / AFK)"
        if r in ("dnd", "busy", "ban", "bận", "dunglamphien", "đừng làm phiền", "3"):
            return discord.Status.dnd, "🔴 Đừng làm phiền (Do Not Disturb)"
        if r in ("inv", "invisible", "off", "offline", "an", "ẩn", "4"):
            return discord.Status.invisible, "⚪ Ẩn danh (Invisible)"
        return None, ""

    async def _apply_presence(self, status_val: Optional[discord.Status] = None, activity_obj: Optional[discord.BaseActivity] = None):
        """Áp dụng presence vào bot và cập nhật Discord gateway."""
        try:
            current_status = status_val or getattr(self.bot, "status", discord.Status.online)
            await self.bot.change_presence(status=current_status, activity=activity_obj)
        except Exception as exc:
            print(f"[ACTIVITY] change_presence lỗi: {exc}", flush=True)

    @commands.Cog.listener()
    async def on_ready(self):
        """Tự động khôi phục presence khi bot khởi động."""
        if self._restored:
            return
        await asyncio.sleep(2)
        saved = self._load_presence()
        if not saved:
            return

        status_str = saved.get("status", "online")
        act_type = saved.get("type", "")
        act_name = saved.get("name", "")
        act_url = saved.get("url", DEFAULT_STREAM_URL)

        st, _ = self._parse_status(status_str)
        if not st:
            st = discord.Status.online

        act = None
        if act_type == "game" and act_name:
            act = discord.Game(name=act_name)
        elif act_type == "stream" and act_name:
            act = discord.Streaming(name=act_name, url=act_url)
        elif act_type == "listen" and act_name:
            act = discord.Activity(type=discord.ActivityType.listening, name=act_name)
        elif act_type == "watch" and act_name:
            act = discord.Activity(type=discord.ActivityType.watching, name=act_name)
        elif act_type == "compete" and act_name:
            act = discord.Activity(type=discord.ActivityType.competing, name=act_name)

        await self._apply_presence(st, act)
        self._restored = True
        print(f"[ACTIVITY] Đã khôi phục Presence cho {self.bot.user}: Status={status_str}, Activity={act_type} - {act_name}", flush=True)

    # ── NHÓM LỆNH CHÍNH: rpc ─────────────────────────────────────────────
    @menu_entry("PROFILE & PRESENCE", "rpc", "Tùy biến trạng thái Online / Stream / Game (RPC)",
                badge="HOT", icon_sym="🎮", icon_color=(168, 85, 247), order=2)
    @alias_declare("rpc", main="rpc", subs=["activity", "presence", "act"])
    @commands.group(name="rpc", aliases=["activity", "presence", "act"], invoke_without_command=True)
    @require_permission("user")
    async def cmd_rpc(self, ctx: commands.Context, *, arg: str = None):
        """Bảng quản lý Rich Presence Control (RPC) và Status."""
        p = self._pfx()
        if arg is None:
            card_buf = None
            try:
                card_buf = await async_help_card("rpc", p)
            except Exception:
                try:
                    card_buf = await async_help_card("activity", p)
                except Exception:
                    card_buf = None

            if card_buf:
                try:
                    file = discord.File(card_buf, filename="rpc_guide.png")
                    return await autorep(
                        ctx.message,
                        content=f"🎮 **HỆ THỐNG RICH PRESENCE CONTROL** (`{p}rpc`)",
                        file=file,
                        auto_delete_delay=35,
                    )
                except Exception:
                    pass

            guide_text = (
                f"🎮 **HỆ THỐNG RICH PRESENCE CONTROL (`{p}rpc`)**\n\n"
                f"• `{p}rpc status <online|idle|dnd|inv>` — Đổi trạng thái trực tuyến\n"
                f"• `{p}rpc play <tên game>` — Hiển thị đang chơi game\n"
                f"• `{p}rpc stream <tên stream> [link]` — Hiển thị phát trực tiếp (Huy hiệu tím)\n"
                f"• `{p}rpc listen <tên bài hát>` — Hiển thị đang nghe nhạc\n"
                f"• `{p}rpc watch <tên phim/video>` — Hiển thị đang xem phim\n"
                f"• `{p}rpc compete <tên giải đấu>` — Hiển thị đang thi đấu\n"
                f"• `{p}rpc clear` — Xoá hoạt động ảo, trở về bình thường\n"
                f"• `{p}rpc info` — Xem trạng thái đang được cài đặt"
            )
            return await self._reply(ctx, guide_text, delay=30)

        await self._reply(ctx, f"❓ Lệnh không hợp lệ. Gõ `{p}rpc` để xem bảng hướng dẫn.", delay=6)

    # ── SUBCOMMANDS DƯỚI rpc ──────────────────────────────────────────────
    @cmd_rpc.command(name="status", aliases=["stt", "setstatus"])
    @require_permission("user")
    async def rpc_status(self, ctx: commands.Context, *, status_arg: str = None):
        """(prefix)rpc status <online|idle|dnd|inv>"""
        await self._do_status(ctx, status_arg)

    @cmd_rpc.command(name="play", aliases=["game", "setgame"])
    @require_permission("user")
    async def rpc_play(self, ctx: commands.Context, *, name: str = None):
        """(prefix)rpc play <tên game>"""
        await self._do_play(ctx, name)

    @cmd_rpc.command(name="stream", aliases=["streaming", "live", "setstream"])
    @require_permission("user")
    async def rpc_stream(self, ctx: commands.Context, *, text: str = None):
        """(prefix)rpc stream <tên stream> [link]"""
        await self._do_stream(ctx, text)

    @cmd_rpc.command(name="listen", aliases=["listening", "music", "song"])
    @require_permission("user")
    async def rpc_listen(self, ctx: commands.Context, *, name: str = None):
        """(prefix)rpc listen <tên bài hát>"""
        await self._do_listen(ctx, name)

    @cmd_rpc.command(name="watch", aliases=["watching", "movie", "film"])
    @require_permission("user")
    async def rpc_watch(self, ctx: commands.Context, *, name: str = None):
        """(prefix)rpc watch <tên phim/video>"""
        await self._do_watch(ctx, name)

    @cmd_rpc.command(name="compete", aliases=["competing", "setcompete"])
    @require_permission("user")
    async def rpc_compete(self, ctx: commands.Context, *, name: str = None):
        """(prefix)rpc compete <tên giải đấu>"""
        await self._do_compete(ctx, name)

    @cmd_rpc.command(name="clear", aliases=["xoa", "reset", "off"])
    @require_permission("user")
    async def rpc_clear(self, ctx: commands.Context):
        """(prefix)rpc clear"""
        if not self._is_owner_or_mod(ctx.author.id):
            return await self._reply(ctx, "⛔ Chỉ chủ tài khoản hoặc Admin bot mới có quyền thay đổi Activity.", delay=6)

        saved = self._load_presence()
        st_str = saved.get("status", "online")
        st, _ = self._parse_status(st_str)
        if not st:
            st = discord.Status.online

        await self._apply_presence(st, None)
        saved["type"] = ""
        saved["name"] = ""
        self._save_presence(saved)

        await self._reply(ctx, "🧹 Đã xoá toàn bộ hoạt động ảo (Rich Presence). Trở về trạng thái bình thường.", delay=6)

    @cmd_rpc.command(name="info", aliases=["check"])
    @require_permission("user")
    async def rpc_info(self, ctx: commands.Context):
        """(prefix)rpc info"""
        saved = self._load_presence()
        st = saved.get("status", "online")
        act_type = saved.get("type") or "Không có"
        act_name = saved.get("name") or "Không có"
        act_url = saved.get("url") or ""

        info_text = (
            "🎮 **THÔNG TIN RPC HIỆN TẠI**\n"
            f"• **Trạng thái:** `{st.upper()}`\n"
            f"• **Hoạt động:** `{act_type}`\n"
            f"• **Nội dung:** {f'**{act_name}**' if act_name != 'Không có' else 'Trống'}\n"
        )
        if act_url:
            info_text += f"• **Link stream:** <{act_url}>\n"
        await self._reply(ctx, info_text, delay=15)

    # ── HANDLERS DÙNG CHUNG (CHO CẢ RPC & SHORTCUT) ────────────────────────
    async def _do_status(self, ctx: commands.Context, status_arg: str = None):
        p = self._pfx()
        if not self._is_owner_or_mod(ctx.author.id):
            return await self._reply(ctx, "⛔ Chỉ chủ tài khoản hoặc Admin bot mới có quyền đổi trạng thái.", delay=6)

        if not status_arg:
            return await self._reply(
                ctx,
                f"❌ Cú pháp: `{p}rpc status <online|idle|dnd|inv>`\n"
                f"• `online` / `on`: Trực tuyến 🟢\n"
                f"• `idle` / `afk`: Chờ 🟡\n"
                f"• `dnd` / `busy`: Đừng làm phiền 🔴\n"
                f"• `inv` / `off`: Ẩn danh ⚪",
                delay=15,
            )

        st, label = self._parse_status(status_arg)
        if not st:
            return await self._reply(ctx, f"❌ Trạng thái `{status_arg}` không hợp lệ (hỗ trợ: online, idle, dnd, inv).", delay=6)

        saved = self._load_presence()
        saved["status"] = status_arg.strip().lower()
        self._save_presence(saved)

        act = None
        if self.bot.user and hasattr(self.bot, "activity"):
            act = self.bot.activity

        await self._apply_presence(st, act)
        await self._reply(ctx, f"✅ Đã đổi trạng thái sang: **{label}**.", delay=6)

    async def _do_play(self, ctx: commands.Context, name: str = None):
        p = self._pfx()
        if not self._is_owner_or_mod(ctx.author.id):
            return await self._reply(ctx, "⛔ Chỉ chủ tài khoản hoặc Admin bot mới có quyền đổi Activity.", delay=6)

        if not name:
            return await self._reply(ctx, f"❌ Cú pháp: `{p}rpc play <tên game>` (Ví dụ: `{p}rpc play Valorant`)", delay=10)

        game = discord.Game(name=name.strip())
        saved = self._load_presence()
        st, _ = self._parse_status(saved.get("status", "online"))
        if not st:
            st = discord.Status.online

        await self._apply_presence(st, game)

        saved["type"] = "game"
        saved["name"] = name.strip()
        self._save_presence(saved)

        await self._reply(ctx, f"🎮 Đã cập nhật hoạt động: **Đang chơi {name.strip()}**", delay=6)

    async def _do_stream(self, ctx: commands.Context, text: str = None):
        p = self._pfx()
        if not self._is_owner_or_mod(ctx.author.id):
            return await self._reply(ctx, "⛔ Chỉ chủ tài khoản hoặc Admin bot mới có quyền đổi Activity.", delay=6)

        if not text:
            return await self._reply(
                ctx,
                f"❌ Cú pháp: `{p}rpc stream <tên stream> [link twitch/youtube]`\n"
                f"• Ví dụ: `{p}rpc stream Leo Rank Thách Đấu https://twitch.tv/mychannel`\n"
                f"• Hoặc: `{p}rpc stream Nghe Nhạc Chill` (tự động dùng link mặc định)",
                delay=12,
            )

        parts = text.strip().split()
        url = DEFAULT_STREAM_URL
        name = text.strip()

        if parts[-1].startswith(("http://", "https://")):
            url = parts[-1]
            name = " ".join(parts[:-1]).strip()

        if not name:
            name = "Trực tiếp"

        stream_act = discord.Streaming(name=name, url=url)
        saved = self._load_presence()
        st, _ = self._parse_status(saved.get("status", "online"))
        if not st:
            st = discord.Status.online

        await self._apply_presence(st, stream_act)

        saved["type"] = "stream"
        saved["name"] = name
        saved["url"] = url
        self._save_presence(saved)

        await self._reply(
            ctx,
            f"🟣 **ĐÃ BẬT TRẠNG THÁI STREAMING**\n"
            f"• Nội dung: **{name}**\n"
            f"• Link: <{url}>",
            delay=8,
        )

    async def _do_listen(self, ctx: commands.Context, name: str = None):
        p = self._pfx()
        if not self._is_owner_or_mod(ctx.author.id):
            return await self._reply(ctx, "⛔ Chỉ chủ tài khoản hoặc Admin bot mới có quyền đổi Activity.", delay=6)

        if not name:
            return await self._reply(ctx, f"❌ Cú pháp: `{p}rpc listen <tên bài hát/nhạc>`", delay=10)

        act = discord.Activity(type=discord.ActivityType.listening, name=name.strip())
        saved = self._load_presence()
        st, _ = self._parse_status(saved.get("status", "online"))
        if not st:
            st = discord.Status.online

        await self._apply_presence(st, act)

        saved["type"] = "listen"
        saved["name"] = name.strip()
        self._save_presence(saved)

        await self._reply(ctx, f"🎧 Đã cập nhật hoạt động: **Đang nghe {name.strip()}**", delay=6)

    async def _do_watch(self, ctx: commands.Context, name: str = None):
        p = self._pfx()
        if not self._is_owner_or_mod(ctx.author.id):
            return await self._reply(ctx, "⛔ Chỉ chủ tài khoản hoặc Admin bot mới có quyền đổi Activity.", delay=6)

        if not name:
            return await self._reply(ctx, f"❌ Cú pháp: `{p}rpc watch <tên phim/video>`", delay=10)

        act = discord.Activity(type=discord.ActivityType.watching, name=name.strip())
        saved = self._load_presence()
        st, _ = self._parse_status(saved.get("status", "online"))
        if not st:
            st = discord.Status.online

        await self._apply_presence(st, act)

        saved["type"] = "watch"
        saved["name"] = name.strip()
        self._save_presence(saved)

        await self._reply(ctx, f"🎬 Đã cập nhật hoạt động: **Đang xem {name.strip()}**", delay=6)

    async def _do_compete(self, ctx: commands.Context, name: str = None):
        p = self._pfx()
        if not self._is_owner_or_mod(ctx.author.id):
            return await self._reply(ctx, "⛔ Chỉ chủ tài khoản hoặc Admin bot mới có quyền đổi Activity.", delay=6)

        if not name:
            return await self._reply(ctx, f"❌ Cú pháp: `{p}rpc compete <tên giải đấu>`", delay=10)

        act = discord.Activity(type=discord.ActivityType.competing, name=name.strip())
        saved = self._load_presence()
        st, _ = self._parse_status(saved.get("status", "online"))
        if not st:
            st = discord.Status.online

        await self._apply_presence(st, act)

        saved["type"] = "compete"
        saved["name"] = name.strip()
        self._save_presence(saved)

        await self._reply(ctx, f"🏆 Đã cập nhật hoạt động: **Đang thi đấu trong {name.strip()}**", delay=6)

    # ── CÁC LỆNH GÕ TẮT (SHORTCUT TOÀN CỤC) ────────────────────────────────
    @commands.command(name="status", aliases=["stt", "setstatus"])
    @require_permission("user")
    async def cmd_status(self, ctx: commands.Context, *, status_arg: str = None):
        """Đổi trạng thái Online: (prefix)status <online|idle|dnd|inv>"""
        await self._do_status(ctx, status_arg)

    @commands.command(name="play", aliases=["game", "setgame"])
    @require_permission("user")
    async def cmd_play(self, ctx: commands.Context, *, name: str = None):
        """Đặt trạng thái đang chơi game: (prefix)play <tên game>"""
        await self._do_play(ctx, name)

    @commands.command(name="stream", aliases=["streaming", "live", "setstream"])
    @require_permission("user")
    async def cmd_stream(self, ctx: commands.Context, *, text: str = None):
        """Đặt trạng thái phát trực tiếp (Huy hiệu tím): (prefix)stream <tên stream> [link]"""
        await self._do_stream(ctx, text)

    @commands.command(name="listen", aliases=["listening", "music", "setlisten"])
    @require_permission("user")
    async def cmd_listen(self, ctx: commands.Context, *, name: str = None):
        """Đặt trạng thái đang nghe nhạc: (prefix)listen <tên bài hát>"""
        await self._do_listen(ctx, name)

    @commands.command(name="watch", aliases=["watching", "movie", "setwatch"])
    @require_permission("user")
    async def cmd_watch(self, ctx: commands.Context, *, name: str = None):
        """Đặt trạng thái đang xem phim/video: (prefix)watch <tên>"""
        await self._do_watch(ctx, name)

    @commands.command(name="compete", aliases=["competing", "setcompete"])
    @require_permission("user")
    async def cmd_compete(self, ctx: commands.Context, *, name: str = None):
        """Đặt trạng thái đang thi đấu: (prefix)compete <tên giải/cuộc thi>"""
        await self._do_compete(ctx, name)


async def setup(bot: commands.Bot):
    await bot.add_cog(ActivityCog(bot))
