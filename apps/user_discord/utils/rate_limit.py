# -*- coding: utf-8 -*-
"""
MODULE: rate_limit (Chong Spam Lenh & Tu Dong Khoa Vinh Vien)
- Admin / Admin cap cao (admintris) / Bot he thong Genesis: MIEN TRU TUYET DOI (Bypass 100%).
- Nguoi thuong spam lenh o server (bot ON/OFF/DM):
  * Qua 3 lenh / 5 giay hoac qua 7 lenh / 20 giay -> Khoa phat tam thoi.
  * Trong thoi gian bi khoa ma van co tinh spam -> Phat tang luy tien (1p -> 5p -> 30p -> 24h).
  * Vi pham nghiem trong / spam dai dang -> KHOA VINH VIEN (khong bao gio rep lai).
- Tat ca truong hop rate limit: CAM NIN TUYET DOI (Silent Drop, khong rep bat cu chu nao).
"""
from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
BLACKLIST_FILE = DATA_DIR / "rate_limit_blacklist.json"

# Nguong phat hien spam
WINDOW_SHORT_SEC = 5.0
MAX_CMDS_SHORT = 3

WINDOW_LONG_SEC = 20.0
MAX_CMDS_LONG = 7

# Thoi gian phat luy tien (giay)
PENALTY_TIERS = [
    60,        # 1 phut
    300,       # 5 phut
    1800,      # 30 phut
    86400,     # 24 gio
]
PERMANENT_STRIKES_THRESHOLD = 5  # Vi pham 5 lan -> Khoa vinh vien

# Bo nho tam thoi
_USER_HISTORY: Dict[int, deque] = defaultdict(lambda: deque(maxlen=20))
_USER_COOLDOWNS: Dict[int, float] = {}  # uid -> expire_timestamp
_USER_STRIKES: Dict[int, int] = defaultdict(int)
_PERMANENT_BLOCKED: set = set()


