# -*- coding: utf-8 -*-
"""
MODULE: extract (Tách Âm Thanh / Nhạc Khỏi Video)
- Lệnh chính: (prefix)tachnhac, (prefix)mp3, (prefix)audio, (prefix)extract, (prefix)tachamthanh
- Hỗ trợ đa năng:
  • Reply vào tin nhắn có đính kèm video hoặc link video rồi gõ: (prefix)tachnhac
  • Đính kèm trực tiếp file video khi gửi lệnh: (prefix)tachnhac
  • Nhập link video mạng xã hội (TikTok, FB, IG, X, Threads, YouTube, direct MP4):
    (prefix)tachnhac <link>
  • Gõ thêm 'v' hoặc 'voice' để phát trực tiếp âm thanh vừa tách vào phòng Voice!
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import shutil
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
TEMP_AUDIO_DIR = BASE_DIR / "data" / "audio_extract"
TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


class ExtractModule(commands.Cog, name="AudioExtract"):
    """Module trích xuất âm thanh MP3 từ video chất lượng cao kèm thẻ Liquid Glass."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.temp_dir = TEMP_AUDIO_DIR
        self._find_ffmpeg()

    def _find_ffmpeg(self) -> str:
        f = shutil.which("ffmpeg")
        if f:
            return f
        # Fallback các đường dẫn phổ biến
        common_paths = [
            "/usr/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            r"C:\Users\BinhMinh\Downloads\ffmpeg-2026-06-10-git-b29bdd3715-essentials_build\ffmpeg-2026-06-10-git-b29bdd3715-essentials_build\bin\ffmpeg.EXE",
        ]
        for p in common_paths:
            if os.path.exists(p):
                return p
        return "ffmpeg"

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return "."

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    def _format_duration(self, seconds: float) -> str:
        sec = int(seconds)
        m = sec // 60
        s = sec % 60
        return f"{m:02d}:{s:02d}"

    # ── TRÍCH XUẤT TỪ FILE ĐÍNH KÈM HOẶC DIRECT URL ────────────────────────
    def _extract_from_video_file(self, in_path: str, out_path: str) -> bool:
        ffmpeg_bin = self._find_ffmpeg()
        cmd = [
            ffmpeg_bin,
            "-nostdin",
            "-y",
            "-i", in_path,
            "-vn",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            out_path
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
            return res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0
        except Exception:
            return False

    # ── TRÍCH XUẤT TỪ LINK MẠNG XÃ HỘI (YT-DLP) ───────────────────────────
    def _extract_from_web_url(self, url: str, stamp: str) -> Optional[Tuple[str, str, float]]:
        out_tmpl = str(self.temp_dir / f"extracted_{stamp}_%(id)s.%(ext)s")
        ffmpeg_bin = self._find_ffmpeg()
        ffmpeg_dir = os.path.dirname(ffmpeg_bin) if os.path.isabs(ffmpeg_bin) else None

        opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "outtmpl": out_tmpl,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "postprocessor_args": ["-ar", "44100", "-ac", "2"],
            "retries": 2,
        }
        if ffmpeg_dir:
            opts["ffmpeg_location"] = ffmpeg_dir

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info and "entries" in info:
                    info = next((e for e in info["entries"] if e), None)
                if not info:
                    return None

                title = info.get("title", "Audio Track")
                duration = float(info.get("duration", 0))

                # Tìm file mp3 đã render
                cands = list(self.temp_dir.glob(f"extracted_{stamp}_*.mp3"))
                if cands:
                    cand = sorted(cands, key=lambda p: p.stat().st_size, reverse=True)[0]
                    return str(cand), title, duration
        except Exception:
            pass
        return None

    # ── RENDER LIQUID GLASS AUDIO CARD ──────────────────────────────────────
    def _render_audio_card(self, title: str, size_str: str, dur_str: str, source_type: str) -> io.BytesIO:
        if G is None:
            raise RuntimeError("Thư viện Liquid Glass không khả dụng.")

        LW, LH = 960, 440
        pad = 20
        head_h = 70
        gap = 14
        cv = G.GlassCanvas(LW, LH, scale=2, out=1.35)
        pfx = self._pfx()

        cv.header(
            pad, pad, LW - pad, head_h,
            "AUDIO EXTRACTION - MP3 192KBPS",
            f"Prefix {pfx}   •   Trich xuat am thanh High-Definition   •   Format: Stereo 44.1kHz",
            tag="AUDIO TOOL",
            right_reserve=160
        )
        cv.pill(LW - pad - 16, pad + head_h / 2 - 14, "PRO AUDIO", cv.font("b", 12), G.G_PURPLE, h=24, align="r")

        top = pad + head_h + gap
        box1_h = 130
        cv.glass((pad, top, LW - pad, top + box1_h), 18, blur=24, tint=(18, 14, 34, 100))
        cv.grad((pad + 4, top + 14, pad + 8, top + box1_h - 14), 2, (168, 85, 247), (236, 72, 153))

        # Big Audio Icon / Letter
        cv.circle_image(None, pad + 24, top + 24, 60, ring=G.G_PURPLE, letter="MP3", fill=(32, 20, 52))

        cv.text(pad + 104, top + 38, cv.fit(title, cv.font("b", 18), LW - pad - 140), cv.font("b", 18), G.C_TEXT, vcenter=True)
        cv.text(pad + 104, top + 64, f"Nguon: {source_type}   •   Engine: FFmpeg LAME MP3", cv.font("r", 12), G.C_MUTED, vcenter=True)

        cv.pill(pad + 104, top + 92, "🎵 192 KBPS STEREO", cv.font("b", 11), G.G_AMBER, h=22, padx=10)

        # 4 Stat Capsules
        top2 = top + box1_h + gap
        bottom = LH - pad - 30
        capsules = [
            ("Dung Lượng MP3", size_str, (16, 185, 129)),
            ("Thời Lượng", dur_str if dur_str else "N/A", (56, 189, 248)),
            ("Tần Số Lấy Mẫu", "44.1 kHz", (251, 191, 36)),
            ("Bộ Mã Hóa (Codec)", "libmp3lame", G.C_TEXT),
        ]
        cap_w = (LW - 2 * pad - 3 * gap) / 4

        for i, (lbl, val, col) in enumerate(capsules):
            cx1 = pad + i * (cap_w + gap)
            cx2 = cx1 + cap_w
            cv.glass((cx1, top2, cx2, bottom), 14, blur=16, tint=(22, 18, 38, 85))
            cv.text((cx1 + cx2) / 2, top2 + 22, lbl, cv.font("r", 12), G.C_MUTED, align="c", vcenter=True)
            cv.text((cx1 + cx2) / 2, top2 + 52, val, cv.font("b", 16), col, align="c", vcenter=True)

        # Footer
        cv.text(
            pad + 10, LH - pad - 10,
            "Ho tro reply video, dinh kem file hoac link TikTok, YouTube, FB, IG, X, Threads",
            cv.font("r", 11), G.C_DIM, vcenter=True
        )

        return cv.finalize()

    # ── LỆNH CHÍNH (PREFIX)TACHNHAC / MP3 / AUDIO ──────────────────────────
    @menu_entry("MEDIA & ENTERTAINMENT", "tachnhac", "Tach am thanh MP3 tu video (reply, file, link)",
                badge="NEW", icon_sym="🎵", icon_color=(168, 85, 247), order=7)
    @alias_declare("tachnhac", ["mp3", "audio", "extract", "tachamthanh"])
    @commands.group(
        name="tachnhac",
        aliases=["mp3", "audio", "extract", "tachamthanh"],
        invoke_without_command=True,
        help="Trich xuat am thanh MP3 chat luong cao tu video clip bat ky."
    )
    async def cmd_extract(self, ctx: commands.Context, *, arg: Optional[str] = None):
        """Tách âm thanh MP3 từ video: (prefix)tachnhac [link / reply / đính kèm video]"""
        pfx = self._pfx()

        target_url = None
        target_filename = "video_audio.mp3"
        is_direct_file = False
        play_to_voice = False

        if arg and ("voice" in arg.lower() or " v" in arg.lower() or arg.strip().lower() == "v"):
            play_to_voice = True
            # Lọc bỏ từ khóa voice khỏi arg
            arg = re.sub(r'\b(voice|v)\b', '', arg, flags=re.IGNORECASE).strip()

        # 1. Kiểm tra File Đính Kèm Trong Tin Nhắn Hiện Tại
        if ctx.message.attachments:
            att = ctx.message.attachments[0]
            if any(att.filename.lower().endswith(ext) for ext in [".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".3gp"]):
                target_url = att.url
                target_filename = Path(att.filename).stem + ".mp3"
                is_direct_file = True

        # 2. Kiểm tra Tin Nhắn Được Reply
        if not target_url and ctx.message.reference and ctx.message.reference.message_id:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if ref_msg.attachments:
                    for att in ref_msg.attachments:
                        if any(att.filename.lower().endswith(ext) for ext in [".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".3gp"]):
                            target_url = att.url
                            target_filename = Path(att.filename).stem + ".mp3"
                            is_direct_file = True
                            break
                if not target_url and ref_msg.content:
                    found_links = re.findall(r'https?://[^\s]+', ref_msg.content)
                    if found_links:
                        target_url = found_links[0]
            except Exception:
                pass

        # 3. Kiểm tra Link Trong Tham Số Truyền Vào
        if not target_url and arg:
            found_links = re.findall(r'https?://[^\s]+', arg)
            if found_links:
                target_url = found_links[0]

        # 4. Nếu Vẫn Chưa Có Gì -> Xuất Help Card Liquid Glass
        if not target_url:
            card_buf = await async_help_card("tachnhac", pfx)
            if card_buf:
                card_file = discord.File(card_buf, filename="tachnhac_guide.png")
                await autorep(
                    ctx.message,
                    content="🎵 **HƯỚNG DẪN TÁCH ÂM THANH MP3 TỪ VIDEO**",
                    file=card_file,
                    auto_delete_delay=60
                )
            else:
                msg = await autorep(
                    ctx.message,
                    f"🎵 **HƯỚNG DẪN TÁCH NHẠC / ÂM THANH TỪ VIDEO**\n"
                    f"👉 **Cách 1:** Reply vào tin nhắn video rồi gõ `{pfx}tachnhac`\n"
                    f"👉 **Cách 2:** Đính kèm video khi gửi lệnh `{pfx}tachnhac`\n"
                    f"👉 **Cách 3:** Dán link video: `{pfx}tachnhac <link TikTok/FB/IG/X/YouTube>`\n"
                    f"💡 Thêm `v` vào cuối lệnh để phát trực tiếp âm thanh vào phòng Voice!"
                )
                autodelet(msg, delay=30)
            return

        waiting = await autorep(ctx.message, "⏳ Đang tải và trích xuất âm thanh MP3 192kbps từ video...")
        autodelet(waiting, delay=15)

        stamp = str(int(time.time() * 1000))
        loop = asyncio.get_running_loop()
        extracted_mp3_path = None
        video_title = "Audio Track"
        duration_sec = 0.0

        try:
            if is_direct_file:
                # Tải file video về rồi convert bằng ffmpeg
                in_ext = os.path.splitext(urllib.parse.urlparse(target_url).path)[-1] or ".mp4"
                tmp_video = str(self.temp_dir / f"in_{stamp}{in_ext}")
                tmp_out_mp3 = str(self.temp_dir / f"out_{stamp}.mp3")

                r = requests.get(target_url, stream=True, timeout=30)
                if r.status_code == 200:
                    with open(tmp_video, "wb") as f:
                        for chunk in r.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)

                    ok = await loop.run_in_executor(None, self._extract_from_video_file, tmp_video, tmp_out_mp3)
                    if ok:
                        extracted_mp3_path = tmp_out_mp3
                        video_title = target_filename.replace(".mp3", "")

                    if os.path.exists(tmp_video):
                        try:
                            os.remove(tmp_video)
                        except Exception:
                            pass
            else:
                # Trích xuất qua yt-dlp
                res = await loop.run_in_executor(None, self._extract_from_web_url, target_url, stamp)
                if res:
                    extracted_mp3_path, video_title, duration_sec = res

            if not extracted_mp3_path or not os.path.exists(extracted_mp3_path):
                msg = await autorep(
                    ctx.message,
                    "❌ Không thể trích xuất âm thanh từ video này (định dạng không hỗ trợ hoặc link bị giới hạn)."
                )
                autodelet(msg, delay=20)
                return

            file_size = os.path.getsize(extracted_mp3_path)
            size_str = self._format_size(file_size)
            dur_str = self._format_duration(duration_sec) if duration_sec > 0 else "00:00"

            # Render Thẻ Liquid Glass
            source_lbl = "Video Attachment" if is_direct_file else "Web Video Link"
            card_buf = await loop.run_in_executor(
                None, self._render_audio_card, video_title, size_str, dur_str, source_lbl
            )

            safe_title = re.sub(r'[^\w\-_]', '_', video_title)[:40]
            audio_file = discord.File(extracted_mp3_path, filename=f"{safe_title}.mp3")

            caption = (
                f"🎵 **ĐÃ TRÍCH XUẤT ÂM THANH THÀNH CÔNG!**\n"
                f"🎧 Tiêu đề: **{video_title}**\n"
                f"📦 Định dạng: **MP3 192kbps (Stereo)**   |   Dung lượng: **{size_str}**"
            )

            # Gửi cả Card và File MP3 (tự động xóa sau 120s)
            sent = await autorep(ctx.message, content=caption, files=[card_file, audio_file], auto_delete_delay=120)
            autodelet(sent, delay=120)

            # BONUS: Nếu user yêu cầu phát Voice hoặc đang ở Voice
            if play_to_voice and ctx.author.voice and ctx.author.voice.channel:
                try:
                    vc = ctx.voice_client
                    if not vc or not vc.is_connected():
                        vc = await ctx.author.voice.channel.connect()
                    if vc.is_playing():
                        vc.stop()
                    ffmpeg_bin = self._find_ffmpeg()
                    source = discord.FFmpegPCMAudio(
                        extracted_mp3_path,
                        executable=ffmpeg_bin,
                        options="-vn -ar 48000 -ac 2 -b:a 192k"
                    )
                    vc.play(source)
                    v_msg = await autorep(ctx.message, f"🔊 Đang phát âm thanh vừa tách vào kênh Voice **{ctx.author.voice.channel.name}**!")
                    autodelet(v_msg, delay=15)
                except Exception as e:
                    pass

        except Exception as e:
            err_msg = await autorep(ctx.message, f"❌ Lỗi xử lý âm thanh: {str(e)[:150]}")
            autodelet(err_msg, delay=20)


async def setup(bot: commands.Bot):
    await bot.add_cog(ExtractModule(bot))
