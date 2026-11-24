# -*- coding: utf-8 -*-
"""
glass.py - Bộ công cụ vẽ LIQUID GLASS dùng chung (menu + mọi ảnh hướng dẫn).

  • Nền: ảnh random trong backgrounds/. Nếu ảnh DỌC mà canvas NGANG (hoặc
    ngược lại) -> tự XOAY 90° cho khớp hướng, tránh bị crop mất gần hết ảnh.
  • Kính lỏng: cắt vùng nền phía sau -> phóng nhẹ (khúc xạ) -> blur sâu ->
    tăng độ rực -> tint -> vệt sáng specular -> rim light -> bóng mềm.
  • Vẽ theo "đơn vị layout", nhân `scale` (mặc định 4x) khi vẽ rồi LANCZOS
    về `out` (mặc định 2x) -> bo góc / chữ mịn, không lộ pixel.
  • LƯU Ý Pillow: vẽ fill có alpha thẳng lên canvas RGBA sẽ GHI ĐÈ alpha chứ
    không pha màu -> mọi khối/chữ bán trong suốt đều vẽ qua layer cục bộ.
"""
from __future__ import annotations

import io
import math
import os
import random
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

import aiohttp
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageStat

from apps.shared.paths import SHARED_BACKGROUNDS_DIR, SHARED_FONTS_DIR

FONT_FILES = {
    "b": "BeVietnamPro-Bold.ttf",
    "r": "BeVietnamPro-Regular.ttf",
    "sym": "Symbola.ttf",
    "modak": "DFVN-Modak.ttf",
}

C_TEXT = (255, 255, 255)
C_MUTED = (230, 238, 250)
C_DIM = (180, 195, 215)
C_GOLD = (253, 224, 71)
SHADOW_TXT = (0, 0, 0, 180)

# Bảng gradient dùng chung
G_BRAND = ((99, 102, 241), (236, 72, 153))
G_RED = ((239, 68, 68), (249, 115, 22))
G_GREEN = ((16, 185, 129), (6, 182, 212))
G_PURPLE = ((139, 92, 246), (236, 72, 153))
G_BLUE = ((59, 130, 246), (6, 182, 212))
G_AMBER = ((245, 158, 11), (239, 68, 68))
G_SLATE = ((100, 116, 139), (71, 85, 105))
G_ON = ((34, 197, 94), (16, 185, 129))
G_OFF = ((239, 68, 68), (190, 18, 60))


# ── font / ký tự ────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _sym_cmap():
    p = SHARED_FONTS_DIR / FONT_FILES["sym"]
    if not p.exists():
        return set()
    try:
        from fontTools.ttLib import TTFont
        return set(TTFont(str(p)).getBestCmap().keys())
    except Exception:
        return None  # không đọc được cmap -> coi như có đủ glyph


_FONT_CACHE: Dict[Tuple[str, int], Any] = {}


def get_font(kind: str, px: int):
    try:
        try:
            from apps.user_discord.utils.fast_image import get_font as _fast_font
        except ImportError:
            from utils.fast_image import get_font as _fast_font  # type: ignore
        hit = _FONT_CACHE.get((kind, px))
        if hit is None:
            hit = _fast_font(kind, px)
            _FONT_CACHE[(kind, px)] = hit
        return hit
    except Exception:
        pass
    key = (kind, px)
    f = _FONT_CACHE.get(key)
    if f is None:
        try:
            f = ImageFont.truetype(str(SHARED_FONTS_DIR / FONT_FILES.get(kind, FONT_FILES["r"])), px)
        except Exception:
            try:
                f = ImageFont.truetype("DejaVuSans.ttf", px)
            except Exception:
                f = ImageFont.load_default()
        _FONT_CACHE[key] = f
    return f


def clean_text(text: Any) -> str:
    """Bỏ emoji / ký tự font chữ không có glyph (tránh ô vuông)."""
    out = []
    for ch in str(text or ""):
        o = ord(ch)
        if o > 0xFFFF or ch in "\ufe0f\u200d" or 0x2600 <= o <= 0x27BF or 0x2B00 <= o <= 0x2BFF:
            continue
        out.append(ch)
    return "".join(out).strip()


def icon_char(sym: str, fallback: str) -> Tuple[str, bool]:
    """(ký tự, có_phải_symbol). Symbola thiếu glyph -> chữ cái đầu của fallback."""
    clean = "".join(ch for ch in (sym or "") if ch not in "\ufe0f\u200d")
    if clean:
        ch = clean[0]
        cmap = _sym_cmap()
        if cmap is None or ord(ch) in cmap:
            return ch, True
    letter = next((c for c in (fallback or "") if c.isalnum()), "•")
    return letter.upper(), False


