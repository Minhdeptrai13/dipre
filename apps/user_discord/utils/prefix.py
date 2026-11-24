# -*- coding: utf-8 -*-
"""Danh tinh & prefix RIENG cua TUNG selfbot trong apps/user_discord.

VAN DE CU
---------
1) Nhieu chuoi hard-code "(prefix)" trong caption/docstring -> bot tra loi nguyen
   van "(prefix)yt stop" (xuat hien ngay trong tin rep cua bot).
2) Vai cho doc truc tiep `bot.command_prefix` (la list ["m", "m "]) nen in ra xau,
   va neu "nho" prefix bang bien toan cu thi khi chay nhieu account chung 1
   process, bot A rat de an prefix cua bot B (nguoc lai).

CACH GIAI QUYET
---------------
Toan bo thong tin "toi la ai / prefix cua toi la gi" duoc gan THANG LEN OBJECT
bot, khong co bien toan cu dung chung nen moi account tu biet minh:

    bot._own_prefix     -> prefix dang dung cua rieng bot do
    bot._own_identity   -> {prefix, name, token_raw}

Thu tu uu tien khi lay prefix cua 1 bot (ham resolve):
    1. bot._own_prefix          (bind luc khoi dong / sau lenh `prefix set`)
    2. bot.user_prefix          (neu gan thu cong)
    3. bot.command_prefix       (discord.py parse: str | list | callable)
    4. config.json match theo TOKEN chinh cua bot do
    5. data/<uid>_setting.json -> key "prefix"
    6. DEFAULT_PREFIX "!"

CACH DUNG
---------
    from apps.user_discord.utils.prefix import get_prefix, fmt

    caption = fmt(self.bot, "*Go `(prefix)yt stop` de dung.*")  ->  "*Go `myt stop` de dung.*"
    pfx     = get_prefix(self.bot)                             ->  "m"

    # main.py:
    from apps.user_discord.utils.prefix import bind, apply_help
    bind(bot, prefix=p, name=name, token=token)   # truoc khi bot.start()
    apply_help(bot)                               # sau khi load xong extensions
"""

from __future__ import annotations

import inspect
import json
import weakref
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from discord.ext import commands

try:
    from apps.user_discord.core.alias import alias_declare
except ImportError:
    try:
        from core.alias import alias_declare
    except ImportError:
        def alias_declare(*args, **kwargs):
            def dec(fn):
                return fn
            return dec

DEFAULT_PREFIX = ""

# Nguon prefix (hien ra cho nguoi dung). SRC_DEFAULT = chua biet -> dung default.
SRC_BIND = "bot._own_prefix (bind luc khoi dong / lenh prefix set)"
SRC_DEFAULT = "mặc định (chưa cấu hình ở đâu cả)"

# Cac dang placeholder se duoc thay bang prefix that cua bot dang chay
PLACEHOLDERS: Tuple[str, ...] = ("(prefix)", "(Prefix)", "{prefix}", "<prefix>", "%prefix%")

_ATTR_PFX = "_own_prefix"
_ATTR_ID = "_own_identity"
_ATTR_RAW = "_own_help_raw"

BASE_DIR = Path(__file__).resolve().parent.parent           # apps/user_discord
PROJECT_ROOT = BASE_DIR.parents[1]                          # goc du an (botdis)
CONFIG_FILES: Tuple[Path, ...] = (BASE_DIR / "config.json", BASE_DIR / "data" / "config.json")
DATA_DIR = BASE_DIR / "data"

# Chi cache NOI DUNG FILE config.json (du lieu chung, doc) - khong bao gio cache
# "prefix cua bot" o cap module => khong the lan giua cac account.
_cfg_state: Dict[str, Any] = {"key": None, "accounts": [], "default": DEFAULT_PREFIX}

# Dang ky cac bot dang song (chi phuc vu lenh `prefix list`, khong anh huong resolve)
_LIVE: "weakref.WeakKeyDictionary[Any, Dict[str, Any]]" = weakref.WeakKeyDictionary()


def _log(msg: str) -> None:
    """In log ASCII-thuan (console Windows cp1252 rat de UnicodeEncodeError)."""
    try:
        print(msg, flush=True)
    except Exception:
        try:
            print(str(msg).encode("ascii", "ignore").decode("ascii"), flush=True)
        except Exception:
            pass


