# -*- coding: utf-8 -*-
"""QR LOGIN - lay token Discord acc bang cach quet QR (Remote Auth Gateway v2).

Luong giao thiec (da test TRUC TIEP voi gateway Discord):
    1. WS  wss://remote-auth-gateway.discord.gg/?v=2   (Origin: https://discord.com)
    2. nhan "hello"  -> gui "init" {encoded_public_key: base64(DER SPKI RSA-2048)}
    3. nhan "nonce_proof" {encrypted_nonce}
       -> gui "nonce_proof" {proof: base64url(sha256(nonce da giai ma RSA-OAEP-SHA256))}
    4. nhan "pending_remote_init" {fingerprint}
       -> QR chua chuoi: https://discord.com/ra/<fingerprint>
    5. Dien thoai quet + Approve -> nhan "pending_ticket" (id:discrim:avatar:username)
                                -> nhan "pending_login" {ticket}
    6. POST /api/v9/users/@me/remote-auth/login  {ticket}
       -> {encrypted_token} -> RSA-OAEP-SHA256 -> TOKEN.

⚠️ Chi dung voi acc BAN SO HUU: ai quet QR nay thi token acc ay se ve bot.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Awaitable, Callable, Optional

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore

try:
    import qrcode
except ImportError:
    qrcode = None  # type: ignore

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
except ImportError:
    hashes = serialization = padding = rsa = None  # type: ignore

GATEWAY_URL = "wss://remote-auth-gateway.discord.gg/?v=2"
GATEWAY_ORIGIN = "https://discord.com"
LOGIN_URL = "https://discord.com/api/v9/users/@me/remote-auth/login"
QR_URL_PREFIX = "https://discord.com/ra/"
DEFAULT_TIMEOUT = 150.0  # giay - QR thuong het han ~2 phut

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

__all__ = [
    "RemoteAuthError",
    "RemoteAuthResult",
    "build_qr_url",
    "render_qr_png",
    "style_qr_card",
    "run_remote_auth",
]


class RemoteAuthError(Exception):
    """Loi phien QR login.

    kind: qr | cancel | timeout | connection | network | captcha | missing_lib
    """

    def __init__(self, kind: str, message: str = ""):
        super().__init__(message or kind)
        self.kind = kind
        self.message = message or kind


@dataclass
class RemoteAuthResult:
    """Ket qua dang nhap QR thanh cong."""
    token: str
    user_id: Optional[str] = None
    username: Optional[str] = None
    avatar: Optional[str] = None


def build_qr_url(fingerprint: str) -> str:
    return f"{QR_URL_PREFIX}{fingerprint}"


def _require_deps() -> None:
    missing = []
    if aiohttp is None:
        missing.append("aiohttp")
    if qrcode is None:
        missing.append("qrcode[pil]")
    if rsa is None:
        missing.append("cryptography")
    if missing:
        raise RemoteAuthError(
            "missing_lib",
            "Thieu thu vien: " + ", ".join(missing) +
            " — cai bang: `pip install " + " ".join(missing) + "`",
        )


def render_qr_png(data: Any) -> BytesIO:
    """Vẽ QR thành PNG, hoặc trả về BytesIO nếu truyền vào raw bytes."""
    if isinstance(data, (bytes, bytearray)):
        buf = BytesIO(data)
        buf.seek(0)
        return buf
    if hasattr(data, "seek") and hasattr(data, "read"):
        data.seek(0)
        return data
    if qrcode is None:
        raise RemoteAuthError("missing_lib", "Thieu thu vien: qrcode[pil]")
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    try:
        img.save(buf, format="PNG")
    except Exception:
        img.save(buf)
    buf.seek(0)
    return buf


def _render_smooth_circle_avatar(av_bytes: bytes, size: int):
    from PIL import Image, ImageDraw
    scale = 4
    large_size = size * scale

    if av_bytes:
        try:
            raw = Image.open(BytesIO(av_bytes)).convert("RGBA")
            raw = raw.resize((large_size, large_size), Image.Resampling.LANCZOS)
        except Exception:
            raw = Image.new("RGBA", (large_size, large_size), (88, 101, 242, 255))
    else:
        raw = Image.new("RGBA", (large_size, large_size), (88, 101, 242, 255))

    mask = Image.new("L", (large_size, large_size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, large_size - 1, large_size - 1), fill=255)

    circle_img = Image.new("RGBA", (large_size, large_size), (0, 0, 0, 0))
    circle_img.paste(raw, (0, 0), mask=mask)

    draw_circle = ImageDraw.Draw(circle_img)
    draw_circle.ellipse(
        (scale, scale, large_size - scale - 1, large_size - scale - 1),
        outline=(255, 255, 255, 200),
        width=scale * 2,
    )

    return circle_img.resize((size, size), Image.Resampling.LANCZOS)


def style_qr_card(
    qr_image_bytes: bytes,
    avatar_bytes: Optional[bytes] = None,
    username: str = "User",
    discord_tag: str = "discord.com/login",
) -> BytesIO:
    """Tạo card ảnh QR chuẩn chỉ:
    - Khối trên: Bo góc, chứa Avatar tròn siêu mượt (không pixel) + Tên người dùng + Dòng địa chỉ discord
    - Khối dưới: Khối bo góc chứa mã QR NGUYÊN BẢN từ web (không sửa đổi, không đè ruột để đảm bảo quét chuẩn 100%)
    - Text dưới cùng: Scan with Discord Mobile App
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        buf = BytesIO(qr_image_bytes)
        buf.seek(0)
        return buf

    try:
        qr_raw = Image.open(BytesIO(qr_image_bytes)).convert("RGBA")
        scale_factor = 2
        qr_w = qr_raw.width * scale_factor
        qr_h = qr_raw.height * scale_factor
        qr_display = qr_raw.resize((qr_w, qr_h), Image.Resampling.NEAREST)

        pad = 24
        card_w = qr_w + (pad * 2)

        header_h = 72
        qr_box_h = qr_h + 20
        bottom_h = 44
        card_h = pad + header_h + 16 + qr_box_h + bottom_h

        card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(card)

        # 1. Nền container tổng thể bo góc
        draw.rounded_rectangle(
            (0, 0, card_w - 1, card_h - 1),
            radius=16,
            fill=(17, 18, 20, 255),
            outline=(43, 45, 49, 255),
            width=2,
        )

        # 2. Khối trên bo góc: Avatar + Tên + Địa chỉ Discord
        header_x = pad
        header_y = pad
        header_w = card_w - (pad * 2)

        draw.rounded_rectangle(
            (header_x, header_y, header_x + header_w, header_y + header_h),
            radius=12,
            fill=(35, 36, 40, 255),
            outline=(53, 55, 60, 255),
            width=1,
        )

        av_size = 48
        av_img = _render_smooth_circle_avatar(avatar_bytes, av_size)
        av_x = header_x + 12
        av_y = header_y + (header_h - av_size) // 2
        card.paste(av_img, (av_x, av_y), mask=av_img)

        text_x = av_x + av_size + 14
        draw.text((text_x, header_y + 18), username, fill=(242, 243, 245, 255))
        draw.text((text_x, header_y + 38), discord_tag, fill=(148, 155, 164, 255))

        # 3. Khối dưới bo góc: Chứa mã QR nguyên bản từ web
        qr_box_x = pad
        qr_box_y = header_y + header_h + 16
        qr_box_w = header_w

        draw.rounded_rectangle(
            (qr_box_x, qr_box_y, qr_box_x + qr_box_w, qr_box_y + qr_box_h),
            radius=12,
            fill=(255, 255, 255, 255),
            outline=(220, 222, 225, 255),
            width=1,
        )

        paste_qr_x = qr_box_x + (qr_box_w - qr_w) // 2
        paste_qr_y = qr_box_y + (qr_box_h - qr_h) // 2
        card.paste(qr_display, (paste_qr_x, paste_qr_y), mask=qr_display)

        # 4. Text dưới cùng
        draw.text(
            (card_w // 2, card_h - 22),
            "Scan with Discord Mobile App",
            fill=(148, 155, 164, 255),
            anchor="mm",
        )

        out = BytesIO()
        card.save(out, format="PNG")
        out.seek(0)
        return out
    except Exception:
        out = BytesIO(qr_image_bytes)
        out.seek(0)
        return out


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


async def run_remote_auth(
    on_fingerprint: Optional[Callable[[Any], Awaitable[None]]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    captcha: Optional[dict] = None,
    on_notice: Optional[Callable[[str], Awaitable[None]]] = None,
) -> RemoteAuthResult:
    """Chay toan bo luong QR login.

    on_fingerprint: callback async duoc goi 1 lan khi nhan duoc fingerprint hoac anh QR PNG
                    (trong do nen gui anh QR ra Discord).
    captcha: {"provider": "web"|"2captcha"|"capsolver"|"nopecha", "api_key": "...",
              "gemini_key": "...", "nopecha_key": "..."} neu co.
             Khi provider == "web", mo Chromium VPS, lay ma QR gui ra kenh de quet.
             Chi khi Discord bat giai Captcha moi mo Stream VPS gui link.
    on_notice: callback gui thong bao tien trinh.
    Tra ve RemoteAuthResult; neu that bai thi raise RemoteAuthError.
    """
    provider = str((captcha or {}).get("provider") or "").strip().lower()
    if provider == "web":
        from .remote_screen import solve_via_discord_web_qr
        return await solve_via_discord_web_qr(
            on_qr_image=on_fingerprint,
            on_notice=on_notice,
            timeout=timeout,
        )

    _require_deps()

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_der = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    encoded_pub = base64.b64encode(pub_der).decode()

    def _decrypt(value: str) -> bytes:
        return key.decrypt(
            base64.b64decode(value),
            padding.OAEP(
                mgf=padding.MGF1(hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

    t0 = time.monotonic()
    deadline = t0 + max(30.0, float(timeout))
    fingerprint_sent = False
    user_id = user_name = user_avatar = None  # tu pending_ticket

    conn = aiohttp.TCPConnector(limit=4)
    async with aiohttp.ClientSession(connector=conn, headers={"User-Agent": _UA}) as http:
        try:
            ws_ctx = http.ws_connect(
                GATEWAY_URL,
                headers={"Origin": GATEWAY_ORIGIN},
                autoping=True,
            )
        except Exception as exc:
            raise RemoteAuthError("network", f"{type(exc).__name__}: {exc}")

        async with ws_ctx as ws:
            # Reader: day tin nhan vao queue -> loop chinh chi doc queue (cancel-safe)
            queue: asyncio.Queue = asyncio.Queue()

            async def _reader() -> None:
                try:
                    while True:
                        m = await ws.receive()
                        if m.type == aiohttp.WSMsgType.TEXT:
                            await queue.put(("msg", m.data))
                        elif m.type in (aiohttp.WSMsgType.CLOSE,
                                        aiohttp.WSMsgType.CLOSING,
                                        aiohttp.WSMsgType.CLOSED,
                                        aiohttp.WSMsgType.ERROR):
                            await queue.put(("closed", None))
                            return
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await queue.put(("closed", None))

            reader = asyncio.create_task(_reader())
            getter: Optional[asyncio.Task] = None
            hb_interval = 41.25
            next_hb: Optional[float] = None

            try:
                while True:
                    now = time.monotonic()
                    if now >= deadline:
                        raise RemoteAuthError(
                            "timeout", "Het thoi gian cho quet QR (ma QR het han).")
                    wait = deadline - now
                    if next_hb is not None:
                        wait = min(wait, max(0.0, next_hb - now))

                    if getter is None or getter.done():
                        getter = asyncio.create_task(queue.get())
                    done, _ = await asyncio.wait({getter}, timeout=wait)

                    if getter not in done:
                        # heartbeat khi den han (khong cancel getter -> khong mat tin)
                        if next_hb is not None and time.monotonic() >= next_hb:
                            if ws.closed:
                                raise RemoteAuthError("connection", "Gateway dong ket noi.")
                            await ws.send_json({"op": "heartbeat"})
                            next_hb = time.monotonic() + hb_interval
                        continue

                    kind, data = getter.result()
                    getter = None
                    if kind == "closed":
                        raise RemoteAuthError(
                            "connection",
                            "Gateway dong ket noi (kiem tra lai ket noi/Origin).")

                    try:
                        msg = json.loads(data)
                    except Exception:
                        continue
                    op = msg.get("op")

                    if op == "hello":
                        try:
                            hb_interval = max(1.0, float(msg.get("heartbeat_interval") or 41250) / 1000.0)
                        except Exception:
                            hb_interval = 41.25
                        try:
                            timeout_ms = float(msg.get("timeout_ms") or 0)
                        except Exception:
                            timeout_ms = 0.0
                        if timeout_ms > 0:
                            # gan deadline theo server, thieu 1s de khong cham gateway close
                            deadline = min(deadline, t0 + timeout_ms / 1000.0 - 1.0)
                        next_hb = time.monotonic() + hb_interval
                        await ws.send_json({"op": "init", "encoded_public_key": encoded_pub})

                    elif op == "heartbeat_ack":
                        pass

                    elif op == "nonce_proof":
                        enc_nonce = msg.get("encrypted_nonce")
                        if not enc_nonce:
                            raise RemoteAuthError("connection", "Gateway gui nonce rong.")
                        try:
                            nonce = _decrypt(enc_nonce)
                        except Exception:
                            raise RemoteAuthError("connection", "Giai ma nonce loi.")
                        proof = _b64url(hashlib.sha256(nonce).digest())
                        await ws.send_json({"op": "nonce_proof", "proof": proof})

                    elif op == "pending_remote_init":
                        fp = msg.get("fingerprint")
                        if not fp:
                            raise RemoteAuthError("connection", "Thieu fingerprint tu gateway.")
                        if on_fingerprint is not None and not fingerprint_sent:
                            fingerprint_sent = True
                            try:
                                await on_fingerprint(fp)
                            except RemoteAuthError:
                                raise
                            except Exception as exc:
                                raise RemoteAuthError(
                                    "qr", f"Loi tao/gui QR: {type(exc).__name__}: {exc}")

                    elif op == "pending_ticket":
                        try:
                            raw = _decrypt(msg.get("encrypted_user_payload") or "").decode("utf-8")
                            parts = raw.split(":", 3)
                            if len(parts) == 4:
                                user_id, _disc, user_avatar, user_name = parts
                        except Exception:
                            pass  # thong tin user chi mang tinh tham khao

                    elif op == "pending_login":
                        ticket = msg.get("ticket")
                        if not ticket:
                            raise RemoteAuthError("connection", "pending_login khong co ticket.")
                        return await _exchange_ticket(
                            http, ticket, _decrypt, user_id, user_name, user_avatar,
                            captcha=captcha, on_notice=on_notice)

                    elif op == "cancel":
                        raise RemoteAuthError(
                            "cancel", "Ban da huy quet ma tren dien thoai.")

                    # cac op khac (khong ro) -> bo qua
            finally:
                if getter is not None and not getter.done():
                    getter.cancel()
                if not reader.done():
                    reader.cancel()


# ── CAPTCHA: AI (Gemini Flash + Chromium) -> service key -> free retry ─────
CAPTCHA_PAGE_URL = "https://discord.com/login"
_RETRY_DELAYS = (6, 12, 20)  # giay - cac lan retry mien phi khi Discord bat captcha

# Cac model Gemini Flash duoc hcaptcha-challenger ho tro (flash = free tier on dinh)
_AI_FLASH_MODELS = ("gemini-2.5-flash", "gemini-2.5-flash-lite")
_AI_SOLVE_TIMEOUT = 150.0  # giay - toi da cho 1 lan AI giai (mo browser + click)


async def _notice(on_notice, text: str) -> None:
    if on_notice is None:
        return
    try:
        await on_notice(text)
    except Exception:
        pass


async def _solve_captcha(http, provider: str, api_key: str, sitekey: str,
                         rqdata: Optional[str], invisible: bool = False) -> str:
    """Goi service giai hCaptcha, tra ve token. Raise RemoteAuthError neu loi."""
    p = (provider or "").strip().lower()
    if p in ("2captcha", "twocaptcha"):
        return await _solve_2captcha(http, api_key, sitekey, rqdata, invisible)
    if p == "capsolver":
        return await _solve_capsolver(http, api_key, sitekey, rqdata, invisible)
    if p == "nopecha":
        return await _solve_nopecha(http, api_key, sitekey, rqdata)
    raise RemoteAuthError(
        "captcha",
        f"Provider captcha khong ho tro: {provider!r} (dung 'nopecha' | '2captcha' | 'capsolver').")


async def _solve_2captcha(http, api_key: str, sitekey: str,
                          rqdata: Optional[str], invisible: bool) -> str:
    """2Captcha classic API: in.php -> res.php (poll)."""
    payload = {
        "key": api_key, "method": "hcaptcha", "sitekey": sitekey,
        "pageurl": CAPTCHA_PAGE_URL, "json": 1,
    }
    if rqdata:
        payload["data"] = rqdata
    if invisible:
        payload["invisible"] = 1
    try:
        async with http.post("https://2captcha.com/in.php", data=payload,
                             timeout=aiohttp.ClientTimeout(total=30)) as resp:
            body = await resp.json(content_type=None)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise RemoteAuthError("captcha", f"2captcha loi gui: {type(exc).__name__}")
    if not isinstance(body, dict) or body.get("status") != 1:
        detail = body.get("request") if isinstance(body, dict) else body
        raise RemoteAuthError("captcha", f"2captcha tu choi: {detail}")
    task_id = str(body.get("request") or "").strip()
    deadline = time.monotonic() + 200
    while time.monotonic() < deadline:
        await asyncio.sleep(8)
        try:
            async with http.get(
                "https://2captcha.com/res.php",
                params={"key": api_key, "action": "get", "id": task_id, "json": 1},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                r = await resp.json(content_type=None)
        except asyncio.CancelledError:
            raise
        except Exception:
            continue
        if not isinstance(r, dict):
            continue
        if r.get("status") == 1 and r.get("request"):
            return str(r.get("request"))
        if r.get("request") not in ("CAPCHA_NOT_READY", None):
            raise RemoteAuthError("captcha", f"2captcha: {r.get('request')}")
    raise RemoteAuthError("captcha", "2captcha het thoi gian giai (200s).")


async def _solve_nopecha(http, api_key: str, sitekey: str,
                          rqdata: Optional[str]) -> str:
    """NopeCHA Token API: POST /token/ -> GET /token/ (poll).

    Pure HTTP, khong can browser. Free: 100 credits/ngay (moi captcha ton
    5 credits ~ 20 captcha/ngay). Key lay tai https://dashboard.nopecha.com
    (login Google/GitHub la co key, khong can nap tien).
    Ho tro ca hCaptcha Enterprise (Discord) - can gui rqdata.
    """
    payload: dict = {
        "key": api_key, "type": "hcaptcha",
        "sitekey": sitekey, "url": CAPTCHA_PAGE_URL,
    }
    if rqdata:
        payload["data"] = {"rqdata": rqdata}
    try:
        async with http.post("https://api.nopecha.com/token/",
                             json=payload,
                             timeout=aiohttp.ClientTimeout(total=30)) as resp:
            body = await resp.json(content_type=None)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise RemoteAuthError("captcha", f"NopeCHA loi gui: {type(exc).__name__}")
    if not isinstance(body, dict) or not body.get("data"):
        raise RemoteAuthError("captcha", f"NopeCHA tu choi: {body}")
    job_id = str(body.get("data"))
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        await asyncio.sleep(6)
        try:
            async with http.get(
                "https://api.nopecha.com/token/",
                params={"key": api_key, "id": job_id},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                r = await resp.json(content_type=None)
        except asyncio.CancelledError:
            raise
        except Exception:
            continue
        if not isinstance(r, dict):
            continue
        token = r.get("data") or ""
        if token and str(token).startswith("P0_"):
            return str(token)
        err = r.get("error")
        if err not in (None, 14):  # 14 = Incomplete job (chua xong, poll tiep)
            raise RemoteAuthError("captcha", f"NopeCHA: {r.get('message') or r}")
    raise RemoteAuthError("captcha", "NopeCHA het thoi gian giai (180s).")


async def _solve_capsolver(http, api_key: str, sitekey: str,
                           rqdata: Optional[str], invisible: bool) -> str:
    """CapSolver API: createTask -> getTaskResult (poll)."""
    task = {
        "type": "HCaptchaTaskProxyLess",
        "websiteURL": CAPTCHA_PAGE_URL,
        "websiteKey": sitekey,
    }
    if invisible:
        task["isInvisible"] = True
    if rqdata:
        task["enterprisePayload"] = {"rqdata": rqdata}
    try:
        async with http.post(
            "https://api.capsolver.com/createTask",
            json={"clientKey": api_key, "task": task},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            body = await resp.json(content_type=None)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise RemoteAuthError("captcha", f"CapSolver loi gui: {type(exc).__name__}")
    if not isinstance(body, dict) or body.get("errorId"):
        detail = (body.get("errorDescription") or body.get("errorId")) if isinstance(body, dict) else body
        raise RemoteAuthError("captcha", f"CapSolver: {detail}")
    task_id = body.get("taskId")
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        await asyncio.sleep(5)
        try:
            async with http.post(
                "https://api.capsolver.com/getTaskResult",
                json={"clientKey": api_key, "taskId": task_id},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                r = await resp.json(content_type=None)
        except asyncio.CancelledError:
            raise
        except Exception:
            continue
        if not isinstance(r, dict) or r.get("errorId"):
            continue
        if r.get("status") == "ready":
            sol = r.get("solution") or {}
            token = sol.get("gRecaptchaResponse") or sol.get("token") or ""
            if token:
                return str(token)
            raise RemoteAuthError("captcha", "CapSolver xong nhung khong co token.")
    raise RemoteAuthError("captcha", "CapSolver het thoi gian giai (180s).")


def _gemini_key(captcha: Optional[dict]) -> str:
    """Lay Gemini key theo thu tu:
    1. config captcha (gemini_key) -> 2. env GEMINI_API_KEY/GOOGLE_API_KEY
    3. fallback: doc GEMINI_API_KEY trong apps/discord_bot/core/aicoresys.py
       (parse text, khong import de tranh keo ca discord_bot len)."""
    cfg = captcha or {}
    for src in (cfg.get("gemini_key"), cfg.get("gemini_api_key")):
        if src and str(src).strip():
            return str(src).strip()
    for env in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        try:
            v = (os.environ.get(env) or "").strip()
        except Exception:
            v = ""
        if v:
            return v
    try:
        from pathlib import Path as _P
        import re as _re
        ai = (_P(__file__).resolve().parents[2]
              / "discord_bot" / "core" / "aicoresys.py")
        if ai.exists():
            m = _re.search(
                r'GEMINI_API_KEY\s*=\s*["\']([^"\']+)["\']',
                ai.read_text(encoding="utf-8", errors="ignore"))
            if m and m.group(1).strip():
                return m.group(1).strip()
    except Exception:
        pass
    return ""


def _ai_available() -> tuple:
    """Kiem tra playwright co san khong. Tra (ok, ly_do).

    Ban LITE: chi can playwright + chromium (khong bat buoc hcaptcha-challenger).
    Co hcaptcha-challenger -> full-auto cu; khong co -> dung Gemini REST + click.
    """
    try:
        import importlib.util as _u
        if _u.find_spec("playwright") is None:
            return False, "thieu playwright (`pip install playwright` + `playwright install chromium`)"
        return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _ai_fullauto_available() -> bool:
    """Co hcaptcha-challenger (ban full-auto cu, nang ~2GB torch) khong?"""
    try:
        import importlib.util as _u
        return _u.find_spec("hcaptcha_challenger") is not None
    except Exception:
        return False


def _ai_stealth_hook(pw) -> bool:
    """Hook playwright-stealth vao playwright instance neu co cai lib.

    Che navigator.webdriver, plugins, languages, WebGL vendor/renderer,
    chrome.*, sec-ch-ua... de hCaptcha Enterprise cham diem nhu browser
    that thay vi chromium headless. Goi NGAY sau
    `async with async_playwright() as pw:` va TRUOC khi launch browser.
    Tra ve True neu da hook, False neu thieu lib / loi (van chay tiep).
    """
    try:
        from playwright_stealth import Stealth
        Stealth().hook_playwright_context(pw)
        return True
    except Exception:
        return False



def _ai_harness_html(sitekey: str, rqdata: str, invisible: bool) -> str:
    """Trang harness render widget hCaptcha enterprise voi sitekey/rqdata that (Tiếng Việt)."""
    import json
    sk_json = json.dumps(sitekey)
    rq_json = json.dumps(rqdata or "")
    size = "invisible" if invisible else "normal"
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<script src="https://js.hcaptcha.com/1/api.js?hl=vi&render=explicit" async defer></script>'
        '</head><body style="background:#313338;color:#fff;font-family:sans-serif;padding:30px">'
        '<h3 style="margin-bottom:15px">Discord Captcha — Xác minh người dùng</h3>'
        '<div id="cap"></div><script>'
        "function onLoad() { try { window.hcaptcha.render('cap', {"
        f'sitekey: {sk_json}, size: "{size}", theme: "dark", hl: "vi", rqdata: {rq_json}'
        "}); } catch (e) { document.title = 'render-err:' + e; } }"
        "window.onload = function() { let n = 0;"
        " const t = setInterval(() => {"
        " if (window.hcaptcha && window.hcaptcha.render) { clearInterval(t); onLoad(); }"
        " else if (++n > 40) clearInterval(t); }, 250); };"
        "</script></body></html>"
    )


async def _ai_wait_token(page, timeout: float = 20.0) -> str:
    """Poll h-captcha-response / hcaptcha.getResponse trong trang harness."""
    deadline = time.monotonic() + max(5.0, float(timeout))
    js = (
        "() => { try {"
        ' const el = document.querySelector("[name=h-captcha-response]");'
        " if (el && el.value && el.value.length > 20) return el.value;"
        " if (window.hcaptcha && window.hcaptcha.getResponse) {"
        " const t = window.hcaptcha.getResponse();"
        " if (t && t.length > 20) return t; }"
        " } catch (e) {} return ''; }"
    )
    while time.monotonic() < deadline:
        try:
            v = await page.evaluate(js)
        except Exception:
            v = ""
        if v and len(str(v)) > 20:
            return str(v)
        await asyncio.sleep(1.0)
    return ""


_GEMINI_LITE_MODELS = ("gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash")
_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


async def _ai_human_move(page, x1: float, y1: float, x2: float, y2: float,
                       steps: int = 12) -> None:
    """Gia lap chuot nguoi: di cong (bezier) + jitter + toc do ngau nhien.

    hCaptcha Enterprise cham diem motionData — duong thang toc do deu
    cua page.mouse.click() de bi danh dau bot. Ham nay di cong cong,
    moi buoc sleep 8-25ms, cuoi duong rung nhe vai pixel nhu tay nguoi.
    """
    import math as _math
    import random as _rnd
    try:
        mx = (x1 + x2) / 2.0 + _rnd.uniform(-40, 40)
        my = (y1 + y2) / 2.0 + _rnd.uniform(-30, 30)
        n = max(4, min(24, int(steps)))
        for i in range(1, n + 1):
            t = i / float(n)
            bx = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * mx + t ** 2 * x2
            by = (1 - t) ** 2 * y1 + 2 * (1 - t) * t * my + t ** 2 * y2
            bx += _rnd.uniform(-1.5, 1.5)
            by += _rnd.uniform(-1.5, 1.5)
            await page.mouse.move(bx, by)
            await page.wait_for_timeout(_rnd.randint(8, 25))
        await page.mouse.move(x2 + _rnd.uniform(-2, 2),
                              y2 + _rnd.uniform(-2, 2))
        await page.wait_for_timeout(_rnd.randint(60, 180))
    except Exception:
        try:
            await page.mouse.move(x2, y2)
        except Exception:
            pass


async def _ai_human_click(page, x: float, y: float) -> None:
    """Click kieu nguoi: lia chuot cong tu vi tri hien tai roi moi down/up."""
    import random as _rnd
    try:
        pos = await page.evaluate(
            "() => ({x: window.__mx || 640, y: window.__my || 450})")
        try:
            await page.evaluate(
                "([x, y]) => { window.__mx = x; window.__my = y; }", [x, y])
        except Exception:
            pass
        await _ai_human_move(page, float(pos.get("x") or 640),
                             float(pos.get("y") or 450), x, y)
        await page.wait_for_timeout(_rnd.randint(80, 220))
        await page.mouse.down()
        await page.wait_for_timeout(_rnd.randint(70, 160))
        await page.mouse.up()
        await page.wait_for_timeout(_rnd.randint(250, 500))
    except Exception:
        try:
            await page.mouse.click(x, y)
        except Exception:
            pass


async def _ai_shot_challenge(frame) -> bytes:
    """Tai anh challenge ve: screenshot RIENG iframe captcha (khong chup ca page).

    Tra ve PNG bytes (~50-150KB) — nhe hon chup full page, AI nhin ro o 3x3.
    """
    try:
        el = await frame.query_selector(
            ".challenge-container, .challenge, .task-grid, .task-image")
        if el:
            bb = await el.bounding_box()
            if bb and bb.get("width", 0) > 60:
                shot = await el.screenshot()
                if shot and len(shot) > 2000:
                    return bytes(shot)
    except Exception:
        pass
    try:
        shot = await frame.screenshot()
        if shot and len(shot) > 2000:
            return bytes(shot)
    except Exception:
        pass
    return b""


async def _ai_click_cells_human(frame, page, png: bytes, cells: list) -> bool:
    """Map o 0-8 tu anh tai ve -> toa do that trong iframe -> click chuot nguoi.

    Dung kich thuoc anh (w,h) lam he quy chieu: o c co tam
    (((c%3)+0.5)/3*w, ((c//3)+0.5)/3*h) tren anh, cong offset cua
    element challenge trong page. Tra False neu khong map duoc.
    """
    if not cells:
        return False
    try:
        from PIL import Image as _Img
        import io as _io
        im = _Img.open(_io.BytesIO(png))
        iw, ih = im.size
    except Exception:
        return False
    try:
        el = await frame.query_selector(
            ".challenge-container, .challenge, .task-grid, .task-image")
        box = await el.bounding_box() if el else None
    except Exception:
        box = None
    try:
        if box and box.get("width", 0) > 60:
            sx = float(box["width"]) / float(iw)
            sy = float(box["height"]) / float(ih)
            ox, oy = float(box["x"]), float(box["y"])
        else:
            # fallback: iframe fit-content — anh ~= element
            ifr = await page.query_selector("iframe[src*='hcaptcha.com']")
            bb = await ifr.bounding_box() if ifr else None
            if not bb:
                return False
            sx = float(bb["width"]) / float(iw)
            sy = float(bb["height"]) / float(ih)
            ox, oy = float(bb["x"]), float(bb["y"])
        import random as _rnd
        for c in cells[:9]:
            c = int(c) % 9
            px = ox + ((c % 3) + 0.5) / 3.0 * iw * sx + _rnd.uniform(-3, 3)
            py = oy + ((c // 3) + 0.5) / 3.0 * ih * sy + _rnd.uniform(-3, 3)
            await _ai_human_click(page, px, py)
        return True
    except Exception:
        return False


async def _gemini_pick_cells(http, png: bytes, prompt_text: str,
                             gemini_key: str) -> list:
    """Gui screenshot (base64) len Gemini REST, hoi o nao can click.

    Tra ve list index 0-8 (luoi 3x3). Raise RemoteAuthError neu het quota/loi.
    Chi dung aiohttp + key cloud — khong can torch.
    """
    import base64 as _b64
    b64 = _b64.b64encode(png).decode("ascii")
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt_text},
                {"inline_data": {"mime_type": "image/png", "data": b64}},
            ],
        }],
        "generation_config": {"temperature": 0.1, "max_output_tokens": 256},
    }
    last_err = "unknown"
    for model in _GEMINI_LITE_MODELS:
        url = f"{_GEMINI_API_BASE}/{model}:generateContent?key={gemini_key}"
        try:
            async with http.post(
                url, json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 429:
                    last_err = f"quota-{model}"
                    continue
                if resp.status != 200:
                    try:
                        last_err = (await resp.text())[:120]
                    except Exception:
                        last_err = f"HTTP {resp.status}"
                    continue
                data = await resp.json(content_type=None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            continue
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if "text" in p)
        except Exception:
            last_err = "empty candidates"
            continue
        import re as _re
        cells = sorted({int(x) for x in _re.findall(r"[0-8]", text or "")})
        if cells:
            return cells
        last_err = f"AI tra ve rong ({(text or '')[:80]})"
    raise RemoteAuthError("captcha", f"Gemini lite het quota/loi: {last_err}.")


async def _solve_captcha_ai_lite(sitekey: str, rqdata: Optional[str],
                                 invisible: bool, gemini_key: str) -> str:
    """Ban LITE: Chromium that + chup man hinh -> Gemini REST -> click.

    Khong can torch/transformers/hcaptcha-challenger (~500MB thay vi ~3GB).
    """
    ok, why = _ai_available()
    if not ok:
        raise RemoteAuthError("captcha", f"AI solver khong san sang: {why}.")
    if not gemini_key:
        raise RemoteAuthError("captcha", "Thieu Gemini key cho AI solver.")
    from playwright.async_api import async_playwright

    html = _ai_harness_html(sitekey, rqdata or "", invisible)

    async def _run() -> str:
        async with async_playwright() as pw:
            _ai_stealth_hook(pw)
            try:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
            except Exception as exc:
                raise RemoteAuthError(
                    "captcha",
                    "Chua cai Chromium (`playwright install chromium`). "
                    f"Chi tiet: {exc}")
            try:
                page = await browser.new_page(viewport={"width": 1280, "height": 900})
                # PHUC VU harness tren cung origin discord.com — KHONG tai trang
                # login that, KHONG nhap email/pass. Chi de hCaptcha Enterprise
                # chap nhan hostname discord.com. Noi dung = widget captcha voi
                # dung sitekey/rqdata Discord gui ve o buoc doi ticket.
                async def _fulfill(route):
                    try:
                        await route.fulfill(
                            status=200, content_type="text/html", body=html)
                    except Exception:
                        try:
                            await route.abort()
                        except Exception:
                            pass
                try:
                    await page.route("https://discord.com/login*", _fulfill)
                except Exception:
                    pass
                try:
                    await page.goto(
                        "https://discord.com/login",
                        wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                await page.wait_for_timeout(3000)
                hc = [f for f in page.frames if "hcaptcha.com" in (f.url or "")]
                if not hc:
                    await page.wait_for_timeout(4000)
                    hc = [f for f in page.frames if "hcaptcha.com" in (f.url or "")]
                if not hc:
                    raise RemoteAuthError(
                        "captcha", "AI lite: khong tai duoc widget hCaptcha.")
                try:
                    box = await page.query_selector("iframe[src*='hcaptcha.com']")
                    if box:
                        bb = await box.bounding_box()
                        if bb:
                            await page.mouse.click(
                                bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
                            await page.wait_for_timeout(3000)
                except Exception:
                    pass
                token = await _ai_wait_token(page, timeout=8.0)
                if token:
                    return token
                if aiohttp is None:
                    raise RemoteAuthError("captcha", "AI lite: thieu aiohttp.")
                import aiohttp as _aio
                cap_frame = hc[0]
                for _rnd in range(3):
                    # 1. TAI ANH VE: screenshot rieng iframe challenge (~50-150KB)
                    try:
                        png = await _ai_shot_challenge(cap_frame)
                    except Exception as exc:
                        raise RemoteAuthError(
                            "captcha", f"AI lite: tai anh challenge loi ({exc}).")
                    if not png:
                        try:
                            png = await page.screenshot(full_page=False)
                        except Exception as exc:
                            raise RemoteAuthError(
                                "captcha", f"AI lite: chup man hinh loi ({exc}).")
                    prompt = (
                        "Day la anh chup captcha hCaptcha (luoi 3x3, o danh so "
                        "0 1 2 / 3 4 5 / 6 7 8 tu trai sang phai, tren xuong duoi). "
                        "Doc yeu cau roi tra loi CHI gom cac so o can click, "
                        "cach nhau boi dau phay (vi du: 0,4,8). "
                        "Khong thay challenge thi tra loi: none.")
                    async with _aio.ClientSession() as http:
                        cells = await _gemini_pick_cells(http, png, prompt, gemini_key)
                    # 2. GUI AI GIAI + 3. GIA LAP CHUOT NGUOI (lia cong + jitter)
                    try:
                        ok_click = await _ai_click_cells_human(
                            cap_frame, page, png, cells)
                        if not ok_click:
                            raise RemoteAuthError(
                                "captcha", "AI lite: khong map duoc toa do o.")
                        for sel in ("button:has-text('Verify')",
                                    "button:has-text('Submit')",
                                    "button[type='submit']"):
                            try:
                                btn = await cap_frame.query_selector(sel)
                                if btn:
                                    bb2 = await btn.bounding_box()
                                    if bb2:
                                        await _ai_human_click(
                                            page,
                                            bb2["x"] + bb2["width"] / 2,
                                            bb2["y"] + bb2["height"] / 2)
                                    else:
                                        await btn.click()
                                    break
                            except Exception:
                                pass
                    except RemoteAuthError:
                        raise
                    except Exception as exc:
                        raise RemoteAuthError(
                            "captcha", f"AI lite: click loi ({type(exc).__name__}).")
                    await page.wait_for_timeout(3000)
                    token = await _ai_wait_token(page, timeout=10.0)
                    if token:
                        return token
                raise RemoteAuthError("captcha", "AI lite giai 3 vong chua ra token.")
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass

    try:
        return await asyncio.wait_for(_run(), timeout=_AI_SOLVE_TIMEOUT + 60)
    except asyncio.TimeoutError:
        raise RemoteAuthError("captcha", "AI lite giai qua lau (het timeout).")
    except RemoteAuthError:
        raise
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise RemoteAuthError(
            "captcha", f"AI lite solver loi: {type(exc).__name__}: {exc}")


async def _solve_captcha_ai(sitekey: str, rqdata: Optional[str],
                            invisible: bool, gemini_key: str) -> str:
    """Giai hCaptcha Enterprise bang AI (Gemini Flash + Chromium that).

    Mo Chromium headless, render widget voi dung sitekey/rqdata,
    dung hcaptcha-challenger (Gemini Flash vision) click challenge,
    lay h-captcha-response token gan dung rqdata + hostname discord.com.
    Raise RemoteAuthError khi that bai.

    Dispatcher: co hcaptcha-challenger -> full-auto cu; khong co ->
    ban LITE (screenshot + Gemini REST + click, khong can torch).
    """
    if not _ai_fullauto_available():
        return await _solve_captcha_ai_lite(sitekey, rqdata, invisible, gemini_key)
    ok, why = _ai_available()
    if not ok:
        raise RemoteAuthError("captcha", f"AI solver khong san sang: {why}.")
    if not gemini_key:
        raise RemoteAuthError(
            "captcha",
            "Thieu Gemini key cho AI solver (config captcha.gemini_key "
            "hoac env GEMINI_API_KEY).")
    from playwright.async_api import async_playwright

    html = _ai_harness_html(sitekey, rqdata or "", invisible)

    async def _run() -> str:
        async with async_playwright() as pw:
            _ai_stealth_hook(pw)
            try:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
            except Exception as exc:
                raise RemoteAuthError(
                    "captcha",
                    "Chua cai Chromium (`playwright install chromium`). "
                    f"Chi tiet: {exc}")
            try:
                page = await browser.new_page(viewport={"width": 1280, "height": 900})
                from hcaptcha_challenger import AgentV, AgentConfig
                from hcaptcha_challenger.agent.challenger import RoboticArm

                # Patch: tranh nộp bài rỗng khi Gemini khong tim duoc toa do phu hop
                _orig_label_select = getattr(RoboticArm, "_orig_label_select", RoboticArm.challenge_image_label_select)
                RoboticArm._orig_label_select = _orig_label_select

                async def _patched_label_select(arm_self, job_type):
                    frame_challenge = await arm_self.get_challenge_frame_locator()
                    crumb_count = await arm_self.check_crumb_count()
                    cache_key = arm_self.config.create_cache_key(arm_self.captcha_payload)

                    for cid in range(crumb_count):
                        await arm_self.page.wait_for_timeout(arm_self.config.WAIT_FOR_CHALLENGE_VIEW_TO_RENDER_MS)
                        raw, projection = await arm_self._capture_spatial_mapping(frame_challenge, cache_key, cid)
                        user_prompt = arm_self._match_user_prompt(job_type)
                        response = await arm_self._spatial_point_reasoner(
                            challenge_screenshot=raw,
                            grid_divisions=projection,
                            auxiliary_information=user_prompt,
                        )
                        if not response.points:
                            # Toa do rong -> de qua kho hoac model bi hallucinate.
                            # Tu dong refresh sang cau hoi khac thay vi nop bai rong de chet!
                            await arm_self.refresh_challenge()
                            await arm_self.page.wait_for_timeout(2000)
                            raise RuntimeError("AI khong tim duoc diem click hop le, da refresh doi cau hoi.")

                        for point in response.points:
                            await arm_self.page.mouse.click(point.x, point.y, delay=180)
                            await arm_self.page.wait_for_timeout(500)

                        from contextlib import suppress
                        with suppress(TimeoutError):
                            submit_btn = frame_challenge.locator("//div[@class='button-submit button']")
                            await arm_self.click_by_mouse(submit_btn)

                RoboticArm.challenge_image_label_select = _patched_label_select

                os.environ["GEMINI_API_KEY"] = gemini_key
                cfg = AgentConfig(
                    GEMINI_API_KEY=gemini_key,  # type: ignore[call-arg]
                    CHALLENGE_CLASSIFIER_MODEL=_AI_FLASH_MODELS[0],
                    IMAGE_CLASSIFIER_MODEL=_AI_FLASH_MODELS[0],
                    SPATIAL_POINT_REASONER_MODEL=_AI_FLASH_MODELS[0],
                    SPATIAL_PATH_REASONER_MODEL=_AI_FLASH_MODELS[0],
                    EXECUTION_TIMEOUT=_AI_SOLVE_TIMEOUT,
                    RESPONSE_TIMEOUT=90,
                    RETRY_ON_FAILURE=True,
                    ignore_request_questions=[
                        "can be fully covered",
                        "covered by the object shown",
                        "fully covered",
                        "covered by",
                        "contained in",
                        "can fit inside",
                        "fit inside",
                        "part of the object",
                    ],
                )
                # Dang ky AgentV NGAY TRUOC KHI goto de bat duoc moi response /getcaptcha/ va /checkcaptcha/
                agent = AgentV(page, cfg)

                # PHUC VU harness tren cung origin discord.com — KHONG tai trang
                # login that, KHONG nhap email/pass. Chi de hCaptcha Enterprise
                # chap nhan hostname discord.com. Noi dung = widget captcha voi
                # dung sitekey/rqdata Discord gui ve o buoc doi ticket.
                async def _fulfill(route):
                    try:
                        await route.fulfill(
                            status=200, content_type="text/html", body=html)
                    except Exception:
                        try:
                            await route.abort()
                        except Exception:
                            pass
                try:
                    await page.route("https://discord.com/login*", _fulfill)
                except Exception:
                    pass
                try:
                    await page.goto(
                        "https://discord.com/login",
                        wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                await page.wait_for_timeout(3000)
                frames = page.frames
                hc = [f for f in frames if "hcaptcha.com" in (f.url or "")]
                if not hc:
                    await page.wait_for_timeout(4000)
                    hc = [f for f in page.frames if "hcaptcha.com" in (f.url or "")]
                if not hc:
                    raise RemoteAuthError("captcha", "AI: khong tai duoc widget hCaptcha.")

                # Click vao checkbox de mo challenge
                try:
                    box = await page.query_selector("iframe[src*='hcaptcha.com']")
                    if box:
                        bb = await box.bounding_box()
                        if bb:
                            await page.mouse.click(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
                            await page.wait_for_timeout(2500)
                except Exception:
                    pass

                token = await _ai_wait_token(page, timeout=5.0)
                if token:
                    return token

                try:
                    signal = await agent.wait_for_challenge()
                except Exception as exc:
                    # Neu timeout response hoac loi, van kiem tra xem token da ve chua
                    token = await _ai_wait_token(page, timeout=5.0)
                    if token:
                        return token
                    raise RemoteAuthError(
                        "captcha", f"AI giai loi: {type(exc).__name__}: {exc}")

                sname = str(getattr(signal, "name", signal))
                token = await _ai_wait_token(page, timeout=15.0)
                if token:
                    return token
                if "SUCCESS" not in sname:
                    raise RemoteAuthError("captcha", f"AI khong vuot duoc challenge ({signal}).")
                raise RemoteAuthError("captcha", "AI pass challenge nhung khong lay duoc token.")
                return token
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass

    try:
        return await asyncio.wait_for(_run(), timeout=_AI_SOLVE_TIMEOUT + 60)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Neu ban AgentV full-auto gap loi (nhu locator None / frame loi),
        # tu dong fallback sang ban AI LITE (screenshot goc + Gemini REST vision)
        try:
            return await _solve_captcha_ai_lite(sitekey, rqdata, invisible, gemini_key)
        except Exception:
            if isinstance(exc, RemoteAuthError):
                raise exc
            raise RemoteAuthError("captcha", f"AI solver loi: {type(exc).__name__}: {exc}")


async def _exchange_ticket(http, ticket, decrypt, user_id, user_name, user_avatar,
                           captcha: Optional[dict] = None,
                           on_notice: Optional[Callable[[str], Awaitable[None]]] = None) -> RemoteAuthResult:
    """Doi ticket lay encrypted_token; xu ly captcha (AI -> NopeCHA free -> API key -> retry free)."""
    api_key = str((captcha or {}).get("api_key") or "").strip()
    provider = str((captcha or {}).get("provider") or "web").strip().lower()
    nopecha_key = str((captcha or {}).get("nopecha_key") or "").strip()
    if not nopecha_key:
        try:
            nopecha_key = (os.environ.get("NOPECHA_API_KEY") or "").strip()
        except Exception:
            pass
    gemini_key = _gemini_key(captcha)
    headers: dict = {}

    async def _post(token: Optional[str] = None, cap_body: Optional[dict] = None):
        post_headers = {
            "User-Agent": _UA,
            "Content-Type": "application/json",
            "Origin": "https://discord.com",
            "Referer": "https://discord.com/login",
            "Accept": "*/*",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        if headers:
            post_headers.update(headers)

        post_json = {"ticket": ticket}
        if token:
            post_headers["X-Captcha-Key"] = token
            post_json["captcha_key"] = token
        if cap_body:
            if cap_body.get("captcha_rqtoken"):
                post_headers["X-Captcha-Rqtoken"] = str(cap_body["captcha_rqtoken"])
                post_json["captcha_rqtoken"] = str(cap_body["captcha_rqtoken"])
            if cap_body.get("captcha_session_id"):
                post_headers["X-Captcha-Session-Id"] = str(cap_body["captcha_session_id"])

        try:
            async with http.post(
                LOGIN_URL,
                json=post_json,
                headers=post_headers,
                timeout=aiohttp.ClientTimeout(total=25),
            ) as resp:
                st = resp.status
                try:
                    b = await resp.json(content_type=None)
                except Exception:
                    b = {}
                return st, (b if isinstance(b, dict) else {})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise RemoteAuthError("network", f"Loi doi ticket: {type(exc).__name__}: {exc}")

    async def _submit(token: str, cap_body: dict):
        st2, b2 = await _post(token=token, cap_body=cap_body)
        print(f"[SUBMIT] Discord phản hồi đổi ticket: status={st2}, body={b2}", flush=True)
        t2 = _extract(st2, b2)
        if t2 is not None:
            return _result(t2), None
        if not _is_captcha(st2, b2):
            raise RemoteAuthError("connection", f"Doi ticket that bai (HTTP {st2}): {b2}")
        return None, b2

    def _extract(st, b) -> Optional[str]:
        if st != 200:
            return None
        enc = b.get("encrypted_token")
        if not enc:
            raise RemoteAuthError("connection", "Phan hoi khong co encrypted_token.")
        try:
            tok = decrypt(enc).decode("utf-8")
        except Exception:
            raise RemoteAuthError("connection", "Giai ma token loi.")
        if not tok:
            raise RemoteAuthError("connection", "Token rong.")
        return tok

    def _is_captcha(st, b) -> bool:
        # dung theo docs Discord: 400 + co captcha_key (hoac captcha_sitekey)
        return st == 400 and (b.get("captcha_key") is not None or bool(b.get("captcha_sitekey")))

    def _result(tok: str) -> RemoteAuthResult:
        return RemoteAuthResult(
            token=tok, user_id=user_id, username=user_name, avatar=user_avatar)

    # 1) Lan doi ticket thu nhat
    status, body = await _post()
    tok = _extract(status, body)
    if tok is not None:
        return _result(tok)
    if not _is_captcha(status, body):
        raise RemoteAuthError("connection", f"Doi ticket that bai (HTTP {status}).")

    # 2.0) Neu config chon dich vu 'web': Chuyen han sang Direct Discord Web (giao dien that)
    if provider == "web":
        from .remote_screen import solve_via_direct_discord_web
        return await solve_via_direct_discord_web(on_notice=on_notice, timeout=180.0)

    # 2) Bi captcha -> AI (Gemini Flash) thu truoc (mien phi, dung key san co)
    if gemini_key:
        sitekey = body.get("captcha_sitekey")
        if sitekey:
            await _notice(
                on_notice,
                "🧩 Discord bắt **captcha** — đang giải bằng **AI (Gemini Flash)** "
                "(1–3 phút, đừng tắt phiên)...")
            try:
                solved = await _solve_captcha_ai(
                    str(sitekey), body.get("captcha_rqdata"),
                    bool(body.get("should_serve_invisible")), gemini_key)
                done, body = await _submit(solved, body)
                if done is not None:
                    return done
            except RemoteAuthError as exc:
                await _notice(on_notice, f"⚠️ AI giải chưa qua ({exc.message}) — mở màn hình VPS...")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await _notice(
                    on_notice, f"⚠️ AI solver lỗi ({type(exc).__name__}) — mở màn hình VPS...")
        else:
            await _notice(on_notice, "⚠️ Discord bắt captcha nhưng không có sitekey — bỏ qua AI.")

    # 3) Web Remote Screencast Fallback: Cho nguoi dung dieu khien chuot tren VPS
    sitekey = body.get("captcha_sitekey")
    if sitekey:
        try:
            from .remote_screen import solve_via_direct_discord_web
            return await solve_via_direct_discord_web(on_notice=on_notice, timeout=180.0)
        except Exception as exc:
            await _notice(on_notice, f"⚠️ Direct Web Login lỗi ({exc}) — chuyển fallback tiếp...")

    # 4) NopeCHA free (100 credits/ngay, pure HTTP, khong can browser)
    if nopecha_key:
        sitekey = body.get("captcha_sitekey")
        if sitekey:
            await _notice(
                on_notice,
                "🧩 Discord bắt **captcha** — đang giải qua **NopeCHA (free)** "
                "(30–90s, đừng tắt phiên)...")
            try:
                solved = await _solve_nopecha(
                    http, nopecha_key, str(sitekey), body.get("captcha_rqdata"))
                done, body = await _submit(solved, body)
                if done is not None:
                    return done
            except RemoteAuthError as exc:
                await _notice(on_notice, f"⚠️ NopeCHA chưa qua ({exc.message}) — chuyển fallback...")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await _notice(
                    on_notice, f"⚠️ NopeCHA lỗi ({type(exc).__name__}) — chuyển fallback...")

    # 5) Bi captcha + co API key -> giai bang service tra phi (2captcha/capsolver)
    if api_key:
        sitekey = body.get("captcha_sitekey")
        if not sitekey:
            raise RemoteAuthError("captcha", "Discord bat captcha nhung khong co sitekey.")
        await _notice(
            on_notice,
            f"🧩 Discord bắt **captcha** — đang giải qua **{provider}** (10–60s, đừng tắt phiên)...")
        solved = await _solve_captcha(
            http, provider, api_key, str(sitekey),
            body.get("captcha_rqdata"), bool(body.get("should_serve_invisible")))
        done, body = await _submit(solved, body)
        if done is not None:
            return done
        raise RemoteAuthError(
            "captcha",
            "Token captcha bi tu choi (doi IP/diem uy tin cua may). Hay chay lai lenh.")

    # 6) Free: auto-retry — captcha o endpoint nay thuong chi hien 1 lan
    for i, delay in enumerate(_RETRY_DELAYS, 1):
        await _notice(
            on_notice,
            f"🔄 Discord bắt **captcha** — auto-retry miễn phí lần {i}/{len(_RETRY_DELAYS)} sau {delay}s...")
        await asyncio.sleep(delay)
        status, body = await _post()
        tok = _extract(status, body)
        if tok is not None:
            return _result(tok)
        if not _is_captcha(status, body):
            raise RemoteAuthError("connection", f"Doi ticket that bai (HTTP {status}).")
    raise RemoteAuthError(
        "captcha",
        "Van bi captcha sau cac lan retry mien phi. Them API key (config.json -> muc "
        "`captcha` co `provider` + `api_key`, hoac env CAPTCHA_API_KEY) de bot tu giai, "
        "hoac thu lai sau.")


async def setup(bot):
    """Extension entrypoint (empty cog for utility module)."""
    pass


