# -*- coding: utf-8 -*-
"""
MODULE: ai (DIPRE AI Smart Assistant)
- Hệ thống AI đa bậc DIPRE Flash ⚡ & DIPRE Pro 🧠 (Keyless Gateway Pool).
- Tính cách tự nhiên, hóm hỉnh hoặc hỗ trợ chuyên sâu về hệ sinh thái DIPRE.
- RAG context & Anti-Ban Rate Guard chống spam làm rate-limit tài khoản.
- Hướng dẫn dạng ảnh Help Card + Status dạng ảnh Liquid Glass.
- Tự động xoá tin nhắn bot qua autodelet.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord.ext import commands

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
AI_SETTINGS_FILE = DATA_DIR / "ai_settings.json"

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

KILO_GATEWAY_URL = "https://api.kilo.ai/api/gateway/chat/completions"

# 3 bậc DIPRE AI độc quyền (1 cổng Gateway tốc độ cao + auto-fallback):
AVAILABLE_MODELS: Dict[str, Dict[str, Any]] = {
    "flash": {
        "name": "DIPRE Flash",
        "creator": "DIPRE Fast",
        "brand_color": (31, 202, 173),
        "gateway_display": "DIPRE FLASH",
        "desc": "Phản hồi siêu tốc (~2-5s) cho trò chuyện, tra cứu nhanh & lệnh UserBot.",
        "gateway": "dipre",
        "endpoint": KILO_GATEWAY_URL,
        "candidates": [
            {"model_id": "baidu/ernie-5.5-flash-preview:free", "max_tokens": 1800, "temperature": 0.5, "supports_effort": True, "timeout": 18.0},
            {"model_id": "particle-ai/particle-1:free", "max_tokens": 2048, "temperature": 0.5, "supports_effort": False, "timeout": 20.0},
            {"model_id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "max_tokens": 2200, "temperature": 0.45, "supports_effort": True, "timeout": 22.0},
        ],
        "headers": {"Content-Type": "application/json", "User-Agent": "DIPRE-UserBot/5.0"},
    },
    "standard": {
        "name": "DIPRE Standard",
        "creator": "DIPRE Core",
        "brand_color": (56, 189, 248),
        "gateway_display": "DIPRE CORE",
        "desc": "Cân bằng (Bình thường) — ổn định cao, phản hồi mạch lạc mọi tác vụ (Mặc định).",
        "gateway": "dipre",
        "endpoint": KILO_GATEWAY_URL,
        "candidates": [
            {"model_id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "max_tokens": 2200, "temperature": 0.4, "supports_effort": True, "timeout": 24.0},
            {"model_id": "nvidia/nemotron-3.5-super-vl:free", "max_tokens": 2600, "temperature": 0.4, "supports_effort": True, "timeout": 26.0},
            {"model_id": "baidu/ernie-5.5-flash-preview:free", "max_tokens": 2000, "temperature": 0.45, "supports_effort": True, "timeout": 20.0},
        ],
        "headers": {"Content-Type": "application/json", "User-Agent": "DIPRE-UserBot/5.0"},
    },
    "pro": {
        "name": "DIPRE Pro",
        "creator": "DIPRE Pro",
        "brand_color": (245, 184, 0),
        "gateway_display": "DIPRE PRO",
        "desc": "Chuyên sâu (Flagship) — xử lý code/JSON, RAG dài & bài toán kỹ thuật khó.",
        "gateway": "dipre",
        "endpoint": KILO_GATEWAY_URL,
        "candidates": [
            {"model_id": "nvidia/nemotron-3-ultra-550b-a55b:free", "max_tokens": 2600, "temperature": 0.35, "supports_effort": True, "cap_effort_medium": True, "timeout": 34.0},
            {"model_id": "nvidia/nemotron-3.5-super-vl:free", "max_tokens": 2800, "temperature": 0.35, "supports_effort": True, "timeout": 28.0},
            {"model_id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "max_tokens": 2400, "temperature": 0.35, "supports_effort": True, "timeout": 24.0},
        ],
        "headers": {"Content-Type": "application/json", "User-Agent": "DIPRE-UserBot/5.0"},
    },
}

REASONING_LEVELS: Dict[str, Dict[str, Any]] = {
    "low": {"label": "Thấp (Low)", "effort": "low", "max_tokens": 1600, "bonus_timeout": 0.0},
    "medium": {"label": "Trung bình (Medium)", "effort": "medium", "max_tokens": 2400, "bonus_timeout": 4.0},
    "high": {"label": "Cao (High)", "effort": "high", "max_tokens": 3400, "bonus_timeout": 12.0},
}

DEFAULT_MODEL_KEY = "standard"
DEFAULT_THINK_KEY = "medium"


def _normalize_model_key(key: Optional[str]) -> str:
    k = (key or DEFAULT_MODEL_KEY).strip().lower()
    if k in AVAILABLE_MODELS:
        return k
    if k in ("pro", "ultra", "flagship"):
        return "pro"
    if k in ("standard", "std", "core", "normal", "binhthuong", "nemotron"):
        return "standard"
    if k in ("flash", "fast", "qwen"):
        return "flash"
    return DEFAULT_MODEL_KEY


def _normalize_think_key(key: Optional[str]) -> str:
    k = re.sub(r"\s+", " ", (key or DEFAULT_THINK_KEY).strip().lower())
    if k in ("low", "fast", "nhanh", "thap", "thấp"):
        return "low"
    if k in ("high", "deep", "sau", "sâu", "cao"):
        return "high"
    return "medium"


def _draw_dipre_crest_logo(size: int = 128):
    """Vẽ Logo Vector DIPRE chính chủ bằng nội suy Cubic Bezier khớp 1:1 SVG Liquid Mercury D."""
    from PIL import Image, ImageDraw

    cs = size * 4
    im = Image.new("RGBA", (cs, cs), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def sc(x: float, y: float) -> Tuple[float, float]:
        return (x / 64.0 * cs, y / 64.0 * cs)

    def cubic(p0, p1, p2, p3, steps=20):
        pts = []
        for i in range(1, steps + 1):
            t = i / steps
            mt = 1.0 - t
            x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
            y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
            pts.append(sc(x, y))
        return pts

    pad = cs * 0.04
    d.rounded_rectangle(
        [pad, pad, cs - pad, cs - pad],
        radius=int(cs * 0.24),
        fill=(9, 9, 13, 250),
        outline=(31, 202, 173, 185),
        width=max(2, int(cs * 0.025)),
    )

    # Path 2 (bóng đáy xám Liquid Mercury): M14 51.5 C20.5 56.2 33.5 57.2 42.8 53 C50.5 49.4 54.5 42.2 54.5 34.2 C51.6 41.4 44.5 46.8 34.8 47.6 C26.5 48.3 20 47.2 14 51.5Z
    m_pts = [sc(14, 51.5)]
    m_pts += cubic((14, 51.5), (20.5, 56.2), (33.5, 57.2), (42.8, 53))
    m_pts += cubic((42.8, 53), (50.5, 49.4), (54.5, 42.2), (54.5, 34.2))
    m_pts += cubic((54.5, 34.2), (51.6, 41.4), (44.5, 46.8), (34.8, 47.6))
    m_pts += cubic((34.8, 47.6), (26.5, 48.3), (20, 47.2), (14, 51.5))
    d.polygon(m_pts, fill=(120, 120, 132, 245))

    # Path 1 (chữ D chính): M14.5 47.5 C11.2 35 12.5 16.5 20.5 10.5 C26 6.4 36 6.8 44 11.5 C51.5 16 55.2 24 54.2 33 C53.2 41 47.5 46.8 40 48.6 C45.5 42.8 46.8 34 44.2 26.5 C41.5 19.2 34.2 15.8 27 17.2 C21.2 18.4 19.2 25 19.6 34.8 C19.8 40.5 17.5 45.2 14.5 47.5Z
    p_pts = [sc(14.5, 47.5)]
    p_pts += cubic((14.5, 47.5), (11.2, 35), (12.5, 16.5), (20.5, 10.5))
    p_pts += cubic((20.5, 10.5), (26, 6.4), (36, 6.8), (44, 11.5))
    p_pts += cubic((44, 11.5), (51.5, 16), (55.2, 24), (54.2, 33))
    p_pts += cubic((54.2, 33), (53.2, 41), (47.5, 46.8), (40, 48.6))
    p_pts += cubic((40, 48.6), (45.5, 42.8), (46.8, 34), (44.2, 26.5))
    p_pts += cubic((44.2, 26.5), (41.5, 19.2), (34.2, 15.8), (27, 17.2))
    p_pts += cubic((27, 17.2), (21.2, 18.4), (19.2, 25), (19.6, 34.8))
    p_pts += cubic((19.6, 34.8), (19.8, 40.5), (17.5, 45.2), (14.5, 47.5))
    d.polygon(p_pts, fill=(250, 250, 252, 255))

    # Tâm tròn ngọc lục bảo #1FCAAD + vệt sáng
    cx, cy = sc(31.5, 32.2)
    cr = 6.5 / 64.0 * cs
    d.ellipse([cx - cr * 1.18, cy - cr * 1.18, cx + cr * 1.18, cy + cr * 1.18], fill=(31, 202, 173, 75))
    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(31, 202, 173, 255))
    hr = cr * 0.56
    d.arc([cx - hr, cy - hr, cx + hr, cy + hr], start=210, end=310, fill=(255, 255, 255, 215), width=max(1, int(cs * 0.025)))

    return im.resize((size, size), Image.Resampling.LANCZOS)


def _draw_think_vector_logo(think_key: str, size: int = 128):
    """Vẽ icon vector hi-res cho 3 cấp độ tư duy (Thấp, Trung bình, Cao)."""
    from PIL import Image, ImageDraw

    cs = size * 4
    im = Image.new("RGBA", (cs, cs), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    lv = _normalize_think_key(think_key)
    cx, cy = cs / 2, cs / 2
    r = cs * 0.44

    if lv == "low":
        bg, rim, active_col, active_bars = (10, 26, 28, 245), (31, 202, 173, 220), (31, 202, 173, 255), 1
    elif lv == "medium":
        bg, rim, active_col, active_bars = (12, 24, 38, 245), (56, 189, 248, 220), (56, 189, 248, 255), 2
    else:
        bg, rim, active_col, active_bars = (34, 24, 10, 245), (245, 184, 0, 230), (245, 184, 0, 255), 3

    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=bg, outline=rim, width=int(cs * 0.035))

    dim_col = (148, 163, 184, 70)
    bar_w = cs * 0.115
    gap = cs * 0.055
    base_y = cy + r * 0.44
    start_x = cx - (bar_w * 3 + gap * 2) / 2
    heights = [r * 0.34, r * 0.58, r * 0.84]

    for i, bh in enumerate(heights):
        bx1 = start_x + i * (bar_w + gap)
        bx2 = bx1 + bar_w
        by1 = base_y - bh
        col = active_col if (i < active_bars) else dim_col
        d.rounded_rectangle([bx1, by1, bx2, base_y], radius=int(bar_w * 0.35), fill=col)

    return im.resize((size, size), Image.Resampling.LANCZOS)


def _draw_brand_vector_logo(brand_key: str, size: int = 128):
    """Vẽ logo vector hi-res cho 3 bậc DIPRE AI (Flash, Standard, Pro)."""
    from PIL import Image, ImageDraw
    import math

    canvas_size = size * 4
    im = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    brand = _normalize_model_key(brand_key)
    cx, cy = canvas_size / 2, canvas_size / 2
    r = canvas_size * 0.44

    if brand == "flash":
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(10, 26, 28, 245), outline=(31, 202, 173, 210), width=int(canvas_size * 0.035))
        bolt = [
            (cx + r * 0.08, cy - r * 0.56),
            (cx - r * 0.36, cy + r * 0.06),
            (cx + r * 0.02, cy + r * 0.06),
            (cx - r * 0.10, cy + r * 0.56),
            (cx + r * 0.38, cy - r * 0.08),
            (cx + r * 0.00, cy - r * 0.08),
        ]
        d.polygon(bolt, fill=(31, 202, 173, 255))
        d.line(bolt + [bolt[0]], fill=(210, 255, 248, 220), width=int(canvas_size * 0.02))
    elif brand == "standard":
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(12, 24, 38, 245), outline=(56, 189, 248, 220), width=int(canvas_size * 0.035))
        ring_r = r * 0.56
        d.ellipse([cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r], outline=(56, 189, 248, 235), width=int(canvas_size * 0.06))
        core_r = r * 0.22
        d.ellipse([cx - core_r, cy - core_r, cx + core_r, cy + core_r], fill=(224, 242, 254, 255))
    else:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(32, 24, 10, 245), outline=(245, 184, 0, 220), width=int(canvas_size * 0.035))
        pts = []
        for i in range(6):
            angle = math.radians(60 * i - 30)
            pts.append((cx + r * 0.62 * math.cos(angle), cy + r * 0.62 * math.sin(angle)))
        d.polygon([cx, cy, pts[5], pts[0], pts[1]], fill=(250, 204, 21, 255))
        d.polygon([cx, cy, pts[1], pts[2], pts[3]], fill=(245, 158, 11, 255))
        d.polygon([cx, cy, pts[3], pts[4], pts[5]], fill=(217, 119, 6, 255))
        d.line([pts[0], pts[1], pts[2], pts[3], pts[4], pts[5], pts[0]], fill=(255, 248, 220, 230), width=int(canvas_size * 0.025))
        cr = canvas_size * 0.07
        d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(255, 255, 255, 250))

    return im.resize((size, size), Image.Resampling.LANCZOS)


def _render_ai_models_card(pfx: str, current_model: str, is_high_admin: bool, current_think: str = DEFAULT_THINK_KEY) -> io.BytesIO:
    """Vẽ ảnh Liquid Glass danh sách 3 bậc DIPRE AI + mức suy luận."""
    if G is None:
        raise RuntimeError("G (glass.py) is not available")

    cv = G.GlassCanvas(860, 510, scale=2, out=1.25, dim=85)

    # 1. Header với Logo DIPRE chính chủ
    cv.header(
        20, 20, 840, 72,
        "DIPRE AI TIER ENGINE",
        "Hệ thống 3 bậc DIPRE AI (Chuyển đổi tức thì theo tác vụ)",
        tag="DIPRE AI",
        tag_grad=((31, 202, 173), (15, 118, 110)),
        logo=_draw_dipre_crest_logo(128),
        logo_size=44,
    )

    y = 112
    f_name = cv.font("b", 16)
    f_creator = cv.font("b", 10.5)
    f_cmd = cv.font("b", 12)
    f_desc = cv.font("r", 11.5)
    f_badge = cv.font("b", 10)

    cur_key = _normalize_model_key(current_model)

    for key, info in AVAILABLE_MODELS.items():
        is_active = (key == cur_key)
        brand_col = info.get("brand_color", (139, 92, 246))
        creator_name = info.get("creator", "AI Studio")
        gateway_name = info.get("gateway_display", "GATEWAY")

        box_card = (20, y, 840, y + 84)
        if is_active:
            cv.glass(box_card, 16, blur=18, tint_grad=(brand_col, (40, 45, 70), 120), rim=(255, 120))
        else:
            cv.glass(box_card, 16, blur=18, tint=(15, 20, 32, 60), rim=(150, 40))

        # Logo thương hiệu
        logo_img = _draw_brand_vector_logo(key, size=cv.s(54))
        cv._comp(logo_img, cv.s(36), cv.s(y + 15))

        # Khối thông tin
        tx = 106
        # Dòng 1: Tên + Creator Badge + Active Badge
        t_w = cv.text(tx, y + 21, info["name"], f_name, (255, 255, 255), vcenter=True)
        cv.pill(
            tx + t_w + 12,
            y + 11,
            creator_name.upper(),
            f_creator,
            (brand_col, (max(0, brand_col[0] - 40), max(0, brand_col[1] - 40), max(0, brand_col[2] - 40))),
            h=20,
            padx=8
        )

        if is_active:
            pill_x = tx + t_w + 12 + cv.tlen(creator_name.upper(), f_creator) + 24
            cv.pill(pill_x, y + 11, "● ĐANG DÙNG", f_badge, ((34, 197, 94), (16, 185, 129)), h=20, padx=8)

        # Dòng 2: Cú pháp lệnh
        cv.text(tx, y + 43, f"Lệnh chọn: {pfx}ai model {key}", f_cmd, (253, 224, 71), vcenter=True)

        # Dòng 3: Mô tả
        cv.text(tx, y + 64, info["desc"], f_desc, (210, 225, 245), vcenter=True)

        # Cột phải: Gateway badge
        gw_w = cv.tlen(gateway_name, f_badge) + 20
        cv.glass_pill(825 - gw_w, y + 27, gateway_name, f_badge, grad=((70, 80, 105), (45, 55, 75)), h=28, padx=10, tint_alpha=110)

        y += 94

    # Footer bar
    f_bar_y = 415
    cv.bar(20, f_bar_y, 840, f_bar_y + 74, r=16)
    f_ft1 = cv.font("b", 12.5)
    f_ft2 = cv.font("r", 11)
    think_lbl = REASONING_LEVELS.get(_normalize_think_key(current_think), REASONING_LEVELS["medium"])["label"]
    if is_high_admin:
        cv.text(38, f_bar_y + 24, f"Lenh chon: {pfx}ai model <flash|standard|pro>   •   {pfx}ai think <low|medium|high> (Dang bat: {think_lbl})", f_ft1, (255, 255, 255), vcenter=True)
    else:
        cv.text(38, f_bar_y + 24, f"Huong dan: Go {pfx}ai <cau hoi> de tro chuyen • Muc suy luan hien tai: {think_lbl}", f_ft1, (255, 255, 255), vcenter=True)
    cv.text(38, f_bar_y + 50, "Quyen doi bac AI & muc suy luan duoc gioi han cho Admintris & Chu he thong.", f_ft2, (180, 195, 215), vcenter=True)

    return cv.finalize(format="PNG")


def _render_ai_think_card(pfx: str, current_think: str, is_high_admin: bool, current_model: str = DEFAULT_MODEL_KEY) -> io.BytesIO:
    """Vẽ ảnh Liquid Glass danh sách 3 cấp độ tư duy (Thấp / Trung bình / Cao) với logo DIPRE."""
    if G is None:
        raise RuntimeError("G (glass.py) is not available")

    cv = G.GlassCanvas(860, 510, scale=2, out=1.25, dim=85)

    cur_model = _normalize_model_key(current_model)
    cur_model_name = AVAILABLE_MODELS[cur_model]["name"]
    cv.header(
        20, 20, 840, 72,
        "DIPRE THINKING LEVELS",
        f"Điều chỉnh cấp độ tư duy AI (Model hiện tại: {cur_model_name})",
        tag="ASK DIPRE",
        tag_grad=((56, 189, 248), (31, 202, 173)),
        logo=_draw_dipre_crest_logo(128),
        logo_size=44,
    )

    think_cards = [
        ("low", "Cấp Độ: Thấp (Low)", "FAST", (31, 202, 173), "Tư duy tối giản, ưu tiên tốc độ phản hồi nhanh & trả lời thẳng."),
        ("medium", "Cấp Độ: Trung Bình (Medium)", "BALANCED", (56, 189, 248), "Cân đối giữa phân tích logic và tốc độ phản hồi (Mặc định)."),
        ("high", "Cấp Độ: Cao (High)", "DEEP", (245, 184, 0), "Tư duy đa bước chuyên sâu, soi kỹ cấu hình & rủi ro Rate-Limit."),
    ]

    y = 112
    f_name = cv.font("b", 16)
    f_tag = cv.font("b", 10.5)
    f_cmd = cv.font("b", 12)
    f_desc = cv.font("r", 11.5)
    f_badge = cv.font("b", 10)
    cur_lv = _normalize_think_key(current_think)

    for key, title, badge_txt, col, desc in think_cards:
        is_active = (key == cur_lv)
        box_card = (20, y, 840, y + 84)
        if is_active:
            cv.glass(box_card, 16, blur=18, tint_grad=(col, (40, 45, 70), 120), rim=(255, 120))
        else:
            cv.glass(box_card, 16, blur=18, tint=(15, 20, 32, 60), rim=(150, 40))

        icon_img = _draw_think_vector_logo(key, size=cv.s(54))
        cv._comp(icon_img, cv.s(36), cv.s(y + 15))

        tx = 106
        t_w = cv.text(tx, y + 21, title, f_name, (255, 255, 255), vcenter=True)
        cv.pill(
            tx + t_w + 12,
            y + 11,
            badge_txt,
            f_tag,
            (col, (max(0, col[0] - 40), max(0, col[1] - 40), max(0, col[2] - 40))),
            h=20,
            padx=8,
        )
        if is_active:
            pill_x = tx + t_w + 12 + cv.tlen(badge_txt, f_tag) + 24
            cv.pill(pill_x, y + 11, "● ĐANG DÙNG", f_badge, ((34, 197, 94), (16, 185, 129)), h=20, padx=8)

        vn_alias = {"low": "thấp", "medium": "trung bình", "high": "cao"}[key]
        cv.text(tx, y + 43, f"Lệnh chọn: {pfx}ai think {key}   (hoặc: {pfx}ai think {vn_alias})", f_cmd, (253, 224, 71), vcenter=True)
        cv.text(tx, y + 64, desc, f_desc, (210, 225, 245), vcenter=True)

        right_tag = f"LEVEL {key.upper()}"
        gw_w = cv.tlen(right_tag, f_badge) + 20
        cv.glass_pill(825 - gw_w, y + 27, right_tag, f_badge, grad=((70, 80, 105), (45, 55, 75)), h=28, padx=10, tint_alpha=110)

        y += 94

    f_bar_y = 415
    cv.bar(20, f_bar_y, 840, f_bar_y + 74, r=16)
    f_ft1 = cv.font("b", 12.5)
    f_ft2 = cv.font("r", 11)
    if is_high_admin:
        cv.text(38, f_bar_y + 24, f"Lệnh chọn: {pfx}ai think <low|medium|high>   •   Hoặc gõ tiếng Việt: thấp / trung bình / cao", f_ft1, (255, 255, 255), vcenter=True)
    else:
        cv.text(38, f_bar_y + 24, f"Hướng dẫn: Gõ {pfx}ai <câu hỏi> để chat với AI ({cur_model_name} • Tư duy {REASONING_LEVELS[cur_lv]['label']})", f_ft1, (255, 255, 255), vcenter=True)
    cv.text(38, f_bar_y + 50, "Quyền thay đổi cấp độ tư duy AI được giới hạn cho Admintris & Chủ hệ thống.", f_ft2, (180, 195, 215), vcenter=True)

    return cv.finalize(format="PNG")


def _call_llm_gateway(
    messages: List[Dict[str, str]],
    max_tokens: int = 1800,
    model_key: str = DEFAULT_MODEL_KEY,
    think_key: str = DEFAULT_THINK_KEY,
) -> Optional[str]:
    norm_key = _normalize_model_key(model_key)
    norm_think = _normalize_think_key(think_key)
    tier_info = AVAILABLE_MODELS[norm_key]
    think_info = REASONING_LEVELS[norm_think]
    other_keys = [k for k in ("standard", "flash", "pro") if k != norm_key]
    candidate_list = list(tier_info["candidates"])
    for ok in other_keys:
        candidate_list.extend(AVAILABLE_MODELS[ok]["candidates"])
    endpoint = tier_info["endpoint"]
    headers = tier_info["headers"]

    for cand in candidate_list:
        try:
            req_payload: Dict[str, Any] = {
                "model": cand["model_id"],
                "messages": messages,
                "max_tokens": max(max_tokens, int(cand.get("max_tokens", 1800)), int(think_info["max_tokens"])),
                "temperature": cand.get("temperature", 0.5),
            }
            if cand.get("supports_effort"):
                eff = think_info["effort"]
                if cand.get("cap_effort_medium") and eff == "high":
                    eff = "medium"
                req_payload["reasoning"] = {"effort": eff}
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(req_payload).encode("utf-8"),
                headers=headers,
            )
            t_out = float(cand.get("timeout", 22.0)) + float(think_info.get("bonus_timeout", 0.0))
            with urllib.request.urlopen(req, timeout=t_out, context=SSL_CTX) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    if content and isinstance(content, str):
                        clean_text = content.strip()
                        if len(clean_text) >= 1:
                            return clean_text
        except Exception:
            continue
    return None


AI_MEMORY_FILE = DATA_DIR / "ai_memory.json"


class ChatMemory:
    """Bộ nhớ hội thoại bền vững (Persistent Chat Memory):
    - Tự động lưu và tải từ file data/ai_memory.json.
    - Lưu tối đa 20 lượt tương tác gần nhất theo từng kênh/DM (40 messages).
    - Duy trì ngữ cảnh mượt mà, nhớ sâu trò chơi (nối từ, đố vui) và nội dung trao đổi.
    """
    def __init__(self, max_history: int = 20):
        self.max_history = max_history
        self._history: Dict[str, List[Dict[str, str]]] = self._load()

    def _load(self) -> Dict[str, List[Dict[str, str]]]:
        if AI_MEMORY_FILE.exists():
            try:
                raw = json.loads(AI_MEMORY_FILE.read_text(encoding="utf-8"))
                return {str(k): list(v) for k, v in raw.items()}
            except Exception:
                pass
        return defaultdict(list)

    def _save(self):
        try:
            AI_MEMORY_FILE.write_text(
                json.dumps(self._history, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    def add(self, channel_id: int, role: str, content: str, sender_name: Optional[str] = None):
        key = str(channel_id)
        if key not in self._history:
            self._history[key] = []
        hist = self._history[key]

        # Chuẩn hoá content để LLM luôn nhận biết rõ ai đang nói
        final_content = content
        if role == "user" and sender_name:
            clean_name = re.sub(r'[^a-zA-Z0-9_\-\s]', '', sender_name).strip()[:30] or "User"
            # Nếu chưa có tiền tố tên thì thêm vào
            if not final_content.startswith(f"{clean_name}:"):
                final_content = f"{clean_name}: {final_content}"

        entry = {"role": role, "content": final_content}
        hist.append(entry)
        if len(hist) > self.max_history * 2:
            self._history[key] = hist[-self.max_history * 2:]
        self._save()

    def get(self, channel_id: int) -> List[Dict[str, str]]:
        key = str(channel_id)
        return list(self._history.get(key, []))

    def clear(self, channel_id: int):
        key = str(channel_id)
        if key in self._history:
            del self._history[key]
            self._save()


class AICog(commands.Cog, name="AI"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.memory = ChatMemory(max_history=20)
        self.settings: Dict[str, Any] = self._load_settings()
        self._cooldowns: Dict[int, float] = {}
        self._user_rate_window: Dict[int, List[float]] = defaultdict(list)

    def _load_settings(self) -> Dict[str, Any]:
        if AI_SETTINGS_FILE.exists():
            try:
                return json.loads(AI_SETTINGS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"active_guilds": {}}

    def _save_settings(self):
        try:
            AI_SETTINGS_FILE.write_text(
                json.dumps(self.settings, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    def _is_ai_on_guild(self, guild_id: Optional[int]) -> bool:
        if not guild_id:
            return True
        return bool(self.settings.get("active_guilds", {}).get(str(guild_id), False))

    def _set_ai_guild(self, guild_id: int, state: bool):
        ag = self.settings.setdefault("active_guilds", {})
        ag[str(guild_id)] = state
        self._save_settings()

    def _pfx(self) -> str:
        try:
            return get_prefix(self.bot)
        except Exception:
            return getattr(self.bot, "_own_prefix", None) or "!"

    def _check_privilege(self, user_id: int) -> Tuple[bool, bool]:
        bot_uid = getattr(self.bot.user, "id", 0)
        is_owner = (user_id == bot_uid)
        cfg_owners = set()
        try:
            cfg_path = next(
                (p for p in (BASE_DIR / "config.json", DATA_DIR / "config.json") if p.exists()),
                None,
            )
            if cfg_path:
                cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
                for acc in cfg_data.get("accounts", []):
                    if isinstance(acc, dict) and acc.get("uid") == bot_uid:
                        for oid in list(acc.get("owner_ids") or []) + [acc.get("created_by")]:
                            if oid and str(oid).isdigit():
                                cfg_owners.add(int(oid))
        except Exception:
            pass

        setting_file = DATA_DIR / f"{bot_uid}_setting.json"
        this_conf: Dict[str, Any] = {}
        if setting_file.exists():
            try:
                this_conf = json.loads(setting_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        mod_list = set(cfg_owners)
        for x in this_conf.get("admintris", this_conf.get("moderator", [])):
            if str(x).isdigit():
                mod_list.add(int(x))

        is_high_admin = is_owner or (user_id in mod_list)

        admin_list = set(mod_list)
        for x in this_conf.get("admins", this_conf.get("admin", [])):
            if str(x).isdigit():
                admin_list.add(int(x))

        is_admin = is_high_admin or (user_id in admin_list)
        return is_high_admin, is_admin

    def _is_bot_on_guild(self, guild_id: Optional[int]) -> bool:
        if not guild_id:
            return True
        bot_uid = getattr(self.bot.user, "id", 0)
        setting_file = DATA_DIR / f"{bot_uid}_setting.json"
        if setting_file.exists():
            try:
                this_conf = json.loads(setting_file.read_text(encoding="utf-8"))
                return bool(this_conf.get("guild_active", {}).get(str(guild_id), False))
            except Exception:
                pass
        return False

    def _can_respond_in_guild(self, guild_id: Optional[int], user_id: int) -> bool:
        if not self._is_ai_on_guild(guild_id):
            return False
        _, is_admin = self._check_privilege(user_id)
        if is_admin:
            return True
        return self._is_bot_on_guild(guild_id)

    def _build_system_prompt(self, user_name: str, guild_name: Optional[str] = None, think_key: str = DEFAULT_THINK_KEY) -> str:
        bot_user = getattr(self.bot, "user", None) if self.bot else None
        bot_name = getattr(bot_user, "name", "DIPRE AI") if bot_user else "DIPRE AI"
        g_info = f"tại máy chủ '{guild_name}'" if guild_name else "trong tin nhắn riêng (DM)"
        think_lv = _normalize_think_key(think_key)
        think_note = {
            "low": "Trả lời cực ngắn gọn, đi thẳng vào ý chính (1-2 câu cho giao tiếp thường).",
            "medium": "Trả lời tự nhiên, súc tích 1-3 câu với câu hỏi thường; đủ ý rõ ràng khi hỏi kỹ thuật.",
            "high": "Phân tích kỹ lưỡng từng bước, nêu rõ cấu hình an toàn, tránh rate-limit khi được hỏi sâu.",
        }[think_lv]
        return (
            f"Bạn là **DIPRE AI** (chạy trên tài khoản `{bot_name}`, nói chuyện {g_info} với `{user_name}`).\n\n"
            f"PHONG CÁCH MIỀN BẮC TỰ NHIÊN (BẮT BUỘC):\n"
            f"- Nói chuyện chuẩn vibe người trẻ Hà Nội / miền Bắc ngoài đời trên Discord: thông minh, thân thiện, hoạt ngôn, dí dỏm vừa phải.\n"
            f"- Luôn xưng 'tôi' (hoặc 'mình') và gọi đối phương là 'ông' / 'bà' / '{user_name}'. KHÔNG xưng 'anh/em' khách sáo kiểu bot CSKH.\n"
            f"- Dùng từ ngữ miền Bắc tự nhiên theo ngữ cảnh ('thế', 'đấy', 'chứ', 'à', 'phát', 'ngon luôn', 'cân được'), TUYỆT ĐỐI KHÔNG dùng từ miền Nam ('nè', 'nha', 'tui', 'nghen', 'hén') và KHÔNG ghép bừa chữ 'nhé' vào câu dịch tiếng Anh kiểu 'Bạn đang làm gì hôm nay nhé?'.\n"
            f"- {think_note}\n"
            f"- TUYỆT ĐỐI KHÔNG tự nhận là mô hình/hãng thứ ba (Baidu, Ernie, NVIDIA, Nemotron, Kilo, Qwen, OpenAI).\n\n"
            f"VÍ DỤ CÁCH TRẢ LỜI MẪU:\n"
            f"- Người dùng: 'chào' -> 'Ồ chào ông, nay có kèo gì cần xử lý không?'\n"
            f"- Người dùng: 'mày biết làm gì' -> 'Cũng đủ món đấy: set Presence RPC, treo voice 24/7, chạy Auto Quest, soi Sniper hay kéo video TikTok/YouTube đều cân hết. Ông cần dùng cái nào?'\n\n"
            f"KIẾN THỨC HỆ THỐNG DIPRE & USERBOT:\n"
            f"- Presence Studio: Custom Rich Presence RPC, YouTube/Music Sync, Custom Status Rotator.\n"
            f"- Voice & Audio: Treo Voice 24/7 (join/leave/play qua Lavalink), bảo vệ chống nhảy kênh gây 429.\n"
            f"- Automation & Anti-Ban: Auto Quest Completer, Sniper Radar, `DiscordAntiBanGuard` (giới hạn 16 write/phút, jitter ngẫu nhiên, Circuit Breaker tự nghỉ khi gặp 429).\n"
            f"- Lệnh UserBot chính (`{self._pfx()}`): `ai <câu hỏi>`, `ai model <flash|standard|pro>`, `ai think <low|medium|high>`, `ai clear`, `ai on/off`, `tiktok/yt/fb/scl` (tải media), `quest`, `afk`, `info`, `server`, `crypto`, `weather`, `mail gen`.\n\n"
            f"QUY TẮC NGỮ CẢNH & NỐI TỪ:\n"
            f"- Bám sát lịch sử hội thoại. Nếu đang chơi nối từ tiếng Việt, nối đúng 1 từ ghép 2 tiếng có nghĩa bắt đầu bằng tiếng cuối của đối phương (vd 'biến số' -> 'số phận')."
        )

    async def _send_ai_reply(self, target_msg: discord.Message, prompt_text: str, user_name: str):
        channel = target_msg.channel
        chan_id = channel.id

        try:
            async with channel.typing():
                clean_name = re.sub(r'[^a-zA-Z0-9_\-\s]', '', user_name).strip()[:30] or "User"
                cur_model = _normalize_model_key(self.settings.get("current_model", DEFAULT_MODEL_KEY))
                cur_think = _normalize_think_key(self.settings.get("reasoning_level", DEFAULT_THINK_KEY))
                sys_prompt = self._build_system_prompt(
                    user_name=clean_name,
                    guild_name=target_msg.guild.name if target_msg.guild else None,
                    think_key=cur_think,
                )
                messages: List[Dict[str, str]] = [{"role": "system", "content": sys_prompt}]

                recent_hist = self.memory.get(chan_id)
                for h in recent_hist:
                    messages.append({"role": h["role"], "content": h["content"]})

                user_msg_content = f"{clean_name}: {prompt_text}"
                messages.append({"role": "user", "content": user_msg_content})

                reply_text = await asyncio.to_thread(_call_llm_gateway, messages, 1800, cur_model, cur_think)

                if not reply_text:
                    reply_text = f"Mạng hơi lag tí, ông hỏi lại phát xem nào {clean_name}."

                self.memory.add(chan_id, "user", prompt_text, sender_name=clean_name)
                self.memory.add(chan_id, "assistant", reply_text)

                chunks = []
                while len(reply_text) > 1900:
                    split_idx = reply_text.rfind("\n", 0, 1900)
                    if split_idx == -1:
                        split_idx = 1900
                    chunks.append(reply_text[:split_idx].strip())
                    reply_text = reply_text[split_idx:].strip()
                if reply_text:
                    chunks.append(reply_text)

                first = True
                for chunk in chunks:
                    if not chunk:
                        continue
                    if first:
                        reply_msg = await autorep(target_msg, chunk)
                        if reply_msg:
                            autodelet(reply_msg, delay=60)
                        first = False
                    else:
                        chunk_msg = await channel.send(chunk)
                        if chunk_msg:
                            autodelet(chunk_msg, delay=60)
        except Exception as e:
            try:
                err_msg = await autorep(target_msg, f"Ui, co chut truc trac nho xiu rui: `{e}`")
                autodelet(err_msg, delay=20)
            except Exception:
                pass

    def _render_ai_status_card(self, ctx: commands.Context) -> io.BytesIO:
        try:
            from apps.user_discord.utils import glass as G
        except ImportError:
            from utils import glass as G

        active_map = self.settings.get("active_guilds", {})
        on_guilds = []
        all_guilds = self.bot.guilds

        for gid_str, is_on in active_map.items():
            if is_on:
                try:
                    g = self.bot.get_guild(int(gid_str))
                    if g:
                        on_guilds.append({
                            "name": g.name,
                            "id": str(g.id),
                            "members": g.member_count or len(g.members),
                        })
                    else:
                        on_guilds.append({
                            "name": f"Server {gid_str}",
                            "id": gid_str,
                            "members": 0,
                        })
                except Exception:
                    pass

        cur_guild = ctx.guild
        cur_guild_id = cur_guild.id if cur_guild else None
        cur_on = self._is_ai_on_guild(cur_guild_id)
        pfx = self._pfx()

        LW, LH = 1040, 560
        pad = 20
        head_h = 70
        gap = 14
        left_w = 330

        cv = G.GlassCanvas(LW, LH, scale=2, out=1.35)

        f_st = cv.font("b", 12)
        st_text = "🟢 AI DANG BAT" if cur_on else "🔴 AI DANG TAT"
        st_pill_col = G.G_ON if cur_on else G.G_OFF
        st_dot = (167, 255, 214) if cur_on else (255, 170, 170)

        cur_tier = _normalize_model_key(self.settings.get("current_model", DEFAULT_MODEL_KEY))
        cur_think = _normalize_think_key(self.settings.get("reasoning_level", DEFAULT_THINK_KEY))
        tier_label = AVAILABLE_MODELS[cur_tier]["name"]
        think_short = REASONING_LEVELS[cur_think]["label"].split(" ")[0]
        cv.header(
            pad, pad, LW - pad, head_h,
            "DIPRE AI MONITOR PANEL",
            f"Prefix {pfx} • {tier_label} ({think_short}) • {len(on_guilds)} Active Server(s)",
            tag="DIPRE AI",
            tag_grad=((31, 202, 173), (15, 118, 110)),
            logo=_draw_dipre_crest_logo(128),
            logo_size=44,
            right_reserve=180
        )
        cv.glass_pill(
            LW - pad - 16, pad + head_h / 2 - 15,
            st_text, f_st, st_pill_col, align="r", dot=st_dot
        )

        top = pad + head_h + gap
        bottom = LH - pad
        lx1, lx2 = pad, pad + left_w

        p_h = 135
        cv.glass((lx1, top, lx2, top + p_h), 20, blur=24, tint=(14, 18, 30, 95))
        cv.text(lx1 + 18, top + 18, "MAY CHU HIEN TAI", cv.font("b", 11), G.C_DIM, vcenter=True)
        if cur_guild:
            g_name = cur_guild.name or "Server"
            cv.text(lx1 + 18, top + 46, cv.fit(g_name, cv.font("b", 16), left_w - 36), cv.font("b", 16), G.C_GOLD, vcenter=True)
            cv.text(lx1 + 18, top + 72, f"ID: {cur_guild.id}  •  {cur_guild.member_count:,} mems", cv.font("r", 11.5), G.C_MUTED, vcenter=True)
            cur_badge = "🟢 DANG BAT TU DONG" if cur_on else "🔴 DANG TAT TU DONG"
            cur_grad = G.G_GREEN if cur_on else G.G_RED
            cv.pill(lx1 + 18, top + 94, cur_badge, cv.font("b", 10.5), grad=cur_grad, h=22)
        else:
            cv.text(lx1 + 18, top + 46, "Tin nhan rieng (DM)", cv.font("b", 16), G.C_GOLD, vcenter=True)
            cv.text(lx1 + 18, top + 72, "Truc tiep voi Bot", cv.font("r", 11.5), G.C_MUTED, vcenter=True)
            cv.pill(lx1 + 18, top + 94, "🟢 LUON KICH HOAT", cv.font("b", 10.5), grad=G.G_GREEN, h=22)

        s_y1 = top + p_h + gap
        s_h = 130
        cv.glass((lx1, s_y1, lx2, s_y1 + s_h), 20, blur=24, tint=(14, 18, 30, 95))
        cv.text(lx1 + 18, s_y1 + 18, "THONG KE KICH HOAT AI", cv.font("b", 11), G.C_DIM, vcenter=True)

        stats = [
            ("Server Bat AI", f"{len(on_guilds)}", G.C_ON),
            ("Tong Server", f"{len(all_guilds)}", G.C_TEXT),
            ("Do Phu Song", f"{(len(on_guilds)/max(1, len(all_guilds))*100):.1f}%", G.C_GOLD),
        ]
        box_w = (left_w - 36 - 16) / 3
        for i, (lbl, val, col) in enumerate(stats):
            bx1 = lx1 + 18 + i * (box_w + 8)
            bx2 = bx1 + box_w
            cv.glass((bx1, s_y1 + 38, bx2, s_y1 + 38 + 72), 12, blur=10, tint=(20, 26, 44, 70))
            cv.text(bx1 + box_w / 2, s_y1 + 58, val, cv.font("b", 17), col, align="c", vcenter=True)
            cv.text(bx1 + box_w / 2, s_y1 + 88, lbl, cv.font("r", 9.5), G.C_MUTED, align="c", vcenter=True)

        t_y1 = s_y1 + s_h + gap
        cv.glass((lx1, t_y1, lx2, bottom), 20, blur=24, tint=(14, 18, 30, 95))
        cv.text(lx1 + 18, t_y1 + 20, "HUONG DAN DIEU KHIEN", cv.font("b", 11), G.C_DIM, vcenter=True)
        cv.text(lx1 + 18, t_y1 + 46, f"• {pfx}ai on / off : Bat/tat AI tai server", cv.font("r", 11), G.C_TEXT, vcenter=True)
        cv.text(lx1 + 18, t_y1 + 72, f"• {pfx}ai <cau hoi> : Tro chuyen truc tiep", cv.font("r", 11), G.C_TEXT, vcenter=True)
        cv.text(lx1 + 18, t_y1 + 98, f"• Tag @bot hoac Reply tin nhan de hoi", cv.font("r", 11), G.C_MUTED, vcenter=True)

        rx1, rx2 = lx2 + gap, LW - pad
        cv.glass((rx1, top, rx2, bottom), 22, blur=24, tint=(14, 18, 30, 95))
        cv.text(rx1 + 24, top + 24, "DANH SACH MAY CHU KICH HOAT TU DONG", cv.font("b", 14), G.C_TEXT, vcenter=True)
        cv.text(rx2 - 24, top + 24, f"{len(on_guilds)} May chu", cv.font("b", 12), G.C_ON, align="r", vcenter=True)
        cv.rrect((rx1 + 24, top + 44, rx2 - 24, top + 45), 0.5, fill=(255, 255, 255, 30))

        list_y = top + 56
        row_h = 56
        max_rows = 6

        if on_guilds:
            for idx, ginfo in enumerate(on_guilds[:max_rows]):
                ry1 = list_y + idx * (row_h + 8)
                ry2 = ry1 + row_h
                cv.glass((rx1 + 20, ry1, rx2 - 20, ry2), 14, blur=12, tint=(22, 28, 48, 65))
                cv.circle_image(None, rx1 + 32, ry1 + 12, 32, ring=G.G_BRAND, letter=str(idx + 1))
                tx = rx1 + 32 + 32 + 14
                cv.text(tx, ry1 + 18, cv.fit(ginfo["name"], cv.font("b", 13.5), 320), cv.font("b", 13.5), G.C_TEXT, vcenter=True)
                cv.text(tx, ry1 + 38, f"ID: {ginfo['id']}   •   {ginfo['members']:,} thanh vien", cv.font("r", 10.5), G.C_MUTED, vcenter=True)
                cv.pill(rx2 - 34, ry1 + 17, "ACTIVE", cv.font("b", 10), grad=G.G_GREEN, h=22, align="r")

            if len(on_guilds) > max_rows:
                rest_cnt = len(on_guilds) - max_rows
                cv.text(rx1 + 30, bottom - 22, f"… va con {rest_cnt} may chu khac dang kich hoat.", cv.font("r", 11), G.C_MUTED, vcenter=True)
        else:
            cv.text((rx1 + rx2) / 2, (top + bottom) / 2 - 10, "Chua co may chu nao kich hoat AI tu dong", cv.font("b", 15), G.C_MUTED, align="c", vcenter=True)
            cv.text((rx1 + rx2) / 2, (top + bottom) / 2 + 18, f"Go {pfx}ai on tai may chu de kich hoat tinh nang nay!", cv.font("r", 12), G.C_DIM, align="c", vcenter=True)

        return cv.finalize()

    @menu_entry("AUTOMATION & QUEST", "ai", "Tro ly AI hoi dap thong minh & nhi nhanh",
                badge="SMART", icon_sym="✨", icon_color=(192, 132, 252), order=1)
    @alias_declare("ai", ["chat", "hoi", "ask"])
    @commands.group(
        name="ai",
        aliases=["chat", "hoi", "ask"],
        invoke_without_command=True,
        help="He thong tro ly AI tro chuyen thong minh khong gioi han."
    )
    async def cmd_ai(self, ctx: commands.Context, *, question: Optional[str] = None):
        p = self._pfx()

        if not question:
            card_buf = None
            try:
                card_buf = await async_help_card("ai", p)
            except Exception:
                card_buf = None

            if card_buf:
                try:
                    file = discord.File(card_buf, filename="ai_help.png")
                    sent_msg = await autorep(
                        ctx.message,
                        content=f"✨ **TRO LY AI THONG MINH & NHI NHANH** (`{p}ai`)",
                        file=file
                    )
                    autodelet(sent_msg, delay=45)
                    return
                except Exception:
                    pass

            cur_model = _normalize_model_key(self.settings.get("current_model", DEFAULT_MODEL_KEY))
            cur_think = _normalize_think_key(self.settings.get("reasoning_level", DEFAULT_THINK_KEY))
            cur_info = AVAILABLE_MODELS[cur_model]
            think_info = REASONING_LEVELS[cur_think]
            ai_status = "ĐANG BẬT" if self._is_ai_on_guild(ctx.guild.id if ctx.guild else None) else "ĐANG TẮT"
            guide = (
                f"✨ **DIPRE AI ASSISTANT - HƯỚNG DẪN SỬ DỤNG** ✨\n\n"
                f"• `{p}ai <câu hỏi>` : Đặt câu hỏi trực tiếp cho AI.\n"
                f"• `{p}ai model <flash|standard|pro>` : Xem/đổi bậc AI (Admin cấp cao).\n"
                f"• `{p}ai think <low|medium|high>` : Đổi mức độ suy luận (Admin cấp cao).\n"
                f"• `{p}ai clear` : Xoá sạch trí nhớ lịch sử chat tại kênh này.\n"
                f"• `{p}ai on` / `off` : Bật/tắt AI tự động tại server này (Admin only).\n"
                f"• `{p}ai status` : Xem trạng thái & server đang bật AI.\n\n"
                f"📌 **Trạng thái:** {ai_status} | **Bậc:** `{cur_model}` ({cur_info['name']}) | **Suy luận:** `{cur_think}` ({think_info['label']})"
            )
            sent_msg = await autorep(ctx.message, guide)
            autodelet(sent_msg, delay=45)
            return

        clean_q = question.lstrip("+").strip()
        if not clean_q:
            sent_msg = await autorep(ctx.message, f"Ban chua nhap cau hoi ne! Go `{p}ai <cau hoi>` nha ✨")
            autodelet(sent_msg, delay=15)
            return

        user_name = ctx.author.display_name or ctx.author.name
        await self._send_ai_reply(ctx.message, clean_q, user_name)

    @cmd_ai.command(name="on", aliases=["bat"])
    async def ai_on(self, ctx: commands.Context):
        if not ctx.guild:
            sent_msg = await autorep(ctx.message, "Trong tin nhan rieng (DM), AI luon luon duoc bat san roi ne! ✨")
            autodelet(sent_msg, delay=15)
            return

        _, is_admin = self._check_privilege(ctx.author.id)
        if not is_admin:
            sent_msg = await autorep(ctx.message, "⛔ Lenh bat AI yeu cau quyen **Admin tro len** cua bot!")
            autodelet(sent_msg, delay=15)
            return

        self._set_ai_guild(ctx.guild.id, True)
        sent_msg = await autorep(
            ctx.message,
            f"🎉 **Da BAT AI tu dong tai may chu:** `{ctx.guild.name}`!\n"
            f"👉 Bay gio moi nguoi chi can **Tag @bot** hoac **Reply tin nhan cua bot** la bot se tro chuyen sieu nhi nhanh nha! ✨"
        )
        autodelet(sent_msg, delay=30)

    @cmd_ai.command(name="off", aliases=["tat"])
    async def ai_off(self, ctx: commands.Context):
        if not ctx.guild:
            sent_msg = await autorep(ctx.message, "Khong the tat AI trong tin nhan rieng (DM).")
            autodelet(sent_msg, delay=15)
            return

        _, is_admin = self._check_privilege(ctx.author.id)
        if not is_admin:
            sent_msg = await autorep(ctx.message, "⛔ Lenh tat AI yeu cau quyen **Admin tro len** cua bot!")
            autodelet(sent_msg, delay=15)
            return

        self._set_ai_guild(ctx.guild.id, False)
        sent_msg = await autorep(
            ctx.message,
            f"💤 **Da TAT AI tu dong tai may chu:** `{ctx.guild.name}`.\n"
            f"Bot se khong tu rep khi duoc Tag hoac Reply tai server nay nua."
        )
        autodelet(sent_msg, delay=30)

    @cmd_ai.command(name="status", aliases=["stt", "list"])
    async def ai_status(self, ctx: commands.Context):
        p = self._pfx()
        buf = None
        try:
            loop = asyncio.get_event_loop()
            buf = await loop.run_in_executor(None, self._render_ai_status_card, ctx)
        except Exception:
            buf = None

        if buf:
            try:
                file = discord.File(buf, filename="ai_status.png")
                sent_msg = await autorep(
                    ctx.message,
                    content=f"🤖 **BAO CAO TRANG THAI AI CHATBOT** (`{p}ai status`)",
                    file=file
                )
                autodelet(sent_msg, delay=45)
                return
            except Exception:
                pass

        active_map = self.settings.get("active_guilds", {})
        on_guilds = [f"• `{gid}`" for gid, on in active_map.items() if on]
        msg = f"🤖 **TRANG THAI AI:** Hien co `{len(on_guilds)}` server dang bat AI."
        sent_msg = await autorep(ctx.message, msg)
        autodelet(sent_msg, delay=30)

    @cmd_ai.command(name="clear", aliases=["reset", "xoa"])
    async def ai_clear(self, ctx: commands.Context):
        """Xoá sạch lịch sử trò chuyện của AI tại kênh này."""
        self.memory.clear(ctx.channel.id)
        msg = await autorep(ctx.message, "🧹 **Đã xoá sạch lịch sử trò chuyện của AI tại kênh này!**")
        autodelet(msg, delay=15)

    @cmd_ai.command(name="model", aliases=["models", "engine"])
    async def ai_model(self, ctx: commands.Context, new_model: Optional[str] = None):
        """Xem hoặc đổi mô hình AI đang sử dụng (Chỉ Admin cấp cao được đổi)."""
        p = self._pfx()
        is_high_admin, _ = self._check_privilege(ctx.author.id)

        cur_model = _normalize_model_key(self.settings.get("current_model", DEFAULT_MODEL_KEY))
        cur_think = _normalize_think_key(self.settings.get("reasoning_level", DEFAULT_THINK_KEY))
        cur_info = AVAILABLE_MODELS[cur_model]

        # Nếu không truyền tên model mới -> Trả về ảnh Liquid Glass danh sách mô hình
        if not new_model:
            sent_msg = None
            if G is not None:
                try:
                    loop = asyncio.get_running_loop()
                    buf = await loop.run_in_executor(
                        None,
                        _render_ai_models_card,
                        p,
                        cur_model,
                        is_high_admin,
                        cur_think
                    )
                    file = discord.File(buf, filename="ai_models.png")
                    sent_msg = await autorep(
                        ctx.message,
                        content=f"🤖 **HỆ THỐNG MÔ HÌNH AI (LLM ENGINES)**\n*Mô hình đang hoạt động:* **{cur_info['name']}** (`{cur_model}`)",
                        file=file
                    )
                except Exception:
                    sent_msg = None

            if not sent_msg:
                lines = [
                    "🤖 **HỆ THỐNG MÔ HÌNH AI (LLM ENGINES)**",
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                    f"• **Mô hình hiện tại:** `{cur_model}` — **{cur_info['name']}**\n",
                    "📋 **DANH SÁCH MÔ HÌNH HOẠT ĐỘNG:**"
                ]
                for k, info in AVAILABLE_MODELS.items():
                    active_mark = " *(Đang dùng)* 👈" if k == cur_model else ""
                    creator_str = f" ({info.get('creator', '')})" if info.get('creator') else ""
                    lines.append(f"• `{p}ai model {k}` : **{info['name']}**{creator_str}{active_mark}\n  └ *{info['desc']}*")

                if is_high_admin:
                    lines.append(f"\n💡 *Admin cấp cao có thể gõ `{p}ai model <tên>` để đổi mô hình.*")
                else:
                    lines.append(f"\n🔒 *Chỉ Admin cấp cao (Chủ bot / Admintris) mới có quyền đổi mô hình.*")

                sent_msg = await autorep(ctx.message, "\n".join(lines))

            autodelet(sent_msg, delay=60)
            return

        # Yêu cầu quyền Admin cấp cao
        if not is_high_admin:
            msg = await autorep(ctx.message, "⛔ Lệnh đổi mô hình AI yêu cầu quyền **Admin cấp cao (admintris / chủ bot)**!")
            autodelet(msg, delay=15)
            return

        choice = new_model.strip().lower()
        if choice not in AVAILABLE_MODELS:
            avail_keys = ", ".join([f"`{k}`" for k in AVAILABLE_MODELS.keys()])
            msg = await autorep(
                ctx.message,
                f"❌ Bậc AI `{new_model}` không hợp lệ!\n"
                f"👉 Các bậc khả dụng: {avail_keys}\n"
                f"💡 Gõ `{p}ai model` để xem chi tiết danh sách."
            )
            autodelet(msg, delay=20)
            return

        # Lưu cài đặt mô hình mới
        self.settings["current_model"] = choice
        self._save_settings()

        target_info = AVAILABLE_MODELS[choice]
        msg = await autorep(
            ctx.message,
            f"✅ **ĐÃ ĐỔI BẬC DIPRE AI THÀNH CÔNG!**\n"
            f"• Bậc kích hoạt: **{target_info['name']}** (`{choice}`)\n"
            f"• Chi tiết: *{target_info['desc']}*\n"
            f"• Hệ thống: `{target_info['gateway_display']}`\n\n"
            f"👉 Mọi câu hỏi tiếp theo sẽ được xử lý bằng bậc này!"
        )
        autodelet(msg, delay=30)

    @cmd_ai.command(name="think", aliases=["reasoning", "suyluan", "effort"])
    async def ai_think(self, ctx: commands.Context, *, level: Optional[str] = None):
        """Xem (thẻ ảnh Liquid Glass) hoặc đổi cấp độ tư duy (low / medium / high)."""
        p = self._pfx()
        is_high_admin, _ = self._check_privilege(ctx.author.id)
        cur_think = _normalize_think_key(self.settings.get("reasoning_level", DEFAULT_THINK_KEY))
        cur_model = _normalize_model_key(self.settings.get("current_model", DEFAULT_MODEL_KEY))
        if not level:
            cur_lbl = REASONING_LEVELS[cur_think]["label"]
            sent_msg = None
            if G is not None:
                try:
                    loop = asyncio.get_running_loop()
                    buf = await loop.run_in_executor(
                        None,
                        _render_ai_think_card,
                        p,
                        cur_think,
                        is_high_admin,
                        cur_model,
                    )
                    file = discord.File(buf, filename="ai_think.png")
                    sent_msg = await autorep(
                        ctx.message,
                        content=f"⚙️ **CẤP ĐỘ TƯ DUY DIPRE AI**\n*Đang bật:* **{cur_lbl}** (`{cur_think}`)",
                        file=file,
                    )
                except Exception:
                    sent_msg = None
            if not sent_msg:
                sent_msg = await autorep(
                    ctx.message,
                    f"⚙️ **Cấp độ tư duy hiện tại:** `{cur_think}` ({cur_lbl})\n"
                    f"• `{p}ai think low` (hoặc `thấp`) : Thấp — ưu tiên tốc độ\n"
                    f"• `{p}ai think medium` (hoặc `trung bình`) : Trung bình — mặc định\n"
                    f"• `{p}ai think high` (hoặc `cao`) : Cao — phân tích kỹ"
                )
            autodelet(sent_msg, delay=60)
            return
        if not is_high_admin:
            msg = await autorep(ctx.message, "⛔ Lệnh đổi cấp độ tư duy yêu cầu quyền **Admin cấp cao**!")
            autodelet(msg, delay=15)
            return
        cleaned = re.sub(r"\s+", " ", level.strip().lower())
        valid_aliases = ("low", "fast", "nhanh", "thap", "thấp", "medium", "balanced", "tb", "trungbinh", "trung binh", "trung bình", "high", "deep", "sau", "sâu", "cao")
        if cleaned not in valid_aliases:
            msg = await autorep(ctx.message, f"❌ Cấp độ `{level}` không hợp lệ! Chọn `low`, `medium` hoặc `high` (hoặc `thấp` / `trung bình` / `cao`).")
            autodelet(msg, delay=15)
            return
        lv = _normalize_think_key(cleaned)
        self.settings["reasoning_level"] = lv
        self._save_settings()
        msg = await autorep(ctx.message, f"✅ **Đã chuyển cấp độ tư duy AI sang `{lv}` ({REASONING_LEVELS[lv]['label']})!**")
        autodelet(msg, delay=25)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.author:
            return

        bot_user = self.bot.user
        if not bot_user:
            return

        # TUYỆT ĐỐI KHÔNG REP CHÍNH MÌNH (Tránh vòng lặp vô tận self-reply)
        if message.author.id == bot_user.id:
            return

        # Bỏ qua tài khoản bot khác
        if getattr(message.author, "bot", False):
            return

        if not message.content:
            return

        pfx = self._pfx()
        if message.content.startswith(pfx):
            return

        # Chỉ phản hồi khi được TAG/MENTION trực tiếp (@bot)
        # KHÔNG tự rep khi người khác chỉ reply tin nhắn của bot (tránh spam)
        is_mentioned = bot_user in message.mentions
        if not is_mentioned:
            return

        guild_id = message.guild.id if message.guild else None
        sender_id = message.author.id

        if not self._can_respond_in_guild(guild_id, sender_id):
            return

        now = time.time()
        chan_id = message.channel.id
        # Anti-Ban Rate-Limit Guard: giãn cách tối thiểu 2.5s/kênh và tối đa 6 req/phút/người (10 ở DM)
        if chan_id in self._cooldowns and (now - self._cooldowns[chan_id]) < 2.5:
            return
        win = [ts for ts in self._user_rate_window[sender_id] if now - ts < 60.0]
        limit_per_min = 10 if guild_id is None else 6
        if len(win) >= limit_per_min:
            self._user_rate_window[sender_id] = win
            return
        win.append(now)
        self._user_rate_window[sender_id] = win
        self._cooldowns[chan_id] = now

        clean_content = message.content
        clean_content = re.sub(rf'<@!?{bot_user.id}>', '', clean_content).strip()
        if not clean_content:
            clean_content = "Chao cau! Cau vua goi to co chuyen gi do?"

        user_name = message.author.display_name or message.author.name
        await self._send_ai_reply(message, clean_content, user_name)


async def setup(bot: commands.Bot):
    await bot.add_cog(AICog(bot))
