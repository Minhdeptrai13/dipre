# -*- coding: utf-8 -*-
"""fast_image.py - Tang toc render anh user_discord (font + bg + thumb cache)."""

from __future__ import annotations

import io
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Tuple

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from apps.shared.paths import SHARED_BACKGROUNDS_DIR, SHARED_FONTS_DIR
except ImportError:
    SHARED_BACKGROUNDS_DIR = None
    SHARED_FONTS_DIR = None

RENDER_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="fastimg")

_FONT_CACHE: Dict[Tuple[str, int], object] = {}
_BG_CACHE: Dict[Tuple[int, int, float, int], tuple] = {}
_BG_CACHE_TTL = 120.0
_THUMB_BYTES: Dict[str, tuple] = {}
_THUMB_TTL = 600.0

FONT_FILES = {"b": "BeVietnamPro-Bold.ttf", "r": "BeVietnamPro-Regular.ttf",
              "sym": "Symbola.ttf", "modak": "DFVN-Modak.ttf"}


def get_font(kind: str = "r", px: int = 24):
    """Lay font theo cache (kind, px)."""
    key = (str(kind), int(px))
    hit = _FONT_CACHE.get(key)
    if hit is not None:
        return hit
    f = None
    try:
        if SHARED_FONTS_DIR is not None:
            p = SHARED_FONTS_DIR / FONT_FILES.get(kind, FONT_FILES["r"])
            if p.exists():
                f = ImageFont.truetype(str(p), int(px))
    except Exception:
        f = None
    if f is None:
        for c in (r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"):
            try:
                if os.path.exists(c):
                    f = ImageFont.truetype(c, int(px))
                    break
            except Exception:
                continue
    if f is None:
        try:
            f = ImageFont.load_default()
        except Exception:
            f = None
    _FONT_CACHE[key] = f
    return f


def _pick_bg_file():
    exts = (".png", ".jpg", ".jpeg", ".jpe", ".webp")
    try:
        if SHARED_BACKGROUNDS_DIR is None:
            return None
        files = [f for f in os.listdir(SHARED_BACKGROUNDS_DIR) if f.lower().endswith(exts)]
    except Exception:
        files = []
    return (SHARED_BACKGROUNDS_DIR / random.choice(files)) if files else None


def fast_background(w: int, h: int, blur: float = 0.0, dim: int = 10):
    """Nen cache theo (w,h): lan sau an cache <2ms."""
    if not HAS_PIL:
        return None
    key = (int(w), int(h), float(blur), int(dim))
    now = time.monotonic()
    hit = _BG_CACHE.get(key)
    if hit is not None:
        img, ts = hit
        if now - ts < _BG_CACHE_TTL:
            try:
                return img.copy()
            except Exception:
                return img
    base = None
    path = _pick_bg_file()
    if path is not None:
        try:
            with Image.open(path) as raw:
                if getattr(raw, "is_animated", False):
                    raw.seek(0)
                img = raw.convert("RGBA")
            base = ImageOps.fit(img, (int(w), int(h)), Image.Resampling.BILINEAR)
            if blur and blur > 0:
                sw, sh = max(int(w) // 4, 64), max(int(h) // 4, 64)
                small = base.resize((sw, sh), Image.Resampling.BILINEAR)
                small = small.filter(ImageFilter.GaussianBlur(float(blur)))
                base = small.resize((int(w), int(h)), Image.Resampling.BILINEAR)
        except Exception:
            base = None
    if base is None:
        base = Image.new("RGBA", (int(w), int(h)), (16, 18, 28, 255))
    if dim:
        try:
            base = base.copy()
            base.alpha_composite(Image.new("RGBA", (int(w), int(h)), (10, 14, 26, int(dim))))
        except Exception:
            pass
    _BG_CACHE[key] = (base, now)
    try:
        return base.copy()
    except Exception:
        return base


_AURORA_CACHE: Dict[Tuple[int, int, int], tuple] = {}
_CAUSTIC_CACHE: Dict[Tuple[int, int, int], tuple] = {}
_CAUSTIC_TTL = 1800.0


def fast_aurora(w: int, h: int, dim: int = 48) -> Optional["Image.Image"]:
    """Nen aurora mesh dam, sac (xanh/tim/hong) — cache theo (w,h,dim).
    Khong dua vao anh ngau nhien -> dashboard luon cung mot phong cach."""
    if not HAS_PIL:
        return None
    key = (int(w), int(h), int(dim))
    now = time.monotonic()
    hit = _AURORA_CACHE.get(key)
    if hit is not None:
        img, ts = hit
        if now - ts < _BG_CACHE_TTL:
            try:
                return img.copy()
            except Exception:
                return img
    try:
        sw, sh = max(int(w) // 6, 80), max(int(h) // 6, 80)
        base = Image.new("RGBA", (sw, sh), (58, 68, 172, 255))
        d = ImageDraw.Draw(base, "RGBA")
        # (fx, fy, fr, mau) — bo mau tuoi/sang hon: cyan/periwinkle/hong tim + core glow
        blobs = [
            (0.06, 0.10, 0.55, (92, 206, 255, 255)),
            (0.50, 0.00, 0.50, (150, 140, 255, 255)),
            (0.92, 0.22, 0.60, (236, 120, 238, 255)),
            (0.30, 0.45, 0.65, (110, 128, 252, 255)),
            (0.75, 0.70, 0.60, (164, 104, 246, 255)),
            (0.10, 0.88, 0.55, (78, 160, 255, 255)),
            (0.95, 0.95, 0.45, (124, 100, 240, 255)),
            (0.48, 0.30, 0.34, (240, 246, 255, 120)),  # glow trung tam
            (0.22, 0.64, 0.26, (255, 255, 255, 55)),   # diem sang phu
            (0.80, 0.36, 0.24, (255, 255, 255, 50)),
        ]
        for fx, fy, fr, col in blobs:
            cx, cy = fx * sw, fy * sh
            r = fr * max(sw, sh)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
        base = base.filter(ImageFilter.GaussianBlur(max(sw, sh) * 0.16))
        up = base.resize((int(w), int(h)), Image.Resampling.BICUBIC).filter(
            ImageFilter.GaussianBlur(1.6))
        if dim:
            up.alpha_composite(Image.new("RGBA", (int(w), int(h)), (10, 12, 30, int(dim))))
        _AURORA_CACHE[key] = (up, now)
        try:
            return up.copy()
        except Exception:
            return up
    except Exception:
        return None


def fast_caustics(w: int, h: int, seed: int = 0) -> Optional["Image.Image"]:
    """Texture CAUSTIC mat nuoc — luoi sang giao diem song gian tiep + nhiu ngau nhien
    (anh sang di qua mat nuoc bi nhiu). Tra ve anh "L" (0..255), cache theo (w,h,seed).
    Sinh o do phan giai giam roi bicubic len -> nhanh, mau mo mem."""
    if not HAS_PIL or w < 8 or h < 8:
        return None
    key = (int(w), int(h), int(seed))
    now = time.monotonic()
    hit = _CAUSTIC_CACHE.get(key)
    if hit is not None:
        img, ts = hit
        if now - ts < _CAUSTIC_TTL:
            try:
                return img.copy()
            except Exception:
                return img
    try:
        import math as _math
        # Do phan giai giam: toi da ~45k pixel/moi texture
        d = max(1, int((int(w) * int(h) / 45000.0) ** 0.5))
        gw, gh = max(8, int(w) // d), max(8, int(h) // d)
        rnd = random.Random(0xA5C3 ^ (int(seed) & 0xFFFF) ^ (gw * 7919 + gh * 104729))
        # 4 song hinh sin giao diem — cat 0 tao thanh sang (net caustic)
        f1 = 0.11 + rnd.random() * 0.13
        f2 = 0.11 + rnd.random() * 0.13
        f3 = 0.07 + rnd.random() * 0.10
        f4 = 0.07 + rnd.random() * 0.10
        p1 = rnd.random() * 6.283
        p2 = rnd.random() * 6.283
        p3 = rnd.random() * 6.283
        p4 = rnd.random() * 6.283
        # Nhiu CUNG MICH (sin tien thap) de uon cong net nuoc ngau nhien manh
        fn1 = 0.06 + rnd.random() * 0.10
        fn2 = 0.06 + rnd.random() * 0.10
        pn1 = rnd.random() * 6.283
        pn2 = rnd.random() * 6.283
        wn_amp = 1.3 + rnd.random() * 0.9
        # Mat do mang theo mang: song rat thap tan -> luoi sang mat/den theo vung
        fp = 0.045 + rnd.random() * 0.05
        fq = 0.045 + rnd.random() * 0.05
        pp = rnd.random() * 6.283
        pq = rnd.random() * 6.283
        sx = [_math.sin(x * f1 + p1) for x in range(gw)]
        sy = [_math.sin(y * f2 + p2) for y in range(gh)]
        wx = [_math.sin(x * fn1 + pn1) for x in range(gw)]
        wy = [_math.sin(y * fn2 + pn2) for y in range(gh)]
        px_ = [_math.sin(x * fp + pp) for x in range(gw)]
        py_ = [_math.sin(y * fq + pq) for y in range(gh)]
        # bang sin tinh truoc cho (x+y) va (x-y) -> moi pixel chi con 1 phep cong
        ssum = [_math.sin(k * f3 + p3) for k in range(-(gh - 1), gw + gh)]
        sdiff = [_math.sin(k * f4 + p4) for k in range(-(gh - 1), gw)]
        k0 = gh - 1
        data = bytearray(gw * gh)
        for gy in range(gh):
            syv = sy[gy]
            wyv = wy[gy]
            pyv = py_[gy]
            row = gy * gw
            for gx in range(gw):
                v = (sx[gx] + syv
                     + 0.95 * ssum[gx + gy + k0]
                     + 0.80 * sdiff[gx - gy + k0]
                     + wn_amp * wx[gx] * wyv)          # uon cong manh
                a = abs(v) * 0.30                       # /3.3 -> [0,1]
                if a >= 1.0:
                    continue
                q = 1.0 - a
                q2 = q * q                              # lur 8 -> day/soi RAT mong
                fil = q2 * q2 * q2 * q
                # Mat do theo mang: (px_+py_)/4 -> [-0.5,0.5] + 0.5 -> [0,1]
                patch = (px_[gx] + pyv) * 0.25 + 0.5
                patch = patch * patch * (3 - 2 * patch)  # smoothstep
                patch = 0.15 + 0.85 * patch              # khong de mat het
                data[row + gx] = min(255, int(255 * fil * patch))
        img = Image.frombytes("L", (gw, gh), bytes(data))
        if d > 1:
            img = img.resize((int(w), int(h)), Image.Resampling.BICUBIC)
        img = img.filter(ImageFilter.GaussianBlur(max(0.8, d * 0.6)))
        # Nang cap do sang cua luoi (net caustic ro hon sau khi blur)
        img = img.point(lambda v: min(255, int(v * 1.6)))
        _CAUSTIC_CACHE[key] = (img, now)
        try:
            return img.copy()
        except Exception:
            return img
    except Exception:
        return None


def fetch_thumb_fast(url: str, size=(120, 120), timeout: float = 2.5):
    """Tai thumb voi cache bytes + resize som."""
    if not HAS_PIL or not url or not str(url).startswith("http"):
        return None
    now = time.monotonic()
    hit = _THUMB_BYTES.get(url)
    raw = None
    if hit is not None:
        data, ts = hit
        if now - ts < _THUMB_TTL:
            raw = data
    if raw is None:
        try:
            import requests
            r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and r.content and len(r.content) > 100:
                raw = r.content[:2000000]
                if len(_THUMB_BYTES) > 200:
                    _THUMB_BYTES.pop(next(iter(_THUMB_BYTES)))
                _THUMB_BYTES[url] = (raw, now)
        except Exception:
            return None
    if not raw:
        return None
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if getattr(im, "is_animated", False):
                im.seek(0)
            img = im.convert("RGB")
        try:
            img.thumbnail((int(size[0]) * 2, int(size[1]) * 2), Image.Resampling.BILINEAR)
        except Exception:
            pass
        return img
    except Exception:
        return None


def clear_caches():
    _FONT_CACHE.clear()
    _BG_CACHE.clear()
    _THUMB_BYTES.clear()
