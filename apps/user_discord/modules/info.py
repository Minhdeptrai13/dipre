# -*- coding: utf-8 -*-
"""MODULE: info (Account & Server Inspector) - Xem thông tin chi tiết tài khoản và máy chủ.

Tính năng:
1. (prefix)info user [@user | uid | username] hoặc (prefix)userinfo / (prefix)ui:
   - Tra cứu chi tiết tài khoản: Avatar, Banner, Ngày tạo acc, Ngày vào server, Badges (Nitro, HypeSquad...), Roles, Trạng thái hoạt động, Rich Presence.
2. (prefix)info server [guild_id] hoặc (prefix)serverinfo / (prefix)si:
   - Tra cứu chi tiết máy chủ: Chủ sở hữu (Owner), Ngày tạo, Thống kê Thành viên (Người/Bot/Online), Kênh, Roles, Boost Tier & Count, Tính năng đặc biệt.
"""
from __future__ import annotations

import asyncio
import datetime
import io
import re
from typing import Any, Dict, List, Optional, Tuple, Union

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


def _format_dt(dt: Optional[datetime.datetime]) -> str:
    """Format thời gian ISO thành chuỗi hiển thị đẹp kèm thời gian tương đối."""
    if not dt:
        return "Không rõ"
    # Discord timestamp syntax
    ts = int(dt.timestamp())
    now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    diff = max(0, now_ts - ts)
    days = diff // 86400
    if days >= 365:
        rel = f"{days // 365} năm trước"
    elif days >= 30:
        rel = f"{days // 30} tháng trước"
    elif days > 0:
        rel = f"{days} ngày trước"
    else:
        hours = diff // 3600
        rel = f"{hours} giờ trước" if hours > 0 else "vừa xong"

    date_str = dt.strftime("%d/%m/%Y %H:%M")
    return f"`{date_str}` ({rel})"


def _get_user_badges(user: Union[discord.User, discord.Member]) -> List[str]:
    """Phân tích các huy hiệu Discord (User Badges) của tài khoản."""
    badges = []
    flags = getattr(user, "public_flags", None)
    if flags:
        if flags.staff:
            badges.append("🛡️ Discord Staff")
        if flags.partner:
            badges.append("🤝 Partnered Server Owner")
        if flags.hypesquad:
            badges.append("🏠 HypeSquad Events")
        if flags.bug_hunter:
            badges.append("🐛 Bug Hunter Tier 1")
        if flags.bug_hunter_level_2:
            badges.append("🐛 Bug Hunter Tier 2")
        if flags.hypesquad_bravery:
            badges.append("⚔️ HypeSquad Bravery")
        if flags.hypesquad_brilliance:
            badges.append("💡 HypeSquad Brilliance")
        if flags.hypesquad_balance:
            badges.append("⚖️ HypeSquad Balance")
        if flags.early_supporter:
            badges.append("⭐ Early Supporter")
        if flags.verified_bot_developer:
            badges.append("👨‍💻 Early Verified Bot Dev")
        if getattr(flags, "active_developer", False):
            badges.append("⚡ Active Developer")

    if isinstance(user, discord.Member):
        if user.premium_since:
            badges.append("🚀 Server Booster")

    # Kiểm tra cờ bot
    if getattr(user, "bot", False):
        badges.append("🤖 Bot App")

    return badges


