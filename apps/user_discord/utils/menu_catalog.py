"""
Nội dung menu GUI (`(prefix)menu`) — apps/user_discord.

Khai báo MỤC MENU NGAY TRÊN CHÍNH LỆNH đó (module/core), không đụng menu.py:
    from apps.user_discord.utils.menu_catalog import menu_entry

    @menu_entry("MEDIA & ENTERTAINMENT", "yt", "Phát Voice & tải video/nhạc YouTube",
                icon_sym="▶", icon_color=(255, 85, 85), order=1)
    @commands.group(name="youtube", aliases=["yt"], invoke_without_command=True)
    async def cmd_youtube(self, ctx, *, query=None): ...

- Thêm lệnh MỚI -> thêm đúng 1 cụm @menu_entry trên lệnh -> menu tự lượm.
- Sửa desc/icon/badge -> sửa ngay dòng đó, reload cog là thấy.
- Lệnh không có @menu_entry -> KHÔNG hiện trong menu (chủ động khai báo).

Fallback hiếm dùng: MENU_GROUPS tĩnh hoặc gọi `register_menu_item(...)` lúc setup().

Item dict sau chuẩn hóa bởi build_menu_groups():
    {name: "{pfx}yt", desc, badge, icon_sym, icon_color}   (desc <= 46 ký tự)
"""
from __future__ import annotations

from typing import Any, Dict, List

DEFAULT_ICON_COLOR = (220, 225, 235)

# ── Thứ tự category cố định (category lạ -> append sau) ──────────────────────
CATEGORY_ORDER: List[str] = [
    "MEDIA & ENTERTAINMENT",
    "AUTOMATION & QUEST",
    "SYSTEM & SECURITY",
]

# ── Khai báo tĩnh fallback (chủ yếu dùng @menu_entry ngay trên lệnh) ────────
MENU_GROUPS: List[Dict[str, Any]] = []

# ── Đăng ký động: @menu_entry() lúc import module + register_menu_item() ────
_PENDING: Dict[str, List[Dict[str, Any]]] = {}


def register_menu_item(category: str, item: Dict[str, Any]) -> None:
    """Đăng ký 1 dòng menu. Idempotent theo name: trùng name -> cập nhật bản mới."""
    name = str(item.get("name", ""))
    bucket = _PENDING.setdefault(category, [])
    for i, existing in enumerate(bucket):
        if str(existing.get("name", "")) == name:
            bucket[i] = dict(item)
            return
    bucket.append(dict(item))


def menu_entry(category: str, name: str, desc: str, *, badge=None,
               icon_sym: str = "•", icon_color=None, order: int = 99):
    """
    Decorator khai báo mục menu NGAY TRÊN LỆNH đó (dùng trực tiếp ở module/core).
    Chạy lúc import file -> menu tự lượm về, không cần sửa file này.
    order: số nhỏ hiện trước trong category (mặc định 99 -> append cuối).
    """
    def decorator(obj):
        register_menu_item(category, {
            "name": "{pfx}" + str(name),
            "desc": desc,
            "badge": badge,
            "icon_sym": icon_sym,
            "icon_color": tuple(icon_color) if icon_color else DEFAULT_ICON_COLOR,
            "order": int(order),
        })
        return obj  # trả lại object gốc -> xếp chồng thoải mái với @commands.*

    return decorator


def _norm_item(raw: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    """Chuẩn hóa item + thay {pfx}; thiếu field -> mặc định an toàn."""
    return {
        "name": str(raw.get("name", "")).replace("{pfx}", prefix),
        "desc": str(raw.get("desc", "")),
        "badge": raw.get("badge"),
        "icon_sym": str(raw.get("icon_sym") or "•"),
        "icon_color": tuple(raw.get("icon_color") or DEFAULT_ICON_COLOR),
    }


def build_menu_groups(prefix: str = "!") -> List[Dict[str, Any]]:
    """Gộp MENU_GROUPS + @menu_entry/register, trả về list SAO CHÉP sẵn cho render."""
    merged: Dict[str, List[Dict[str, Any]]] = {}

    # 1. Fallback tĩnh trước (nếu có)
    for grp in MENU_GROUPS:
        cat = str(grp.get("category", ""))
        merged.setdefault(cat, []).extend(dict(it) for it in grp.get("items", []))

    # 2. Đăng ký từ @menu_entry / register_menu_item (trùng name -> bỏ bản sau)
    for cat, items in _PENDING.items():
        bucket = merged.setdefault(cat, [])
        for it in items:
            name = str(it.get("name", ""))
            if any(str(e.get("name", "")) == name for e in bucket):
                continue
            bucket.append(dict(it))

    # 3. Category theo CATEGORY_ORDER (category lạ append sau), item theo order
    cats = [c for c in CATEGORY_ORDER if c in merged]
    cats += [c for c in merged if c not in cats]

    return [
        {
            "category": cat,
            "items": [
                _norm_item(it, prefix)
                for it in sorted(merged[cat], key=lambda x: int(x.get("order", 99)))
            ],
        }
        for cat in cats
    ]


# ── Extension loader hook cho main.py (load MỌI file .py trong utils/ làm extension) ──
async def setup(bot):
    """Không làm gì — menu_catalog là module dữ liệu/decorator, không có cog."""
    pass

