import discord
from discord.ext import commands
import asyncio
import os
import sys
import re
import tempfile
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
import yt_dlp
from apps.user_discord.utils.media_card import async_search_card, async_nowplaying_card, async_help_card
from apps.user_discord.utils.menu_catalog import menu_entry
from apps.user_discord.core.alias import alias_declare
from apps.user_discord.utils.lavalink_voice import (
    LavalinkPlayer,
    LavalinkManager,
    forward_voice_to_lavalink,
    wait_voice_credentials,
    stop_fake_voice_playback,
)
from apps.user_discord.utils.fake_voice_gateway import (
    FakeVoiceGateway,
    OpusGatewaySource,
)


def _log(msg) -> None:
    text = str(msg)
    try:
        print(text, flush=True)
    except Exception:
        try:
            buf = getattr(sys.stdout, "buffer", None)
            if buf is not None:
                buf.write((text + "\n").encode("utf-8", "replace"))
                sys.stdout.flush()
        except Exception:
            pass


class YouTubeModule(commands.Cog):
    """
    Module YouTube Music chia làm 2 phần rõ rệt:
    1. THÔNG TIN: Dùng yt-dlp trích xuất metadata (Title, Author, Duration, Thumbnail, Link).
       Chỉ đọc thông tin phẳng (extract_flat=True, skip_download=True), không bao giờ tải file hay stream video.
    2. THỰC HÀNH: Dùng Lavalink V4 SSL Engine đảm nhiệm kết nối và stream âm thanh vào Voice Channel.
       Bypass triệt để việc IP Datacenter/Hosting của bot bị YouTube chặn khi phát nhạc.
    """
    def __init__(self, bot):
        self.bot = bot
        self.current_track = {}     # guild_id -> dict
        self._fallback_files = {}   # guild_id -> filepath tải về bằng yt-dlp
        self.temp_dir = os.path.join("data", "youtube")
        os.makedirs(self.temp_dir, exist_ok=True)

    async def reply_text(self, message, text, delay=30):
        try:
            from apps.user_discord.utils.autorep import autorep
        except ImportError:
            from utils.autorep import autorep
        return await autorep(message, content=text, auto_delete_delay=delay)

    @staticmethod
    def _yt_thumb_from_id(vid: str) -> str:
        return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""

    # =========================================================================
    # PHẦN 1: THÔNG TIN (DÙNG YT-DLP TRÍCH XUẤT METADATA, KHÔNG TẢI BÀI)
    # =========================================================================
    def _extract_metadata_flat(self, query: str, limit: int = 10) -> list:
        """
        Sử dụng yt-dlp chỉ để lấy thông tin: thumbnail, title, uploader, duration và link.
        Tuyệt đối không tải video hay stream về máy tính (skip_download=True, extract_flat=True).
        """
        is_url = "youtube.com" in query or "youtu.be" in query
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'extract_flat': True,
            'noplaylist': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web']
                }
            }
        }

        results = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_target = query if is_url else f"ytsearch{limit}:{query}"
                info = ydl.extract_info(search_target, download=False)
                if not info:
                    return []

                raw_entries = [info] if is_url else info.get('entries', [])
                for it in raw_entries:
                    if not it:
                        continue
                    v_id = it.get('id') or ""
                    dur = it.get('duration') or 0
                    dur_str = f"{int(dur // 60):02d}:{int(dur % 60):02d}" if dur else ""
                    raw_thumb = it.get('thumbnail') or ""
                    if not raw_thumb and v_id:
                        raw_thumb = self._yt_thumb_from_id(v_id)

                    results.append({
                        'id': v_id,
                        'title': it.get('title') or "YouTube Track",
                        'author': it.get('uploader') or it.get('channel') or "YouTube Artist",
                        'duration': dur_str,
                        'thumb_url': raw_thumb,
                        'url': it.get('url') or (f"https://www.youtube.com/watch?v={v_id}" if v_id else query)
                    })
                    if len(results) >= limit:
                        break
        except Exception as e:
            _log(f"[Metadata Extract Err] {e}")

        return results

    # =========================================================================
    # PHẦN 2: THỰC HÀNH (DÙNG LAVALINK V4 SSL PHÁT ÂM THANH VÀO VOICE)
    # =========================================================================
    async def _resolve_via_lavalink(self, track_url: str) -> Optional[dict]:
        """Gửi link yt-dlp lấy được sang Lavalink V4 SSL để phân giải track sạch."""
        mgr = LavalinkManager.get_instance(self.bot)
        if not mgr:
            mgr = LavalinkManager(self.bot)
            LavalinkManager._instance = mgr
        mgr.ensure_connecting()

        _log(f"[LAVALINK REQUEST 🚀] Gửi link sang Lavalink Node: {track_url}")
        try:
            tracks = await mgr.search(track_url, limit=1)
            if tracks:
                _log(f"[LAVALINK SUCCESS 🟢] Node đã phân giải: {tracks[0].get('title')}")
                return tracks[0]
        except Exception as e:
            _log(f"[Lavalink Resolve Err] {e}")
        return None

    @staticmethod
    def _download_ytdlp_file(target_url: str) -> dict:
        """Tai audio YouTube ve file tam (mp3) khi Lavalink chet."""
        cache_dir = Path(tempfile.gettempdir()) / "botdis_ytdlp"
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        stamp = f"{int(time.time() * 1000)}"
        out_tpl = str(cache_dir / f"%(id)s_{stamp}.%(ext)s")
        options = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "outtmpl": out_tpl,
            "retries": 3,
            "fragment_retries": 3,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }],
            "postprocessor_args": ["-ar", "48000", "-ac", "2"],
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(target_url, download=True)
        if info and info.get("entries"):
            info = next((e for e in info["entries"] if e), None)
        if not info:
            raise RuntimeError("yt-dlp khong tai duoc file audio")
        vid = info.get("id") or "audio"
        cands = sorted(
            cache_dir.glob(f"{vid}_{stamp}.*"),
            key=lambda p: p.stat().st_size if p.exists() else 0,
            reverse=True,
        )
        file_path = ""
        for cand in cands:
            if cand.suffix.lower() in (".mp3", ".m4a", ".webm", ".opus", ".ogg", ".wav"):
                file_path = str(cand)
                break
        if not file_path:
            guessed = cache_dir / f"{vid}_{stamp}.mp3"
            if guessed.exists():
                file_path = str(guessed)
        if not file_path or not os.path.exists(file_path):
            raise RuntimeError("tai xong nhung khong tim thay file audio")
        info["filepath"] = file_path
        return info

    def _cleanup_fallback_file(self, guild_id: int) -> None:
        old = self._fallback_files.pop(int(guild_id), None)
        if not old:
            return
        try:
            if os.path.exists(old):
                os.remove(old)
        except Exception:
            pass

    async def _play_ytdlp_fallback(self, ctx, target_url: str, title: str, uploader: str, meta: dict = None):
        """Fallback: tai file yt-dlp ve roi phat nhu mic user."""
        vs = getattr(ctx.author, "voice", None)
        channel = vs.channel if vs else None
        if channel is None:
            await self.reply_text(ctx.message, "❌ Bạn cần vào Voice trước!", delay=20)
            return False
        guild = channel.guild
        await self.reply_text(ctx.message, "⚠️ Lavalink lỗi, đang tải file yt-dlp về phát mic...", delay=20)
        try:
            info = await asyncio.to_thread(self._download_ytdlp_file, target_url)
            file_path = info.get("filepath", "")
            final_title = info.get("title") or title or "YouTube Audio"
            final_author = info.get("uploader") or info.get("channel") or uploader or "YouTube"
            dur = info.get("duration") or 0
            dur_txt = f"{int(dur // 60):02d}:{int(dur % 60):02d}" if dur else ""
            thumb = info.get("thumbnail") or (meta or {}).get("thumb_url", "")
            self._cleanup_fallback_file(guild.id)

            voice_client = guild.voice_client
            if voice_client is not None and not isinstance(voice_client, discord.VoiceClient):
                try:
                    await voice_client.disconnect(force=True)
                except Exception:
                    pass
                voice_client = None
                await asyncio.sleep(0.5)

            if voice_client is None or not voice_client.is_connected():
                voice_client = await channel.connect(
                    reconnect=True, timeout=25.0, self_deaf=False, self_mute=False
                )
            elif getattr(getattr(voice_client, "channel", None), "id", None) != channel.id:
                await voice_client.move_to(channel)

            try:
                await guild.change_voice_state(channel=channel, self_mute=False, self_deaf=False)
            except Exception:
                pass
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
            if not file_path or not os.path.exists(file_path) or os.path.getsize(file_path) <= 0:
                raise RuntimeError("file audio tai ve bi rong")
            gid = int(guild.id)
            cached = file_path

            def _after_play(error=None):
                if error:
                    _log(f"[YT-DLP FILE AFTER] {error}")
                try:
                    if os.path.exists(cached):
                        os.remove(cached)
                except Exception:
                    pass
                self._fallback_files.pop(gid, None)

            src = discord.FFmpegPCMAudio(file_path, before_options="-nostdin", options="-vn -ar 48000 -ac 2 -b:a 128k")
            voice_client.play(src, after=_after_play)
            self._fallback_files[guild.id] = file_path
            self.current_track[guild.id] = {
                "title": final_title,
                "author": final_author,
                "duration": dur_txt,
                "thumb_url": thumb,
                "channel": channel.name,
            }
            await self._send_nowplaying(ctx, final_title, final_author, dur_txt, thumb, channel, engine="yt-dlp file + mic fallback")
            _log(f"[YT-DLP FILE FALLBACK] Phat file '{final_title}' trong {channel.name}.")
            return True
        except Exception as error:
            _log(f"[YT-DLP FALLBACK ERROR] {type(error).__name__}: {error}")
            await self.reply_text(ctx.message, f"❌ Lavalink loi va yt-dlp tai file that bai: {str(error)[:180]}", delay=25)
            return False

    async def play_in_voice(self, ctx, target_url: str, title: str = None, uploader: str = None, meta: dict = None):
        """
        Thực hành phát âm thanh:
        1. Gửi link bài hát sang server Lavalink V4 SSL để lấy luồng âm thanh sạch không bị datacenter chặn.
        2. Kết nối vào Voice Channel thông qua LavalinkPlayer (channel.connect(cls=LavalinkPlayer)).
        3. Lavalink V4 Node tự động đảm nhiệm việc stream âm thanh chất lượng cao vào phòng Voice.
        """
        if not ctx.author.voice or not ctx.author.voice.channel:
            await self.reply_text(ctx.message, "❌ Bạn cần tham gia một kênh Voice trước để phát nhạc!", delay=20)
            return

        channel = ctx.author.voice.channel
        guild = channel.guild
        guild_id = guild.id

        await self.reply_text(ctx.message, "⚡ **Đang gửi yêu cầu sang Lavalink V4 giải mã âm thanh...**", delay=15)

        # Gửi link sang Lavalink Node phân giải track
        lavalink_track = await self._resolve_via_lavalink(target_url)

        final_title = title or (lavalink_track.get("title") if lavalink_track else None) or (meta.get("title") if meta else "YouTube Track")
        final_author = uploader or (lavalink_track.get("author") if lavalink_track else None) or (meta.get("author") if meta else "YouTube")
        final_dur = (lavalink_track.get("duration") if lavalink_track else None) or (meta.get("duration") if meta else "")
        final_thumb = (lavalink_track.get("thumb_url") if lavalink_track else None) or (meta.get("thumb_url") if meta else "") or self._yt_thumb_from_id(meta.get("id", "") if meta else "")

        if not lavalink_track:
            await self.reply_text(
                ctx.message,
                "⚠️ Không có Lavalink node khả dụng; đang thử yt-dlp fallback...",
                delay=20,
            )
            await self._play_ytdlp_fallback(
                ctx, target_url, final_title, final_author, meta=meta
            )
            return

        # Nếu Lavalink không phân giải được link trực tiếp, tạo track info cơ bản
        if not lavalink_track:
            lavalink_track = {
                "title": final_title,
                "author": final_author,
                "duration": final_dur,
                "thumb_url": final_thumb,
                "uri": target_url,
                "encoded": ""
            }

        try:
            # 1) Bật Fake Discord Voice Gateway (WS nội bộ + UDP hứng Opus)
            gateway = FakeVoiceGateway.instance()
            await gateway.start()
            # Tạo sẵn nguồn Opus để KHÔNG mất khung nào khi Lavalink phát quá nhanh
            opus_source = OpusGatewaySource(gateway, guild_id)

            # 2) Bot THẬT SỰ vào Voice bằng VoiceClient chuẩn (đủ DAVE/E2EE)
            vc = guild.voice_client
            if vc is not None and not isinstance(vc, discord.VoiceClient):
                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass
                vc = None
                await asyncio.sleep(0.5)

            if vc is None or not vc.is_connected():
                try:
                    vc = await channel.connect(
                        reconnect=True, timeout=25.0, self_deaf=False, self_mute=False
                    )
                except Exception as e:
                    await self.reply_text(
                        ctx.message,
                        f"❌ Bot không vào được Voice (lỗi E2EE/DAVE?): `{e}`",
                        delay=25,
                    )
                    return
            elif getattr(getattr(vc, "channel", None), "id", None) != channel.id:
                await vc.move_to(channel)

            # 3) Đợi Discord cấp token + session_id cho bot user
            token, session_id = await wait_voice_credentials(vc, timeout=25.0)
            if not token:
                await self.reply_text(
                    ctx.message, "❌ Không nhận được voice credentials từ Discord.", delay=25
                )
                return

            # 4) Đẩy credentials (endpoint GIẢ) + track sang Lavalink
            play_ok = await forward_voice_to_lavalink(
                self.bot, guild_id, token, session_id, channel.id,
                encoded=lavalink_track.get("encoded") or None, volume=100,
            )
            if not play_ok:
                await self.reply_text(ctx.message, "⚠️ Lavalink phát lỗi, chuyển sang tải file yt-dlp...", delay=20)
                await self._play_ytdlp_fallback(ctx, target_url, final_title, final_author, meta=meta)
                return

            # 5) Nghe Opus từ gateway và phát lại (KHÔNG mã hoá lại -> nhẹ CPU)
            try:
                if vc.is_playing():
                    vc.stop()
            except Exception:
                pass
            vc.play(opus_source)

            self.current_track[guild_id] = {
                'title': final_title,
                'author': final_author,
                'duration': final_dur,
                'thumb_url': final_thumb,
                'channel': channel.name
            }
            # Gửi duy nhất 1 card NowPlaying
            await self._send_nowplaying(ctx, final_title, final_author, final_dur, final_thumb, channel, engine="Lavalink V4 → Fake Voice Gateway")
            _log(f"[YT PLAY 🟢] '{final_title}' đang phát qua Fake Voice Gateway trong: {channel.name}")

        except Exception as e:
            _log(f"[Play Voice Err] {e}")
            await self.reply_text(ctx.message, "⚠️ Lavalink lỗi, chuyển sang tải file yt-dlp...", delay=20)
            await self._play_ytdlp_fallback(ctx, target_url, final_title, final_author, meta=meta)

    async def _send_nowplaying(self, ctx, title: str, uploader: str, duration: str, thumb: str, channel, engine: str = "Lavalink V4 SSL"):
        """Gửi DUY NHẤT 1 Card NowPlaying YouTube siêu đẹp."""
        card_file = None
        try:
            card_buf = await async_nowplaying_card(
                "youtube", title, uploader, duration or "", thumb or "",
                channel_name=channel.name, engine=engine,
            )
            if card_buf:
                card_file = discord.File(card_buf, filename="nowplaying.png")
        except Exception as ce:
            _log(f"[Card render err] {ce}")

        caption = (
            f"🎵 **Đang phát:** **{title}**\n"
            f"👤 {uploader} | 📍 {channel.name}\n"
            f"🛡️ Engine: `{engine}`\n"
            f"*Gõ `(prefix)yt stop` để dừng.*"
        )
        try:
            from apps.user_discord.utils.autorep import autorep
            from apps.user_discord.utils.prefix import fmt as _pfx_fmt
            caption = _pfx_fmt(self.bot, caption)
            return await autorep(ctx.message, content=caption, file=card_file, auto_delete_delay=None)
        except Exception:
            return None

    async def download_and_send_media(self, ctx, title: str, uploader: str, video_url: str, is_audio: bool = True):
        """Tải file âm thanh (MP3) hoặc video (MP4) YouTube bằng yt-dlp và gửi vào Discord."""
        clean_title = re.sub(r'[^\w\s-]', '', title)[:30].strip() or "youtube_media"
        ext = "mp3" if is_audio else "mp4"
        local_path = os.path.join(self.temp_dir, f"yt_{int(asyncio.get_event_loop().time())}_{clean_title}.{ext}")

        loop = asyncio.get_event_loop()
        def _dl():
            if is_audio:
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': local_path,
                    'quiet': True,
                    'no_warnings': True,
                    'max_filesize': 25 * 1024 * 1024,
                }
            else:
                ydl_opts = {
                    'format': 'best[ext=mp4]/best',
                    'outtmpl': local_path,
                    'quiet': True,
                    'no_warnings': True,
                    'max_filesize': 25 * 1024 * 1024,
                }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            return os.path.exists(local_path)

        try:
            ok = await loop.run_in_executor(None, _dl)
            if ok and os.path.getsize(local_path) <= 25 * 1024 * 1024:
                with open(local_path, "rb") as f:
                    file = discord.File(fp=f, filename=f"{clean_title}.{ext}")
                    type_str = "🎵 File Âm Thanh" if is_audio else "🎬 Video MP4"
                    caption = f"{type_str}: **{title}**\n👤 Kênh: **{uploader}**\n🔗 {video_url}"
                    try:
                        from apps.user_discord.utils.autorep import autorep
                        await autorep(ctx.message, content=caption, file=file, auto_delete_delay=None)
                    except Exception:
                        await ctx.send(content=caption, file=file)
            else:
                await self.reply_text(ctx.message, f"⚠️ File vượt quá giới hạn 25MB của Discord.\n🔗 Xem trực tiếp: {video_url}", delay=25)
        except Exception as e:
            await self.reply_text(ctx.message, f"❌ Lỗi tải YouTube: {e}", delay=20)
        finally:
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except Exception:
                    pass

    async def _do_stop(self, ctx):
        """Dừng phát âm thanh và rời Voice."""
        stopped = False
        if ctx.guild and ctx.guild.voice_client:
            vc = ctx.guild.voice_client
            try:
                if hasattr(vc, "stop_track"):
                    await vc.stop_track()
                elif hasattr(vc, "stop") and callable(vc.stop):
                    vc.stop()
                await stop_fake_voice_playback(self.bot, ctx.guild.id)
                await vc.disconnect(force=True)
                stopped = True
            except Exception:
                pass
        try:
            self._cleanup_fallback_file(ctx.guild.id)
        except Exception:
            pass
        self.current_track.pop(ctx.guild.id, None)
        if stopped:
            await self.reply_text(ctx.message, "⏹️ Đã dừng phát nhạc và rời Voice.", delay=15)
        else:
            await self.reply_text(ctx.message, "ℹ️ Hiện không có bài hát nào đang phát.", delay=15)

    # =========================================================================
    # LỆNH CHÍNH & MENU ĐIỀU KHIỂN
    # =========================================================================
    @menu_entry("MEDIA & ENTERTAINMENT", "yt", "Phát Voice YouTube (yt-dlp Info + Lavalink Voice)",
                icon_sym="▶", icon_color=(255, 85, 85), order=1)
    @alias_declare("youtube", main="youtube", subs=["yt"])
    @commands.group(name="youtube", aliases=["yt"], invoke_without_command=True)
    async def cmd_youtube(self, ctx, *, query: str = None):
        """Tìm kiếm (yt-dlp info) và phát nhạc (Lavalink V4 SSL)."""
        if not query:
            from apps.user_discord.utils.prefix import get_prefix
            pfx = get_prefix(self.bot)
            card_buf = await async_help_card("youtube", pfx)
            if card_buf:
                card_file = discord.File(card_buf, filename="yt_guide.png")
                from apps.user_discord.utils.autorep import autorep
                await autorep(ctx.message, content="📺 **HƯỚNG DẪN SỬ DỤNG LỆNH YOUTUBE**", file=card_file, auto_delete_delay=60)
            else:
                await self.reply_text(ctx.message, f"❌ Cú pháp: `{pfx}yt <từ khóa>` hoặc `{pfx}yt <link>` | `{pfx}yt stop`", delay=30)
            return

        # 1. Nếu người dùng dán Link trực tiếp
        if "youtube.com" in query or "youtu.be" in query:
            clean_url = query.split()[0]
            await self.play_in_voice(ctx, clean_url, "YouTube Video", "YouTube")
            return

        # 2. PHẦN 1: Dùng yt-dlp trích xuất danh sách 10 bài hát (flat metadata, KHÔNG tải video)
        await self.reply_text(ctx.message, f"🔍 Đang tìm kiếm YouTube: **{query}**...", delay=15)
        loop = asyncio.get_event_loop()
        entries = await loop.run_in_executor(None, self._extract_metadata_flat, query, 10)

        if not entries:
            await self.reply_text(ctx.message, "❌ Không tìm thấy video YouTube nào phù hợp.", delay=30)
            return

        # Render Card ảnh danh sách kết quả Glassmorphism
        items_gui = []
        for it in entries:
            items_gui.append({
                "title": it.get("title", "YouTube Video"),
                "author": it.get("author", "YouTube Channel"),
                "duration": it.get("duration", "0:00"),
                "thumb_url": it.get("thumb_url") or self._yt_thumb_from_id(it.get("id") or "")
            })

        selector_file = None
        try:
            card_buf = await async_search_card("youtube", query, items_gui)
            if card_buf:
                selector_file = discord.File(card_buf, filename="yt_search.png")
        except Exception:
            pass

        if not selector_file:
            from apps.user_discord.utils.media_gui import render_media_selector
            selector_file = await render_media_selector("YOUTUBE", query, items_gui)

        prompt_txt = f"📋 Hãy gõ số `1` - `{len(entries)}` (kèm `v` để vào Voice, `f` để tải MP3, `mp4` để tải Video, vd `1 v` / `1 f` / `1 mp4`):"
        from apps.user_discord.utils.autorep import autorep
        await autorep(ctx.message, content=prompt_txt, file=selector_file, auto_delete_delay=45)

        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

        try:
            choice_msg = await self.bot.wait_for("message", check=check, timeout=35.0)
            val = choice_msg.content.strip().lower()

            if val in ["c", "cancel", "huy"]:
                await self.reply_text(choice_msg, "❌ Đã hủy lựa chọn YouTube.", delay=15)
                return

            m_choice = re.match(r'^(\d+)(?:\s*([a-zA-Z0-9]+))?$', val)
            if not m_choice:
                return

            choice_idx = int(m_choice.group(1))
            if not (1 <= choice_idx <= len(entries)):
                await self.reply_text(choice_msg, "❌ Số thứ tự không hợp lệ.", delay=15)
                return

            chosen_entry = entries[choice_idx - 1]
            video_url = chosen_entry.get("url")
            title = chosen_entry.get("title", "YouTube Video")
            uploader = chosen_entry.get("author", "YouTube")

            req_suffix = (m_choice.group(2) or "").lower()
            mode = None
            if req_suffix in ["v", "voice", "play", "am"]:
                mode = "voice"
            elif req_suffix in ["f", "file", "mp3", "audio", "dl", "down"]:
                mode = "audio"
            elif req_suffix in ["mp4", "vid", "video"]:
                mode = "video"
            else:
                # User chỉ gõ số mà không kèm hậu tố: Hiện menu hỏi nhanh
                ask_menu = (
                    f"📺 **Bạn đã chọn video #{choice_idx}:** *{title[:50]}*\n"
                    f"👉 Gõ `v` để **Phát nhạc vào Voice** 🔊\n"
                    f"👉 Gõ `f` để **Tải file Âm Thanh MP3** 📥\n"
                    f"👉 Gõ `mp4` để **Tải Video MP4** 🎬\n"
                    f"*(Hoặc gõ `c` để hủy. Hết hạn sau 20s)*"
                )
                await self.reply_text(choice_msg, ask_menu, delay=25)
                try:
                    mode_msg = await self.bot.wait_for("message", check=check, timeout=20.0)
                    m_val = mode_msg.content.strip().lower()
                    if m_val in ["c", "cancel", "huy"]:
                        await self.reply_text(mode_msg, "❌ Đã hủy lựa chọn.", delay=15)
                        return
                    elif m_val in ["v", "voice", "play", "1"]:
                        mode = "voice"
                    elif m_val in ["f", "file", "mp3", "2"]:
                        mode = "audio"
                    elif m_val in ["mp4", "vid", "video", "3"]:
                        mode = "video"
                    else:
                        mode = "voice" if (ctx.author.voice and ctx.author.voice.channel) else "audio"
                except asyncio.TimeoutError:
                    mode = "voice" if (ctx.author.voice and ctx.author.voice.channel) else "audio"

            if mode == "audio":
                await self.reply_text(choice_msg, f"⏳ Đang tải file âm thanh MP3: **{title}**...", delay=15)
                await self.download_and_send_media(ctx, title, uploader, video_url, is_audio=True)
            elif mode == "video":
                await self.reply_text(choice_msg, f"⏳ Đang tải video MP4: **{title}**...", delay=15)
                await self.download_and_send_media(ctx, title, uploader, video_url, is_audio=False)
            else:
                await self.play_in_voice(ctx, video_url, title, uploader, meta=chosen_entry)

        except asyncio.TimeoutError:
            pass

    @cmd_youtube.command(name="dl", aliases=["mp3", "file", "down", "download"])
    async def yt_dl(self, ctx, *, query: str):
        """Tải thẳng file âm thanh MP3 từ YouTube: (prefix)yt dl <link hoặc từ khóa>"""
        if "youtube.com" in query or "youtu.be" in query:
            clean_url = query.split()[0]
            await self.reply_text(ctx.message, "⏳ Đang tải file MP3 từ link YouTube...", delay=15)
            await self.download_and_send_media(ctx, "YouTube Audio", "YouTube", clean_url, is_audio=True)
            return

        await self.reply_text(ctx.message, f"🔍 Đang tìm kiếm MP3: **{query}**...", delay=10)
        loop = asyncio.get_event_loop()
        entries = await loop.run_in_executor(None, self._extract_metadata_flat, query, 1)
        if not entries:
            return await self.reply_text(ctx.message, "❌ Không tìm thấy bài hát phù hợp.", delay=15)
        top = entries[0]
        await self.reply_text(ctx.message, f"⏳ Đang tải MP3: **{top.get('title')}**...", delay=15)
        await self.download_and_send_media(ctx, top.get("title", "Audio"), top.get("author", "YouTube"), top.get("url"), is_audio=True)

    @cmd_youtube.command(name="mp4", aliases=["video", "vid"])
    async def yt_mp4(self, ctx, *, query: str):
        """Tải thẳng video MP4 từ YouTube: (prefix)yt mp4 <link hoặc từ khóa>"""
        if "youtube.com" in query or "youtu.be" in query:
            clean_url = query.split()[0]
            await self.reply_text(ctx.message, "⏳ Đang tải video MP4 từ link YouTube...", delay=15)
            await self.download_and_send_media(ctx, "YouTube Video", "YouTube", clean_url, is_audio=False)
            return

        await self.reply_text(ctx.message, f"🔍 Đang tìm kiếm Video: **{query}**...", delay=10)
        loop = asyncio.get_event_loop()
        entries = await loop.run_in_executor(None, self._extract_metadata_flat, query, 1)
        if not entries:
            return await self.reply_text(ctx.message, "❌ Không tìm thấy video phù hợp.", delay=15)
        top = entries[0]
        await self.reply_text(ctx.message, f"⏳ Đang tải Video: **{top.get('title')}**...", delay=15)
        await self.download_and_send_media(ctx, top.get("title", "Video"), top.get("author", "YouTube"), top.get("url"), is_audio=False)

    @cmd_youtube.command(name="stop", aliases=["leave", "dc", "offvoice"])
    async def yt_stop(self, ctx):
        """Dừng phát âm thanh YouTube và rời Voice: (prefix)yt stop"""
        await self._do_stop(ctx)

    @cmd_youtube.command(name="pause")
    async def yt_pause(self, ctx):
        """Tạm dừng bài hát đang phát: (prefix)yt pause"""
        vc = ctx.guild.voice_client if ctx.guild else None
        if vc and hasattr(vc, "is_playing") and vc.is_playing():
            if hasattr(vc, "pause"):
                vc.pause()
            await self.reply_text(ctx.message, "⏸️ Đã tạm dừng phát nhạc.", delay=15)
        else:
            await self.reply_text(ctx.message, "❌ Hiện không có bài hát nào đang phát để tạm dừng.", delay=15)

    @cmd_youtube.command(name="resume")
    async def yt_resume(self, ctx):
        """Tiếp tục phát bài hát: (prefix)yt resume"""
        vc = ctx.guild.voice_client if ctx.guild else None
        if vc and hasattr(vc, "is_paused") and vc.is_paused():
            if hasattr(vc, "resume"):
                vc.resume()
            await self.reply_text(ctx.message, "▶️ Đã tiếp tục phát nhạc.", delay=15)
        else:
            await self.reply_text(ctx.message, "❌ Hiện không có bài hát nào bị tạm dừng.", delay=15)

    @cmd_youtube.command(name="fix", aliases=["rejoin"])
    async def yt_fix(self, ctx):
        """Làm mới kết nối Voice Channel: (prefix)yt fix"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await self.reply_text(ctx.message, "❌ Bạn phải vào voice channel trước!", delay=15)

        channel = ctx.author.voice.channel
        guild = channel.guild
        vc = guild.voice_client
        if vc:
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass
            await asyncio.sleep(0.5)

        try:
            new_vc = await channel.connect(reconnect=True, timeout=20.0, self_deaf=False, self_mute=False)
            if new_vc and new_vc.is_connected():
                await self.reply_text(ctx.message, f"✅ Đã làm mới kết nối Voice Channel `{channel.name}` thành công!", delay=15)
            else:
                await self.reply_text(ctx.message, "❌ Không thể kết nối lại Voice Channel!", delay=15)
        except Exception as e:
            await self.reply_text(ctx.message, f"❌ Lỗi kết nối lại: `{e}`", delay=15)

    @cmd_youtube.command(name="now", aliases=["np"])
    async def yt_now(self, ctx):
        """Hiển thị bài hát hiện tại: (prefix)yt now"""
        track = self.current_track.get(ctx.guild.id)
        vc = ctx.guild.voice_client if ctx.guild else None
        if not track or not vc:
            return await self.reply_text(ctx.message, "❌ Hiện không có bài hát nào đang phát.", delay=15)

        channel = getattr(vc, "channel", None) or ctx.author.voice.channel
        await self._send_nowplaying(
            ctx,
            track.get('title', 'Unknown'),
            track.get('author', 'YouTube'),
            track.get('duration', ''),
            track.get('thumb_url', ''),
            channel,
            engine="Lavalink V4 SSL"
        )


async def setup(bot):
    await bot.add_cog(YouTubeModule(bot))
