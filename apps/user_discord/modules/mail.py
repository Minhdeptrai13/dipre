# -*- coding: utf-8 -*-
"""
MODULE: mail (Temp Mail 10 Phút & Nhận Mã OTP Tự Động)
- Lệnh chính: (prefix)mail, (prefix)tempmail, (prefix)hopthu
- Cú pháp:
  • (prefix)mail : Mở bảng hướng dẫn Liquid Glass Hộp Thư Ảo.
  • (prefix)mail gen : Tạo một địa chỉ email ảo 10 phút mới kèm thẻ hiển thị.
  • (prefix)mail inbox : Kiểm tra danh sách thư và mã OTP gửi về.
  • (prefix)mail read <id> : Đọc chi tiết toàn bộ nội dung của bức thư.
  • (prefix)mail current : Xem lại địa chỉ email ảo đang hoạt động hiện tại.
"""
from __future__ import annotations

import asyncio
import datetime
import io
import json
import os
import random
import re
import time
from pathlib import Path
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

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_FILE = DATA_DIR / "mail_sessions.json"


class MailModule(commands.Cog, name="TempMail"):
    """Module hộp thư ảo 10 phút nhận mã OTP và email xác thực tự động."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json"
        })
        self.sessions: Dict[str, Dict[str, Any]] = self._load_sessions()

    def _load_sessions(self) -> Dict[str, Dict[str, Any]]:
        if SESSIONS_FILE.exists():
            try:
                with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_sessions(self) -> None:
        try:
            with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.sessions, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return "."

    # ── TẠO TÀI KHOẢN TRÊN MAIL.TM ─────────────────────────────────────────
    def _create_mail_account(self) -> Optional[Dict[str, Any]]:
        try:
            # 1. Lấy domain khả dụng
            res_domains = self.session.get("https://api.mail.tm/domains", timeout=6).json()
            members = res_domains.get("hydra:member", [])
            if not members:
                return None
            domain = members[0].get("domain")

            rand_id = f"user_{int(time.time() % 100000)}_{random.randint(100, 999)}"
            address = f"{rand_id}@{domain}"
            password = f"Pass_{random.randint(100000, 999999)}!"

            # 2. Tạo tài khoản
            reg_payload = json.dumps({"address": address, "password": password})
            res_reg = self.session.post("https://api.mail.tm/accounts", data=reg_payload, timeout=6)
            if res_reg.status_code not in (200, 201):
                return None

            # 3. Lấy auth token
            res_tok = self.session.post("https://api.mail.tm/token", data=reg_payload, timeout=6)
            if res_tok.status_code != 200:
                return None
            token = res_tok.json().get("token")

            return {
                "address": address,
                "password": password,
                "token": token,
                "created_at": time.time(),
            }
        except Exception:
            return None

    # ── LẤY DANH SÁCH HỘP THƯ ĐẾN ──────────────────────────────────────────
    def _fetch_inbox(self, token: str) -> List[Dict[str, Any]]:
        try:
            headers = {"Authorization": f"Bearer {token}"}
            res = self.session.get("https://api.mail.tm/messages", headers=headers, timeout=6)
            if res.status_code == 200:
                return res.json().get("hydra:member", [])
        except Exception:
            pass
        return []

    # ── LẤY CHI TIẾT 1 EMAIL ────────────────────────────────────────────────
    def _fetch_message(self, token: str, msg_id: str) -> Optional[Dict[str, Any]]:
        try:
            headers = {"Authorization": f"Bearer {token}"}
            res = self.session.get(f"https://api.mail.tm/messages/{msg_id}", headers=headers, timeout=6)
            if res.status_code == 200:
                return res.json()
        except Exception:
            pass
        return None

    # ── RENDER LIQUID GLASS THẺ EMAIL ĐÃ TẠO ──────────────────────────────
    def _render_created_card(self, address: str) -> io.BytesIO:
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
            "HỘP THƯ ẢO 10 PHÚT — ACTIVE",
            f"Prefix {pfx}   •   Nhận OTP & Email xác thực tức thì   •   Thời hạn: 10 phút",
            tag="TEMP MAIL",
            right_reserve=160
        )
        cv.pill(LW - pad - 16, pad + head_h / 2 - 14, "READY 10M", cv.font("b", 12), G.G_GREEN, h=24, align="r")

        top = pad + head_h + gap
        box1_h = 135
        cv.glass((pad, top, LW - pad, top + box1_h), 18, blur=24, tint=(16, 24, 38, 100))
        cv.grad((pad + 4, top + 14, pad + 8, top + box1_h - 14), 2, (16, 185, 129), (6, 182, 212))

        # Icon hòm thư
        cv.circle_image(None, pad + 24, top + 22, 68, ring=G.G_GREEN, letter="OTP", fill=(20, 36, 44))

        cv.text(pad + 114, top + 34, "ĐỊA CHỈ EMAIL ẢO CỦA BẠN:", cv.font("r", 12), G.C_MUTED, vcenter=True)
        cv.text(pad + 114, top + 64, address, cv.font("b", 22), G.C_GOLD, vcenter=True)
        cv.pill(pad + 114, top + 98, "🟢 ĐANG LẮNG NGHE HỘP THƯ", cv.font("b", 11), G.G_GREEN, h=22, padx=10)

        # 4 Stat Capsules
        top2 = top + box1_h + gap
        bottom = LH - pad - 24
        capsules = [
            ("Lệnh Kiểm Tra", f"{pfx}mail inbox", (56, 189, 248)),
            ("Tự Động Làm Mới", "Realtime", (16, 185, 129)),
            ("Nhận Mã OTP", "Hỗ trợ 100%", (251, 191, 36)),
            ("Bảo Mật", "Ẩn danh hoàn toàn", G.C_TEXT),
        ]
        cap_w = (LW - 2 * pad - 3 * gap) / 4

        for i, (lbl, val, col) in enumerate(capsules):
            cx1 = pad + i * (cap_w + gap)
            cx2 = cx1 + cap_w
            cv.glass((cx1, top2, cx2, bottom), 14, blur=16, tint=(18, 22, 38, 85))
            cv.text((cx1 + cx2) / 2, top2 + 22, lbl, cv.font("r", 12), G.C_MUTED, align="c", vcenter=True)
            cv.text((cx1 + cx2) / 2, top2 + 52, val, cv.font("b", 15), col, align="c", vcenter=True)

        return cv.finalize()

    # ── LỆNH CHÍNH (PREFIX)MAIL / TEMPMAIL / HOPTHU ─────────────────────────
    @menu_entry("AI & TIỆN ÍCH", "mail", "Hop thu ao 10 phut nhan ma OTP",
                badge="HOT", icon_sym="✉️", icon_color=(16, 185, 129), order=8)
    @alias_declare("mail", ["tempmail", "hopthu"])
    @commands.group(
        name="mail",
        aliases=["tempmail", "hopthu"],
        invoke_without_command=True,
        help="Hop thu ao 10 phut nhan ma OTP va email xac thuc tu dong."
    )
    async def cmd_mail(self, ctx: commands.Context):
        """Mở thẻ hướng dẫn Liquid Glass Hộp Thư Ảo."""
        pfx = self._pfx()
        card_buf = await async_help_card("mail", pfx)
        if card_buf:
            card_file = discord.File(card_buf, filename="mail_guide.png")
            await autorep(
                ctx.message,
                content="✉️ **HƯỚNG DẪN HỘP THƯ ẢO 10 PHÚT & NHẬN OTP**",
                file=card_file,
                auto_delete_delay=60
            )
        else:
            msg = await autorep(
                ctx.message,
                f"✉️ **HƯỚNG DẪN SỬ DỤNG HỘP THƯ ẢO**\n"
                f"• `{pfx}mail gen` : Tạo một email ảo mới 10 phút\n"
                f"• `{pfx}mail inbox` : Kiểm tra hòm thư đến và nhận mã OTP\n"
                f"• `{pfx}mail read <id>` : Đọc chi tiết nội dung thư\n"
                f"• `{pfx}mail current` : Xem email đang dùng hiện tại"
            )
            autodelet(msg, delay=30)

    # ── LỆNH CON: TẠO EMAIL MỚI (MAIL GEN) ─────────────────────────────────
    @cmd_mail.command(name="gen", aliases=["new", "create", "tao"])
    async def sub_gen(self, ctx: commands.Context):
        """Tạo địa chỉ email ảo mới 10 phút: (prefix)mail gen"""
        waiting = await autorep(ctx.message, "⏳ Đang kết nối máy chủ tạo email ảo 10 phút...")
        autodelet(waiting, delay=10)

        loop = asyncio.get_running_loop()
        acc = await loop.run_in_executor(None, self._create_mail_account)

        if not acc:
            msg = await autorep(ctx.message, "❌ Máy chủ email đang bảo trì hoặc quá tải. Vui lòng thử lại sau giây lát!")
            autodelet(msg, delay=15)
            return

        # Lưu session theo user_id
        user_key = str(ctx.author.id)
        self.sessions[user_key] = acc
        self._save_sessions()

        address = acc["address"]
        try:
            buf = await loop.run_in_executor(None, self._render_created_card, address)
            file = discord.File(buf, filename="mail_created.png")
            caption = (
                f"✉️ **ĐÃ TẠO HỘP THƯ ẢO THÀNH CÔNG!**\n"
                f"📧 Email: `{address}`\n"
                f"💡 Hãy dùng email này để nhận OTP/đăng ký tài khoản, sau đó gõ `{self._pfx()}mail inbox` để kiểm tra thư đến!"
            )
            sent = await autorep(ctx.message, content=caption, file=file, auto_delete_delay=90)
            autodelet(sent, delay=90)
        except Exception:
            sent = await autorep(
                ctx.message,
                content=f"✉️ **Email ảo mới của bạn:** `{address}`\n👉 Gõ `{self._pfx()}mail inbox` để xem mã OTP!",
                auto_delete_delay=90
            )
            autodelet(sent, delay=90)

    # ── LỆNH CON: KIỂM TRA HỘP THƯ (MAIL INBOX) ────────────────────────────
    @cmd_mail.command(name="inbox", aliases=["check", "xem", "list"])
    async def sub_inbox(self, ctx: commands.Context):
        """Kiểm tra hộp thư đến & mã OTP: (prefix)mail inbox"""
        pfx = self._pfx()
        user_key = str(ctx.author.id)
        session_data = self.sessions.get(user_key)

        if not session_data:
            msg = await autorep(ctx.message, f"❌ Bạn chưa tạo email ảo nào! Hãy gõ `{pfx}mail gen` để tạo ngay.")
            autodelet(msg, delay=15)
            return

        token = session_data.get("token")
        address = session_data.get("address")

        waiting = await autorep(ctx.message, f"⏳ Đang kiểm tra hộp thư đến của `{address}`...")
        autodelet(waiting, delay=10)

        loop = asyncio.get_running_loop()
        messages = await loop.run_in_executor(None, self._fetch_inbox, token)

        if not messages:
            msg = await autorep(
                ctx.message,
                f"📭 Hộp thư `{address}` hiện **chưa có thư mới nào**.\n"
                f"*(Nếu vừa gửi yêu cầu OTP, hãy đợi 5 - 15 giây rồi gõ lại `{pfx}mail inbox`)*"
            )
            autodelet(msg, delay=20)
            return

        # Soạn danh sách thư
        lines = [f"📬 **HỘP THƯ ĐẾN CỦA `{address}` ({len(messages)} thư):**\n"]
        for idx, m in enumerate(messages[:10], 1):
            sender = m.get("from", {}).get("address", "Unknown")
            subject = m.get("subject", "(Không có tiêu đề)")
            intro = m.get("intro", "")
            msg_id = m.get("id")

            # Tìm mã OTP nếu có trong intro hoặc subject (chuỗi 4-8 số)
            otp_match = re.search(r'\b\d{4,8}\b', f"{subject} {intro}")
            otp_badge = f" [🔑 OTP: **{otp_match.group(0)}**]" if otp_match else ""

            lines.append(f"**#{idx}** từ **{sender}**{otp_badge}")
            lines.append(f"   📌 Tiêu đề: *{subject}*")
            lines.append(f"   📄 Trích đoạn: `{intro[:80]}...`")
            lines.append(f"   👉 Đọc chi tiết: `{pfx}mail read {msg_id}`\n")

        full_txt = "\n".join(lines)
        sent = await autorep(ctx.message, content=full_txt, auto_delete_delay=90)
        autodelet(sent, delay=90)

    # ── LỆNH CON: ĐỌC CHI TIẾT THƯ (MAIL READ) ─────────────────────────────
    @cmd_mail.command(name="read", aliases=["doc"])
    async def sub_read(self, ctx: commands.Context, msg_id: str):
        """Đọc chi tiết nội dung 1 bức thư: (prefix)mail read <id>"""
        user_key = str(ctx.author.id)
        session_data = self.sessions.get(user_key)

        if not session_data:
            msg = await autorep(ctx.message, "❌ Bạn chưa có phiên email ảo nào đang hoạt động.")
            autodelet(msg, delay=15)
            return

        token = session_data.get("token")
        loop = asyncio.get_running_loop()
        m = await loop.run_in_executor(None, self._fetch_message, token, msg_id.strip())

        if not m:
            msg = await autorep(ctx.message, f"❌ Không tìm thấy thư với ID: `{msg_id}` (hoặc thư đã hết hạn).")
            autodelet(msg, delay=15)
            return

        sender = m.get("from", {}).get("address", "Unknown")
        subject = m.get("subject", "(Không có tiêu đề)")
        text = m.get("text", "") or m.get("intro", "Không có nội dung chữ.")

        # Phát hiện mã OTP
        otp_match = re.search(r'\b\d{4,8}\b', f"{subject} {text}")
        otp_highlight = f"\n🔥 **MÃ XÁC THỰC OTP PHÁT HIỆN ĐƯỢC:** `{otp_match.group(0)}`\n" if otp_match else ""

        clean_text = text[:1500] + ("..." if len(text) > 1500 else "")

        caption = (
            f"📄 **CHI TIẾT EMAIL XÁC THỰC**\n"
            f"👤 Người gửi: **{sender}**\n"
            f"📌 Tiêu đề: **{subject}**{otp_highlight}\n"
            f"```text\n{clean_text}\n```"
        )
        sent = await autorep(ctx.message, content=caption, auto_delete_delay=90)
        autodelet(sent, delay=90)

    # ── LỆNH CON: XEM EMAIL HIỆN TẠI (MAIL CURRENT) ───────────────────────
    @cmd_mail.command(name="current", aliases=["me", "status"])
    async def sub_current(self, ctx: commands.Context):
        """Xem lại email ảo đang dùng: (prefix)mail current"""
        user_key = str(ctx.author.id)
        session_data = self.sessions.get(user_key)
        if not session_data:
            msg = await autorep(ctx.message, f"❌ Bạn chưa tạo email ảo nào. Gõ `{self._pfx()}mail gen` để tạo mới!")
            autodelet(msg, delay=15)
            return

        address = session_data.get("address")
        caption = (
            f"📧 **EMAIL ẢO HIỆN TẠI CỦA BẠN:** `{address}`\n"
            f"👉 Gõ `{self._pfx()}mail inbox` để kiểm tra thư & mã OTP mới!"
        )
        sent = await autorep(ctx.message, content=caption, auto_delete_delay=60)
        autodelet(sent, delay=60)


async def setup(bot: commands.Bot):
    await bot.add_cog(MailModule(bot))
