# -*- coding: utf-8 -*-
"""
MODULE: fb (Facebook Media Downloader - Video & Photo)
- Lệnh độc lập: (prefix)fb <link>
- Hỗ trợ tải cả VIDEO (Reels, Watch, Video) và ẢNH (Single Photo, Album, Post ảnh).
- Thẻ hướng dẫn Liquid Glass chuẩn chỉ, tự động xóa thông báo sau thời gian quy định.
"""
from __future__ import annotations

import asyncio
import html
import io
import os
import re
import time
from pathlib import Path
from typing import List, Optional, Tuple

import discord
from discord.ext import commands
import requests
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


class FacebookDownloader(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return "!"

    def _is_photo_link(self, url: str) -> bool:
        low = url.lower()
        return any(k in low for k in ["/photo", "photo.php", "/photos/", "fbid=", "set=a."])

    def _fetch_fb_photos_sync(self, url: str) -> Tuple[str, List[str]]:
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                return "Facebook Post", []

            title_m = re.search(r'<title>([^<]+)</title>', r.text)
            title = html.unescape(title_m.group(1)).strip() if title_m else "Facebook Photo"
            if "Facebook" in title and len(title) <= 12:
                title = "Facebook Photo"

            raw_matches = re.findall(r'https://scontent[^\s"\'\\]+', r.text)
            seen = set()
            photos = []
            for m in raw_matches:
                u = m.replace('\\u0026', '&').replace('\\/', '/').replace('&amp;', '&')
                if any(bad in u for bad in ["p50x50", "s50x50", "s32x32", "p32x32"]):
                    continue
                base_id = u.split('?')[0]
                if base_id not in seen:
                    seen.add(base_id)
                    photos.append(u)

            return title, photos
        except Exception:
            return "Facebook Photo", []

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

    async def _download_photos_and_send(self, message: discord.Message, url: str) -> bool:
        loop = asyncio.get_event_loop()
        title, photo_urls = await loop.run_in_executor(None, self._fetch_fb_photos_sync, url)

        if not photo_urls:
            return False

        def _fetch_images(urls: List[str]):
            results = []
            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
            }
            for idx, pu in enumerate(urls[:9]):  # Tối đa 9 ảnh để dành 1 slot cho thẻ Card Info
                try:
                    res = requests.get(pu, headers=headers, timeout=10)
                    if res.status_code == 200 and len(res.content) > 1000:
                        results.append((f"fb_photo_{idx+1}.jpg", res.content))
                except Exception:
                    pass
            return results

        imgs = await loop.run_in_executor(None, _fetch_images, photo_urls)
        if not imgs:
            return False

        # Render thẻ Liquid Glass Info
        card_buf = None
        try:
            from apps.user_discord.utils.media_card import async_media_post_card
            cover = photo_urls[0] if photo_urls else None
            card_buf = await async_media_post_card(
                platform="Facebook",
                title=title,
                author_nick="Facebook Creator",
                cover_url=cover,
                likes="HOT",
                comments=f"{len(photo_urls)} Ảnh",
                badge="PHOTO HD",
                extra_info=f"Album {len(photo_urls)} ảnh gốc"
            )
        except Exception:
            try:
                from utils.media_card import async_media_post_card
                cover = photo_urls[0] if photo_urls else None
                card_buf = await async_media_post_card(
                    platform="Facebook",
                    title=title,
                    author_nick="Facebook Creator",
                    cover_url=cover,
                    likes="HOT",
                    comments=f"{len(photo_urls)} Ảnh",
                    badge="PHOTO HD",
                    extra_info=f"Album {len(photo_urls)} ảnh gốc"
                )
            except Exception:
                pass

        files = []
        if card_buf:
            files.append(discord.File(card_buf, filename="fb_info_card.png"))
        for name, data in imgs:
            files.append(discord.File(io.BytesIO(data), filename=name))

        caption = f"🖼️ **[Facebook Ảnh]** {title[:80]}\n📸 Đã tải **{len(imgs)}** ảnh chất lượng cao\n🔗 {url}"
        await autorep(message, content=caption, files=files)
        return True

    async def _download_and_send(self, message: discord.Message, url: str):
        # 1. Nếu là dạng link Photo rõ ràng -> Ưu tiên tải ảnh trước
        if self._is_photo_link(url):
            success = await self._download_photos_and_send(message, url)
            if success:
                return

        # 2. Thử tải video qua yt_dlp
        clean_url = url.split("?")[0] if ("?" in url and "fb" in url and not self._is_photo_link(url)) else url
        timestamp = int(time.time())
        out_tmpl = str(TEMP_DIR / f"fb_{timestamp}_%(id)s.%(ext)s")

        loop = asyncio.get_event_loop()
        def _exec_video():
            ydl_opts = {
                'outtmpl': out_tmpl,
                'quiet': True,
                'no_warnings': True,
                'max_filesize': 25 * 1024 * 1024,
                'format': 'best[ext=mp4]/best',
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clean_url, download=True)
                filename = ydl.prepare_filename(info)
                return info, filename

        try:
            info, filepath = await loop.run_in_executor(None, _exec_video)
            if os.path.exists(filepath) and os.path.getsize(filepath) <= 25 * 1024 * 1024:
                title = info.get("title") or "Facebook Video"
                uploader = info.get("uploader") or info.get("channel") or "Facebook Creator"
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
                        platform="Facebook",
                        title=title,
                        author_nick=uploader,
                        author_user=uploader_id,
                        cover_url=cover_url,
                        likes=likes,
                        comments=comments,
                        shares=shares,
                        views=views,
                        badge="VIDEO HD"
                    )
                except Exception:
                    try:
                        from utils.media_card import async_media_post_card
                        card_buf = await async_media_post_card(
                            platform="Facebook",
                            title=title,
                            author_nick=uploader,
                            author_user=uploader_id,
                            cover_url=cover_url,
                            likes=likes,
                            comments=comments,
                            shares=shares,
                            views=views,
                            badge="VIDEO HD"
                        )
                    except Exception:
                        pass

                files = []
                if card_buf:
                    files.append(discord.File(card_buf, filename="fb_info_card.png"))

                with open(filepath, "rb") as f:
                    files.append(discord.File(fp=f, filename=os.path.basename(filepath)))
                    caption = f"🎬 **[Facebook Video]** {title[:80]}\n👤 {uploader} | ❤️ {likes} | 💬 {comments}\n🔗 {url}"
                    await autorep(message, content=caption, files=files)
                return
            elif os.path.exists(filepath):
                sent = await autorep(message, f"⚠️ Video vượt quá giới hạn 25MB của Discord.\n🔗 Xem trực tiếp: {url}")
                autodelet(sent, delay=30)
                return
        except Exception:
            # Nếu yt_dlp lỗi (thường do post chỉ có ảnh hoặc album ảnh), fallback sang cào ảnh
            photo_success = await self._download_photos_and_send(message, url)
            if photo_success:
                return

            sent = await autorep(message, "❌ Không thể tải media Facebook (Link không hợp lệ, bài viết bị khóa riêng tư hoặc định dạng không hỗ trợ).")
            autodelet(sent, delay=20)
        finally:
            try:
                for f in TEMP_DIR.glob(f"fb_{timestamp}_*"):
                    f.unlink(missing_ok=True)
            except Exception:
                pass

    @menu_entry("MEDIA & ENTERTAINMENT", "fb", "Tai video & anh Facebook Reels, Watch, Photo",
                badge="HOT", icon_sym="📘", icon_color=(24, 119, 242), order=4)
    @alias_declare("fb", ["facebook"])
    @commands.command(
        name="fb",
        aliases=["facebook"],
        help="Tai video Reels/Watch hoac anh Facebook khong logo."
    )
    async def cmd_fb(self, ctx: commands.Context, *, url: Optional[str] = None):
        p = self._pfx()
        if not url:
            card_buf = None
            try:
                card_buf = await async_help_card("fb", p)
            except Exception:
                card_buf = None

            if card_buf:
                try:
                    file = discord.File(card_buf, filename="fb_guide.png")
                    sent = await autorep(ctx.message, content=f"📘 **FACEBOOK MEDIA DOWNLOADER** (`{p}fb`)", file=file)
                    autodelet(sent, delay=45)
                    return
                except Exception:
                    pass

            guide = (
                f"📘 **FACEBOOK DOWNLOADER - HUONG DAN** 📘\n\n"
                f"• `{p}fb <link>` : Tai video Facebook Reels, Watch hoac Anh photo/album goc.\n"
                f"• `{p}fb <tu_khoa>` : Tim kiem video Facebook theo tu khoa va tu dong tai.\n"
                f"• Ho tro ca link truc tiep va tim kiem da dang."
            )
            sent = await autorep(ctx.message, guide)
            autodelet(sent, delay=45)
            return

        target = url.strip()
        is_link = target.startswith("http://") or target.startswith("https://")
        if is_link:
            waiting = await autorep(ctx.message, "⏳ Đang tải media Facebook (Video/Ảnh)...")
            autodelet(waiting, delay=15)
            await self._download_and_send(ctx.message, target)
        else:
            waiting = await autorep(ctx.message, f"🔍 Đang tìm kiếm video Facebook theo từ khóa: **{target}**...")
            autodelet(waiting, delay=15)
            search_query = f"ytsearch1:facebook {target}"
            await self._download_and_send(ctx.message, search_query)


async def setup(bot: commands.Bot):
    await bot.add_cog(FacebookDownloader(bot))
