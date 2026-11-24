# -*- coding: utf-8 -*-
"""
MODULE: download (Universal Multi-Platform Media Downloader)
- Lệnh chính: (prefix)dl <link> hoặc (prefix)dl <nen_tang> <link>
- Chế độ tự động phát hiện link (dl on/off/status) theo máy chủ.
- Xuất thẻ ảnh hướng dẫn và thẻ ảnh báo cáo trạng thái Liquid Glass.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_DIR / "media_tool_settings.json"
TEMP_DIR = DATA_DIR / "downloads"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Regex phát hiện link mạng xã hội
RE_FB = re.compile(r'https?://(?:www\.|m\.|web\.)?(?:facebook\.com|fb\.watch)/[^\s]+', re.IGNORECASE)
RE_IG = re.compile(r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv|reels)/[^\s]+', re.IGNORECASE)
RE_X = re.compile(r'https?://(?:www\.)?(?:twitter\.com|x\.com)/[^\s]+/status/\d+[^\s]*', re.IGNORECASE)
RE_THREADS = re.compile(r'https?://(?:www\.)?threads\.net/@[^\s]+/post/[^\s]+', re.IGNORECASE)
RE_TIKTOK = re.compile(r'https?://(?:www\.|vm\.|vt\.)?tiktok\.com/[^\s]+', re.IGNORECASE)
RE_YT = re.compile(r'https?://(?:www\.)?(?:youtube\.com/shorts/|youtu\.be/)[^\s]+', re.IGNORECASE)

ALL_MEDIA_URL_REGEX = re.compile(
    r'https?://(?:www\.)?(?:facebook\.com|fb\.watch|instagram\.com/(?:p|reel|tv|reels)|twitter\.com/[^\s]+/status|x\.com/[^\s]+/status|threads\.net/@[^\s]+/post|tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com|youtube\.com/shorts/|youtu\.be)/[^\s]+',
    re.IGNORECASE
)


class MediaToolModule(commands.Cog, name="MediaTool"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings: Dict[str, Any] = self._load_settings()
        self._dl_cooldowns: Dict[int, float] = {}

    def _load_settings(self) -> Dict[str, Any]:
        if SETTINGS_FILE.exists():
            try:
                return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"active_guilds": {}}

    def _save_settings(self):
        try:
            SETTINGS_FILE.write_text(
                json.dumps(self.settings, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    def _is_auto_on_guild(self, guild_id: Optional[int]) -> bool:
        if not guild_id:
            return False
        return bool(self.settings.get("active_guilds", {}).get(str(guild_id), False))

    def _set_auto_guild(self, guild_id: int, state: bool):
        ag = self.settings.setdefault("active_guilds", {})
        ag[str(guild_id)] = state
        self._save_settings()

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return getattr(self.bot, "_own_prefix", None) or "!"

    def _check_admin(self, user_id: int) -> bool:
        bot_uid = getattr(self.bot.user, "id", 0)
        if user_id == bot_uid:
            return True
        cfg_owners = set()
        try:
            cfg_path = next(
                (p for p in (BASE_DIR / "config.json", DATA_DIR / "config.json") if p.exists()),
                None,
            )
            if cfg_path:
                cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
                for acc in cfg_data.get("accounts", []):
                    if isinstance(acc, dict) and acc.get("uid") == bot_uid:
                        for oid in list(acc.get("owner_ids") or []) + [acc.get("created_by")]:
                            if oid and str(oid).isdigit():
                                cfg_owners.add(int(oid))
        except Exception:
            pass

        setting_file = DATA_DIR / f"{bot_uid}_setting.json"
        this_conf: Dict[str, Any] = {}
        if setting_file.exists():
            try:
                this_conf = json.loads(setting_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        admin_list = set(cfg_owners)
        for x in this_conf.get("admintris", []) + this_conf.get("admins", []):
            if str(x).isdigit():
                admin_list.add(int(x))

        return user_id in admin_list

    # ── HÀM TẢI MEDIA DÙNG CHUNG ──────────────────────────────────────────
    def _fetch_fb_photos_sync(self, url: str) -> Tuple[str, List[str]]:
        import requests
        import html
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

    async def _download_and_send(self, message: discord.Message, url: str, platform_hint: str = "Video"):
        is_fb = ("facebook.com" in url or "fb.watch" in url)
        is_fb_photo = is_fb and any(k in url.lower() for k in ["/photo", "photo.php", "/photos/", "fbid=", "set=a."])

        # 1. Nếu là ảnh FB rõ ràng -> tải ảnh trước
        if is_fb_photo:
            loop = asyncio.get_event_loop()
            title, photo_urls = await loop.run_in_executor(None, self._fetch_fb_photos_sync, url)
            if photo_urls:
                import requests
                def _fetch_imgs():
                    res_list = []
                    hdrs = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)'}
                    for idx, pu in enumerate(photo_urls[:10]):
                        try:
                            resp = requests.get(pu, headers=hdrs, timeout=10)
                            if resp.status_code == 200 and len(resp.content) > 1000:
                                res_list.append((f"fb_photo_{idx+1}.jpg", resp.content))
                        except Exception:
                            pass
                    return res_list

                imgs = await loop.run_in_executor(None, _fetch_imgs)
                if imgs:
                    files = [discord.File(io.BytesIO(data), filename=name) for name, data in imgs]
                    caption = f"🖼️ **[Facebook Ảnh]** {title[:80]}\n📸 Đã tải **{len(files)}** ảnh\n🔗 {url}"
                    await autorep(message, content=caption, files=files)
                    return

        timestamp = int(time.time())
        out_tmpl = str(TEMP_DIR / f"dl_{timestamp}_%(id)s.%(ext)s")

        loop = asyncio.get_event_loop()
        def _exec_dl():
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
            info, filepath = await loop.run_in_executor(None, _exec_dl)
            if os.path.exists(filepath) and os.path.getsize(filepath) <= 25 * 1024 * 1024:
                title = info.get("title") or f"{platform_hint} Video"
                uploader = info.get("uploader") or info.get("channel") or platform_hint
                uploader_id = info.get("uploader_id") or ""
                cover_url = info.get("thumbnail")

                def _fmt_n(n):
                    if not n: return '0'
                    try:
                        v = int(n)
                        if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
                        if v >= 1_000: return f"{v/1_000:.1f}K"
                        return str(v)
                    except Exception: return str(n)

                likes = _fmt_n(info.get("like_count"))
                comments = _fmt_n(info.get("comment_count"))
                shares = _fmt_n(info.get("repost_count"))
                views = _fmt_n(info.get("view_count"))

                # Render Liquid Glass Info Card
                card_buf = None
                try:
                    from apps.user_discord.utils.media_card import async_media_post_card
                    card_buf = await async_media_post_card(
                        platform=platform_hint,
                        title=title,
                        author_nick=uploader,
                        author_user=uploader_id,
                        cover_url=cover_url,
                        likes=likes,
                        comments=comments,
                        shares=shares,
                        views=views,
                        badge="MEDIA HD"
                    )
                except Exception:
                    try:
                        from utils.media_card import async_media_post_card
                        card_buf = await async_media_post_card(
                            platform=platform_hint,
                            title=title,
                            author_nick=uploader,
                            author_user=uploader_id,
                            cover_url=cover_url,
                            likes=likes,
                            comments=comments,
                            shares=shares,
                            views=views,
                            badge="MEDIA HD"
                        )
                    except Exception:
                        pass

                files = []
                if card_buf:
                    files.append(discord.File(card_buf, filename="dl_info_card.png"))

                with open(filepath, "rb") as f:
                    files.append(discord.File(fp=f, filename=os.path.basename(filepath)))
                    caption = f"🎬 **[{platform_hint}]** {title[:80]}\n👤 {uploader} | ❤️ {likes} | 💬 {comments}\n🔗 {url}"
                    await autorep(message, content=caption, files=files)
                return
            else:
                sent = await autorep(message, f"⚠️ Video vượt quá giới hạn 25MB của Discord.\n🔗 Xem trực tiếp: {url}")
                autodelet(sent, delay=30)
                return
        except Exception as e:
            if is_fb:
                # Fallback sang tải ảnh nếu là Facebook
                title, photo_urls = await loop.run_in_executor(None, self._fetch_fb_photos_sync, url)
                if photo_urls:
                    import requests
                    def _fetch_imgs():
                        res_list = []
                        hdrs = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)'}
                        for idx, pu in enumerate(photo_urls[:9]):
                            try:
                                resp = requests.get(pu, headers=hdrs, timeout=10)
                                if resp.status_code == 200 and len(resp.content) > 1000:
                                    res_list.append((f"fb_photo_{idx+1}.jpg", resp.content))
                            except Exception:
                                pass
                        return res_list

                    imgs = await loop.run_in_executor(None, _fetch_imgs)
                    if imgs:
                        card_buf = None
                        try:
                            from apps.user_discord.utils.media_card import async_media_post_card
                            card_buf = await async_media_post_card(
                                platform="Facebook",
                                title=title,
                                author_nick="Facebook Creator",
                                cover_url=photo_urls[0],
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
                        return

            err_str = str(e)
            if "Unsupported URL" in err_str:
                sent = await autorep(message, f"❌ Không thể phân giải link {platform_hint} này.")
            else:
                sent = await autorep(message, f"❌ Lỗi tải media: {err_str[:120]}")
            autodelet(sent, delay=20)
        finally:
            try:
                for f in TEMP_DIR.glob(f"dl_{timestamp}_*"):
                    f.unlink(missing_ok=True)
            except Exception:
                pass

    # ── RENDER STATUS CARD LIQUID GLASS ──────────────────────────────────
    def _render_dl_status_card(self, ctx: commands.Context) -> io.BytesIO:
        try:
            from apps.user_discord.utils import glass as G
        except ImportError:
            from utils import glass as G

        active_map = self.settings.get("active_guilds", {})
        on_guilds = []
        all_guilds = self.bot.guilds

        for gid_str, is_on in active_map.items():
            if is_on:
                try:
                    g = self.bot.get_guild(int(gid_str))
                    if g:
                        on_guilds.append({
                            "name": g.name,
                            "id": str(g.id),
                            "members": g.member_count or len(g.members),
                        })
                    else:
                        on_guilds.append({"name": f"Server {gid_str}", "id": gid_str, "members": 0})
                except Exception:
                    pass

        cur_guild = ctx.guild
        cur_guild_id = cur_guild.id if cur_guild else None
        cur_on = self._is_auto_on_guild(cur_guild_id)
        pfx = self._pfx()

        LW, LH = 1040, 560
        pad = 20
        head_h = 70
        gap = 14
        left_w = 330

        cv = G.GlassCanvas(LW, LH, scale=2, out=1.35)

        f_st = cv.font("b", 12)
        st_text = "🟢 AUTO DL BAT" if cur_on else "🔴 AUTO DL TAT"
        st_pill_col = G.G_ON if cur_on else G.G_OFF
        st_dot = (167, 255, 214) if cur_on else (255, 170, 170)

        cv.header(
            pad, pad, LW - pad, head_h,
            "MEDIA DOWNLOADER MONITOR",
            f"Prefix  {pfx}   •   Engine: yt-dlp Universal   •   {len(on_guilds)} Active Server(s)",
            tag="DL STATUS",
            right_reserve=180
        )
        cv.glass_pill(LW - pad - 16, pad + head_h / 2 - 15, st_text, f_st, st_pill_col, align="r", dot=st_dot)

        top = pad + head_h + gap
        bottom = LH - pad
        lx1, lx2 = pad, pad + left_w

        p_h = 135
        cv.glass((lx1, top, lx2, top + p_h), 20, blur=24, tint=(14, 18, 30, 95))
        cv.text(lx1 + 18, top + 18, "MAY CHU HIEN TAI", cv.font("b", 11), G.C_DIM, vcenter=True)
        if cur_guild:
            cv.text(lx1 + 18, top + 46, cv.fit(cur_guild.name, cv.font("b", 16), left_w - 36), cv.font("b", 16), G.C_GOLD, vcenter=True)
            cv.text(lx1 + 18, top + 72, f"ID: {cur_guild.id}  •  {cur_guild.member_count:,} mems", cv.font("r", 11.5), G.C_MUTED, vcenter=True)
            cur_badge = "🟢 DANG BAT TU DONG" if cur_on else "🔴 DANG TAT TU DONG"
            cv.pill(lx1 + 18, top + 94, cur_badge, cv.font("b", 10.5), grad=G.G_GREEN if cur_on else G.G_RED, h=22)
        else:
            cv.text(lx1 + 18, top + 46, "Tin nhan rieng (DM)", cv.font("b", 16), G.C_GOLD, vcenter=True)
            cv.pill(lx1 + 18, top + 94, "⚪ KHONG HO TRO AUTO", cv.font("b", 10.5), grad=G.G_GRAY, h=22)

        s_y1 = top + p_h + gap
        s_h = 130
        cv.glass((lx1, s_y1, lx2, s_y1 + s_h), 20, blur=24, tint=(14, 18, 30, 95))
        cv.text(lx1 + 18, s_y1 + 18, "THONG KE TU DONG BAT LINK", cv.font("b", 11), G.C_DIM, vcenter=True)

        stats = [
            ("Server Bat", f"{len(on_guilds)}", G.C_ON),
            ("Tong Server", f"{len(all_guilds)}", G.C_TEXT),
            ("Ti Le Bat", f"{(len(on_guilds)/max(1, len(all_guilds))*100):.1f}%", G.C_GOLD),
        ]
        box_w = (left_w - 36 - 16) / 3
        for i, (lbl, val, col) in enumerate(stats):
            bx1 = lx1 + 18 + i * (box_w + 8)
            bx2 = bx1 + box_w
            cv.glass((bx1, s_y1 + 38, bx2, s_y1 + 38 + 72), 12, blur=10, tint=(20, 26, 44, 70))
            cv.text(bx1 + box_w / 2, s_y1 + 58, val, cv.font("b", 17), col, align="c", vcenter=True)
            cv.text(bx1 + box_w / 2, s_y1 + 88, lbl, cv.font("r", 9.5), G.C_MUTED, align="c", vcenter=True)

        t_y1 = s_y1 + s_h + gap
        cv.glass((lx1, t_y1, lx2, bottom), 20, blur=24, tint=(14, 18, 30, 95))
        cv.text(lx1 + 18, t_y1 + 20, "NEN TANG HO TRO", cv.font("b", 11), G.C_DIM, vcenter=True)
        cv.text(lx1 + 18, t_y1 + 46, "• Facebook Reels, Watch, Video", cv.font("r", 11), G.C_TEXT, vcenter=True)
        cv.text(lx1 + 18, t_y1 + 70, "• Instagram Reels, Post video", cv.font("r", 11), G.C_TEXT, vcenter=True)
        cv.text(lx1 + 18, t_y1 + 94, "• X (Twitter), Threads, TikTok", cv.font("r", 11), G.C_TEXT, vcenter=True)
        cv.text(lx1 + 18, t_y1 + 118, "• YouTube Shorts, Video", cv.font("r", 11), G.C_MUTED, vcenter=True)

        rx1, rx2 = lx2 + gap, LW - pad
        cv.glass((rx1, top, rx2, bottom), 22, blur=24, tint=(14, 18, 30, 95))
        cv.text(rx1 + 24, top + 24, "DANH SACH MAY CHU KICH HOAT TU DONG", cv.font("b", 14), G.C_TEXT, vcenter=True)
        cv.text(rx2 - 24, top + 24, f"{len(on_guilds)} May chu", cv.font("b", 12), G.C_ON, align="r", vcenter=True)
        cv.rrect((rx1 + 24, top + 44, rx2 - 24, top + 45), 0.5, fill=(255, 255, 255, 30))

        list_y = top + 56
        row_h = 56
        max_rows = 6

        if on_guilds:
            for idx, ginfo in enumerate(on_guilds[:max_rows]):
                ry1 = list_y + idx * (row_h + 8)
                ry2 = ry1 + row_h
                cv.glass((rx1 + 20, ry1, rx2 - 20, ry2), 14, blur=12, tint=(22, 28, 48, 65))
                cv.circle_image(None, rx1 + 32, ry1 + 12, 32, ring=G.G_BRAND, letter=str(idx + 1))
                tx = rx1 + 32 + 32 + 14
                cv.text(tx, ry1 + 18, cv.fit(ginfo["name"], cv.font("b", 13.5), 320), cv.font("b", 13.5), G.C_TEXT, vcenter=True)
                cv.text(tx, ry1 + 38, f"ID: {ginfo['id']}   •   {ginfo['members']:,} thanh vien", cv.font("r", 10.5), G.C_MUTED, vcenter=True)
                cv.pill(rx2 - 34, ry1 + 17, "ACTIVE", cv.font("b", 10), grad=G.G_GREEN, h=22, align="r")
        else:
            cv.text((rx1 + rx2) / 2, (top + bottom) / 2 - 10, "Chua co may chu nao bat Auto Download", cv.font("b", 15), G.C_MUTED, align="c", vcenter=True)
            cv.text((rx1 + rx2) / 2, (top + bottom) / 2 + 18, f"Go {pfx}dl on tai may chu de bat tinh nang nay!", cv.font("r", 12), G.C_DIM, align="c", vcenter=True)

        return cv.finalize()

    # ─────────────────────────────────────────────────────────────────────────
    # LỆNH CHÍNH (PREFIX)DL
    # ─────────────────────────────────────────────────────────────────────────
    @menu_entry("MEDIA & ENTERTAINMENT", "dl", "Tai video FB, IG, X, Threads, TikTok, Shorts",
                badge="HOT", icon_sym="📥", icon_color=(56, 189, 248), order=3)
    @alias_declare("dl", ["download", "tai", "get"])
    @commands.command(
        name="dl",
        aliases=["download", "tai", "get"],
        help="Tai video da nen tang tu dong khong logo."
    )
    async def cmd_dl(self, ctx: commands.Context, *, target: Optional[str] = None):
        p = self._pfx()
        if not target:
            card_buf = None
            try:
                card_buf = await async_help_card("dl", p)
            except Exception:
                card_buf = None

            if card_buf:
                try:
                    file = discord.File(card_buf, filename="dl_guide.png")
                    sent = await autorep(ctx.message, content=f"📥 **MEDIA DOWNLOADER DA NEN TANG** (`{p}dl`)", file=file)
                    autodelet(sent, delay=45)
                    return
                except Exception:
                    pass

            guide = (
                f"📥 **MEDIA DOWNLOADER - HUONG DAN SU DUNG** 📥\n\n"
                f"• `{p}dl <link>` : Tu dong nhan dien nen tang & tai video.\n"
                f"• `{p}dl <nen_tang> <link>` : Chi dinh nen tang (fb, ig, x, threads, tt, yt...).\n"
                f"• `{p}dl on/off` : Bat/tat tu dong bat link tai server.\n"
                f"• `{p}dl status` : Xem trang thai cac server dang bat."
            )
            sent = await autorep(ctx.message, guide)
            autodelet(sent, delay=45)
            return

        parts = target.strip().split(maxsplit=1)
        sub = parts[0].lower()
        sub_arg = parts[1].strip() if len(parts) > 1 else ""

        if sub in ["on", "bat"]:
            return await self.dl_on(ctx)
        elif sub in ["off", "tat"]:
            return await self.dl_off(ctx)
        elif sub in ["status", "stt", "list"]:
            return await self.dl_status(ctx)
        elif sub in ["fb", "facebook"]:
            arg = sub_arg or sub
            if arg.startswith("http://") or arg.startswith("https://"):
                return await self._download_and_send(ctx.message, arg, "Facebook")
            waiting = await autorep(ctx.message, f"🔍 Đang tìm kiếm video Facebook theo từ khóa: **{arg}**...")
            autodelet(waiting, delay=15)
            return await self._download_and_send(ctx.message, f"ytsearch1:facebook {arg}", "Facebook")
        elif sub in ["ig", "instagram"]:
            arg = sub_arg or sub
            if arg.startswith("http://") or arg.startswith("https://"):
                return await self._download_and_send(ctx.message, arg, "Instagram")
            waiting = await autorep(ctx.message, f"🔍 Đang tìm kiếm video Instagram theo từ khóa: **{arg}**...")
            autodelet(waiting, delay=15)
            return await self._download_and_send(ctx.message, f"ytsearch1:instagram reel {arg}", "Instagram")
        elif sub in ["x", "twitter"]:
            arg = sub_arg or sub
            if arg.startswith("http://") or arg.startswith("https://"):
                return await self._download_and_send(ctx.message, arg, "X (Twitter)")
            waiting = await autorep(ctx.message, f"🔍 Đang tìm kiếm video X (Twitter) theo từ khóa: **{arg}**...")
            autodelet(waiting, delay=15)
            return await self._download_and_send(ctx.message, f"ytsearch1:twitter video {arg}", "X (Twitter)")
        elif sub in ["threads"]:
            arg = sub_arg or sub
            if arg.startswith("http://") or arg.startswith("https://"):
                return await self._download_and_send(ctx.message, arg, "Threads")
            waiting = await autorep(ctx.message, f"🔍 Đang tìm kiếm video Threads theo từ khóa: **{arg}**...")
            autodelet(waiting, delay=15)
            return await self._download_and_send(ctx.message, f"ytsearch1:threads video {arg}", "Threads")
        elif sub in ["tt", "tiktok"]:
            arg = sub_arg or sub
            if arg.startswith("http://") or arg.startswith("https://"):
                return await self._download_and_send(ctx.message, arg, "TikTok")
            waiting = await autorep(ctx.message, f"🔍 Đang tìm kiếm video TikTok theo từ khóa: **{arg}**...")
            autodelet(waiting, delay=15)
            return await self._download_and_send(ctx.message, f"ytsearch1:tiktok {arg}", "TikTok")
        elif sub in ["yt", "youtube"]:
            arg = sub_arg or sub
            if arg.startswith("http://") or arg.startswith("https://"):
                return await self._download_and_send(ctx.message, arg, "YouTube")
            waiting = await autorep(ctx.message, f"🔍 Đang tìm kiếm video YouTube theo từ khóa: **{arg}**...")
            autodelet(waiting, delay=15)
            return await self._download_and_send(ctx.message, f"ytsearch1:{arg}", "YouTube")

        # Kiểm tra nếu là link trực tiếp
        is_link = target.startswith("http://") or target.startswith("https://")
        if is_link:
            url = parts[0]
            platform_hint = "Video"
            if "facebook.com" in url or "fb.watch" in url:
                platform_hint = "Facebook"
            elif "instagram.com" in url:
                platform_hint = "Instagram"
            elif "twitter.com" in url or "x.com" in url:
                platform_hint = "X (Twitter)"
            elif "threads.net" in url:
                platform_hint = "Threads"
            elif "tiktok.com" in url:
                platform_hint = "TikTok"
            elif "youtube.com" in url or "youtu.be" in url:
                platform_hint = "YouTube"

            waiting = await autorep(ctx.message, f"⏳ Đang tải video {platform_hint}...")
            autodelet(waiting, delay=15)
            await self._download_and_send(ctx.message, url, platform_hint)
        else:
            # Tìm kiếm video đa nền tảng theo từ khóa
            waiting = await autorep(ctx.message, f"🔍 Đang tìm kiếm video theo từ khóa: **{target}**...")
            autodelet(waiting, delay=15)
            await self._download_and_send(ctx.message, f"ytsearch1:{target}", "Media")

    async def dl_on(self, ctx: commands.Context):
        """Bat che do tu dong tai video khi phat hien link tai server nay."""
        if not ctx.guild:
            sent = await autorep(ctx.message, "Không thể bật chế độ tự động trong tin nhắn riêng.")
            autodelet(sent, delay=15)
            return

        if not self._check_admin(ctx.author.id):
            sent = await autorep(ctx.message, "⛔ Lệnh này yêu cầu quyền **Admin trở lên** của bot!")
            autodelet(sent, delay=15)
            return

        self._set_auto_guild(ctx.guild.id, True)
        sent = await autorep(
            ctx.message,
            f"🎉 **Đã BẬT Tự Động Tải Video tại máy chủ:** `{ctx.guild.name}`!\\n"
            f"👉 Khi ai đó gửi link FB, IG, X, Threads, TikTok... bot sẽ tự động tải và gửi video ra ngay!"
        )
        autodelet(sent, delay=30)

    async def dl_off(self, ctx: commands.Context):
        """Tat che do tu dong tai video tai server nay."""
        if not ctx.guild:
            sent = await autorep(ctx.message, "Không thể tắt chế độ tự động trong tin nhắn riêng.")
            autodelet(sent, delay=15)
            return

        if not self._check_admin(ctx.author.id):
            sent = await autorep(ctx.message, "⛔ Lệnh này yêu cầu quyền **Admin trở lên** của bot!")
            autodelet(sent, delay=15)
            return

        self._set_auto_guild(ctx.guild.id, False)
        sent = await autorep(ctx.message, f"💤 **Đã TẮT Tự Động Tải Video tại máy chủ:** `{ctx.guild.name}`.")
        autodelet(sent, delay=30)

    async def dl_status(self, ctx: commands.Context):
        """Xem trang thai cac may chu dang bat tu dong tai video dang anh Liquid Glass."""
        p = self._pfx()
        buf = None
        try:
            loop = asyncio.get_event_loop()
            buf = await loop.run_in_executor(None, self._render_dl_status_card, ctx)
        except Exception:
            buf = None

        if buf:
            try:
                file = discord.File(buf, filename="dl_status.png")
                sent = await autorep(
                    ctx.message,
                    content=f"🤖 **BÁO CÁO TRẠNG THÁI AUTO DOWNLOAD** (`{p}dl status`)",
                    file=file
                )
                autodelet(sent, delay=45)
                return
            except Exception:
                pass

        active_map = self.settings.get("active_guilds", {})
        on_guilds = [f"• `{gid}`" for gid, on in active_map.items() if on]
        msg = f"🤖 **TRẠNG THÁI AUTO DOWNLOAD:** Hiện có `{len(on_guilds)}` server đang bật."
        sent = await autorep(ctx.message, msg)
        autodelet(sent, delay=30)

    # ── LISTENER ON_MESSAGE: TỰ ĐỘNG BẮT LINK KHI ĐƯỢC BẬT ────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.author or message.author.bot:
            return
        if not message.content or not message.guild:
            return

        # Chỉ chạy nếu server đó đang BẬT chế độ Auto Download
        if not self._is_auto_on_guild(message.guild.id):
            return

        # Bỏ qua nếu là tin nhắn lệnh
        pfx = self._pfx()
        if message.content.startswith(pfx):
            return

        match = ALL_MEDIA_URL_REGEX.search(message.content)
        if not match:
            return

        matched_url = match.group(0)

        # Anti spam per channel 3s
        chan_id = message.channel.id
        now = time.time()
        if chan_id in self._dl_cooldowns and (now - self._dl_cooldowns[chan_id]) < 3.0:
            return
        self._dl_cooldowns[chan_id] = now

        platform_hint = "Video"
        if "facebook.com" in matched_url or "fb.watch" in matched_url:
            platform_hint = "Facebook"
        elif "instagram.com" in matched_url:
            platform_hint = "Instagram"
        elif "twitter.com" in matched_url or "x.com" in matched_url:
            platform_hint = "X (Twitter)"
        elif "threads.net" in matched_url:
            platform_hint = "Threads"
        elif "tiktok.com" in matched_url:
            platform_hint = "TikTok"
        elif "youtube.com" in matched_url or "youtu.be" in matched_url:
            platform_hint = "YouTube Shorts"

        try:
            await self._download_and_send(message, matched_url, platform_hint)
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(MediaToolModule(bot))
