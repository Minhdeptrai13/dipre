# -*- coding: utf-8 -*-
"""
menu.py - Bảng điều khiển DASHBOARD (sidebar + lưới card lệnh).

Cấu trúc theo ảnh mẫu:
  • Panel tối bo góc, nền ảnh backgrounds/ mờ phía sau.
  • Sidebar trái: avatar người gọi + pill ONLINE, mục "TỔNG QUAN",
    các danh mục (category) kèm icon màu + số lệnh (dòng active tô sáng),
    card người dùng nhỏ ở dưới cùng.
  • Khu chính: header "BẢNG ĐIỀU KHIỂN" + pill SELECT + trạng thái
    ONLINE/Prefix; lưới card lệnh 2 cột x 5 dòng (10 lệnh/trang):
    icon màu + tên lệnh + badge + mô tả; footer phân trang + mẹo.
  • SUPERSAMPLING: vẽ ở RENDER_SCALE(2x), xuất OUTPUT_SCALE(1.25x) -> JPEG.
  • Icon font Symbola (glyph thiếu -> chữ cái đầu lệnh).
"""
from __future__ import annotations

import asyncio
import io
import math
import os
from pathlib import Path
import random
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageStat

from apps.shared.paths import SHARED_BACKGROUNDS_DIR, SHARED_FONTS_DIR
try:
    from apps.user_discord.utils.autorep import autorep
    from apps.user_discord.utils.autodelet import autodelet
    from apps.user_discord.utils.menu_catalog import build_menu_groups, menu_entry
    from apps.user_discord.utils.prefix import get_prefix
    from apps.user_discord.utils import glass as G
    from apps.user_discord.utils.glass import load_background
    from apps.user_discord.core.alias import alias_declare
except ImportError:
    from utils.autorep import autorep
    from utils.autodelet import autodelet
    from utils.menu_catalog import build_menu_groups, menu_entry
    try:
        from core.alias import alias_declare
    except ImportError:
        def alias_declare(*args, **kwargs):
            return lambda f: f
    from utils.prefix import get_prefix
    import utils.glass as G
    from utils.glass import load_background

try:
    from apps.user_discord.utils.card_registry import get_card
    from apps.user_discord.utils.media_card import async_help_card
except ImportError:
    try:
        from utils.card_registry import get_card
        from utils.media_card import async_help_card
    except ImportError:
        get_card = lambda k: None
        async_help_card = None


# ── Thông số render (FAST MODE: dep + nhanh) ───────
LAYOUT_W = 1120
RENDER_SCALE = 2         # Vẽ ở 2x (2240px)
OUTPUT_SCALE = 1.25      # Xuất 1.25x (1400px - nhe hon 30% ma van net)
MENU_PAGE_SIZE = 10      # 10 lệnh/trang (2 cột x 5 dòng) khít sát nhau, sân khấu anime cực đại
MENU_FILE_FORMAT = "JPEG"  # JPEG ~150-250KB vs PNG ~1.5-3MB
MENU_JPEG_QUALITY = 82
MENU_CACHE_TTL = 90.0
_MENU_PAGE_CACHE: Dict[tuple, tuple] = {}

C_TEXT = (255, 255, 255)
C_MUTED = (230, 238, 250)
C_DIM = (180, 195, 215)
SHADOW_TXT = (0, 0, 0, 180)

BADGE_COLORS = {
    "ROOT": ((239, 68, 68), (190, 18, 60)),
    "ADMIN": ((245, 158, 11), (217, 119, 6)),
    "AUTO": ((59, 130, 246), (37, 99, 235)),
    "UTIL": ((16, 185, 129), (5, 150, 105)),
    "HD": ((20, 184, 166), (13, 148, 136)),
    "VOICE": ((249, 115, 22), (234, 88, 12)),
}
BADGE_DEFAULT = ((99, 102, 241), (79, 70, 229))


ANIME_PROFILES = {
    "chosen_gojo_satoru": {
        "theme_name": "Gojo Satoru - Vô Hạ Hạn",
        "crop_banner": (0.15, 0.02, 0.85, 0.45),
        "ring_color": ((56, 189, 248), (14, 165, 233)),
        "accent": (56, 189, 248),
        "sec": (125, 211, 252),
    },
    "chosen_sung_jinwoo": {
        "theme_name": "Sung Jin-Woo - Shadow Monarch",
        "crop_banner": (0.15, 0.05, 0.85, 0.35),
        "ring_color": ((139, 92, 246), (192, 132, 252)),
        "accent": (139, 92, 246),
        "sec": (192, 132, 252),
    },
    "chosen_raiden_shogun": {
        "theme_name": "Raiden Shogun - Lôi Thần",
        "crop_banner": (0.12, 0.02, 0.88, 0.48),
        "ring_color": ((168, 85, 247), (217, 70, 239)),
        "accent": (168, 85, 247),
        "sec": (217, 70, 239),
    },
    "chosen_roronoa_zoro": {
        "theme_name": "Roronoa Zoro - Quỷ Kiếm Asura",
        "crop_banner": (0.10, 0.02, 0.90, 0.50),
        "ring_color": ((16, 185, 129), (5, 150, 105)),
        "accent": (16, 185, 129),
        "sec": (52, 211, 153),
    },
    "chosen_frieren": {
        "theme_name": "Frieren - Pháp Sư Ngàn Năm",
        "crop_banner": (0.10, 0.02, 0.90, 0.52),
        "ring_color": ((45, 212, 191), (56, 189, 248)),
        "accent": (45, 212, 191),
        "sec": (56, 189, 248),
    },
    "chosen_hu_tao": {
        "theme_name": "Hu Tao - Điệp Vũ Hỏa Diệm",
        "crop_banner": (0.08, 0.02, 0.92, 0.60),
        "ring_color": ((249, 115, 22), (239, 68, 68)),
        "accent": (249, 115, 22),
        "sec": (239, 68, 68),
    },
    "chosen_kafka": {
        "theme_name": "Kafka - Thợ Săn Stellaron",
        "crop_banner": (0.10, 0.02, 0.90, 0.50),
        "ring_color": ((192, 38, 211), (139, 92, 246)),
        "accent": (192, 38, 211),
        "sec": (139, 92, 246),
    },
    "chosen_arlecchino": {
        "theme_name": "Arlecchino - Quan Chấp Hành Knave",
        "crop_banner": (0.10, 0.02, 0.90, 0.45),
        "ring_color": ((225, 29, 72), (159, 18, 57)),
        "accent": (225, 29, 72),
        "sec": (244, 63, 94),
    },
    "chosen_tanjiro": {
        "theme_name": "Kamado Tanjiro - Hinokami",
        "crop_banner": (0.08, 0.02, 0.92, 0.55),
        "ring_color": ((239, 68, 68), (249, 115, 22)),
        "accent": (239, 68, 68),
        "sec": (249, 115, 22),
    },
    "chosen_acheron": {
        "theme_name": "Acheron - Tuyệt Diệt Hoàng Hôn",
        "crop_banner": (0.08, 0.02, 0.92, 0.55),
        "ring_color": ((147, 51, 234), (219, 39, 119)),
        "accent": (147, 51, 234),
        "sec": (219, 39, 119),
    }
}


def _glyph_set(path: str) -> Optional[set]:
    """Tập codepoint font hỗ trợ."""
    try:
        from fontTools.ttLib import TTFont
        return set(TTFont(path).getBestCmap().keys())
    except Exception:
        return None


def _vgrad_L(w: int, h: int, top: int, bottom: int) -> Image.Image:
    """Mask L gradient dọc: giá trị `top` ở trên -> `bottom` ở dưới."""
    g = Image.linear_gradient("L").resize((max(1, w), max(1, h)), Image.Resampling.BILINEAR)
    return g.point(lambda v: int(top + (bottom - top) * v / 255))


_HGRAD_CACHE: Dict[Tuple[int, int, Tuple, Tuple], Image.Image] = {}


