"""
card_registry.py
----
Registry trung gian: moi module (alias, voice, del, rpc...) tu khai bao
schema help-card cua minh tai day.

media_card.py chi la RENDER ENGINE -- no import PLATFORM_CONFIG tu day,
khong tu chua bat ky dinh nghia lenh nao.

Cach module khac khai bao:
    from apps.user_discord.utils.card_registry import register_card, CardSchema

    register_card("voice", CardSchema(
        title="VOICE 24/7 & AUTO-KEEPER",
        sub="...",
        accent=(74, 222, 128),
        logo_fn=draw_voice_logo_hires,
        tip="...",
        items=[
            ("voice join [id|link]", "Mo ta", "JOIN 24/7"),
        ]
    ))
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple, Any, Dict


@dataclass
class CardSchema:
    """Schema day du cho 1 help-card. Moi module khai bao 1 instance nay."""
    title: str
    sub: str
    accent: Tuple[int, int, int]
    logo_fn: Optional[Callable]
    items: List[Tuple[str, str, str]]
    tip: str = "Meo: Dung dung prefix truoc moi lenh."
    accent_rgba: Optional[Tuple[int, int, int, int]] = None
    accent_bg: Optional[Tuple[int, int, int, int]] = None

    def __post_init__(self):
        if self.accent_rgba is None:
            self.accent_rgba = (*self.accent, 255)
        if self.accent_bg is None:
            self.accent_bg = (*self.accent, 25)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title":       self.title,
            "sub":         self.sub,
            "accent":      self.accent,
            "accent_rgba": self.accent_rgba,
            "accent_bg":   self.accent_bg,
            "logo_fn":     self.logo_fn,
            "tip":         self.tip,
            "items":       self.items,
        }


_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_card(key: str, schema) -> None:
    """Dang ky hoac cap nhat schema cho key (ten lenh / alias)."""
    if isinstance(schema, CardSchema):
        _REGISTRY[key] = schema.to_dict()
    else:
        _REGISTRY[key] = dict(schema)


def get_card(key: str) -> Optional[Dict[str, Any]]:
    """Tra ve schema dict cho key, hoac None neu chua dang ky."""
    return _REGISTRY.get(key)


def get_registry() -> Dict[str, Dict[str, Any]]:
    """Tra ve toan bo registry."""
    return _REGISTRY


def all_keys() -> List[str]:
    return list(_REGISTRY.keys())


def _bootstrap() -> None:
    try:
        from apps.user_discord.utils import default_cards as _dc  # noqa
    except ImportError:
        try:
            from utils import default_cards as _dc  # type: ignore  # noqa
        except ImportError:
            pass


_bootstrap()
