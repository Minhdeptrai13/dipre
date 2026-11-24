# -*- coding: utf-8 -*-
"""
MODULE: x (X / Twitter Media Downloader)
- Lệnh độc lập: (prefix)x <link>
- Tải video và GIF từ nền tảng X (Twitter) siêu tốc.
- Thẻ hướng dẫn Liquid Glass chuẩn chỉ, tự động xóa thông báo sau thời gian quy định.
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands
import yt_dlp

try:
    from apps.user_discord.core.bot_sys import require_permission
    from apps.user_discord.core.alias import alias_declare
    from apps.user_discord.utils.prefix import fmt, get_prefix
    from apps.user_discord.utils.menu_catalog import menu_entry
    from apps.user_discord.utils.media_card import async_help_card
    from apps.user_discord.utils.autorep import autorep
    from apps.user_discord.utils.autodelet import autodelet
except ImportError:
    from core.bot_sys import require_permission
    from core.alias import alias_declare
    from utils.prefix import fmt, get_prefix
    from utils.menu_catalog import menu_entry
    from utils.media_card import async_help_card
    from utils.autorep import autorep
    from utils.autodelet import autodelet

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = DATA_DIR / "downloads"
TEMP_DIR.mkdir(parents=True, exist_ok=True)


class XDownloader(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return "!"

    @staticmethod
    def _fmt_num(n) -> str:
        if not n:
            return '0'
        try:
            val = int(n)
            if val >= 1_000_000:
                return f"{val / 1_000_000:.1f}M"
            if val >= 1_000:
                return f"{val / 1_000:.1f}K"
            return str(val)
        except Exception:
            return str(n)

    async def _download_and_send(self, message: discord.Message, url: str):
        timestamp = int(time.time())
        out_tmpl = str(TEMP_DIR / f"x_{timestamp}_%(id)s.%(ext)s")

        loop = asyncio.get_event_loop()
        def _exec():
            ydl_opts = {
                'outtmpl': out_tmpl,
                'quiet': True,
                'no_warnings': True,
                'max_filesize': 25 * 1024 * 1024,
                'format': 'best[ext=mp4]/best',
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                return info, filename

        try:
            info, filepath = await loop.run_in_executor(None, _exec)
            if os.path.exists(filepath) and os.path.getsize(filepath) <= 25 * 1024 * 1024:
                title = info.get("title") or "X Video"
                uploader = info.get("uploader") or info.get("channel") or "Twitter User"
                uploader_id = info.get("uploader_id") or ""
                likes = self._fmt_num(info.get("like_count"))
                comments = self._fmt_num(info.get("comment_count"))
                shares = self._fmt_num(info.get("repost_count"))
                views = self._fmt_num(info.get("view_count"))
                cover_url = info.get("thumbnail")

                # Render Card Info Liquid Glass
                card_buf = None
                try:
                    from apps.user_discord.utils.media_card import async_media_post_card
                    card_buf = await async_media_post_card(
                        platform="X",
                        title=title,
                        author_nick=uploader,
                        author_user=uploader_id,
                        cover_url=cover_url,
                        likes=likes,
                        comments=comments,
                        shares=shares,
                        views=views,
                        badge="TWEET HD"
                    )
                except Exception:
                    try:
                        from utils.media_card import async_media_post_card
                        card_buf = await async_media_post_card(
                            platform="X",
                            title=title,
                            author_nick=uploader,
                            author_user=uploader_id,
                            cover_url=cover_url,
                            likes=likes,
                            comments=comments,
                            shares=shares,
                            views=views,
                            badge="TWEET HD"
                        )
                    except Exception:
                        pass

                files = []
                if card_buf:
                    files.append(discord.File(card_buf, filename="x_info_card.png"))

                with open(filepath, "rb") as f:
                    files.append(discord.File(fp=f, filename=os.path.basename(filepath)))
                    caption = f"🎬 **[X (Twitter)]** {title[:80]}\n👤 @{uploader} | ❤️ {likes} | 💬 {comments} | 🔁 {shares}\n🔗 {url}"
                    await autorep(message, content=caption, files=files)
            else:
                sent = await autorep(message, f"⚠️ Video vượt quá giới hạn 25MB của Discord.\n🔗 Xem trực tiếp: {url}")
                autodelet(sent, delay=30)
        except Exception as e:
            err_str = str(e)
            if "Unsupported URL" in err_str:
                sent = await autorep(message, "❌ Link X/Twitter không hợp lệ hoặc bài viết không chứa video.")
            else:
                sent = await autorep(message, f"❌ Lỗi tải X/Twitter: {err_str[:120]}")
            autodelet(sent, delay=20)
        finally:
            try:
                for f in TEMP_DIR.glob(f"x_{timestamp}_*"):
                    f.unlink(missing_ok=True)
            except Exception:
                pass

    @menu_entry("MEDIA & ENTERTAINMENT", "x", "Tai video X / Twitter",
                badge="HOT", icon_sym="🐦", icon_color=(29, 155, 240), order=6)
    @alias_declare("x", ["twitter"])
    @commands.command(
        name="x",
        aliases=["twitter"],
        help="Tai video hoac GIF tu mang xa hoi X (Twitter)."
    )
    async def cmd_x(self, ctx: commands.Context, *, url: Optional[str] = None):
        p = self._pfx()
        if not url:
            card_buf = None
            try:
                card_buf = await async_help_card("x", p)
            except Exception:
                card_buf = None

            if card_buf:
                try:
                    file = discord.File(card_buf, filename="x_guide.png")
                    sent = await autorep(ctx.message, content=f"🐦 **X (TWITTER) MEDIA DOWNLOADER** (`{p}x`)", file=file)
                    autodelet(sent, delay=45)
                    return
                except Exception:
                    pass

            guide = (
                f"🐦 **X (TWITTER) DOWNLOADER - HUONG DAN** 🐦\n\n"
                f"• `{p}x <link>` : Tai video hoac GIF tu bai dang X / Twitter.\n"
                f"• `{p}x <tu_khoa>` : Tim kiem video X (Twitter) theo tu khoa va tai.\n"
                f"• Ho tro link x.com hoac twitter.com."
            )
            sent = await autorep(ctx.message, guide)
            autodelet(sent, delay=45)
            return

        target = url.strip()
        is_link = target.startswith("http://") or target.startswith("https://")
        if is_link:
            waiting = await autorep(ctx.message, "⏳ Đang tải video X (Twitter)...")
            autodelet(waiting, delay=15)
            await self._download_and_send(ctx.message, target)
        else:
            waiting = await autorep(ctx.message, f"🔍 Đang tìm kiếm video X (Twitter) theo từ khóa: **{target}**...")
            autodelet(waiting, delay=15)
            search_query = f"ytsearch1:twitter video {target}"
            await self._download_and_send(ctx.message, search_query)


async def setup(bot: commands.Bot):
    await bot.add_cog(XDownloader(bot))


async def setup(bot: commands.Bot):
    await bot.add_cog(XDownloader(bot))