def _clean(value: Any) -> str:
    """Chuan hoa prefix: ep kieu str + bo khoang trang dau/cuoi ("m " -> "m")."""
    if value is None:
        return ""
    try:
        return str(value).strip()
    except Exception:
        return ""


def mask_token(token: Optional[str]) -> str:
    """Che token nhung van du cho nhan biet do la account nao."""
    t = _clean(token)
    if not t:
        return "(chua co token)"
    if len(t) <= 14:
        return "*" * len(t)
    return f"{t[:6]}...{t[-6:]}"

# ─────────────────────────────────────────────────────────────────────────────
# DOC CONFIG THEO TOKEN: bot A biet token cua minh -> prefix cua minh
# ─────────────────────────────────────────────────────────────────────────────
def _accounts() -> List[Dict[str, str]]:
    """Doc config.json va tra ve danh sach account {name, token, prefix} (co cache mtime)."""
    path = next((p for p in CONFIG_FILES if p.exists()), None)
    if path is None:
        return []
    try:
        key: Any = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return []

    if _cfg_state["key"] != key:
        accounts: List[Dict[str, str]] = []
        try:
            raw_cfg = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw_cfg, dict):
                raw_cfg = {}
            default_pfx = _clean(raw_cfg.get("prefix")) if raw_cfg.get("prefix") is not None else DEFAULT_PREFIX
            _cfg_state["default"] = default_pfx

            try:
                from apps.shared.token_crypto import decrypt
            except Exception:
                decrypt = lambda x: x

            for acc in (raw_cfg.get("accounts") or []):
                if not isinstance(acc, dict):
                    continue
                acc_pfx = _clean(acc["prefix"]) if acc.get("prefix") is not None else default_pfx
                accounts.append({
                    "name": _clean(acc.get("name")),
                    "token": _clean(decrypt(acc.get("token"))),
                    "prefix": acc_pfx,
                })

            for tok in (raw_cfg.get("tokens") or []):
                t = _clean(decrypt(tok))
                if t and all(a["token"] != t for a in accounts):
                    accounts.append({"name": f"Account-{len(accounts) + 1}", "token": t, "prefix": default_pfx})

            single = _clean(decrypt(raw_cfg.get("token")))
            if single and all(a["token"] != single for a in accounts):
                accounts.append({"name": "Primary", "token": single, "prefix": default_pfx})
        except Exception as exc:
            _log(f"[PREFIX] Khong doc duoc config.json: {type(exc).__name__}")
            accounts = []

        _cfg_state["key"] = key
        _cfg_state["accounts"] = accounts

    return _cfg_state["accounts"]


def _identity(bot: Any) -> Dict[str, Any]:
    ident = getattr(bot, _ATTR_ID, None)
    return ident if isinstance(ident, dict) else {}


def token_of(bot: Any) -> str:
    """Lay token dang thuc su chay cua RIENG bot nay (khong phai bot khac)."""
    getters = (
        lambda: getattr(getattr(bot, "http", None), "token", None),
        lambda: getattr(bot, "token", None),
        lambda: getattr(getattr(bot, "_connection", None), "token", None),
    )
    for get in getters:
        try:
            tok = _clean(get())
        except Exception:
            tok = ""
        if tok:
            return tok
    return _clean(_identity(bot).get("token_raw"))


def account_for(bot: Any) -> Optional[Dict[str, str]]:
    """Tim account trong config.json dung voi bot nay (uu tien token, roi ten)."""
    accounts = _accounts()
    if not accounts:
        return None

    tok = token_of(bot)
    if tok:
        for acc in accounts:
            if acc.get("token") and acc.get("token") == tok:
                return acc

    user = getattr(bot, "user", None)
    user_name = _clean(getattr(user, "name", "")) if user is not None else ""
    if user_name:
        for acc in accounts:
            if _clean(acc.get("name")).lower() == user_name.lower():
                return acc

    name_hint = _clean(_identity(bot).get("name"))
    if name_hint:
        for acc in accounts:
            if _clean(acc.get("name")).lower() == name_hint.lower():
                return acc
    return None


