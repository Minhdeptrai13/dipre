import discord
from discord.ext import commands
import asyncio
import os
import io
import re
import urllib.parse
import aiohttp
import requests

try:
    import primp
    HAS_PRIMP = True
except ImportError:
    HAS_PRIMP = False
from apps.user_discord.utils.media_gui import render_media_selector
from apps.user_discord.utils.media_card import async_search_card, async_nowplaying_card, async_help_card, async_tiktok_video_card
from apps.user_discord.utils.menu_catalog import menu_entry
from apps.user_discord.core.alias import alias_declare

class TikTokModule(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.temp_dir = os.path.join("data", "tiktok")
        os.makedirs(self.temp_dir, exist_ok=True)
        self.headers_api = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Referer': 'https://www.tikwm.com/'
        }
        self.headers_search = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
        }

    def _normalize_url(self, u: str) -> str:
        if not u or not isinstance(u, str):
            return ""
        if u.startswith("/"):
            return "https://www.tikwm.com" + u
        return u

    def format_num(self, num):
        if not num: return '0'
        try:
            num = int(num)
            if num >= 1000000: return f"{num / 1000000:.1f}M"
            if num >= 1000: return f"{num / 1000:.1f}K"
            return f"{num:,}"
        except Exception:
            return str(num)

    async def reply_text(self, message, text, delay=30):
        try:
            from apps.user_discord.utils.autorep import autorep
        except ImportError:
            from utils.autorep import autorep
        return await autorep(message, content=text, auto_delete_delay=delay)

    def extract_tiktok_url(self, text: str) -> str:
        match = re.search(r'https?://[^\s]+', text)
        return match.group(0) if match else ""

    async def expand_short_url(self, session: aiohttp.ClientSession, url: str) -> str:
        if any(short in url for short in ['vt.tiktok.com', 'vm.tiktok.com', '/t/']):
            try:
                async with session.head(url, allow_redirects=True, timeout=8, headers=self.headers_api) as resp:
                    return str(resp.url)
            except Exception:
                pass
        return url

    async def get_tiktok_info(self, url: str) -> dict:
        try:
            async with aiohttp.ClientSession() as session:
                expanded_url = await self.expand_short_url(session, url)
                # Method 1: POST TikWM
                try:
                    async with session.post('https://www.tikwm.com/api/', data={'url': expanded_url, 'hd': 1}, headers=self.headers_api, timeout=12) as r:
                        if r.status == 200:
                            data = await r.json()
                            if data.get('code') == 0 and 'data' in data:
                                return data['data']
                except Exception:
                    pass
                # Method 2: GET TikWM
                try:
                    params = {'url': expanded_url, 'hd': 1}
                    async with session.get('https://www.tikwm.com/api/', params=params, headers=self.headers_api, timeout=12) as r:
                        if r.status == 200:
                            data = await r.json()
                            if data.get('code') == 0 and 'data' in data:
                                return data['data']
                except Exception:
                    pass
        except Exception:
            pass
        return {}

    def search_tiktok_raw_links(self, query: str, max_results: int = 15) -> list:
        """Tìm các URL video TikTok thật từ các search engine (DuckDuckGo, Yahoo, Bing), bỏ qua /live"""
        video_links = []
        seen = set()

        def _add_matches(text):
            raw = urllib.parse.unquote(text)
            matches = re.findall(r'https?://(?:www\.)?tiktok\.com/@[a-zA-Z0-9_.-]+/video/\d+', raw)
            for m in matches:
                if '/live' not in m and m not in seen:
                    seen.add(m)
                    video_links.append(m)

        # Engine 1: DuckDuckGo HTML với inurl:video chuẩn chỉ
        queries_to_try = [
            f"site:tiktok.com inurl:video {query}",
            f"site:tiktok.com {query}",
            f"tiktok video {query}"
        ]

        for q_try in queries_to_try:
            if len(video_links) >= max_results:
                break
            encoded_q = urllib.parse.quote(q_try)
            try:
                if HAS_PRIMP:
                    client = primp.Client()
                    r = client.get(f"https://html.duckduckgo.com/html/?q={encoded_q}")
                    if r.status_code == 200:
                        _add_matches(r.text)
                else:
                    r = requests.post("https://html.duckduckgo.com/html/", data={"q": q_try}, headers=self.headers_search, timeout=6)
                    if r.status_code == 200:
                        _add_matches(r.text)
            except Exception:
                pass

        # Engine 2: Yahoo search fallback
        if len(video_links) < max_results:
            encoded_q = urllib.parse.quote(f"site:tiktok.com video {query}")
            try:
                if HAS_PRIMP:
                    client = primp.Client()
                    r = client.get(f"https://search.yahoo.com/search?p={encoded_q}&n=20", headers=self.headers_search)
                    if r.status_code == 200:
                        _add_matches(r.text)
                else:
                    r = requests.get(f"https://search.yahoo.com/search?p={encoded_q}&n=20", headers=self.headers_search, timeout=6)
                    if r.status_code == 200:
                        _add_matches(r.text)
            except Exception:
                pass

        # Engine 3: Bing search fallback
        if len(video_links) < max_results:
            encoded_q = urllib.parse.quote(f"site:tiktok.com video {query}")
            try:
                if HAS_PRIMP:
                    client = primp.Client()
                    r = client.get(f"https://www.bing.com/search?q={encoded_q}&count=20", headers=self.headers_search)
                    if r.status_code == 200:
                        _add_matches(r.text)
                else:
                    r = requests.get(f"https://www.bing.com/search?q={encoded_q}&count=20", headers=self.headers_search, timeout=6)
                    if r.status_code == 200:
                        _add_matches(r.text)
            except Exception:
                pass

        return video_links[:max_results]

    async def fetch_meta_for_search(self, session: aiohttp.ClientSession, url: str) -> dict:
        """Lấy tiêu đề thật, tác giả, cover và media play URL qua TikWM POST + GET fallback"""
        m = re.search(r'tiktok\.com/@([^/]+)/video/(\d+)', url)
        username = m.group(1) if m else "TikTok Creator"
        vid_id = m.group(2) if m else ""

        d = None
        # 1. Thử qua TikWM POST
        try:
            async with session.post('https://www.tikwm.com/api/', data={'url': url, 'hd': 1}, headers=self.headers_api, timeout=6) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    if res.get('code') == 0 and res.get('data'):
                        d = res.get('data')
        except Exception:
            pass

        # 2. Thử qua TikWM GET nếu POST bị từ chối
        if not d:
            try:
                async with session.get('https://www.tikwm.com/api/', params={'url': url, 'hd': 1}, headers=self.headers_api, timeout=6) as resp:
                    if resp.status == 200:
                        res = await resp.json()
                        if res.get('code') == 0 and res.get('data'):
                            d = res.get('data')
            except Exception:
                pass

        if d:
            t = d.get('title') or f"Video của @{username}"
            author = d.get('author', {}).get('nickname') or username
            return {
                'title': t.strip(),
                'author': {
                    'nickname': author,
                    'unique_id': d.get('author', {}).get('unique_id') or username,
                    'avatar': d.get('author', {}).get('avatar') or ""
                },
                'region': d.get('region', ''),
                'duration': d.get('duration', 0),
                'cover': d.get('cover') or d.get('origin_cover'),
                'origin_cover': d.get('origin_cover'),
                'play': d.get('play') or d.get('wmplay'),
                'wmplay': d.get('wmplay'),
                'music': d.get('music'),
                'music_info': d.get('music_info', {}),
                'video_id': vid_id,
                'id': vid_id,
                'digg_count': d.get('digg_count', 0),
                'comment_count': d.get('comment_count', 0),
                'share_count': d.get('share_count', 0),
                'play_count': d.get('play_count', 0),
                'url': url
            }

        return {
            'title': f"Video TikTok của @{username}",
            'author': {'nickname': username, 'unique_id': username},
            'duration': 0,
            'cover': None,
            'origin_cover': None,
            'play': None,
            'wmplay': None,
            'music': None,
            'music_info': {},
            'video_id': vid_id,
            'id': vid_id,
            'digg_count': 0,
            'url': url
        }

    async def search_tiktok(self, query: str) -> list:
        """Tìm kiếm video TikTok theo thuật toán discord_bot, lấy 6 kết quả tối ưu nhất với thumbnail đầy đủ"""
        loop = asyncio.get_event_loop()
        raw_links = await loop.run_in_executor(None, self.search_tiktok_raw_links, query, 12)
        if not raw_links:
            return []

        results = []
        target_links = raw_links[:6]
        async with aiohttp.ClientSession() as session:
            for idx, u in enumerate(target_links):
                meta = await self.fetch_meta_for_search(session, u)
                if meta:
                    results.append(meta)
                # Giữ khoảng nghỉ nhẹ để TikWM không chặn IP
                if idx < len(target_links) - 1:
                    await asyncio.sleep(0.25)
        return results

    async def _do_stop(self, ctx):
        """Dừng phát âm thanh TikTok và rời Voice."""
        stopped = False
        if ctx.guild and ctx.guild.voice_client:
            vc = ctx.guild.voice_client
            try:
                if hasattr(vc, "stop_track"):
                    await vc.stop_track()
                elif vc.is_playing():
                    vc.stop()
                await vc.disconnect(force=True)
                stopped = True
            except Exception:
                pass
        if stopped:
            await self.reply_text(ctx.message, "⏹️ Đã dừng phát nhạc và rời Voice.", delay=15)
        else:
            await self.reply_text(ctx.message, "ℹ️ Hiện không có bài hát nào đang phát.", delay=15)

    async def play_in_voice(self, ctx, audio_stream_url: str, title: str, author: str, video_link: str = "", thumb_url: str = "", duration: str = ""):
        """Phát âm thanh/nhạc nền TikTok trực tiếp vào kênh Voice (stream FFmpeg, không lưu file)."""
        audio_stream_url = self._normalize_url(audio_stream_url)
        if not ctx.author.voice or not ctx.author.voice.channel:
            await self.reply_text(ctx.message, "❌ Bạn cần tham gia một kênh Voice trước để bot phát nhạc!", delay=20)
            return

        channel = ctx.author.voice.channel

        try:
            from apps.user_discord.utils.autorep import autorep
        except ImportError:
            from utils.autorep import autorep

        try:
            voice_client = channel.guild.voice_client
            if not voice_client or not voice_client.is_connected():
                try:
                    voice_client = await channel.connect(reconnect=True, timeout=20.0, self_deaf=False, self_mute=False)
                except Exception as e:
                    err_str = str(e).lower()
                    if "4006" in err_str or "session is no longer valid" in err_str:
                        try:
                            await channel.guild.change_voice_state(channel=None)
                            await asyncio.sleep(0.6)
                        except Exception:
                            pass
                        voice_client = await channel.connect(reconnect=True, timeout=20.0, self_deaf=False, self_mute=False)
                    else:
                        raise e
            elif voice_client.channel.id != channel.id:
                await voice_client.move_to(channel)

            if voice_client.is_playing():
                voice_client.stop()

            ffmpeg_options = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                'options': '-vn -ar 48000 -ac 2 -b:a 128k'
            }
            source = discord.FFmpegPCMAudio(audio_stream_url, **ffmpeg_options)

            # Tạo now-playing card
            card_file = None
            try:
                card_buf = await async_nowplaying_card("tiktok", title, author, duration, thumb_url, channel_name=channel.name, engine="TikTok")
                if card_buf:
                    card_file = discord.File(card_buf, filename="nowplaying.png")
            except Exception:
                pass

            caption = f"🔊 **[TikTok 🎵] Đang phát trong Voice:** **{title}**\n👤 Kênh: **{author}** | 📍 Phòng: **{channel.name}**"
            if video_link:
                caption += f"\n🔗 {video_link}"
            caption += f"\n*Gõ `(prefix)tt stop` để dừng.*"

            try:
                from apps.user_discord.utils.prefix import fmt as _pfx_fmt
            except ImportError:
                from utils.prefix import fmt as _pfx_fmt
            caption = _pfx_fmt(self.bot, caption)
            status_ref = await autorep(ctx.message, content=caption, file=card_file, auto_delete_delay=None)

            def after_play(err):
                if status_ref:
                    asyncio.run_coroutine_threadsafe(_safe_delete(status_ref), self.bot.loop)

            async def _safe_delete(msg):
                try:
                    await msg.delete()
                except Exception:
                    pass

            voice_client.play(source, after=after_play)

        except Exception as e:
            err_msg = str(e)
            if "4017" in err_msg or "DAVE" in err_msg:
                await self.reply_text(
                    ctx.message,
                    f"⚠️ **Kênh Voice kích hoạt DAVE E2EE (4017):** Discord áp dụng E2EE cho User. Dùng Bot Discord chính thức (`apps/discord_bot`) để phát trực tiếp không bao giờ lỗi!",
                    delay=None
                )
            else:
                await self.reply_text(ctx.message, f"❌ Lỗi phát voice TikTok: {err_msg[:100]}", delay=20)

    async def download_and_send_video(self, ctx, video_url: str, title: str, author: str, likes: str = "0", video_link: str = "", meta: dict = None):
        """Tải video TikTok không logo về và gửi lên Discord kèm ảnh Card thông tin siêu đẹp (avatar, địa chỉ, like, comment, share, view). Không xóa tin nhắn."""
        video_url = self._normalize_url(video_url)
        clean_title = re.sub(r'[^\w\s-]', '', title)[:25].strip() or "tiktok"
        local_path = os.path.join(self.temp_dir, f"tt_{int(asyncio.get_event_loop().time())}_{clean_title}.mp4")

        # Chuẩn bị dữ liệu cho Card ảnh thông tin
        meta = meta or {}
        author_user = meta.get("author", {}).get("unique_id", "") if isinstance(meta.get("author"), dict) else ""
        region = meta.get("region", "")
        avatar_url = meta.get("author", {}).get("avatar", "") if isinstance(meta.get("author"), dict) else ""
        cover_url = meta.get("cover") or meta.get("origin_cover") or ""
        comments = self.format_num(meta.get("comment_count", 0))
        shares = self.format_num(meta.get("share_count", 0))
        views = self.format_num(meta.get("play_count", 0))
        hashtags = [f"#{tag}" for tag in re.findall(r'#(\w+)', title)]

        try:
            # 1. Tải video và render Card ảnh song song
            async def _dl():
                async with aiohttp.ClientSession() as session:
                    async with session.get(video_url, headers=self.headers_api, timeout=40) as v_resp:
                        if v_resp.status == 200:
                            v_bytes = await v_resp.read()
                            if len(v_bytes) <= 25 * 1024 * 1024:
                                with open(local_path, "wb") as f:
                                    f.write(v_bytes)
                                return True
                return False

            async def _card():
                try:
                    return await async_tiktok_video_card(
                        title=title,
                        author_nick=author,
                        author_user=author_user,
                        region=region,
                        avatar_url=avatar_url,
                        cover_url=cover_url,
                        likes=likes,
                        comments=comments,
                        shares=shares,
                        views=views,
                        hashtags=hashtags
                    )
                except Exception:
                    return None

            dl_ok, card_buf = await asyncio.gather(_dl(), _card())

            if os.path.exists(local_path):
                files = []
                with open(local_path, "rb") as f:
                    files.append(discord.File(fp=f, filename="tiktok.mp4"))
                    if card_buf:
                        files.append(discord.File(fp=card_buf, filename="tiktok_info.png"))

                    try:
                        from apps.user_discord.utils.autorep import autorep
                    except ImportError:
                        from utils.autorep import autorep

                    # Gửi cả video và ảnh thông tin siêu nét, auto_delete_delay=None (KHÔNG XÓA)
                    await autorep(ctx.message, files=files, auto_delete_delay=None)
            else:
                await self.reply_text(ctx.message, f"⚠️ Video vượt quá 25MB hoặc không tải được.\n🔗 Xem trực tiếp: {video_link or video_url}", delay=None)

        except Exception as e:
            await self.reply_text(ctx.message, f"❌ Lỗi tải video TikTok: {str(e)[:100]}", delay=20)
        finally:
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except Exception:
                    pass

    async def download_and_send_slideshow(self, ctx, images: list, audio_url: str, title: str, author: str, likes: str = "0", video_link: str = "", meta: dict = None):
        """Tải toàn bộ album ảnh TikTok (slideshow) không logo + nhạc nền MP3, chia nhiều lần gửi nếu > 10 ảnh kèm Card thông tin siêu đẹp."""
        meta = meta or {}
        author_user = meta.get("author", {}).get("unique_id", "") if isinstance(meta.get("author"), dict) else ""
        region = meta.get("region", "")
        avatar_url = meta.get("author", {}).get("avatar", "") if isinstance(meta.get("author"), dict) else ""
        cover_url = meta.get("cover") or meta.get("origin_cover") or (images[0] if images else "")
        comments = self.format_num(meta.get("comment_count", 0))
        shares = self.format_num(meta.get("share_count", 0))
        views = self.format_num(meta.get("play_count", 0))
        hashtags = [f"#{tag}" for tag in re.findall(r'#(\w+)', title)]

        session_id = f"tt_slide_{int(asyncio.get_event_loop().time())}"
        slide_dir = os.path.join(self.temp_dir, session_id)
        os.makedirs(slide_dir, exist_ok=True)

        try:
            try:
                from apps.user_discord.utils.autorep import autorep
            except ImportError:
                from utils.autorep import autorep

            status_msg = await self.reply_text(ctx.message, f"📸 Đang tải Album gồm **{len(images)}** ảnh TikTok + Nhạc nền...", delay=20)

            # 1. Tải ảnh và nhạc nền song song
            img_paths = []
            audio_path = None

            async with aiohttp.ClientSession() as session:
                # Tải nhạc nền nếu có
                if audio_url:
                    audio_url = self._normalize_url(audio_url)
                    try:
                        async with session.get(audio_url, headers=self.headers_api, timeout=25) as a_resp:
                            if a_resp.status == 200:
                                a_bytes = await a_resp.read()
                                if len(a_bytes) <= 25 * 1024 * 1024:
                                    audio_path = os.path.join(slide_dir, "tiktok_music.mp3")
                                    with open(audio_path, "wb") as f:
                                        f.write(a_bytes)
                    except Exception:
                        pass

                # Tải các ảnh
                async def _download_img(idx, url):
                    url = self._normalize_url(url)
                    try:
                        async with session.get(url, headers=self.headers_api, timeout=20) as r:
                            if r.status == 200:
                                b = await r.read()
                                p = os.path.join(slide_dir, f"photo_{idx+1:02d}.jpg")
                                with open(p, "wb") as f:
                                    f.write(b)
                                return (idx, p)
                    except Exception:
                        pass
                    return (idx, None)

                img_tasks = [_download_img(i, u) for i, u in enumerate(images)]
                dl_results = await asyncio.gather(*img_tasks)
                dl_results.sort(key=lambda x: x[0])
                img_paths = [p for _, p in dl_results if p and os.path.exists(p)]

            if not img_paths:
                await self.reply_text(ctx.message, f"❌ Không thể tải ảnh từ Album TikTok này.\n🔗 Xem trực tiếp: {video_link}", delay=30)
                return

            # 2. Render Card thông tin TikTok
            card_buf = None
            try:
                card_buf = await async_tiktok_video_card(
                    title=f"[Album {len(images)} ảnh] {title}",
                    author_nick=author,
                    author_user=author_user,
                    region=region,
                    avatar_url=avatar_url,
                    cover_url=cover_url,
                    likes=likes,
                    comments=comments,
                    shares=shares,
                    views=views,
                    hashtags=hashtags
                )
            except Exception:
                pass

            # 3. Chia ảnh thành các batch để gửi (Discord giới hạn tối đa 10 file/tin nhắn)
            batch_1_files = []
            if card_buf:
                batch_1_files.append(discord.File(fp=card_buf, filename="tiktok_info.png"))
            if audio_path and os.path.exists(audio_path):
                batch_1_files.append(discord.File(fp=audio_path, filename="tiktok_music.mp3"))

            slots_left = 10 - len(batch_1_files)
            b1_imgs = img_paths[:slots_left]
            remaining_imgs = img_paths[slots_left:]

            for p in b1_imgs:
                batch_1_files.append(discord.File(fp=p, filename=os.path.basename(p)))

            caption_1 = f"📸 **[TikTok Photo Album]** **{title}**\n👤 Kênh: **{author}** | ❤️ Likes: **{likes}** | 🖼️ **{len(img_paths)} ảnh**"
            if audio_path:
                caption_1 += " | 🎵 **Có nhạc nền MP3**"
            if video_link:
                caption_1 += f"\n🔗 {video_link}"

            await autorep(ctx.message, content=caption_1, files=batch_1_files, auto_delete_delay=None)

            # Các batch tiếp theo (nếu tổng số ảnh vượt quá slot của đợt 1)
            batch_size = 10
            batch_num = 2
            sent_count = len(b1_imgs)
            while remaining_imgs:
                current_batch = remaining_imgs[:batch_size]
                remaining_imgs = remaining_imgs[batch_size:]

                current_files = [discord.File(fp=p, filename=os.path.basename(p)) for p in current_batch]
                caption_more = f"📸 **[TikTok Album - Phần {batch_num}]** (Ảnh {sent_count + 1} - {sent_count + len(current_batch)}/{len(img_paths)})"
                sent_count += len(current_batch)
                batch_num += 1

                await autorep(ctx.message, content=caption_more, files=current_files, auto_delete_delay=None)
                await asyncio.sleep(1.2)

        except Exception as e:
            await self.reply_text(ctx.message, f"❌ Lỗi gửi Album TikTok: {str(e)[:100]}", delay=20)
        finally:
            if os.path.exists(slide_dir):
                try:
                    import shutil
                    shutil.rmtree(slide_dir, ignore_errors=True)
                except Exception:
                    pass

    @menu_entry("MEDIA & ENTERTAINMENT", "tt", "Tải video TikTok không logo (hoặc Voice)",
                badge="HD", icon_sym="🎵", icon_color=(0, 242, 234), order=2)
    @alias_declare("tiktok", main="tiktok", subs=["tt"])
    @commands.group(name="tiktok", aliases=["tt"], invoke_without_command=True)
    async def cmd_tiktok(self, ctx, *, query: str = None):
        """Tải video TikTok không logo, phát Voice hoặc tìm kiếm video (Gửi ảnh Card chọn 1-20)."""
        if not query:
            try:
                from apps.user_discord.utils.prefix import get_prefix
            except ImportError:
                from utils.prefix import get_prefix
            pfx = get_prefix(self.bot)
            card_buf = await async_help_card("tiktok", pfx)
            if card_buf:
                card_file = discord.File(card_buf, filename="tt_guide.png")
                try:
                    from apps.user_discord.utils.autorep import autorep
                except ImportError:
                    from utils.autorep import autorep
                await autorep(ctx.message, content="🎵 **HƯỚNG DẪN SỬ DỤNG LỆNH TIKTOK**", file=card_file, auto_delete_delay=60)
            else:
                await self.reply_text(ctx.message, f"❌ Cú pháp: `{pfx}tt <link/từ khóa>` | `{pfx}tt stop`", delay=30)
            return

        tiktok_url = self.extract_tiktok_url(query)

        # 1. Trực tiếp dán link TikTok
        if "tiktok.com" in tiktok_url:
            parts = query.split()
            # Kiểm tra nếu user đã chỉ định rõ v/voice hoặc f/file trong lệnh
            explicit_mode = None
            if len(parts) > 1:
                last_arg = parts[-1].lower()
                if last_arg in ["v", "voice", "play", "am"]:
                    explicit_mode = "voice"
                elif last_arg in ["f", "file", "video", "mp4", "down", "dl"]:
                    explicit_mode = "file"

            req_mode = explicit_mode
            if not req_mode:
                # Nếu không chỉ định: Kiểm tra nếu user đang trong voice channel thì hỏi muốn phát voice hay gửi file
                if ctx.author.voice and ctx.author.voice.channel:
                    ask_txt = (
                        f"🎬 **Đã nhận link TikTok! Bạn muốn làm gì?**\n"
                        f"👉 Gõ `v` để **Phát nhạc vào Voice** 🔊\n"
                        f"👉 Gõ `f` để **Tải File Video MP4/Ảnh** 📥\n"
                        f"*(Hoặc gõ `c` để hủy. Mặc định tải file sau 20s)*"
                    )
                    ask_msg = await self.reply_text(ctx.message, ask_txt, delay=25)
                    def check_choice(m):
                        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
                    try:
                        resp_msg = await self.bot.wait_for("message", check=check_choice, timeout=20.0)
                        resp_val = resp_msg.content.strip().lower()
                        if resp_val in ["c", "cancel", "huy"]:
                            await self.reply_text(resp_msg, "❌ Đã hủy xử lý link TikTok.", delay=15)
                            return
                        elif resp_val in ["v", "voice", "play", "am", "1"]:
                            req_mode = "voice"
                        elif resp_val in ["f", "file", "video", "mp4", "down", "dl", "2"]:
                            req_mode = "file"
                        else:
                            req_mode = "file"
                    except asyncio.TimeoutError:
                        req_mode = "file"
                else:
                    req_mode = "file"

            status_msg = await self.reply_text(ctx.message, "⏳ Đang trích xuất dữ liệu TikTok...", delay=15)
            data = await self.get_tiktok_info(tiktok_url)
            if not data:
                await self.reply_text(ctx.message, "❌ Không thể tải video TikTok này (link lỗi hoặc video riêng tư).", delay=30)
                return

            images = data.get("images")
            video_url = self._normalize_url(data.get("hdplay") or data.get("play") or data.get("wmplay"))
            audio_url = self._normalize_url(data.get("music") or data.get("music_info", {}).get("play") or video_url)
            title = data.get("title", "TikTok Video")[:80]
            author = data.get("author", {}).get("nickname", "Creator")
            likes = self.format_num(data.get("digg_count", 0))
            thumb_url = data.get("cover") or data.get("origin_cover") or ""
            dur_sec = data.get("duration", 0)
            dur_str = f"{int(dur_sec // 60):02d}:{int(dur_sec % 60):02d}" if dur_sec else ""

            if req_mode == "voice" and audio_url:
                await self.play_in_voice(ctx, audio_url, title, author, tiktok_url, thumb_url=thumb_url, duration=dur_str)
            elif images and isinstance(images, list) and len(images) > 0:
                await self.download_and_send_slideshow(ctx, images, audio_url, title, author, likes, tiktok_url, meta=data)
            elif video_url:
                await self.download_and_send_video(ctx, video_url, title, author, likes, tiktok_url, meta=data)
            elif audio_url:
                await self.reply_text(ctx.message, f"🎵 Nội dung TikTok này chỉ có âm thanh/nhạc nền.", delay=15)
            return

        # 2. Tìm kiếm 20 video TikTok theo từ khóa
        status = await self.reply_text(ctx.message, f"🔍 Đang tìm kiếm TikTok: **{query}**...", delay=15)
        videos = await self.search_tiktok(query)

        if not videos:
            await self.reply_text(ctx.message, "❌ Không tìm thấy video TikTok nào phù hợp.", delay=30)
            return

        # Chuẩn bị dữ liệu để render Card ảnh
        items_gui = []
        for v in videos:
            dur_sec = v.get("duration", 0)
            dur_str = f"{int(dur_sec // 60):02d}:{int(dur_sec % 60):02d}" if dur_sec else ""
            thumb_url = v.get("cover") or v.get("origin_cover") or ""
            items_gui.append({
                "title": v.get("title", "TikTok Video"),
                "author": v.get("author", {}).get("nickname", "Creator"),
                "duration": dur_str,
                "thumb_url": thumb_url
            })

        selector_file = None
        try:
            card_buf = await async_search_card("tiktok", query, items_gui)
            if card_buf:
                selector_file = discord.File(card_buf, filename="tt_search.png")
        except Exception:
            pass

        if not selector_file:
            selector_file = await render_media_selector("TIKTOK", query, items_gui)

        prompt_txt = f"📋 Hãy gõ số `1` - `{len(videos)}` (hoặc kèm `v` để vào Voice, `f` để gửi File, vd `1 v` / `1 f`):"
        try:
            from apps.user_discord.utils.autorep import autorep
        except ImportError:
            from utils.autorep import autorep
        prompt_msg = await autorep(ctx.message, content=prompt_txt, file=selector_file, auto_delete_delay=45)

        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

        try:
            choice_msg = await self.bot.wait_for("message", check=check, timeout=35.0)
            val = choice_msg.content.strip().lower()

            if val in ["c", "cancel", "huy"]:
                await self.reply_text(choice_msg, "❌ Đã hủy lựa chọn TikTok.", delay=15)
                return

            m_choice = re.match(r'^(\d+)(?:\s*([a-zA-Z]+))?$', val)
            if not m_choice:
                return

            choice_idx = int(m_choice.group(1))
            if not (1 <= choice_idx <= len(videos)):
                await self.reply_text(choice_msg, f"❌ Số thứ tự không hợp lệ. Vui lòng chọn từ `1` đến `{len(videos)}`.", delay=15)
                return

            chosen_v = videos[choice_idx - 1]
            video_id = chosen_v.get("video_id") or chosen_v.get("id")
            video_link = chosen_v.get("url") or (f"https://www.tiktok.com/@{chosen_v.get('author', {}).get('unique_id', 'user')}/video/{video_id}" if video_id else "")
            
            video_url = self._normalize_url(chosen_v.get("hdplay") or chosen_v.get("play") or chosen_v.get("wmplay"))
            audio_url = self._normalize_url(chosen_v.get("music") or chosen_v.get("music_info", {}).get("play") or video_url)
            title = chosen_v.get("title", "TikTok Video")
            author = chosen_v.get("author", {}).get("nickname", "Creator")
            likes = self.format_num(chosen_v.get("digg_count", 0))
            thumb_url = chosen_v.get("cover") or chosen_v.get("origin_cover") or ""
            dur_sec = chosen_v.get("duration", 0)
            dur_str = f"{int(dur_sec // 60):02d}:{int(dur_sec % 60):02d}" if dur_sec else ""

            # NẾU CHƯA CÓ LINK VIDEO / AUDIO: LẬP TỨC TRÍCH XUẤT FULL DATA NGAY
            if (not video_url or not audio_url) and video_link:
                try:
                    await self.reply_text(choice_msg, f"⏳ Đang lấy dữ liệu video TikTok #{choice_idx}...", delay=15)
                    fetched_data = await self.get_tiktok_info(video_link)
                    if fetched_data:
                        chosen_v = fetched_data
                        video_url = self._normalize_url(chosen_v.get("hdplay") or chosen_v.get("play") or chosen_v.get("wmplay") or video_url)
                        audio_url = self._normalize_url(chosen_v.get("music") or chosen_v.get("music_info", {}).get("play") or video_url)
                        title = chosen_v.get("title", title)
                        author = chosen_v.get("author", {}).get("nickname", author)
                        likes = self.format_num(chosen_v.get("digg_count", 0))
                        thumb_url = chosen_v.get("cover") or chosen_v.get("origin_cover") or thumb_url
                        dur_sec = chosen_v.get("duration", dur_sec)
                        if dur_sec:
                            dur_str = f"{int(dur_sec // 60):02d}:{int(dur_sec % 60):02d}"
                except Exception:
                    pass

            if not video_url and not audio_url:
                await self.reply_text(choice_msg, f"❌ Không thể lấy link tải cho video #{choice_idx} (video bị hạn chế hoặc link hỏng). Bạn hãy thử chọn số khác hoặc dán link trực tiếp!", delay=20)
                return

            req_suffix = (m_choice.group(2) or "").lower()
            mode = None
            if req_suffix in ["v", "voice", "play", "am"]:
                mode = "voice"
            elif req_suffix in ["f", "file", "video", "mp4", "down", "dl"]:
                mode = "file"
            else:
                # User chỉ gõ số mà không kèm v hay f: Hỏi user muốn voice hay file
                ask_menu = (
                    f"🎬 **Bạn đã chọn video #{choice_idx}:** *{title[:50]}*\n"
                    f"👉 Gõ `v` để **Phát nhạc vào Voice** 🔊\n"
                    f"👉 Gõ `f` để **Tải File Video MP4/Ảnh** 📥\n"
                    f"*(Hoặc gõ `c` để hủy. Hết hạn sau 20s)*"
                )
                await self.reply_text(choice_msg, ask_menu, delay=25)
                try:
                    mode_msg = await self.bot.wait_for("message", check=check, timeout=20.0)
                    m_val = mode_msg.content.strip().lower()
                    if m_val in ["c", "cancel", "huy"]:
                        await self.reply_text(mode_msg, "❌ Đã hủy lựa chọn.", delay=15)
                        return
                    elif m_val in ["v", "voice", "play", "am", "1"]:
                        mode = "voice"
                    elif m_val in ["f", "file", "video", "mp4", "down", "dl", "2"]:
                        mode = "file"
                    else:
                        mode = "voice" if (ctx.author.voice and ctx.author.voice.channel) else "file"
                except asyncio.TimeoutError:
                    mode = "voice" if (ctx.author.voice and ctx.author.voice.channel) else "file"

            images = chosen_v.get("images")
            if mode == "voice" and audio_url:
                await self.play_in_voice(ctx, audio_url, title, author, video_link, thumb_url=thumb_url, duration=dur_str)
            elif images and isinstance(images, list) and len(images) > 0:
                await self.download_and_send_slideshow(ctx, images, audio_url, title, author, likes, video_link, meta=chosen_v)
            elif video_url:
                await self.reply_text(choice_msg, f"⏳ Đang tải video TikTok: **{title}**...", delay=15)
                await self.download_and_send_video(ctx, video_url, title, author, likes, video_link, meta=chosen_v)
            elif audio_url:
                await self.reply_text(choice_msg, f"🎵 Nội dung TikTok này chỉ có âm thanh/nhạc nền.", delay=15)
            else:
                await self.reply_text(choice_msg, "❌ Không tìm thấy luồng phát phù hợp cho video này.", delay=20)

        except asyncio.TimeoutError:
            pass

    @cmd_tiktok.command(name="info", aliases=["acc", "card", "user"])
    async def tt_info(self, ctx, *, query: str = None):
        """Xem thông tin account và video TikTok dạng Card Liquid Glass siêu đẹp: (prefix)tt info <link>"""
        if not query:
            try:
                from apps.user_discord.utils.prefix import get_prefix
            except ImportError:
                from utils.prefix import get_prefix
            pfx = get_prefix(self.bot)
            await self.reply_text(ctx.message, f"❌ Cú pháp: `{pfx}tt info <link TikTok>`", delay=20)
            return

        tiktok_url = self.extract_tiktok_url(query) or query.strip()
        status_msg = await self.reply_text(ctx.message, "⏳ Đang trích xuất thông tin account & video TikTok...", delay=15)
        data = await self.get_tiktok_info(tiktok_url)
        if not data:
            await self.reply_text(ctx.message, "❌ Không thể lấy thông tin video TikTok này (link lỗi hoặc riêng tư).", delay=20)
            return

        title = data.get("title", "TikTok Video")
        author = data.get("author", {}).get("nickname", "Creator")
        author_user = data.get("author", {}).get("unique_id", "")
        region = data.get("region", "")
        avatar_url = data.get("author", {}).get("avatar", "")
        likes = self.format_num(data.get("digg_count", 0))
        comments = self.format_num(data.get("comment_count", 0))
        shares = self.format_num(data.get("share_count", 0))
        views = self.format_num(data.get("play_count", 0))
        hashtags = [f"#{tag}" for tag in re.findall(r'#(\w+)', title)]
        music_name = data.get("music_info", {}).get("title", "") or data.get("music", "")

        try:
            card_buf = await async_tiktok_video_card(
                title=title,
                author_nick=author,
                author_user=author_user,
                region=region,
                avatar_url=avatar_url,
                likes=likes,
                comments=comments,
                shares=shares,
                views=views,
                hashtags=hashtags,
                music_name=music_name
            )
            if card_buf:
                card_file = discord.File(card_buf, filename="tiktok_glass_info.png")
                try:
                    from apps.user_discord.utils.autorep import autorep
                except ImportError:
                    from utils.autorep import autorep
                caption = f"✨ **THÔNG TIN ACCOUNT & VIDEO TIKTOK**\n👤 Kênh: **{author}** (@{author_user})\n🔗 {tiktok_url}"
                await autorep(ctx.message, content=caption, file=card_file, auto_delete_delay=None)
            else:
                await self.reply_text(ctx.message, "❌ Không thể render Card thông tin TikTok.", delay=20)
        except Exception as e:
            await self.reply_text(ctx.message, f"❌ Lỗi: {str(e)[:100]}", delay=20)

    @cmd_tiktok.command(name="stop", aliases=["leave", "dc", "offvoice"])
    async def tt_stop(self, ctx):
        """Dừng phát âm thanh TikTok và rời Voice: (prefix)tt stop"""
        await self._do_stop(ctx)

async def setup(bot):
    await bot.add_cog(TikTokModule(bot))
