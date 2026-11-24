# -*- coding: utf-8 -*-
"""
MODULE: github (GitHub Developer & Repository Hub)
- Lệnh chính: (prefix)github, (prefix)git, (prefix)gh
- Cú pháp:
  • (prefix)github : Mở thẻ hướng dẫn Liquid Glass.
  • (prefix)github user <username> : Tra cứu hồ sơ lập trình viên, số repo, followers, bio.
  • (prefix)github repo <owner/repo> : Soi chi tiết repository (Stars, Forks, Issues, Ngôn ngữ).
  • (prefix)github release <owner/repo> : Xem phiên bản phát hành mới nhất (Tag, changelog).
"""
from __future__ import annotations

import asyncio
import datetime
import io
import json
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


class GitHubModule(commands.Cog, name="GitHub"):
    """Module tra cứu GitHub Developer, Repository & Release dạng Liquid Glass."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/vnd.github.v3+json"
        })

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return "."

    def _format_num(self, n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}k"
        return str(n)

    def _format_iso(self, iso_str: Optional[str]) -> str:
        if not iso_str:
            return "N/A"
        try:
            dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y")
        except Exception:
            return iso_str[:10]

    # ── RENDER LIQUID GLASS USER PROFILE ────────────────────────────────────
    def _render_user_card(self, u: Dict[str, Any], avatar_bytes: Optional[bytes] = None) -> io.BytesIO:
        if G is None:
            raise RuntimeError("Thư viện Liquid Glass không khả dụng.")

        LW, LH = 980, 480
        pad = 20
        head_h = 70
        gap = 14
        cv = G.GlassCanvas(LW, LH, scale=2, out=1.35)
        pfx = self._pfx()

        login = u.get("login", "Unknown")
        name = u.get("name") or login
        bio = u.get("bio") or "Không có tiểu sử giới thiệu."
        company = u.get("company") or "Cá nhân"
        location = u.get("location") or "Toàn cầu"
        created_at = self._format_iso(u.get("created_at"))

        cv.header(
            pad, pad, LW - pad, head_h,
            f"GITHUB DEVELOPER - {login.upper()}",
            f"Prefix {pfx}   •   Tham gia: {created_at}   •   Khu vực: {location}",
            tag="DEVELOPER PROFILE",
            right_reserve=160
        )
        cv.pill(LW - pad - 16, pad + head_h / 2 - 14, "GITHUB DEV", cv.font("b", 12), G.G_BRAND, h=24, align="r")

        top = pad + head_h + gap
        box1_h = 135
        cv.glass((pad, top, LW - pad, top + box1_h), 18, blur=24, tint=(16, 20, 32, 100))
        cv.grad((pad + 4, top + 14, pad + 8, top + box1_h - 14), 2, (99, 102, 241), (236, 72, 153))

        # Avatar tròn
        cv.circle_image(avatar_bytes, pad + 24, top + 22, 68, ring=G.G_BRAND, letter=login[:2].upper())

        # Tên & Bio
        cv.text(pad + 112, top + 34, f"{name} (@{login})", cv.font("b", 19), G.C_TEXT, vcenter=True)
        cv.text(pad + 112, top + 62, cv.fit(bio, cv.font("r", 12), LW - pad - 140), cv.font("r", 12), G.C_MUTED, vcenter=True)

        meta_str = f"🏢 {company}   •   📍 {location}   •   🔗 github.com/{login}"
        cv.text(pad + 112, top + 92, cv.fit(meta_str, cv.font("r", 11), LW - pad - 140), cv.font("r", 11), G.C_DIM, vcenter=True)

        # 4 Stat Capsules
        top2 = top + box1_h + gap
        bottom = LH - pad - 26
        capsules = [
            ("Kho Lưu Trữ (Repos)", self._format_num(u.get("public_repos", 0)), (56, 189, 248)),
            ("Người Theo Dõi", self._format_num(u.get("followers", 0)), (251, 191, 36)),
            ("Đang Theo Dõi", self._format_num(u.get("following", 0)), (16, 185, 129)),
            ("Gists Công Khai", self._format_num(u.get("public_gists", 0)), G.C_TEXT),
        ]
        cap_w = (LW - 2 * pad - 3 * gap) / 4

        for i, (lbl, val, col) in enumerate(capsules):
            cx1 = pad + i * (cap_w + gap)
            cx2 = cx1 + cap_w
            cv.glass((cx1, top2, cx2, bottom), 14, blur=16, tint=(18, 22, 38, 85))
            cv.text((cx1 + cx2) / 2, top2 + 24, lbl, cv.font("r", 12), G.C_MUTED, align="c", vcenter=True)
            cv.text((cx1 + cx2) / 2, top2 + 56, val, cv.font("b", 18), col, align="c", vcenter=True)

        # Footer
        cv.text(
            pad + 10, LH - pad - 8,
            f"Dữ liệu trực tiếp từ GitHub REST API v3   •   https://github.com/{login}",
            cv.font("r", 11), G.C_DIM, vcenter=True
        )

        return cv.finalize()

    # ── RENDER LIQUID GLASS REPO CARD ───────────────────────────────────────
    def _render_repo_card(self, r: Dict[str, Any], owner_avatar: Optional[bytes] = None) -> io.BytesIO:
        if G is None:
            raise RuntimeError("Thư viện Liquid Glass không khả dụng.")

        LW, LH = 980, 480
        pad = 20
        head_h = 70
        gap = 14
        cv = G.GlassCanvas(LW, LH, scale=2, out=1.35)
        pfx = self._pfx()

        full_name = r.get("full_name", "repository")
        desc = r.get("description") or "Không có mô tả cho repository này."
        lang = r.get("language") or "Nhiều ngôn ngữ"
        license_name = r.get("license", {}).get("spdx_id") if r.get("license") else "Không rõ"
        branch = r.get("default_branch", "main")
        stars = self._format_num(r.get("stargazers_count", 0))
        forks = self._format_num(r.get("forks_count", 0))
        issues = self._format_num(r.get("open_issues_count", 0))
        subscribers = self._format_num(r.get("subscribers_count", 0))

        cv.header(
            pad, pad, LW - pad, head_h,
            f"REPOSITORY - {full_name.upper()}",
            f"Prefix {pfx}   •   Nhánh chính: {branch}   •   Giấy phép: {license_name}",
            tag="OPEN SOURCE",
            right_reserve=160
        )
        cv.pill(LW - pad - 16, pad + head_h / 2 - 14, f"★ {stars}", cv.font("b", 12), G.G_AMBER, h=24, align="r")

        top = pad + head_h + gap
        box1_h = 135
        cv.glass((pad, top, LW - pad, top + box1_h), 18, blur=24, tint=(16, 20, 32, 100))
        cv.grad((pad + 4, top + 14, pad + 8, top + box1_h - 14), 2, (245, 158, 11), (239, 68, 68))

        # Avatar repo owner
        owner_name = r.get("owner", {}).get("login", "GH")
        cv.circle_image(owner_avatar, pad + 24, top + 22, 68, ring=G.G_AMBER, letter=owner_name[:2].upper())

        # Tên & Mô tả
        cv.text(pad + 112, top + 34, full_name, cv.font("b", 19), G.C_TEXT, vcenter=True)
        cv.text(pad + 112, top + 62, cv.fit(desc, cv.font("r", 12), LW - pad - 140), cv.font("r", 12), G.C_MUTED, vcenter=True)

        pill_txt = f"💻 {lang}"
        cv.pill(pad + 112, top + 92, pill_txt, cv.font("b", 11), G.G_BLUE, h=22, padx=10)
        cv.text(pad + 230, top + 102, f"Cập nhật: {self._format_iso(r.get('updated_at'))}", cv.font("r", 11), G.C_DIM, vcenter=True)

        # 4 Stat Capsules
        top2 = top + box1_h + gap
        bottom = LH - pad - 26
        capsules = [
            ("Số Sao (Stars)", f"★ {stars}", (251, 191, 36)),
            ("Nhánh Sao Chép (Forks)", f"⑂ {forks}", (56, 189, 248)),
            ("Vấn Đề Đang Mở (Issues)", f"◎ {issues}", (239, 68, 68)),
            ("Người Theo Dõi (Watchers)", f"👁 {subscribers}", (16, 185, 129)),
        ]
        cap_w = (LW - 2 * pad - 3 * gap) / 4

        for i, (lbl, val, col) in enumerate(capsules):
            cx1 = pad + i * (cap_w + gap)
            cx2 = cx1 + cap_w
            cv.glass((cx1, top2, cx2, bottom), 14, blur=16, tint=(18, 22, 38, 85))
            cv.text((cx1 + cx2) / 2, top2 + 24, lbl, cv.font("r", 12), G.C_MUTED, align="c", vcenter=True)
            cv.text((cx1 + cx2) / 2, top2 + 56, val, cv.font("b", 18), col, align="c", vcenter=True)

        # Footer
        cv.text(
            pad + 10, LH - pad - 8,
            f"Kho mã nguồn công khai: https://github.com/{full_name}",
            cv.font("r", 11), G.C_DIM, vcenter=True
        )

        return cv.finalize()

    # ── LỆNH CHÍNH (PREFIX)GITHUB / GIT / GH ────────────────────────────────
    @menu_entry("AI & TIỆN ÍCH", "github", "Tra cuu Profile, Repo va Release GitHub",
                badge="DEV", icon_sym="🐙", icon_color=(99, 102, 241), order=5)
    @alias_declare("github", ["git", "gh"])
    @commands.group(
        name="github",
        aliases=["git", "gh"],
        invoke_without_command=True,
        help="Tra cuu ho so lap trinh vien, ma nguon va ban release GitHub."
    )
    async def cmd_github(self, ctx: commands.Context, *, target: Optional[str] = None):
        """Lệnh tra cứu GitHub: (prefix)git <user/repo> hoặc (prefix)git user <user>"""
        pfx = self._pfx()

        if not target:
            card_buf = await async_help_card("github", pfx)
            if card_buf:
                card_file = discord.File(card_buf, filename="github_guide.png")
                await autorep(
                    ctx.message,
                    content="🐙 **HƯỚNG DẪN TRA CỨU GITHUB DEVELOPER & REPOSITORY**",
                    file=card_file,
                    auto_delete_delay=60
                )
            else:
                msg = await autorep(
                    ctx.message,
                    f"🐙 **HƯỚNG DẪN TRA CỨU GITHUB**\n"
                    f"👉 Tra cứu user: `{pfx}git user <username>` (VD: `{pfx}git user torvalds`)\n"
                    f"👉 Tra cứu repo: `{pfx}git repo <owner/repo>` (VD: `{pfx}git repo yt-dlp/yt-dlp`)\n"
                    f"👉 Tra cứu release: `{pfx}git release <owner/repo>`\n"
                    f"💡 Có thể gõ tắt nhanh: `{pfx}git <owner/repo>` để xem repo!"
                )
                autodelet(msg, delay=30)
            return

        # Nếu user gõ tắt 'git owner/repo'
        if "/" in target and not target.startswith("user ") and not target.startswith("repo "):
            await self.sub_repo(ctx, repo_name=target.strip())
            return

        # Ngược lại tra cứu user
        await self.sub_user(ctx, username=target.strip())

    @cmd_github.command(name="user", aliases=["u", "profile"])
    async def sub_user(self, ctx: commands.Context, *, username: str):
        """Soi hồ sơ lập trình viên GitHub: (prefix)git user <username>"""
        username = username.strip().lstrip("@")
        waiting = await autorep(ctx.message, f"⏳ Đang tải dữ liệu GitHub profile **{username}**...")
        autodelet(waiting, delay=10)

        loop = asyncio.get_running_loop()

        def _fetch():
            url = f"https://api.github.com/users/{urllib.parse.quote(username)}"
            res = self.session.get(url, timeout=6)
            if res.status_code != 200:
                return None, None
            u_data = res.json()
            avt_url = u_data.get("avatar_url")
            avt_bytes = None
            if avt_url:
                try:
                    avt_bytes = self.session.get(avt_url, timeout=5).content
                except Exception:
                    pass
            return u_data, avt_bytes

        data, avt_bytes = await loop.run_in_executor(None, _fetch)

        if not data:
            msg = await autorep(ctx.message, f"❌ Không tìm thấy người dùng GitHub: **{username}**.")
            autodelet(msg, delay=20)
            return

        try:
            buf = await loop.run_in_executor(None, self._render_user_card, data, avt_bytes)
            file = discord.File(buf, filename=f"gh_user_{username}.png")
            caption = (
                f"🐙 **GITHUB PROFILE: {data.get('name') or username}** (@{data.get('login')})\n"
                f"📦 Repos: **{data.get('public_repos')}**   |   👥 Followers: **{data.get('followers')}**   |   📍 **{data.get('location') or 'Global'}**\n"
                f"🔗 https://github.com/{data.get('login')}"
            )
            sent = await autorep(ctx.message, content=caption, file=file, auto_delete_delay=60)
            autodelet(sent, delay=60)
        except Exception as e:
            msg = await autorep(ctx.message, f"❌ Lỗi render thẻ GitHub: {str(e)[:100]}")
            autodelet(msg, delay=20)

    @cmd_github.command(name="repo", aliases=["r"])
    async def sub_repo(self, ctx: commands.Context, *, repo_name: str):
        """Soi repository GitHub: (prefix)git repo <owner/repo>"""
        repo_name = repo_name.strip().replace("https://github.com/", "").strip("/")
        if "/" not in repo_name:
            msg = await autorep(ctx.message, "❌ Vui lòng nhập đúng định dạng: `owner/repository` (VD: `yt-dlp/yt-dlp`).")
            autodelet(msg, delay=15)
            return

        waiting = await autorep(ctx.message, f"⏳ Đang tải dữ liệu repository **{repo_name}**...")
        autodelet(waiting, delay=10)

        loop = asyncio.get_running_loop()

        def _fetch():
            url = f"https://api.github.com/repos/{repo_name}"
            res = self.session.get(url, timeout=6)
            if res.status_code != 200:
                return None, None
            r_data = res.json()
            avt_url = r_data.get("owner", {}).get("avatar_url")
            avt_bytes = None
            if avt_url:
                try:
                    avt_bytes = self.session.get(avt_url, timeout=5).content
                except Exception:
                    pass
            return r_data, avt_bytes

        data, avt_bytes = await loop.run_in_executor(None, _fetch)

        if not data:
            msg = await autorep(ctx.message, f"❌ Không tìm thấy repository: **{repo_name}** (hoặc là repo riêng tư).")
            autodelet(msg, delay=20)
            return

        try:
            buf = await loop.run_in_executor(None, self._render_repo_card, data, avt_bytes)
            file = discord.File(buf, filename=f"gh_repo_{repo_name.replace('/', '_')}.png")
            caption = (
                f"🐙 **GITHUB REPOSITORY: {data.get('full_name')}**\n"
                f"★ Stars: **{data.get('stargazers_count'):,}**   |   ⑂ Forks: **{data.get('forks_count'):,}**   |   💻 **{data.get('language') or 'General'}**\n"
                f"🔗 https://github.com/{data.get('full_name')}"
            )
            sent = await autorep(ctx.message, content=caption, file=file, auto_delete_delay=60)
            autodelet(sent, delay=60)
        except Exception as e:
            msg = await autorep(ctx.message, f"❌ Lỗi render thẻ Repo: {str(e)[:100]}")
            autodelet(msg, delay=20)

    @cmd_github.command(name="release", aliases=["rel"])
    async def sub_release(self, ctx: commands.Context, *, repo_name: str):
        """Xem bản phát hành mới nhất: (prefix)git release <owner/repo>"""
        repo_name = repo_name.strip().replace("https://github.com/", "").strip("/")
        if "/" not in repo_name:
            msg = await autorep(ctx.message, "❌ Vui lòng nhập đúng định dạng: `owner/repository` (VD: `yt-dlp/yt-dlp`).")
            autodelet(msg, delay=15)
            return

        waiting = await autorep(ctx.message, f"⏳ Đang kiểm tra bản phát hành mới nhất của **{repo_name}**...")
        autodelet(waiting, delay=10)

        loop = asyncio.get_running_loop()

        def _fetch():
            url = f"https://api.github.com/repos/{repo_name}/releases/latest"
            res = self.session.get(url, timeout=6)
            if res.status_code != 200:
                return None
            return res.json()

        rel = await loop.run_in_executor(None, _fetch)

        if not rel:
            msg = await autorep(ctx.message, f"❌ Repository **{repo_name}** chưa có bản phát hành (release) chính thức nào.")
            autodelet(msg, delay=20)
            return

        tag = rel.get("tag_name", "latest")
        name = rel.get("name") or tag
        author = rel.get("author", {}).get("login", "author")
        pub_at = self._format_iso(rel.get("published_at"))
        html_url = rel.get("html_url", "")
        assets = rel.get("assets", [])
        asset_count = len(assets)

        caption = (
            f"🚀 **GITHUB LATEST RELEASE — {repo_name}**\n"
            f"🏷️ Phiên bản: **{tag}** ({name})\n"
            f"👤 Người phát hành: **{author}**   •   📅 Ngày: **{pub_at}**\n"
            f"📦 File đính kèm: **{asset_count} assets**\n"
            f"🔗 {html_url}"
        )
        sent = await autorep(ctx.message, content=caption, auto_delete_delay=60)
        autodelet(sent, delay=60)


async def setup(bot: commands.Bot):
    await bot.add_cog(GitHubModule(bot))