def _from_data_setting(bot: Any) -> Optional[str]:
    """Doc key "prefix" trong data/<uid>_setting.json cua dung UID nay."""
    uid = getattr(getattr(bot, "user", None), "id", None) or getattr(bot, "uid", None)
    if not uid:
        return None
    setting = DATA_DIR / f"{uid}_setting.json"
    if not setting.exists():
        return None
    try:
        data = json.loads(setting.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "prefix" in data:
            return _clean(data.get("prefix"))
        return None
    except Exception:
        return None


def _from_command_prefix(cp: Any, bot: Any = None) -> str:
    """Lay 1 prefix duy nhat tu `command_prefix` (str | list | tuple | callable)."""
    if cp is None:
        return ""
    if callable(cp):
        for args in ((bot, None), (bot,), ()):
            try:
                res = cp(*args)
            except TypeError:
                continue
            except Exception:
                return ""
            if inspect.isawaitable(res):
                try:
                    res.close()          # khong await duoc o day -> bo qua
                except Exception:
                    pass
                return ""
            val = res[0] if isinstance(res, (list, tuple)) and res else res
            p = _clean(val)
            if p:
                return p
            break
        return ""
    if isinstance(cp, (list, tuple)):
        for item in cp:
            p = _clean(item)
            if p:
                return p
        return ""
    return _clean(cp)

# ─────────────────────────────────────────────────────────────────────────────
# API CHINH - luon tra ve prefix cua DUNG bot duoc truyen vao
# ─────────────────────────────────────────────────────────────────────────────
def resolve(bot: Any) -> Tuple[str, str]:
    """Resolve prefix cua RIENG bot nay + ghi ro nguon da dung de lay."""
    if bot is None:
        return DEFAULT_PREFIX, "mac dinh (khong co bot)"

    if hasattr(bot, _ATTR_PFX):
        raw_val = getattr(bot, _ATTR_PFX)
        if raw_val is not None:
            p = _clean(raw_val)
            src = _identity(bot).get("source") or SRC_BIND
            return p, src

    if hasattr(bot, "_own_prefix") and getattr(bot, "_own_prefix") is not None:
        return _clean(getattr(bot, "_own_prefix")), "bot._own_prefix"

    acc = account_for(bot)
    if acc and acc.get("prefix") is not None:
        src = f"config.json ({acc.get('name') or '?'})"
        return _clean(acc["prefix"]), src

    if hasattr(bot, "user_prefix") and getattr(bot, "user_prefix") is not None:
        return _clean(getattr(bot, "user_prefix")), "bot.user_prefix"

    p = _from_command_prefix(getattr(bot, "command_prefix", None), bot)
    if p:
        return p, "bot.command_prefix"

    p_ds = _from_data_setting(bot)
    if p_ds is not None:
        uid = getattr(getattr(bot, "user", None), "id", None) or "?"
        return p_ds, f"data/{uid}_setting.json"

    return DEFAULT_PREFIX, SRC_DEFAULT


def get_prefix(bot: Any) -> str:
    """Prefix dang hoat dong cua dung bot nay - khong bao gio cua bot khac."""
    p, src = resolve(bot)
    try:
        setattr(bot, _ATTR_PFX, p)
        ident = getattr(bot, _ATTR_ID, None)
        if isinstance(ident, dict):
            ident.setdefault("source", src)
    except Exception:
        pass
    return p


def get_prefixes(bot: Any) -> List[str]:
    """Toan bo prefix hop le cua bot nay (kem bien the co dau cach phia sau)."""
    p = get_prefix(bot)
    if p == "":
        return [""]
    out: List[str] = [p]
    if not p.endswith(" "):
        out.append(f"{p} ")
    return out


def has_prefix(bot: Any, content: str) -> bool:
    """Kiem tra nhanh 1 chuoi tin nhan co phai lenh cua bot nay khong."""
    if not content:
        return False
    for p in get_prefixes(bot):
        if content.startswith(p):
            return True
    return False


def fmt(bot: Any, text: Any) -> Any:
    """Thay moi placeholder `(prefix)` / `{prefix}` bang prefix that cua bot nay."""
    if not text:
        return text
    try:
        out = str(text)
    except Exception:
        return text
    p = get_prefix(bot)
    for tok in PLACEHOLDERS:
        if tok in out:
            out = out.replace(tok, p)
    return out


def apply_help(bot: Any) -> int:
    """Cap nhat help/brief cua MOI lenh THUOC bot nay (thay placeholder bang prefix tu than).

    GOI DUOC NHIEU LAN: luon render lai tu ban GOC docstring (luu trong
    cmd._own_help_raw) chu khong render tu ban da thay, nen doi prefix lan 2
    van ra dung (khong bi "mat" placeholder o lan 1).

    Goi sau khi load xong toan bo extension. Chi cham vao lenh cua bot duoc
    truyen vao => 2 account chay dong thoi van co 2 chuoi help khac nhau.
    """
    changed = 0
    try:
        cmds: Iterable[Any] = list(bot.walk_commands())
    except Exception:
        return 0
    for cmd in cmds:
        raw_store = getattr(cmd, _ATTR_RAW, None)
        if not isinstance(raw_store, dict):
            raw_store = {}
            try:
                setattr(cmd, _ATTR_RAW, raw_store)
            except Exception:
                pass
        for attr in ("help", "brief"):
            cur = getattr(cmd, attr, None)
            if not isinstance(cur, str):
                continue
            base = raw_store.get(attr, cur)          # docstring GOC
            if any(tok in base for tok in PLACEHOLDERS):
                raw_store[attr] = base
                base = raw_store[attr]
            rendered = fmt(bot, base)
            if rendered != cur:
                try:
                    setattr(cmd, attr, rendered)
                    changed += 1
                except Exception:
                    pass
    return changed


def identity(bot: Any) -> Dict[str, Any]:
    """Thong tin danh tinh day du cua RIENG bot nay."""
    p, src = resolve(bot)
    acc = account_for(bot) or {}
    tok = token_of(bot)
    user = getattr(bot, "user", None)
    uid = getattr(user, "id", None)
    name = _clean(getattr(user, "name", "")) if user is not None else ""
    return {
        "prefix": p,
        "prefixes": get_prefixes(bot),
        "source": src,
        "name": name or _clean(acc.get("name")) or "(chua login)",
        "account": _clean(acc.get("name")) or "(khong co trong config.json)",
        "uid": uid,
        "token_masked": mask_token(tok),
        "token_raw": tok,
        "self_bot": bool(getattr(bot, "self_bot", False)),
    }


def describe_accounts(bot: Any) -> str:
    """Sinh doan van: account nao - token nao - prefix nao, cai nao la minh."""
    ident = identity(bot)
    my_token = ident.get("token_raw") or ""
    accounts = _accounts()
    lines: List[str] = []

    if not accounts:
        lines.append("(Khong tim thay tai khoan nao trong config.json)")
    for idx, acc in enumerate(accounts, start=1):
        mine = bool(my_token) and acc.get("token") == my_token
        tag = "  <-- LA BOT NAY" if mine else ""
        status = "dang chay" if acc.get("token") else "chua nhap token"
        acc_p = acc.get("prefix") if acc.get("prefix") is not None else DEFAULT_PREFIX
        p_disp = f"'{acc_p}' (none)" if acc_p == "" else f"`{acc_p}`"
        lines.append(
            f"{idx}. `{acc.get('name') or f'Account-{idx}'}` | token `{mask_token(acc.get('token'))}`"
            f" | prefix: **{p_disp}** | {status}{tag}"
        )

    try:
        live = max(len(list(_LIVE.keys())), 1)
    except Exception:
        live = 1

    lines.append("")
    lines.append(f"🔑 Bot đang chạy trong tiến trình: **{live}**")
    lines.append(f"📌 Bot bạn đang hỏi: **{ident['name']}** (UID `{ident['uid'] or '?'}`) → prefix **`{ident['prefix']}`**")
    lines.append(f"• Nguồn prefix: {ident['source']}")
    lines.append(f"• Token: `{ident['token_masked']}` | trùng account: {ident['account']}")
    return "\n".join(lines)

# ─────────────────────────────────────────────────────────────────────────────
# Gan / doi danh tinh prefix cho MOT bot cu the
# ─────────────────────────────────────────────────────────────────────────────
def bind(bot: Any, prefix: Optional[str] = None, name: Optional[str] = None,
         token: Optional[str] = None, force: bool = False) -> str:
    """Gan danh tinh + prefix cua bot vao chinh object bot (goi luc khoi dong).

    Neus `prefix` duoc truyen (tu main.py) thi day la nguon chinh; neu de trong,
    ham tu suy ra tu command_prefix / config.json theo token cua chinh bot do.
    """
    tok = _clean(token) or token_of(bot)
    acc = None
    if tok:
        acc = next((a for a in _accounts() if a.get("token") and a.get("token") == tok), None)

    if prefix is not None:
        chosen = _clean(prefix)
    else:
        chosen = None
        if hasattr(bot, _ATTR_PFX):
            val = getattr(bot, _ATTR_PFX)
            if val is not None:
                chosen = _clean(val)
        if chosen is None and acc and acc.get("prefix") is not None:
            chosen = _clean(acc["prefix"])
        if chosen is None:
            val = getattr(bot, "_own_prefix", None)
            if val is not None:
                chosen = _clean(val)
        if chosen is None:
            chosen = _from_data_setting(bot)
        if chosen is None:
            chosen = DEFAULT_PREFIX

    try:
        setattr(bot, _ATTR_PFX, chosen)
        setattr(bot, "user_prefix", chosen)
        setattr(bot, "_own_prefix", chosen)
        setattr(bot, _ATTR_ID, {
            "prefix": chosen,
            "name": _clean(name) or _clean((acc or {}).get("name")),
            "token_raw": tok,
        })
    except Exception:
        pass

    try:
        _LIVE[bot] = {"prefix": chosen, "name": _clean(name)}
    except Exception:
        pass

    return chosen


def set_prefix(bot: Any, new_prefix: str, persist: bool = True) -> Tuple[bool, str]:
    """Doi prefix CHANH bot nay tai thoi gian thuc (+ ghi lai config.json theo token).

    Tra ve (thanh_cong, ghi_chu). Khong anh huong bat ky bot nao khac.
    """
    p = _clean(new_prefix)
    is_none = p.lower() in ("none", "no", "off", "empty", "trong", "null")
    if is_none:
        p = ""
    elif not p and new_prefix != "":
        return False, "prefix khong duoc de trong (go 'none' de chay khong can prefix)."
    if len(p) > 12:
        return False, "prefix toi da 12 ky tu."
    if "\n" in p or "\t" in p:
        return False, "prefix khong duoc chua xuong dong/tab."

    old = get_prefix(bot)
    variants = [""] if p == "" else ([p] if p.endswith(" ") else [p, f"{p} "])

    try:
        bot.command_prefix = variants
    except Exception as exc:
        pass

    try:
        setattr(bot, _ATTR_PFX, p)
        setattr(bot, "user_prefix", p)
        setattr(bot, "_own_prefix", p)
    except Exception:
        pass

    bind(bot, prefix=p, force=True)
    apply_help(bot)

    note = f"prefix cu `{old}` -> `{p or 'None'}` (chi ap dung cho bot nay)."
    if persist:
        ok, msg = sync_config(bot, p)
        note += f" | {msg}"
        save_setting_prefix(bot, p)
    return True, note


def sync_config(bot: Any, new_prefix: str) -> Tuple[bool, str]:
    """Ghi prefix moi vao config.json, DUNG VAO account co token trung voi bot nay."""
    p = _clean(new_prefix)
    path = next((x for x in CONFIG_FILES if x.exists()), None)
    if path is None:
        return False, "khong tim thay config.json nen khong the luu vinh"
    tok = token_of(bot)
    if not tok:
        return False, "khong doc duoc token cua bot nen khong the luu vinh"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            return False, "config.json khong phai JSON object, bo luu"
        hit = False
        try:
            from apps.shared.token_crypto import decrypt
        except Exception:
            decrypt = lambda x: x

        for acc in (cfg.get("accounts") or []):
            if not isinstance(acc, dict):
                continue
            acc_tok = _clean(acc.get("token"))
            if acc_tok == tok or _clean(decrypt(acc_tok)) == tok:
                acc["prefix"] = p
                hit = True
        if not hit:
            return False, "token cua bot khong co trong config.json -> chi doi tam thoi"

        try:
            path.with_suffix(".json.bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass

        path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        _cfg_state["key"] = None          # buoc doc lai config.json
        return True, "da luu vinh vao config.json"
    except Exception as exc:
        return False, f"loi ghi config.json: {type(exc).__name__}"


def save_setting_prefix(bot: Any, new_prefix: str) -> bool:
    """Ghi prefix vao data/<uid>_setting.json cua chinh UID nay (luu theo tung account)."""
    uid = getattr(getattr(bot, "user", None), "id", None) or getattr(bot, "uid", None)
    if not uid:
        return False
    setting = DATA_DIR / f"{uid}_setting.json"
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data: Dict[str, Any] = {}
        if setting.exists():
            try:
                loaded = json.loads(setting.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                data = {}
        data["prefix"] = _clean(new_prefix)
        setting.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────────────────────
# COG: lenh de bot tu khai bao prefix cua minh
# ─────────────────────────────────────────────────────────────────────────────
async def _reply(ctx: commands.Context, text: str, delay: Optional[int] = 45):
    """Rep theo chuẩn của user_discord (autorep) nhung van chay duu khi thieu module."""
    # Tu thay placeholder (prefix) trong MOI noi dung reply bang prefix cua
    # DUNG bot nay. ctx.bot chinh la bot dang xu ly tin nhan nen khong bao gio
    # nham prefix cua bot khac.
    try:
        text = fmt(getattr(ctx, "bot", None), text)
    except Exception:
        pass

    try:
        from apps.user_discord.utils.autorep import autorep
    except ImportError:
        try:
            from utils.autorep import autorep
        except ImportError:
            return await ctx.send(text)
    return await autorep(ctx.message, content=text, auto_delete_delay=delay)


class PrefixIdentity(commands.Cog):
    """Bot tu biet minh la ai (token nao) va prefix cua minh la gi."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bind(bot)
        self._cd = {}

    @alias_declare("prefix", main="prefix", subs=["pfx"])
    @commands.command(name="prefix", aliases=("pfx", "dau-lenh", "dau_lenh"))
    async def cmd_prefix(self, ctx: commands.Context):
        """Xem prefix của bot này: (prefix)prefix"""
        import time
        cid = ctx.channel.id
        now = time.time()
        if now - self._cd.get(cid, 0) < 3.0:
            return
        self._cd[cid] = now
        pfx = get_prefix(self.bot)
        pfx_clean = pfx if pfx else "None"
        bot_name = self.bot.user.name if self.bot.user else "Bot"
        bot_uid = self.bot.user.id if self.bot.user else 0

        # Kiểm tra quyền hạn
        sender_id = ctx.author.id
        is_owner_this_bot = (sender_id == bot_uid)
        cfg_owners = set()
        try:
            cfg_path = next((p for p in CONFIG_FILES if p.exists()), None)
            if cfg_path:
                cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
                for acc in cfg_data.get("accounts", []):
                    if isinstance(acc, dict) and acc.get("uid") == bot_uid:
                        for oid in list(acc.get("owner_ids") or []) + [acc.get("created_by")]:
                            if oid:
                                try:
                                    cfg_owners.add(int(oid))
                                except Exception:
                                    pass
        except Exception:
            pass

        setting_file = DATA_DIR / f"{bot_uid}_setting.json"
        this_conf: Dict[str, Any] = {}
        if setting_file.exists():
            try:
                this_conf = json.loads(setting_file.read_text(encoding="utf-8"))
            except Exception:
                this_conf = {}

        this_mod_list = set(cfg_owners)
        for x in this_conf.get("admintris", this_conf.get("moderator", [])):
            try:
                if str(x).isdigit():
                    this_mod_list.add(int(x))
            except Exception:
                pass

        is_high_admin_this_bot = is_owner_this_bot or (sender_id in this_mod_list)
        this_admin_list = set(this_mod_list)
        for x in this_conf.get("admins", this_conf.get("admin", [])):
            try:
                if str(x).isdigit():
                    this_admin_list.add(int(x))
            except Exception:
                pass
        is_admin_this_bot = is_high_admin_this_bot or (sender_id in this_admin_list)

        tier_txt = "Admin cấp cao (admintris)" if is_high_admin_this_bot else (
            "Admin" if is_admin_this_bot else "Thành viên"
        )

        if ctx.guild:
            guild_active_map = this_conf.get("guild_active", {})
            bot_on_here = bool(guild_active_map.get(str(ctx.guild.id), False))
        else:
            bot_on_here = bool(this_conf.get("dm_active", True))

        latency_ms = int(self.bot.latency * 1000) if (self.bot.latency and self.bot.latency > 0) else 15
        status_txt = "Đang bật" if bot_on_here else "Đang tắt (Admin Only)"

        text = (
            f"```\n"
            f"BotIdentity:\n"
            f"  tên           {bot_name} ({bot_uid})\n"
            f"  prefix        {pfx_clean}\n"
            f"  quyền         {tier_txt}\n"
            f"  trạng thái    {status_txt} ({latency_ms}ms)\n\n"
            f"Gõ {pfx}menu để xem toàn bộ danh sách lệnh.\n"
            f"```"
        )
        await _reply(ctx, text, delay=30)


async def setup(bot: commands.Bot):
    bind(bot)
    await bot.add_cog(PrefixIdentity(bot))