# ── gradient / mask ─────────────────────────────────────────────────────────
def vgrad_L(w: int, h: int, top: int, bottom: int) -> Image.Image:
    g = Image.linear_gradient("L").resize((max(1, w), max(1, h)), Image.Resampling.BILINEAR)
    return g.point(lambda v: int(top + (bottom - top) * v / 255))


def hgrad_rgb(w: int, h: int, c1, c2) -> Image.Image:
    g = Image.linear_gradient("L").rotate(90, expand=True).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    g = g.resize((max(1, w), max(1, h)), Image.Resampling.BILINEAR)
    a = Image.new("RGB", g.size, tuple(c1[:3]))
    b = Image.new("RGB", g.size, tuple(c2[:3]))
    return Image.composite(b, a, g).convert("RGBA")


_RMASK_CACHE: Dict[Tuple[int, int, int, int], Image.Image] = {}


def rmask(w: int, h: int, radius: int, fill: int = 255) -> Image.Image:
    """Tạo mask bo góc khử răng cưa siêu mượt kèm cache tốc độ cao."""
    w, h, radius, fill = int(w), int(h), int(radius), int(fill)
    key = (w, h, radius, fill)
    hit = _RMASK_CACHE.get(key)
    if hit is not None:
        return hit
    S = 2
    sw, sh = max(1, w * S), max(1, h * S)
    sr = max(1, radius * S)
    m = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, sw - 1, sh - 1], radius=sr, fill=fill)
    res = m.resize((max(1, w), max(1, h)), Image.Resampling.BILINEAR)
    if len(_RMASK_CACHE) < 250:
        _RMASK_CACHE[key] = res
    return res


# ── nền ─────────────────────────────────────────────────────────────────────
def orient_to_canvas(img: Image.Image, W: int, H: int) -> Image.Image:
    """Ảnh dọc + canvas ngang (hoặc ngược lại) -> xoay 90° cho cùng hướng."""
    iw, ih = img.size
    if iw <= 0 or ih <= 0 or W <= 0 or H <= 0:
        return img
    can_land, can_port = W / H >= 1.08, H / W >= 1.08
    img_land, img_port = iw / ih >= 1.08, ih / iw >= 1.08
    if (can_land and img_port) or (can_port and img_land):
        return img.transpose(Image.Transpose.ROTATE_90)
    return img


def _pick_bg_file():
    exts = (".png", ".jpg", ".jpeg", ".jpe", ".webp", ".gif")
    try:
        files = [f for f in os.listdir(SHARED_BACKGROUNDS_DIR) if f.lower().endswith(exts)]
    except Exception:
        files = []
    return (SHARED_BACKGROUNDS_DIR / random.choice(files)) if files else None


def _mesh_background(W: int, H: int) -> Image.Image:
    small = Image.new("RGBA", (160, max(40, int(160 * H / max(1, W)))), (14, 16, 30, 255))
    sw, sh = small.size
    layer = Image.new("RGBA", small.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(8):
        cx, cy = random.randint(0, sw), random.randint(0, sh)
        r = random.randint(25, 55)
        col = random.choice([(99, 102, 241), (236, 72, 153), (16, 185, 129),
                             (249, 115, 22), (6, 182, 212), (168, 85, 247)])
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (170,))
    small.alpha_composite(layer)
    small = small.filter(ImageFilter.GaussianBlur(14))
    return small.resize((W, H), Image.Resampling.BICUBIC)


