"""Ma hoa token trong config.json  (dung chung cho ca 2 app).

Muc dich
--------
Token nam trong `config.json` la dang plaintext -> chuyen code / zip / upload la
lo token ngay. Module nay ma hoa token ngay trong file:

    "token": "MTM5...fQ"                ->  "token": "enc:v1:AbCd...=="

Dac diem
--------
* Chi dung thu vien chuan (hashlib/hmac/secrets/base64) -> khong can cai them
  `cryptography` (2 venv cua du an deu khong co san).
* Khoa duoc suy ra tu mot "pepper" CO DINH TRONG CODE (bi chia nho + base64 de
  khong lo ra dang doc duoc). Nho vay **di chuyen code sang may/thu muc khac
  van giai ma duoc** (khac voi khoa gan theo may).
* Co the ghi de khoa rieng bang bien moi truong `BOTDIS_TOKEN_KEY` (khuyen dung
  khi public code: dat env nay roi chay bot 1 lan de ma hoa lai).
* Giai ma la "best effort": gia tri khong phai dang `enc:v1:...` (plaintext cu)
  duoc tra ve nguyen ven -> code cu / config cu van chay binh thuong.

API chinh
---------
    is_encrypted(value) -> bool
    encrypt(text) -> str
    decrypt(value) -> str
    looks_like_token(text) -> bool
    mask(value) -> str
    encrypt_config_inplace(path, log=print) -> dict      # quet + ma hoa file
    encrypt_config(cfg) / decrypt_config(cfg) -> dict    # tren dict da load
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Hang so dinh dang
# ─────────────────────────────────────────────────────────────────────────────
PREFIX = "enc:v1:"
ENV_KEY = "BOTDIS_TOKEN_KEY"
_SALT = b"botdis::config::token::salt::v1"
_INFO = b"botdis-token-vault-v1"
_ROUNDS = 200_000
_TAG_LEN = 16
_NONCE_LEN = 16

# Pepper (bi chia nho + base64) - KHONG sua sau khi da ma hoa token, neu sua thi
# token cu se khong giai ma duoc nua.
_PEPPER_PARTS = (
    "Ym90ZGlz",
    "LXdl",
    "YWx0aC1rZXkt",
    "c2hhcmVkLXYx",
)

# Token Discord: 3 phan cach nhau bang dau cham, hoac dang "mfa.xxxx.yyyy".
_TOKEN_RE = re.compile(
    r"^(?:mfa\.)?[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]{20,}$"
)


# ─────────────────────────────────────────────────────────────────────────────
# Khoa
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _pepper() -> bytes:
    """Lay pepper: uu tien bien moi truong, khong thi dung hang so trong code."""
    env = (os.environ.get(ENV_KEY) or "").strip()
    if env:
        return env.encode("utf-8")
    return base64.b64decode("".join(_PEPPER_PARTS))


@lru_cache(maxsize=1)
def _keys() -> tuple:
    """Sinh cap khoa (enc_key, mac_key) tu pepper, co dinh tren moi may."""
    material = hashlib.pbkdf2_hmac("sha256", _pepper(), _SALT, _ROUNDS, dklen=64)
    enc_key = hmac.new(material, b"enc" + _INFO, hashlib.sha256).digest()
    mac_key = hmac.new(material, b"mac" + _INFO, hashlib.sha256).digest()
    return enc_key, mac_key


def reset_cache() -> None:
    """Xoa cache khoa (dung khi doi bien moi truong trong cung 1 process)."""
    _pepper.cache_clear()
    _keys.cache_clear()
# ─────────────────────────────────────────────────────────────────────────────
# Cipher (stream HMAC-SHA256 + tag HMAC-SHA256, encrypt-then-MAC)
# ─────────────────────────────────────────────────────────────────────────────
def _keystream(key: bytes, nonce: bytes, size: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < size:
        out += hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:size])


def _xor(data: bytes, stream: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, stream))


def is_encrypted(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX) and len(value) > len(PREFIX)


def looks_like_token(value: Any) -> bool:
    """True neu chuoi trong giong token Discord (de quyet dinh co ma hoa hay khong)."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if len(text) < 50 or len(text) > 200:
        return False
    return bool(_TOKEN_RE.match(text))


