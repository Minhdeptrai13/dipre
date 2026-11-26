"""
media_card.py - Fancy card cho search results va now-playing
Dung chung cho YouTube, SoundCloud, TikTok
"""
from __future__ import annotations
import io, asyncio, os, re
from typing import Literal, List, Dict, Any, Optional

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageOps, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

PLATFORM_META = {
    "youtube":    {"label": "YouTube",    "accent": (255, 0,   0),   "bg": (15, 15, 15)},
    "soundcloud": {"label": "SoundCloud", "accent": (255, 85,  0),   "bg": (12, 12, 12)},
    "tiktok":     {"label": "TikTok",     "accent": (105, 201, 208), "bg": (18, 18, 18)},
}

def _draw_yt_logo(draw, x, y, size=28):
    w = int(size * 1.4)
    h = size
    r = h // 3
    draw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=(255, 0, 0))
    cx, cy = x + w // 2, y + h // 2
    pw = size // 3
    ph = size // 3
    pts = [(cx - pw // 2, cy - ph), (cx - pw // 2, cy + ph), (cx + pw, cy)]
    draw.polygon(pts, fill=(255, 255, 255))

def _draw_sc_logo(draw, x, y, size=28):
    """Vẽ logo đám mây SoundCloud đầy đặn, mượt mà chuẩn vector tỉ lệ không bị cắt"""
    o = (255, 85, 0)
    w = int(size * 1.5)
    h = size
    # Đáy mây thẳng ở dưới
    base_y = y + int(h * 0.88)
    # Các vòm mây tròn liên hoàn
    # 1. Vòm trái
    r1 = int(h * 0.28)
    draw.ellipse([x, base_y - 2 * r1, x + 2 * r1, base_y], fill=o)
    # 2. Vòm giữa cao nhất
    r2 = int(h * 0.45)
    draw.ellipse([x + int(w * 0.22), base_y - 2 * r2, x + int(w * 0.22) + 2 * r2, base_y], fill=o)
    # 3. Vòm phải
    r3 = int(h * 0.35)
    draw.ellipse([x + int(w * 0.52), base_y - 2 * r3, x + int(w * 0.52) + 2 * r3, base_y], fill=o)
    # Khối liền đáy mây
    draw.rectangle([x + r1, base_y - int(h * 0.45), x + int(w * 0.52) + r3, base_y], fill=o)

def _draw_tt_logo(draw, x, y, size=28):
    s = size
    draw.rounded_rectangle([x, y, x + s, y + s], radius=6, fill=(0, 0, 0))
    cx, cy = x + s // 2, y + s // 2
    ro, ri = s // 3, s // 6
    draw.ellipse([cx - ro - 2, cy - ro - 2, cx + ro + 2, cy + ro + 2], fill=(254, 44, 85))
    draw.ellipse([cx - ro, cy - ro, cx + ro, cy + ro], fill=(105, 201, 208))
    draw.ellipse([cx - ro + 2, cy - ro + 2, cx + ro - 2, cy + ro - 2], fill=(255, 255, 255))
    draw.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill=(0, 0, 0))
    sx = cx + ro - 4
    draw.rectangle([sx, y + 4, sx + 4, cy], fill=(255, 255, 255))

LOGO_DRAWERS = {"youtube": _draw_yt_logo, "soundcloud": _draw_sc_logo, "tiktok": _draw_tt_logo}

def _get_modak_font(size: int):
    try:
        try:
            from apps.user_discord.utils.fast_image import get_font as _fast_font
        except ImportError:
            from utils.fast_image import get_font as _fast_font  # type: ignore
        return _fast_font("modak", int(size))
    except Exception:
        pass
    if not HAS_PIL: return None
    try:
        from apps.shared.paths import SHARED_FONTS_DIR
        modak_path = SHARED_FONTS_DIR / "DFVN-Modak.ttf"
        if modak_path.exists():
            return ImageFont.truetype(str(modak_path), size)
    except Exception:
        pass
    for c in [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\calibrib.ttf"]:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()

def _get_regular_font(size: int, bold: bool = False):
    try:
        try:
            from apps.user_discord.utils.fast_image import get_font as _fast_font
        except ImportError:
            from utils.fast_image import get_font as _fast_font  # type: ignore
        return _fast_font("b" if bold else "r", int(size))
    except Exception:
        pass
    if not HAS_PIL: return None
    try:
        from apps.shared.paths import SHARED_FONTS_DIR
        reg_file = "BeVietnamPro-Bold.ttf" if bold else "BeVietnamPro-Regular.ttf"
        reg_path = SHARED_FONTS_DIR / reg_file
        if reg_path.exists():
            return ImageFont.truetype(str(reg_path), size)
        reg_alt = SHARED_FONTS_DIR / "BeVietnamPro-Regular.ttf"
        if reg_alt.exists():
            return ImageFont.truetype(str(reg_alt), size)
    except Exception:
        pass
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibrib.ttf" if bold else r"C:\Windows\Fonts\calibri.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()

def _font(size):
    return _get_regular_font(size)

# Memory Cache cho Thumbnails (Giúp tạo ảnh siêu tốc trong sub-5ms)
_THUMB_CACHE = {}

def _fetch_img(url, referer=None):
    if not HAS_REQUESTS or not url or not str(url).startswith("http"):
        return None
    if url in _THUMB_CACHE:
        return _THUMB_CACHE[url].copy()
    try:
        try:
            from apps.user_discord.utils.fast_image import fetch_thumb_fast as _fast_thumb
        except ImportError:
            from utils.fast_image import fetch_thumb_fast as _fast_thumb  # type: ignore
        fast = _fast_thumb(url, size=(160, 160), timeout=2.5)
        if fast is not None:
            if len(_THUMB_CACHE) > 150:
                _THUMB_CACHE.pop(next(iter(_THUMB_CACHE)))
            _THUMB_CACHE[url] = fast
            return fast.copy()
    except Exception:
        pass
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": referer or ("https://www.tiktok.com/" if "tiktok" in url else "https://soundcloud.com/")
        }
        r = _requests.get(url, timeout=3.5, headers=headers)
        if r.status_code == 200 and len(r.content) > 100:
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            if len(_THUMB_CACHE) > 150:
                _THUMB_CACHE.pop(next(iter(_THUMB_CACHE)))
            _THUMB_CACHE[url] = im
            return im.copy()
    except Exception:
        pass
    return None

def _crop_black_bars(img):
    """Tự động xén bỏ dải đen pillarbox/letterbox thừa của video YouTube để ảnh tròn tràn kín hoàn mỹ"""
    if not img: return img
    try:
        gray = img.convert("L")
        w, h = gray.size
        # Tìm mép trái không đen (threshold 22)
        left = 0
        for x in range(w // 3):
            col = [gray.getpixel((x, y)) for y in range(0, h, max(1, h // 20))]
            if sum(col) / len(col) > 22:
                left = max(0, x - 1)
                break
        # Tìm mép phải không đen
        right = w
        for x in range(w - 1, w - w // 3, -1):
            col = [gray.getpixel((x, y)) for y in range(0, h, max(1, h // 20))]
            if sum(col) / len(col) > 22:
                right = min(w, x + 1)
                break
        # Tìm mép trên
        top = 0
        for y in range(h // 4):
            row = [gray.getpixel((x, y)) for x in range(0, w, max(1, w // 20))]
            if sum(row) / len(row) > 22:
                top = max(0, y - 1)
                break
        # Tìm mép dưới
        bottom = h
        for y in range(h - 1, h - h // 4, -1):
            row = [gray.getpixel((x, y)) for x in range(0, w, max(1, w // 20))]
            if sum(row) / len(row) > 22:
                bottom = min(h, y + 1)
                break
        
        if right > left + 40 and bottom > top + 40:
            return img.crop((left, top, right, bottom))
    except Exception:
        pass
    return img

def _trunc(text, n):
    s = str(text)
    return s[:n]+"..." if len(s)>n else s

def _format_count(n):
    try:
        n = int(n)
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n/1_000:.1f}K"
        return str(n)
    except Exception:
        return "0"

def _make_thumb_fallback(platform, w, h, accent):
    """Tạo thumbnail placeholder sang trọng với gradient và logo phát sáng không bị cắt"""
    im = Image.new("RGBA", (w, h), (24, 24, 28, 255))
    d = ImageDraw.Draw(im)
    # Subtle bottom glow bar
    d.rectangle([0, h - 5, w, h], fill=accent)
    # Vẽ logo nền tảng trung tâm chuẩn size
    s = int(min(w, h) * 0.42)
    lx = (w - int(s * 1.5 if platform == "soundcloud" else (s * 1.4 if platform == "youtube" else s))) // 2
    ly = (h - s) // 2
    fn = LOGO_DRAWERS.get(platform)
    if fn:
        try:
            fn(d, lx, ly, size=s)
        except Exception:
            pass
    return im.convert("RGB")

def _make_soundcloud_search_card(query, items):
    if not HAS_PIL: return None
    try:
        W = 960
        N = min(len(items), 8)
        if N <= 0:
            return None
        rows_count = (N + 1) // 2
        ROW_H = 76
        row_gap = 14
        HDR = 68
        H = HDR + rows_count * (ROW_H + row_gap) + 20

        base = Image.new("RGBA", (W, H), (18, 20, 26, 255))
        draw = ImageDraw.Draw(base)

        # Viền ngoài
        draw.rounded_rectangle([(4, 4), (W - 4, H - 4)], radius=20, outline=(36, 40, 48), width=1)

        f_hdr = _get_modak_font(26)
        f_badge = _get_regular_font(11, bold=True)
        f_hint = _get_regular_font(12)
        f_rank = _get_regular_font(13)
        f_track_title = _get_regular_font(14, bold=True)
        f_track_artist = _get_regular_font(12)
        f_stat = _get_regular_font(10, bold=True)

        pad_x = 26

        # 1. Header
        header_y = 20
        hdr_text = "Search Results"
        draw.text((pad_x, header_y + 2), hdr_text, fill=(255, 255, 255), font=f_hdr)
        hdr_w = draw.textlength(hdr_text, font=f_hdr)

        # Pill badge e.g. "8 tracks"
        badge_text = f"{N} tracks"
        bw = draw.textlength(badge_text, font=f_badge) + 16
        bx1 = pad_x + hdr_w + 14
        by1 = header_y + 6
        draw.rounded_rectangle([(bx1, by1), (bx1 + bw, by1 + 22)], radius=11, fill=(32, 42, 36), outline=(74, 222, 128, 80), width=1)
        draw.text((bx1 + 8, by1 + 3), badge_text, fill=(134, 239, 172), font=f_badge)

        # Top Right: Glowing dot + hint
        dot_x = W - pad_x - 8
        draw.ellipse([(dot_x, header_y + 12), (dot_x + 8, header_y + 20)], fill=(74, 222, 128))
        hint_text = "CHỌN BÀI: GÕ SỐ (1-8) • 'C' ĐỂ HỦY"
        hint_w = draw.textlength(hint_text, font=f_hint)
        draw.text((dot_x - hint_w - 14, header_y + 10), hint_text, fill=(125, 135, 145), font=f_hint)

        # 2. Hai cột dữ liệu (4 dòng x 2 cột theo đúng layout tham khảo)
        col_gap = 24
        COL_W = (W - 2 * pad_x - col_gap) // 2
        cx0 = pad_x
        cx1 = pad_x + COL_W + col_gap

        NEON_COLORS = [
            (74, 222, 128),  # 1: lime
            (56, 189, 248),  # 2: cyan
            (244, 114, 182), # 3: pink
            (251, 146, 60),  # 4: orange
            (167, 139, 250), # 5: violet
            (250, 204, 21),  # 6: yellow
            (45, 212, 191),  # 7: teal
            (248, 113, 113), # 8: coral
        ]

        th_s = 60
        mk = Image.new("L", (th_s, th_s), 0)
        ImageDraw.Draw(mk).rounded_rectangle([0, 0, th_s, th_s], radius=12, fill=255)

        for idx, item in enumerate(items[:N]):
            col = idx % 2
            row = idx // 2
            col_x = cx0 if col == 0 else cx1
            item_y = HDR + row * (ROW_H + row_gap)
            border_col = NEON_COLORS[idx % len(NEON_COLORS)]

            # Rank number
            rank_str = str(idx + 1)
            draw.text((col_x + 4, item_y + 22), rank_str, fill=(120, 125, 135), font=f_rank)

            # Artwork thumbnail
            th_x = col_x + 22
            th_y = item_y + (ROW_H - th_s) // 2
            raw_img = _fetch_img(item.get("thumb_url", ""))
            if not raw_img:
                raw_img = _make_thumb_fallback("soundcloud", th_s, th_s, border_col)
            try:
                th_img = ImageOps.fit(raw_img.convert("RGBA"), (th_s, th_s))
                th_img.putalpha(mk)
                base.paste(th_img.convert("RGB"), (th_x, th_y), th_img)
            except Exception:
                draw.rounded_rectangle([(th_x, th_y), (th_x + th_s, th_y + th_s)], radius=12, fill=(35, 38, 46))

            # Viền neon phát sáng quanh ảnh
            draw.rounded_rectangle([(th_x - 1, th_y - 1), (th_x + th_s + 1, th_y + th_s + 1)], radius=13, outline=border_col, width=2)

            # Text Info
            tx = th_x + th_s + 14
            max_tw = col_x + COL_W - tx - 6

            raw_title = str(item.get("title", "SoundCloud Track")).strip()
            disp_title = raw_title
            while draw.textlength(disp_title + "...", font=f_track_title) > max_tw and len(disp_title) > 3:
                disp_title = disp_title[:-1]
            if len(disp_title) < len(raw_title):
                disp_title += "..."
            draw.text((tx, item_y + 6), disp_title, fill=(255, 255, 255), font=f_track_title)

            raw_artist = str(item.get("author") or "Artist").strip()
            disp_artist = raw_artist
            while draw.textlength(disp_artist + "...", font=f_track_artist) > max_tw and len(disp_artist) > 3:
                disp_artist = disp_artist[:-1]
            if len(disp_artist) < len(raw_artist):
                disp_artist += "..."
            draw.text((tx, item_y + 26), disp_artist, fill=(145, 150, 160), font=f_track_artist)

            # Badges Row (Plays & Likes)
            by = item_y + 47
            p_cnt = item.get("playback_count") or 0
            dur_str = str(item.get("duration", "")).strip()
            if p_cnt:
                p_text = f"{_format_count(p_cnt)} plays"
            elif dur_str:
                p_text = f"⏱ {dur_str}"
            else:
                p_text = "Lossless"

            pw = draw.textlength(p_text, font=f_stat) + 12
            draw.rounded_rectangle([(tx, by), (tx + pw, by + 18)], radius=6, fill=(26, 36, 28, 220))
            draw.text((tx + 6, by + 2), p_text, fill=(134, 239, 172), font=f_stat)

            l_cnt = item.get("likes_count") or 0
            if l_cnt:
                l_text = f"{_format_count(l_cnt)} likes"
            else:
                l_text = "HQ Audio"
            lw = draw.textlength(l_text, font=f_stat) + 12
            lx = tx + pw + 8
            draw.rounded_rectangle([(lx, by), (lx + lw, by + 18)], radius=6, fill=(26, 32, 42, 220))
            draw.text((lx + 6, by + 2), l_text, fill=(56, 189, 248), font=f_stat)

        buf = io.BytesIO()
        base.save(buf, format="PNG", compress_level=1)
        buf.seek(0)
        return buf
    except Exception as e:
        import logging; logging.getLogger("media_card").error(f"scl_search_card error: {e}")
        return None

def make_search_card(platform, query, items):
    if not HAS_PIL: return None
    try:
        p_lower = str(platform).lower()
        if "soundcloud" in p_lower:
            return _make_soundcloud_search_card(query, items)

        if "tiktok" in p_lower:
            brand_title = "TikTok"
            pill_fill = (254, 44, 85)
            dur_bg = (20, 32, 44)
            dur_fg = (0, 242, 234)
            hint_text = "GÕ SỐ (1-N) ĐỂ CHỌN HOẶC 'C' ĐỂ HỦY"
        else: # youtube default
            brand_title = "YouTube Music"
            pill_fill = (255, 0, 0)
            dur_bg = (38, 30, 30)
            dur_fg = (220, 80, 80)
            hint_text = "CHỌN BÀI QUA MENU BÊN DƯỚI"

        W = 760
        ROW_H = 78
        HDR = 68
        N = min(len(items), 10)
        if N <= 0:
            return None
        H = HDR + N * (ROW_H + 10) + 16

        base = Image.new("RGBA", (W, H), (20, 20, 22, 255))
        draw = ImageDraw.Draw(base)

        # Viền ngoài toàn khung
        draw.rounded_rectangle([(4, 4), (W - 4, H - 4)], radius=20, outline=(36, 36, 40), width=1)

        # Fonts
        f_brand = _get_modak_font(26)
        f_hint = _get_regular_font(12)
        f_num = _get_modak_font(18)
        f_title = _get_modak_font(18)
        f_artist = _get_regular_font(13)
        f_dur = _get_regular_font(13, bold=True)

        pad_x = 22

        # 1. Header (Logo + Brand + Hint)
        header_y = 20
        # Logo drawing
        if "tiktok" in p_lower:
            _draw_tt_logo(draw, pad_x, header_y + 4, size=28)
            text_logo_x = pad_x + 36
        elif "soundcloud" in p_lower:
            _draw_sc_logo(draw, pad_x, header_y + 6, size=24)
            text_logo_x = pad_x + 38
        else:
            # YouTube play button
            draw.rounded_rectangle([(pad_x, header_y + 4), (pad_x + 38, header_y + 30)], radius=9, fill=(255, 0, 0))
            draw.polygon([(pad_x + 15, header_y + 11), (pad_x + 15, header_y + 23), (pad_x + 26, header_y + 17)], fill=(255, 255, 255))
            text_logo_x = pad_x + 46

        draw.text((text_logo_x, header_y + 2), brand_title, fill=(255, 255, 255), font=f_brand)

        # Hint text bên phải
        hint_w = draw.textlength(hint_text, font=f_hint)
        draw.text((W - pad_x - hint_w, header_y + 12), hint_text, fill=(130, 130, 130), font=f_hint)

        # 2. Rows
        th_s = 58
        mk = Image.new("L", (th_s, th_s), 0)
        ImageDraw.Draw(mk).rounded_rectangle([0, 0, th_s, th_s], radius=10, fill=255)

        for i, item in enumerate(items[:N]):
            ry = HDR + i * (ROW_H + 10)

            # Container bo góc cho mỗi dòng
            draw.rounded_rectangle([(pad_x, ry), (W - pad_x, ry + ROW_H)], radius=14, fill=(28, 28, 30), outline=(38, 38, 42), width=1)

            # Number Pill tròn/bầu dục
            nx = pad_x + 14
            nw, nh = 44, 34
            ny = ry + (ROW_H - nh) // 2
            draw.rounded_rectangle([(nx, ny), (nx + nw, ny + nh)], radius=12, fill=pill_fill)
            
            num_str = f"{i+1:02d}"
            bb = draw.textbbox((0, 0), num_str, font=f_num)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            draw.text((nx + (nw - tw) / 2 - bb[0], ny + (nh - th) / 2 - bb[1]), num_str, fill=(255, 255, 255), font=f_num)

            # Thumbnail vuông 58x58
            th_x = nx + nw + 12
            th_y = ry + (ROW_H - th_s) // 2
            raw_img = _fetch_img(item.get("thumb_url", ""))
            if not raw_img:
                raw_img = _make_thumb_fallback(platform, th_s, th_s, pill_fill)
            try:
                th_img = ImageOps.fit(raw_img.convert("RGBA"), (th_s, th_s))
                th_img.putalpha(mk)
                base.paste(th_img.convert("RGB"), (th_x, th_y), th_img)
            except Exception:
                draw.rounded_rectangle([(th_x, th_y), (th_x + th_s, th_y + th_s)], radius=10, fill=(35, 35, 38))

            # Duration Badge bên phải
            dur_str = str(item.get("duration", "")).strip() or "0:00"
            dur_w, dur_h = 76, 30
            dur_x = W - pad_x - dur_w - 14
            dur_y = ry + (ROW_H - dur_h) // 2
            draw.rounded_rectangle([(dur_x, dur_y), (dur_x + dur_w, dur_y + dur_h)], radius=8, fill=dur_bg)
            bb_d = draw.textbbox((0, 0), dur_str, font=f_dur)
            dw, dh = bb_d[2] - bb_d[0], bb_d[3] - bb_d[1]
            draw.text((dur_x + (dur_w - dw) / 2 - bb_d[0], dur_y + (dur_h - dh) / 2 - bb_d[1]), dur_str, fill=dur_fg, font=f_dur)

            # Title & Artist Text
            tx = th_x + th_s + 14
            max_w = dur_x - tx - 14

            raw_title = str(item.get("title", "?")).strip()
            disp_title = raw_title
            while draw.textlength(disp_title + "...", font=f_title) > max_w and len(disp_title) > 3:
                disp_title = disp_title[:-1]
            if len(disp_title) < len(raw_title):
                disp_title += "..."

            draw.text((tx, ry + 16), disp_title, fill=(255, 255, 255), font=f_title)

            raw_artist = str(item.get("author") or item.get("uploader") or "Unknown").strip()
            disp_artist = raw_artist
            while draw.textlength(disp_artist + "...", font=f_artist) > max_w and len(disp_artist) > 3:
                disp_artist = disp_artist[:-1]
            if len(disp_artist) < len(raw_artist):
                disp_artist += "..."

            draw.text((tx, ry + 44), disp_artist, fill=(160, 160, 165), font=f_artist)

        buf = io.BytesIO()
        base.save(buf, format="PNG", compress_level=1)
        buf.seek(0)
        return buf
    except Exception as e:
        import logging; logging.getLogger("media_card").error(f"search_card error: {e}")
        return None

def _draw_player_controls(draw, cx, cy, accent, is_paused=False):
    """Vẽ cụm điều khiển media: Previous, Big Play/Pause Button, Next"""
    # 1. Previous Button (|◀◀) at cx - 80
    px = cx - 80
    # Left bar
    draw.rounded_rectangle([px - 14, cy - 8, px - 11, cy + 8], radius=1, fill=(200, 205, 215))
    # Two left triangles
    draw.polygon([(px - 10, cy), (px - 2, cy - 8), (px - 2, cy + 8)], fill=(200, 205, 215))
    draw.polygon([(px - 2, cy), (px + 6, cy - 8), (px + 6, cy + 8)], fill=(200, 205, 215))

    # 2. Main Play/Pause Button (54px circle) at cx
    r = 27
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)
    if is_paused:
        # Play triangle
        draw.polygon([(cx - 7, cy - 10), (cx - 7, cy + 10), (cx + 9, cy)], fill=(255, 255, 255))
    else:
        # Pause bars (two rounded pills)
        draw.rounded_rectangle([cx - 7, cy - 9, cx - 3, cy + 9], radius=2, fill=(255, 255, 255))
        draw.rounded_rectangle([cx + 3, cy - 9, cx + 7, cy + 9], radius=2, fill=(255, 255, 255))

    # 3. Next Button (▶▶|) at cx + 80
    nx = cx + 80
    # Two right triangles
    draw.polygon([(nx - 6, cy - 8), (nx - 6, cy + 8), (nx + 2, cy)], fill=(200, 205, 215))
    draw.polygon([(nx + 2, cy - 8), (nx + 2, cy + 8), (nx + 10, cy)], fill=(200, 205, 215))
    # Right bar
    draw.rounded_rectangle([nx + 11, cy - 8, nx + 14, cy + 8], radius=1, fill=(200, 205, 215))

def make_nowplaying_card(platform, title, author, duration, thumb_url, channel_name="", engine=""):
    if not HAS_PIL: return None
    try:
        meta = PLATFORM_META.get(platform, PLATFORM_META["youtube"])
        accent = meta["accent"]
        W, H = 880, 440

        # Tải ảnh thumbnail gốc
        ti = _fetch_img(thumb_url)
        if not ti:
            ti = _make_thumb_fallback(platform, 250, 250, accent)

        # 1. Background: Biến thumbnail gốc thành toàn bộ Background làm mờ RÕ RỆT (Cinematic Bokeh Backdrop)
        bg_clean = _crop_black_bars(ti) if ti else ti
        bg_raw = ImageOps.fit(bg_clean, (W, H), Image.Resampling.BILINEAR)
        # Làm mờ mịn màng nhưng giữ lại rõ hình khối và màu sắc rực rỡ của MV/bài hát
        bg_blur = bg_raw.resize((160, 80), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(5)).resize((W, H), Image.Resampling.BICUBIC)
        # Giữ độ sáng và độ rực rỡ cao để thấy rõ hình ảnh nền mờ
        bg_tinted = ImageEnhance.Brightness(bg_blur).enhance(0.65).convert("RGB")
        # Phủ một lớp kính mờ mỏng (25% opacity) để chữ trắng nổi bật mà nền vẫn sáng rõ
        dark_glass = Image.new("RGB", (W, H), (18, 18, 22))
        bg = Image.blend(bg_tinted, dark_glass, 0.28)

        # Bo tròn góc toàn bộ card theo khung viền radius=28
        card_mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(card_mask).rounded_rectangle([0, 0, W, H], radius=28, fill=255)
        final_canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        final_canvas.paste(bg.convert("RGBA"), (0, 0), card_mask)
        bg = final_canvas.convert("RGB")

        # 2. Khung viền chính bo góc ngoài (Accent outline)
        draw = ImageDraw.Draw(bg)
        draw.rounded_rectangle([1, 1, W - 2, H - 2], radius=28, outline=accent, width=2)

        # 3. Left Section: THUMBNAIL TRÒN TINH GỌN (+ ĐĨA THAN BÊN CẠNH CHO SOUNDCLOUD)
        C = 236
        cx = 54
        cy = (H - C) // 2  # 102

        # ── RIÊNG SOUNDCLOUD: Đĩa than Vinyl cổ điển ló ra ở bên cạnh như cũ ──
        if platform == "soundcloud":
            disc_dia = 224
            disc_cx = cx + C - 20
            disc_cy = cy + C // 2
            disc_box = [disc_cx - disc_dia//2, disc_cy - disc_dia//2, disc_cx + disc_dia//2, disc_cy + disc_dia//2]
            
            # Thân đĩa than đen bóng
            draw.ellipse(disc_box, fill=(20, 20, 24), outline=(45, 45, 52), width=2)
            # Rãnh đĩa đồng tâm
            for gr in [95, 80, 65, 50]:
                draw.ellipse([disc_cx - gr, disc_cy - gr, disc_cx + gr, disc_cy + gr], outline=(34, 34, 39), width=1)
            # Nhãn đĩa màu cam rực ở tâm đĩa than
            lr = 36
            draw.ellipse([disc_cx - lr, disc_cy - lr, disc_cx + lr, disc_cy + lr], fill=accent)
            # Vòng kim loại bóng quanh nhãn
            draw.ellipse([disc_cx - lr + 5, disc_cy - lr + 5, disc_cx + lr - 5, disc_cy + lr - 5], outline=(255, 255, 255, 70), width=1)
            # Lỗ trục đĩa
            shr = 10
            draw.ellipse([disc_cx - shr, disc_cy - shr, disc_cx + shr, disc_cy + shr], fill=(16, 17, 20))

        # Thumbnail tròn hoàn hảo đè lên nửa trái của đĩa than (Tự động xén sạch viền đen)
        try:
            ti_clean = _crop_black_bars(ti)
            cov = ImageOps.fit(ti_clean, (C, C), Image.Resampling.LANCZOS)
            circle_mask = Image.new("L", (C, C), 0)
            ImageDraw.Draw(circle_mask).ellipse([0, 0, C, C], fill=255)
            
            circle_img = Image.new("RGBA", (C, C), (0, 0, 0, 0))
            circle_img.paste(cov.convert("RGBA"), (0, 0), circle_mask)
            bg.paste(circle_img, (cx, cy), circle_img)

            # Viền tròn thanh mảnh, sạch sẽ (Clean 1.5px border)
            draw.ellipse([cx, cy, cx + C, cy + C], outline=(255, 255, 255, 75), width=2)
        except Exception:
            draw.ellipse([cx, cy, cx + C, cy + C], fill=(35, 35, 40), outline=accent, width=2)

        # 4. Right Section: BÙNG NỔ Ý TƯỞNG TẠI KHU VỰC ĐIỀU KHIỂN & NỘI DUNG
        TX = cx + C + 46
        TW = W - TX - 44

        # ── BÙNG NỔ 1: Header Platform + Huy Hiệu HI-RES LOSSLESS Audio góc trên ──
        head_y = 62
        fn = LOGO_DRAWERS.get(platform)
        if fn:
            fn(draw, TX, head_y, size=24)
        
        platform_names = {
            "youtube": "YouTube Music",
            "soundcloud": "SoundCloud",
            "tiktok": "TikTok Music"
        }
        brand_name = platform_names.get(platform, "Music Player")
        f_brand = _get_modak_font(20)
        draw.text((TX + 46, head_y + 1), brand_name, fill=(255, 255, 255), font=f_brand)

        # Capsule Badge "HI-RES AUDIO 24-BIT" phát sáng góc trên bên phải
        # ── BÙNG NỔ 1: Header Platform + Huy Hiệu Đặc Trưng Riêng Cho Từng Nền Tảng ──
        head_y = 62
        fn = LOGO_DRAWERS.get(platform)
        if fn:
            fn(draw, TX, head_y, size=24)
        
        platform_names = {
            "youtube": "YouTube Music",
            "soundcloud": "SoundCloud",
            "tiktok": "TikTok Music"
        }
        brand_name = platform_names.get(platform, "Music Player")
        f_brand = _get_modak_font(20)
        draw.text((TX + 46, head_y + 1), brand_name, fill=(255, 255, 255), font=f_brand)

        # Huy hiệu góc trên bên phải riêng biệt từng nền tảng
        f_badge_pill = _get_regular_font(11, bold=True)
        if platform == "soundcloud":
            pill_txt = "● 24-BIT LOSSLESS"
            pill_col = (255, 120, 40)
        elif platform == "youtube":
            pill_txt = "● PREMIUM STEREO"
            pill_col = (255, 50, 50)
        else: # tiktok
            pill_txt = "⚡ VIRAL BEAT"
            pill_col = (0, 242, 254)

        pill_w = draw.textlength(pill_txt, font=f_badge_pill) + 16
        pill_x = W - 40 - pill_w
        pill_y = head_y + 1
        draw.rounded_rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + 22], radius=11, fill=(24, 26, 32), outline=pill_col, width=1)
        draw.text((pill_x + 8, pill_y + 3), pill_txt, fill=pill_col, font=f_badge_pill)

        # ── BÙNG NỔ 2: Title bài hát sạch sẽ, to rõ với font Modak ──
        clean_title = re.sub(r'\[.*?\]|\(.*?\)', '', str(title))
        if '|' in clean_title:
            clean_title = clean_title.split('|')[0]
        clean_title = clean_title.strip() or str(title).strip()

        font_size = 32 if len(clean_title) <= 24 else 27
        f_title = _get_modak_font(font_size)
        disp_title = clean_title
        while f_title and draw.textlength(disp_title, font=f_title) > TW and len(disp_title) > 6:
            disp_title = disp_title[:-4] + "..."
        draw.text((TX, head_y + 44), disp_title, fill=(255, 255, 255), font=f_title)

        # Author / Ca sĩ kèm icon Verified
        f_author = _get_regular_font(18)
        author_text = author if author else (channel_name if channel_name else "Unknown Artist")
        draw.text((TX, head_y + 92), _trunc(author_text, 36) + "  ✓", fill=(185, 190, 200), font=f_author)

        # ── BÙNG NỔ 3: KIỂU ÂM THANH KHÁC BIỆT THEO TỪNG NỀN TẢNG ──
        wf_y = head_y + 138

        if platform == "soundcloud":
            # ── 1. SOUNDCLOUD: GIỮ NGUYÊN DẢI SÓNG ÂM WAVEFORM 28 CỘT KINH ĐIỂN ──
            wf_bars = [6, 12, 18, 10, 22, 28, 16, 24, 32, 20, 14, 26, 30, 18, 22, 34, 28, 16, 24, 18, 12, 20, 14, 8, 16, 12, 6, 10]
            col_w = int(TW / len(wf_bars))
            for i, bh in enumerate(wf_bars):
                bx = TX + i * col_w
                is_active = (i / len(wf_bars)) <= 0.28
                b_color = accent if is_active else (65, 68, 76)
                draw.rounded_rectangle([bx, wf_y + (36 - bh), bx + col_w - 3, wf_y + 36], radius=2, fill=b_color)

        elif platform == "youtube":
            # ── 2. YOUTUBE MUSIC: STUDIO EQUALIZER SPECTRUM (Đa băng tần phòng thu) ──
            # 16 cột tần số Bass - Mid - Treble với các nấc LED phân tầng chuyên nghiệp
            eq_heights = [18, 26, 34, 30, 22, 28, 36, 32, 24, 30, 26, 20, 28, 22, 16, 12]
            eq_w = int(TW / len(eq_heights))
            for i, eh in enumerate(eq_heights):
                bx = TX + i * eq_w
                is_active = (i / len(eq_heights)) <= 0.28
                # Vẽ các phân đoạn LED pixel xếp chồng (mỗi block 5px)
                num_blocks = max(2, eh // 6)
                for b_idx in range(num_blocks):
                    block_y = wf_y + 36 - (b_idx + 1) * 6
                    if is_active:
                        block_col = (255, 230, 230) if b_idx == num_blocks - 1 else (255, 30, 30)
                    else:
                        block_col = (60, 62, 70)
                    draw.rounded_rectangle([bx, block_y, bx + eq_w - 4, block_y + 4], radius=1, fill=block_col)

        else: # tiktok
            # ── 3. TIKTOK MUSIC: CYBERPUNK BEAT-DROP PULSE (Sóng nhịp Cyan & Pink đan xen) ──
            # Dãy sóng nhịp đối xứng đập theo bass với màu Neon kép
            tt_bars = [8, 14, 24, 34, 20, 10, 16, 30, 38, 26, 14, 22, 32, 20, 12, 18, 28, 36, 18, 8]
            tt_w = int(TW / len(tt_bars))
            for i, bh in enumerate(tt_bars):
                bx = TX + i * tt_w
                is_active = (i / len(tt_bars)) <= 0.28
                # Xen kẽ màu Neon Cyan và Pink theo phong cách TikTok Glitch
                neon_color = (0, 242, 254) if i % 2 == 0 else (254, 44, 85)
                bar_col = neon_color if is_active else (55, 58, 66)
                # Cột sóng nhịp nở từ tâm ra hai phía
                half = bh // 2
                draw.rounded_rectangle([bx, wf_y + 18 - half, bx + tt_w - 3, wf_y + 18 + half], radius=2, fill=bar_col)

        # Thanh Progress Bar chuẩn mockup
        pb_y = wf_y + 44
        pb_w = TW
        pb_h = 5
        draw.rounded_rectangle([TX, pb_y, TX + pb_w, pb_y + pb_h], radius=3, fill=(52, 54, 60))
        progress_ratio = 0.28
        fw = max(10, int(pb_w * progress_ratio))
        draw.rounded_rectangle([TX, pb_y, TX + fw, pb_y + pb_h], radius=3, fill=accent)
        # Nút tròn scrubber
        knob_r = 7
        draw.ellipse([TX + fw - knob_r, pb_y + pb_h//2 - knob_r, TX + fw + knob_r, pb_y + pb_h//2 + knob_r], fill=(255, 255, 255))

        # Timestamps dưới progress bar
        f_time = _get_regular_font(15, bold=True)
        draw.text((TX, pb_y + 14), "00:45", fill=(170, 175, 185), font=f_time)
        dur_text = duration if duration else "3:52"
        dw = draw.textlength(dur_text, font=f_time)
        draw.text((TX + pb_w - dw, pb_y + 14), dur_text, fill=(170, 175, 185), font=f_time)

        # ── BÙNG NỔ 4: Controls Full Studio (Shuffle 🔀, Previous, Big Pause, Next, Repeat 🔁) ──
        ctrl_cx = TX + pb_w // 2
        ctrl_cy = pb_y + 54

        # Nút Shuffle 🔀 bên trái
        shuf_x = ctrl_cx - 140
        draw.text((shuf_x - 10, ctrl_cy - 10), "🔀", fill=(140, 145, 155), font=_get_regular_font(16))

        # Nút Previous |◀◀, Big Pause, Next ▶▶|
        _draw_player_controls(draw, ctrl_cx, ctrl_cy, accent, is_paused=False)

        # Nút Repeat 🔁 bên phải
        rep_x = ctrl_cx + 140
        draw.text((rep_x - 10, ctrl_cy - 10), "🔁", fill=(140, 145, 155), font=_get_regular_font(16))

        # Trả về BytesIO siêu tốc (sub-5ms, không tốn CPU)
        buf = io.BytesIO()
        bg.save(buf, format="PNG", compress_level=1)
        buf.seek(0)
        return buf
    except Exception as e:
        import logging; logging.getLogger("media_card").error(f"nowplaying_card: {e}")
        return None


async def async_search_card(platform, query, items):
    loop=asyncio.get_event_loop()
    return await loop.run_in_executor(None, make_search_card, platform, query, items)

async def async_nowplaying_card(platform, title, author, duration, thumb_url, channel_name="", engine=""):
    loop=asyncio.get_event_loop()
    return await loop.run_in_executor(None, make_nowplaying_card, platform, title, author, duration, thumb_url, channel_name, engine)



from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageEnhance
import io, os, random
from apps.shared.paths import SHARED_FONTS_DIR, SHARED_BACKGROUNDS_DIR

font_bold_path = str(SHARED_FONTS_DIR / "BeVietnamPro-Bold.ttf")
font_reg_path = str(SHARED_FONTS_DIR / "BeVietnamPro-Regular.ttf")

def _get_font(bold: bool, size: int):
    p = font_bold_path if bold else font_reg_path
    try:
        return ImageFont.truetype(p, size)
    except Exception:
        return ImageFont.load_default()

def draw_supersampled_rounded_box(w, h, radius, fill, outline=None, outline_w=1, scale=3):
    sw, sh = w * scale, h * scale
    sr = radius * scale
    s_out_w = outline_w * scale if outline else 0
    img = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([(0, 0), (sw - 1, sh - 1)], radius=sr, fill=fill, outline=outline, width=s_out_w)
    return img.resize((w, h), Image.Resampling.LANCZOS)

def draw_yt_logo_hires(size=44):
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0,0,0,0))
    d = ImageDraw.Draw(im)
    w, h = int(s * 0.96), int(s * 0.68)
    x = (s - w) // 2
    y = (s - h) // 2
    r = int(h * 0.30)
    d.rounded_rectangle([(x, y), (x + w, y + h)], radius=r, fill=(255, 0, 0, 255))
    cx, cy = s // 2, s // 2
    pw = int(w * 0.28)
    ph = int(h * 0.38)
    pts = [(cx - pw//2 + 4, cy - ph), (cx - pw//2 + 4, cy + ph), (cx + pw, cy)]
    d.polygon(pts, fill=(255, 255, 255, 255))
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_sc_logo_hires(size=44):
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0,0,0,0))
    d = ImageDraw.Draw(im)
    o = (255, 85, 0, 255)
    cx, cy = int(s * 0.65), int(s * 0.42)
    r = int(s * 0.28)
    d.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=o)
    cx2, cy2 = int(s * 0.82), int(s * 0.58)
    r2 = int(s * 0.16)
    d.ellipse([(cx2 - r2, cy2 - r2), (cx2 + r2, cy2 + r2)], fill=o)
    d.rectangle([(int(s * 0.48), int(s * 0.42)), (int(s * 0.85), int(s * 0.74))], fill=o)
    bar_x_start = int(s * 0.12)
    bar_w = int(s * 0.05)
    gap = int(s * 0.035)
    bar_bottom = int(s * 0.74)
    heights = [0.20, 0.35, 0.50, 0.60]
    for i, h_factor in enumerate(heights):
        bx = bar_x_start + i * (bar_w + gap)
        bh = int(s * h_factor)
        by = bar_bottom - bh
        d.rounded_rectangle([(bx, by), (bx + bar_w, bar_bottom)], radius=bar_w//2, fill=o)
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_tt_logo_hires(size=44):
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0,0,0,0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([(0, 0), (s-1, s-1)], radius=int(s*0.24), fill=(10, 10, 15, 255))
    cx, cy = s // 2, s // 2
    def draw_note(offset_x, offset_y, col):
        head_x, head_y = cx - int(s*0.14) + offset_x, cy + int(s*0.14) + offset_y
        hrx, hry = int(s*0.14), int(s*0.11)
        d.ellipse([(head_x - hrx, head_y - hry), (head_x + hrx, head_y + hry)], fill=col)
        stem_x = head_x + hrx - int(s*0.04)
        stem_top = cy - int(s*0.28) + offset_y
        stem_w = int(s*0.075)
        d.rectangle([(stem_x, stem_top), (stem_x + stem_w, head_y)], fill=col)
        fx, fy = stem_x + stem_w, stem_top
        fw, fh = int(s*0.22), int(s*0.26)
        d.arc([(fx - int(s*0.12), fy), (fx + fw, fy + fh*2)], start=270, end=360, fill=col, width=stem_w)

    draw_note(int(s*0.03), int(s*0.01), (254, 44, 85, 255))
    draw_note(-int(s*0.03), -int(s*0.01), (37, 244, 238, 255))
    draw_note(0, 0, (255, 255, 255, 255))
    return im.resize((size, size), Image.Resampling.LANCZOS)


def draw_dipre_crest_logo_hires(size=44):
    """Logo DIPRE chính chủ (Cubic Bezier Liquid Mercury D + tâm ngọc #1FCAAD)."""
    scale = 4
    cs = size * scale
    im = Image.new("RGBA", (cs, cs), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def sc(x, y):
        return (x / 64.0 * cs, y / 64.0 * cs)

    def cubic(p0, p1, p2, p3, steps=18):
        pts = []
        for i in range(1, steps + 1):
            t = i / steps
            mt = 1.0 - t
            pts.append(sc(
                mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0],
                mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1],
            ))
        return pts

    pad = cs * 0.04
    d.rounded_rectangle([pad, pad, cs - pad, cs - pad], radius=int(cs * 0.24), fill=(9, 9, 13, 250), outline=(31, 202, 173, 195), width=max(2, int(cs * 0.028)))
    m_pts = [sc(14, 51.5)] + cubic((14, 51.5), (20.5, 56.2), (33.5, 57.2), (42.8, 53)) + cubic((42.8, 53), (50.5, 49.4), (54.5, 42.2), (54.5, 34.2)) + cubic((54.5, 34.2), (51.6, 41.4), (44.5, 46.8), (34.8, 47.6)) + cubic((34.8, 47.6), (26.5, 48.3), (20, 47.2), (14, 51.5))
    d.polygon(m_pts, fill=(120, 120, 132, 245))
    p_pts = [sc(14.5, 47.5)] + cubic((14.5, 47.5), (11.2, 35), (12.5, 16.5), (20.5, 10.5)) + cubic((20.5, 10.5), (26, 6.4), (36, 6.8), (44, 11.5)) + cubic((44, 11.5), (51.5, 16), (55.2, 24), (54.2, 33)) + cubic((54.2, 33), (53.2, 41), (47.5, 46.8), (40, 48.6)) + cubic((40, 48.6), (45.5, 42.8), (46.8, 34), (44.2, 26.5)) + cubic((44.2, 26.5), (41.5, 19.2), (34.2, 15.8), (27, 17.2)) + cubic((27, 17.2), (21.2, 18.4), (19.2, 25), (19.6, 34.8)) + cubic((19.6, 34.8), (19.8, 40.5), (17.5, 45.2), (14.5, 47.5))
    d.polygon(p_pts, fill=(250, 250, 252, 255))
    cx, cy = sc(31.5, 32.2)
    cr = 6.5 / 64.0 * cs
    d.ellipse([cx - cr * 1.2, cy - cr * 1.2, cx + cr * 1.2, cy + cr * 1.2], fill=(31, 202, 173, 80))
    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(31, 202, 173, 255))
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_genesis_logo_hires(size=44):
    """Logo GENESIS: lốc xoáy DNA (2 sợi Neon Cyan/Tím + rung ngang) trong badge bo góc."""
    import math
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([(0, 0), (s - 1, s - 1)], radius=int(s * 0.24), fill=(16, 20, 34, 255))
    cx = s // 2
    amp = int(s * 0.20)
    top, bot = int(s * 0.14), int(s * 0.86)
    strand_w = max(1, int(s * 0.045))
    col_a, col_b = (0, 242, 234, 255), (153, 102, 255, 255)
    prev_a = prev_b = None
    rung_step = max(2, int(s * 0.16))
    for y in range(top, bot):
        ph = (y - top) / (bot - top) * math.pi * 2.2
        xa = cx + amp * math.sin(ph)
        xb = cx - amp * math.sin(ph)
        if prev_a:
            d.line([prev_a, (xa, y)], fill=col_a, width=strand_w)
        if prev_b:
            d.line([prev_b, (xb, y)], fill=col_b, width=strand_w)
        if (y - top) % rung_step < 1:
            d.line([(xa, y), (xb, y)], fill=(255, 255, 255, 160), width=max(1, int(s * 0.018)))
        prev_a, prev_b = (xa, y), (xb, y)
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_trash_logo_hires(size=44):
    """Logo DELETE / PURGE: Thùng rác Neon Red trong badge bo góc."""
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([(0, 0), (s - 1, s - 1)], radius=int(s * 0.24), fill=(32, 16, 22, 255))
    cx = s // 2
    top_y = int(s * 0.28)
    lid_w = int(s * 0.54)
    d.line([(cx - lid_w // 2, top_y), (cx + lid_w // 2, top_y)], fill=(239, 68, 68, 255), width=max(1, int(s * 0.05)))
    handle_w = int(s * 0.22)
    d.arc([(cx - handle_w // 2, top_y - int(s * 0.12)), (cx + handle_w // 2, top_y)], start=180, end=360, fill=(239, 68, 68, 255), width=max(1, int(s * 0.04)))
    body_top = top_y + max(2, int(s * 0.06))
    body_bot = int(s * 0.78)
    body_tw = int(s * 0.44)
    body_bw = int(s * 0.34)
    pts = [
        (cx - body_tw // 2, body_top),
        (cx + body_tw // 2, body_top),
        (cx + body_bw // 2, body_bot),
        (cx - body_bw // 2, body_bot)
    ]
    d.polygon(pts, fill=(239, 68, 68, 60), outline=(239, 68, 68, 255))
    for ox in (-int(s * 0.08), 0, int(s * 0.08)):
        d.line([(cx + ox, body_top + int(s * 0.08)), (cx + int(ox * 0.8), body_bot - int(s * 0.08))], fill=(255, 255, 255, 200), width=max(1, int(s * 0.03)))
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_activity_logo_hires(size=44):
    """Logo ACTIVITY / PRESENCE: Tay cầm Gamepad Neon Purple trong badge bo góc."""
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([(0, 0), (s - 1, s - 1)], radius=int(s * 0.24), fill=(24, 16, 36, 255))
    cx, cy = s // 2, s // 2
    # Thân tay cầm Gamepad
    gw, gh = int(s * 0.62), int(s * 0.38)
    gx1, gy1 = cx - gw // 2, cy - gh // 2
    d.rounded_rectangle([(gx1, gy1), (gx1 + gw, gy1 + gh)], radius=int(gh * 0.45), fill=(168, 85, 247, 50), outline=(168, 85, 247, 255), width=max(1, int(s * 0.035)))
    # D-pad (Dấu cộng bên trái)
    dpx, dpy = gx1 + int(gw * 0.26), cy
    dsz = int(s * 0.07)
    d.line([(dpx - dsz, dpy), (dpx + dsz, dpy)], fill=(255, 255, 255, 220), width=max(1, int(s * 0.04)))
    d.line([(dpx, dpy - dsz), (dpx, dpy + dsz)], fill=(255, 255, 255, 220), width=max(1, int(s * 0.04)))
    # Nút bấm bên phải (4 chấm)
    abx, aby = gx1 + int(gw * 0.74), cy
    asz = int(s * 0.05)
    for ox, oy, col in ((-asz, 0, (239, 68, 68)), (asz, 0, (59, 130, 246)), (0, -asz, (234, 179, 8)), (0, asz, (34, 197, 94))):
        d.ellipse([(abx + ox - 2, aby + oy - 2), (abx + ox + 2, aby + oy + 2)], fill=col)
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_afk_logo_hires(size=44):
    """Logo AFK: Trăng khuyết và chữ Zzz Neon Blue trong badge bo góc."""
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([(0, 0), (s - 1, s - 1)], radius=int(s * 0.24), fill=(16, 24, 44, 255))
    cx, cy = s // 2, s // 2
    # Trăng khuyết (Moon crescent)
    mr = int(s * 0.28)
    mx, my = cx - int(s * 0.08), cy + int(s * 0.04)
    # Vẽ vòng tròn mặt trăng
    moon = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    md = ImageDraw.Draw(moon)
    md.ellipse([(mx - mr, my - mr), (mx + mr, my + mr)], fill=(59, 130, 246, 255))
    # Khuyết bằng vòng tròn cắt
    md.ellipse([(mx - mr + int(s * 0.16), my - mr - int(s * 0.08)), (mx + mr + int(s * 0.16), my + mr - int(s * 0.08))], fill=(0, 0, 0, 0))
    im = Image.alpha_composite(im, moon)
    d = ImageDraw.Draw(im)
    # Các ngôi sao nhỏ / tia sáng
    d.ellipse([(cx + int(s * 0.16), cy - int(s * 0.22)), (cx + int(s * 0.22), cy - int(s * 0.16))], fill=(147, 197, 253, 240))
    d.ellipse([(cx + int(s * 0.26), cy - int(s * 0.08)), (cx + int(s * 0.30), cy - int(s * 0.04))], fill=(191, 219, 254, 200))
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_read_logo_hires(size=44):
    """Logo READ / NOTIFICATION ACK: Phong bì thư mở Neon Emerald trong badge bo góc."""
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([(0, 0), (s - 1, s - 1)], radius=int(s * 0.24), fill=(12, 28, 24, 255))
    cx, cy = s // 2, s // 2
    ew, eh = int(s * 0.64), int(s * 0.44)
    ex1, ey1 = cx - ew // 2, cy - eh // 2 + int(s * 0.04)
    ex2, ey2 = ex1 + ew, ey1 + eh
    d.rounded_rectangle([(ex1, ey1), (ex2, ey2)], radius=int(s * 0.08), fill=(52, 211, 153, 60), outline=(52, 211, 153, 255), width=max(1, int(s * 0.035)))
    d.line([(ex1, ey1), (cx, cy + int(s * 0.06)), (ex2, ey1)], fill=(255, 255, 255, 220), width=max(1, int(s * 0.035)))
    # Dấu check mark xanh ngọc
    ck_cx, ck_cy = cx + int(s * 0.16), cy - int(s * 0.16)
    cr = int(s * 0.12)
    d.ellipse([(ck_cx - cr, ck_cy - cr), (ck_cx + cr, ck_cy + cr)], fill=(16, 185, 129, 255))
    d.line([(ck_cx - int(cr * 0.45), ck_cy), (ck_cx - int(cr * 0.1), ck_cy + int(cr * 0.4)), (ck_cx + int(cr * 0.5), ck_cy - int(cr * 0.4))],
           fill=(255, 255, 255, 255), width=max(1, int(s * 0.035)))
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_info_logo_hires(size=44):
    """Logo INFO: Biểu tượng chữ i Neon Sky Blue trong badge bo góc tròn."""
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([(0, 0), (s - 1, s - 1)], radius=int(s * 0.24), fill=(12, 24, 38, 255))
    cx, cy = s // 2, s // 2
    r = int(s * 0.32)
    d.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(56, 189, 248, 50), outline=(56, 189, 248, 255), width=max(1, int(s * 0.035)))
    # Chấm chữ i
    dot_r = max(2, int(s * 0.045))
    # Thân chữ i
    d.rounded_rectangle([(cx - dot_r, cy - int(s * 0.04)), (cx + dot_r, cy + int(s * 0.17))], radius=dot_r, fill=(255, 255, 255, 240))
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_voice_logo_hires(size=44):
    """Logo VOICE: Tai nghe & sóng âm Neon Emerald trong badge bo góc."""
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([(0, 0), (s - 1, s - 1)], radius=int(s * 0.24), fill=(16, 32, 28, 255))
    cx, cy = s // 2, s // 2
    r = int(s * 0.28)
    # Vòm tai nghe
    d.arc([(cx - r, cy - r), (cx + r, cy + r)], start=180, end=360, fill=(74, 222, 128, 255), width=max(2, int(s * 0.05)))
    # 2 củ tai nghe
    ew, eh = int(s * 0.12), int(s * 0.24)
    d.rounded_rectangle([(cx - r - ew // 2, cy), (cx - r + ew // 2, cy + eh)], radius=int(ew * 0.4), fill=(34, 197, 94, 255))
    d.rounded_rectangle([(cx + r - ew // 2, cy), (cx + r + ew // 2, cy + eh)], radius=int(ew * 0.4), fill=(34, 197, 94, 255))
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_alias_logo_hires(size=44):
    """Logo ALIAS: Biểu tượng thẻ tag bí danh lệnh Hồng Neon / Tím Pha Lê."""
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([(0, 0), (s - 1, s - 1)], radius=int(s * 0.24), fill=(36, 16, 32, 255))
    cx, cy = s // 2, s // 2
    # Thẻ Tag
    tw, th = int(s * 0.46), int(s * 0.32)
    d.rounded_rectangle([(cx - tw // 2, cy - th // 2), (cx + tw // 2, cy + th // 2)], radius=int(s * 0.08), fill=(236, 72, 153, 50), outline=(236, 72, 153, 255), width=max(1, int(s * 0.035)))
    # Lỗ tag
    lr = max(2, int(s * 0.04))
    d.ellipse([(cx - tw // 2 + int(s * 0.06), cy - lr), (cx - tw // 2 + int(s * 0.06) + lr * 2, cy + lr)], fill=(255, 255, 255, 220))
    # Dấu gạch nhãn lệnh
    d.rounded_rectangle([(cx - int(s * 0.06), cy - int(s * 0.03)), (cx + int(s * 0.14), cy + int(s * 0.03))], radius=max(1, int(s * 0.02)), fill=(255, 255, 255, 240))
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_fb_logo_hires(size=44):
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0,0,0,0))
    d = ImageDraw.Draw(im)
    # Circle xanh FB
    d.ellipse([(2, 2), (s - 3, s - 3)], fill=(24, 119, 242, 255))
    # Chữ f
    fx = int(s * 0.44)
    fy = int(s * 0.22)
    fw = int(s * 0.16)
    # Thân dọc
    d.rectangle([(fx, fy + int(s * 0.16)), (fx + fw, s - 3)], fill=(255, 255, 255, 255))
    # Vòng cong trên
    d.arc([(fx, fy), (fx + fw * 2 + int(s * 0.08), fy + int(s * 0.32))], start=180, end=270, fill=(255, 255, 255, 255), width=fw)
    # Gạch ngang
    d.rectangle([(fx - int(s * 0.12), fy + int(s * 0.25)), (fx + fw + int(s * 0.12), fy + int(s * 0.25) + fw)], fill=(255, 255, 255, 255))
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_ig_logo_hires(size=44):
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0,0,0,0))
    d = ImageDraw.Draw(im)
    # Nền gradient/tím hồng Instagram
    d.rounded_rectangle([(3, 3), (s - 4, s - 4)], radius=int(s * 0.28), fill=(225, 48, 108, 255))
    # Khung camera trắng
    w_cam = int(s * 0.6)
    c_x, c_y = s // 2, s // 2
    d.rounded_rectangle([(c_x - w_cam // 2, c_y - w_cam // 2), (c_x + w_cam // 2, c_y + w_cam // 2)], radius=int(w_cam * 0.28), outline=(255, 255, 255, 255), width=max(1, int(s * 0.05)))
    # Ống kính giữa
    lens_r = int(w_cam * 0.22)
    d.ellipse([(c_x - lens_r, c_y - lens_r), (c_x + lens_r, c_y + lens_r)], outline=(255, 255, 255, 255), width=max(1, int(s * 0.05)))
    # Chấm đèn flash
    dot_r = max(2, int(s * 0.035))
    d.ellipse([(c_x + w_cam // 2 - int(s * 0.12), c_y - w_cam // 2 + int(s * 0.08)), (c_x + w_cam // 2 - int(s * 0.12) + dot_r * 2, c_y - w_cam // 2 + int(s * 0.08) + dot_r * 2)], fill=(255, 255, 255, 255))
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_x_logo_hires(size=44):
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0,0,0,0))
    d = ImageDraw.Draw(im)
    # Nền đen bo góc
    d.rounded_rectangle([(2, 2), (s - 3, s - 3)], radius=int(s * 0.22), fill=(15, 20, 25, 255), outline=(50, 60, 75, 255), width=max(1, int(s * 0.02)))
    # Logo chữ X trắng tối giản sắc nét
    pad = int(s * 0.22)
    d.line([(pad, pad), (s - pad, s - pad)], fill=(255, 255, 255, 255), width=max(2, int(s * 0.08)))
    d.line([(s - pad, pad), (pad, s - pad)], fill=(255, 255, 255, 255), width=max(2, int(s * 0.08)))
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_threads_logo_hires(size=44):
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0,0,0,0))
    d = ImageDraw.Draw(im)
    # Nền đen bo tròn
    d.rounded_rectangle([(2, 2), (s - 3, s - 3)], radius=int(s * 0.25), fill=(10, 10, 10, 255))
    # Vòng xoắn Threads (@ style)
    cx, cy = s // 2, s // 2
    r1 = int(s * 0.26)
    d.ellipse([(cx - r1, cy - r1), (cx + r1, cy + r1)], outline=(255, 255, 255, 255), width=max(2, int(s * 0.06)))
    r2 = int(s * 0.12)
    d.ellipse([(cx - r2, cy - r2), (cx + r2, cy + r2)], fill=(255, 255, 255, 255))
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_vps_logo_hires(size=44):
    """Logo VPS / Terminal: Khung console den voi dau nhac lenh >_ mau Xanh Cyber."""
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # Nen console bo goc
    d.rounded_rectangle([(2, 2), (s - 3, s - 3)], radius=int(s * 0.22), fill=(10, 16, 26, 255), outline=(14, 165, 233, 200), width=max(1, int(s * 0.03)))
    # Thanh tieu de 3 cham tron
    dot_r = max(2, int(s * 0.035))
    d.ellipse([(int(s * 0.16), int(s * 0.18)), (int(s * 0.16) + dot_r * 2, int(s * 0.18) + dot_r * 2)], fill=(239, 68, 68, 255))
    d.ellipse([(int(s * 0.28), int(s * 0.18)), (int(s * 0.28) + dot_r * 2, int(s * 0.18) + dot_r * 2)], fill=(245, 158, 11, 255))
    d.ellipse([(int(s * 0.40), int(s * 0.18)), (int(s * 0.40) + dot_r * 2, int(s * 0.18) + dot_r * 2)], fill=(16, 185, 129, 255))
    # Dau prompt '>'
    p1 = (int(s * 0.18), int(s * 0.44))
    p2 = (int(s * 0.38), int(s * 0.58))
    p3 = (int(s * 0.18), int(s * 0.72))
    d.line([p1, p2, p3], fill=(56, 189, 248, 255), width=max(2, int(s * 0.06)))
    # Dau gach cursor '_'
    c_x1 = int(s * 0.46)
    c_x2 = int(s * 0.78)
    c_y = int(s * 0.72)
    d.line([(c_x1, c_y), (c_x2, c_y)], fill=(56, 189, 248, 255), width=max(2, int(s * 0.06)))
    return im.resize((size, size), Image.Resampling.LANCZOS)

def draw_war_logo_hires(size=44):
    """Logo WAR / VAR: Hai thanh kiem cheo Neon Crimson & Am Khi Chien Tranh."""
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # Khung badge do neon am u
    d.rounded_rectangle([(2, 2), (s - 3, s - 3)], radius=int(s * 0.22), fill=(30, 10, 15, 255), outline=(239, 68, 68, 220), width=max(1, int(s * 0.03)))
    pad = int(s * 0.20)
    # Kiem 1: cheo tu trai tren xuong phai duoi
    d.line([(pad, pad), (s - pad, s - pad)], fill=(248, 113, 113, 255), width=max(2, int(s * 0.065)))
    # Canh kiem 1
    d.line([(pad + int(s * 0.08), pad - int(s * 0.04)), (pad - int(s * 0.04), pad + int(s * 0.08))], fill=(255, 255, 255, 240), width=max(1, int(s * 0.045)))
    # Kiem 2: cheo tu phai tren xuong trai duoi
    d.line([(s - pad, pad), (pad, s - pad)], fill=(239, 68, 68, 255), width=max(2, int(s * 0.065)))
    # Canh kiem 2
    d.line([(s - pad - int(s * 0.08), pad - int(s * 0.04)), (s - pad + int(s * 0.04), pad + int(s * 0.08))], fill=(255, 255, 255, 240), width=max(1, int(s * 0.045)))
    # Cham toa sang trung tam
    cx, cy = s // 2, s // 2
    cr = int(s * 0.06)
    d.ellipse([(cx - cr, cy - cr), (cx + cr, cy + cr)], fill=(255, 255, 255, 250))
    return im.resize((size, size), Image.Resampling.LANCZOS)




# ─── PLATFORM_CONFIG: proxy sang card_registry ───────────────────────────────
# Không còn hardcode ở đây. Mỗi module tự register qua card_registry.
# Để backward-compat, PLATFORM_CONFIG vẫn là một dict-like object proxy.

class _RegistryProxy(dict):
    """Dict proxy lazily đọc từ card_registry khi cần."""
    def __getitem__(self, key):
        try:
            from apps.user_discord.utils.card_registry import get_card, get_registry
        except ImportError:
            from utils.card_registry import get_card, get_registry  # type: ignore
        val = get_card(key)
        if val is not None:
            return val
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        try:
            self[key]
            return True
        except KeyError:
            return False

    def keys(self):
        try:
            from apps.user_discord.utils.card_registry import all_keys
        except ImportError:
            from utils.card_registry import all_keys  # type: ignore
        return all_keys()

    def items(self):
        try:
            from apps.user_discord.utils.card_registry import get_registry
        except ImportError:
            from utils.card_registry import get_registry  # type: ignore
        return get_registry().items()

    def values(self):
        try:
            from apps.user_discord.utils.card_registry import get_registry
        except ImportError:
            from utils.card_registry import get_registry  # type: ignore
        return get_registry().values()


PLATFORM_CONFIG = _RegistryProxy()

# HACK: ensure voice key present as "voice" — trigger bootstrap nếu chưa load
try:
    from apps.user_discord.utils import default_cards as _dc  # noqa: F401
except ImportError:
    try:
        from utils import default_cards as _dc  # type: ignore  # noqa: F401
    except ImportError:
        pass

# Legacy: keep "voice" as minimal fallback nếu registry vẫn trống
def _ensure_fallback():
    try:
        from apps.user_discord.utils.card_registry import get_card
    except ImportError:
        from utils.card_registry import get_card  # type: ignore
    if get_card("voice") is None:
        # Registry chưa load được — dùng dict tĩnh tối giản
        pass

# ─── NOTE: Toàn bộ data lệnh (title, sub, items, tip, logo_fn...) giờ sống trong:
#   apps/user_discord/utils/default_cards.py  (khai báo mặc định)
#   apps/user_discord/utils/card_registry.py  (registry API)
#
# Để thêm/sửa card cho module mới:
#   from apps.user_discord.utils.card_registry import register_card, CardSchema
#   register_card("mymod", CardSchema(title=..., items=[...], ...))
# ─────────────────────────────────────────────────────────────────────────────

_HELP_CARD_CACHE = {}



def render_premium_help_card(platform: str, prefix: str = "!") -> io.BytesIO:
    """Bảng lệnh LIQUID GLASS (ngang) siêu tốc độ. >6 lệnh -> 2 cột. Lỗi -> fallback bản cũ."""
    cache_key = (str(platform).lower(), str(prefix))
    if cache_key in _HELP_CARD_CACHE:
        buf = io.BytesIO(_HELP_CARD_CACHE[cache_key])
        buf.seek(0)
        return buf

    try:
        buf = _render_help_card_glass(platform, prefix)
        _HELP_CARD_CACHE[cache_key] = buf.getvalue()
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"[help_card] liquid glass lỗi, dùng bản cũ: {type(e).__name__}: {e}")
        buf = _render_premium_help_card_legacy(platform, prefix)
        _HELP_CARD_CACHE[cache_key] = buf.getvalue()
        buf.seek(0)
        return buf


def _render_help_card_glass(platform: str, prefix: str = "!") -> io.BytesIO:
    try:
        from apps.user_discord.utils import glass as G
    except ImportError:
        from utils import glass as G
    cfg = PLATFORM_CONFIG.get(platform, PLATFORM_CONFIG["youtube"])
    items = list(cfg.get("items", []))
    n = max(1, len(items))
    accent = tuple(cfg["accent"][:3])
    dark = tuple(max(0, int(v * 0.5)) for v in accent)
    grad = (accent, dark)

    two_cols = n > 6
    pad, gap, head_h, foot_h = 24, 16, 84, 52
    LW = 1180 if two_cols else 1000
    row_h = 62 if two_cols else 56
    desc_lines = 2 if two_cols else 1
    cols = [items[: (n + 1) // 2], items[(n + 1) // 2:]] if two_cols else [items]
    max_rows = max(len(c) for c in cols)
    sec_h = G.GlassCanvas.section_height(max_rows, row_h, 8)
    LH = pad + head_h + gap + sec_h + gap + foot_h + pad

    # Tối ưu siêu tốc giống menu.py: scale=2, out=1.25 -> render cực nhanh, nhẹ RAM và sắc nét
    cv = G.GlassCanvas(LW, LH, scale=2, out=1.25)
    logo = None
    try:
        logo = cfg["logo_fn"](int(44 * cv.k))
    except Exception:
        logo = None
    f_st = cv.font("b", 12)
    st_text = f"Prefix  {prefix}"
    st_w = cv.tlen(st_text, f_st) + 28
    cv.header(pad, pad, LW - pad, head_h, cfg["title"], cfg.get("sub", ""), logo=logo, logo_size=44,
              tag=f"{len(items)} LỆNH", tag_grad=grad, right_reserve=st_w + 8)
    cv.glass_pill(LW - pad - 20, pad + head_h / 2 - 15, st_text, f_st, grad, align="r", tint_alpha=120)

    top = pad + head_h + gap
    nc = len(cols)
    col_w = (LW - 2 * pad - (nc - 1) * gap) / nc
    start = 1
    f_cmd = cv.font("b", 13)
    f_desc = cv.font("r", 11)
    for ci, chunk in enumerate(cols):
        x1 = pad + ci * (col_w + gap)
        x2 = x1 + col_w
        end = start + len(chunk) - 1
        label = f"{start} – {end}" if two_cols else f"{len(chunk)} lệnh"
        y2 = top + sec_h
        # khung section + header nhuộm màu (rows tự vẽ để có tag + mô tả 2 dòng)
        cv.section(x1, top, x2, "DANH SÁCH LỆNH", "Gõ đúng prefix ở đầu mỗi lệnh", grad, [],
                   row_h=row_h, y2=y2, count_label=label)
        cy = top + 50 + 12
        for syn, desc, tag in chunk:
            cv.cmd_row((x1 + 10, cy, x2 - 10, cy + row_h), f"{prefix}{syn}", desc, tag, accent=accent,
                       f_cmd=f_cmd, f_desc=f_desc, desc_lines=desc_lines)
            cy += row_h + 8
        start = end + 1

    # footer mẹo
    fy1 = top + sec_h + gap
    cv.bar(pad, fy1, LW - pad, fy1 + foot_h)
    tip = cfg.get("tip", "💡 Mẹo: Khi hiện bảng danh sách 1-20, gõ thêm 'v' để phát Voice, "
                         "'f' để nhận File, hoặc 'c' để hủy bỏ.")
    tip = G.clean_text(tip)
    cv.chip((pad + 14, fy1 + 10, pad + 46, fy1 + foot_h - 10), "💡", "i", (250, 204, 21), r=10, size=16)
    f_tip = cv.font("r", 12)
    cv.text(pad + 58, fy1 + foot_h / 2, cv.fit(tip, f_tip, LW - 2 * pad - 76), f_tip, (254, 240, 138),
            vcenter=True)
    return cv.finalize()


def _render_premium_help_card_legacy(platform: str, prefix: str = "!") -> io.BytesIO:
    cfg = PLATFORM_CONFIG.get(platform, PLATFORM_CONFIG["youtube"])
    # TỰ THU PHÓNG: ít lệnh -> row cao 58 (như cũ); nhiều lệnh -> row gọn 50/44
    # + font bớt size, để card luôn vừa màn hình, không tràn/đè nhau.
    item_count = len(cfg.get("items", []))
    W = 880
    if item_count <= 8:
        row_step, sz_cmd, sz_desc, sz_tag = 58, 13, 12, 10
    elif item_count <= 14:
        row_step, sz_cmd, sz_desc, sz_tag = 50, 12, 11, 10
    else:
        row_step, sz_cmd, sz_desc, sz_tag = 44, 11, 10, 9
    H = max(520, 198 + item_count * row_step)

    # 1. Background loading & smooth blur
    base = Image.new("RGBA", (W, H), (14, 18, 30, 255))
    if SHARED_BACKGROUNDS_DIR.exists():
        bg_files = [f for f in os.listdir(SHARED_BACKGROUNDS_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
        if bg_files:
            try:
                chosen = SHARED_BACKGROUNDS_DIR / random.choice(bg_files)
                with Image.open(chosen) as r_bg:
                    im = r_bg.convert("RGBA")
                    im = ImageOps.fit(im, (W, H), method=Image.Resampling.LANCZOS)
                    # Gaussian blur sâu tạo chiều sâu
                    im = im.filter(ImageFilter.GaussianBlur(radius=10))
                    # Làm tối nền vừa phải
                    darken = Image.new("RGBA", (W, H), (10, 14, 26, 175))
                    im = Image.alpha_composite(im, darken)
                    base = im
            except Exception:
                pass

    # 2. Outer Glass Panel (Supersampled bo góc siêu mượt)
    pad = 22
    panel_w = W - pad * 2
    panel_h = H - pad * 2
    
    # Shadow mềm
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    s_box = draw_supersampled_rounded_box(panel_w, panel_h, radius=22, fill=(0, 0, 0, 110), scale=2)
    shadow.paste(s_box, (pad, pad + 6), s_box)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=8))
    base = Image.alpha_composite(base, shadow)

    # Panel Body (Frosted Glass đa tầng, viền phát sáng nhẹ)
    panel_img = draw_supersampled_rounded_box(
        panel_w, panel_h, 
        radius=22, 
        fill=(18, 24, 40, 210), 
        outline=(255, 255, 255, 45), 
        outline_w=1, 
        scale=3
    )
    base.paste(panel_img, (pad, pad), panel_img)

    # Header Top Accent Glow Line
    accent = cfg["accent"]
    glow_bar = draw_supersampled_rounded_box(panel_w - 40, 3, radius=2, fill=(accent[0], accent[1], accent[2], 160), scale=2)
    base.paste(glow_bar, (pad + 20, pad + 1), glow_bar)

    # 3. macOS Window Controls (● ● ●)
    mac_dots = Image.new("RGBA", (80, 20), (0, 0, 0, 0))
    d_mac = ImageDraw.Draw(mac_dots)
    d_mac.ellipse([(0, 2), (12, 14)], fill=(255, 95, 86, 255))
    d_mac.ellipse([(18, 2), (30, 14)], fill=(255, 189, 46, 255))
    d_mac.ellipse([(36, 2), (48, 14)], fill=(39, 201, 63, 255))
    base.paste(mac_dots, (pad + 22, pad + 20), mac_dots)

    # 4. Hi-Res Logo
    logo = cfg["logo_fn"](44)
    base.paste(logo, (pad + 22, pad + 48), logo)

    # 5. Header Typography (BeVietnamPro-Bold & Regular)
    draw = ImageDraw.Draw(base)
    f_title = _get_font(True, 19)
    f_sub = _get_font(False, 12)
    f_cmd = _get_font(True, sz_cmd)
    f_desc = _get_font(False, sz_desc)
    f_tag = _get_font(True, sz_tag)
    f_tip = _get_font(False, 11)

    draw.text((pad + 78, pad + 47), cfg["title"], fill=(255, 255, 255), font=f_title)
    draw.text((pad + 78, pad + 73), cfg["sub"], fill=(160, 175, 205), font=f_sub)

    # Header divider
    div_y = pad + 104
    draw.line([(pad + 22, div_y), (W - pad - 22, div_y)], fill=(255, 255, 255, 25), width=1)

    # 6. Command Rows (Clean Modern Glass Rows)
    row_y_start = pad + 116
    row_h = row_step
    row_w = panel_w - 44
    bg_h = row_h - 10            # capsule row (58 -> 48 như cũ)
    code_h = max(28, row_h - 22) # capsule cú pháp
    tag_h = max(20, min(24, bg_h - 6))

    for idx, (syntax_tmpl, desc, tag) in enumerate(cfg["items"]):
        cur_y = row_y_start + idx * row_h
        cur_x = pad + 22

        # Cú pháp đầy đủ với prefix
        full_syntax = f"{prefix}{syntax_tmpl}"

        # Row Background Capsule (Supersampled viền mượt)
        row_bg = draw_supersampled_rounded_box(
            row_w, bg_h,
            radius=12, 
            fill=(24, 32, 54, 180), 
            outline=(255, 255, 255, 22), 
            outline_w=1, 
            scale=3
        )
        base.paste(row_bg, (cur_x, cur_y), row_bg)

        # Code Block bên trái (Frosted Capsule với viền màu Accent)
        # Code block vừa khít cú pháp (tự nới rộng, cắt … nếu dài bất thường)
        _syn_w = int(draw.textlength(full_syntax, font=f_cmd)) + 36
        code_w = min(max(260, _syn_w), row_w - 240)
        if draw.textlength(full_syntax, font=f_cmd) > code_w - 30:
            while full_syntax and draw.textlength(full_syntax + "…", font=f_cmd) > code_w - 30:
                full_syntax = full_syntax[:-1]
            full_syntax = (full_syntax + "…") if full_syntax else ""
        code_y = cur_y + (bg_h - code_h) // 2
        code_bg = draw_supersampled_rounded_box(
            code_w, code_h, 
            radius=8, 
            fill=(14, 18, 30, 240), 
            outline=(accent[0], accent[1], accent[2], 180), 
            outline_w=1, 
            scale=3
        )
        base.paste(code_bg, (cur_x + 6, code_y), code_bg)

        # Cú pháp text
        _ca, _cd = f_cmd.getmetrics()
        draw.text((cur_x + 18, code_y + (code_h - (_ca + _cd)) // 2), full_syntax, fill=(255, 255, 255), font=f_cmd)

        # Mô tả tính năng
        # Mô tả — cắt … nếu dài quá không vừa khoảng trống trước tag
        desc_x = cur_x + code_w + 22
        _tag_x = cur_x + row_w - (int(draw.textlength(tag, font=f_tag)) + 18) - 12
        desc_max = _tag_x - 24 - desc_x
        if desc_max > 40 and draw.textlength(desc, font=f_desc) > desc_max:
            while desc and draw.textlength(desc + "…", font=f_desc) > desc_max:
                desc = desc[:-1]
            desc = (desc + "…") if desc else ""
        _da, _dd = f_desc.getmetrics()
        draw.text((desc_x, cur_y + (bg_h - (_da + _dd)) // 2), desc, fill=(205, 215, 235), font=f_desc)

        # Tag Badge bên phải (Viền + Nền mờ cùng màu accent)
        tag_w = int(draw.textlength(tag, font=f_tag)) + 18
        tag_bg = draw_supersampled_rounded_box(
            tag_w, tag_h, 
            radius=6, 
            fill=(accent[0], accent[1], accent[2], 40), 
            outline=(accent[0], accent[1], accent[2], 180), 
            outline_w=1, 
            scale=3
        )
        tag_x = cur_x + row_w - tag_w - 12
        tag_y = cur_y + (bg_h - tag_h) // 2
        base.paste(tag_bg, (tag_x, tag_y), tag_bg)
        _ta, _td = f_tag.getmetrics()
        draw.text((tag_x + 9, tag_y + (tag_h - (_ta + _td)) // 2), tag, fill=(255, 255, 255), font=f_tag)

    # 7. Bottom Tip Capsule
    tip_y = H - pad - 42
    tip_bg = draw_supersampled_rounded_box(
        row_w, 30, 
        radius=8, 
        fill=(14, 18, 30, 200), 
        outline=(255, 255, 255, 18), 
        outline_w=1, 
        scale=2
    )
    base.paste(tip_bg, (pad + 22, tip_y), tip_bg)
    draw.text(
        (pad + 34, tip_y + 7), 
        cfg.get("tip", "💡 Mẹo: Khi hiện bảng danh sách 1-20, gõ thêm 'v' để phát Voice, 'f' để nhận File, hoặc 'c' để hủy bỏ."), 
        fill=(255, 210, 60), 
        font=f_tip
    )

    buf = io.BytesIO()
    base.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf



def _get_genesis_font(size: int, bold: bool = False, modak: bool = False):
    """Font chữ cho card genesis list: modak -> BeVietnamPro -> Segoe UI."""
    if not HAS_PIL:
        return None
    try:
        from apps.shared.paths import SHARED_FONTS_DIR
        if modak:
            m_path = SHARED_FONTS_DIR / "DFVN-Modak.ttf"
            if m_path.exists():
                return ImageFont.truetype(str(m_path), size)
        reg_file = "BeVietnamPro-Bold.ttf" if bold else "BeVietnamPro-Regular.ttf"
        reg_path = SHARED_FONTS_DIR / reg_file
        if reg_path.exists():
            return ImageFont.truetype(str(reg_path), size)
        reg_alt = SHARED_FONTS_DIR / "BeVietnamPro-Regular.ttf"
        if reg_alt.exists():
            return ImageFont.truetype(str(reg_alt), size)
    except Exception:
        pass
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibrib.ttf" if bold else r"C:\Windows\Fonts\calibri.ttf",
        r"C:\Windows\Fonts\seguisym.ttf",   # Segoe UI Symbol: ký tự đặc biệt (∞, •, 🔒…)
        r"C:\Windows\Fonts\seguiemj.ttf",   # Segoe UI Emoji: chỉ fallback cuối (chữ dễ vỡ nét)
    ]
    for c in candidates:
        try:
            if os.path.exists(c):
                return ImageFont.truetype(c, size)
        except Exception:
            continue
    # Fallback cuối: DejaVu đi kèm Pillow (vector, scale mượt) — KHÔNG dùng load_default.
    try:
        import PIL
        pil_dir = os.path.dirname(PIL.__file__)
        for dj in (os.path.join(pil_dir, "fonts", "DejaVuSans-Bold.ttf") if bold
                   else os.path.join(pil_dir, "fonts", "DejaVuSans.ttf"),
                   r"C:\Windows\Fonts\DejaVuSans-Bold.ttf" if bold else r"C:\Windows\Fonts\DejaVuSans.ttf"):
            if os.path.exists(dj):
                return ImageFont.truetype(dj, size)
    except Exception:
        pass
    # Cố gắng lần cuối với truetype mặc định của Pillow (vẫn là vector).
    return ImageFont.truetype("DejaVuSans.ttf", size)


def _clean_card_title(text: str, fallback: str = "") -> str:
    """Làm sạch tiêu đề TRƯỚC KHI VẼ lên ảnh: 1 dòng, bỏ markdown + emoji.

    Font card (BeVietnamPro/Segoe UI) KHÔNG có glyph emoji -> vẽ emoji sẽ thành
    ô vuông. Nên chỉ giữ ký tự Latin/Việt và vài ký hiệu font có sẵn (∞ • —).
    """
    head = (text or "").splitlines()[0] if text else ""
    head = head.replace("**", "").replace("__", "").replace("`", "").replace("*", "").strip()
    head = "".join(ch for ch in head if ch.isprintable() and (ord(ch) < 0x2000 or ch in "∞•—–"))
    return head.strip(" •—-") or (fallback or "")


def render_genesis_list_card(rows, prefix="!", title=None, tip=None):
    """Bảng danh sách bot con (sổ genesis) dạng ẢNH Liquid Glass siêu nét."""
    try:
        return _render_genesis_list_glass(rows, prefix=prefix, title=title, tip=tip)
    except Exception as e:
        print(f"[genesis] liquid glass error, fallback to legacy: {e}")
        return _render_genesis_list_legacy(rows, prefix=prefix, title=title, tip=tip)


def _render_genesis_list_glass(rows, prefix="!", title=None, tip=None) -> io.BytesIO:
    from apps.user_discord.utils.glass import (
        GlassCanvas, G_PURPLE, G_BRAND, G_AMBER, G_GREEN, G_RED, G_BLUE, C_TEXT, C_MUTED, C_DIM
    )
    n = max(1, len(rows))
    lw = 880
    pad = 18
    head_h = 76
    foot_h = 42
    row_h = 76
    gap = 8
    lh = pad + head_h + 14 + n * row_h + (n - 1) * gap + 14 + foot_h + pad

    cv = GlassCanvas(lw, lh, scale=2, out=1.25)
    _card_title = _clean_card_title(title) if title else "SỔ GENESIS — DANH SÁCH BOT"
    cv.header(pad, pad, lw - pad, head_h, _card_title,
              f"{n} bot trong hệ thống • Quản lý Shard / Prime",
              tag=f"{n} BOT", tag_grad=G_PURPLE)

    f_name = cv.font("b", 14)
    f_meta = cv.font("r", 11)
    f_badge = cv.font("b", 10)
    f_pfx = cv.font("b", 10.5)

    state_colors = {
        "login": (G_GREEN, (167, 255, 214), "login"),
        "locked": (G_RED, (255, 170, 170), "locked 🔒"),
        "stopped": (G_BRAND, (200, 200, 200), "stopped ⏹️"),
        "no_token": (G_BRAND, (200, 200, 200), "chưa token"),
        "bad_token": (G_RED, (255, 170, 170), "token lỗi"),
        "error": (G_RED, (255, 170, 170), "lỗi kết nối"),
    }

    cy = pad + head_h + 14
    for r in rows:
        is_prime = (r.get("role") == "prime")
        card_box = (pad, cy, lw - pad, cy + row_h)
        cv.glass(card_box, 16, blur=12, highlight=24, rim=None)

        # Avatar bot
        av_img = None
        ab = r.get("avatar_bytes")
        if ab:
            try:
                with Image.open(io.BytesIO(ab)) as aim:
                    av_img = aim.convert("RGBA")
            except Exception:
                av_img = None
        ring_col = G_AMBER if is_prime else G_PURPLE
        cv.circle_image(av_img, pad + 12, cy + (row_h - 48) / 2, 48, ring=ring_col, letter=r.get("name") or "?")

        # Tên + bot_id pill + prefix pill
        tx = pad + 12 + 48 + 14
        top_y = cy + row_h * 0.33
        name_txt = r.get("name") or "Bot"
        tw = cv.text(tx, top_y, name_txt, f_name, (254, 240, 138) if is_prime else C_TEXT, vcenter=True)
        
        # Bot ID pill (G001, G003...)
        bid = str(r.get("bot_id") or "")
        if bid:
            cv.pill(tx + tw + 10, top_y - 9.5, bid, f_badge, G_PURPLE if not is_prime else G_AMBER, h=19, padx=7)
            tw += cv.tlen(bid, f_badge) + 24

        # Prefix pill (cyan)
        pfx_val = r.get("prefix")
        if pfx_val:
            pfx_str = f"prefix: {pfx_val}"
            cv.pill(tx + tw + 8, top_y - 9.5, pfx_str, f_pfx, G_BLUE, h=19, padx=8)

        # UID + Time subtext
        uid_val = r.get("uid") or "Chưa có UID"
        time_val = r.get("time") or "infinity"
        sub_text = f"UID: {uid_val}   •   Hạn: {time_val}"
        cv.text(tx, cy + row_h * 0.68, sub_text, f_meta, C_MUTED, vcenter=True)

        # Right side: Role pill + State pill
        right_x = lw - pad - 14
        role_txt = "PRIME" if is_prime else "SHARD"
        rx1, rx2 = cv.pill(right_x, cy + 14, role_txt, f_badge, G_AMBER if is_prime else G_PURPLE, h=22, padx=12, align="r")

        st_key = r.get("state") or "login"
        st_grad, st_dot, st_lbl = state_colors.get(st_key, (G_GREEN, (167, 255, 214), st_key))
        cv.glass_pill(right_x, cy + 42, st_lbl, f_badge, st_grad, h=20, padx=10, align="r", dot=st_dot)

        cy += row_h + gap

    foot_y = cy + 6
    cv.bar(pad, foot_y, lw - pad, foot_y + foot_h, r=12)
    f_foot = cv.font("r", 11)
    tip_msg = tip or f"💡 {prefix}gene start/lock/unlock/stop/remove <id>  •  Thời gian: infinity hoặc 10s/5m/2h/1d"
    cv.text(lw / 2, foot_y + foot_h / 2, tip_msg, f_foot, C_MUTED, align="c", vcenter=True)
    return cv.finalize()


def _render_genesis_list_legacy(rows, prefix="!", title=None, tip=None):
    """Bảng danh sách bot con (sổ genesis) dạng ẢNH LEGACY."""
    OUT_SCALE = 2
    W, pad = 960, 24
    n = max(1, len(rows))

    # ── TỰ THU PHÓNG: ít bot -> full 1 cột; nhiều bot -> lưới tối đa 5 cột,
    #    mỗi cột ≤ 12 dòng, cao dòng nén về 44–66px → card luôn vừa, hết tràn. ──
    if n <= 8:
        mode, cols, per, row_h = "full", 1, n, 94
    else:
        cols = min(5, max(1, -(-n // 12)))          # ceil(n/12), tối đa 5 cột
        per = -(-n // cols)                          # số dòng mỗi cột
        row_h = max(44, min(66, 1030 // per))        # nén để vùng dòng ≤ ~1030px
        mode = "grid"

    # Full giữ supersampling 4x; grid render 2x (đã đủ nét, tiết kiệm RAM)
    S = 4 if mode == "full" else 2

    def s(v):
        return int(round(v * S))

    rows_end = 140 + per * row_h                     # đáy vùng dòng (logical)
    H = max(340, rows_end + (108 if mode != "full" else 84))
    W2, H2 = s(W), s(H)
    pad2 = s(pad)
    gap = 14
    col_w = (W - pad * 2 - 44 - gap * (cols - 1)) // cols   # bề rộng 1 cột (logical)

    # 1. Nen gradient MUOT (strip 256px -> BICUBIC, het banding/vun hat)
    _grad = Image.new("RGBA", (1, 256), (0, 0, 0, 0))
    _gg = ImageDraw.Draw(_grad)
    _top = (26, 32, 54)
    _bot = (10, 13, 25)
    for _yy in range(256):
        _k = _yy / 255.0
        _cc = tuple(int(_top[i] + (_bot[i] - _top[i]) * _k) for i in range(3))
        _gg.point((0, _yy), fill=_cc + (255,))
    base = _grad.resize((W2, H2), Image.Resampling.BICUBIC)
    _ov = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    _od = ImageDraw.Draw(_ov)
    _od.ellipse([s(-180), s(-180), s(380), s(300)], fill=(139, 92, 246, 46))
    _od.ellipse([W2 - s(380), H2 - s(320), W2 + s(180), H2 + s(180)], fill=(34, 211, 238, 34))
    _ov = _ov.filter(ImageFilter.GaussianBlur(radius=s(4)))
    base = Image.alpha_composite(base, _ov)
    base = Image.alpha_composite(base, Image.new("RGBA", (W2, H2), (8, 10, 22, 60)))

    # 2. Panel glassmorphism (đổ bóng + viền phát sáng)
    panel_w2, panel_h2 = s(W - pad * 2), s(H - pad * 2)
    shadow = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    s_box = draw_supersampled_rounded_box(panel_w2, panel_h2, radius=s(22), fill=(0, 0, 0, 110), scale=2)
    shadow.paste(s_box, (pad2, pad2 + s(6)), s_box)
    base = Image.alpha_composite(base, shadow.filter(ImageFilter.GaussianBlur(radius=s(6))))
    panel = draw_supersampled_rounded_box(panel_w2, panel_h2, radius=s(22), fill=(16, 20, 32, 135),
                                          outline=(255, 255, 255, 65), outline_w=max(1, s(1)), scale=2)
    base.paste(panel, (pad2, pad2), panel)

    accent = (139, 92, 246)
    glow = draw_supersampled_rounded_box(panel_w2 - s(40), s(3), radius=s(2),
                                         fill=(accent[0], accent[1], accent[2], 160), scale=2)
    base.paste(glow, (pad2 + s(20), pad2 + s(1)), glow)

    # 3. Header: logo DNA + tiêu đề
    logo = draw_genesis_logo_hires(s(44))
    base.paste(logo, (pad2 + s(22), pad2 + s(48)), logo)
    draw = ImageDraw.Draw(base)
    f_title = _get_genesis_font(s(22), modak=True)
    f_sub = _get_genesis_font(s(12))
    f_name = _get_genesis_font(s(15), True)
    f_small = _get_genesis_font(s(11))
    f_badge = _get_genesis_font(s(10), True)
    # font cho dòng gọn (grid/compact)
    f_tile_name = _get_genesis_font(s(13), True)
    f_tile_sub = _get_genesis_font(s(10))
    f_tile_badge = _get_genesis_font(s(9), True)

    draw.text((pad2 + s(78), pad2 + s(47)), _clean_card_title(title) or "SỔ GENESIS — DANH SÁCH BOT", fill=(255, 255, 255), font=f_title)
    _cols_note = f" • {cols} cột" if cols > 1 else ""
    _sub_txt = (f"{n} bot có thể reset{_cols_note}" if title else f"Quản lý bot con (prime / shard) • {n} bot trong sổ{_cols_note}")
    draw.text((pad2 + s(78), pad2 + s(73)), _sub_txt, fill=(160, 175, 205), font=f_sub)
    draw.line([(pad2 + s(22), pad2 + s(104)), (W2 - pad2 - s(22), pad2 + s(104))],
              fill=(255, 255, 255, 25), width=max(1, s(1)))

    state_meta = {
        "login": ("login", (46, 204, 113)),
        "locked": ("locked 🔒", (235, 87, 87)),
        "stopped": ("stopped ⏹️", (150, 155, 165)),
        "no_token": ("chưa có token", (150, 155, 165)),
        "bad_token": ("token lỗi", (235, 87, 87)),
        "error": ("lỗi kết nối", (245, 158, 11)),
    }

    # 4. Từng dòng bot — full: 1 cột như cũ; grid: xếp nhiều cột, tự thu phóng
    row_y2 = pad2 + s(116)
    row_w2 = panel_w2 - s(44)
    row_h2 = s(row_h)

    def _draw_tile(idx, r):
        """Dòng gọn 2 tầng: avatar + tên (+badge role) / id • thời gian • [prefix] + chấm trạng thái."""
        col_i, row_i = idx // per, idx % per
        x = pad2 + s(22 + col_i * (col_w + gap))
        y = row_y2 + s(row_i * row_h)
        w = s(col_w)
        bg_h = s(row_h - 6)
        bg_top = y + s(3)
        is_prime = (r.get("role") == "prime")
        ring = (255, 200, 60) if is_prime else accent
        tile_bg = draw_supersampled_rounded_box(
            w, bg_h, radius=s(12), fill=(24, 32, 54, 185),
            outline=(255, 255, 255, 22), outline_w=max(1, s(1)), scale=2)
        base.paste(tile_bg, (x, bg_top), tile_bg)
        d = ImageDraw.Draw(base)

        # Avatar bo tròn + vòng role (vàng = prime, tím = shard)
        av = max(s(24), min(s(44), bg_h - s(14)))
        av_x, av_y = x + s(10), bg_top + (bg_h - av) // 2
        ab = r.get("avatar_bytes")
        av_img = None
        if ab:
            try:
                with Image.open(io.BytesIO(ab)) as aim:
                    _raw = aim.convert("RGBA")
                    if min(_raw.size) < av:
                        _raw = _raw.resize((av, av), Image.Resampling.LANCZOS)
                    av_img = ImageOps.fit(_raw, (av, av), method=Image.Resampling.LANCZOS)
            except Exception:
                av_img = None
        _big = av * 4
        _mb = Image.new("L", (_big, _big), 0)
        ImageDraw.Draw(_mb).ellipse([(0, 0), (_big - 1, _big - 1)], fill=255)
        mask = _mb.resize((av, av), Image.Resampling.LANCZOS)
        if av_img is not None:
            base.paste(av_img, (av_x, av_y), mask)
        else:
            d.ellipse([(av_x, av_y), (av_x + av, av_y + av)], fill=(30, 38, 58))
            d.text((av_x + av // 2, av_y + av // 2), (r.get("name") or "?")[:1].upper(),
                   fill=(200, 210, 230), font=f_tile_name, anchor="mm")
        d.ellipse([(av_x - s(2), av_y - s(2)), (av_x + av + s(2), av_y + av + s(2))],
                  outline=ring + (90,), width=max(1, s(3)))
        d.ellipse([(av_x - s(2), av_y - s(2)), (av_x + av + s(2), av_y + av + s(2))],
                  outline=ring, width=max(1, s(1)))

        y1 = bg_top + int(bg_h * 0.36)
        y2 = bg_top + int(bg_h * 0.74)
        tx = av_x + av + s(10)

        # Dòng 1: tên bot + badge role (nếu đủ rộng)
        role_txt = "prime" if is_prime else "shard"
        rb_w = 0
        if col_w >= 190:
            rb_w = d.textlength(role_txt, font=f_tile_badge) + s(18)
            rx = x + w - s(10) - rb_w
            d.rounded_rectangle([(rx, y1 - s(9)), (rx + rb_w, y1 + s(9))], radius=s(6),
                                fill=(28, 36, 60, 235), outline=ring, width=max(1, s(1)))
            d.text((rx + s(9), y1), role_txt, fill=(255, 255, 255), font=f_tile_badge, anchor="lm")
        disp_name = r.get("name") or "?"
        max_w = x + w - s(10) - rb_w - s(8) - tx
        if max_w > s(16) and d.textlength(disp_name, font=f_tile_name) > max_w:
            while disp_name and d.textlength(disp_name + "…", font=f_tile_name) > max_w:
                disp_name = disp_name[:-1]
            disp_name = (disp_name + "…") if disp_name else "?"
        d.text((tx, y1), disp_name, fill=(255, 220, 130) if is_prime else (255, 255, 255),
               font=f_tile_name, anchor="lm")

        # Dòng 2: bot_id • thời gian • [prefix] (rút gọn theo độ rộng) + chấm trạng thái
        segs = [r.get("bot_id") or "--", str(r.get("time") or "-"), f"[{r.get('prefix') or '-'}]"]
        right_lim = x + w - s(24)
        while len(segs) > 1 and tx + d.textlength("  •  ".join(segs), font=f_tile_sub) > right_lim:
            segs.pop()
        d.text((tx, y2), "  •  ".join(segs), fill=(170, 190, 225), font=f_tile_sub, anchor="lm")
        st_col = state_meta.get(r.get("state"), state_meta["error"])[1]
        cx, cy = x + w - s(14), y2
        d.ellipse([(cx - s(7), cy - s(7)), (cx + s(7), cy + s(7))],
                  fill=(st_col[0], st_col[1], st_col[2], 60))
        d.ellipse([(cx - s(4), cy - s(4)), (cx + s(4), cy + s(4))], fill=st_col)

    for idx, r in enumerate(rows):
        if mode != "full":
            _draw_tile(idx, r)
            continue
        cur_y = row_y2 + idx * row_h2
        cur_x = pad2 + s(22)
        is_prime = (r.get("role") == "prime")
        ring = (255, 200, 60) if is_prime else accent

        row_bg = draw_supersampled_rounded_box(row_w2, s(70), radius=s(14), fill=(24, 32, 54, 185),
                                               outline=(255, 255, 255, 22), outline_w=max(1, s(1)), scale=2)
        base.paste(row_bg, (cur_x, cur_y + s(5)), row_bg)

        # Avatar tron NET: fit anh that 1 lan LANCZOS + mask supersample 4x
        # (mask 4x du min, tranh resize vo han gay nhoè khi downscale tong the)
        av_s = s(48)
        av_x, av_y = cur_x + s(16), cur_y + s(12)
        av_img = None
        ab = r.get("avatar_bytes")
        if ab:
            try:
                with Image.open(io.BytesIO(ab)) as aim:
                    # Anh goc cang lon cang tot: xin size=512 tu CDN, upscale truoc khi fit
                    # de tranh truong hop avatar 128px bi phong dai -> vo hat.
                    _raw = aim.convert("RGBA")
                    if min(_raw.size) < av_s:
                        _raw = _raw.resize((av_s, av_s), Image.Resampling.LANCZOS)
                    av_img = ImageOps.fit(_raw, (av_s, av_s),
                                          method=Image.Resampling.LANCZOS)
            except Exception:
                av_img = None
        _ms = 4
        _big = av_s * _ms
        _mask_big = Image.new("L", (_big, _big), 0)
        ImageDraw.Draw(_mask_big).ellipse([(0, 0), (_big - 1, _big - 1)], fill=255)
        mask = _mask_big.resize((av_s, av_s), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(base)
        if av_img is not None:
            base.paste(av_img, (av_x, av_y), mask)
        else:
            draw.ellipse([(av_x, av_y), (av_x + av_s, av_y + av_s)], fill=(30, 38, 58))
            draw.text((av_x + av_s // 2, av_y + av_s // 2 - s(2)), (r.get("name") or "?")[:1].upper(),
                      fill=(200, 210, 230), font=f_name, anchor="mm")
        draw.ellipse([(av_x - s(2), av_y - s(2)), (av_x + av_s + s(2), av_y + av_s + s(2))],
                     outline=ring + (90,), width=max(1, s(3)))
        draw.ellipse([(av_x - s(2), av_y - s(2)), (av_x + av_s + s(2), av_y + av_s + s(2))],
                     outline=ring, width=max(1, s(1)))

        # Badge vai trò (phải trên) — tính trước để cắt tên nếu quá dài, tránh đè badge/prefix
        role_txt = "prime" if is_prime else "shard"
        rw = draw.textlength(role_txt, font=f_badge) + s(24)
        rx = cur_x + row_w2 - rw - s(20)

        # Tên bot + mã bot_id + badge PREFIX riêng (nổi bật, viền cyan)
        tx = av_x + av_s + s(16)
        disp_name = r.get("name") or "?"
        bid = r.get("bot_id") or "--"
        bw = draw.textlength(bid, font=f_badge) + s(16)
        pfx_txt = r.get("prefix") or "-"
        pfx_label = f"prefix: {pfx_txt}"
        pw = draw.textlength(pfx_label, font=f_badge) + s(16)
        # Giới hạn tên để không đè lên cụm badge bên phải
        max_name_w = rx - s(12) - tx - bw - pw - s(26)
        if max_name_w > s(40) and draw.textlength(disp_name, font=f_name) > max_name_w:
            while disp_name and draw.textlength(disp_name + "…", font=f_name) > max_name_w:
                disp_name = disp_name[:-1]
            disp_name = (disp_name + "…") if disp_name else "?"
            name_w = draw.textlength(disp_name, font=f_name)
        else:
            name_w = draw.textlength(disp_name, font=f_name)
        draw.text((tx, cur_y + s(10)), disp_name, fill=(255, 255, 255), font=f_name)
        bx1 = tx + name_w + s(10)
        draw.rounded_rectangle([(bx1, cur_y + s(11)), (bx1 + bw, cur_y + s(29))], radius=s(6),
                               fill=(accent[0], accent[1], accent[2], 60),
                               outline=(accent[0], accent[1], accent[2], 160), width=max(1, s(1)))
        draw.text((bx1 + s(8), cur_y + s(15)), bid, fill=(255, 255, 255), font=f_badge)

        px1 = bx1 + bw + s(8)
        draw.rounded_rectangle([(px1, cur_y + s(11)), (px1 + pw, cur_y + s(29))], radius=s(6),
                               fill=(34, 211, 238, 45),
                               outline=(34, 211, 238, 170), width=max(1, s(1)))
        draw.text((px1 + s(8), cur_y + s(15)), pfx_label, fill=(255, 255, 255), font=f_badge)

        # UID + thời gian (dòng 2) — kèm CHECK uid: uid sổ vs uid THẬT (đang hoạt động)
        true_uid = r.get("uid")
        cfg_uid = r.get("uid_cfg")
        uid_txt = true_uid or cfg_uid or "chưa login"
        uid_note = ""
        if cfg_uid and true_uid and str(cfg_uid) != str(true_uid):
            uid_note = f"   •   ⚠️ sổ ghi {cfg_uid}"
        elif not cfg_uid and true_uid:
            uid_note = "   •   ⚠️ sổ chưa có uid"
        draw.text((tx, cur_y + s(42)),
                  f"UID {uid_txt}{uid_note}   •   {r.get('time')}",
                  fill=(170, 190, 225), font=f_small)

        # Vẽ badge vai trò (đã tính vị trí ở trên)
        draw.rounded_rectangle([(rx, cur_y + s(12)), (rx + rw, cur_y + s(30))], radius=s(6),
                               fill=(28, 36, 60, 235), outline=ring, width=max(1, s(1)))
        draw.text((rx + s(12), cur_y + s(16)), role_txt, fill=(255, 255, 255), font=f_badge)

        st_txt, st_col = state_meta.get(r.get("state"), state_meta["error"])
        _dot_d = s(9)
        _txt_w = draw.textlength(st_txt, font=f_badge)
        # ascent/descent thật để căn dọc chuẩn, tránh chữ chạm viền pill
        _asc, _desc = f_badge.getmetrics()
        _cap = _asc + _desc
        _pad_x, _gap = s(12), s(8)
        _pill_h = max(s(20), _cap + s(12))
        _pill_top = cur_y + s(42)
        sw = _pad_x + _dot_d + _gap + _txt_w + _pad_x
        sx = cur_x + row_w2 - sw - s(20)
        draw.rounded_rectangle([(sx, _pill_top), (sx + sw, _pill_top + _pill_h)], radius=s(9),
                               fill=(st_col[0], st_col[1], st_col[2], 40),
                               outline=(st_col[0], st_col[1], st_col[2], 190), width=max(1, s(1)))
        _cx = sx + _pad_x + _dot_d / 2
        _cy = _pill_top + _pill_h / 2
        draw.ellipse([(_cx - _dot_d / 2, _cy - _dot_d / 2),
                      (_cx + _dot_d / 2, _cy + _dot_d / 2)], fill=st_col)
        draw.text((sx + _pad_x + _dot_d + _gap, _pill_top + (_pill_h - _cap) / 2),
                  st_txt, fill=(236, 242, 252), font=f_badge)

    # 5. Footer tip (+ chú giải chấm trạng thái ở chế độ lưới)
    tip_h = s(54) if mode != "full" else s(30)
    tip_y = H2 - pad2 - s(42) - (s(24) if mode != "full" else 0)
    tip_bg = draw_supersampled_rounded_box(row_w2, tip_h, radius=s(8), fill=(14, 18, 30, 205),
                                           outline=(255, 255, 255, 18), outline_w=max(1, s(1)), scale=2)
    base.paste(tip_bg, (pad2 + s(22), tip_y), tip_bg)
    if mode != "full":
        lx = pad2 + s(34)
        lc_y = tip_y + s(15)
        for lbl, col in (("login", (46, 204, 113)), ("chưa có token", (150, 155, 165)),
                         ("token lỗi", (235, 87, 87)), ("lỗi kết nối", (245, 158, 11))):
            draw.ellipse([(lx, lc_y - s(5)), (lx + s(10), lc_y + s(5))], fill=col)
            draw.text((lx + s(15), lc_y), lbl, fill=(160, 175, 205), font=f_tile_sub, anchor="lm")
            lx += s(15) + draw.textlength(lbl, font=f_tile_sub) + s(18)
        _tail = "• tên & vòng vàng = prime"
        if lx + draw.textlength(_tail, font=f_tile_sub) <= pad2 + s(886):
            draw.text((lx, lc_y), _tail, fill=(255, 200, 60), font=f_tile_sub, anchor="lm")
        draw.text((pad2 + s(34), tip_y + s(34)),
                  tip or f"💡 {prefix}gene start/lock/unlock/stop/remove <id> — thời gian: infinity hoặc 10s/5m/2h/1d.",
                  fill=(255, 210, 60), font=f_small)
    else:
        draw.text((pad2 + s(34), tip_y + s(7)),
                  tip or f"💡 {prefix}gene start/lock/unlock/stop/remove <id> — thời gian: infinity hoặc 10s/5m/2h/1d.",
                  fill=(255, 210, 60), font=f_small)

    # Downscale 1 BUOC + SHARPEN NHẸ (khong bo -> diet halo pixel sau nen):
    # S=4 -> 2x: 1 lan LANCZOS giu edge muot, chu khong ro.
    OW, OH = W * OUT_SCALE, H * OUT_SCALE
    final = base.resize((OW, OH), Image.Resampling.LANCZOS)
    try:
        final = final.filter(ImageFilter.UnsharpMask(radius=2.0, percent=45, threshold=3))
    except Exception:
        pass
    buf = io.BytesIO()
    final.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


async def async_genesis_list_card(rows, prefix="!", title=None, tip=None):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, render_genesis_list_card, rows, prefix, title, tip)


def render_admin_list_card(rows, prefix="!"):
    """Bảng danh sách ADMIN dạng ẢNH Liquid Glass siêu nét và siêu nhanh."""
    try:
        return _render_admin_list_glass(rows, prefix=prefix)
    except Exception:
        return _render_admin_list_legacy(rows, prefix=prefix)


def _render_admin_list_glass(rows, prefix="!") -> io.BytesIO:
    from apps.user_discord.utils.glass import (
        GlassCanvas, G_AMBER, G_PURPLE, C_TEXT, C_MUTED, C_DIM
    )
    n = max(1, len(rows))
    lw = 840
    pad = 18
    head_h = 76
    foot_h = 42
    row_h = 66
    gap = 8
    lh = pad + head_h + 14 + n * row_h + (n - 1) * gap + 14 + foot_h + pad

    cv = GlassCanvas(lw, lh, scale=2, out=1.25)
    cv.header(pad, pad, lw - pad, head_h, "DANH SÁCH ADMIN & QUYỀN HẠN", f"{n} quản trị viên • Hệ thống bảo mật phân cấp", tag="ADMIN LIST", tag_grad=G_AMBER)

    f_name = cv.font("b", 14)
    f_uid = cv.font("r", 11)
    f_badge = cv.font("b", 10.5)

    cy = pad + head_h + 14
    for r in rows:
        is_high = (r.get("tier") == "admintris")
        card_box = (pad, cy, lw - pad, cy + row_h)
        cv.glass(card_box, 14, blur=8, highlight=36, rim=(160, 30))

        av_img = None
        ab = r.get("avatar_bytes")
        if ab:
            try:
                with Image.open(io.BytesIO(ab)) as aim:
                    av_img = aim.convert("RGBA")
            except Exception:
                av_img = None
        cv.circle_image(av_img, pad + 12, cy + (row_h - 46) / 2, 46, ring=G_AMBER if is_high else G_PURPLE, letter=r.get("name") or "?")

        tier_txt = "ADMINTRIS" if is_high else "ADMIN"
        cv.pill(lw - pad - 14, cy + (row_h - 22) / 2, tier_txt, f_badge, G_AMBER if is_high else G_PURPLE, h=22, padx=12, align="r")

        uid_str = r.get("uid", "")
        cv.text(pad + 12 + 46 + 14, cy + row_h * 0.35, r.get("name") or "?", f_name, (254, 240, 138) if is_high else C_TEXT, vcenter=True)
        cv.text(pad + 12 + 46 + 14, cy + row_h * 0.70, f"UID: {uid_str}", f_uid, C_DIM, vcenter=True)
        cy += row_h + gap

    foot_y = cy + 6
    cv.bar(pad, foot_y, lw - pad, foot_y + foot_h, r=12)
    f_foot = cv.font("r", 11)
    cv.text(lw / 2, foot_y + foot_h / 2, f"👑 admintris = Cấp cao tối cao  •  💜 admin = Quản trị viên  •  {prefix}bot admin add/remove/list", f_foot, C_MUTED, align="c", vcenter=True)
    return cv.finalize()


def _render_admin_list_legacy(rows, prefix="!"):
    """Bảng danh sách ADMIN dạng ẢNH: avatar tròn + tên + uid + badge admintris/admin."""
    if not HAS_PIL:
        return None
    OUT_SCALE = 2
    W, pad = 760, 24
    n = max(1, len(rows))
    row_h = 78
    header_h = 116
    tip_h = 64
    H = header_h + n * row_h + tip_h + pad * 2

    S = 4

    def s(v):
        return int(round(v * S))

    W2, H2 = s(W), s(H)
    pad2 = s(pad)

    # 1. Nen gradient muot (giong genesis card)
    _grad = Image.new("RGBA", (1, 256), (0, 0, 0, 0))
    _gg = ImageDraw.Draw(_grad)
    _top = (30, 26, 54)
    _bot = (11, 13, 25)
    for _yy in range(256):
        _k = _yy / 255.0
        _cc = tuple(int(_top[i] + (_bot[i] - _top[i]) * _k) for i in range(3))
        _gg.point((0, _yy), fill=_cc + (255,))
    base = _grad.resize((W2, H2), Image.Resampling.BICUBIC)
    _ov = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    _od = ImageDraw.Draw(_ov)
    _od.ellipse([s(-170), s(-170), s(360), s(300)], fill=(255, 200, 60, 40))
    _od.ellipse([W2 - s(360), H2 - s(320), W2 + s(170), H2 + s(170)], fill=(139, 92, 246, 44))
    _ov = _ov.filter(ImageFilter.GaussianBlur(radius=s(4)))
    base = Image.alpha_composite(base, _ov)
    base = Image.alpha_composite(base, Image.new("RGBA", (W2, H2), (8, 10, 22, 60)))

    # 2. Panel glassmorphism
    panel_w2, panel_h2 = s(W - pad * 2), s(H - pad * 2)
    shadow = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    s_box = draw_supersampled_rounded_box(panel_w2, panel_h2, radius=s(22), fill=(0, 0, 0, 110), scale=2)
    shadow.paste(s_box, (pad2, pad2 + s(6)), s_box)
    base = Image.alpha_composite(base, shadow.filter(ImageFilter.GaussianBlur(radius=s(6))))
    panel = draw_supersampled_rounded_box(panel_w2, panel_h2, radius=s(22), fill=(16, 20, 32, 135),
                                          outline=(255, 255, 255, 65), outline_w=max(1, s(1)), scale=2)
    base.paste(panel, (pad2, pad2), panel)

    accent = (255, 200, 60)
    glow = draw_supersampled_rounded_box(panel_w2 - s(40), s(3), radius=s(2),
                                         fill=(accent[0], accent[1], accent[2], 160), scale=2)
    base.paste(glow, (pad2 + s(20), pad2 + s(1)), glow)

    draw = ImageDraw.Draw(base)
    f_title = _get_genesis_font(s(22), modak=True)
    f_sub = _get_genesis_font(s(12))
    f_name = _get_genesis_font(s(15), True)
    f_small = _get_genesis_font(s(11))
    f_badge = _get_genesis_font(s(10), True)

    # 3. Header: crown vang + tieu de
    crown = _draw_crown_hires(s(40))
    base.paste(crown, (pad2 + s(24), pad2 + s(50)), crown)
    n_high = sum(1 for r in rows if r.get("tier") == "admintris")
    draw.text((pad2 + s(76), pad2 + s(47)), "DANH SÁCH ADMIN CẤP QUYỀN",
              fill=(255, 255, 255), font=f_title)
    draw.text((pad2 + s(76), pad2 + s(73)),
              f"{n} admin • {n_high} admin cấp cao (admintris) • {prefix}bot admin add/remove/list",
              fill=(160, 175, 205), font=f_sub)
    draw.line([(pad2 + s(22), pad2 + s(104)), (W2 - pad2 - s(22), pad2 + s(104))],
              fill=(255, 255, 255, 25), width=max(1, s(1)))

    row_y2 = pad2 + s(header_h - pad)
    row_w2 = panel_w2 - s(44)
    # 4. Tung dong admin
    for i, r in enumerate(rows):
        y = row_y2 + s(i * row_h)
        bg_h = s(row_h - 8)
        bg_top = y + s(4)
        is_high = (r.get("tier") == "admintris")
        ring = (255, 200, 60) if is_high else (167, 139, 250)
        x = pad2 + s(22)
        tile = draw_supersampled_rounded_box(
            row_w2, bg_h, radius=s(12), fill=(24, 32, 54, 185),
            outline=(255, 255, 255, 22), outline_w=max(1, s(1)), scale=2)
        base.paste(tile, (x, bg_top), tile)

        # Avatar bo tron + ring tier
        av = s(54)
        av_x, av_y = x + s(12), bg_top + (bg_h - av) // 2
        ab = r.get("avatar_bytes")
        av_img = None
        if ab:
            try:
                with Image.open(io.BytesIO(ab)) as aim:
                    _raw = aim.convert("RGBA")
                    if min(_raw.size) < av:
                        _raw = _raw.resize((av, av), Image.Resampling.LANCZOS)
                    av_img = ImageOps.fit(_raw, (av, av), method=Image.Resampling.LANCZOS)
            except Exception:
                av_img = None
        _big = av * 4
        _mb = Image.new("L", (_big, _big), 0)
        ImageDraw.Draw(_mb).ellipse([(0, 0), (_big - 1, _big - 1)], fill=255)
        mask = _mb.resize((av, av), Image.Resampling.LANCZOS)
        if av_img is not None:
            base.paste(av_img, (av_x, av_y), mask)
        else:
            draw.ellipse([(av_x, av_y), (av_x + av, av_y + av)], fill=(30, 38, 58))
            draw.text((av_x + av // 2, av_y + av // 2),
                      (r.get("name") or "?")[:1].upper(),
                      fill=(200, 210, 230), font=f_name, anchor="mm")
        draw.ellipse([(av_x - s(2), av_y - s(2)), (av_x + av + s(2), av_y + av + s(2))],
                     outline=ring + (90,), width=max(1, s(3)))
        draw.ellipse([(av_x - s(2), av_y - s(2)), (av_x + av + s(2), av_y + av + s(2))],
                     outline=ring, width=max(1, s(1)))

        # Badge tier (phai tren)
        tier_txt = "admintris" if is_high else "admin"
        rw = draw.textlength(tier_txt, font=f_badge) + s(24)
        rx = x + row_w2 - rw - s(16)
        ry = bg_top + s(14)
        draw.rounded_rectangle([(rx, ry), (rx + rw, ry + s(28))], radius=s(7),
                               fill=(ring[0], ring[1], ring[2], 46),
                               outline=ring, width=max(1, s(1)))
        draw.text((rx + s(12), ry + s(14)), tier_txt, fill=(255, 255, 255),
                  font=f_badge, anchor="lm")

        # Ten + uid
        tx = av_x + av + s(14)
        disp_name = r.get("name") or "?"
        max_w = rx - s(14) - tx
        if max_w > s(30) and draw.textlength(disp_name, font=f_name) > max_w:
            while disp_name and draw.textlength(disp_name + "…", font=f_name) > max_w:
                disp_name = disp_name[:-1]
            disp_name = (disp_name + "…") if disp_name else "?"
        draw.text((tx, bg_top + s(18)), disp_name,
                  fill=(255, 220, 130) if is_high else (255, 255, 255),
                  font=f_name, anchor="lm")
        draw.text((tx, bg_top + s(44)), f"UID {r.get('uid')}",
                  fill=(170, 190, 225), font=f_small, anchor="lm")

    # 5. Footer tip
    tip_y = row_y2 + s(n * row_h) + s(6)
    tip_bg = draw_supersampled_rounded_box(row_w2, s(tip_h - 24), radius=s(8),
                                           fill=(14, 18, 30, 205),
                                           outline=(255, 255, 255, 18),
                                           outline_w=max(1, s(1)), scale=2)
    base.paste(tip_bg, (pad2 + s(22), tip_y), tip_bg)
    draw.text((pad2 + s(36), tip_y + s(17)),
              f"👑 admintris = cấp cao nhất  •  💜 admin = thường  •  {prefix}bot admin add/remove/list @user",
              fill=(255, 210, 60), font=f_small, anchor="lm")

    OW, OH = W * OUT_SCALE, H * OUT_SCALE
    final = base.resize((OW, OH), Image.Resampling.LANCZOS)
    try:
        final = final.filter(ImageFilter.UnsharpMask(radius=2.0, percent=45, threshold=3))
    except Exception:
        pass
    buf = io.BytesIO()
    final.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def _draw_crown_hires(size: int):
    """Ve crown vang phiieu lich (vector supersample 4x) cho header admin list."""
    S = 4
    n = size * S
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    gold = (255, 200, 60, 255)
    gold_dark = (214, 158, 34, 255)
    m = n * 0.14
    w = n - 2 * m
    top = m
    bottom = n - m
    mid_y = top + w * 0.42
    base_y = bottom - w * 0.16
    d.polygon([
        (m, mid_y),
        (m + w * 0.18, base_y),
        (m + w * 0.30, mid_y - w * 0.10),
        (m + w * 0.50, top),
        (m + w * 0.70, mid_y - w * 0.10),
        (m + w * 0.82, base_y),
        (m + w, mid_y),
    ], fill=gold)
    d.rounded_rectangle([(m, base_y - w * 0.04), (m + w, bottom)],
                        radius=w * 0.06, fill=gold_dark)
    for cx in (m + w * 0.5, m + w * 0.16, m + w * 0.84):
        cy = base_y + (bottom - base_y) * 0.42
        rr = w * 0.06
        d.ellipse([(cx - rr, cy - rr), (cx + rr, cy + rr)], fill=(235, 90, 90, 255))
    return img.resize((size, size), Image.Resampling.LANCZOS)


async def async_admin_list_card(rows, prefix="!"):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, render_admin_list_card, rows, prefix)


def make_help_card(platform, prefix="!"):
    return render_premium_help_card(platform, prefix)

async def async_help_card(platform, prefix="!"):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, make_help_card, platform, prefix)


def render_tiktok_video_card(title, author_nick, author_user='', region='', avatar_url=None, likes='0', comments='0', shares='0', views='0', hashtags=None, music_name='', cover_url=None):
    try:
        from apps.user_discord.utils import glass as G
    except ImportError:
        from utils import glass as G

    LW, LH = 1020, 340
    pad = 18
    # scale=2, out=1.5 tối ưu tốc độ nhanh như menu mà cực kỳ sắc nét
    cv = G.GlassCanvas(LW, LH, scale=2, out=1.5)

    # 1. Outer Glass Panel bo góc lớn
    panel_box = (pad, pad, LW - pad, LH - pad)
    cv.glass(panel_box, 20, blur=24, tint=(14, 18, 32, 110), magnify=1.02, saturate=1.15,
             highlight=55, rim=(220, 60), shadow=True, shadow_opacity=65)

    # 2. Thanh Accent Neon TikTok Gradient ở đỉnh
    g_tt = ((0, 242, 234), (254, 44, 85))
    cv.grad((pad + 24, pad + 1, LW - pad - 24, pad + 4), 2, g_tt[0], g_tt[1])

    # 3. Ảnh bìa video với lớp phủ nút phát
    thumb_x, thumb_y = pad + 14, pad + 14
    thumb_w, thumb_h = 282, LH - 2 * pad - 28
    thumb_img = _fetch_img(cover_url, referer="https://www.tiktok.com/") if cover_url else None
    if thumb_img:
        thumb_size = (int(round(thumb_w * cv.k)), int(round(thumb_h * cv.k)))
        thumb_img = ImageOps.fit(thumb_img.convert('RGBA'), thumb_size, method=Image.Resampling.LANCZOS)
        thumb_img.alpha_composite(Image.new('RGBA', thumb_size, (5, 10, 20, 38)))
        thumb_draw = ImageDraw.Draw(thumb_img)
        cx, cy = thumb_size[0] // 2, thumb_size[1] // 2
        play_r = int(round(25 * cv.k))
        thumb_draw.ellipse((cx - play_r, cy - play_r, cx + play_r, cy + play_r), fill=(8, 12, 20, 190), outline=(255, 255, 255, 210), width=max(1, int(round(2 * cv.k))))
        inset = int(round(8 * cv.k))
        thumb_draw.polygon(((cx - inset // 2, cy - inset), (cx - inset // 2, cy + inset), (cx + inset, cy)), fill=(255, 255, 255, 245))
        thumb_mask = Image.new('L', thumb_size, 0)
        ImageDraw.Draw(thumb_mask).rounded_rectangle((0, 0, thumb_size[0] - 1, thumb_size[1] - 1), radius=int(round(15 * cv.k)), fill=255)
        thumb_img.putalpha(thumb_mask)
        cv._comp(thumb_img, cv.s(thumb_x), cv.s(thumb_y))
        cv.rrect((thumb_x, thumb_y, thumb_x + thumb_w, thumb_y + thumb_h), 15, fill=(0, 0, 0, 0), outline=(255, 255, 255, 75), width=1)
    else:
        cv.glass((thumb_x, thumb_y, thumb_x + thumb_w, thumb_y + thumb_h), 15, blur=8, tint=(9, 18, 32, 150),
                 magnify=1.0, saturate=1.0, highlight=28, rim=(120, 35), shadow=False)
        cv.text(thumb_x + thumb_w / 2, thumb_y + thumb_h / 2, "TIKTOK", cv.font("b", 18), (220, 235, 245), align="c", vcenter=True)

    # 4. Avatar TikTok User (Hình tròn với viền Neon Cyan/Pink)
    avt_size = 54
    content_x = thumb_x + thumb_w + 24
    avt_x, avt_y = content_x, pad + 18
    avt_img = None
    if avatar_url:
        try:
            if isinstance(avatar_url, dict):
                avatar_url = avatar_url.get("url_list") or avatar_url.get("url") or avatar_url.get("src")
            if isinstance(avatar_url, (list, tuple)):
                avatar_url = next((url for url in avatar_url if isinstance(url, str) and url.startswith("http")), None)
            raw_avt = _fetch_img(avatar_url, referer="https://www.tiktok.com/")
            if raw_avt is not None:
                raw_avt = raw_avt.convert('RGBA')
                s_size = cv.s(avt_size)
                raw_avt = ImageOps.fit(raw_avt, (s_size, s_size), method=Image.Resampling.LANCZOS)
                mask = Image.new('L', (s_size, s_size), 0)
                ImageDraw.Draw(mask).ellipse([(0, 0), (s_size - 1, s_size - 1)], fill=255)
                circle_avt = Image.new('RGBA', (s_size, s_size), (0, 0, 0, 0))
                circle_avt.paste(raw_avt, (0, 0), mask)
                ImageDraw.Draw(circle_avt).ellipse([(0, 0), (s_size - 1, s_size - 1)], outline=(0, 242, 234, 230), width=cv.s(2))
                avt_img = circle_avt
        except Exception:
            pass

    if avt_img:
        cv._comp(avt_img, cv.s(avt_x), cv.s(avt_y))
    else:
        cv.circle_image(None, avt_x, avt_y, avt_size, ring=((0, 242, 234), (254, 44, 85)),
                        letter=str(author_nick or "C")[:1].upper(), fill=(28, 42, 58))

    # 5. Tiêu đề video & Tác giả
    f_title = cv.font("b", 15)
    f_author = cv.font("b", 12.5)
    f_sub = cv.font("r", 11)
    f_badge = cv.font("b", 10)

    clean_title = re.sub(r'#\w+', '', str(title or '')).strip() or 'TikTok Video'
    text_x = avt_x + avt_size + 16
    avail_title_w = LW - pad - 190 - text_x

    cv.text(text_x, avt_y + 8, cv.fit(clean_title, f_title, avail_title_w), f_title, G.C_TEXT, vcenter=True)

    author_disp = f"👤 {author_nick or 'Creator'}"
    if author_user and author_user != author_nick:
        author_disp += f" (@{author_user})"
    tw_auth = cv.text(text_x, avt_y + 32, cv.fit(author_disp, f_author, avail_title_w - 70), f_author, (215, 230, 255), vcenter=True)

    if region:
        reg_str = f"📍 {region.upper()}"
        cv.pill(text_x + tw_auth + 12, avt_y + 23, reg_str, f_sub, ((59, 130, 246), (37, 99, 235)), h=18, padx=8)

    # 6. Badge VIP Top Right: "NO WATERMARK"
    badge_w = 142
    bx2 = LW - pad - 18
    bx1 = bx2 - badge_w
    cv.pill(bx2, avt_y + 12, "NO WATERMARK", f_badge, g_tt, h=24, padx=12, align="r")

    # 7. Đường phân cách kính mờ
    div_y = pad + 82
    cv.rrect((content_x, div_y, LW - pad - 18, div_y + 1), 0.5, fill=(255, 255, 255, 35))

    # 8. 4 Hộp Stats Kính Lỏng (Liquid Glass Capsules)
    stats = [
        ("❤️", likes, "Likes", (254, 44, 85)),
        ("💬", comments, "Comments", (0, 242, 234)),
        ("🔁", shares, "Shares", (245, 158, 11)),
        ("👁️", views, "Views", (16, 185, 129)),
    ]
    grid_y = div_y + 16
    stats_x = content_x
    stats_right = LW - pad - 18
    box_w = (stats_right - stats_x - 30) / 4
    box_h = 78
    f_stat_val = cv.font("b", 16)
    f_stat_lbl = cv.font("r", 11)

    for i, (emoji, val, lbl, col) in enumerate(stats):
        cx1 = stats_x + i * (box_w + 10)
        cx2 = cx1 + box_w
        # Hộp kính lỏng
        cv.glass((cx1, grid_y, cx2, grid_y + box_h), 12, blur=6, tint=(16, 22, 38, 80),
                 magnify=1.0, saturate=1.1, highlight=32, rim=(160, 35), shadow=True, shadow_opacity=50)
        # Vạch màu accent bên trái hộp
        cv.grad((cx1 + 4, grid_y + 14, cx1 + 7.5, grid_y + box_h - 14), 2, col,
                tuple(max(0, int(v * 0.6)) for v in col[:3]))

        cv.text(cx1 + 18, grid_y + 22, f"{emoji} {val}", f_stat_val, G.C_TEXT, vcenter=True)
        cv.text(cx1 + 20, grid_y + 48, lbl, f_stat_lbl, G.C_MUTED, vcenter=True)

    # 9. Footer: Hashtags & Nhạc nền
    foot_y = grid_y + box_h + 16
    f_foot = cv.font("r", 11)
    if hashtags:
        tag_str = ' '.join(hashtags[:6])
        if len(tag_str) > 75: tag_str = tag_str[:72] + '...'
        cv.text(content_x, foot_y + 10, f"🏷️ {tag_str}", f_foot, (0, 242, 234), vcenter=True)

    if music_name:
        m_txt = f"🎵 {music_name}"
        cv.text(LW - pad - 20, foot_y + 10, cv.fit(m_txt, f_foot, 280), f_foot, G.C_MUTED, align="r", vcenter=True)

    return cv.finalize()

async def async_tiktok_video_card(title, author_nick, author_user='', region='', avatar_url=None, likes='0', comments='0', shares='0', views='0', hashtags=None, music_name='', cover_url=None):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, render_tiktok_video_card, title, author_nick, author_user, region, avatar_url, likes, comments, shares, views, hashtags, music_name, cover_url)


def render_media_post_card(platform: str, title: str, author_nick: str, author_user: str = '', avatar_url: str = None, cover_url: str = None, likes: str = '0', comments: str = '0', shares: str = '0', views: str = '0', badge: str = 'HD', hashtags: list = None, extra_info: str = ''):
    try:
        from apps.user_discord.utils import glass as G
    except ImportError:
        from utils import glass as G

    LW, LH = 1020, 340
    pad = 18
    cv = G.GlassCanvas(LW, LH, scale=2, out=1.5)

    # 1. Outer Glass Panel bo góc lớn
    panel_box = (pad, pad, LW - pad, LH - pad)
    cv.glass(panel_box, 20, blur=24, tint=(14, 18, 32, 110), magnify=1.02, saturate=1.15,
             highlight=55, rim=(220, 60), shadow=True, shadow_opacity=65)

    # Bảng màu Accent cho từng nền tảng
    p_low = str(platform).lower()
    if any(k in p_low for k in ["fb", "face"]):
        p_name = "FACEBOOK"
        g_accent = ((24, 119, 242), (10, 80, 180))
        border_col = (24, 119, 242, 230)
    elif any(k in p_low for k in ["ig", "insta"]):
        p_name = "INSTAGRAM"
        g_accent = ((225, 48, 108), (253, 29, 29))
        border_col = (225, 48, 108, 230)
    elif any(k in p_low for k in ["x", "twit"]):
        p_name = "X (TWITTER)"
        g_accent = ((29, 155, 240), (15, 90, 160))
        border_col = (29, 155, 240, 230)
    elif "thread" in p_low:
        p_name = "THREADS"
        g_accent = ((230, 230, 230), (100, 100, 100))
        border_col = (240, 240, 240, 230)
    else:
        p_name = platform.upper()
        g_accent = ((56, 189, 248), (14, 116, 144))
        border_col = (56, 189, 248, 230)

    # 2. Thanh Accent Neon Gradient ở đỉnh
    cv.grad((pad + 24, pad + 1, LW - pad - 24, pad + 4), 2, g_accent[0], g_accent[1])

    # 3. Ảnh bìa video/ảnh với lớp phủ nút phát nếu là video
    thumb_x, thumb_y = pad + 14, pad + 14
    thumb_w, thumb_h = 282, LH - 2 * pad - 28
    thumb_img = _fetch_img(cover_url) if cover_url else None
    if thumb_img:
        thumb_size = (int(round(thumb_w * cv.k)), int(round(thumb_h * cv.k)))
        thumb_img = ImageOps.fit(thumb_img.convert('RGBA'), thumb_size, method=Image.Resampling.LANCZOS)
        thumb_img.alpha_composite(Image.new('RGBA', thumb_size, (5, 10, 20, 35)))
        thumb_draw = ImageDraw.Draw(thumb_img)
        cx, cy = thumb_size[0] // 2, thumb_size[1] // 2
        play_r = int(round(25 * cv.k))
        thumb_draw.ellipse((cx - play_r, cy - play_r, cx + play_r, cy + play_r), fill=(8, 12, 20, 190), outline=(255, 255, 255, 210), width=max(1, int(round(2 * cv.k))))
        inset = int(round(8 * cv.k))
        thumb_draw.polygon(((cx - inset // 2, cy - inset), (cx - inset // 2, cy + inset), (cx + inset, cy)), fill=(255, 255, 255, 245))
        thumb_mask = Image.new('L', thumb_size, 0)
        ImageDraw.Draw(thumb_mask).rounded_rectangle((0, 0, thumb_size[0] - 1, thumb_size[1] - 1), radius=int(round(15 * cv.k)), fill=255)
        thumb_img.putalpha(thumb_mask)
        cv._comp(thumb_img, cv.s(thumb_x), cv.s(thumb_y))
        cv.rrect((thumb_x, thumb_y, thumb_x + thumb_w, thumb_y + thumb_h), 15, fill=(0, 0, 0, 0), outline=(255, 255, 255, 75), width=1)
    else:
        cv.glass((thumb_x, thumb_y, thumb_x + thumb_w, thumb_y + thumb_h), 15, blur=8, tint=(9, 18, 32, 150),
                 magnify=1.0, saturate=1.0, highlight=28, rim=(120, 35), shadow=False)
        cv.text(thumb_x + thumb_w / 2, thumb_y + thumb_h / 2, p_name, cv.font("b", 18), (220, 235, 245), align="c", vcenter=True)

    # 4. Avatar Người Đăng (Bo tròn với viền Neon Accent)
    avt_size = 54
    content_x = thumb_x + thumb_w + 24
    avt_x, avt_y = content_x, pad + 18
    avt_img = None
    if avatar_url:
        try:
            raw_avt = _fetch_img(avatar_url)
            if raw_avt is not None:
                raw_avt = raw_avt.convert('RGBA')
                s_size = cv.s(avt_size)
                raw_avt = ImageOps.fit(raw_avt, (s_size, s_size), method=Image.Resampling.LANCZOS)
                mask = Image.new('L', (s_size, s_size), 0)
                ImageDraw.Draw(mask).ellipse([(0, 0), (s_size - 1, s_size - 1)], fill=255)
                circle_avt = Image.new('RGBA', (s_size, s_size), (0, 0, 0, 0))
                circle_avt.paste(raw_avt, (0, 0), mask)
                ImageDraw.Draw(circle_avt).ellipse([(0, 0), (s_size - 1, s_size - 1)], outline=border_col, width=cv.s(2))
                avt_img = circle_avt
        except Exception:
            pass

    if avt_img:
        cv._comp(avt_img, cv.s(avt_x), cv.s(avt_y))
    else:
        letter = str(author_nick or p_name)[:1].upper()
        cv.circle_image(None, avt_x, avt_y, avt_size, ring=g_accent,
                        letter=letter, fill=(28, 42, 58))

    # 5. Tiêu đề bài viết & Tác giả
    f_title = cv.font("b", 15)
    f_author = cv.font("b", 12.5)
    f_sub = cv.font("r", 11)
    f_badge = cv.font("b", 10)

    clean_title = re.sub(r'#\w+', '', str(title or '')).strip() or f'{p_name} Media'
    text_x = avt_x + avt_size + 16
    avail_title_w = LW - pad - 190 - text_x

    cv.text(text_x, avt_y + 8, cv.fit(clean_title, f_title, avail_title_w), f_title, G.C_TEXT, vcenter=True)

    author_disp = f"👤 {author_nick or 'Creator'}"
    if author_user and author_user != author_nick:
        author_disp += f" (@{author_user})"
    cv.text(text_x, avt_y + 32, cv.fit(author_disp, f_author, avail_title_w - 50), f_author, (215, 230, 255), vcenter=True)

    # 6. Badge Top Right
    bx2 = LW - pad - 18
    cv.pill(bx2, avt_y + 12, badge, f_badge, g_accent, h=24, padx=12, align="r")

    # 7. Đường phân cách kính mờ
    div_y = pad + 82
    cv.rrect((content_x, div_y, LW - pad - 18, div_y + 1), 0.5, fill=(255, 255, 255, 35))

    # 8. 4 Hộp Stats Kính Lỏng (Liquid Glass Capsules)
    stats = [
        ("❤️", str(likes or '0'), "Likes", (254, 44, 85)),
        ("💬", str(comments or '0'), "Comments", (0, 242, 234)),
        ("🔁", str(shares or '0'), "Shares", (245, 158, 11)),
        ("👁️", str(views or '0'), "Views", (16, 185, 129)),
    ]
    grid_y = div_y + 16
    stats_x = content_x
    stats_right = LW - pad - 18
    box_w = (stats_right - stats_x - 30) / 4
    box_h = 78
    f_stat_val = cv.font("b", 16)
    f_stat_lbl = cv.font("r", 11)

    for i, (emoji, val, lbl, col) in enumerate(stats):
        cx1 = stats_x + i * (box_w + 10)
        cx2 = cx1 + box_w
        cv.glass((cx1, grid_y, cx2, grid_y + box_h), 12, blur=6, tint=(16, 22, 38, 80),
                 magnify=1.0, saturate=1.1, highlight=32, rim=(160, 35), shadow=True, shadow_opacity=50)
        cv.grad((cx1 + 4, grid_y + 14, cx1 + 7.5, grid_y + box_h - 14), 2, col,
                tuple(max(0, int(v * 0.6)) for v in col[:3]))

        cv.text(cx1 + 18, grid_y + 22, f"{emoji} {val}", f_stat_val, G.C_TEXT, vcenter=True)
        cv.text(cx1 + 20, grid_y + 48, lbl, f_stat_lbl, G.C_MUTED, vcenter=True)

    # 9. Footer: Hashtags & Extra Info
    foot_y = grid_y + box_h + 16
    f_foot = cv.font("r", 11)
    if hashtags:
        tag_str = ' '.join(hashtags[:6])
        if len(tag_str) > 75: tag_str = tag_str[:72] + '...'
        cv.text(content_x, foot_y + 10, f"🏷️ {tag_str}", f_foot, g_accent[0], vcenter=True)

    if extra_info:
        cv.text(LW - pad - 20, foot_y + 10, cv.fit(extra_info, f_foot, 280), f_foot, G.C_MUTED, align="r", vcenter=True)

    return cv.finalize()


async def async_media_post_card(platform: str, title: str, author_nick: str, author_user: str = '', avatar_url: str = None, cover_url: str = None, likes: str = '0', comments: str = '0', shares: str = '0', views: str = '0', badge: str = 'HD', hashtags: list = None, extra_info: str = ''):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, render_media_post_card, platform, title, author_nick, author_user, avatar_url, cover_url, likes, comments, shares, views, badge, hashtags, extra_info)


async def setup(bot):
    """Extension loader hook cho main.py"""
    pass

