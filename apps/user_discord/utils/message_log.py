# -*- coding: utf-8 -*-
"""Bo loc log tin nhan user_discord chong tran console (1 log chung).

Chi log dung 5 loai:
  1. TAG   - NGUOI KHAC tag 1 acc co trong config.json
             (@mention / @everyone / @here / reply toi UID token).
  2. SV-ON - tin nhan o server co bot ON.
  3. BOT   - tin nhan do acc trong config gui.
  4. DM    - tin nhan rieng (khong o server nao).
  5. STAFF - tin cua admin / admin cap cao o server co bot (ke ca bot OFF).

Bot tu tag nhau -> CUT, khong log.
"""

from __future__ import annotations

from typing import Any, Optional, Set, Tuple

_TOKEN_UIDS_CACHE: Set[int] = set()


def _all_config_uids(bot: Any = None) -> Set[int]:
    """UID cua TAT CA acc co trong config.json (prime + shard + bot dang chay)."""
    global _TOKEN_UIDS_CACHE
    uids: Set[int] = set(_TOKEN_UIDS_CACHE)
    if bot is not None:
        try:
            user = getattr(bot, "user", None)
            uid = getattr(user, "id", None)
            if uid is not None:
                uids.add(int(uid))
        except Exception:
            pass
    try:
        try:
            from apps.user_discord.core.bot_sys import get_all_shard_uids
        except ImportError:
            from core.bot_sys import get_all_shard_uids  # type: ignore
        for u in (get_all_shard_uids() or set()):
            try:
                uids.add(int(u))
            except Exception:
                continue
    except Exception:
        pass
    _TOKEN_UIDS_CACHE = set(uids)
    return uids


def _author_id(message: Any) -> Optional[int]:
    try:
        author = getattr(message, "author", None)
        if author is None:
            return None
        return int(getattr(author, "id", -1))
    except Exception:
        return None


def _is_own_message(bot: Any, message: Any) -> bool:
    """Tin do 1 acc trong config gui."""
    try:
        aid = _author_id(message)
        if aid is None:
            return False
        return aid in _all_config_uids(bot)
    except Exception:
        return False


def _mentions_me(bot: Any, message: Any) -> bool:
    """NGUOI KHAC tag 1 acc trong config: @mention / @everyone / @here / reply."""
    try:
        config_uids = _all_config_uids(bot)
        # Bot tu tag nhau -> CUT ngay.
        aid = _author_id(message)
        if aid is not None and aid in config_uids:
            return False
        # @everyone / @here -> log luon (nguoi khac ping ca kenh).
        try:
            if bool(getattr(message, "mention_everyone", False)):
                return True
        except Exception:
            pass
        if not config_uids:
            return False
        for u in (getattr(message, "mentions", None) or []):
            try:
                if int(getattr(u, "id", -1)) in config_uids:
                    return True
            except Exception:
                continue
        ref = getattr(message, "reference", None)
        resolved = getattr(ref, "resolved", None) if ref else None
        if resolved is not None:
            try:
                rauthor = getattr(resolved, "author", None)
                if rauthor and int(getattr(rauthor, "id", -1)) in config_uids:
                    return True
            except Exception:
                pass
        return False
    except Exception:
        return False


def _guild_bot_on(bot: Any, message: Any, bot_on_checker=None) -> bool:
    """Server co bot ON khong? DM -> True (khong co khai niem ON/OFF)."""
    try:
        guild = getattr(message, "guild", None)
        if guild is None:
            return True
        gid = getattr(guild, "id", None)
        if gid is None:
            return False
        if callable(bot_on_checker):
            try:
                return bool(bot_on_checker(int(gid)))
            except Exception:
                return False
        fn = getattr(bot, "is_bot_active", None)
        if callable(fn):
            try:
                return bool(fn(int(gid)))
            except Exception:
                return False
        return False
    except Exception:
        return False


def _has_bot_in_guild(bot: Any, message: Any) -> bool:
    """Server nay co bot (acc config) khong? Co mat bot.user trong guild."""
    try:
        guild = getattr(message, "guild", None)
        if guild is None:
            return False
        config_uids = _all_config_uids(bot)
        if not config_uids:
            me = getattr(getattr(bot, "user", None), "id", None)
            return me is not None and getattr(guild, "get_member", None) is not None and guild.get_member(int(me)) is not None
        try:
            members = getattr(guild, "members", None) or []
            for m in members:
                try:
                    if int(getattr(m, "id", -1)) in config_uids:
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        try:
            me = getattr(getattr(bot, "user", None), "id", None)
            if me is not None and getattr(guild, "get_member", None) is not None:
                return guild.get_member(int(me)) is not None
        except Exception:
            pass
        return False
    except Exception:
        return False


def _is_staff_message(bot: Any, message: Any) -> bool:
    """Tin cua admin / admin cap cao (ke ca bot OFF)."""
    try:
        aid = _author_id(message)
        if aid is None:
            return False
        try:
            try:
                from apps.user_discord.core.bot_sys import is_staff as _sys_staff, is_mod as _sys_mod
            except ImportError:
                from core.bot_sys import is_staff as _sys_staff, is_mod as _sys_mod  # type: ignore
            if bool(_sys_staff(bot, int(aid))):
                return True
            if bool(_sys_mod(bot, int(aid))):
                return True
        except Exception:
            pass
        try:
            fn = getattr(bot, "is_staff", None)
            if callable(fn) and bool(fn(int(aid))):
                return True
        except Exception:
            pass
        return False
    except Exception:
        return False


def should_log_message(bot: Any, message: Any, bot_on_checker=None) -> Tuple[bool, str]:
    """Tra (co_log, ly_do). Ly do: TAG | SV-ON | BOT | DM | STAFF | ''."""
    try:
        if message is None or getattr(message, "author", None) is None:
            return False, ""
        # 3. Tin cua acc trong config -> luon log (bot nao thay cung log).
        if _is_own_message(bot, message):
            if getattr(message, "guild", None) is None:
                return True, "DM"
            return True, "BOT"
        # 1. NGUOI KHAC tag acc trong config -> log.
        if _mentions_me(bot, message):
            if getattr(message, "guild", None) is None:
                return True, "DM"
            return True, "TAG"
        # 4. Tin nhan rieng (DM) -> log.
        try:
            if getattr(message, "guild", None) is None:
                return True, "DM"
        except Exception:
            pass
        # 5. Tin admin / admin cap cao o server co bot (ke ca bot OFF).
        try:
            if getattr(message, "guild", None) is not None:
                if _has_bot_in_guild(bot, message) and _is_staff_message(bot, message):
                    return True, "STAFF"
        except Exception:
            pass
        # 2. Tin o sv co bot ON -> log.
        if _guild_bot_on(bot, message, bot_on_checker):
            return True, "SV-ON"
        return False, ""
    except Exception:
        return False, ""