def encrypt(text: Any) -> str:
    """Ma hoa 1 chuoi -> 'enc:v1:<base64>'. Rong / khong phai str -> tra nguyen ven."""
    if not isinstance(text, str):
        return text
    raw = text.strip()
    if not raw or is_encrypted(raw):
        return raw
    enc_key, mac_key = _keys()
    nonce = secrets.token_bytes(_NONCE_LEN)
    data = raw.encode("utf-8")
    ct = _xor(data, _keystream(enc_key, nonce, len(data)))
    tag = hmac.new(mac_key, nonce + ct, hashlib.sha256).digest()[:_TAG_LEN]
    return PREFIX + base64.urlsafe_b64encode(nonce + ct + tag).decode("ascii")


_WARNED: List[str] = []


def _warn_once(msg: str) -> None:
    if msg in _WARNED:
        return
    _WARNED.append(msg)
    try:
        print(f"[SECURE] {msg}", flush=True)
    except Exception:
        pass


def decrypt(value: Any) -> str:
    """Giai ma 'enc:v1:...' -> plaintext. Loi/gia tri thuong -> tra nguyen ven."""
    if not isinstance(value, str):
        return value
    if not is_encrypted(value):
        return value
    payload = value[len(PREFIX):]
    try:
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        if len(raw) <= _NONCE_LEN + _TAG_LEN:
            return value
        nonce, ct, tag = raw[:_NONCE_LEN], raw[_NONCE_LEN:-_TAG_LEN], raw[-_TAG_LEN:]
        enc_key, mac_key = _keys()
        expect = hmac.new(mac_key, nonce + ct, hashlib.sha256).digest()[:_TAG_LEN]
        if not hmac.compare_digest(tag, expect):
            _warn_once("token: sai khoa hoac du lieu bi sua -> tra nguyen ven")
            return value
        return _xor(ct, _keystream(enc_key, nonce, len(ct))).decode("utf-8", "replace")
    except Exception:
        _warn_once("token: giai ma that bai -> tra nguyen ven")
        return value


def mask(value: Any, keep: int = 6) -> str:
    """Che token de hien thi: 'MTM5OT...C9YTg'."""
    tok = decrypt(value) if is_encrypted(value) else value
    if not isinstance(tok, str):
        return ""
    tok = tok.strip()
    if not tok:
        return "(chua co token)"
    if len(tok) <= keep * 2:
        return "*" * len(tok)
    return f"{tok[:keep]}...{tok[-keep:]}"
# ─────────────────────────────────────────────────────────────────────────────
# Quet / ma hoa ca file config.json
# ─────────────────────────────────────────────────────────────────────────────
def _iter_token_slots(cfg: Dict[str, Any]) -> Iterable[tuple]:
    """Sinh (getter, setter, mo ta) cho MOI cho co the chua token trong config."""
    if isinstance(cfg.get("token"), str):
        yield (
            lambda: cfg.get("token"),
            lambda v: cfg.__setitem__("token", v),
            "token",
        )

    seq = cfg.get("tokens")
    if isinstance(seq, list):
        for idx, item in enumerate(seq):
            if isinstance(item, str):
                yield (
                    lambda i=idx: cfg["tokens"][i],
                    lambda v, i=idx: cfg["tokens"].__setitem__(i, v),
                    f"tokens[{idx}]",
                )

    for key in ("accounts", "bots"):
        seq = cfg.get(key)
        if not isinstance(seq, list):
            continue
        for idx, acc in enumerate(seq):
            if not isinstance(acc, dict):
                continue
            yield (
                lambda a=acc: a.get("token"),
                lambda v, a=acc: a.__setitem__("token", v),
                f"{key}[{idx}].token",
            )