class InfoCog(commands.Cog, name="Info"):
    """Module tra cứu thông tin tài khoản và máy chủ chuyên sâu."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return getattr(self.bot, "_own_prefix", None) or ""

    # ── Command Group: info ──────────────────────────────────────────────────
    @menu_entry("MEDIA & ENTERTAINMENT", "info", "Xem thông tin chi tiết tài khoản & server",
                badge="INFO", icon_sym="ℹ", icon_color=(56, 189, 248), order=4)
    @alias_declare("info", main="info", subs=["information"])
    @commands.group(name="info", aliases=["information"], invoke_without_command=True)
    @require_permission("user")
    async def cmd_info(self, ctx: commands.Context, *, target: Optional[str] = None):
        """Lệnh tra cứu thông tin. Gõ (prefix)info [user|server] hoặc truyền thẳng @user / ID."""
        p = self._pfx()

        # Nếu có tham số target
        if target:
            target_clean = target.strip()
            # Nếu truyền 'server' hoặc 'guild'
            if target_clean.lower() in ("server", "guild"):
                return await self.sub_server(ctx)
            # Thử parse user trước
            return await self.sub_user(ctx, target=target_clean)

        # Nếu không có text target nhưng tin nhắn có tag mentions (ví dụ: (prefix)info @user1 @user2)
        if ctx.message and ctx.message.mentions:
            return await self.sub_user(ctx, target=None)

        # Nếu không có tham số: Hiển thị bảng hướng dẫn ảnh Liquid Glass
        try:
            buf = await async_help_card("info", p)
            if buf:
                file = discord.File(buf, filename="info_guide.png")
                await autorep(
                    ctx.message,
                    content=f"ℹ️ **HƯỚNG DẪN TRA CỨU THÔNG TIN** (`{p}info`)",
                    file=file,
                    auto_delete_delay=35,
                )
                return
        except Exception:
            pass

        server_txt = f"• `{p}info server` — Xem máy chủ hiện tại ({ctx.guild.name})\n" if ctx.guild else ""
        msg = (
            f"ℹ️ **HỆ THỐNG TRA CỨU THÔNG TIN (INFO SYSTEM)**\n\n"
            f"📌 **Cú pháp khả dụng:**\n"
            f"• `{p}info user [@user|id...]`: Tra cứu thông tin tài khoản (hỗ trợ tag nhiều người)\n"
            f"{server_txt}"
            f"• `{p}userinfo [@user1 @user2...]` / `{p}serverinfo`: Lệnh tắt tra cứu thông tin\n\n"
            f"💡 *Ví dụ:* `{p}info @user1 @user2` hoặc `{p}info server`."
        )
        await autorep(ctx, msg, auto_delete_delay=30)

    async def _resolve_users(self, ctx: commands.Context, target: Optional[str] = None) -> List[Union[discord.Member, discord.User]]:
        """Trích xuất và tìm kiếm toàn bộ danh sách User/Member từ mentions và chuỗi target."""
        results: List[Union[discord.Member, discord.User]] = []
        seen_ids = set()

        # 1. Thu thập từ ctx.message.mentions
        if ctx.message and ctx.message.mentions:
            for m in ctx.message.mentions:
                if m.id not in seen_ids:
                    seen_ids.add(m.id)
                    results.append(m)

        # 2. Quét qua chuỗi target nếu có
        if target:
            target_str = target.strip()
            # Tìm các ID dạng số 17-20 chữ số
            raw_ids = re.findall(r"\b\d{17,20}\b", target_str)
            # Tìm các tag dạng <@12345...> hoặc <@!12345...>
            tag_ids = re.findall(r"<@!?(\d+)>", target_str)
            combined_ids = []
            for tid in tag_ids + raw_ids:
                if tid not in combined_ids:
                    combined_ids.append(tid)

            for tid in combined_ids:
                try:
                    uid = int(tid)
                except ValueError:
                    continue
                if uid in seen_ids:
                    continue

                # Tìm trong guild
                member = ctx.guild.get_member(uid) if ctx.guild else None
                if member:
                    seen_ids.add(uid)
                    results.append(member)
                    continue

                # Fetch từ Discord API
                try:
                    user = await self.bot.fetch_user(uid)
                    if user:
                        seen_ids.add(uid)
                        results.append(user)
                except Exception:
                    pass

            # Nếu không có mention và không có ID nào tìm thấy, thử tìm theo tên trong server
            if not results and ctx.guild:
                t_lower = target_str.lower()
                for m in ctx.guild.members:
                    if (
                        t_lower in m.name.lower()
                        or (m.nick and t_lower in m.nick.lower())
                        or (m.global_name and t_lower in m.global_name.lower())
                    ):
                        if m.id not in seen_ids:
                            seen_ids.add(m.id)
                            results.append(m)
                            break

        # 3. Nếu không có ai và không truyền target -> lấy ctx.author
        if not results and not target:
            results.append(ctx.author)

        return results

    # ── Subcommand: info user ────────────────────────────────────────────────
    @cmd_info.command(name="user", aliases=["member", "account"])
    @require_permission("user")
    async def sub_user(self, ctx: commands.Context, *, target: Optional[str] = None):
        """Tra cứu thông tin tài khoản (Hỗ trợ 1 hoặc nhiều @user / UID): (prefix)info user [@user1 @user2...]."""
        users = await self._resolve_users(ctx, target=target)
        if not users:
            p = self._pfx()
            return await autorep(
                ctx,
                f"❌ **Không tìm thấy tài khoản hợp lệ nào từ yêu cầu `{target}`!**\n"
                f"💡 Hãy tag `@user` hoặc nhập ID gồm 17-20 chữ số (Ví dụ: `{p}ui 123456789012345678`).",
                auto_delete_delay=20,
            )

        # ── TRƯỜNG HỢP 1: DUY NHẤT 1 USER ──
        if len(users) == 1:
            return await self._show_single_user_info(ctx, users[0])

        # ── TRƯỜNG HỢP 2: NHIỀU USER ĐƯỢC TAG CÙNG LÚC ──
        return await self._show_multi_user_info(ctx, users)

    async def _show_single_user_info(self, ctx: commands.Context, user: Union[discord.User, discord.Member]):
        """Hiển thị thông tin chi tiết đầy đủ cho 1 tài khoản."""
        is_member = isinstance(user, discord.Member)
        u_name = user.name
        g_name = getattr(user, "global_name", None) or u_name
        uid = user.id
        avatar_url = user.display_avatar.url if user.display_avatar else None
        banner_url = getattr(user, "banner", None)
        if banner_url:
            banner_url = banner_url.url

        created_str = _format_dt(user.created_at)
        joined_str = _format_dt(user.joined_at) if is_member else "Không ở trong server này"

        # Badges
        badges = _get_user_badges(user)
        badges_str = " • ".join(badges) if badges else "Không có huy hiệu đặc biệt"

        # Trạng thái hiện diện & Client
        status_icon = "⚪ Offline"
        client_icons = []
        if is_member:
            status_map = {
                discord.Status.online: "🟢 Online",
                discord.Status.idle: "🟡 Chờ (Idle)",
                discord.Status.dnd: "🔴 Không làm phiền (DND)",
                discord.Status.offline: "⚪ Ngoại tuyến (Offline)",
            }
            status_icon = status_map.get(user.status, "⚪ Offline")

            # Client statuses (Mobile, Desktop, Web)
            if hasattr(user, "mobile_status") and user.mobile_status != discord.Status.offline:
                client_icons.append("📱 Mobile")
            if hasattr(user, "desktop_status") and user.desktop_status != discord.Status.offline:
                client_icons.append("💻 Desktop")
            if hasattr(user, "web_status") and user.web_status != discord.Status.offline:
                client_icons.append("🌐 Web")

        client_str = " | ".join(client_icons) if client_icons else "Không xác định"

        # Roles
        roles_info = "Không có"
        highest_role = "Không có"
        if is_member and ctx.guild:
            guild_roles = [r for r in user.roles if r != ctx.guild.default_role]
            if guild_roles:
                guild_roles.sort(key=lambda r: r.position, reverse=True)
                highest_role = guild_roles[0].mention
                role_mentions = [r.mention for r in guild_roles[:12]]
                roles_info = " ".join(role_mentions)
                if len(guild_roles) > 12:
                    roles_info += f" *+{len(guild_roles) - 12} role khác*"
            else:
                highest_role = "`@everyone`"

        # Activities / Rich presence
        activity_str = "Không hoạt động"
        if is_member and user.activities:
            acts = []
            for a in user.activities:
                if isinstance(a, discord.Spotify):
                    acts.append(f"🎧 **Spotify:** *{a.title}* - {a.artist}")
                elif isinstance(a, discord.CustomActivity):
                    c_txt = f"{a.emoji} " if a.emoji else ""
                    c_txt += str(a.name or "")
                    if c_txt.strip():
                        acts.append(f"💬 **Trạng thái:** \"{c_txt.strip()}\"")
                elif a.type == discord.ActivityType.playing:
                    acts.append(f"🎮 **Đang chơi:** {a.name}")
                elif a.type == discord.ActivityType.streaming:
                    acts.append(f"🟣 **Đang Stream:** [{a.name}]({getattr(a, 'url', '')})")
                elif a.type == discord.ActivityType.listening:
                    acts.append(f"🎵 **Đang nghe:** {a.name}")
                elif a.type == discord.ActivityType.watching:
                    acts.append(f"🎬 **Đang xem:** {a.name}")
            if acts:
                activity_str = "\n".join(acts)

        links = [f"[Avatar Link]({avatar_url})"]
        if banner_url:
            links.append(f"[Banner Link]({banner_url})")
        links_str = " • ".join(links)

        card_file = None
        try:
            buf = await self.render_user_info_card(user, ctx.guild)
            if buf:
                card_file = discord.File(buf, filename="user_info.png")
        except Exception as e:
            print(f"[userinfo] Lỗi vẽ card: {e}", flush=True)

        msg = (
            f"👤 **THÔNG TIN TÀI KHOẢN: {g_name}** (`@{u_name}`)\n\n"
            f"🆔 **User ID:** `{uid}`\n"
            f"🏷️ **Tên hiển thị:** {g_name} | **Username:** @{u_name}\n"
            f"🏅 **Huy hiệu:** {badges_str}\n"
            f"📶 **Trạng thái:** {status_icon} ({client_str})\n\n"
            f"📅 **Mốc thời gian:**\n"
            f"• 🎂 **Ngày tạo tài khoản:** {created_str}\n"
            f"• 📥 **Ngày vào máy chủ:** {joined_str}\n\n"
            f"🎭 **Vai trò (Roles):**\n"
            f"• **Cao nhất:** {highest_role}\n"
            f"• **Danh sách:** {roles_info}\n\n"
            f"🎯 **Hoạt động hiện tại:**\n{activity_str}\n\n"
            f"🖼️ **Hình ảnh:** {links_str}"
        )
        if card_file:
            await autorep(ctx.message, content=f"👤 **THÔNG TIN TÀI KHOẢN: {g_name}** (`@{u_name}`)", file=card_file, auto_delete_delay=60)
        else:
            await autorep(ctx, msg, auto_delete_delay=60)

    async def _show_multi_user_info(self, ctx: commands.Context, users: List[Union[discord.User, discord.Member]]):
        """Hiển thị thông tin cho nhiều tài khoản được tag cùng lúc."""
        total = len(users)

        # 1. Render card ảnh cho tối đa 4 user đầu tiên (chạy song song)
        render_targets = users[:4]
        tasks = [self.render_user_info_card(u, ctx.guild) for u in render_targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        card_files: List[discord.File] = []
        for idx, res in enumerate(results):
            if isinstance(res, io.BytesIO):
                u_obj = render_targets[idx]
                card_files.append(discord.File(res, filename=f"user_{u_obj.id}.png"))

        # 2. Xây dựng văn bản tổng hợp chi tiết
        num_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        lines = [
            f"👥 **THÔNG TIN ĐA TÀI KHOẢN ({total} NGƯỜI DÙNG ĐƯỢC TAG)**\n"
        ]

        for i, u in enumerate(users, 1):
            is_mem = isinstance(u, discord.Member)
            g_name = getattr(u, "global_name", None) or getattr(u, "display_name", None) or u.name
            u_name = u.name
            uid = u.id

            created_str = _format_dt(u.created_at)
            joined_str = _format_dt(u.joined_at) if is_mem else "Chưa vào server này"

            # Status
            status_icon = "⚪ Offline"
            if is_mem:
                status_map = {
                    discord.Status.online: "🟢 Online",
                    discord.Status.idle: "🟡 Chờ",
                    discord.Status.dnd: "🔴 Bận (DND)",
                    discord.Status.offline: "⚪ Ngoại tuyến",
                }
                status_icon = status_map.get(u.status, "⚪ Offline")

            # Roles
            highest_role = "Không có"
            if is_mem and ctx.guild:
                guild_roles = [r for r in u.roles if r != ctx.guild.default_role]
                if guild_roles:
                    guild_roles.sort(key=lambda r: r.position, reverse=True)
                    highest_role = guild_roles[0].mention

            badges = _get_user_badges(u)
            badges_str = " ".join(badges) if badges else "Thành viên"
            num_tag = num_emojis[i - 1] if i <= 10 else f"`{i}.`"

            lines.append(
                f"{num_tag} **{g_name}** (`@{u_name}`) • ID: `{uid}`\n"
                f"   • 📶 **Trạng thái:** {status_icon} • 🏅 **Huy hiệu:** {badges_str}\n"
                f"   • 🎂 **Tạo:** {created_str}\n"
                f"   • 📥 **Vào SV:** {joined_str}\n"
                f"   • 🎭 **Role cao nhất:** {highest_role}\n"
            )

        if total > 4:
            lines.append(f"*(Đã đính kèm ảnh card thông tin cho 4 tài khoản đầu tiên)*")

        final_content = "\n".join(lines)
        if len(final_content) > 1900:
            final_content = final_content[:1880] + "\n...(quá dài đã rút gọn)"

        if card_files:
            await autorep(
                ctx.message,
                content=final_content,
                files=card_files,
                auto_delete_delay=90,
            )
        else:
            await autorep(ctx.message, content=final_content, auto_delete_delay=90)

    async def render_user_info_card(self, user: Union[discord.User, discord.Member], guild: Optional[discord.Guild] = None) -> io.BytesIO:
        try:
            from apps.user_discord.utils import glass as G
        except ImportError:
            from utils import glass as G

        avatar_img = None
        if user.display_avatar:
            try:
                avatar_img = await G.fetch_image(str(user.display_avatar.url))
            except Exception:
                pass

        is_member = isinstance(user, discord.Member)
        u_name = user.name
        g_name = getattr(user, "global_name", None) or getattr(user, "display_name", None) or u_name
        uid = str(user.id)

        created_str = user.created_at.strftime("%d/%m/%Y") if user.created_at else "?"
        joined_str = user.joined_at.strftime("%d/%m/%Y") if (is_member and user.joined_at) else "Chưa vào server"

        status_txt = "Offline"
        status_col = (148, 163, 184)
        if is_member:
            if user.status == discord.Status.online:
                status_txt = "Online"
                status_col = (34, 197, 94)
            elif user.status == discord.Status.idle:
                status_txt = "Idle (Chờ)"
                status_col = (234, 179, 8)
            elif user.status == discord.Status.dnd:
                status_txt = "Do Not Disturb"
                status_col = (239, 68, 68)

        highest_role = "None"
        role_count = 0
        if is_member and guild:
            roles = [r for r in user.roles if r != guild.default_role]
            role_count = len(roles)
            if roles:
                roles.sort(key=lambda r: r.position, reverse=True)
                highest_role = roles[0].name

        badges = _get_user_badges(user)
        badges_str = " • ".join(badges) if badges else "Thành viên thông thường"

        info = {
            "name": g_name,
            "username": u_name,
            "uid": uid,
            "created": created_str,
            "joined": joined_str,
            "status": status_txt,
            "status_col": status_col,
            "role": highest_role,
            "role_count": role_count,
            "badges": badges_str,
            "is_bot": getattr(user, "bot", False),
        }
        return await asyncio.to_thread(self._draw_user_glass, G, info, avatar_img)

    @staticmethod
    def _draw_user_glass(G, info: Dict[str, Any], avatar_img) -> io.BytesIO:
        pad, gap, head_h, stat_h = 24, 16, 108, 80
        LW = 1180
        LH = pad + head_h + gap + stat_h + gap + 160 + pad
        cv = G.GlassCanvas(LW, LH)

        # ── Header: Avatar + Display Name + Username + UID ──
        cv.glass((pad, pad, LW - pad, pad + head_h), 24, blur=24)
        isz = 72
        ring_col = G.G_PURPLE if info["is_bot"] else G.G_BLUE
        cv.circle_image(avatar_img, pad + 20, pad + (head_h - isz) / 2, isz, ring=ring_col, ring_w=3, letter=info["name"][:1])

        tx = pad + 20 + isz + 18
        f_t = cv.font("modak", 24)
        tmax = LW - pad - 20 - 200 - tx
        name_fit = cv.fit(G.clean_text(info["name"]) or "User", f_t, tmax)
        tw = cv.text(tx, pad + head_h / 2 - 14, name_fit, f_t, G.C_TEXT, vcenter=True)
        bot_badge_text = "BOT" if info["is_bot"] else "USER"
        bot_badge_grad = G.G_PURPLE if info["is_bot"] else G.G_GREEN
        cv.pill(tx + tw + 14, pad + head_h / 2 - 24, bot_badge_text, cv.font("b", 11), bot_badge_grad, h=20, padx=10)
        cv.text(tx, pad + head_h / 2 + 16, f"@{info['username']}   •   ID: {info['uid']}", cv.font("r", 12.5), G.C_MUTED, vcenter=True)

        cv.glass_pill(LW - pad - 20, pad + head_h / 2 - 15, info["status"], cv.font("b", 12), G.G_SLATE, align="r", dot=info["status_col"])

        # ── 4 Ô Thống kê ──
        sy = pad + head_h + gap
        stats = [
            ("NGÀY TẠO ACC", info["created"], "🎂", "C", (96, 165, 250)),
            ("VÀO MÁY CHỦ", info["joined"], "📥", "J", (52, 211, 153)),
            ("VAI TRÒ CHÍNH", cv.fit(info["role"], cv.font("b", 12), 160), "🎭", "R", (167, 139, 250)),
            ("SỐ LƯỢNG ROLE", f"{info['role_count']} roles", "🛡️", "L", (244, 114, 182)),
        ]
        tw_ = (LW - 2 * pad - 3 * gap) / 4
        for i, (lbl, val, sym, fb, col) in enumerate(stats):
            x1 = pad + i * (tw_ + gap)
            cv.glass((x1, sy, x1 + tw_, sy + stat_h), 20, blur=22, tint=(12, 16, 28, 50))
            cv.chip((x1 + 16, sy + 20, x1 + 56, sy + 60), sym, fb, col, r=12, size=19)
            vx = x1 + 70
            cv.text(vx, sy + 30, lbl, cv.font("b", 10.5), col, vcenter=True)
            cv.text(vx, sy + 52, val, cv.font("b", 13), G.C_TEXT, vcenter=True)

        # ── Panel Chi tiết đáy (Kèm QR Code kết bạn Discord) ──
        by = sy + stat_h + gap
        bh = 176
        cv.glass((pad, by, LW - pad, by + bh), 22, blur=24, tint=(14, 18, 30, 80))
        cv.text(pad + 24, by + 26, "THÔNG TIN BỔ SUNG & KẾT NỐI", cv.font("b", 13), G.C_GOLD, vcenter=True)

        # ── QR Code mở profile kết bạn Discord ──
        qr_box_w = 138
        qr_x2 = LW - pad - 20
        qr_x1 = qr_x2 - qr_box_w
        qr_y1 = by + 16
        qr_y2 = by + bh - 16

        cv.glass((qr_x1, qr_y1, qr_x2, qr_y2), 16, blur=18, tint=(255, 255, 255, 30), rim=(255, 90))
        try:
            import qrcode
            from PIL import Image, ImageOps
            qr = qrcode.QRCode(box_size=4, border=1)
            qr.add_data(f"https://discord.com/users/{info['uid']}")
            qr.make(fit=True)
            qr_raw = qr.make_image(fill_color=(15, 23, 42), back_color=(255, 255, 255)).convert("RGBA")
            q_sz = int(cv.s(104))
            qr_fitted = qr_raw.resize((q_sz, q_sz), Image.Resampling.NEAREST)
            q_x = int(cv.s(qr_x1 + (qr_box_w - 104) / 2))
            q_y = int(cv.s(qr_y1 + 10))
            # Nền trắng bo góc giúp máy ảnh quét dễ dàng 100%
            white_bg = Image.new("RGBA", (q_sz + 4, q_sz + 4), (255, 255, 255, 255))
            cv.c.paste(white_bg, (q_x - 2, q_y - 2))
            cv.c.paste(qr_fitted, (q_x, q_y))
            cv.text((qr_x1 + qr_x2) / 2, qr_y2 - 13, "QUÉT KẾT BẠN", cv.font("b", 10), G.C_GOLD, align="c", vcenter=True)
        except Exception as _e:
            print(f"[userinfo QR error]: {_e}", flush=True)
            cv.text((qr_x1 + qr_x2) / 2, (qr_y1 + qr_y2) / 2, "DISCORD QR", cv.font("b", 11), G.C_MUTED, align="c", vcenter=True)

        # ── Thông tin bên trái (không lấn sang vùng QR) ──
        text_max_w = qr_x1 - (pad + 24) - 24
        detail_lines = [
            ("Huy hiệu Discord: ", info["badges"]),
            ("Trạng thái hoạt động: ", info["status"]),
            ("Quyền hạn máy chủ: ", f"Thành viên thuộc {info['role_count']} vai trò trong server."),
            ("Kết bạn nhanh: ", "Quét mã QR góc phải bằng Camera hoặc Discord Mobile để mở trang cá nhân."),
        ]
        dy = by + 54
        for title_l, val_l in detail_lines:
            val_fit = cv.fit(val_l, cv.font("b", 12), text_max_w - cv.tlen(title_l, cv.font("r", 12)))
            cv.rich(pad + 24, dy, [(title_l, cv.font("r", 12), G.C_MUTED), (val_fit, cv.font("b", 12), G.C_TEXT)], vcenter=True)
            dy += 26

        return cv.finalize()

    # ── Subcommand: info server ──────────────────────────────────────────────
    @cmd_info.command(name="server", aliases=["guild"])
    @require_permission("user")
    async def sub_server(self, ctx: commands.Context, *, target: Optional[str] = None):
        """Tra cứu thông tin máy chủ Discord: (prefix)info server [guild_id]."""
        p = self._pfx()
        guild: Optional[discord.Guild] = None

        if not target:
            guild = ctx.guild
        else:
            t = target.strip()
            if t.isdigit():
                guild = self.bot.get_guild(int(t))
            else:
                for g in self.bot.guilds:
                    if t.lower() in g.name.lower():
                        guild = g
                        break

        if not guild:
            return await autorep(
                ctx,
                f"❌ **Không tìm thấy máy chủ `{target or ''}`!**\n"
                f"💡 Lệnh cần được chạy bên trong server hoặc cung cấp ID server mà bot đã tham gia.",
                auto_delete_delay=20,
            )

        card_file = None
        try:
            from apps.user_discord.modules.server import ServerCog
            scog = ServerCog(self.bot)
            buf = await scog.render_server_info_card(guild)
            if buf:
                card_file = discord.File(buf, filename="server_info.png")
        except Exception as e:
            print(f"[serverinfo] Lỗi vẽ card server: {e}", flush=True)

        owner = guild.owner
        if not owner and guild.owner_id:
            owner = guild.get_member(guild.owner_id) or await self.bot.fetch_user(guild.owner_id)
        owner_str = f"{owner.name} (`{owner.id}`)" if owner else f"ID: `{guild.owner_id}`"

        created_str = _format_dt(guild.created_at)

        total_members = guild.member_count or len(guild.members)
        bots = sum(1 for m in guild.members if m.bot)
        humans = total_members - bots
        online = sum(1 for m in guild.members if m.status != discord.Status.offline)

        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        stage_channels = len(guild.stage_channels)
        forum_channels = len(getattr(guild, "forum_channels", []))
        total_channels = len(guild.channels)

        boost_tier = guild.premium_tier
        boost_count = guild.premium_subscription_count or 0

        roles_count = len(guild.roles)
        emojis_count = len(guild.emojis)
        stickers_count = len(guild.stickers)

        icon_url = guild.icon.url if guild.icon else None
        banner_url = guild.banner.url if guild.banner else None
        splash_url = guild.splash.url if guild.splash else None

        img_links = []
        if icon_url:
            img_links.append(f"[Server Icon]({icon_url})")
        if banner_url:
            img_links.append(f"[Server Banner]({banner_url})")
        if splash_url:
            img_links.append(f"[Splash Invite]({splash_url})")
        img_str = " • ".join(img_links) if img_links else "Không có"

        vanity = getattr(guild, "vanity_url_code", None)
        vanity_str = f"https://discord.gg/{vanity}" if vanity else "Không có"

        features_list = [f.replace("_", " ").title() for f in guild.features[:8]]
        features_str = ", ".join(features_list) if features_list else "Mặc định"
        if len(guild.features) > 8:
            features_str += f" *+{len(guild.features) - 8} tính năng khác*"

        msg = (
            f"🏰 **THÔNG TIN MÁY CHỦ: {guild.name}**\n\n"
            f"🆔 **Server ID:** `{guild.id}`\n"
            f"👑 **Chủ sở hữu (Owner):** {owner_str}\n"
            f"🎂 **Ngày tạo:** {created_str}\n\n"
            f"👥 **Thành viên ({total_members:,}):**\n"
            f"• 👤 Người thật: `{humans:,}` | 🤖 Bots: `{bots:,}`\n"
            f"• 🟢 Trực tuyến (Cached): `{online:,}`\n\n"
            f"📺 **Kênh ({total_channels}):**\n"
            f"• 💬 Văn bản: `{text_channels}` | 🔊 Thoại: `{voice_channels}`\n"
            f"• 📁 Danh mục: `{categories}` | 🎙️ Stage: `{stage_channels}` | 📋 Diễn đàn: `{forum_channels}`\n\n"
            f"🚀 **Nitro Boost:**\n"
            f"• Cấp độ: **Tier {boost_tier}** | Số lượt Boost: **{boost_count} boosts**\n\n"
            f"🎨 **Tài nguyên & Tính năng:**\n"
            f"• 🎭 Roles: `{roles_count}` | 😀 Emojis: `{emojis_count}` | 🏷️ Stickers: `{stickers_count}`\n"
            f"• 🔗 Link riêng (Vanity): `{vanity_str}`\n"
            f"• ✨ Tính năng: {features_str}\n\n"
            f"🖼️ **Hình ảnh máy chủ:** {img_str}"
        )
        if card_file:
            await autorep(ctx.message, content=f"🏰 **THÔNG TIN MÁY CHỦ: {guild.name}**", file=card_file, auto_delete_delay=60)
        else:
            await autorep(ctx, msg, auto_delete_delay=60)

    # ── Fast Shortcuts: userinfo, serverinfo ────────────────────────────────
    @commands.command(name="userinfo", aliases=["whois"])
    @require_permission("user")
    async def fast_userinfo(self, ctx: commands.Context, *, target: Optional[str] = None):
        """Lệnh tắt tra cứu thông tin user: (prefix)userinfo [@user|uid]."""
        await self.sub_user(ctx, target=target)

    @commands.command(name="serverinfo", aliases=["guildinfo"])
    @require_permission("user")
    async def fast_serverinfo(self, ctx: commands.Context, *, target: Optional[str] = None):
        """Lệnh tắt tra cứu thông tin máy chủ: (prefix)serverinfo [id]."""
        await self.sub_server(ctx, target=target)


async def setup(bot: commands.Bot):
    """Đăng ký Cog Info vào bot."""
    await bot.add_cog(InfoCog(bot))