def load_background(W: int, H: int, dim: int = 15, blur: float = 0.8) -> Image.Image:
    """Nền RGBA kích thước pixel (W, H): ảnh random (tự xoay theo hướng) + rực rỡ chuẩn Apple Liquid Glass."""
    base = None
    path = _pick_bg_file()
    if path is not None:
        try:
            with Image.open(path) as raw:
                if getattr(raw, "is_animated", False):
                    raw.seek(0)
                img = raw.convert("RGBA")
            img = orient_to_canvas(img, W, H)
            mid = ImageOps.fit(img, (max(W // 4, 64), max(H // 4, 64)), Image.Resampling.LANCZOS)
            if blur:
                mid = mid.filter(ImageFilter.GaussianBlur(blur))
            base = mid.resize((W, H), Image.Resampling.BICUBIC)
        except Exception:
            base = None
    if base is None:
        base = _mesh_background(W, H)
    if dim:
        # Lớp phủ cực mỏng để nền sáng bừng rực rỡ như wallpaper Apple
        base.alpha_composite(Image.new("RGBA", (W, H), (10, 14, 26, dim)))
    return base


async def fetch_image(url: Optional[str], timeout: float = 4.0,
                      session: Optional[aiohttp.ClientSession] = None) -> Optional[Image.Image]:
    """Tải ảnh (avatar/icon) -> RGBA, lỗi -> None."""
    if not url:
        return None
    try:
        async def _get(s):
            async with s.get(str(url), timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                if r.status != 200:
                    return None
                return await r.read()
        if session is not None:
            raw = await _get(session)
        else:
            async with aiohttp.ClientSession() as s:
                raw = await _get(s)
        if not raw:
            return None
        with Image.open(io.BytesIO(raw)) as im:
            if getattr(im, "is_animated", False):
                im.seek(0)
            return im.convert("RGBA")
    except Exception:
        return None


def avatar_url(user, size: int = 256) -> Optional[str]:
    try:
        return str(user.display_avatar.replace(size=size, format="png").url)
    except Exception:
        try:
            return str(user.display_avatar.url)
        except Exception:
            return None


# ── CANVAS ──────────────────────────────────────────────────────────────────
class GlassCanvas:
    """Canvas Liquid Glass: mọi toạ độ truyền vào là ĐƠN VỊ LAYOUT."""

    def __init__(self, lw: float, lh: float, scale: int = 2, out: float = 1.25,
                 dim: int = 95, bg_blur: float = 1.0):
        self.lw, self.lh = float(lw), float(lh)
        self.k = int(scale)
        self.out = float(out)
        self.W, self.H = self.s(lw), self.s(lh)
        self.c = load_background(self.W, self.H, dim=dim, blur=bg_blur)

    # ── tiện ích toạ độ / font ──
    def s(self, v: float) -> int:
        return int(round(v * self.k))

    def box(self, x1, y1, x2, y2) -> List[int]:
        return [self.s(x1), self.s(y1), self.s(x2), self.s(y2)]

    @property
    def d(self) -> ImageDraw.ImageDraw:
        return ImageDraw.Draw(self.c, "RGBA")

    def font(self, kind: str, size: float):
        return get_font(kind, max(1, int(round(size * self.k))))

    def tlen(self, text: str, font) -> float:
        return self.d.textlength(text or "", font=font) / self.k

    def fit(self, text: str, font, max_w: float) -> str:
        text = text or ""
        d = self.d
        mw = max_w * self.k
        if d.textlength(text, font=font) <= mw:
            return text
        while len(text) > 1 and d.textlength(text + "…", font=font) > mw:
            text = text[:-1]
        return text.rstrip() + "…"

    def wrap(self, text: str, font, max_w: float, max_lines: int = 2) -> List[str]:
        words = (text or "").split()
        lines: List[str] = []
        cur = ""
        for w in words:
            t = (cur + " " + w).strip()
            if self.tlen(t, font) <= max_w or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
                if len(lines) == max_lines:
                    break
        if len(lines) < max_lines and cur:
            lines.append(cur)
        rest = " ".join(words[len(" ".join(lines).split()):])
        if rest and lines:
            lines[-1] = self.fit(lines[-1] + " " + rest, font, max_w)
        return [self.fit(l, font, max_w) for l in lines[:max_lines]]

    def _comp(self, layer: Image.Image, x: int, y: int):
        sx, sy = max(0, -x), max(0, -y)
        if sx >= layer.width or sy >= layer.height:
            return
        self.c.alpha_composite(layer, (max(0, x), max(0, y)), (sx, sy))

    # ── chữ ──
    def text(self, x: float, y: float, text: str, font, fill=C_TEXT, *,
             shadow: bool = True, align: str = "l", vcenter: bool = False) -> float:
        """Vẽ chữ (bóng mềm). align l/c/r theo x; vcenter: y là tâm dọc. Trả về bề rộng layout."""
        if not text:
            return 0.0
        d = self.d
        tl = d.textlength(text, font=font)
        bb = d.textbbox((0, 0), text, font=font)
        px, py = self.s(x), self.s(y)
        if align == "c":
            px -= int(tl / 2)
        elif align == "r":
            px -= int(tl)
        if vcenter:
            py -= (bb[1] + bb[3]) // 2
        if shadow:
            m = self.k * 3
            layer = Image.new("RGBA", (bb[2] + m * 2, bb[3] + m * 2), (0, 0, 0, 0))
            ImageDraw.Draw(layer).text((m, m), text, font=font, fill=SHADOW_TXT)
            layer = layer.filter(ImageFilter.GaussianBlur(self.k * 0.8))
            self._comp(layer, px - m, py - m + max(1, self.k // 2))
        if len(fill) == 4 and fill[3] < 255:
            layer = Image.new("RGBA", (bb[2] + 4, bb[3] + 4), (0, 0, 0, 0))
            ImageDraw.Draw(layer).text((0, 0), text, font=font, fill=fill)
            self._comp(layer, px, py)
        else:
            self.d.text((px, py), text, font=font, fill=tuple(fill[:3]))
        return tl / self.k

    def rich(self, x: float, y: float, parts: Sequence[Tuple[str, Any, Any]], *,
             align: str = "l", vcenter: bool = False, shadow: bool = True) -> float:
        """Một dòng nhiều kiểu chữ: parts = [(text, font, color), ...]."""
        total = sum(self.tlen(t, f) for t, f, _ in parts)
        if align == "c":
            x -= total / 2
        elif align == "r":
            x -= total
        if vcenter:
            # căn theo font lớn nhất để các mảnh thẳng hàng baseline
            f0 = max((f for _, f, _ in parts), key=lambda f: getattr(f, "size", 0))
            asc, desc = f0.getmetrics()
            y -= (asc + desc) / 2 / self.k
        for t, f, col in parts:
            if vcenter:
                fa, fd = f.getmetrics()
                f0a, _ = f0.getmetrics()
                yy = y + (f0a - fa) / self.k
            else:
                yy = y
            x += self.text(x, yy, t, f, col, shadow=shadow)
        return total

    # ── khối ──
    def rrect(self, box, r: float, fill=None, outline=None, width: float = 0):
        x1, y1, x2, y2 = self.box(*box)
        layer = Image.new("RGBA", (max(1, x2 - x1), max(1, y2 - y1)), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle(
            [0, 0, x2 - x1 - 1, y2 - y1 - 1], radius=self.s(r), fill=fill, outline=outline,
            width=max(1, self.s(width)) if outline else 0)
        self._comp(layer, x1, y1)

    def ellipse(self, box, fill=None, outline=None, width: float = 0):
        x1, y1, x2, y2 = self.box(*box)
        layer = Image.new("RGBA", (max(1, x2 - x1), max(1, y2 - y1)), (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse([0, 0, x2 - x1 - 1, y2 - y1 - 1], fill=fill, outline=outline,
                                      width=max(1, self.s(width)) if outline else 0)
        self._comp(layer, x1, y1)

    def grad(self, box, r: float, c1, c2, alpha: int = 255):
        x1, y1, x2, y2 = self.box(*box)
        w, h = x2 - x1, y2 - y1
        if w < 1 or h < 1:
            return
        self.c.paste(hgrad_rgb(w, h, c1, c2), (x1, y1), rmask(w, h, self.s(r), alpha))

    def shadow(self, box, r: float, blur: float = 18, offset: float = 7, opacity: int = 95):
        x1, y1, x2, y2 = self.box(*box)
        b, off = self.s(blur), self.s(offset)
        pad = b * 2
        w, h = x2 - x1 + pad * 2, y2 - y1 + pad * 2
        small_k = 4  # blur ở độ phân giải thấp cho nhanh
        layer = Image.new("RGBA", (max(1, w // small_k), max(1, h // small_k)), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle(
            [pad // small_k, (pad + off) // small_k, (pad + x2 - x1) // small_k, (pad + off + y2 - y1) // small_k],
            radius=max(1, self.s(r) // small_k), fill=(0, 0, 0, opacity))
        layer = layer.filter(ImageFilter.GaussianBlur(max(0.5, b / 2 / small_k)))
        layer = layer.resize((w, h), Image.Resampling.BICUBIC)
        self._comp(layer, x1 - pad, y1 - pad)

    def glass(self, box, r: float, *, blur: float = 24, tint=None, tint_grad=None,
              magnify: float = 1.05, saturate: float = 1.45, brighten: Optional[float] = None,
              highlight: Optional[int] = None, rim: Optional[Tuple[int, int]] = None,
              shadow: bool = True, shadow_opacity: int = 55, caustics: bool = True, **kwargs):
        """Khối kính lỏng Apple Crystal pha lê quang học thích ứng (Adaptive Crystal Liquid Glass).
        - Tự động đo độ sáng vùng nền (Adaptive Luminance): nếu quá sáng thì tạo tương phản tối mờ
          (smoked obsidian), nếu tối thì bừng sáng trắng pha lê (crystal white glow).
        - Tự động nhận diện điểm phát sáng (Dynamic Light Source Detection): tính vector góc tới của ánh sáng,
          uốn lượn chùm phản quang (Caustics Refraction Flow) khi đi xiên qua môi trường nước/kính.
        - Khử răng cưa hoàn hảo (Lanczos supersampling mask), không viền thô nhân tạo.
        """
        x1, y1, x2, y2 = self.box(*box)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(self.W, x2), min(self.H, y2)
        w, h = x2 - x1, y2 - y1
        if w < 4 or h < 4:
            return
        radius = self.s(r)

        # ── 1. ĐO ĐỘ SÁNG TRUNG BÌNH CỦA VÙNG KÍNH (Adaptive Luminance & Contrast) ──
        region = self.c.crop((x1, y1, x2, y2))
        stat = ImageStat.Stat(region.convert("L"))
        avg_lum = stat.mean[0]  # Thang độ sáng 0 -> 255

        # Tự động cân bằng tương phản:
        # Nếu nền quá sáng (>165): dùng tint tối mờ pha lê đen để chữ/nội dung rõ nét
        # Nếu nền tối (<95): dùng tint trắng pha lê siêu sáng
        # Ở khoảng giữa: nội suy mượt mà
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
            # Bóng đổ ambient phân tán rộng mềm mại chuẩn VisionOS/Apple WWDC25
            self.shadow(box, r, blur=28, offset=8, opacity=shadow_opacity)

        # ── 2. KHÚC XẠ NỀN & FROSTED ──
        if magnify > 1.0:
            mw, mh = max(2, int(w / magnify)), max(2, int(h / magnify))
            ox, oy = (w - mw) // 2, (h - mh) // 2
            region = region.crop((ox, oy, ox + mw, oy + mh))
        k = 4
        small = region.resize((max(2, w // k), max(2, h // k)), Image.Resampling.BILINEAR)
        small = small.filter(ImageFilter.GaussianBlur(max(0.8, self.s(blur) / k / 2)))
        frosted = small.resize((w, h), Image.Resampling.BICUBIC).convert("RGBA")
        if saturate != 1.0:
            frosted = ImageEnhance.Color(frosted.convert("RGB")).enhance(saturate).convert("RGBA")
        if brighten_factor != 1.0:
            frosted = ImageEnhance.Brightness(frosted.convert("RGB")).enhance(brighten_factor).convert("RGBA")
        
        # Áp dụng tint thích ứng
        if tint_grad:
            c1, c2, a = tint_grad
            tl = hgrad_rgb(w, h, c1, c2)
            tl.putalpha(a)
            frosted.alpha_composite(tl)
        elif tint:
            frosted.alpha_composite(Image.new("RGBA", (w, h), tuple(tint)))

        # ── 3. NHẬN DIỆN NGUỒN SÁNG (Dynamic Light Source & Water-like Refraction) ──
        card_center_x = (x1 + x2) / 2.0
        card_center_y = (y1 + y2) / 2.0
        if not hasattr(self, "_light_source"):
            try:
                bg_small = self.c.convert("L").resize((32, 32), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(2))
                pixels = list(bg_small.getdata())
                max_idx = max(range(len(pixels)), key=lambda i: pixels[i])
                mx = max_idx % 32
                my = max_idx // 32
                self._light_source = (mx / 32.0 * self.W, my / 32.0 * self.H)
            except Exception:
                self._light_source = (self.W * 0.5, self.H * 0.2)

        ls_x, ls_y = self._light_source
        dx = card_center_x - ls_x
        dy = card_center_y - ls_y
        dist = math.hypot(dx, dy) or 1.0
        vx, vy = dx / dist, dy / dist

        # Độ dốc tia sáng xiên qua mặt kính/nước (Snell's Law refraction offset)
        slant_x = vx * (h * 0.75)

        # ── 4. PHẢN QUANG DẠNG LƯỢN NƯỚC / LĂNG KÍNH (Caustics Refraction Flow) ──
        if caustics and w > 40 and h > 20:
            diag = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            d_diag = ImageDraw.Draw(diag)
            # Chùm tia chính uốn lượn xiên theo hướng nguồn sáng
            p1 = max(0, min(w, int(w * 0.32 + vx * w * 0.15)))
            p2 = max(0, min(w, p1 + int(w * 0.22)))
            q1 = max(0, min(w, int(p1 + slant_x)))
            q2 = max(0, min(w, int(p2 + slant_x)))

            d_diag.polygon([(p1, 0), (p2, 0), (q2, h), (q1, h)], fill=caustic_fill + (caustic_alpha,))

            # Dải quang phổ tán sắc lăng kính mờ ảo (chromatic dispersion)
            d_diag.polygon([(max(0, p1 - int(w * 0.04)), 0), (p1, 0), (q1, h), (max(0, q1 - int(w * 0.04)), h)],
                           fill=(210, 240, 255, int(caustic_alpha * 0.6)))
            
            # Chùm tia phụ thứ hai
            p3 = max(0, min(w, int(w * 0.70 + vx * w * 0.1)))
            p4 = max(0, min(w, p3 + int(w * 0.12)))
            q3 = max(0, min(w, int(p3 + slant_x)))
            q4 = max(0, min(w, int(p4 + slant_x)))
            d_diag.polygon([(p3, 0), (p4, 0), (q4, h), (q3, h)], fill=(255, 255, 255, int(caustic_alpha * 0.7)))

            blur_rad = max(2.5, h * 0.32)
            diag = diag.filter(ImageFilter.GaussianBlur(blur_rad))
            frosted.alpha_composite(diag)

        # ── 5. SPECULAR PHẢN XẠ MẶT KÍNH & HỘI TỤ ĐÁY KÍNH ──
        if highlight_val:
            hl = Image.new("RGBA", (w, h), (255, 255, 255, 0))
            g_raw = Image.linear_gradient("L").resize((max(1, w), max(1, h)), Image.Resampling.BILINEAR)
            if vy >= 0:
                a_curve = g_raw.point(lambda v: int(highlight_val * ((255 - v) / 255.0) ** 2.0))
            else:
                a_curve = g_raw.point(lambda v: int(highlight_val * (v / 255.0) ** 2.0))
            hl.putalpha(a_curve)
            frosted.alpha_composite(hl)

            # Khúc xạ ánh sáng hội tụ đáy kính (bottom caustic concentration)
            bot_glow = g_raw.point(lambda v: int((highlight_val * 0.5) * (v / 255.0) ** 2.8))
            b_layer = Image.new("RGBA", (w, h), (255, 255, 255, 0))
            b_layer.putalpha(bot_glow)
            frosted.alpha_composite(b_layer)

        # ── 6. VIỀN PHẢN XẠ KÍNH (chỉ khi truyền rim rõ ràng) ──
        if rim:
            rw = max(1, self.s(0.5))
            ring = Image.new("L", (w, h), 0)
            ImageDraw.Draw(ring).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, outline=255, width=rw)
            ring = ImageChops.multiply(ring, vgrad_L(w, h, rim[0], rim[1]))
            rl = Image.new("RGBA", (w, h), (255, 255, 255, 0))
            rl.putalpha(ring)
            frosted.alpha_composite(rl)

        self.c.paste(frosted, (x1, y1), rmask(w, h, radius))

    # ── component ──
    def dots(self, x: float, y: float):
        """3 chấm macOS, y = tâm dọc."""
        for i, col in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
            cx = x + 6 + i * 18
            self.ellipse((cx - 6, y - 6, cx + 6, y + 6), fill=col + (255,))

    def pill(self, x: float, y: float, text: str, font, grad=G_BRAND, *, h: float = 20,
             padx: float = 10, align: str = "l", text_color=(255, 255, 255)) -> Tuple[float, float]:
        """Viên thuốc gradient đặc, y = mép trên. Trả về (x1, x2)."""
        w = self.tlen(text, font) + padx * 2
        x1 = x if align == "l" else (x - w if align == "r" else x - w / 2)
        bx = (x1, y, x1 + w, y + h)
        self.grad(bx, h / 2, grad[0], grad[1])
        self.rrect(bx, h / 2, outline=(255, 255, 255, 90), width=1)
        self.text(x1 + w / 2, y + h / 2, text, font, text_color, shadow=False, align="c", vcenter=True)
        return x1, x1 + w

    def glass_pill(self, x: float, y: float, text: str, font, grad=G_GREEN, *, h: float = 30,
                   padx: float = 14, align: str = "l", dot=None, tint_alpha: int = 95) -> Tuple[float, float]:
        """Viên thuốc kính nhuộm màu (+ chấm phát sáng tuỳ chọn)."""
        dot_w = 18 if dot else 0
        w = self.tlen(text, font) + padx * 2 + dot_w
        x1 = x if align == "l" else (x - w if align == "r" else x - w / 2)
        self.glass((x1, y, x1 + w, y + h), h / 2, blur=10, tint_grad=(grad[0], grad[1], tint_alpha),
                   magnify=1.0, shadow=False, highlight=42, rim=(190, 50))
        if dot:
            cx, cy = x1 + padx + 4, y + h / 2
            glow = Image.new("RGBA", (self.s(24), self.s(24)), (0, 0, 0, 0))
            ImageDraw.Draw(glow).ellipse([self.s(6), self.s(6), self.s(18), self.s(18)], fill=tuple(dot[:3]) + (230,))
            glow = glow.filter(ImageFilter.GaussianBlur(self.s(3)))
            self._comp(glow, self.s(cx - 12), self.s(cy - 12))
            self.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=tuple(dot[:3]) + (255,))
        self.text(x1 + padx + dot_w, y + h / 2, text, font, (255, 255, 255), vcenter=True)
        return x1, x1 + w

    def circle_image(self, img: Optional[Image.Image], x: float, y: float, size: float, *,
                     ring=G_BRAND, ring_w: float = 2.5, letter: str = "?", fill=(51, 65, 85)):
        """Ảnh tròn + vòng gradient. img None -> vòng tròn + chữ cái."""
        if ring:
            rb = (x - ring_w, y - ring_w, x + size + ring_w, y + size + ring_w)
            self.grad(rb, size, ring[0], ring[1])
        px = self.s(size)
        if img is not None:
            try:
                im = ImageOps.fit(img.convert("RGBA"), (px, px), Image.Resampling.LANCZOS)
                mask = Image.new("L", (px, px), 0)
                ImageDraw.Draw(mask).ellipse([0, 0, px - 1, px - 1], fill=255)
                self.c.paste(im, (self.s(x), self.s(y)), mask)
                return
            except Exception:
                pass
        self.ellipse((x, y, x + size, y + size), fill=tuple(fill[:3]) + (255,))
        f = self.font("b", size * 0.42)
        self.text(x + size / 2, y + size / 2, (clean_text(letter) or "?")[:2].upper(), f, C_TEXT,
                  align="c", vcenter=True)

    def chip(self, box, sym: str, fallback: str, color=(148, 163, 184), r: float = 11, size: float = 17):
        """Ô icon kính nhuộm màu + glyph ở giữa."""
        ic = tuple(color[:3])
        dark = tuple(max(0, int(v * 0.5)) for v in ic)
        self.glass(box, r, blur=4, tint_grad=(ic, dark, 125), magnify=1.0, saturate=1.0,
                   highlight=60, rim=(210, 60), shadow=False)
        ch, is_sym = icon_char(sym, fallback)
        f = self.font("sym", size) if is_sym else self.font("b", size * 0.88)
        x1, y1, x2, y2 = box
        self.text((x1 + x2) / 2, (y1 + y2) / 2, ch, f, (255, 255, 255), align="c", vcenter=True)

    def header(self, x1: float, y1: float, x2: float, h: float, title: str, sub: str = "", *,
               tag: Optional[str] = None, tag_grad=G_BRAND, logo: Optional[Image.Image] = None,
               logo_size: float = 42, right_reserve: float = 0, title_font: str = "modak", title_size: float = 23) -> float:
        """Thanh header kính: dots (hoặc logo) + tiêu đề (Modak/Bold) + tag + phụ đề. Trả về x bắt đầu vùng phải trống."""
        self.glass((x1, y1, x2, y1 + h), 22, blur=24)
        cy = y1 + h / 2
        if logo is not None:
            ls = logo_size
            lim = logo.convert("RGBA").resize((self.s(ls), self.s(ls)), Image.Resampling.LANCZOS)
            self._comp(lim, self.s(x1 + 18), self.s(cy - ls / 2))
            tx = x1 + 18 + ls + 14
        else:
            self.dots(x1 + 20, cy - (9 if sub else 0))
            tx = x1 + 20 + 66
        f_title = self.font(title_font, title_size)
        f_sub = self.font("r", 12)
        f_tag = self.font("b", 10.5)
        avail = (x2 - 20 - right_reserve) - tx
        title_y = cy - (13 if sub else 0)
        tag_w = (self.tlen(tag, f_tag) + 34) if tag else 0
        t = self.fit(title, f_title, max(40, avail - tag_w))
        tw = self.text(tx, title_y, t, f_title, C_TEXT, vcenter=True)
        if tag:
            self.pill(tx + tw + 14, title_y - 10, tag, f_tag, tag_grad, h=20, padx=11)
        if sub:
            self.text(tx, cy + 13, self.fit(sub, f_sub, avail), f_sub, C_MUTED, vcenter=True)
        return x2 - 20 - right_reserve

    @staticmethod
    def section_height(n_rows: int, row_h: float = 50, gap: float = 8, head_h: float = 50) -> float:
        n = max(1, n_rows)
        return head_h + 12 + n * row_h + (n - 1) * gap + 12

    def section(self, x1: float, y1: float, x2: float, title: str, sub: str, grad,
                rows: Sequence[Tuple], *, row_h: float = 50, gap: float = 8, head_h: float = 50,
                y2: Optional[float] = None, count_label: Optional[str] = None) -> float:
        """Khối kính lớn + header kính nhuộm gradient + các dòng lệnh kính nhỏ.

        rows: (cú_pháp, mô_tả[, tag]). Trả về y2."""
        if y2 is None:
            y2 = y1 + self.section_height(len(rows), row_h, gap, head_h)
        c1, c2 = grad
        self.glass((x1, y1, x2, y2), 22, blur=24, tint=(12, 16, 28, 50))
        self.glass((x1 + 8, y1 + 8, x2 - 8, y1 + head_h), 15, blur=8, tint_grad=(c1, c2, 140),
                   magnify=1.0, highlight=70, rim=(210, 60), shadow=True, shadow_opacity=65)
        f_t = self.font("b", 14)
        f_s = self.font("r", 11)
        f_c = self.font("b", 10.5)
        hc = y1 + 8 + (head_h - 8) / 2
        cnt = count_label if count_label is not None else f"{len(rows)} lệnh"
        cw = (self.tlen(cnt, f_c) + 18) if cnt else 0
        tmax = (x2 - 22 - cw - 8) - (x1 + 22)
        if sub:
            self.text(x1 + 22, hc - 8, self.fit(title, f_t, tmax), f_t, (255, 255, 255), vcenter=True)
            self.text(x1 + 22, hc + 9, self.fit(sub, f_s, tmax), f_s, (255, 255, 255, 225), vcenter=True)
        else:
            self.text(x1 + 22, hc, self.fit(title, f_t, tmax), f_t, (255, 255, 255), vcenter=True)
        if cnt:
            bx = (x2 - 20 - cw, hc - 11, x2 - 20, hc + 11)
            self.rrect(bx, 11, fill=(255, 255, 255, 46), outline=(255, 255, 255, 110), width=1)
            self.text(bx[0] + cw / 2, hc, cnt, f_c, (255, 255, 255), shadow=False, align="c", vcenter=True)
        cy = y1 + head_h + 12
        for row in rows:
            self.cmd_row((x1 + 10, cy, x2 - 10, cy + row_h), row[0], row[1] if len(row) > 1 else "",
                         row[2] if len(row) > 2 else None, accent=c1)
            cy += row_h + gap
        return y2

    def cmd_row(self, box, syntax: str, desc: str = "", tag: Optional[str] = None, *,
                accent=(129, 140, 248), tag_grad=None, f_cmd=None, f_desc=None, desc_lines: int = 1):
        """Ô kính 1 lệnh: chấm sáng + cú pháp (đậm) + mô tả + tag tuỳ chọn."""
        x1, y1, x2, y2 = box
        h = y2 - y1
        self.glass(box, min(14, h / 2), blur=4, tint=(255, 255, 255, 20), magnify=1.0, saturate=1.0,
                   highlight=32, rim=(140, 35), shadow=False)
        f_cmd = f_cmd or self.font("b", 13)
        f_desc = f_desc or self.font("r", 11)
        f_tag = self.font("b", 9.5)
        # thanh accent dọc bên trái
        self.grad((x1 + 10, y1 + h * 0.25, x1 + 13.5, y2 - h * 0.25), 2, accent,
                  tuple(min(255, int(v * 0.6 + 100)) for v in accent[:3]))
        tx = x1 + 24
        right = x2 - 12
        if tag:
            tg = tag_grad or (tuple(accent[:3]), tuple(max(0, int(v * 0.55)) for v in accent[:3]))
            tw = self.tlen(tag, f_tag) + 14
            self.pill(right, y1 + (h - 18) / 2 if not desc else y1 + 9, tag, f_tag, tg, h=18, padx=7, align="r")
            name_right = right - tw - 8
        else:
            name_right = right
        if desc:
            if desc_lines > 1:
                lines = self.wrap(desc, f_desc, name_right - tx, desc_lines)
                n = 1 + len(lines)
                lh = 17
                top = y1 + h / 2 - (n * lh) / 2 + lh / 2
                self.text(tx, top, self.fit(syntax, f_cmd, name_right - tx), f_cmd, C_TEXT, vcenter=True)
                for i, ln in enumerate(lines):
                    self.text(tx, top + (i + 1) * lh, ln, f_desc, C_MUTED, vcenter=True)
            else:
                self.text(tx, y1 + h * 0.34, self.fit(syntax, f_cmd, name_right - tx), f_cmd, C_TEXT, vcenter=True)
                self.text(tx, y1 + h * 0.70, self.fit(desc, f_desc, right - tx), f_desc, C_MUTED, vcenter=True)
        else:
            self.text(tx, y1 + h / 2, self.fit(syntax, f_cmd, name_right - tx), f_cmd, C_TEXT, vcenter=True)

    def bar(self, x1: float, y1: float, x2: float, y2: float, r: float = 20):
        """Thanh kính trơn (footer / ghi chú)."""
        self.glass((x1, y1, x2, y2), r, blur=24)

    # ── xuất ảnh (Tối ưu siêu tốc JPEG 90% giống menu.py) ──
    def finalize(self, format: str = "JPEG", quality: int = 90) -> io.BytesIO:
        out_size = (max(1, int(self.lw * self.out)), max(1, int(self.lh * self.out)))
        final = self.c.resize(out_size, Image.Resampling.BICUBIC).convert("RGB")
        buf = io.BytesIO()
        fmt = str(format).upper()
        if fmt in ("JPG", "JPEG"):
            final.save(buf, format="JPEG", quality=quality, subsampling=0)
        else:
            final.save(buf, format="PNG", compress_level=1)
        buf.seek(0)
        return buf


async def setup(bot):  # main.py nạp mọi utils/*.py như extension
    pass
