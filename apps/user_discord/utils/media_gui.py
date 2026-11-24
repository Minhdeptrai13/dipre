import discord
import asyncio
import os
import io
import random
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from apps.shared.paths import SHARED_FONTS_DIR, SHARED_BACKGROUNDS_DIR

font_bold = str(SHARED_FONTS_DIR / "BeVietnamPro-Bold.ttf")
font_reg = str(SHARED_FONTS_DIR / "BeVietnamPro-Regular.ttf")

PLATFORM_COLORS = {
    "YOUTUBE": {"accent": (235, 45, 45), "tag": "▶ YOUTUBE"},
    "TIKTOK": {"accent": (254, 44, 85), "tag": "🎵 TIKTOK"},
    "SOUNDCLOUD": {"accent": (255, 85, 0), "tag": "☁ SOUNDCLOUD"},
}

async def fetch_thumb(session: aiohttp.ClientSession, url: str, size: tuple = (56, 36)) -> Image.Image:
    if not url or not str(url).startswith("http"):
        return create_fallback_thumb(size)
    try:
        async with session.get(url, timeout=1.2) as r:
            if r.status == 200:
                raw = await r.read()
                with Image.open(io.BytesIO(raw)) as im:
                    im = im.convert("RGBA")
                    return ImageOps.fit(im, size, method=Image.Resampling.LANCZOS)
    except Exception:
        pass
    return create_fallback_thumb(size)

def create_fallback_thumb(size: tuple) -> Image.Image:
    im = Image.new("RGBA", size, (25, 32, 50, 255))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([(0, 0), (size[0]-1, size[1]-1)], radius=5, fill=(30, 38, 58), outline=(255, 255, 255, 30), width=1)
    return im

