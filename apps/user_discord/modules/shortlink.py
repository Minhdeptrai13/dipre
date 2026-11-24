# -*- coding: utf-8 -*-
"""
MODULE: shortlink (Rút Gọn Link & Giải Mã Soi Link Ẩn)
- Lệnh chính:
  • (prefix)short <link> : Rút gọn đường link dài qua TinyURL & is.gd.
  • (prefix)unshort <link> : Giải mã link rút gọn, soi đích đến thực sự & cảnh báo link bẫy/IP logger.
* Hỗ trợ dán link trực tiếp hoặc reply vào tin nhắn có link!
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord.ext import commands
import requests

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

SUSPICIOUS_DOMAINS = [
    "grabify.link", "iplogger.org", "2no.co", "yip.su", "iplogger.com",
    "iplogger.ru", "ezstat.ru", "whatsmyserp.com", "ps3cfw.com"
]


class ShortlinkModule(commands.Cog, name="Shortlink"):
    """Module rút gọn link và soi link ẩn, giải mã unshorten chống link lừa đảo/IP logger."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        })

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return "."

    def _extract_url(self, ctx: commands.Context, text: Optional[str]) -> Optional[str]:
        # 1. Tìm trong text truyền vào
        if text:
            links = re.findall(r'https?://[^\s]+', text)
            if links:
                return links[0]

        # 2. Tìm trong reply tin nhắn
        if ctx.message.reference and ctx.message.reference.message_id:
            try:
                # Không await trực tiếp ở sync, dùng trong async context
                pass
            except Exception:
                pass
        return None

    # ── RÚT GỌN LINK QUA TINYURL / IS.GD ──────────────────────────────────
    def _create_short_link(self, long_url: str) -> Optional[Tuple[str, str]]:
        """Trả về (short_url, provider)"""
        q = urllib.parse.quote(long_url)
        # Thử is.gd trước
        try:
            r = self.session.get(f"https://is.gd/create.php?format=simple&url={q}", timeout=5)
            if r.status_code == 200 and r.text.startswith("https://"):
                return r.text.strip(), "is.gd"
        except Exception:
            pass

        # Fallback sang TinyURL
        try:
            r = self.session.get(f"https://tinyurl.com/api-create.php?url={q}", timeout=5)
            if r.status_code == 200 and r.text.startswith("https://"):
                return r.text.strip(), "TinyURL"
        except Exception:
            pass

        return None

    # ── SOI LINK ẨN (UNSHORTEN) ───────────────────────────────────────────
    def _trace_unshorten(self, short_url: str) -> Dict[str, Any]:
        hops = [short_url]
        current_url = short_url
        status_code = 200

        try:
            # Lần theo redirect tối đa 10 hops
            for _ in range(10):
                res = self.session.head(current_url, allow_redirects=False, timeout=6)
                status_code = res.status_code
                if status_code in (301, 302, 303, 307, 308) and "Location" in res.headers:
                    next_url = res.headers["Location"]
                    if not next_url.startswith("http"):
                        next_url = urllib.parse.urljoin(current_url, next_url)
                    current_url = next_url
                    hops.append(current_url)
                else:
                    break
        except Exception:
            try:
                # Fallback dùng GET theo redirect
                res2 = self.session.get(short_url, allow_redirects=True, timeout=8)
                current_url = res2.url
                status_code = res2.status_code
                if current_url not in hops:
                    hops.append(current_url)
            except Exception:
                pass

        final_url = current_url
        domain = urllib.parse.urlparse(final_url).netloc.lower()

        # Kiểm tra nghi vấn IP logger / lừa đảo
        is_suspicious = any(s in domain for s in SUSPICIOUS_DOMAINS)

        return {
            "initial": short_url,
            "final": final_url,
            "domain": domain,
            "hops_count": len(hops) - 1,
            "hops": hops,
            "status_code": status_code,
            "is_suspicious": is_suspicious
        }

    # ── RENDER LIQUID GLASS SHORT LINK CARD ───────────────────────────────
    def _render_short_card(self, long_url: str, short_url: str, provider: str) -> io.BytesIO:
        if G is None:
            raise RuntimeError("Thư viện Liquid Glass không khả dụng.")

        LW, LH = 960, 440
        pad = 20
        head_h = 70
        gap = 14
        cv = G.GlassCanvas(LW, LH, scale=2, out=1.35)
        pfx = self._pfx()

        orig_len = len(long_url)
        short_len = len(short_url)
        saved_pct = max(0, int((1 - short_len / orig_len) * 100)) if orig_len > short_len else 0

        cv.header(
            pad, pad, LW - pad, head_h,
            "URL SHORTENER - LINK CONDENSER",
            f"Prefix {pfx}   •   Rút gọn đường dẫn siêu tốc   •   Máy chủ: {provider}",
            tag="LINK STUDIO",
            right_reserve=160
        )
        cv.pill(LW - pad - 16, pad + head_h / 2 - 14, f"-{saved_pct}% LENGTH", cv.font("b", 12), G.G_GREEN, h=24, align="r")

        top = pad + head_h + gap
        box1_h = 135
        cv.glass((pad, top, LW - pad, top + box1_h), 18, blur=24, tint=(16, 24, 38, 100))
        cv.grad((pad + 4, top + 14, pad + 8, top + box1_h - 14), 2, (14, 165, 233), (99, 102, 241))

        cv.circle_image(None, pad + 24, top + 22, 68, ring=G.G_BLUE, letter="URL", fill=(20, 32, 48))

        cv.text(pad + 114, top + 34, "ĐƯỜNG LINK RÚT GỌN MỚI:", cv.font("r", 12), G.C_MUTED, vcenter=True)
        cv.text(pad + 114, top + 64, short_url, cv.font("b", 22), G.C_GOLD, vcenter=True)
        cv.text(pad + 114, top + 98, cv.fit(f"Gốc: {long_url}", cv.font("r", 12), LW - pad - 140), cv.font("r", 12), G.C_DIM, vcenter=True)

        # 4 Stat Capsules
        top2 = top + box1_h + gap
        bottom = LH - pad - 24
        capsules = [
            ("Độ Dài Ban Đầu", f"{orig_len} ký tự", G.C_TEXT),
            ("Độ Dài Sau Rút Gọn", f"{short_len} ký tự", (16, 185, 129)),
            ("Tỉ Lệ Tiết Kiệm", f"Giảm {saved_pct}%", (251, 191, 36)),
            ("Nhà Cung Cấp", provider, (56, 189, 248)),
        ]
        cap_w = (LW - 2 * pad - 3 * gap) / 4

        for i, (lbl, val, col) in enumerate(capsules):
            cx1 = pad + i * (cap_w + gap)
            cx2 = cx1 + cap_w
            cv.glass((cx1, top2, cx2, bottom), 14, blur=16, tint=(18, 22, 38, 85))
            cv.text((cx1 + cx2) / 2, top2 + 22, lbl, cv.font("r", 12), G.C_MUTED, align="c", vcenter=True)
            cv.text((cx1 + cx2) / 2, top2 + 52, val, cv.font("b", 16), col, align="c", vcenter=True)

        return cv.finalize()

    # ── RENDER LIQUID GLASS UNSHORTEN CARD ─────────────────────────────────
    def _render_unshort_card(self, d: Dict[str, Any]) -> io.BytesIO:
        if G is None:
            raise RuntimeError("Thư viện Liquid Glass không khả dụng.")

        LW, LH = 960, 480
        pad = 20
        head_h = 70
        gap = 14
        cv = G.GlassCanvas(LW, LH, scale=2, out=1.35)
        pfx = self._pfx()

        is_bad = d["is_suspicious"]
        accent_col = (239, 68, 68) if is_bad else (16, 185, 129)
        grad = G.G_RED if is_bad else G.G_GREEN
        tag_status = "CẢNH BÁO IP LOGGER / NGUY HIỂM" if is_bad else "AN TOÀN / ĐÃ XÁC MINH"

        cv.header(
            pad, pad, LW - pad, head_h,
            "UNSHORTEN - GIẢI MÃ ĐÍCH ĐẾN LINK ẨN",
            f"Prefix {pfx}   •   Lần theo chuỗi chuyển hướng HTTP   •   {d['hops_count']} Hops",
            tag="SECURITY RADAR",
            right_reserve=160
        )
        cv.pill(LW - pad - 16, pad + head_h / 2 - 14, "UNMASKED", cv.font("b", 12), grad, h=24, align="r")

        top = pad + head_h + gap
        box1_h = 145
        cv.glass((pad, top, LW - pad, top + box1_h), 18, blur=24, tint=(18, 22, 36, 100))
        cv.grad((pad + 4, top + 14, pad + 8, top + box1_h - 14), 2, accent_col,
                tuple(max(0, int(v * 0.5)) for v in accent_col))

        letter = "WARN" if is_bad else "SAFE"
        cv.circle_image(None, pad + 24, top + 24, 68, ring=grad, letter=letter, fill=(32, 20, 24) if is_bad else (20, 36, 32))

        cv.text(pad + 114, top + 34, tag_status, cv.font("b", 15), accent_col, vcenter=True)
        cv.text(pad + 114, top + 64, cv.fit(f"Đích đến: {d['final']}", cv.font("b", 18), LW - pad - 140), cv.font("b", 18), G.C_GOLD, vcenter=True)
        cv.text(pad + 114, top + 98, cv.fit(f"Link đầu vào: {d['initial']}", cv.font("r", 12), LW - pad - 140), cv.font("r", 12), G.C_MUTED, vcenter=True)
        cv.text(pad + 114, top + 124, f"Tên miền đích: {d['domain']}   •   Mã phản hồi HTTP: {d['status_code']}", cv.font("r", 11), G.C_DIM, vcenter=True)

        # 4 Stat Capsules
        top2 = top + box1_h + gap
        bottom = LH - pad - 24
        capsules = [
            ("Số Bước Chuyển Hướng", f"{d['hops_count']} lần (Hops)", (56, 189, 248)),
            ("Tên Miền Đích", cv.fit(d["domain"], cv.font("b", 14), 180), G.C_TEXT),
            ("Đánh Giá An Toàn", "NGUY HIỂM" if is_bad else "Bình thường", accent_col),
            ("Giao Thức", "HTTPS" if d["final"].startswith("https") else "HTTP", (251, 191, 36)),
        ]
        cap_w = (LW - 2 * pad - 3 * gap) / 4

        for i, (lbl, val, col) in enumerate(capsules):
            cx1 = pad + i * (cap_w + gap)
            cx2 = cx1 + cap_w
            cv.glass((cx1, top2, cx2, bottom), 14, blur=16, tint=(18, 22, 38, 85))
            cv.text((cx1 + cx2) / 2, top2 + 22, lbl, cv.font("r", 12), G.C_MUTED, align="c", vcenter=True)
            cv.text((cx1 + cx2) / 2, top2 + 52, val, cv.font("b", 15), col, align="c", vcenter=True)

        return cv.finalize()

    # ── LỆNH CHÍNH (PREFIX)SHORT / SHORTLINK / RUTGON ──────────────────────
    @menu_entry("AI & TIỆN ÍCH", "short", "Rut gon link dai thanh link ngan sieu toc",
                badge="NEW", icon_sym="🔗", icon_color=(14, 165, 233), order=9)
    @alias_declare("short", ["shortlink", "rutgon"])
    @commands.command(
        name="short",
        aliases=["shortlink", "rutgon"],
        help="Rut gon duong dan web dai thanh link ngan."
    )
    async def cmd_short(self, ctx: commands.Context, *, url_arg: Optional[str] = None):
        """Rút gọn link: (prefix)short <link> (hoặc reply link)"""
        pfx = self._pfx()

        # Kiểm tra reply nếu không truyền tham số
        target_url = None
        if url_arg:
            links = re.findall(r'https?://[^\s]+', url_arg)
            if links:
                target_url = links[0]

        if not target_url and ctx.message.reference and ctx.message.reference.message_id:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if ref_msg.content:
                    links = re.findall(r'https?://[^\s]+', ref_msg.content)
                    if links:
                        target_url = links[0]
            except Exception:
                pass

        if not target_url:
            card_buf = await async_help_card("short", pfx)
            if card_buf:
                card_file = discord.File(card_buf, filename="short_guide.png")
                await autorep(
                    ctx.message,
                    content="🔗 **HƯỚNG DẪN RÚT GỌN LINK (URL SHORTENER)**",
                    file=card_file,
                    auto_delete_delay=60
                )
            else:
                msg = await autorep(
                    ctx.message,
                    f"🔗 **HƯỚNG DẪN RÚT GỌN LINK**\n"
                    f"👉 Cú pháp: `{pfx}short <link>` (hoặc reply vào tin nhắn có link rồi gõ `{pfx}short`)\n"
                    f"👉 Để soi link rút gọn: `{pfx}unshort <link_ngắn>`"
                )
                autodelet(msg, delay=30)
            return

        waiting = await autorep(ctx.message, "⏳ Đang tạo link rút gọn...")
        autodelet(waiting, delay=10)

        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, self._create_short_link, target_url)

        if not res:
            msg = await autorep(ctx.message, "❌ Không thể rút gọn link này (link lỗi hoặc máy chủ rút gọn từ chối).")
            autodelet(msg, delay=15)
            return

        short_url, provider = res
        try:
            buf = await loop.run_in_executor(None, self._render_short_card, target_url, short_url, provider)
            file = discord.File(buf, filename="shortlink.png")
            caption = (
                f"🔗 **ĐÃ RÚT GỌN LINK THÀNH CÔNG!**\n"
                f"👉 Link rút gọn: **{short_url}**\n"
                f"📦 Nguồn: *{target_url[:80]}...*"
            )
            sent = await autorep(ctx.message, content=caption, file=file, auto_delete_delay=60)
            autodelet(sent, delay=60)
        except Exception:
            sent = await autorep(ctx.message, content=f"🔗 Link rút gọn của bạn: **{short_url}**", auto_delete_delay=60)
            autodelet(sent, delay=60)

    # ── LỆNH GIẢI MÃ (PREFIX)UNSHORT / CHECKLINK / GIAIMALINK ──────────────
    @menu_entry("AI & TIỆN ÍCH", "unshort", "Soi link an, giai ma link rut gon & canh bao IP logger",
                badge="HOT", icon_sym="🛡️", icon_color=(239, 68, 68), order=10)
    @alias_declare("unshort", ["checklink", "giaimalink"])
    @commands.command(
        name="unshort",
        aliases=["checklink", "giaimalink"],
        help="Giai ma link rut gon, soi dich den thuc su va canh bao link doc hai."
    )
    async def cmd_unshort(self, ctx: commands.Context, *, url_arg: Optional[str] = None):
        """Giải mã link ẩn: (prefix)unshort <link_ngắn> (hoặc reply link)"""
        pfx = self._pfx()

        target_url = None
        if url_arg:
            links = re.findall(r'https?://[^\s]+', url_arg)
            if links:
                target_url = links[0]

        if not target_url and ctx.message.reference and ctx.message.reference.message_id:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if ref_msg.content:
                    links = re.findall(r'https?://[^\s]+', ref_msg.content)
                    if links:
                        target_url = links[0]
            except Exception:
                pass

        if not target_url:
            msg = await autorep(ctx.message, f"❌ Cú pháp: `{pfx}unshort <link rút gọn>` (hoặc reply vào tin nhắn có link).")
            autodelet(msg, delay=15)
            return

        waiting = await autorep(ctx.message, f"⏳ Đang lần theo luồng chuyển hướng của `{target_url}`...")
        autodelet(waiting, delay=10)

        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, self._trace_unshorten, target_url)

        try:
            buf = await loop.run_in_executor(None, self._render_unshort_card, data)
            file = discord.File(buf, filename="unshort_radar.png")
            warn_txt = "⚠️ **CẢNH BÁO: PHÁT HIỆN DẤU HIỆU LINK IP LOGGER / BẪY!**\n" if data["is_suspicious"] else ""
            caption = (
                f"{warn_txt}🛡️ **KẾT QUẢ SOI ĐÍCH ĐẾN LINK ẨN:**\n"
                f"🔗 Link gốc: `{data['initial']}`\n"
                f"🎯 **Đích đến thực sự:** **{data['final']}**\n"
                f"🏢 Tên miền đích: `{data['domain']}`   •   Hops: `{data['hops_count']}` lần"
            )
            sent = await autorep(ctx.message, content=caption, file=file, auto_delete_delay=60)
            autodelet(sent, delay=60)
        except Exception as e:
            sent = await autorep(
                ctx.message,
                content=f"🎯 **Đích đến thực sự:** **{data['final']}** (Domain: `{data['domain']}`)",
                auto_delete_delay=60
            )
            autodelet(sent, delay=60)


async def setup(bot: commands.Bot):
    await bot.add_cog(ShortlinkModule(bot))
