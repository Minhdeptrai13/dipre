import discord
from discord.ext import commands
import asyncio
import os
import io
import re
import sys
import urllib.parse
import aiohttp
import base64
import requests
from apps.user_discord.utils.media_gui import render_media_selector
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


WIDGET_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Origin': 'https://w.soundcloud.com',
    'Referer': 'https://w.soundcloud.com/'
}

_ENC_KEYS = [
    "Y2lVWldyZzc5MWo5Y2p0QUVtRG5xSjU3STN4R21ldFk=",
    "MnQ5bG9OZmhUdzRPcFJBQ2RhV2hpcXFTQ1B1OW02S2U=",
    "YlhVcUs0YU00UTladEs5ZjlCMHFWMlc2eTBtMVoyWDM="
]

def get_client_ids():
    res = []
    for k in _ENC_KEYS:
        try:
            res.append(base64.b64decode(k.encode()).decode())
        except Exception:
            pass
    return res

import yt_dlp

class SoundCloudModule(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.temp_dir = os.path.join("data", "soundcloud")
        os.makedirs(self.temp_dir, exist_ok=True)
        self.current_track = {}     # guild_id -> dict

    async def reply_text(self, message, text, delay=30):
        try:
            from apps.user_discord.utils.autorep import autorep
        except ImportError:
            from utils.autorep import autorep
        return await autorep(message, content=text, auto_delete_delay=delay)

    def _ytdlp_search_sc(self, query: str, limit: int = 20) -> list:
        """Tìm kiếm bài hát SoundCloud bằng yt-dlp flat search (lấy metadata & link 100% chuẩn)."""
        opts = {
            'quiet': True,
            'skip_download': True,
            'extract_flat': True,
            'noplaylist': True,
        }
        res_list = []
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"scsearch{limit}:{query}", download=False)
                for it in (info.get("entries") or []):
                    if not it:
                        continue
                    dur = it.get("duration") or 0
                    dur_str = f"{int(dur // 60):02d}:{int(dur % 60):02d}" if dur else ""
                    thumb = it.get("thumbnail") or (it.get("thumbnails", [{}])[-1].get("url") if it.get("thumbnails") else "")
                    res_list.append({
                        "title": it.get("title", "SoundCloud Track"),
                        "author": it.get("uploader") or it.get("channel", "Artist"),
                        "duration": dur_str,
                        "thumb_url": thumb,
                        "uri": it.get("url") or it.get("webpage_url", ""),
                        "encoded": "",
                        "id": it.get("id", "")
                    })
        except Exception as e:
            print(f"[SoundCloud yt-dlp Search Error] {e}", flush=True)
        return res_list

    async def search_tracks(self, query: str, limit: int = 20) -> list:
        """Tìm kiếm bài hát SoundCloud: Ưu tiên Lavalink V4 siêu tốc, fallback sang yt-dlp."""
        try:
            from apps.user_discord.utils.lavalink_voice import LavalinkManager
            mgr = LavalinkManager.get_instance(self.bot)
            if mgr:
                mgr.ensure_connecting()
                res = await mgr.search(query, limit=limit, source="scsearch")
                if res:
                    return res
        except Exception as e:
            print(f"[SoundCloud Lavalink Search Error] {e}", flush=True)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._ytdlp_search_sc, query, limit)

    async def _do_stop(self, ctx):
        """Dừng phát âm thanh SoundCloud và rời Voice."""
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
        self.current_track.pop(ctx.guild.id, None)
        if stopped:
            await self.reply_text(ctx.message, "⏹️ Đã dừng phát nhạc SoundCloud và rời Voice.", delay=15)
        else:
            await self.reply_text(ctx.message, "ℹ️ Hiện không có bài hát nào đang phát.", delay=15)

    async def _resolve_via_lavalink(self, track_url: str):
        """Gui link SoundCloud sang Lavalink V4 SSL de phan giai track sach."""
        if not track_url:
            return None
        mgr = LavalinkManager.get_instance(self.bot)
        if not mgr:
            mgr = LavalinkManager(self.bot)
            LavalinkManager._instance = mgr
        mgr.ensure_connecting()

        _log(f"[SC LAVALINK REQUEST] Gui link sang Lavalink Node: {track_url}")
        try:
            tracks = await mgr.search(track_url, limit=1)
            if tracks:
                _log(f"[SC LAVALINK OK] Node da phan giai: {tracks[0].get('title')}")
                return tracks[0]
        except Exception as e:
            _log(f"[SC Lavalink Resolve Err] {e}")
        return None

    async def play_in_voice(self, ctx, track_info: dict):
        """
        Phat am thanh SoundCloud:
        1. Lay encoded track sach tu Lavalink V4 SSL.
        2. Bot vao Voice bang discord.VoiceClient chuan (du DAVE/E2EE).
        3. Lavalink day Opus ve Fake Voice Gateway -> bot phat lai nguyen khung.
        """
        if not ctx.author.voice or not ctx.author.voice.channel:
            await self.reply_text(ctx.message, "❌ Bạn cần tham gia một kênh Voice trước để bot phát nhạc!", delay=20)
            return

        channel = ctx.author.voice.channel
        guild = channel.guild
        guild_id = guild.id

        target_url = track_info.get("uri", "") or ""
        title = track_info.get("title") or "SoundCloud Track"
        artist = track_info.get("author") or "SoundCloud Artist"
        thumb_url = track_info.get("thumb_url") or ""
        duration = track_info.get("duration") or ""

        await self.reply_text(ctx.message, "⚡ **Đang gửi yêu cầu sang Lavalink V4 giải mã âm thanh...**", delay=15)

        # Uu tien encoded co san tu ket qua search; thieu thi resolve lai bang URL
        lavalink_track = dict(track_info) if track_info.get("encoded") else None
        if not lavalink_track:
            lavalink_track = await self._resolve_via_lavalink(target_url)

        final_title = (lavalink_track.get("title") if lavalink_track else None) or title
        final_author = (lavalink_track.get("author") if lavalink_track else None) or artist
        final_dur = (lavalink_track.get("duration") if lavalink_track else None) or duration
        final_thumb = (lavalink_track.get("thumb_url") if lavalink_track else None) or thumb_url

        if not lavalink_track:
            lavalink_track = {
                "title": final_title,
                "author": final_author,
                "duration": final_dur,
                "thumb_url": final_thumb,
                "uri": target_url,
                "encoded": track_info.get("encoded") or ""
            }
        encoded = lavalink_track.get("encoded") or None

        try:
            # 1) Bat Fake Discord Voice Gateway (WS noi bo + UDP hung Opus)
            gateway = FakeVoiceGateway.instance()
            await gateway.start()
            # Tao san nguon Opus de KHONG mat khung nao khi Lavalink phat qua nhanh
            opus_source = OpusGatewaySource(gateway, guild_id)

            # 2) Bot THAT SU vao Voice bang VoiceClient chuan (du DAVE/E2EE)
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

            # 3) Doi Discord cap token + session_id cho bot user
            token, session_id = await wait_voice_credentials(vc, timeout=25.0)
            if not token:
                await self.reply_text(
                    ctx.message, "❌ Không nhận được voice credentials từ Discord.", delay=25
                )
                return
            # 4) Day credentials (endpoint GIA) + track sang Lavalink
            play_ok = await forward_voice_to_lavalink(
                self.bot, guild_id, token, session_id, channel.id,
                encoded=encoded, volume=100,
            )
            if not play_ok:
                await self.reply_text(
                    ctx.message,
                    f"❌ Không thể phát track SoundCloud: **{final_title}**",
                    delay=20,
                )
                return

            # 5) Nghe Opus tu gateway va phat lai (KHONG ma hoa lai -> nhe CPU)
            try:
                if vc.is_playing():
                    vc.stop()
            except Exception:
                pass
            vc.play(opus_source)

            self.current_track[guild_id] = {
                "title": final_title,
                "author": final_author,
                "duration": final_dur,
                "thumb_url": final_thumb,
                "channel": channel.name
            }
            await self._send_nowplaying(ctx, final_title, final_author, final_dur, final_thumb, channel)
            _log(f"[SCL PLAY OK] '{final_title}' dang phat qua Fake Voice Gateway trong: {channel.name}")

        except Exception as e:
            err_msg = str(e)
            print(f"[SoundCloud Play Voice Error] {err_msg}", flush=True)
            await self.reply_text(ctx.message, f"❌ Lỗi phát voice SoundCloud: {err_msg[:100]}", delay=20)

    async def _send_nowplaying(self, ctx, title: str, artist: str, duration: str, thumb: str, channel, engine: str = "Lavalink V4 -> Fake Voice Gateway"):
        """Gui DUY NHAT 1 Card NowPlaying SoundCloud."""
        card_file = None
        try:
            card_buf = await async_nowplaying_card(
                "soundcloud", title, artist, duration or "", thumb or "",
                channel_name=channel.name, engine=engine,
            )
            if card_buf:
                card_file = discord.File(card_buf, filename="nowplaying.png")
        except Exception as ce:
            _log(f"[Card render err] {ce}")

        caption = (
            f"☁️ **[SoundCloud] Đang phát:** **{title}**\n"
            f"👤 {artist} | 📍 {channel.name}\n"
            f"🛡️ Engine: `{engine}`\n"
            f"*Gõ `(prefix)scl stop` để dừng.*"
        )
        try:
            try:
                from apps.user_discord.utils.autorep import autorep
            except ImportError:
                from utils.autorep import autorep
            from apps.user_discord.utils.prefix import fmt as _pfx_fmt
            caption = _pfx_fmt(self.bot, caption)
            return await autorep(ctx.message, content=caption, file=card_file, auto_delete_delay=None)
        except Exception:
            return None

    async def download_and_send_audio(self, ctx, title: str, artist: str, track_url: str):
        """Tải file MP3 từ SoundCloud bằng yt-dlp và gửi lên Discord. Gửi xong KHÔNG xóa tin nhắn bot và xóa file đĩa."""
        clean_title = re.sub(r'[^\w\s-]', '', title)[:30].strip() or "track"
        local_path = os.path.join(self.temp_dir, f"scl_{int(asyncio.get_event_loop().time())}_{clean_title}.mp3")

        loop = asyncio.get_event_loop()
        def _dl():
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': local_path,
                'quiet': True,
                'no_warnings': True,
                'max_filesize': 25 * 1024 * 1024,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([track_url])
            return os.path.exists(local_path)

        try:
            ok = await loop.run_in_executor(None, _dl)
            if ok and os.path.getsize(local_path) <= 25 * 1024 * 1024:
                with open(local_path, "rb") as f:
                    file = discord.File(fp=f, filename=f"{clean_title}.mp3")
                    caption = f"🎵 **{title}**\n👤 Nghệ sĩ: **{artist}**\n🔗 {track_url}"
                    try:
                        from apps.user_discord.utils.autorep import autorep
                    except ImportError:
                        from utils.autorep import autorep
                    await autorep(ctx.message, content=caption, file=file, auto_delete_delay=None)
            else:
                await self.reply_text(ctx.message, f"⚠️ Không thể tải file hoặc vượt quá 25MB.\n🔗 Nghe trực tiếp: {track_url}", delay=None)

        except Exception as e:
            await self.reply_text(ctx.message, f"❌ Lỗi tải bài hát SoundCloud: {str(e)[:100]}", delay=20)
        finally:
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except Exception:
                    pass

    @menu_entry("MEDIA & ENTERTAINMENT", "scl", "Nghe nhạc SoundCloud lossless & tải MP3",
                icon_sym="☁", icon_color=(255, 140, 50), order=3)
    @alias_declare("soundcloud", main="soundcloud", subs=["scl"])
    @commands.group(name="soundcloud", aliases=["scl"], invoke_without_command=True)
    async def cmd_soundcloud(self, ctx, *, query: str = None):
        """Tìm kiếm, phát Voice hoặc tải nhạc SoundCloud (Gửi ảnh Card chọn 1-20)."""
        if not query:
            try:
                from apps.user_discord.utils.prefix import get_prefix
            except ImportError:
                from utils.prefix import get_prefix
            pfx = get_prefix(self.bot)
            card_buf = await async_help_card("soundcloud", pfx)
            if card_buf:
                card_file = discord.File(card_buf, filename="scl_guide.png")
                try:
                    from apps.user_discord.utils.autorep import autorep
                except ImportError:
                    from utils.autorep import autorep
                await autorep(ctx.message, content="☁️ **HƯỚNG DẪN SỬ DỤNG LỆNH SOUNDCLOUD**", file=card_file, auto_delete_delay=60)
            else:
                await self.reply_text(ctx.message, f"❌ Cú pháp: `{pfx}scl <tên bài hát>` | `{pfx}scl stop`", delay=30)
            return

        # Hỗ trợ link SoundCloud trực tiếp
        if "soundcloud.com" in query:
            parts = query.split()
            link = parts[0]
            explicit_mode = None
            if len(parts) > 1:
                last_arg = parts[-1].lower()
                if last_arg in ["v", "voice", "play", "am"]:
                    explicit_mode = "voice"
                elif last_arg in ["f", "file", "mp3", "audio", "down", "dl"]:
                    explicit_mode = "file"

            mode = explicit_mode
            if not mode:
                if ctx.author.voice and ctx.author.voice.channel:
                    ask_txt = (
                        f"☁️ **Đã nhận link SoundCloud! Bạn muốn làm gì?**\n"
                        f"👉 Gõ `v` để **Phát nhạc vào Voice** 🔊\n"
                        f"👉 Gõ `f` để **Tải File MP3** 📥\n"
                        f"*(Hoặc gõ `c` để hủy. Mặc định tải file sau 20s)*"
                    )
                    ask_msg = await self.reply_text(ctx.message, ask_txt, delay=25)
                    def check_choice(m):
                        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
                    try:
                        resp_msg = await self.bot.wait_for("message", check=check_choice, timeout=20.0)
                        resp_val = resp_msg.content.strip().lower()
                        if resp_val in ["c", "cancel", "huy"]:
                            await self.reply_text(resp_msg, "❌ Đã hủy xử lý link SoundCloud.", delay=15)
                            return
                        elif resp_val in ["v", "voice", "play", "am", "1"]:
                            mode = "voice"
                        elif resp_val in ["f", "file", "mp3", "audio", "down", "dl", "2"]:
                            mode = "file"
                        else:
                            mode = "file"
                    except asyncio.TimeoutError:
                        mode = "file"
                else:
                    mode = "file"

            from apps.user_discord.utils.lavalink_voice import LavalinkManager
            mgr = LavalinkManager.get_instance(self.bot)
            resolved = await mgr.search(link, limit=1) if mgr else []
            if resolved:
                chosen_track = resolved[0]
                if mode == "voice":
                    await self.play_in_voice(ctx, chosen_track)
                else:
                    await self.reply_text(ctx.message, f"⏳ Đang tải file MP3: **{chosen_track.get('title')}**...", delay=15)
                    await self.download_and_send_audio(ctx, chosen_track.get("title", "Track"), chosen_track.get("author", "Artist"), link)
            else:
                await self.reply_text(ctx.message, "❌ Không thể tải link SoundCloud này qua Lavalink.", delay=20)
            return

        status = await self.reply_text(ctx.message, f"🔍 Đang tìm kiếm SoundCloud: **{query}**...", delay=15)
        tracks = await self.search_tracks(query, 20)

        if not tracks:
            await self.reply_text(ctx.message, "❌ Không tìm thấy bài hát SoundCloud nào phù hợp.", delay=30)
            return

        # Chuẩn bị dữ liệu để render Card ảnh
        items_gui = []
        for t in tracks:
            items_gui.append({
                "title": t.get("title", "SoundCloud Track"),
                "author": t.get("author", "Artist"),
                "duration": t.get("duration", "0:00"),
                "thumb_url": t.get("thumb_url", ""),
            })

        selector_file = None
        try:
            card_buf = await async_search_card("soundcloud", query, items_gui)
            if card_buf:
                selector_file = discord.File(card_buf, filename="scl_search.png")
        except Exception:
            pass

        if not selector_file:
            selector_file = await render_media_selector("SOUNDCLOUD", query, items_gui)

        prompt_txt = f"📋 Hãy gõ số `1` - `{len(tracks)}` (hoặc kèm `v` để vào Voice, `f` để gửi File MP3, vd `1 v` / `1 f`):"
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
                await self.reply_text(choice_msg, "❌ Đã hủy lựa chọn SoundCloud.", delay=15)
                return

            m_choice = re.match(r'^(\d+)(?:\s*([a-zA-Z]+))?$', val)
            if not m_choice:
                return

            choice_idx = int(m_choice.group(1))
            if not (1 <= choice_idx <= len(tracks)):
                await self.reply_text(choice_msg, f"❌ Số thứ tự không hợp lệ. Vui lòng chọn từ `1` đến `{len(tracks)}`.", delay=15)
                return

            chosen_track = tracks[choice_idx - 1]
            title = chosen_track.get("title", "Track")
            author = chosen_track.get("author", "Artist")
            track_url = chosen_track.get("uri", "")

            req_suffix = (m_choice.group(2) or "").lower()
            mode = None
            if req_suffix in ["v", "voice", "play", "am"]:
                mode = "voice"
            elif req_suffix in ["f", "file", "mp3", "audio", "down", "dl"]:
                mode = "file"
            else:
                # User chỉ gõ số mà không kèm v hay f: Hỏi user muốn voice hay file
                ask_menu = (
                    f"☁️ **Bạn đã chọn bài #{choice_idx}:** *{title[:50]}*\n"
                    f"👉 Gõ `v` để **Phát nhạc vào Voice** 🔊\n"
                    f"👉 Gõ `f` để **Tải File Nhạc MP3** 📥\n"
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
                    elif m_val in ["f", "file", "mp3", "audio", "down", "dl", "2"]:
                        mode = "file"
                    else:
                        mode = "voice" if (ctx.author.voice and ctx.author.voice.channel) else "file"
                except asyncio.TimeoutError:
                    mode = "voice" if (ctx.author.voice and ctx.author.voice.channel) else "file"

            if mode == "file":
                await self.reply_text(choice_msg, f"⏳ Đang tải nhạc MP3: **{title}**...", delay=15)
                await self.download_and_send_audio(ctx, title, author, track_url)
            else:
                await self.play_in_voice(ctx, chosen_track)

        except asyncio.TimeoutError:
            pass

    @cmd_soundcloud.command(name="now", aliases=["np"])
    async def scl_now(self, ctx):
        """Hien thi bai hat SoundCloud hien tai: (prefix)scl now"""
        track = self.current_track.get(ctx.guild.id)
        vc = ctx.guild.voice_client if ctx.guild else None
        if not track or not vc:
            return await self.reply_text(ctx.message, "❌ Hiện không có bài hát nào đang phát.", delay=15)

        channel = getattr(vc, "channel", None)
        if not channel and ctx.author.voice:
            channel = ctx.author.voice.channel
        if not channel:
            return await self.reply_text(ctx.message, "❌ Hiện không có bài hát nào đang phát.", delay=15)

        await self._send_nowplaying(
            ctx,
            track.get("title", "Unknown"),
            track.get("author", "SoundCloud"),
            track.get("duration", ""),
            track.get("thumb_url", ""),
            channel,
        )

    @cmd_soundcloud.command(name="stop", aliases=["leave", "dc", "offvoice"])
    async def scl_stop(self, ctx):
        """Dừng phát âm thanh SoundCloud và rời Voice: (prefix)scl stop"""
        await self._do_stop(ctx)

async def setup(bot):
    await bot.add_cog(SoundCloudModule(bot))
