# -*- coding: utf-8 -*-
"""MODULE: voice (Voice 24/7 & Auto-Keeper) - Treo phòng Voice 24/7 siêu nhẹ & tự động kết nối lại.

Tính năng:
1. (prefix)voice join [channel_id | link] hoặc (prefix)vjoin:
   - Vào phòng voice chỉ định, duy trì kết nối 24/7 thông qua Gateway Opcode 4 (siêu nhẹ, không tốn RAM).
   - Tự động Mute & Deafen để tiết kiệm băng thông tối đa.
   - Lưu cấu hình vĩnh viễn theo UID tài khoản, khởi động lại bot tự vào lại.
2. (prefix)voice leave hoặc (prefix)vleave:
   - Rời phòng voice và tắt chế độ treo 24/7.
3. (prefix)voice status hoặc (prefix)vstatus:
   - Xem chi tiết trạng thái: phòng đang treo, server, thời gian đã treo (uptime), Mute/Deaf/Video.
4. (prefix)voice deaf <on|off>:
   - Bật / tắt chế độ điếc tai ảo (Deafen).
5. (prefix)voice mute <on|off>:
   - Bật / tắt chế độ tắt mic ảo (Mute).
6. (prefix)voice video <on|off>:
   - Bật / tắt trạng thái camera ảo (Video).
7. (prefix)voice move <channel_id>:
   - Chuyển sang kênh voice khác nhanh chóng.
8. (prefix)voice keeper <on|off>:
   - Bật / tắt cơ chế tự động kết nối lại khi bị kick hoặc rớt mạng.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import discord
from discord.ext import commands

try:
    from apps.user_discord.core.bot_sys import require_permission
    from apps.user_discord.utils.prefix import fmt, get_prefix
    from apps.user_discord.utils.menu_catalog import menu_entry
    from apps.user_discord.utils.media_card import async_help_card
    from apps.user_discord.utils.autorep import autorep
    from apps.user_discord.core.alias import alias_declare
except ImportError:
    from core.bot_sys import require_permission
    from utils.prefix import fmt, get_prefix
    from utils.menu_catalog import menu_entry
    from utils.media_card import async_help_card
    from utils.autorep import autorep
    try:
        from core.alias import alias_declare
    except ImportError:
        def alias_declare(*args, **kwargs):
            return lambda f: f

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _format_uptime(seconds: float) -> str:
    """Đổi số giây uptime thành chuỗi định dạng đẹp."""
    s = int(seconds)
    if s < 60:
        return f"{s} giây"
    m = s // 60
    rem_s = s % 60
    if m < 60:
        return f"{m} phút {rem_s}s"
    h = m // 60
    rem_m = m % 60
    if h < 24:
        return f"{h} giờ {rem_m}p"
    d = h // 24
    rem_h = h % 24
    return f"{d} ngày {rem_h}h {rem_m}p"


def _extract_channel_id(query: str) -> Optional[int]:
    """Trích xuất channel ID từ chuỗi văn bản hoặc link Discord."""
    if not query:
        return None
    query = query.strip()
    if query.isdigit():
        return int(query)
    # Hỗ trợ dạng link: https://discord.com/channels/guild_id/channel_id
    m = re.search(r"/channels/\d+/(\d+)", query)
    if m:
        return int(m.group(1))
    return None


class VoiceCog(commands.Cog, name="Voice247"):
    """Quản lý kết nối Voice 24/7 và Auto-Keeper cho Selfbot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._keeper_task: Optional[asyncio.Task] = None
        self._reconnecting = False
        self._restored = False
        # Khởi chạy loop keeper
        self._start_keeper_task()

    def cog_unload(self):
        """Dọn dẹp background task khi cog bị reload/unload."""
        if self._keeper_task and not self._keeper_task.done():
            self._keeper_task.cancel()

    def _start_keeper_task(self):
        if self._keeper_task is None or self._keeper_task.done():
            self._keeper_task = asyncio.create_task(self._keeper_loop())

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return getattr(self.bot, "_own_prefix", None) or ""

    def _voice_file(self) -> Optional[Path]:
        uid = getattr(getattr(self.bot, "user", None), "id", None)
        if not uid:
            return None
        return DATA_DIR / f"{uid}_voice.json"

    def _load_config(self) -> Dict[str, Any]:
        path = self._voice_file()
        if not path or not path.exists():
            return {
                "enabled": False,
                "guild_id": None,
                "channel_id": None,
                "self_mute": True,
                "self_deaf": True,
                "self_video": False,
                "auto_keeper": True,
                "connected_at": 0,
            }
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
            data.setdefault("enabled", False)
            data.setdefault("guild_id", None)
            data.setdefault("channel_id", None)
            data.setdefault("self_mute", True)
            data.setdefault("self_deaf", True)
            data.setdefault("self_video", False)
            data.setdefault("auto_keeper", True)
            data.setdefault("connected_at", 0)
            return data
        except Exception:
            return {
                "enabled": False,
                "guild_id": None,
                "channel_id": None,
                "self_mute": True,
                "self_deaf": True,
                "self_video": False,
                "auto_keeper": True,
                "connected_at": 0,
            }

    def _save_config(self, cfg: Dict[str, Any]) -> None:
        path = self._voice_file()
        if not path:
            return
        try:
            path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[VOICE] Lỗi lưu cấu hình voice: {e}")

    def _find_voice_channel(self, channel_id: int) -> Optional[discord.VoiceChannel | discord.StageChannel]:
        """Tìm kênh voice theo ID trên toàn bộ cache của bot."""
        ch = self.bot.get_channel(channel_id)
        if ch and isinstance(ch, (discord.VoiceChannel, discord.StageChannel)):
            return ch
        # Tìm trong các guild
        for guild in self.bot.guilds:
            vch = guild.get_channel(channel_id)
            if vch and isinstance(vch, (discord.VoiceChannel, discord.StageChannel)):
                return vch
        return None

    def _get_current_voice_state(self) -> Optional[Tuple[discord.Guild, discord.VoiceChannel | discord.StageChannel]]:
        """Lấy guild và channel voice mà bot hiện đang tham gia thực tế."""
        me_id = getattr(getattr(self.bot, "user", None), "id", None)
        if not me_id:
            return None
        for guild in self.bot.guilds:
            me = guild.me or guild.get_member(me_id)
            if me and me.voice and me.voice.channel:
                return guild, me.voice.channel
        return None

    async def _apply_voice_state(
        self,
        guild: discord.Guild,
        channel: Optional[discord.VoiceChannel | discord.StageChannel],
        self_mute: bool = True,
        self_deaf: bool = True,
        self_video: bool = False,
    ) -> bool:
        """Gửi Gateway Opcode 4 (change_voice_state) an toàn và nhẹ nhất."""
        try:
            # Ngắt các audio voice_client thừa nếu có
            if channel is None:
                for vc in self.bot.voice_clients:
                    if vc.guild.id == guild.id:
                        try:
                            await vc.disconnect(force=True)
                        except Exception:
                            pass
            await guild.change_voice_state(
                channel=channel,
                self_mute=self_mute,
                self_deaf=self_deaf,
                self_video=self_video,
            )
            return True
        except Exception as e:
            print(f"[VOICE] Lỗi change_voice_state: {e}")
            return False

    # ── Background Keeper Loop ────────────────────────────────────────────────
    async def _keeper_loop(self):
        """Task chạy ngầm định kỳ 45s: Đảm bảo tự động nối lại phòng nếu bị rớt mạng."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(4.0)

        while not self.bot.is_closed():
            try:
                await asyncio.sleep(30.0)
                cfg = self._load_config()
                if not cfg.get("enabled") or not cfg.get("auto_keeper"):
                    continue

                ch_id = cfg.get("channel_id")
                if not ch_id:
                    continue

                curr = self._get_current_voice_state()
                # Nếu chưa ở trong kênh voice nào hoặc bị move sang kênh khác
                if curr is None or curr[1].id != ch_id:
                    target_ch = self._find_voice_channel(ch_id)
                    if target_ch:
                        print(f"[VOICE 24/7] Keeper phát hiện mất kết nối. Đang phục hồi vào #{target_ch.name}...")
                        await self._apply_voice_state(
                            guild=target_ch.guild,
                            channel=target_ch,
                            self_mute=cfg.get("self_mute", True),
                            self_deaf=cfg.get("self_deaf", True),
                            self_video=cfg.get("self_video", False),
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[VOICE] Keeper loop warning: {e}")
                await asyncio.sleep(10.0)

    # ── Event Listeners ───────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_ready(self):
        """Khi bot khởi động xong, tự động khôi phục kết nối voice nếu đã bật 24/7."""
        if self._restored:
            return
        self._restored = True
        await asyncio.sleep(3.0)
        cfg = self._load_config()
        if cfg.get("enabled") and cfg.get("channel_id"):
            ch_id = cfg.get("channel_id")
            ch = self._find_voice_channel(ch_id)
            if ch:
                print(f"[VOICE 24/7] Khôi phục treo voice phòng: {ch.name} ({ch.id})")
                await self._apply_voice_state(
                    guild=ch.guild,
                    channel=ch,
                    self_mute=cfg.get("self_mute", True),
                    self_deaf=cfg.get("self_deaf", True),
                    self_video=cfg.get("self_video", False),
                )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Phát hiện bot bị ngắt kết nối đột ngột hoặc bị kick để lập tức reconnect."""
        if not self.bot.user or member.id != self.bot.user.id:
            return

        cfg = self._load_config()
        if not cfg.get("enabled") or not cfg.get("auto_keeper"):
            return

        target_ch_id = cfg.get("channel_id")
        if not target_ch_id:
            return

        # Nếu bot bị kick ra ngoài (after.channel is None)
        if after.channel is None and not self._reconnecting:
            self._reconnecting = True
            await asyncio.sleep(4.0)  # Đợi nhẹ trước khi reconnect
            try:
                ch = self._find_voice_channel(target_ch_id)
                if ch:
                    print(f"[VOICE 24/7] Bị ngắt kết nối. Đang tự động kết nối lại #{ch.name}...")
                    await self._apply_voice_state(
                        guild=ch.guild,
                        channel=ch,
                        self_mute=cfg.get("self_mute", True),
                        self_deaf=cfg.get("self_deaf", True),
                        self_video=cfg.get("self_video", False),
                    )
            finally:
                self._reconnecting = False

    # ── Command Group: voice / v247 ──────────────────────────────────────────
    @menu_entry("AUTOMATION & QUEST", "voice", "Treo Voice 24/7 nhẹ mượt & tự động giữ phòng",
                badge="VOICE", icon_sym="🎙", icon_color=(74, 222, 128), order=3)
    @alias_declare("voice", main="voice", subs=["v247"])
    @commands.group(name="voice", aliases=["v247"], invoke_without_command=True)
    @require_permission("user")
    async def cmd_voice(self, ctx: commands.Context):
        """Lệnh điều khiển Voice 24/7. Gõ không tham số để mở bảng trợ giúp."""
        p = self._pfx()
        cfg = self._load_config()
        curr = self._get_current_voice_state()

        status_text = "🟢 Đang treo" if (curr and curr[1].id == cfg.get("channel_id")) else "🔴 Đang tắt"
        chan_name = f"#{curr[1].name}" if curr else "Chưa tham gia"

        commands_list = [
            (f"{p}voice join [id/link]", "Tham gia phòng voice & kích hoạt 24/7"),
            (f"{p}voice leave", "Rời phòng voice & tắt chế độ treo"),
            (f"{p}voice status", "Xem chi tiết thông số Uptime & cài đặt"),
            (f"{p}voice deaf <on|off>", "Bật/tắt điếc tai ảo (Deafen)"),
            (f"{p}voice mute <on|off>", "Bật/tắt tắt mic ảo (Mute)"),
            (f"{p}voice video <on|off>", "Bật/tắt camera ảo (Video)"),
            (f"{p}voice keeper <on|off>", "Bật/tắt tự động vào lại khi bị kick"),
            (f"{p}vjoin / {p}vleave", "Lệnh gõ tắt nhanh tiện lợi"),
        ]

        card_buf = None
        try:
            card_buf = await async_help_card("voice", p)
        except Exception:
            card_buf = None

        card_file = discord.File(card_buf, filename="voice_guide.png") if card_buf else None

        msg_body = (
            f"🎙️ **VOICE 24/7 & AUTO-KEEPER DASHBOARD**\n"
            f"Trạng thái: **{status_text}** | Phòng: **{chan_name}**\n\n"
            f"📌 **Các lệnh thông dụng:**\n"
            f"• `{p}voice join [channel_id]` hoặc `{p}vjoin`: Tham gia phòng voice\n"
            f"• `{p}voice leave` hoặc `{p}vleave`: Rời phòng và tắt treo\n"
            f"• `{p}voice status`: Xem thời gian uptime\n"
            f"• `{p}voice deaf on/off`: Chế độ điếc tai (mặc định: ON)\n"
            f"• `{p}voice mute on/off`: Chế độ tắt mic (mặc định: ON)\n"
        )
        await autorep(ctx, msg_body, file=card_file, auto_delete_delay=35)

    # ── Subcommand: join ──────────────────────────────────────────────────────
    @cmd_voice.command(name="join", aliases=["connect", "j"])
    @require_permission("user")
    async def sub_join(self, ctx: commands.Context, *, target: Optional[str] = None):
        """Tham gia vào một kênh voice chỉ định và lưu cấu hình 24/7."""
        channel: Optional[discord.VoiceChannel | discord.StageChannel] = None

        if target:
            ch_id = _extract_channel_id(target)
            if ch_id:
                channel = self._find_voice_channel(ch_id)
            if not channel:
                # Thử tìm theo tên kênh trong guild hiện tại
                if ctx.guild:
                    for vc in ctx.guild.voice_channels:
                        if target.lower() in vc.name.lower():
                            channel = vc
                            break
        else:
            # Nếu không truyền id, thử lấy kênh mà tác giả lệnh đang đứng
            if ctx.author and getattr(ctx.author, "voice", None) and ctx.author.voice.channel:
                channel = ctx.author.voice.channel

        if not channel:
            p = self._pfx()
            return await autorep(
                ctx,
                f"❌ **Không tìm thấy phòng voice!**\n"
                f"💡 **Cách dùng:**\n"
                f"• Nhập ID kênh: `{p}voice join 123456789012345678`\n"
                f"• Hoặc copy link kênh voice: `{p}voice join https://discord.com/channels/.../...`\n"
                f"• Hoặc bạn vào trước một phòng voice rồi gõ `{p}voice join`.",
                auto_delete_delay=20,
            )

        guild = channel.guild
        cfg = self._load_config()
        self_mute = cfg.get("self_mute", True)
        self_deaf = cfg.get("self_deaf", True)
        self_video = cfg.get("self_video", False)

        success = await self._apply_voice_state(
            guild=guild,
            channel=channel,
            self_mute=self_mute,
            self_deaf=self_deaf,
            self_video=self_video,
        )

        if not success:
            return await autorep(
                ctx,
                f"⚠️ **Không thể kết nối vào #{channel.name}!** Vui lòng kiểm tra quyền xem và kết nối kênh voice của tài khoản.",
                auto_delete_delay=15,
            )

        cfg["enabled"] = True
        cfg["guild_id"] = guild.id
        cfg["channel_id"] = channel.id
        cfg["connected_at"] = time.time()
        self._save_config(cfg)

        mute_badge = "🔇 Mute: BẬT" if self_mute else "🎙️ Mute: TẮT"
        deaf_badge = "🎧 Deaf: BẬT" if self_deaf else "🔊 Deaf: TẮT"
        video_badge = "📹 Video: BẬT" if self_video else "📷 Video: TẮT"

        msg = (
            f"✅ **Đã kết nối thành công vào phòng Voice 24/7!**\n\n"
            f"📡 **Máy chủ:** `{guild.name}` (`{guild.id}`)\n"
            f"🔊 **Phòng voice:** **#{channel.name}** (`{channel.id}`)\n"
            f"⚙️ **Cài đặt:** {mute_badge} | {deaf_badge} | {video_badge}\n"
            f"🛡️ **Auto-Keeper:** `BẬT` (Tự động kết nối lại nếu bị kick hoặc rớt mạng)\n\n"
            f"💡 *Tài khoản sẽ duy trì online trong kênh này 24/7 kể cả khi khởi động lại bot.*"
        )
        await autorep(ctx, msg, auto_delete_delay=25)

    # ── Subcommand: leave ─────────────────────────────────────────────────────
    @cmd_voice.command(name="leave", aliases=["disconnect", "dc", "quit", "stop"])
    @require_permission("user")
    async def sub_leave(self, ctx: commands.Context):
        """Rời phòng voice hiện tại và tắt chế độ treo 24/7."""
        curr = self._get_current_voice_state()
        cfg = self._load_config()

        target_guild = curr[0] if curr else None
        if not target_guild and cfg.get("guild_id"):
            target_guild = self.bot.get_guild(cfg["guild_id"])

        if target_guild:
            await self._apply_voice_state(guild=target_guild, channel=None)

        # Tính thời gian đã treo
        uptime_str = "0 giây"
        if cfg.get("connected_at") and cfg.get("connected_at") > 0:
            uptime_str = _format_uptime(time.time() - cfg["connected_at"])

        cfg["enabled"] = False
        cfg["guild_id"] = None
        cfg["channel_id"] = None
        cfg["connected_at"] = 0
        self._save_config(cfg)

        await autorep(
            ctx,
            f"🛑 **Đã ngắt kết nối và tắt chế độ Voice 24/7!**\n"
            f"⏱️ **Tổng thời gian đã treo phiên vừa qua:** `{uptime_str}`",
            auto_delete_delay=20,
        )

    # ── Subcommand: status ────────────────────────────────────────────────────
    @cmd_voice.command(name="status", aliases=["info"])
    @require_permission("user")
    async def sub_status(self, ctx: commands.Context):
        """Xem trạng thái chi tiết của Voice 24/7."""
        cfg = self._load_config()
        curr = self._get_current_voice_state()
        p = self._pfx()

        if not curr:
            status_text = "🔴 **Đang KHÔNG ở trong phòng Voice nào**"
            if cfg.get("enabled"):
                status_text += "\n⚠️ *Cấu hình 24/7 đang BẬT nhưng mất kết nối. Auto-Keeper sẽ sớm nối lại!*"
            return await autorep(
                ctx,
                f"{status_text}\n\n"
                f"💡 Gõ `{p}voice join <channel_id>` để bắt đầu treo voice 24/7.",
                auto_delete_delay=20,
            )

        guild, channel = curr
        uptime_str = "Vừa kết nối"
        if cfg.get("connected_at") and cfg.get("connected_at") > 0:
            uptime_str = _format_uptime(time.time() - cfg["connected_at"])

        is_247 = "🟢 BẬT (Tự kết nối lại vĩnh viễn)" if cfg.get("enabled") else "⚪ TẮT (Chỉ đang treo tạm)"
        keeper = "🛡️ BẬT" if cfg.get("auto_keeper") else "⚠️ TẮT"

        msg = (
            f"📊 **BÁO CÁO TRẠNG THÁI VOICE 24/7**\n\n"
            f"🔊 **Phòng voice:** **#{channel.name}** (`{channel.id}`)\n"
            f"📡 **Máy chủ:** `{guild.name}` (`{guild.id}`)\n"
            f"⏱️ **Thời gian đã treo (Uptime):** `{uptime_str}`\n"
            f"🔄 **Chế độ 24/7:** {is_247}\n"
            f"🛡️ **Auto-Keeper:** {keeper}\n\n"
            f"⚙️ **Trạng thái Stream:**\n"
            f"• 🔇 **Mute:** `{'BẬT' if cfg.get('self_mute') else 'TẮT'}`\n"
            f"• 🎧 **Deafen:** `{'BẬT' if cfg.get('self_deaf') else 'TẮT'}`\n"
            f"• 📹 **Video/Camera:** `{'BẬT' if cfg.get('self_video') else 'TẮT'}`"
        )
        await autorep(ctx, msg, auto_delete_delay=30)

    # ── Subcommand: deaf ──────────────────────────────────────────────────────
    @cmd_voice.command(name="deaf", aliases=["deafen"])
    @require_permission("user")
    async def sub_deaf(self, ctx: commands.Context, state: Optional[str] = None):
        """Bật/tắt trạng thái điếc tai ảo (Deafen)."""
        cfg = self._load_config()
        if state is None:
            new_val = not cfg.get("self_deaf", True)
        else:
            new_val = state.lower() in ("on", "true", "1", "bat", "bật", "yes")

        cfg["self_deaf"] = new_val
        self._save_config(cfg)

        curr = self._get_current_voice_state()
        if curr:
            guild, channel = curr
            await self._apply_voice_state(
                guild=guild,
                channel=channel,
                self_mute=cfg.get("self_mute", True),
                self_deaf=new_val,
                self_video=cfg.get("self_video", False),
            )

        status = "BẬT (Điếc tai)" if new_val else "TẮT (Nghe bình thường)"
        await autorep(ctx, f"🎧 Chế độ Deafen: **{status}**", auto_delete_delay=15)

    # ── Subcommand: mute ──────────────────────────────────────────────────────
    @cmd_voice.command(name="mute")
    @require_permission("user")
    async def sub_mute(self, ctx: commands.Context, state: Optional[str] = None):
        """Bật/tắt trạng thái tắt mic ảo (Mute)."""
        cfg = self._load_config()
        if state is None:
            new_val = not cfg.get("self_mute", True)
        else:
            new_val = state.lower() in ("on", "true", "1", "bat", "bật", "yes")

        cfg["self_mute"] = new_val
        self._save_config(cfg)

        curr = self._get_current_voice_state()
        if curr:
            guild, channel = curr
            await self._apply_voice_state(
                guild=guild,
                channel=channel,
                self_mute=new_val,
                self_deaf=cfg.get("self_deaf", True),
                self_video=cfg.get("self_video", False),
            )

        status = "BẬT (Tắt mic)" if new_val else "TẮT (Mở mic)"
        await autorep(ctx, f"🔇 Chế độ Mute: **{status}**", auto_delete_delay=15)

    # ── Subcommand: video ─────────────────────────────────────────────────────
    @cmd_voice.command(name="video", aliases=["cam", "camera"])
    @require_permission("user")
    async def sub_video(self, ctx: commands.Context, state: Optional[str] = None):
        """Bật/tắt camera ảo (Video state)."""
        cfg = self._load_config()
        if state is None:
            new_val = not cfg.get("self_video", False)
        else:
            new_val = state.lower() in ("on", "true", "1", "bat", "bật", "yes")

        cfg["self_video"] = new_val
        self._save_config(cfg)

        curr = self._get_current_voice_state()
        if curr:
            guild, channel = curr
            await self._apply_voice_state(
                guild=guild,
                channel=channel,
                self_mute=cfg.get("self_mute", True),
                self_deaf=cfg.get("self_deaf", True),
                self_video=new_val,
            )

        status = "BẬT" if new_val else "TẮT"
        await autorep(ctx, f"📹 Trạng thái Camera/Video: **{status}**", auto_delete_delay=15)

    # ── Subcommand: keeper ────────────────────────────────────────────────────
    @cmd_voice.command(name="keeper", aliases=["reconnect", "auto"])
    @require_permission("user")
    async def sub_keeper(self, ctx: commands.Context, state: Optional[str] = None):
        """Bật/tắt cơ chế Auto-Keeper (tự động kết nối lại khi bị kick/rớt mạng)."""
        cfg = self._load_config()
        if state is None:
            new_val = not cfg.get("auto_keeper", True)
        else:
            new_val = state.lower() in ("on", "true", "1", "bat", "bật", "yes")

        cfg["auto_keeper"] = new_val
        self._save_config(cfg)

        status = "BẬT" if new_val else "TẮT"
        await autorep(
            ctx,
            f"🛡️ Auto-Keeper tự động kết nối lại phòng: **{status}**",
            auto_delete_delay=15,
        )

    # ── Shortcut commands: vjoin, vleave, vstatus ─────────────────────────────
    @commands.command(name="vjoin")
    @require_permission("user")
    async def fast_vjoin(self, ctx: commands.Context, *, target: Optional[str] = None):
        """Lệnh tắt tham gia voice: (prefix)vjoin [id|link]."""
        await self.sub_join(ctx, target=target)

    @commands.command(name="vleave")
    @require_permission("user")
    async def fast_vleave(self, ctx: commands.Context):
        """Lệnh tắt rời voice: (prefix)vleave."""
        await self.sub_leave(ctx)

    @commands.command(name="vstatus")
    @require_permission("user")
    async def fast_vstatus(self, ctx: commands.Context):
        """Lệnh tắt kiểm tra trạng thái voice: (prefix)vstatus."""
        await self.sub_status(ctx)


async def setup(bot: commands.Bot):
    """Đăng ký Cog Voice vào bot."""
    await bot.add_cog(VoiceCog(bot))
