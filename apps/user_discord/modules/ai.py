# -*- coding: utf-8 -*-
"""
MODULE: ai (AI Smart Chatbot & Assistant)
- Tro chuyen thong minh khong can API key (Qwen 3.8 27B / Free Gateway Pool).
- Tinh cach nhi nhanh, lem linh, dang yeu, thong minh.
- RAG user context: Nhận diện danh tính người chat để xưng hô thân mật.
- Huong dan dang anh Help Card + Status dang anh Liquid Glass.
- Tu dong xoa tin nhan bot qua autodelet.
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

LLMTECH_GATEWAY_URL = "https://api.llmtech.eu/v1/chat/completions"
LLMTECH_MODEL = "nvidia/Qwen3.8-27B-NVFP4"
LLMTECH_PUBLIC_KEY = "lt-trial-ba1ef28c6d32ed6980678d8d"

KILO_GATEWAY_URL = "https://api.kilo.ai/api/gateway/chat/completions"

# Danh bạ các AI Models được hỗ trợ (miễn phí, đã test hoạt động):
AVAILABLE_MODELS: Dict[str, Dict[str, Any]] = {
    "qwen": {
        "name": "Qwen 3.8 27B",
        "creator": "Alibaba Cloud / Qwen",
        "brand_color": (168, 85, 247),
        "gateway_display": "LLMTECH EU",
        "desc": "Mô hình siêu thông minh, suy luận sâu, phản hồi sắc bén (Mặc định).",
        "gateway": "llmtech",
        "endpoint": LLMTECH_GATEWAY_URL,
        "model_id": "nvidia/Qwen3.8-27B-NVFP4",
        "headers": {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLMTECH_PUBLIC_KEY}",
            "User-Agent": "Mozilla/5.0",
        },
    },
    "nemotron": {
        "name": "NVIDIA Nemotron 3.5",
        "creator": "NVIDIA Corp",
        "brand_color": (118, 185, 0),
        "gateway_display": "KILO GATEWAY",
        "desc": "Tối ưu siêu tốc độ do NVIDIA phát triển, cực nhạy bén.",
        "gateway": "kilo",
        "endpoint": KILO_GATEWAY_URL,
        "model_id": "nvidia/nemotron-3.5-lightning:free",
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    },
    "dots": {
        "name": "Dots 3 Studio",
        "creator": "Dots Studio (Rednote)",
        "brand_color": (255, 45, 85),
        "gateway_display": "KILO GATEWAY",
        "desc": "Mô hình đàm thoại cảm xúc, tự nhiên, gần gũi, hóm hỉnh.",
        "gateway": "kilo",
        "endpoint": KILO_GATEWAY_URL,
        "model_id": "dots-studio/dots-3-note-preview:free",
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    },
    "openrouter": {
        "name": "OpenRouter Free Cluster",
        "creator": "OpenRouter AI",
        "brand_color": (56, 189, 248),
        "gateway_display": "KILO GATEWAY",
        "desc": "Cụm mô hình đa năng tối ưu thông minh của OpenRouter.",
        "gateway": "kilo",
        "endpoint": KILO_GATEWAY_URL,
        "model_id": "openrouter/free",
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    },
    "cohere": {
        "name": "Cohere North Mini",
        "creator": "Cohere AI",
        "brand_color": (218, 119, 86),
        "gateway_display": "KILO GATEWAY",
        "desc": "Mô hình logic sắc sảo chuyên xử lý văn bản và lập trình.",
        "gateway": "kilo",
        "endpoint": KILO_GATEWAY_URL,
        "model_id": "cohere/north-mini-code:free",
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    },
}

DEFAULT_MODEL_KEY = "qwen"


def _draw_brand_vector_logo(brand_key: str, size: int = 128):
    """Vẽ logo vector SVG hi-res siêu nét (supersampled 4x) của từng hãng sản xuất AI."""
    from PIL import Image, ImageDraw
    import math

    canvas_size = size * 4
    im = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    brand = brand_key.lower()
    cx, cy = canvas_size / 2, canvas_size / 2
    r = canvas_size * 0.44

    if brand in ("qwen", "alibaba"):
        # Logo Alibaba / Qwen: Khối lập phương lăng kính 3D (Faceted Hexagon / Prism)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(26, 16, 50, 245))
        pts = []
        for i in range(6):
            angle = math.radians(60 * i - 30)
            pts.append((cx + r * 0.78 * math.cos(angle), cy + r * 0.78 * math.sin(angle)))

        d.polygon([cx, cy, pts[5], pts[0], pts[1]], fill=(168, 85, 247, 255))
        d.polygon([cx, cy, pts[1], pts[2], pts[3]], fill=(59, 130, 246, 255))
        d.polygon([cx, cy, pts[3], pts[4], pts[5]], fill=(14, 165, 233, 255))

        d.line([pts[0], pts[1], pts[2], pts[3], pts[4], pts[5], pts[0]], fill=(255, 255, 255, 210), width=int(canvas_size * 0.025))
        d.line([cx, cy, pts[1][0], pts[1][1]], fill=(255, 255, 255, 230), width=int(canvas_size * 0.02))
        d.line([cx, cy, pts[3][0], pts[3][1]], fill=(255, 255, 255, 230), width=int(canvas_size * 0.02))
        d.line([cx, cy, pts[5][0], pts[5][1]], fill=(255, 255, 255, 230), width=int(canvas_size * 0.02))
        cr = canvas_size * 0.06
        d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(255, 255, 255, 245))

    elif brand in ("nemotron", "nvidia"):
        # Logo NVIDIA: Mắt rồng xoắn ốc xanh lá đặc trưng
        nv_green = (118, 185, 0, 255)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(15, 24, 12, 245))

        box_out = [cx - r * 0.8, cy - r * 0.65, cx + r * 0.8, cy + r * 0.75]
        d.arc(box_out, start=180, end=360, fill=nv_green, width=int(canvas_size * 0.08))
        d.line([cx - r * 0.8, cy + r * 0.05, cx + r * 0.8, cy + r * 0.05], fill=nv_green, width=int(canvas_size * 0.08))

        box_mid = [cx - r * 0.52, cy - r * 0.42, cx + r * 0.52, cy + r * 0.52]
        d.arc(box_mid, start=180, end=360, fill=(255, 255, 255, 255), width=int(canvas_size * 0.06))
        d.line([cx - r * 0.52, cy + r * 0.05, cx + r * 0.52, cy + r * 0.05], fill=(255, 255, 255, 255), width=int(canvas_size * 0.06))

        d.ellipse([cx - r * 0.22, cy - r * 0.1, cx + r * 0.22, cy + r * 0.22], fill=nv_green)

    elif brand in ("dots", "dots-studio"):
        # Logo Dots Studio: 3 chấm tròn neon liên kết năng động
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(34, 15, 22, 245))
        p1 = (cx, cy - r * 0.48)
        p2 = (cx - r * 0.48, cy + r * 0.38)
        p3 = (cx + r * 0.48, cy + r * 0.38)

        d.line([p1, p2], fill=(255, 45, 85, 180), width=int(canvas_size * 0.04))
        d.line([p2, p3], fill=(255, 45, 85, 180), width=int(canvas_size * 0.04))
        d.line([p3, p1], fill=(255, 45, 85, 180), width=int(canvas_size * 0.04))

        for pt, col in [(p1, (255, 45, 85)), (p2, (255, 107, 107)), (p3, (255, 159, 67))]:
            dot_r = canvas_size * 0.13
            d.ellipse([pt[0] - dot_r, pt[1] - dot_r, pt[0] + dot_r, pt[1] + dot_r], fill=col + (255,))
            inner_r = canvas_size * 0.05
            d.ellipse([pt[0] - inner_r, pt[1] - inner_r, pt[0] + inner_r, pt[1] + inner_r], fill=(255, 255, 255, 240))

    elif brand in ("openrouter",):
        # Logo OpenRouter: Mạng lưới rẽ nhánh Router đa kênh
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(12, 24, 38, 245))
        nr = canvas_size * 0.11
        d.ellipse([cx - nr, cy - nr, cx + nr, cy + nr], fill=(56, 189, 248, 255))
        d.ellipse([cx - nr * 0.4, cy - nr * 0.4, cx + nr * 0.4, cy + nr * 0.4], fill=(255, 255, 255, 240))

        nodes = [
            (cx - r * 0.62, cy - r * 0.5),
            (cx + r * 0.62, cy - r * 0.5),
            (cx - r * 0.62, cy + r * 0.5),
            (cx + r * 0.62, cy + r * 0.5),
        ]
        for nx, ny in nodes:
            d.line([(cx, cy), (nx, ny)], fill=(56, 189, 248, 200), width=int(canvas_size * 0.04))
            sub_r = canvas_size * 0.075
            d.ellipse([nx - sub_r, ny - sub_r, nx + sub_r, ny + sub_r], fill=(14, 165, 233, 255))
            d.ellipse([nx - sub_r * 0.4, ny - sub_r * 0.4, nx + sub_r * 0.4, ny + sub_r * 0.4], fill=(255, 255, 255, 255))

    elif brand in ("cohere",):
        # Logo Cohere: Khối tế bào / organic shape san hô ấm áp
        coral = (218, 119, 86, 255)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(36, 22, 18, 245))

        w_box = r * 0.72
        h_box = r * 0.55
        d.rounded_rectangle([cx - w_box, cy - h_box, cx + w_box, cy + h_box], radius=int(h_box * 0.9), fill=coral)
        cut_w = w_box * 0.5
        cut_h = h_box * 0.5
        d.ellipse([cx - cut_w * 0.5, cy - cut_h, cx + cut_w * 1.2, cy + cut_h], fill=(36, 22, 18, 255))
        d.ellipse([cx - w_box * 0.35, cy - h_box * 0.25, cx + w_box * 0.1, cy + h_box * 0.25], fill=(255, 220, 200, 255))

    else:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(30, 41, 59, 245))
        d.rounded_rectangle([cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5], radius=int(r * 0.15), fill=(99, 102, 241, 255))

    return im.resize((size, size), Image.Resampling.LANCZOS)


def _render_ai_models_card(pfx: str, current_model: str, is_high_admin: bool) -> io.BytesIO:
    """Vẽ ảnh Liquid Glass danh sách các mô hình AI với logo SVG thương hiệu chính hãng."""
    if G is None:
        raise RuntimeError("G (glass.py) is not available")

    cv = G.GlassCanvas(860, 680, scale=2, out=1.25, dim=85)

    # 1. Header
    cv.header(
        20, 20, 840, 72,
        "AI INTELLIGENCE MODELS",
        "Hệ thống mô hình trí tuệ nhân tạo (Hỗ trợ chuyển đổi tức thì)",
        tag="LLM GATEWAY",
        tag_grad=((139, 92, 246), (236, 72, 153))
    )

    y = 106
    f_name = cv.font("b", 16)
    f_creator = cv.font("b", 10.5)
    f_cmd = cv.font("b", 12)
    f_desc = cv.font("r", 11.5)
    f_badge = cv.font("b", 10)

    cur_key = current_model.lower()

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
    f_bar_y = 590
    cv.bar(20, f_bar_y, 840, f_bar_y + 68, r=16)
    f_ft1 = cv.font("b", 12.5)
    f_ft2 = cv.font("r", 11)
    if is_high_admin:
        cv.text(38, f_bar_y + 24, f"💡 Hướng dẫn: Bạn là Admin cấp cao, gõ  {pfx}ai model <tên_model>  để đổi mô hình ngay.", f_ft1, (255, 255, 255), vcenter=True)
    else:
        cv.text(38, f_bar_y + 24, f"💡 Hướng dẫn: Gõ  {pfx}ai <câu_hỏi>  để trò chuyện trực tiếp cùng trợ lý ảo.", f_ft1, (255, 255, 255), vcenter=True)
    cv.text(38, f_bar_y + 48, "🔒 Bảo mật: Quyền thay đổi mô hình được giới hạn cho Admintris & Chủ sở hữu hệ thống.", f_ft2, (180, 195, 215), vcenter=True)

    return cv.finalize(format="PNG")


def _call_llm_gateway(messages: List[Dict[str, str]], max_tokens: int = 700, model_key: str = DEFAULT_MODEL_KEY) -> Optional[str]:
    # 1. Thử gọi model được chỉ định
    target_info = AVAILABLE_MODELS.get(model_key.lower()) or AVAILABLE_MODELS[DEFAULT_MODEL_KEY]
    candidate_list = [target_info]
    # 2. Thêm các model dự phòng nếu model chính bị nghẽn
    for k, v in AVAILABLE_MODELS.items():
        if k != model_key.lower():
            candidate_list.append(v)

    for item in candidate_list:
        try:
            req_payload = {
                "model": item["model_id"],
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.75,
            }
            req = urllib.request.Request(
                item["endpoint"],
                data=json.dumps(req_payload).encode("utf-8"),
                headers=item["headers"],
            )
            with urllib.request.urlopen(req, timeout=12.0, context=SSL_CTX) as resp:
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

    def _build_system_prompt(self, user_name: str, guild_name: Optional[str] = None) -> str:
        bot_user = getattr(self.bot, "user", None) if self.bot else None
        bot_name = getattr(bot_user, "name", "AI") if bot_user else "AI"
        g_info = f"tại máy chủ '{guild_name}'" if guild_name else "trong tin nhắn riêng"
        return (
            f"Bạn là {bot_name} - một người bạn thật đang trò chuyện trên Discord {g_info}.\n"
            f"Bạn đang nói chuyện trực tiếp với '{user_name}'.\n\n"
            f"PHONG CÁCH GIAO TIẾP (CHUẨN NGƯỜI THẬT MIỀN BẮC THỜI NAY, TỰ NHIÊN, HÓM HỈNH):\n"
            f"1. Nhắn tin tự nhiên hệt như một người bạn trẻ Hà Nội / miền Bắc ngoài đời thực đang chat trên mạng: thông minh, hoạt ngôn, dí dỏm, phản xạ nhanh, ngắn gọn và thực tế.\n"
            f"2. Xưng hô thân mật, linh hoạt: xưng 'tôi' / 'tớ', gọi đối phương là 'ông', 'bà', 'cậu', hoặc gọi thẳng tên '{user_name}'. Tuyệt đối KHÔNG xưng hô kiểu bot/trợ lý khách sáo ('tôi là trợ lý', 'rất vui được hỗ trợ').\n"
            f"3. Dùng ngữ điệu và từ đệm đặc trưng của miền Bắc một cách tự nhiên: 'nhé', 'nhá', 'thế á', 'chuẩn luôn', 'đấy', 'chứ', 'nhỉ', 'xem nào', 'được của nó đấy', 'chán chả buồn nói', 'lại còn thế nữa', 'gớm', 'đùa chứ', 'thật đấy'...\n"
            f"4. TUYỆT ĐỐI KHÔNG dùng từ ngữ miền Nam (CẤM: 'nè', 'nha', 'nghen', 'tui', 'hén').\n"
            f"5. Câu trả lời thường súc tích, đi thẳng vào trọng tâm từ 1 đến 3 câu, trừ khi đối phương yêu cầu phân tích dài hoặc viết code.\n\n"
            f"QUY TẮC BỘ NHỚ VÀ XỬ LÝ TRÒ CHƠI / NGỮ CẢNH (RẤT QUAN TRỌNG):\n"
            f"1. Luôn theo sát dòng thời gian và ngữ cảnh lịch sử trò chuyện phía trước. Không bao giờ được quên mạch chuyện đối phương đang nói.\n"
            f"2. NẾU ĐANG CHƠI TRÒ NỐI TỪ TIẾNG VIỆT:\n"
            f"   - Phải tiếp tục luật chơi nối từ ngay lập tức mà không cần nhắc lại luật!\n"
            f"   - LUẬT NỐI TỪ: Mỗi lượt đi BẮT BUỘC là MỘT TỪ GHÉP / CỤM TỪ 2 TIẾNG CÓ NGHĨA trong tiếng Việt. Tiếng đầu của bạn PHẢI trùng với tiếng cuối cùng của từ đối phương vừa đưa ra.\n"
            f"   - VÍ DỤ: Đối phương đưa 'biến số' -> bạn PHẢI nối một từ ghép 2 tiếng như 'số phận', 'số lượng', 'số má', 'số liệu', 'số học'... CẤM TUYỆT ĐỐI CHỈ TRẢ VỀ 1 TIẾNG ĐƠN LẺ NHƯ 'số'!\n"
            f"   - Khi đối phương đưa tiếp từ 2 tiếng (ví dụ: 'phận đời'), bạn lập tức nối tiếp từ 2 tiếng bắt đầu bằng 'đời' (ví dụ: 'đời sống', 'đời người'). Có thể kèm 1 câu ngắn vui chuẩn vibe miền Bắc.\n"
            f"3. NẾU ĐANG CHƠI ĐỐ VUI, GIẢI ĐỐ HOẶC TRÒ CHUYỆN LIÊN TỤC: Khi đối phương gửi câu trả lời ngắn (1-2 từ), hãy hiểu ngay đó là đáp án hoặc lượt tiếp theo trong trò chơi đang diễn ra."
        )

    async def _send_ai_reply(self, target_msg: discord.Message, prompt_text: str, user_name: str):
        channel = target_msg.channel
        chan_id = channel.id

        try:
            async with channel.typing():
                clean_name = re.sub(r'[^a-zA-Z0-9_\-\s]', '', user_name).strip()[:30] or "User"
                sys_prompt = self._build_system_prompt(
                    user_name=clean_name,
                    guild_name=target_msg.guild.name if target_msg.guild else None
                )
                messages: List[Dict[str, str]] = [{"role": "system", "content": sys_prompt}]

                recent_hist = self.memory.get(chan_id)
                for h in recent_hist:
                    messages.append({"role": h["role"], "content": h["content"]})

                user_msg_content = f"{clean_name}: {prompt_text}"
                messages.append({"role": "user", "content": user_msg_content})

                cur_model = self.settings.get("current_model", DEFAULT_MODEL_KEY)
                reply_text = await asyncio.to_thread(_call_llm_gateway, messages, 700, cur_model)

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

        cv.header(
            pad, pad, LW - pad, head_h,
            "AI CHATBOT MONITOR PANEL",
            f"Prefix  {pfx}   •   Engine: Qwen 3.8 27B NVFP4   •   {len(on_guilds)} Active Server(s)",
            tag="AI STATUS",
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

            cur_model = self.settings.get("current_model", DEFAULT_MODEL_KEY)
            cur_info = AVAILABLE_MODELS.get(cur_model, AVAILABLE_MODELS[DEFAULT_MODEL_KEY])
            guide = (
                f"✨ **TRỢ LÝ AI THÔNG MINH - HƯỚNG DẪN SỬ DỤNG** ✨\n\n"
                f"• `{p}ai <câu hỏi>` : Đặt câu hỏi trực tiếp cho AI.\n"
                f"• `{p}ai model` : Xem danh sách & đổi mô hình AI (Admin cấp cao).\n"
                f"• `{p}ai clear` : Xoá sạch trí nhớ lịch sử chat tại kênh này.\n"
                f"• `{p}ai on` : Bật AI tự động tại server này (Admin only).\n"
                f"• `{p}ai off` : Tắt AI tự động tại server này (Admin only).\n"
                f"• `{p}ai status` : Xem trạng thái & server đang bật AI.\n"
                f"• **Tag @bot** : Khi AI bật tại server, chỉ cần tag bot (@bot) là AI rep ngay!\n\n"
                f"📌 **Trạng thái:** {ai_status}   |   **Mô hình đang chạy:** `{cur_model}` ({cur_info['name']})"
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

        cur_model = self.settings.get("current_model", DEFAULT_MODEL_KEY)
        cur_info = AVAILABLE_MODELS.get(cur_model, AVAILABLE_MODELS[DEFAULT_MODEL_KEY])

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
                        is_high_admin
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
                f"❌ Mô hình `{new_model}` không hợp lệ hoặc hiện chưa được hỗ trợ!\n"
                f"👉 Các mô hình có sẵn: {avail_keys}\n"
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
            f"✅ **ĐÃ ĐỔI MÔ HÌNH AI THÀNH CÔNG!**\n"
            f"• Mô hình kích hoạt: **{target_info['name']}** (`{choice}`)\n"
            f"• Chi tiết: *{target_info['desc']}*\n"
            f"• Cổng Gateway: `{target_info['gateway'].upper()}` (`{target_info['model_id']}`)\n\n"
            f"👉 Mọi câu hỏi tiếp theo sẽ được xử lý bằng mô hình này!"
        )
        autodelet(msg, delay=30)

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
        if chan_id in self._cooldowns and (now - self._cooldowns[chan_id]) < 1.5:
            return
        self._cooldowns[chan_id] = now

        clean_content = message.content
        clean_content = re.sub(rf'<@!?{bot_user.id}>', '', clean_content).strip()
        if not clean_content:
            clean_content = "Chao cau! Cau vua goi to co chuyen gi do?"

        user_name = message.author.display_name or message.author.name
        await self._send_ai_reply(message, clean_content, user_name)


async def setup(bot: commands.Bot):
    await bot.add_cog(AICog(bot))