def _hgrad_rgb(w: int, h: int, c1, c2) -> Image.Image:
    w, h = int(w), int(h)
    key = (w, h, tuple(c1[:3]), tuple(c2[:3]))
    hit = _HGRAD_CACHE.get(key)
    if hit is not None:
        return hit
    g = Image.linear_gradient("L").rotate(90, expand=True).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    g = g.resize((max(1, w), max(1, h)), Image.Resampling.BILINEAR)
    a = Image.new("RGB", g.size, tuple(c1[:3]))
    b = Image.new("RGB", g.size, tuple(c2[:3]))
    res = Image.composite(b, a, g).convert("RGBA")
    if len(_HGRAD_CACHE) < 200:
        _HGRAD_CACHE[key] = res
    return res


def _encode_menu_file(final_img: Image.Image, page: int, total_pages: int) -> discord.File:
    """Encode PNG chất lượng cao, giữ trọn độ trong suốt và độ nét Liquid Glass."""
    buf = io.BytesIO()
    final_img.save(buf, format="PNG", compress_level=3)
    buf.seek(0)
    return discord.File(fp=buf, filename=f"menu-p{page}.png")


class UserMenu(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.font_bold = str(SHARED_FONTS_DIR / "BeVietnamPro-Bold.ttf")
        self.font_reg = str(SHARED_FONTS_DIR / "BeVietnamPro-Regular.ttf")
        self.font_sym = str(SHARED_FONTS_DIR / "Symbola.ttf")
        self.font_modak = str(SHARED_FONTS_DIR / "DFVN-Modak.ttf")
        self._sym_cmap = _glyph_set(self.font_sym) if os.path.exists(self.font_sym) else set()
        self._font_cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}

    # ── tiện ích chung ──────────────────────────────────────────────────────
    def get_prefix(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return getattr(self.bot, "_own_prefix", None) or ""

    def _font(self, path: str, size: float) -> ImageFont.FreeTypeFont:
        px = max(1, int(round(size * RENDER_SCALE)))
        key = (path, px)
        if key not in self._font_cache:
            try:
                self._font_cache[key] = ImageFont.truetype(path, px)
            except Exception:
                self._font_cache[key] = ImageFont.load_default()
        return self._font_cache[key]

    @staticmethod
    def _s(v: float) -> int:
        return int(round(v * RENDER_SCALE))

    def _box(self, x1, y1, x2, y2) -> List[int]:
        return [self._s(x1), self._s(y1), self._s(x2), self._s(y2)]

    @staticmethod
    def _rmask(w: int, h: int, radius: int, fill: int = 255) -> Image.Image:
        try:
            from apps.user_discord.utils.glass import rmask as _g_rmask
            return _g_rmask(w, h, radius, fill)
        except Exception:
            pass
        return rmask(w, h, radius, fill)

    def _icon_char(self, sym: str, fallback_name: str) -> Tuple[str, bool]:
        clean = "".join(ch for ch in (sym or "") if ch not in "\ufe0f\u200d")
        if clean:
            ch = clean[0]
            if self._sym_cmap is None or ord(ch) in self._sym_cmap:
                return ch, True
        letter = next((c for c in fallback_name if c.isalpha()), "•")
        return letter.upper(), False

    def _text_fit(self, draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
        if draw.textlength(text, font=font) <= max_w:
            return text
        while len(text) > 1 and draw.textlength(text + "…", font=font) > max_w:
            text = text[:-1]
        return text.rstrip() + "…"

    def _txt(self, d: ImageDraw.ImageDraw, xy, text: str, font, fill, shadow: bool = True):
        """Chữ có bóng mềm (vẽ qua layer cục bộ -> pha alpha đúng, không ghi đè)."""
        x, y = int(xy[0]), int(xy[1])
        canvas = getattr(d, "_image", None)
        if shadow and canvas is not None and text:
            bb = d.textbbox((0, 0), text, font=font)
            m = RENDER_SCALE * 3
            lw, lh = bb[2] + m * 2, bb[3] + m * 2
            layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
            ImageDraw.Draw(layer).text((m, m), text, font=font, fill=SHADOW_TXT)
            layer = layer.filter(ImageFilter.GaussianBlur(RENDER_SCALE * 0.8))
            ox, oy = x - m, y - m + max(1, RENDER_SCALE // 2)
            if ox >= 0 and oy >= 0:
                canvas.alpha_composite(layer, (ox, oy))
        if len(fill) == 4 and canvas is not None and fill[3] < 255:
            bb = d.textbbox((0, 0), text, font=font)
            layer = Image.new("RGBA", (bb[2] + 4, bb[3] + 4), (0, 0, 0, 0))
            ImageDraw.Draw(layer).text((0, 0), text, font=font, fill=fill)
            canvas.alpha_composite(layer, (x, y))
        else:
            d.text((x, y), text, font=font, fill=fill[:3] if len(fill) == 4 else fill)

    def _rrect_alpha(self, canvas: Image.Image, box, radius, fill=None, outline=None, width=0):
        """Khối bo góc bán trong suốt, pha alpha đúng (layer cục bộ)."""
        x1, y1, x2, y2 = map(int, box)
        layer = Image.new("RGBA", (x2 - x1, y2 - y1), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle(
            [0, 0, x2 - x1 - 1, y2 - y1 - 1], radius=radius, fill=fill, outline=outline, width=width)
        canvas.alpha_composite(layer, (x1, y1))

    def _paste_grad(self, canvas: Image.Image, box, radius, c1, c2, alpha=255):
        x1, y1, x2, y2 = map(int, box)
        w, h = x2 - x1, y2 - y1
        canvas.paste(_hgrad_rgb(w, h, c1, c2), (x1, y1), self._rmask(w, h, radius, alpha))

    def _soft_shadow(self, canvas: Image.Image, box, radius, blur=14, offset=6, opacity=110):
        """Bóng mềm siêu tốc — downsample 4x khi GaussianBlur vùng shadow."""
        x1, y1, x2, y2 = map(int, box)
        b = self._s(blur)
        off = self._s(offset)
        pad = b * 2
        w, h = x2 - x1 + pad * 2, y2 - y1 + pad * 2
        sk = 4
        layer = Image.new("RGBA", (max(1, w // sk), max(1, h // sk)), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle(
            [pad // sk, (pad + off) // sk, (pad + x2 - x1) // sk, (pad + off + y2 - y1) // sk],
            radius=max(1, radius // sk), fill=(0, 0, 0, opacity))
        layer = layer.filter(ImageFilter.GaussianBlur(max(0.5, b / 2 / sk)))
        layer = layer.resize((w, h), Image.Resampling.BICUBIC)
        canvas.alpha_composite(layer, (max(0, x1 - pad), max(0, y1 - pad)),
                               (max(0, pad - x1), max(0, pad - y1)))

    def _neon_rim(self, canvas: Image.Image, box, radius: int,
                  colors: Tuple[Tuple[int, int, int], Tuple[int, int, int]],
                  width: int = 1, glow_width: int = 3, glow_alpha: int = 80):
        """Vẽ viền gradient với hiệu ứng phát quang dạ quang (Neon Glow Rim)."""
        x1, y1, x2, y2 = map(int, box)
        w, h = x2 - x1, y2 - y1
        if w < 4 or h < 4:
            return
        c1, c2 = colors
        grad = _hgrad_rgb(w, h, c1, c2)
        if glow_width > 0 and glow_alpha > 0:
            gw = Image.new("L", (w, h), 0)
            ImageDraw.Draw(gw).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, outline=255, width=glow_width)
            gw = gw.filter(ImageFilter.GaussianBlur(self._s(1.2)))
            glow_layer = grad.copy()
            glow_layer.putalpha(gw.point(lambda v: int(v * (glow_alpha / 255.0))))
            canvas.alpha_composite(glow_layer, (x1, y1))
        rw = Image.new("L", (w, h), 0)
        ImageDraw.Draw(rw).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, outline=255, width=width)
        rim_layer = grad.copy()
        rim_layer.putalpha(rw)
        canvas.alpha_composite(rim_layer, (x1, y1))

    def _glow_txt(self, canvas: Image.Image, xy, text: str, font, fill,
                  glow_col=(56, 189, 248), glow_radius: float = 2.4, glow_opacity: int = 140):
        """Chữ phát quang neon rực rỡ với vầng sáng mịn màng."""
        x, y = int(xy[0]), int(xy[1])
        if not text:
            return
        d = ImageDraw.Draw(canvas, "RGBA")
        bb = d.textbbox((0, 0), text, font=font)
        m = self._s(8)
        lw, lh = (bb[2] - bb[0]) + m * 2, (bb[3] - bb[1]) + m * 2
        gl = Image.new("RGBA", (max(1, lw), max(1, lh)), (0, 0, 0, 0))
        d_gl = ImageDraw.Draw(gl)
        d_gl.text((m - bb[0], m - bb[1]), text, font=font, fill=tuple(list(glow_col[:3]) + [glow_opacity]))
        gl = gl.filter(ImageFilter.GaussianBlur(max(0.8, self._s(glow_radius))))
        canvas.alpha_composite(gl, (x - m, y - m))
        self._txt(d, xy, text, font, fill, shadow=True)

    # ── LIQUID GLASS ────────────────────────────────────────────────────────
    def _glass(self, canvas: Image.Image, box, radius: int, *,
               blur: float = 24, tint=None, tint_grad=None,
               magnify: float = 1.05, saturate: float = 1.45, brighten: Optional[float] = None,
               highlight: Optional[int] = None, rim: Optional[Tuple[int, int]] = None,
               shadow: bool = True, shadow_opacity: int = 55, caustics: bool = True,
               water: float = 0.0, **kwargs):
        """Phủ 1 khối kính lỏng Apple Crystal pha lê quang học thích ứng lên canvas."""
        x1, y1, x2, y2 = map(int, box)
        w, h = x2 - x1, y2 - y1
        if w < 4 or h < 4:
            return

        # 1. Đo độ sáng vùng kính để tự động chọn tương phản thích ứng
        region = canvas.crop((x1, y1, x2, y2))
        stat = ImageStat.Stat(region.convert("L"))
        avg_lum = stat.mean[0]

        if tint is None:
            if avg_lum > 165:
                tint = (16, 22, 34, int(75 + min(60, (avg_lum - 165) * 0.9)))
                brighten_factor = brighten if brighten is not None else 0.92
                highlight_val = 32 if highlight is None else highlight
                caustic_alpha = 26
                caustic_fill = (255, 255, 255)
            elif avg_lum < 95:
                tint = (255, 255, 255, 75)
                brighten_factor = brighten if brighten is not None else 1.45
                highlight_val = 58 if highlight is None else highlight
                caustic_alpha = 46
                caustic_fill = (235, 248, 255)
            else:
                t = (avg_lum - 95) / (165 - 95)
                white_a = int(75 * (1 - t) + 20 * t)
                tint = (255, 255, 255, white_a)
                brighten_factor = brighten if brighten is not None else (1.45 * (1 - t) + 1.06 * t)
                highlight_val = int(58 * (1 - t) + 32 * t) if highlight is None else highlight
                caustic_alpha = int(46 * (1 - t) + 26 * t)
                caustic_fill = (235, 248, 255)
        else:
            brighten_factor = brighten if brighten is not None else 1.42
            highlight_val = 55 if highlight is None else highlight
            caustic_alpha = 44
            caustic_fill = (235, 248, 255)

        if shadow:
            self._soft_shadow(canvas, box, radius, blur=28, offset=8, opacity=shadow_opacity)

        # 2. Khúc xạ: phóng nhẹ từ tâm (giả thấu kính)
        if magnify > 1.0:
            mw, mh = max(2, int(w / magnify)), max(2, int(h / magnify))
            ox, oy = (w - mw) // 2, (h - mh) // 2
            region = region.crop((ox, oy, ox + mw, oy + mh))

        # 3. Blur sâu quang học
        k = 4
        small = region.resize((max(2, w // k), max(2, h // k)), Image.Resampling.BILINEAR)
        small = small.filter(ImageFilter.GaussianBlur(max(0.8, self._s(blur) / k / 2)))
        frosted = small.resize((w, h), Image.Resampling.BICUBIC).convert("RGBA")

        if saturate != 1.0:
            rgb = ImageEnhance.Color(frosted.convert("RGB")).enhance(saturate)
            frosted = rgb.convert("RGBA")
        if brighten_factor != 1.0:
            frosted = ImageEnhance.Brightness(frosted.convert("RGB")).enhance(brighten_factor).convert("RGBA")

        # 4. Tint
        if tint_grad:
            c1, c2, a = tint_grad
            tl = _hgrad_rgb(w, h, c1, c2)
            tl.putalpha(a)
            frosted.alpha_composite(tl)
        elif tint:
            frosted.alpha_composite(Image.new("RGBA", (w, h), tint))

        # 5. Nhận diện nguồn sáng toàn cục & uốn tia khúc xạ qua nước/kính
        card_center_x = (x1 + x2) / 2.0
        card_center_y = (y1 + y2) / 2.0
        if not hasattr(self, "_light_source"):
            try:
                bg_small = canvas.convert("L").resize((32, 32), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(2))
                pixels = list(bg_small.getdata())
                max_idx = max(range(len(pixels)), key=lambda i: pixels[i])
                mx = max_idx % 32
                my = max_idx // 32
                self._light_source = (mx / 32.0 * canvas.width, my / 32.0 * canvas.height)
            except Exception:
                self._light_source = (canvas.width * 0.5, canvas.height * 0.2)

        ls_x, ls_y = self._light_source
        dx = card_center_x - ls_x
        dy = card_center_y - ls_y
        dist = math.hypot(dx, dy) or 1.0
        vx, vy = dx / dist, dy / dist
        slant_x = vx * (h * 0.75)

        # 6. Phản quang chùm sáng lăng kính khi ánh sáng đi qua mặt nước/kính (Caustics)
        if caustics and w > 80 and h > 40:
            diag = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            d_diag = ImageDraw.Draw(diag)
            p1 = max(0, min(w, int(w * 0.32 + vx * w * 0.15)))
            p2 = max(0, min(w, p1 + int(w * 0.22)))
            q1 = max(0, min(w, int(p1 + slant_x)))
            q2 = max(0, min(w, int(p2 + slant_x)))

            d_diag.polygon([(p1, 0), (p2, 0), (q2, h), (q1, h)], fill=caustic_fill + (caustic_alpha,))
            d_diag.polygon([(max(0, p1 - int(w * 0.04)), 0), (p1, 0), (q1, h), (max(0, q1 - int(w * 0.04)), h)],
                           fill=(210, 240, 255, int(caustic_alpha * 0.6)))
            
            p3 = max(0, min(w, int(w * 0.70 + vx * w * 0.1)))
            p4 = max(0, min(w, p3 + int(w * 0.12)))
            q3 = max(0, min(w, int(p3 + slant_x)))
            q4 = max(0, min(w, int(p4 + slant_x)))
            d_diag.polygon([(p3, 0), (p4, 0), (q4, h), (q3, h)], fill=(255, 255, 255, int(caustic_alpha * 0.7)))

            blur_rad = max(2.0, h * 0.25)
            diag = diag.filter(ImageFilter.GaussianBlur(blur_rad))
            frosted.alpha_composite(diag)

        # 7. Vệt sáng Specular định hướng theo nguồn sáng + khúc xạ đáy kính
        if highlight_val:
            hl = Image.new("RGBA", (w, h), (255, 255, 255, 0))
            g_raw = Image.linear_gradient("L").resize((max(1, w), max(1, h)), Image.Resampling.BILINEAR)
            if vy >= 0:
                a_curve = g_raw.point(lambda v: int(highlight_val * ((255 - v) / 255.0) ** 2.0))
            else:
                a_curve = g_raw.point(lambda v: int(highlight_val * (v / 255.0) ** 2.0))
            hl.putalpha(a_curve)
            frosted.alpha_composite(hl)

            bot_glow = g_raw.point(lambda v: int((highlight_val * 0.5) * (v / 255.0) ** 2.8))
            b_layer = Image.new("RGBA", (w, h), (255, 255, 255, 0))
            b_layer.putalpha(bot_glow)
            frosted.alpha_composite(b_layer)

        # 8. Rim viền siêu mảnh (chỉ vẽ khi yêu cầu)
        if rim:
            rw = max(1, self._s(0.5))
            ring = Image.new("L", (w, h), 0)
            ImageDraw.Draw(ring).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, outline=255, width=rw)
            ring = ImageChops.multiply(ring, _vgrad_L(w, h, rim[0], rim[1]))
            rl = Image.new("RGBA", (w, h), (255, 255, 255, 0))
            rl.putalpha(ring)
            frosted.alpha_composite(rl)

        canvas.paste(frosted, (x1, y1), self._rmask(w, h, radius))

    # ── nền & avatar ────────────────────────────────────────────────────────
    def _background(self, W: int, H: int) -> Image.Image:
        # Nền random từ thư mục backgrounds / background
        from pathlib import Path
        exts = (".png", ".jpg", ".jpeg", ".webp")
        candidates = []
        for bg_dir in (SHARED_BACKGROUNDS_DIR, Path("backgrounds"), Path("background"), Path(__file__).resolve().parents[3] / "backgrounds", Path(__file__).resolve().parents[3] / "background"):
            try:
                p = Path(bg_dir)
                if p.exists() and p.is_dir():
                    candidates.extend([p / f for f in os.listdir(p) if f.lower().endswith(exts)])
            except Exception:
                continue

        base = None
        if candidates:
            try:
                chosen = random.choice(candidates)
                with Image.open(chosen) as raw:
                    if getattr(raw, "is_animated", False):
                        raw.seek(0)
                    img = raw.convert("RGBA")
                
                # Tự xoay nếu ảnh dọc mà khung ngang
                iw, ih = img.size
                if (W / H >= 1.08 and ih / iw >= 1.08) or (H / W >= 1.08 and iw / ih >= 1.08):
                    img = img.transpose(Image.Transpose.ROTATE_90)
                
                mid = ImageOps.fit(img, (max(W // 4, 64), max(H // 4, 64)), Image.Resampling.LANCZOS)
                mid = mid.filter(ImageFilter.GaussianBlur(1.0))
                base = mid.resize((W, H), Image.Resampling.BICUBIC)
            except Exception:
                base = None

        if base is None:
            try:
                return load_background(W, H)
            except Exception:
                pass
            small = Image.new("RGBA", (160, 120), (14, 16, 30, 255))
            d = ImageDraw.Draw(small, "RGBA")
            for _ in range(7):
                cx, cy = random.randint(0, 160), random.randint(0, 120)
                r = random.randint(25, 55)
                col = random.choice([(99, 102, 241), (236, 72, 153), (16, 185, 129),
                                     (249, 115, 22), (6, 182, 212), (168, 85, 247)])
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (170,))
            small = small.filter(ImageFilter.GaussianBlur(14))
            base = small.resize((W, H), Image.Resampling.BICUBIC)

        base.alpha_composite(Image.new("RGBA", (W, H), (6, 8, 14, 75)))
        return base

    async def _avatar(self, invoker, size_px: int) -> Optional[Image.Image]:
        try:
            url = str(invoker.display_avatar.replace(size=256, format="png").url)
        except Exception:
            try:
                url = str(invoker.display_avatar.url)
            except Exception:
                return None
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=3)) as r:
                    if r.status != 200:
                        return None
                    raw = await r.read()
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            return ImageOps.fit(img, (size_px, size_px), Image.Resampling.LANCZOS)
        except Exception:
            return None

    def _flat_items(self, pfx: str) -> List[Dict[str, Any]]:
        """Tat ca lenh 1 list phang (cho che do ALL + phan trang)."""
        out: List[Dict[str, Any]] = []
        for grp in build_menu_groups(pfx):
            cat = str(grp.get("category", ""))
            for it in grp.get("items", []):
                d = dict(it)
                d["_cat"] = cat
                out.append(d)
        return out

    def _menu_cache_key(self, pfx: str, page: int, mode: str, invoker: Any = None) -> tuple:
        try:
            n = len(self._flat_items(pfx))
        except Exception:
            n = 0
        return (pfx, page, mode, n, getattr(invoker, "id", None))

    def _cat_meta(self, cat: str) -> Tuple[str, Tuple[int, int, int], str, str]:
        """(tenViet, mau, icon_sym, nhan_badge) cho 1 category."""
        u = str(cat or "").upper()
        if "MEDIA" in u:
            return ("Media & Giải trí", (249, 115, 22), "▶", "MEDIA")
        if "AUTOMATION" in u or "QUEST" in u:
            return ("Tự động & Tiện ích", (16, 185, 129), "⚡", "AUTO")
        if "SYSTEM" in u or "SECURITY" in u:
            return ("Hệ thống & Quản trị", (139, 92, 246), "🛡", "SYSTEM")
        short = str(cat or "Khác").strip()[:22] or "Khác"
        first = next((w for w in short.split() if w.isalnum()), "MENU")
        return (short, (99, 102, 241), "•", first.upper()[:8])

    # ── RENDER ──────────────────────────────────────────────────────────────
    async def render_menu_gui(self, invoker: discord.User, page: int = 1, mode: str = "all") -> tuple:
        """Render dashboard menu 1 trang. Tra (file, page, total_pages)."""
        import time as _time
        pfx = self.get_prefix()
        items = self._flat_items(pfx)
        total_pages = max(1, (len(items) + MENU_PAGE_SIZE - 1) // MENU_PAGE_SIZE)
        page = max(1, min(int(page or 1), total_pages))
        key = self._menu_cache_key(pfx, page, mode, invoker)
        hit = _MENU_PAGE_CACHE.get(key)
        if hit is not None:
            buf_bytes, ts = hit
            if _time.monotonic() - ts < MENU_CACHE_TTL:
                return (discord.File(fp=io.BytesIO(buf_bytes), filename=f"menu-p{page}.png"), page, total_pages)
        file = await self._render_dash_page(invoker, pfx, items, page, total_pages)
        try:
            pos = file.fp.getvalue() if hasattr(file.fp, "getvalue") else None
            if pos is not None:
                if len(_MENU_PAGE_CACHE) > 30:
                    _MENU_PAGE_CACHE.pop(next(iter(_MENU_PAGE_CACHE)))
                _MENU_PAGE_CACHE[key] = (pos, _time.monotonic())
        except Exception:
            pass
        return (file, page, total_pages)

    async def _render_dash_page(self, invoker, pfx: str, items: List[Dict[str, Any]],
                                page: int, total_pages: int) -> discord.File:
        """Dashboard Anime Liquid Glass VIP: Tông xuyệt tông, nền mờ nhẹ, nhân vật banner sắc nét."""
        lw, lh = 1060, 600
        start = (page - 1) * MENU_PAGE_SIZE
        chunk = items[start:start + MENU_PAGE_SIZE]
        
        cv = G.GlassCanvas(lw, lh, scale=2, out=1.0)
        
        # ── 1. NẠP HÌNH NỀN ANIME TỪ BACKGROUNDS/MENU & TÔNG XUYỆT TÔNG ──
        menu_bg_dirs = [
            Path("backgrounds/menu"),
            SHARED_BACKGROUNDS_DIR / "menu",
            Path(__file__).resolve().parents[3] / "backgrounds" / "menu",
            Path("backgrounds"),
            SHARED_BACKGROUNDS_DIR,
        ]
        bg_files = []
        for d in menu_bg_dirs:
            if d.exists() and d.is_dir():
                for ext in ("*.png", "*.jpg", "*.jpe", "*.jpeg", "*.webp"):
                    bg_files.extend(list(d.glob(ext)))
                if bg_files:
                    break

        chosen_bg = random.choice(bg_files) if bg_files else None
        bg_stem = chosen_bg.stem if chosen_bg else ""
        profile = ANIME_PROFILES.get(bg_stem, None)

        raw_bg = None
        if chosen_bg and chosen_bg.exists():
            try:
                with Image.open(chosen_bg) as r:
                    raw_bg = r.convert("RGBA")
            except Exception:
                raw_bg = None

        if raw_bg is None:
            raw_bg = G.load_background(cv.W, cv.H)

        # Dynamic Color Palette: Tông xuyệt tông với nhân vật anime
        if not profile:
            crop_banner = (0.2, 0.05, 0.8, 0.85)
            try:
                thumb = raw_bg.resize((32, 32), Image.Resampling.BILINEAR).convert("RGB")
                c_list = thumb.getcolors(maxcolors=1024) or []
                vibrant = []
                for cnt, (r, g, b) in c_list:
                    sat = (max(r, g, b) - min(r, g, b)) / max(max(r, g, b), 1)
                    brt = (r + g + b) / 3
                    if sat > 0.30 and 45 < brt < 225:
                        vibrant.append((sat * cnt, (r, g, b)))
                if vibrant:
                    vibrant.sort(key=lambda x: x[0], reverse=True)
                    acc = vibrant[0][1]
                    sec = vibrant[len(vibrant)//2][1] if len(vibrant) > 1 else (56, 189, 248)
                else:
                    acc, sec = (56, 189, 248), (168, 85, 247)
            except Exception:
                acc, sec = (56, 189, 248), (168, 85, 247)

            profile = {
                "theme_name": "Anime Theme",
                "crop_banner": crop_banner,
                "ring_color": (acc, sec),
                "accent": acc,
                "sec": sec,
            }

        # Nền canvas: Làm mờ nhẹ (Gaussian Blur = 5.0) để card và nhân vật banner nổi bật
        bg_oriented = G.orient_to_canvas(raw_bg.copy(), cv.W, cv.H)
        bg_fitted = ImageOps.fit(bg_oriented, (cv.W, cv.H), Image.Resampling.LANCZOS)
        bg_blurred = bg_fitted.filter(ImageFilter.GaussianBlur(5.0))
        dim_layer = Image.new("RGBA", (cv.W, cv.H), (10, 14, 26, 32))
        cv.c = Image.alpha_composite(bg_blurred, dim_layer)

        # Lấy avatar người dùng và bot
        user_avatar_img = await self._avatar(invoker, 120)
        bot_user = getattr(self.bot, "user", None)
        bot_avatar_img = await self._avatar(bot_user, 60) if bot_user else None

        user_name = str(getattr(invoker, "display_name", None) or getattr(invoker, "name", "Người dùng"))
        bot_name = str(getattr(bot_user, "display_name", None) or getattr(bot_user, "name", "Minhbasan"))

        # ── 2. VẼ SIDEBAR LIQUID GLASS TRÁI ──
        pad = 16
        sb_w = 230
        sb_h = lh - pad * 2
        sb_box = (pad, pad, pad + sb_w, pad + sb_h)
        
        cv.glass(sb_box, 22, blur=18, tint=(15, 22, 38, 70), magnify=1.02, saturate=1.45,
                 brighten=1.10, highlight=60, rim=(255, 140), shadow=True, shadow_opacity=35)
        
        # ── 3. PROFILE NGƯỜI DÙNG Ở ĐỈNH SIDEBAR (Tên + Avatar Người Dùng Lệnh) ──
        av_sz = 58
        av_x = pad + 16
        av_y = pad + 16
        ring_col = profile["ring_color"]
        
        cv.circle_image(user_avatar_img, av_x, av_y, av_sz, ring=ring_col, ring_w=2.5, letter=user_name[:1])
        
        # Chấm tròn Online phát sáng
        dot_r = 5.5
        dot_x = av_x + av_sz - 4
        dot_y = av_y + av_sz - 4
        cv.ellipse((dot_x - dot_r - 2, dot_y - dot_r - 2, dot_x + dot_r + 2, dot_y + dot_r + 2), fill=(12, 16, 28, 255))
        cv.ellipse((dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r), fill=(34, 197, 94, 255))
        
        # Tên người dùng lệnh + Pill • ONLINE
        f_uname = cv.font("b", 14)
        name_fit = cv.fit(user_name, f_uname, sb_w - av_sz - 34)
        cv.text(av_x + av_sz + 12, av_y + 8, name_fit, f_uname, G.C_TEXT)
        cv.pill(av_x + av_sz + 12, av_y + 32, "• ONLINE", cv.font("b", 9), G.G_GREEN, h=18, padx=8)

        # ── DANH MỤC TRÊN SIDEBAR ──
        div_y = av_y + av_sz + 18
        cv.grad((pad + 14, div_y, pad + sb_w - 14, div_y + 1), 0, (255, 255, 255), (255, 255, 255), alpha=35)
        
        cur_y = div_y + 12
        f_cat_h = cv.font("b", 10.5)
        f_cat_r = cv.font("r", 12)
        f_cat_b = cv.font("b", 12)
        f_badge_cnt = cv.font("b", 9)
        
        groups = build_menu_groups(pfx)
        cur_cat = chunk[0].get("_cat") if chunk else None

        cv.text(pad + 16, cur_y, "TỔNG QUAN", f_cat_h, (170, 185, 210))
        cv.text(pad + sb_w - 28, cur_y, str(len(items)), f_cat_h, (175, 190, 215), align="r")
        cur_y += 18

        for grp in groups[:6]:
            cat = str(grp.get("category", ""))
            label, ccol, csym, _ = self._cat_meta(cat)
            cnt = len(grp.get("items", []))
            is_active = (cat == cur_cat)
            
            item_h = 32
            ix1 = pad + 8
            iy1 = cur_y
            ix2 = pad + sb_w - 8
            iy2 = cur_y + item_h
            
            if is_active:
                cv.glass((ix1, iy1, ix2, iy2), 9, blur=12, tint=(255, 255, 255, 25),
                         brighten=1.2, rim=(220, 100), shadow=False)
                cv.text(ix1 + 10, iy1 + 8, csym, f_cat_b, G.C_TEXT)
                cv.text(ix1 + 28, iy1 + 8, label, f_cat_b, G.C_TEXT)
                cv.pill(ix2 - 8, iy1 + 7, str(cnt), f_badge_cnt, G.G_BRAND, h=18, padx=7, align="r")
            else:
                cv.text(ix1 + 10, iy1 + 8, csym, f_cat_r, (185, 200, 225))
                cv.text(ix1 + 28, iy1 + 8, label, f_cat_r, (195, 210, 235))
                cv.text(ix2 - 10, iy1 + 8, str(cnt), f_badge_cnt, (155, 170, 195), align="r")
                
            cur_y += item_h + 3

        # ── PROFILE BOT Ở ĐÁY SIDEBAR (Avatar + Tên Bot) ──
        bot_card_h = 44
        bx1 = pad + 10
        by1 = pad + sb_h - bot_card_h - 10
        bx2 = pad + sb_w - 10
        by2 = by1 + bot_card_h
        
        cv.glass((bx1, by1, bx2, by2), 12, blur=14, tint=(15, 20, 35, 80),
                 rim=(255, 90), shadow=False)
        
        bot_av_sz = 28
        bav_x = bx1 + 8
        bav_y = by1 + (bot_card_h - bot_av_sz) / 2
        cv.circle_image(bot_avatar_img, bav_x, bav_y, bot_av_sz, ring=profile["ring_color"], ring_w=1.8, letter=bot_name[:1])
        
        f_bot_name = cv.font("b", 11)
        f_bot_sub = cv.font("r", 9.5)
        cv.text(bav_x + bot_av_sz + 8, by1 + 7, cv.fit(bot_name, f_bot_name, sb_w - bot_av_sz - 36), f_bot_name, G.C_TEXT)
        cv.text(bav_x + bot_av_sz + 8, by1 + 22, f"Prefix {pfx} • {len(items)} lệnh", f_bot_sub, (185, 200, 225))

        # ── 4. HEADER BANNER (SÂN KHẤU ANIME NHÂN VẬT CHÍNH CỰC ĐẠI + CÂU CHÀO HAY HO) ──
        main_x1 = pad + sb_w + 14
        main_x2 = lw - pad
        head_h = 242  # Banner cực đại 242px tôn vinh nhân vật anime chính
        head_box = (main_x1, pad, main_x2, pad + head_h)
        
        cv.glass(head_box, 20, blur=14, tint=(255, 255, 255, 26), magnify=1.02, saturate=1.35,
                 brighten=1.18, highlight=90, rim=(255, 175), shadow=True, shadow_opacity=35)
        
        # Dán hình nhân vật Anime TO RỰC RỠ, TÔN CHỦ THỂ VỚI HÀO QUANG AURA & LIỀN MÀU
        try:
            if raw_bg is not None:
                char_src = raw_bg.copy()
                iw, ih = char_src.size
                # Canh chuẩn vùng nhân vật chính
                cx1, cy1, cx2, cy2 = profile.get("crop_banner", (0.05, 0.0, 0.95, 0.90))
                c_crop = char_src.crop((int(cx1 * iw), int(cy1 * ih), int(cx2 * iw), int(cy2 * ih)))
                
                banner_w_px = cv.s(main_x2 - main_x1)
                banner_h_px = cv.s(head_h)
                
                # Phóng to nhân vật anime cao 1.25x chiều cao banner để cực kỳ nổi bật
                ch_h = int(banner_h_px * 1.25)
                ch_w = int(c_crop.width * (ch_h / c_crop.height))
                c_resized = c_crop.resize((ch_w, ch_h), Image.Resampling.LANCZOS)
                
                # 1. TÔN NHÂN VẬT: Làm nét và tăng tương phản chủ thể tối đa
                c_resized = ImageEnhance.Brightness(c_resized).enhance(1.15)
                c_resized = ImageEnhance.Color(c_resized).enhance(1.22)
                c_resized = ImageEnhance.Contrast(c_resized).enhance(1.15)
                c_resized = ImageEnhance.Sharpness(c_resized).enhance(1.40)
                
                # 2. Làm mờ nhẹ nền nhân vật bằng cách hòa trộn lớp sương mờ (ambient blur)
                c_blur = c_resized.filter(ImageFilter.GaussianBlur(cv.s(7.0)))
                c_fused = Image.blend(c_resized, c_blur, 0.20)
                c_fused = ImageEnhance.Sharpness(c_fused).enhance(1.30)
                
                # 3. Tạo Gradient chuyển tiếp màu mượt mà
                pos_x_px = max(int(banner_w_px * 0.38), banner_w_px - ch_w)
                pos_y_px = (banner_h_px - ch_h) // 2
                
                fade_m = Image.new("L", (ch_w, ch_h), 255)
                fmd = ImageDraw.Draw(fade_m)
                fade_transition_w = int(ch_w * 0.26)
                for fx in range(fade_transition_w):
                    t = fx / float(fade_transition_w)
                    smooth_alpha = int(255 * (3 * (t ** 2) - 2 * (t ** 3)))
                    fmd.line([(fx, 0), (fx, ch_h)], fill=smooth_alpha)
                    
                hb_mask = G.rmask(banner_w_px, banner_h_px, cv.s(20))
                char_alpha = c_fused.split()[3] if len(c_fused.split()) == 4 else Image.new("L", (ch_w, ch_h), 255)
                char_masked_alpha = ImageChops.multiply(char_alpha, fade_m)
                
                # 4. HIỆU ỨNG TÔN NHÂN VẬT: Tạo lớp Hào Quang Neon (Aura Glow) sau lưng nhân vật
                acc = profile.get("accent", (56, 189, 248))
                aura_layer = Image.new("RGBA", (banner_w_px, banner_h_px), (0, 0, 0, 0))
                aura_patch = Image.new("RGBA", (ch_w, ch_h), acc + (140,))
                aura_patch.putalpha(char_masked_alpha)
                aura_patch = aura_patch.filter(ImageFilter.GaussianBlur(cv.s(16.0)))
                aura_layer.paste(aura_patch, (pos_x_px, pos_y_px), aura_patch.split()[3])
                aura_masked = ImageChops.multiply(aura_layer.split()[3], hb_mask)
                aura_layer.putalpha(aura_masked)
                cv.c.alpha_composite(aura_layer, (cv.s(main_x1), cv.s(pad)))
                
                # Dán nhân vật chính lên trên lớp hào quang
                full_char_plane = Image.new("RGBA", (banner_w_px, banner_h_px), (0, 0, 0, 0))
                full_char_plane.paste(c_fused, (pos_x_px, pos_y_px), char_masked_alpha)
                final_composite_mask = ImageChops.multiply(full_char_plane.split()[3], hb_mask)
                cv.c.paste(full_char_plane, (cv.s(main_x1), cv.s(pad)), final_composite_mask)
                
                # 5. KHỐI LIỀN MÀU TOÀN BẢNG ĐIỀU KHIỂN: Phủ lớp Ambient Light đồng điệu xuyên suốt cả trái và phải
                ambient_tint = Image.new("RGBA", (banner_w_px, banner_h_px), (0, 0, 0, 0))
                d_amb = ImageDraw.Draw(ambient_tint)
                for bx in range(banner_w_px):
                    ratio = bx / float(banner_w_px)
                    a_amb = int(28 + 18 * math.sin(ratio * math.pi))
                    d_amb.line([(bx, 0), (bx, banner_h_px)], fill=acc + (a_amb,))
                    
                ambient_masked = ImageChops.multiply(ambient_tint.split()[3], hb_mask)
                ambient_tint.putalpha(ambient_masked)
                cv.c.alpha_composite(ambient_tint, (cv.s(main_x1), cv.s(pad)))
        except Exception as e:
            print(f"Lỗi dán nhân vật banner: {e}")

        # Chữ trên Header Banner to hoành tráng, kèm câu chào cá nhân hóa cực hay
        f_htitle = cv.font("b", 30.0)
        htx = main_x1 + 26
        hty = pad + 32
        
        cv.text(htx + 1, hty + 1, "Bảng Điều Khiển", f_htitle, (0, 0, 0, 160))
        cv.text(htx, hty, "Bảng Điều Khiển", f_htitle, G.C_TEXT)
        
        tw = cv.tlen("Bảng Điều Khiển", f_htitle)
        cv.pill(htx + tw + 16, hty + 6, "DASHBOARD VIP", cv.font("b", 11.0), G.G_PURPLE, h=26, padx=12)
        
        # Câu chào hay ho và thông điệp truyền cảm hứng cho người dùng
        nice_quotes = [
            f"Chào bạn {user_name}! Chúc bạn một ngày tràn đầy năng lượng & cảm hứng.",
            f"Xin chào {user_name}! Hệ thống sẵn sàng phục vụ mọi tác vụ âm nhạc & tiện ích.",
            f"Yo {user_name}! Thư giãn cùng âm thanh chất lượng cao và không gian giải trí.",
            f"Chào {user_name}! Khám phá kho lệnh đa phương tiện cực chất và tiện lợi.",
            f"Hé lô {user_name}! Chúc bạn có những phút giây thư thái tuyệt vời hôm nay.",
        ]
        # Lấy câu chào ổn định theo ID người gọi
        inv_id = getattr(invoker, "id", 0) or 0
        greeting_text = nice_quotes[inv_id % len(nice_quotes)]
        
        f_greet = cv.font("b", 13.5)
        cv.text(htx + 1, hty + 46, greeting_text, f_greet, (0, 0, 0, 150))
        cv.text(htx, hty + 45, greeting_text, f_greet, (254, 240, 138))  # Màu vàng nắng ấm áp
        
        f_hsub = cv.font("r", 12.5)
        cv.text(htx + 1, hty + 72, f"Hệ thống đa phương tiện & tiện ích tự động hóa cao cấp", f_hsub, (0, 0, 0, 140))
        cv.text(htx, hty + 71, f"Hệ thống đa phương tiện & tiện ích tự động hóa cao cấp", f_hsub, (230, 240, 255))
        
        f_htip = cv.font("r", 11.5)
        cv.text(htx, hty + 98, f"• Chọn danh mục ở sidebar  •  Gõ {pfx}menu <số> để chuyển trang", f_htip, (200, 220, 245))
        cv.pill(htx, hty + 128, f"⚡ HỆ THỐNG SẴN SÀNG", cv.font("b", 9.5), G.G_GREEN, h=22, padx=10)

        # ── 5. LƯỚI CARD LỆNH SÁT NHAU, GỌN GÀNG LIỀN MẠCH (2 cột x 5 hàng = 10 lệnh/trang) ──
        grid_top = pad + head_h + 8
        card_h = 49   # Card nhỏ gọn 49px
        gap_y = 6     # Kéo 5 hàng card lại sát nhau khít rịt (6px)!
        gap_x = 10
        card_w = (main_x2 - main_x1 - gap_x) / 2
        
        # Font chữ card lệnh nhỏ gọn gàng, thanh lịch
        f_cmd_name = cv.font("b", 13.8)
        f_cmd_desc = cv.font("r", 10.5)
        f_badge = cv.font("b", 8.0)
        
        # Thư mục chứa icon brand chuẩn sắc nét (YouTube, TikTok, Facebook, Instagram...)
        icons_dirs = [
            Path("backgrounds/icons"),
            Path("backgrounds/svg"),
            SHARED_BACKGROUNDS_DIR / "icons",
            SHARED_BACKGROUNDS_DIR / "svg",
            Path(__file__).resolve().parents[3] / "backgrounds" / "icons",
        ]
        
        for i, it in enumerate(chunk):
            col = i % 2
            row = i // 2
            cx1 = main_x1 + col * (card_w + gap_x)
            cy1 = grid_top + row * (card_h + gap_y)
            cx2 = cx1 + card_w
            cy2 = cy1 + card_h
            
            # Thẻ lệnh Liquid Glass trong suốt sáng rực
            cv.glass((cx1, cy1, cx2, cy2), 12, blur=12, tint=(16, 22, 38, 70),
                     brighten=1.12, highlight=40, rim=(255, 110), shadow=True, shadow_opacity=22)
            
            # Vạch Neon Accent mép trái
            accent_col = profile.get("accent", (56, 189, 248))
            cv.rrect((cx1 + 3.5, cy1 + 8, cx1 + 6.5, cy2 - 8), 1.5, fill=accent_col + (240,))
            
            # Icon App vuông bo góc 3D kích thước 34px nhỏ gọn
            ic_sz = 34
            ic_x = cx1 + 11
            ic_y = cy1 + (card_h - ic_sz) / 2
            
            raw_cmd_name = str(it.get("name", ""))
            clean_cmd = raw_cmd_name[len(pfx):].lower().strip()
            
            brand_file = None
            brand_map = {
                "yt": "yt.png",
                "youtube": "yt.png",
                "play": "yt.png",
                "tt": "tt.png",
                "tiktok": "tt.png",
                "fb": "fb.png",
                "facebook": "fb.png",
                "ig": "ig.png",
                "instagram": "ig.png",
                "sc": "scl.png",
                "scl": "scl.png",
                "soundcloud": "scl.png",
                "threads": "threads.png",
                "x": "x.png",
                "twitter": "x.png",
                "dl": "dl.png",
                "download": "dl.png",
                "down": "dl.png",
                "tachnhac": "tachnhac.png",
                "stem": "tachnhac.png",
                "info": "info.png",
                "bot": "info.png",
            }
            
            target_icon = brand_map.get(clean_cmd)
            if target_icon:
                for idir in icons_dirs:
                    cand = idir / target_icon
                    if cand.exists():
                        brand_file = cand
                        break
            
            if brand_file:
                try:
                    with Image.open(brand_file) as r_ic:
                        r_ic = r_ic.convert("RGBA")
                        ic_scaled = r_ic.resize((cv.s(ic_sz), cv.s(ic_sz)), Image.Resampling.LANCZOS)
                        cv.c.paste(ic_scaled, (cv.s(ic_x), cv.s(ic_y)), ic_scaled.split()[3])
                except Exception:
                    brand_file = None
            
            if not brand_file:
                icon_bg = tuple((it.get("icon_color") or profile["sec"])[:3])
                cv.rrect((ic_x, ic_y, ic_x + ic_sz, ic_y + ic_sz), 8, fill=icon_bg + (235,),
                         outline=(255, 255, 255, 120), width=1)
                
                ch, is_sym = self._icon_char(it.get("icon_sym", ""), clean_cmd)
                fint = cv.font("b", 16 if not is_sym else 14.5)
                cv.text(ic_x + ic_sz / 2, ic_y + ic_sz / 2, ch, fint, (255, 255, 255), align="c", vcenter=True)
            
            # Badge góc phải
            badge = it.get("badge")
            _lbl, bcol, _sym, bfb = self._cat_meta(str(it.get("_cat", "")))
            if badge:
                bcol = BADGE_COLORS.get(str(badge), BADGE_DEFAULT)[0]
            else:
                badge = bfb
            badge_str = f"• {badge}" if badge else "• CMD"
            
            bw = cv.tlen(badge_str, f_badge) + 14
            badge_x = cx2 - 10
            cv.pill(badge_x, cy1 + 7, badge_str, f_badge, (bcol, bcol), h=18, padx=7, align="r")
            
            # Tên lệnh & mô tả kéo sát lại gần icon hơn (khoảng cách 10px)
            cmd_tx = ic_x + ic_sz + 10
            max_cmd_w = (cx2 - bw - 14) - cmd_tx
            cv.text(cmd_tx, cy1 + 7, cv.fit(raw_cmd_name, f_cmd_name, max_cmd_w), f_cmd_name, G.C_TEXT)
            
            max_desc_w = (cx2 - 10) - cmd_tx
            raw_desc = str(it.get("desc", ""))
            cv.text(cmd_tx, cy1 + 28, cv.fit(raw_desc, f_cmd_desc, max_desc_w), f_cmd_desc, (215, 230, 250))

        # ── 6. FOOTER THANH LỊCH (Phân trang + Hướng dẫn) ──
        foot_h = 34
        foot_y1 = lh - pad - foot_h
        foot_y2 = foot_y1 + foot_h
        cv.glass((main_x1, foot_y1, main_x2, foot_y2), 12, blur=14, tint=(14, 20, 36, 65),
                 rim=(255, 90), shadow=False)
        
        f_foot = cv.font("r", 11.0)
        f_footb = cv.font("b", 11.0)
        
        rng = f"{start + 1}–{start + len(chunk)}" if chunk else "0"
        cv.text(main_x1 + 16, foot_y1 + 10, f"Trang {page}/{total_pages}  •  {rng}/{len(items)} lệnh", f_foot, (190, 205, 230))
        cv.text(main_x2 - 16, foot_y1 + 10, f"{pfx}menu <số> chuyển trang  •  {pfx}menu all xem tất cả", f_footb, (253, 224, 71), align="r")

        buf = cv.finalize(format="PNG")
        return discord.File(fp=buf, filename=f"menu-p{page}.png")

    # (_render_all_page da bo — dashboard render tai _render_dash_page)

    @menu_entry("SYSTEM & SECURITY", "menu", "Bảng điều khiển & danh sách lệnh",
                icon_sym="📋", icon_color=(148, 163, 184), order=2)
    @alias_declare("menu", main="menu", subs=["helpme", "ds"])
    @commands.command(name="menu", aliases=["helpme", "ds"])
    async def cmd_menu(self, ctx: commands.Context, arg1: str = None, arg2: str = None):
        """menu -> trang 1 | menu <so> -> trang do | menu all -> toan bo danh sach."""
        mode = "all"
        page = 1
        full = False
        for a in (arg1, arg2):
            if a is None:
                continue
            s = str(a).strip().lower()
            if s in ("all", "full", "tatca", "het"):
                full = True
            elif s.isdigit():
                page = max(1, int(s))
        # Icon da tha som o on_message -> khong tha lai o day.
        # Tra loi nhanh: gui text truoc, render anh sau (cam giac <1s).
        try:
            wait_msg = await ctx.reply("⏳ Đang mở bảng điều khiển...", mention_author=False)
        except Exception:
            wait_msg = None
        if full:
            # Render streaming: moi chunk 10 anh (gioi han Discord) gui ngay,
            # khong de nguoi goi phai doi render het truoc.
            try:
                pfx_f = self.get_prefix()
                n_items = len(self._flat_items(pfx_f))
                total_pages = max(1, (n_items + MENU_PAGE_SIZE - 1) // MENU_PAGE_SIZE)
                CHUNK = 10
                buf: List[discord.File] = []
                wait_used = False
                for p in range(1, total_pages + 1):
                    f_p, _, _ = await self.render_menu_gui(ctx.author, page=p, mode="all")
                    buf.append(f_p)
                    if len(buf) < CHUNK and p < total_pages:
                        continue
                    part, buf = buf, []
                    label = (f"📋 **FULL MENU** — trang {p - len(part) + 1}-{p}/{total_pages} • {n_items} lệnh"
                             if total_pages > 1 else f"📋 **FULL MENU** — {n_items} lệnh")
                    if wait_msg is not None and not wait_used:
                        try:
                            await wait_msg.edit(content=label, attachments=part)
                            autodelet(wait_msg, delay=120)
                            wait_used = True
                            continue
                        except Exception:
                            pass
                    try:
                        sent_chunk = await autorep(ctx.message, content=label, files=part,
                                                  auto_delete_delay=120, auto_react=False)
                        autodelet(sent_chunk, delay=120)
                    except Exception:
                        try:
                            sent_chunk = await ctx.channel.send(content=label, files=part)
                            autodelet(sent_chunk, delay=120)
                        except Exception:
                            break
                    if p < total_pages:
                        await asyncio.sleep(1.0)
                if wait_msg is not None and not wait_used:
                    try:
                        await wait_msg.delete()
                    except Exception:
                        pass
                try:
                    autodelet(ctx.message, delay=120)
                except Exception:
                    pass
                return
            except Exception as e:
                err = await autorep(ctx.message, content=f"❌ Lỗi render full: {e}", auto_delete_delay=20)
                autodelet(err, delay=20)
                return
        try:
            file, page, total = await self.render_menu_gui(ctx.author, page=page, mode=mode)
        except Exception as e:
            if wait_msg is not None:
                try:
                    await wait_msg.delete()
                except Exception:
                    pass
            err = await autorep(ctx.message, content=f"❌ Lỗi render menu: {e}", auto_delete_delay=20)
            autodelet(err, delay=20)
            return

        has_ui = hasattr(discord, "ui") and hasattr(getattr(discord, "ui", None), "View")
        view = _MenuNavView(self, ctx.author, mode, page, total) if has_ui else None
        nav_hint = f" — gõ `{self.get_prefix()}menu <số>` chuyển trang, `{self.get_prefix()}menu all` xem full"
        sent = None
        try:
            if wait_msg is not None:
                if view is not None:
                    await wait_msg.edit(content=f"📋 **BẢNG ĐIỀU KHIỂN** — trang {page}/{total}{nav_hint}", attachments=[file], view=view)
                else:
                    await wait_msg.edit(content=f"📋 **BẢNG ĐIỀU KHIỂN** — trang {page}/{total}{nav_hint}", attachments=[file])
                sent = wait_msg
            else:
                sent = await autorep(ctx.message, content=f"📋 Trang {page}/{total}{nav_hint}", file=file, auto_delete_delay=60, auto_react=False)
                if view is not None:
                    try:
                        await sent.edit(view=view)
                    except Exception:
                        pass
        except Exception:
            sent = await autorep(ctx.message, file=file, auto_delete_delay=60, auto_react=False)
            if view is not None:
                try:
                    await sent.edit(view=view)
                except Exception:
                    pass

        if sent is not None:
            autodelet(sent, delay=60)
        try:
            autodelet(ctx.message, delay=60)
        except Exception:
            pass

        if view is not None:
            view.message = sent

    # ── LỆNH HELP: XEM CHI TIẾT LỆNH BẰNG LIQUID GLASS CARD ────────────────
    @menu_entry("SYSTEM & SECURITY", "help", "Xem thẻ hướng dẫn chi tiết từng lệnh",
                icon_sym="💡", icon_color=(56, 189, 248), order=3)
    @alias_declare("help", main="help", subs=["hd", "hdsd"])
    @commands.command(name="help", aliases=["hd", "hdsd"])
    async def cmd_help(self, ctx: commands.Context, *, command_name: Optional[str] = None):
        """help <tên_lệnh> -> hiển thị thẻ Liquid Glass Card chi tiết của lệnh."""
        pfx = self.get_prefix()
        if not command_name:
            msg = await autorep(
                ctx.message,
                content=f"💡 **Cú pháp:** `{pfx}help <tên_lệnh>` (Ví dụ: `{pfx}help fb`, `{pfx}help yt`, `{pfx}help img`, `{pfx}help weather`)\n"
                        f"👉 Để xem danh sách tất cả các lệnh, vui lòng gõ `{pfx}menu`.",
                auto_delete_delay=30
            )
            autodelet(msg, delay=30)
            return

        target = str(command_name).strip().lower()
        if get_card and get_card(target) and async_help_card:
            try:
                card_buf = await async_help_card(target, pfx)
                if card_buf:
                    card_file = discord.File(card_buf, filename=f"help_{target}.png")
                    sent = await autorep(
                        ctx.message,
                        content=f"📋 **HƯỚNG DẪN CHI TIẾT LỆNH {target.upper()}**",
                        file=card_file,
                        auto_delete_delay=60
                    )
                    autodelet(sent, delay=60)
                    return
            except Exception as e:
                err = await autorep(ctx.message, content=f"❌ Lỗi tạo thẻ trợ giúp: {e}", auto_delete_delay=20)
                autodelet(err, delay=20)
                return

        msg = await autorep(
            ctx.message,
            content=f"❌ Không tìm thấy thẻ hướng dẫn cho lệnh `{target}`.\n"
                    f"👉 Gõ `{pfx}menu` để xem danh sách lệnh đang có.",
            auto_delete_delay=20
        )
        autodelet(msg, delay=20)


class _MenuNavView:
    """View gia khi discord selfbot khong co discord.ui (menu van chay, chuyen trang bang lenh)."""
    def __init__(self, *a, **k):
        self.message = None


if hasattr(discord, "ui") and hasattr(getattr(discord, "ui", None), "View") and hasattr(discord.ui, "button"):
    _BaseView = discord.ui.View

    class _MenuNavView(_BaseView):  # type: ignore
        """Nut chuyen trang menu: |◀ ◀ ▶ ▶| + ALL."""
        def __init__(self, cog, user, mode: str, page: int, total: int):
            super().__init__(timeout=180)
            self.cog = cog
            self.user = user
            self.mode = mode
            self.page = page
            self.total = max(1, int(total))
            self.message = None

        async def _goto(self, interaction: discord.Interaction, page: int):
            if interaction.user.id != self.user.id:
                return await interaction.response.send_message("❌ Nút này của người gọi menu.", ephemeral=True)
            page = max(1, min(int(page), self.total))
            await interaction.response.defer()
            try:
                file, page, total = await self.cog.render_menu_gui(self.user, page=page, mode=self.mode)
            except Exception as e:
                return await interaction.followup.send(f"❌ Lỗi render: {e}", ephemeral=True)
            self.page, self.total = page, total
            try:
                await interaction.message.edit(content=f"📋 **BẢNG ĐIỀU KHIỂN** — trang {page}/{total}", attachments=[file], view=self)
                autodelet(interaction.message, delay=60)
            except Exception:
                fup = await interaction.followup.send(content=f"📋 Trang {page}/{total}", file=file, view=self)
                autodelet(fup, delay=60)

        @discord.ui.button(label="◀◀", style=discord.ButtonStyle.secondary)
        async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._goto(interaction, 1)

        @discord.ui.button(label="◀", style=discord.ButtonStyle.primary)
        async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._goto(interaction, self.page - 1)

        @discord.ui.button(label="▶", style=discord.ButtonStyle.primary)
        async def nxt(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._goto(interaction, self.page + 1)

        @discord.ui.button(label="▶▶", style=discord.ButtonStyle.secondary)
        async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._goto(interaction, self.total)

        @discord.ui.button(label="ALL", style=discord.ButtonStyle.success)
        async def all_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user.id:
                return await interaction.response.send_message("❌ Nút này của người gọi menu.", ephemeral=True)
            self.mode = "all"
            await interaction.response.defer()
            try:
                _, _, total = await self.cog.render_menu_gui(self.user, page=1, mode="all")
            except Exception:
                total = self.total
            self.total = total
            await self._goto(interaction, 1)


async def setup(bot: commands.Bot):
    await bot.add_cog(UserMenu(bot))