def encrypt_config(cfg: Dict[str, Any], only_tokens: bool = True) -> Dict[str, int]:
    """Ma hoa tai cho moi token trong dict config (tra ve thong ke)."""
    stats = {"ma_hoa": 0, "da_ma_hoa": 0, "bo_qua": 0}
    if not isinstance(cfg, dict):
        return stats
    for getter, setter, _where in _iter_token_slots(cfg):
        try:
            current = getter()
        except Exception:
            continue
        if not isinstance(current, str):
            continue
        if is_encrypted(current):
            stats["da_ma_hoa"] += 1
            continue
        if not current.strip():
            stats["bo_qua"] += 1
            continue
        if only_tokens and not looks_like_token(current):
            stats["bo_qua"] += 1
            continue
        setter(encrypt(current))
        stats["ma_hoa"] += 1
    return stats


def decrypt_config(cfg: Dict[str, Any]) -> Dict[str, int]:
    """Giai ma tai cho moi token trong dict config (tra ve thong ke)."""
    stats = {"giai_ma": 0, "giu_nguyen": 0}
    if not isinstance(cfg, dict):
        return stats
    for getter, setter, _where in _iter_token_slots(cfg):
        try:
            current = getter()
        except Exception:
            continue
        if not isinstance(current, str):
            continue
        if is_encrypted(current):
            plain = decrypt(current)
            if plain != current:
                setter(plain)
                stats["giai_ma"] += 1
            else:
                stats["giu_nguyen"] += 1
        else:
            stats["giu_nguyen"] += 1
    return stats


def encrypt_config_inplace(
    path: Path,
    log: Optional[Callable[[str], None]] = print,
    only_tokens: bool = True,
) -> Dict[str, Any]:
    """Doc config.json -> ma hoa token chua ma hoa -> ghi lai (co backup .bak).

    Tra ve: {"ok": bool, "ma_hoa": n, "da_ma_hoa": n, "bo_qua": n, "loi": str|None}
    """
    result: Dict[str, Any] = {
        "ok": False, "ma_hoa": 0, "da_ma_hoa": 0, "bo_qua": 0, "loi": None
    }
    p = Path(path)
    if not p.exists():
        result["loi"] = "khong tim thay config.json"
        return result

    try:
        raw_text = p.read_text(encoding="utf-8")
        cfg = json.loads(raw_text)
    except Exception as exc:
        result["loi"] = f"doc config loi: {type(exc).__name__}"
        return result

    if not isinstance(cfg, dict):
        result["loi"] = "config.json khong phai JSON object"
        return result

    stats = encrypt_config(cfg, only_tokens=only_tokens)
    result.update(stats)
    result["ok"] = True

    if not stats["ma_hoa"]:
        if log:
            try:
                log(
                    f"[SECURE] Token trong {p.name}: DA ma hoa "
                    f"({stats['da_ma_hoa']} token) - ok, khong can lam gi."
                )
            except Exception:
                pass
        return result

    try:
        try:
            p.with_suffix(".json.bak").write_text(raw_text, encoding="utf-8")
        except Exception:
            pass
        p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        result["ok"] = False
        result["loi"] = f"ghi config loi: {type(exc).__name__}"
        return result

    if log:
        try:
            log(
                f"[SECURE] Da ma hoa {stats['ma_hoa']} token trong {p.name} "
                f"(giu nguyen {stats['da_ma_hoa']} token da ma hoa). "
                f"Backup: {p.with_suffix('.json.bak').name}"
            )
        except Exception:
            pass
    return result


__all__ = [
    "PREFIX",
    "ENV_KEY",
    "encrypt",
    "decrypt",
    "is_encrypted",
    "looks_like_token",
    "mask",
    "encrypt_config",
    "decrypt_config",
    "encrypt_config_inplace",
    "reset_cache",
]