def _load_blacklist():
    global _PERMANENT_BLOCKED
    try:
        if BLACKLIST_FILE.exists():
            data = json.loads(BLACKLIST_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                _PERMANENT_BLOCKED = set(int(x) for x in data)
            elif isinstance(data, dict):
                _PERMANENT_BLOCKED = set(int(x) for x in data.get("permanent_blocked", []))
    except Exception:
        pass


def _save_blacklist():
    try:
        data = {
            "permanent_blocked": list(_PERMANENT_BLOCKED),
            "updated_at": time.time(),
        }
        BLACKLIST_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


_load_blacklist()


def is_privileged_user(bot: Any, user_id: int) -> bool:
    """True neu user la Admin, Admin cap cao, hoac Bot noi bo Genesis -> Khong bao gio bi rate limit."""
    try:
        uid = int(user_id)
        # 1. Chinh la bot dang chay
        bot_user = getattr(bot, "user", None)
        if bot_user and int(getattr(bot_user, "id", 0)) == uid:
            return True

        # 2. Bot noi bo Genesis (prime hoac shard)
        try:
            from apps.user_discord.core.bot_sys import is_internal_bot
        except ImportError:
            from core.bot_sys import is_internal_bot  # type: ignore
        if is_internal_bot(uid):
            return True

        # 3. Staff (Admin / Admin cap cao / Owner)
        try:
            from apps.user_discord.core.bot_sys import is_staff, is_mod
        except ImportError:
            from core.bot_sys import is_staff, is_mod  # type: ignore

        if is_mod(bot, uid) or is_staff(bot, uid):
            return True

        # Fallback check qua bot method neu co
        if hasattr(bot, "is_staff") and callable(bot.is_staff) and bot.is_staff(uid):
            return True

    except Exception:
        pass
    return False


def is_rate_limited(bot: Any, message: Any) -> bool:
    """
    Kiem tra tin nhan co phai lenh va nguoi dung co dang bi rate limit hay khong.
    Tra ve:
      True  -> BI RATE LIMIT (DROP tin nhan, khong xu ly, khong rep).
      False -> HOP LE (Cho phep chay binh thuong).
    """
    try:
        author = getattr(message, "author", None)
        if not author:
            return False
        uid = getattr(author, "id", None)
        if not uid:
            return False
        uid = int(uid)

        # 1. Nhom dac quyen: Mien tru 100%
        if is_privileged_user(bot, uid):
            return False

        now = time.time()

        # 2. Da bi khoa VINH VIEN
        if uid in _PERMANENT_BLOCKED:
            return True

        # 3. Kiem tra xem co phai la tin nhan goi LENH hay khong
        content = str(getattr(message, "content", "") or "").strip()
        if not content:
            return False

        is_cmd = False
        try:
            from apps.user_discord.utils.prefix import get_prefixes
        except ImportError:
            from utils.prefix import get_prefixes  # type: ignore

        for p in get_prefixes(bot):
            p_c = str(p or "").rstrip().lower()
            if not p_c:
                continue
            for pm in [p_c, f"{p_c} "]:
                if content.lower().startswith(pm):
                    is_cmd = True
                    break
            if is_cmd:
                break

        # Neu khong phai lenh -> khong can tinh rate limit lenh
        if not is_cmd:
            return False

        # 4. Dang trong thoi gian bi phat tam thoi
        cd_expire = _USER_COOLDOWNS.get(uid, 0)
        if now < cd_expire:
            # Tiep tuc spam trong luc bi phat -> Tang strike va gia han phat!
            _USER_STRIKES[uid] += 1
            strikes = _USER_STRIKES[uid]

            if strikes >= PERMANENT_STRIKES_THRESHOLD:
                _PERMANENT_BLOCKED.add(uid)
                _save_blacklist()
                print(f"[RATE-LIMIT] ⛔ Nguoi dung {uid} ({getattr(author, 'name', '')}) da bi KHOA VINH VIEN do co tinh spam dai dang!")
                return True

            tier_idx = min(strikes - 1, len(PENALTY_TIERS) - 1)
            penalty_time = PENALTY_TIERS[tier_idx]
            _USER_COOLDOWNS[uid] = now + penalty_time
            return True

        # 5. Kiem tra tan suat su dung (Sliding window)
        history = _USER_HISTORY[uid]
        history.append(now)

        # Kiem tra trong WINDOW_SHORT
        recent_short = sum(1 for t in history if now - t <= WINDOW_SHORT_SEC)
        recent_long = sum(1 for t in history if now - t <= WINDOW_LONG_SEC)

        if recent_short > MAX_CMDS_SHORT or recent_long > MAX_CMDS_LONG:
            _USER_STRIKES[uid] += 1
            strikes = _USER_STRIKES[uid]

            if strikes >= PERMANENT_STRIKES_THRESHOLD:
                _PERMANENT_BLOCKED.add(uid)
                _save_blacklist()
                print(f"[RATE-LIMIT] ⛔ Nguoi dung {uid} ({getattr(author, 'name', '')}) da bi KHOA VINH VIEN do spam qua nhieu lan!")
                return True

            tier_idx = min(strikes - 1, len(PENALTY_TIERS) - 1)
            penalty_time = PENALTY_TIERS[tier_idx]
            _USER_COOLDOWNS[uid] = now + penalty_time

            mins = penalty_time // 60
            secs = penalty_time % 60
            dur_str = f"{mins}p{secs}s" if mins else f"{secs}s"
            print(f"[RATE-LIMIT] ⚠️ Nguoi dung {uid} ({getattr(author, 'name', '')}) bi phat CAM NIN trong {dur_str} (Vi pham #{strikes}).")
            return True

    except Exception:
        pass

    return False


def unban_user(user_id: int) -> bool:
    """Go khoa rate limit cho 1 nguoi dung."""
    try:
        uid = int(user_id)
        changed = False
        if uid in _PERMANENT_BLOCKED:
            _PERMANENT_BLOCKED.discard(uid)
            _save_blacklist()
            changed = True
        if uid in _USER_COOLDOWNS:
            del _USER_COOLDOWNS[uid]
            changed = True
        if uid in _USER_STRIKES:
            del _USER_STRIKES[uid]
            changed = True
        if uid in _USER_HISTORY:
            del _USER_HISTORY[uid]
            changed = True
        return changed
    except Exception:
        return False