async def render_media_selector(platform: str, query: str, items: list) -> discord.File:
    """
    Render bảng chọn bài/video đồ họa Liquid Glass cao cấp chuẩn GlassCanvas:
    - Nền tự động xoay ngang nếu ảnh nền dọc, khúc xạ kính mờ siêu nét.
    - Header macOS dots, hiển thị badge nền tảng và kết quả tìm kiếm.
    - Từng ô kết quả bo góc kính, thumbnail, STT phát sáng, thời lượng và thẻ tag.
    """
    try:
        from apps.user_discord.utils.glass import (
            GlassCanvas, G_BRAND, G_RED, G_GREEN, G_PURPLE, G_BLUE, G_AMBER, C_TEXT, C_MUTED, C_DIM
        )
    except ImportError:
        from utils.glass import (
            GlassCanvas, G_BRAND, G_RED, G_GREEN, G_PURPLE, G_BLUE, G_AMBER, C_TEXT, C_MUTED, C_DIM
        )

    plt = platform.upper()
    cfg = PLATFORM_COLORS.get(plt, {"accent": (14, 62, 222), "tag": f"⚡ {plt}"})
    tag_name = cfg["tag"]

    plat_grads = {
        "YOUTUBE": G_RED,
        "TIKTOK": G_BRAND,
        "SOUNDCLOUD": G_AMBER,
    }
    p_grad = plat_grads.get(plt, G_BLUE)

    count = min(20, len(items))
    use_two_cols = count > 5
    cols = 2 if use_two_cols else 1

    lw = 1040 if use_two_cols else 760
    pad = 18
    head_h = 76
    foot_h = 42
    gap_x = 12
    gap_y = 7
    row_h = 58 if use_two_cols else 64
    rows_per_col = (count + 1) // 2 if use_two_cols else count
    lh = pad + head_h + 14 + rows_per_col * row_h + (rows_per_col - 1) * gap_y + 12 + foot_h + pad

    cv = GlassCanvas(lw, lh, scale=2, out=1.25)
    q_short = query if len(query) <= 32 else query[:29] + "..."
    cv.header(pad, pad, lw - pad, head_h, f"{tag_name} — \"{q_short}\"", f"Top {count} kết quả phù hợp • Gõ số để chọn", tag=f"TOP {count}", tag_grad=p_grad)

    f_name = cv.font("b", 12.5 if use_two_cols else 13.5)
    f_meta = cv.font("r", 10.5 if use_two_cols else 11.5)
    f_num = cv.font("b", 10.5)
    f_tag = cv.font("b", 9.5)

    thumb_w, thumb_h = (54, 38) if use_two_cols else (68, 46)
    async with aiohttp.ClientSession() as session:
        thumb_tasks = [fetch_thumb(session, it.get("thumb_url"), size=(thumb_w, thumb_h)) for it in items[:count]]
        thumbs = await asyncio.gather(*thumb_tasks, return_exceptions=True)

    col_w = (lw - pad * 2 - (cols - 1) * gap_x) / cols
    start_y = pad + head_h + 14

    for idx, it in enumerate(items[:count], start=1):
        if use_two_cols:
            per_col = (count + 1) // 2
            c_idx = 0 if idx <= per_col else 1
            r_idx = (idx - 1) if c_idx == 0 else (idx - 1 - per_col)
        else:
            c_idx = 0
            r_idx = idx - 1

        x1 = pad + c_idx * (col_w + gap_x)
        y1 = start_y + r_idx * (row_h + gap_y)
        x2 = x1 + col_w
        y2 = y1 + row_h

        cv.glass((x1, y1, x2, y2), 12, blur=8, highlight=34, rim=(160, 30))

        num_str = f"{idx:02d}" if count >= 10 else str(idx)
        bw = 28
        bh = 22
        by1 = y1 + (row_h - bh) / 2
        cv.pill(x1 + 10, by1, num_str, f_num, p_grad, h=bh, padx=7)

        th = thumbs[idx - 1] if (idx - 1 < len(thumbs) and isinstance(thumbs[idx - 1], Image.Image)) else create_fallback_thumb((thumb_w, thumb_h))
        tx_pos = x1 + 10 + bw + 10
        ty_pos = y1 + (row_h - thumb_h) / 2
        cv.rrect((tx_pos, ty_pos, tx_pos + thumb_w, ty_pos + thumb_h), 5, outline=(255, 255, 255, 40), width=1)
        th_k = th.resize((cv.s(thumb_w), cv.s(thumb_h)), Image.Resampling.LANCZOS)
        mask = Image.new("L", (cv.s(thumb_w), cv.s(thumb_h)), 0)
        ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (cv.s(thumb_w) - 1, cv.s(thumb_h) - 1)], radius=cv.s(5), fill=255)
        cv.c.paste(th_k, (cv.s(tx_pos), cv.s(ty_pos)), mask)

        tag_w = 68
        rx = x2 - 10
        cv.glass_pill(rx, y1 + (row_h - 22) / 2, "🔊v • 🎬f", f_tag, p_grad, h=22, padx=8, align="r")

        info_x = tx_pos + thumb_w + 10
        info_avail = (rx - tag_w - 10) - info_x

        raw_title = str(it.get("title", "Unknown Title"))
        fit_title = cv.fit(raw_title, f_name, info_avail)
        cv.text(info_x, y1 + row_h * 0.33, fit_title, f_name, C_TEXT, vcenter=True)

        raw_author = str(it.get("author", "Unknown"))
        dur_str = str(it.get("duration", ""))
        sub_txt = f"{raw_author}" + (f" • ⏱️ {dur_str}" if dur_str else "")
        fit_sub = cv.fit(sub_txt, f_meta, info_avail)
        cv.text(info_x, y1 + row_h * 0.70, fit_sub, f_meta, C_MUTED, vcenter=True)

    foot_y = start_y + rows_per_col * row_h + (rows_per_col - 1) * gap_y + 10
    cv.bar(pad, foot_y, lw - pad, foot_y + foot_h, r=12)
    f_foot = cv.font("r", 11)
    foot_txt = f"💡 Chọn: Gõ [1-{count}] ('v': phát Voice, 'f': gửi File) • Gõ 'c' để hủy • Kết quả gửi xong không bị xóa"
    cv.text(lw / 2, foot_y + foot_h / 2, foot_txt, f_foot, (254, 240, 138), align="c", vcenter=True)

    buf = cv.finalize()
    return discord.File(fp=buf, filename="search_selector.png")


async def setup(bot):
    """Setup hook để main.py có thể nạp module utils một cách sạch sẽ."""
    pass

